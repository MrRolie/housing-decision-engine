"""P7 gates — does the committed note EARN its closed-cohort verdict (spec §5 r3-F2, ruling K)?

The verdict vocabulary ruling K fixes is TWO-VALUED on the evidenced side, plus the honest
refusal. Both evidenced values must be REACHABLE, or the gate below is watching a constant:

  PASS iff the note records EITHER
    (a) EVIDENCED-WITH-NAMED-EXCEEDANCE carrying EVERY evidence token — the full published
        span, the coverage split (including the NOT-COVERED member, which ruling K names),
        the exact-identity result, the maximum rate with its geography and period, the
        tripwire count, the window contrast, and the operator resolution — each INDEPENDENTLY
        gated, plus the named-exceedance TABLE whose rows must actually exceed the tripwire
        and must agree with the per-geography counts printed above them; OR
    (b) EVIDENCED-NO-EXCEEDANCE carrying the same evidence with a zero tripwire count; OR
    (c) UNKNOWN-PROBE-FAILED with a recorded reason AND boundary.
  FAIL on an unresolved `[FILL`, a verdict missing any evidence, tokens that contradict each
    other, or a recorded failure whose exception type is a code fault (a `ProbeRefusal` is a
    floor guard firing — it must redden the suite, never launder into a skip).
  SKIP-with-reason ONLY when the recorded failure is network-class AND the boundary's host is
    independently confirmed unreachable — probed with the SAME HTTP method run_p7.py uses
    against that host (POST; `getCubeMetadata` rejects GET, so a GET liveness check reports a
    healthy service as down and turns every recorded failure into a false all-clear).

  The green path is OFFLINE — it reads the committed note. Only the failure branch probes
  reachability, and only to decide fail-vs-skip. Every mutation test is OFFLINE too.

  test_p7_no_unfilled_placeholder          -> the fabrication surface stays closed
  test_p7_records_a_resolved_verdict       -> the load-bearing RULING-2 / ruling-K gate
  test_p7_cited_figures_travel_both_paths  -> the dual-path citation gate
  test_p7_floor_guard_earns_verdict        -> the floor guards are load-bearing (mutation test)
  test_p7_both_evidenced_verdicts_reachable-> the verdict is not a constant
  test_p7_tripwire_is_falsifiable          -> the threshold really decides
  test_p7_age_bands_resolved_by_name_not_by_a_shared_id_table
                                           -> the denominator is the right age band
  test_p7_note_states_only_per_cube_quantities_it_measured
                                           -> §2a/§2c prose carries MEASURED per-cube figures
  test_p7_compo_boundary_failure_is_not_a_skip -> a local fault never reads as an outage

  This index is the file's map and NO test reads it, so a gate added without a row here is
  invisible to a green suite — both entries above the compo line were added after a review
  found them missing. (The "Gate N" numbers in the docstrings below are NOT a sequence: two
  distinct tests already label themselves Gate 7. Read the names, not the numbers.)
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from ._probe_asserts import (
    NETWORK_EXCEPTIONS,
    recorded_failure_type as _recorded_failure_type,
    source_reachable,
    token as _token,
)

NOTE = Path(__file__).resolve().parent.parent / "probes" / "closed-cohort-migration.md"

# run_p7.py reaches exactly one host, and it reaches it by POST. `getCubeMetadata` rejects
# GET, so a GET liveness check here would report a perfectly healthy StatCan as unreachable
# and launder every recorded failure into `pytest.skip` — the cardinal cheap all-clear.
# (test_probe_contracts.py enforces that this method matches the probe's own.)
WDS_LIVENESS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
LIVENESS_PID = 17100149
REACHABILITY_TIMEOUT = 10

# "NOT-FOUND" is absent because run_p7.py has no such verdict — an absence is not one of the
# outcomes this measurement can produce. "NONE" is present: no token here legitimately reads
# "none", so accepting it would let an unresolved slot pass as an answer.
UNRESOLVED = {"", "UNKNOWN-PROBE-FAILED", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL", "[FILL]",
              "N/A", "NONE", "?"}

BOUNDARIES = ("wds-meta", "wds-data", "compo-workbook")
EVIDENCED = {"EVIDENCED-WITH-NAMED-EXCEEDANCE", "EVIDENCED-NO-EXCEEDANCE"}


def _note_text() -> str:
    assert NOTE.exists(), f"{NOTE} is missing — run `uv run python probes/run_p7.py` first"
    return NOTE.read_text(encoding="utf-8")


def _recorded_failure_boundary(text: str) -> str | None:
    found = re.search(rf"LIVE PROBE FAILED-AT:\s*({'|'.join(BOUNDARIES)})", text)
    return found.group(1) if found else None


def _source_reachable() -> bool:
    """Cheap POST liveness probe against the one host run_p7.py reaches. Any exception = down."""
    return source_reachable(
        WDS_LIVENESS,
        timeout=REACHABILITY_TIMEOUT,
        method="POST",
        data=json.dumps([{"productId": LIVENESS_PID}]).encode(),
        headers={"Content-Type": "application/json"},
    )


def _fail_or_skip_on_recorded_failure(text: str) -> None:
    """Failure-branch policy for UNKNOWN-PROBE-FAILED. Never a silent pass."""
    if "LIVE PROBE FAILED" not in text:
        pytest.fail(f"{NOTE} records UNKNOWN-PROBE-FAILED but no `LIVE PROBE FAILED` reason — "
                    f"an unexplained UNKNOWN is not a recorded observation. Re-run run_p7.py.")
    recorded = _recorded_failure_type(text)
    if recorded is None:
        pytest.fail(f"{NOTE} records LIVE PROBE FAILED with no parseable exception type.")
    if recorded not in NETWORK_EXCEPTIONS:
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED: {recorded} — a code fault or a floor-guard "
            f"refusal (`ProbeRefusal`), not a network outage, so an unreachable source does "
            f"not excuse it. Re-run run_p7.py.")
    boundary = _recorded_failure_boundary(text)
    if boundary is None:
        pytest.fail(f"{NOTE} records LIVE PROBE FAILED with no parseable `LIVE PROBE FAILED-AT` "
                    f"boundary (expected one of {BOUNDARIES}).")
    if boundary == "compo-workbook":
        pytest.fail(f"{NOTE} attributes its failure to the LOCAL compo workbook, which no "
                    f"network outage can excuse. Re-run run_p7.py.")
    if _source_reachable():
        pytest.fail(f"{NOTE} records LIVE PROBE FAILED ({recorded}) at '{boundary}' while "
                    f"www150.statcan.gc.ca answers — the probe is broken, not the source.")
    pytest.skip(f"{NOTE} records a network-class failure ({recorded}) at '{boundary}', "
                f"independently confirmed unreachable — the measurement is genuinely "
                f"unrecordable here, NOT a pass.")


# ---------------------------------------------------------------------------
# Gate 1 — the fabrication surface stays closed.
# ---------------------------------------------------------------------------
def test_p7_no_unfilled_placeholder():
    """run_p7.py refuses to write a surviving `[FILL`; this is the committed-artifact half."""
    assert "[FILL" not in _note_text(), (
        f"{NOTE} carries an unresolved `[FILL` placeholder — the note must be GENERATED by "
        f"probes/run_p7.py, never hand-filled. Re-run: uv run python probes/run_p7.py")


# ---------------------------------------------------------------------------
# Gate 2 — the RULING-2 outcome gate over ruling K's vocabulary.
# ---------------------------------------------------------------------------
def _pct(token_text: str) -> float:
    found = re.search(r"(-?\d+(?:\.\d+)?)\s*%/yr", token_text or "")
    assert found, f"no percent-per-year figure in {token_text!r}"
    return float(found.group(1))


def test_p7_records_a_resolved_verdict():
    """Gate 2 — every evidence token asserted INDEPENDENTLY, then cross-checked.

    A verdict that resolved the span but left the identity, the coverage or the tripwire count
    bare must FAIL here rather than pass on the strength of its neighbours; and a token that
    contradicts the table printed under it is the defect this probe family keeps
    reintroducing beside correctly-computed values.
    """
    text = _note_text()
    verdict = _token(text, "DECISION-VERDICT")
    assert verdict in EVIDENCED | {"UNKNOWN-PROBE-FAILED"}, (
        f"{NOTE} records no resolved `DECISION-VERDICT` (got {verdict!r}). Ruling K's forms "
        f"are {sorted(EVIDENCED)} or an honest UNKNOWN-PROBE-FAILED.")

    if verdict == "UNKNOWN-PROBE-FAILED":
        _fail_or_skip_on_recorded_failure(text)     # -> fail (bad) or skip (confirmed outage)
        return

    # --- span: the FULL published span, stated with its period count ------------------
    span = _token(text, "DECISION-SPAN")
    assert span is not None and span.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-SPAN` ({span!r}).")
    periods = re.search(r"(\d+) periods", span)
    assert periods and int(periods.group(1)) > 1, (
        f"{NOTE}'s DECISION-SPAN states no plural period count: {span!r}. Ruling K evaluates "
        f"the tripwire on the FULL published span; a one-period 'span' is the window it "
        f"refuses, wearing the word 'span'.")
    assert "FULL published span" in span, (
        f"{NOTE}'s DECISION-SPAN no longer claims the full published span: {span!r}")

    # --- coverage: measured + NOT-COVERED must account for every modeled geography ----
    coverage = _token(text, "DECISION-COVERAGE")
    assert coverage is not None and coverage.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-COVERAGE` ({coverage!r}).")
    split = re.search(r"(\d+) of (\d+) modeled geographies MEASURED, (\d+) NOT-COVERED",
                      coverage)
    assert split, (
        f"{NOTE}'s DECISION-COVERAGE states no measured/NOT-COVERED split: {coverage!r}. "
        f"Ruling K requires HORS_RMR recorded NOT-COVERED, never approximated — and an "
        f"unevaluated geography must not be countable as a passing one.")
    measured, modeled, uncovered = (int(g) for g in split.groups())
    assert measured > 0 and measured + uncovered == modeled, (
        f"{NOTE}'s DECISION-COVERAGE does not account for every modeled geography: "
        f"{coverage!r} ({measured} + {uncovered} != {modeled}).")
    assert "HORS_RMR" in coverage, (
        f"{NOTE}'s DECISION-COVERAGE does not name HORS_RMR as the NOT-COVERED member, which "
        f"is what ruling K requires recorded: {coverage!r}")
    assert re.search(r"^\| HORS_RMR \|.*\*\*NOT-COVERED\*\*", text, re.M), (
        f"{NOTE}'s per-geography table carries no HORS_RMR NOT-COVERED row — the decision "
        f"line claims a coverage split the table never shows.")

    # --- identity: the alignment guard's result, EXACT ---------------------------------
    identity = _token(text, "DECISION-IDENTITY")
    assert identity is not None and identity.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-IDENTITY` ({identity!r}).")
    assert identity.startswith("EXACT"), (
        f"{NOTE}'s DECISION-IDENTITY is {identity!r} — a measurement whose own accounting "
        f"identity did not close exactly is not evidence about anything.")
    difference = re.search(r"max \|difference\| (\d+)", identity)
    assert difference and int(difference.group(1)) == 0, (
        f"{NOTE} claims EXACT while printing a non-zero difference: {identity!r}")

    # --- the maximum rate, and where it is -------------------------------------------
    max_rate = _token(text, "DECISION-MAX-RATE")
    assert max_rate is not None and max_rate.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-MAX-RATE` ({max_rate!r}).")
    peak = re.match(r"^(\d+\.\d+) %/yr at (\S+) (\d{4}/\d{2})$", max_rate.strip())
    assert peak, (
        f"{NOTE}'s DECISION-MAX-RATE does not state a rate WITH the geography and period it "
        f"occurs at: {max_rate!r}. A maximum with no location cannot be checked against the "
        f"table under it.")
    peak_rate, peak_geography, peak_period = float(peak.group(1)), peak.group(2), peak.group(3)
    peak_row = re.search(rf"^\| {re.escape(peak_geography)} \|.*\| {re.escape(peak_period)} \|",
                         text, re.M)
    assert peak_row, (
        f"{NOTE}'s DECISION-MAX-RATE points at {peak_geography} {peak_period}, which has no "
        f"row in the per-geography table — the decision line and the evidence disagree.")

    # --- the tripwire count, and its agreement with the table -------------------------
    tripwire = _token(text, "DECISION-TRIPWIRE")
    assert tripwire is not None and tripwire.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-TRIPWIRE` ({tripwire!r}).")
    fired = tripwire.startswith("FIRED")
    assert fired or tripwire.startswith("NOT FIRED"), (
        f"{NOTE}'s DECISION-TRIPWIRE resolves to neither FIRED nor NOT FIRED: {tripwire!r}")
    count = re.search(r"— (\d+) geography-period\(s\) above", tripwire)
    assert count, f"{NOTE}'s DECISION-TRIPWIRE states no exceedance count: {tripwire!r}"
    n_exceed = int(count.group(1))
    assert fired == (verdict == "EVIDENCED-WITH-NAMED-EXCEEDANCE"), (
        f"{NOTE}'s verdict {verdict!r} disagrees with its own tripwire line {tripwire!r} — one "
        f"of the two is not computed from the measurement.")
    assert fired == (n_exceed > 0), (
        f"{NOTE}'s DECISION-TRIPWIRE says {'FIRED' if fired else 'NOT FIRED'} while counting "
        f"{n_exceed} exceedances — the gloss contradicts the number beside it: {tripwire!r}")
    threshold = _pct(tripwire)
    assert threshold > 0, f"{NOTE} states a non-positive tripwire: {tripwire!r}"
    assert "[cited:" in tripwire, (
        f"{NOTE}'s tripwire level is printed without its source: {tripwire!r}. It is a SPEC "
        f"quantity this run did not compute, so it must travel cited.")

    # The per-geography `n > tripwire` column must sum to the decision line's count.
    per_geography = [int(row) for row in
                     re.findall(r"^\|\s*\S+\s*\|.*\|\s*\d{4}/\d{2}\s*\|\s*(\d+)\s*\|$",
                                text, re.M)]
    assert per_geography, f"{NOTE} has no readable per-geography exceedance-count column"
    assert sum(per_geography) == n_exceed, (
        f"{NOTE}'s per-geography exceedance counts sum to {sum(per_geography)} but the "
        f"decision line claims {n_exceed} — a summary that contradicts its own table.")

    # --- the window contrast: recorded, and the full span must win --------------------
    window = _token(text, "DECISION-WINDOW-CONTRAST")
    assert window is not None and window.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-WINDOW-CONTRAST` ({window!r}). Ruling K requires the "
        f"refused window to be RECORDED — an unrecorded window cannot be shown to have been "
        f"refused rather than never considered.")
    both = re.findall(r"(\d+\.\d+) %/yr", window)
    assert len(both) == 2, f"{NOTE}'s window contrast prints no two rates: {window!r}"
    latest_max, full_max = float(both[0]), float(both[1])
    assert full_max == peak_rate, (
        f"{NOTE}'s window contrast quotes a full-span max of {full_max} while DECISION-MAX-RATE "
        f"says {peak_rate} — two numbers for one measured quantity.")
    assert latest_max <= full_max, (
        f"{NOTE} reports a latest-window max ({latest_max}) ABOVE the full-span max "
        f"({full_max}), which is arithmetically impossible for a subset: {window!r}")
    assert "FULL SPAN rules" in window, (
        f"{NOTE}'s window contrast no longer records which span governs: {window!r}")

    # --- the operator resolution, cited -----------------------------------------------
    resolution = _token(text, "DECISION-RESOLUTION")
    assert resolution is not None and resolution.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-RESOLUTION` ({resolution!r}).")
    assert "[cited:" in resolution and "RULING K" in resolution.upper(), (
        f"{NOTE}'s DECISION-RESOLUTION does not travel cited to steering ruling K: "
        f"{resolution!r}. The resolution is an OPERATOR ruling this run did not compute; "
        f"printing it as a derived figure would attribute a decision to a measurement.")

    if not fired:
        return

    # --- a FIRED verdict must NAME its exceedances, and they must really exceed --------
    rows = re.findall(r"^\| (\S+) \| (\d{4}/\d{2}) \| ([+-][\d,]+) \| ([\d,]+) \| \*\*(\d+\.\d+)\*\* \|$",
                      text, re.M)
    assert len(rows) == n_exceed, (
        f"{NOTE} claims {n_exceed} exceedance(s) but names {len(rows)} in its table — "
        f"EVIDENCED-WITH-NAMED-EXCEEDANCE means every one of them is NAMED.")
    for geography, period, net, population, rate in rows:
        value = float(rate)
        assert value > threshold, (
            f"{NOTE} names {geography} {period} as an exceedance at {value} %/yr, which does "
            f"not exceed the {threshold} %/yr tripwire it is listed under.")
        # The rate must be the quotient the note says it is, not a number printed beside two
        # others: |net| / population x 100, to the precision the table prints.
        recomputed = abs(float(net.replace(",", ""))) / float(population.replace(",", "")) * 100
        assert round(recomputed, 4) == value, (
            f"{NOTE}'s row {geography} {period} prints rate {value} but |{net}| / {population} "
            f"x 100 = {recomputed:.4f} — the rate does not follow from the operands beside it.")
    assert max(float(row[4]) for row in rows) == peak_rate, (
        f"{NOTE}'s named exceedances top out below its own DECISION-MAX-RATE {peak_rate}.")


# ---------------------------------------------------------------------------
# Gate 3 — the dual-path citation gate.
# ---------------------------------------------------------------------------
def test_p7_cited_figures_travel_both_paths():
    """Every externally-cited figure must appear on BOTH paths: the provenance header's cited
    list AND, with its source attached, in the body that uses it.

    Either path alone is escapable. A cited figure listed only in the header is a source
    credited for nothing; a figure quoted only in the body is an external number wearing the
    note's own authority. `Fact.__str__` renders the `value [cited: source]` form, so a body
    occurrence without the bracket is a figure that lost its provenance on the way in.
    """
    text = _note_text()
    if _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED":
        pytest.skip("the failure branch registers no cited figures")
    label = "Externally cited figures (NOT computed by this run):"
    assert label in text, f"{NOTE} carries no cited block ({label!r})"
    block = text.split(label, 1)[1].split("\n\n", 1)[0]
    entries = re.findall(r"^- (.+?) — (.+)$", block, re.M)
    assert entries, f"{NOTE}'s cited block lists nothing: {block!r}"
    body = text.split(label, 1)[1].split("\n\n", 1)[1]
    for value, source in entries:
        assert f"{value} [cited: {source}]" in body, (
            f"{NOTE} lists {value!r} (source {source!r}) in its provenance header but the body "
            f"never uses it in the cited form — a source credited for a figure the note does "
            f"not actually carry, or a figure that lost its provenance.")


# ---------------------------------------------------------------------------
# Gates 4-7 — the offline mutation / reachability suite.
# ---------------------------------------------------------------------------
def _load_run_p7():
    """Load `probes/run_p7.py` as a fresh module (probes/ is not an importable package).

    The `sys.path` insert is load-bearing: run_p7.py imports `_wds` FLAT, and
    `spec_from_file_location` does not put the file's directory on the path.
    """
    probes_dir = str(NOTE.parent)
    if probes_dir not in sys.path:
        sys.path.insert(0, probes_dir)
    spec = importlib.util.spec_from_file_location("run_p7_under_test", NOTE.parent / "run_p7.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_COMPONENT_IDS = {"Births": 1, "Deaths": 2, "Immigrants": 3, "Net emigration": 4,
                  "Emigrants": 5, "Returning emigrants": 6, "Net temporary emigration": 7,
                  "Net interprovincial migration": 8, "Net intraprovincial migration": 9,
                  "Net non-permanent residents": 10, "Residual deviation": 11}
# The live cubes' STRUCTURE, reproduced; their live id VALUES, deliberately NOT. The same age
# band sits one id apart across the two families (components 114 age members, population 115),
# and that offset is the whole point — a probe resolving the population bands with the
# components ids would read one band's migration against another band's population. So the
# offset is preserved exactly, and the values are then displaced by a uniform +200, clear of
# every id these cubes can publish. Without that displacement the fixture would seat the LIVE
# ids, a hardcoded literal in the note generator would print the fixture's number too, and
# §2a's id assertion would be watching a constant — the trap the age-member COUNTS already
# avoid by publishing 5 and 9 here against 114 and 115 live.
_LIVE_AGE_ID_CEILING = 115  # MEASURED 2026-08-08: all four cubes' Age group dimension, max id
_COMPONENT_AGE_IDS = {"All ages": 201, "75 to 79 years": 293, "80 to 84 years": 299,
                      "85 to 89 years": 305, "90 years and older": 311}
_POPULATION_AGE_IDS = {"All ages": 201, "75 to 79 years": 292, "80 to 84 years": 298,
                       "85 to 89 years": 304, "90 years and older": 310,
                       # DECOYS, and they are the whole point: in the live population cubes
                       # EVERY components-cube band id is a real member under another name
                       # (MEASURED 2026-08-08 on 17-10-0148-01 and 17-10-0150-01: 93 is
                       # `75 years`, 99 `80 years`, 105 `85 years`, 111 `0 to 14 years`). So a
                       # shared hardcoded id table does not fail loudly — it resolves, to the
                       # wrong denominator. Modeled here as four SMALL members so the
                       # fabricated quotient is visibly INFLATED offline; live the fourth is a
                       # large band, so the live distortion's DIRECTION is not what this
                       # fixture shows — only that name resolution is what prevents it. Without
                       # these the misuse would be untestable, and the module docstring's
                       # central safety claim would rest on nothing.
                       "75 years": 293, "80 years": 299, "85 years": 305, "90 years": 311}
_COMPONENT_BAND_IDS = {band: _COMPONENT_AGE_IDS[band]
                       for band in ("75 to 79 years", "80 to 84 years", "85 to 89 years",
                                    "90 years and older")}
_GENDERS = (("Total - gender", 1), ("Men+", 2), ("Women+", 3))

# All-ages components, constant. `Residual deviation` is DERIVED per year so the accounting
# identity closes exactly against the population path below — the same way the live cubes do.
_ALL_AGE_COMPONENTS = {"Births": 1000.0, "Deaths": 800.0, "Immigrants": 500.0,
                       "Net emigration": 50.0, "Emigrants": 0.0, "Returning emigrants": 0.0,
                       "Net temporary emigration": 0.0,
                       "Net interprovincial migration": -20.0,
                       "Net intraprovincial migration": 30.0,
                       "Net non-permanent residents": 10.0}
_FIRST_YEAR = 2001


def _all_age_population(year: int) -> float:
    """A deliberately NON-LINEAR population path.

    Linear would make the period-shift mutation invisible: a constant year-over-year change
    survives being shifted by one period, so the identity would still close and the guard
    would grade as dead when it is not.
    """
    step = year - _FIRST_YEAR
    return 100_000.0 + 700.0 * step + 13.0 * step * step


def _quiet(tag: str, year: str) -> float:
    return 0.5


def _one_exceedance(tag: str, year: str) -> float:
    """0.5 %/yr everywhere except one geography-period, which clears the 1 %/yr tripwire."""
    return 1.5 if (tag == "LAVAL_RA13" and year == "2007") else 0.5


def _steep_pop75(tag: str, year: str) -> float:
    """A 75+ population that triples after 2007 — so shifting the denominator by one period
    divides the 2007 rate by three, which is what turns the identity mutation into a visibly
    FABRICATED no-exceedance rather than a slightly different number."""
    return 20_000.0 if int(year) <= 2007 else 60_000.0


def _flat_pop75(tag: str, year: str) -> float:
    return 20_000.0


class _Cubes:
    """A complete offline stand-in for the four StatCan cubes.

    Every knob below exists to drive ONE guard's refusal branch, and the honest (no-knob)
    fixture must reach a real verdict — otherwise the mutations prove nothing about the
    guards and everything about a broken fixture.
    """

    def __init__(self, mod, *, rate=_one_exceedance, pop75=_flat_pop75,
                 keep_periods=None, null_migration=False, drop_series=0,
                 meta_status="SUCCESS", population_shift=0):
        self.mod = mod
        self.rate, self.pop75 = rate, pop75
        self.keep_periods = keep_periods
        self.null_migration = null_migration
        self.drop_series = drop_series
        self.meta_status = meta_status
        self.population_shift = population_shift
        # ALWAYS the module's full declared set, captured before any test patches it: the
        # cubes publish what StatCan publishes. Narrowing the fixture alongside the probe's
        # declaration would make the coverage mutation fail for the wrong reason — the member
        # would be missing from the SOURCE rather than dropped by the probe.
        self.sources = tuple(mod.GEOGRAPHY_SOURCES)
        self.metas = self._build_metas()

    # -- metadata ---------------------------------------------------------------
    def _geo_members(self, pid: int, offset: int) -> list:
        members, seen = [], []
        for source in self.sources:
            if pid in (source.components_pid, source.population_pid) \
                    and source.member_name not in seen:
                seen.append(source.member_name)
                members.append({"memberId": offset + len(members),
                                "memberNameEn": source.member_name,
                                "classificationCode": source.declared_class})
        return members

    def _build_metas(self) -> dict:
        mod = self.mod

        def named(mapping):
            return [{"memberId": mid, "memberNameEn": name} for name, mid in mapping.items()]

        metas = {}
        for pid in (mod.COMPONENTS_CMA_PID, mod.COMPONENTS_ER_PID):
            metas[pid] = {
                "productId": pid, "cubeTitleEn": f"Components fixture {pid}",
                "cubeStartDate": "2001-01-01", "cubeEndDate": "2024-01-01",
                "releaseTime": "2026-01-14T08:30",
                "dimension": [
                    {"dimensionPositionId": 1, "member": self._geo_members(pid, 1)},
                    {"dimensionPositionId": 2, "member": named(_COMPONENT_IDS)},
                    {"dimensionPositionId": 3,
                     "member": [{"memberId": i, "memberNameEn": n} for n, i in _GENDERS]},
                    {"dimensionPositionId": 4, "member": named(_COMPONENT_AGE_IDS)},
                ]}
        for pid in (mod.POPULATION_CMA_PID, mod.POPULATION_ER_PID):
            # Geography ids deliberately OFFSET from the components cubes': reusing a
            # components geography id against a population cube must not accidentally work.
            metas[pid] = {
                "productId": pid, "cubeTitleEn": f"Population fixture {pid}",
                "cubeStartDate": "2001-01-01", "cubeEndDate": "2025-01-01",
                "releaseTime": "2026-01-14T08:30",
                "dimension": [
                    {"dimensionPositionId": 1, "member": self._geo_members(pid, 41)},
                    {"dimensionPositionId": 2,
                     "member": [{"memberId": i, "memberNameEn": n} for n, i in _GENDERS]},
                    {"dimensionPositionId": 3, "member": named(_POPULATION_AGE_IDS)},
                ]}
        return metas

    def meta(self, pids) -> list:
        return [{"status": self.meta_status, "object": self.metas[pid]} for pid in pids]

    # -- data -------------------------------------------------------------------
    def _name_at(self, pid: int, position: int, member_id: int) -> str:
        dim = next(d for d in self.metas[pid]["dimension"]
                   if d["dimensionPositionId"] == position)
        return next(m["memberNameEn"] for m in dim["member"] if m["memberId"] == member_id)

    def _tag_of(self, member_name: str) -> str:
        return next(s.tag for s in self.sources if s.member_name == member_name)

    def _years(self, pid: int) -> list:
        components = pid in (self.mod.COMPONENTS_CMA_PID, self.mod.COMPONENTS_ER_PID)
        years = [str(y) for y in range(_FIRST_YEAR, (2024 if components else 2025) + 1)]
        if not self.keep_periods:
            return years
        # The population window keeps ONE period more than the components window — the same
        # +1 relation the real cubes carry, because a start-of-period denominator needs the
        # following July-1 count. Truncating both to the same length would make the identity
        # guard refuse for a missing denominator, and the span mutation would then "prove"
        # `_guard_span` load-bearing on a failure it had nothing to do with.
        return years[:self.keep_periods + (0 if components else 1)]

    def _component_value(self, tag: str, component: str, age: str, year: str):
        if age == "All ages":
            if component != "Residual deviation":
                return _ALL_AGE_COMPONENTS[component]
            change = _all_age_population(int(year) + 1) - _all_age_population(int(year))
            named_sum = sum(sign * _ALL_AGE_COMPONENTS[name]
                            for name, sign in self.mod.IDENTITY_COMPONENTS.items())
            return change - named_sum
        if self.null_migration:
            return None
        if component != "Immigrants":
            return 0.0
        return self.rate(tag, year) * self.pop75(tag, year) / 100.0 / 4.0

    def _population_value(self, tag: str, age: str, year: str) -> float:
        effective = str(int(year) + self.population_shift)
        if age == "All ages":
            return _all_age_population(int(effective))
        band = self.pop75(tag, effective) / 4.0
        # A decoy single-year member holds roughly a fifth of its five-year band.
        return band if age in self.mod.BANDS_75_PLUS else band / 5.0

    def data(self, requests: list) -> list:
        mod = self.mod
        out = []
        for request in requests:
            pid = request["productId"]
            ids = [int(part) for part in request["coordinate"].split(".")]
            tag = self._tag_of(self._name_at(pid, 1, ids[0]))
            if pid in (mod.COMPONENTS_CMA_PID, mod.COMPONENTS_ER_PID):
                component = self._name_at(pid, 2, ids[1])
                age = self._name_at(pid, 4, ids[3])
                value = lambda year: self._component_value(tag, component, age, year)  # noqa: E731
            else:
                age = self._name_at(pid, 3, ids[2])
                value = lambda year: self._population_value(tag, age, year)  # noqa: E731
            out.append({"status": "SUCCESS", "object": {
                "productId": pid, "coordinate": request["coordinate"],
                "vectorDataPoint": [{"refPer": f"{year}-01-01", "value": value(year)}
                                    for year in self._years(pid)]}})
        # Returned SORTED BY COORDINATE, never in request order — that is what the live
        # service does (MEASURED 2026-08-07), and a probe that read positionally would pair
        # every series with the wrong one.
        out.sort(key=lambda item: (item["object"]["productId"], item["object"]["coordinate"]))
        return out[self.drop_series:]


def _wire(mod, cubes: _Cubes) -> None:
    """Patch every boundary so a scenario runs fully OFFLINE.

    The compo half is stubbed rather than loaded: it is measured live by the committed note
    and by test_compo_loader.py, and re-reading two pinned workbooks on every mutation would
    buy nothing but seconds.
    """
    mod._meta = cubes.meta
    mod._data = cubes.data
    mod.load_immigrant_flows = lambda name: name
    mod.compo_evidence_lines = lambda frame: ["### compo section (stubbed offline)"]


def _run(mod, tmp_path, label, cubes, *, declared=None) -> str:
    mod.OUT = tmp_path / f"note_{abs(hash(label))}.md"
    _wire(mod, cubes)
    if declared is not None:
        # Applied AFTER the cubes are built, so the source still publishes every geography and
        # only the probe's declaration narrows — which is the real failure mode.
        mod.GEOGRAPHY_SOURCES = declared
    mod.main()
    return mod.OUT.read_text(encoding="utf-8")


def test_p7_floor_guard_earns_verdict(tmp_path):
    """Gate 4 — every verdict must be EARNED. Six responses that never RAISE on their own must
    each route to UNKNOWN-PROBE-FAILED at the right boundary; then NEUTERING each guard must
    show what it is actually holding up.

    The grades below were obtained by RUNNING each mutation and reading what changed — not
    assumed from the guard's name. Two of the six are honestly graded as attribution-only, and
    saying so is the point: P5b shipped a file claiming a guard was safety-load-bearing when it
    was structurally incapable of being so, and a wrong self-grade propagates into every risk
    list that reads it.

      * `_guard_coverage`  — SAFETY-load-bearing. Neutered with the exceeding geography dropped
        from the declared sources, the run publishes a fabricated EVIDENCED-NO-EXCEEDANCE over
        6 geographies: the exceedance is invisible because the geography carrying it was never
        measured.
      * `_guard_span`      — SAFETY-load-bearing. Neutered against a truncated response, the
        run publishes a no-exceedance verdict computed on a window that excludes the exceeding
        period — literally ruling K's refused window, arriving without anyone choosing it.
      * `_guard_published` — SAFETY-load-bearing. Neutered against an all-null migration
        response, every null coerces to zero and the run publishes a rate of exactly 0.0000
        %/yr everywhere.
      * `_guard_identity`  — SAFETY-load-bearing. Neutered against a population series shifted
        by one period, the run divides each period's migration by the NEXT period's 75+
        population and the exceedance disappears.
      * `_guard_meta`      — SAFETY-load-bearing AGAINST THE SHAPE IT IS WRITTEN FOR, which is
        the honest limit of this grade: the fixture returns `status: "FAILED"` beside a
        well-formed `object`, and that pairing has NOT been observed live (the live service was
        only ever seen answering SUCCESS). Neutered against it, the run publishes a full verdict
        off a response the service said failed. What a real WDS failure looks like is unmeasured
        here, so read this grade as "the guard holds the shape it screens", not as a claim about
        StatCan's error contract.
      * `_guard_response`  — ATTRIBUTION-ONLY. Neutered against a short response, the run still
        fails (a `KeyError` on the missing series downstream) — the VERDICT does not move, only
        the recorded exception type does, from a floor-guard refusal to a code fault. Recorded
        here so this docstring cannot drift into over-claiming.

    Runs OFFLINE — every boundary is patched; the committed note is untouched.
    """
    without_laval = tuple(s for s in _load_run_p7().GEOGRAPHY_SOURCES
                          if s.tag != "LAVAL_RA13")
    assert len(without_laval) == len(_load_run_p7().GEOGRAPHY_SOURCES) - 1, (
        "the coverage mutation did not actually drop a declared source")

    scenarios = {
        "cubes answer a non-SUCCESS status": (dict(meta_status="FAILED"), None, "wds-meta"),
        "a modeled geography has no declared source": ({}, without_laval, "wds-meta"),
        "the response is truncated to six periods": (dict(keep_periods=6), None, "wds-data"),
        "every 75+ migration datapoint is unpublished": (
            dict(null_migration=True), None, "wds-data"),
        "series are missing from the response": (dict(drop_series=3), None, "wds-data"),
        "the population series is shifted by a period": (
            dict(population_shift=1, pop75=_steep_pop75), None, "wds-data"),
    }
    for label, (knobs, declared, boundary) in scenarios.items():
        mod = _load_run_p7()
        text = _run(mod, tmp_path, label, _Cubes(mod, **knobs), declared=declared)
        assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED", (
            f"[{label}] a vacuous / misaligned response was laundered into "
            f"{_token(text, 'DECISION-VERDICT')!r} — the floor guard did not fire.")
        assert _recorded_failure_type(text) == "ProbeRefusal", (
            f"[{label}] the failure was recorded as "
            f"{_recorded_failure_type(text)!r}, not a floor-guard refusal.")
        assert _recorded_failure_boundary(text) == boundary, (
            f"[{label}] expected boundary {boundary!r}, got "
            f"{_recorded_failure_boundary(text)!r} — the skip gate needs the right host.")

    # --- the fixture itself must be capable of a real verdict, or the mutations below
    # would "flip" scenarios that were never going to resolve anyway.
    mod = _load_run_p7()
    honest = _run(mod, tmp_path, "honest", _Cubes(mod))
    assert _token(honest, "DECISION-VERDICT") == "EVIDENCED-WITH-NAMED-EXCEEDANCE", (
        f"the unmutated fixture does not reach a verdict "
        f"({_token(honest, 'DECISION-VERDICT')!r}); every mutation below would be vacuous.")

    def _neutered(label, knobs, patch, *, declared=None):
        mod = _load_run_p7()
        mod.OUT = tmp_path / f"neutered_{abs(hash(label))}.md"
        cubes = _Cubes(mod, **knobs)
        _wire(mod, cubes)
        if declared is not None:
            mod.GEOGRAPHY_SOURCES = declared
        patch(mod)
        mod.main()
        return mod.OUT.read_text(encoding="utf-8")

    # MUTATION 1 — `_guard_coverage`, with its derivation KEPT (a neuter that also deleted the
    # resolution would kill the run for the wrong reason and prove nothing).
    text = _neutered(
        "coverage", {},
        lambda m: setattr(m, "_guard_coverage", lambda metas: [
            (s, m._member(metas, s.components_pid, m._POS_GEO, s.member_name))
            for s in m.GEOGRAPHY_SOURCES]),
        declared=without_laval)
    assert _token(text, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE", (
        "neutering `_guard_coverage` did not flip a silently-dropped geography into a "
        "fabricated no-exceedance — the completeness check is then holding nothing up.")
    assert "6 of 8 modeled geographies MEASURED" in (_token(text, "DECISION-COVERAGE") or ""), (
        "the neutered run must publish a verdict over an INCOMPLETE geography set — that is "
        f"the fabrication `_guard_coverage` refuses; got {_token(text, 'DECISION-COVERAGE')!r}")

    # MUTATION 2 — `_guard_span`: ruling K's window rule.
    text = _neutered("span", dict(keep_periods=6),
                     lambda m: setattr(m, "_guard_span",
                                       lambda metas, series, keys: None))
    assert _token(text, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE", (
        "neutering `_guard_span` did not flip a truncated response into a fabricated "
        "no-exceedance — ruling K's 'a window whose sole visible effect is to remove the "
        "exceedance is not evidence' then rests on nothing.")
    assert "6 periods" in (_token(text, "DECISION-SPAN") or ""), (
        "the neutered run must publish a SHORT span as if it were the full one; got "
        f"{_token(text, 'DECISION-SPAN')!r}")

    # MUTATION 3 — `_guard_published`: nulls coerced to a measured zero.
    text = _neutered("published", dict(null_migration=True),
                     lambda m: setattr(m, "_guard_published", lambda series, keys: 0))
    assert _token(text, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE", (
        "neutering `_guard_published` did not flip an all-null response into a fabricated "
        "no-exceedance.")
    assert (_token(text, "DECISION-MAX-RATE") or "").startswith("0.0000 %/yr"), (
        "the neutered run must publish a rate of exactly zero over UNPUBLISHED data — that is "
        f"the fabrication the guard refuses; got {_token(text, 'DECISION-MAX-RATE')!r}")

    # MUTATION 4 — `_guard_identity`: the alignment guard.
    text = _neutered(
        "identity", dict(population_shift=1, pop75=_steep_pop75),
        lambda m: setattr(m, "_guard_identity",
                          lambda series, keys, resolved, spans: {"max_abs_difference": 0.0,
                                                                 "checked": 0}))
    assert _token(text, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE", (
        "neutering `_guard_identity` did not flip a period-misaligned response into a "
        "fabricated no-exceedance — the identity is then not what keeps the denominators "
        "honest, and every rate in the committed note rests on nothing.")

    # MUTATION 5 — `_guard_meta`: a response the service said failed.
    text = _neutered(
        "meta", dict(meta_status="FAILED"),
        lambda m: setattr(m, "_guard_meta", lambda pids, response: {
            int(item["object"]["productId"]): item["object"] for item in response}))
    assert _token(text, "DECISION-VERDICT") in EVIDENCED, (
        "neutering `_guard_meta` did not let a non-SUCCESS metadata response reach a published "
        f"verdict; got {_token(text, 'DECISION-VERDICT')!r}")

    # MUTATION 6 — `_guard_response`, graded ATTRIBUTION-ONLY by measurement. The verdict must
    # NOT move; only the recorded exception type does. Asserted rather than claimed, so the
    # docstring above cannot drift into calling it safety-load-bearing.
    text = _neutered(
        "response", dict(drop_series=3),
        lambda m: setattr(m, "_guard_response", lambda requests, response: {
            (int(item["object"]["productId"]), item["object"]["coordinate"]):
                {p["refPer"][:4]: p["value"] for p in item["object"]["vectorDataPoint"]}
            for item in response}))
    assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED", (
        "neutering `_guard_response` changed the VERDICT — it is then safety-load-bearing and "
        "this test's docstring, which grades it attribution-only, is wrong.")
    assert _recorded_failure_type(text) == "KeyError", (
        "neutering `_guard_response` must degrade a named refusal into a raw code fault; if "
        f"nothing changes at all the guard is dead code. Got "
        f"{_recorded_failure_type(text)!r}")


def test_p7_both_evidenced_verdicts_reachable(tmp_path):
    """Gate 5 — EVIDENCED-NO-EXCEEDANCE is a REACHABLE verdict, distinct from the other two.

    The live run FIRES, so nothing in the green path ever reaches the no-exceedance branch —
    which is exactly how a two-valued verdict decays into a constant, and how a gate that can
    only ever say one thing gets mistaken for a working gate. Runs OFFLINE.
    """
    mod = _load_run_p7()
    quiet = _run(mod, tmp_path, "quiet", _Cubes(mod, rate=_quiet))
    assert _token(quiet, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE", (
        f"a measurement with no exceedance must EARN EVIDENCED-NO-EXCEEDANCE, not "
        f"{_token(quiet, 'DECISION-VERDICT')!r}.")
    assert (_token(quiet, "DECISION-TRIPWIRE") or "").startswith("NOT FIRED — 0 "), (
        f"the quiet run's tripwire line contradicts its verdict: "
        f"{_token(quiet, 'DECISION-TRIPWIRE')!r}")
    assert "### 2e. The named exceedances\n\nNone." in quiet, (
        "a no-exceedance run must SAY it named none, not leave the section blank")

    mod2 = _load_run_p7()
    loud = _run(mod2, tmp_path, "loud", _Cubes(mod2, rate=_one_exceedance))
    assert _token(loud, "DECISION-VERDICT") == "EVIDENCED-WITH-NAMED-EXCEEDANCE", (
        f"the SAME fixture with one exceeding period reached "
        f"{_token(loud, 'DECISION-VERDICT')!r} — the two evidenced verdicts are then one "
        f"value wearing two names, and the measurement is not discriminating.")
    assert (_token(loud, "DECISION-TRIPWIRE") or "").startswith("FIRED — 1 ")
    assert re.search(r"^\| LAVAL_RA13 \| 2007/08 \|", loud, re.M), (
        "the fired run must NAME the exceeding geography-period in its table")


def test_p7_tripwire_is_falsifiable(tmp_path):
    """Gate 6 — the THRESHOLD is what decides, and the decision is strict.

    Without this, a fixture that fires and one that does not could both be explained by
    something other than the tripwire (a hardcoded geography, say). Driving the SAME rate
    across the threshold — and sitting exactly ON it — is what pins the comparison itself.
    Runs OFFLINE.
    """
    mod = _load_run_p7()
    threshold = mod.TRIPWIRE_PCT

    def at(value):
        return lambda tag, year: (value if (tag == "LAVAL_RA13" and year == "2007") else 0.1)

    just_over = _run(mod, tmp_path, "over", _Cubes(mod, rate=at(threshold + 0.05)))
    assert _token(just_over, "DECISION-VERDICT") == "EVIDENCED-WITH-NAMED-EXCEEDANCE"

    mod2 = _load_run_p7()
    exactly = _run(mod2, tmp_path, "exact", _Cubes(mod2, rate=at(threshold)))
    assert _token(exactly, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE", (
        f"a rate exactly AT {threshold} %/yr was counted as an exceedance. The spec says "
        f"'above 1%/yr'; a >= comparison would fire on the boundary the spec excludes.")

    mod3 = _load_run_p7()
    under = _run(mod3, tmp_path, "under", _Cubes(mod3, rate=at(threshold - 0.05)))
    assert _token(under, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE"


def test_p7_age_bands_resolved_by_name_not_by_a_shared_id_table(tmp_path):
    """Gate 7 — run-time NAME resolution is what keeps the denominator the right age band.

    run_p7.py's module docstring makes this its central safety claim: the components cubes
    carry 114 age members and the population cubes 115, so the SAME band sits at different ids
    and "a hardcoded id table would silently divide one age band's migration by another age
    band's population." Until this test, that claim had no gate — the fixture reproduced the
    offset, but nothing ever exercised the misuse.

    It is worth its own test because NO other guard can see it. `_guard_identity` closes on the
    All-ages series, so a band-level mis-resolution leaves it perfectly exact; `_guard_span`,
    `_guard_published` and `_guard_response` all pass on data that is complete, published and
    fully returned. Name resolution is the ONLY thing standing between the note and a plausible
    wrong number — which is exactly the class of defect that ships.

    The mutation is the real one: resolve the population cube's 75+ bands with the COMPONENTS
    cube's ids. Every one of those ids is a real member of the population cubes under a
    DIFFERENT name (MEASURED 2026-08-08: 93 `75 years`, 99 `80 years`, 105 `85 years`, 111
    `0 to 14 years`), so nothing raises — the run just divides by the wrong population. In
    THIS fixture all four decoys are small, so the fabricated quotient is inflated and a quiet
    measurement publishes fabricated exceedances; live the fourth decoy is a large band, so the
    magnitude and even the SIGN of the live distortion are not what this test measures. What it
    measures is that a shared id table moves the published answer at all, silently. OFFLINE.
    """
    honest_mod = _load_run_p7()
    honest = _run(honest_mod, tmp_path, "byname_honest", _Cubes(honest_mod, rate=_quiet))
    assert _token(honest, "DECISION-VERDICT") == "EVIDENCED-NO-EXCEEDANCE", (
        "the fixture must be quiet before the mutation, or a fabricated exceedance below "
        "would be indistinguishable from a real one")

    mod = _load_run_p7()
    mod.OUT = tmp_path / "note_shared_id_table.md"
    _wire(mod, _Cubes(mod, rate=_quiet))
    real_member = mod._member

    def shared_id_table(metas, pid, position, name):
        """The defect: one id table, reused across two cubes that do not share one."""
        if (pid in (mod.POPULATION_CMA_PID, mod.POPULATION_ER_PID)
                and position == mod._POS_AGE_POPULATION and name in _COMPONENT_BAND_IDS):
            dim = next(d for d in metas[pid]["dimension"]
                       if d["dimensionPositionId"] == position)
            return next(member for member in dim["member"]
                        if member["memberId"] == _COMPONENT_BAND_IDS[name])
        return real_member(metas, pid, position, name)

    mod._member = shared_id_table
    mod.main()
    text = mod.OUT.read_text(encoding="utf-8")

    assert _token(text, "DECISION-IDENTITY") == _token(honest, "DECISION-IDENTITY"), (
        "the id mutation changed the identity result, so this test is not isolating what it "
        "claims to — the point is that the identity guard CANNOT see a band-level defect.")
    assert _token(text, "DECISION-VERDICT") == "EVIDENCED-WITH-NAMED-EXCEEDANCE", (
        f"resolving the population bands with the COMPONENTS cube's ids did not change the "
        f"verdict ({_token(text, 'DECISION-VERDICT')!r}). Either the fixture no longer "
        f"reproduces the id offset, or the probe is not really resolving by name — and the "
        f"module docstring's central safety claim is then unfounded.")
    assert _pct(_token(text, "DECISION-MAX-RATE")) > _pct(_token(honest, "DECISION-MAX-RATE")), (
        "the mutated run must publish an INFLATED rate — that is the fabricated quotient a "
        "shared id table produces, and it is what run-time name resolution prevents.")


def _paragraph(text: str, needle: str) -> str:
    """The one blank-line-delimited block of the note carrying `needle`."""
    blocks = [block for block in text.split("\n\n") if needle in block]
    assert len(blocks) == 1, (
        f"expected exactly one block of {NOTE.name} carrying {needle!r}; found {len(blocks)}")
    return blocks[0]


def test_p7_note_states_only_per_cube_quantities_it_measured(tmp_path):
    """The note's §2a and §2c prose must carry MEASURED per-cube quantities.

    What this test measurably catches, and why each half needs its own assertion:

      * §2a's age-member counts as LITERALS. `Fact` is the registry, but nothing gates a
        DERIVED figure the way `test_p7_cited_figures_travel_both_paths` gates a cited one,
        so a hardcoded `114`/`115` inside the f-string prints a correct number today and a
        stale one on a re-editioned cube — under prose asserting the resolution-by-name it
        exists to justify. The offline cubes publish 5 and 9 age members, so a literal and a
        derivation are VISIBLY different here; against the live cubes they are identical and
        this test would be watching a constant.
      * §2a's band member IDS as literals — the same class one level down, and it needs the
        same condition honoured. It was not: the fixture originally seated the band at the
        LIVE ids, so this half WAS watching a constant. MEASURED 2026-08-08: with run_p7.py's
        two `_member` lookups for the band ids replaced by the literals `93`/`92`, the whole
        demoflow suite stayed green. The fixture ids are now displaced clear of the live
        range (see `_LIVE_AGE_ID_CEILING`), and the same mutation reddens here.
      * §2c's span bullet attaching ONE period count to ALL requested series. The two cube
        families do not share a span (components 24 periods, population 25 — the extra July-1
        count a start-of-period denominator needs), so a single figure beside the total series
        count is false for the population cubes' share of them. `_guard_span` itself is
        per-cube and correct; this pins the PROSE to the same per-cube shape.

    Runs OFFLINE against a generated note, never the committed one — a committed note some
    other run last wrote would make this a test of a file rather than of the generator.
    """
    mod = _load_run_p7()
    cubes = _Cubes(mod)
    text = _run(mod, tmp_path, "per_cube_prose", cubes)
    assert _token(text, "DECISION-VERDICT") in EVIDENCED, (
        f"the fixture must reach a real verdict or the prose below is the failure branch's; "
        f"got {_token(text, 'DECISION-VERDICT')!r}")

    # --- §2a: the age-member counts and the band ids are the FIXTURE's, not the live ones ---
    sources = _paragraph(text, "Release stamp")
    counts = re.findall(r"publishes (\d+) age members", sources)
    assert counts == [str(len(_COMPONENT_AGE_IDS)), str(len(_POPULATION_AGE_IDS))], (
        f"§2a states age-member counts {counts} while the cubes it ran against publish "
        f"{len(_COMPONENT_AGE_IDS)} and {len(_POPULATION_AGE_IDS)} — the sentence is a "
        f"literal, so it will print a stale count on a re-editioned cube.")
    assert len(_COMPONENT_AGE_IDS) != len(_POPULATION_AGE_IDS), (
        "the fixture must publish DIFFERENT age-member counts per family, or a literal and a "
        "derivation are indistinguishable here and this assertion is watching a constant")
    band = mod.BANDS_75_PLUS[0]
    expected_ids = (_COMPONENT_AGE_IDS[band], _POPULATION_AGE_IDS[band])
    assert expected_ids[0] != expected_ids[1], (
        "the fixture must seat the SAME band at DIFFERENT ids across the pair — that offset is "
        "the whole reason §2a's sentence exists, and without it the assertion below is vacuous")
    assert min(expected_ids) > _LIVE_AGE_ID_CEILING, (
        f"the fixture seats {band!r} at {expected_ids}, inside the id range these cubes really "
        f"publish (max member id {_LIVE_AGE_ID_CEILING}, MEASURED 2026-08-08). The literal a "
        f"stale hardcode carries IS the live id, so the assertion below would then match it "
        f"and be watching a constant. Residual, stated plainly: the ceiling is a remembered "
        f"live figure, so it is the fixture's SEPARATION from it that has to stay generous.")
    ids = re.search(r"resolves to member (\d+) in the first against (\d+) in the second",
                    sources)
    assert ids and (int(ids.group(1)), int(ids.group(2))) == expected_ids, (
        f"§2a does not state the LIVE-resolved member ids for {band!r} "
        f"({ids.groups() if ids else None} vs the cubes' {expected_ids}) — the 'resolved by "
        f"name' claim then rests on nothing the run actually looked up.")

    # --- §2c: the span bullet records a span PER CUBE, not one count over every series ------
    span_bullet = _paragraph(text, "**Span**")
    rows = re.findall(r"(\d\d-\d\d-\d{4}-01) \((\d+) series, (\d+) periods\)", span_bullet)
    assert len(rows) == len(mod.PIDS), (
        f"§2c's Span bullet breaks its series count down over {len(rows)} cube(s), not "
        f"{len(mod.PIDS)}: {span_bullet!r}. A single period count beside the TOTAL series "
        f"count is false for every series on the other-spanned cube.")
    declared = {mod.table_number(pid):
                int(str(cubes.metas[pid]["cubeEndDate"])[:4])
                - int(str(cubes.metas[pid]["cubeStartDate"])[:4]) + 1
                for pid in mod.PIDS}
    assert len(set(declared.values())) > 1, (
        "the fixture's cubes all declare the SAME span length, so a per-cube breakdown and a "
        "single over-generalised count would render identically — the assertion below would "
        "pass on the defect it exists to catch")
    assert {table: int(periods) for table, _, periods in rows} == declared, (
        f"§2c's per-cube period counts disagree with the spans the cubes declared: "
        f"{ {t: p for t, _, p in rows} } vs {declared}")
    total = re.search(r"each of the (\d+) requested series", span_bullet)
    assert total, f"§2c's Span bullet states no total requested-series count: {span_bullet!r}"
    assert sum(int(series) for _, series, _ in rows) == int(total.group(1)), (
        f"§2c's per-cube series counts sum to "
        f"{sum(int(s) for _, s, _ in rows)} but the bullet claims {total.group(1)} requested "
        f"— a breakdown that does not decompose the total beside it.")


def test_p7_compo_boundary_failure_is_not_a_skip(tmp_path):
    """Gate 7 — a LOCAL failure is attributed locally, and can never launder into a skip.

    The compo workbook is on disk. If it were attributed to a network boundary, an unrelated
    StatCan outage would excuse a broken local read — the exact laundering the skip gate
    exists to prevent. Runs OFFLINE.
    """
    from demoflow.errors import LoaderError

    mod = _load_run_p7()
    mod.OUT = tmp_path / "note_compo_fail.md"
    _wire(mod, _Cubes(mod))

    def _boom(name):
        raise LoaderError("workbook not found: synthetic")

    mod.load_immigrant_flows = _boom
    mod.main()
    text = mod.OUT.read_text(encoding="utf-8")
    assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED"
    assert _recorded_failure_boundary(text) == "compo-workbook", (
        f"a local workbook failure was attributed to {_recorded_failure_boundary(text)!r}")
    assert _recorded_failure_type(text) == "LoaderError"
    assert "LoaderError" not in NETWORK_EXCEPTIONS, (
        "a LoaderError inside the network-excusable set would let an outage excuse a broken "
        "local read")
