"""Parameter sweeps — the flip point on ANY input (2026-09-02, user-model dogfood).

Every persona's assistant hand-rolled sed loops over throwaway YAML copies to
find where the verdict flips on horizon, growth or price. This does it once,
through the same loader (so every point is validated and echoes its defaults)
and the same verdict rule as the main run.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

import numpy as np

from .config import ConfigValidationError, load_config_dict
from .config import single_path_run
from .deterministic import compute_deterministic
from .models import compute_verdict
from .monte_carlo import run_monte_carlo
from .serialization import mc_to_dict

# Inputs the parser reads as integers.
INT_KEYS = frozenset({
    "years", "simulation.years", "simulation.num_sims", "simulation.random_seed",
    "condo.mortgage_term_years", "house.mortgage_term_years",
})
# Keys that live at the YAML top level even when addressed through simulation.*
_TOP_LEVEL = {"years", "discount_rate"}


def parse_sweep(arg: str) -> Tuple[str, List[Any]]:
    """'KEY=v1,v2,...' or 'KEY=start:stop:n' -> (key, values)."""
    key, sep, spec = arg.partition("=")
    key, spec = key.strip(), spec.strip()
    if not sep or not key or not spec:
        raise ValueError(f"--sweep expects KEY=v1,v2,... or KEY=start:stop:n, got {arg!r}")
    if ":" in spec:
        parts = spec.split(":")
        if len(parts) != 3:
            raise ValueError(f"--sweep range form is start:stop:n, got {spec!r}")
        start, stop, n = float(parts[0]), float(parts[1]), int(parts[2])
        if n < 2:
            raise ValueError("--sweep range needs n >= 2 points")
        values: List[Any] = [float(x) for x in np.linspace(start, stop, n)]
    else:
        values = [float(x) for x in spec.split(",") if x.strip()]
    if not values:
        raise ValueError(f"--sweep {key}: no values")
    if key in INT_KEYS:
        values = [int(round(v)) for v in values]
    return key, values


def with_value(raw: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
    """A deep copy of the raw YAML mapping with one dotted key set."""
    doc = copy.deepcopy(raw)
    parts = key.split(".")
    if len(parts) == 2 and parts[0] == "simulation" and parts[1] in _TOP_LEVEL:
        parts = [parts[1]]
    node: Any = doc
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise ValueError(f"cannot sweep {key}: {part} is not a mapping")
    node[parts[-1]] = value
    return doc


def run_sweep(raw: Dict[str, Any], key: str, values: List[Any], *, monte_carlo: bool = True) -> Dict[str, Any]:
    """Re-run the comparison at each value; rows carry per-option totals and the
    shared verdict; flips mark consecutive points whose cheapest option differs."""
    rows: List[Dict[str, Any]] = []
    for v in values:
        try:
            spec = load_config_dict(with_value(raw, key, v))
        except (ConfigValidationError, ValueError) as e:
            rows.append({"value": v, "error": str(e).splitlines()[-1]})
            continue
        det = compute_deterministic(spec)
        single = single_path_run(spec)
        mc = run_monte_carlo(spec) if (monte_carlo and not single) else None
        verdict = compute_verdict(det, mc, years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate, single_path=single)
        rows.append({
            "value": v,
            "totals": {k: getattr(det, k).total_pv for k in ("condo", "house", "rent")
                       if getattr(det, k) is not None},
            "best": verdict.best, "runner_up": verdict.runner_up,
            "margin_pv": verdict.margin_pv, "margin_frac": verdict.margin_frac,
            "decisive": verdict.decisive, "prob_best": verdict.prob_best,
            "mc_mean_best": verdict.mc_mean_best, "reason": verdict.reason,
            "monte_carlo": (
                {k: v for k, v in mc_to_dict(mc).items() if k in ("condo", "house", "rent") and v is not None}
                if mc is not None else None
            ),
        })
    flips: List[Dict[str, Any]] = []
    prev = None
    for row in rows:
        if "error" in row:
            prev = None
            continue
        if prev is not None and row["best"] != prev["best"]:
            flips.append({"from_value": prev["value"], "from_best": prev["best"],
                          "to_value": row["value"], "to_best": row["best"]})
        prev = row
    return {"key": key, "values": values, "rows": rows, "flips": flips}


def _fmt_value(key: str, v: Any) -> str:
    if key in INT_KEYS or isinstance(v, int):
        return str(v)
    return f"{v:.2%}" if abs(v) < 1 else f"{v:,.0f}"


def format_sweep(result: Dict[str, Any]) -> str:
    key, rows = result["key"], result["rows"]
    opts = [o for o in ("condo", "house", "rent") if any(o in r.get("totals", {}) for r in rows)]
    lines = [f"\nSweep {key} ({len(rows)} points; every other input held at its base value — "
             f"a joint question needs a second --sweep on the edited config; per-point Monte Carlo "
             f"percentiles ride --json):"]
    head = f"  {key:>{max(len(key), 10)}} | " + " | ".join(f"{o.capitalize():>12}" for o in opts) + " | cheapest | margin vs runner-up | decisive | P(best) | MC-mean best"
    lines.append(head)
    for r in rows:
        val = _fmt_value(key, r["value"])
        if "error" in r:
            lines.append(f"  {val:>{max(len(key), 10)}} | refused: {r['error']}")
            continue
        totals = " | ".join(f"${r['totals'][o]:>11,.0f}" for o in opts)
        prob = f"{r['prob_best']:.0%}" if r["prob_best"] is not None else "n/a"
        mean_best = r.get("mc_mean_best") or "n/a"
        lines.append(
            f"  {val:>{max(len(key), 10)}} | {totals} | {r['best']:>8} | "
            f"${r['margin_pv']:>11,.0f} ({r['margin_frac']:.1%}) | {str(r['decisive']):>8} | {prob:>7} | {mean_best:>12}"
        )
    if result["flips"]:
        for f in result["flips"]:
            lines.append(
                f"  flip: cheapest changes from {f['from_best']} ({key}={_fmt_value(key, f['from_value'])}) "
                f"to {f['to_best']} ({key}={_fmt_value(key, f['to_value'])})"
            )
    else:
        lines.append("  no flip: the same option is cheapest across the whole sweep")
    return "\n".join(lines)
