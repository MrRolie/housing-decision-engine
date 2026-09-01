# mcp_server/tools.py
from __future__ import annotations
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from hde.anchors import ANCHORS, _ECHO_ALIASES
from hde.config import load_config_dict, validate_config, all_warnings, single_path_run, ConfigValidationError
from hde.deterministic import compute_deterministic
from hde.market_scenario import ScenarioPriorError
from hde.serialization import (
    anchor_to_dict,
    assumptions_to_dict,
    engine_version,
    verdict_to_dict,
    det_to_dict as _det_to_dict,
    mc_to_dict as _mc_to_dict,
)
from hde.monte_carlo import run_monte_carlo, _load_prior_if_any
from hde.models import (
    ComparisonSpec,
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    MonteCarloSummary,
    InputError,
    compute_verdict,
    CONDO_BREAKDOWN_KEYS,
    HOUSE_BREAKDOWN_KEYS,
    RENT_BREAKDOWN_KEYS,
)
from hde.reporting import format_text_report, plot_diff_distribution, plot_pv_distributions
from mcp_server import registry

FIGURE_CACHE_DIR: Path = Path.home() / ".cache" / "hde" / "figures"


# ---------------------------------------------------------------------------
# Serialization helpers (private)
# ---------------------------------------------------------------------------

from hde.serialization import det_to_dict as _det_to_dict, mc_to_dict as _mc_to_dict  # noqa: E402


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def define_scenario(name: str, config: dict) -> dict:
    """Define a named housing scenario. Config must include 'years', 'discount_rate',
    and at least one of 'condo', 'house', 'rent'. Optional 'income' for affordability."""
    safe_name = Path(name).name
    try:
        spec = load_config_dict(config)
    except (ConfigValidationError, ValueError, TypeError) as e:
        return {"error": str(e)}

    overwriting = safe_name in registry._REGISTRY
    registry.define(safe_name, config, spec)
    registry.store_results(safe_name)  # total-replace: clear any stale results

    response = {
        "name": safe_name,
        "status": "defined",
        "years": spec.simulation.years,
        "discount_rate": spec.simulation.discount_rate,
    }
    # None-safe option summaries
    if spec.condo is not None:
        response["condo_monthly_fee"] = spec.condo.monthly_fee
    if spec.house is not None:
        response["house_initial_value"] = spec.house.initial_value
    if spec.rent is not None:
        response["rent_monthly_rent"] = spec.rent.monthly_rent
    if spec.income is not None:
        response["income_annual"] = spec.income.annual_income
    if overwriting:
        response["previous_results_cleared"] = True
    # Audit U1/U2: structured assumption echo (lines + anchor records) and
    # coherence warnings (surface, never refuse) — same shape as run_comparison.
    response["assumptions"] = assumptions_to_dict(spec)
    response["warnings"] = all_warnings(spec)
    return response


def run_comparison(scenario_name: str, mode: str = "both",
                   current_year: int | None = None) -> dict:
    """Run deterministic and/or Monte Carlo comparison for a named scenario.
    mode: 'deterministic' | 'monte_carlo' | 'both'.
    current_year: injectable wall-clock year (tests pass it explicitly; the
    default resolves to datetime.date.today().year — never read in the engine)."""
    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}
    if mode not in {"deterministic", "monte_carlo", "both"}:
        return {"error": f"unsupported mode '{mode}'; use deterministic, monte_carlo, or both"}

    entry = registry.get(safe_name)
    det_result = None
    mc_result = None

    # The prior is loaded once at this edge: the prior-vs-constant mismatch
    # hard-fails inside load_scenario_prior and returns as {error}; the
    # wall-clock staleness half rides the warnings list via all_warnings.
    prior = None
    if entry.spec.market_scenario is not None:
        try:
            prior = _load_prior_if_any(entry.spec)
        except ScenarioPriorError as e:
            return {"error": str(e)}
    warnings = all_warnings(entry.spec, prior, current_year)

    try:
        if mode in {"deterministic", "both"}:
            det_result = compute_deterministic(entry.spec)
        if mode in {"monte_carlo", "both"}:
            mc_result = run_monte_carlo(entry.spec)
    except (InputError, ScenarioPriorError) as e:
        # S4b typed refusals (nominal-mode composition, prior contract violations)
        return {"error": str(e)}

    registry.store_results(safe_name, det_result=det_result, mc_result=mc_result)

    report = format_text_report(
        det_result if det_result is not None else ComparisonDeterministicResult(),
        mc_result,
        entry.spec.simulation,
        entry.spec.economic,
        spec=entry.spec, prior=prior,
    )

    response = {
        "name": safe_name,
        "mode": mode,
        "report": report,
        "engine_version": engine_version(),
        "warnings": warnings,
        "assumptions": assumptions_to_dict(entry.spec, prior),
        "verdict": verdict_to_dict(
            compute_verdict(
                det_result, mc_result,
                years=entry.spec.simulation.years,
                discount_rate=entry.spec.simulation.discount_rate,
                single_path=single_path_run(entry.spec),
            ) if det_result is not None else None
        ),
    }
    if det_result is not None:
        response["deterministic"] = _det_to_dict(det_result)
    if mc_result is not None:
        response["monte_carlo"] = _mc_to_dict(mc_result)
    return response


