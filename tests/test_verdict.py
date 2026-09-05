"""
Verdict tests (src/hde/models.py compute_verdict): ONE decisiveness rule that
every surface consumes — readiness plan B.1/B.2, operator-ruled 2026-09-01:
Monte Carlo probability floor 0.65 when MC ran with real uncertainty; else a
tie band of 5% of the winner's total PV. Both constants are registered anchors.
"""

import pytest

from hde.anchors import ANCHORS
from hde.models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    OptionResult,
    compute_verdict,
)


def _det(pvs: dict) -> ComparisonDeterministicResult:
    def opt(pv):
        return OptionResult(total_pv=pv, breakdown={})
    return ComparisonDeterministicResult(
        condo=opt(pvs["condo"]) if "condo" in pvs else None,
        house=opt(pvs["house"]) if "house" in pvs else None,
        rent=opt(pvs["rent"]) if "rent" in pvs else None,
    )


def _mc(**probs) -> ComparisonMonteCarloResult:
    return ComparisonMonteCarloResult(**{f"prob_{k}_cheapest": v for k, v in probs.items()})


FLOOR = ANCHORS["verdict.prob_floor"].value
BAND = ANCHORS["verdict.tie_band"].value


class TestConstantsAreAnchored:
    def test_registered_as_derivations_with_bands(self):
        for name in ("verdict.prob_floor", "verdict.tie_band"):
            a = ANCHORS[name]
            assert a.kind == "derivation"
            assert a.band[0] <= a.value <= a.band[1]
            assert "verdict" in a.short_cite

    def test_ruled_values(self):
        assert FLOOR == pytest.approx(0.65)
        assert BAND == pytest.approx(0.05)


class TestMarginRule:
    def test_margin_is_vs_runner_up_not_costliest(self):
        v = compute_verdict(_det({"condo": 500_000.0, "house": 900_000.0, "rent": 520_000.0}), None, years=30)
        assert (v.best, v.runner_up) == ("condo", "rent")
        assert v.margin_pv == pytest.approx(20_000.0)
        assert v.margin_frac == pytest.approx(0.04)

    def test_band_boundary(self):
        below = compute_verdict(_det({"condo": 400_000.0, "rent": 400_000.0 * (1 + BAND) - 1}), None, years=15)
        at = compute_verdict(_det({"condo": 400_000.0, "rent": 400_000.0 * (1 + BAND)}), None, years=15)
        assert not below.decisive and below.rule == "margin_band"
        assert at.decisive and at.rule == "margin_band"

    def test_reason_names_the_rule(self):
        v = compute_verdict(_det({"condo": 400_000.0, "rent": 401_000.0}), None, years=15)
        assert "tie band" in v.reason and "hde verdict rule" in v.reason

    def test_monthly_equivalent_from_runner_up_margin(self):
        from hde.pv import pv_to_monthly_savings
        v = compute_verdict(_det({"condo": 500_000.0, "house": 900_000.0, "rent": 520_000.0}),
                            None, years=30, discount_rate=0.04)
        assert v.monthly_equivalent == pytest.approx(pv_to_monthly_savings(20_000.0, 0.04, 30))


class TestMonteCarloRule:
    def test_floor_boundary(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})   # 10% margin: would win on margin alone
        below = compute_verdict(det, _mc(condo=FLOOR - 0.001, house=1 - FLOOR + 0.001), years=20)
        at = compute_verdict(det, _mc(condo=FLOOR, house=1 - FLOOR), years=20)
        assert not below.decisive and below.rule == "mc_floor"
        assert at.decisive and at.rule == "mc_floor"
        assert below.prob_best == pytest.approx(FLOOR - 0.001)

    def test_mc_favouring_another_option_is_a_disagreement(self):
        det = _det({"condo": 400_000.0, "house": 400_200.0})
        v = compute_verdict(det, _mc(condo=0.472, house=0.528), years=20)
        assert not v.decisive and v.state == "disagreement"
        assert "most futures say house (53% cheapest)" in v.reason

    def test_single_path_run_ignores_mc(self):
        det = _det({"condo": 400_000.0, "house": 404_000.0})   # 1% margin
        v = compute_verdict(det, _mc(condo=1.0, house=0.0), years=20, single_path=True)
        assert v.rule == "margin_band" and not v.decisive and v.prob_best is None

    def test_missing_probability_falls_back_to_margin(self):
        det = _det({"condo": 400_000.0, "house": 480_000.0})
        v = compute_verdict(det, ComparisonMonteCarloResult(), years=20)
        assert v.rule == "margin_band" and v.decisive


class TestEdges:
    def test_single_option(self):
        v = compute_verdict(_det({"rent": 123_456.0}), None, years=5)
        assert v.rule == "single_option" and v.runner_up is None and v.decisive

    def test_no_options_is_none(self):
        assert compute_verdict(ComparisonDeterministicResult(), None, years=5) is None


