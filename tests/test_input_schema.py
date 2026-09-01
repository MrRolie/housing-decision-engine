"""
The published input contract (src/hde/input_schema.py) must be TRUE, not just
complete (readiness plan F.3, 2026-09-01): every parser key carries a curated
note, every `required` flag survives a drop-one round trip against the parser,
`required_if` states the capital-structure rule, and the top level enumerates
every block the parser accepts.
"""

import copy
from pathlib import Path

import pytest

from hde.config import ConfigValidationError, _SECTION_KEYS, _TOP_LEVEL_KEYS, load_config_dict
from hde.input_schema import _NOTES, input_schema

GOLDEN = str(Path(__file__).parent / "fixtures" / "scenario_prior_golden.json")
SCHEMA = input_schema()


class TestCompleteness:
    def test_every_parser_key_has_a_curated_note(self):
        for section, keys in _SECTION_KEYS.items():
            missing = sorted(set(keys) - set(_NOTES.get(section, {})))
            assert not missing, (section, missing)

    def test_no_note_is_a_placeholder(self):
        for section, block in SCHEMA.items():
            for key, entry in block.items():
                assert entry["note"].strip(), (section, key)
                assert not entry["note"].startswith("see "), (section, key, entry["note"])
                assert "docs/examples" not in entry["note"], (section, key)

    def test_no_stale_note_keys(self):
        for section, notes in _NOTES.items():
            if section == "top":
                continue
            stale = sorted(set(notes) - set(_SECTION_KEYS[section]))
            assert not stale, (section, stale)

    def test_top_level_enumerates_every_accepted_key(self):
        assert set(SCHEMA["top_level"]) == set(_TOP_LEVEL_KEYS)
        for block in ("condo", "house", "rent"):
            assert "at least ONE" in SCHEMA["top_level"][block]["note"]


# Every block present with ONLY its required keys; the capital-structure
# `required_if` satisfied by all_cash. If this parses, every optional key is
# truly optional; dropping any required key must then refuse.
KNOWN_GOOD = {
    "years": 10, "discount_rate": 0.03,
    "condo": {"initial_value": 300_000, "monthly_fee": 350, "all_cash": True},
    "house": {"initial_value": 400_000, "all_cash": True},
    "rent": {"monthly_rent": 1_500},
    "income": {"annual_income": 80_000},
    "economic": {},
    "simulation": {},
    "market_scenario": {"path": GOLDEN, "geography": "MTL_RMR"},
}
REQUIRED = [
    (section, key)
    for section, block in SCHEMA.items() if section != "top_level"
    for key, entry in block.items() if entry["required"]
]
CONDITIONAL = [
    (section, key)
    for section, block in SCHEMA.items() if section != "top_level"
    for key, entry in block.items() if entry.get("required_if")
]


class TestRequiredFlagsAreTrue:
    def test_known_good_is_exactly_the_required_keys(self):
        load_config_dict(KNOWN_GOOD)
        for section, block in SCHEMA.items():
            if section == "top_level":
                continue
            required = {k for k, e in block.items() if e["required"]}
            present = set(KNOWN_GOOD[section])
            extra = present - required
            assert extra <= {"all_cash"}, (section, extra)   # the one required_if choice
            assert required <= present, (section, required - present)

    @pytest.mark.parametrize("section,key", REQUIRED)
    def test_dropping_a_required_key_refuses(self, section, key):
        cfg = copy.deepcopy(KNOWN_GOOD)
        cfg[section].pop(key)
        with pytest.raises(ConfigValidationError):
            load_config_dict(cfg)

    def test_capital_structure_is_conditional_not_required(self):
        assert {k for _, k in CONDITIONAL} == {"all_cash", "down_payment", "mortgage_rate", "mortgage_term_years"}
        for section, key in CONDITIONAL:
            assert not SCHEMA[section][key]["required"], (section, key)
            assert "declare all_cash: true OR" in SCHEMA[section][key]["required_if"]

    def test_dropping_the_capital_structure_refuses_with_the_quoted_sentence(self):
        cfg = copy.deepcopy(KNOWN_GOOD)
        cfg["house"].pop("all_cash")
        with pytest.raises(ConfigValidationError, match="declare all_cash: true OR a mortgage block"):
            load_config_dict(cfg)

    def test_mortgage_block_satisfies_the_conditional(self):
        cfg = copy.deepcopy(KNOWN_GOOD)
        cfg["house"] = {"initial_value": 400_000, "down_payment": 80_000,
                        "mortgage_rate": 0.05, "mortgage_term_years": 25}
        load_config_dict(cfg)

    def test_omitting_an_optional_block_is_fine(self):
        cfg = {k: v for k, v in KNOWN_GOOD.items() if k not in ("condo", "income", "market_scenario")}
        load_config_dict(cfg)
