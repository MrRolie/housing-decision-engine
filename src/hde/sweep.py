"""Parameter sweeps — the flip point on ANY input (2026-09-02, user-model dogfood).

Every persona's assistant hand-rolled sed loops over throwaway YAML copies to
find where the verdict flips on horizon, growth or price. This does it once,
through the same loader (so every point is validated and echoes its defaults)
and the same verdict rule as the main run.
"""
from __future__ import annotations

import copy
import dataclasses
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .anchors import ANCHORS
from .config import ConfigValidationError, load_config_dict
from .config import single_path_run
from .deterministic import compute_deterministic
from .models import ComparisonDeterministicResult, ComparisonSpec, _against, compute_verdict
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


def dedupe(key: str, values: List[Any]) -> Tuple[List[Any], Optional[str]]:
    """Distinct grid points in the order asked for, and the note when some
    collapsed. `--sweep years=7:8:5` casts to [7, 7, 8, 8, 8]: five rows, three
    of them the same answer, and no hint that the range was finer than the
    input's grain (2026-09-03 review)."""
    seen: List[Any] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    if len(seen) == len(values):
        return seen, None
    why = ("the input takes whole numbers only" if key in INT_KEYS
           else "the same value was asked for more than once")
    return seen, (
        f"{len(values)} requested points collapse to {len(seen)} distinct values — {why}, "
        f"so duplicates were dropped (order kept); widen the range or ask for fewer points"
    )


# Dollar-denominated inputs that are price-proportional in reality: a price scan
# re-derives nothing about them, so they stay sized for the seed price. The
# check reads the RAW YAML, not the parsed spec, so a figure the loader itself
# derived from the price is never flagged.
_PRICE_PROPORTIONAL_DOLLARS = ("purchase_costs", "financed_purchase_costs")
_PROPORTIONAL_COST_NAMES = ("tax", "insurance")


def price_scan_note(raw: Dict[str, Any], key: str) -> Optional[str]:
    """The coherence note for a break-even or sweep that moves an owned
    option's `initial_value` while a price-proportional input is stated in
    dollars — the band it reports moves once those inputs scale (one reviewed
    answer's "buying wins above $346k" moved ~$50k, another's edge $35k)."""
    option, _, field = key.rpartition(".")
    if field != "initial_value" or option not in ("condo", "house"):
        return None
    block = raw.get(option)
    if not isinstance(block, dict) or not block.get("initial_value"):
        return None
    held: List[str] = []
    for dollar_key in _PRICE_PROPORTIONAL_DOLLARS:
        amount = block.get(dollar_key)
        if amount:
            held.append(f"{option}.{dollar_key}=${float(amount):,.0f}")
    for cost in block.get("other_recurring_costs") or []:
        if not isinstance(cost, dict) or not cost.get("annual_amount"):
            continue
        name = str(cost.get("name", ""))
        if any(word in name.lower() for word in _PROPORTIONAL_COST_NAMES):
            held.append(f"{option}.other_recurring_costs[{name}]="
                        f"${float(cost['annual_amount']):,.0f}/yr")
    if not held:
        return None
    return (
        f"held fixed in dollars while the price moves: {', '.join(held)} — sized for "
        f"${float(block['initial_value']):,.0f}, this understates owner costs above it "
        f"(favours buying) and overstates them below (favours renting); use "
        f"property_tax_rate / purchase_costs_rate to scale them"
    )


def base_value(raw: Dict[str, Any], key: str) -> Optional[Any]:
    """The value the raw YAML states for a dotted key (the `simulation.years` /
    `simulation.discount_rate` aliases read the top level), or None."""
    parts = key.split(".")
    if len(parts) == 2 and parts[0] == "simulation" and parts[1] in _TOP_LEVEL:
        parts = [parts[1]]
    node: Any = raw
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def one_sided_sweep_warning(raw: Dict[str, Any], key: str, values: List[Any]) -> Optional[str]:
    """The warning for a sweep over a key the ASSISTANT typed whose grid lies
    entirely above or entirely below the placeholder: one direction of the
    guess is tested and the other is not (2026-09-04 — an Ontario tax
    placeholder swept upward only was read as a sensitivity test). Quiet for a
    user-stated or undeclared key, and for a grid that straddles or touches
    the base value."""
    sources = raw.get("sources")
    parts = key.split(".")
    if len(parts) == 2 and parts[0] == "simulation" and parts[1] in _TOP_LEVEL:
        parts = [parts[1]]
    if not isinstance(sources, dict) or sources.get(".".join(parts)) != "assistant":
        return None
    base = base_value(raw, key)
    if not isinstance(base, (int, float)) or isinstance(base, bool) or not values:
        return None
    if all(v > base for v in values):
        side = "ABOVE"
    elif all(v < base for v in values):
        side = "BELOW"
    else:
        return None
    shown = _fmt_value(key, base if key in INT_KEYS else float(base))  # as the grid prints
    return (f"sweep of {key} covers only values {side} the placeholder "
            f"{shown}; the other direction is untested")


