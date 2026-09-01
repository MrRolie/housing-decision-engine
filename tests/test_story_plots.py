"""
Story-plot tests: the five-act narrative rendering (src/hde/story_plots.py).

Covers:
  - full render against a synthetic spec + tiny MC + the golden fixture prior
  - pure computation helpers (_verdict_sentence, cumulative curves, crossovers)
  - degradation without MC / without prior / both
  - fmt parameter and CLI --plots wiring
"""

import sys
from pathlib import Path

import numpy as np
import pytest

from hde.cli import main as cli_main
from hde.config import load_config
from hde.deterministic import compute_deterministic
from hde.market_scenario import load_scenario_prior
from hde.models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    ComparisonSpec,
    CondoParams,
    EconomicParams,
    HouseParams,
    MonteCarloOptionResult,
    MonteCarloSummary,
    OptionResult,
    PriceShockParams,
    RentParams,
    SimulationParams,
)
from hde.monte_carlo import run_monte_carlo
from hde.story_plots import (
    _cumulative_cost_curves,
    find_crossovers,
    render_decision_story,
    verdict_sentence,
)

GOLDEN_PRIOR = str(Path(__file__).parent / "fixtures" / "scenario_prior_golden.json")
MIN_FIG_BYTES = 5000


def _spec(with_prior: bool = False) -> ComparisonSpec:
    sim = SimulationParams(
        years=25, discount_rate=0.03, num_sims=100, random_seed=42,
        house_maintenance_vol=0.10, condo_fee_vol=0.05, rent_escalation_vol=0.02,
    )
    econ = EconomicParams(mode="real")
    spec = ComparisonSpec(
        simulation=sim,
        economic=econ,
        condo=CondoParams(monthly_fee=450, fee_escalation_rate=0.02,
                          initial_value=350_000, all_cash=True),
        house=HouseParams(initial_value=400_000, value_growth_rate=0.01,
                          annual_maintenance_rate=0.012, all_cash=True,
                          price_shock=PriceShockParams(annual_hazard=0.04)),
        rent=RentParams(monthly_rent=1_900, rent_escalation_rate=0.03,
                        invested_down_payment=60_000, investment_return_rate=0.05),
    )
    if with_prior:
        from hde.models import MarketScenario

        spec.market_scenario = MarketScenario(path=GOLDEN_PRIOR, geography="MTL_RMR")
    return spec


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _det_from_pvs(pvs: dict) -> ComparisonDeterministicResult:
    def opt(pv):
        return OptionResult(total_pv=pv, breakdown={})
    return ComparisonDeterministicResult(
        condo=opt(pvs["condo"]) if "condo" in pvs else None,
        house=opt(pvs["house"]) if "house" in pvs else None,
        rent=opt(pvs["rent"]) if "rent" in pvs else None,
    )


class TestVerdictSentence:
    def test_rent_wins_states_margin_and_horizon(self):
        det = _det_from_pvs({"condo": 684_000.0, "house": 700_000.0, "rent": 600_000.0})
        sentence = verdict_sentence(det, 25)
        assert sentence == "Renting wins by $84,000 over 25 years"

    def test_margin_is_vs_closest_competitor(self):
        det = _det_from_pvs({"condo": 500_000.0, "house": 900_000.0, "rent": 520_000.0})
        # closest competitor to renting is condo at 500k -> margin 20k
        assert "$20,000" in verdict_sentence(det, 30)
        assert "over 30 years" in verdict_sentence(det, 30)

    def test_condo_winning_uses_display_name(self):
        det = _det_from_pvs({"condo": 400_000.0, "house": 450_000.0, "rent": 480_000.0})
        sentence = verdict_sentence(det, 10)
        assert sentence == "Buying a condo wins by $50,000 over 10 years"

    def test_single_option(self):
        det = _det_from_pvs({"rent": 123_456.0})
        assert "Only one option priced" in verdict_sentence(det, 5)

    def test_tie(self):
        det = _det_from_pvs({"condo": 400_000.0, "rent": 400_000.0})
        assert "tie" in verdict_sentence(det, 15)


