"""
The decomposition's arithmetic: the Sobol' index estimators, the sign-flip
column, the bootstrap that puts an interval on each figure, and the level
register's paired statistics.

Pure numpy. This module imports nothing from the engine — no spec, no config,
no simulation, no result type. It takes arrays of the decision margin `f`
evaluated on matched sets of futures and returns plain floats, tuples and
arrays. The dataclasses the decomposition block exchanges live in
`decomposition.py`, so each of those truths keeps one home.

Design: `docs/specs/2026-09-22-which-risk-decides-it.md`, section 3.3 (the
estimators, the bootstrap, the flip column), 3.4 (the level arithmetic) and 4
(the interaction residual and the branch on which it refuses to print).

ONE AMENDMENT TO SECTION 3.3, ruled in section 0.1 item 13 and carried here:
the first-order numerator's `f(B)` is CENTRED by its own sample mean. Section
3.3's formula block still prints the uncentred form; the ruling supersedes it
and says why in measured terms. `first_order_indices` carries the derivation.

THE THREE TABLES, named once:

    f_a    `f` on draw set A                                  shape (n,)
    f_b    `f` on an independent draw set B                   shape (n,)
    f_ab   `f` on A with ONE channel's draws taken from B     shape (k, n)
           Row `c` differs from `f_a` in channel `c` and in nothing else.

Every function here is a statement about those tables and nothing else: it
cannot know which channel is which, and it never decides what prints.

TWO KINDS OF NUMBER, and conflating them is this feature's headline failure:

  * a SHARE OF THE SPREAD's variance — `first_order_indices`,
    `total_order_indices`. Shares sum toward 1 across channels, and
    `sum_first_order_shares` is the only function here that adds anything up.
  * a FRACTION OF FUTURES that change sides — `sign_flip_fraction_of_futures`.
    It is not a share of anything. It sums to nothing, no function here sums
    it, and on the design's own fixture the same channel reads 0.88 as a share
    and 41% as a flip fraction.

NOTHING IS EVER CLAMPED. A first-order estimate below 0 or above 1 is returned
as measured; `share_is_resolved` says it does not resolve, and the caller
prints that rather than a tidy 0.00. A clamp is the cheap all-clear in this
feature's costume.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
import numpy.typing as npt

__all__ = [
    "DEFAULT_RESAMPLES",
    "BOOTSTRAP_SPAWN_SALT",
    "LEVEL_RESOLUTION_SIGMAS",
    "DEFAULT_CONFIDENCE",
    "first_order_indices",
    "total_order_indices",
    "sign_flip_fraction_of_futures",
    "sum_first_order_shares",
    "share_is_resolved",
    "bootstrap_path_indices",
    "bootstrap_spread_intervals",
    "residual_interaction",
    "level_shift",
    "level_shifts",
    "level_is_resolved",
    "level_resolved_mask",
]

Array = npt.NDArray[np.float64]

# Section 3.3: 300 resamples of the path index, vectorised. They cost no model
# evaluation, so this is the whole price of an interval on every figure.
DEFAULT_RESAMPLES = 300

DEFAULT_CONFIDENCE = 0.95

# The bootstrap's generator is derived from the run's seed and this fixed salt,
# NEVER from the run's own stream (section 3.3). Two consequences, both load
# bearing: the decomposition consumes no draw from the futures it decomposes,
# and two processes at one seed produce byte-identical intervals. The value is
# the design's date and is fixed forever — changing it silently re-rolls every
# published interval.
BOOTSTRAP_SPAWN_SALT = 20260922

# Section 3.4: a level shift is a number only when it clears twice its own
# paired standard error. The rest are named as indistinguishable from zero at
# this sample size — a row the reader must see, never an absence.
LEVEL_RESOLUTION_SIGMAS = 2.0

# Resample work is done in blocks of at most this many floats so that a large
# path count cannot turn a sub-second bootstrap into a memory event. The block
# size cannot change any result: the whole index table is drawn first, once.
_BOOTSTRAP_BLOCK_ELEMENTS = 2_000_000


def _futures(name: str, values: object) -> Array:
    """One value of `f` per future, validated. Refuses rather than propagating."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(
            f"{name} must be one-dimensional (one value of f per future); got shape {arr.shape}"
        )
    if arr.size < 2:
        raise ValueError(f"{name} needs at least two futures; got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains a non-finite value; no index is defined over it")
    return arr


