"""
The reversal register — board item 4, slice 1
(docs/specs/2026-09-22-which-risk-decides-it.md §6, §8, §10, §11, and §0.1's
rulings 4, 5 and 9 on what typing the contract found).

WHAT IT ANSWERS. For each input the config STATES that carries no distribution
in this run: how far would this one input have to move, holding everything
else, before the verdict names a different winner.

THE ONE FINDING THESE TESTS GUARD. `house.mortgage_renewal_rates` is a path the
user states, so its variance is identically zero and any variance table prints
it as a dash. On this repo's own flagship fixture the opposite is true:
replacing the stated ladder with one flat rate, the verdict's own winner is the
house below 1.6052% and rent above it — inside the bracket the engine already
uses for a contract rate, and the run itself says rent.

EVERY BOUNDARY READS THE KEY UPWARD: `was` is what the verdict says just below
the value, `becomes` what it says just above, so `--sweep` at a point either
side prints `was` below and `becomes` above. `TestEveryBoundaryReadsTheKeyUpward`
checks exactly that, against the sweep rather than against the solver. A run that prices a financed option and cannot say that is
telling a household renewal was weighed and found irrelevant.

MEASURED, AND NOW CARRIED BY THE CONTRACT. Across seeds 42, 7, 1234, 99 and
2026 the `best` and `runner_up` boundaries below are identical to seven digits
while the `mc_best` boundary moves 2.698% -> 2.805%: two are properties of the
config, one is a property of this run's 2,000 futures. So the first two arrive
as `SolvedBoundary`, carrying no sample at all, and the third as
`SampledBoundary`, carrying the curve's path count and its seed — and the class
below pins which kind each field arrives as, on the real fixture. (That
five-seed sweep is five full Monte Carlo runs and is deliberately NOT in this
suite — it is recorded in the commit that landed the register.)
"""

import copy
import dataclasses
import math
import re
import os
import pathlib
import types

import numpy as np
import pytest
import yaml

import hde.break_even as be
from hde.break_even import (BRACKET_SOURCE, RATE_BRACKETS, REVERSAL_GATE_TOLERANCE,
                            _DETERMINISTIC_FIELDS, _FUTURES_FIELDS,
                            _shift_deviation_over_sd, _typed_boundary,
                            deterministic_boundaries, floor_at_zero, reversal_admission,
                            reversal_bracket, reversal_candidates, reversal_gate,
                            reversal_register, solve_break_even, solve_crossings)
from hde.config import load_config_dict, single_path_run
from hde.decomposition import (BOUNDARY_FIELDS, EstimatedReversal, ExactReversal,
                               SampledBoundary, SolvedBoundary)
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo
from hde.sweep import load_at, run_sweep

from tests.decomposition_runs import (CONDO_ONLY, DECISIVE_STEP, DECISIVE_STEP_LOWER, INERT,
                                      THIRD_IN_ONE_CELL)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"
# A SHIPPED config with every uncertainty input off, so every path it prices is
# the same path. The tests that read it assert that precondition first: an
# example that later gains a volatility must fail them, not pass them vacuously.
SINGLE_PATH = REPO_ROOT / "examples" / "first_time_buyer_montreal.yaml"
# A SHIPPED two-option config whose futures are decisive for the house at its
# own contract rate and decisive for rent past ~6.84%, with a tie band between:
# the axis on which a boolean decisiveness printed "True to False" twice.
TWO_OPTION = REPO_ROOT / "examples" / "mortgage_house_vs_rent.yaml"

RENEWAL = "house.mortgage_renewal_rates"
CONTRACT = "house.mortgage_rate"

# The fixture's own committed seed and path count, named here so that reseeding
# it is a deliberate act with a failing test attached rather than a silent
# re-tuning of every figure below (spec T6's discipline, applied to §6).
SEED = 42
PATHS = 2000

# Measured on this tree, derived from the solver rather than copied from the
# spec: `solve_crossings` on the relevant pair for the two deterministic
# figures, an independent bisection of the free curve for the third.
BEST_FLIPS_AT = 0.016052260138094424        # house below, rent above: the master's-project finding
RUNNER_UP_SWAPS_AT = 0.029549435637891294   # house below, condo above
MAJORITY_SWAPS_AT = 0.027164030807034577    # house below, condo above — a property of THIS sample


@pytest.fixture(scope="module", autouse=True)
def _at_repo_root():
    """`market_scenario.path` in the fixture resolves against the CURRENT
    WORKING DIRECTORY, the convention every config in this repo uses."""
    prior = os.getcwd()
    os.chdir(REPO_ROOT)
    yield
    os.chdir(prior)


@pytest.fixture(scope="module")
def raw(_at_repo_root):
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def base(raw):
    """This run's own results — what the register takes rather than
    re-simulating, so a caller and the register cannot disagree about the base
    case."""
    spec = load_config_dict(raw)
    assert spec.simulation.random_seed == SEED and spec.simulation.num_sims == PATHS
    return spec, compute_deterministic(spec), run_monte_carlo(spec)


@pytest.fixture(scope="module")
def register(raw, base):
    _, det, mc = base
    return reversal_register(raw, det, mc)


@pytest.fixture(scope="module")
def reseeded(raw):
    """The same config at a DIFFERENT seed. One reseed, not the five-seed sweep:
    it is what makes "the sampled boundary carries this run's seed" a claim that
    can fail, since a seed pinned to the fixture's own 42 passes every other
    assertion in this file. Measured at 5s for the whole register."""
    doc = _set(raw, "simulation.random_seed", 7)
    spec = load_config_dict(doc)
    return doc, compute_deterministic(spec), run_monte_carlo(spec)


def _without(raw, *options):
    """`raw` with whole option blocks dropped, `sources:` included — the loader
    refuses a source declared for a key the config no longer sets, which is the
    honest behaviour and not what these tests are about."""
    doc = copy.deepcopy(raw)
    for option in options:
        doc.pop(option, None)
    doc["sources"] = {k: v for k, v in doc["sources"].items()
                      if not any(k.startswith(f"{o}.") for o in options)}
    return doc


def _set(raw, key, value):
    """One dotted key set on a plain copy. Not `sweep.with_value`, which marks
    the `sources:` entry `sweep` for `load_at` to relabel — a doc only
    `load_at` can load, and these tests hand the doc to the register, which
    loads the caller's config itself."""
    doc = copy.deepcopy(raw)
    node = doc
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return doc


def _row(register, key):
    rows = [r for r in register.exact if r.key == key]
    assert len(rows) == 1, f"{key} is not one exact reversal: {[r.key for r in register.exact]}"
    return rows[0]


def _boundary(row, field):
    found = [b for b in row.boundaries if b.verdict_field == field]
    assert len(found) == 1, f"{field} is not one boundary of {row.key}: {row.boundaries}"
    return found[0]


def _refusal(row, field):
    found = [r for r in row.refused_boundaries if r.verdict_field == field]
    assert len(found) == 1, f"{field} is not one refusal of {row.key}: {row.refused_boundaries}"
    return found[0]


# The two futures-side fields are refused on a run with no futures for
# DIFFERENT reasons, and each sentence has to be true of its own field.
def _assert_the_no_futures_reasons_are_each_true(row):
    """The measured fact, true of both fields: this run has no futures, and
    this solver reads each of them only off futures. `decisive` DOES exist
    without futures — the margin band decides it — so no reason may say it
    does not (`test_without_futures_decisiveness_still_changes...`)."""
    for field in ("mc_best", "decisive"):
        assert _refusal(row, field).reason == (
            f"this run has no futures, and this solver reads {field} only off futures")


# ---------------------------------------------------------------------------
# The three figures. Each is re-derived independently in the class below, so
# the numbers pinned here are not their own authority.
# ---------------------------------------------------------------------------

class TestTheThreeFiguresOnTheFixture:

    def test_the_verdicts_own_winner_flips_inside_the_contract_rates_bracket(self, register):
        """The finding: an input with no variance at all reverses the verdict
        inside the bracket the engine already uses for a mortgage rate."""
        flip = _boundary(_row(register, RENEWAL), "best")
        # Read upward: the house wins below the flat rate, rent above it.
        assert (flip.was, flip.becomes) == ("house", "rent")
        assert flip.value == pytest.approx(BEST_FLIPS_AT, abs=1e-9)
        lo, hi = RATE_BRACKETS["mortgage_rate"]
        assert lo < flip.value < hi

    def test_the_runner_up_swaps_where_the_house_crosses_the_condo(self, register):
        swap = _boundary(_row(register, RENEWAL), "runner_up")
        assert (swap.was, swap.becomes) == ("house", "condo")
        assert swap.value == pytest.approx(RUNNER_UP_SWAPS_AT, abs=1e-9)

    def test_the_option_most_futures_call_cheapest_changes_too(self, register):
        swap = _boundary(_row(register, RENEWAL), "mc_best")
        assert (swap.was, swap.becomes) == ("house", "condo")
        assert swap.value == pytest.approx(MAJORITY_SWAPS_AT, abs=1e-9)

    def test_the_contract_rate_alone_reverses_no_winner_anywhere_in_its_bracket(
            self, register):
        """Measured, and not anticipated by the spec: the opening term runs five
        of twenty-five years, so `mortgage_rate` cannot take the house past the
        renter at ANY rate in its own bracket while the renewal ladder does it
        at 1.61%. The register has to be able to come out this way, or the
        renewal finding is a number with nothing to compare it to."""
        row = _row(register, CONTRACT)
        assert [b.verdict_field for b in row.boundaries] == ["runner_up", "mc_best"]
        assert _refusal(row, "best").reason == (
            "best says 'rent' at every one of 9 points across 1.00%–10.00%")


