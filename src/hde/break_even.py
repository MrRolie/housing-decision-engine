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
from .sweep import INT_KEYS, _fmt_value, with_value

# Inputs whose default bracket is [¼·base, 4·base]; anything else needs lo:hi.
_MONEY_KEYS = frozenset({
    "monthly_rent", "initial_value", "down_payment", "purchase_costs",
    "financed_purchase_costs", "monthly_fee", "invested_down_payment", "annual_income",
})


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


def solve_break_even(
    raw: Dict[str, Any], key: str, lo: Optional[float] = None, hi: Optional[float] = None,
    *, iterations: int = 60,
) -> Dict[str, Any]:
    """
    Bisection on gap(v) = total_pv(A) − total_pv(B) for the two priced options
    (A, B in the order condo, house, rent). A coarse scan of the bracket finds
    every sign change (the gap need not be monotone in the input); each is
    refined by bisection, and the tie-band edges around it are solved the same
    way, walking outward from the crossing one grid cell at a time (a second
    crossing ends the band: that edge is None). Grid points the loader refuses
    (a price below the fixed down payment) are recorded under "refused" and
    the search shrinks to the accepted run(s), reported as "searched". Raises
    ValueError when the config prices more or fewer than two options, when the
    key is not in the YAML and no bracket was given, or when every point of
    the bracket is refused.
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
        if base is None or field not in _MONEY_KEYS:
            raise ValueError(
                f"--break-even {key}: give the bracket as {key}=lo:hi "
                f"({'the key is not in the YAML' if base is None else 'only money inputs get a default bracket'})"
            )
        lo, hi = 0.25 * float(base), 4.0 * float(base)
    is_int = key in INT_KEYS
    band = ANCHORS["verdict.tie_band"].value

    cache: Dict[float, Optional[Tuple[float, float]]] = {}
    refused: List[Tuple[float, str]] = []

    def totals_or_none(v: float) -> Optional[Tuple[float, float]]:
        """The two totals at v, or None when the loader refuses that value (a
        price below the fixed down payment, a rate outside its bounds): the
        refusal is recorded, never raised — the search shrinks to what the
        config accepts and the output says so."""
        vv = int(round(v)) if is_int else float(v)
        if vv not in cache:
            try:
                det = compute_deterministic(load_config_dict(with_value(raw, key, vv)))
            except (ConfigValidationError, ValueError) as e:
                cache[vv] = None
                refused.append((vv, str(e).strip().splitlines()[-1].strip()))
            else:
                cache[vv] = (getattr(det, a).total_pv, getattr(det, b).total_pv)
        return cache[vv]

    def totals(v: float) -> Tuple[float, float]:
        t = totals_or_none(v)
        if t is None:
            raise ValueError(
                f"--break-even {key}: the loader refused {_fmt_value(key, v)} inside a bracket "
                f"whose ends it accepted ({refused[-1][1]}) — give a bracket the config accepts (KEY=lo:hi)"
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
                found.append({
                    "value": first_above, "last_value_below": first_above - 1,
                    "cheaper_below": below, "cheaper_above": above,
                    "tie_band": [None if left is None else int(math.floor(left)),
                                 None if right is None else int(math.ceil(right))],
                })
            else:
                found.append({
                    "value": v,
                    "cheaper_below": below, "cheaper_above": above,
                    "tie_band": [left, right],
                })
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
        raise ValueError(
            f"--break-even {key}: the loader refused every point in the bracket "
            f"{_fmt_value(key, lo)}–{_fmt_value(key, hi)} ({refused[0][1]}) — "
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
        "base_value": base, "tie_band_fraction": band, "break_evens": break_evens,
    }
    if refused:
        out["refused"] = {"count": len(refused), "values": [r[0] for r in refused],
                          "reason": refused[0][1]}
    if not break_evens:
        out["cheaper_throughout"] = a if (first_gap or 0.0) < 0 else b
    return out


def format_break_even(result: Dict[str, Any]) -> str:
    key = result["key"]
    a, b = result["options"]
    lo, hi = result["bracket"]
    lines = [f"\nBreak-even {key} between {a} and {b} (deterministic line; bracket "
             f"{_fmt_value(key, lo)}–{_fmt_value(key, hi)}; every other input held at its base value):"]
    if result.get("refused"):
        r = result["refused"]
        span = ", ".join(f"{_fmt_value(key, s0)}–{_fmt_value(key, s1)}" for s0, s1 in result["searched"])
        lines.append(f"  the config refuses {r['count']} point(s) of that bracket ({r['reason']}); searched {span}")
    if not result["break_evens"]:
        lines.append(f"  no crossing in the bracket: {result['cheaper_throughout']} is cheaper throughout")
        return "\n".join(lines)
    for be in result["break_evens"]:
        left, right = be["tie_band"]
        band_txt = (
            f"too close to call between {_fmt_value(key, left) if left is not None else 'below the bracket'} "
            f"and {_fmt_value(key, right) if right is not None else 'above the bracket'} "
            f"({result['tie_band_fraction']:.0%} of the cheaper option's PV)"
        )
        if "last_value_below" in be:
            lines.append(
                f"  {be['cheaper_below']} is cheaper up to {key}={be['last_value_below']}, "
                f"{be['cheaper_above']} is cheaper from {key}={be['value']}; {band_txt}"
            )
        else:
            lines.append(
                f"  {_fmt_value(key, be['value'])}: {be['cheaper_below']} is cheaper below, "
                f"{be['cheaper_above']} is cheaper above; {band_txt}"
            )
    return "\n".join(lines)
