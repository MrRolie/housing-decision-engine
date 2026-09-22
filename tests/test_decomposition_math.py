"""
The decomposition's arithmetic, tested against answers derived on paper.

WHY THIS FILE LOOKS LIKE THIS: `decomposition_math` is the leg of the
decomposition most likely to be subtly wrong, and the only one that needs no
simulation to check. So nothing here runs the engine. Every table is synthetic,
built from a function whose Sobol' indices are known in closed form — the
additive Gaussian case, the Ishigami function's published indices, a pure
interaction whose first-order indices are zero, and a degenerate case where one
channel carries everything — and the estimators are asserted to recover those
known values inside their own bootstrap intervals. An estimator tested only
against itself is not tested.

Then the cases that will actually occur on a real run, from the design's own
measurements: first-order shares that sum ABOVE 1 on estimator noise alone, a
channel whose index comes out slightly NEGATIVE and must be reported as
unresolved rather than clipped, and a channel that is exactly dead.

Design: `docs/specs/2026-09-22-which-risk-decides-it.md`, sections 3.3, 3.4, 4
and the test plan in 10.
"""

from __future__ import annotations

import importlib.util
import math
import subprocess
import sys
from pathlib import Path
from typing import Callable, Tuple

import numpy as np
import pytest

from hde import decomposition_math as dm

Table = Tuple[np.ndarray, np.ndarray, np.ndarray]


# ---------------------------------------------------------------------------
# Synthetic pick-freeze tables. This is the whole harness: two independent
# draws of the channel set, and one re-draw of a single channel at a time.
# ---------------------------------------------------------------------------

def build_tables(
    f: Callable[[np.ndarray], np.ndarray],
    n: int,
    k: int,
    seed: int,
    sampler: str = "normal",
) -> Table:
    """f(A), f(B) and the (k, n) f(A_B) table for a model of `k` inputs."""
    rng = np.random.default_rng(seed)
    if sampler == "normal":
        a = rng.standard_normal((n, k))
        b = rng.standard_normal((n, k))
    elif sampler == "uniform_pi":
        a = rng.uniform(-np.pi, np.pi, size=(n, k))
        b = rng.uniform(-np.pi, np.pi, size=(n, k))
    else:  # pragma: no cover - a typo in a test is not a branch
        raise AssertionError(f"unknown sampler {sampler!r}")
    f_a = np.asarray(f(a), dtype=float)
    f_b = np.asarray(f(b), dtype=float)
    f_ab = np.empty((k, n), dtype=float)
    for channel in range(k):
        mixed = a.copy()
        mixed[:, channel] = b[:, channel]
        f_ab[channel] = f(mixed)
    return f_a, f_b, f_ab


def inside(interval: np.ndarray, value: float) -> bool:
    return bool(interval[0] <= value <= interval[1])


def agrees_within_stated_precision(
    point: float,
    interval: np.ndarray,
    analytic: float,
    sigmas: float = 4.0,
    widest: float = 0.06,
) -> None:
    """The estimate agrees with the analytic answer to within its own precision.

    HOW THIS IS ASSERTED, AND WHY NOT SIMPLY "INSIDE THE 95% INTERVAL": a single
    95% interval misses its target one time in twenty BY CONSTRUCTION. Measured
    on the additive case at 2,000 futures over 150 trials, this bootstrap's
    per-figure coverage is 0.947 to 0.987 — nominal, so the intervals are honest
    — and a test asserting six such containments at once would therefore fail
    about a quarter of the time. A suite that fails a quarter of the time teaches
    a reader to re-run it, which is worse than no test.

    So agreement is asserted at four times the standard error the interval
    implies (a one-in-sixteen-thousand tail per figure), AND the interval is
    asserted to be narrow enough for that to mean something — without the second
    half, an estimator that returned absurdly wide intervals would pass. The
    95% level's own calibration is measured once, over many trials, in
    `test_the_interval_width_is_calibrated_not_decorative`.
    """
    half = (float(interval[1]) - float(interval[0])) / 2.0
    assert 0.0 < half < widest, f"interval {interval} is not informative about {analytic}"
    standard_error = half / 1.96
    assert abs(point - analytic) <= sigmas * standard_error, (
        f"{point} is more than {sigmas} standard errors ({standard_error:.5f}) "
        f"from the analytic {analytic}"
    )


# ---------------------------------------------------------------------------
# 1. The additive Gaussian case: each channel's share is its coefficient's
#    share of the total variance, and there is no interaction, so S == S_T.
# ---------------------------------------------------------------------------

