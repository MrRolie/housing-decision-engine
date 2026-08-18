"""Tripwire tests (spec §7c).

TWO LAYERS, and the split is the point.

LAYER 1 — the plan-verbatim core gate (13 contracts, unchanged): status trichotomy,
closed reason enum, registry-bound `source`, record allowlist, UNKNOWN-branch
nullability, completeness integrity, exit code.

LAYER 2 — the FEED-DERIVED `pr_landings_annual` indicator. The plan body computes this
indicator's realized value as the literal `45000.0`, which is the exact midpoint of the
band it then compares against: a false-green GENERATOR, green forever, on any data, in
any era. Layer 2 exists because the fix is not "type a better number" — it is "compute
the number from the feed, and refuse when the feed cannot honestly answer".

FIXTURE PROVENANCE (derivation, never transcription):
`fixtures/ircc_pr_qc_slice.csv` is a raw BYTE SLICE of the live feed
`https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_CMA.csv`
(fetched 2026-08-18: HTTP 200, 1,727,985 bytes, sha256
d5af3237c5ed81e2ae824eecd766221d99f6ba56c85047592417981aa444a14b, 21,383 data rows,
172 CMA members, 2015..2026) — the verbatim header plus every row of years 2025-2026
for province ∈ {Quebec, Not stated} plus the Toronto rows of those years, CRLF
preserved, 560 data rows. Quebec keeps all 32 of its members so the suppression
arithmetic is the REAL one; the Ontario/Not-stated rows exist so the province filter has
something to exclude.

The measured values pinned below are the feed's own (2026-08-18 vintage):
  Quebec province 2025 = 60,010 over 355 cells (51 suppressed, 12 distinct months)
  Montréal+Québec CMA pair 2025 = 45,895 → 76.48% of province (2023 84.22%, 2024 79.48%)
  Quebec province 2026 = 21,720 over 6 distinct months (partial — NOT a year)
Pinning them against a FROZEN fixture is deliberate: IRCC restates history, so a golden
computed from the LIVE feed reds on refresh with no code change, while these stay green.
That asymmetry is the data-vs-code attribution channel (Task 30's input).

ERA MUTANTS: the 2026-2029 plan's first evaluable year is 2026 full-year, which does not
exist yet (the feed carries 6 months). Every plan-era test therefore runs on a
year-RELABELED slice of real 2025 bytes — derived from measured data, never invented.
"""
import hashlib
import math
from pathlib import Path

import pytest

from demoflow.errors import LoaderError
from demoflow.loaders.constants import CONSTANTS
from demoflow.loaders.ircc import CSV_NAME, EXPECTED_COLUMNS, PRLandings, load_pr_landings
from demoflow.output.tripwires import (
    FEED_FRESHNESS_MONTHS, MONTHS_PER_CLOSED_YEAR, PLAN_GOVERNED_YEARS,
    PR_LANDINGS_INDICATOR, QUEBEC_PROVINCE, REQUIRED_INDICATORS, SOURCE_REGISTRY,
    TRIPWIRE_RECORD_REQUIRED, Reason, SourceKind, Status, TripwireSpec,
    assert_tripwire_record_valid, check_registry, closed_plan_years, evaluate_indicator,
    evaluate_pr_landings, exit_code, pr_landings_realized, run_exit_code, tripwire_record,
)

# ---------------------------------------------------------------------------------------
# LAYER 1 — the plan's 13 core-gate contracts, verbatim.
# ---------------------------------------------------------------------------------------


def _spec(**kw):
    base = dict(indicator="pr_landings_annual", band_low=40000.0, band_high=50000.0, as_of=2026,
                freshness_years=1, source_kind=SourceKind.WIRED)
    base.update(kw)
    return TripwireSpec(**base)


def test_within_band_and_fresh_is_ok():
    assert evaluate_indicator(_spec(), 45000, available=True, now=2026).status is Status.OK


