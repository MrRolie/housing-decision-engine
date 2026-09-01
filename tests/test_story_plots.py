"""
Story-plot tests: the six-act narrative rendering (src/hde/story_plots.py).

Covers:
  - full render against a synthetic spec + tiny MC + the golden fixture prior
  - pure computation helpers (_verdict_sentence, cumulative curves, crossovers,
    break-evens, sweeps)
  - degradation without MC / without prior / without rent-vs-owned / both
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
    _owned_at_price,
    find_break_evens,
    find_crossovers,
    market_line_sentence,
    plot_act6_the_market_line,
    render_decision_story,
    sweep_price_totals,
    sweep_rent_totals,
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

    # --- B.3 (readiness plan 2026-09-01): decisiveness is a rule, not a 50-cent epsilon ---

    def test_quarter_percent_margin_reads_as_tie(self):
        det = _det_from_pvs({"condo": 400_000.0, "rent": 401_000.0})
        sentence = verdict_sentence(det, 15)
        assert "tie" in sentence and "wins by" not in sentence
        assert "$1,000" in sentence and "0.2%" in sentence

    def test_fifteen_percent_margin_still_wins(self):
        det = _det_from_pvs({"condo": 400_000.0, "rent": 460_000.0})
        assert verdict_sentence(det, 15).startswith("Buying a condo wins by $60,000")

    def test_coin_flip_monte_carlo_is_not_a_confident_win(self):
        det = _det_from_pvs({"condo": 400_000.0, "house": 440_000.0})
        mc = ComparisonMonteCarloResult(prob_condo_cheapest=0.57, prob_house_cheapest=0.43)
        sentence = verdict_sentence(det, 20, mc=mc, num_sims=10_000)
        assert "wins by" not in sentence
        assert "57%" in sentence and "10,000" in sentence

    def test_decisive_monte_carlo_keeps_the_plain_headline(self):
        det = _det_from_pvs({"condo": 400_000.0, "house": 440_000.0})
        mc = ComparisonMonteCarloResult(prob_condo_cheapest=0.81, prob_house_cheapest=0.19)
        assert verdict_sentence(det, 20, mc=mc, num_sims=5_000) == "Buying a condo wins by $40,000 over 20 years"


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
    "act6_the_market_line",
]


class TestRenderDecisionStory:
    def test_full_story_renders_six_acts(self, tmp_path):
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
        assert len(saved) == 5

    def test_degrades_without_prior_renders_act4_fallback_only(self, tmp_path):
        spec = _spec(with_prior=False)
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        saved = render_decision_story(spec, det, mc, prior=None, out_dir=tmp_path)
        stems = {p.stem for p in saved}
        assert stems == {"act1_the_answer", "act2_the_race",
                         "act3_the_uncertainty", "act4_home_futures",
                         "act6_the_market_line"}
        for p in saved:
            assert p.stat().st_size > MIN_FIG_BYTES

    def test_degrades_without_mc_and_without_prior(self, tmp_path):
        spec = _spec(with_prior=False)
        det = compute_deterministic(spec)
        saved = render_decision_story(spec, det, None, prior=None, out_dir=tmp_path)
        stems = {p.stem for p in saved}
        assert stems == {"act1_the_answer", "act2_the_race", "act4_home_futures",
                         "act6_the_market_line"}

    def test_act4_with_price_shock_renders_crash_overlay(self, tmp_path):
        spec = _spec(with_prior=True)
        spec.house.price_shock = PriceShockParams(
            annual_hazard=0.08, severity_mean=0.25, severity_vol=0.10,
        )
        prior = load_scenario_prior(GOLDEN_PRIOR, "MTL_RMR")
        det = compute_deterministic(spec)
        saved = render_decision_story(spec, det, None, prior=prior, out_dir=tmp_path)
        assert (tmp_path / "act4_home_futures.png").stat().st_size > MIN_FIG_BYTES
        assert len(saved) == 5  # no MC here: acts 1, 2, 4, 5, 6

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
        # acts 1, 2, 4, 6 — no prior loaded via this YAML; this config sets no
        # vols, so audit U3 degrades the zero-uncertainty MC like no-MC (no Act 3)
        assert len(saved) == 4
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
                         "act5_demographic_signal", "act6_the_market_line"}

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
        assert len(saved) == 4  # act1, act2, act4, act6

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


# ---------------------------------------------------------------------------
# Act 6: the market line (break-even sensitivity to the quoted amounts)
# ---------------------------------------------------------------------------

class TestFindBreakEvens:
    def test_crossing_at_grid_point(self):
        xs = [1, 2, 3, 4]
        ya = [10, 8, 6, 4]
        yb = [4, 5, 6, 7]
        # ya - yb: 6, 3, 0, -3 — equal exactly at x=3
        assert find_break_evens(xs, ya, yb) == [3.0]

    def test_interpolates_between_grid_points(self):
        xs = [0.0, 1.0]
        ya = [10.0, 0.0]
        yb = [0.0, 10.0]
        assert find_break_evens(xs, ya, yb) == pytest.approx([0.5])

    def test_no_crossing(self):
        assert find_break_evens([1, 2, 3], [5, 4, 3], [9, 8, 7]) == []


class TestSweepHelpers:
    def test_owned_at_price_holds_down_payment_fraction(self):
        params = HouseParams(
            initial_value=500_000, down_payment=100_000,
            mortgage_rate=0.05, mortgage_term_years=25,
        )
        re_priced = _owned_at_price(params, 600_000)
        assert re_priced.initial_value == 600_000
        assert re_priced.down_payment == pytest.approx(120_000)  # 20% held

    def test_owned_at_price_all_cash_scales_value_only(self):
        params = HouseParams(initial_value=500_000, all_cash=True)
        re_priced = _owned_at_price(params, 400_000)
        assert re_priced.initial_value == 400_000
        assert re_priced.down_payment is None

    def test_sweep_rent_totals_rent_rises_owned_flat(self):
        spec = _spec()
        totals = sweep_rent_totals(spec, [1_000.0, 2_000.0])
        assert totals["rent"][1] > totals["rent"][0]
        assert totals["condo"][0] == totals["condo"][1]
        assert totals["house"][0] == totals["house"][1]

    def test_sweep_price_totals_swept_moves_others_flat(self):
        spec = _spec()
        xs = [spec.condo.initial_value * 0.8, spec.condo.initial_value * 1.2]
        totals = sweep_price_totals(spec, "condo", xs)
        assert totals["condo"][1] != totals["condo"][0]
        assert totals["rent"][0] == totals["rent"][1]
        assert totals["house"][0] == totals["house"][1]


class TestAct6MarketLine:
    def test_renders_with_rent_and_owned(self, tmp_path):
        spec = _spec()
        det = compute_deterministic(spec)
        path = plot_act6_the_market_line(spec, det, "png", tmp_path)
        assert path.name == "act6_the_market_line.png"
        assert path.stat().st_size > MIN_FIG_BYTES

    def test_requires_rent_option(self, tmp_path):
        spec = _spec()
        spec.rent = None
        det = compute_deterministic(spec)
        with pytest.raises(ValueError):
            plot_act6_the_market_line(spec, det, "png", tmp_path)

    def test_requires_owned_option(self, tmp_path):
        spec = _spec()
        spec.condo = None
        spec.house = None
        det = compute_deterministic(spec)
        with pytest.raises(ValueError):
            plot_act6_the_market_line(spec, det, "png", tmp_path)

    def test_market_line_sentence_names_a_rent_level_or_range(self):
        spec = _spec()
        det = compute_deterministic(spec)
        sentence = market_line_sentence(spec, det)
        assert ("$/mo" in sentence) or ("range" in sentence) or ("/mo" in sentence)
