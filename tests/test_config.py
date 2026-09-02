"""
Tests for configuration loading.
"""

import pytest
import tempfile
from pathlib import Path
import yaml

from hde.config import (
    load_config,
    load_config_dict,
    coherence_warnings,
    single_path_run,
    ConfigValidationError,
)


class TestLoadConfigFromFile:
    """Tests for loading config from YAML files."""
    
    def test_load_basic_config(self):
        """Test loading a basic configuration."""
        config_data = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 400,
                "initial_value": 300_000,
                "all_cash": True,
            },
            "house": {
                "initial_value": 400000,
                "all_cash": True,
            },
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            spec = load_config(config_path)

            assert spec.condo.monthly_fee == 400
            assert spec.house.initial_value == 400000
            assert spec.simulation.years == 20
            assert spec.simulation.discount_rate == 0.03
        finally:
            Path(config_path).unlink()
    
    def test_load_config_with_all_fields(self):
        """Test loading a complete configuration."""
        config_data = {
            "years": 25,
            "discount_rate": 0.035,
            "economic": {
                "mode": "real",
                "inflation_rate": 0.025,
            },
            "condo": {
                "monthly_fee": 550,
                "fee_escalation_rate": 0.02,
                "initial_value": 350_000,
                "all_cash": True,
                "events": [
                    {
                        "name": "assessment",
                        "base_cost": 5000,
                        "expected_year": 10,
                        "timing_std_years": 2,
                        "cost_vol": 0.20,
                    }
                ],
                "other_recurring_costs": [
                    {
                        "name": "insurance",
                        "annual_amount": 600,
                        "escalation_rate": 0.02,
                    }
                ],
            },
            "house": {
                "initial_value": 500000,
                "value_growth_rate": 0.02,
                "annual_maintenance_rate": 0.015,
                "all_cash": True,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        "expected_year": 20,
                    }
                ],
            },
            "simulation": {
                "num_sims": 5000,
                "random_seed": 123,
                "house_maintenance_vol": 0.25,
                "condo_fee_vol": 0.08,
            },
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            spec = load_config(config_path)

            assert spec.condo.monthly_fee == 550
            assert spec.condo.fee_escalation_rate == 0.02
            assert len(spec.condo.events) == 1
            assert spec.condo.events[0].name == "assessment"
            assert len(spec.condo.other_recurring_costs) == 1

            assert spec.house.initial_value == 500000
            assert spec.house.value_growth_rate == 0.02
            assert len(spec.house.events) == 1

            assert spec.simulation.num_sims == 5000
            assert spec.simulation.random_seed == 123
            assert spec.simulation.house_maintenance_vol == 0.25

            assert spec.economic.mode == "real"
            assert spec.economic.inflation_rate == 0.025
        finally:
            Path(config_path).unlink()
    
    def test_file_not_found(self):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")


class TestLoadConfigDict:
    """Tests for loading config from dictionary."""
    
    def test_load_from_dict(self):
        """Test loading configuration from dictionary."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True},
            "house": {"initial_value": 400000, "all_cash": True},
        }

        spec = load_config_dict(config)

        assert spec.condo.monthly_fee == 400
        assert spec.house.initial_value == 400000

    def test_defaults_applied(self):
        """Test that default values are applied."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True},
            "house": {"initial_value": 400000, "all_cash": True},
        }

        spec = load_config_dict(config)

        # Check defaults
        assert spec.condo.fee_escalation_rate == 0.0
        assert spec.house.value_growth_rate == 0.0
        assert spec.house.annual_maintenance_rate == 0.0
        assert spec.simulation.num_sims == 10000
        assert spec.simulation.random_seed == 42
        assert spec.economic.mode == "real"