# ---------------------------------------------------------------------------
# WHICH KIND EACH FIGURE IS — the split the register's own measurement forced
# (§6, 2026-09-22). One level below the exactness gate: that one splits ROWS by
# key, these are two kinds WITHIN one key.
# ---------------------------------------------------------------------------

class TestTheTwoBoundaryKinds:

    def test_the_solved_pair_arrives_carrying_no_sample_at_all(self, register):
        """`best` and `runner_up` are solved on the deterministic verdict, which
        reads no path: identical to seven digits at seeds 42, 7, 1234, 99 and
        2026. The type they arrive as has NO field that could name a sample, so
        nothing downstream can attach this run's seed to a figure that does not
        depend on it."""
        for field in ("best", "runner_up"):
            boundary = _boundary(_row(register, RENEWAL), field)
            assert isinstance(boundary, SolvedBoundary)
            assert not hasattr(boundary, "curve_paths")
            assert not hasattr(boundary, "seed")

    def test_the_futures_majority_arrives_carrying_the_sample_it_depends_on(self, register):
        """`mc_best` is bisected on this run's own curve and moves
        2.698%-2.805% across those same five seeds, so it arrives as the other
        type — carrying the count of paths the curve was bisected on and the
        seed that drew them. Without those two a reader is handed 2.716% in the
        typography of an exact figure."""
        boundary = _boundary(_row(register, RENEWAL), "mc_best")
        assert isinstance(boundary, SampledBoundary)
        assert (boundary.curve_paths, boundary.seed) == (PATHS, SEED)
        assert boundary.value == pytest.approx(MAJORITY_SWAPS_AT, abs=1e-9)

    def test_the_sample_on_the_row_is_this_runs_and_never_the_fixtures(self, reseeded):
        """Reseeded to 7, which is the assertion that can fail: the sampled
        boundary's seed follows the RUN and its value MOVES (measured
        2.698%-2.805% over the five seeds), while the solved pair does not move
        at all. A seed or a path count pinned to the fixture's own 42 and 2,000
        would satisfy every other test in this file."""
        doc, det, mc = reseeded
        row = _row(reversal_register(doc, det, mc), RENEWAL)
        sampled = _boundary(row, "mc_best")
        assert (sampled.curve_paths, sampled.seed) == (PATHS, 7)
        assert sampled.value != pytest.approx(MAJORITY_SWAPS_AT, abs=1e-9)
        assert _boundary(row, "best").value == pytest.approx(BEST_FLIPS_AT, abs=1e-9)

    def test_the_router_types_every_field_by_its_own_solver_and_refuses_a_fifth(self):
        """The routing itself, for all four fields — `decisive` included, which
        the fixture never yields a boundary of, so its route is pinned here or
        nowhere. A field no solver claims RAISES: routed by a default branch it
        would be typed as whichever kind the branch happened to be, and that is
        the one error no downstream reader could detect.
        """
        entry = {"value": 0.0271, "was": "house", "becomes": "condo", "further": None}
        probs = {"condo": 0.44, "house": 0.51, "rent": None}
        kinds = {field: type(_typed_boundary(field, entry, formatted="2.71%", curve=probs,
                                             confirmed=probs, curve_paths=1234, seed=7))
                 for field in BOUNDARY_FIELDS}
        assert kinds == {"best": SolvedBoundary, "runner_up": SolvedBoundary,
                         "mc_best": SampledBoundary, "decisive": SampledBoundary}
        # The sample travels from the caller rather than from a constant.
        sampled = _typed_boundary("decisive", entry, formatted="2.71%", curve=probs,
                                  confirmed=probs, curve_paths=1234, seed=7)
        assert (sampled.curve_paths, sampled.seed) == (1234, 7)
        with pytest.raises(ValueError, match="neither"):
            _typed_boundary("margin_pv", entry, formatted="2.71%", curve=probs,
                            confirmed=probs, curve_paths=1234, seed=7)
        # And a sampled field with no curve to belong to refuses rather than
        # inventing a sample: this is the call the no-futures branch must never
        # be able to make.
        with pytest.raises(ValueError, match="no sample|has none"):
            _typed_boundary("mc_best", entry, formatted="2.71%", curve=None,
                            confirmed=None, curve_paths=1234, seed=7)
        # And the router passes `was` / `becomes` through UNCOERCED, so a raw
        # boolean decisiveness reaches the type's own check and refuses there.
        # A `str()` in the router is what once printed "True to False".
        for field in BOUNDARY_FIELDS:
            with pytest.raises(TypeError, match="not words"):
                _typed_boundary(field, {"value": 0.05, "was": True, "becomes": False,
                                        "further": None},
                                formatted="5.00%", curve=probs, confirmed=probs,
                                curve_paths=1234, seed=7)

    def test_the_two_field_lists_partition_the_four_kinds(self):
        """The router reads these lists, so a fifth field added to
        `BOUNDARY_FIELDS` without a solver named for it must not fall through to
        either type."""
        assert set(_DETERMINISTIC_FIELDS) | set(_FUTURES_FIELDS) == set(BOUNDARY_FIELDS)
        assert not set(_DETERMINISTIC_FIELDS) & set(_FUTURES_FIELDS)


# ---------------------------------------------------------------------------
# §0.1 ruling 4: four kinds, and an unreachable one refuses BY NAME
# ---------------------------------------------------------------------------

class TestAllFourKindsAreAnswered:

    def test_every_boundary_field_is_either_solved_or_refused_by_name(self, register):
        """An absent row and a refused row are different claims and a reader
        cannot tell them apart. Every one of the four is accounted for on every
        row, with nothing silently missing and nothing answered twice."""
        assert register.exact, "no exact reversal, so this test proves nothing"
        for row in register.exact:
            answered = [b.verdict_field for b in row.boundaries]
            refused = [r.verdict_field for r in row.refused_boundaries]
            assert set(answered) | set(refused) == set(BOUNDARY_FIELDS)
            assert not set(answered) & set(refused)
            for refusal in row.refused_boundaries:
                assert refusal.reason and refusal.reason.strip()

    def test_decisiveness_never_changes_and_is_refused_rather_than_dropped(self, register):
        """The fixture is not decisive anywhere in the bracket. That is an
        ANSWER — the row names it, in words, with the resolution it was looked
        for at."""
        reason = _refusal(_row(register, RENEWAL), "decisive").reason
        assert reason == ("decisive says 'not decisive' at every one of 65 points "
                          "across 1.00%–10.00%")
        assert "False" not in reason


# ---------------------------------------------------------------------------
# Every boundary reads the key UPWARD, and agrees with --sweep either side
# ---------------------------------------------------------------------------

# Half a hundredth of a basis point. Far below the nearest two boundaries on any
# axis here (the example's `best` and `mc_best` sit 0.3 bp apart) and far above
# the bisection's own 1e-12 resolution, so a point either side is in the region
# the boundary claims and in no other.
_EITHER_SIDE = 1e-5


def _sweep_says(row, field):
    """What one `--sweep` row says for a verdict field, in the words a boundary
    must carry. Written out here from the row's own `best` / `decisive` columns
    rather than by calling the register's labeller, so the two are compared and
    not assumed equal."""
    if field == "decisive":
        return f"decisive for {row['best']}" if row["decisive"] else "not decisive"
    return row[field]


def _assert_agrees_with_the_sweep(raw, key, boundaries):
    assert boundaries, "no boundary to check, so this test proves nothing"
    for boundary in boundaries:
        rows = run_sweep(raw, key, [boundary.value - _EITHER_SIDE,
                                    boundary.value + _EITHER_SIDE])["rows"]
        below, above = (_sweep_says(r, boundary.verdict_field) for r in rows)
        assert (boundary.was, boundary.becomes) == (below, above), (
            f"{boundary.verdict_field} at {boundary.value!r} reads "
            f"{boundary.was!r} -> {boundary.becomes!r}; --sweep prints {below!r} just "
            f"below and {above!r} just above")


@pytest.fixture(scope="module")
def two_option():
    raw = yaml.safe_load(TWO_OPTION.read_text(encoding="utf-8"))
    spec = load_config_dict(raw)
    return raw, reversal_register(raw, compute_deterministic(spec), run_monte_carlo(spec))