def test_additive_gaussian_recovers_its_known_variance_shares() -> None:
    coefficients = np.array([3.0, 2.0, 1.0])
    analytic = (coefficients ** 2) / float((coefficients ** 2).sum())
    assert np.isclose(analytic.sum(), 1.0)

    f_a, f_b, f_ab = build_tables(lambda x: x @ coefficients, 20_000, 3, seed=12345)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total = dm.total_order_indices(f_a, f_ab)
    first_ci, total_ci, _flip_ci, sum_ci = dm.bootstrap_spread_intervals(
        f_a, f_b, f_ab, seed=12345
    )

    for channel in range(3):
        agrees_within_stated_precision(first[channel], first_ci[channel], analytic[channel])
        agrees_within_stated_precision(total[channel], total_ci[channel], analytic[channel])
        assert abs(first[channel] - analytic[channel]) < 0.01
        assert abs(total[channel] - analytic[channel]) < 0.01
        # No interaction in an additive model: the two orders agree.
        assert abs(first[channel] - total[channel]) < 0.02

    assert inside(np.asarray(sum_ci), 1.0)
    assert abs(dm.sum_first_order_shares(first) - 1.0) < 0.02


# ---------------------------------------------------------------------------
# 2. Ishigami: indices published in closed form, first order and total order,
#    with a channel whose first-order index is exactly zero while its total
#    order is not. Computed here from the formulas, never pasted as constants.
# ---------------------------------------------------------------------------

def ishigami_analytic(a: float, b: float) -> Tuple[np.ndarray, np.ndarray, float]:
    pi4 = math.pi ** 4
    pi8 = math.pi ** 8
    variance = a ** 2 / 8.0 + b * pi4 / 5.0 + b ** 2 * pi8 / 18.0 + 0.5
    v1 = b * pi4 / 5.0 + b ** 2 * pi8 / 50.0 + 0.5
    v2 = a ** 2 / 8.0
    v13 = b ** 2 * pi8 * (1.0 / 18.0 - 1.0 / 50.0)
    first = np.array([v1, v2, 0.0]) / variance
    total = np.array([v1 + v13, v2, v13]) / variance
    return first, total, v13 / variance


def test_ishigami_recovers_its_published_closed_form() -> None:
    a, b = 7.0, 0.1
    analytic_first, analytic_total, analytic_interaction = ishigami_analytic(a, b)
    # The published values for a=7, b=0.1, as a check on the formulas above.
    assert np.allclose(analytic_first, [0.3139, 0.4424, 0.0], atol=5e-4)
    assert np.allclose(analytic_total, [0.5576, 0.4424, 0.2437], atol=5e-4)

    def ishigami(x: np.ndarray) -> np.ndarray:
        return np.sin(x[:, 0]) + a * np.sin(x[:, 1]) ** 2 + b * (x[:, 2] ** 4) * np.sin(x[:, 0])

    f_a, f_b, f_ab = build_tables(ishigami, 32_768, 3, seed=777, sampler="uniform_pi")
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total = dm.total_order_indices(f_a, f_ab)
    first_ci, total_ci, _flip_ci, sum_ci = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=777)

    for channel in range(3):
        agrees_within_stated_precision(first[channel], first_ci[channel], analytic_first[channel])
        agrees_within_stated_precision(total[channel], total_ci[channel], analytic_total[channel])
        assert abs(first[channel] - analytic_first[channel]) < 0.015
        assert abs(total[channel] - analytic_total[channel]) < 0.015

    # Channel 2 enters only through its interaction with channel 0: first order
    # zero, total order a quarter of the variance. A build that reported S in
    # the total-order column would put 0.00 here.
    assert total[2] - first[2] > 0.20

    # The residual is the interaction the additive shares leave unexplained,
    # and on this function that figure is analytic too.
    residual = dm.residual_interaction(dm.sum_first_order_shares(first), *sum_ci)
    assert residual is not None, "Ishigami's shares resolve below 1; the residual must print"
    point, low, high = residual
    agrees_within_stated_precision(point, np.array([low, high]), analytic_interaction)


# ---------------------------------------------------------------------------
# 3. Pure interaction: first-order indices zero, total-order indices one.
# ---------------------------------------------------------------------------

def test_pure_interaction_has_zero_first_order_and_total_order_of_one() -> None:
    f_a, f_b, f_ab = build_tables(lambda x: x[:, 0] * x[:, 1], 20_000, 2, seed=99)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total = dm.total_order_indices(f_a, f_ab)
    first_ci, total_ci, _flip, sum_ci = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=99)

    for channel in range(2):
        agrees_within_stated_precision(first[channel], first_ci[channel], 0.0, widest=0.05)
        agrees_within_stated_precision(total[channel], total_ci[channel], 1.0, widest=0.05)
        assert abs(first[channel]) < 0.03
        assert abs(total[channel] - 1.0) < 0.05

    # Every bit of this variance is movement no single channel owns.
    residual = dm.residual_interaction(dm.sum_first_order_shares(first), *sum_ci)
    assert residual is not None
    assert abs(residual[0] - 1.0) < 0.05