class TestValidation:
    """Tests for configuration validation."""
    
    def test_missing_years(self):
        """Test that missing years raises error."""
        config = {
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="years"):
            load_config_dict(config)
    
    def test_missing_discount_rate_defaults_to_the_anchor(self):
        """discount_rate is optional since 2026-09-02: it defaults to the anchored
        investment return and is echoed under defaults applied."""
        from hde.anchors import ANCHORS
        config = {
            "years": 20,
            "condo": {"monthly_fee": 400, "initial_value": 400000, "all_cash": True},
        }
        spec = load_config_dict(config)
        assert spec.simulation.discount_rate == ANCHORS["simulation.discount_rate"].value
        assert "simulation.discount_rate" in spec.defaults_applied
    
    def test_missing_condo(self):
        """Test that a house-only config (no condo) is now valid."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "house": {"initial_value": 400000, "all_cash": True},
        }
        spec = load_config_dict(config)
        assert spec.condo is None
        assert spec.house.initial_value == 400000

    def test_missing_house(self):
        """Test that a condo-only config (no house) is now valid."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True},
        }
        spec = load_config_dict(config)
        assert spec.house is None
        assert spec.condo.monthly_fee == 400
    
    def test_invalid_years(self):
        """Test that invalid years raises error."""
        config = {
            "years": 0,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="years"):
            load_config_dict(config)
    
    def test_negative_discount_rate(self):
        """Test that negative discount_rate raises error."""
        config = {
            "years": 20,
            "discount_rate": -0.01,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="discount_rate"):
            load_config_dict(config)
    
    def test_invalid_economic_mode(self):
        """Test that invalid economic mode raises error."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "economic": {"mode": "invalid"},
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="mode"):
            load_config_dict(config)


class TestEventParsing:
    """Tests for event configuration parsing."""
    
    def test_event_with_all_fields(self):
        """Test parsing event with all fields specified."""
        config = {
            "years": 25,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True},
            "house": {
                "initial_value": 400000,
                "all_cash": True,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        "expected_year": 20,
                        "timing_std_years": 3,
                        "min_year": 15,
                        "max_year": 25,
                        "cost_vol": 0.25,
                    }
                ],
            },
        }
        
        spec = load_config_dict(config)

        event = spec.house.events[0]
        assert event.name == "roof"
        assert event.base_cost == 15000
        assert event.expected_year == 20
        assert event.timing_std_years == 3
        assert event.min_year == 15
        assert event.max_year == 25
        assert event.cost_vol == 0.25

    def test_event_with_defaults(self):
        """Test parsing event with only required fields."""
        config = {
            "years": 25,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True},
            "house": {
                "initial_value": 400000,
                "all_cash": True,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        "expected_year": 20,
                    }
                ],
            },
        }

        spec = load_config_dict(config)

        event = spec.house.events[0]
        assert event.timing_std_years == 0.0
        assert event.min_year == 1
        assert event.max_year is None
        assert event.cost_vol == 0.0
        assert event.timing_model == "jitter"
        assert event.cost_distribution == "lognormal"

    def test_parse_maintenance_curve_and_reserves(self):
        """Test parsing maintenance_curve and reserve fields."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 500,
                "initial_value": 300_000,
                "all_cash": True,
                "reserve_contribution_rate": 0.1,
                "reserve_initial_balance": 1000,
                "reserve_growth_rate": 0.02,
            },
            "house": {
                "initial_value": 300_000,
                "all_cash": True,
                "maintenance_curve": [
                    {"year": 1, "rate": 0.01},
                    {"year": 10, "rate": 0.02},
                ],
            },
        }

        spec = load_config_dict(config)

        assert spec.condo.reserve_contribution_rate == 0.1
        assert spec.condo.reserve_initial_balance == 1000
        assert spec.condo.reserve_growth_rate == 0.02
        assert spec.house.maintenance_curve == [(1, 0.01), (10, 0.02)]
    
    def test_event_missing_required_field(self):
        """Test that event missing required field raises error."""
        config = {
            "years": 25,
            "discount_rate": 0.03,
            "condo": {"monthly_fee": 400},
            "house": {
                "initial_value": 400000,
                "events": [
                    {
                        "name": "roof",
                        "base_cost": 15000,
                        # missing expected_year
                    }
                ],
            },
        }
        
        with pytest.raises(ConfigValidationError, match="expected_year"):
            load_config_dict(config)


