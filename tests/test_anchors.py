"""Anchor discipline tests (provenance remediation; readiness plan C, 2026-09-01).

Pins, beyond the import-time enforcement in anchors.py:

1. Registry coverage is GENERATIVE: every anchor is either a dataclass default
   (WIRING) or declared consumed elsewhere (CONSUMED_ELSEWHERE); every key the
   assumption echo can emit resolves to an anchor. A new anchor left unwired,
   or a new echoed default left unanchored, goes red.
2. The three-way single-source-of-truth pin — dataclass default == config
   parser default == anchor value — for EVERY wired anchor.
3. The provenance coherence warnings (defaulted rent escalation, defaulted
   house maintenance, nominal mode with zero inflation) and the nested
   price-shock echo.
"""

import math

import pytest

from hde.anchors import (
    ANCHORS,
    ANCHOR_KINDS,
    Anchor,
    AnchorError,
    _ECHO_ALIASES,
    is_reference,
    short_cite,
)
from hde.config import _ASSUMPTION_KEYS, coherence_warnings, load_config_dict
from hde.models import (
    CondoParams,
    EconomicParams,
    HouseParams,
    IncomeParams,
    PriceShockParams,
    RentParams,
    SimulationParams,
)
from hde.serialization import format_assumptions, spec_value