class TestEveryBoundaryReadsTheKeyUpward:
    """`was` is what the verdict says just BELOW the value and `becomes` what it
    says just above — checked against `--sweep` at a point either side, never
    against the solver that produced it.

    Two defects this closes. Each edge used to be labelled from inside the
    run's own region, so an edge BELOW that region read downward and one above
    it read upward: on the fixture the winner is the house below 1.6052% and
    rent above, and the row said "from rent to house". And decisiveness
    travelled as a boolean, which merges decisive for one option with decisive
    for the other: on the two-option example the block printed "True to False
    at 6.74%" and "True to False at 6.84%", where the second crossing runs from
    a tie INTO rent's decisiveness and is True to False in no reading direction.
    """

    @pytest.mark.parametrize("key", [RENEWAL, CONTRACT])
    def test_every_fixture_boundary_agrees_with_a_sweep_either_side(self, raw, register, key):
        """Every edge on the fixture lies BELOW the run's own region, which is
        the side the old labelling read backwards.
        *Kills it:* labelling a lower edge from inside the run's region."""
        _assert_agrees_with_the_sweep(raw, key, _row(register, key).boundaries)

    def test_the_two_option_example_agrees_with_a_sweep_either_side(self, two_option):
        raw, register = two_option
        _assert_agrees_with_the_sweep(raw, CONTRACT, _row(register, CONTRACT).boundaries)

    def test_decisiveness_is_named_for_whom_and_never_as_a_boolean(self, two_option):
        """The example is decisive for the house at its own 4.40%. One edge
        bounds that region, read upward, in words that say for whom — and the
        crossing past ~6.84% from the tie band into RENT's decisiveness is no
        edge of this run's region, so it is not reported as one.
        *Kills it:* a boolean `decisive`, which re-admits the 6.84% edge as a
        second "True to False"."""
        _, register = two_option
        decisive = [b for b in _row(register, CONTRACT).boundaries
                    if b.verdict_field == "decisive"]
        assert [(b.was, b.becomes) for b in decisive] == [("decisive for house", "not decisive")]
        assert 0.066 < decisive[0].value < 0.068
        for boundary in _row(register, CONTRACT).boundaries:
            assert {boundary.was, boundary.becomes}.isdisjoint({"True", "False"})

    def test_a_run_inside_the_tie_band_reads_both_its_edges_upward(self, two_option):
        """The same example restated at 6.80%, inside the band where neither
        option is decisive. Its region now has TWO edges, and the upper one is
        the crossing into rent's decisiveness — the case the boolean could not
        say, read in the one direction that makes both lines true."""
        raw, _ = two_option
        inside = _set(raw, CONTRACT, 0.068)
        spec = load_config_dict(inside)
        register = reversal_register(inside, compute_deterministic(spec), run_monte_carlo(spec))
        decisive = [b for b in _row(register, CONTRACT).boundaries
                    if b.verdict_field == "decisive"]
        assert [(b.was, b.becomes) for b in decisive] == [
            ("decisive for house", "not decisive"),
            ("not decisive", "decisive for rent")]
        _assert_agrees_with_the_sweep(inside, CONTRACT, decisive)
        # Both edges of this run's region are reported, so neither has a
        # change beyond it that no row reports.
        assert [b.further_changes for b in decisive] == [None, None]


class TestTheStatePastAnEdgeIsReadAtTheEdge:
    """§0.1 item 47. `was` and `becomes` are the field's states at the two
    ends of the bracket its edge converged in, and `further_changes` is read
    from there onward. Read at the next scan point instead, a state lying
    wholly between the edge and that point was skipped: on `DECISIVE_STEP`
    the decisiveness verdict goes decisive for house, not decisive, decisive
    for rent, all inside one step of the 65-point scan, and the row said it
    changed straight from the first to the third."""

    @staticmethod
    def _decisive(raw):
        raw = copy.deepcopy(raw)
        spec = load_config_dict(raw)
        register = reversal_register(raw, compute_deterministic(spec), run_monte_carlo(spec))
        (row,) = register.exact
        (edge,) = [b for b in row.boundaries if b.verdict_field == "decisive"]
        return raw, edge

    def test_an_upper_edge_becomes_the_state_just_above_it(self):
        """*Kills it:* `becomes` read at the next scan group, or `further`
        read from it."""
        raw, edge = self._decisive(DECISIVE_STEP)
        assert (edge.was, edge.becomes, edge.further_changes) == (
            "decisive for house", "not decisive", "above")
        # the scan points either side of the edge read the first and third states
        xs = be._scan_grid(0.01, 0.10, be.REVERSAL_SCAN_POINTS)
        below = max(x for x in xs if x < edge.value)
        above = min(x for x in xs if x > edge.value)
        states = [_sweep_says(r, "decisive") for r in run_sweep(
            raw, CONTRACT, [below, edge.value + 1e-4, above])["rows"]]
        assert states == ["decisive for house", "not decisive", "decisive for rent"]

    def test_a_lower_edge_was_the_state_just_below_it(self):
        """The same stretch below a lower edge: the run states 8.00%, decisive
        for rent, and the edge out of its region is read downward from itself.
        *Kills it:* `was` read at the scan group below."""
        raw, edge = self._decisive(DECISIVE_STEP_LOWER)
        assert (edge.was, edge.becomes, edge.further_changes) == (
            "not decisive", "decisive for rent", "below")
        xs = be._scan_grid(0.01, 0.10, be.REVERSAL_SCAN_POINTS)
        below = max(x for x in xs if x < edge.value)
        states = [_sweep_says(r, "decisive") for r in run_sweep(
            raw, CONTRACT, [below, edge.value - 1e-4, edge.value + 1e-4])["rows"]]
        assert states == ["decisive for house", "not decisive", "decisive for rent"]

    def test_a_third_option_inside_one_cell_is_the_state_past_the_edge(self):
        """Three options, through the real solver on a ten-point scan: the
        option most futures call cheapest goes house, condo, rent, and the
        condo's stretch holds no scan point. The edge reads condo past it and
        says the range changes again above.
        *Kills it:* the three-option `becomes` read at the next scan group."""
        raw = copy.deepcopy(THIRD_IN_ONE_CELL)
        spec = load_config_dict(raw)
        det, mc = compute_deterministic(spec), run_monte_carlo(spec)
        free = be._free_curve(raw, CONTRACT, be._priced_options(raw), det, mc,
                              single_path=False)
        scan = [be.field_state(free(x)[0], "mc_best") for x in be._scan_grid(0.01, 0.10, 10)]
        assert "condo" not in scan and scan[0] == "house" and scan[-1] == "rent"
        register = reversal_register(raw, det, mc, scan_points=10)
        (row,) = register.exact
        (edge,) = [b for b in row.boundaries if b.verdict_field == "mc_best"]
        assert (edge.was, edge.becomes, edge.further_changes) == ("house", "condo", "above")
        assert be.field_state(free(edge.value)[0], "mc_best") == "house"
        assert be.field_state(free(edge.value + 1e-6)[0], "mc_best") == "condo"

    def test_a_field_no_crossing_moves_is_read_at_the_nine_points(self, raw, monkeypatch):
        """A solved field with no edge refuses with the scan it rests on, read
        at the pair scan's own nine points; points that disagree with the
        crossings raise rather than print "at every one of 9 points".
        *Kills it:* deleting the check, or raising on a field every point
        agrees on."""
        found = deterministic_boundaries(raw, CONTRACT, 0.01, 0.10)
        (unchanged,) = [u for u in found["unchanged"] if u["attribute"] == "best"]
        assert (unchanged["value"], unchanged["points"]) == ("rent", 9)
        real = be._ranking_at

        def lying(doc, key, value):
            got = real(doc, key, value)
            return {**got, "best": "house"} if value == 0.01 else got

        monkeypatch.setattr(be, "_ranking_at", lying)
        with pytest.raises(ValueError, match="no solved crossing moves best"):
            deterministic_boundaries(raw, CONTRACT, 0.01, 0.10)

    def test_a_run_whose_winner_no_point_reads_says_so_with_its_scan(self, raw, monkeypatch):
        """The run's own winner read at none of the nine points: its refusal
        says so, and a point that reads it raises.
        *Kills it:* deleting the check, or the reason losing its scan."""
        dearer_rent = copy.deepcopy(raw)
        dearer_rent["rent"]["monthly_rent"] *= 3
        other = compute_deterministic(load_config_dict(dearer_rent))
        found = deterministic_boundaries(raw, CONTRACT, 0.01, 0.10, base=other)
        (anomaly,) = [a for a in found["anomalies"] if a["attribute"] == "best"]
        assert (anomaly["value"], anomaly["points"]) == ("condo", 9)
        assert be._scan_reason(CONTRACT, "best", "condo", 9, 0.01, 0.10,
                               in_this_run_only=True) == (
            "not_on_axis",
            "best says 'condo' in this run and at none of 9 points across 1.00%–10.00%")
        real = be._ranking_at

        def lying(doc, key, value):
            got = real(doc, key, value)
            return {**got, "best": "condo"} if value == 0.01 else got

        monkeypatch.setattr(be, "_ranking_at", lying)
        with pytest.raises(ValueError, match="no solved crossing moves best"):
            deterministic_boundaries(raw, CONTRACT, 0.01, 0.10, base=other)


