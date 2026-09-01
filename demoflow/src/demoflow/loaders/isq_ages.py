"""Select the single-year 'Âge' header-GROUP block from an ISQ pop workbook and melt
it to pre-junction long rows (spec §8 Age junction).

Sheet "Années d'âge"; a two-row header (level-0 merged GROUP row, level-1 label row)
followed by a units row ('n' / 'ans'), then the data. The single-year block sits under
the level-0 group label 'Âge'; the grouped-age block sits under "Groupe d'âge" /
"Grand groupe d'âge". Selection is by GROUP, never by bare column name — the naive
`pandas header=[6,7]` form is REJECTED by the spec. pandas does not forward-fill merged
group cells, so the sheet is read with `header=None` and the level-0 spans are
reconstructed by ffill.

MEASURED 2026-08-07 against the three committed, sha256-pinned pop workbooks (the
geometry the plan body pinned to pop-as-rmr only — Task 11 calls this builder for all
three, so nothing below is hardcoded to one workbook):

  workbook               group row  label row  units row  data row  geo id     'Code'
  pop-as-rmr-base.xlsx       6          7          8          9     Région1    present
  pop-as-ra-base.xlsx        5          6          7          8     Région1    present
  pop-as-qc-base.xlsx        4          5          6          7     Région     ABSENT

so the header row is LOCATED (never assumed), 'Code' is NOT required (it never reaches
the output), and the geography id column is resolved from {'Région1', 'Région'} with a
raise if neither — or both — is present.

Level-1 age labels read back as FLOATS (1.0, 2.0, …) with two exceptions: age 0 is an
int and the terminal bucket is the string '100+' (-> capped to 100, spec §8). The ffill'd
'Âge' group spans 104 columns of which only 101 are ages — a spacer plus 'Âge moyen' and
'Âge médian' ride under the same group — so non-age labels are skipped and the resulting
span is required to be exactly 0..100.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from demoflow.errors import LoaderError

SHEET = "Années d'âge"

# Required id header labels. 'Code' is deliberately EXCLUDED: pop-as-qc-base.xlsx ships
# no 'Code' column and the builder never emits it — requiring it would reject a valid
# pinned workbook.
_REQUIRED_IDS = ("Scénario", "Année", "Statut", "Sexe")
# Geography id column, spelled differently across the committed workbooks.
_GEO_IDS = ("Région1", "Région")
_AGE_GROUP = "Âge"                 # single-year block level-0 label (byte-exact, NFC)
_TERMINAL_LABELS = frozenset({"100+", "100 +", "100et+", "100 et +"})
_TERMINAL_AGE = 100
_HDR_SCAN_ROWS = 30                # header sits under a few title/source lines


def _norm(value: object) -> str:
    """Header cell -> stripped string ('' for blank), for label comparison only."""
    return str(value).strip() if pd.notna(value) else ""


def _age_of(label: object) -> int | None:
    """Map a level-1 header cell to a single-year age, or None if it is not one.

    A str-only `.isdigit()` test is NOT sufficient: openpyxl returns the single-year
    labels as floats, so `str(np.float64(1.0)) == '1.0'` would reject the whole block.
    """
    if label is None:
        return None
    if isinstance(label, str):
        text = label.strip()
        if text in _TERMINAL_LABELS:
            return _TERMINAL_AGE
        return int(text) if text.isdigit() else None
    try:
        number = float(label)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or not number.is_integer():
        return None
    return int(number)


def _find_group_row(rawnh: pd.DataFrame, name: str) -> int:
    """Locate the level-0 GROUP header row by its id-label tokens (offsets differ per
    workbook). Raises rather than guessing — a drifted header must not silently shift
    the data window."""
    for row in range(min(_HDR_SCAN_ROWS, len(rawnh))):
        tokens = {_norm(v) for v in rawnh.iloc[row]}
        if set(_REQUIRED_IDS) <= tokens and tokens & set(_GEO_IDS):
            return row
    raise LoaderError(
        f"{name}: could not locate the {SHEET!r} header row — id tokens "
        f"{list(_REQUIRED_IDS)} plus one of {list(_GEO_IDS)} not found together in the "
        f"first {_HDR_SCAN_ROWS} rows (schema drift)"
    )


def _first_pos(header: pd.Series, wanted: tuple[str, ...], width: int) -> dict[str, int]:
    """First column POSITION of each wanted header token (id cells are never merged)."""
    found: dict[str, int] = {}
    for pos in range(width):
        token = _norm(header.iloc[pos])
        if token in wanted and token not in found:
            found[token] = pos
    return found


def _as_int_column(column: pd.Series, what: str, name: str) -> np.ndarray:
    """Body column -> int64 array, fail-loud on blank / non-numeric / non-integer."""
    numeric = pd.to_numeric(column, errors="coerce")
    if numeric.isna().any():
        bad = list(pd.unique(column[numeric.isna()]))[:5]
        raise LoaderError(f"{name}: blank or non-numeric {what!r} cell(s) {bad} (schema drift)")
    values = numeric.to_numpy(dtype=float)
    if not np.all(np.mod(values, 1.0) == 0.0):
        raise LoaderError(f"{name}: non-integer {what!r} value(s) (schema drift)")
    return values.astype(np.int64)


def build_single_year_long(path: Path) -> pd.DataFrame:
    """Pre-junction long rows: label, scenario_label, year, status, sex_code, age,
    population. Raw ISQ strings/codes are preserved — the enum junctions, the sex
    additivity/orientation checks and the finiteness gate belong to Task 11."""
    path = Path(path)
    if not path.exists():
        raise LoaderError(f"workbook not found: {path} (re-download is a fallback, spec §4)")
    try:
        rawnh = pd.read_excel(path, sheet_name=SHEET, header=None, engine="openpyxl")
    except ValueError as exc:   # pandas raises ValueError for an absent sheet name
        raise LoaderError(f"{path.name}: sheet {SHEET!r} not readable ({exc}) — schema drift") from exc

    group_row = _find_group_row(rawnh, path.name)
    label_row = group_row + 1
    units_row = group_row + 2
    data_first_row = group_row + 3
    if len(rawnh) <= data_first_row:
        raise LoaderError(f"empty/short sheet {SHEET!r} in {path.name}")

    width = rawnh.shape[1]
    header = rawnh.iloc[group_row]
    labels = rawnh.iloc[label_row]

    id_pos = _first_pos(header, _REQUIRED_IDS, width)
    missing = [c for c in _REQUIRED_IDS if c not in id_pos]
    if missing:
        raise LoaderError(f"{path.name}: missing id header columns {missing} (schema drift)")

    geo_pos = _first_pos(header, _GEO_IDS, width)
    if len(geo_pos) != 1:
        raise LoaderError(
            f"{path.name}: expected exactly ONE geography id header column out of "
            f"{list(_GEO_IDS)}, found {sorted(geo_pos)} (schema drift)"
        )
    geo_col = next(iter(geo_pos.values()))

    # Single-year age columns: ffill'd level-0 group == 'Âge' AND a level-1 age label.
    groups = header.ffill()
    age_pos: dict[int, int] = {}
    for pos in range(width):
        if _norm(groups.iloc[pos]) != _AGE_GROUP:
            continue
        age = _age_of(labels.iloc[pos])
        if age is None:
            continue                      # spacer / 'Âge moyen' / 'Âge médian'
        if age in age_pos:
            raise LoaderError(
                f"{path.name}: duplicate single-year age column {age} at positions "
                f"{age_pos[age]} and {pos} (schema drift)"
            )
        age_pos[age] = pos
    ages = sorted(age_pos)
    if ages != list(range(0, _TERMINAL_AGE + 1)):
        raise LoaderError(
            f"{path.name}: single-year block is not a 0..{_TERMINAL_AGE} span "
            f"({len(ages)} ages, first {ages[:5]}, last {ages[-5:]}) — header-group "
            f"selection failed; confirm the group label {_AGE_GROUP!r}"
        )

    # A units row ('n' / 'ans') must separate the label row from the data. Asserting it
    # is blank in the 'Scénario' column closes the other direction: an edition that DROPS
    # the units row would otherwise lose its first data row silently.
    if pd.notna(rawnh.iloc[units_row].iloc[id_pos["Scénario"]]):
        raise LoaderError(
            f"{path.name}: expected a units row at 0-indexed sheet row {units_row}, "
            f"found a populated 'Scénario' cell (schema drift)"
        )

    body = rawnh.iloc[data_first_row:]
    n_rows = len(body)
    scenario = body.iloc[:, id_pos["Scénario"]]
    if scenario.isna().any():
        raise LoaderError(
            f"{path.name}: {int(scenario.isna().sum())} body row(s) with a blank "
            f"'Scénario' cell (schema drift)"
        )

    year = _as_int_column(body.iloc[:, id_pos["Année"]], "Année", path.name)
    sex_code = _as_int_column(body.iloc[:, id_pos["Sexe"]], "Sexe", path.name)

    block = body.iloc[:, [age_pos[a] for a in ages]]
    try:
        population = block.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise LoaderError(f"{path.name}: non-numeric population cell ({exc}) — schema drift") from exc

    # The three broadcasts below (ids repeated, ages tiled, populations flattened C-order)
    # are only correct while they AGREE; the pairing is pinned by
    # tests/test_isq_ages.py::test_population_stays_paired_with_its_age, which reconciles
    # against the sheet's independent grouped-age block. Change one leg, run that test.
    n_ages = len(ages)
    return pd.DataFrame({
        "label": np.repeat(body.iloc[:, geo_col].to_numpy(), n_ages),
        "scenario_label": np.repeat(scenario.to_numpy(), n_ages),
        "year": np.repeat(year, n_ages),
        "status": np.repeat(body.iloc[:, id_pos["Statut"]].to_numpy(), n_ages),
        "sex_code": np.repeat(sex_code, n_ages),
        "age": np.tile(np.asarray(ages, dtype=np.int64), n_rows),
        "population": population.reshape(-1),
    })
