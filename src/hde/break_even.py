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
            found.append({"sentence": _band_sentence(key, entry, band), **entry})
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
    if "market_scenario" in raw:
        out["note"] = ("deterministic line: the market_scenario prior does not move this threshold "
                       "(its drift enters the Monte Carlo only) — sweep value_growth_rate for the "
                       "threshold's growth sensitivity; read the sweep's decisive flags for the prior's")
    if refused:
        out["refused"] = {"count": len(refused), "values": [r[0] for r in refused],
                          "reason": refused[0][1]}
    if not break_evens:
        out["cheaper_throughout"] = a if (first_gap or 0.0) < 0 else b
    return out


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


def _band_sentence(key: str, be: Dict[str, Any], band: float) -> str:
    """The threshold as the user should read it: band-first, the edges named.
    "rent is cheaper below 2,537; too close to call between 2,537 and 2,797;
    house is cheaper above 2,797 (crossing 2,663; band = 5% of the cheaper PV)"."""
    left, right = be["tie_band"]
    if "last_value_below" in be:
        # Integer input (a step function): whole values on each side of the band.
        up_to = f"{key}={left - 1}" if left is not None else "the bracket's low end"
        from_ = f"{key}={right + 1}" if right is not None else "the bracket's high end"
        band_txt = (f"from {key}={left} to {key}={right}" if left is not None and right is not None
                    else f"between {up_to} and {from_}")
        return (
            f"{be['cheaper_below']} is cheaper up to {up_to}; too close to call {band_txt}; "
            f"{be['cheaper_above']} is cheaper from {from_} "
            f"({be['cheaper_above']} first cheaper at {key}={be['value']}; band = {band:.0%} of the cheaper option's PV)"
        )
    lo_txt = _fmt_value(key, left) if left is not None else "the bracket's low end"
    hi_txt = _fmt_value(key, right) if right is not None else "the bracket's high end"
    return (
        f"{be['cheaper_below']} is cheaper below {lo_txt}; too close to call between {lo_txt} and "
        f"{hi_txt}; {be['cheaper_above']} is cheaper above {hi_txt} "
        f"(crossing {_fmt_value(key, be['value'])}; band = {band:.0%} of the cheaper option's PV)"
    )


def _threshold_sentences(key: str, result_like: Dict[str, Any], band: float) -> List[str]:
    """The threshold in words, one sentence per crossing (or the no-crossing line)."""
    if not result_like["break_evens"]:
        return [f"no crossing in the bracket: {result_like['cheaper_throughout']} is cheaper throughout"]
    return [be.get("sentence") or _band_sentence(key, be, band) for be in result_like["break_evens"]]


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
    for across in result.get("across", []):
        skey = across["key"]
        lines.append(f"  across {skey} (the threshold re-solved at each value):")
        for row in across["rows"]:
            sentences = _threshold_sentences(key, row, band)
            if row.get("refused"):
                sentences.append(f"config refuses {row['refused']['count']} point(s) ({row['refused']['reason']})")
            lines.append(f"    {skey}={_fmt_value(skey, row['value'])}: " + "; ".join(sentences))
    return "\n".join(lines)