# ---------------------------------------------------------------------------
# 4. One channel carries everything, and the dead channels are EXACTLY zero.
# ---------------------------------------------------------------------------

def test_one_channel_carries_everything_and_dead_channels_are_exactly_zero() -> None:
    f_a, f_b, f_ab = build_tables(lambda x: x[:, 0], 20_000, 4, seed=7)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total = dm.total_order_indices(f_a, f_ab)
    flips = dm.sign_flip_fraction_of_futures(f_a, f_ab)
    first_ci, total_ci, flip_ci, _sum_ci = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=7)

    assert abs(first[0] - 1.0) < 0.05
    assert abs(total[0] - 1.0) < 0.05
    agrees_within_stated_precision(first[0], first_ci[0], 1.0)
    # Re-drawing the only live channel changes the sign of f half the time.
    assert abs(flips[0] - 0.5) < 0.02

    for dead in (1, 2, 3):
        # f never reads these inputs, so f(A_B) is f(A) bit for bit and there is
        # no estimator noise to hide behind: not "close to zero", zero.
        assert first[dead] == 0.0
        assert total[dead] == 0.0
        assert flips[dead] == 0.0
        assert tuple(first_ci[dead]) == (0.0, 0.0)
        assert tuple(total_ci[dead]) == (0.0, 0.0)
        assert tuple(flip_ci[dead]) == (0.0, 0.0)


def test_a_dead_channel_is_zero_on_a_table_that_is_dead_by_construction() -> None:
    rng = np.random.default_rng(3)
    f_a = rng.standard_normal(500)
    f_b = rng.standard_normal(500)
    f_ab = np.vstack([f_a.copy(), rng.standard_normal(500)])
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total = dm.total_order_indices(f_a, f_ab)
    flips = dm.sign_flip_fraction_of_futures(f_a, f_ab)
    assert (first[0], total[0], flips[0]) == (0.0, 0.0, 0.0)
    assert total[1] > 0.0


# ---------------------------------------------------------------------------
# 5. The flip column is a fraction of futures, and it is NOT the share.
# ---------------------------------------------------------------------------

def test_flip_fraction_matches_its_analytic_value_and_is_not_the_share() -> None:
    """f = x + 1 on one channel: the share is 1.0 and the flip fraction is 0.267.

    Both numbers are exact. P(f > 0) = Phi(1) = 0.8413, and re-drawing the only
    channel changes the sign when exactly one of the two draws is negative, so
    the flip fraction is 2p(1-p) = 0.2670. One channel, one input, two entirely
    different true numbers — which is why the design prints both columns and
    says in words that they are different kinds of number.
    """
    p = 0.5 * (1.0 + math.erf(1.0 / math.sqrt(2.0)))
    analytic_flip = 2.0 * p * (1.0 - p)
    assert abs(analytic_flip - 0.2670) < 1e-3

    f_a, f_b, f_ab = build_tables(lambda x: x[:, 0] + 1.0, 40_000, 1, seed=2024)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    flips = dm.sign_flip_fraction_of_futures(f_a, f_ab)
    _first_ci, _total_ci, flip_ci, _sum_ci = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=5)

    assert abs(first[0] - 1.0) < 0.05
    assert abs(flips[0] - analytic_flip) < 0.01
    agrees_within_stated_precision(flips[0], flip_ci[0], analytic_flip, widest=0.02)
    # The two columns are 1.00 and 0.27 about one channel.
    assert first[0] - flips[0] > 0.6


def test_a_future_sitting_exactly_on_zero_counts_as_flipped() -> None:
    f_a = np.array([0.0, 1.0, -1.0, 2.0])
    f_ab = np.array([[1.0, 1.0, -1.0, 2.0]])
    assert dm.sign_flip_fraction_of_futures(f_a, f_ab)[0] == 0.25


def test_the_flip_column_does_not_sum_to_anything() -> None:
    """Three channels split the variance in thirds; their flip fractions do not.

    The shares add to 1.00, because that is what a variance decomposition of
    three additive channels does. The flip fractions add to 0.80 — not to one,
    not to the shares, not to anything derivable from them, and the figure would
    move with the target's mean while the shares would not. The module offers no
    function that sums flips; this records the reason.
    """
    coefficients = np.array([1.0, 1.0, 1.0])
    f_a, f_b, f_ab = build_tables(lambda x: x @ coefficients, 20_000, 3, seed=8)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    flips = dm.sign_flip_fraction_of_futures(f_a, f_ab)

    assert abs(dm.sum_first_order_shares(first) - 1.0) < 0.05
    assert np.allclose(flips, 0.265, atol=0.01)
    assert abs(float(flips.sum()) - 0.80) < 0.03
    assert abs(float(flips.sum()) - 1.0) > 0.15

    # The same three channels, the same TRUE shares, a different flip column:
    # add a mean of 3.5 standard deviations and every flip fraction collapses
    # while each share stays a third. The estimates drift by up to 0.03 doing
    # it, which is the estimator's own mean-sensitivity, measured in
    # `test_the_specified_estimator_loses_precision_as_the_verdict_gets_decisive`.
    shifted_a, shifted_b, shifted_ab = build_tables(
        lambda x: x @ coefficients + 6.0, 20_000, 3, seed=8
    )
    shifted_first = dm.first_order_indices(shifted_a, shifted_b, shifted_ab)
    shifted_flips = dm.sign_flip_fraction_of_futures(shifted_a, shifted_ab)
    assert np.allclose(shifted_first, 1.0 / 3.0, atol=0.04)
    assert float(shifted_flips.sum()) < 0.15

    assert not hasattr(dm, "sum_flip_fractions")


