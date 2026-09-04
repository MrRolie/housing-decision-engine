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
from typing import Any, Callable, Dict, List, Optional, Tuple

from .anchors import ANCHORS
from .config import ConfigValidationError
from .deterministic import compute_deterministic
from .market_scenario import (LoadedScenarioPrior, band_horizon_for_calendar_year,
                              calendar_year_for_sim_year)
from .sweep import (INT_KEYS, _fmt_value, affordability_of, base_value, constant_options,
                    join_notes, load_at, price_scan_note, with_value)

# The default bracket for a money input, as multiples of its base value; any
# other key needs lo:hi. The story's act 6 solves the rent threshold on this
# same bracket, so the act and `--break-even rent.monthly_rent` search alike.
MONEY_BRACKET = (0.25, 4.0)
_MONEY_KEYS = frozenset({
    "monthly_rent", "initial_value", "down_payment", "cash_available", "purchase_costs",
    "financed_purchase_costs", "monthly_fee", "invested_down_payment", "annual_income",
})

# A rate has no natural multiple of itself (0% growth × 4 is still 0%), so its
# default bracket is absolute: the plausible range for that rate, wide enough to
# hold the crossing and narrow enough that every point loads. 2026-09-03 review:
# `--break-even condo.value_growth_rate` refused with "only money inputs get a
# default bracket", and the threshold question users actually ask about growth
# needed a bracket they had no way to guess. The bracket used is always printed.
RATE_BRACKETS: Dict[str, Tuple[float, float]] = {
    "value_growth_rate": (-0.02, 0.05),        # real: a shrinking market to a hot one
    "rent_escalation_rate": (-0.01, 0.05),     # real shelter-cost growth
    "annual_maintenance_rate": (0.0, 0.03),    # nothing modelled to a high-upkeep house
    "mortgage_rate": (0.01, 0.10),             # effective annual, two decades of Canadian rates
    "discount_rate": (0.0, 0.08),              # the loader refuses outside [0, 15%]
}


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
            # Band-first, and FIRST in the entry: three dogfood serves copied the
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
    """
    lo, hi = searched[0][0], searched[-1][1]
    side = "high" if abs(gap_hi) < abs(gap_lo) else "low"
    width = hi - lo
    open_end = (hi == asked[1]) if side == "high" else (lo == asked[0])
    widen: Optional[List[float]] = None
    if open_end and width > 0:
        if side == "high":
            widen = [lo, hi + width]
        else:
            new_lo = lo - width
            if lo > 0:
                new_lo = max(new_lo, lo / 2)
            if is_int:
                new_lo = max(1.0, float(math.floor(new_lo)))
            widen = [new_lo, hi]
    return {"lo": lo, "hi": hi, "cheaper": cheaper, "narrows_toward": side, "widen": widen}


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
            raise ValueError(
                f"--break-even {key}: give the bracket as {key}=lo:hi "
                f"({'the key is not in the YAML' if base is None else 'only money and rate inputs get a default bracket'})"
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
    for entry in core["break_evens"]:
        entry["affordability"] = _affordability_at(raw, key, entry)

    out: Dict[str, Any] = {
        "key": key, "options": [a, b], "bracket": [lo, hi], "searched": core["searched"],
        "base_value": base, "tie_band_fraction": core["tie_band_fraction"],
        "break_evens": core["break_evens"],
    }
    prior_note = None
    if "market_scenario" in raw:
        prior_note = ("deterministic line: the market_scenario prior does not move this threshold "
                      "(its drift enters the Monte Carlo only) — sweep value_growth_rate for the "
                      "threshold's growth sensitivity; read the sweep's decisive flags for the prior's")
    note = join_notes(
        prior_note,
        prior_band_note(key, horizon_drift(raw, key, prior), core["break_evens"]),
        cliff_note(raw, key, core["break_evens"]),
        price_scan_note(raw, key),
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
) -> Dict[int, float]:
    """The prior's reference REAL drift per horizon band the run touches, for
    the owned option a `<owned>.value_growth_rate` threshold is solved on.

    Empty for every other key, without a prior, or when the prior carries no
    reference scenario for this dwelling type — an absent band is reported by
    saying nothing, never by guessing a rate.
    """
    option, _, field = key.rpartition(".")
    if prior is None or field != "value_growth_rate" or option not in ("condo", "house"):
        return {}
    years = _raw_value(raw, "years")
    if not isinstance(years, (int, float)) or years < 1:
        return {}
    encoded = prior.encoded_drift()
    entry = encoded.get(option) or encoded.get("all")
    if entry is None:
        return {}
    reference: Dict[int, float] = entry["reference_by_band"]  # type: ignore[assignment]
    touched = sorted({band_horizon_for_calendar_year(calendar_year_for_sim_year(y))
                      for y in range(1, int(years) + 1)})
    return {band: reference[band] for band in touched if band in reference}


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
    key: str, drifts: Dict[int, float], entries: List[Dict[str, Any]],
) -> Optional[str]:
    """Where the prior's own drift sits against the tie band this threshold
    reports — INSIDE (the prior does not settle the question), BELOW or ABOVE
    (it points at one side).

    Three reviewed answers assembled this comparison by hand from two separate
    outputs. It is a comparison of the drift READ AS A GROWTH LEVEL: the Monte
    Carlo adds the drift to `value_growth_rate` rather than replacing it, and
    the note says so rather than letting the reader assume either.
    """
    if not drifts or not entries:
        return None
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
                where = f"the prior's drift {values[0]:+.2%}/yr ({bands[0]} band)"
            else:
                listed = ", ".join(str(band) for band in bands)
                where = (f"the prior's drift {min(values):+.2%}…{max(values):+.2%}/yr "
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
    return ("the prior against this threshold — " + "; ".join(clauses)
            + " (the drift is added to value_growth_rate in the Monte Carlo, not substituted "
              "for it; this reads it as a growth level to place it on the same axis)")


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
    Round 5b dogfood: the skill asked for the threshold at both ends of the
    growth bracket and the persona could not produce it — --break-even solved
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
    # can say "(= base)" instead of repeating the base line.
    return {"key": sweep_key, "base_value": base_value(raw, sweep_key), "rows": rows}


def band_rule(band: float) -> str:
    """The tie band's definition, in the words every surface uses."""
    return f"band = {band:.0%} of the cheaper option's PV"