class TestRecurringCostParsing:
    """Tests for recurring other cost parsing."""
    
    def test_recurring_cost_with_all_fields(self):
        """Test parsing recurring cost with all fields."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 400,
                "initial_value": 300_000,
                "all_cash": True,
                "other_recurring_costs": [
                    {
                        "name": "insurance",
                        "annual_amount": 1000,
                        "escalation_rate": 0.02,
                    }
                ],
            },
            "house": {"initial_value": 400000, "all_cash": True},
        }
        
        spec = load_config_dict(config)

        cost = spec.condo.other_recurring_costs[0]
        assert cost.name == "insurance"
        assert cost.annual_amount == 1000
        assert cost.escalation_rate == 0.02
    
    def test_recurring_cost_with_defaults(self):
        """Test parsing recurring cost with default escalation."""
        config = {
            "years": 20,
            "discount_rate": 0.03,
            "condo": {
                "monthly_fee": 400,
                "initial_value": 300_000,
                "all_cash": True,
                "other_recurring_costs": [
                    {
                        "name": "insurance",
                        "annual_amount": 1000,
                    }
                ],
            },
            "house": {"initial_value": 400000, "all_cash": True},
        }
        
        spec = load_config_dict(config)

        cost = spec.condo.other_recurring_costs[0]
        assert cost.escalation_rate == 0.0


class TestComparisonSpecReturn:
    """load_config_dict returns ComparisonSpec."""

    def test_load_returns_comparison_spec(self):
        from hde.models import ComparisonSpec
        config = {
            "years": 10, "discount_rate": 0.05,
            "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": True},
            "house": {"initial_value": 300_000, "all_cash": True},
        }
        spec = load_config_dict(config)
        assert isinstance(spec, ComparisonSpec)
        assert spec.condo.monthly_fee == 500
        assert spec.house.initial_value == 300_000
        assert spec.simulation.years == 10
        assert spec.economic.mode == "real"

    def test_load_rent_only_config(self):
        from hde.models import ComparisonSpec
        config = {
            "years": 10, "discount_rate": 0.05,
            "rent": {"monthly_rent": 2000},
        }
        spec = load_config_dict(config)
        assert isinstance(spec, ComparisonSpec)
        assert spec.rent.monthly_rent == 2000
        assert spec.condo is None
        assert spec.house is None

    def test_all_none_options_raises(self):
        config = {"years": 10, "discount_rate": 0.05}
        with pytest.raises(ConfigValidationError):
            load_config_dict(config)

    def test_rent_params_parsed_correctly(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "rent": {
                "monthly_rent": 2500,
                "rent_escalation_rate": 0.04,
                "invested_down_payment": 100_000,
                "investment_return_rate": 0.07,
            },
        }
        spec = load_config_dict(config)
        assert spec.rent.monthly_rent == 2500
        assert spec.rent.rent_escalation_rate == 0.04
        assert spec.rent.invested_down_payment == 100_000
        assert spec.rent.investment_return_rate == 0.07

    def test_income_params_parsed_correctly(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": True},
            "income": {
                "annual_income": 120_000,
                "income_growth_rate": 0.03,
                "affordability_threshold": 0.35,
                "pay_drop_events": [
                    {"year": 3, "magnitude": 0.8}
                ],
            },
        }
        spec = load_config_dict(config)
        assert spec.income.annual_income == 120_000
        assert len(spec.income.pay_drop_events) == 1
        assert spec.income.pay_drop_events[0].year == 3
        assert spec.income.pay_drop_events[0].magnitude == 0.8

    def test_rent_validation_invalid_monthly_rent(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "rent": {"monthly_rent": -100},
        }
        with pytest.raises(ConfigValidationError):
            load_config_dict(config)

    def test_income_validation_invalid_threshold(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "condo": {"monthly_fee": 500},
            "income": {"annual_income": 100_000, "affordability_threshold": 1.5},
        }
        with pytest.raises(ConfigValidationError):
            load_config_dict(config)


# --- Task 8: capital-structure validation ---

def test_config_house_requires_capital_structure():
    from hde.config import load_config_dict, ConfigValidationError
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "annual_maintenance_rate": 0.01}}
    with pytest.raises(ConfigValidationError):
        load_config_dict(cfg)  # neither all_cash nor mortgage block


def test_config_house_all_cash_ok():
    from hde.config import load_config_dict
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "annual_maintenance_rate": 0.01, "all_cash": True}}
    spec = load_config_dict(cfg)
    assert spec.house.all_cash is True


def test_config_house_mortgage_block_ok():
    from hde.config import load_config_dict
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "down_payment": 80_000,
                     "mortgage_rate": 0.05, "mortgage_term_years": 25}}
    spec = load_config_dict(cfg)
    assert spec.house.down_payment == 80_000


def test_config_condo_requires_initial_value_and_capital_structure():
    from hde.config import load_config_dict, ConfigValidationError
    cfg = {"years": 10, "discount_rate": 0.04,
           "condo": {"monthly_fee": 500, "all_cash": True}}  # missing initial_value
    with pytest.raises(ConfigValidationError):
        load_config_dict(cfg)


# --- PR #4 external-review findings ---

def test_config_rejects_all_cash_with_mortgage_block():
    """Finding #1: all_cash=True AND a mortgage field set is ambiguous intent — reject."""
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "all_cash": True,
                     "down_payment": 80_000, "mortgage_rate": 0.05, "mortgage_term_years": 25}}
    with pytest.raises(ConfigValidationError, match="all_cash"):
        load_config_dict(cfg)