# ---------------------------------------------------------------------------
# 6. The cases that will actually occur, from the design's own measurements.
# ---------------------------------------------------------------------------

SEVEN_CHANNEL_COEFFICIENTS = np.array([3.0, 2.0, 1.5, 1.0, 0.8, 0.5, 0.2])


def seven_channel_tables(n: int, seed: int) -> Table:
    return build_tables(lambda x: x @ SEVEN_CHANNEL_COEFFICIENTS, n, 7, seed=seed)


def test_first_order_shares_can_sum_above_one_and_the_residual_then_refuses() -> None:
    """Seven channels at 200 futures: the shares add to 1.15 and there is no
    residual to print. The design measures 1.164 [1.042, 1.310] on its own
    fixture at 2,000 paths; this is the same failure of the sum on a table whose
    true shares are known to add to exactly 1.

    The seed is load-bearing and deliberate, the way the design names seed 42 in
    T6: the overshoot is a property of the sample, not of the model. Measured
    over 60 seeds at this size, the sum clears 1.05 in 26 of them and at least
    one share comes out negative in 24 — so this seed pins a common outcome, not
    a freak one, and a different seed would need its own measurement.
    """
    f_a, f_b, f_ab = seven_channel_tables(200, seed=0)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total_share = dm.sum_first_order_shares(first)
    _first_ci, _total_ci, _flip_ci, sum_ci = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=42)

    analytic = SEVEN_CHANNEL_COEFFICIENTS ** 2 / float((SEVEN_CHANNEL_COEFFICIENTS ** 2).sum())
    assert np.isclose(analytic.sum(), 1.0)
    assert total_share > 1.05, f"expected the sum to overshoot; got {total_share}"
    assert sum_ci[1] >= 1.0
    assert dm.residual_interaction(total_share, *sum_ci) is None

    # Raising the futures resolves it: same model, same seed, more paths.
    f_a, f_b, f_ab = seven_channel_tables(20_000, seed=0)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    _fc, _tc, _flc, wide_sum_ci = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=42)
    assert abs(dm.sum_first_order_shares(first) - 1.0) < 0.05
    assert wide_sum_ci[1] - wide_sum_ci[0] < (sum_ci[1] - sum_ci[0]) / 4.0


def test_the_residual_refuses_on_the_designs_own_published_sums() -> None:
    """Section 4's rule applied to the two figures section 4 publishes.

    NOTE, and it is a finding rather than a test convenience: section 4 states
    the rule as "when the bootstrap CI of Sigma S_c lies entirely BELOW 1 the
    residual prints; when that CI includes or exceeds 1, no residual number
    prints", and its own 10,000-path figure is 1.023 [0.969, 1.091]. That
    interval includes 1, so under the stated rule the 10,000-path case ALSO
    refuses — while T5 in section 10 asserts it takes the numeric branch. The
    rule and the test plan disagree about this fixture. This module implements
    the rule as section 4 writes it, and this test pins that reading so the
    disagreement is visible rather than discovered by a formatter.
    """
    assert dm.residual_interaction(1.164, 1.042, 1.310) is None
    assert dm.residual_interaction(1.023, 0.969, 1.091) is None
    # An interval that really does clear 1 prints, and the bounds invert.
    resolved = dm.residual_interaction(0.80, 0.74, 0.88)
    assert resolved is not None
    point, low, high = resolved
    assert (round(point, 10), round(low, 10), round(high, 10)) == (0.20, 0.12, 0.26)


def test_an_interval_touching_one_exactly_still_refuses() -> None:
    assert dm.residual_interaction(0.9, 0.7, 1.0) is None
    assert dm.residual_interaction(0.9, 0.7, 0.9999999) is not None


