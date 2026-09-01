# tests/test_tools.py
import copy
import json
import os
import pytest
import numpy as np
from hde.config import load_config_dict
from hde.models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    MonteCarloOptionResult,
    MonteCarloSummary,
    OptionResult,
)
from mcp_server import registry
import mcp_server.tools as tools_module
from mcp_server.tools import _det_to_dict, _mc_to_dict, define_scenario, run_comparison, sweep_param, save_figure
from mcp_server.tools import list_scenarios, delete_scenario


@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


def _make_det() -> ComparisonDeterministicResult:
    return ComparisonDeterministicResult(
        condo=OptionResult(
            total_pv=13.0,
            breakdown={"fee_pv": 10.0, "events_pv": 2.0, "other_pv": 1.0, "reserve_pv": 0.0},
        ),
        house=OptionResult(
            total_pv=24.0,
            breakdown={"maintenance_pv": 20.0, "events_pv": 3.0, "other_pv": 1.0},
        ),
    )


def _make_mc() -> ComparisonMonteCarloResult:
    arr = np.array([1.0, 2.0, 3.0])
    s = MonteCarloSummary(mean=2.0, std=1.0, p5=1.0, p50=2.0, p95=3.0)
    return ComparisonMonteCarloResult(
        condo=MonteCarloOptionResult(pvs=arr, summary=s),
        house=MonteCarloOptionResult(pvs=arr, summary=s),
        prob_condo_cheapest=0.5,
        prob_house_cheapest=0.5,
    )


BASIC_CONFIG = {
    "years": 20,
    "discount_rate": 0.03,
    "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": True},
    "house": {"initial_value": 400_000, "all_cash": True},
}


# --- Serialization helpers ---

def test_det_to_dict_is_json_safe():
    d = _det_to_dict(_make_det())
    json.dumps(d)  # must not raise
    assert d["condo"]["total_pv"] == 13.0
    assert d["house"]["total_pv"] == 24.0
    assert d["rent"] is None
    assert d["affordability"] is None


def test_mc_to_dict_no_numpy_arrays():
    d = _mc_to_dict(_make_mc())
    json.dumps(d)  # must not raise; numpy arrays would fail here
    assert d["prob_condo_cheapest"] == 0.5
    assert d["prob_house_cheapest"] == 0.5
    for key in ("condo", "house"):
        assert set(d[key].keys()) == {"mean", "std", "p5", "p50", "p95"}
    assert d["rent"] is None
    assert d["condo"]["mean"] == 2.0


# --- define_scenario ---

def test_define_scenario_valid():
    result = define_scenario("s1", BASIC_CONFIG)
    assert result["name"] == "s1"
    assert result["status"] == "defined"
    assert result["condo_monthly_fee"] == 500
    assert result["house_initial_value"] == 400_000
    assert result["years"] == 20


def test_define_scenario_stores_in_registry():
    define_scenario("s1", BASIC_CONFIG)
    entry = registry.get("s1")
    assert entry.name == "s1"
    assert entry.raw_config == BASIC_CONFIG


def test_define_scenario_invalid_config_returns_error():
    bad = {"years": 20, "discount_rate": 0.03, "condo": {"monthly_fee": -100}, "house": {"initial_value": 400_000}}
    result = define_scenario("bad", bad)
    assert "error" in result


# --- run_comparison ---

def test_run_comparison_both_modes():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1")
    assert result["name"] == "s1"
    assert result["mode"] == "both"
    assert isinstance(result["report"], str)
    assert len(result["report"]) > 0
    assert "deterministic" in result
    assert "monte_carlo" in result
    assert isinstance(result["deterministic"]["condo"]["total_pv"], float)
    assert 0.0 <= result["monte_carlo"]["prob_condo_cheapest"] <= 1.0


def test_run_comparison_deterministic_only():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1", mode="deterministic")
    assert "deterministic" in result
    assert "monte_carlo" not in result


