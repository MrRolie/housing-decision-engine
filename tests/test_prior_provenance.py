"""
Demographic-prior provenance (readiness plan E, 2026-09-01): everything hde
says about a prior is rendered from the FILE plus a closed citation registry —
never a literal. Pins the registry against the committed golden, the honest
degradation for unknown keys, and the surfaces the description reaches.
"""

import json
from pathlib import Path

from hde.anchors import (
    MAPPING_VERSION_NOTES,
    SOURCE_KEY_CITATIONS,
    describe_mapping_version,
    describe_source_key,
    source_key_label,
)
from hde.config import load_config_dict
from hde.deterministic import compute_deterministic
from hde.market_scenario import LoadedScenarioPrior, load_scenario_prior
from hde.reporting import format_text_report
from hde.serialization import assumptions_to_dict, format_assumptions
from hde.story_page import generate_story_markdown

GOLDEN = Path(__file__).parent / "fixtures" / "scenario_prior_golden.json"


class TestCitationRegistry:
    def test_every_golden_source_key_is_cited(self):
        keys = json.loads(GOLDEN.read_text(encoding="utf-8"))["data_vintage"]["source_hashes"]
        for key in keys:
            assert key in SOURCE_KEY_CITATIONS, f"golden source {key!r} has no citation"
            assert " — " in SOURCE_KEY_CITATIONS[key], key

    def test_unknown_key_degrades_honestly(self):
        assert describe_source_key("mystery.xlsx") == "uncited source: mystery.xlsx"
        assert source_key_label("mystery.xlsx") == "uncited source: mystery.xlsx"

    def test_mapping_version_of_the_golden_is_described(self):
        version = json.loads(GOLDEN.read_text(encoding="utf-8"))["mapping_version"]
        assert version in MAPPING_VERSION_NOTES
        assert "β" in describe_mapping_version(version)
        assert describe_mapping_version("99").startswith("undescribed mapping version")


class TestDescribeIsFileDerived:
    def _prior(self, **vintage) -> LoadedScenarioPrior:
        return LoadedScenarioPrior(
            schema_version="7", mapping_version="1", assumptions_hash="h",
            file_sha256="f" * 64, geography="QC_RMR", rows={},
            data_vintage={"isq_edition": "A2026", "census_year": "1999",
                          "constants_as_of": "2026-Q3",
                          "source_hashes": {"census_tenure_age_98100231.csv": {"sha256": "x"},
                                            "weird.bin": {"sha256": "y"}},
                          **vintage},
        )

    def test_describe_quotes_only_the_file(self):
        text = self._prior().describe()
        assert "QC_RMR demand model (ISQ A2026 scenarios, 1999 census)" in text
        assert "constants as of 2026-Q3" in text
        assert "simulation year 1 = calendar 2026, bands 2030/2035/2040/2045/2050" in text
        assert "mapping v1:" in text
        assert "StatCan 98-10-0231-01" in text and "uncited source: weird.bin" in text
        assert "UN" not in text.replace("uncited", "")

    def test_source_line_names_primary_families_and_counts_uncited(self):
        line = self._prior().source_line()
        assert line.startswith("Source: StatCan 98-10-0231-01")
        assert "(+1 uncited)" in line and "ScenarioPrior v7" in line

    def test_provenance_block_carries_the_vintage(self):
        block = self._prior().provenance_block()
        assert block["isq_edition"] == "A2026" and block["census_year"] == "1999"
        assert block["source_keys"] == ["census_tenure_age_98100231.csv", "weird.bin"]
        assert block["horizon_years"] == [2030, 2035, 2040, 2045, 2050]


class TestSurfacesCarryThePrior:
    def _spec_and_prior(self):
        spec = load_config_dict({
            "years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True, "annual_maintenance_rate": 0.01},
            "rent": {"monthly_rent": 1_800, "invested_down_payment": 400_000},
            "market_scenario": {"path": str(GOLDEN), "geography": "MTL_RMR"},
        })
        return spec, load_scenario_prior(str(GOLDEN), "MTL_RMR")

    def test_text_report_names_the_prior(self):
        spec, prior = self._spec_and_prior()
        report = format_text_report(compute_deterministic(spec), None, spec.simulation,
                                    spec.economic, spec=spec, prior=prior)
        assert "demographic prior: MTL_RMR (ISQ 2026 scenarios, 2021 census)" in report
        assert "constants as of 2026-07-21" in report and "ScenarioPrior v" in report

    def test_assumptions_json_carries_description_and_sources(self):
        spec, prior = self._spec_and_prior()
        doc = assumptions_to_dict(spec, prior)["demographic_prior"]
        assert doc["geography"] == "MTL_RMR" and doc["constants_as_of"] == "2026-07-21"
        assert "StatCan 98-10-0231-01" in doc["description"]
        assert all(s["citation"] and s["sha256"] for s in doc["sources"])
        assert not any(s["citation"].startswith("uncited") for s in doc["sources"])

    def test_no_prior_means_no_prior_line(self):
        spec, _ = self._spec_and_prior()
        assert not any("demographic prior" in ln for ln in format_assumptions(spec, None))
        assert assumptions_to_dict(spec, None)["demographic_prior"] is None


def test_story_markdown_persists_warnings():
    story = generate_story_markdown(
        acts=[], image_paths={}, command="cmd", headline="H", subtitle="S",
        warnings=["time anchor stale: current year 2027 is past START_CALENDAR_YEAR=2026"],
    )
    assert "> warning: time anchor stale" in story