class TestCumulativeCurves:
    def test_net_curves_reconcile_to_total_pv_and_paid_is_gross(self):
        spec = _spec()
        det = compute_deterministic(spec)
        curves = _cumulative_cost_curves(spec)
        for key in ("rent", "condo", "house"):
            net = curves[key]["net"]
            paid = curves[key]["paid"]
            expected = getattr(det, key).total_pv
            assert net[-1] == pytest.approx(expected, rel=1e-9)
            assert len(net) == spec.simulation.years + 1
            assert len(paid) == spec.simulation.years + 1
            # paid excludes only the end-of-horizon credit, so it never dips
            # below net at any point along the race
            assert all(p >= nv - 1e-6 for p, nv in zip(paid, net))
            assert paid[0] >= 0

    def test_crossover_detection_on_synthetic_curves(self):
        curves = {
            "rent": [0, 100, 200, 300],
            "house": [50, 150, 210, 290],  # overtakes rent between year 2 and 3
        }
        crossovers = find_crossovers(curves)
        assert crossovers == [(3, "rent", "house")]

    def test_no_crossover_when_leader_stable(self):
        curves = {"rent": [0, 10, 20], "house": [100, 200, 300]}
        assert find_crossovers(curves) == []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

EXPECTED_STEMS = [
    "act1_the_answer",
    "act2_the_race",
    "act3_the_uncertainty",
    "act4_home_futures",
    "act5_demographic_signal",
]


class TestRenderDecisionStory:
    def test_full_story_renders_five_acts(self, tmp_path):
        spec = _spec(with_prior=True)
        prior = load_scenario_prior(GOLDEN_PRIOR, "MTL_RMR")
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        out = tmp_path / "story"
        saved = render_decision_story(spec, det, mc, prior=prior, out_dir=out)

        names = sorted(p.name for p in saved)
        assert names == sorted(f"{stem}.png" for stem in EXPECTED_STEMS)
        for p in saved:
            assert p.exists()
            assert p.stat().st_size > MIN_FIG_BYTES

    def test_degrades_without_mc_skips_act3_silently(self, tmp_path):
        spec = _spec(with_prior=True)
        prior = load_scenario_prior(GOLDEN_PRIOR, "MTL_RMR")
        det = compute_deterministic(spec)
        saved = render_decision_story(spec, det, None, prior=prior, out_dir=tmp_path)
        stems = {p.stem for p in saved}
        assert "act3_the_uncertainty" not in stems
        assert len(saved) == 4

    def test_degrades_without_prior_renders_act4_fallback_only(self, tmp_path):
        spec = _spec(with_prior=False)
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        saved = render_decision_story(spec, det, mc, prior=None, out_dir=tmp_path)
        stems = {p.stem for p in saved}
        assert stems == {"act1_the_answer", "act2_the_race",
                         "act3_the_uncertainty", "act4_home_futures"}
        for p in saved:
            assert p.stat().st_size > MIN_FIG_BYTES

    def test_degrades_without_mc_and_without_prior(self, tmp_path):
        spec = _spec(with_prior=False)
        det = compute_deterministic(spec)
        saved = render_decision_story(spec, det, None, prior=None, out_dir=tmp_path)
        stems = {p.stem for p in saved}
        assert stems == {"act1_the_answer", "act2_the_race", "act4_home_futures"}

    def test_act4_with_price_shock_renders_crash_overlay(self, tmp_path):
        spec = _spec(with_prior=True)
        spec.house.price_shock = PriceShockParams(
            annual_hazard=0.08, severity_mean=0.25, severity_vol=0.10,
        )
        prior = load_scenario_prior(GOLDEN_PRIOR, "MTL_RMR")
        det = compute_deterministic(spec)
        saved = render_decision_story(spec, det, None, prior=prior, out_dir=tmp_path)
        assert (tmp_path / "act4_home_futures.png").stat().st_size > MIN_FIG_BYTES
        assert len(saved) == 4  # no MC here

    def test_fmt_svg(self, tmp_path):
        spec = _spec(with_prior=False)
        det = compute_deterministic(spec)
        saved = render_decision_story(spec, det, None, prior=None,
                                      out_dir=tmp_path, fmt="svg")
        assert all(p.suffix == ".svg" and p.stat().st_size > 0 for p in saved)

    def test_requires_deterministic_result(self, tmp_path):
        spec = _spec()
        with pytest.raises(ValueError):
            render_decision_story(spec, None, None, out_dir=tmp_path)

    def test_verdict_numbers_match_rendered_result(self, tmp_path):
        """The Act 1 title must carry numbers derived from the passed results."""
        spec = _spec(with_prior=True)
        prior = load_scenario_prior(GOLDEN_PRIOR, "MTL_RMR")
        det = compute_deterministic(spec)
        render_decision_story(spec, det, None, prior=prior, out_dir=tmp_path)
        expected_title = verdict_sentence(det, spec.simulation.years)
        totals = {
            k: getattr(det, k).total_pv for k in ("rent", "condo", "house")
        }
        cheapest = min(totals, key=lambda k: totals[k])
        runner_up = sorted(totals.values())[1]
        margin = runner_up - totals[cheapest]
        display = {"rent": "Renting", "condo": "Buying a condo",
                   "house": "Buying a house"}[cheapest]
        assert expected_title == (
            f"{display} wins by ${margin:,.0f} over {spec.simulation.years} years"
        )