# Every anchored key omitted below, so the parsers fall back to anchors.
BASE_CONFIG = {
    "years": 20,
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

# anchor name -> (dataclass factory, attribute). The parser paths are derived
# below (aliases fan one anchor out to both owned options).
WIRING = {
    "rent.rent_escalation_rate": (lambda: RentParams(monthly_rent=1_000), "rent_escalation_rate"),
    "rent.investment_return_rate": (lambda: RentParams(monthly_rent=1_000), "investment_return_rate"),
    "rent.invested_down_payment": (lambda: RentParams(monthly_rent=1_000), "invested_down_payment"),
    "simulation.discount_rate": (lambda: SimulationParams(years=1), "discount_rate"),
    "income.income_growth_rate": (lambda: IncomeParams(annual_income=1), "income_growth_rate"),
    "income.affordability_threshold": (lambda: IncomeParams(annual_income=1), "affordability_threshold"),
    "condo.house.selling_cost_rate": (lambda: HouseParams(initial_value=1), "selling_cost_rate"),
    "condo.fee_escalation_rate": (lambda: CondoParams(monthly_fee=1), "fee_escalation_rate"),
    "condo.value_growth_rate": (lambda: CondoParams(monthly_fee=1), "value_growth_rate"),
    "house.value_growth_rate": (lambda: HouseParams(initial_value=1), "value_growth_rate"),
    "house.annual_maintenance_rate": (lambda: HouseParams(initial_value=1), "annual_maintenance_rate"),
    "economic.inflation_rate": (EconomicParams, "inflation_rate"),
    "price_shock.severity_mean": (PriceShockParams, "severity_mean"),
    "price_shock.severity_vol": (PriceShockParams, "severity_vol"),
}

# Anchors read by a code path other than a dataclass default — say where.
CONSUMED_ELSEWHERE = {
    "economic.inflation_rate.nominal_planning": "config.coherence_warnings + input_schema note",
    "market_scenario.drift_sigma_divisor": "market_scenario.DRIFT_SIGMA_DIVISOR",
    "verdict.prob_floor": "models.compute_verdict",
    "verdict.tie_band": "models.compute_verdict",
    # The premium schedule is a table, not a per-field default: it has no
    # dataclass default to pin, and mortgage_insurance.anchored_schedule builds
    # the schedule FROM these entries (tests/test_mortgage_insurance.py pins the
    # rates against the quoted table).
    "mortgage_insurance.premium_rate.ltv_65": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.premium_rate.ltv_65_75": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.premium_rate.ltv_75_80": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.premium_rate.ltv_80_85": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.premium_rate.ltv_85_90": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.premium_rate.ltv_90_95": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.max_ltv": "mortgage_insurance.PremiumSchedule.max_ltv",
    "mortgage_insurance.amortization_surcharge": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.premium_tax_rate.qc": "mortgage_insurance.anchored_schedule",
    "mortgage_insurance.premium_tax_rate.on": "mortgage_insurance.anchored_schedule",
}


def _parser_paths(name: str):
    if name == "condo.house.selling_cost_rate":
        return ["condo.selling_cost_rate", "house.selling_cost_rate"]
    if name.startswith("price_shock."):
        sub = name.split(".", 1)[1]
        return [f"condo.price_shock.{sub}", f"house.price_shock.{sub}"]
    return [name]


class TestRegistryDiscipline:
    def test_every_anchor_is_wired_or_declared_consumed(self):
        # Jurisdiction reference tables are a THIRD class: never an engine
        # default, consumed by serialization.reference_matches when a user's own
        # figure equals the published one. Declared by family, not one by one,
        # so adding a municipality does not need a line here — but adding a new
        # FAMILY does. Their own discipline is pinned in test_reference_anchors.
        declared = (set(WIRING) | set(CONSUMED_ELSEWHERE)
                    | {n for n in ANCHORS if is_reference(n)})
        assert declared == set(ANCHORS), {
            "unwired anchors": sorted(set(ANCHORS) - declared),
            "stale wiring": sorted(declared - set(ANCHORS)),
        }

    def test_every_echoable_default_resolves_to_an_anchor(self):
        """Every key `_defaults_applied` can emit (mode flags excepted) has a
        registry entry — the echo can never print a bare uncited number."""
        for section, keys in _ASSUMPTION_KEYS.items():
            for key in keys:
                if key == "mode":
                    continue
                assert short_cite(f"{section}.{key}"), f"{section}.{key} has no anchor"
        for alias in _ECHO_ALIASES:
            assert short_cite(alias), alias

    def test_every_anchor_carries_citation_and_band(self):
        for name, anchor in ANCHORS.items():
            assert anchor.name == name
            for field in ("as_of", "source", "url", "rationale", "short_cite"):
                assert getattr(anchor, field).strip(), f"{name}: empty {field}"
            assert anchor.kind in ANCHOR_KINDS, name
            if anchor.kind == "unsourced":
                assert anchor.value is None, f"{name}: unsourced entry holds a value"
            else:
                assert anchor.band[0] <= anchor.value <= anchor.band[1], name
            if anchor.url.startswith("http"):
                assert anchor.retrieved_on, f"{name}: live URL without retrieved_on"

    def test_anchor_construction_refuses_uncited_constants(self):
        with pytest.raises(AnchorError):
            Anchor(name="x.y", value=0.1, as_of="", source="s", url="u",
                   rationale="r", band=(0.0, 1.0), short_cite="s")

    def test_anchor_construction_refuses_value_outside_band(self):
        with pytest.raises(AnchorError):
            Anchor(name="x.y", value=0.9, as_of="2026", source="s", url="u",
                   rationale="r", band=(0.0, 0.5), short_cite="s")

    def test_anchor_refuses_live_url_without_retrieved_on(self):
        with pytest.raises(AnchorError):
            Anchor(name="x.y", value=0.1, as_of="2026", source="s", url="https://example.org",
                   rationale="r", band=(0.0, 1.0), short_cite="s")

    def test_anchor_refuses_unknown_kind(self):
        with pytest.raises(AnchorError):
            Anchor(name="x.y", value=0.1, as_of="2026", source="s", url="u",
                   rationale="r", band=(0.0, 1.0), short_cite="s", kind="vibes")

    def test_short_cite_aliases_share_the_shock_and_selling_cost_anchors(self):
        shared = ANCHORS["condo.house.selling_cost_rate"].short_cite
        assert short_cite("condo.selling_cost_rate") == shared
        assert short_cite("house.selling_cost_rate") == shared
        assert short_cite("house.price_shock.severity_mean") == ANCHORS["price_shock.severity_mean"].short_cite
        assert short_cite("simulation.num_sims") == ""

    def test_reference_kind_renders_as_ref_tag(self):
        assert short_cite("economic.inflation_rate") == "ref: FP Canada 2026 PAG"
        assert short_cite("condo.fee_escalation_rate") == "ref: FP Canada 2026 PAG"

    def test_severity_draw_endpoints_match_the_rationale(self):
        """The severity_vol rationale quotes the ±1σ span the lognormal draw
        produces; recompute it from the two anchors and check it stays inside
        the severity anchor's own band."""
        mean = ANCHORS["price_shock.severity_mean"].value
        vol = ANCHORS["price_shock.severity_vol"].value
        lo = mean * math.exp(-vol - 0.5 * vol ** 2)
        hi = mean * math.exp(vol - 0.5 * vol ** 2)
        assert lo == pytest.approx(0.225, abs=0.001)
        assert hi == pytest.approx(0.275, abs=0.001)
        band_lo, band_hi = ANCHORS["price_shock.severity_mean"].band
        assert band_lo <= lo <= hi <= band_hi


class TestThreeWayPin:
    """dataclass default == config parser default == anchor value, for EVERY wired anchor."""

    def test_dataclass_defaults_equal_anchors(self):
        for name, (factory, attr) in WIRING.items():
            assert getattr(factory(), attr) == ANCHORS[name].value, name
        # the shared selling-cost anchor also drives the condo dataclass
        assert CondoParams(monthly_fee=1).selling_cost_rate == ANCHORS["condo.house.selling_cost_rate"].value

    def test_parser_defaults_equal_anchors(self):
        spec = load_config_dict(BASE_CONFIG)
        for name in WIRING:
            for path in _parser_paths(name):
                assert spec_value(spec, path) == ANCHORS[name].value, path


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

    def test_defaulted_house_maintenance_warns(self):
        warns = coherence_warnings(load_config_dict(BASE_CONFIG))
        assert any("annual_maintenance_rate defaulted to 0.0%" in w and "NAHB" in w for w in warns)

    def test_explicit_house_maintenance_does_not_warn(self):
        cfg = {**BASE_CONFIG, "house": {**BASE_CONFIG["house"], "annual_maintenance_rate": 0.01}}
        assert not any("annual_maintenance_rate defaulted" in w
                       for w in coherence_warnings(load_config_dict(cfg)))

    def test_nominal_mode_zero_inflation_suggests_fp_canada(self):
        cfg = {**BASE_CONFIG, "economic": {"mode": "nominal", "inflation_rate": 0.0}}
        planning = ANCHORS["economic.inflation_rate.nominal_planning"]
        assert any(
            "inflation_rate=0" in w and f"{planning.value:.1%}" in w
            for w in coherence_warnings(load_config_dict(cfg))
        )

    def test_real_mode_zero_inflation_does_not_warn(self):
        assert not any(
            "inflation_rate=0" in w
            for w in coherence_warnings(load_config_dict(BASE_CONFIG))
        )


class TestNestedPriceShockEcho:
    def test_defaulted_shock_severity_is_echoed_with_its_citation(self):
        spec = load_config_dict(BASE_CONFIG)
        assert "condo.price_shock.severity_mean" in spec.defaults_applied
        assert "house.price_shock.severity_vol" in spec.defaults_applied
        joined = "\n".join(format_assumptions(spec))
        assert "condo.price_shock.severity_mean=25.0% [TREB 1989–96]" in joined

    def test_explicit_shock_severity_is_not_echoed(self):
        cfg = {**BASE_CONFIG, "condo": {**BASE_CONFIG["condo"],
                                        "price_shock": {"annual_hazard": 0.01,
                                                        "severity_mean": 0.3,
                                                        "severity_vol": 0.1}}}
        spec = load_config_dict(cfg)
        assert not any(k.startswith("condo.price_shock") for k in spec.defaults_applied)

    def test_no_shock_block_means_no_shock_default(self):
        cfg = {**BASE_CONFIG, "condo": {"monthly_fee": 500, "initial_value": 400_000, "all_cash": True}}
        spec = load_config_dict(cfg)
        assert not any(k.startswith("condo.price_shock") for k in spec.defaults_applied)
        assert any(k.startswith("house.price_shock") for k in spec.defaults_applied)
