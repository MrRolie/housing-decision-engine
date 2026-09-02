"""
S4b market-scenario slot tests.

Covers the ScenarioPrior loader/validator contract (demoflow spec §7(a) as
ratified by docs/specs/2026-08-26-s4b-demographic-input-slot-sketch.md):
one broken variant per refusal rule, determinism, byte-identical default-off
behavior, and the additive-composition arithmetic.
"""

import copy
import hashlib
import json

import numpy as np
import pytest

from hde.config import ConfigValidationError, load_config_dict
from hde.deterministic import compute_deterministic
from hde.market_scenario import (
    DRIFT_SIGMA_DIVISOR,
    HORIZON_YEARS,
    SCENARIOS,
    ScenarioPriorError,
    band_drift,
    band_horizon_for_calendar_year,
    calendar_year_for_sim_year,
    load_scenario_prior,
)
from hde.monte_carlo import (
    _apply_price_shock,
    run_monte_carlo,
)
from hde.models import (
    ComparisonSpec,
    CondoParams,
    EconomicParams,
    HouseParams,
    PriceShockParams,
    SimulationParams,
    MarketScenario,
)

GEO = "MTL_RMR"
OTHER_GEO = "QC_RMR"


def _row(geo=GEO, dwelling="condo", horizon=2030, scenario="reference",
         mean=0.0100, p10=0.0000, p90=0.051264, tilt=1.0, flags=None, edf=0.004):
    if flags is None:
        flags = ["never_relax_stress"] if tilt < 1.0 else []
    return {
        "geography": geo,
        "dwelling_type": dwelling,
        "horizon_year": horizon,
        "scenario": scenario,
        "demo_drift_mean": mean,
        "demo_drift_p10": p10,
        "demo_drift_p90": p90,
        "drawdown_weight_tilt": tilt,
        "excess_demand_rate": edf,
        "flags": flags,
    }


def _valid_prior(geographies=(GEO,), **kwargs):
    rows = []
    for g in geographies:
        for d in ("condo", "house"):
            for h in HORIZON_YEARS:
                for s in SCENARIOS:
                    # low-scenario rows carry the stress guard flag, mirroring the emitter
                    kwargs_row = dict(kwargs)
                    if s == "low":
                        kwargs_row.setdefault("tilt", 0.7)
                    rows.append(_row(geo=g, dwelling=d, horizon=h, scenario=s, **kwargs_row))
    return {
        "schema_version": "1",
        "mapping_version": "linear-through-origin-v0",
        "data_vintage": {
            "isq_edition": "A2026",
            "census_year": 2021,
            "constants_as_of": "2026-07-21",
            "source_hashes": {"98-10-0621-01": {
                "sha256": "a" * 64, "extracted_at": "2026-07-21T00:00:00Z"}},
        },
        "assumptions_hash": "abc123",
        "run_pairing": {"pairing_token": "test-token", "content_sha256": "b" * 64},
        "schema": "demoflow.scenario_prior.v1",
        "scenario_priors": rows,
    }