def test_a_negative_share_is_reported_as_measured_not_clipped_to_zero() -> None:
    """The smallest channel's index comes out below zero at 200 futures.

    Its true share is 0.0023 and the estimator's own error on a channel that
    small is several times that, so a negative estimate is the expected
    outcome, not a defect. What would be a defect is printing it as 0.00: that
    reads as "measured, and it does not matter", when the truth is that this
    sample cannot tell.
    """
    f_a, f_b, f_ab = seven_channel_tables(200, seed=0)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    first_ci, _total_ci, _flip_ci, _sum_ci = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=42)

    smallest = 6
    assert first[smallest] < 0.0, f"expected a negative estimate, got {first[smallest]}"
    assert first[smallest] > -0.05
    assert dm.share_is_resolved(float(first[smallest])) is False
    # Reported as measured: the interval straddles zero and is not truncated.
    assert first_ci[smallest][0] < 0.0
    # And the channels that do resolve still resolve.
    assert dm.share_is_resolved(float(first[0])) is True


def test_share_is_resolved_is_the_rule_and_nothing_is_clamped() -> None:
    assert dm.share_is_resolved(0.0) is True
    assert dm.share_is_resolved(1.0) is True
    assert dm.share_is_resolved(0.877) is True
    assert dm.share_is_resolved(-0.001) is False
    assert dm.share_is_resolved(1.05) is False
    assert dm.share_is_resolved(float("nan")) is False


# ---------------------------------------------------------------------------
# 7. The level register: paired standard errors, and the 2 x SE rule.
# ---------------------------------------------------------------------------

def test_level_shift_is_the_paired_mean_and_its_paired_standard_error() -> None:
    base = np.array([1.0, 2.0, 3.0])
    frozen = np.array([2.0, 4.0, 6.0])
    delta, error = dm.level_shift(base, frozen)
    # differences 1, 2, 3: mean 2, sample sd 1, standard error 1/sqrt(3)
    assert delta == pytest.approx(2.0)
    assert error == pytest.approx(1.0 / math.sqrt(3.0))
    assert dm.level_is_resolved(delta, error) is True


def test_the_pairing_is_what_makes_a_level_shift_readable() -> None:
    """A $100 shift inside a spread a thousand times wider still resolves.

    Section 3.4's whole claim: the difference is taken per future, so the
    spread cancels. An unpaired standard error on these same two tables is
    larger than the shift by three orders of magnitude and would report the
    channel as indistinguishable from zero.
    """
    rng = np.random.default_rng(4242)
    base = rng.normal(0.0, 1e6, 500)
    frozen = base + 100.0 + rng.normal(0.0, 1.0, 500)

    delta, paired_error = dm.level_shift(base, frozen)
    assert delta == pytest.approx(100.0, abs=1.0)
    assert paired_error < 0.1
    assert dm.level_is_resolved(delta, paired_error) is True

    unpaired = math.sqrt(np.var(base, ddof=1) / 500 + np.var(frozen, ddof=1) / 500)
    assert unpaired > 1000.0
    assert dm.level_is_resolved(delta, unpaired) is False


def test_the_two_sigma_rule_on_the_designs_own_measured_pairs() -> None:
    """The tenancy resolves, the portfolio does not — the design's headline.

    Both pairs are measured figures from section 3.4 / section 7 of the design.
    The portfolio is the channel carrying most of the spread, and its level
    effect is what the block must print as indistinguishable from zero rather
    than as a number or as an absence.
    """
    assert dm.level_is_resolved(125_074.0, 1_775.0) is True     # the tenancy
    assert dm.level_is_resolved(-38_314.0, 2_252.0) is True     # the housing market
    assert dm.level_is_resolved(11_064.0, 1_095.0) is True      # the population
    assert dm.level_is_resolved(5_232.0, 786.0) is True         # the condo's costs
    assert dm.level_is_resolved(-3_805.0, 5_383.0) is False     # the portfolio
    assert dm.level_is_resolved(-886.0, 179.0) is True          # the house's costs
    assert dm.level_is_resolved(-252.0, 642.0) is False         # the economy
    # Exactly on the boundary does not resolve: the rule is strict.
    assert dm.level_is_resolved(200.0, 100.0) is False
    assert dm.level_is_resolved(200.001, 100.0) is True


def test_level_shifts_over_a_table_agree_row_by_row_with_the_scalar_form() -> None:
    rng = np.random.default_rng(11)
    base = rng.normal(0.0, 1000.0, 400)
    frozen = np.vstack([
        base + 500.0 + rng.normal(0.0, 10.0, 400),
        base + rng.normal(0.0, 400.0, 400),
        base.copy(),
    ])
    deltas, errors = dm.level_shifts(base, frozen)
    for row in range(3):
        delta, error = dm.level_shift(base, frozen[row])
        assert deltas[row] == delta
        assert errors[row] == error
    mask = dm.level_resolved_mask(deltas, errors)
    assert mask.tolist() == [dm.level_is_resolved(deltas[i], errors[i]) for i in range(3)]
    assert mask[0] is np.True_
    # A channel whose freeze changes nothing: an exact zero shift, no error.
    assert deltas[2] == 0.0 and errors[2] == 0.0
    assert mask[2] is np.False_


