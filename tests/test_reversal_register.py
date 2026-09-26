"""
The reversal register — board item 4 track C, slice 1
(docs/specs/2026-09-22-which-risk-decides-it.md §6, §8, §10, §11, and §0.1's
rulings 4, 5 and 9 on what typing the contract found).

WHAT IT ANSWERS. For each input the config STATES that carries no distribution
in this run: how far would this one input have to move, holding everything
else, before the verdict names a different winner.

THE ONE FINDING THESE TESTS GUARD. `house.mortgage_renewal_rates` is a path the
user states, so its variance is identically zero and any variance table prints
it as a dash. On this repo's own flagship fixture the opposite is true:
replacing the stated ladder with one flat rate, the verdict's own winner flips
from rent to the house at 1.6052%, inside the bracket the engine already uses
for a contract rate. A run that prices a financed option and cannot say that is
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
import os
import pathlib

import numpy as np
import pytest
import yaml

from hde.break_even import (BRACKET_SOURCE, RATE_BRACKETS, _DETERMINISTIC_FIELDS,
                            _FUTURES_FIELDS, _typed_boundary,
                            deterministic_boundaries, floor_at_zero, reversal_admission,
                            reversal_bracket, reversal_candidates, reversal_gate,
                            reversal_register, solve_break_even, solve_crossings)
from hde.config import load_config_dict, single_path_run
from hde.decomposition import (BOUNDARY_FIELDS, EstimatedReversal, ExactReversal,
                               SampledBoundary, SolvedBoundary)
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo
from hde.sweep import load_at

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"
# A SHIPPED config with every uncertainty input off, so every path it prices is
# the same path. The tests that read it assert that precondition first: an
# example that later gains a volatility must fail them, not pass them vacuously.
SINGLE_PATH = REPO_ROOT / "examples" / "first_time_buyer_montreal.yaml"

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
BEST_FLIPS_AT = 0.016052260138094424        # rent -> house, the master's-project finding
RUNNER_UP_SWAPS_AT = 0.029549435637891294   # condo -> house
MAJORITY_SWAPS_AT = 0.027164030807034577    # condo -> house, a property of THIS sample


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


# ---------------------------------------------------------------------------
# The three figures. Each is re-derived independently in the class below, so
# the numbers pinned here are not their own authority.
# ---------------------------------------------------------------------------

class TestTheThreeFiguresOnTheFixture:

    def test_the_verdicts_own_winner_flips_inside_the_contract_rates_bracket(self, register):
        """The finding: an input with no variance at all reverses the verdict
        inside the bracket the engine already uses for a mortgage rate."""
        flip = _boundary(_row(register, RENEWAL), "best")
        assert (flip.was, flip.becomes) == ("rent", "house")
        assert flip.value == pytest.approx(BEST_FLIPS_AT, abs=1e-9)
        lo, hi = RATE_BRACKETS["mortgage_rate"]
        assert lo < flip.value < hi

    def test_the_runner_up_swaps_where_the_house_crosses_the_condo(self, register):
        swap = _boundary(_row(register, RENEWAL), "runner_up")
        assert (swap.was, swap.becomes) == ("condo", "house")
        assert swap.value == pytest.approx(RUNNER_UP_SWAPS_AT, abs=1e-9)

    def test_the_option_most_futures_call_cheapest_changes_too(self, register):
        swap = _boundary(_row(register, RENEWAL), "mc_best")
        assert (swap.was, swap.becomes) == ("condo", "house")
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
        assert "is 'rent' at every point" in _refusal(row, "best").reason


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
        entry = {"value": 0.0271, "from": "condo", "to": "house"}
        probs = {"condo": 0.44, "house": 0.51, "rent": None}
        kinds = {field: type(_typed_boundary(field, entry, curve=probs, confirmed=probs,
                                             curve_paths=1234, seed=7))
                 for field in BOUNDARY_FIELDS}
        assert kinds == {"best": SolvedBoundary, "runner_up": SolvedBoundary,
                         "mc_best": SampledBoundary, "decisive": SampledBoundary}
        # The sample travels from the caller rather than from a constant.
        sampled = _typed_boundary("decisive", entry, curve=probs, confirmed=probs,
                                  curve_paths=1234, seed=7)
        assert (sampled.curve_paths, sampled.seed) == (1234, 7)
        with pytest.raises(ValueError, match="neither"):
            _typed_boundary("margin_pv", entry, curve=probs, confirmed=probs,
                            curve_paths=1234, seed=7)
        # And a sampled field with no curve to belong to refuses rather than
        # inventing a sample: this is the call the no-futures branch must never
        # be able to make.
        with pytest.raises(ValueError, match="no sample|has none"):
            _typed_boundary("mc_best", entry, curve=None, confirmed=None,
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
        ANSWER — the row names it, with the resolution it was looked for at."""
        reason = _refusal(_row(register, RENEWAL), "decisive").reason
        assert "says False at every one of 65 points" in reason
        assert "1.00%–10.00%" in reason