class TestTheNearestEdgeSaysWhenTheRangeChangesAgain:
    """A row reports the NEAREST edge of the region in which the field says
    what this run says (§6). On the two-option example `decisive` changes from
    decisive for house to not decisive at ~6.74% and again, into decisive for
    rent, near ~6.84%; the row printed only the first, and a reader took "not
    decisive" to hold to the top of the bracket. `further_changes` says on
    which side the searched range changes again where no row reports it —
    checked against `--sweep`, never against the scan that produced it."""

    def test_the_two_option_decisive_edge_says_the_range_changes_again_above(
            self, two_option):
        """*Kills it:* dropping the flag, or setting it on every edge."""
        raw, register = two_option
        row = _row(register, CONTRACT)
        flags = {b.verdict_field: b.further_changes for b in row.boundaries}
        assert flags == {"best": None, "runner_up": None, "mc_best": None,
                         "decisive": "above"}
        decisive = next(b for b in row.boundaries if b.verdict_field == "decisive")
        # The change the flag reports is real: past the edge's own `becomes`,
        # --sweep reads a third state inside the bracket.
        top = run_sweep(raw, CONTRACT, [decisive.value + 0.005, row.bracket_high])["rows"]
        seen = {_sweep_says(r, "decisive") for r in top}
        assert seen - {decisive.becomes}, seen

    def test_the_fixture_runner_up_edge_says_the_range_changes_again_below(
            self, raw, register):
        """The renewal row's runner-up changes from house to condo at 2.9549%;
        below, where the winner is the house, the runner-up is not the house —
        a change no row reports. And no other fixture boundary has one."""
        flags = {(row.key, b.verdict_field): b.further_changes
                 for row in register.exact for b in row.boundaries}
        assert flags.pop((RENEWAL, "runner_up")) == "below"
        assert set(flags.values()) == {None}
        runner_up = next(b for b in _row(register, RENEWAL).boundaries
                         if b.verdict_field == "runner_up")
        low = run_sweep(raw, RENEWAL, [0.0101])["rows"][0]
        assert _sweep_says(low, "runner_up") != runner_up.was

    @pytest.mark.parametrize("values, says_now, expected", [
        # a third state past the nearest edge: flagged on that side
        (["A", "B", "C"], "A", [("above", "above")]),
        (["C", "B", "A"], "A", [("below", "below")]),
        # a return INTO the run's answer is the next region's own edge, and is
        # reported, so it is no further change
        (["A", "B", "A"], "A", [("above", None), ("below", None)]),
        # repeated spans of one state are no change (the deterministic regions
        # split at every pair's crossing, not only this field's)
        (["B", "B", "A", "A"], "A", [("below", None)]),
        (["A", "B"], "A", [("above", None)]),
    ], ids=["third-above", "third-below", "return", "repeats", "two"])
    def test_the_rule(self, values, says_now, expected):
        """*Kills it:* counting a return into the run's answer, or a repeated
        span, as a further change."""
        span = [(float(i), float(i + 1)) for i in range(len(values))]
        found, anomaly = be._region_boundaries(
            "house.mortgage_rate", "best", says_now, values, span,
            lambda i, step: ((float(i), values[i - 1]) if step < 0
                             else (float(i + 1), values[i + 1])), (0.0, 1.0))
        assert anomaly is None
        assert [(b["direction"], b["further"]) for b in found] == expected


# ---------------------------------------------------------------------------
# Whose figure the stated value is (the read-back's own classifier)
# ---------------------------------------------------------------------------

class TestWhoseFigureTheStatedValueIs:
    """A row's boundaries are solved on the config's figures whoever typed
    them, so "solved on your own figures" is true only of a figure the user
    stated. The fixture's renewal ladder is assistant-typed and its contract
    rate an anchor's, and the read-back of the same run says so; each row now
    carries that class, from the same classifier, for the words to key on."""

    def test_each_fixture_row_carries_the_echo_s_own_class(self, raw, register):
        echo = load_config_dict(raw).sources
        assert _row(register, RENEWAL).stated_source == "assistant"
        assert _row(register, CONTRACT).stated_source == "anchor"
        for row in register.exact:
            assert row.stated_source == echo.classify(row.key)

    def test_a_config_with_no_sources_block_reads_unattributed(self, two_option):
        """Silence is reported, never read as the user's answer."""
        _, register = two_option
        assert _row(register, CONTRACT).stated_source == "unattributed"

    @pytest.mark.parametrize("declared,expected", [
        ("user", "user"), ("assistant", "assistant"), (None, "unattributed")],
        ids=["user", "assistant", "undeclared"])
    def test_one_sources_entry_moves_the_class(self, raw, declared, expected):
        """Change one `sources:` entry and the class follows it — the test §5
        names for the provenance gate, applied to the stated value."""
        doc = copy.deepcopy(raw)
        if declared is None:
            del doc["sources"][RENEWAL]
        else:
            doc["sources"][RENEWAL] = declared
        assert be._stated_source(load_config_dict(doc), RENEWAL) == expected

    def test_the_stated_path_rows_carry_no_sentence_about_who_stated_it(self, register):
        """A structural zero carries its kind and no sentence (§0.1 item 35):
        whose figure the stated value is travels as the exact row's
        `stated_source`, the read-back's own class."""
        zeros = [z for z in register.structural_zeros if z.kind == "stated_path"]
        assert len(zeros) == 2
        for zero in zeros:
            assert not hasattr(zero, "reason")
            assert _row(register, zero.reversal_key).stated_source in (
                "user", "assistant", "anchor", "unattributed")


# ---------------------------------------------------------------------------
# One solver, two consumers (spec §0; T12)
# ---------------------------------------------------------------------------

class TestOneSolverTwoConsumers:

    def test_the_solved_boundary_is_solve_crossings_own_figure(self, raw, register):
        """Re-solved here through `solve_crossings` with this test's own
        `totals_at`: EXACT equality, because the register reports that solver's
        figure rather than a bisection of its own."""
        lo, hi = RATE_BRACKETS["mortgage_rate"]

        def totals_at(v):
            det = compute_deterministic(load_at(raw, RENEWAL, v))
            return det.house.total_pv, det.rent.total_pv

        mine = solve_crossings(RENEWAL, ("house", "rent"), lo, hi, totals_at)
        assert len(mine["break_evens"]) == 1
        assert _boundary(_row(register, RENEWAL), "best").value == \
            mine["break_evens"][0]["value"]

    def test_it_is_also_break_evens_own_figure_on_a_two_option_config(self, raw):
        """`--break-even` refuses a three-option config, so the two surfaces are
        compared where both can speak. `deterministic_boundaries` needs no Monte
        Carlo at all, which is also the shape the unpriced-dimensions
        renewal-flip line is planned to call it in (that slice is not built)."""
        two = _without(raw, "condo")
        lo, hi = RATE_BRACKETS["mortgage_rate"]
        cli = solve_break_even(two, RENEWAL, None, None)
        mine = deterministic_boundaries(two, RENEWAL, lo, hi)
        assert [b["value"] for b in cli["break_evens"]] == \
            [c["value"] for c in mine["crossings"]]
        best = [b for b in mine["boundaries"] if b["attribute"] == "best"]
        assert [b["value"] for b in best] == [cli["break_evens"][0]["value"]]

    def test_the_two_reversal_kinds_share_no_field_set(self, register):
        """§0's ruling, encoded: `list(exact) + list(estimated)` must not render
        as one ordered table. The types carry different fields, so a formatter
        that concatenated them would break on the first row."""
        exact_fields = {f.name for f in ExactReversal.__dataclass_fields__.values()}
        estimated_fields = {f.name for f in EstimatedReversal.__dataclass_fields__.values()}
        assert exact_fields != estimated_fields
        assert "probe_paths" in exact_fields and "probe_paths" not in estimated_fields
        # And slice 1 populates the estimated kind never: §6 refuses a key that
        # fails the exactness gate rather than estimating it.
        assert register.estimated == ()


# ---------------------------------------------------------------------------
# The exactness gate (spec T10)
# ---------------------------------------------------------------------------