def test_a_level_shift_needs_at_least_two_futures() -> None:
    with pytest.raises(ValueError, match="at least two futures"):
        dm.level_shift(np.array([1.0]), np.array([2.0]))


# ---------------------------------------------------------------------------
# 8. The bootstrap: over path indices, from a salted generator, reproducible.
# ---------------------------------------------------------------------------

def test_the_bootstrap_resamples_paths_and_not_channels() -> None:
    """The resample table is (resamples, futures) and holds PATH indices.

    A bootstrap over channels would produce a table shaped by the channel count
    and would mix one channel's figures into another's interval. The shape and
    the value range both say which axis was resampled: here there are 97 futures
    and 5 channels, so the two cannot be confused.
    """
    table = dm.bootstrap_path_indices(97, 40, 5)
    assert table.shape == (40, 97)
    assert table.min() >= 0
    assert table.max() < 97
    # Every future is reachable: 3,880 draws over 97 futures leave none unused,
    # so a table of channel indices — seven values in a 97-future shape, which
    # passes every assertion above — fails here.
    assert len(np.unique(table)) == 97
    # Drawn with replacement: a row is not a permutation of the futures.
    assert len(set(table[0].tolist())) < 97


def test_the_bootstrap_generator_is_salted_and_is_not_the_runs_own_stream() -> None:
    """The generator is addressed from the seed through a fixed salt.

    Seeding the bootstrap from the run's own generator would consume draws from
    the futures being decomposed and would make the intervals depend on how much
    of the stream had already been used. This asserts the exact derivation, so
    that swapping it for `default_rng(seed)` fails here.
    """
    seed = 42
    expected = np.random.default_rng(
        np.random.SeedSequence(entropy=seed, spawn_key=(dm.BOOTSTRAP_SPAWN_SALT,))
    ).integers(0, 500, size=(300, 500), dtype=np.int64)
    np.testing.assert_array_equal(dm.bootstrap_path_indices(500, 300, seed), expected)

    runs_own_stream = np.random.default_rng(seed).integers(0, 500, size=(300, 500), dtype=np.int64)
    assert not np.array_equal(dm.bootstrap_path_indices(500, 300, seed), runs_own_stream)
    assert dm.BOOTSTRAP_SPAWN_SALT == 20260922


def test_every_interval_recomputes_from_the_published_resample_table() -> None:
    """Rebuild all four outputs by hand from the resample table, bit for bit.

    This is the pin under the whole bootstrap: the resampling unit, the
    generator, the recomputed denominator, the percentile and the pairing across
    figures are all asserted at once, against an independent transcription of
    section 3.3's formulas.
    """
    n, k, resamples, seed = 97, 3, 40, 2024
    f_a, f_b, f_ab = build_tables(
        lambda x: x[:, 0] * 3.0 + x[:, 1] * 2.0 + x[:, 0] * x[:, 2], n, k, seed=1
    )
    first_ci, total_ci, flip_ci, sum_ci = dm.bootstrap_spread_intervals(
        f_a, f_b, f_ab, seed=seed, n_resamples=resamples
    )

    rows = dm.bootstrap_path_indices(n, resamples, seed)
    a_r, b_r = f_a[rows], f_b[rows]
    var_r = np.var(a_r, axis=1)
    first_samples = np.empty((resamples, k))
    total_samples = np.empty((resamples, k))
    flip_samples = np.empty((resamples, k))
    for channel in range(k):
        ab_r = f_ab[channel][rows]
        first_samples[:, channel] = np.mean(b_r * (ab_r - a_r), axis=1) / var_r
        total_samples[:, channel] = np.mean((a_r - ab_r) ** 2, axis=1) / (2.0 * var_r)
        flip_samples[:, channel] = np.mean(np.sign(ab_r) != np.sign(a_r), axis=1)

    for measured, samples in (
        (first_ci, first_samples),
        (total_ci, total_samples),
        (flip_ci, flip_samples),
    ):
        bounds = np.percentile(samples, [2.5, 97.5], axis=0)
        np.testing.assert_array_equal(measured, np.column_stack((bounds[0], bounds[1])))

    sum_bounds = np.percentile(first_samples.sum(axis=1), [2.5, 97.5])
    assert sum_ci == (float(sum_bounds[0]), float(sum_bounds[1]))