def test_run_comparison_mc_only():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1", mode="monte_carlo")
    assert "monte_carlo" in result
    assert "deterministic" not in result


def test_run_comparison_stores_results_in_registry():
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="both")
    entry = registry.get("s1")
    assert entry.det_result is not None
    assert entry.mc_result is not None


def test_run_comparison_missing_scenario():
    result = run_comparison("nonexistent")
    assert "error" in result
    assert "nonexistent" in result["error"]


# --- sweep_param ---

def test_sweep_param_returns_rows():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "condo.monthly_fee", [400.0, 500.0, 600.0])
    assert "rows" in result
    assert len(result["rows"]) == 3
    assert result["param_path"] == "condo.monthly_fee"
    # Higher fee → higher condo PV total
    pv_totals = [r["condo_total_pv"] for r in result["rows"]]
    assert pv_totals[0] < pv_totals[1] < pv_totals[2]


def test_sweep_param_top_level_key():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "years", [10, 20, 30])
    assert len(result["rows"]) == 3


def test_sweep_param_invalid_path_returns_error():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "house.events.0.base_cost", [1000.0])
    assert "error" in result
    assert "unsupported" in result["error"]


def test_sweep_param_missing_scenario():
    result = sweep_param("nonexistent", "years", [10, 20])
    assert "error" in result
    assert "nonexistent" in result["error"]


def test_sweep_does_not_mutate_registry_config():
    define_scenario("s1", BASIC_CONFIG)
    original_fee = registry.get("s1").raw_config["condo"]["monthly_fee"]
    sweep_param("s1", "condo.monthly_fee", [999.0])
    assert registry.get("s1").raw_config["condo"]["monthly_fee"] == original_fee


def test_sweep_paths_resolve_against_live_dataclass_fields():
    """Drift guard: each _SWEEP_PATHS entry must produce a valid config that load_config_dict accepts."""
    from mcp_server.tools import _SWEEP_PATHS
    # Owned options use mortgage blocks (not all_cash) so the down_payment/mortgage_rate/
    # mortgage_term_years sweep paths resolve — all_cash XOR mortgage block is now enforced.
    base = {
        "years": 20, "discount_rate": 0.03,
        "condo": {"monthly_fee": 500, "fee_escalation_rate": 0.02, "reserve_contribution_rate": 0.01,
                  "initial_value": 300_000, "down_payment": 60_000,
                  "mortgage_rate": 0.05, "mortgage_term_years": 25},
        "house": {"initial_value": 400_000, "value_growth_rate": 0.01, "annual_maintenance_rate": 0.015,
                  "down_payment": 80_000, "mortgage_rate": 0.05, "mortgage_term_years": 25},
        "rent": {"monthly_rent": 2000, "invested_down_payment": 100_000, "investment_return_rate": 0.07},
        "simulation": {"house_maintenance_vol": 0.3, "condo_fee_vol": 0.05},
        "economic": {"inflation_rate": 0.02},
    }
    for path, (section, field) in _SWEEP_PATHS.items():
        config = copy.deepcopy(base)
        if section is None:
            config[field] = base.get(field, 20)
        else:
            config.setdefault(section, {})[field] = base.get(section, {}).get(field, 0.01)
        try:
            load_config_dict(config)
        except Exception as e:
            pytest.fail(f"_SWEEP_PATHS[{path!r}] → invalid config: {e}")


# --- save_figure ---

def test_save_figure_requires_mc_first(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    result = save_figure("s1", "diff_distribution")
    assert "error" in result
    assert "run_comparison" in result["error"]


def test_save_figure_diff_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="monte_carlo")
    result = save_figure("s1", "diff_distribution")
    assert "path" in result
    assert os.path.exists(result["path"])
    assert result["path"].endswith(".png")


def test_save_figure_pv_distributions(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="monte_carlo")
    result = save_figure("s1", "pv_distributions")
    assert "path" in result
    assert os.path.exists(result["path"])