def test_stale_is_unknown_with_closed_reason():
    r = evaluate_indicator(_spec(as_of=2023), 45000, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.STALE


def test_unavailable_is_unknown_source_unavailable():
    r = evaluate_indicator(_spec(), None, available=False, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.SOURCE_UNAVAILABLE


def test_operator_input_missing_is_unknown():
    r = evaluate_indicator(_spec(source_kind=SourceKind.OPERATOR_SUPPLIED), None, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.OPERATOR_INPUT_MISSING


def test_non_finite_value_is_unknown_and_current_value_null():   # RED value integrity + r8-F2
    for bad in (math.nan, math.inf, "n/a"):
        r = evaluate_indicator(_spec(), bad, available=True, now=2026)
        assert r.status is Status.UNKNOWN and r.reason is Reason.NON_FINITE
        assert r.current_value is None and r.as_of is None   # raw value -> run log, not the record


def test_future_as_of_is_unknown():
    r = evaluate_indicator(_spec(as_of=2030), 45000, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.FUTURE_AS_OF


def test_inverted_band_is_unknown():
    r = evaluate_indicator(_spec(band_low=50000.0, band_high=40000.0), 45000, available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.MALFORMED_BAND


def test_closed_band_endpoints_are_crossed():
    assert evaluate_indicator(_spec(), 40000, available=True, now=2026).status is Status.CROSSED
    assert evaluate_indicator(_spec(), 50000, available=True, now=2026).status is Status.CROSSED


def test_registry_completeness_empty_missing_duplicate():
    with pytest.raises(LoaderError, match="empty"):              # codex r10: empty = RUN-level terminal
        check_registry([])
    missing = check_registry(["pr_landings_annual"])            # far short of the required set
    assert any(r.reason is Reason.MISSING_INDICATOR for r in missing) and exit_code(missing) != 0
    dup = check_registry(sorted(REQUIRED_INDICATORS) + ["pr_landings_annual"])
    assert any(r.reason is Reason.DUPLICATE_INDICATOR for r in dup) and exit_code(dup) != 0
    complete = check_registry(sorted(REQUIRED_INDICATORS))
    assert complete == []                                      # no completeness violations


def test_exit_code_zero_only_when_all_ok():
    ok = evaluate_indicator(_spec(), 45000, available=True, now=2026)
    crossed = evaluate_indicator(_spec(), 60000, available=True, now=2026)
    unknown = evaluate_indicator(_spec(), None, available=False, now=2026)
    assert exit_code([ok]) == 0 and exit_code([ok, crossed]) != 0 and exit_code([ok, unknown]) != 0


def test_record_allowlist_and_reason_enum_reject_crash_probability():
    ok = evaluate_indicator(_spec(), 45000, available=True, now=2026)
    rec = tripwire_record(ok)
    assert TRIPWIRE_RECORD_REQUIRED <= set(rec)
    assert_tripwire_record_valid(rec)                         # clean: no raise
    with pytest.raises(ValueError, match="allowlist"):        # RED: forbidden extra field
        assert_tripwire_record_valid({**rec, "crash_probability": 0.35})
    with pytest.raises(ValueError, match="reason"):           # RED: smuggled through reason
        assert_tripwire_record_valid({**rec, "reason": "crash_probability=0.35"})


def test_source_bound_to_code_owned_registry():
    rec = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    assert rec["source"] == SOURCE_REGISTRY["pr_landings_annual"]   # declared string, not a SourceKind
    with pytest.raises(ValueError, match="source"):                # RED: smuggled source content
        assert_tripwire_record_valid({**rec, "source": "crash_probability=0.35"})


def test_unknown_branch_nullability_contract():
    ok = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    assert ok["current_value"] is not None and ok["as_of"] is not None
    assert_tripwire_record_valid(ok)
    with pytest.raises(ValueError, match="non-null"):          # OK record cannot null its value
        assert_tripwire_record_valid({**ok, "current_value": None})

    unavail = tripwire_record(evaluate_indicator(_spec(), None, available=False, now=2026))
    assert unavail["current_value"] is None and unavail["as_of"] is None   # nullable-reason branch
    assert_tripwire_record_valid(unavail)
    with pytest.raises(ValueError, match="NULL"):              # nullable-reason record cannot carry a value
        assert_tripwire_record_valid({**unavail, "current_value": 45000.0})


# ---------------------------------------------------------------------------------------
# LAYER 2 — the feed-derived indicator. Fixture plumbing first.
# ---------------------------------------------------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "ircc_pr_qc_slice.csv"
_COL = {name: i for i, name in enumerate(EXPECTED_COLUMNS)}

# Measured on the 2026-08-18 vintage, reproduced from the frozen slice by the tests below.
QC_2025_PROVINCE = 60010.0
QC_2025_PAIR = 45895.0
QC_2025_CELLS = 355
QC_2025_SUPPRESSED = 51
QC_2026_PARTIAL_PROVINCE = 21720.0
QC_2026_PARTIAL_MONTHS = 6
BAND = (40000.0, 50000.0)      # caller-owned. NOT a module constant — see the impl docstring.


def _lines() -> list[str]:
    """Read BYTES: `read_text` applies universal-newline translation and would collapse the
    CRLF split to one giant line, so every mutant below would silently test nothing."""
    return FIXTURE.read_bytes().decode("utf-8").rstrip("\r\n").split("\r\n")


def _plant(tmp_path: Path, lines: list[str]) -> PRLandings:
    """Write a (possibly mutated) slice where the loader looks and load it THROUGH the real
    loader — mutants must survive the same schema gates the live feed does."""
    (tmp_path / CSV_NAME).write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return load_pr_landings(data_dir=tmp_path)


def _relabel_year(lines: list[str], src: str, dst: str) -> list[str]:
    """Real `src`-year bytes re-stamped as `dst`. Rows of `dst` already in the slice are
    DROPPED first, so the result carries no duplicate (member, year, month) key."""
    out = [lines[0]]
    for ln in lines[1:]:
        f = ln.split("\t")
        if f[_COL["EN_YEAR"]] == dst:
            continue
        if f[_COL["EN_YEAR"]] == src:
            f[_COL["EN_YEAR"]] = dst
            f[_COL["FR_ANNEÉ"]] = dst
        out.append("\t".join(f))
    return out


def _suppress(lines: list[str], year: str, cma: str | None = None) -> list[str]:
    """Replace TOTAL with the feed's own suppression marker — a vintage in which a member
    (or everything) fell under the disclosure floor. `--` is NOT a zero: it absorbs 0-5."""
    out = [lines[0]]
    for ln in lines[1:]:
        f = ln.split("\t")
        if f[_COL["EN_YEAR"]] == year and (cma is None or f[_COL["EN_CENSUS_METROPOLITAN_AREA"]] == cma):
            f[_COL["TOTAL"]] = "--"
        out.append("\t".join(f))
    return out


def _floor_to_five(lines: list[str], year: str, keep: tuple[str, ...]) -> list[str]:
    """Near-total suppression: every `year` cell becomes `--` except `keep`'s, which become
    the smallest publishable count. `keep` is BOTH modeled members on purpose — with either
    one gutted the per-member content gate fires first and the envelope floor is never the
    thing that refuses (a mutation run proved exactly that: dropping the floor survived an
    earlier single-member variant of this fixture)."""
    out = [lines[0]]
    for ln in lines[1:]:
        f = ln.split("\t")
        if f[_COL["EN_YEAR"]] == year:
            f[_COL["TOTAL"]] = "5" if f[_COL["EN_CENSUS_METROPOLITAN_AREA"]] in keep else "--"
        out.append("\t".join(f))
    return out


def _pair_sum(frame, year: int) -> float:
    """The MTL+QC CMA pair — computed here, in the test, deliberately: it is the MODEL's
    demand-side quantity and has no consumer in the tripwire, so production code that
    computed it would be dead code inviting the very scope confusion this test pins."""
    sel = frame[(frame["EN_YEAR"] == str(year))
                & (frame["EN_CENSUS_METROPOLITAN_AREA"].isin(["Montréal", "Québec"]))]
    return float(sum(0 if v == "--" else int(v) for v in sel["TOTAL"]))


# --- carry 1: realized is COMPUTED, and it is not the band midpoint --------------------

def test_realized_is_computed_from_the_feed_not_the_band_midpoint(tmp_path):
    landings = _plant(tmp_path, _lines())
    realized = pr_landings_realized(landings.frame, 2025)
    assert realized.value == QC_2025_PROVINCE
    assert realized.year == 2025
    assert realized.n_cells == QC_2025_CELLS and realized.n_suppressed == QC_2025_SUPPRESSED
    # the plan body's literal, and the band it would have been compared against
    midpoint = (BAND[0] + BAND[1]) / 2
    assert realized.value != midpoint, "realized must not be the band midpoint the plan typed"


def test_suppression_envelope_is_derived_from_the_cell_count(tmp_path):
    """±2.5 per published cell (base-5 rounding; a suppressed cell absorbs the whole 0-5
    band). 355 × 2.5 = 887.5 — the ±888/yr floor, recorded not corrected."""
    realized = pr_landings_realized(_plant(tmp_path, _lines()).frame, 2025)
    assert realized.envelope == pytest.approx(887.5)


# --- carry 2: the numerator is PROVINCIAL; the CMA pair is a different quantity --------

def test_provincial_numerator_is_not_the_cma_pair_and_the_share_decays(tmp_path):
    landings = _plant(tmp_path, _lines())
    province = pr_landings_realized(landings.frame, 2025).value
    pair = _pair_sum(landings.frame, 2025)
    assert province == QC_2025_PROVINCE and pair == QC_2025_PAIR
    assert pair < province                       # the pair is a SUBSET, never the plan's scope
    assert pair / province == pytest.approx(0.7648, abs=5e-5)
    # 45,895 ≈ 45,000 is a coincidence of mismatched scopes: the pair sits ~24% under the
    # PROVINCIAL plan level it would otherwise appear to match.
    plan_level = float(CONSTANTS["mifi_pr_annual_plan"].value)
    assert abs(pair - plan_level) / plan_level < 0.02
    assert province > plan_level * 1.3


def test_other_provinces_are_excluded_from_the_numerator(tmp_path):
    """The slice carries Ontario (Toronto) and `Not stated` rows. A province filter that
    leaked would inflate the numerator; `Not stated` is excluded because those admissions
    are not attributable to Québec (measured ≤20/yr — inside the ±888 envelope)."""
    frame = _plant(tmp_path, _lines()).frame
    everything = float(sum(0 if v == "--" else int(v)
                           for v in frame[frame["EN_YEAR"] == "2025"]["TOTAL"]))
    assert pr_landings_realized(frame, 2025).value == QC_2025_PROVINCE < everything


# --- carry 3: only years the plan in force governs ------------------------------------

def test_pre_plan_years_are_never_evaluated(tmp_path):
    """2025 is closed and complete, and it is NOT governed by the 2026-2029 plan. Its
    provincial 60,010 against a 45k-plan band would read CROSSED — a cross-era artifact."""
    landings = _plant(tmp_path, _lines())
    assert 2025 not in closed_plan_years(landings.frame)
    assert 2025 not in PLAN_GOVERNED_YEARS


def test_first_evaluable_year_is_2026_and_today_it_is_not_closed(tmp_path):
    """The live state at this build: the plan's first evaluable year has 6 months in the
    feed, so the indicator REFUSES — UNKNOWN, both nullable fields null, exit nonzero."""
    landings = _plant(tmp_path, _lines())
    assert min(PLAN_GOVERNED_YEARS) == 2026
    assert closed_plan_years(landings.frame) == []
    ev = evaluate_pr_landings(landings, band=BAND, now=(2026, 8))
    assert ev.result.status is Status.UNKNOWN
    assert ev.result.reason is Reason.SOURCE_UNAVAILABLE
    assert ev.result.current_value is None and ev.result.as_of is None
    assert exit_code([ev.result]) != 0
    assert_tripwire_record_valid(tripwire_record(ev.result))


def test_plan_era_bounds_are_bound_to_the_anchor_that_declares_them():
    """The era is the MIFI anchor's own; a plan replacement that edits the anchor must red
    here rather than leave the tripwire silently evaluating a superseded era."""
    assert "2026-2029" in CONSTANTS["mifi_pr_annual_plan"].source
    assert (min(PLAN_GOVERNED_YEARS), max(PLAN_GOVERNED_YEARS)) == (2026, 2029)


# --- carry 4: twelve distinct months, and a freshness limit the lag can clear ----------

def test_partial_year_would_read_crossed_and_is_refused_instead(tmp_path):
    """The defect this kills, on real bytes: six months of 2026 sum to 21,720, which is
    below the band and would publish CROSSED — a crash headline manufactured by a
    publication calendar."""
    landings = _plant(tmp_path, _lines())
    partial = pr_landings_realized(landings.frame, 2026)
    assert partial.value == QC_2026_PARTIAL_PROVINCE
    assert len(partial.months) == QC_2026_PARTIAL_MONTHS < MONTHS_PER_CLOSED_YEAR
    assert partial.value < BAND[0]                       # presence-only checking: CROSSED
    assert evaluate_indicator(
        _spec(as_of=2026), partial.value, available=True, now=2026).status is Status.CROSSED
    ev = evaluate_pr_landings(landings, band=BAND, now=(2026, 8))
    assert ev.result.status is not Status.CROSSED and ev.result.status is Status.UNKNOWN


def test_a_month_gap_inside_a_relabeled_year_is_not_a_closed_year(tmp_path):
    """Silent interior gaps are real (103 of 172 members carry them). A year is closed only
    when all twelve month tokens are present — not when the row count merely looks full."""
    era = _relabel_year(_lines(), "2025", "2026")
    assert closed_plan_years(_plant(tmp_path, era).frame) == [2026]
    gapped = [era[0]] + [ln for ln in era[1:] if ln.split("\t")[_COL["EN_MONTH"]] != "Sep"]
    assert closed_plan_years(_plant(tmp_path, gapped).frame) == []


def test_closed_year_check_is_vocabulary_bound_not_a_count(tmp_path):
    """Twelve DISTINCT tokens is not twelve MONTHS. The loader refuses an unknown token, so
    this frame cannot arrive through it — which is the point: `closed_plan_years` is
    importable, and a caller that hands it a frame from anywhere else must still be refused.
    A `len(months) == 12` gate passes this input; the vocabulary equality does not."""
    import pandas as pd
    rows = [{"EN_YEAR": "2026", "EN_MONTH": m, "EN_PROVINCE_TERRITORY": QUEBEC_PROVINCE,
             "EN_CENSUS_METROPOLITAN_AREA": "Montréal", "TOTAL": "5"}
            for m in ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sept", "Oct", "Nov", "Dec")]   # `Sept`, not `Sep`
    frame = pd.DataFrame(rows)
    assert frame["EN_MONTH"].nunique() == MONTHS_PER_CLOSED_YEAR
    assert closed_plan_years(frame) == []


def test_feed_freshness_limit_admits_the_measured_publication_lag(tmp_path):
    """Publication lag runs 1.5-4 months, so a limit tighter than ~5 makes this indicator
    permanently UNKNOWN. At 5 months behind, it still evaluates; past that the feed itself
    is stale — and stale keeps its measurement, because one honestly exists."""
    assert FEED_FRESHNESS_MONTHS == 5
    landings = _plant(tmp_path, _relabel_year(_lines(), "2025", "2026"))
    assert landings.latest_period == (2026, 12)
    inside = evaluate_pr_landings(landings, band=BAND, now=(2027, 5))     # 5 months
    assert inside.result.status is Status.CROSSED and inside.result.reason is None
    outside = evaluate_pr_landings(landings, band=BAND, now=(2027, 6))    # 6 months
    assert outside.result.status is Status.UNKNOWN and outside.result.reason is Reason.STALE
    assert outside.result.current_value == QC_2025_PROVINCE and outside.result.as_of == 2026


# --- carry 5: the degenerate-feed floor never crosses ---------------------------------

def test_all_marker_modeled_member_raises_to_unknown_and_never_crosses(tmp_path):
    """An all-suppressed Montréal defeats the loader's presence-only gate one level down:
    the member is still IN the feed, so nothing raises, and the provincial sum falls to
    22,810 (−62%; the CMA pair falls −81%) — comfortably CROSSED under band comparison.
    A degenerate feed is not evidence of a crossing."""
    era = _relabel_year(_lines(), "2025", "2026")
    gutted = _plant(tmp_path, _suppress(era, "2026", cma="Montréal"))
    realized = pr_landings_realized(gutted.frame, 2026)
    assert realized.value == 22810.0 < BAND[0]           # would be CROSSED on presence-only
    ev = evaluate_pr_landings(gutted, band=BAND, now=(2027, 1))
    assert ev.result.status is Status.UNKNOWN and ev.result.status is not Status.CROSSED
    assert ev.result.reason is Reason.SOURCE_UNAVAILABLE
    assert ev.result.current_value is None and ev.result.as_of is None   # gutted sum never rides


def test_all_marker_selection_is_unknown_not_a_zero(tmp_path):
    era = _relabel_year(_lines(), "2025", "2026")
    dead = _plant(tmp_path, _suppress(era, "2026"))
    realized = pr_landings_realized(dead.frame, 2026)
    assert realized.value == 0.0 and realized.n_numeric == 0     # `--` is not a zero
    ev = evaluate_pr_landings(dead, band=BAND, now=(2027, 1))
    assert ev.result.status is Status.UNKNOWN and ev.result.current_value is None


def test_sum_indistinguishable_from_suppression_is_unknown(tmp_path):
    """Both modeled members report, every cell is a legal integer, and the total is still
    inside what the suppressed cells alone could have carried. Presence and per-member
    content both pass; the envelope floor is what refuses."""
    era = _relabel_year(_lines(), "2025", "2026")
    floored = _plant(tmp_path, _floor_to_five(era, "2026", keep=("Montréal", "Québec")))
    realized = pr_landings_realized(floored.frame, 2026)
    assert realized.n_numeric > 0 and realized.value <= 5.0 * realized.n_suppressed
    for member in ("Montréal", "Québec"):
        assert realized.numeric_by_member[member] > 0     # per-member gate is NOT what refuses
    ev = evaluate_pr_landings(floored, band=BAND, now=(2027, 1))
    assert ev.result.status is Status.UNKNOWN and ev.result.current_value is None


# --- the evaluating paths that DO produce a verdict -----------------------------------

def test_closed_plan_year_crosses_high_on_the_measured_provincial_sum(tmp_path):
    """Real 2025 provincial bytes under a plan-era stamp: 60,010 against the 45k-plan band
    is a genuine CROSSED — the verdict the tripwire exists to produce."""
    landings = _plant(tmp_path, _relabel_year(_lines(), "2025", "2026"))
    ev = evaluate_pr_landings(landings, band=BAND, now=(2027, 3))
    assert ev.result.status is Status.CROSSED and ev.result.reason is None
    assert ev.result.current_value == QC_2025_PROVINCE and ev.result.as_of == 2026
    rec = tripwire_record(ev.result)
    assert_tripwire_record_valid(rec)
    assert rec["source"] == SOURCE_REGISTRY[PR_LANDINGS_INDICATOR]
    assert set(rec) <= set(TRIPWIRE_RECORD_REQUIRED) | {"reason"}
    assert exit_code([ev.result]) != 0


def test_within_a_caller_supplied_band_the_same_year_is_ok(tmp_path):
    """The band is the CALLER's — no band literal lives in the module. Same bytes, a band
    that brackets them, and the gate returns OK with exit 0."""
    landings = _plant(tmp_path, _relabel_year(_lines(), "2025", "2026"))
    ev = evaluate_pr_landings(landings, band=(55000.0, 65000.0), now=(2027, 3))
    assert ev.result.status is Status.OK and ev.result.reason is None
    assert exit_code([ev.result]) == 0


def _rows_of(lines: list[str], year: str) -> list[str]:
    return [ln for ln in lines[1:] if ln.split("\t")[_COL["EN_YEAR"]] == year]


def test_latest_closed_plan_year_wins_when_several_are_available(tmp_path):
    """Two full plan-era years, each a relabeled copy of real 2025, and NEITHER carries the
    slice's own partial-2026 rows. The earlier construction concatenated two whole relabeled
    slices, which silently re-admitted those 6 real 2026 months alongside the relabeled ones
    — 340 duplicate cell keys, double-counting Jan-Jun of the year under test. It passed
    only because the assertion was about WHICH year won, never about its sum. That is the
    duplicate-cell defect (review finding F5) caught in this suite's own fixture, so the
    construction is corrected here and the loader now refuses the old one outright."""
    lines = _lines()
    both = (_rows_of(_relabel_year(lines, "2025", "2026"), "2026")
            + _rows_of(_relabel_year(lines, "2025", "2027"), "2027"))
    landings = _plant(tmp_path, [lines[0]] + both)
    assert closed_plan_years(landings.frame) == [2026, 2027]
    ev = evaluate_pr_landings(landings, band=BAND, now=(2028, 3))
    assert ev.result.as_of == 2027
    assert ev.realized.value == QC_2025_PROVINCE      # the winning year is not double-counted


def test_expired_plan_era_composes_to_stale_through_the_generic_gate(tmp_path):
    """The 2029 datum is the last the plan governs. Evaluated in 2031 it is a year-2 stale
    baseline: UNKNOWN, measurement retained. Deliberate composition, pinned so it stays so."""
    landings = _plant(tmp_path, _relabel_year(_lines(), "2025", "2029"))
    ev = evaluate_pr_landings(landings, band=BAND, now=(2031, 3))
    assert ev.result.status is Status.UNKNOWN and ev.result.reason is Reason.STALE
    assert ev.result.current_value == QC_2025_PROVINCE and ev.result.as_of == 2029


def test_absent_feed_is_unknown_and_nothing_is_fabricated():
    ev = evaluate_pr_landings(PRLandings(available=False, reason="not found"),
                              band=BAND, now=(2027, 3))
    assert ev.result.status is Status.UNKNOWN and ev.result.reason is Reason.SOURCE_UNAVAILABLE
    assert ev.result.current_value is None and ev.result.as_of is None
    assert ev.realized is None
    assert_tripwire_record_valid(tripwire_record(ev.result))


# --- what the evaluation hands FORWARD (Task 29's envelope, never the record) ----------

def test_vintage_rides_the_evaluation_never_the_record(tmp_path):
    """IRCC restates history (0.4-0.7% of overlapping cells per vintage, a decade deep), so
    a red must be attributable to data-vs-code: the evaluation carries the feed's content
    digest. It CANNOT ride the record — the record allowlist is closed."""
    landings = _plant(tmp_path, _lines())
    expected = hashlib.sha256((tmp_path / CSV_NAME).read_bytes()).hexdigest()
    assert landings.sha256 == expected
    ev = evaluate_pr_landings(landings, band=BAND, now=(2026, 8))
    assert ev.vintage_sha256 == expected
    assert "sha256" not in tripwire_record(ev.result)
    assert_tripwire_record_valid(tripwire_record(ev.result))


def test_run_log_detail_never_reaches_the_record(tmp_path):
    landings = _plant(tmp_path, _lines())
    ev = evaluate_pr_landings(landings, band=BAND, now=(2026, 8))
    assert ev.log and isinstance(ev.log, str)          # detail exists, for the RUN LOG
    assert ev.log not in tripwire_record(ev.result).values()
    assert set(tripwire_record(ev.result)) <= set(TRIPWIRE_RECORD_REQUIRED) | {"reason"}


def test_the_wired_indicator_is_covered_by_the_code_owned_required_set():
    """`run_exit_code` ranges over REQUIRED_INDICATORS, so an indicator that computes
    honestly but sits outside that set is a gate nobody consults. Renaming one of the two
    constants without the other reds here. (This docstring said `exit_code` and that was
    false of the delivered function — it ranged over whatever list it was handed, which is
    review finding F4; the coverage question now has its own gate.)"""
    assert PR_LANDINGS_INDICATOR in REQUIRED_INDICATORS
    assert PR_LANDINGS_INDICATOR in SOURCE_REGISTRY
    assert QUEBEC_PROVINCE == "Quebec"


# ---------------------------------------------------------------------------------------
# LAYER 3 — review-response gates. Every one of these was a demonstrated FALSE GREEN or a
# demonstrated escape from the module's own taxonomy, reproduced on the frozen slice.
# ---------------------------------------------------------------------------------------

# --- F1 (partial): the closed-year check verified PROVINCE months, not member coverage ---

def test_a_modeled_member_month_gap_is_not_a_closed_year(tmp_path):
    """`set(province_rows[EN_MONTH]) == EN_MONTHS` is a UNION over all members, so two
    members alone satisfy it. Measured on the slice: drop Montréal's Jan-May and the year
    still counts CLOSED, realized falls to 46,640 (a 22% hole), and the gate publishes
    status=OK / exit 0 against a true 60,010 that is CROSSED. Per-MODELED-member coverage
    is the part derivable from the code-owned `MODELED_CMAS` — and it is clearable: both
    modeled members carry 12/12 months in the real 2025 data (11 of 32 members do not,
    which is why a whole-province 'every member 12/12' rule would never clear)."""
    era = _relabel_year(_lines(), "2025", "2026")
    gapped = [era[0]] + [
        ln for ln in era[1:]
        if not (ln.split("\t")[_COL["EN_YEAR"]] == "2026"
                and ln.split("\t")[_COL["EN_CENSUS_METROPOLITAN_AREA"]] == "Montréal"
                and ln.split("\t")[_COL["EN_MONTH"]] in ("Jan", "Feb", "Mar", "Apr", "May"))]
    landings = _plant(tmp_path, gapped)
    assert set(landings.frame[landings.frame["EN_YEAR"] == "2026"]["EN_MONTH"]) == set(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))          # province union still full
    assert closed_plan_years(landings.frame) == []            # member coverage is not
    ev = evaluate_pr_landings(landings, band=BAND, now=(2027, 3))
    assert ev.result.status is Status.UNKNOWN and ev.result.status is not Status.OK
    assert exit_code([ev.result]) != 0


def test_an_intact_modeled_pair_still_closes_the_year(tmp_path):
    """The countervailing half: the new coverage rule must not make the indicator
    permanently UNKNOWN. Real 2025 bytes under a plan-era stamp still close."""
    landings = _plant(tmp_path, _relabel_year(_lines(), "2025", "2026"))
    assert closed_plan_years(landings.frame) == [2026]


# --- F2: value integrity was enforced on the value but not on its twin, the BAND --------

@pytest.mark.parametrize("band", [(math.nan, 50000.0), (40000.0, math.nan),
                                  (math.nan, math.nan), (40000.0, math.inf),
                                  (-math.inf, 50000.0)])
def test_non_finite_band_endpoint_is_unknown_never_within_band(band):
    """A non-finite endpoint makes BOTH boundary comparisons False, so every value
    classifies as within-band: status=OK, exit 0 — verbatim the mechanism spec §7c names
    in words for the VALUE side ('naive comparisons classify NaN as inside every band').
    ±Inf belongs in the same branch and not only by symmetry: band endpoints RIDE the
    emitted record, and spec §7 emits tripwire JSON with `allow_nan=False`, which rejects
    Infinity as well as NaN — an endpoint that cannot be serialized is not a threshold.
    Same closed reason token as inversion; the enum is spec-closed, so no new member."""
    r = evaluate_indicator(_spec(band_low=band[0], band_high=band[1]), 45000,
                           available=True, now=2026)
    assert r.status is Status.UNKNOWN and r.reason is Reason.MALFORMED_BAND
    assert exit_code([r]) != 0


def test_non_coercible_band_raises_inside_the_taxonomy():
    """A str endpoint crashed the gate with `TypeError: '>' not supported between str and
    float` — a class no caller's `except LoaderError`/`except ValueError` catches, so the
    verification gate DIED instead of refusing. It cannot ride the record either (band_low
    is a float field), so it is a named terminal, not an UNKNOWN."""
    with pytest.raises(ValueError, match="band"):
        evaluate_indicator(_spec(band_low="x"), 45000, available=True, now=2026)
    with pytest.raises(ValueError, match="band"):
        evaluate_pr_landings(PRLandings(available=False, reason="n/a"),
                             band=("x", 50000.0), now=(2027, 3))


def test_a_numeric_field_can_never_carry_a_string():
    """The same closure one step further (F2's census names band-non-numeric). `float()`
    coercion means a str endpoint like "40000" compares fine and then RIDES the record's
    numeric band field — a string in a typed position, which is the channel spec §7's "no
    open string anywhere" rule exists to close. The type is bound at the contract boundary,
    so it holds however the record was built."""
    rec = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    for field_name in ("current_value", "band_low", "band_high"):
        with pytest.raises(ValueError, match="number"):
            assert_tripwire_record_valid({**rec, field_name: "45000"})
    with pytest.raises(ValueError, match="number"):
        assert_tripwire_record_valid({**rec, "band_high": True})   # bool is not a threshold


def test_a_non_finite_band_can_never_ride_a_record():
    """The refusal is not enough on its own: the malformed endpoint still travels in the
    record's band_low/band_high, and `json.dumps(..., allow_nan=False)` would only discover
    it at emit time. The contract validator is where it must die."""
    r = evaluate_indicator(_spec(band_high=math.nan), 45000, available=True, now=2026)
    with pytest.raises(ValueError, match="finite"):
        assert_tripwire_record_valid(tripwire_record(r))


# --- F3: only ONE of the record's four string-typed positions was bound -----------------

def test_status_token_is_bound_to_the_status_enum():
    rec = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    with pytest.raises(ValueError, match="status"):
        assert_tripwire_record_valid({**rec, "status": "crash_probability=0.35"})


def test_indicator_is_registry_bound_and_source_is_checked_unconditionally():
    """The source binding was CONDITIONAL — `if ind in SOURCE_REGISTRY` — so an
    unregistered indicator skipped it entirely and a record that literally announces a
    crash probability passed the validator whose whole job is to make that quantity
    inexpressible. Spec §7: EVERY string-typed position is registry- or enum-bound."""
    rec = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    with pytest.raises(ValueError, match="indicator"):
        assert_tripwire_record_valid({**rec, "indicator": "crash_probability=0.35"})
    with pytest.raises(ValueError, match="indicator"):
        assert_tripwire_record_valid({**rec, "indicator": "xx",
                                      "source": "crash_probability=0.35"})
    with pytest.raises(ValueError, match="indicator"):
        assert_tripwire_record_valid({"indicator": "crash_probability", "current_value": 0.35,
                                      "source": "P(crash)=0.35 by 2031", "as_of": 2026,
                                      "band_low": 0.0, "band_high": 1.0, "status": "OK"})


def test_reason_is_present_exactly_when_status_is_unknown():
    """Spec §7 writes the state as `UNKNOWN(reason)`. An UNKNOWN with no reason names no
    cause; a CROSSED carrying `stale` is two incompatible verdicts in one record."""
    ok = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    with pytest.raises(ValueError, match="reason"):
        assert_tripwire_record_valid({**ok, "reason": "stale"})
    unavail = tripwire_record(evaluate_indicator(_spec(), None, available=False, now=2026))
    with pytest.raises(ValueError, match="reason"):
        assert_tripwire_record_valid({k: v for k, v in unavail.items() if k != "reason"})


# --- F4: completeness was a SUBSET test, and the exit path never saw the required set ---

def test_unregistered_indicator_is_a_run_level_terminal():
    """`required - set(indicators)` is one-directional: an EXTRA key was reported
    'complete'. It cannot be a per-indicator UNKNOWN either — the reason enum is
    spec-closed and carries no token for it — so it is the same RUN-level terminal codex
    r10 set for the empty registry."""
    with pytest.raises(LoaderError, match="unregistered"):
        check_registry(sorted(REQUIRED_INDICATORS) + ["crash_probability"])


def test_the_code_owned_required_set_cannot_be_substituted_at_the_call_site():
    """`required=` was a caller-overridable default on the function whose entire purpose is
    that the required set is CODE-owned and not co-deletable."""
    import inspect
    assert "required" not in inspect.signature(check_registry).parameters


def test_run_exit_code_requires_the_full_code_owned_set():
    """`exit_code` ranges over WHAT IT IS HANDED — a truthy list of OK results exits 0
    however short it is, and REQUIRED_INDICATORS is never consulted. Spec §7c: 'Exit code:
    0 only when every code-required indicator is present exactly once ... and OK.' The
    run-level gate is composed on top; `exit_code`'s own semantics are plan-pinned above."""
    every = [evaluate_indicator(_spec(indicator=name), 45000, available=True, now=2026)
             for name in sorted(REQUIRED_INDICATORS)]
    assert run_exit_code(every) == 0
    assert run_exit_code(every[:-1]) != 0                      # short of the required set
    assert run_exit_code(every + [every[0]]) != 0              # present twice
    smuggled = evaluate_indicator(
        TripwireSpec("crash_probability", 0.0, 1.0, 2026, 1, SourceKind.WIRED),
        0.35, available=True, now=2026)
    assert smuggled.status is Status.OK                        # it evaluates clean...
    assert run_exit_code(every + [smuggled]) != 0              # ...and still never exits 0
    crossed = evaluate_indicator(_spec(indicator=sorted(REQUIRED_INDICATORS)[0]), 60000,
                                 available=True, now=2026)
    assert run_exit_code(every[1:] + [crossed]) != 0


# --- F5: duplicate data cells double-count, and doubling reaches a FALSE GREEN ----------

def test_a_duplicated_vintage_cannot_reach_a_verdict(tmp_path):
    """Halving 2026's cells puts the province at 29,918 — CROSSED below a 55k-65k band.
    Duplicate every row and it becomes 59,836: OK, exit 0, record accepted. The refusal
    belongs in the loader's schema stage, so nothing downstream can be handed the sum."""
    era = _relabel_year(_lines(), "2025", "2026")
    halved = [era[0]]
    for ln in era[1:]:
        f = ln.split("\t")
        if f[_COL["EN_YEAR"]] == "2026" and f[_COL["TOTAL"]] != "--":
            f[_COL["TOTAL"]] = str(int(f[_COL["TOTAL"]]) // 2)
        halved.append("\t".join(f))
    wide = (55000.0, 65000.0)
    single = evaluate_pr_landings(_plant(tmp_path, halved), band=wide, now=(2027, 3))
    assert single.result.status is Status.CROSSED and single.realized.value == 29918.0
    doubled = halved + [ln for ln in halved[1:]
                        if ln.split("\t")[_COL["EN_YEAR"]] == "2026"]
    with pytest.raises(LoaderError, match="duplicate"):
        _plant(tmp_path, doubled)


# --- F8: the staleness gate was one-sided ----------------------------------------------

def test_a_feed_dated_ahead_of_now_is_refused_not_evaluated(tmp_path):
    """`behind` is signed and only `> FEED_FRESHNESS_MONTHS` acted, so a feed publishing
    periods AFTER `now` fell straight through to the band comparison on an impossible
    vintage. The generic gate's own `as_of > now` guard is silent here — it sees the
    SELECTED year, which is in the past. The measurement exists, so this is the
    value-retaining UNKNOWN branch: `future_as_of` is NOT a nullable reason, and a
    null-valued record under it fails the nullability contract."""
    landings = _plant(tmp_path, _relabel_year(_lines(), "2025", "2026"))
    assert landings.latest_period == (2026, 12)
    ev = evaluate_pr_landings(landings, band=BAND, now=(2026, 1))
    assert ev.result.status is Status.UNKNOWN and ev.result.reason is Reason.FUTURE_AS_OF
    assert ev.result.current_value == QC_2025_PROVINCE and ev.result.as_of == 2026
    assert_tripwire_record_valid(tripwire_record(ev.result))
    assert exit_code([ev.result]) != 0
    assert "ahead" in ev.log.lower()