def _write_prior(tmp_path, data, name="prior.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _write_raw(tmp_path, text, name="prior_nan.json"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Loader / validator
# ---------------------------------------------------------------------------

class TestLoaderValid:
    def test_valid_load_returns_rows_and_sha256(self, tmp_path):
        data = _valid_prior()
        path = _write_prior(tmp_path, data)
        prior = load_scenario_prior(path, GEO)
        assert len(prior.rows) == 2 * len(HORIZON_YEARS) * len(SCENARIOS)
        raw = open(path, "rb").read()
        assert prior.file_sha256 == hashlib.sha256(raw).hexdigest()
        assert prior.schema_version == "1"
        assert prior.assumptions_hash == "abc123"
        assert prior.geography == GEO
        block = prior.provenance_block()
        assert set(block.keys()) == {
            "file_sha256", "assumptions_hash", "geography", "schema_version",
            "mapping_version", "isq_edition", "census_year", "constants_as_of",
            "start_calendar_year", "horizon_years", "source_keys", "encoded_drift",
        }

    def test_geography_filter_ignores_other_rows(self, tmp_path):
        path = _write_prior(tmp_path, _valid_prior(geographies=(GEO, OTHER_GEO)))
        prior = load_scenario_prior(path, OTHER_GEO)
        assert all(r.geography == OTHER_GEO for r in prior.rows.values())
        assert len(prior.rows) == 2 * len(HORIZON_YEARS) * len(SCENARIOS)


class TestLoaderRefusals:
    def test_unknown_row_field(self, tmp_path):
        data = _valid_prior()
        data["scenario_priors"][7]["crash_probability"] = 0.3
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="crash_probability"):
            load_scenario_prior(path, GEO)

    def test_unknown_top_level_field(self, tmp_path):
        data = _valid_prior()
        data["forecast"] = True
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="unknown top-level"):
            load_scenario_prior(path, GEO)

    def test_bad_flag_string(self, tmp_path):
        data = _valid_prior()
        data["scenario_priors"][3]["flags"] = ["never_relax_stress", "value_bearing_opinion"]
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="closed enum"):
            load_scenario_prior(path, GEO)

    def test_missing_cartesian_member(self, tmp_path):
        data = _valid_prior()
        removed = data["scenario_priors"].pop(11)
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError) as excinfo:
            load_scenario_prior(path, GEO)
        msg = str(excinfo.value)
        assert "missing Cartesian row" in msg
        assert removed["horizon_year"] and removed["scenario"] in msg

    def test_duplicate_row(self, tmp_path):
        data = _valid_prior()
        data["scenario_priors"].append(copy.deepcopy(data["scenario_priors"][5]))
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="duplicates"):
            load_scenario_prior(path, GEO)

    def test_inverted_band(self, tmp_path):
        data = _valid_prior(mean=0.9, p10=0.0, p90=0.051264)
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="band ordering"):
            load_scenario_prior(path, GEO)

    def test_mean_above_p90(self, tmp_path):
        data = _valid_prior(p90=0.005)
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="band ordering"):
            load_scenario_prior(path, GEO)

    def test_negative_tilt(self, tmp_path):
        data = _valid_prior(tilt=-0.1, flags=["never_relax_stress"])
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="drawdown_weight_tilt must be >= 0"):
            load_scenario_prior(path, GEO)

    def test_nan_literal(self, tmp_path):
        # Python's json.dumps CAN emit NaN; the emitter contract forbids it
        # (allow_nan=False) and the loader must refuse it.
        data = json.dumps(_valid_prior()).replace("0.051264", "NaN", 1)
        path = _write_raw(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="NaN"):
            load_scenario_prior(path, GEO)

    def test_tilt_below_one_requires_never_relax_stress_flag(self, tmp_path):
        data = _valid_prior(tilt=0.7, flags=[])
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="never_relax_stress"):
            load_scenario_prior(path, GEO)

    def test_unknown_geography_value_in_row(self, tmp_path):
        data = _valid_prior()
        data["scenario_priors"][2]["geography"] = "TORONTO_CMA"
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="TORONTO_CMA"):
            load_scenario_prior(path, GEO)

    def test_unknown_dwelling_type(self, tmp_path):
        data = _valid_prior()
        data["scenario_priors"][2]["dwelling_type"] = "plex"
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="dwelling_type"):
            load_scenario_prior(path, GEO)

    def test_unknown_scenario_value(self, tmp_path):
        data = _valid_prior()
        data["scenario_priors"][2]["scenario"] = "central"
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="scenario"):
            load_scenario_prior(path, GEO)

    def test_unknown_horizon_year(self, tmp_path):
        data = _valid_prior()
        data["scenario_priors"][2]["horizon_year"] = 2032
        path = _write_prior(tmp_path, data)
        with pytest.raises(ScenarioPriorError, match="horizon_year"):
            load_scenario_prior(path, GEO)

    def test_missing_file(self, tmp_path):
        with pytest.raises(ScenarioPriorError, match="not found"):
            load_scenario_prior(str(tmp_path / "nope.json"), GEO)


class TestGeographyMatchRule:
    def test_requested_geography_must_match_at_least_one_row(self, tmp_path):
        path = _write_prior(tmp_path, _valid_prior())
        with pytest.raises(ScenarioPriorError, match=OTHER_GEO):
            load_scenario_prior(path, OTHER_GEO)


