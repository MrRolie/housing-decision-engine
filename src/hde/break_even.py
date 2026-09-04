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
from .config import ConfigValidationError, load_config_dict
from .deterministic import compute_deterministic
from .market_scenario import (LoadedScenarioPrior, band_horizon_for_calendar_year,
                              calendar_year_for_sim_year)
from .sweep import (INT_KEYS, _fmt_value, affordability_of, join_notes,
                    price_scan_note, with_value)

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


def _raw_value(raw: Dict[str, Any], key: str) -> Optional[Any]:
    parts = key.split(".")
    if len(parts) == 2 and parts[0] == "simulation" and parts[1] in ("years", "discount_rate"):
        parts = [parts[1]]
    node: Any = raw
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


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
            found.append({"sentence": band_sentence(key, entry, band), **entry})
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
    for run in runs:
        r_lo, r_hi = run[0], run[-1]
        rxs, rys = (xs, ys) if (r_lo, r_hi) == (lo, hi) else scan(r_lo, r_hi)
        searched.append([r_lo, r_hi])
        if first_gap is None:
            first_gap = next((y for y in rys if y is not None), None)
        break_evens.extend(solve_run(rxs, rys))

    out: Dict[str, Any] = {
        "key": key, "options": [a, b], "bracket": [lo, hi], "searched": searched,
        "tie_band_fraction": band, "break_evens": break_evens,
    }
    if not break_evens:
        out["cheaper_throughout"] = a if (first_gap or 0.0) < 0 else b
    return out


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
            det = compute_deterministic(load_config_dict(with_value(raw, key, v)))
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
    if "cheaper_throughout" in core:
        out["cheaper_throughout"] = core["cheaper_throughout"]
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
        spec = load_config_dict(with_value(raw, key, value))
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
    """One side of a crossing, in words: insured (with its tier and the loan it
    is priced on), uninsured, or carrying no derived record at all."""
    if side is None:
        return "without a derived insurance record"
    required, _label, rate = side["tier"]
    if not required:
        return f"uninsured ({side['ltv']:.2%} loan-to-value)"
    return (f"insured ({side['ltv']:.2%} loan-to-value, {rate:.2%} premium on the loan)")


def cliff_note(
    raw: Dict[str, Any], key: str, entries: List[Dict[str, Any]],
) -> Optional[str]:
    """A crossing that is a STEP, not a meeting: the two sides of it price a
    different mortgage (the 20%-down line crossed, an insurance tier changed) or
    one side is refused outright.

    2026-09-04 review: a $651,163 "crossing" was exactly cash ÷ 0.215 — the
    house won by $3,076 a hundred dollars below it and lost by $10,902 a hundred
    above, because the premium switched on. Read as a smooth crossing, the tie
    band around it says "these are near-ties"; it is the width of a jump.
    """
    clauses: List[str] = []
    for entry in entries:
        value = entry["value"]
        if "last_value_below" in entry:  # integer input: the two whole values
            below_v, above_v = entry["last_value_below"], value
        else:
            step = max(abs(float(value)), 1.0) * 1e-6
            below_v, above_v = float(value) - step, float(value) + step
        ok_below, below = _financing_regime(raw, key, below_v)
        ok_above, above = _financing_regime(raw, key, above_v)
        at = _fmt_value(key, value)
        if not ok_below or not ok_above:
            side, reason = ("below", below) if not ok_below else ("above", above)
            clauses.append(f"the crossing at {at} sits on the edge of what the config accepts: "
                           f"values just {side} it are refused ({reason}), so the band around it "
                           f"is bounded by the refusal, not by near-ties")
            continue
        for name in sorted(set(below) & set(above)):
            was, now = below[name], above[name]
            was_tier = None if was is None else was["tier"]
            now_tier = None if now is None else now["tier"]
            if was_tier == now_tier:
                continue  # the same mortgage on both sides: the costs really do meet
            insured_below = bool(was_tier and was_tier[0])
            insured_above = bool(now_tier and now_tier[0])
            if insured_below != insured_above:
                clauses.append(
                    f"the crossing at {at} is the mortgage-insurance cliff — {name} is "
                    f"{_regime_state(was)} just below it and {_regime_state(now)} just above, "
                    f"so the 20%-down line falls there and the premium switches on: not a "
                    f"smooth cost crossing, and the tie band around it is the cliff's width, "
                    f"not a range of near-ties")
            else:
                clauses.append(
                    f"the crossing at {at} is a mortgage-insurance tier change for {name} "
                    f"({was_tier[2]:.2%} → {now_tier[2]:.2%} of the loan), not a smooth cost "
                    f"crossing: the tie band around it is the step's width, not a range of "
                    f"near-ties")
    return "; ".join(clauses) if clauses else None


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
            det = compute_deterministic(load_config_dict(with_value(raw, key, value)))
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
        for carried in ("cheaper_throughout", "refused"):
            if carried in r:
                row[carried] = r[carried]
        rows.append(row)
    return {"key": sweep_key, "rows": rows}


