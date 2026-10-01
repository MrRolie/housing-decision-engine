"""
--break-even: solve ONE input for the value where two priced options' deterministic
total PVs cross, plus the tie-band edges around it.

Why (2026-09-02, operator product direction): most users arrive certain about
one side ("houses around $650k") and want the threshold on the other ("what
rent keeps renting the better deal?"), or the reverse ("at my rent, what price
makes buying worth it?"). A --sweep grid brackets that point; this solves it,
through the same loader as every run, on the deterministic line (the Monte
Carlo floor is the verdict's business, not a threshold's).

The tie band is the verdict's own (anchors: verdict.tie_band): between the two
edges the gap is under that fraction of the cheaper option's PV, so the answer
reads "A is cheaper below X, too close to call between L and H, B above H".
"""
from __future__ import annotations

import copy
import math
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .anchors import ANCHORS
from .config import ConfigValidationError, load_config_dict, single_path_run
from .decomposition import (BOUNDARY_FIELDS,
                            EstimatedReversal, ExactReversal, RefusedBoundary,
                            RefusedReversal, ReversalRegister, SampledBoundary,
                            SolvedBoundary, StructuralZero)
from .deterministic import compute_deterministic
from .models import (ComparisonDeterministicResult, ComparisonMonteCarloResult, ComparisonSpec,
                     MonteCarloOptionResult, Verdict, compute_verdict)
# `_summarize_array` is the reversal register's, on purpose: the free curve has
# to rebuild each option's summary from the shifted array, and `compute_verdict`
# reads `summary.mean` for `mc_mean_best`. Reusing the base run's summary leaves
# that figure stale and the free curve then disagrees with a true re-simulation
# at the same value (spec §6, T11).
from .monte_carlo import _summarize_array, run_monte_carlo
from .rates import RateConventionError, compose, deflate, resolve_convention
from .market_scenario import (LoadedScenarioPrior, band_horizon_for_calendar_year,
                              calendar_year_for_sim_year)
from .sources import MONEY_LEAVES
from .sweep import (INT_KEYS, _fmt_value, affordability_of, base_value, constant_options,
                    flattened_path_note,
                    join_notes, load_at, point_label, price_scan_note,
                    real_equivalent_inflation, stated_path, with_value)

# How many points `solve_crossings` reads each pair's gap at before it bisects
# a sign change (an integer key: at most this many). The reversal register
# reads a deterministic field at the same points when no crossing moves it.
CROSSING_SCAN_POINTS = 9

# The default bracket for a money input, as multiples of its base value; any
# other key needs lo:hi. The story's act 6 solves the rent threshold on this
# same bracket, so the act and `--break-even rent.monthly_rent` search alike.
MONEY_BRACKET = (0.25, 4.0)
# The dollar leaves, by name — one set for the default bracket and for how a
# bound or grid point prints (`sweep._fmt_value`), so the two cannot disagree
# about a key's kind (2026-09-08).
_MONEY_KEYS = MONEY_LEAVES

# Rates whose domain stops at 0 beside the dollar leaves: a tax or cost rate,
# a mortgage rate, a share of price or income. A growth, escalation, return
# or discount rate may be negative and is deliberately absent — its floor is
# open (2026-09-08: a property-tax rate widened to 0% was then offered
# "widen with … = -0.005:…", one bracket width below a floor the input
# cannot cross).
_FLOOR_AT_ZERO_LEAVES = frozenset({
    "property_tax_rate", "purchase_costs_rate", "annual_maintenance_rate", "mortgage_rate",
    # A renewal rate sits here for the same reason `mortgage_rate` does, and it
    # was missing: the loader refuses a negative one outright
    # (`mortgage_renewal_rates must be >= 0`), so a widen hint that offered one
    # would name a bracket no point of which loads (2026-09-22).
    "mortgage_renewal_rates",
    "selling_cost_rate", "reserve_contribution_rate", "marginal_rate",
    "retirement_marginal_rate", "affordability_threshold",
})


def floor_at_zero(key: str) -> bool:
    """True for an input the widen hint must never take below 0 — a dollar
    figure, one of the rates above, or a volatility."""
    leaf = key.rsplit(".", 1)[-1]
    return leaf in _MONEY_KEYS or leaf in _FLOOR_AT_ZERO_LEAVES or leaf.endswith("_vol")

# A rate has no natural multiple of itself (0% growth × 4 is still 0%), so its
# default bracket is absolute: the plausible range for that rate, wide enough to
# hold the crossing and narrow enough that every point loads. 2026-09-03 review:
# `--break-even condo.value_growth_rate` refused with "only money inputs get a
# default bracket", and the threshold question users actually ask about growth
# needed a bracket they had no way to guess. The bracket used is always printed.
RATE_BRACKETS: Dict[str, Tuple[float, float]] = {
    "value_growth_rate": (-0.02, 0.05),        # on the config's own axis (as quoted by default): a shrinking market to a hot one
    "rent_escalation_rate": (-0.01, 0.05),     # shelter-cost growth, on the same axis
    "annual_maintenance_rate": (0.0, 0.03),    # nothing modelled to a high-upkeep house
    "mortgage_rate": (0.01, 0.10),             # as quoted (semi-annual by default), two decades of Canadian rates
    "discount_rate": (0.0, 0.08),              # the loader refuses outside [0, 15%]
}
# The renewal ladder searches the CONTRACT rate's own bracket, read from that
# entry rather than restated: config.py types a renewal rate as "a quoted
# contract rate of `mortgage_rate`'s class" and converts both through
# `mortgage_rate_compounding`, so the two cannot plausibly want different
# ranges and widening one must widen the other (2026-09-22, board item 4 §6).
# Before this entry the leaf had NO bracket — `RATE_BRACKETS` is keyed by the
# leaf — so `--break-even <opt>.mortgage_renewal_rates` refused rather than
# borrowing one. The bracket is set in the engine like every other entry here
# and is printed on every solve, which is the only thing that keeps it a
# declared convention rather than a silent one.
RATE_BRACKETS["mortgage_renewal_rates"] = RATE_BRACKETS["mortgage_rate"]


def parse_break_even(arg: str) -> Tuple[str, Optional[float], Optional[float]]:
    """'KEY' or 'KEY=lo:hi' -> (key, lo, hi)."""
    key, sep, spec = arg.partition("=")
    key, spec = key.strip(), spec.strip()
    if not key:
        raise ValueError(f"--break-even expects KEY or KEY=lo:hi, got {arg!r}")
    if not sep:
        return key, None, None
    parts = spec.split(":")
    if len(parts) != 2:
        raise ValueError(f"--break-even bracket form is KEY=lo:hi, got {arg!r}")
    lo, hi = float(parts[0]), float(parts[1])
    if not lo < hi:
        raise ValueError(f"--break-even bracket needs lo < hi, got {spec!r}")
    return key, lo, hi


_raw_value = base_value  # one reader of the raw YAML, shared with the sweep


def _priced_options(raw: Dict[str, Any]) -> List[str]:
    return [o for o in ("condo", "house", "rent") if o in raw]


def _solver_point(v: float, is_int: bool) -> Any:
    """The value the solver prices for the grid point v: an integer input at
    its nearest whole number (Python's `round`, a half to the even one),
    anything else as v itself."""
    return int(round(v)) if is_int else float(v)


def solve_crossings(
    key: str,
    options: Tuple[str, str],
    lo: float,
    hi: float,
    totals_at: Callable[[float], Optional[Tuple[float, float]]],
    *,
    is_int: bool = False,
    iterations: int = 60,
    refused: Optional[List[Tuple[float, str]]] = None,
    to_adjacent_floats: bool = False,
) -> Dict[str, Any]:
    """
    The solver itself, over ANY pair of total-PV curves. A coarse scan of the
    bracket finds every sign change of gap(v) = total_pv(A) − total_pv(B) (the
    gap need not be monotone in the input); each is refined by bisection, and
    the tie-band edges around it are solved the same way, walking outward from
    the crossing one grid cell at a time (a second crossing ends the band: that
    edge is None).

    ``totals_at(v)`` returns the two totals at v, or None when the caller
    refuses that value (its reason appended to the ``refused`` list the caller
    passes in); each distinct v is asked for once. The search shrinks to the
    accepted run(s), reported as "searched", and a bracket refused throughout
    raises. Those refusal messages name ``--break-even`` because it is the only
    surface that refuses — the story's act 6 sweeps an already-validated spec.

    With ``to_adjacent_floats`` the bisection of each crossing runs on past
    that stop until its two ends are adjacent floats, and the entry's
    ``value`` is the lower end, with ``bracket`` holding both. A gap of exactly
    zero then counts with the first option's side, as `models.compute_verdict`
    ranks a tie.
    """
    a, b = options
    band = ANCHORS["verdict.tie_band"].value
    refused = [] if refused is None else refused
    cache: Dict[float, Optional[Tuple[float, float]]] = {}
    priced: Dict[float, Any] = {}  # each point the solver is asked for -> the value it prices

    def totals_or_none(v: float) -> Optional[Tuple[float, float]]:
        """The two totals at v, or None when the caller refuses that value (a
        price below the fixed down payment, a rate outside its bounds): the
        refusal is recorded, never raised — the search shrinks to what the
        config accepts and the output says so."""
        vv = _solver_point(v, is_int)
        priced[v] = vv
        if vv not in cache:
            cache[vv] = totals_at(vv)
        return cache[vv]

    def totals(v: float) -> Tuple[float, float]:
        t = totals_or_none(v)
        if t is None:
            reason = refused[-1][1] if refused else "value refused"
            raise ValueError(
                f"--break-even {key}: the loader refused {_fmt_value(key, v)} inside a bracket "
                f"whose ends it accepted ({reason}) — give a bracket the config accepts (KEY=lo:hi)"
            )
        return t

    def gap_or_none(v: float) -> Optional[float]:
        t = totals_or_none(v)
        return None if t is None else t[0] - t[1]

    def gap(v: float) -> float:
        ta, tb = totals(v)
        return ta - tb

    def frac(v: float) -> float:
        """Signed gap as a fraction of the cheaper option's PV (the verdict's denominator)."""
        ta, tb = totals(v)
        denom = abs(min(ta, tb)) or abs(max(ta, tb))
        return (ta - tb) / denom if denom else 0.0

    def bisect(f: Callable[[float], float], x0: float, x1: float) -> float:
        f0, f1 = f(x0), f(x1)
        if f0 == 0.0:
            return x0
        if f1 == 0.0:
            return x1
        for _ in range(iterations):
            mid = 0.5 * (x0 + x1)
            fm = f(mid)
            if fm == 0.0 or (x1 - x0) < (1e-9 * max(1.0, abs(x1))):
                return mid
            if (f0 < 0) == (fm < 0):
                x0, f0 = mid, fm
            else:
                x1, f1 = mid, fm
        return 0.5 * (x0 + x1)

    def adjacent(f: Callable[[float], float], x0: float, x1: float) -> Tuple[float, float]:
        """`bisect`'s halving, carried on until no float lies strictly between
        the two ends."""
        first = f(x0) <= 0
        for _ in range(4 * iterations):
            mid = 0.5 * (x0 + x1)
            if not x0 < mid < x1:
                break
            if (f(mid) <= 0) == first:
                x0 = mid
            else:
                x1 = mid
        return x0, x1

    def scan(x_lo: float, x_hi: float) -> Tuple[List[float], List[Optional[float]]]:
        n = (CROSSING_SCAN_POINTS if not is_int
             else max(2, min(CROSSING_SCAN_POINTS, int(x_hi - x_lo) + 1)))
        pts = [x_lo + (x_hi - x_lo) * i / (n - 1) for i in range(n)]
        return pts, [gap_or_none(x) for x in pts]

    def solve_run(xs: List[float], ys: List[Optional[float]]) -> List[Dict[str, Any]]:
        """Every sign change on one accepted run of the grid, each refined by
        bisection, with the tie-band edges found by walking outward from the
        crossing one grid cell at a time — so a second crossing further along
        the grid ends the band (edge None) instead of being searched across."""

        def edge(v: float, j: int, step: int) -> Optional[float]:
            inner, side = v, 0.0
            while 0 <= j < len(xs):
                if ys[j] is None:
                    return None
                outer = xs[j]
                fo = frac(outer)
                if side == 0.0:
                    side = 1.0 if fo > 0 else (-1.0 if fo < 0 else 0.0)
                elif fo != 0.0 and (fo > 0) != (side > 0):
                    return None  # the next crossing comes before the band edge
                if side and abs(fo) >= band:
                    target = side * band
                    return bisect(lambda x: frac(x) - target, min(inner, outer), max(inner, outer))
                inner = outer
                j += step
            return None

        found: List[Dict[str, Any]] = []
        for i in range(1, len(xs)):
            y0, y1 = ys[i - 1], ys[i]
            if y0 is None or y1 is None:
                continue
            if to_adjacent_floats:
                if (y0 <= 0) == (y1 <= 0):
                    continue
                x0, x1 = xs[i - 1], xs[i]
            elif y0 == 0.0:
                x0 = x1 = xs[i - 1]
            elif y0 * y1 < 0:
                x0, x1 = xs[i - 1], xs[i]
            else:
                continue
            ends = None
            if x0 == x1:
                v = x0
            elif to_adjacent_floats:
                ends = adjacent(gap, x0, x1)
                v = ends[0]
            else:
                v = bisect(gap, x0, x1)
            if x0 == x1:
                probe = min(x1 + 1e-9 * max(1.0, abs(x1)), xs[-1])
                below, above = (a, b) if gap(probe) > 0 else (b, a)
                left = edge(v, i - 2, -1)
            else:
                below, above = (a, b) if y0 <= 0 else (b, a)  # gap<0 ⇒ A cheaper
                left = edge(v, i - 1, -1)
            right = edge(v, i, +1)
            if is_int:
                # An integer input is a step function: report the first value where
                # the above-side option is cheaper, and integer band edges.
                first_above = int(math.ceil(v - 1e-9))
                if gap(first_above) == 0.0 or ((gap(first_above) < 0) == (a == below)):
                    first_above += 1
                entry: Dict[str, Any] = {
                    "value": first_above, "last_value_below": first_above - 1,
                    "cheaper_below": below, "cheaper_above": above,
                    "tie_band": [None if left is None else int(math.floor(left)),
                                 None if right is None else int(math.ceil(right))],
                }
            else:
                entry = {
                    "value": v,
                    "cheaper_below": below, "cheaper_above": above,
                    "tie_band": [left, right],
                }
                if to_adjacent_floats:
                    entry["bracket"] = list(ends if ends is not None else (v, v))
            # Band-first, and FIRST in the entry: three evaluation runs copied the
            # crossing-first shape into the user's text ("$2,663: renting below,
            # buying above; too close between…" contradicts itself on the gap).
            # The band rule itself is the block header's, said once.
            found.append({"sentence": band_sentence(key, entry, band, band_clause=False), **entry})
        return found

    xs, ys = scan(lo, hi)
    # Contiguous runs of grid points the loader accepted. A run narrower than the
    # bracket is re-scanned at full resolution: a refused tail costs no precision,
    # and the output reports what was actually searched.
    runs: List[List[float]] = []
    cur: List[float] = []
    for x, y in zip(xs, ys):
        if y is None:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
        else:
            cur.append(x)
    if len(cur) >= 2:
        runs.append(cur)
    if not runs:
        reason = refused[0][1] if refused else "every point refused"
        raise ValueError(
            f"--break-even {key}: the loader refused every point in the bracket "
            f"{_fmt_value(key, lo)}–{_fmt_value(key, hi)} ({reason}) — "
            f"give a bracket the config accepts (KEY=lo:hi)"
        )

    break_evens: List[Dict[str, Any]] = []
    searched: List[List[float]] = []
    first_gap: Optional[float] = None
    last_gap: Optional[float] = None
    for run in runs:
        r_lo, r_hi = run[0], run[-1]
        rxs, rys = (xs, ys) if (r_lo, r_hi) == (lo, hi) else scan(r_lo, r_hi)
        searched.append([r_lo, r_hi])
        accepted = [y for y in rys if y is not None]
        if first_gap is None and accepted:
            first_gap = accepted[0]
        if accepted:
            last_gap = accepted[-1]
        break_evens.extend(solve_run(rxs, rys))

    out: Dict[str, Any] = {
        "key": key, "options": [a, b], "bracket": [lo, hi], "searched": searched,
        "tie_band_fraction": band, "break_evens": break_evens,
    }
    if not break_evens:
        out["cheaper_throughout"] = a if (first_gap or 0.0) < 0 else b
        record = no_crossing_record(
            key, out["cheaper_throughout"], searched, (lo, hi),
            first_gap or 0.0, last_gap or 0.0, is_int=is_int)
        # The ends as priced, read from the solver's own memo rather than
        # rounded again: a grid point of 3.75 on a term in years was priced as
        # a 4-year term (2026-10-01). Set after `widen` is derived, and apart
        # from `searched`, so the widen hint and the refusal line do not move.
        record["lo"], record["hi"] = priced[record["lo"]], priced[record["hi"]]
        out["no_crossing"] = record
    return out