class TestTimeAnchorCrossCheck:
    """Prior-vs-constant alignment: constants_as_of within +/- 1 year of
    START_CALENDAR_YEAR loads; beyond it the band mapping is misaligned and
    the loader refuses rather than silently banding every sim year wrong."""

    def test_constants_as_of_one_year_off_loads(self, tmp_path):
        data = _valid_prior()
        data["data_vintage"]["constants_as_of"] = "2027-06-01"
        prior = load_scenario_prior(_write_prior(tmp_path, data), GEO)
        assert prior.data_vintage["constants_as_of"] == "2027-06-01"

    @pytest.mark.parametrize("as_of", ["2028-01-01", "2024", "2020-Q3"])
    def test_constants_as_of_two_plus_years_off_raises_naming_both_years(self, tmp_path, as_of):
        data = _valid_prior()
        data["data_vintage"]["constants_as_of"] = as_of
        with pytest.raises(ScenarioPriorError) as excinfo:
            load_scenario_prior(_write_prior(tmp_path, data), GEO)
        msg = str(excinfo.value)
        assert as_of[:4] in msg
        assert "2026" in msg
        assert "misaligned" in msg

    def test_constants_as_of_without_leading_four_digit_year_raises(self, tmp_path):
        data = _valid_prior()
        data["data_vintage"]["constants_as_of"] = "const-2026"
        with pytest.raises(ScenarioPriorError, match="constants_as_of"):
            load_scenario_prior(_write_prior(tmp_path, data), GEO)


# ---------------------------------------------------------------------------
# Banding + additive composition arithmetic
# ---------------------------------------------------------------------------

class TestBandsAndDrift:
    @pytest.mark.parametrize("sim_year,expected_band", [
        (1, 2030), (4, 2030),   # years 1..(2030-2026) -> 2030 band
        (5, 2035), (9, 2035),
        (10, 2040), (19, 2045), (20, 2050),  # 2026+20=2046 -> 2050 band
        (24, 2050),
        (25, 2050), (40, 2050),  # last declared band holds to the horizon end
    ])
    def test_piecewise_constant_band_selection(self, sim_year, expected_band):
        assert calendar_year_for_sim_year(sim_year) == 2026 + sim_year
        assert band_horizon_for_calendar_year(calendar_year_for_sim_year(sim_year)) == expected_band

    def test_additive_drift_hand_computed_for_known_band(self):
        # Pinned example: sigma = (p90 - p10) / 2.5632 = (0.051264 - 0.0)/2.5632 = 0.02;
        # z = 1.5 -> drift = mean + z * sigma = 0.01 + 0.03 = 0.04 exactly.
        row = _row()
        from hde.market_scenario import ScenarioPriorRow
        parsed = ScenarioPriorRow(
            geography=row["geography"], dwelling_type=row["dwelling_type"],
            horizon_year=row["horizon_year"], scenario=row["scenario"],
            demo_drift_mean=row["demo_drift_mean"], demo_drift_p10=row["demo_drift_p10"],
            demo_drift_p90=row["demo_drift_p90"],
            drawdown_weight_tilt=row["drawdown_weight_tilt"],
            excess_demand_rate=row["excess_demand_rate"], flags=(),
        )
        assert parsed.drift_sigma == pytest.approx(0.02)
        assert DRIFT_SIGMA_DIVISOR == pytest.approx(2 * 1.2816)
        assert band_drift(parsed, z=1.5) == pytest.approx(0.04)
        assert band_drift(parsed, z=-1.0) == pytest.approx(-0.01)


# ---------------------------------------------------------------------------
# Engine composition
# ---------------------------------------------------------------------------

def _spec(market_scenario=None, condo_price_shock=None, house_price_shock=None,
          num_sims=30, seed=7, econ=None):
    condo = CondoParams(
        monthly_fee=400, initial_value=300_000, value_growth_rate=0.02,
        down_payment=60_000, mortgage_rate=0.04, mortgage_term_years=25,
        price_shock=condo_price_shock,
    )
    house = HouseParams(
        initial_value=400_000, annual_maintenance_rate=0.015, value_growth_rate=0.02,
        down_payment=80_000, mortgage_rate=0.04, mortgage_term_years=25,
        price_shock=house_price_shock,
    )
    sim = SimulationParams(years=10, discount_rate=0.03, num_sims=num_sims, random_seed=seed)
    return ComparisonSpec(
        simulation=sim,
        economic=econ or EconomicParams(),
        condo=condo, house=house,
        market_scenario=market_scenario,
    )