def test_save_figure_unknown_type(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="monte_carlo")
    result = save_figure("s1", "unknown_type")
    assert "error" in result


def test_save_figure_missing_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_module, "FIGURE_CACHE_DIR", tmp_path)
    result = save_figure("nonexistent", "diff_distribution")
    assert "error" in result


# --- list_scenarios + delete_scenario ---

def test_list_scenarios_empty():
    result = list_scenarios()
    assert result == {"scenarios": [], "count": 0}


def test_list_scenarios_with_entries():
    define_scenario("a", BASIC_CONFIG)
    define_scenario("b", BASIC_CONFIG)
    result = list_scenarios()
    assert result["count"] == 2
    names = {s["name"] for s in result["scenarios"]}
    assert names == {"a", "b"}


def test_delete_scenario_existing():
    define_scenario("s1", BASIC_CONFIG)
    result = delete_scenario("s1")
    assert result == {"deleted": "s1"}
    assert list_scenarios()["count"] == 0


def test_delete_scenario_missing():
    result = delete_scenario("nonexistent")
    assert "error" in result
    assert "nonexistent" in result["error"]


# --- cross-mode re-run stale state clearing ---

def test_run_comparison_deterministic_clears_stale_mc():
    define_scenario("s1", BASIC_CONFIG)
    run_comparison("s1", mode="both")
    assert registry.get("s1").mc_result is not None
    run_comparison("s1", mode="deterministic")
    assert registry.get("s1").mc_result is None
    assert registry.get("s1").det_result is not None


# --- rent sweep drift guards ---

def test_drift_guard_sweep_paths_rent():
    """All rent _SWEEP_PATHS entries must resolve against a rent-inclusive spec."""
    from mcp_server.tools import _SWEEP_PATHS
    from hde.config import load_config_dict
    config = {
        "years": 10, "discount_rate": 0.05,
        "rent": {"monthly_rent": 2000, "invested_down_payment": 100_000, "investment_return_rate": 0.07},
    }
    spec = load_config_dict(config)
    rent_paths = {k: v for k, v in _SWEEP_PATHS.items() if k.startswith("rent.")}
    for path, (section, field) in rent_paths.items():
        assert hasattr(spec.rent, field), f"rent.{field} not in RentParams"


def test_sweep_param_rent_path_no_rent_section():
    """Sweep on rent.* path with no rent section returns error."""
    define_scenario("s1", {"years": 10, "discount_rate": 0.05, "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": True}})
    result = sweep_param("s1", "rent.monthly_rent", [2000.0, 2500.0])
    assert "error" in result
    assert "no rent section" in result["error"]


# --- PR #4 external-review findings ---

MORTGAGE_CONFIG = {
    "years": 20,
    "discount_rate": 0.03,
    "house": {"initial_value": 400_000, "down_payment": 80_000,
              "mortgage_rate": 0.05, "mortgage_term_years": 25},
}


def test_sweep_mortgage_field_on_all_cash_section_rejected():
    """Finding #5: sweeping a mortgage field while all_cash=True is a silent no-op — reject loudly."""
    define_scenario("s1", BASIC_CONFIG)  # house is all_cash
    result = sweep_param("s1", "house.down_payment", [50_000.0, 80_000.0])
    assert "error" in result
    assert "all_cash" in result["error"]
    assert "rows" not in result


def test_sweep_mortgage_field_on_financed_section_ok():
    """A financed (non-all_cash) section still sweeps mortgage fields normally."""
    define_scenario("s1", MORTGAGE_CONFIG)
    result = sweep_param("s1", "house.down_payment", [60_000.0, 100_000.0])
    assert "rows" in result
    assert len(result["rows"]) == 2
    assert all("error" not in r for r in result["rows"])