def join_notes(*notes: Optional[str]) -> Optional[str]:
    """The notes a block carries, as one sentence-joined string (or None)."""
    present = [n for n in notes if n]
    return "; ".join(present) if present else None


def affordability_of(det: ComparisonDeterministicResult) -> Optional[Dict[str, Dict[str, Any]]]:
    """Per-option `{max_ratio, years_exceeding}`, or None without an `income`
    block. Round 6: a maintenance bracket moved the affordability ratio from
    34% to 37% in every year and the lane's command could not see it; round 7:
    an answer called a price range "cheaper on average" while the engine's own
    ratios there were above the cap the answer itself quoted."""
    report = det.income_report
    if report is None:
        return None
    return {
        name: {"max_ratio": max(ratios), "years_exceeding": exceeds}
        for name, ratios, exceeds in (
            ("condo", report.condo_ratios, report.years_condo_exceeds),
            ("house", report.house_ratios, report.years_house_exceeds),
            ("rent", report.rent_ratios, report.years_rent_exceeds),
        )
        if ratios
    }


# The source class of a key a sweep or break-even overrode: the grid point's
# value is the scan's, not whoever declared the base value's. `with_value`
# marks the lifted declaration with this and `load_at` relabels the echo —
# the loader itself never sees the marker.
SWEEP_SOURCE = "sweep"