# Whitelist: dot-notation param_path → (spec_section_attr, dataclass_field)
# section=None means the field lives on SimulationParams (top-level config keys).
_SWEEP_PATHS: dict[str, tuple[str | None, str]] = {
    "years":                              (None, "years"),
    "discount_rate":                      (None, "discount_rate"),
    "condo.monthly_fee":                  ("condo", "monthly_fee"),
    "condo.fee_escalation_rate":          ("condo", "fee_escalation_rate"),
    "condo.reserve_contribution_rate":    ("condo", "reserve_contribution_rate"),
    "house.initial_value":                ("house", "initial_value"),
    "house.value_growth_rate":            ("house", "value_growth_rate"),
    "house.annual_maintenance_rate":      ("house", "annual_maintenance_rate"),
    "simulation.house_maintenance_vol":   ("simulation", "house_maintenance_vol"),
    "simulation.condo_fee_vol":           ("simulation", "condo_fee_vol"),
    "economic.inflation_rate":            ("economic", "inflation_rate"),
    "rent.monthly_rent":                  ("rent", "monthly_rent"),
    "rent.invested_down_payment":         ("rent", "invested_down_payment"),
    "rent.investment_return_rate":        ("rent", "investment_return_rate"),
    "house.down_payment":                 ("house", "down_payment"),
    "house.mortgage_rate":                ("house", "mortgage_rate"),
    "house.mortgage_term_years":          ("house", "mortgage_term_years"),
    "house.selling_cost_rate":            ("house", "selling_cost_rate"),
    "condo.initial_value":                ("condo", "initial_value"),
    "condo.value_growth_rate":            ("condo", "value_growth_rate"),
    "condo.down_payment":                 ("condo", "down_payment"),
    "condo.mortgage_rate":                ("condo", "mortgage_rate"),
    "condo.mortgage_term_years":          ("condo", "mortgage_term_years"),
    "condo.selling_cost_rate":            ("condo", "selling_cost_rate"),
}