class TestTheExactnessGate:

    def test_both_financing_keys_license(self, raw):
        for key in (RENEWAL, CONTRACT):
            gate = reversal_gate(raw, key, 0.10, paths=200)
            assert gate["licensed"], gate
            assert gate["others_bit_identical"]
            # Fifteen orders of magnitude from the refusals below, so nothing
            # here rests on where the tolerance sits.
            assert gate["worst_deviation_over_sd"] < 1e-12
            assert gate["paths"] == 200 and gate["names"] == "house"

    @pytest.mark.parametrize("key,probe", [("rent.monthly_rent", 1880 * 4.0),
                                           ("house.value_growth_rate", 0.05)])
    def test_a_key_whose_shift_is_not_constant_is_refused(self, raw, key, probe):
        """Clause (b). The free curve would be wrong by percentage points here,
        not by rounding."""
        gate = reversal_gate(raw, key, probe, paths=200)
        assert not gate["licensed"]
        assert gate["others_bit_identical"]          # it is clause (b) that fires
        assert gate["worst_deviation_over_sd"] > 1.0
        assert gate["why"].startswith(
            f"moving {key} shifts {key.split('.')[0]} by a different amount on "
            f"different paths (worst ")

    def test_identical_paths_license_a_constant_shift(self):
        """On a single-path config every path carries the same float, and
        rounding in `np.std` and in `x - mean(x)` returns one ULP for both — a
        raw ratio of exactly 1.0, which refuses with "shifts condo by a
        DIFFERENT amount on different paths" when not one path differs. The
        shift of an identical set of paths is one constant by construction."""
        raw = yaml.safe_load(SINGLE_PATH.read_text(encoding="utf-8"))
        assert single_path_run(load_config_dict(raw))
        gate = reversal_gate(raw, "condo.mortgage_rate", 0.10, paths=200)
        assert gate["others_bit_identical"]
        assert gate["worst_deviation_over_sd"] == 0.0
        assert gate["licensed"], gate

    @staticmethod
    def _poisoned(option, call, value, index=3):
        """`simulate` for the gate with ONE present value replaced: `call` 1 is
        the run at the stated value, 2 the run at the probe. The real engine
        prices both; only the one figure is doctored."""
        calls = []

        def simulate(spec):
            result = run_monte_carlo(spec)
            calls.append(spec)
            if len(calls) == call:
                pvs = np.array(getattr(result, option).pvs, dtype=float)
                pvs[index] = value
                getattr(result, option).pvs = pvs
            return result

        return simulate

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf],
                             ids=["nan", "inf", "-inf"])
    @pytest.mark.parametrize("call,where", [
        (1, "with house.mortgage_rate as stated"),
        (2, "with house.mortgage_rate at 10.00%"),
    ], ids=["stated", "at"])
    def test_a_non_finite_present_value_in_the_named_option_refuses_by_name(
            self, raw, value, call, where):
        """Both sides failed OPEN before: a NaN in the stated run's array made
        `np.ptp(x) > 0` False and read as a zero deviation, and a NaN in the
        probe's array made the deviation NaN, which `NaN > tolerance` never
        exceeds. Either way the gate licensed a curve nothing had measured.
        *Kills it:* deleting the non-finite refusal."""
        gate = reversal_gate(raw, CONTRACT, 0.10, paths=200,
                             simulate=self._poisoned("house", call, value))
        assert not gate["licensed"]
        assert gate["why"] == (
            f"a present value this gate compares is not a finite number: house "
            f"{where} (1 of 200 paths)")
        assert math.isnan(gate["worst_deviation_over_sd"])
        assert gate["others_bit_identical"] is None

    def test_a_non_finite_value_in_another_option_is_named_as_that_not_as_a_stream(
            self, raw):
        """`array_equal` is False on NaN, so a NaN in the condo — which the key
        does not name — used to refuse under "it changes the draw stream",
        which is not what happened."""
        gate = reversal_gate(raw, CONTRACT, 0.10, paths=200,
                             simulate=self._poisoned("condo", 2, math.nan))
        assert not gate["licensed"]
        assert gate["why"] == (
            "a present value this gate compares is not a finite number: condo with "
            "house.mortgage_rate at 10.00% (1 of 200 paths)")
        assert "which it does not name" not in gate["why"]

    def test_the_same_seam_with_a_finite_constant_still_licenses(self, raw):
        """The nearest legal call: the same one-figure edit, but to a finite
        value on every path — one constant, which is exactly what licenses.
        *Kills it:* a refusal widened past non-finite values."""
        calls = []

        def constant(spec):
            result = run_monte_carlo(spec)
            calls.append(spec)
            if len(calls) == 2:
                result.house.pvs = result.house.pvs + 1234.5
            return result

        gate = reversal_gate(raw, CONTRACT, 0.10, paths=200, simulate=constant)
        assert gate["licensed"], gate
        assert gate["others_bit_identical"] is True

    def test_the_refusal_reaches_the_row_a_reader_sees(self, raw, base):
        """Through `reversal_register`: the row moves to the estimated kind
        with every boundary refused under the gate's own sentence, and its
        deviation is NaN — not a number is what was measured."""
        _, det, mc = base
        gate_runs = []

        def poisoned_probe(spec):
            result = run_monte_carlo(spec)
            # The gate prices 200 paths; the confirming re-simulations price the
            # run's own 2,000. Gate runs come in (stated, probe) pairs, one pair
            # per key in candidate order: RENEWAL, then CONTRACT.
            if spec.simulation.num_sims == 200:
                gate_runs.append(spec)
            if spec.simulation.num_sims == 200 and len(gate_runs) == 4:
                pvs = np.array(result.house.pvs, dtype=float)
                pvs[0] = math.nan
                result.house.pvs = pvs
            return result

        register = reversal_register(raw, det, mc, simulate=poisoned_probe)
        assert [r.key for r in register.estimated] == [CONTRACT]
        row = register.estimated[0]
        assert math.isnan(row.max_path_deviation_over_sd)
        assert {r.verdict_field for r in row.refused_boundaries} == set(BOUNDARY_FIELDS)
        for refusal in row.refused_boundaries:
            assert refusal.reason == (
                "a present value this gate compares is not a finite number: house with "
                "house.mortgage_rate at 10.00% (1 of 200 paths)")

    @pytest.mark.parametrize("side", ["before", "after"])
    def test_the_shift_measure_itself_never_admits_a_nan(self, side):
        """Below the refusal, the measure must not fail open on its own: in the
        `> 0` form a NaN read as "no spread" and came back 0.0.
        *Kills it:* reverting the delta half of the identical-paths guard to
        `np.ptp(delta) > 0`."""
        before = np.array([100.0, 101.0, 102.0, 103.0])
        after = before + 5.0
        (before if side == "before" else after)[1] = math.nan
        measured = _shift_deviation_over_sd(before, after)
        assert not measured <= REVERSAL_GATE_TOLERANCE

    def test_a_deviation_that_is_not_a_number_never_licenses(self, raw, monkeypatch):
        """The comparison fails closed too: `NaN > tolerance` is False, so the
        old `deviation > tolerance` test licensed a NaN.
        *Kills it:* writing the licence test as `deviation > tolerance`."""
        monkeypatch.setattr(be, "_shift_deviation_over_sd", lambda before, after: math.nan)
        gate = reversal_gate(raw, CONTRACT, 0.10, paths=200)
        assert not gate["licensed"]
        assert "a different amount on different paths" in gate["why"]
        # ...and the reason a reader is shown says so in words: it printed
        # "worst nan of its own sd".
        assert "(its deviation over its own s.d. is not a number)" in gate["why"]
        assert "nan" not in gate["why"].lower().split()

    def test_a_finite_deviation_prints_as_a_multiple_of_the_s_d(self, raw, monkeypatch):
        """The nearest legal call to the two above: a finite figure that fails
        the tolerance prints as the multiple of the s.d. it is, against the
        tolerance — words are for a figure that is not a multiple of anything,
        not for every refusal.
        *Kills it:* wording every refused figure as unmeasured."""
        monkeypatch.setattr(be, "_shift_deviation_over_sd", lambda before, after: 2.7)
        gate = reversal_gate(raw, CONTRACT, 0.10, paths=200)
        assert not gate["licensed"]
        assert "(worst 2.70e+00 of its own s.d., against 1e-09)" in gate["why"]
        assert "not a number" not in gate["why"]
        assert "differs across paths" not in gate["why"]

    def test_identical_paths_under_a_varying_shift_read_infinitely_far(self):
        """The s.d. half of the identical-paths guard. Every path of the
        single-path config's condo is one float, and `np.std` of them is one
        ULP rather than zero — so without the guard a shift that varies path
        by path is divided by rounding noise and reported as a large FINITE
        multiple of an s.d. the option does not have.
        *Kills it:* deleting the `np.ptp(before) == 0` half."""
        raw = yaml.safe_load(SINGLE_PATH.read_text(encoding="utf-8"))
        seen = []

        def varying(spec):
            result = run_monte_carlo(spec)
            seen.append(np.array(result.condo.pvs))
            if len(seen) == 2:
                result.condo.pvs = result.condo.pvs + np.arange(result.condo.pvs.size) * 1.0
            return result

        gate = reversal_gate(raw, "condo.mortgage_rate", 0.10, paths=200, simulate=varying)
        stated = seen[0]
        assert np.ptp(stated) == 0.0 and float(np.std(stated)) > 0.0, (
            "the precondition that makes this test able to fail: identical paths "
            "whose np.std is rounding noise rather than zero")
        assert gate["worst_deviation_over_sd"] == math.inf
        assert not gate["licensed"]
        # The reason a reader is shown: it printed "worst inf of its own sd".
        assert ("(condo is priced the same on every path as stated, and its shift "
                "differs across paths)") in gate["why"]
        assert " inf " not in gate["why"]

    def test_a_key_that_moves_the_draw_stream_is_refused_by_clause_a(self, raw):
        """Clause (a), which nothing else catches: `rent.reset_hazard` names
        `rent`, and `_sample_reset_year` returns early inside its own year
        loop, so the draw COUNT depends on the outcome and the condo's and the
        house's arrays move too. Drop clause (a) and this key licenses."""
        gate = reversal_gate(raw, "rent.reset_hazard", 0.20, paths=200)
        assert not gate["licensed"]
        assert not gate["others_bit_identical"]
        assert set(gate["moved_others"]) == {"condo", "house"}
        assert gate["why"] == "moving rent.reset_hazard moves condo, house, which it does not name"

    def test_a_key_that_fails_the_gate_carries_no_boundary_and_says_why(self, raw, base):
        """The gate is load-bearing, not decorative. No financing-leg key can
        fail it — `_financing_pv` shifts every path by one constant, which is
        why slice 1 is these two keys — so the branch is reached by injecting
        the failure the gate exists to catch: a shift that differs path by
        path. All four kinds are then refused with the gate's own reason, and
        the row moves to the kind whose deviation FAILED the gate rather than
        vanishing.
        """
        _, det, mc = base
        calls = []

        def non_constant_shift(spec):
            result = run_monte_carlo(spec)
            calls.append(spec)
            if len(calls) == 2:            # the gate's probe run
                result.house.pvs = result.house.pvs + np.arange(result.house.pvs.size) * 1.0
            return result

        register = reversal_register(raw, det, mc, simulate=non_constant_shift)
        assert [r.key for r in register.exact] == [CONTRACT]
        assert [r.key for r in register.estimated] == [RENEWAL]
        row = register.estimated[0]
        assert row.boundaries == ()
        assert {r.verdict_field for r in row.refused_boundaries} == set(BOUNDARY_FIELDS)
        assert all("a different amount on different paths" in r.reason
                   for r in row.refused_boundaries)
        assert row.max_path_deviation_over_sd > 1e-9
        assert row.stated_source == "assistant"   # whose figure travels with either kind