class TestByteIdenticalDefaultOff:
    GOLDEN_CONDO_SUM = 5029205.9929277925
    GOLDEN_HOUSE_SUM = 6764553.176467273

    def test_no_prior_no_shock_matches_pre_s4b_output(self):
        """Pinned against the pre-S4b tree: absent slots consume zero rng draws."""
        result = run_monte_carlo(_spec(num_sims=50))
        assert float(result.condo.pvs.sum()) == self.GOLDEN_CONDO_SUM
        assert float(result.house.pvs.sum()) == self.GOLDEN_HOUSE_SUM
        assert result.market_scenario is None


class TestMCComposition:
    def test_same_seed_same_prior_is_deterministic(self, tmp_path):
        path = _write_prior(tmp_path, _valid_prior())
        ms = MarketScenario(path=path, geography=GEO)
        r1 = run_monte_carlo(_spec(market_scenario=ms))
        r2 = run_monte_carlo(_spec(market_scenario=ms))
        np.testing.assert_array_equal(r1.condo.pvs, r2.condo.pvs)
        np.testing.assert_array_equal(r1.house.pvs, r2.house.pvs)

    def test_prior_changes_output_and_stamps_provenance(self, tmp_path):
        path = _write_prior(tmp_path, _valid_prior())
        baseline = run_monte_carlo(_spec())
        loaded = run_monte_carlo(_spec(market_scenario=MarketScenario(path=path, geography=GEO)))
        assert not np.array_equal(baseline.condo.pvs, loaded.condo.pvs)
        assert not np.array_equal(baseline.house.pvs, loaded.house.pvs)
        block = loaded.market_scenario
        assert block is not None
        assert block["geography"] == GEO
        assert block["file_sha256"]
        assert block["assumptions_hash"] == "abc123"

    def test_zero_drift_prior_leaves_growth_unchanged_but_provenance_present(self, tmp_path):
        # A prior whose bands say exactly the user's own view (drift 0 everywhere)
        # changes only the rng stream, not the drift level.
        path = _write_prior(tmp_path, _valid_prior(
            mean=0.0, p10=0.0, p90=0.0, tilt=1.0))
        loaded = run_monte_carlo(_spec(market_scenario=MarketScenario(path=path, geography=GEO)))
        assert loaded.condo.pvs.shape == (30,)
        assert loaded.market_scenario is not None


class TestNominalModeComposesThePrior:
    """The refusal of a prior in nominal mode was lifted 2026-09-02: the drift
    is a REAL rate and composes with inflation exactly like value_growth_rate
    (a financed buyer runs nominal mode for the lender's payment and must still
    be able to check the shipped prior)."""

    def test_nominal_run_with_prior_is_accepted_by_both_engines(self, tmp_path):
        path = _write_prior(tmp_path, _valid_prior())
        spec = _spec(
            market_scenario=MarketScenario(path=path, geography=GEO),
            econ=EconomicParams(mode="nominal", inflation_rate=0.021),
        )
        mc = run_monte_carlo(spec)
        assert mc.market_scenario is not None and mc.market_scenario["geography"] == GEO
        assert compute_deterministic(spec).market_scenario is not None

    def test_zero_inflation_nominal_equals_real_and_inflation_moves_it(self, tmp_path):
        path = _write_prior(tmp_path, _valid_prior())
        ms = MarketScenario(path=path, geography=GEO)
        real = run_monte_carlo(_spec(market_scenario=ms, econ=EconomicParams(mode="real")))
        nominal0 = run_monte_carlo(_spec(market_scenario=ms,
                                         econ=EconomicParams(mode="nominal", inflation_rate=0.0)))
        nominal = run_monte_carlo(_spec(market_scenario=ms,
                                        econ=EconomicParams(mode="nominal", inflation_rate=0.021)))
        # Composition with zero inflation is the identity: the prior path is mode-agnostic.
        assert np.allclose(real.condo.pvs, nominal0.condo.pvs)
        assert not np.allclose(real.condo.pvs, nominal.condo.pvs)