def band_sentence(
    key: str, be: Dict[str, Any], band: float,
    *,
    fmt: Optional[Callable[[float], str]] = None,
    label: Optional[Callable[[str], str]] = None,
) -> str:
    """The threshold as the user should read it: band-first, the edges named.
    "rent is cheaper below 2,537; too close to call between 2,537 and 2,797;
    house is cheaper above 2,797 (crossing 2,663; band = 5% of the cheaper PV)".

    ``fmt`` renders one value and ``label`` one option name; both default to the
    CLI's own rendering. The story's act 6 passes "$2,663/mo" and "buying a
    house" — one grammar, so the drawn crossing and the reported one read the
    same, in each surface's own units.
    """
    show = fmt or (lambda v: _fmt_value(key, v))
    name = label or (lambda option: option)
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
            f"({name(be['cheaper_above'])} first cheaper at {key}={be['value']}; band = {band:.0%} of the cheaper option's PV)"
        )
    lo_txt = show(left) if left is not None else "the bracket's low end"
    hi_txt = show(right) if right is not None else "the bracket's high end"
    return (
        f"{name(be['cheaper_below'])} is cheaper below {lo_txt}; too close to call between {lo_txt} and "
        f"{hi_txt}; {name(be['cheaper_above'])} is cheaper above {hi_txt} "
        f"(crossing {show(be['value'])}; band = {band:.0%} of the cheaper option's PV)"
    )


def _threshold_sentences(key: str, result_like: Dict[str, Any], band: float) -> List[str]:
    """The threshold in words, one sentence per crossing (or the no-crossing line)."""
    if not result_like["break_evens"]:
        return [f"no crossing in the bracket: {result_like['cheaper_throughout']} is cheaper throughout"]
    return [be.get("sentence") or band_sentence(key, be, band) for be in result_like["break_evens"]]


def _affordability_lines(key: str, be: Dict[str, Any]) -> List[str]:
    """What the threshold and its band edges cost against income — the lines a
    "cheaper on average" answer needs beside the crossing it quotes."""
    aff = be.get("affordability")
    if not aff:
        return []
    threshold = aff.get("threshold")
    head = "affordability at the crossing and the band edges (highest cost/income ratio"
    head += f"; years above the {threshold:.0%} threshold):" if threshold is not None else "):"
    lines = [head]
    lo, hi = be["tie_band"]
    points = [("at the crossing", be["value"], aff["value"]),
              ("at the band's low edge", lo, aff["tie_band"][0]),
              ("at the band's high edge", hi, aff["tie_band"][1])]
    for label, value, per_option in points:
        if per_option is None or value is None:
            continue
        parts = ", ".join(
            f"{option} {per_option[option]['max_ratio']:.1%}"
            f" ({len(per_option[option]['years_exceeding'])} yr(s) over)"
            for option in ("condo", "house", "rent") if option in per_option
        )
        lines.append(f"  {label} {_fmt_value(key, value)}: {parts}")
    return lines


def format_break_even(result: Dict[str, Any]) -> str:
    key = result["key"]
    a, b = result["options"]
    lo, hi = result["bracket"]
    band = result["tie_band_fraction"]
    lines = [f"\nBreak-even {key} between {a} and {b} (deterministic line — a market_scenario prior "
             f"does not move it; bracket {_fmt_value(key, lo)}–{_fmt_value(key, hi)}; every other input "
             f"held at its base value):"]
    if result.get("note"):
        lines.append(f"  {result['note']}")
    if result.get("refused"):
        r = result["refused"]
        span = ", ".join(f"{_fmt_value(key, s0)}–{_fmt_value(key, s1)}" for s0, s1 in result["searched"])
        lines.append(f"  the config refuses {r['count']} point(s) of that bracket ({r['reason']}); searched {span}")
    lines.extend(f"  {t}" for t in _threshold_sentences(key, result, band))
    for be in result["break_evens"]:
        lines.extend(f"  {t}" for t in _affordability_lines(key, be))
    # `across` rows keep their one-line shape; their affordability rides --json.
    for across in result.get("across", []):
        skey = across["key"]
        lines.append(f"  across {skey} (the threshold re-solved at each value):")
        for row in across["rows"]:
            sentences = _threshold_sentences(key, row, band)
            if row.get("refused"):
                sentences.append(f"config refuses {row['refused']['count']} point(s) ({row['refused']['reason']})")
            lines.append(f"    {skey}={_fmt_value(skey, row['value'])}: " + "; ".join(sentences))
    return "\n".join(lines)
