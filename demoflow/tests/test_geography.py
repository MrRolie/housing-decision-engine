import pytest

from demoflow.geography import (
    Geography, Scenario, SEX_CODE_TO_GENDER, SCENARIO_LABEL_TO_ENUM,
    normalize_label, classify_geography, IGNORED, require_all_geographies, RA_PROXY_MEMBERS,
)
from demoflow.errors import LoaderError


def test_normalize_strips_whitespace_and_footnote_digits():
    assert normalize_label("RMR de Montréal ") == "RMR de Montréal"
    assert normalize_label("RMR d'Ottawa-Gatineau2") == "RMR d'Ottawa-Gatineau"


def test_modeled_label_maps_to_enum():
    assert classify_geography("RMR de Montréal ") is Geography.MTL_RMR


def test_known_unmodeled_label_is_IGNORED_not_raise():
    # Valid ISQ geography, outside model scope -> IGNORED sentinel (a valid workbook must LOAD).
    assert classify_geography("RMR de Saguenay") is IGNORED
    assert classify_geography("Le Québec") is IGNORED


def test_label_outside_verified_set_raises():
    with pytest.raises(LoaderError, match="verified set|drift"):
        classify_geography("RMR de Nowhere")


def test_require_all_geographies_raises_on_missing_expected():
    with pytest.raises(LoaderError, match="not found"):
        require_all_geographies({Geography.MTL_RMR}, {Geography.MTL_RMR, Geography.QC_RMR}, "ctx")
    require_all_geographies({Geography.MTL_RMR, Geography.QC_RMR},
                            {Geography.MTL_RMR, Geography.QC_RMR}, "ctx")  # complete: no raise


def test_scenario_labels_map_to_enum():
    assert SCENARIO_LABEL_TO_ENUM["Référence (A2026)"] is Scenario.REFERENCE
    assert SCENARIO_LABEL_TO_ENUM["Faible (D2026)"] is Scenario.LOW
    assert SCENARIO_LABEL_TO_ENUM["Fort (E2026)"] is Scenario.HIGH


def test_sex_codes_are_numeric_1_2_3():
    assert SEX_CODE_TO_GENDER[1] == "M"
    assert SEX_CODE_TO_GENDER[2] == "F"
    assert 3 not in SEX_CODE_TO_GENDER  # code 3 is TOTAL, used only for additivity


def test_geography_value_is_a_string():
    assert Geography.MTL_RMR.value == "MTL_RMR"
    assert isinstance(Geography.MTL_RMR.value, str)


def test_ra_proxy_members_flagged():
    assert Geography.LANAUDIERE_RA14_PROXY in RA_PROXY_MEMBERS
    assert Geography.MTL_RMR not in RA_PROXY_MEMBERS


def test_both_dash_editions_of_the_ra_labels_are_IGNORED():
    """Measured 2026-08-07 against the committed workbooks: the SAME nominal region
    ships under TWO dash codepoints across editions — pop-as-ra-base.xlsx uses
    U+2013 EN DASH, compo-ra-base.xlsx uses U+002D HYPHEN-MINUS. Both must classify
    as IGNORED or compo-ra-base.xlsx (a valid workbook) fails to LOAD, contradicting
    spec §8 r4-F2. The plan's provisional map carried only the U+2013 variants."""
    assert classify_geography("Saguenay–Lac-Saint-Jean") is IGNORED     # U+2013, pop-as-ra
    assert classify_geography("Saguenay-Lac-Saint-Jean") is IGNORED     # U+002D, compo-ra
    assert classify_geography("Gaspésie–Îles-de-la-Madeleine") is IGNORED   # U+2013, pop-as-ra
    assert classify_geography("Gaspésie-Îles-de-la-Madeleine") is IGNORED   # U+002D, compo-ra