def test_the_block_size_cannot_change_a_bootstrap_result(monkeypatch: pytest.MonkeyPatch) -> None:
    f_a, f_b, f_ab = build_tables(lambda x: x @ np.array([2.0, 1.0]), 300, 2, seed=6)
    whole = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=3, n_resamples=50)
    monkeypatch.setattr(dm, "_BOOTSTRAP_BLOCK_ELEMENTS", 301)
    split = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=3, n_resamples=50)
    for a, b in zip(whole[:3], split[:3]):
        np.testing.assert_array_equal(a, b)
    assert whole[3] == split[3]


def test_the_bootstrap_is_reproducible_in_a_second_process() -> None:
    f_a, f_b, f_ab = build_tables(lambda x: x @ np.array([2.0, 1.0]), 400, 2, seed=21)
    here = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=99, n_resamples=60)
    script = (
        "import numpy as np, sys\n"
        "sys.path.insert(0, %r)\n"
        "from hde import decomposition_math as dm\n"
        "rng = np.random.default_rng(21)\n"
        "a = rng.standard_normal((400, 2)); b = rng.standard_normal((400, 2))\n"
        "c = np.array([2.0, 1.0])\n"
        "fa, fb = a @ c, b @ c\n"
        "fab = np.empty((2, 400))\n"
        "for i in range(2):\n"
        "    m = a.copy(); m[:, i] = b[:, i]; fab[i] = m @ c\n"
        "out = dm.bootstrap_spread_intervals(fa, fb, fab, seed=99, n_resamples=60)\n"
        "print(repr((out[0].tolist(), out[1].tolist(), out[2].tolist(), out[3])))\n"
    ) % str(Path(dm.__file__).resolve().parents[1])
    finished = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    there = eval(finished.stdout.strip())  # noqa: S307 - our own repr, our own process
    assert here[0].tolist() == there[0]
    assert here[1].tolist() == there[1]
    assert here[2].tolist() == there[2]
    assert here[3] == there[3]


def test_the_interval_width_is_calibrated_not_decorative() -> None:
    """The 95% interval covers the analytic answer about 95 times in 100.

    This is where the confidence level itself is checked, and it is the reason
    the analytic tests above assert agreement at four standard errors instead of
    containment: a percentile bootstrap can be optimistic, so the coverage is
    measured rather than assumed. Measured over 150 trials at 2,000 futures,
    per-figure coverage runs 0.947 to 0.987 — at or above nominal.
    """
    coefficients = np.array([3.0, 2.0, 1.0])
    analytic = (coefficients ** 2) / float((coefficients ** 2).sum())
    hits = 0
    trials = 40
    for trial in range(trials):
        f_a, f_b, f_ab = build_tables(lambda x: x @ coefficients, 2_000, 3, seed=50_000 + trial)
        first_ci, _t, _f, _s = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=trial)
        hits += sum(inside(first_ci[c], analytic[c]) for c in range(3))
    coverage = hits / (3 * trials)
    assert coverage > 0.85, f"95% intervals covered only {coverage:.2%} of the analytic answers"


# ---------------------------------------------------------------------------
# 9. Refusals. A surface that cannot verify refuses instead of computing.
# ---------------------------------------------------------------------------

def test_a_spread_with_no_variance_refuses_rather_than_dividing_by_zero() -> None:
    flat = np.full(50, 7.0)
    other = np.arange(50, dtype=float)
    table = np.vstack([other])
    with pytest.raises(ValueError, match="Var\\(f\\) is zero"):
        dm.first_order_indices(flat, other, table)
    with pytest.raises(ValueError, match="Var\\(f\\) is zero"):
        dm.total_order_indices(flat, table)
    with pytest.raises(ValueError, match="Var\\(f\\) is zero"):
        dm.bootstrap_spread_intervals(flat, other, table, seed=1)


def test_tables_that_do_not_match_refuse() -> None:
    f_a = np.arange(10, dtype=float)
    with pytest.raises(ValueError, match="same size"):
        dm.first_order_indices(f_a, np.arange(9, dtype=float), np.vstack([f_a]))
    with pytest.raises(ValueError, match="same futures in the same order"):
        dm.total_order_indices(f_a, np.zeros((2, 9)))
    with pytest.raises(ValueError, match="one row per channel"):
        dm.total_order_indices(f_a, f_a)
    with pytest.raises(ValueError, match="holds no channel"):
        dm.total_order_indices(f_a, np.zeros((0, 10)))
    with pytest.raises(ValueError, match="same futures in the same order"):
        dm.level_shifts(f_a, np.zeros((3, 9)))
    with pytest.raises(ValueError, match="same futures in the same order"):
        dm.level_shift(f_a, np.arange(9, dtype=float))
    with pytest.raises(ValueError, match="level shifts against"):
        dm.level_resolved_mask(np.zeros(3), np.zeros(2))