# ---------------------------------------------------------------------------
# The confirming re-simulation (spec T11)
# ---------------------------------------------------------------------------

class TestTheConfirmingResimulation:

    def test_every_reported_boundary_is_confirmed_by_a_full_re_simulation(self, register):
        """Measured: identical to the digit, both ways, at every boundary — and
        that includes the solved ones, whose confirmation is what licenses the
        free curve the sampled boundary is read off.

        Asserted per KIND, because the two kinds make different claims about
        the same re-simulation: on a sampled boundary the curve's own
        probabilities are stored beside the confirming ones and the two must
        agree; on a solved one the confirming set is CORROBORATION of a value
        that read no path, so it is non-empty here and there is no curve field
        to compare it against.
        """
        reported = [b for row in register.exact for b in row.boundaries]
        assert len(reported) == 5, reported
        for boundary in reported:
            assert boundary.confirming_probabilities  # a re-simulation ran and agreed
            if isinstance(boundary, SampledBoundary):
                assert boundary.curve_probabilities == boundary.confirming_probabilities
                assert boundary.curve_probabilities  # not an empty tuple comparing equal
            else:
                assert not hasattr(boundary, "curve_probabilities")

    def test_a_disagreeing_re_simulation_withholds_every_boundary(self, raw, base):
        """The check that can fail. `simulate` is the seam: a re-simulation that
        disagrees with the free curve moves each boundary out of `boundaries`
        and into `refused_boundaries` with its reason. Without this, "confirmed"
        would be a flag that cannot come out false."""
        _, det, mc = base

        def disagreeing(spec):
            result = run_monte_carlo(spec)
            # The arrays are untouched, so the exactness gate still licenses;
            # only the probabilities the confirmation compares are moved.
            result.prob_condo_cheapest = (result.prob_condo_cheapest or 0.0) + 0.05
            return result

        register = reversal_register(raw, det, mc, simulate=disagreeing)
        row = _row(register, RENEWAL)
        assert row.boundaries == ()
        assert {r.verdict_field for r in row.refused_boundaries} == set(BOUNDARY_FIELDS)
        reason = _refusal(row, "best").reason
        assert reason.startswith("the re-simulation at ") and ", and the free curve gives " in reason
        # the two sets of figures it names are the two that disagreed
        gave, curve = reason.split(" gives ", 1)[1].split(", and the free curve gives ")
        assert gave != curve

    def test_a_futures_boundary_inside_monte_carlo_noise_is_not_reported(self, raw, register):
        """Refusal (i), asserted in BOTH directions so neither half can pass
        vacuously. At the fixture's 2,000 paths the majority boundary is
        resolved by a wide margin and reported; at 100 paths the same boundary
        moves the probabilities it turns on by 0.0800 against a 2·SE of 0.0960
        and is refused by name. The deterministic pair reads no path at all, so
        it reports identically at both counts — which is what makes this a test
        of the identification rule rather than of the solver."""
        assert _boundary(_row(register, RENEWAL), "mc_best")

        thin = _set(raw, "simulation.num_sims", 100)
        spec = load_config_dict(thin)
        row = _row(reversal_register(thin, compute_deterministic(spec),
                                     run_monte_carlo(spec)), RENEWAL)
        assert [b.verdict_field for b in row.boundaries] == ["best", "runner_up"]
        assert [b.value for b in row.boundaries] == [
            pytest.approx(BEST_FLIPS_AT, abs=1e-9),
            pytest.approx(RUNNER_UP_SWAPS_AT, abs=1e-9)]
        # Same values at a twentieth of the paths, and the type says why they
        # could not have moved: the solved kind carries no sample to move with.
        assert all(isinstance(b, SolvedBoundary) for b in row.boundaries)
        reason = _refusal(row, "mc_best").reason
        assert reason.startswith("across the bracket the probabilities this boundary "
                                 "turns on move by ")
        assert reason.endswith(" on 100 paths")
        moved, noise = (float(x) for x in re.findall(r"\d\.\d{4}", reason))
        assert moved <= noise


# ---------------------------------------------------------------------------
# The trap the spec names: the stated path is not a point on the axis
# ---------------------------------------------------------------------------

class TestTheFlatteningTrap:

    def test_the_renewal_row_says_how_its_axis_was_built(self, register):
        """§0.1 item 41: a construction fact, and nothing after it — no "so",
        and no grid, threshold or sweep the block does not print."""
        note = _row(register, RENEWAL).path_note
        assert note == ("each crossing on this key is priced with the stated path "
                        "(4.60%, 5.00%, 4.80%, 4.40%) replaced by one rate at every "
                        "renewal")

    def test_the_stated_path_is_reported_whole_and_unflattened(self, register):
        """A row that printed one figure where the user stated four would have
        erased the trap it exists to name."""
        assert _row(register, RENEWAL).stated_formatted == "4.60%, 5.00%, 4.80%, 4.40%"

    def test_a_scalar_key_carries_no_flattening_note(self, register):
        row = _row(register, CONTRACT)
        assert row.path_note is None
        assert row.stated_formatted == "4.35%"


# ---------------------------------------------------------------------------
# The bracket's own width has a source class (§0.1 ruling 9)
# ---------------------------------------------------------------------------

class TestTheBracket:

    def test_the_renewal_ladder_searches_the_contract_rates_own_bracket(self):
        """Read from that entry rather than restated, so widening one widens
        both and the two cannot drift apart."""
        assert RATE_BRACKETS["mortgage_renewal_rates"] == RATE_BRACKETS["mortgage_rate"]
        assert reversal_bracket(RENEWAL) == (0.01, 0.10)

    def test_every_row_says_whose_figure_the_bracket_is(self, register):
        """Converting an honest refusal into an answer is a stronger act than
        replacing a silent default, so the width the register chose is printed
        with its class rather than assumed."""
        assert BRACKET_SOURCE == "set in the engine"
        for row in register.exact:
            assert row.bracket_source == "set in the engine"
            assert (row.bracket_low, row.bracket_high) == RATE_BRACKETS["mortgage_rate"]

    def test_a_widen_hint_never_offers_a_negative_renewal_rate(self):
        """The loader refuses `mortgage_renewal_rates < 0`, so a hint below zero
        would name a bracket no point of which loads."""
        assert floor_at_zero(RENEWAL)

    def test_every_reported_boundary_lies_inside_the_bracket_it_searched(self, register):
        for row in register.exact:
            for boundary in row.boundaries:
                assert row.bracket_low <= boundary.value <= row.bracket_high

    def test_the_axis_carries_its_published_references(self, register):
        """The anchored rates on the axis, as figures with their anchors: on
        this semi-annual axis no note, because nothing was converted and what
        a reference licenses is interpretation (§0.1 item 35)."""
        for key in (RENEWAL, CONTRACT):
            refs = {r.anchor: r for r in _row(register, key).references}
            assert set(refs) == {"mortgage_rate.contracted_5y_uninsured",
                                 "mortgage_rate.contracted_5y_insured",
                                 "mortgage_rate.posted_5y"}
            assert refs["mortgage_rate.posted_5y"].formatted == "6.09%"
            assert all(r.note is None for r in refs.values())

    def test_a_converted_reference_names_the_figure_as_published(self):
        """The one note a reference carries: on an effective-annual axis the
        semi-annual anchor is converted, and the note names it as published."""
        refs = {r.anchor: r for r in be._axis_references(CONTRACT, "effective_annual")}
        posted = refs["mortgage_rate.posted_5y"]
        assert posted.note == "published as 6.09% compounded semi-annually"
        assert posted.formatted != "6.09%"


