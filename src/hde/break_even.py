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
from .config import load_config_dict
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
    way. Raises ValueError when the config prices more or fewer than two
    options, or when the key is not in the YAML and no bracket was given.
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

    cache: Dict[float, Tuple[float, float]] = {}

    def totals(v: float) -> Tuple[float, float]:
        vv = int(round(v)) if is_int else float(v)
        if vv not in cache:
            det = compute_deterministic(load_config_dict(with_value(raw, key, vv)))
            cache[vv] = (getattr(det, a).total_pv, getattr(det, b).total_pv)
        return cache[vv]

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

    n = 9 if not is_int else max(2, min(9, int(hi - lo) + 1))
    xs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    ys = [gap(x) for x in xs]
    crossings: List[Tuple[float, float]] = []
    for i in range(1, n):
        if ys[i - 1] == 0.0:
            crossings.append((xs[i - 1], xs[i - 1]))
        elif ys[i - 1] * ys[i] < 0:
            crossings.append((xs[i - 1], xs[i]))

    break_evens: List[Dict[str, Any]] = []
    for x0, x1 in crossings:
        v = x0 if x0 == x1 else bisect(gap, x0, x1)
        below, above = (a, b) if gap(x0) < 0 else (b, a)  # gap<0 ⇒ A cheaper
        if x0 == x1:
            below, above = (a, b) if gap(min(x1 + 1e-9 * max(1.0, abs(x1)), hi)) > 0 else (b, a)
        # Tie-band edges: where |frac| == band on each side of the crossing.
        def edge(side_lo: float, side_hi: float, target: float) -> Optional[float]:
            g = lambda x: frac(x) - target  # noqa: E731
            if (g(side_lo) < 0) == (g(side_hi) < 0):
                return None
            return bisect(g, side_lo, side_hi)
        s_lo, s_hi = frac(lo), frac(hi)
        left = edge(lo, v, band if s_lo > 0 else -band)
        right = edge(v, hi, band if s_hi > 0 else -band)
        if is_int:
            # An integer input is a step function: report the first value where
            # the above-side option is cheaper, and integer band edges.
            first_above = int(math.ceil(v - 1e-9))
            if gap(first_above) == 0.0 or ((gap(first_above) < 0) == (a == below)):
                first_above += 1
            break_evens.append({
                "value": first_above, "last_value_below": first_above - 1,
                "cheaper_below": below, "cheaper_above": above,
                "tie_band": [None if left is None else int(math.floor(left)),
                             None if right is None else int(math.ceil(right))],
            })
        else:
            break_evens.append({
                "value": v,
                "cheaper_below": below, "cheaper_above": above,
                "tie_band": [left, right],
            })
    out: Dict[str, Any] = {
        "key": key, "options": [a, b], "bracket": [lo, hi], "base_value": base,
        "tie_band_fraction": band, "break_evens": break_evens,
    }
    if not break_evens:
        out["cheaper_throughout"] = a if ys[0] < 0 else b
    return out


def format_break_even(result: Dict[str, Any]) -> str:
    key = result["key"]
    a, b = result["options"]
    lo, hi = result["bracket"]
    lines = [f"\nBreak-even {key} between {a} and {b} (deterministic line; bracket searched "
             f"{_fmt_value(key, lo)}–{_fmt_value(key, hi)}; every other input held at its base value):"]
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
