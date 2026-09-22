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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .anchors import ANCHORS
from .config import ConfigValidationError, load_config_dict, single_path_run
from .decomposition import (BOUNDARY_FIELDS, CHANNELS, AxisReference, Boundary,
                            EstimatedReversal, ExactReversal, RefusedBoundary,
                            ReversalRegister, StructuralZero)
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
                    real_equivalent_inflation, with_value)

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
# borrowing one. The bracket is assistant-chosen like every other entry here
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

    Two callers, one crossing: ``solve_break_even`` wraps this with the YAML
    loader, ``story_plots.solve_rent_threshold`` with a spec-level rent sweep,
    so the act draws and phrases the threshold the CLI reports.
    """
    a, b = options
    band = ANCHORS["verdict.tie_band"].value
    refused = [] if refused is None else refused
    cache: Dict[float, Optional[Tuple[float, float]]] = {}

    def totals_or_none(v: float) -> Optional[Tuple[float, float]]:
        """The two totals at v, or None when the caller refuses that value (a
        price below the fixed down payment, a rate outside its bounds): the
        refusal is recorded, never raised — the search shrinks to what the
        config accepts and the output says so."""
        vv = int(round(v)) if is_int else float(v)
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

    def scan(x_lo: float, x_hi: float) -> Tuple[List[float], List[Optional[float]]]:
        n = 9 if not is_int else max(2, min(9, int(x_hi - x_lo) + 1))
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
            if y0 == 0.0:
                x0 = x1 = xs[i - 1]
            elif y0 * y1 < 0:
                x0, x1 = xs[i - 1], xs[i]
            else:
                continue
            v = x0 if x0 == x1 else bisect(gap, x0, x1)
            if x0 == x1:
                probe = min(x1 + 1e-9 * max(1.0, abs(x1)), xs[-1])
                below, above = (a, b) if gap(probe) > 0 else (b, a)
                left = edge(v, i - 2, -1)
            else:
                below, above = (a, b) if y0 < 0 else (b, a)  # gap<0 ⇒ A cheaper
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
        out["no_crossing"] = no_crossing_record(
            key, out["cheaper_throughout"], searched, (lo, hi),
            first_gap or 0.0, last_gap or 0.0, is_int=is_int)
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
    threshold: Optional[float] = None

    def at(value: Any) -> Optional[Dict[str, Dict[str, Any]]]:
        nonlocal threshold
        if value is None:
            return None
        try:
            det = compute_deterministic(load_at(raw, key, value))
        except (ConfigValidationError, ValueError):
            return None
        if det.income_report is not None:
            threshold = det.income_report.threshold
        return affordability_of(det)

    crossing = at(entry["value"])
    if crossing is None:
        return None
    edges = [at(edge) for edge in entry["tie_band"]]
    return {"threshold": threshold, "value": crossing, "tie_band": edges}


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
    line). One builder for the text block, the read-back and every `across`
    row, so the three cannot phrase the same threshold differently."""
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


def quoted_points(key: str, be: Dict[str, Any]) -> List[Tuple[str, Any, Dict[str, Any]]]:
    """(label, value, per-option affordability) for every point the sentence
    quotes and the run priced: the crossing and both band edges."""
    aff = be.get("affordability")
    if not aff:
        return []
    lo, hi = be["tie_band"]
    points = [("at the crossing", be["value"], aff["value"]),
              ("at the band's low edge", lo, aff["tie_band"][0]),
              ("at the band's high edge", hi, aff["tie_band"][1])]
    return [(label, value, per) for label, value, per in points
            if per is not None and value is not None]


def _aff_phrase(option: str, entry: Dict[str, Any]) -> str:
    return f"{option} {entry['max_ratio']:.1%} ({len(entry['years_exceeding'])} yr(s) over)"