# ---------------------------------------------------------------------------
# Admission — a measurement, and what it is allowed to exclude
# ---------------------------------------------------------------------------

class TestAdmission:

    def test_an_all_cash_option_contributes_no_candidate(self, raw, register):
        """The fixture's condo is all-cash. The loader refuses both financing
        keys on it outright, so the admission MEASUREMENT never gets a chance
        and the stated-key rule is what excludes it — a loader refusal reported
        as a measured absence of effect would be a false claim."""
        assert reversal_candidates(raw) == [(RENEWAL, "house"), (CONTRACT, "house")]
        assert all(row.key.startswith("house.") for row in register.exact)
        for key in ("condo.mortgage_rate", "condo.mortgage_renewal_rates"):
            with pytest.raises(Exception):
                load_at(raw, key, 0.05)

    def test_an_inert_renewal_ladder_is_measured_out_rather_than_printed_flat(self, raw):
        """A term at or past the amortization renews nothing, so the stated
        ladder is priced nowhere. The key IS stated, so only the measurement can
        exclude it — and it must, or the row would print a flat curve under a
        heading that reads "what would have to change"."""
        inert = _set(raw, "house.mortgage_renewal_years", 25)
        admitted, record = reversal_admission(inert, RENEWAL, 0.10)
        assert not admitted
        assert "no option's present value moves" in record["why"]

    def test_the_ladder_of_this_fixture_is_admitted_by_measurement(self, raw, base):
        _, det, _ = base
        admitted, record = reversal_admission(raw, RENEWAL, 0.10, base=det)
        assert admitted and record["moves"] == ["house"]
        assert record["deltas"]["house"] > 0

    def test_a_dispersion_key_is_never_a_candidate(self, raw):
        """By construction, not by omission: `compute_deterministic` reads no
        dispersion input, so a curve over a vol key is flat and a flat curve
        under this heading would say "this risk does not affect the verdict"
        about every risk."""
        for key in ("simulation.investment_return_vol", "simulation.value_growth_vol",
                    "rent.reset_hazard", "simulation.corr_inflation_house"):
            assert reversal_bracket(key) is None
            assert key not in [k for k, _ in reversal_candidates(raw)]


# ---------------------------------------------------------------------------
# The structural zeros, which live here by ruling (§0.1 item 5)
# ---------------------------------------------------------------------------

class TestTheStructuralZeros:

    def test_the_stated_path_row_joins_to_the_numbers_it_carries(self, register):
        """A reader who sees a dash concludes renewal was weighed and found
        irrelevant. The row instead joins to the reversal that carries three
        solved rates."""
        zeros = {z.reversal_key: z for z in register.structural_zeros
                 if z.kind == "stated_path"}
        assert set(zeros) == {RENEWAL, CONTRACT}
        renewal = zeros[RENEWAL]
        assert renewal.label == "the renewal rate"
        assert zeros[CONTRACT].label == "the contract rate"
        assert renewal.keys == (RENEWAL,) and renewal.channel_id is None
        assert _row(register, renewal.reversal_key).boundaries

    def test_the_register_names_only_stated_paths(self, register):
        """Whether a stream draws, and whether its re-draw moves a present
        value, is measured on the block's futures by the assembler, which this
        register never sees; the income block's row is one of those
        (`decomposition_run._dead_draw_rows`). This register once emitted it
        from the config alone, and said "drawn" over pay drops that draw
        nothing. *Kills it:* restoring that row here."""
        assert {z.kind for z in register.structural_zeros} == {"stated_path"}

    def test_the_register_names_no_dead_draw_row_of_its_own(self, raw):
        """A stream that draws and moves nothing is decided in ONE place, the
        assembler's `_dead_draw_rows`, on its own measurement. This register
        once carried a second copy for the real-mode economy, keyed on a
        narrower condition than the assembler's, so the two could word one
        channel two ways. *Kills it:* restoring that copy."""
        real = copy.deepcopy(raw)
        real["economic"]["mode"] = "real"
        for name in ("condo", "house", "other", "event_cost"):
            real["simulation"][f"corr_inflation_{name}"] = 0.0
        spec = load_config_dict(real)
        register = reversal_register(real, compute_deterministic(spec), run_monte_carlo(spec))
        assert not [z for z in register.structural_zeros if z.kind == "dead_draw"]

    def test_a_nominal_run_has_no_dead_draw_row(self, register):
        """The fixture is nominal with live correlations, so the channel is not
        dead and no row claims it is."""
        assert not [z for z in register.structural_zeros if z.kind == "dead_draw"]


# ---------------------------------------------------------------------------
# Refusals (spec §8)
# ---------------------------------------------------------------------------

class TestRefusals:

    def test_without_futures_the_register_still_carries_its_solved_half(self, raw, base):
        """§8 refusal 2 refuses the BLOCK on a path-free run; this function is
        not the block. The old one-shape boundary REQUIRED a curve and a
        confirming set of probabilities, so a register with no futures came back
        empty and two perfectly computable figures vanished — a reader saw
        "nothing here" where the truth was "1.61%, and it reads no path".

        Now the solved half answers: the same values, to the digit, as the run
        WITH futures reports, because `deterministic_boundaries` reads no path
        in either case. Nothing corroborates them, and the empty
        `confirming_probabilities` is what says so rather than an omission.
        """
        _, det, _ = base
        register = reversal_register(raw, det, None)
        assert register.estimated == ()
        row = _row(register, RENEWAL)
        assert [b.verdict_field for b in row.boundaries] == ["best", "runner_up"]
        assert [b.value for b in row.boundaries] == [
            pytest.approx(BEST_FLIPS_AT, abs=1e-9),
            pytest.approx(RUNNER_UP_SWAPS_AT, abs=1e-9)]
        for boundary in row.boundaries:
            assert isinstance(boundary, SolvedBoundary)
            assert boundary.confirming_probabilities == ()
        _assert_the_no_futures_reasons_are_each_true(row)
        # The stated-path zeros come with it: they join to this row's solved
        # rates, and a renewal ladder printed as a dash is the whole finding.
        assert [z.reversal_key for z in register.structural_zeros
                if z.kind == "stated_path"] == [RENEWAL, CONTRACT]
        # One solver, two consumers: `deterministic_boundaries`, which reads
        # no path either, reports the same figure.
        lo, hi = RATE_BRACKETS["mortgage_rate"]
        solved = deterministic_boundaries(raw, RENEWAL, lo, hi, base=det)
        best = [b for b in solved["boundaries"] if b["attribute"] == "best"]
        assert [b["value"] for b in best] == [pytest.approx(BEST_FLIPS_AT, abs=1e-9)]

    def test_all_four_kinds_are_answered_on_a_run_with_no_futures_too(self, raw, base):
        """The property that makes an absence unreadable as "nothing here", on
        the branch where half the fields cannot be located at all: every one of
        the four is either carried or refused BY NAME, on every row, and never
        silently missing."""
        _, det, _ = base
        register = reversal_register(raw, det, None)
        assert register.exact, "no exact reversal, so this test proves nothing"
        for row in register.exact:
            answered = [b.verdict_field for b in row.boundaries]
            refused = [r.verdict_field for r in row.refused_boundaries]
            assert set(answered) | set(refused) == set(BOUNDARY_FIELDS)
            assert not set(answered) & set(refused)
            for refusal in row.refused_boundaries:
                assert refusal.reason and refusal.reason.strip()

    @pytest.mark.parametrize("with_mc", [False, True], ids=["no-monte-carlo", "single-path"])
    def test_a_single_path_run_is_a_run_with_no_futures(self, with_mc):
        """The other way a run has no futures: a config whose every uncertainty
        input is off. Its Monte Carlo object exists and holds N copies of one
        path, so there is no curve to read a sampled boundary off — with or
        without that object in hand the register answers with the solved half,
        uncorroborated, and refuses the futures pair by name."""
        raw = yaml.safe_load(SINGLE_PATH.read_text(encoding="utf-8"))
        spec = load_config_dict(raw)
        assert single_path_run(spec)
        det = compute_deterministic(spec)
        register = reversal_register(raw, det, run_monte_carlo(spec) if with_mc else None)
        assert register.estimated == ()
        row = _row(register, "condo.mortgage_rate")
        lo, hi = RATE_BRACKETS["mortgage_rate"]
        solved = deterministic_boundaries(raw, "condo.mortgage_rate", lo, hi, base=det)
        expected = [(b["attribute"], b["value"]) for b in solved["boundaries"]]
        assert expected, "no crossing in the bracket, so this test proves nothing"
        assert [(b.verdict_field, b.value) for b in row.boundaries] == expected
        for boundary in row.boundaries:
            assert isinstance(boundary, SolvedBoundary)
            assert boundary.confirming_probabilities == ()
        _assert_the_no_futures_reasons_are_each_true(row)

    def test_without_futures_decisiveness_still_changes_so_its_reason_cannot_be_none(self):
        """Why the decisive sentence had to change. On the shipped single-path
        config the verdict IS decisive at some rates of the bracket and not at
        others — read off the central margin, with no futures anywhere — so
        "decisive is read off this run's futures and this run has none" told
        the reader something false about a field that exists and moves."""
        raw = yaml.safe_load(SINGLE_PATH.read_text(encoding="utf-8"))
        assert single_path_run(load_config_dict(raw))
        rows = run_sweep(raw, "condo.mortgage_rate", [0.044, 0.048, 0.053],
                         monte_carlo=False)["rows"]
        assert [(r["decisive"], r["rule"]) for r in rows] == [
            (True, "margin_band"), (False, "margin_band"), (True, "margin_band")]
        det = compute_deterministic(load_config_dict(raw))
        row = _row(reversal_register(raw, det, None), "condo.mortgage_rate")
        _assert_the_no_futures_reasons_are_each_true(row)

    def test_a_single_option_config_has_no_winner_to_reverse(self, raw):
        one = _without(raw, "condo", "rent")
        spec = load_config_dict(one)
        register = reversal_register(one, compute_deterministic(spec), run_monte_carlo(spec))
        assert (register.exact, register.estimated, register.structural_zeros) == ((), (), ())


