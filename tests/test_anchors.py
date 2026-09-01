"""Anchor discipline tests (provenance remediation, Task A).

Pins three things beyond the import-time enforcement in anchors.py:

1. Registry coverage + citation discipline: every wired default is registered
   and carries as_of/source/url/rationale with its value inside its band.
2. The three-way single-source-of-truth pin — dataclass default == config
   parser default == anchor value — so a future edit at one site without the
   others goes red instead of silently drifting back to a vibe.
3. The two provenance coherence warnings (defaulted rent escalation; nominal
   mode with zero inflation).
"""

import pytest

from hde.anchors import ANCHORS, Anchor, AnchorError, short_cite
from hde.config import coherence_warnings, load_config_dict
from hde.models import (
    CondoParams,
    HouseParams,
    IncomeParams,
    PriceShockParams,
    RentParams,
)

# Every anchored key omitted below, so the parsers fall back to anchors.
BASE_CONFIG = {
    "years": 20,
    "discount_rate": 0.03,
    "economic": {"mode": "real"},
    "condo": {
        "monthly_fee": 500,
        "initial_value": 400_000,
        "all_cash": True,
        "price_shock": {"annual_hazard": 0.01},
    },
    "house": {
        "initial_value": 500_000,
        "all_cash": True,
        "price_shock": {"annual_hazard": 0.01},
    },
    "rent": {"monthly_rent": 2_000},
    "income": {"annual_income": 100_000},
}


class TestRegistryDiscipline:
    def test_registry_covers_the_wired_defaults(self):
        expected = {
            "rent.investment_return_rate",
            "rent.rent_escalation_rate",
            "income.income_growth_rate",
            "income.affordability_threshold",
            "condo.house.selling_cost_rate",
            "price_shock.severity_mean",
            "price_shock.severity_vol",
            "condo.fee_escalation_rate",
            "house.value_growth_rate",
            "condo.value_growth_rate",
            "economic.inflation_rate",
        }
        assert expected <= set(ANCHORS), sorted(expected - set(ANCHORS))

    def test_every_anchor_carries_citation_and_band(self):
        for name, anchor in ANCHORS.items():
            assert anchor.name == name
            for field in ("as_of", "source", "url", "rationale", "short_cite"):
                assert getattr(anchor, field).strip(), f"{name}: empty {field}"
            assert anchor.band[0] <= anchor.value <= anchor.band[1], name

    def test_anchor_construction_refuses_uncited_constants(self):
        with pytest.raises(AnchorError):
            Anchor(name="x.y", value=0.1, as_of="", source="s", url="u",
                   rationale="r", band=(0.0, 1.0), short_cite="s")

    def test_anchor_construction_refuses_value_outside_band(self):
        with pytest.raises(AnchorError):
            Anchor(name="x.y", value=0.9, as_of="2026", source="s", url="u",
                   rationale="r", band=(0.0, 0.5), short_cite="s")

    def test_short_cite_aliases_share_the_selling_cost_anchor(self):
        shared = ANCHORS["condo.house.selling_cost_rate"].short_cite
        assert short_cite("condo.selling_cost_rate") == shared
        assert short_cite("house.selling_cost_rate") == shared
        assert short_cite("simulation.num_sims") == ""


class TestThreeWayPin:
    """dataclass default == config parser default == anchor value."""

    def test_dataclass_defaults_equal_anchors(self):
        rent = RentParams(monthly_rent=1_000)
        income = IncomeParams(annual_income=1)
        condo = CondoParams(monthly_fee=1)
        house = HouseParams(initial_value=1)
        shock = PriceShockParams()
        assert rent.rent_escalation_rate == ANCHORS["rent.rent_escalation_rate"].value
        assert rent.investment_return_rate == ANCHORS["rent.investment_return_rate"].value
        assert income.income_growth_rate == ANCHORS["income.income_growth_rate"].value
        assert income.affordability_threshold == ANCHORS["income.affordability_threshold"].value
        assert condo.selling_cost_rate == ANCHORS["condo.house.selling_cost_rate"].value
        assert house.selling_cost_rate == ANCHORS["condo.house.selling_cost_rate"].value
        assert shock.severity_mean == ANCHORS["price_shock.severity_mean"].value
        assert shock.severity_vol == ANCHORS["price_shock.severity_vol"].value

    def test_parser_defaults_equal_anchors(self):
        spec = load_config_dict(BASE_CONFIG)
        assert spec.rent.rent_escalation_rate == ANCHORS["rent.rent_escalation_rate"].value
        assert spec.rent.investment_return_rate == ANCHORS["rent.investment_return_rate"].value
        assert spec.income.income_growth_rate == ANCHORS["income.income_growth_rate"].value
        assert spec.income.affordability_threshold == ANCHORS["income.affordability_threshold"].value
        assert spec.condo.selling_cost_rate == ANCHORS["condo.house.selling_cost_rate"].value
        assert spec.house.selling_cost_rate == ANCHORS["condo.house.selling_cost_rate"].value
        assert spec.condo.price_shock.severity_mean == ANCHORS["price_shock.severity_mean"].value
        assert spec.house.price_shock.severity_vol == ANCHORS["price_shock.severity_vol"].value


class TestProvenanceWarnings:
    def test_defaulted_rent_escalation_warns_with_citation(self):
        warns = coherence_warnings(load_config_dict(BASE_CONFIG))
        assert any(
            "rent.rent_escalation_rate defaulted to 1.0% real" in w
            and "FP Canada" in w
            for w in warns
        )

    def test_explicit_rent_escalation_does_not_warn(self):
        cfg = {**BASE_CONFIG, "rent": {**BASE_CONFIG["rent"], "rent_escalation_rate": 0.0}}
        assert not any(
            "rent_escalation_rate defaulted" in w
            for w in coherence_warnings(load_config_dict(cfg))
        )

    def test_nominal_mode_zero_inflation_suggests_fp_canada(self):
        cfg = {**BASE_CONFIG, "economic": {"mode": "nominal", "inflation_rate": 0.0}}
        assert any(
            "inflation_rate=0" in w and "2.1%" in w
            for w in coherence_warnings(load_config_dict(cfg))
        )

    def test_real_mode_zero_inflation_does_not_warn(self):
        assert not any(
            "inflation_rate=0" in w
            for w in coherence_warnings(load_config_dict(BASE_CONFIG))
        )