# ---------------------------------------------------------------------------
# One solver, two consumers (seat ruling; spec T12)
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
        renewal-flip line calls it in."""
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
        assert "DIFFERENT amount on different paths" in gate["why"]

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

    def test_a_key_that_moves_the_draw_stream_is_refused_by_clause_a(self, raw):
        """Clause (a), which nothing else catches: `rent.reset_hazard` names
        `rent`, and `_sample_reset_year` returns early inside its own year
        loop, so the draw COUNT depends on the outcome and the condo's and the
        house's arrays move too. Drop clause (a) and this key licenses."""
        gate = reversal_gate(raw, "rent.reset_hazard", 0.20, paths=200)
        assert not gate["licensed"]
        assert not gate["others_bit_identical"]
        assert set(gate["moved_others"]) == {"condo", "house"}
        assert "changes the draw stream" in gate["why"]

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
        assert all("DIFFERENT amount on different paths" in r.reason
                   for r in row.refused_boundaries)
        assert row.max_path_deviation_over_sd > 1e-9


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
        assert "disagrees with the free curve" in _refusal(row, "best").reason

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
        assert "inside the" in reason and "100 paths cannot resolve" in reason


# ---------------------------------------------------------------------------
# The trap the spec names: the stated path is not a point on the axis
# ---------------------------------------------------------------------------

class TestTheFlatteningTrap:

    def test_the_renewal_row_says_the_stated_path_is_not_on_the_axis(self, register):
        note = _row(register, RENEWAL).path_note
        assert note is not None
        assert "4.60%, 5.00%, 4.80%, 4.40%" in note
        assert "ONE figure applied at each renewal" in note
        assert "not a point on this grid" in note

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
        assert BRACKET_SOURCE == "assistant"
        for row in register.exact:
            assert row.bracket_source == "assistant"
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
        """A solved rate needs something cited to be read against, and the
        posted rate's note says what the citation does not license."""
        refs = {r.anchor: r for r in _row(register, RENEWAL).references}
        assert set(refs) == {"mortgage_rate.contracted_5y_uninsured",
                             "mortgage_rate.contracted_5y_insured",
                             "mortgage_rate.posted_5y"}
        assert refs["mortgage_rate.posted_5y"].formatted == "6.09%"
        assert "never a ceiling" in refs["mortgage_rate.posted_5y"].note
        assert refs["mortgage_rate.contracted_5y_uninsured"].note is None


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
        assert renewal.label == "your renewal rate"
        assert renewal.stated_formatted == "4.60%, 5.00%, 4.80%, 4.40%"
        assert "not a distribution" in renewal.reason
        assert _row(register, renewal.reversal_key).boundaries

    def test_each_stated_path_row_gives_the_reason_true_of_its_own_key(self, register):
        """The contract rate is not a forward path, so the ladder's own
        justification may not be pasted onto its row — the category-general
        sentence has to be true of the key it names."""
        zeros = {z.reversal_key: z for z in register.structural_zeros
                 if z.kind == "stated_path"}
        assert "anchors no forward rate" in zeros[RENEWAL].reason
        assert "anchors no forward rate" not in zeros[CONTRACT].reason
        assert "held for the opening term" in zeros[CONTRACT].reason

    def test_the_income_block_reaches_no_present_value(self, register):
        zero = [z for z in register.structural_zeros if z.kind == "no_pv_reach"]
        assert len(zero) == 1
        assert zero[0].keys == ("income.pay_drop_events",)
        assert "not either option's present value" in zero[0].reason
        assert zero[0].channel_id is None

    def test_the_real_mode_inflation_trap_is_a_named_zero_with_its_channel(self, raw):
        """A channel that draws every year and reaches nothing. Detected from
        the config, with no evaluation spent on it — a measured 0.00 in that row
        would read as "inflation does not matter", which is not what is true."""
        real = copy.deepcopy(raw)
        real["economic"]["mode"] = "real"
        for name in ("condo", "house", "other", "event_cost"):
            real["simulation"][f"corr_inflation_{name}"] = 0.0
        # Real mode takes real rates; the fixture's are sticker figures, and the
        # magnitudes do not matter to a zero detected from the config's shape.
        spec = load_config_dict(real)
        register = reversal_register(real, compute_deterministic(spec), run_monte_carlo(spec))
        dead = [z for z in register.structural_zeros if z.kind == "dead_draw"]
        assert len(dead) == 1
        assert dead[0].channel_id == 0 and dead[0].label == "the economy"
        assert "economic.inflation_vol" in dead[0].keys
        assert "reaches no cash flow" in dead[0].reason

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
        for field in ("mc_best", "decisive"):
            assert "this run has none" in _refusal(row, field).reason
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
        for field in ("mc_best", "decisive"):
            assert "this run has none" in _refusal(row, field).reason

    def test_a_single_option_config_has_no_winner_to_reverse(self, raw):
        one = _without(raw, "condo", "rent")
        spec = load_config_dict(one)
        register = reversal_register(one, compute_deterministic(spec), run_monte_carlo(spec))
        assert (register.exact, register.estimated, register.structural_zeros) == ((), (), ())