def _arg_value(key: str, v: float) -> str:
    """One bracket bound as the CLI accepts it (no separators, whole numbers
    where the input takes them) — the widen hint is meant to be pasted."""
    if key in INT_KEYS or float(v).is_integer():
        return str(int(round(v)))
    return f"{v:.6g}"


def no_crossing_record(
    key: str, cheaper: str, searched: List[List[float]], asked: Tuple[float, float],
    gap_lo: float, gap_hi: float, *, is_int: bool = False,
) -> Dict[str, Any]:
    """What a bracket with no crossing has to say: the bounds it held for,
    which option is cheaper at each end, and the widened bracket to try —
    on the side where the gap narrows, one bracket width further out (a money
    input never below half its low end, an integer input never below 1).

    2026-09-04: `<opt> is cheaper throughout` named neither the bounds it held
    for nor what to run next. `widen` is None when the gap narrows toward an
    end the config refuses beyond — no bracket reaches a crossing there.

    2026-09-08: an input whose domain stops at 0 (`floor_at_zero`) is never
    widened below it. `at_floor` is True when the gap narrows toward the low
    end and that end already sits at 0: nothing below is searchable, so the
    hint goes UP instead (when the high end is open), and the sentence says
    the range ran down to 0.
    """
    lo, hi = searched[0][0], searched[-1][1]
    side = "high" if abs(gap_hi) < abs(gap_lo) else "low"
    width = hi - lo
    floor = floor_at_zero(key)
    at_floor = floor and side == "low" and lo <= 0
    open_end = (hi == asked[1]) if (side == "high" or at_floor) else (lo == asked[0])
    widen: Optional[List[float]] = None
    if open_end and width > 0:
        if side == "high" or at_floor:
            widen = [lo, hi + width]
        else:
            new_lo = lo - width
            if lo > 0:
                new_lo = max(new_lo, lo / 2)
            if floor:
                new_lo = max(new_lo, 0.0)
            if is_int:
                new_lo = max(1.0, float(math.floor(new_lo)))
            widen = [new_lo, hi]
    return {"lo": lo, "hi": hi, "cheaper": cheaper, "narrows_toward": side,
            "at_floor": at_floor, "widen": widen}


def solve_break_even(
    raw: Dict[str, Any], key: str, lo: Optional[float] = None, hi: Optional[float] = None,
    *, iterations: int = 60, prior: Optional[LoadedScenarioPrior] = None,
) -> Dict[str, Any]:
    """
    The threshold on one YAML input, for the two priced options (A, B in the
    order condo, house, rent): every grid point re-runs the comparison through
    the same loader, and ``solve_crossings`` does the searching. Grid points the
    loader refuses (a price below the fixed down payment) are recorded under
    "refused" and the search shrinks to the accepted run(s), reported as
    "searched". Raises ValueError when the config prices more or fewer than two
    options, when the key is not in the YAML and no bracket was given, or when
    every point of the bracket is refused.
    """
    options = _priced_options(raw)
    if len(options) != 2:
        raise ValueError(
            f"--break-even needs exactly two priced options, got {options or 'none'} — "
            f"drop one section or answer the pairwise question in two runs"
        )
    a, b = options
    base = _raw_value(raw, key)
    if lo is None or hi is None:
        field = key.rsplit(".", 1)[-1]
        if field in RATE_BRACKETS:
            # A rate's default bracket is absolute, so it does not need the key
            # to be in the YAML: an omitted growth rate defaulted to 0% is still
            # a threshold question ("what growth would make buying win?").
            lo, hi = RATE_BRACKETS[field]
        elif base is not None and field in _MONEY_KEYS:
            lo, hi = MONEY_BRACKET[0] * float(base), MONEY_BRACKET[1] * float(base)
        else:
            if base is None:
                why = "the key is not in the YAML"
            elif field.endswith(("_rate", "_rates")):
                # A rate IS in the YAML and still has no default bracket — the
                # old sentence said "only money and rate inputs get a default
                # bracket" while refusing a rate input, leaving the user who
                # followed the schema's own suggestion with nothing to do next
                # (2026-09-21).
                #
                # The sentence itself is the second half of that fix and it was
                # wrong: written for the renewal ladder, it told every one of
                # the twelve rate leaves that still land here that "the engine
                # forecasts no renewal path" — true, and nothing to do with
                # `economic.inflation_rate`. Now it names the refused key's own
                # situation in the branch's own terms, and the one key the old
                # prose WAS about has a bracket and no longer reaches here
                # (2026-09-22). Note the distinction the sentence has to keep:
                # `property_tax_rate` has anchored VALUES and still no range.
                why = (f"{field} has no default search range — an anchored value is not a "
                       f"range, and this engine states a plausible span for only a few rate "
                       f"leaves, so the bracket to search is yours")
            else:
                why = "only money and rate inputs get a default bracket"
            raise ValueError(
                f"--break-even {key}: give the bracket as {key}=lo:hi ({why})"
            )
    refused: List[Tuple[float, str]] = []

    def totals_at(v: float) -> Optional[Tuple[float, float]]:
        """The two totals at v, or None when the loader refuses that value."""
        try:
            det = compute_deterministic(load_at(raw, key, v))
        except (ConfigValidationError, ValueError) as e:
            refused.append((v, str(e).strip().splitlines()[-1].strip()))
            return None
        return getattr(det, a).total_pv, getattr(det, b).total_pv

    core = solve_crossings(
        key, (a, b), lo, hi, totals_at,
        is_int=key in INT_KEYS, iterations=iterations, refused=refused,
    )
    # A quoted rate in a nominal run: each edge and the crossing carry their
    # real equivalent, glossed once (2026-09-08).
    pi = real_equivalent_inflation(raw, key)
    for entry in core["break_evens"]:
        entry["affordability"] = _affordability_at(raw, key, entry)
        if pi is not None:
            entry["sentence"] = band_sentence(
                key, entry, core["tie_band_fraction"], band_clause=False,
                note=lambda v: f"{deflate(v, pi):.2%} real")
    # Attached here rather than in `no_crossing_record`: `solve_crossings`
    # solves any pair of total curves, and its other callers, the story's act
    # 6 and the reversal register, never read this record's affordability.
    if "no_crossing" in core:
        record = core["no_crossing"]
        record["affordability"] = _affordability_at_ends(raw, key, record)

    out: Dict[str, Any] = {
        "key": key, "options": [a, b], "bracket": [lo, hi], "searched": core["searched"],
        "base_value": base, "tie_band_fraction": core["tie_band_fraction"],
        "real_equivalent_inflation": pi,
        "break_evens": core["break_evens"],
    }
    prior_note = None
    if "market_scenario" in raw:
        prior_note = ("deterministic line: the market_scenario prior does not move this threshold "
                      "(its drift enters the Monte Carlo only) — sweep value_growth_rate for the "
                      "threshold's growth sensitivity; read the sweep's decisive flags for the prior's")
    note = join_notes(
        prior_note,
        prior_band_note(key, *horizon_drift(raw, key, prior), core["break_evens"]),
        cliff_note(raw, key, core["break_evens"]),
        price_scan_note(raw, key),
        flattened_path_note(raw, key),
    )
    if note:
        out["note"] = note
    if refused:
        out["refused"] = {"count": len(refused), "values": [r[0] for r in refused],
                          "reason": refused[0][1]}
    for carried in ("cheaper_throughout", "no_crossing"):
        if carried in core:
            out[carried] = core[carried]
    return out


# ---------------------------------------------------------------------------
# What the threshold's note has to say beside the crossing (2026-09-04 reviews)
#
# Two failures, both found in real answers: a demographic prior sitting on the
# desk while the assistant compared its drift to the tie band by hand, and a
# "crossing" that was the mortgage-insurance cliff — the premium switching on,
# not two costs meeting. Both are the engine's to state.
# ---------------------------------------------------------------------------


def horizon_drift(
    raw: Dict[str, Any], key: str, prior: Optional[LoadedScenarioPrior],
) -> Tuple[Dict[int, float], Optional[float]]:
    """The prior's reference drift per horizon band the run touches, for the
    owned option a `<owned>.value_growth_rate` threshold is solved on, ON THE
    AXIS THE THRESHOLD IS SOLVED ON — and the inflation_rate that put it there.

    The prior encodes a REAL drift; the threshold is solved on the config's own
    `value_growth_rate`, which is AS QUOTED unless the config declares
    `rates: real` (2026-09-05). Comparing the two as printed would put a real
    figure against a quoted band — the double count the convention exists to
    stop — so under the default the drift is composed with inflation_rate and
    the second value says so (None when the axis is real).

    Empty for every other key, without a prior, or when the prior carries no
    reference scenario for this dwelling type — an absent band is reported by
    saying nothing, never by guessing a rate.
    """
    option, _, field = key.rpartition(".")
    if prior is None or field != "value_growth_rate" or option not in ("condo", "house"):
        return {}, None
    years = _raw_value(raw, "years")
    if not isinstance(years, (int, float)) or years < 1:
        return {}, None
    encoded = prior.encoded_drift()
    entry = encoded.get(option) or encoded.get("all")
    if entry is None:
        return {}, None
    reference: Dict[int, float] = entry["reference_by_band"]  # type: ignore[assignment]
    touched = sorted({band_horizon_for_calendar_year(calendar_year_for_sim_year(y))
                      for y in range(1, int(years) + 1)})
    drifts = {band: reference[band] for band in touched if band in reference}
    try:
        rates, _, pi = resolve_convention(raw)
    except RateConventionError:
        return drifts, None
    if rates != "as_quoted":
        return drifts, None
    return {band: compose(drift, pi) for band, drift in drifts.items()}, pi


def _group_by_relation(
    drifts: Dict[int, float], lo: Optional[float], hi: Optional[float],
) -> List[Tuple[str, List[int]]]:
    """Horizon bands grouped, in band order, by where their drift sits against
    the tie band: `below`, `inside`, `above`, or `unbounded` when an edge of the
    band lies outside the searched bracket and there is nothing to compare to."""
    groups: List[Tuple[str, List[int]]] = []
    for band in sorted(drifts):
        drift = drifts[band]
        if lo is None or hi is None:
            relation = "unbounded"
        elif drift < lo:
            relation = "below"
        elif drift > hi:
            relation = "above"
        else:
            relation = "inside"
        if groups and groups[-1][0] == relation:
            groups[-1][1].append(band)
        else:
            groups.append((relation, [band]))
    return groups