def test_the_figure_checks_raise_where_nothing_passes():
    """Each check, alone: a crossing whose field never says `was` at any
    floored figure, and a stated figure equal to a crossing's value, which a
    rounding upward never prints equal to that crossing's floored figure."""
    with pytest.raises(ValueError, match="the printed-rate check"):
        be.printed_crossing("house.mortgage_rate", "decisive", 0.0627, "not decisive",
                            lambda v: "decisive for rent", 0.01)
    assert be.printed_crossing("house.mortgage_rate", "decisive", 0.0627123, "x",
                               lambda v: "x" if v >= 0.06271 else "y", 0.01) == "6.271%"
    with pytest.raises(ValueError, match="the figure-order check"):
        be.ordered_figure("house.mortgage_rate", 0.0627126,
                          [(0.0627126, be.floored_rate(0.0627126, 4))])
    assert be.ordered_figure("house.mortgage_rate", 0.06273,
                             [(0.0627246, "6.2724%")]) == "6.273%"
    # a floored figure below the bracket is off the axis searched, and passed
    # over for a finer one
    assert be.printed_crossing("house.mortgage_rate", "best", 0.0100003, "x",
                               lambda v: "x", 0.0100001) == "1.00003%"
    # a stated figure between a printed crossing and its value holds the
    # crossing's figure above it
    assert be.printed_crossing("house.mortgage_rate", "mc_best", 0.06278, "house",
                               lambda v: "house", 0.01, figures=(0.06273,)) == "6.278%"

# ---------------------------------------------------------------------------
# The library's own seams, reached by a direct call
# ---------------------------------------------------------------------------

# The refusal a futures field writes when the run's own state is read at no
# point of its scan.
_SAYS_SO_NOWHERE = re.compile(
    r"^(?P<field>best|runner_up|mc_best|decisive) says '(?P<value>[^']+)' in this run "
    r"and at none of (?P<n>\d+) points across (?P<lo>\d+\.\d+%)–(?P<hi>\d+\.\d+%)$")


def test_a_field_the_axis_never_reproduces_says_so():
    """"in this run and at none of N points": the run's own state is read at
    no point of the scan. A futures field on a free curve that never names the
    run's own answer, and a solved field on an axis whose nine points never
    read the run's own winner, each state the scan the refusal rests on."""
    xs = []

    def free(x):
        xs.append(x)
        return types.SimpleNamespace(mc_best="condo" if x < 0.05 else "house"), {}

    found, why = be._futures_field_boundaries(
        {}, "house.mortgage_rate", "mc_best", free,
        types.SimpleNamespace(mc_best="rent"), 0.01, 0.10,
        scan_points=be.REVERSAL_SCAN_POINTS)
    assert found == [] and why[0] == "not_on_axis"
    m = _SAYS_SO_NOWHERE.match(why[1])
    assert m and (m["field"], m["value"], int(m["n"])) == ("mc_best", "rent", 65)
    assert sorted(set(xs)) == pytest.approx(
        [0.01 + 0.09 * i / 64 for i in range(65)])
    assert "rent" not in {free(x)[0].mc_best for x in list(xs)}


def test_a_boundary_with_no_probability_is_not_identified():
    record = be._identification("mc_best", {"was": "condo", "becomes": "house"},
                                {"lo": {}, "hi": {}, "at": {}}, "condo", 100)
    assert not record["identified"] and record["watched"] == []
    assert record["why"] == "no probability is attached to this boundary"


def test_a_gate_handed_no_figures_for_its_option_raises():
    """The key's option is in the config, so a run with no present values for
    it is a producer defect: the gate raises rather than printing a reason for
    a case the engine cannot produce."""
    raw = yaml.safe_load(TWO_OPTION.read_text(encoding="utf-8"))

    def without_the_house(spec):
        return dataclasses.replace(run_monte_carlo(spec), house=None)

    with pytest.raises(ValueError, match="nothing to measure"):
        be.reversal_gate(raw, "house.mortgage_rate", 0.10, paths=40,
                         simulate=without_the_house)


def test_a_register_on_one_option_has_no_verdict_to_reverse():
    spec = load_config_dict(copy.deepcopy(CONDO_ONLY))
    register = be.reversal_register(copy.deepcopy(CONDO_ONLY), compute_deterministic(spec),
                                    run_monte_carlo(spec))
    assert [o for o in ("condo", "house", "rent") if o in CONDO_ONLY] == ["condo"]
    assert register.exact == () and register.estimated == ()
    assert register.no_distance_reason == "fewer than two options are priced"


def test_a_key_the_loader_refuses_at_the_far_end_is_named_as_that(monkeypatch):
    """The empty register never calls a refused probe a key that moved
    nothing: the loader's refusal is named as the loader's."""
    raw = copy.deepcopy(INERT)
    real_load_at = be.load_at

    def refuse_far_end(doc, key, value):
        if key == "condo.mortgage_rate" and value == be.reversal_bracket(key)[1]:
            raise be.ConfigValidationError("a refusal the test put there")
        return real_load_at(doc, key, value)

    monkeypatch.setattr(be, "load_at", refuse_far_end)
    spec = load_config_dict(raw)
    register = be.reversal_register(raw, compute_deterministic(spec), run_monte_carlo(spec))
    reason = register.no_distance_reason
    assert register.no_distance_code == "not_admitted"
    assert reason == ("this config states condo.mortgage_rate, and the loader refuses it "
                      "at the far end of its bracket")




def test_a_futures_boundary_is_identified_exactly_when_it_moves_by_more_than_the_noise():
    """`_identification` names a boundary identified when the smallest
    bracket-wide move of a watched probability exceeds `2·SE` at the
    boundary, and not otherwise. Constructed on both sides of the line: a
    move between 1 and 2 times the noise is identified, a move at or under
    it is not, and the reason printed for the latter carries both figures.
    *Kills it:* comparing against any multiple of the noise but one (a move
    of 1.5 noise refused, or one of 0.75 noise admitted), or `>=`."""
    paths = 400
    at = 0.5
    noise = 2.0 * math.sqrt(at * (1.0 - at) / paths)

    def record(low, high):
        probs = {"lo": {"condo": low}, "hi": {"condo": high}, "at": {"condo": at}}
        return be._identification("best", {"was": "condo", "becomes": "house"},
                                  probs, "condo", paths)

    for factor in (1.5, 1.01, 1.99):
        got = record(0.2, 0.2 + factor * noise)
        assert got["identified"] is True, factor
        assert got["two_se"] == noise and got["why"] is None
    for factor in (0.75, 0.5, 0.0):
        got = record(0.2, 0.2 + factor * noise)
        assert got["identified"] is False, factor
        assert (f"move by {got['delta_p']:.4f}, not more than 2 s.e. at the boundary "
                f"({noise:.4f}) on {paths} paths") in got["why"]
    assert record(0.0, noise)["identified"] is False