def test_sweep_revalidates_each_swept_config():
    """Finding #7: each swept config is re-validated; an out-of-range value surfaces as a
    per-row error. selling_cost_rate must be in [0, 1) — enforced only by validate_config,
    not by the compute engine, so this fails without the re-validation."""
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "condo.selling_cost_rate", [1.5])
    assert len(result["rows"]) == 1
    assert "error" in result["rows"][0]
    assert result["rows"][0]["value"] == 1.5


# --- Audit F1: unknown-key rejection via the MCP tools path ---

def test_define_scenario_typo_key_returns_error_with_did_you_mean():
    """A typo'd key must refuse via define_scenario (the MCP path), not be ignored."""
    cfg = {**BASIC_CONFIG, "condo": {**BASIC_CONFIG["condo"], "fee_escalation_ratte": 0.02}}
    result = define_scenario("typo", cfg)
    assert "error" in result
    assert "unknown key 'condo.fee_escalation_ratte'" in result["error"]
    assert "did you mean 'fee_escalation_rate'?" in result["error"]
    assert list_scenarios()["count"] == 0  # nothing registered on refusal


# --- Audit U1/U2: assumption echo + coherence warnings on MCP surfaces ---

def test_define_scenario_returns_assumption_echo_and_warnings():
    result = define_scenario("s1", BASIC_CONFIG)
    assert result["assumptions"], "assumption echo must be present"
    joined = "\n".join(result["assumptions"]["lines"])
    assert "mode: real terms" in joined
    assert "discount_rate 3.0%" in joined
    assert "defaults applied:" in joined
    assert isinstance(result["warnings"], list)
    # structured half: every defaulted key carries its anchor record
    entries = result["assumptions"]["defaults_applied"]
    assert entries and all("kind" in e and "anchor" in e for e in entries)


def test_run_comparison_carries_structured_assumptions_and_version():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1", mode="deterministic")
    assert result["engine_version"]
    assert result["assumptions"]["lines"] == define_scenario("s1", BASIC_CONFIG)["assumptions"]["lines"]
    by_key = {e["key"]: e for e in result["assumptions"]["defaults_applied"]}
    assert by_key["condo.selling_cost_rate"]["anchor"]["short_cite"] == "WOWA 2026"
    assert result["verdict"]["best"] in {"condo", "house", "rent"}
    assert isinstance(result["verdict"]["decisive"], bool)


def test_sweep_of_anchored_param_attaches_anchor_and_band_flags():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "condo.selling_cost_rate", [0.02, 0.05, 0.10])
    assert result["anchor"]["name"] == "condo.house.selling_cost_rate"
    assert [row["outside_band"] for row in result["rows"]] == [True, False, True]


def test_sweep_of_unanchored_param_has_no_anchor_key():
    define_scenario("s1", BASIC_CONFIG)
    result = sweep_param("s1", "condo.monthly_fee", [300.0, 500.0])
    assert "anchor" not in result
    assert all("outside_band" not in row for row in result["rows"])


def test_define_scenario_warnings_flag_nominal_quote_experiment_a():
    """Audit experiment A: real mode + 5% growth + mortgage 6%."""
    cfg = {
        "years": 25, "discount_rate": 0.05,
        "economic": {"mode": "real"},
        "house": {"initial_value": 500_000, "value_growth_rate": 0.05,
                  "down_payment": 100_000, "mortgage_rate": 0.06,
                  "mortgage_term_years": 25},
        "rent": {"monthly_rent": 2_200},
    }
    result = define_scenario("expA", cfg)
    warns = "\n".join(result["warnings"])
    assert "house.value_growth_rate=5.0%" in warns
    assert "nominal quote" in warns
    assert "not like-for-like" in warns
    assert result["status"] == "defined"  # warnings never refuse


def test_run_comparison_response_carries_warnings():
    define_scenario("s1", BASIC_CONFIG)
    result = run_comparison("s1", mode="deterministic")
    assert "warnings" in result
    assert isinstance(result["warnings"], list)
    assert "Assumptions" in result["report"]  # echo header via spec