def prior_band_note(
    key: str, drifts: Dict[int, float], quoted_with: Optional[float],
    entries: List[Dict[str, Any]],
) -> Optional[str]:
    """Where the prior's own drift sits against the tie band this threshold
    reports — INSIDE (the prior does not settle the question), BELOW or ABOVE
    (it points at one side).

    Three reviewed answers assembled this comparison by hand from two separate
    outputs. It is a comparison of the drift READ AS A GROWTH LEVEL: the Monte
    Carlo adds the drift to `value_growth_rate` rather than replacing it, and
    the note says so rather than letting the reader assume either. `quoted_with`
    is the inflation_rate the drift was composed with to sit on a typed-as-
    quoted axis (`horizon_drift`), None when the axis is real; the clause names
    the convention so the figure is never read in the other one.
    """
    if not drifts or not entries:
        return None
    axis = "/yr as quoted" if quoted_with is not None else "/yr"
    clauses: List[str] = []
    for entry in entries:
        lo, hi = entry["tie_band"]
        span = (None if lo is None or hi is None
                else f"{_fmt_value(key, lo)}–{_fmt_value(key, hi)}")
        # Bands landing on the same side of the tie band are one sentence, not
        # five: a 25-year run touches five horizon bands, and the drift usually
        # sits the same side of the threshold in every one of them.
        for relation, bands in _group_by_relation(drifts, lo, hi):
            values = [drifts[band] for band in bands]
            if len(bands) == 1:
                where = f"the prior's drift {values[0]:+.2%}{axis} ({bands[0]} band)"
            else:
                listed = ", ".join(str(band) for band in bands)
                where = (f"the prior's drift {min(values):+.2%}…{max(values):+.2%}{axis} "
                         f"({listed} bands)")
            if relation == "unbounded":
                edge = "low" if lo is None else "high"
                clauses.append(f"{where}: the tie band's {edge} edge lies outside the searched "
                               f"bracket, so the comparison is not available")
            elif relation == "below":
                clauses.append(f"{where} sits BELOW the tie band {span}: on the prior's own drift "
                               f"{entry['cheaper_below']} is the cheaper side")
            elif relation == "above":
                clauses.append(f"{where} sits ABOVE the tie band {span}: on the prior's own drift "
                               f"{entry['cheaper_above']} is the cheaper side")
            else:
                clauses.append(f"{where} sits INSIDE the tie band {span}: the prior does not "
                               f"settle it")
    if not clauses:
        return None
    convention = ("" if quoted_with is None else
                  f"; the threshold is on the typed axis, so the prior's real drift is stated "
                  f"as quoted — composed with {quoted_with:.1%} inflation_rate")
    return ("the prior against this threshold — " + "; ".join(clauses)
            + " (the drift is added to value_growth_rate in the Monte Carlo, not substituted "
              f"for it; this reads it as a growth level to place it on the same axis{convention})")


def _financing_regime(
    raw: Dict[str, Any], key: str, value: Any,
) -> Tuple[bool, Any]:
    """(accepted, regime) at one value: per owned option, what the engine
    derived for its mortgage insurance — `{"tier": (required, band label, rate),
    "ltv": …}`, or None where the option carries no insurance record at all.
    `accepted` is False when the loader refuses the value; the regime is then
    the refusal reason.

    `tier` is what a comparison across the crossing may read, and it is exactly
    what changes the cash flows. The loan-to-value rides ALONGSIDE it, never
    inside it: it moves continuously with the price, so a tuple carrying it
    would differ at every pair of points and report a step at every crossing.

    Only the DERIVED record counts: without `mortgage_insurance`, crossing the
    20% line changes no cash flow, so it is not a cliff to warn about.
    """
    try:
        spec = load_at(raw, key, value)
    except (ConfigValidationError, ValueError) as e:
        return False, str(e).strip().splitlines()[-1].strip()
    regime = {}
    for name in ("condo", "house"):
        option = getattr(spec, name, None)
        if option is None:
            continue
        record = option.mortgage_insurance
        regime[name] = (None if record is None else
                        {"tier": (record.required, record.band_label, record.rate),
                         "ltv": record.ltv})
    return True, regime


def _regime_state(side: Optional[Dict[str, Any]]) -> str:
    """One side of a crossing, in words: insured (with its premium rate),
    uninsured, or carrying no derived record at all."""
    if side is None:
        return "without a derived insurance record"
    required, _label, rate = side["tier"]
    if not required:
        return "uninsured"
    return f"insured ({rate:.2%} premium on the loan)"


def _step_clauses(
    raw: Dict[str, Any], key: str, what: str, value: Any, below_v: Any, above_v: Any,
) -> List[str]:
    """What a jump at ONE point of the threshold has to say: `what` names the
    point ("the crossing", "the tie band's upper edge") so a note that fires on
    an edge says WHICH edge."""
    clauses: List[str] = []
    ok_below, below = _financing_regime(raw, key, below_v)
    ok_above, above = _financing_regime(raw, key, above_v)
    at = _fmt_value(key, value)
    if not ok_below or not ok_above:
        side, reason = ("below", below) if not ok_below else ("above", above)
        return [f"{what} at {at} sits on the edge of what the config accepts: "
                f"values just {side} it are refused ({reason}), so the band around it "
                f"is bounded by the refusal, not by near-ties"]
    for name in sorted(set(below) & set(above)):
        was, now = below[name], above[name]
        was_tier = None if was is None else was["tier"]
        now_tier = None if now is None else now["tier"]
        if was_tier == now_tier:
            continue  # the same mortgage on both sides: the costs really do meet
        insured_below = bool(was_tier and was_tier[0])
        insured_above = bool(now_tier and now_tier[0])
        # One sentence per jump (2026-09-04): the point, what changed across
        # it, and what that does to the band.
        if insured_below != insured_above:
            step = (f"is the mortgage-insurance cliff — {name} {_regime_state(was)} just "
                    f"below it, {_regime_state(now)} just above —")
        else:
            step = (f"is a mortgage-insurance tier change for {name} "
                    f"({was_tier[2]:.2%} → {now_tier[2]:.2%} of the loan) —")
        clauses.append(
            f"{what} at {at} {step} not a smooth cost crossing: the tie band around it "
            f"is the step's width, not a range of near-ties")
    return clauses


def cliff_note(
    raw: Dict[str, Any], key: str, entries: List[Dict[str, Any]],
) -> Optional[str]:
    """A crossing — or a BAND EDGE — that is a STEP, not a meeting: the two
    sides of it price a different mortgage (the 20%-down line crossed, an
    insurance tier changed) or one side is refused outright.

    2026-09-04 review: a $651,163 "crossing" was exactly cash ÷ 0.215 — the
    house won by $3,076 a hundred dollars below it and lost by $10,902 a hundred
    above, because the premium switched on. Read as a smooth crossing, the tie
    band around it says "these are near-ties"; it is the width of a jump.

    Round 9 found the same defect one step out: the crossing was smooth and the
    band's UPPER EDGE landed exactly on the 20%-down line (the PV jumped
    $426,940 → $440,760 across it), so "band = 5% of the cheaper option's PV"
    was false at that edge and nothing fired. Every point the sentence quotes
    is probed, and the clause names which one jumped.
    """
    clauses: List[str] = []
    for entry in entries:
        is_int = "last_value_below" in entry
        low, high = entry["tie_band"]
        # The three values the sentence quotes. An integer input is a step
        # function, so its probe pair is the two whole values across the point;
        # anything else is probed a hair either side.
        points = [("the crossing", entry["value"],
                   (entry["last_value_below"], entry["value"]) if is_int else None),
                  ("the tie band's lower edge", low,
                   (None if low is None else (int(low) - 1, int(low))) if is_int else None),
                  ("the tie band's upper edge", high,
                   (None if high is None else (int(high), int(high) + 1)) if is_int else None)]
        seen: List[str] = []
        for what, value, pair in points:
            if value is None:
                continue  # an edge outside the searched bracket: nothing to probe
            at = _fmt_value(key, value)
            if at in seen:
                continue  # the crossing IS this edge — one jump, said once
            seen.append(at)
            if pair is None:
                step = max(abs(float(value)), 1.0) * 1e-6
                pair = (float(value) - step, float(value) + step)
            clauses.extend(_step_clauses(raw, key, what, value, *pair))
        # A step strictly INSIDE the band — neither the crossing nor an edge —
        # is a jump the three probes above never see (2026-09-04: a smooth
        # crossing whose band held the 85%-LTV tier change said nothing).
        clauses.extend(_band_interior_steps(raw, key, entry, is_int, seen))
    return "; ".join(clauses) if clauses else None


def _tier_of(accepted: bool, regime: Any, name: str) -> Any:
    """The insurance tier one owned option carries in a probed regime, or the
    refusal marker when the loader refused that point."""
    if not accepted:
        return ("refused",)
    side = regime.get(name)
    return None if side is None else side["tier"]


def _band_interior_steps(
    raw: Dict[str, Any], key: str, entry: Dict[str, Any], is_int: bool, seen: List[str],
) -> List[str]:
    """One clause per mortgage-insurance step that lies strictly inside the
    tie band: the band is sampled, consecutive samples whose tier differs are
    bisected to the step (a loader-level step function of the input), and a
    step already reported at the crossing or an edge is not said again."""
    low, high = entry["tie_band"]
    if low is None or high is None:
        return []
    if is_int:
        xs: List[float] = [float(x) for x in range(int(low), int(high) + 1)]
    else:
        lo, hi = float(low), float(high)
        span = hi - lo
        if span <= 0:
            return []
        eps = max(abs(lo), abs(hi), 1.0) * 1e-6
        xs = [lo + eps] + [lo + span * i / 10 for i in range(1, 10)] + [hi - eps]
    if len(xs) < 2:
        return []
    probes = [_financing_regime(raw, key, x) for x in xs]
    names = sorted({name for ok, regime in probes if ok for name in regime})
    clauses: List[str] = []
    for name in names:
        tiers = [_tier_of(ok, regime, name) for ok, regime in probes]
        for i in range(1, len(xs)):
            was, now = tiers[i - 1], tiers[i]
            if was == now or was in (None, ("refused",)) or now in (None, ("refused",)):
                continue  # no step between two priced tiers
            a, b = xs[i - 1], xs[i]
            if not is_int:
                for _ in range(40):
                    mid = 0.5 * (a + b)
                    ok_m, regime_m = _financing_regime(raw, key, mid)
                    if _tier_of(ok_m, regime_m, name) == was:
                        a = mid
                    else:
                        b = mid
            at = _fmt_value(key, int(b) if is_int else b)
            if at in seen:
                continue
            seen.append(at)
            insured_was, insured_now = bool(was and was[0]), bool(now and now[0])
            if insured_was != insured_now:
                what = (f"the mortgage-insurance cliff for {name} ({'uninsured' if not insured_was else f'insured at {was[2]:.2%}'}"
                        f" → {'uninsured' if not insured_now else f'insured at {now[2]:.2%} of the loan'})")
            else:
                what = (f"a mortgage-insurance tier change for {name} "
                        f"({was[2]:.2%} → {now[2]:.2%} of the loan)")
            clauses.append(f"{what} lies inside the tie band, at {at} — the gap steps there; "
                           f"the band is not one smooth range of near-ties")
    return clauses


def _affordability_points_at(
    raw: Dict[str, Any], key: str, values: Sequence[Any],
) -> Optional[Tuple[Optional[float], List[Optional[Dict[str, Dict[str, Any]]]]]]:
    """Each value priced the way a single run there is, as `(threshold,
    [per-option {max_ratio, years_exceeding} or None per value])`: None for a
    value that is None or that the loader refuses. The whole result is None
    when the FIRST value carries no affordability (no `income` block), so a
    run without one prices that one point and no other. One home for both
    branches of a break-even: the crossing with its band edges, and the two
    searched ends of a bracket with no crossing."""
    threshold: Optional[float] = None
    priced: List[Optional[Dict[str, Dict[str, Any]]]] = []
    for value in values:
        per = None
        if value is not None:
            try:
                det = compute_deterministic(load_at(raw, key, value))
            except (ConfigValidationError, ValueError):
                det = None
            if det is not None:
                if det.income_report is not None:
                    threshold = det.income_report.threshold
                per = affordability_of(det)
        if not priced and per is None:
            return None
        priced.append(per)
    return threshold, priced