def test_config_rejects_condo_value_growth_at_or_below_neg_one():
    """Finding #2/#4: value_growth_rate <= -1 flips terminal-equity sign by year parity — reject."""
    cfg = {"years": 10, "discount_rate": 0.04,
           "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": True,
                     "value_growth_rate": -1.5}}
    with pytest.raises(ConfigValidationError, match="value_growth_rate"):
        load_config_dict(cfg)


def test_config_rejects_house_value_growth_at_or_below_neg_one():
    """Finding #4 (house side): value_growth_rate <= -1 rejected at config level."""
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "all_cash": True, "value_growth_rate": -1.0}}
    with pytest.raises(ConfigValidationError, match="value_growth_rate"):
        load_config_dict(cfg)


def test_config_all_cash_string_false_parses_to_false():
    """Finding #6: bool('false') is True — 'false' must parse to False, not True.
    With all_cash correctly False and no mortgage block, capital-structure validation must fire."""
    cfg = {"years": 10, "discount_rate": 0.04,
           "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": "false"}}
    with pytest.raises(ConfigValidationError):
        load_config_dict(cfg)


def test_config_all_cash_invalid_string_rejected():
    """Finding #6: a non-boolean all_cash value is rejected at parse time."""
    cfg = {"years": 10, "discount_rate": 0.04,
           "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": "maybe"}}
    with pytest.raises(ConfigValidationError, match="all_cash"):
        load_config_dict(cfg)


def test_config_all_cash_string_true_still_accepted():
    """Finding #6: exact 'true'/'false' strings remain valid for YAML round-trip tolerance."""
    cfg = {"years": 10, "discount_rate": 0.04,
           "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": "true"}}
    spec = load_config_dict(cfg)
    assert spec.condo.all_cash is True


# --- Audit F1: unknown-key rejection with did-you-mean suggestions ---

