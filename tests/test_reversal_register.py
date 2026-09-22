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

MEASURED, AND NOT CARRIED BY THE CONTRACT. Across seeds 42, 7, 1234, 99 and
2026 the `best` and `runner_up` boundaries below are identical to seven digits
while the `mc_best` boundary moves 2.698% -> 2.805%: two are properties of the
config, one is a property of this run's 2,000 futures, and `Boundary` carries
the same shape for all three. (That five-seed sweep is five full Monte Carlo
runs and is deliberately NOT in this suite — it is recorded in the commit that
landed the register.)
"""

import copy
import os
import pathlib

import numpy as np
import pytest
import yaml

from hde.break_even import (BRACKET_SOURCE, RATE_BRACKETS, deterministic_boundaries,
                            floor_at_zero, reversal_admission, reversal_bracket,
                            reversal_candidates, reversal_gate, reversal_register,
                            solve_break_even, solve_crossings)
from hde.config import load_config_dict
from hde.decomposition import BOUNDARY_FIELDS, EstimatedReversal, ExactReversal
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo
from hde.sweep import load_at

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"

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
        that includes the two deterministic ones, whose confirmation is what
        licenses the free curve the futures boundary is read off."""
        reported = [b for row in register.exact for b in row.boundaries]
        assert len(reported) == 5, reported
        for boundary in reported:
            assert boundary.curve_probabilities == boundary.confirming_probabilities
            assert boundary.curve_probabilities  # not an empty tuple comparing equal

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

    def test_without_futures_the_block_refuses_and_returns_an_empty_register(
            self, raw, base):
        """§8 refusal 2. `decomposition.Boundary` requires a curve AND a
        confirming set of probabilities, so it cannot express a boundary that
        read no path — an empty register is the honest shape, and the surface
        that DOES answer there is `deterministic_boundaries`."""
        _, det, _ = base
        register = reversal_register(raw, det, None)
        assert (register.exact, register.estimated, register.structural_zeros) == ((), (), ())
        lo, hi = RATE_BRACKETS["mortgage_rate"]
        solved = deterministic_boundaries(raw, RENEWAL, lo, hi, base=det)
        best = [b for b in solved["boundaries"] if b["attribute"] == "best"]
        assert [b["value"] for b in best] == [pytest.approx(BEST_FLIPS_AT, abs=1e-9)]

    def test_a_single_option_config_has_no_winner_to_reverse(self, raw):
        one = _without(raw, "condo", "rent")
        spec = load_config_dict(one)
        register = reversal_register(one, compute_deterministic(spec), run_monte_carlo(spec))
        assert (register.exact, register.estimated, register.structural_zeros) == ((), (), ())