def test_a_non_finite_value_refuses() -> None:
    f_a = np.array([1.0, 2.0, np.nan, 4.0])
    good = np.array([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(ValueError, match="non-finite"):
        dm.total_order_indices(f_a, np.vstack([good]))
    with pytest.raises(ValueError, match="non-finite"):
        dm.total_order_indices(good, np.vstack([f_a]))
    with pytest.raises(ValueError, match="non-finite"):
        dm.level_shift(good, np.array([1.0, 2.0, np.inf, 4.0]))


def test_the_bootstrap_refuses_a_seed_it_cannot_reproduce_from() -> None:
    for bad in (None, -1, 3.5, "42", True):
        with pytest.raises(ValueError, match="non-negative integer seed"):
            dm.bootstrap_path_indices(100, 10, bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least two futures"):
        dm.bootstrap_path_indices(1, 10, 0)
    with pytest.raises(ValueError, match="at least one resample"):
        dm.bootstrap_path_indices(100, 0, 0)


def test_a_confidence_outside_zero_to_one_refuses() -> None:
    f_a, f_b, f_ab = build_tables(lambda x: x[:, 0], 100, 1, seed=2)
    for bad in (0.0, 1.0, 1.5, -0.1):
        with pytest.raises(ValueError, match="strictly inside"):
            dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=1, confidence=bad)


def test_an_inverted_interval_on_the_sum_refuses() -> None:
    with pytest.raises(ValueError, match="inverted"):
        dm.residual_interaction(0.9, 0.95, 0.85)


def test_a_single_future_refuses() -> None:
    with pytest.raises(ValueError, match="at least two futures"):
        dm.first_order_indices(np.array([1.0]), np.array([2.0]), np.array([[3.0]]))


# ---------------------------------------------------------------------------
# 10. The boundary this track was built behind, and the estimator's own limit.
# ---------------------------------------------------------------------------

def test_this_module_imports_no_engine_and_loads_on_its_own() -> None:
    """Loaded straight from its path, with no `hde` package imported at all.

    The whole point of developing this leg detached is that its answers can be
    checked without the simulation. A relative import added here would fail
    this load with "attempted relative import with no known parent package",
    and an absolute `hde.` import would show up in the module list below.
    """
    path = Path(dm.__file__).resolve()
    script = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('standalone_math', %r)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "assert not [m for m in sys.modules if m == 'hde' or m.startswith('hde.')], "
        "sorted(m for m in sys.modules if m.startswith('hde'))\n"
        "print(module.DEFAULT_RESAMPLES, module.BOOTSTRAP_SPAWN_SALT)\n"
    ) % str(path)
    finished = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip() == "300 20260922"

    source = path.read_text(encoding="utf-8")
    for forbidden in ("from .", "from hde", "import hde"):
        assert forbidden not in source, f"{forbidden!r} appears in a module that must stay detached"


def test_the_module_defines_no_result_type() -> None:
    """Every exchanged dataclass lives in `decomposition.py`; this module has
    none, so a figure cannot come to have two homes."""
    import dataclasses

    for name in dir(dm):
        value = getattr(dm, name)
        assert not dataclasses.is_dataclass(value), f"{name} is a result type and does not live here"
        assert not (isinstance(value, type) and issubclass(value, tuple) and hasattr(value, "_fields")), (
            f"{name} is a named tuple and does not live here"
        )


def test_the_specified_estimator_loses_precision_as_the_verdict_gets_decisive() -> None:
    """Section 3.3's estimator is not invariant to the target's own mean.

    `S_c = mean(f(B) * (f(A_B) - f(A))) / Var(f(A))` carries a term
    `E[f] * mean(f(A_B) - f(A))`, which is zero in expectation but noisy in
    sample, so the estimator's error grows with |E f| / sd(f). On the design's
    own fixture that ratio is 0.23 and the penalty is about 1%; on a decisive
    run, where one option is far ahead, it is material.

    THIS TEST RECORDS A TRADE, NOT A BLESSING. Centring the numerator's f(B) by
    its own sample mean removes the term, is identical in expectation, costs one
    subtraction, and measured 0.0447 against 0.0451 at the fixture's ratio and
    0.0447 against 0.0948 at three sigma. Adopting it will fail this test, which
    is the intended way to find out that the trade was reconsidered.
    """
    coefficients = np.sqrt(np.array([0.9, 0.1]))
    errors = {}
    for ratio in (0.0, 4.0):
        squared = []
        for trial in range(60):
            f_a, f_b, f_ab = build_tables(
                lambda x: x @ coefficients + ratio, 400, 2, seed=60_000 + trial
            )
            squared.append((dm.first_order_indices(f_a, f_b, f_ab)[0] - 0.9) ** 2)
        errors[ratio] = math.sqrt(float(np.mean(squared)))
    assert errors[4.0] > 2.0 * errors[0.0], (
        f"the mean-sensitivity is gone: {errors} — if the numerator was centred, "
        "record it in the design and retire this test"
    )