class TestUnknownKeyRejection:
    """A typo'd key must refuse loudly instead of being silently ignored."""

    def test_section_typo_suggests_close_match(self):
        cfg = {"years": 10, "discount_rate": 0.04,
               "house": {"initial_value": 400_000, "all_cash": True,
                         "value_growth_rat": 0.05}}
        with pytest.raises(ConfigValidationError, match="unknown key 'house.value_growth_rat'"):
            load_config_dict(cfg)
        with pytest.raises(ConfigValidationError, match="did you mean 'value_growth_rate'"):
            load_config_dict(cfg)

    def test_section_typo_refuses_cli_file_path(self):
        """The CLI loads via load_config(file) — same refusal on that path."""
        cfg = {"years": 10, "discount_rate": 0.04,
               "condo": {"monthly_fee": 500, "initial_value": 300_000, "all_cash": True,
                         "fee_escalation_ratte": 0.02}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(cfg, f)
            config_path = f.name
        try:
            with pytest.raises(ConfigValidationError, match="did you mean 'fee_escalation_rate'"):
                load_config(config_path)
        finally:
            Path(config_path).unlink()

    def test_unknown_top_level_key_suggests_years(self):
        cfg = {"yeers": 10, "discount_rate": 0.04,
               "house": {"initial_value": 400_000, "all_cash": True}}
        with pytest.raises(ConfigValidationError, match="unknown key 'yeers' — did you mean 'years'\?"):
            load_config_dict(cfg)

    def test_legacy_monte_carlo_section_hints_simulation(self):
        """There is no top-level monte_carlo section — hint at 'simulation'."""
        cfg = {"years": 10, "discount_rate": 0.04, "monte_carlo": {"num_sims": 100},
               "house": {"initial_value": 400_000, "all_cash": True}}
        with pytest.raises(ConfigValidationError, match="did you mean 'simulation'\?"):
            load_config_dict(cfg)

    def test_unknown_simulation_key(self):
        cfg = {"years": 10, "discount_rate": 0.04,
               "house": {"initial_value": 400_000, "all_cash": True},
               "simulation": {"randomseed": 7}}
        with pytest.raises(ConfigValidationError, match="did you mean 'random_seed'\?"):
            load_config_dict(cfg)

    def test_unknown_price_shock_key(self):
        cfg = {"years": 10, "discount_rate": 0.04,
               "house": {"initial_value": 400_000, "all_cash": True,
                         "price_shock": {"annual_hazzard": 0.02}}}
        with pytest.raises(ConfigValidationError, match="unknown key 'house.price_shock.annual_hazzard'"):
            load_config_dict(cfg)

    def test_unknown_market_scenario_key(self):
        cfg = {"years": 10, "discount_rate": 0.04,
               "house": {"initial_value": 400_000, "all_cash": True},
               "market_scenario": {"path": "p.json", "geography": "MTL_RMR", "vintage": 2026}}
        with pytest.raises(ConfigValidationError, match="unknown key 'market_scenario.vintage'"):
            load_config_dict(cfg)

    def test_unknown_event_entry_key(self):
        cfg = {"years": 10, "discount_rate": 0.04,
               "house": {"initial_value": 400_000, "all_cash": True,
                         "events": [{"name": "roof", "base_cost": 10_000,
                                     "expected_yer": 8}]}}
        with pytest.raises(ConfigValidationError, match=r"house\.events\[0\].expected_yer"):
            load_config_dict(cfg)

    def test_no_close_match_still_names_the_key(self):
        cfg = {"years": 10, "discount_rate": 0.04,
               "economic": {"mode": "real", "banana": 1},
               "house": {"initial_value": 400_000, "all_cash": True}}
        with pytest.raises(ConfigValidationError, match="unknown key 'economic.banana'"):
            load_config_dict(cfg)

    def test_multiple_unknown_keys_all_reported(self):
        cfg = {"years": 10, "discount_rate": 0.04, "banana": 1,
               "house": {"initial_value": 400_000, "all_cash": True, "woof": 2}}
        with pytest.raises(ConfigValidationError, match="woof"):
            load_config_dict(cfg)


# --- Audit U1: defaults-applied provenance ---

class TestDefaultsApplied:
    def _config(self, **overrides):
        cfg = {
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True},
            "rent": {"monthly_rent": 2_000},
        }
        cfg.update(overrides)
        return cfg

    def test_absent_assumption_keys_recorded(self):
        spec = load_config_dict(self._config())
        assert "economic.mode" in spec.defaults_applied
        assert "economic.inflation_rate" in spec.defaults_applied
        assert "house.value_growth_rate" in spec.defaults_applied
        assert "house.selling_cost_rate" in spec.defaults_applied
        assert "rent.rent_escalation_rate" in spec.defaults_applied
        assert "rent.invested_down_payment" in spec.defaults_applied
        assert "rent.investment_return_rate" in spec.defaults_applied

    def test_provided_keys_not_recorded(self):
        cfg = self._config(
            economic={"mode": "real", "inflation_rate": 0.0},
            house={"initial_value": 400_000, "all_cash": True,
                   "value_growth_rate": 0.01, "selling_cost_rate": 0.06,
                   "annual_maintenance_rate": 0.01},
            rent={"monthly_rent": 2_000, "rent_escalation_rate": 0.025,
                  "invested_down_payment": 50_000, "investment_return_rate": 0.05},
        )
        spec = load_config_dict(cfg)
        assert spec.defaults_applied == []

    def test_absent_option_section_not_recorded(self):
        """An absent condo section is not modeled at all — not a 'default'."""
        spec = load_config_dict(self._config())
        assert not any(k.startswith("condo.") for k in spec.defaults_applied)