class TestPriceShockChannel:
    def test_apply_price_shock_full_hazard_exact_haircut(self):
        # hazard=1 fires every year; severity_vol=0 collapses the lognormal
        # machinery to its mean: exactly a 20% haircut per firing year.
        rng = np.random.default_rng(0)
        track = [100.0]
        _apply_price_shock(track, PriceShockParams(annual_hazard=1.0, severity_mean=0.2, severity_vol=0.0), 1.0, rng)
        assert track[0] == pytest.approx(80.0)

    def test_tilt_scales_the_hazard(self):
        # hazard 1.0 x tilt 0.0 never fires: track untouched, no draw consumed.
        rng = np.random.default_rng(0)
        track = [100.0]
        _apply_price_shock(track, PriceShockParams(annual_hazard=1.0, severity_mean=0.2, severity_vol=0.0), 0.0, rng)
        assert track[0] == 100.0

    def test_shock_hits_both_house_tracks(self, tmp_path):
        rng = np.random.default_rng(0)
        house_value = 400_000.0
        terminal_value = 400_000.0
        tracks = [house_value, terminal_value]
        _apply_price_shock(tracks, PriceShockParams(annual_hazard=1.0, severity_mean=0.2, severity_vol=0.0), 1.0, rng)
        assert tracks[0] == pytest.approx(320_000.0)
        assert tracks[1] == pytest.approx(320_000.0)

    def test_default_off_shock_is_byte_identical(self):
        result = run_monte_carlo(_spec(house_price_shock=None, num_sims=50))
        assert float(result.house.pvs.sum()) == TestByteIdenticalDefaultOff.GOLDEN_HOUSE_SUM

    def test_enabled_shock_changes_house_pv(self):
        shocked = run_monte_carlo(_spec(
            house_price_shock=PriceShockParams(annual_hazard=0.15)))
        unshocked = run_monte_carlo(_spec())
        assert not np.array_equal(shocked.house.pvs, unshocked.house.pvs)


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------

class TestConfigWiring:
    def _base_config(self):
        return {
            "years": 10,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "value_growth_rate": 0.02,
                      "all_cash": True},
            "house": {"initial_value": 400_000, "annual_maintenance_rate": 0.015,
                      "all_cash": True},
        }

    def test_market_scenario_block_parses(self):
        cfg = self._base_config()
        cfg["market_scenario"] = {"path": "/tmp/prior.json", "geography": "MTL_RMR"}
        spec = load_config_dict(cfg)
        assert spec.market_scenario.path == "/tmp/prior.json"
        assert spec.market_scenario.geography == "MTL_RMR"

    def test_market_scenario_missing_geography_raises(self):
        cfg = self._base_config()
        cfg["market_scenario"] = {"path": "/tmp/prior.json"}
        with pytest.raises(ConfigValidationError, match="geography"):
            load_config_dict(cfg)

    def test_price_shock_blocks_parse_with_defaults_off_values(self):
        cfg = self._base_config()
        cfg["condo"]["price_shock"] = {"annual_hazard": 0.03}
        spec = load_config_dict(cfg)
        assert spec.condo.price_shock.annual_hazard == 0.03
        assert spec.condo.price_shock.severity_mean == pytest.approx(0.25)  # TREB 1989–96 anchor
        assert spec.condo.price_shock.severity_vol == pytest.approx(0.10)
        assert spec.house.price_shock is None

    def test_end_to_end_config_with_prior(self, tmp_path):
        path = _write_prior(tmp_path, _valid_prior(), name="e2e.json")
        cfg = self._base_config()
        cfg["market_scenario"] = {"path": path, "geography": GEO}
        spec = load_config_dict(cfg)
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        assert det.market_scenario["file_sha256"] == mc.market_scenario["file_sha256"]


# --- cross-repo golden: the REAL emitter output, pinned ----------------------
# This file is demoflow's actual run output (committed from its artifacts),
# not a hand-built doc. If either side's contract drifts, THIS goes red first.
def test_real_emitted_artifact_loads_and_filters():
    from pathlib import Path
    golden = Path(__file__).parent / "fixtures" / "scenario_prior_golden.json"
    ms = load_scenario_prior(str(golden), geography="MTL_RMR")
    assert len(ms.rows) == 15                     # 5 horizons x 3 scenarios
    assert len(ms.rows_for_dwelling("condo")) == 15
    row = ms.rows[("all", 2030, "reference")]
    assert 0.0 < row.demo_drift_mean < 0.02       # plausible demographic tilt
    assert row.demo_drift_p10 <= row.demo_drift_mean <= row.demo_drift_p90


def test_real_emitted_artifact_refuses_unknown_geography():
    from pathlib import Path
    import pytest
    golden = Path(__file__).parent / "fixtures" / "scenario_prior_golden.json"
    with pytest.raises(ScenarioPriorError, match="matches no row"):
        load_scenario_prior(str(golden), geography="NOWHERE_RMR")