def _affordability_points(
    key: str, be: Dict[str, Any], drop: Any = (),
) -> Tuple[Optional[float], List[str]]:
    """(threshold, phrases): the crossing and both band edges with their
    highest cost/income ratio and breach count. An option whose figures are
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
    "cheaper on average" answer needs beside the crossing it quotes."""
    threshold, phrases = _affordability_points(key, be)
    if not phrases:
        return []
    head = _affordability_head(threshold, " at the crossing and the band edges")
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
    there, what the config refused, and what the crossing costs against income.

    One builder for the text block and the read-back line (2026-09-04 review:
    the block carried the base sentence alone, so an answer reduced a whole
    years bracket to "near $300k"). The read-back passes `refused_clause=False`
    and `head=False` where its header states those once, and `drop` for the
    options the header states at every point.
    """
    sentences = threshold_sentences(key, row, band)
    if refused_clause and _refused_clause(row):
        sentences.append(_refused_clause(row))
    text = f"{sweep_key}={point_label(sweep_key, row['value'], pi)}: " + "; ".join(sentences)
    for be in row["break_evens"]:
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
    quoted = [per for c in carriers for be in c["break_evens"]
              for _, _, per in quoted_points(key, be)]
    constant = constant_options(quoted) if len(quoted) > 1 else {}
    thresholds = [be["affordability"]["threshold"] for c in carriers for be in c["break_evens"]
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
        _affordability_clause(key, be, drop=drop, head=False) for be in result["break_evens"])
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
    for be in result["break_evens"]:
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
# can answer. For each input the config STATES that carries no distribution in
# this run, it answers one question — how far would this one input have to
# move, holding everything else, before the verdict names a different winner.
#
# EXACT AND ESTIMATED, in `decomposition`'s sense, split on whether the
# EXACTNESS GATE licensed the key's shift, not on which verdict field moved:
# a licensed key's boundaries are all exact, confirmed by re-simulation, and
# live in `ExactReversal`; slice 1 REFUSES an unlicensed key rather than
# estimating it (§6), so `EstimatedReversal` stays empty on a correct engine.
# All four of `BOUNDARY_FIELDS` are answered on every row, and a kind this
# solver cannot reach comes back as a `RefusedBoundary` naming why (§0.1
# ruling 4) — an absent row and a refused row are different claims.
#
# ONE PROPERTY THE CONTRACT DOES NOT CARRY, measured here so a later reader
# is not surprised by it: on tests/fixtures/uncertainty_surface.yaml the
# `best` and `runner_up` boundaries are identical to seven digits at seeds 42,
# 7, 1234, 99 and 2026, while the `mc_best` boundary moves across
# 2.698%–2.805% over those same five seeds. Two are properties of the config;
# one is a property of this run's 2,000 futures. `Boundary` gives all three
# the same shape, so nothing downstream can tell them apart — the deterministic
# pair is recoverable from `deterministic_boundaries`, which reads no path.
#
# Why the register exists at all: `mortgage_renewal_rates` is a path the user
# states, not a distribution, so its variance is zero BY CONSTRUCTION and any
# variance table prints it as a dash. A reader sees six rows carrying numbers
# and one carrying dashes and concludes renewal was weighed and found
# irrelevant. Measured on the fixture the opposite is true: the verdict's own
# winner flips from rent to the house at a flat renewal rate of 1.6052%, inside
# the bracket the engine already uses for a contract rate.
# ---------------------------------------------------------------------------

# The financing-leg keys, per owned option. Candidates are inputs the config
# STATES that carry no distribution and move an owned option's deterministic
# PV; a sizing key of a drawn channel (`*_vol`, a hazard, a correlation) is
# never one, by construction rather than by omission — `compute_deterministic`
# reads no dispersion input, so a deterministic curve over a vol key is a flat
# line, and a flat line under this heading would print "this risk does not
# affect the verdict" about every risk (spec §6).
REVERSAL_LEAVES: Tuple[str, ...] = ("mortgage_renewal_rates", "mortgage_rate")

# The exactness gate's tolerance, as a multiple of the option's own PV standard
# deviation. NOT a tuned threshold, and the measurement is what says so: on the
# fixture the worst per-path deviation is 9.5e-16 of sd for both financing keys
# against 2.7 and 2.9 for `house.value_growth_rate` and `rent.monthly_rent` —
# fifteen orders of magnitude, so every figure in that gap licenses and refuses
# exactly the same keys.
REVERSAL_GATE_TOLERANCE = 1e-9

# `BOUNDARY_FIELDS` split by HOW each one is located. The deterministic pair
# comes off `solve_crossings`, reads no path, and is the same figure at any
# `num_sims`; the futures pair is a step function of the axis found on the free
# curve. Both kinds land in the same `ExactReversal.boundaries` tuple, because
# `decomposition`'s exact/estimated axis is the GATE's, not this one — see the
# section header.
_DETERMINISTIC_FIELDS: Tuple[str, ...] = ("best", "runner_up")
_FUTURES_FIELDS: Tuple[str, ...] = ("mc_best", "decisive")

# How finely a futures field's bracket is scanned before an edge is bisected.
# A deterministic field needs no scan (its crossing is solved), but `mc_best`
# and `decisive` are STEP functions of the axis with no sign to bracket, so their
# edges are found by scan-then-bisect and a flip lying entirely inside one
# scan cell is not seen. The count is reported with every futures row so that
# resolution is the reader's to judge: at 65 points a cell is 1/64 of the
# bracket, 0.14 points of rate on the contract bracket, against the 0.24
# points that separate the fixture's own two futures-side boundaries.
REVERSAL_SCAN_POINTS = 65

# The anchors that sit on a mortgage-rate axis — the published figures a reader
# can put beside a guess. Named here rather than in a formatter so the axis and
# the anchors on it have one home. A posted rate is a LIST PRICE that brackets a
# guess from above; it is never a ceiling on a future renewal.
_RATE_AXIS_ANCHORS: Tuple[str, ...] = (
    "mortgage_rate.contracted_5y_uninsured",
    "mortgage_rate.contracted_5y_insured",
    "mortgage_rate.posted_5y",
)


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
    admission measurement. That is what excludes an ALL-CASH option, and the
    measurement could not have done it: measured on the fixture's `condo`, the
    loader refuses `condo.mortgage_rate` outright (`all_cash: true is set
    together with mortgage fields`) and refuses `condo.mortgage_renewal_rates`
    for want of a renewal term — so probing either would report a loader
    refusal as though it were a measured absence of effect.
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


def reversal_admission(
    raw: Dict[str, Any], key: str, hi: float,
    *, base: Optional[ComparisonDeterministicResult] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """`(admitted, record)` — the admission test, which is a MEASUREMENT and
    not a list (spec §6): one `load_at` + `compute_deterministic` at the far
    end of the key's bracket, and the key is admitted only if some option's
    deterministic PV moves.

    A key that moves nothing is not printed as a flat curve; it is not a
    candidate. The screen still has work to do on a key the config states — a
    renewal term at or past the amortization makes the ladder inert, which the
    loader warns about and prices as stated — so it is kept even though
    `reversal_candidates` has already dropped the unstated keys.
    """
    base = base if base is not None else compute_deterministic(load_config_dict(raw))
    options = _priced_options(raw)
    try:
        probe = compute_deterministic(load_at(raw, key, hi))
    except (ConfigValidationError, ValueError, RateConventionError) as e:
        return False, {"probe": hi, "moves": [], "deltas": {},
                       "why": (f"the loader refuses {_fmt_value(key, hi)} — "
                               f"{str(e).strip().splitlines()[-1].strip()}")}
    deltas = {
        option: getattr(probe, option).total_pv - getattr(base, option).total_pv
        for option in options
        if getattr(probe, option, None) is not None and getattr(base, option, None) is not None
    }
    moves = [option for option, delta in deltas.items() if delta != 0.0]
    if not moves:
        return False, {
            "probe": hi, "moves": [], "deltas": deltas,
            "why": (f"no option's present value moves at {_fmt_value(key, hi)}, the far end "
                    f"of its bracket — the config states it and this run prices nothing by it"),
        }
    return True, {"probe": hi, "moves": moves,
                  "deltas": {option: deltas[option] for option in moves}, "why": None}


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
    for name in _priced_options(raw):
        before, after = getattr(base, name, None), getattr(at, name, None)
        if before is None or after is None:
            continue
        if name == option:
            delta = after.pvs - before.pvs
            sd = float(np.std(before.pvs))
            worst = float(np.max(np.abs(delta - float(np.mean(delta)))))
            record["worst_deviation_over_sd"] = (
                worst / sd if sd > 0 else (0.0 if worst == 0.0 else math.inf))
        elif not np.array_equal(before.pvs, after.pvs):
            record["others_bit_identical"] = False
            record["moved_others"].append(name)
    deviation = record["worst_deviation_over_sd"]
    if not record["others_bit_identical"]:
        record["why"] = (
            f"moving {key} moves {', '.join(record['moved_others'])} too, and this key names "
            f"neither — it changes the draw stream, so no curve over it is free")
    elif deviation is None:
        record["why"] = f"{option} is not priced in this run, so its shift cannot be measured"
    elif deviation > REVERSAL_GATE_TOLERANCE:
        record["why"] = (
            f"moving {key} shifts {option} by a DIFFERENT amount on different paths (worst "
            f"{deviation:.2e} of its own sd, against {REVERSAL_GATE_TOLERANCE:.0e}) — the "
            f"futures at another value have to be re-simulated, not shifted")
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


def _region_boundaries(
    key: str, field: str, says_now: Any, region_values: Sequence[Any],
    region_span: Sequence[Tuple[float, float]],
    edge_at: Callable[[int, int], Optional[float]],
    bracket: Tuple[float, float],
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """The boundaries of the region(s) in which `field` still says what this
    run says — plus the one anomaly this can produce.

    There is no base POINT on the axis to measure a distance from when the
    config states the input as a path. What is well defined, and what the
    output prints, is the edge of the region whose answer matches the run's:
    *the winner changes from rent to the house at 1.61%* means `best` is `rent`
    above that value and `house` below it. `([], record)` comes back when the
    run's own answer appears nowhere on the axis — reported, never dropped.
    """
    runs = _matching_runs(region_values, says_now)
    if not runs:
        return [], {
            "attribute": field, "says_now": says_now, "bracket": list(bracket),
            "why": (f"{field} says {says_now!r} in this run and says so nowhere in "
                    f"{_fmt_value(key, bracket[0])}–{_fmt_value(key, bracket[1])}, so no "
                    f"distance along this axis is a distance from what the run says"),
        }
    if len(runs) == 1 and len(runs[0]) == len(region_values):
        return [], None                       # unchanged across the whole bracket
    out: List[Dict[str, Any]] = []
    for run in runs:
        first, last = run[0], run[-1]
        low = edge_at(first, -1) if first > 0 else None
        high = edge_at(last, +1) if last < len(region_values) - 1 else None
        holds = [low if low is not None else region_span[first][0],
                 high if high is not None else region_span[last][1]]
        if low is not None:
            out.append({"attribute": field, "from": says_now, "to": region_values[first - 1],
                        "value": low, "direction": "below", "holds": holds})
        if high is not None:
            out.append({"attribute": field, "from": says_now, "to": region_values[last + 1],
                        "value": high, "direction": "above", "holds": holds})
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
    that carries no sample in it anywhere, and the half the deterministic
    renewal-flip line of `2026-09-21-unpriced-dimensions.md` slice 2 calls.

    ONE SOLVER, TWO CONSUMERS (seat ruling, mechanism): every value reported
    here is `solve_crossings`' own figure on the relevant pair, so the number
    this prints and the number `--break-even` prints on that pair are the same
    number BY CONSTRUCTION rather than by a test comparing two bisections.
    `--break-even` itself refuses a three-option config; its solver takes a
    pair and a `totals_at` callable and is the one home for this truth.
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
                                         refused=declined)
            except ValueError as e:
                refused.append({"pair": [a, b], "why": str(e).strip().splitlines()[-1].strip()})
                continue
            for entry in solved["break_evens"]:
                crossings.append({"pair": [a, b], **entry})
    crossings.sort(key=lambda c: c["value"])
    edges = [c["value"] for c in crossings]
    span = [(x0, x1) for x0, x1 in zip([lo] + edges, edges + [hi])]
    ranks = [_ranking_at(raw, key, 0.5 * (x0 + x1)) for x0, x1 in span]
    # What the RUN says, from its own deterministic result rather than from any
    # point of the axis — the stated input may be a path, which is not on it.
    base = base if base is not None else compute_deterministic(spec)
    stated = compute_verdict(base, None, years=spec.simulation.years,
                             discount_rate=spec.simulation.discount_rate, single_path=True)

    out: Dict[str, Any] = {
        "key": key, "bracket": [lo, hi], "options": options, "crossings": crossings,
        "regions": [{"from": x0, "to": x1, **rank} for (x0, x1), rank in zip(span, ranks)],
        "boundaries": [], "unchanged": [], "anomalies": [], "refused": refused,
    }
    for field in _DETERMINISTIC_FIELDS:
        found, anomaly = _region_boundaries(
            key, field, getattr(stated, field), [rank[field] for rank in ranks], span,
            lambda i, step: edges[i - 1] if step < 0 else edges[i], (lo, hi))
        if anomaly is not None:
            out["anomalies"].append(anomaly)
        elif not found:
            out["unchanged"].append({"attribute": field, "value": getattr(stated, field),
                                     "bracket": [lo, hi]})
        else:
            for entry in found:
                crossing = next((c for c in crossings if c["value"] == entry["value"]), None)
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
) -> float:
    """The extreme value at which `attribute` still equals `says_now`, bisected
    between a value that matches and one that does not.

    Not `solve_crossings`' bisection and deliberately not folded into it: that
    one brackets a SIGN CHANGE of a continuous gap and reports the value where
    the gap is zero. `mc_best` and `decisive` are step functions of a discrete
    attribute — there is no gap and no sign — so what is bracketed is a change
    of VALUE and what is returned is the last value on the run's own side of
    the step, which is where the confirming re-simulation has to be run.
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
    return hi