def _affordability_at(
    raw: Dict[str, Any], key: str, entry: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """The affordability ratios where the threshold actually puts the user: at
    the crossing and at both tie-band edges, mirroring the entry's own `value`
    and `tie_band` keys.

    2026-09-03 review: an answer called a price range "cheaper on average"
    while the engine's own sweep showed 40.9% of income inside it — above the
    39% cap the answer itself had cited. A threshold that says "buy up to $X"
    has to say what $X costs against income; the band edges are where it bites
    hardest. `None` without an `income` block, like a sweep row's.
    """
    priced = _affordability_points_at(raw, key, [entry["value"], *entry["tie_band"]])
    if priced is None:
        return None
    threshold, (crossing, *edges) = priced
    return {"threshold": threshold, "value": crossing, "tie_band": edges}


def _affordability_at_ends(
    raw: Dict[str, Any], key: str, record: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """The same ratios for a bracket with no crossing, at the two ends it
    searched, mirroring the record's own `lo` and `hi` keys. Both are points
    the solver priced and the loader accepted (`searched` holds accepted runs
    only), the `at_floor` low end of 0 included: an integer key's ends are
    the whole numbers the solver priced its grid points at, and the record
    carries those.

    2026-10-01, board round 12 item 3: the no-crossing line printed no ratio at
    all. On examples/first_time_buyer_montreal.yaml seeded at $380,000, the
    bracket 250,000–420,000 printed none, while a sweep over it found the
    condo at 34.0% of income at its top, three years over the 32% threshold.
    The lanes withhold that sweep in that shape. `None` without an `income`
    block."""
    priced = _affordability_points_at(raw, key, [record["lo"], record["hi"]])
    if priced is None:
        return None
    threshold, (lo, hi) = priced
    return {"threshold": threshold, "lo": lo, "hi": hi}


def solve_break_even_across(
    raw: Dict[str, Any], key: str, lo: Optional[float], hi: Optional[float],
    sweep_key: str, values: List[Any], **kw: Any,
) -> Dict[str, Any]:
    """
    The threshold re-solved at each value of a SECOND input (--break-even
    beside --sweep): "the rent threshold at 0% and at 2% growth" in one call.
    Round 5b evaluation: the skill asked for the threshold at both ends of the
    growth bracket and the trial run could not produce it — --break-even solved
    the base config once and --sweep reported verdicts at the placeholder rent.
    """
    rows: List[Dict[str, Any]] = []
    for v in values:
        r = solve_break_even(with_value(raw, sweep_key, v), key, lo, hi, **kw)
        row: Dict[str, Any] = {"value": v, "break_evens": r["break_evens"]}
        for carried in ("cheaper_throughout", "no_crossing", "refused"):
            if carried in r:
                row[carried] = r[carried]
        rows.append(row)
    # The sweep key's base value, so the row that re-solves the base config
    # can say "(= base)" instead of repeating the base line; and the sweep
    # key's own quoted-rate marker, so its row labels carry the real figure.
    return {"key": sweep_key, "base_value": base_value(raw, sweep_key),
            "real_equivalent_inflation": real_equivalent_inflation(raw, sweep_key),
            "rows": rows}


def band_rule(band: float) -> str:
    """The tie band's definition, in the words every surface uses."""
    return f"band = {band:.0%} of the cheaper option's PV"


def band_sentence(
    key: str, be: Dict[str, Any], band: float,
    *,
    fmt: Optional[Callable[[float], str]] = None,
    label: Optional[Callable[[str], str]] = None,
    band_clause: bool = True,
    note: Optional[Callable[[float], str]] = None,
) -> str:
    """The threshold as the user should read it: band-first, the edges named.
    "rent is cheaper below 2,537; too close to call between 2,537 and 2,797;
    house is cheaper above 2,797 (crossing 2,663; band = 5% of the cheaper PV)".

    ``fmt`` renders one value and ``label`` one option name; both default to the
    CLI's own rendering. The story's act 6 passes "$2,663/mo" and "buying a
    house" — one grammar, so the drawn crossing and the reported one read the
    same, in each surface's own units. ``band_clause`` keeps the band rule in
    the closing bracket (the story's caption stands alone); the CLI's blocks
    state the rule once, in their header, and pass False. ``note`` adds one
    clause after the FIRST mention of each edge and after the crossing — the
    real equivalent of a quoted rate in a nominal run (2026-09-08) — so each
    figure is glossed once and the sentence stays readable.
    """
    show = fmt or (lambda v: _fmt_value(key, v))
    name = label or (lambda option: option)

    def gloss(v: float, edge: bool = True) -> str:
        """`note`'s text for one figure, punctuated for its place: ` (…)`
        after an edge, `, …` inside the crossing's own bracket."""
        if note is None:
            return ""
        return f" ({note(v)})" if edge else f", {note(v)}"

    rule = f"; {band_rule(band)}" if band_clause else ""
    left, right = be["tie_band"]
    if "last_value_below" in be:
        # Integer input (a step function): whole values on each side of the band.
        up_to = f"{key}={left - 1}" if left is not None else "the bracket's low end"
        from_ = f"{key}={right + 1}" if right is not None else "the bracket's high end"
        band_txt = (f"from {key}={left} to {key}={right}" if left is not None and right is not None
                    else f"between {up_to} and {from_}")
        return (
            f"{name(be['cheaper_below'])} is cheaper up to {up_to}; too close to call {band_txt}; "
            f"{name(be['cheaper_above'])} is cheaper from {from_} "
            f"({name(be['cheaper_above'])} first cheaper at {key}={be['value']}{rule})"
        )
    lo_txt = show(left) if left is not None else "the bracket's low end"
    hi_txt = show(right) if right is not None else "the bracket's high end"
    lo_first = lo_txt + (gloss(left) if left is not None else "")
    hi_first = hi_txt + (gloss(right) if right is not None else "")
    return (
        f"{name(be['cheaper_below'])} is cheaper below {lo_first}; too close to call between {lo_txt} and "
        f"{hi_first}; {name(be['cheaper_above'])} is cheaper above {hi_txt} "
        f"(crossing {show(be['value'])}{gloss(be['value'], edge=False)}{rule})"
    )


def threshold_sentences(key: str, result_like: Dict[str, Any], band: float) -> List[str]:
    """The threshold in words, one sentence per crossing (or the no-crossing
    line). One function words the text block, the read-back and every
    `across` row, so the three cannot phrase the same threshold differently."""
    if not result_like["break_evens"]:
        record = result_like.get("no_crossing")
        if record is None:  # a caller that solved without the record
            return [f"no crossing in the bracket: {result_like['cheaper_throughout']} is cheaper throughout"]
        if record.get("at_floor"):
            # The low end is the input's floor: the range ran down to 0 and
            # the only direction left is up (2026-09-08).
            head = (f"no crossing down to 0 on {key}: {record['cheaper']} is cheaper "
                    f"throughout that range")
            if record["widen"] is not None:
                _, w_hi = record["widen"]
                return [f"{head} — widen upward with --break-even {key}=0:{_arg_value(key, w_hi)}"]
            return [f"{head} — the high end is one the config refuses beyond; no wider "
                    f"bracket reaches a crossing"]
        head = (f"no crossing between {_fmt_value(key, record['lo'])} and "
                f"{_fmt_value(key, record['hi'])}: {record['cheaper']} is cheaper at both ends")
        if record["widen"] is not None:
            w_lo, w_hi = record["widen"]
            return [f"{head} — widen with --break-even {key}={_arg_value(key, w_lo)}:{_arg_value(key, w_hi)}"]
        return [f"{head} — the gap narrows toward the {record['narrows_toward']} end, "
                f"which the config refuses beyond; no wider bracket reaches a crossing"]
    return [be.get("sentence") or band_sentence(key, be, band) for be in result_like["break_evens"]]


def _crossing_branch(be: Dict[str, Any]) -> bool:
    """True for a crossing entry (it has a tie band), False for the
    no-crossing record (it has the searched `lo` and `hi`)."""
    return "tie_band" in be


def quoted_records(carrier: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The records whose affordability a solve's line quotes: each crossing
    entry, or, when there is none, the no-crossing record (2026-10-01)."""
    if carrier["break_evens"]:
        return list(carrier["break_evens"])
    record = carrier.get("no_crossing")
    return [record] if record else []


def quoted_points(key: str, be: Dict[str, Any]) -> List[Tuple[str, Any, Dict[str, Any]]]:
    """(label, value, per-option affordability) for every point the sentence
    quotes and the run priced: the crossing and both band edges, or, for the
    no-crossing record, the two ends it searched."""
    aff = be.get("affordability")
    if not aff:
        return []
    if _crossing_branch(be):
        lo, hi = be["tie_band"]
        points = [("at the crossing", be["value"], aff["value"]),
                  ("at the band's low edge", lo, aff["tie_band"][0]),
                  ("at the band's high edge", hi, aff["tie_band"][1])]
    else:
        points = [("at the low end", be["lo"], aff["lo"]),
                  ("at the high end", be["hi"], aff["hi"])]
    return [(label, value, per) for label, value, per in points
            if per is not None and value is not None]


def _aff_phrase(option: str, entry: Dict[str, Any]) -> str:
    return f"{option} {entry['max_ratio']:.1%} ({len(entry['years_exceeding'])} yr(s) over)"


def _affordability_points(
    key: str, be: Dict[str, Any], drop: Any = (),
) -> Tuple[Optional[float], List[str]]:
    """(threshold, phrases): the crossing and both band edges, or the two
    searched ends of a no-crossing record, with their highest cost/income
    ratio and breach count. An option whose figures are
    the same at every quoted point — the renter's, on a price scan — is one
    phrase, `… at every quoted point`, not three; `drop` names the options a
    block header already stated. Empty without an `income` block."""
    points = quoted_points(key, be)
    if not points:
        return None, []
    constant = ({o: e for o, e in constant_options(per for _, _, per in points).items()
                 if o not in drop} if len(points) > 1 else {})
    phrases: List[str] = []
    if constant:
        phrases.append(", ".join(_aff_phrase(o, e) for o, e in constant.items())
                       + " at every quoted point")
    for label, value, per_option in points:
        parts = ", ".join(
            _aff_phrase(option, per_option[option])
            for option in ("condo", "house", "rent")
            if option in per_option and option not in drop and option not in constant
        )
        if parts:
            phrases.append(f"{label} {_fmt_value(key, value)}: {parts}")
    return be["affordability"].get("threshold"), phrases


def _affordability_head(threshold: Optional[float], where: str = "") -> str:
    """The header over the affordability figures. `where` names the points when
    they are listed BELOW it; the one-line form drops it, since each phrase
    names its own point."""
    head = f"affordability{where} (highest cost/income ratio"
    return head + (f"; years above the {threshold:.0%} threshold):"
                   if threshold is not None else "):")


def _affordability_lines(key: str, be: Dict[str, Any]) -> List[str]:
    """What the threshold and its band edges cost against income — the lines a
    "cheaper on average" answer needs beside the crossing it quotes. With no
    crossing, the same lines at the two ends the bracket searched."""
    threshold, phrases = _affordability_points(key, be)
    if not phrases:
        return []
    where = (" at the crossing and the band edges" if _crossing_branch(be)
             else " at both searched ends")
    head = _affordability_head(threshold, where)
    return [head] + [f"  {phrase}" for phrase in phrases]


def _affordability_clause(
    key: str, be: Dict[str, Any], *, drop: Any = (), head: bool = True,
) -> str:
    """The same figures on ONE line, for an `across` row (2026-09-04 review: an
    answer called $858k a "safe-buy ceiling" while the across row it came from
    carried 44.1% of income — above the 39% cap the answer itself cited).
    `head=False` drops the sub-header a block header already carries."""
    threshold, phrases = _affordability_points(key, be, drop)
    if not phrases:
        return ""
    lead = _affordability_head(threshold) if head else "affordability"
    return f"; {lead} " + " · ".join(phrases)


def _refused_clause(carrier: Dict[str, Any]) -> Optional[str]:
    refused = carrier.get("refused")
    if not refused:
        return None
    return f"config refuses {refused['count']} point(s) ({refused['reason']})"


def across_row_sentence(
    key: str, sweep_key: str, row: Dict[str, Any], band: float,
    *, refused_clause: bool = True, drop: Any = (), head: bool = True,
    pi: Optional[float] = None,
) -> str:
    """One `across` row in words: the sweep point, the threshold re-solved
    there, what the config refused, and what the crossing costs against income
    (with no crossing, what the two searched ends cost).

    One function words the text block and the read-back line (2026-09-04 review:
    the block carried the base sentence alone, so an answer reduced a whole
    years bracket to "near $300k"). The read-back passes `refused_clause=False`
    and `head=False` where its header states those once, and `drop` for the
    options the header states at every point.
    """
    sentences = threshold_sentences(key, row, band)
    if refused_clause and _refused_clause(row):
        sentences.append(_refused_clause(row))
    text = f"{sweep_key}={point_label(sweep_key, row['value'], pi)}: " + "; ".join(sentences)
    for be in quoted_records(row):
        text += _affordability_clause(key, be, drop=drop, head=head)
    return text


def read_back_block(result: Dict[str, Any]) -> List[str]:
    """The read-back lines of one break-even, each fact once (2026-09-04):

    - a header naming the bracket, the band rule, the refused clause when
      every solve refused the same points, and the affordability an option
      holds at every quoted point of every solve;
    - the base threshold with its own affordability clause;
    - each `across` row, or `(= base)` where it re-solved the base config;
    - the block's note.
    """
    key, band = result["key"], result["tie_band_fraction"]
    lo, hi = result["bracket"]
    rows = [row for across in result.get("across", []) for row in across["rows"]]
    carriers = [result] + rows
    refused = [_refused_clause(c) for c in carriers]
    refused_once = all(refused) and len(set(refused)) == 1
    quoted = [per for c in carriers for be in quoted_records(c)
              for _, _, per in quoted_points(key, be)]
    constant = constant_options(quoted) if len(quoted) > 1 else {}
    thresholds = [be["affordability"]["threshold"] for c in carriers for be in quoted_records(c)
                  if be.get("affordability") and be["affordability"].get("threshold") is not None]
    head = [f"bracket {_fmt_value(key, lo)}–{_fmt_value(key, hi)}", band_rule(band)]
    if refused_once:
        head.append(refused[0])
    if quoted:
        aff = "affordability = highest cost/income ratio"
        if thresholds:
            aff += f"; years above the {thresholds[0]:.0%} threshold"
        if constant:
            aff += ("; " + ", ".join(_aff_phrase(o, e) for o, e in constant.items())
                    + " at every quoted point")
        head.append(aff)
    lines = [f"break-even {key} (" + "; ".join(head) + ")"]
    drop = constant.keys()
    sentences = threshold_sentences(key, result, band)
    if not refused_once and refused[0]:
        sentences.append(refused[0])
    base_text = "; ".join(sentences) + "".join(
        _affordability_clause(key, be, drop=drop, head=False) for be in quoted_records(result))
    lines.append(f"break-even {key}: {base_text}")
    for across in result.get("across", []):
        skey, base = across["key"], across.get("base_value")
        spi = across.get("real_equivalent_inflation")
        for row in across["rows"]:
            text = across_row_sentence(key, skey, row, band, refused_clause=not refused_once,
                                       drop=drop, head=False, pi=spi)
            prefix = f"{skey}={point_label(skey, row['value'], spi)}: "
            at_base = (isinstance(base, (int, float)) and not isinstance(base, bool)
                       and float(row["value"]) == float(base))
            if at_base and text[len(prefix):] == base_text:
                lines.append(f"break-even {key} at {prefix}(= base)")
            else:
                lines.append(f"break-even {key} at {text}")
    if result.get("note"):
        lines.append(f"break-even {key} note: {result['note']}")
    return lines


def format_break_even(result: Dict[str, Any]) -> str:
    key = result["key"]
    a, b = result["options"]
    lo, hi = result["bracket"]
    band = result["tie_band_fraction"]
    lines = [f"\nBreak-even {key} between {a} and {b} (deterministic line — a market_scenario prior "
             f"does not move it; bracket {_fmt_value(key, lo)}–{_fmt_value(key, hi)}; {band_rule(band)}; "
             f"every other input held at its base value):"]
    if result.get("note"):
        lines.append(f"  {result['note']}")
    if result.get("refused"):
        r = result["refused"]
        span = ", ".join(f"{_fmt_value(key, s0)}–{_fmt_value(key, s1)}" for s0, s1 in result["searched"])
        lines.append(f"  the config refuses {r['count']} point(s) of that bracket ({r['reason']}); searched {span}")
    lines.extend(f"  {t}" for t in threshold_sentences(key, result, band))
    for be in quoted_records(result):
        lines.extend(f"  {t}" for t in _affordability_lines(key, be))
    # `across` rows keep their one-line shape — the affordability the row
    # implies rides that same line.
    for across in result.get("across", []):
        skey = across["key"]
        lines.append(f"  across {skey} (the threshold re-solved at each value):")
        for row in across["rows"]:
            lines.append(f"    {across_row_sentence(key, skey, row, band, pi=across.get('real_equivalent_inflation'))}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The reversal register (board item 4,
# docs/specs/2026-09-22-which-risk-decides-it.md §6)
#
# The half of "which risk decides it" that no decomposition of drawn channels
# can answer.
#
# EXACT AND ESTIMATED, in `decomposition`'s sense, split on whether the
# EXACTNESS GATE licensed the key's shift, not on which verdict field moved:
# a licensed key's boundaries are all exact, confirmed by re-simulation
# whenever the run has futures to re-simulate, and live in `ExactReversal`;
# slice 1 REFUSES an unlicensed key rather than estimating it (§6), so
# `EstimatedReversal` stays empty on a correct engine.
# All four of `BOUNDARY_FIELDS` are answered on every exact or estimated row,
# and a kind this solver cannot reach comes back as a `RefusedBoundary` naming
# why (§0.1 ruling 4) — an absent row and a refused row are different claims.
#
# TWO KINDS OF BOUNDARY, AND THE CONTRACT CARRIES WHICH, because they are not
# one thing: a `best` or `runner_up` boundary is solved on the central case and
# does not move with the seed, while an `mc_best` boundary is bisected on the
# futures and does (both pinned in `tests/test_reversal_register.py`). So a
# solved value comes back
# as a `SolvedBoundary` carrying no sample and a bisected one as a
# `SampledBoundary` carrying the curve's path count and seed — two types with
# no shared base class, which the formatter tells apart by type, so a
# sampled figure cannot be printed under the solved line's prefix. The prefix
# ("solved on the central case", or the sample's paths and seed) is what tells
# the two apart on the page; the precision a figure prints at does not, since
# either kind widens it until the field says `was` there (§0.1 item 54).
#
# Why the register exists at all: `mortgage_renewal_rates` is a path the config
# states, not a distribution, so its variance is zero BY CONSTRUCTION and any
# variance table prints it as a dash. A reader sees six rows carrying numbers
# and one carrying dashes and concludes renewal was weighed and found
# irrelevant, when the verdict's own winner can change inside the bracket the
# engine already uses for a contract rate (the fixture's does, pinned in
# `tests/test_reversal_register.py::TestTheThreeFiguresOnTheFixture`).
# ---------------------------------------------------------------------------

# The financing-leg keys, per owned option. Candidates are inputs the config
# STATES that carry no distribution; a sizing key of a drawn channel (`*_vol`,
# a hazard, a correlation) is never one, by construction rather than by
# omission — `compute_deterministic` reads no dispersion input, so a
# deterministic curve over a vol key is a flat line, and a flat line under this
# heading would print "this risk does not affect the verdict" about every risk
# (spec §6).
REVERSAL_LEAVES: Tuple[str, ...] = ("mortgage_renewal_rates", "mortgage_rate")

# The exactness gate's tolerance, as a multiple of the option's own PV standard
# deviation. NOT a tuned threshold, and the measurement is what says so: on the
# fixture the worst per-path deviation is 9.5e-16 of sd for both financing keys
# against 2.7 and 2.9 for `house.value_growth_rate` and `rent.monthly_rent` —
# fifteen orders of magnitude, so every figure in that gap licenses and refuses
# exactly the same keys.
REVERSAL_GATE_TOLERANCE = 1e-9

# `BOUNDARY_FIELDS` split by HOW each one is located, which is also WHICH TYPE
# it comes back as. The deterministic pair comes off `solve_crossings`, reads no
# path, and is the same figure at any `num_sims` or seed — a `SolvedBoundary`.
# The futures pair is a step function of the axis found on the free curve, so it
# moves with the sample — a `SampledBoundary`, carrying the curve's path count
# and seed. `decisive` is in the futures pair because `compute_verdict` reads
# `P(best cheapest) ≥ verdict.prob_floor` whenever this run has futures, so its
# own flip is a fact about them.
#
# Both types still land in the one `ExactReversal.boundaries` tuple, because
# `decomposition`'s exact/estimated axis splits ROWS BY KEY on the gate's
# licence, and this split is two kinds WITHIN one key — see the section header.
# These two lists must PARTITION `BOUNDARY_FIELDS`: `_typed_boundary` routes off
# them and raises on a field in neither, so a fifth kind cannot be typed by
# whichever branch happened to be the default.
_DETERMINISTIC_FIELDS: Tuple[str, ...] = ("best", "runner_up")
_FUTURES_FIELDS: Tuple[str, ...] = ("mc_best", "decisive")

# How finely a futures field's bracket is scanned before an edge is bisected.
# `mc_best` and `decisive` are STEP functions of the axis with no sign to
# bracket, so their edges are found by scan-then-bisect, and a flip lying
# entirely inside one scan cell is not seen. (The deterministic pair is
# scanned too, each pair of options at `CROSSING_SCAN_POINTS`, before its
# sign changes are bisected.) The count is stated where a field refuses
# (`_scan_reason`) and in the contract; a printed crossing does not carry it.
# At 65 points a cell is 1/64 of the bracket.
REVERSAL_SCAN_POINTS = 65

# The finest precision, in decimals of a percent, a printed crossing may widen
# to (§0.1 item 54).
PRINTED_RATE_MAX_PLACES = 12


def reversal_bracket(key: str) -> Optional[Tuple[float, float]]:
    """The bracket a reversal row searches — the key's own `RATE_BRACKETS`
    entry, or None for a key with no default range. A key with no range is not
    a candidate: a bracket the register invented would be a width nobody
    stated, and §6's whole claim for this register is that it carries no such
    width anywhere."""
    return RATE_BRACKETS.get(key.rsplit(".", 1)[-1])


def reversal_candidates(raw: Dict[str, Any]) -> List[Tuple[str, str]]:
    """`[(key, option)]` — the financing-leg keys this config states, in the
    engine's own option order.

    A key the config does not state is not a candidate and never reaches the
    admission measurement. That is what excludes an ALL-CASH option.
    """
    out: List[Tuple[str, str]] = []
    for option in ("condo", "house"):
        if not isinstance(raw.get(option), dict):
            continue
        for leaf in REVERSAL_LEAVES:
            key = f"{option}.{leaf}"
            if base_value(raw, key) is not None and reversal_bracket(key) is not None:
                out.append((key, option))
    return out


def reversal_probe(raw: Dict[str, Any], key: str) -> float:
    """The far end of `key`'s bracket, where the admission test and the
    exactness gate move it: `bracket_high`, or `bracket_low` where every
    figure the config states for the key is `bracket_high`."""
    lo, hi = reversal_bracket(key)
    return lo if all(float(v) == hi for v in _stated_values(raw, key)) else hi


def reversal_admission(
    raw: Dict[str, Any], key: str, far: float,
    *, base: Optional[ComparisonDeterministicResult] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """`(admitted, record)` — the admission test, which is a MEASUREMENT and
    not a list (spec §6): one `load_at` + `compute_deterministic` at `far`,
    the far end of the key's bracket (`reversal_probe`), and the key is
    admitted only if some option's deterministic PV moves.

    A key that moves nothing is not printed as a flat curve; it is a
    `not_admitted` row. The screen still has work to do on a key the config states — a
    renewal term at or past the amortization makes the ladder inert, which the
    loader warns about and prices as stated — so it is kept even though
    `reversal_candidates` has already dropped the unstated keys.
    """
    base = base if base is not None else compute_deterministic(load_config_dict(raw))
    options = _priced_options(raw)
    try:
        probe = compute_deterministic(load_at(raw, key, far))
    except (ConfigValidationError, ValueError, RateConventionError) as e:
        return False, {"probe": far, "moves": [], "deltas": {},
                       "why": (f"the loader refuses {_fmt_value(key, far)} — "
                               f"{str(e).strip().splitlines()[-1].strip()}")}
    deltas = {
        option: getattr(probe, option).total_pv - getattr(base, option).total_pv
        for option in options
        if getattr(probe, option, None) is not None and getattr(base, option, None) is not None
    }
    moves = [option for option, delta in deltas.items() if delta != 0.0]
    if not moves:
        return False, {
            "probe": far, "moves": [], "deltas": deltas,
            "why": (f"no option's present value moves at {_fmt_value(key, far)}, the far end "
                    f"of its bracket — the config states it and this run prices nothing by it"),
        }
    return True, {"probe": far, "moves": moves,
                  "deltas": {option: deltas[option] for option in moves}, "why": None}


def _shift_deviation_over_sd(before: Any, after: Any) -> float:
    """Clause (b)'s measure: `max |Δ_i − mean Δ| / sd(before)` for one option's
    per-path PVs at the stated value and at the probe.

    IDENTICAL PATHS MEASURE AS IDENTICAL. On a single-path config every path
    carries the same float, yet `np.std` and `x − mean(x)` both round the mean
    and return one ULP of the PV (2.9e-11 on a present value near 200,501).
    Left to that arithmetic, a constant shift reads a ratio of exactly 1.0 and
    refuses when not one path differs, and a shift that DOES vary is divided by
    rounding noise and printed as a finite multiple of an s.d. that is really
    zero. So a zero range is an exact zero, on each half separately: a constant
    shift of identical paths is 0.0, a varying one is `inf`, and any real
    spread takes the arithmetic unchanged.

    Both halves test `== 0`, never `> 0`: `np.ptp` of an array holding a NaN is
    NaN, and `NaN > 0` is False, so the `> 0` form read a NaN as "no spread"
    and returned 0.0 — a licence. In the `== 0` form a NaN takes the arithmetic
    and comes back NaN or `inf`, neither of which any tolerance admits.
    `reversal_gate` refuses a non-finite PV by name before it gets here; this
    form is what keeps the measure itself from failing open.
    """
    delta = after - before
    sd = 0.0 if np.ptp(before) == 0 else float(np.std(before))
    worst = 0.0 if np.ptp(delta) == 0 else float(np.max(np.abs(delta - float(np.mean(delta)))))
    return worst / sd if sd > 0 else (0.0 if worst == 0.0 else math.inf)


def _over_sd_words(deviation: float, option: str) -> str:
    """Clause (b)'s figure as a reader is shown it. A finite figure prints as a
    multiple of the option's s.d. against the tolerance; `inf` is a shift that
    varies over paths with no spread of their own, and NaN is not a number —
    neither is a multiple of anything, and "worst inf of its own sd" printed
    one as though it were. Each case prints what was measured."""
    if math.isfinite(deviation):
        return (f"worst {deviation:.2e} of its own s.d., against "
                f"{REVERSAL_GATE_TOLERANCE:.0e}")
    if math.isinf(deviation):
        return (f"{option} is priced the same on every path as stated, and its shift "
                f"differs across paths")
    return "its deviation over its own s.d. is not a number"


def reversal_gate(
    raw: Dict[str, Any], key: str, probe: float,
    *, paths: int = 200,
    simulate: Callable[[ComparisonSpec], ComparisonMonteCarloResult] = run_monte_carlo,
) -> Dict[str, Any]:
    """The exactness test that licenses the free curve (spec §6), run on
    `m = min(paths, num_sims)` paths. Two clauses, BOTH required:

    (a) every option the key does not name is **bit-identical** — which is what
        catches a key that moves the draw stream rather than the cash flows.
        Measured: `rent.reset_hazard` names `rent` and moves the condo's and
        the house's arrays too, because `_sample_reset_year` returns early
        inside its own year loop, so the draw COUNT depends on the outcome.
    (b) the option the key does name moves by **one constant on every path**:
        `max |Δ_i − mean Δ| ≤ REVERSAL_GATE_TOLERANCE · sd(PV)`.

    An exactness test, not a tolerance — see `REVERSAL_GATE_TOLERANCE`. The
    mechanism behind the licence is readable rather than lucky: `_financing_pv`
    is one terminal call and `equity_N = value_N·(1−s) − balance_N` has no
    clamp, so `balance_N` separates additively from the path-dependent value.

    A NON-FINITE PRESENT VALUE REFUSES FIRST, on either run and on every
    option, with its own reason. Every comparison below fails OPEN on NaN:
    `np.ptp(x) > 0` and `NaN > tolerance` are both False, so one NaN in the
    stated run's array read as a zero deviation, and one NaN in the probe's
    array as a deviation no tolerance exceeds — either way the gate licensed a
    curve it never measured. And `array_equal` is False on NaN, so a NaN in an
    option the key does not name refused under the draw-stream sentence, which
    is not what happened. The refused record carries `worst_deviation_over_sd`
    as NaN — not a number is what was measured — and `others_bit_identical`
    as None, since neither clause was reached.
    """
    option = key.split(".", 1)[0]
    spec = load_config_dict(raw)
    m = max(1, min(int(paths), int(spec.simulation.num_sims)))
    base = simulate(load_at(raw, "simulation.num_sims", m))
    at = simulate(load_at(with_value(raw, "simulation.num_sims", m), key, probe))
    record: Dict[str, Any] = {
        "paths": m, "probe": probe, "names": option,
        "tolerance": REVERSAL_GATE_TOLERANCE,
        "others_bit_identical": True, "moved_others": [],
        "worst_deviation_over_sd": None, "licensed": False, "why": None,
    }
    pairs = [(name, getattr(base, name, None), getattr(at, name, None))
             for name in _priced_options(raw)]
    pairs = [(name, before, after) for name, before, after in pairs
             if before is not None and after is not None]
    unreadable = [
        f"{name} {where} ({bad:,} of {pvs.size:,} paths)"
        for name, before, after in pairs
        for where, pvs in ((f"with {key} as stated", before.pvs),
                           (f"with {key} at {_fmt_value(key, probe)}", after.pvs))
        for bad in [int(np.count_nonzero(~np.isfinite(pvs)))] if bad
    ]
    if unreadable:
        record.update(
            others_bit_identical=None, worst_deviation_over_sd=math.nan,
            why=(f"a present value this gate compares is not a finite number: "
                 f"{'; '.join(unreadable)}"))
        return record
    for name, before, after in pairs:
        if name == option:
            record["worst_deviation_over_sd"] = _shift_deviation_over_sd(
                before.pvs, after.pvs)
        elif not np.array_equal(before.pvs, after.pvs):
            record["others_bit_identical"] = False
            record["moved_others"].append(name)
    deviation = record["worst_deviation_over_sd"]
    if not record["others_bit_identical"]:
        record["why"] = (
            f"moving {key} moves {', '.join(record['moved_others'])}, which it does not "
            f"name")
    elif deviation is None:
        # The key's option is in the config (the loader prices every section it
        # is given), so a run that returns no figures for it is a producer
        # defect, not a sentence to print.
        raise ValueError(
            f"{option} is priced by this config and the run returned no present values "
            f"for it, so the gate on {key} has nothing to measure")
    elif not deviation <= REVERSAL_GATE_TOLERANCE:
        record["why"] = (
            f"moving {key} shifts {option} by a different amount on different paths "
            f"({_over_sd_words(deviation, option)})")
    else:
        record["licensed"] = True
    return record


def _cheapest_probabilities(
    arrays: Dict[str, Any], options: Sequence[str],
) -> Dict[str, Optional[float]]:
    """`P(option cheapest)` from per-option PV arrays, by the SAME rule
    `run_monte_carlo` uses — `argmin` over the options stacked in the engine's
    own order — so a free curve's probability and a re-simulation's are the
    same statistic and can be compared for exact equality."""
    present = [o for o in options if o in arrays]
    out: Dict[str, Optional[float]] = {o: None for o in ("condo", "house", "rent")}
    if len(present) < 2:
        return out
    winners = np.argmin(np.stack([arrays[o] for o in present], axis=0), axis=0)
    for index, name in enumerate(present):
        out[name] = float(np.mean(winners == index))
    return out


def _free_curve(
    raw: Dict[str, Any], key: str, options: Sequence[str],
    det_base: ComparisonDeterministicResult, mc_base: ComparisonMonteCarloResult,
    *, single_path: bool,
) -> Callable[[float], Tuple[Verdict, Dict[str, Optional[float]]]]:
    """`v -> (verdict, probabilities)` at no simulation cost, for a key the
    exactness gate licensed.

    Each option's PV array is shifted by its own DETERMINISTIC delta, each
    summary is rebuilt from the shifted array, and the whole thing goes to
    `models.compute_verdict` — the engine's own rule. Nothing here computes a
    verdict, a state or a probability by arithmetic of its own.

    `affordability_mc` is dropped rather than carried forward: the financing
    leg moves an owner's annual cost, so the base run's breach probabilities
    are NOT the ones that hold at this value and nothing may read them as if
    they were. `compute_verdict` does not read them.
    """
    base_pv = {o: getattr(det_base, o).total_pv for o in options}
    base_arr = {o: getattr(mc_base, o).pvs for o in options}
    cache: Dict[float, Tuple[Verdict, Dict[str, Optional[float]]]] = {}

    def at(value: float) -> Tuple[Verdict, Dict[str, Optional[float]]]:
        v = float(value)
        if v not in cache:
            spec = load_at(raw, key, v)
            det = compute_deterministic(spec)
            arrays = {o: base_arr[o] + (getattr(det, o).total_pv - base_pv[o]) for o in options}
            probs = _cheapest_probabilities(arrays, options)
            mc = ComparisonMonteCarloResult(
                **{o: (MonteCarloOptionResult(pvs=arrays[o],
                                              summary=_summarize_array(arrays[o]))
                       if o in arrays else None)
                   for o in ("condo", "house", "rent")},
                prob_condo_cheapest=probs["condo"], prob_house_cheapest=probs["house"],
                prob_rent_cheapest=probs["rent"],
                affordability_mc=None, market_scenario=mc_base.market_scenario)
            cache[v] = (compute_verdict(det, mc, years=spec.simulation.years,
                                        discount_rate=spec.simulation.discount_rate,
                                        single_path=single_path), probs)
        return cache[v]

    return at


def decisive_state(verdict: Verdict) -> str:
    """The `decisive` verdict field in the words a boundary carries: one of
    "decisive for <option>" or "not decisive".

    FOR WHOM is read off the verdict, not guessed: `compute_verdict` sets
    `decisive` only in its `option` state, and that state is decisive for
    `best`, the central case's winner — under `mc_floor` because P(best
    cheapest) clears the floor with no other option the majority, under
    `margin_band` because the central margin clears the tie band. Every other
    state is not decisive, and the words say no more than that: `tie` and
    `disagreement` are both "not decisive", because naming the difference here
    would report a change between them as a change of decisiveness when
    decisiveness did not change. Whether the majority left `best` is
    `mc_best`'s own boundary.

    A boolean is what this replaces, and it was false on a two-option axis:
    decisive for the house on one side of the tie band and decisive for rent
    on the other are both True, so the crossing out of the tie band INTO
    rent's decisiveness printed as "True to False".
    """
    return f"decisive for {verdict.best}" if verdict.decisive else "not decisive"


def field_state(verdict: Verdict, field: str) -> Any:
    """What `field` of `verdict` says, as a boundary reads it: the option name
    for `best`, `runner_up` and `mc_best`, and `decisive_state` for
    `decisive`. One accessor for the scan, the bisection and the run's own
    reading, so the three cannot compare different things."""
    return decisive_state(verdict) if field == "decisive" else getattr(verdict, field)


def _matching_runs(values: Sequence[Any], target: Any) -> List[List[int]]:
    """The maximal contiguous index runs of `values` equal to `target`."""
    runs: List[List[int]] = []
    current: List[int] = []
    for index, value in enumerate(values):
        if value == target:
            current.append(index)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def _scan_grid(lo: float, hi: float, points: int) -> List[float]:
    """The `points` evenly spaced values of `[lo, hi]` a scan reads, ends
    included — the one formula for both scans."""
    return [lo + (hi - lo) * i / (points - 1) for i in range(points)]


def _scan_reason(key: str, field: str, says: Any, points: int, lo: float, hi: float,
                 *, in_this_run_only: bool) -> Tuple[str, str]:
    """`(code, reason)` for a field on which no boundary is printed, stated as
    the scan it rests on (§0.1 items 47 and 50): what the field read at each of
    the `points` scanned, never a claim about the values between them."""
    across = f"{points} points across {_fmt_value(key, lo)}–{_fmt_value(key, hi)}"
    if in_this_run_only:
        return "not_on_axis", f"{field} says {says!r} in this run and at none of {across}"
    return "unchanged", f"{field} says {says!r} at every one of {across}"


def _mismatch_reason(key: str, field: str, record: Dict[str, Any]) -> Tuple[str, str]:
    """`(code, reason)` for a solved field on which the stretches between the
    solved crossings and the points the pairs were scanned at disagree (§0.1
    item 61): what each of the two read."""
    lo, hi = record["bracket"]
    stretches = "no stretch" if record["anomaly"] else "every stretch"
    return "scan_mismatch", (
        f"{field} says {record['value']!r} in this run and on {stretches} between the "
        f"solved crossings, read at its middle, and at the {record['points']} points "
        f"across {_fmt_value(key, lo)}–{_fmt_value(key, hi)} it reads "
        + ", ".join(repr(reading) for reading in record["readings"]))


def _changes(states: Sequence[Any]) -> bool:
    """Whether a run of states, read in order, holds more than one state."""
    return any(a != b for a, b in zip(states, states[1:]))


def _region_boundaries(
    key: str, field: str, says_now: Any, region_values: Sequence[Any],
    region_span: Sequence[Tuple[float, float]],
    edge_at: Callable[[int, int], Tuple[Tuple[float, float], Any]],
    bracket: Tuple[float, float],
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """The boundaries of the region(s) in which `field` still says what this
    run says — plus the one anomaly this can produce.

    There is no base POINT on the axis to measure a distance from when the
    config states the input as a path. What is well defined, and what the
    output prints, is the edge of the region whose answer matches the run's.

    EVERY EDGE READS THE KEY UPWARD, whichever side the run's own region lies
    on, so `--sweep` at a point either side prints `was` below and `becomes`
    above: an edge below which the house wins and above which rent does is
    `was="house"`, `becomes="rent"` even when the run itself says rent.
    `direction` says which side of the run's region the edge bounds.
    `([], record)` comes back when the run's own answer is in no region —
    reported, never dropped.

    THE STATE PAST AN EDGE IS READ AT THE EDGE (§0.1 item 47). `edge_at(index,
    step)` returns `((lower, upper), state)`: the two ends of the bracket the
    edge converged in, and what the field says at its far end. That state is
    the edge's `becomes` (an upper edge) or `was` (a lower one), and `further`
    is read from it onward. The boundary's `value` is the lower end and its
    `upper_end` the upper one (§0.1 item 60). Read at the next region
    instead, a state lying wholly between the edge and the next scan point
    was skipped: decisive for house
    printed as changing straight to decisive for rent across a stretch where
    `--sweep` says not decisive.

    ONLY THE NEAREST EDGE IS AN EDGE HERE (§6), so `further` says what lies
    past it: the side ("above" or "below") on which the searched range changes
    AGAIN before this run's answer returns, or None. A change back INTO the
    run's answer is the next region's own edge and is reported; a change
    between two other states is reported nowhere, and a reader handed only
    the nearest edge takes its `becomes` to hold to the end of the bracket.
    """
    runs = _matching_runs(region_values, says_now)
    if not runs:
        return [], {"attribute": field, "says_now": says_now, "bracket": list(bracket)}
    if len(runs) == 1 and len(runs[0]) == len(region_values):
        return [], None                       # unchanged across the whole bracket

    out: List[Dict[str, Any]] = []
    for index, run in enumerate(runs):
        first, last = run[0], run[-1]
        low = edge_at(first, -1) if first > 0 else None
        high = edge_at(last, +1) if last < len(region_values) - 1 else None
        holds = [low[0][1] if low is not None else region_span[first][0],
                 high[0][0] if high is not None else region_span[last][1]]
        if low is not None:
            (lower, upper), was = low
            floor = runs[index - 1][-1] + 1 if index > 0 else 0
            # read downward from the edge to the next region of the run's own
            # answer, or to the bracket's end
            past = [was] + list(reversed(region_values[floor:first]))
            out.append({"attribute": field, "was": was, "becomes": says_now,
                        "value": lower, "upper_end": upper, "direction": "below",
                        "holds": holds, "further": "below" if _changes(past) else None})
        if high is not None:
            (lower, upper), becomes = high
            ceiling = runs[index + 1][0] if index + 1 < len(runs) else len(region_values)
            past = [becomes] + list(region_values[last + 1:ceiling])
            out.append({"attribute": field, "was": says_now, "becomes": becomes,
                        "value": lower, "upper_end": upper, "direction": "above",
                        "holds": holds, "further": "above" if _changes(past) else None})
    return out, None


def _ranking_at(raw: Dict[str, Any], key: str, value: float) -> Dict[str, Any]:
    """`{best, runner_up}` at one value of the axis, read off `compute_verdict`
    rather than a sort written here — the ranking rule has one home."""
    spec = load_at(raw, key, value)
    verdict = compute_verdict(compute_deterministic(spec), None,
                              years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate, single_path=True)
    return {"best": verdict.best, "runner_up": verdict.runner_up}


def deterministic_boundaries(
    raw: Dict[str, Any], key: str, lo: float, hi: float,
    *, base: Optional[ComparisonDeterministicResult] = None, iterations: int = 60,
) -> Dict[str, Any]:
    """Every value in `[lo, hi]` at which the DETERMINISTIC verdict stops
    saying what this config's own run says — the half of the reversal register
    that carries no sample in it anywhere. The deterministic renewal-flip line
    of `2026-09-21-unpriced-dimensions.md` slice 2 is planned to call it too;
    that slice is not built, so today the reversal register is its only caller.

    ONE SOLVER (spec §0): every value reported here is
    `solve_crossings`' own figure on the relevant pair, bisected on to
    adjacent floats (§0.1 item 60). `--break-even` itself refuses a
    three-option config; its solver takes a pair and a `totals_at` callable
    and is the one home for this truth.

    A field no crossing moves is filed as unchanged or as an anomaly, and
    under `mismatched` instead where the nine points the pairs were scanned
    at disagree with that (§0.1 item 61).
    """
    spec = load_config_dict(raw)
    options = _priced_options(raw)
    refused: List[Dict[str, Any]] = []
    crossings: List[Dict[str, Any]] = []
    for index, a in enumerate(options):
        for b in options[index + 1:]:
            def totals_at(v: float, a: str = a, b: str = b) -> Optional[Tuple[float, float]]:
                try:
                    det = compute_deterministic(load_at(raw, key, v))
                except (ConfigValidationError, ValueError, RateConventionError):
                    return None
                return getattr(det, a).total_pv, getattr(det, b).total_pv
            declined: List[Tuple[float, str]] = []
            try:
                solved = solve_crossings(key, (a, b), lo, hi, totals_at,
                                         is_int=key in INT_KEYS, iterations=iterations,
                                         refused=declined, to_adjacent_floats=True)
            except ValueError as e:
                refused.append({"pair": [a, b], "why": str(e).strip().splitlines()[-1].strip()})
                continue
            for entry in solved["break_evens"]:
                crossings.append({"pair": [a, b], **entry})
    crossings.sort(key=lambda c: c["value"])
    edges = [tuple(c["bracket"]) for c in crossings]
    span = [(x0, x1) for x0, x1 in zip([lo] + [e[1] for e in edges],
                                       [e[0] for e in edges] + [hi])]
    ranks = [_ranking_at(raw, key, 0.5 * (x0 + x1)) for x0, x1 in span]
    # What the RUN says, from its own deterministic result rather than from any
    # point of the axis — the stated input may be a path, which is not on it.
    base = base if base is not None else compute_deterministic(spec)
    stated = compute_verdict(base, None, years=spec.simulation.years,
                             discount_rate=spec.simulation.discount_rate, single_path=True)

    out: Dict[str, Any] = {
        "key": key, "bracket": [lo, hi], "options": options, "crossings": crossings,
        "regions": [{"from": x0, "to": x1, **rank} for (x0, x1), rank in zip(span, ranks)],
        "boundaries": [], "unchanged": [], "anomalies": [], "mismatched": [],
        "refused": refused,
    }
    grid: List[Dict[str, Any]] = []
    for field in _DETERMINISTIC_FIELDS:
        values = [rank[field] for rank in ranks]

        def edge_at(i: int, step: int,
                    values: List[Any] = values) -> Tuple[Tuple[float, float], Any]:
            # The spans are cut at every solved crossing, so the span beyond
            # an edge is what the field says from that edge's converged
            # bracket to the next crossing.
            return (edges[i - 1], values[i - 1]) if step < 0 else (edges[i], values[i + 1])

        found, anomaly = _region_boundaries(
            key, field, getattr(stated, field), values, span, edge_at, (lo, hi))
        if anomaly is not None or not found:
            # No edge: what the field reads at each point the pairs were
            # scanned at, measured here, so the refusal states its scan.
            if not grid:
                grid = [_ranking_at(raw, key, x)
                        for x in _scan_grid(lo, hi, CROSSING_SCAN_POINTS)]
            readings = [point[field] for point in grid]
            says = getattr(stated, field)
            record = {"attribute": field, "value": says, "bracket": [lo, hi],
                      "points": CROSSING_SCAN_POINTS, "anomaly": anomaly is not None}
            if (says in readings) if anomaly is not None else (set(readings) != {says}):
                out["mismatched"].append({**record, "readings": readings})
            else:
                out["anomalies" if anomaly is not None else "unchanged"].append(record)
        else:
            for entry in found:
                crossing = next((c for c in crossings
                                 if tuple(c["bracket"]) == (entry["value"], entry["upper_end"])),
                                None)
                # No `exactness` field: the LIST is the home of that
                # classification (see `reversal_register`), and a boundary
                # carrying its own label could be quoted out of the list that
                # gives it meaning.
                out["boundaries"].append({
                    **entry, "method": "break_even.solve_crossings",
                    "pair": crossing["pair"] if crossing else None, "crossing": crossing})
    out["boundaries"].sort(key=lambda b: b["value"])
    return out


def _step_edge(
    attribute: Callable[[float], Any], says_now: Any, x_matching: float, x_other: float,
    *, iterations: int = 90,
) -> Tuple[float, float]:
    """`(inside, outside)`: the bracket a step of `attribute` away from
    `says_now` converges in, bisected between a value that matches and one
    that does not. `inside` is the extreme value at which `attribute` still
    equals `says_now`; `outside` is the nearest value bisected at which it
    does not, where the state past the edge is read (§0.1 item 47).

    Not `solve_crossings`' bisection and deliberately not folded into it: that
    one brackets a SIGN CHANGE of a continuous gap and reports the value where
    the gap is zero. `mc_best` and `decisive` are step functions of a discrete
    attribute — there is no gap and no sign — so what is bracketed is a change
    of VALUE.
    """
    lo, hi = x_other, x_matching
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if attribute(mid) == says_now:
            hi = mid
        else:
            lo = mid
        if abs(hi - lo) < 1e-12 * max(1.0, abs(hi)):
            break
    return hi, lo


def _identification(
    boundary: Dict[str, Any], probs: Dict[str, Dict[str, Optional[float]]], paths: int,
) -> Dict[str, Any]:
    """Whether a futures boundary is identified outside Monte Carlo noise
    (spec §6, refusal i; §0.1 items 63, 67 and 68): the bracket-wide `|ΔP|` of
    P(cheapest) for each option in the boundary's `computed_from`, each
    against `2·SE` of that probability at the boundary itself, where
    `SE = sqrt(p(1−p)/N)`. The first that does not clear its own is the one
    the reason names. A decisiveness boundary whose two states differ, and
    at which every one of those probabilities has an `SE` of 0, has no noise
    to lie inside, and is identified. So is one whose two states differ and
    whose two sides are computed from different options: the central case's
    winner changes inside its bracket, a step solved on the central case and
    not drawn from the futures.
    """
    watched = list(dict.fromkeys(boundary["computed_from"]))
    rows = []
    for option in watched:
        p_lo, p_hi = probs["lo"].get(option), probs["hi"].get(option)
        p_at = probs["at"].get(option)
        if p_lo is None or p_hi is None or p_at is None:
            continue
        rows.append({"option": option, "delta_p": abs(p_hi - p_lo),
                     "two_se": 2.0 * math.sqrt(max(p_at * (1.0 - p_at), 0.0) / paths)})
    if not rows:
        return {"identified": False, "paths": paths, "watched": [],
                "why": "no probability is attached to this boundary"}
    exact = ((len(watched) > 1 or all(row["two_se"] == 0.0 for row in rows))
             and boundary["attribute"] == "decisive" and boundary["was"] != boundary["becomes"])
    short = None if exact else next(
        (row for row in rows if not row["delta_p"] > row["two_se"]), None)
    record = {"identified": short is None, "paths": paths, "watched": rows, "why": None}
    if short is not None:
        record["why"] = (
            f"across the bracket P({short['option']} cheapest) moves by "
            f"{short['delta_p']:.4f}, not more than 2 s.e. of it at the boundary "
            f"({short['two_se']:.4f}) on {paths} paths")
    return record


def _futures_field_boundaries(
    raw: Dict[str, Any], key: str, field: str, free: Callable[[float], Any],
    stated: Verdict, lo: float, hi: float, *, scan_points: int,
) -> Tuple[List[Dict[str, Any]], Optional[Tuple[str, str]]]:
    """`([boundary, ...], None)` or `([], (code, reason))` for one FUTURES
    field.

    `mc_best` and `decisive` are step functions of the axis with no sign to
    bracket, so the bracket is scanned and each edge of the run that matches
    what this run says is bisected. A flip lying entirely inside one scan cell
    is not seen; where no boundary is found, the refusal's reason states the
    scan it rests on.
    """
    xs = _scan_grid(lo, hi, scan_points)
    says_now = field_state(stated, field)

    def attribute(v: float) -> Any:
        return field_state(free(v)[0], field)

    values = [attribute(x) for x in xs]
    groups: List[Tuple[int, int, Any]] = []
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[start]:
            groups.append((start, i - 1, values[start]))
            start = i
    span = [(xs[a], xs[b]) for a, b, _ in groups]

    def edge_at(index: int, step: int) -> Tuple[Tuple[float, float], Any]:
        a, b, _ = groups[index]
        inside = xs[a] if step < 0 else xs[b]
        outside = xs[groups[index - 1][1]] if step < 0 else xs[groups[index + 1][0]]
        edge, beyond = _step_edge(attribute, says_now, inside, outside)
        return (min(edge, beyond), max(edge, beyond)), attribute(beyond)

    found, anomaly = _region_boundaries(
        key, field, says_now, [g[2] for g in groups], span, edge_at, (lo, hi))
    if anomaly is not None or not found:
        return [], _scan_reason(key, field, says_now, scan_points, lo, hi,
                                in_this_run_only=anomaly is not None)
    # The option each side's state is computed from (§0.1 item 63): the
    # state itself for `mc_best`, and for `decisive` the central case's
    # winner there, whose P(cheapest) the floor is read against.
    for entry in found:
        entry["computed_from"] = (
            (entry["was"], entry["becomes"]) if field == "mc_best"
            else (free(entry["value"])[0].best, free(entry["upper_end"])[0].best))
    return found, None


# ---------------------------------------------------------------------------
# The figure a crossing prints (§0.1 items 42, 54 and 60)
# ---------------------------------------------------------------------------

# The precision each kind of crossing starts at, in decimals of a percent.
_START_PLACES: Dict[str, int] = {**{field: 4 for field in _DETERMINISTIC_FIELDS},
                                 **{field: 2 for field in _FUTURES_FIELDS}}


def floored_rate(value: float, places: int) -> str:
    """`value` as a percent at `places` decimals, FLOORED on the float's exact
    decimal value, so no binary representation can lift the printed figure
    past the value."""
    exact = Decimal(value).scaleb(2)
    return f"{exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_FLOOR):.{places}f}%"


def _percent_value(text: str) -> float:
    """The rate a printed percent names, read the way `--sweep` reads the same
    figure typed back."""
    return float(Decimal(text.rstrip("%")).scaleb(-2))


class CrossingRefused(Exception):
    """A check on one crossing that cannot pass (§0.1 item 61): the
    `RefusedBoundary` code it carries and the reason it measured. The row
    refuses that boundary; nothing else is refused with it."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"({code}): {reason}")
        self.code = code
        self.reason = reason


def _places_within(value: float, upper_end: float) -> int:
    """The most decimals of a percent a crossing whose bracket is
    `[value, upper_end]` prints at: one printed step is never narrower than
    the bracket (§0.1 item 60), and never finer than
    `PRINTED_RATE_MAX_PLACES`."""
    width = Decimal(upper_end) - Decimal(value)
    places = PRINTED_RATE_MAX_PLACES
    while places > 0 and Decimal(1).scaleb(-(places + 2)) < width:
        places -= 1
    return places


def printed_crossing(key: str, field: str, value: float, upper_end: float, was: Any,
                     says_at: Callable[[float], Any], lo: float) -> str:
    """The figure a crossing prints (§0.1 items 54 and 60): `value`, the lower
    end of the bracket the crossing converged in, floored at its kind's
    starting precision and widened one decimal at a time, up to
    `_places_within` the bracket, until the field, evaluated AT the printed
    figure by `says_at`, says `was` there. `says_at` is the field's own
    evaluation: the deterministic verdict for a solved crossing, this run's
    seeded curve for a sampled one.

    A floored figure below `lo`, the low end of the bracket searched, is
    passed over. Where no precision passes, it raises `CrossingRefused` with
    the code `not_printable` and what it found at each floored figure."""
    start = _START_PLACES[field]
    finest = _places_within(value, upper_end)
    found: List[str] = []
    for places in range(start, finest + 1):
        text = floored_rate(value, places)
        at = _percent_value(text)
        if at < lo:
            found.append(f"{text} is below the bracket searched")
            continue
        says = says_at(at)
        if says == was:
            return text
        found.append(f"{text} reads {says!r}")
    head = (f"the crossing of {field} from {was!r} whose bracket starts at {value!r}, "
            f"floored")
    if not found:
        raise CrossingRefused(
            "not_printable",
            f"{head} at no precision: its bracket is wider than one step at {start} "
            f"decimals of a percent")
    raise CrossingRefused(
        "not_printable",
        f"{head} at {start} to {finest} decimals of a percent: " + "; ".join(found))


def _probability_pairs(probs: Dict[str, Optional[float]]) -> Tuple[Tuple[str, float], ...]:
    """Option→P(cheapest) as ordered pairs, in the engine's own option order —
    the shape both boundary types take, so the frozen row is frozen all the way
    down."""
    return tuple((name, probs[name]) for name in ("condo", "house", "rent")
                 if probs.get(name) is not None)


def _typed_boundary(
    field: str, entry: Dict[str, Any], *,
    formatted: str,
    curve: Optional[Dict[str, Optional[float]]],
    confirmed: Optional[Dict[str, Optional[float]]],
    curve_paths: int, seed: int,
) -> Union[SolvedBoundary, SampledBoundary]:
    """One boundary, typed by WHICH SOLVER produced its value.

    A `_DETERMINISTIC_FIELDS` value is solved on the deterministic verdict and
    is the same figure at any seed, so it comes back as a `SolvedBoundary`
    carrying no sample — `confirmed` is corroboration when a re-simulation ran
    and an empty tuple when none did. A `_FUTURES_FIELDS` value is bisected on
    this run's free curve, so it comes back as a `SampledBoundary` carrying the
    curve's path count and seed, and it REFUSES to be built without them: a
    sample-dependent figure with no sample on it is the confusion the two types
    exist to make impossible.

    A field in neither list raises. Routing it by a default branch would type a
    fifth boundary kind as whichever of the two the branch happened to be, and
    that is the one error no downstream reader could detect.
    """
    # `was` / `becomes` pass through UNCOERCED: a `str()` here is what turned
    # a boolean decisiveness into "True" and let it print, so the type's own
    # check is the one that has to see the raw value.
    common = {"verdict_field": field, "value": entry["value"],
              "upper_end": entry["upper_end"], "formatted": formatted,
              "was": entry["was"], "becomes": entry["becomes"],
              "further_changes": entry["further"]}
    if field in _DETERMINISTIC_FIELDS:
        return SolvedBoundary(
            **common,
            confirming_probabilities=(
                _probability_pairs(confirmed) if confirmed is not None else ()))
    if field in _FUTURES_FIELDS:
        if curve is None or confirmed is None:
            raise ValueError(
                f"{field} is bisected on the futures curve and this call has none, so "
                f"nothing can say which sample its value belongs to")
        return SampledBoundary(**common,
                               curve_probabilities=_probability_pairs(curve),
                               confirming_probabilities=_probability_pairs(confirmed),
                               curve_paths=curve_paths, seed=seed)
    raise ValueError(
        f"{field} is in neither _DETERMINISTIC_FIELDS nor _FUTURES_FIELDS, so no solver "
        f"claims it and nothing here can say whether its value reads a sample")


# The label each candidate leaf prints under in the zero-spread section. Two
# entries rather than a derivation because the two rows are not the same claim:
# one is a schedule of future rates, the other the rate on the mortgage as
# quoted. NEUTRAL on whose figure it is.
_STATED_PATH_LABELS: Dict[str, str] = {
    "mortgage_renewal_rates": "the renewal rate",
    "mortgage_rate": "the contract rate",
}


def _stated_path_zero(key: str) -> StructuralZero:
    """The §3.5 `stated_path` row for one financing key: zero spread BY
    CONSTRUCTION, never a dash. `reversal_key` names the exact row carrying its
    crossings. It carries no sentence: that no draw touches the key is its
    KIND, and anything more would explain rather than report (§0.1 item 35)."""
    leaf = key.rsplit(".", 1)[-1]
    return StructuralZero(kind="stated_path", label=_STATED_PATH_LABELS.get(leaf, key),
                          keys=(key,), reversal_key=key)


def reversal_path_note(raw: Dict[str, Any], key: str) -> Optional[str]:
    """How the reversal axis of `key` is built, for a key the config states as
    a path of two or more different rates (§0.1 items 41 and 67), or None.

    A construction fact, and nothing more: every point on the axis is the
    config with that one leaf set to one figure (`sweep.load_at`), so the
    whole stated path is replaced by one rate at every renewal. Which configs
    get it is `sweep.stated_path`'s answer, the same one `--sweep`'s own note
    reads, so the two cannot disagree about what is a path.
    """
    if stated_path(raw, key) is None:
        return None
    return ("each crossing on this key is priced with the stated path replaced by one "
            "rate at every renewal")


# Every `RATE_BRACKETS` entry is a span written into the engine's code, never a
# figure typed for this household — so it carries the one label the block gives
# every figure the engine sets (§0.1 item 43), the label the budget ceiling
# carries. §6's correction is why the class is PRINTED: adding the renewal entry
# converted an honest refusal into an answer, which is a stronger act than
# replacing a silent default.
BRACKET_SOURCE = "set in the engine"


def reversal_register(
    raw: Dict[str, Any],
    det: ComparisonDeterministicResult,
    mc: Optional[ComparisonMonteCarloResult],
    *,
    gate_paths: int = 200,
    scan_points: int = REVERSAL_SCAN_POINTS,
    simulate: Callable[[ComparisonSpec], ComparisonMonteCarloResult] = run_monte_carlo,
    iterations: int = 60,
) -> ReversalRegister:
    """THE REVERSAL REGISTER — what would have to change for the verdict to
    change, for each input in scope that this config STATES.

    `det` and `mc` are THIS RUN's own results for `raw`, so a caller and the
    register cannot disagree about the base case. `simulate` is the seam the
    confirming re-simulation runs through: a test perturbs it and watches a
    boundary refuse, without which "confirmed on the fixture" would be a check
    that cannot fail.

    ALL FOUR of `decomposition.BOUNDARY_FIELDS` are answered on every exact or
    estimated row, and a kind this solver cannot reach on this config comes
    back as a `RefusedBoundary` naming why (§0.1 ruling 4). An absent row and
    a refused row are different claims and a reader cannot tell them apart.

    RETURNS AN EMPTY REGISTER, and that is data rather than an error, on the one
    config where no margin exists at all: fewer than two options priced
    (`single_option`). `decomposition.REFUSAL_CODES` is where the block-level
    refusals live and the assembler carries them; this function has no field for
    one and invents none.

    WITH NO FUTURES (`mc` is None — `--no-monte-carlo` — or a single-path run)
    the register still answers, with its SOLVED half: a crossing of the
    deterministic verdict reads no path, so `best` and `runner_up` come back as
    `SolvedBoundary` rows with an empty `confirming_probabilities` (there is no
    free curve for a re-simulation to confirm), and `mc_best` and `decisive`
    come back as `RefusedBoundary`, each with the reason true of it
    (`_unsolved_without_futures`): there is no majority without futures, while
    decisiveness exists — read off the margin band — and this solver does not
    look for it there. An empty register here would hide two figures that need
    no futures to compute, and a reader would take it as "nothing reverses".

    What that route costs, stated because it is not free: the exactness gate
    still runs, on `min(gate_paths, num_sims)` paths of a run whose caller
    priced none, because its licence divides by a standard deviation — and on a
    config where every uncertainty input is OFF those paths are identical, so
    its one-constant-shift clause is measured against zero dispersion and
    cannot fail. `probe_paths` and `max_path_deviation_over_sd` say on the row
    what was probed; reporting `probe_paths=0` beside a `0.0` deviation instead
    would be an all-clear nobody measured. The row still ROUTES on the gate as
    the futures branch does, although a solved crossing reads no path and needs
    no free curve: a key the gate refuses comes back as an `EstimatedReversal`
    carrying no boundary, here as there.

    THIS BRANCH IS THE LIBRARY SHAPE, AND NO SURFACE REACHES IT. Nothing in
    this package calls this function on a run without futures, and §0.1 item
    25 rules the branch deliberately unreached from `--decompose`: §8 refusal
    2 refuses that whole block with `no_futures` on a path-free run before any
    register is built. It is kept, rather than turned into a refusal, because the crossings it
    returns are `deterministic_boundaries`' own figures and need no futures; an
    unreached branch with its reason recorded is not an oversight to be
    "fixed" by wiring the block into a path-free run.
    """
    spec = load_config_dict(raw)
    options = _priced_options(raw)
    if len(options) < 2:
        return ReversalRegister(
            exact=(), estimated=(), structural_zeros=(), no_distance_code="single_option",
            no_distance_reason="fewer than two options are priced")

    # One flag, read in both places that care: whether THIS run has futures for
    # a curve to be read off. A single-path run has an `mc` object and no
    # futures in it, so the two cases are one case here.
    futures = mc if (mc is not None and not single_path_run(spec)) else None
    paths = int(spec.simulation.num_sims)
    seed = int(spec.simulation.random_seed)
    stated = compute_verdict(det, futures, years=spec.simulation.years,
                             discount_rate=spec.simulation.discount_rate,
                             single_path=futures is None)
    exact: List[ExactReversal] = []
    estimated: List[EstimatedReversal] = []
    zeros: List[StructuralZero] = []
    not_admitted: List[RefusedReversal] = []

    for key, option in reversal_candidates(raw):
        lo, hi = reversal_bracket(key)
        far = reversal_probe(raw, key)
        admitted, record = reversal_admission(raw, key, far, base=det)
        if not admitted:
            # §6: a key that moves nothing is not printed as a flat curve. It
            # is a refused row with what was measured (§0.1 item 64).
            not_admitted.append(RefusedReversal(
                key=key, option=option, code="not_admitted",
                reason=_not_admitted_reason(key, priced=bool(record["deltas"]))))
            continue
        gate = reversal_gate(raw, key, far, paths=gate_paths, simulate=simulate)

        common = {
            "key": key, "option": option,
            "bracket_low": lo, "bracket_high": hi, "bracket_source": BRACKET_SOURCE,
            "max_path_deviation_over_sd": gate["worst_deviation_over_sd"],
            "path_note": reversal_path_note(raw, key),
        }
        if not gate["licensed"]:
            # Unreachable for a financing-leg key on a correct engine —
            # `_financing_pv` shifts every path by one constant — so arriving
            # here means the licence evidence failed and the row exists to say
            # so by name rather than vanish. The row refuses rather than
            # estimating (§6), so it carries no boundary at all.
            estimated.append(EstimatedReversal(
                **common, boundaries=(),
                refused_boundaries=tuple(
                    RefusedBoundary(verdict_field=field, code="not_exact",
                                    reason=gate["why"])
                    for field in BOUNDARY_FIELDS)))
            continue
        boundaries, refused = _confirmed_boundaries(
            raw, key, options, det, futures, stated, lo, hi, paths=paths, seed=seed,
            scan_points=scan_points, simulate=simulate, iterations=iterations)
        exact.append(ExactReversal(
            **common, probe_paths=gate["paths"],
            boundaries=tuple(boundaries), refused_boundaries=tuple(refused)))
        zeros.append(_stated_path_zero(key))

    rowless = not (exact or estimated or not_admitted)
    return ReversalRegister(
        exact=tuple(exact), estimated=tuple(estimated), structural_zeros=tuple(zeros),
        no_distance_code="no_candidate" if rowless else None,
        no_distance_reason=(f"this config states no {' or '.join(REVERSAL_LEAVES)}"
                            if rowless else None),
        refused=tuple(not_admitted))


def _stated_values(raw: Dict[str, Any], key: str) -> List[Any]:
    """Each figure the config states for `key`: one, or each rate of a path."""
    value = base_value(raw, key)
    return list(value) if isinstance(value, list) else [value]


def _not_admitted_reason(key: str, *, priced: bool) -> str:
    """The measured fact a `not_admitted` row states (§0.1 items 50 and 64):
    the far end of the key's bracket was priced and moved no option's present
    value, or the loader refused it."""
    return (f"this config states {key}, and "
            + ("moving it to the far end of its bracket moves no option's present value"
               if priced else "the loader refuses it at the far end of its bracket"))


def _unsolved_without_futures(field: str) -> Tuple[str, str]:
    """Why a futures-side field is not solved on a run WITHOUT futures.

    `mc_best` does not exist on such a run: the majority is a frequency over
    futures, and `compute_verdict` leaves it None. `decisive` DOES exist — the
    verdict reads it off the central case's margin against the tie band
    (`margin_band`) — and it can change inside the bracket, so the reason may
    not say it does not exist. What is true of both, and measured, is that
    this run has no futures and this solver reads both fields off them.
    """
    if field not in _FUTURES_FIELDS:
        raise ValueError(f"{field} is solved on the central case, not on futures")
    return "no_futures", (f"this run has no futures, and this solver reads {field} "
                          f"only off futures")


def _confirmed_boundaries(
    raw: Dict[str, Any], key: str, options: Sequence[str],
    det: ComparisonDeterministicResult, mc: Optional[ComparisonMonteCarloResult],
    stated: Verdict, lo: float, hi: float, *,
    paths: int, seed: int, scan_points: int,
    simulate: Callable[[ComparisonSpec], ComparisonMonteCarloResult], iterations: int,
) -> Tuple[List[Union[SolvedBoundary, SampledBoundary]], List[RefusedBoundary]]:
    """`(boundaries, refused)`: every one of `BOUNDARY_FIELDS` answered, the
    boundary's own type where one exists, was confirmed and prints, a
    `RefusedBoundary` naming why everywhere else. Nothing is ever silently
    absent — an absent row and a refused row are different claims and a
    reader cannot tell them apart.

    A boundary whose field does not say its `was` at its `value` and its
    `becomes` at its `upper_end` refuses first (§0.1 item 67). Each reported
    boundary is confirmed by ONE FULL RE-SIMULATION at its `value`, compared
    against the free curve's own probabilities at that same value. A boundary
    of a futures field is additionally required to be identified outside
    Monte Carlo noise before it is confirmed at all — re-simulating an
    unidentified boundary would dress noise in a measurement. A confirmed
    boundary then prints its figure (`printed_crossing`). A check that cannot
    pass refuses that one boundary (§0.1 item 61).

    `mc` IS None WHEN THIS RUN HAS NO FUTURES, and then there is no free curve
    to build: the deterministic pair is still solved, comes back as
    `SolvedBoundary` with nothing corroborating it, and the futures pair is
    refused by name. The solved values are bit-identical either way, because
    `deterministic_boundaries` reads no path in either case.
    """
    free = (_free_curve(raw, key, options, det, mc, single_path=False)
            if mc is not None else None)
    solved = deterministic_boundaries(raw, key, lo, hi, base=det, iterations=iterations)
    per_field: Dict[str, Tuple[List[Dict[str, Any]], Optional[Tuple[str, str]]]] = {}
    for field in _DETERMINISTIC_FIELDS:
        found = [b for b in solved["boundaries"] if b["attribute"] == field]
        mismatch = next((m for m in solved["mismatched"] if m["attribute"] == field), None)
        if found:
            per_field[field] = (found, None)
        elif mismatch is not None:
            per_field[field] = ([], _mismatch_reason(key, field, mismatch))
        else:
            # `deterministic_boundaries` files a field with no boundary as an
            # anomaly, as unchanged or as mismatched, never as none of them.
            anomaly = next((a for a in solved["anomalies"] if a["attribute"] == field), None)
            record = anomaly if anomaly is not None else [
                u for u in solved["unchanged"] if u["attribute"] == field][0]
            per_field[field] = ([], _scan_reason(
                key, field, record["value"], record["points"], lo, hi,
                in_this_run_only=anomaly is not None))
    for field in _FUTURES_FIELDS:
        per_field[field] = ((
            _futures_field_boundaries(
                raw, key, field, free, stated, lo, hi, scan_points=scan_points))
            if free is not None else ([], _unsolved_without_futures(field)))

    def says_at(field: str) -> Callable[[float], Any]:
        """The field's own evaluation at one value of the axis: the
        deterministic verdict for a solved kind, the seeded curve for a
        sampled one — what a boundary's two ends and its printed figure are
        checked on."""
        if field in _DETERMINISTIC_FIELDS:
            return lambda v: _ranking_at(raw, key, v)[field]
        return lambda v: field_state(free(v)[0], field)

    def said(probs: Dict[str, Optional[float]]) -> str:
        return ", ".join(f"{name} {p:.4f}" for name, p in probs.items() if p is not None)

    refused: List[RefusedBoundary] = []
    reported: List[Union[SolvedBoundary, SampledBoundary]] = []
    for field in BOUNDARY_FIELDS:
        found, refusal = per_field[field]
        if refusal is not None:
            refused.append(RefusedBoundary(verdict_field=field, code=refusal[0],
                                           reason=refusal[1]))
            continue
        for entry in found:
            value = entry["value"]
            ends = [says_at(field)(end) for end in (value, entry["upper_end"])]
            if ends != [entry["was"], entry["becomes"]]:
                refused.append(RefusedBoundary(
                    verdict_field=field, code="not_bracketed", reason=(
                        f"{field} says {ends[0]!r} at {value!r} and {ends[1]!r} at "
                        f"{entry['upper_end']!r}, the two ends of the bracket its "
                        f"crossing from {entry['was']!r} to {entry['becomes']!r} "
                        f"converged in")))
                continue
            # No futures: the solved value stands on its own and nothing
            # re-simulates it, which is what the empty corroboration says.
            curve = confirmed = None
            if free is not None:
                curve = free(value)[1]
                if field in _FUTURES_FIELDS:
                    identified = _identification(
                        entry, {"lo": free(lo)[1], "hi": free(hi)[1], "at": curve}, paths)
                    if not identified["identified"]:
                        refused.append(RefusedBoundary(verdict_field=field,
                                                       code="not_identified",
                                                       reason=identified["why"]))
                        continue
                confirming = simulate(load_at(raw, key, value))
                confirmed = {name: getattr(confirming, f"prob_{name}_cheapest")
                             for name in ("condo", "house", "rent")}
                if confirmed != curve:
                    refused.append(RefusedBoundary(
                        verdict_field=field, code="unconfirmed", reason=(
                            f"the re-simulation at {value!r} gives {said(confirmed)}, and "
                            f"the free curve gives {said(curve)}")))
                    continue
            try:
                text = printed_crossing(key, field, value, entry["upper_end"],
                                        entry["was"], says_at(field), lo)
            except CrossingRefused as no:
                refused.append(RefusedBoundary(verdict_field=field, code=no.code,
                                               reason=no.reason))
                continue
            reported.append(_typed_boundary(field, entry, curve=curve, confirmed=confirmed,
                                            curve_paths=paths, seed=seed, formatted=text))
    reported.sort(key=lambda b: (BOUNDARY_FIELDS.index(b.verdict_field), b.value))
    refused.sort(key=lambda r: BOUNDARY_FIELDS.index(r.verdict_field))
    return reported, refused