def _channel_table(name: str, values: object, n_futures: int) -> Array:
    """The (k, n) table, one row per channel, validated against the path count."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(
            f"{name} must be two-dimensional, one row per channel (k, n); got shape {arr.shape}"
        )
    if arr.shape[0] < 1:
        raise ValueError(f"{name} holds no channel; there is nothing to decompose")
    if arr.shape[1] != n_futures:
        raise ValueError(
            f"{name} has {arr.shape[1]} futures per channel but f(A) has {n_futures}; "
            "the two tables must be the same futures in the same order"
        )
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains a non-finite value; no index is defined over it")
    return arr


def _matched(f_a: object, f_b: object) -> Tuple[Array, Array]:
    a = _futures("f(A)", f_a)
    b = _futures("f(B)", f_b)
    if b.shape != a.shape:
        raise ValueError(
            f"f(A) has {a.size} futures and f(B) has {b.size}; "
            "the two draw sets must be the same size"
        )
    return a, b


def _variance_of_f(f_a: Array) -> float:
    """Var(f(A)), the denominator both estimators divide by (section 3.3).

    Population variance (1/N), matching the 1/N means in both numerators.
    """
    var = float(np.var(f_a))
    if not var > 0.0:
        raise ValueError(
            "Var(f) is zero over these futures: every index would be 0/0. "
            "A run with no decision spread refuses this block rather than printing shares."
        )
    return var


def first_order_indices(f_a: object, f_b: object, f_ab: object) -> Array:
    """S_c for every channel — the Saltelli 2010 estimator, CENTRED.

        S_c = mean( (f(B) - mean f(B)) * (f(A_B^(c)) - f(A)) ) / Var(f(A))

    Reads: if you learned channel `c`'s realization exactly and nothing else,
    the spread's variance would fall by this fraction. It is NOT how often the
    channel changes the answer — that is `sign_flip_fraction_of_futures`.

    `f(B)` in the numerator is not interchangeable with `f(A)`: B and A_B^(c)
    share channel `c` and nothing else, which is what makes the product estimate
    Var(E[f | X_c]). Written with `f(A)` there, the estimator returns the
    NEGATIVE of the index on an additive model.

    WHY f(B) IS CENTRED (design section 0.1 item 13, ruled 2026-09-22, a change
    to the mechanism taken on measured grounds): uncentred, the numerator
    carries an `E[f] * mean(f(A_B) - f(A))` term which is zero in expectation
    and noisy in sample, so the estimator's error grows with `|E f| / sd(f)` —
    about 1% at this target's measured 0.23, 1.17x at one sigma and 2.1x at
    three. Three sigma is a DECISIVE run, so the attribution was worst exactly
    where the engine tells a household the answer is settled. Subtracting f(B)'s
    own sample mean removes the term and is identical in expectation, because
    `f(A_B^(c)) - f(A)` is itself mean-zero.

    Returns one value per channel, as measured — outside [0, 1] when the
    estimator's own noise puts it there. Never clamped.
    """
    a, b = _matched(f_a, f_b)
    ab = _channel_table("the f(A_B) table", f_ab, a.size)
    variance = _variance_of_f(a)
    numerator: Array = np.mean((b - np.mean(b)) * (ab - a), axis=1)
    return numerator / variance


def total_order_indices(f_a: object, f_ab: object) -> Array:
    """S_Tc for every channel — the Jansen 1999 estimator of section 3.3.

        S_Tc = mean( (f(A) - f(A_B^(c)))^2 ) / (2 * Var(f(A)))

    Reads: the share of the spread that would remain if every OTHER channel were
    learned exactly — first order plus every interaction the channel is in.

    The 2 in the denominator is the estimator, not a convention: f(A) and
    f(A_B^(c)) differ only in channel `c`, so the mean squared difference is
    TWICE the expected conditional variance. Dropping it doubles every total.

    `f(B)` is not an argument because the estimator does not read it; an
    argument it ignored would be a place for a defect to hide.
    """
    a = _futures("f(A)", f_a)
    ab = _channel_table("the f(A_B) table", f_ab, a.size)
    variance = _variance_of_f(a)
    numerator: Array = np.mean((a - ab) ** 2, axis=1)
    return numerator / (2.0 * variance)


def sign_flip_fraction_of_futures(f_a: object, f_ab: object) -> Array:
    """The fraction of futures in which re-drawing ONE channel changes the sign of `f`.

    NOT A SHARE. This is a count of futures divided by the futures counted: it
    has no denominator in the spread, it does not sum to one, it does not sum to
    anything, and nothing in this module adds it up. It is the only column that
    speaks in decision space, and section 3.3 makes it never optional for that
    reason.

    A future sitting at exactly f = 0 carries its own sign and counts as flipped
    against any non-zero value — which is the honest reading of a future that sat
    on the boundary before the channel was re-drawn.

    A channel that consumes no draw gives back f(A) bit for bit, so its flip
    fraction is exactly 0.0.
    """
    a = _futures("f(A)", f_a)
    ab = _channel_table("the f(A_B) table", f_ab, a.size)
    flipped: Array = np.mean(np.sign(ab) != np.sign(a), axis=1)
    return flipped


def sum_first_order_shares(first_order: object) -> float:
    """Sigma S_c — the first-order shares, added up.

    The only sum in this module, and it takes first-order shares only. Its value
    against 1 is what `residual_interaction` branches on.
    """
    arr = np.asarray(first_order, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"the first-order shares must be one per channel; got shape {arr.shape}")
    return float(arr.sum())


def share_is_resolved(share: float) -> bool:
    """False for a share the estimator's noise put outside [0, 1] (section 4).

    The caller prints such a row as `not resolved at N futures` alongside the
    measured value and its interval. It never clamps it into range: a negative
    index printed as 0.00 reads as "measured, and it does not matter", which is
    a different claim from "this sample cannot tell".
    """
    value = float(share)
    return bool(0.0 <= value <= 1.0)


def bootstrap_path_indices(n_futures: int, n_resamples: int, seed: int) -> npt.NDArray[np.int64]:
    """The resample table: `n_resamples` rows, each `n_futures` PATH indices with replacement.

    The resampling unit is the path — a future, drawn whole, so that f(A), f(B)
    and every row of the f(A_B) table are re-read at the SAME futures and the
    figures stay paired inside each resample. Channels are never resampled:
    there are seven of them, they are a fixed table, and their sampling error is
    not what an interval here is about.

    Public so that a test can rebuild the resample table itself and recompute
    every interval from it by hand.

    The generator is `SeedSequence(entropy=seed, spawn_key=(BOOTSTRAP_SPAWN_SALT,))`
    — addressed from the run's seed, never the run's own generator, so this
    consumes nothing from the simulation and reproduces across processes.
    """
    if not isinstance(n_futures, (int, np.integer)) or n_futures < 2:
        raise ValueError(f"the bootstrap needs at least two futures; got {n_futures!r}")
    if not isinstance(n_resamples, (int, np.integer)) or n_resamples < 1:
        raise ValueError(f"the bootstrap needs at least one resample; got {n_resamples!r}")
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, bool) or int(seed) < 0:
        raise ValueError(
            f"the bootstrap needs the run's non-negative integer seed to reproduce; got {seed!r}"
        )
    sequence = np.random.SeedSequence(entropy=int(seed), spawn_key=(BOOTSTRAP_SPAWN_SALT,))
    generator = np.random.default_rng(sequence)
    table: npt.NDArray[np.int64] = generator.integers(
        0, int(n_futures), size=(int(n_resamples), int(n_futures)), dtype=np.int64
    )
    return table


def bootstrap_spread_intervals(
    f_a: object,
    f_b: object,
    f_ab: object,
    *,
    seed: int,
    n_resamples: int = DEFAULT_RESAMPLES,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Tuple[Array, Array, Array, Tuple[float, float]]:
    """Percentile intervals on every figure of the spread register, and on Sigma S_c.

    Returns, in order:

        first_order_ci   (k, 2) — [low, high] per channel for S_c
        total_order_ci   (k, 2) — [low, high] per channel for S_Tc
        flip_ci          (k, 2) — [low, high] per channel for the flip FRACTION
        sum_ci           (low, high) for Sigma S_c, which the residual branches on

    Every resample recomputes the denominator Var(f(A)) as well as the
    numerators: the denominator is a statistic of the same futures, and holding
    it fixed would understate every width.

    Costs no model evaluation. A channel that consumes no draw has an interval of
    exactly [0.0, 0.0] on all three figures, because every resample of an
    identical table gives exactly 0.
    """
    a, b = _matched(f_a, f_b)
    ab = _channel_table("the f(A_B) table", f_ab, a.size)
    _variance_of_f(a)
    if not 0.0 < float(confidence) < 1.0:
        raise ValueError(f"confidence must lie strictly inside (0, 1); got {confidence!r}")

    n_futures = a.size
    n_channels = ab.shape[0]
    indices = bootstrap_path_indices(n_futures, n_resamples, seed)

    first_order = np.empty((n_resamples, n_channels), dtype=np.float64)
    total_order = np.empty((n_resamples, n_channels), dtype=np.float64)
    flips = np.empty((n_resamples, n_channels), dtype=np.float64)

    block = max(1, _BOOTSTRAP_BLOCK_ELEMENTS // n_futures)
    for start in range(0, n_resamples, block):
        stop = min(start + block, n_resamples)
        rows = indices[start:stop]
        a_r = a[rows]
        b_r = b[rows]
        var_r = np.var(a_r, axis=1)
        if not np.all(var_r > 0.0):
            raise ValueError(
                "a resample drew futures of identical f: Var(f) is zero inside the bootstrap. "
                "Too few futures to interval this decomposition."
            )
        sign_a_r = np.sign(a_r)
        # Centred per RESAMPLE, by that resample's own mean: the bootstrap
        # applies the whole estimator to each resample, the way `var_r` is
        # recomputed rather than held at the full sample's value.
        b_r_centred = b_r - np.mean(b_r, axis=1, keepdims=True)
        for channel in range(n_channels):
            ab_r = ab[channel][rows]
            first_order[start:stop, channel] = (
                np.mean(b_r_centred * (ab_r - a_r), axis=1) / var_r
            )
            total_order[start:stop, channel] = np.mean((a_r - ab_r) ** 2, axis=1) / (2.0 * var_r)
            flips[start:stop, channel] = np.mean(np.sign(ab_r) != sign_a_r, axis=1)

    # Written so that the default lands on exactly 2.5 and 97.5: the obvious
    # `100 * (1 - confidence) / 2` evaluates to 2.500000000000002, which shifts
    # the interpolated bound by an ULP and makes a published figure depend on an
    # arithmetic accident rather than on the confidence level.
    half_width = 50.0 * float(confidence)
    low_q = 50.0 - half_width
    high_q = 50.0 + half_width

    def interval_per_channel(samples: Array) -> Array:
        bounds = np.percentile(samples, [low_q, high_q], axis=0)
        stacked: Array = np.column_stack((bounds[0], bounds[1]))
        return stacked

    sums = first_order.sum(axis=1)
    sum_bounds = np.percentile(sums, [low_q, high_q])
    return (
        interval_per_channel(first_order),
        interval_per_channel(total_order),
        interval_per_channel(flips),
        (float(sum_bounds[0]), float(sum_bounds[1])),
    )


def residual_interaction(
    sum_of_shares: float, sum_low: float, sum_high: float
) -> Optional[Tuple[float, float, float]]:
    """The interaction residual `1 - Sigma S_c`, or None when it must not print.

    Section 4's rule, and the refusal is the point of the function:

      * the interval lies entirely BELOW 1 -> `(residual, low, high)`, movement
        no single channel owns;
      * the interval includes or exceeds 1 -> None. The shares add to more than
        the whole, which is estimator noise and not a finding, and a residual
        computed from it would be a negative number dressed as a measurement.
        The caller says interaction is not measurable at this sample size and
        names the figure to raise.

    Returning None rather than a number with a flag is deliberate: a caller
    cannot print a residual it was never given.
    """
    low = float(sum_low)
    high = float(sum_high)
    if low > high:
        raise ValueError(f"the interval on Sigma S_c is inverted: [{low}, {high}]")
    if not high < 1.0:
        return None
    point = float(sum_of_shares)
    return (1.0 - point, 1.0 - high, 1.0 - low)


def level_shift(f_base: object, f_frozen: object) -> Tuple[float, float]:
    """One channel's level effect and its PAIRED standard error (section 3.4).

    `f_base` and `f_frozen` are the SAME futures, differing only in that the
    channel was priced the way the central case prices it. Returns
    `(delta, standard_error)` where delta is the mean of the per-future
    difference — what the futures price that the central case does not.

    The standard error is taken on the DIFFERENCE, not on the two samples: the
    pairing is what makes a $125,074 shift readable against a $286,506 spread.
    An unpaired error on the same tables is larger by orders of magnitude and
    would report every channel as unresolved.
    """
    base = _futures("f (base)", f_base)
    frozen = _futures("f (frozen)", f_frozen)
    if frozen.shape != base.shape:
        raise ValueError(
            f"the frozen run has {frozen.size} futures and the base run {base.size}; "
            "a paired difference needs the same futures in the same order"
        )
    difference = frozen - base
    error = float(np.std(difference, ddof=1) / math.sqrt(difference.size))
    return float(np.mean(difference)), error


def level_shifts(f_base: object, f_frozen: object) -> Tuple[Array, Array]:
    """`level_shift` for a whole (k, m) table of frozen runs: `(deltas, standard_errors)`."""
    base = _futures("f (base)", f_base)
    frozen = _channel_table("the frozen table", f_frozen, base.size)
    difference = frozen - base
    deltas: Array = np.mean(difference, axis=1)
    errors: Array = np.std(difference, axis=1, ddof=1) / math.sqrt(base.size)
    return deltas, errors


def level_is_resolved(delta: float, standard_error: float) -> bool:
    """Section 3.4's rule: a level shift resolves when |delta| > 2 * SE.

    False is not silence. The caller names the channel and prints the measured
    pair as indistinguishable from zero at this sample size — which is the whole
    finding on a channel that carries most of the spread and moves nothing.
    """
    return bool(abs(float(delta)) > LEVEL_RESOLUTION_SIGMAS * float(standard_error))


def level_resolved_mask(deltas: object, standard_errors: object) -> npt.NDArray[np.bool_]:
    """`level_is_resolved` across a table — one home for the factor of 2."""
    delta_arr = np.asarray(deltas, dtype=np.float64)
    error_arr = np.asarray(standard_errors, dtype=np.float64)
    if delta_arr.shape != error_arr.shape:
        raise ValueError(
            f"{delta_arr.shape} level shifts against {error_arr.shape} standard errors"
        )
    mask: npt.NDArray[np.bool_] = np.abs(delta_arr) > LEVEL_RESOLUTION_SIGMAS * error_arr
    return mask
