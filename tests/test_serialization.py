"""
Serialization tests (src/hde/serialization.py): the agent-facing provenance
surface — anchor records, the structured assumption echo, engine identity.
Readiness plan A.1/A.5 (2026-09-01).
"""

from hde.anchors import ANCHORS, _ECHO_ALIASES
from hde.config import load_config_dict
from hde.serialization import (
    anchor_to_dict,
    anchors_to_dict,
    assumptions_to_dict,
    engine_version,
    format_assumptions,
)

MINIMAL_CONFIG = {
    "years": 20, "discount_rate": 0.03,
    "house": {"initial_value": 400_000, "all_cash": True},
    "rent": {"monthly_rent": 2_000},
}

ANCHOR_FIELDS = {
    "name", "value", "as_of", "source", "url", "rationale", "band",
    "short_cite", "retrieved_on", "kind", "replaces",
}


class TestAnchorRecords:
    def test_anchor_to_dict_carries_every_field_json_shaped(self):
        doc = anchor_to_dict(ANCHORS["rent.investment_return_rate"])
        assert set(doc) == ANCHOR_FIELDS
        assert doc["band"] == [0.02, 0.05]
        assert doc["replaces"] == {"value": 0.07, "why": doc["replaces"]["why"]}
        assert doc["replaces"]["why"]
        assert doc["url"].startswith("https://")
        assert doc["retrieved_on"] == "2026-09-01"

    def test_registry_dump_names_every_anchor_with_a_source(self):
        dump = anchors_to_dict()
        assert set(dump) == set(ANCHORS)
        for name, doc in dump.items():
            assert doc["name"] == name
            assert doc["source"].strip(), name
            assert doc["kind"] in {"cited", "reference", "neutral", "derivation"}, name

    def test_live_urls_are_dated(self):
        for name, doc in anchors_to_dict().items():
            if doc["url"].startswith("http"):
                assert doc["retrieved_on"], f"{name}: live URL without retrieved_on"


class TestAssumptionsToDict:
    def test_every_defaulted_key_is_present_with_its_kind(self):
        spec = load_config_dict(MINIMAL_CONFIG)
        doc = assumptions_to_dict(spec)
        keys = [e["key"] for e in doc["defaults_applied"]]
        assert keys == spec.defaults_applied
        assert doc["lines"] == format_assumptions(spec)
        assert doc["mode"] == "real" and doc["years"] == 20
        by_key = {e["key"]: e for e in doc["defaults_applied"]}
        assert by_key["economic.mode"]["kind"] == "mode"
        assert by_key["economic.mode"]["anchor"] is None
        cited = by_key["rent.investment_return_rate"]
        assert cited["kind"] == "cited"
        assert cited["cite"] == "FP Canada 2026 PAG"
        assert cited["anchor"]["source"]
        assert cited["value"] == ANCHORS["rent.investment_return_rate"].value

    def test_reference_anchor_renders_as_ref_tag(self):
        spec = load_config_dict(MINIMAL_CONFIG)
        by_key = {e["key"]: e for e in assumptions_to_dict(spec)["defaults_applied"]}
        infl = by_key["economic.inflation_rate"]
        assert infl["kind"] == "reference"
        assert infl["cite"] == "ref: FP Canada 2026 PAG"
        assert "economic.inflation_rate=0.0% [ref: FP Canada 2026 PAG]" in "\n".join(
            format_assumptions(spec))

    def test_no_defaulted_key_is_uncited(self):
        """Every key `_defaults_applied` can emit resolves to an anchor or is a
        mode flag — an `uncited` entry is a registry gap, not a valid state."""
        spec = load_config_dict({
            "years": 10, "discount_rate": 0.04,
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True},
            "house": {"initial_value": 400_000, "all_cash": True},
            "rent": {"monthly_rent": 1_500},
            "income": {"annual_income": 90_000},
        })
        for entry in assumptions_to_dict(spec)["defaults_applied"]:
            assert entry["kind"] != "uncited", entry["key"]

    def test_aliases_resolve_to_the_shared_anchor(self):
        spec = load_config_dict(MINIMAL_CONFIG)
        by_key = {e["key"]: e for e in assumptions_to_dict(spec)["defaults_applied"]}
        target = _ECHO_ALIASES["house.selling_cost_rate"]
        assert by_key["house.selling_cost_rate"]["anchor"]["name"] == target


def test_engine_version_is_the_installed_version():
    assert engine_version() not in {"", "unknown"}