# --- Audit U2: coherence warnings (surface, never refuse) ---

class TestCoherenceWarnings:
    def _spec(self, **overrides):
        cfg = {
            "years": 20, "discount_rate": 0.03,
            "economic": {"mode": "real"},
            "house": {"initial_value": 400_000, "all_cash": True,
                      "value_growth_rate": 0.01, "annual_maintenance_rate": 0.01,
                      # 2026-09-02: owner costs must be stated for a quiet run
                      "purchase_costs": 8_000,
                      "other_recurring_costs": [{"name": "tax", "annual_amount": 3_000,
                                                 "escalation_rate": 0.0}]},
            # like-for-like: the all-cash buyer puts $400k down, so the clean
            # fixture gives the renter the same capital (B.5 made the warning
            # fire for all_cash purchases, which it silently skipped before)
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.01,
                     "invested_down_payment": 400_000},
        }
        cfg.update(overrides)
        return load_config_dict(cfg)

    def test_clean_config_no_warnings(self):
        assert coherence_warnings(self._spec()) == []

    def test_real_mode_with_inflation_warns_ignored(self):
        spec = self._spec(economic={"mode": "real", "inflation_rate": 0.025})
        warns = coherence_warnings(spec)
        assert any("ignored in real mode" in w for w in warns)

    def test_high_real_growth_looks_like_nominal_quote(self):
        # audit experiment A: 5% growth in real mode
        spec = self._spec(house={"initial_value": 400_000, "all_cash": True,
                                 "value_growth_rate": 0.05})
        warns = coherence_warnings(spec)
        assert any("house.value_growth_rate=5.0%" in w and "nominal quote" in w
                   for w in warns)

    def test_nominal_mode_high_growth_not_flagged(self):
        spec = self._spec(
            economic={"mode": "nominal", "inflation_rate": 0.02},
            house={"initial_value": 400_000, "all_cash": True,
                   "value_growth_rate": 0.05},
        )
        assert not any("nominal quote" in w for w in coherence_warnings(spec))

    def test_discount_rate_outside_band(self):
        spec = self._spec(discount_rate=0.20)
        warns = coherence_warnings(spec)
        assert any("discount_rate=20.0%" in w and "outside" in w for w in warns)

    def test_tiny_initial_value_units_warning(self):
        spec = self._spec(house={"initial_value": 4_000, "all_cash": True})
        warns = coherence_warnings(spec)
        assert any("house.initial_value=$4,000" in w and "units?" in w for w in warns)

    def test_high_monthly_rent_units_warning(self):
        spec = self._spec(rent={"monthly_rent": 25_000})
        warns = coherence_warnings(spec)
        assert any("rent.monthly_rent=$25,000" in w and "units?" in w for w in warns)

    def test_short_horizon_selling_cost_warning(self):
        spec = self._spec(years=3)
        warns = coherence_warnings(spec)
        assert any("years=3" in w and "selling costs dominate" in w for w in warns)

    def test_owned_down_payment_with_unmodeled_renter_capital(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "down_payment": 80_000,
                      "mortgage_rate": 0.06, "mortgage_term_years": 25},
            "rent": {"monthly_rent": 2_000},
        })
        warns = coherence_warnings(spec)
        assert any("rent.invested_down_payment=0" in w and "net present value 0" in w
                   for w in warns)

    def test_modeled_renter_capital_not_flagged(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "down_payment": 80_000,
                      "mortgage_rate": 0.06, "mortgage_term_years": 25},
            "rent": {"monthly_rent": 2_000, "invested_down_payment": 80_000},
        })
        assert not any("like-for-like" in w for w in coherence_warnings(spec))

    def test_warnings_never_refuse_load(self):
        """Experiment A config loads fine despite multiple warnings."""
        spec = self._spec(
            house={"initial_value": 400_000, "all_cash": True,
                   "value_growth_rate": 0.05},
            discount_rate=0.20,
        )
        assert coherence_warnings(spec)  # non-empty, but spec loaded