def _identification(
    field: str, boundary: Dict[str, Any], probs: Dict[str, Dict[str, Optional[float]]],
    best: Optional[str], paths: int,
) -> Dict[str, Any]:
    """Whether a futures boundary is identified INSIDE Monte Carlo noise
    (spec §6, refusal i): the bracket-wide `|ΔP|` of each probability the
    boundary turns on, against `2·SE` at the boundary itself, where
    `SE = sqrt(p(1−p)/N)`.

    `SE` is taken at the boundary rather than at either end on purpose: that is
    where the two probabilities meet, so it is where the standard error is
    largest and the test is at its strictest.
    """
    if field == "mc_best":
        watched = [o for o in (boundary["from"], boundary["to"]) if isinstance(o, str)]
    else:
        watched = [best] if best else []
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
                "why": "no probability is attached to this boundary, so it cannot be identified"}
    worst = min(row["delta_p"] for row in rows)
    noise = max(row["two_se"] for row in rows)
    record = {"identified": worst > noise, "paths": paths, "watched": rows,
              "delta_p": worst, "two_se": noise, "why": None}
    if not record["identified"]:
        record["why"] = (
            f"across the bracket the probabilities this boundary turns on move by "
            f"{worst:.4f}, inside the {noise:.4f} that {paths} paths cannot resolve — the "
            f"boundary is not identified and is not reported")
    return record


