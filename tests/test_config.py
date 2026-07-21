"""
Tests for configuration loading.
"""

import pytest
import tempfile
from pathlib import Path
import yaml

from hde.config import load_config, load_config_dict, ConfigValidationError


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
    
    def test_missing_discount_rate(self):
        """Test that missing discount_rate raises error."""
        config = {
            "years": 20,
            "condo": {"monthly_fee": 400},
            "house": {"initial_value": 400000},
        }
        
        with pytest.raises(ConfigValidationError, match="discount_rate"):
            load_config_dict(config)
    
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