# --- Audit U3: single-path predicate (all uncertainty inputs off) ---

class TestSinglePathRun:
    def test_all_vols_zero_is_single_path(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True,
                      "events": [{"name": "roof", "base_cost": 10_000,
                                  "expected_year": 15}]},
            "rent": {"monthly_rent": 2_000},
        })
        assert single_path_run(spec) is True

    def test_any_sim_vol_disqualifies(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "simulation": {"house_maintenance_vol": 0.1},
            "house": {"initial_value": 400_000, "all_cash": True},
            "rent": {"monthly_rent": 2_000},
        })
        assert single_path_run(spec) is False

    def test_event_jitter_disqualifies(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True,
                      "events": [{"name": "roof", "base_cost": 10_000,
                                  "expected_year": 15, "timing_std_years": 2}]},
        })
        assert single_path_run(spec) is False

    def test_event_cost_vol_disqualifies(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True,
                      "events": [{"name": "roof", "base_cost": 10_000,
                                  "expected_year": 15, "cost_vol": 0.2}]},
        })
        assert single_path_run(spec) is False

    def test_inflation_vol_disqualifies(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "economic": {"mode": "nominal", "inflation_rate": 0.02,
                         "inflation_vol": 0.01},
            "house": {"initial_value": 400_000, "all_cash": True},
        })
        assert single_path_run(spec) is False

    def test_price_shock_hazard_disqualifies(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True,
                      "price_shock": {"annual_hazard": 0.02}},
        })
        assert single_path_run(spec) is False

    def test_prior_disqualifies(self):
        spec = load_config_dict({
            "years": 20, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True},
            "market_scenario": {"path": "p.json", "geography": "MTL_RMR"},
        })
        assert single_path_run(spec) is False


def test_like_for_like_warning_fires_for_all_cash_purchase():
    """B.5: an all-cash buy puts the whole price down; with the renter's capital
    unset the verdict is not like-for-like and the warning must say so."""
    from hde.config import coherence_warnings, load_config_dict
    spec = load_config_dict({
        "years": 20, "discount_rate": 0.03,
        "condo": {"monthly_fee": 400, "initial_value": 480_000, "all_cash": True},
        "rent": {"monthly_rent": 2_000},
    })
    warns = "\n".join(coherence_warnings(spec))
    assert "net present value 0" in warns and "$480,000" in warns