def _futures_field_boundaries(
    raw: Dict[str, Any], key: str, field: str, free: Callable[[float], Any],
    stated: Verdict, lo: float, hi: float, *, scan_points: int,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """`([boundary, ...], None)` or `([], reason)` for one FUTURES field.

    `mc_best` and `decisive` are step functions of the axis with no sign to
    bracket, so the bracket is scanned and each edge of the run that matches
    what this run says is bisected. A flip lying entirely inside one scan cell
    is not seen, which is why `scan_points` rides with every row.
    """
    xs = [lo + (hi - lo) * i / (scan_points - 1) for i in range(scan_points)]
    values = [getattr(free(x)[0], field) for x in xs]
    groups: List[Tuple[int, int, Any]] = []
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[start]:
            groups.append((start, i - 1, values[start]))
            start = i
    span = [(xs[a], xs[b]) for a, b, _ in groups]

    def edge_at(index: int, step: int) -> float:
        a, b, _ = groups[index]
        inside = xs[a] if step < 0 else xs[b]
        outside = xs[groups[index - 1][1]] if step < 0 else xs[groups[index + 1][0]]
        return _step_edge(lambda v: getattr(free(v)[0], field),
                          getattr(stated, field), inside, outside)

    found, anomaly = _region_boundaries(
        key, field, getattr(stated, field), [g[2] for g in groups], span, edge_at, (lo, hi))
    if anomaly is not None:
        return [], anomaly["why"] + f" (scanned at {scan_points} points)"
    if not found:
        return [], (f"{field} says {getattr(stated, field)!r} at every one of {scan_points} "
                    f"points across {_fmt_value(key, lo)}–{_fmt_value(key, hi)}, so no "
                    f"boundary of it lies in the range this axis searches")
    return found, None


def _probability_pairs(probs: Dict[str, Optional[float]]) -> Tuple[Tuple[str, float], ...]:
    """Option→P(cheapest) as ordered pairs, in the engine's own option order —
    the shape `decomposition.Boundary` takes, so the frozen row is frozen all
    the way down."""
    return tuple((name, probs[name]) for name in ("condo", "house", "rent")
                 if probs.get(name) is not None)


# The label each candidate leaf prints under "NOT DRAWN IN THIS RUN" (§7). Two
# entries rather than a derivation because the renewal row's wording is the
# spec's own and the two rows are not the same claim: one is a schedule the
# user invented, the other a contract they signed.
_STATED_PATH_LABELS: Dict[str, str] = {
    "mortgage_renewal_rates": "your renewal rate",
    "mortgage_rate": "your contract rate",
}


def _stated_path_zero(raw: Dict[str, Any], key: str, option: str) -> StructuralZero:
    """The §3.5 `stated_path` row for one financing key: zero spread BY
    CONSTRUCTION, never a dash. `reversal_key` joins it to the reversal row
    that carries its solved rates, which is the whole reason the row is worth
    printing — a reader who sees a dash concludes renewal was weighed and found
    irrelevant."""
    leaf = key.rsplit(".", 1)[-1]
    value = base_value(raw, key)
    formatted = (", ".join(_fmt_value(key, float(v)) for v in value)
                 if isinstance(value, list) else _fmt_value(key, float(value)))
    # One reason per kind of key, not the ladder's reason pasted onto both. The
    # forward-rate clause is TRUE of a renewal path and beside the point on a
    # rate already contracted for the opening term, and a sentence that is true
    # of the row it was written for is exactly what a category-general branch
    # loses first (2026-09-22, the same find as the bracket refusal above).
    if isinstance(value, list):
        reason = (f"{key} is a path you stated, not a distribution — the engine anchors no "
                  f"forward rate and draws none, so {option}'s renewals carry no spread here "
                  f"at all. They carry a solved distance instead")
    else:
        reason = (f"{key} is one rate you stated, held for the opening term — no draw in this "
                  f"engine touches it, so {option}'s financing carries no spread here at all. "
                  f"It carries a solved distance instead")
    return StructuralZero(
        kind="stated_path", label=_STATED_PATH_LABELS.get(leaf, key),
        keys=(key,), reason=reason,
        stated_formatted=formatted, reversal_key=key)


def _other_structural_zeros(raw: Dict[str, Any], spec: ComparisonSpec) -> List[StructuralZero]:
    """§3.5's other two kinds, both resolved from the spec and costing no
    evaluation. They live in the reversal register by ruling (§0.1 item 5),
    because §7 renders them in the same section as the stated-path rows."""
    out: List[StructuralZero] = []
    if spec.income is not None and raw.get("income", {}).get("pay_drop_events"):
        out.append(StructuralZero(
            kind="no_pv_reach", label="your income", keys=("income.pay_drop_events",),
            reason=("income.pay_drop_events moves the affordability report, not either "
                    "option's present value, so it cannot move this margin")))
    corr_keys = ("corr_inflation_condo", "corr_inflation_house",
                 "corr_inflation_other", "corr_inflation_event_cost")
    if (spec.economic.mode == "real" and spec.economic.inflation_vol > 0
            and all(float(getattr(spec.simulation, name, 0.0) or 0.0) == 0.0
                    for name in corr_keys)):
        economy = next(c for c in CHANNELS if c.key == "economy")
        out.append(StructuralZero(
            kind="dead_draw", label=economy.label,
            keys=("economic.inflation_vol",) + tuple(f"simulation.{n}" for n in corr_keys),
            reason=("in REAL mode `_effective_growth_rate` discards the inflation factor by "
                    "construction, and every corr_inflation_* is 0, so this channel draws "
                    "every year and reaches no cash flow — detected from the config, with no "
                    "evaluation spent on it. A measured 0.00 here would read as 'inflation "
                    "does not matter', which is not what is true"),
            channel_id=economy.id))
    return out


# Every `RATE_BRACKETS` entry is a span the assistant chose — the module's own
# comment says so — and §6's correction is why the class is PRINTED: adding the
# renewal entry converted an honest refusal into an answer, which is a stronger
# act than replacing a silent default.
BRACKET_SOURCE = "assistant"


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

    ALL FOUR of `decomposition.BOUNDARY_FIELDS` are answered on every row, and
    a kind this solver cannot reach on this config comes back as a
    `RefusedBoundary` naming why (§0.1 ruling 4). An absent row and a refused
    row are different claims and a reader cannot tell them apart.

    RETURNS AN EMPTY REGISTER, and that is data rather than an error, when the
    block itself refuses: fewer than two options priced (`single_option`), or
    no futures at all (`no_futures` — `--no-monte-carlo`, or a single-path
    run). `decomposition.REFUSAL_CODES` is where those live and the assembler
    carries them; this function has no field for a block-level refusal and
    invents none.

    On no futures the DETERMINISTIC half is genuinely still available — a
    crossing reads no path — and `decomposition.Boundary` requires both a
    curve and a confirming set of probabilities, so it cannot express one.
    `deterministic_boundaries` is the surface that answers there, and it is the
    one the unpriced-dimensions renewal-flip line calls.
    """
    spec = load_config_dict(raw)
    options = _priced_options(raw)
    if len(options) < 2 or mc is None or single_path_run(spec):
        return ReversalRegister(exact=(), estimated=(), structural_zeros=())

    paths = int(spec.simulation.num_sims)
    stated = compute_verdict(det, mc, years=spec.simulation.years,
                             discount_rate=spec.simulation.discount_rate, single_path=False)
    exact: List[ExactReversal] = []
    estimated: List[EstimatedReversal] = []
    zeros: List[StructuralZero] = []

    for key, option in reversal_candidates(raw):
        lo, hi = reversal_bracket(key)
        admitted, _ = reversal_admission(raw, key, hi, base=det)
        if not admitted:
            # §6: a key that moves nothing is not printed as a flat curve; it
            # is not a candidate. Absence is the ruled answer here, not a
            # refusal — the flat curve is what must never appear.
            continue
        gate = reversal_gate(raw, key, hi, paths=gate_paths, simulate=simulate)
        common = {
            "key": key, "option": option,
            # The STATED value, never flattened: the schedule is what the axis
            # replaces, so one figure here would erase the trap.
            "stated_formatted": _stated_formatted(raw, key),
            "bracket_low": lo, "bracket_high": hi, "bracket_source": BRACKET_SOURCE,
            "max_path_deviation_over_sd": gate["worst_deviation_over_sd"],
            "references": _axis_references(key),
            "path_note": flattened_path_note(raw, key),
        }
        if not gate["licensed"]:
            # Unreachable for a financing-leg key on a correct engine —
            # `_financing_pv` shifts every path by one constant — so arriving
            # here means the licence evidence failed and the row exists to say
            # so by name rather than vanish. Slice 1 refuses rather than
            # estimating (§6), so the row carries no boundary at all.
            estimated.append(EstimatedReversal(
                **{k: v for k, v in common.items() if k != "references"},
                references=common["references"],
                boundaries=(),
                refused_boundaries=tuple(
                    RefusedBoundary(verdict_field=field, reason=gate["why"])
                    for field in BOUNDARY_FIELDS)))
            continue
        boundaries, refused = _confirmed_boundaries(
            raw, key, options, det, mc, stated, lo, hi, paths=paths,
            scan_points=scan_points, simulate=simulate, iterations=iterations)
        exact.append(ExactReversal(
            **common, probe_paths=gate["paths"],
            boundaries=tuple(boundaries), refused_boundaries=tuple(refused)))
        zeros.append(_stated_path_zero(raw, key, option))

    zeros.extend(_other_structural_zeros(raw, spec))
    return ReversalRegister(exact=tuple(exact), estimated=tuple(estimated),
                            structural_zeros=tuple(zeros))


def _stated_formatted(raw: Dict[str, Any], key: str) -> str:
    value = base_value(raw, key)
    if isinstance(value, list):
        return ", ".join(_fmt_value(key, float(item)) for item in value)
    return _fmt_value(key, float(value))


def _axis_references(key: str) -> Tuple[AxisReference, ...]:
    """The published figures that sit on this axis, so a solved rate has
    something cited to be read against."""
    if key.rsplit(".", 1)[-1] not in ("mortgage_rate", "mortgage_renewal_rates"):
        return ()
    out: List[AxisReference] = []
    for name in _RATE_AXIS_ANCHORS:
        anchor = ANCHORS.get(name)
        if anchor is None:
            continue
        out.append(AxisReference(
            label=name.rsplit(".", 1)[-1].replace("_", " "), value=anchor.value,
            formatted=_fmt_value(key, float(anchor.value)), anchor=name,
            note=("a list price, to bracket a guess from above — never a ceiling on a "
                  "renewal years from now" if name.endswith("posted_5y") else None)))
    return tuple(out)


def _confirmed_boundaries(
    raw: Dict[str, Any], key: str, options: Sequence[str],
    det: ComparisonDeterministicResult, mc: ComparisonMonteCarloResult,
    stated: Verdict, lo: float, hi: float, *,
    paths: int, scan_points: int,
    simulate: Callable[[ComparisonSpec], ComparisonMonteCarloResult], iterations: int,
) -> Tuple[List[Boundary], List[RefusedBoundary]]:
    """Every one of `BOUNDARY_FIELDS` answered: a `Boundary` where one exists
    and was confirmed, a `RefusedBoundary` naming why everywhere else.

    Each reported boundary is confirmed by ONE FULL RE-SIMULATION at the solved
    value, compared against the free curve's own probabilities at that same
    value. A boundary of a futures field is additionally required to be
    identified outside Monte Carlo noise before it is confirmed at all —
    re-simulating an unidentified boundary would dress noise in a measurement.
    """
    free = _free_curve(raw, key, options, det, mc, single_path=False)
    solved = deterministic_boundaries(raw, key, lo, hi, base=det, iterations=iterations)
    per_field: Dict[str, Tuple[List[Dict[str, Any]], Optional[str]]] = {}
    for field in _DETERMINISTIC_FIELDS:
        found = [b for b in solved["boundaries"] if b["attribute"] == field]
        if found:
            per_field[field] = (found, None)
        else:
            anomaly = next((a for a in solved["anomalies"] if a["attribute"] == field), None)
            unchanged = next((u for u in solved["unchanged"] if u["attribute"] == field), None)
            per_field[field] = ([], anomaly["why"] if anomaly is not None else (
                f"{field} is {unchanged['value']!r} at every point of "
                f"{_fmt_value(key, lo)}–{_fmt_value(key, hi)}, so no boundary of it lies in "
                f"the range this axis searches"
                if unchanged is not None else
                "no pair of options crosses in this bracket, so no boundary exists to solve"))
    for field in _FUTURES_FIELDS:
        per_field[field] = _futures_field_boundaries(
            raw, key, field, free, stated, lo, hi, scan_points=scan_points)

    reported: List[Boundary] = []
    refused: List[RefusedBoundary] = []
    for field in BOUNDARY_FIELDS:
        found, reason = per_field.get(field, ([], "this field was not solved for"))
        if reason is not None:
            refused.append(RefusedBoundary(verdict_field=field, reason=reason))
            continue
        for entry in found:
            value = entry["value"]
            curve = free(value)[1]
            if field in _FUTURES_FIELDS:
                identified = _identification(
                    field, entry,
                    {"lo": free(lo)[1], "hi": free(hi)[1], "at": curve}, stated.best, paths)
                if not identified["identified"]:
                    refused.append(RefusedBoundary(verdict_field=field,
                                                   reason=identified["why"]))
                    continue
            confirming = simulate(load_at(raw, key, value))
            confirmed = {name: getattr(confirming, f"prob_{name}_cheapest")
                         for name in ("condo", "house", "rent")}
            if confirmed != curve:
                refused.append(RefusedBoundary(verdict_field=field, reason=(
                    f"the re-simulation at {_fmt_value(key, value)} disagrees with the free "
                    f"curve (free {curve}, re-simulated {confirmed}) — the shift this boundary "
                    f"rests on is not exact after all, so it is withheld")))
                continue
            reported.append(Boundary(
                verdict_field=field, value=value,
                was=str(entry["from"]), becomes=str(entry["to"]),
                curve_probabilities=_probability_pairs(curve),
                confirming_probabilities=_probability_pairs(confirmed)))
    reported.sort(key=lambda b: (BOUNDARY_FIELDS.index(b.verdict_field), b.value))
    return reported, refused
