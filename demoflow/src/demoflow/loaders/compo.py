"""ISQ compo loader — the §6 immigrant-arrival-flow source (invariant I2: these flows
DECOMPOSE the ISQ scenario population, they never add demand on top of it).

Sheet "Scénarios de 2026" (single sheet in both committed compo workbooks). MEASURED
2026-08-07 against the two sha256-pinned workbooks:

  workbook              group row  id row  label rows  units row  data first row
  compo-rmr-base.xlsx       5         6       7, 8         9           10
  compo-ra-base.xlsx        4         5       6, 7         8            9

The row offsets DIFFER by one, so the header is LOCATED by its id tokens and never
assumed (the plan body's hardcoded `_DATA_FIRST_ROW = 10` is correct for the rmr workbook
and silently drops the ra workbook's first data row).

Columns are the other way round — PINNED by position, VERIFIED by token:
`Immigrants`/`permanents` at 16 and `Solde de`/` résidents `/`non permanents` at 18, in
BOTH workbooks. Position is the only usable identity here: the level-1 label `Solde` is
NOT unique on this sheet (it also heads cols 23, 27, 28, 29, 31), so a by-name lookup
would be ambiguous. `_verify_header_tokens` is therefore the schema guard, and it demands
BOTH of each column's tokens — the one-token form passes a 16<->18 SWAP, because col 18's
own header contains "permanent".

The `year` column semantics differ from the pop loader's — see `YEAR_SEMANTICS`.

Structurally INAPPLICABLE here (RUN-1 measured fact, recorded so nobody re-derives it):
the compo workbooks carry NO `Sexe` and NO `Statut` column, so spec §4's Statut
sub-lattice gate and §8's sex-additivity / sex-orientation guards have no operands on
this source. They are not weakened, not skipped-with-a-TODO — they do not apply.

This loader deliberately does NOT emit the `Population (t)` column it reads: population
has exactly one source (the pop loader, §8), and a second one here would be a silent
second anchor for the I1 roll-forward. Col 4 is read ONLY as the terminal-row evidence
leg below.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from demoflow.errors import LoaderError
from demoflow.geography import (
    IGNORED, SCENARIO_LABEL_TO_ENUM, WORKBOOK_GEOGRAPHIES, Geography, Scenario,
    classify_geography, require_all_geographies,
)
from demoflow.loaders.pins import DATA_DIR, verify_pin
from demoflow.loaders.validate import (
    assert_uniform_year_domain, assert_unique_primary_key, assert_year_lattice,
)

SHEET = "Scénarios de 2026"

# Pinned-by-position, verified-by-token (see module docstring).
COL_IMMIG_PERM, COL_NPR_NET = 16, 18
# Read for the suppression gate's evidence leg only; never emitted.
COL_STOCK = 4
# Located by token, never assumed: the id header labels the body's key columns.
_ID_LABELS = ("Scénario", "Code", "Région1", "Année")
_HDR_SCAN_ROWS = 30
_UNITS_MARKER = "n"

# ISQ's "not published / not applicable" marker. MEASURED: it fills EVERY flow column on
# the sheet's terminal year (2051) in both workbooks — 27 rows (rmr) / 54 rows (ra), one
# per geography x scenario key — while `Population (t)` stays published on those rows.
SUPPRESSION_MARKER = "..."

# Two spans, because they describe two different objects and the difference is semantic,
# not a truncation:
#   RAW_SHEET_SPAN — the sheet's own `Année` column (steering ruling H, measured on the
#                    sheet: 2025-2051, NOT the pop family's 2021-2051).
#   FLOW_SPAN      — the FLOW series this loader emits. The terminal year publishes no
#                    flow because a flow row labeled t is the t -> t+1 bridge; verified
#                    arithmetically on the committed vintage (RMR de Montréal, référence):
#                    2050 Population(t) 4460001 + accroissement total -3920 = 4456081 =
#                    the 2051 row's Population(t). So flows over 2025-2050 span the
#                    2025-2051 stock lattice with NO gap and nothing dropped.
RAW_SHEET_SPAN = (2025, 2051)
FLOW_SPAN = (2025, 2050)

# The one fact a §6 consumer cannot get wrong without mis-timing every arrival cohort.
YEAR_SEMANTICS = (
    "`year` is the ISQ flow-interval START: the row labeled t covers 1 July t -> 1 July "
    "t+1 (the sheet's own 'Année / du 1er juillet / de (t) à (t+1)' header) and it lands "
    "in Population(t+1), NOT Population(t). A §6 consumer that subtracts "
    "arrivals(year=t) from P_ISQ(t) mis-times every arrival cohort by one year."
)

_PRIMARY_KEY = ["geography", "scenario", "year"]
_SERIES_KEY = ["geography", "scenario"]
_ALL_SCENARIOS = frozenset(SCENARIO_LABEL_TO_ENUM.values())

# EXTRACTION CANDIDATE (named, not silent): `_resolve_path`, `_expected_geographies` and
# `_check_scenario_completeness` below are the same units as the ones in
# `loaders/isq.py`. They are duplicated ON PURPOSE for this task — both loaders were
# built in the same parallel run, and reaching into a sibling's module (or editing the
# shared `validate.py` underneath it) would have coupled two in-flight files. Extracting
# the three into `validate.py` / `pins.py` is a follow-up task, not a silent local fix.


def _verify_header_tokens(tokens_at: dict[int, str]) -> None:
    """Raise unless the header tokens at the pinned positions are the migration columns
    (guards a re-ordered / re-editioned workbook, AND a 16<->18 swap).

    BOTH tokens of a column must be present. The single-token form is fail-OPEN: col 18's
    real header ("Solde de  résidents  non permanents n") contains "permanent", so it
    satisfies col 16's check on its own — a swapped edition would load the
    non-permanent-resident BALANCE as the permanent-immigrant arrival flow, silently, and
    every downstream §6 decomposition would be wrong with no gate firing."""
    required = {COL_IMMIG_PERM: ("immigrant", "permanent"),
                COL_NPR_NET: ("solde", "permanent")}
    for col, tokens in required.items():
        text = str(tokens_at.get(col, "")).lower()
        missing = [t for t in tokens if t not in text]
        if missing:
            raise LoaderError(
                f"header token drift at col {col}: {tokens_at.get(col)!r} is missing "
                f"{missing} (expected all of {list(tokens)})")


def _resolve_path(name: str, data_dir: Path | None) -> Path:
    # is_file(), NOT exists(): a DIRECTORY passes exists() and then leaks
    # IsADirectoryError out of verify_pin's read_bytes, past this named guard.
    path = (data_dir or DATA_DIR) / name
    if not path.is_file():
        raise LoaderError(f"workbook not found: {path} (re-download is a fallback, spec §4)")
    verify_pin(path, name)
    return path


def _expected_geographies(name: str) -> frozenset[Geography]:
    """REQUIRED lookup. `WORKBOOK_GEOGRAPHIES.get(name, frozenset())` (the plan body) makes
    `require_all_geographies` pass trivially for an unregistered workbook — the
    completeness gate becomes unfalsifiable."""
    try:
        return WORKBOOK_GEOGRAPHIES[name]
    except KeyError:
        raise LoaderError(f"{name}: no expected-geography set registered in "
                          f"WORKBOOK_GEOGRAPHIES (registered: "
                          f"{sorted(WORKBOOK_GEOGRAPHIES)})") from None


def _norm(value: object) -> str:
    return str(value).strip() if pd.notna(value) else ""


def _locate_id_row(rawnh: pd.DataFrame, name: str) -> int:
    """Locate the id header row by its tokens (the offset differs per workbook). Raises
    rather than guessing — a drifted header must not shift the data window silently."""
    for row in range(min(_HDR_SCAN_ROWS, len(rawnh))):
        if set(_ID_LABELS) <= {_norm(v) for v in rawnh.iloc[row]}:
            return row
    raise LoaderError(f"{name}: could not locate the {SHEET!r} id header row — tokens "
                      f"{list(_ID_LABELS)} not found together in the first "
                      f"{_HDR_SCAN_ROWS} rows (schema drift)")


def _id_positions(header: pd.Series, name: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for pos in range(len(header)):
        token = _norm(header.iloc[pos])
        if token in _ID_LABELS and token not in found:
            found[token] = pos
    missing = [label for label in _ID_LABELS if label not in found]
    if missing:
        raise LoaderError(f"{name}: missing id header columns {missing} (schema drift)")
    return found


def _is_marker(value: object) -> bool:
    return isinstance(value, str) and value.strip() == SUPPRESSION_MARKER


def _drop_suppressed_terminal_year(tidy: pd.DataFrame, terminal_year: int,
                                   name: str) -> pd.DataFrame:
    """Drop the out-of-horizon terminal-year flow rows — under a NAMED, falsifiable rule,
    never a blanket "skip the rows that fail to parse".

    Three legs, each of which fails on a different kind of edition drift:
      1. a marker may appear ONLY on the sheet's terminal year (elsewhere it is a genuinely
         missing observation, and dropping it would shorten a real series);
      2. the terminal row must be suppressed in BOTH flow columns (a half-suppressed row is
         not the t->t+1 bridge falling outside the horizon — it is drift);
      3. the terminal row's `Population (t)` must still be PUBLISHED. This is what separates
         "the terminal flow is out of horizon" (measured: stock 4456081 on the 2051 row)
         from "the trailing rows went unpublished", which must never be dropped quietly.
         "Unpublished" means blank OR the suppression marker: an `isna()`-only test would be
         fail-OPEN against the very form this sheet uses — MEASURED on the in-scope 2051
         rows, cols 6/9/16/17/18/34/35 all carry '...' and col 4 alone is published, so a
         col-4 that went unpublished would go '...' too, not blank.
    """
    flows = ["immigrants_permanents", "npr_net_flow"]
    marked = pd.DataFrame({col: tidy[col].map(_is_marker) for col in flows})
    any_marked, all_marked = marked.any(axis=1), marked.all(axis=1)

    off_year = tidy.loc[any_marked & (tidy["year"] != terminal_year), "year"]
    if len(off_year):
        raise LoaderError(
            f"{name}: {SUPPRESSION_MARKER!r} suppressed flow(s) on {len(off_year)} row(s) "
            f"at NON-terminal year(s) {sorted(set(off_year))[:5]} (terminal year is "
            f"{terminal_year}) — a missing observation, not an out-of-horizon row")
    partial = any_marked & ~all_marked
    if partial.any():
        raise LoaderError(
            f"{name}: {int(partial.sum())} row(s) suppress ONE flow column but not the "
            f"other (schema drift — the terminal row suppresses every flow column)")
    # Both unpublished forms, not just blank: `_is_marker` is what this sheet actually uses.
    unpublished_stock = all_marked & (tidy["stock"].isna()
                                      | tidy["stock"].map(_is_marker).astype(bool))
    if unpublished_stock.any():
        raise LoaderError(
            f"{name}: {int(unpublished_stock.sum())} suppressed terminal row(s) also carry an "
            f"UNPUBLISHED 'Population (t)' stock (blank or {SUPPRESSION_MARKER!r}) — the "
            f"trailing rows went unpublished, which is drift, not the out-of-horizon terminal "
            f"flow (whose stock stays published)")
    if not all_marked.any():
        raise LoaderError(
            f"{name}: no suppressed terminal-year flow row found at {terminal_year} — the "
            f"committed vintage publishes no {terminal_year} flow (schema drift; if a new "
            f"edition DOES publish it, FLOW_SPAN must be re-measured, not widened)")
    return tidy.loc[~all_marked].reset_index(drop=True)


def _as_flow_column(values: pd.Series, what: str, name: str, *,
                    nonneg: bool) -> np.ndarray:
    """Body column -> float64, fail-loud on blank / non-numeric / non-finite (spec §4
    r4-F3). `nonneg` is the signed-flow carve-out (r9-F2): the permanent-immigrant ARRIVAL
    flow is a nonnegative count; the non-permanent-resident BALANCE is legitimately signed
    (measured: MTL_RMR 2025 = -59399) and binds finite-only."""
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        bad = list(pd.unique(values[numeric.isna()]))[:5]
        raise LoaderError(f"{name}: blank or non-numeric {what!r} cell(s) {bad} (schema drift)")
    out = numeric.to_numpy(dtype=float)
    if not np.all(np.isfinite(out)):
        raise LoaderError(f"{name}: {int((~np.isfinite(out)).sum())} non-finite {what!r} cell(s)")
    if nonneg and (out < 0).any():
        raise LoaderError(f"{name}: negative {what!r} on {int((out < 0).sum())} row(s) "
                          f"(min {out.min()})")
    return out


def _check_scenario_completeness(df: pd.DataFrame, name: str) -> None:
    """All three ISQ fans must exist for every geography x year (spec §8: "missing any of
    the three for a geography x year -> raise"). The plan body mapped the labels but never
    checked completeness — a workbook shipping only the reference fan for one geography
    would otherwise be ranked on a single scenario, silently."""
    seen: dict[tuple, set] = {}
    for geography, year, scenario in zip(df["geography"], df["year"], df["scenario"]):
        seen.setdefault((geography, year), set()).add(scenario)
    missing = {key: sorted(s.value for s in _ALL_SCENARIOS - got)
               for key, got in seen.items() if got != _ALL_SCENARIOS}
    if missing:
        raise LoaderError(f"{name}: missing scenario(s) for {len(missing)} geography x year "
                          f"key(s) (spec §8 requires all three): {list(missing.items())[:3]}")


def load_immigrant_flows(name: str = "compo-rmr-base.xlsx",
                         data_dir: Path | None = None) -> pd.DataFrame:
    """Tidy long arrival-flow frame: geography x scenario x year ->
    (immigrants_permanents, npr_net_flow). Raises LoaderError on any drift; never imputes.
    `year` is the flow-INTERVAL START — see `YEAR_SEMANTICS`."""
    path = _resolve_path(name, data_dir)
    expected = _expected_geographies(name)
    try:
        rawnh = pd.read_excel(path, sheet_name=SHEET, header=None, engine="openpyxl")
    except ValueError as exc:   # pandas raises ValueError for an absent sheet name
        raise LoaderError(f"{name}: sheet {SHEET!r} not readable ({exc}) — schema drift") from exc

    id_row = _locate_id_row(rawnh, name)
    units_row, data_first_row = id_row + 3, id_row + 4
    if len(rawnh) <= data_first_row:
        raise LoaderError(f"empty/short sheet {SHEET!r} in {name}")
    id_pos = _id_positions(rawnh.iloc[id_row], name)

    # Header-token check over the whole header block (group row .. units row), joining the
    # populated cells of each pinned column. No ffill: within a column it only duplicates
    # tokens, and the merged GROUP label spans columns (axis 1), which this check does not
    # need — the level-1 labels alone discriminate col 16 from col 18.
    block = rawnh.iloc[id_row - 1:data_first_row]
    joined = {col: " ".join(str(v) for v in block.iloc[:, col] if pd.notna(v))
              for col in (COL_IMMIG_PERM, COL_NPR_NET)}
    _verify_header_tokens(joined)

    # A units row ('n') must separate the header from the data. Independent of the token
    # check above: an edition that DROPS the units row keeps its tokens intact while
    # shifting the body by one, which would silently lose the first data row.
    if _norm(rawnh.iloc[units_row].iloc[COL_IMMIG_PERM]) != _UNITS_MARKER:
        raise LoaderError(
            f"{name}: expected the units row {_UNITS_MARKER!r} at 0-indexed sheet row "
            f"{units_row} col {COL_IMMIG_PERM}, found "
            f"{rawnh.iloc[units_row].iloc[COL_IMMIG_PERM]!r} (schema drift)")

    body = rawnh.iloc[data_first_row:]

    # Raw-sheet year gate FIRST, at the layer ruling H measured it (2025-2051), and over
    # EVERY row including the unmodeled geographies. This is also what discharges the
    # RUN-1 'Année' header-spill fact: the 2 non-numeric cells ('du 1er juillet',
    # 'de (t) à (t+1)') live in the header block, above `data_first_row`, so they never
    # reach the body — and if a drifted edition ever let one through, `assert_year_lattice`
    # raises "non-numeric year" on it rather than a filter hiding it (same resolution as
    # the sibling pop loader: locate the header, never drop-filter the body).
    assert_year_lattice(body.iloc[:, id_pos["Année"]].unique(), f"{name} raw sheet",
                        expected_span=RAW_SHEET_SPAN)

    # --- geography junction: TOTAL map -> Geography | IGNORED; IGNORED rows dropped.
    labels = body.iloc[:, id_pos["Région1"]]
    label_class = {label: classify_geography(label) for label in labels.unique()}
    classified = np.array([label_class[label] for label in labels], dtype=object)
    keep = np.fromiter((cls is not IGNORED for cls in classified), dtype=bool,
                       count=len(classified))
    if not keep.any():
        raise LoaderError(f"{name}: no modeled geography — every row classified IGNORED, so "
                          f"this workbook is not a compo source (expected set: "
                          f"{sorted(g.value for g in expected)})")
    kept = body.loc[keep]

    # --- scenario junction (strict for IN-SCOPE rows: an unrecognized label on a modeled
    # geography is genuine drift, never a row to skip).
    scenarios = []
    for geo, raw_label in zip(classified[keep], kept.iloc[:, id_pos["Scénario"]]):
        key = str(raw_label).strip()
        if key not in SCENARIO_LABEL_TO_ENUM:
            raise LoaderError(f"{name}: in-scope geography {geo.value} carries unknown "
                              f"scenario {key!r}")
        scenarios.append(SCENARIO_LABEL_TO_ENUM[key])

    tidy = pd.DataFrame({
        "geography": classified[keep],
        "scenario": scenarios,
        "year": [int(float(y)) for y in kept.iloc[:, id_pos["Année"]]],
        "immigrants_permanents": kept.iloc[:, COL_IMMIG_PERM].to_numpy(),
        "npr_net_flow": kept.iloc[:, COL_NPR_NET].to_numpy(),
        "stock": kept.iloc[:, COL_STOCK].to_numpy(),
    })
    # The two casts below are LOAD-BEARING, and their POSITION is the whole point. pandas
    # 3.x infers its `str` dtype for a column of str-SUBCLASS objects, and that dtype's
    # comparison path str()-ifies the scalar operand: `df["geography"] == Geography.MTL_RMR`
    # then compares against "Geography.MTL_RMR" and matches NOTHING, while `.unique()` still
    # hands back enum members — so every downstream equality filter silently selects an EMPTY
    # frame. MEASURED on pandas 3.0.3: the DataFrame CONSTRUCTOR coerces to `str` from every
    # input form — a plain list, an object-dtype Series, even an explicitly object-dtype
    # ndarray — so passing dtype=object INTO the constructor is not protection; only this
    # post-construction astype survives. Canary:
    # test_compo_loader.py::test_enum_columns_stay_object_dtype_so_equality_filters_work.
    tidy["geography"] = tidy["geography"].astype(object)
    tidy["scenario"] = tidy["scenario"].astype(object)

    # --- terminal-year suppression: verified and dropped BEFORE any numeric coercion.
    # Order is load-bearing: `pd.to_numeric(..., errors="coerce")` turns '...' into NaN,
    # which is exactly the fail-open the marker gate exists to prevent, and a bare
    # to_numpy(dtype=float) would leak ValueError past this module's error taxonomy.
    tidy = _drop_suppressed_terminal_year(tidy, terminal_year=RAW_SHEET_SPAN[1], name=name)
    tidy["immigrants_permanents"] = _as_flow_column(
        tidy["immigrants_permanents"], "Immigrants permanents", name, nonneg=True)
    tidy["npr_net_flow"] = _as_flow_column(
        tidy["npr_net_flow"], "Solde des résidents non permanents", name, nonneg=False)

    require_all_geographies(set(tidy["geography"]), set(expected), name)
    _check_scenario_completeness(tidy, name)

    out = tidy[["geography", "scenario", "year", "immigrants_permanents", "npr_net_flow"]]
    assert_unique_primary_key(out, _PRIMARY_KEY, name)
    assert_year_lattice(out["year"].unique(), f"{name} flows", expected_span=FLOW_SPAN)
    assert_uniform_year_domain(out, _SERIES_KEY, "year", f"{name} flows")
    return out.reset_index(drop=True)


def compo_evidence_lines(df: pd.DataFrame) -> list[str]:
    """The COMPO half of the closed-cohort evidence note (spec §5 r3-F2), as lines.

    Returns lines; it does NOT write. The note has exactly ONE writer — `probes/run_p7.py`,
    which owns the file end-to-end (title, provenance header, the measured StatCan evidence,
    and this section). Two functions writing one artifact is a hand-edit surface by another
    name: whichever ran last would silently define the file, and the byte-diff that proves
    the note is generated would prove nothing about the half that did not run. (This
    function was `write_closed_cohort_evidence(df, out_path)` until steering ruling K
    re-pointed the evidence leg at an age-structured source; the measurement below is
    unchanged, only its writer moved.)

    What it records: the spec originally asked for "the 75+ net-migration share" as the
    assumption's evidence. That share is NOT COMPUTABLE from compo — the workbook has no age
    axis at all (ruling J). So this section states the gap explicitly and reports the
    observable ALL-AGE magnitudes as context, instead of inferring a bound from an unmeasured
    senior share. Magnitudes are broken out per scenario AND per geography: one blended total
    across three mutually exclusive scenario fans is an artifact, not an observation."""
    if df.empty:
        raise LoaderError("closed-cohort evidence: empty flow frame (nothing to record)")
    span = f"{int(df['year'].min())}-{int(df['year'].max())}"
    lines = [
        "### What the compo workbooks cannot establish",
        "",
        "The spec asks for the 75+ net-migration share as the assumption's evidence. It is",
        "**not computable from the compo workbooks: they carry no age axis** (no `Âge`, no",
        "`Groupe d'âge` column — only region x scenario x year). The omitted 75+ term is",
        "therefore **unbounded by this source alone**; bounding it needs an age-structured",
        "migration source (ISQ migration-by-age tables or StatCan components by age), which",
        "is what §2 above supplies.",
        "",
        f"### Observable ALL-AGE magnitudes — flow-interval years {span}, per scenario x geography",
        "",
        f"`year` semantics: {YEAR_SEMANTICS}",
        "",
        "| geography | scenario | Σ immigrants_permanents | Σ npr_net_flow |",
        "|---|---|---:|---:|",
    ]
    grouped = df.groupby(["geography", "scenario"], dropna=False)[
        ["immigrants_permanents", "npr_net_flow"]].sum()
    # pandas 3 coerces str-Enum groupby keys to plain strings holding the member VALUE (pandas 2
    # handed the members back). Value-lookup reconstructs the enum under BOTH behaviors, and is
    # lossless because the keys ARE the values by construction.
    for (geography, scenario), row in grouped.iterrows():
        geography = geography if isinstance(geography, Geography) else Geography(geography)
        scenario = scenario if isinstance(scenario, Scenario) else Scenario(scenario)
        lines.append(f"| {geography.value} | {scenario.value} | "
                     f"{row['immigrants_permanents']:,.0f} | {row['npr_net_flow']:,.0f} |")
    lines += [
        "",
        "These are ALL-AGE flows. The spec's assumption asserts that senior migration flows",
        "are thin; this source can neither corroborate nor refute that, because it carries no",
        "age axis. The magnitudes above are therefore CONTEXT for the assumption — the scale",
        "of the all-age flows the omitted 75+ term is a sub-share of — never its bound.",
    ]
    return lines