def sweep_param(scenario_name: str, param_path: str, values: list[float]) -> dict:
    """Sweep a scalar parameter across a list of values using the deterministic engine.
    param_path uses dot-notation (e.g. 'condo.monthly_fee', 'years'). Flat scalar fields only."""
    import copy
    import dataclasses as dc

    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}
    if not values:
        return {"error": "values list is empty"}
    if param_path not in _SWEEP_PATHS:
        return {"error": f"unsupported param_path '{param_path}'. Supported: {sorted(_SWEEP_PATHS.keys())}"}

    entry = registry.get(safe_name)
    section, field = _SWEEP_PATHS[param_path]

    # Guard: option-section sweeps require that section to exist on the spec.
    if section in {"condo", "house", "rent"} and getattr(entry.spec, section) is None:
        return {"error": f"scenario '{safe_name}' has no {section} section; cannot sweep {param_path}"}

    # Guard: sweeping a mortgage field on an all_cash owned option is a silent no-op
    # (the financing engine ignores the mortgage block when all_cash=True). Reject loudly.
    MORTGAGE_FIELDS = {"down_payment", "mortgage_rate", "mortgage_term_years"}
    if section in {"condo", "house"} and field in MORTGAGE_FIELDS:
        opt = getattr(entry.spec, section)
        if opt is not None and opt.all_cash:
            return {"error": f"cannot sweep {param_path}: {section} is all_cash, so mortgage "
                             f"fields are ignored and the sweep would be a no-op"}

    # Coerce integer fields — JSON delivers all numbers as float (e.g. 10.0),
    # but SimulationParams.years: int — range(1, sim.years + 1) crashes on float.
    INT_FIELDS = {"years", "num_sims", "random_seed", "mortgage_term_years"}
    if field in INT_FIELDS:
        values = [int(v) for v in values]

    rows = []
    for v in values:
        spec_copy = copy.deepcopy(entry.spec)
        if section is None:
            # top-level SimulationParams field
            spec_copy = dc.replace(spec_copy, simulation=dc.replace(spec_copy.simulation, **{field: v}))
        else:
            section_obj = getattr(spec_copy, section)
            new_section = dc.replace(section_obj, **{field: v})
            spec_copy = dc.replace(spec_copy, **{section: new_section})
        try:
            # Re-validate the swept config: dc.replace bypasses load_config_dict's
            # validation, so an out-of-range swept value would otherwise compute
            # garbage. Surface any violation as this sweep point's failure.
            sweep_warnings = validate_config(spec_copy)
            if sweep_warnings:
                raise ConfigValidationError(
                    "swept config invalid:\n" + "\n".join(sweep_warnings))
            det = compute_deterministic(spec_copy)
            row = {"value": v}
            if det.condo is not None:
                row["condo_total_pv"] = det.condo.total_pv
            if det.house is not None:
                row["house_total_pv"] = det.house.total_pv
            if det.rent is not None:
                row["rent_total_pv"] = det.rent.total_pv
            rows.append(row)
        except Exception as e:
            rows.append({"value": v, "error": str(e)})

    result: dict = {"name": safe_name, "param_path": param_path, "rows": rows}
    # Provenance for the swept parameter: when it is an anchored engine default,
    # attach the full record and flag each swept value that leaves the anchor's
    # plausible band, so a sweep never reads as evidence for an implausible value.
    anchor = ANCHORS.get(_ECHO_ALIASES.get(param_path, param_path))
    if anchor is not None:
        lo, hi = anchor.band
        result["anchor"] = anchor_to_dict(anchor)
        for row in rows:
            row["outside_band"] = not (lo <= row["value"] <= hi)
    return result


def save_figure(scenario_name: str, figure_type: str) -> dict:
    """Save a matplotlib figure for a scenario to the figure cache dir.
    figure_type: 'diff_distribution' | 'pv_distributions'.
    Returns {'path': '<absolute_path>'}.
    Requires run_comparison to have been called with mode='monte_carlo' or 'both' first."""
    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}

    entry = registry.get(safe_name)
    if entry.mc_result is None:
        return {"error": "run run_comparison with mode='monte_carlo' or 'both' first"}

    mc = entry.mc_result
    if figure_type == "diff_distribution":
        if mc.condo is None or mc.house is None:
            return {"error": "diff_distribution requires both condo and house options"}
        diff_pvs = mc.house.pvs - mc.condo.pvs
        fig = plot_diff_distribution(diff_pvs)
    elif figure_type == "pv_distributions":
        option_arrays = {}
        if mc.condo is not None:
            option_arrays["Condo"] = mc.condo.pvs
        if mc.house is not None:
            option_arrays["House"] = mc.house.pvs
        if mc.rent is not None:
            option_arrays["Rent"] = mc.rent.pvs
        if not option_arrays:
            return {"error": "no option arrays available for pv_distributions"}
        fig = plot_pv_distributions(option_arrays)
    else:
        return {"error": f"unknown figure_type '{figure_type}'. Use diff_distribution or pv_distributions"}

    FIGURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time_ns())
    path = FIGURE_CACHE_DIR / f"{safe_name}_{figure_type}_{ts}.png"
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(path)}


def list_scenarios() -> dict:
    """List all scenarios defined in this session with their result-cached status."""
    entries = registry.all_entries()
    return {"scenarios": entries, "count": len(entries)}


def delete_scenario(name: str) -> dict:
    """Remove a scenario from the session registry."""
    try:
        registry.remove(name)
    except KeyError:
        return {"error": f"scenario not found: {name}"}
    return {"deleted": name}