class TestCliWiring:
    def _write_config(self, tmp_path: Path) -> str:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            """
years: 8
discount_rate: 0.03
economic:
  mode: real
condo:
  monthly_fee: 450
  initial_value: 350000
  all_cash: true
house:
  initial_value: 400000
  value_growth_rate: 0.01
  annual_maintenance_rate: 0.012
  all_cash: true
rent:
  monthly_rent: 1900
  rent_escalation_rate: 0.03
simulation:
  num_sims: 50
  random_seed: 42
""",
            encoding="utf-8",
        )
        return str(cfg)

    def test_cli_plots_flag_renders_and_prints_paths(self, tmp_path, monkeypatch, capsys):
        config = self._write_config(tmp_path)
        plots_dir = tmp_path / "plots"
        monkeypatch.setattr(sys, "argv", ["hde", config, "--plots", str(plots_dir)])
        assert cli_main() == 0
        out = capsys.readouterr().out
        saved = sorted(plots_dir.glob("*.png"))
        # acts 1, 2, 4 — no prior loaded via this YAML; this config sets no
        # vols, so audit U3 degrades the zero-uncertainty MC like no-MC (no Act 3)
        assert len(saved) == 3
        assert all(f"Saved plot: {p}" in out for p in saved)

    def test_cli_plots_with_market_scenario_yaml(self, tmp_path, monkeypatch):
        config = tmp_path / "cfg.yaml"
        config.write_text(
            f"""
years: 6
discount_rate: 0.03
economic:
  mode: real
market_scenario:
  path: {GOLDEN_PRIOR}
  geography: MTL_RMR
house:
  initial_value: 400000
  value_growth_rate: 0.01
  annual_maintenance_rate: 0.012
  all_cash: true
rent:
  monthly_rent: 1900
simulation:
  num_sims: 50
""",
            encoding="utf-8",
        )
        plots_dir = tmp_path / "plots"
        monkeypatch.setattr(sys, "argv", ["hde", str(config), "--plots", str(plots_dir)])
        assert cli_main() == 0
        stems = {p.stem for p in plots_dir.glob("*.png")}
        assert stems == {"act1_the_answer", "act2_the_race",
                         "act3_the_uncertainty", "act4_home_futures",
                         "act5_demographic_signal"}

    def test_cli_plots_with_no_deterministic_warns(self, tmp_path, monkeypatch, capsys):
        config = self._write_config(tmp_path)
        monkeypatch.setattr(
            sys, "argv",
            ["hde", config, "--no-deterministic", "--plots", str(tmp_path / "p")],
        )
        assert cli_main() == 0
        err = capsys.readouterr().err
        assert "--no-deterministic" in err or "deterministic" in err


# --- Audit U3: zero-uncertainty MC degrades like no-MC ---

def _zero_vol_spec() -> ComparisonSpec:
    """All uncertainty inputs off: MC would produce identical paths."""
    return ComparisonSpec(
        simulation=SimulationParams(years=10, discount_rate=0.03, num_sims=25),
        economic=EconomicParams(mode="real"),
        condo=CondoParams(monthly_fee=450, initial_value=350_000, all_cash=True),
        house=HouseParams(initial_value=400_000, value_growth_rate=0.01,
                          annual_maintenance_rate=0.012, all_cash=True),
        rent=RentParams(monthly_rent=1_900, invested_down_payment=60_000),
    )


class TestSinglePathDegradation:
    def test_zero_vol_mc_skips_act3(self, tmp_path):
        spec = _zero_vol_spec()
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        saved = render_decision_story(spec, det, mc, prior=None, out_dir=tmp_path)
        stems = {p.stem for p in saved}
        assert "act3_the_uncertainty" not in stems
        assert not (tmp_path / "act3_the_uncertainty.png").exists()
        assert "act1_the_answer" in stems  # the stamped headline act still renders
        assert len(saved) == 3  # act1, act2, act4

    def test_zero_vol_mc_act1_renders(self, tmp_path):
        spec = _zero_vol_spec()
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        render_decision_story(spec, det, mc, prior=None, out_dir=tmp_path)
        assert (tmp_path / "act1_the_answer.png").stat().st_size > MIN_FIG_BYTES

    def test_voled_mc_still_renders_act3(self, tmp_path):
        spec = _spec()  # carries house/condo/rent vols
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        saved = render_decision_story(spec, det, mc, prior=None, out_dir=tmp_path)
        assert "act3_the_uncertainty" in {p.stem for p in saved}