class TestReasonNeverPrintsAsItsOwnThreshold:
    """2026-09-03 review: P(best) = 0.6499 printed "65% < 65% floor" — a
    sentence that contradicts itself, and the one place whole-percent rounding
    can mislead. The reason line escalates precision until the measured
    quantity and the threshold differ on the page (equal values still print
    equal, because "≥" is then true)."""

    def test_just_under_the_floor_is_not_printed_as_the_floor(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})
        v = compute_verdict(det, _mc(condo=0.6499, house=0.3501), years=20)
        assert not v.decisive
        assert "64.99% < 65.00% floor" in v.reason

    def test_just_over_the_floor_is_not_printed_as_the_floor(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})
        v = compute_verdict(det, _mc(condo=0.6501, house=0.3499), years=20)
        assert v.decisive and "65.01% ≥ 65.00% floor" in v.reason

    def test_exactly_at_the_floor_stays_whole(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})
        v = compute_verdict(det, _mc(condo=FLOOR, house=1 - FLOOR), years=20)
        assert v.decisive and "65% ≥ 65% floor" in v.reason

    def test_clear_cases_keep_whole_percent(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})
        v = compute_verdict(det, _mc(condo=0.81, house=0.19), years=20)
        assert "P(condo cheapest) = 81% ≥ 65% floor" in v.reason

    def test_the_margin_band_line_obeys_the_same_rule(self):
        v = compute_verdict(_det({"condo": 400_000.0, "rent": 400_000.0 * 1.0499}),
                            None, years=15)
        assert not v.decisive
        assert "margin 5.0% of condo PV < 5% tie band" not in v.reason
        assert "margin 4.99% of condo PV < 5.00% tie band" in v.reason

    def test_a_clear_margin_keeps_one_decimal(self):
        v = compute_verdict(_det({"condo": 400_000.0, "house": 900_000.0, "rent": 520_000.0}),
                            None, years=30)
        assert "margin 30.0% of condo PV ≥ 5% tie band" in v.reason


class TestThreeStates:
    """2026-09-04: served answers showed a table reading "rent, not decisive"
    beside a 66% house column. The verdict has three states — `option`
    (decisive), `tie` (not decisive; the majority agrees or is absent) and
    `disagreement` (the deterministic central case and the Monte Carlo
    majority favour different options — named with both figures, never
    decisive). `best` stays the deterministic winner; `mc_best` is the
    majority's option, None without Monte Carlo."""

    def test_disagreement_names_both_figures_and_is_never_decisive(self):
        det = _det({"rent": 400_000.0, "house": 404_551.0})
        v = compute_verdict(det, _mc(rent=0.39, house=0.61), years=20)
        assert v.state == "disagreement"
        assert not v.decisive
        assert v.best == "rent" and v.mc_best == "house"
        assert v.prob_best == pytest.approx(0.39)
        assert v.mc_prob_best == pytest.approx(0.61)
        assert v.reason.startswith(
            "best guess says rent by $4,551 (1.1% of rent PV); most futures say house "
            "(61% cheapest) — the two disagree, not decisive [hde verdict rule]")

    def test_a_wide_margin_does_not_rescue_a_disagreement(self):
        det = _det({"rent": 400_000.0, "house": 480_000.0})   # 20% margin
        v = compute_verdict(det, _mc(rent=0.40, house=0.60), years=20)
        assert v.state == "disagreement" and not v.decisive

    def test_majority_equal_to_best_under_the_floor_stays_tie(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})
        v = compute_verdict(det, _mc(condo=0.55, house=0.45), years=20)
        assert v.state == "tie" and not v.decisive
        assert v.mc_best == "condo" and v.mc_prob_best == pytest.approx(0.55)
        assert v.reason.startswith("P(condo cheapest) = 55% < 65% floor [hde verdict rule]")

    def test_majority_equal_to_best_above_the_floor_is_option(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})
        v = compute_verdict(det, _mc(condo=0.81, house=0.19), years=20)
        assert v.state == "option" and v.decisive and v.mc_best == "condo"

    def test_an_exact_probability_tie_sides_with_the_deterministic_best(self):
        det = _det({"condo": 400_000.0, "house": 440_000.0})
        v = compute_verdict(det, _mc(condo=0.5, house=0.5), years=20)
        assert v.state == "tie" and v.mc_best == "condo"

    def test_three_options_majority_is_the_highest_probability(self):
        det = _det({"rent": 400_000.0, "condo": 410_000.0, "house": 420_000.0})
        v = compute_verdict(det, _mc(rent=0.30, condo=0.25, house=0.45), years=20)
        assert v.state == "disagreement" and v.mc_best == "house"
        assert "most futures say house (45% cheapest)" in v.reason

    def test_margin_band_states_carry_no_majority(self):
        tie = compute_verdict(_det({"condo": 400_000.0, "rent": 401_000.0}), None, years=15)
        option = compute_verdict(_det({"condo": 400_000.0, "rent": 460_000.0}), None, years=15)
        assert (tie.state, tie.mc_best, tie.mc_prob_best) == ("tie", None, None)
        assert (option.state, option.mc_best, option.mc_prob_best) == ("option", None, None)

    def test_single_path_run_carries_no_majority(self):
        det = _det({"condo": 400_000.0, "house": 404_000.0})
        v = compute_verdict(det, _mc(condo=0.0, house=1.0), years=20, single_path=True)
        assert v.state == "tie" and v.mc_best is None

    def test_single_option_is_option(self):
        v = compute_verdict(_det({"rent": 123_456.0}), None, years=5)
        assert v.state == "option" and v.mc_best is None

    def test_the_mean_clause_still_appends(self):
        import numpy as np
        from hde.models import MonteCarloOptionResult, MonteCarloSummary
        det = _det({"rent": 400_000.0, "house": 404_551.0})
        mc = _mc(rent=0.39, house=0.61)
        mc.rent = MonteCarloOptionResult(np.zeros(1), MonteCarloSummary(420_000.0, 0.0, 0.0, 0.0, 0.0))
        mc.house = MonteCarloOptionResult(np.zeros(1), MonteCarloSummary(404_000.0, 0.0, 0.0, 0.0, 0.0))
        v = compute_verdict(det, mc, years=20)
        assert v.state == "disagreement"
        assert "[hde verdict rule]; Monte Carlo mean favours house ($404,000 vs $420,000)" in v.reason