def band_sentence(
    key: str, be: Dict[str, Any], band: float,
    *,
    fmt: Optional[Callable[[float], str]] = None,
    label: Optional[Callable[[str], str]] = None,
    band_clause: bool = True,
) -> str:
    """The threshold as the user should read it: band-first, the edges named.
    "rent is cheaper below 2,537; too close to call between 2,537 and 2,797;
    house is cheaper above 2,797 (crossing 2,663; band = 5% of the cheaper PV)".

    ``fmt`` renders one value and ``label`` one option name; both default to the
    CLI's own rendering. The story's act 6 passes "$2,663/mo" and "buying a
    house" — one grammar, so the drawn crossing and the reported one read the
    same, in each surface's own units. ``band_clause`` keeps the band rule in
    the closing bracket (the story's caption stands alone); the CLI's blocks
    state the rule once, in their header, and pass False.
    """
    show = fmt or (lambda v: _fmt_value(key, v))
    name = label or (lambda option: option)
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
    return (
        f"{name(be['cheaper_below'])} is cheaper below {lo_txt}; too close to call between {lo_txt} and "
        f"{hi_txt}; {name(be['cheaper_above'])} is cheaper above {hi_txt} "
        f"(crossing {show(be['value'])}{rule})"
    )


def threshold_sentences(key: str, result_like: Dict[str, Any], band: float) -> List[str]:
    """The threshold in words, one sentence per crossing (or the no-crossing
    line). One builder for the text block, the read-back and every `across`
    row, so the three cannot phrase the same threshold differently."""
    if not result_like["break_evens"]:
        record = result_like.get("no_crossing")
        if record is None:  # a caller that solved without the record
            return [f"no crossing in the bracket: {result_like['cheaper_throughout']} is cheaper throughout"]
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
    text = f"{sweep_key}={_fmt_value(sweep_key, row['value'])}: " + "; ".join(sentences)
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
        for row in across["rows"]:
            text = across_row_sentence(key, skey, row, band, refused_clause=not refused_once,
                                       drop=drop, head=False)
            prefix = f"{skey}={_fmt_value(skey, row['value'])}: "
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
            lines.append(f"    {across_row_sentence(key, skey, row, band)}")
    return "\n".join(lines)
