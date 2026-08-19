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
import inspect
import math
from pathlib import Path

import pytest

from demoflow.errors import LoaderError
from demoflow.loaders.constants import CONSTANTS
from demoflow.loaders.ircc import (
    CSV_NAME, EN_MONTHS, EXPECTED_COLUMNS, MODELED_CMAS, QUEBEC_REQUIRED_CMAS,
    PRLandings, load_pr_landings,
)
from demoflow.output.tripwires import (
    CELL_ROUNDING_HALFWIDTH, FEED_FRESHNESS_MONTHS, MONTHS_PER_CLOSED_YEAR,
    NULLABLE_REASONS, PLAN_GOVERNED_YEARS, PR_LANDINGS_INDICATOR, QUEBEC_PROVINCE,
    REQUIRED_INDICATORS, SOURCE_REGISTRY, SUPPRESSED_CELL_MAX, TRIPWIRE_RECORD_REQUIRED,
    Reason, SourceKind, Status, TripwireSpec,
    assert_tripwire_record_valid, check_registry, closed_plan_years, evaluate_indicator,
    evaluate_pr_landings, exit_code, pr_landings_realized, run_exit_code, tripwire_record,
)
# The month-vocabulary CLAUSE by name. Private, and imported deliberately: the rule is an
# equivalent mutant at `closed_plan_years`' boundary, so it is only killable here.
from demoflow.output.tripwires import _months_are_the_closed_vocabulary

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


def test_a_duplicate_record_from_the_producer_validates():
    """THE SEAM between the producer and the contract, which nothing crossed.

    `check_registry` emits its duplicate record with `current_value=None` and `as_of=None` — a
    duplicated key names no honest measurement, the identical logic that nulls the other four
    UNKNOWN branches. `NULLABLE_REASONS` did not list `duplicate_indicator`, so
    `assert_tripwire_record_valid` took its NON-null branch and REJECTED a record its own
    module had just built. Latent rather than live: nothing in the run emits a duplicate today,
    and that is exactly why it shipped — the two halves disagreed and no test made them meet.

    The crossing is the test: every record `check_registry` produces must validate, for BOTH
    completeness reasons, and both must be null on both nullable fields. Asserted over the
    reasons the producer can actually emit rather than over a copy of the frozenset, so a
    record that starts carrying a value reds here instead of passing a set-equality check."""
    dup = check_registry(sorted(REQUIRED_INDICATORS) + [PR_LANDINGS_INDICATOR])
    assert [r.reason for r in dup] == [Reason.DUPLICATE_INDICATOR]
    short = check_registry([PR_LANDINGS_INDICATOR])
    assert {r.reason for r in short} == {Reason.MISSING_INDICATOR}
    for produced in (dup, short):
        for r in produced:
            assert r.current_value is None and r.as_of is None
            assert_tripwire_record_valid(tripwire_record(r))   # the contract accepts its producer


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