def with_value(raw: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
    """A deep copy of the raw YAML mapping with one dotted key set.

    A `sources:` declaration on that key is marked `sweep`: an `anchor:<name>`
    declaration is validated against the anchor's figure at load time, and a
    scan that moves the key would otherwise be refused at every off-anchor
    point (2026-09-04). The base run still validates it — only the copy a grid
    point loads is relabelled. Load the copy through `load_at`.
    """
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
    sources = doc.get("sources")
    if isinstance(sources, dict) and ".".join(parts) in sources:
        sources[".".join(parts)] = SWEEP_SOURCE
    return doc


def load_at(raw: Dict[str, Any], key: str, value: Any) -> ComparisonSpec:
    """The spec at one grid point: `with_value` and the loader, with every
    declaration a scan lifted echoed as `sweep` rather than re-validated.

    One entry for every scan path (the sweep rows, the threshold solver, its
    cliff and affordability probes), so no path can load the copy raw and
    trip over the marker."""
    doc = with_value(raw, key, value)
    sources = doc.get("sources")
    swept = ([k for k, v in sources.items() if v == SWEEP_SOURCE]
             if isinstance(sources, dict) else [])
    for k in swept:
        del sources[k]
    spec = load_config_dict(doc)
    if swept and spec.sources is not None:
        spec.sources = dataclasses.replace(spec.sources, entries=tuple(
            dataclasses.replace(e, source=SWEEP_SOURCE, anchor=None) if e.key in swept else e
            for e in spec.sources.entries))
    return spec


def run_sweep(raw: Dict[str, Any], key: str, values: List[Any], *, monte_carlo: bool = True) -> Dict[str, Any]:
    """Re-run the comparison at each value; rows carry per-option totals and the
    shared verdict; flips mark consecutive points whose cheapest option differs.
    Duplicate grid points collapse (the block says so), and a scan that moves a
    price while a price-proportional input is stated in dollars carries the
    coherence note."""
    values, collapse = dedupe(key, values)
    rows: List[Dict[str, Any]] = []
    for v in values:
        try:
            spec = load_at(raw, key, v)
        except (ConfigValidationError, ValueError) as e:
            rows.append({"value": v, "error": str(e).splitlines()[-1]})
            continue
        det = compute_deterministic(spec)
        single = single_path_run(spec)
        mc = run_monte_carlo(spec) if (monte_carlo and not single) else None
        verdict = compute_verdict(det, mc, years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate, single_path=single)
        row: Dict[str, Any] = {
            "value": v,
            "totals": {k: getattr(det, k).total_pv for k in ("condo", "house", "rent")
                       if getattr(det, k) is not None},
            "best": verdict.best, "runner_up": verdict.runner_up,
            "margin_pv": verdict.margin_pv, "margin_frac": verdict.margin_frac,
            "decisive": verdict.decisive, "rule": verdict.rule, "prob_best": verdict.prob_best,
            "mc_mean_best": verdict.mc_mean_best, "reason": verdict.reason,
            # The Monte Carlo majority, beside the deterministic best. `decisive`
            # keys to the DETERMINISTIC winner by design (ruled 2026-09-01), so a
            # row can read best=rent / decisive=false / prob_best=34% while the
            # majority and the mean both favour house; readers of the bare triple
            # were misled (2026-09-04 review). `prob_best` answers "how often is
            # the deterministic winner cheapest?", `mc_prob_best` "how often is
            # the most likely winner cheapest?" — never the same question.
            **_mc_majority(mc, det),
            "affordability": affordability_of(det),
            # The insured tier the loader derived at this point, per owned
            # option — a price scan walks the loan-to-value across tier edges.
            "insured": insured_of(spec),
            "monte_carlo": (
                {k: v for k, v in mc_to_dict(mc).items() if k in ("condo", "house", "rent") and v is not None}
                if mc is not None else None
            ),
        }
        row["sentence"] = point_sentence(key, row)
        rows.append(row)
    flips, mc_mean_flips = find_flips(rows)
    out: Dict[str, Any] = {"key": key, "values": values, "rows": rows,
                           "base_value": base_value(raw, key),
                           "flips": flips, "mc_mean_flips": mc_mean_flips,
                           "mc_majority_flips": track_flips(rows, "mc_best")}
    note = join_notes(collapse, price_scan_note(raw, key))
    if note:
        out["note"] = note
    return out


def insured_of(spec: ComparisonSpec) -> Dict[str, float]:
    """`{option: premium rate}` for every owned option whose derived mortgage
    insurance is required at this point; empty otherwise."""
    out: Dict[str, float] = {}
    for name in ("condo", "house"):
        option = getattr(spec, name, None)
        record = getattr(option, "mortgage_insurance", None)
        if record is not None and record.required:
            out[name] = record.rate
    return out


def _aff_tuple(entry: Dict[str, Any]) -> Tuple[float, Tuple[int, ...]]:
    return (round(float(entry["max_ratio"]), 6), tuple(entry["years_exceeding"]))


def constant_options(point_sets: Any) -> Dict[str, Dict[str, Any]]:
    """The options whose affordability — highest ratio and breach years — is
    identical in EVERY per-option mapping given (one per quoted point). A
    price-invariant ratio (the renter's, on a price scan) is one fact, stated
    once rather than at every point (2026-09-04)."""
    sets = [s for s in point_sets if s]
    if not sets:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for option in ("condo", "house", "rent"):
        if all(option in s for s in sets):
            first = _aff_tuple(sets[0][option])
            if all(_aff_tuple(s[option]) == first for s in sets):
                out[option] = sets[0][option]
    return out


def _breaches(entry: Dict[str, Any]) -> str:
    years = entry["years_exceeding"]
    return f"breaches years {list(years)}" if years else "breaches none"


def point_sentence(
    key: str, row: Dict[str, Any], *, base: bool = False,
    drop_affordability: Any = (), drop_insured: Any = (),
) -> str:
    """One grid point in words: `<key>=<v>: best <opt> by $<margin> (<pct>% of
    <opt> PV)[, P(best) <p>%][, insured <opt> <tier>%][, affordability <opt>
    max <r>% breaches years […]]` — only the clauses whose data the run has.

    `base` marks the point equal to the base config and keeps its verdict
    clauses alone: its affordability and financing are already in the block.
    `drop_*` name the options a header stated once for every point.
    """
    head = f"{key}={_fmt_value(key, row['value'])}" + (" (= base)" if base else "")
    if "error" in row:
        return f"{head}: refused: {row['error']}"
    best = row["best"]
    parts = [f"best {best} by ${row['margin_pv']:,.0f} ({row['margin_frac']:.1%} of {best} PV)"]
    prob = row.get("prob_best")
    if prob is not None:
        measured, _ = _against(prob, ANCHORS["verdict.prob_floor"].value)
        parts.append(f"P(best) {measured}" + (" (at the floor)" if at_the_floor(prob) else ""))
    if not base:
        for option, rate in (row.get("insured") or {}).items():
            if option not in drop_insured:
                parts.append(f"insured {option} {rate:.2%}")
        aff = row.get("affordability") or {}
        clauses = [f"{option} max {aff[option]['max_ratio']:.1%} {_breaches(aff[option])}"
                   for option in ("condo", "house", "rent")
                   if option in aff and option not in drop_affordability]
        if clauses:
            parts.append("affordability " + "; ".join(clauses))
    return f"{head}: " + ", ".join(parts)


def sweep_lines(result: Dict[str, Any]) -> List[str]:
    """The read-back lines of one sweep: a header naming the sweep and what
    holds at every point, one line per grid point, then the flip lines."""
    key, rows = result["key"], result["rows"]
    ok = [r for r in rows if "error" not in r]
    clauses: List[str] = []
    sets = [r.get("affordability") for r in ok]
    constant = constant_options(sets) if ok and all(sets) and len(ok) > 1 else {}
    if constant:
        clauses.append("affordability " + "; ".join(
            f"{o} max {e['max_ratio']:.1%} {_breaches(e)}" for o, e in constant.items())
            + " at every point")
    insured = ok[0].get("insured") if ok else None
    same_tier = bool(insured) and len(ok) > 1 and all(r.get("insured") == insured for r in ok)
    if same_tier:
        clauses.append(", ".join(f"insured {o} {rate:.2%}" for o, rate in insured.items())
                       + " at every point")
    head = f"sweep {key} ({len(rows)} points" + ("; " + "; ".join(clauses) if clauses else "") + ")"
    base = result.get("base_value")
    lines = [head]
    for r in rows:
        is_base = (isinstance(base, (int, float)) and not isinstance(base, bool)
                   and abs(float(r["value"]) - float(base)) <= 1e-12 * max(1.0, abs(float(base))))
        lines.append(point_sentence(key, r, base=is_base,
                                    drop_affordability=constant.keys(),
                                    drop_insured=(insured or {}).keys() if same_tier else ()))
    lines.extend(flip_lines(result))
    return lines


def _mc_majority(mc: Optional[Any], det: ComparisonDeterministicResult) -> Dict[str, Any]:
    """`mc_best` / `mc_prob_best`: the option Monte Carlo calls cheapest most
    often, and how often. Both None without a Monte Carlo run."""
    if mc is None:
        return {"mc_best": None, "mc_prob_best": None}
    probs = {
        name: getattr(mc, f"prob_{name}_cheapest")
        for name in ("condo", "house", "rent")
        if getattr(det, name, None) is not None
        and getattr(mc, f"prob_{name}_cheapest") is not None
    }
    if not probs:
        return {"mc_best": None, "mc_prob_best": None}
    best = max(probs, key=lambda name: probs[name])
    return {"mc_best": best, "mc_prob_best": probs[best]}


def track_flips(rows: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    """Consecutive points whose value of `field` differs — a refused point (or a
    point with nothing to compare) ends the run rather than joining two sides
    that were never adjacent."""
    out: List[Dict[str, Any]] = []
    prev = None
    for row in rows:
        if "error" in row or row.get(field) is None:
            prev = None
            continue
        if prev is not None and row[field] != prev[field]:
            out.append({"from_value": prev["value"], "from_best": prev[field],
                        "to_value": row["value"], "to_best": row[field]})
        prev = row
    return out


def find_flips(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Consecutive points whose cheapest option differs — once for the
    deterministic `best`, once for `mc_mean_best` (the Monte Carlo mean can
    change sides where the deterministic line does not; round-four dogfood
    2026-09-02 printed 'no flip' on exactly such a sweep)."""
    return track_flips(rows, "best"), track_flips(rows, "mc_mean_best")


def _fmt_value(key: str, v: Any) -> str:
    if key in INT_KEYS or isinstance(v, int):
        return str(v)
    return f"{v:.2%}" if abs(v) < 1 else f"{v:,.0f}"


def at_the_floor(prob_best: Optional[float]) -> bool:
    """True when P(best) EQUALS the verdict's probability floor: decisive by
    the rule (≥), with nothing to spare — a row says so rather than print a
    bare decisive flag (2026-09-04)."""
    if prob_best is None:
        return False
    return abs(prob_best - ANCHORS["verdict.prob_floor"].value) < 1e-12


def format_sweep(result: Dict[str, Any]) -> str:
    key, rows = result["key"], result["rows"]
    opts = [o for o in ("condo", "house", "rent") if any(o in r.get("totals", {}) for r in rows)]
    lines = [f"\nSweep {key} ({len(rows)} points; every other input held at its base value — "
             f"a joint question needs a second --sweep on the edited config; per-point Monte Carlo "
             f"percentiles ride --json; 'decisive' is judged by the rule shown — mc_floor when Monte "
             f"Carlo ran with uncertainty on, else margin_band):"]
    if result.get("note"):
        lines.append(f"  {result['note']}")
    head = f"  {key:>{max(len(key), 10)}} | " + " | ".join(f"{o.capitalize():>12}" for o in opts) + " | cheapest | margin vs runner-up | decisive (rule) | P(best) | MC-mean best"
    lines.append(head)
    for r in rows:
        val = _fmt_value(key, r["value"])
        if "error" in r:
            lines.append(f"  {val:>{max(len(key), 10)}} | refused: {r['error']}")
            continue
        totals = " | ".join(f"${r['totals'][o]:>11,.0f}" for o in opts)
        prob = f"{r['prob_best']:.0%}" if r["prob_best"] is not None else "n/a"
        mean_best = r.get("mc_mean_best") or "n/a"
        rule = r.get("rule", "?")
        if at_the_floor(r["prob_best"]):
            rule += ", at the floor"  # decisive by ≥, on nothing to spare
        lines.append(
            f"  {val:>{max(len(key), 10)}} | {totals} | {r['best']:>8} | "
            f"${r['margin_pv']:>11,.0f} ({r['margin_frac']:.1%}) | {str(r['decisive']):>5} ({rule}) | {prob:>7} | {mean_best:>12}"
        )
    lines.extend(f"  {line}" for line in flip_lines(result))
    return "\n".join(lines)


def flip_lines(result: Dict[str, Any]) -> List[str]:
    """Where the sweep changes sides, unindented: the deterministic flip (or the
    'no flip' line), the Monte Carlo MEAN flip, and the Monte Carlo MAJORITY
    flip — the last only where it says something the deterministic flip does
    not, since a majority that turns exactly where the deterministic line turns
    is the same sentence twice.

    One builder for the sweep block and the read-back block (2026-09-04).
    """
    key = result["key"]

    def _move(f: Dict[str, Any], joiner: str) -> str:
        return (f"{f['from_best']} ({key}={_fmt_value(key, f['from_value'])}) "
                f"{joiner} {f['to_best']} ({key}={_fmt_value(key, f['to_value'])})")

    # Every line names its key: two --sweep flags printed two bare "no flip"
    # lines and nothing said which sweep each belonged to (2026-09-04).
    lines: List[str] = []
    if result["flips"]:
        for f in result["flips"]:
            lines.append(f"flip {key}: cheapest changes from {_move(f, 'to')}")
    else:
        lines.append(f"no flip along {key}: the same option is cheapest across the whole sweep")
    for f in result.get("mc_mean_flips", []):
        lines.append(f"mean flip {key}: Monte Carlo mean favours {_move(f, 'then')}")
    majority = result.get("mc_majority_flips") or []
    if majority != result["flips"]:
        for f in majority:
            lines.append(f"majority flip {key}: Monte Carlo P(cheapest) majority favours "
                         f"{_move(f, 'then')}")
    return lines
