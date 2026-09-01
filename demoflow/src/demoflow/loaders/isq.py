"""ISQ population loader — spec §8 junctions + §4 loader contracts
(codex r2-F5 / r4-F2 / r4-F3 / r5-F1-F2 / r6-F3 / r10).

Junctions: geography (TOTAL label map with the `IGNORED` sentinel; a label outside the
verified set raises), scenario (explicit map + all-three completeness), sex (numeric ISQ
codes {1, 2, 3}; code 3 is VALIDATION-ONLY and never leaves this module). Gates, in the
order they run — each one names its own cause, never imputes, never warns-and-continues:

 1. workbook resolved (`is_file`, not `exists`) and sha256-pinned;
 2. the expected-geography set is REGISTERED for this workbook (missing key → raise);
 3. every row label classifies (modeled → enum, known-unmodeled → IGNORED, else raise),
    every EXPECTED modeled geography is still present (`require_all_geographies`), and at
    least one row survives (an all-IGNORED workbook is refused, naming the cause);
 4. every ISQ scenario label maps, and all three fans exist for every geography × year;
 5. populations are finite and non-negative on EVERY kept row, code 3 included (r4-F3);
 6. the sex block is a complete {1,2,3} × key lattice (spec: any other code → raise);
 7. sex ADDITIVITY: code3 ≈ code1 + code2 per geography × scenario × year × age × Statut;
 8. sex ORIENTATION: 85+ female-mapped > male-mapped in every geography × scenario × year
    (additivity alone is swap-symmetric and cannot orient the map — codex r2-F5), and the
    guard REFUSES rather than passes when its own 85+ window is empty or short a sex cell;
 9. primary key unique; year lattice contiguous AND pinned to the file family's span;
    identical year domain across every geography × scenario × sex series; Statut
    sub-lattice (r5-F2, r6-F3, r10).

Header-spill note (RUN-1 addendum): the addendum's "2 all-NaN `Région1` rows, indices 0/1
of 2513" are an artifact of a naive `read_excel(header=6)` read, which turns the label and
units rows into data. `build_single_year_long` LOCATES the header row and starts the body
at group_row + 3, and refuses a blank `Scénario` cell in the body — so no header-spill row
reaches this module (MEASURED 2026-08-07: 0 NaN labels in all three pinned pop workbooks).
Hence NO drop-filter here: if a NaN label ever did arrive, `classify_geography` RAISES on
it, which is strictly stronger than dropping it (and a blanket `dropna` would reopen the
fail-open hole that `validate.py`'s `dropna=False` closes).
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from demoflow.errors import LoaderError
from demoflow.geography import (
    IGNORED, SCENARIO_LABEL_TO_ENUM, SEX_CODE_TO_GENDER, WORKBOOK_GEOGRAPHIES, Geography,
    classify_geography, require_all_geographies,
)
from demoflow.loaders.isq_ages import build_single_year_long
from demoflow.loaders.pins import DATA_DIR, verify_pin
from demoflow.loaders.validate import (
    assert_statut_sublattice, assert_uniform_year_domain, assert_unique_primary_key,
    assert_year_lattice,
)

SEX_ADDITIVITY_RTOL = 1e-6
SEX_ADDITIVITY_ATOL = 1e-6

_SEX_TOTAL_CODE = 3                                      # ISQ 'les deux sexes'
_SEX_PART_CODES = tuple(sorted(SEX_CODE_TO_GENDER))      # (1, 2) — the M/F codes
_SEX_CODES = frozenset(_SEX_PART_CODES) | {_SEX_TOTAL_CODE}
_ALL_SCENARIOS = frozenset(SCENARIO_LABEL_TO_ENUM.values())
_ORIENTATION_MIN_AGE = 85

_ADDITIVITY_KEY = ["geography", "scenario", "year", "age", "status"]
_PRIMARY_KEY = ["geography", "scenario", "year", "sex", "age"]
_SERIES_KEY = ["geography", "scenario", "sex"]

# MEASURED 2026-08-07 in ALL THREE pinned pop workbooks (steering ruling: the plan body's
# {'est','proj'} was never in the data): 'r' réel (2021–2024), 'p' provisoire (2025),
# 'proj' projeté (2026→). assert_statut_sublattice's startswith('proj') logic is unchanged.
_STATUT_ALLOWED = frozenset({"r", "p", "proj"})

# Year span per FILE FAMILY (spec §4 + steering ruling H): the spec's "(2021–2051)" governs
# the pop-as-rmr / pop-as-ra family; the QC-total workbook runs to 2071 (measured). The qc
# entry is declared for the family, not exercised: every one of its rows classifies IGNORED,
# so load_population refuses that workbook at gate 3 (see test_isq_loader.py).
_DEFAULT_SPAN = (2021, 2051)
_EXPECTED_SPAN = {"pop-as-qc-base.xlsx": (2021, 2071)}


def _check_sex_additivity(code3: float, code1: float, code2: float, ctx: str) -> None:
    if not math.isclose(code3, code1 + code2,
                        rel_tol=SEX_ADDITIVITY_RTOL, abs_tol=SEX_ADDITIVITY_ATOL):
        raise LoaderError(f"sex additivity violated at {ctx}: "
                          f"code3={code3} != code1+code2={code1 + code2}")


def _check_sex_orientation(mf: pd.DataFrame, name: str) -> None:
    """85+ female-mapped population must EXCEED male-mapped in every geography × scenario ×
    year (the universal old-age female survival advantage) — a violation means the 1↔2 map
    is swapped, which additivity cannot see (codex r2-F5). Aggregated over the 85+ bucket,
    the spec's own unit. MEASURED 2026-08-07: min F/M = 1.213 (rmr, 279 cells) / 1.212 (ra,
    465 cells); 0 violations per SINGLE age too (0/4464, 0/7440) — a stricter per-age guard
    is available at no measured risk if the model ever wants one."""
    old = mf[mf["age"] >= _ORIENTATION_MIN_AGE]
    piv = old.pivot_table(index=["geography", "scenario", "year"], columns="sex",
                          values="population", aggfunc="sum")
    absent = set(SEX_CODE_TO_GENDER.values()) - set(piv.columns)
    empty_cells = int(piv.isna().to_numpy().sum())
    if old.empty or absent or empty_cells:
        # A guard that cannot verify REFUSES; it never passes by default. The empty-CELL
        # cause is the fail-OPEN one: a geography × scenario × year key short its 85+ rows
        # for ONE sex pivots to NaN, and `NaN <= x` is False — the comparison below would
        # report "no violation" for a key it never saw. `_sex_lattice` refuses such a frame
        # earlier in load_population, but this guard must not depend on another gate's
        # POSITION for its own correctness.
        # `old.empty` is DELIBERATELY redundant under pandas 3.0.3: an empty input pivots to
        # a COLUMN-LESS frame, so `absent` already fires (MEASURED — dropping the emptiness
        # clause alone leaves the suite green, so no test can pin it on its own). It is kept
        # as the version-INDEPENDENT leg: an empty comparison window yields zero violations,
        # i.e. a silent pass, and refusing it must not rest on pivot_table's column behaviour.
        raise LoaderError(f"{name}: sex orientation guard cannot run — the "
                          f"{_ORIENTATION_MIN_AGE}+ block has {len(old)} row(s), is missing "
                          f"sex column(s) {sorted(absent)}, and has {empty_cells} key(s) "
                          f"short a sex cell")
    violations = piv.index[piv["F"] <= piv["M"]]
    if len(violations) > 0:
        raise LoaderError(f"{name}: sex orientation guard failed — {_ORIENTATION_MIN_AGE}+ "
                          f"female-mapped <= male-mapped (swapped 1<->2 map?) in "
                          f"{len(violations)} geography×scenario×year cell(s): "
                          f"{list(violations)[:3]}")


def _sex_lattice(long: pd.DataFrame, name: str) -> pd.DataFrame:
    """One row per additivity key × sex code, and the lattice must be COMPLETE: exactly the
    ISQ codes {1,2,3} (spec §8 'Any other code → raise'; the plan body dropped unknown codes
    silently via `.isin`), one cell per (key, code), and no row lost or duplicate-summed on
    the way in — `pivot_table` silently OMITS rows with a NaN key cell and silently SUMS
    duplicates, either of which would let the additivity gate pass over data it never saw.
    The row-count identity `rows == keys × codes` catches both."""
    keyed = long.pivot_table(index=_ADDITIVITY_KEY, columns="sex_code",
                             values="population", aggfunc="sum")
    codes = set(keyed.columns)
    if codes != _SEX_CODES:
        raise LoaderError(f"{name}: sex code set {sorted(codes)} != the ISQ codes "
                          f"{sorted(_SEX_CODES)} (unknown or missing 'Sexe' code)")
    empty_cells = int(keyed.isna().to_numpy().sum())
    if empty_cells or len(keyed) * len(_SEX_CODES) != len(long):
        raise LoaderError(f"{name}: sex lattice incomplete — {len(long)} row(s) for "
                          f"{len(keyed)} key(s) × {len(_SEX_CODES)} code(s), {empty_cells} "
                          f"empty cell(s): a key is missing a sex row, carries a duplicate, "
                          f"or has a NaN key cell")
    return keyed


def _check_scenario_completeness(long: pd.DataFrame, name: str) -> None:
    """All three ISQ fans must exist for every geography × year (spec §8 Scenario: "missing
    any of the three for a geography×year → raise"). The plan body mapped the labels but
    never checked completeness — a workbook shipping only the reference fan for one
    geography would otherwise be ranked on a single scenario, silently."""
    seen: dict[tuple, set] = {}
    for geography, year, scenario in zip(long["geography"], long["year"], long["scenario"]):
        seen.setdefault((geography, year), set()).add(scenario)
    missing = {key: sorted(s.value for s in _ALL_SCENARIOS - got)
               for key, got in seen.items() if got != _ALL_SCENARIOS}
    if missing:
        raise LoaderError(f"{name}: missing scenario(s) for {len(missing)} geography×year "
                          f"key(s) (spec §8 requires all three): {list(missing.items())[:3]}")


def _resolve_path(name: str, data_dir: Path | None) -> Path:
    path = (data_dir or DATA_DIR) / name
    # is_file(), NOT exists(): a DIRECTORY passes exists() and then leaks IsADirectoryError
    # out of verify_pin's read_bytes, past this named guard (RUN-1 addendum).
    if not path.is_file():
        raise LoaderError(f"workbook not found: {path} (re-download is a fallback, spec §4)")
    verify_pin(path, name)
    return path


def _expected_geographies(name: str) -> frozenset[Geography]:
    """REQUIRED lookup (RUN-1 addendum): `WORKBOOK_GEOGRAPHIES.get(name, frozenset())` makes
    `require_all_geographies` pass trivially for an unregistered workbook — the completeness
    gate becomes unfalsifiable. Resolved BEFORE the workbook is read so the refusal is
    immediate."""
    try:
        return WORKBOOK_GEOGRAPHIES[name]
    except KeyError:
        raise LoaderError(f"{name}: no expected-geography set registered in "
                          f"WORKBOOK_GEOGRAPHIES (registered: "
                          f"{sorted(WORKBOOK_GEOGRAPHIES)})") from None


def load_population(name: str, data_dir: Path | None = None) -> pd.DataFrame:
    """Tidy long population frame: geography × scenario × year × sex × age → population
    (+ the row's `status`, the ISQ `Statut` revision marker). Raises LoaderError on any
    drift; never imputes."""
    path = _resolve_path(name, data_dir)
    expected = _expected_geographies(name)
    long = build_single_year_long(path)

    # --- geography junction: TOTAL map → Geography | IGNORED; IGNORED rows dropped.
    # Classifying the DISTINCT labels keeps classify_geography's raise on the first unknown
    # label (a NaN label included) while paying the normalization regex once per label.
    label_class = {label: classify_geography(label) for label in long["label"].unique()}
    classified = np.array([label_class[label] for label in long["label"]], dtype=object)
    keep = np.fromiter((cls is not IGNORED for cls in classified), dtype=bool, count=len(classified))
    long = long.loc[keep].copy()
    # dtype=object is FORCED on both enum columns (here and `scenario` below). pandas 3.x
    # infers its `str` dtype for a column of str-SUBCLASS objects, and that dtype's
    # comparison path str()-ifies the scalar operand: `df["geography"] == Geography.MTL_RMR`
    # then compares against "Geography.MTL_RMR" and matches NOTHING, while `.unique()` still
    # hands back enum members — so every downstream equality filter would silently select an
    # empty frame. MEASURED on pandas 3.0.3; the canary is
    # test_isq_loader.py::test_all_three_scenarios_present_for_mtl_rmr (the plan's own test).
    long["geography"] = pd.Series(classified[keep], index=long.index, dtype=object)
    require_all_geographies(set(long["geography"]), set(expected), name)
    if long.empty:
        raise LoaderError(f"{name}: no modeled geography — every row classified IGNORED, so "
                          f"this workbook is not a population source (expected set: "
                          f"{sorted(g.value for g in expected)})")

    # --- scenario junction
    unknown = sorted(set(long["scenario_label"]) - set(SCENARIO_LABEL_TO_ENUM))
    if unknown:
        raise LoaderError(f"{name}: unknown ISQ scenario labels: {unknown}")
    long["scenario"] = pd.Series(
        [SCENARIO_LABEL_TO_ENUM[label] for label in long["scenario_label"]],
        index=long.index, dtype=object)
    _check_scenario_completeness(long, name)

    # --- finite + non-negative populations on EVERY kept row, code 3 included (r4-F3:
    # reject NaN AND ±Inf). Running it BEFORE the additivity gate is what makes that gate
    # unskippable: a NaN total would otherwise compare-false and pass silently.
    population = long["population"].to_numpy(dtype=float)
    non_finite, negative = int((~np.isfinite(population)).sum()), int((population < 0).sum())
    if non_finite or negative:
        raise LoaderError(f"{name}: {non_finite} non-finite and {negative} negative "
                          f"population cell(s)")

    # --- sex junction: complete lattice → additivity → M/F projection → orientation guard
    keyed = _sex_lattice(long, name)
    part_a, part_b = _SEX_PART_CODES
    for key, code_a, code_b, total in zip(keyed.index, keyed[part_a], keyed[part_b],
                                          keyed[_SEX_TOTAL_CODE]):
        _check_sex_additivity(code3=float(total), code1=float(code_a), code2=float(code_b),
                              ctx=f"{name} {key}")

    mf = long[long["sex_code"] != _SEX_TOTAL_CODE].copy()
    mf["sex"] = [SEX_CODE_TO_GENDER[code] for code in mf["sex_code"]]
    _check_sex_orientation(mf, name)

    out = (mf[["geography", "scenario", "year", "sex", "age", "population", "status"]]
           .reset_index(drop=True))

    # --- primary key + pinned/uniform year lattice (r5-F2, r6-F3) + Statut sub-lattice (r10).
    # assert_year_lattice is called UNCONDITIONALLY on every loaded series (RUN-1 addendum):
    # the other three gates all pass an empty frame clean, so it is the only one that refuses
    # an empty year index. The all-IGNORED workbook is caught earlier, at gate 3, because the
    # sex lattice would otherwise reach this point first and blame a missing 'Sexe' code.
    assert_unique_primary_key(out, _PRIMARY_KEY, name)
    assert_year_lattice(out["year"].unique(), name,
                        expected_span=_EXPECTED_SPAN.get(name, _DEFAULT_SPAN))
    assert_uniform_year_domain(out, _SERIES_KEY, "year", name)
    assert_statut_sublattice(out, _SERIES_KEY, "year", "status", set(_STATUT_ALLOWED), name)
    return out