@pytest.mark.parametrize("year,cells,numeric,suppressed,value,bound", [
    (2025, QC_2025_CELLS, 304, QC_2025_SUPPRESSED, QC_2025_PROVINCE, (59250.0, 61025.0)),
    (2026, 174, 142, 32, QC_2026_PARTIAL_PROVINCE, (21365.0, 22235.0)),
])
def test_the_published_interval_is_asymmetric_because_suppression_only_adds(
        tmp_path, year, cells, numeric, suppressed, value, bound):
    """ROUNDING is two-sided on PUBLISHED cells (base-5, ±2.5 each). SUPPRESSION IS
    ONE-SIDED: a `--` contributes 0 to the sum and its true contribution is [0, +5].

    The shipped property published a SYMMETRIC ±2.5·n_cells and called it "±(rounding +
    suppression)" — 355 × 2.5 = 887.5 on this slice, an interval centred 2.5×51 = 127.5
    BELOW the arithmetic whose upper end it understated by the same 127.5 (quant gate F3 /
    stress gate F9). The strongest argument is internal: `_degenerate` models the suppressed
    cell correctly one-sided one constant away, as `SUPPRESSED_CELL_MAX * n_suppressed`.

    Both legs are asserted against the module's OWN constants as well as against the
    measured bytes, so a re-tuned constant reds rather than silently re-centring."""
    realized = pr_landings_realized(_plant(tmp_path, _lines()).frame, year)
    assert (realized.n_cells, realized.n_numeric, realized.n_suppressed) == (
        cells, numeric, suppressed)
    assert realized.n_numeric + realized.n_suppressed == realized.n_cells
    assert realized.value == value
    lo, hi = realized.interval
    assert (lo, hi) == pytest.approx(bound)
    assert lo == pytest.approx(value - CELL_ROUNDING_HALFWIDTH * numeric)
    assert hi == pytest.approx(value + CELL_ROUNDING_HALFWIDTH * numeric
                               + SUPPRESSED_CELL_MAX * suppressed)
    # The interval is NOT centred on the realized value, and it is wider ABOVE than below —
    # the whole content of the correction, stated as a property rather than as two numbers.
    assert hi - value > value - lo
    assert (hi - value) - (value - lo) == pytest.approx(SUPPRESSED_CELL_MAX * suppressed)
    # ...and the symmetric figure it replaced sat INSIDE the true upper bound.
    assert value + CELL_ROUNDING_HALFWIDTH * cells < hi


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
    are not attributable to Québec (measured ≤20/yr — inside the 1,775-landing width the
    published interval carries on this slice)."""
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


def test_closed_year_check_is_vocabulary_bound_not_a_count():
    """Twelve DISTINCT tokens is not twelve MONTHS — asserted against the CLAUSE, because
    through `closed_plan_years` this rule cannot be observed at all.

    WHAT THIS TEST USED TO DO, and why it was passing for the wrong reason. It handed
    `closed_plan_years` a directly-built frame of twelve Montréal rows carrying `Sept` instead
    of `Sep` and asserted the year did not close. It did not close — but the MEMBER-SET clause
    and the per-MODELED-member clause both refuse that frame on their own (thirty required
    members absent, `Québec` absent), so the assertion held with the month-vocabulary clause
    mutated to a bare count AND with it deleted outright. Run 29's reviewer measured both mutants
    surviving the FULL suite; reproduced here at module scope against pristine HEAD sources — 60
    passed under each mutant, this test among them.

    THE MUTANT IS EQUIVALENT AT THE FUNCTION'S BOUNDARY, so isolating the clause is the only
    fix. `closed_plan_years` also demands `by_member[m] == set(EN_MONTHS)` for both
    `MODELED_CMAS`, which forces the province-wide union to CONTAIN all twelve tokens; on any
    frame satisfying that, `len(set(months)) == 12` holds exactly when
    `set(months) == set(EN_MONTHS)` does. No input to `closed_plan_years` can separate them.
    Handed the rows directly, the rule separates them on the first input below.

    THE REACHABLE THREAT IS A DIRECTLY CONSTRUCTED FRAME AND ONLY THAT. `ircc._check_periods`
    refuses `Sept` at LOAD, so no frame carrying it arrives through the loader — but
    `closed_plan_years` is importable, and a caller handing it a frame assembled anywhere else
    must still be refused rather than counted. The clause's WIRING is defended one test down.
    """
    import pandas as pd
    smuggled = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sept", "Oct", "Nov", "Dec")        # `Sept`, not `Sep`
    rows = pd.DataFrame([{"EN_MONTH": m} for m in smuggled])
    assert rows["EN_MONTH"].nunique() == MONTHS_PER_CLOSED_YEAR    # a bare count says CLOSED
    assert set(smuggled) != set(EN_MONTHS)
    assert not _months_are_the_closed_vocabulary(rows)             # the vocabulary says NO
    # ...and it is clearable, or it is not a gate: the real twelve pass.
    assert _months_are_the_closed_vocabulary(pd.DataFrame([{"EN_MONTH": m} for m in EN_MONTHS]))
    # a SHORT year is refused by the same rule, which is the shape the loader does deliver.
    assert not _months_are_the_closed_vocabulary(
        pd.DataFrame([{"EN_MONTH": m} for m in EN_MONTHS[:6]]))


def test_an_extra_month_token_refuses_a_year_the_other_two_clauses_accept(tmp_path):
    """THE CLAUSE'S WIRING, which the isolated test above cannot reach: is the rule actually
    consulted by `closed_plan_years`?

    Built to satisfy EVERY OTHER CLAUSE, so only the month-vocabulary rule can refuse it: real
    2025 bytes under a plan-era stamp (all 31 required members, both modeled members 12/12),
    plus ONE appended cell on a NON-modeled member carrying `Sept`. Delete the clause and this
    year closes; keep it and the year is refused. Directly constructed for the same reason as
    above — `_check_periods` refuses the token at load, so this frame is spliced onto a loaded
    one rather than planted through the loader.

    THIS TEST DOES NOT DISTINGUISH the bare-count rewrite (thirteen tokens fails a count too);
    the test above does. Two mutants, two rules, two tests: the rule, and its wiring."""
    import pandas as pd
    era = _relabel_year(_lines(), "2025", "2026")
    landings = _plant(tmp_path, era)
    assert closed_plan_years(landings.frame) == [2026]         # the un-spliced frame CLOSES

    extra_token, smuggler = "Sept", "Saguenay"
    assert extra_token not in set(EN_MONTHS)
    assert smuggler not in MODELED_CMAS and smuggler in QUEBEC_REQUIRED_CMAS
    row = {column: "" for column in EXPECTED_COLUMNS}
    row.update({"EN_YEAR": "2026", "EN_MONTH": extra_token,
                "EN_PROVINCE_TERRITORY": QUEBEC_PROVINCE,
                "EN_CENSUS_METROPOLITAN_AREA": smuggler, "TOTAL": "5"})
    frame = pd.concat([landings.frame, pd.DataFrame([row])], ignore_index=True)

    # every OTHER clause is satisfied on this frame — stated as assertions, not as a claim.
    assert QUEBEC_REQUIRED_CMAS <= _qc_members(frame, "2026")
    for modeled in MODELED_CMAS:
        member = frame[(frame["EN_YEAR"] == "2026")
                       & (frame["EN_CENSUS_METROPOLITAN_AREA"] == modeled)]
        assert set(member["EN_MONTH"]) == set(EN_MONTHS)
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


# --- Ruling U: completeness is MEMBER-SET, not month-presence (F1's remaining half) -----
# Ruling U (seat, 2026-08-18) closes the DATA-path version of the scope confusion the SCOPE
# block above prevents on the literal path. `MODELED_CMAS` coverage is the part derivable
# from a two-name constant; it leaves the province's name wearable by any subset that
# happens to include those two. The third clause fixes WHO must report.

def _only_members(lines: list[str], members) -> list[str]:
    """Truncate the feed to `members` — a vintage in which the province lost everyone else."""
    keep = set(members)
    return [lines[0]] + [ln for ln in lines[1:]
                         if ln.split("\t")[_COL["EN_CENSUS_METROPOLITAN_AREA"]] in keep]


def _without_member(lines: list[str], member: str) -> list[str]:
    return [lines[0]] + [ln for ln in lines[1:]
                         if ln.split("\t")[_COL["EN_CENSUS_METROPOLITAN_AREA"]] != member]


def _qc_members(frame, year: str) -> set:
    sel = frame[(frame["EN_YEAR"] == year) & (frame["EN_PROVINCE_TERRITORY"] == QUEBEC_PROVINCE)]
    return set(sel["EN_CENSUS_METROPOLITAN_AREA"])


def test_a_feed_truncated_to_the_modeled_pair_is_refused(tmp_path):
    """THE CRITICAL. Both shipped rules see nothing wrong on a two-member feed: the
    province-wide month union is full (the pair alone supplies twelve tokens) and both
    modeled members are 12/12. Measured on the frozen slice under a plan-era stamp, the
    shipped gate closes 2026 and publishes 45,895 over 24 cells — the Montréal+Québec CMA
    PAIR wearing the province's name — status OK, exit 0, record accepted, against a true
    provincial 60,010. Member-set completeness is what refuses it."""
    era = _relabel_year(_lines(), "2025", "2026")
    truncated = _plant(tmp_path, _only_members(era, MODELED_CMAS))
    assert _qc_members(truncated.frame, "2026") == set(MODELED_CMAS)
    assert set(truncated.frame[truncated.frame["EN_YEAR"] == "2026"]["EN_MONTH"]) == set(EN_MONTHS)
    realized = pr_landings_realized(truncated.frame, 2026)
    assert realized.value == QC_2025_PAIR and realized.n_cells == 24
    assert BAND[0] < realized.value < BAND[1]          # it would publish OK, exit 0
    assert closed_plan_years(truncated.frame) == []
    ev = evaluate_pr_landings(truncated, band=BAND, now=(2027, 3))
    assert ev.result.status is Status.UNKNOWN and ev.result.status is not Status.OK
    assert ev.result.reason is Reason.SOURCE_UNAVAILABLE
    assert ev.result.current_value is None and ev.result.as_of is None
    assert exit_code([ev.result]) != 0
    assert_tripwire_record_valid(tripwire_record(ev.result))
    # The reason enum is spec-closed, so this surfaces as `source_unavailable` exactly like a
    # pre-era refusal does. The RUN LOG is the only place the two can be told apart.
    assert "member-set truncation" in ev.log.lower()
    # ...and the discriminator must ALSO fire on the shape a truncation would arrive in
    # TODAY, while 2026 is still 6 months deep. Gating the note on month-completeness would
    # log plain pre-era here — the very confusion it exists to close. The intact feed in that
    # same state stays silent (`test_first_evaluable_year_is_2026_and_today_it_is_not_closed`).
    partial = _plant(tmp_path, _only_members(_lines(), MODELED_CMAS))
    log = evaluate_pr_landings(partial, band=BAND, now=(2026, 8)).log
    assert "member-set truncation" in log.lower() and "6 of 12 months" in log


def test_dropping_one_non_modeled_member_is_a_value_integrity_breach(tmp_path):
    """The exploit the review had not listed, and it is quieter than the truncation: drop
    ONE non-modeled member and the shipped gate still closes every year. Measured at the
    (55000, 65000) probe band the drop NEVER changes a verdict on any year — deltas run
    -60 to -675 — so no band comparison could ever catch it. It is a VALUE-INTEGRITY breach:
    59,335 published under the name of a provincial 60,010."""
    dropped = "Saguenay"
    assert dropped not in MODELED_CMAS
    era = _relabel_year(_lines(), "2025", "2026")
    landings = _plant(tmp_path, _without_member(era, dropped))
    realized = pr_landings_realized(landings.frame, 2026)
    assert realized.value == 59335.0 < QC_2025_PROVINCE
    wide = (55000.0, 65000.0)
    for value in (realized.value, QC_2025_PROVINCE):       # same verdict either way
        assert evaluate_indicator(_spec(band_low=wide[0], band_high=wide[1]), value,
                                  available=True, now=2026).status is Status.OK
    assert closed_plan_years(landings.frame) == []
    ev = evaluate_pr_landings(landings, band=wide, now=(2027, 3))
    assert ev.result.status is Status.UNKNOWN and ev.result.current_value is None
    assert exit_code([ev.result]) != 0


def test_the_member_set_rule_is_clearable_on_the_intact_year(tmp_path):
    """The countervailing half, and the 2020-anchor property in miniature: a rule that can
    never clear is not a gate. Real 2025 bytes under a plan-era stamp carry every required
    member, so the year still CLOSES and still reaches a verdict."""
    era = _relabel_year(_lines(), "2025", "2026")
    landings = _plant(tmp_path, era)
    assert QUEBEC_REQUIRED_CMAS <= _qc_members(landings.frame, "2026")
    assert closed_plan_years(landings.frame) == [2026]
    ev = evaluate_pr_landings(landings, band=(55000.0, 65000.0), now=(2027, 3))
    assert ev.result.status is Status.OK and ev.result.reason is None
    assert exit_code([ev.result]) == 0


def test_the_optional_intermittent_member_is_not_required(tmp_path):
    """Pins the INTERSECTION choice. The required set is the cross-year intersection of the
    feed's Quebec members, which leaves exactly one intermittent member OPTIONAL — published
    in 6 of the 12 years. Without this test a future reader "tightens" the constant to the
    32-member union and the gate silently stops clearing six real years. The optional member
    is DERIVED from the fixture here, never named: fixture-2025 members minus the constant."""
    era = _relabel_year(_lines(), "2025", "2026")
    optional = sorted(_qc_members(_plant(tmp_path, era).frame, "2026") - QUEBEC_REQUIRED_CMAS)
    assert len(optional) == 1
    landings = _plant(tmp_path, _without_member(era, optional[0]))
    assert optional[0] not in _qc_members(landings.frame, "2026")
    assert closed_plan_years(landings.frame) == [2026]


def test_the_required_member_set_is_bound_to_the_committed_fixture_bytes(tmp_path):
    """A transcription error in the constant is the one failure the derivation cannot
    self-detect — it would simply have derived a different set. So the constant is checked
    against REAL BYTES, which is a stronger guard than the spec's test-owned literal copy
    (§7c's co-deletion residual) for a 31-token accented French vocabulary that no reviewer
    proofreads reliably.

    EXACT equality against the fixture's 2026 Quebec members fully determines the constant —
    membership, size and spelling in one comparison, so a SWAP (one required name out, the
    optional name in) reds here too, which neither a subset test nor a size test catches.
    That the frozen slice's partial 2026 happens to carry precisely the 31 is a byte-fact of
    a FROZEN fixture, not a claim that 2026 defines the set; 2025 is the subset case, adding
    the one optional member."""
    frame = _plant(tmp_path, _lines()).frame
    assert QUEBEC_REQUIRED_CMAS == _qc_members(frame, "2026")
    assert len(QUEBEC_REQUIRED_CMAS) == 31
    assert QUEBEC_REQUIRED_CMAS <= _qc_members(frame, "2025")
    assert len(_qc_members(frame, "2025") - QUEBEC_REQUIRED_CMAS) == 1


# --- The DISCRIMINATOR must discriminate: it earns its claim, or it hedges --------------
# Ruling U made the run log the only place a gutted feed can be told from a pre-era refusal,
# because the reason enum is spec-closed at `source_unavailable` for both. A line that stays
# SILENT on the worst truncation, or that asserts truncation on a state the publication
# CALENDAR explains, is not a discriminator — it is a second defect wearing the fix's name.


def _without_province_year(lines: list[str], province: str, year: str) -> list[str]:
    """Delete every row of one province-year — the MAXIMAL truncation, 100% of the members."""
    return [lines[0]] + [ln for ln in lines[1:]
                         if not (ln.split("\t")[_COL["EN_YEAR"]] == year
                                 and ln.split("\t")[_COL["EN_PROVINCE_TERRITORY"]] == province)]


def test_a_wholly_absent_member_set_is_named_not_read_as_pre_era_silence(tmp_path):
    """The truncation taken to its LIMIT: every Quebec row of the plan year gone. This is the
    worst instance of the state Ruling U required the log to NAME, and it is the one state a
    member-by-member note can miss — with no rows there is no member to call absent.

    It is DISTINGUISHABLE, and the frame carries the proof: the feed has published 2026 for
    other provinces. Pre-era means NOBODY has published the year; this is the year published
    with Quebec cut out of it. Reading the second as the first tells the operator to wait for
    data that has already arrived."""
    lines = _lines()
    gutted = _without_province_year(lines, QUEBEC_PROVINCE, "2026")
    others = [ln for ln in gutted[1:] if ln.split("\t")[_COL["EN_YEAR"]] == "2026"]
    assert others                                          # the feed HAS published 2026
    landings = _plant(tmp_path, gutted)
    assert _qc_members(landings.frame, "2026") == set()
    ev = evaluate_pr_landings(landings, band=BAND, now=(2026, 8))
    assert ev.result.status is Status.UNKNOWN and ev.result.reason is Reason.SOURCE_UNAVAILABLE
    assert exit_code([ev.result]) != 0
    assert_tripwire_record_valid(tripwire_record(ev.result))
    assert "member-set truncation" in ev.log.lower()
    assert f"{len(others)} rows for other provinces" in ev.log   # the evidence, in the line
    assert "cannot explain" in ev.log            # categorical, and here it is EARNED
    # ...and the same reason token on the INTACT feed in the same month must stay silent,
    # or the discriminator discriminates nothing.
    intact = evaluate_pr_landings(_plant(tmp_path, lines), band=BAND, now=(2026, 8))
    assert intact.result.reason is Reason.SOURCE_UNAVAILABLE     # same token, other cause
    assert "member-set truncation" not in intact.log.lower()


def test_an_intact_partial_year_reports_the_member_gap_without_claiming_its_cause(tmp_path):
    """The discriminator's other half, and the reason it may not assert CATEGORICALLY at a
    partial year: IRCC fills its member set over a year's first months. Derived from the
    committed 2025 bytes in this fixture — 24 of the 31 required members after Jan, 29 after
    Feb, 30 after Mar/Apr, 31 only from May. So a real vintage published through Jan shows
    members absent for a reason that is pure publication ORDER, and a line that calls that
    truncation is making a false claim about the feed.

    The gap is still REPORTED (silence would hide a truncation that arrived mid-year, which
    is the shape one would arrive in today); only the CAUSE is withheld. At twelve of twelve
    the calendar is exhausted and the categorical claim is earned — the contrast is asserted
    here so the two halves cannot drift apart."""
    lines = _lines()
    # The evidence for withholding the cause, RE-DERIVED from the committed bytes rather than
    # transcribed: a real, intact, untouched 2025 shows 7 required members still absent after
    # its first month. If a re-vintaged fixture ever made publication order instantaneous,
    # this reds and the hedge below has to be re-argued instead of silently outliving it.
    jan_2025 = {ln.split("\t")[_COL["EN_CENSUS_METROPOLITAN_AREA"]] for ln in lines[1:]
                if ln.split("\t")[_COL["EN_YEAR"]] == "2025"
                and ln.split("\t")[_COL["EN_MONTH"]] == "Jan"
                and ln.split("\t")[_COL["EN_PROVINCE_TERRITORY"]] == QUEBEC_PROVINCE}
    assert len(QUEBEC_REQUIRED_CMAS & jan_2025) == 24
    jan_only = [lines[0]] + [ln for ln in lines[1:]
                             if not (ln.split("\t")[_COL["EN_YEAR"]] == "2026"
                                     and ln.split("\t")[_COL["EN_MONTH"]] != "Jan")]
    partial = _plant(tmp_path, jan_only)
    assert len(QUEBEC_REQUIRED_CMAS - _qc_members(partial.frame, "2026")) == 1   # real bytes
    ev = evaluate_pr_landings(partial, band=BAND, now=(2026, 3))
    assert ev.result.status is Status.UNKNOWN and exit_code([ev.result]) != 0
    assert "1 of 31 required" in ev.log and "1 of 12 months" in ev.log   # the gap, reported
    assert "cannot explain" not in ev.log                               # the cause, withheld
    assert "publication-calendar gap" not in ev.log       # the shipped phrasing said exactly
    assert "cause is NOT claimed" in ev.log               # this, of exactly this state
    # The SAME member gap at a COMPLETE calendar: publication order is exhausted as an
    # explanation, so the categorical claim is earned there and only there.
    era = _relabel_year(lines, "2025", "2026")
    full = _plant(tmp_path, _without_member(era, "Saguenay"))
    log = evaluate_pr_landings(full, band=BAND, now=(2027, 3)).log
    assert "1 of 31 required" in log and "12 of 12 months" in log
    assert "cannot explain" in log and "cause is NOT claimed" not in log


# --- F2: value integrity was enforced on the value but not on its twin, the BAND --------

@pytest.mark.parametrize("band", [(math.nan, 50000.0), (40000.0, math.nan),
                                  (math.nan, math.nan), (40000.0, math.inf),
                                  (-math.inf, 50000.0), (math.inf, -math.inf)])
def test_a_non_finite_band_is_a_run_level_terminal(band):
    """A non-finite endpoint makes BOTH boundary comparisons False, so every value
    classifies as within-band: status=OK, exit 0 — verbatim the mechanism spec §7c names
    in words for the VALUE side ('naive comparisons classify NaN as inside every band').

    IT REFUSES AS A RUN-LEVEL TERMINAL, NOT AS AN UNKNOWN RECORD, and the shipped tree got
    that wrong in a way no test crossed (run-33 data gate F2). The UNKNOWN(`malformed_band`)
    record it built carried the offending ±Inf/NaN in `band_low`/`band_high`, and
    `assert_tripwire_record_valid` — the contract in this same module — REJECTED exactly
    that record: four of the five malformed-band sub-cases died with a bare serialization
    ValueError and NO baseline at all, where §7c wants that indicator UNKNOWN and the other
    five still evaluated.

    THE BAND IS THE CALLER'S, injected, so a non-finite band is a caller/config defect —
    deterministic, independent of the feed — which is the shape of a run-level terminal and
    not of a per-indicator UNKNOWN. The module already ruled the sibling case this way:
    `_band_endpoints` raises a named terminal for a NON-COERCIBLE endpoint because it
    "cannot ride the record's float-typed band fields", and under §7's `allow_nan=False` a
    non-finite endpoint cannot ride them either.

    THE FINITE INVERSION KEEPS ITS UNKNOWN(`malformed_band`) — it is serializable, it rides
    the record honestly, and `test_inverted_band_is_unknown` is where that stays pinned."""
    with pytest.raises(ValueError, match="finite"):
        evaluate_indicator(_spec(band_low=band[0], band_high=band[1]), 45000,
                           available=True, now=2026)
    # The terminal fires at the ENTRY of both producers, before availability is consulted —
    # the same door and the same ordering the non-coercible sibling already used.
    with pytest.raises(ValueError, match="finite"):
        evaluate_pr_landings(PRLandings(available=False, reason="n/a"), band=band,
                             now=(2027, 3))


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


def test_a_non_finite_number_can_never_ride_a_record():
    """The producer terminal above is one half; this is the CONTRACT half, and BOTH are
    needed. `json.dumps(..., allow_nan=False)` would discover a non-finite number only at
    emit time, and a record assembled anywhere other than `evaluate_indicator` never meets
    that terminal — so the validator binds the field itself, however the record was built.
    Every numeric position, and every non-finite value, not just the one pair the producer
    used to be able to reach."""
    rec = tripwire_record(evaluate_indicator(_spec(), 45000, available=True, now=2026))
    for field_name in ("current_value", "band_low", "band_high"):
        for bad in (math.nan, math.inf, -math.inf):
            with pytest.raises(ValueError, match="finite"):
                assert_tripwire_record_valid({**rec, field_name: bad})


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


def _restamp_year(lines: list[str], src: str, dst: str, drop_member: str | None = None) -> list[str]:
    """DATA rows of `src` re-stamped as `dst` (header excluded), optionally minus one member.
    Returned as rows to APPEND, so a caller can hold two plan-era years in one feed."""
    out = []
    for ln in lines[1:]:
        f = ln.split("\t")
        if f[_COL["EN_YEAR"]] != src:
            continue
        if drop_member is not None and f[_COL["EN_CENSUS_METROPOLITAN_AREA"]] == drop_member:
            continue
        f[_COL["EN_YEAR"]] = dst
        f[_COL["FR_ANNEÉ"]] = dst
        out.append("\t".join(f))
    return out


def test_a_later_year_losing_members_is_named_while_the_verdict_rides_the_honest_year(tmp_path):
    """THE THIRD UNCHECKED SIBLING of the discriminator's cause set, and it was silent.

    `_member_set_note` was wired into the empty-closed-years branch ALONE. So a feed with 2026
    CLOSED and 2027 truncated — twelve months published, one required member gone — reached a
    verdict on 2026 (`year = max(years)` selects the honest year, which is right) and said
    NOTHING about 2027 anywhere. The verdict is not at risk; the REPORT is. A reader learns the
    feed is losing members only once the loss reaches the evaluated year, which is a year late.

    Both arms below carry the same frame and differ only in `freshness_years`, because the
    bound that was doing the hiding is exactly the freshness gate: at the run's declared
    `freshness_years=1` the 2026 verdict is STALE by 2028, and a bound that holds only while
    another gate refuses is not a bound this module may rely on. Widen it and the run reaches a
    real OK/exit-0 verdict — with the 2027 truncation still named in the log."""
    era = _relabel_year(_lines(), "2025", "2026")
    dropped = "Saguenay"
    assert dropped in QUEBEC_REQUIRED_CMAS
    landings = _plant(tmp_path, era + _restamp_year(era, "2026", "2027", drop_member=dropped))
    assert landings.latest_period == (2027, 12)
    assert closed_plan_years(landings.frame) == [2026]          # 2027 fails the member set
    assert dropped not in _qc_members(landings.frame, "2027")

    wide = (55000.0, 65000.0)
    stale = evaluate_pr_landings(landings, band=wide, now=(2028, 3))
    assert stale.result.status is Status.UNKNOWN and stale.result.reason is Reason.STALE
    assert "member-set truncation" in stale.log.lower()

    verdict = evaluate_pr_landings(landings, band=wide, now=(2028, 3), freshness_years=2)
    assert verdict.result.status is Status.OK and verdict.result.reason is None
    assert verdict.result.as_of == 2026 and verdict.result.current_value == QC_2025_PROVINCE
    assert exit_code([verdict.result]) == 0                     # an honest year, honestly green
    assert "member-set truncation" in verdict.log.lower()       # ...and the gap still NAMED
    assert "2027: 1 of 31 required" in verdict.log
    assert "12 of 12 months" in verdict.log and "cannot explain" in verdict.log
    # the evaluated year itself is intact, so the note speaks about 2027 and not about 2026.
    assert "2026:" not in verdict.log.split("MEMBER-SET TRUNCATION SUSPECTED")[1]


def test_the_member_set_note_rides_every_branch_that_has_a_frame(tmp_path):
    """The invariant `evaluate_pr_landings`' docstring ASSERTS, pinned at every site it names.

    The note was computed once and appended to five returning branches, but only two of the
    five were reachable by any test: dropping `+ note` from the degenerate branch, the
    impossible-vintage branch, or the feed-staleness branch left the whole suite green. That
    is the diff's own defect class — behaviour with no crossing test — sitting inside the fix
    that introduced it, and a stated invariant no test defends decays branch by branch.

    Reason tokens CANNOT discriminate these branches and asserting on them would rebuild the
    passes-for-the-wrong-reason defect here: `source_unavailable` is emitted by the
    empty-years branch AND the degenerate one, and `stale` by the feed-staleness branch AND
    the generic gate on the verdict path. So each arm asserts the LOG HEAD that only its own
    branch writes. That also makes the arms honest about which gate they crossed: the two
    arms of `test_a_later_year_losing_members_is_named_while_the_verdict_rides_the_honest_year`
    LOOK like a stale/fresh pair, and both in fact return through the verdict path — 2027-12 is 3 months behind 2028-03, inside the 5-month feed limit, so the
    STALE there is the generic gate's, not this module's.

    ONE truncated 2027 rides every arm; what selects the branch is the state of 2026 and the
    `now` the run is asked about. The note must name 2027 in all five."""
    era = _relabel_year(_lines(), "2025", "2026")
    tail = _restamp_year(era, "2026", "2027", drop_member="Saguenay")   # 12/12 months, 30/31 members
    wide = (55000.0, 65000.0)

    def plant(name: str, lines: list[str]) -> PRLandings:
        d = tmp_path / name
        d.mkdir()
        return _plant(d, lines)

    # (arm, landings, kwargs, the log head ONLY that branch writes)
    arms = [
        ("no closed year", plant("a", [_lines()[0]] + tail),
         dict(now=(2028, 1)), "no CLOSED year in the plan era"),
        ("degenerate read", plant("b", _suppress(era, "2026", cma="Montréal") + tail),
         dict(now=(2028, 1)), "degenerate feed read"),
        ("impossible vintage", plant("c", era + tail),
         dict(now=(2027, 6)), "is AHEAD of"),
        ("feed stale", plant("d", era + tail),
         dict(now=(2029, 6)), "months behind"),
        ("verdict", plant("e", era + tail),
         dict(now=(2028, 3), freshness_years=2), "realized="),
    ]
    heads = set()
    for arm, landings, kwargs, head in arms:
        ev = evaluate_pr_landings(landings, band=wide, **kwargs)
        assert head in ev.log, f"{arm}: expected branch not taken — {ev.log[:120]}"
        assert "member-set truncation" in ev.log.lower(), f"{arm}: the note is NOT on this branch"
        assert "2027: 1 of 31 required" in ev.log, f"{arm}: the note names the wrong year"
        heads.add(ev.log.split("MEMBER-SET")[0])

    # ...and the arms are genuinely five DIFFERENT branches, not one branch reached five ways.
    assert len(heads) == len(arms)

    # LAST, never first: the loop above is what proves the note is ON each branch, and it is
    # the only thing that can — a count is blind to WHICH branch a note rides, and a count
    # checked ahead of the loop would swallow every drop-`+ note` mutant into one arity
    # failure that names no branch. Here it closes the remaining hole: the number of RETURNING
    # BRANCHES is read off the function rather than transcribed, so ANY sixth returning branch
    # reds this test — carrying the note or not, and the note-less one is the defect shape —
    # demanding an arm above or a recorded exemption. The `+ 1` IS the one exemption, and it
    # is exempt by construction: `not landings.available` returns BEFORE a frame exists, so it
    # has no member set to speak about and no note to carry.
    returns = inspect.getsource(evaluate_pr_landings).count("return PRLandingsEvaluation(")
    assert returns == len(arms) + 1


# =======================================================================================
# THE PRODUCER/CONTRACT SEAM, GENERALIZED (run-33: data F2, stress F3, stress F4)
# =======================================================================================
#
# THREE SEAMS IN THIS ONE MODULE IN THREE CONSECUTIVE ROUNDS, all the same shape: a producer
# builds a record its OWN contract validator refuses, nothing in the run reaches that branch
# today, and no test walks producer -> contract on the input that would. Amendment #16 closed
# `duplicate_indicator` one record at a time; `test_a_duplicate_record_from_the_producer_
# validates` is that crossing for that one branch.
#
# THIS IS THAT TEST GENERALIZED, and it is worth more than any of the three individual fixes:
# every record every producer in this module can emit, crossed into
# `assert_tripwire_record_valid` — with the reason and status coverage ASSERTED, so the
# property cannot quietly shrink to whichever branches happen to be reachable today. A new
# branch that emits a record the contract refuses reds here; a branch that stops being
# reachable reds the coverage assertion rather than silently narrowing the crossing.


def _generic_gate_records():
    """Every record `evaluate_indicator` can emit, labelled by the branch that built it."""
    string_band = dict(band_low="40000", band_high="50000")
    return [
        ("ok", evaluate_indicator(_spec(), 45000, available=True, now=2026)),
        ("crossed(low endpoint)", evaluate_indicator(_spec(), 40000, available=True, now=2026)),
        ("crossed(high endpoint)", evaluate_indicator(_spec(), 60000, available=True, now=2026)),
        ("stale", evaluate_indicator(_spec(as_of=2023), 45000, available=True, now=2026)),
        ("source_unavailable", evaluate_indicator(_spec(), None, available=False, now=2026)),
        ("operator_input_missing",
         evaluate_indicator(_spec(source_kind=SourceKind.OPERATOR_SUPPLIED), None,
                            available=True, now=2026)),
        ("non_finite(nan)", evaluate_indicator(_spec(), math.nan, available=True, now=2026)),
        ("non_finite(inf)", evaluate_indicator(_spec(), math.inf, available=True, now=2026)),
        ("non_finite(str)", evaluate_indicator(_spec(), "n/a", available=True, now=2026)),
        ("future_as_of", evaluate_indicator(_spec(as_of=2030), 45000, available=True, now=2026)),
        ("malformed_band(finite inversion)",
         evaluate_indicator(_spec(band_low=50000.0, band_high=40000.0), 45000,
                            available=True, now=2026)),
        # stress F4's input class: a COERCIBLE band endpoint. The verdict path coerced and
        # the record path re-read the RAW field, so these two rows are where the listing
        # path and the emit path used to disagree about the same input.
        ("coercible-string band, within",
         evaluate_indicator(_spec(**string_band), 45000, available=True, now=2026)),
        ("coercible-string band, crossed",
         evaluate_indicator(_spec(**string_band), 60000, available=True, now=2026)),
        ("coercible-string band, UNKNOWN branch",
         evaluate_indicator(_spec(**string_band), None, available=False, now=2026)),
        ("int band", evaluate_indicator(_spec(band_low=40000, band_high=50000), 45000,
                                        available=True, now=2026)),
    ]


def _registry_records():
    """Both completeness branches of `check_registry` — amendment #16's own seam, kept in
    the generalized property rather than left to the one-branch test that closed it."""
    dup = check_registry(sorted(REQUIRED_INDICATORS) + [PR_LANDINGS_INDICATOR])
    short = check_registry([PR_LANDINGS_INDICATOR])
    return ([("check_registry duplicate", r) for r in dup]
            + [("check_registry missing", r) for r in short])


def _fed_indicator_records(tmp_path):
    """Every RETURNING branch of `evaluate_pr_landings` — the third producer, and the only
    one whose records come off real feed bytes rather than a hand-built spec.

    The BRANCH CENSUS has one owner and it is not here:
    `test_the_member_set_note_rides_every_branch_that_has_a_frame` reads the returning-branch
    count off the function itself, so a new branch reds there and sends a reader back to both
    arm lists. Transcribing that count a second time would be two facts where there is one."""
    era = _relabel_year(_lines(), "2025", "2026")
    wide = (55000.0, 65000.0)

    def plant(name, lines):
        d = tmp_path / name
        d.mkdir()
        return _plant(d, lines)

    arms = [
        ("pr feed absent", PRLandings(available=False, reason="not found"), BAND, dict(now=(2027, 3))),
        ("pr no closed year", plant("a", _lines()), BAND, dict(now=(2026, 8))),
        ("pr degenerate read", plant("b", _suppress(era, "2026", cma="Montréal")), BAND,
         dict(now=(2027, 1))),
        ("pr impossible vintage", plant("c", era), BAND, dict(now=(2026, 1))),
        ("pr feed stale", plant("d", era), BAND, dict(now=(2028, 6))),
        ("pr verdict CROSSED", plant("e", era), BAND, dict(now=(2027, 3))),
        ("pr verdict OK", plant("f", era), wide, dict(now=(2027, 3))),
    ]
    return [(label, evaluate_pr_landings(landings, band=band, **kw).result)
            for label, landings, band, kw in arms]


@pytest.fixture(scope="module")
def producible(tmp_path_factory):
    """(label, TripwireResult) for EVERY record this module's three producers can emit.

    Module-scoped: `_fed_indicator_records` plants seven real feed slices through the real
    loader, and the properties below all range over the same set."""
    return (_generic_gate_records() + _registry_records()
            + _fed_indicator_records(tmp_path_factory.mktemp("seam")))


def test_every_record_a_producer_can_emit_validates(producible):
    """THE CROSSING. Three producers, every reachable branch, one contract validator.

    This is the test shape that would have caught all three of this arc's seams — the
    `duplicate_indicator` nullability disagreement (amendment #16), the non-finite band the
    contract refused while the producer emitted it (data F2), and the coercible-string band
    that verdicted GREEN on the listing path while crashing on the emit path (stress F4).
    Each was latent on the committed tree for the SAME reason: a property of today's
    callers, not of the contract."""
    assert producible
    rejected = []
    for label, r in producible:
        try:
            assert_tripwire_record_valid(tripwire_record(r))
        except ValueError as exc:
            rejected.append(f"  [{label}] {exc}")
    # EVERY failing sub-case, not the first: a seam usually opens across a whole branch
    # class (four of five malformed-band sub-cases, in data F2's), and a report that stops
    # at one of them understates what has to be fixed.
    assert not rejected, ("the contract REJECTS records its own producers built:\n"
                          + "\n".join(rejected))


def test_the_producers_reach_every_state_the_closed_enums_declare(producible):
    """What makes the crossing a PROPERTY rather than a spot check. Without this, deleting a
    branch from the census above would narrow the crossing silently — the failure mode the
    three seams all shared, one level up."""
    assert {r.reason for _, r in producible if r.reason is not None} == set(Reason)
    assert {r.status for _, r in producible} == set(Status)


def test_nullable_reasons_is_exactly_the_set_the_producers_null(producible):
    """stress F3: `NULLABLE_REASONS` is a spec-closed enumeration with NO exact-membership
    pin — `Reason.STALE` and `Reason.MALFORMED_BAND` could each be ADDED and the whole suite
    still passed. A widened set reintroduces amendment #16's seam in the OPPOSITE direction:
    `_unknown_measured` RETAINS current_value and as_of, so the validator's nullability
    branch would reject the record its own module just built — CI-green, and live the first
    time a real indicator value lands.

    PINNED AS A PROPERTY OVER THE PRODUCERS, not as a fourth frozenset copy (which would
    pass under any widening applied to both halves): the set of reasons under which a
    producer emits NULLs must EQUAL `NULLABLE_REASONS`, and no value-retaining reason may be
    in it. Drop-one is already pinned by the crossing above; this pins the widening."""
    unknowns = [r for _, r in producible if r.status is Status.UNKNOWN]
    nulled = {r.reason for r in unknowns if r.current_value is None}
    valued = {r.reason for r in unknowns if r.current_value is not None}
    assert nulled == set(NULLABLE_REASONS)
    assert not (valued & set(NULLABLE_REASONS))
    # current_value and as_of null TOGETHER or not at all — the contract reads them as one
    # branch, so a producer that split them would satisfy the two set assertions above.
    for label, r in producible:
        assert (r.current_value is None) == (r.as_of is None), label


def test_a_coercible_band_endpoint_never_rides_the_record_raw(producible):
    """stress F4, THE CHEAP-GREEN HALF OF THE SEAM. `_band_endpoints` COERCED the caller's
    band and returned floats, but every `TripwireResult` constructor re-read the RAW
    `spec.band_low`/`spec.band_high` — so `("40000", "50000")` verdicted OK on the
    `demoflow tripwires` path (six OK, exit 0) while the emit path CRASHED on the record
    that same producer built. Two verification paths disagreeing about one input, and the
    GREEN one is the cheap one. The spec is rebuilt from the coerced endpoints, which is
    what `evaluate_pr_landings` already did with its `year_spec`."""
    for label, r in producible:
        for endpoint in (r.band_low, r.band_high):
            assert isinstance(endpoint, float) and not isinstance(endpoint, bool), label
    string_band = evaluate_indicator(_spec(band_low="40000", band_high="50000"), 45000,
                                     available=True, now=2026)
    assert string_band.status is Status.OK and exit_code([string_band]) == 0   # listing path
    assert string_band.band_low == 40000.0 and string_band.band_high == 50000.0
    assert_tripwire_record_valid(tripwire_record(string_band))                 # emit path
