"""Tranche-2 ScenarioPrior contract tests (spec §7(a) + §10's RED fixtures) — every §7(a)
integrity rule gets its own refusal, exercised as a distinct fixture:

  field-set-equals-allowlist · never_relax_stress iff tilt < 1.0 · COMPLETE Cartesian product
  with no duplicates · every numeric finite (allow_nan=False serialization) · p10 <= mean <= p90
  · tilt >= 0 · enum-only horizons/scenarios/geography-as-string-value.

Plus the mapping (`balance/mapping.py`) pins: the worked ED=0.01 fixture, the closed-form beta
quantiles, sign reversal for negative ED, and the VERSION-STAMP enforcement — changing the
mapping without bumping `MAPPING_VERSION` fails, per spec §7(a).
"""
import json

import pytest

from demoflow.balance import mapping
from demoflow.errors import CalibrationError
from demoflow.geography import RA_PROXY_MEMBERS, Geography, Scenario
from demoflow.golden import GOLDEN_DIR
from demoflow.loaders.census import _POP_BASE_YEAR
from demoflow.loaders.constants import CONSTANTS
from demoflow.output import scenario_prior as sp
from demoflow.output.artifacts import (
    SCENARIO_PRIOR_SCHEMA,
    _assert_finite,
    _canonical_bytes,
    assert_no_open_strings,
    payload_of,
    scenario_prior_document,
    write_json_strict,
)
from demoflow.output.scenario_prior import (
    DWELLING_TYPES,
    EXCESS_DEMAND_RATE_FIELD,
    HORIZON_YEARS,
    PRIOR_FLAGS_ALLOWED,
    PRIOR_GEOGRAPHIES,
    PRIOR_ROW_FIELDS,
    assert_scenario_prior_row_valid,
    build_scenario_prior_rows,
    prior_document_complete,
    prior_row_to_dict,
    prior_vintage,
)

# --------------------------------------------------------------------- shared fixtures

LATTICE = list(range(2026, 2051))


def _ed_value(geo_index: int, scen: Scenario, year: int) -> float:
    """Deterministic synthetic ED spanning BOTH signs across scenarios and time."""
    offset = {"low": -0.003, "reference": 0.0, "high": 0.003}[scen.value]
    return -0.004 + 0.0004 * (year - 2026) + offset + 0.001 * geo_index


def _ed_grid(geos=PRIOR_GEOGRAPHIES):
    return {geo: {scen: [_ed_value(i, scen, year) for year in LATTICE]
                  for scen in Scenario}
            for i, geo in enumerate(geos)}


def _lattices(geos=PRIOR_GEOGRAPHIES):
    return {geo: list(LATTICE) for geo in geos}


def _rows():
    return build_scenario_prior_rows(_ed_grid(), _lattices(), borrowed={Geography.LAVAL_RA13})


def _row_dict(**overrides) -> dict:
    """One VALID serialized row (the first of the fixture grid), with overrides applied."""
    row = prior_row_to_dict(_rows()[0]) | overrides
    return row


def _doc(rows=None):
    rows = _rows() if rows is None else rows
    vintage = prior_vintage({"pop-as-rmr-base.xlsx": {
        "sha256": "a" * 64, "extracted_at": "2026-07-21"}})
    return scenario_prior_document(rows, vintage, "b" * 16, frozenset({"pop-as-rmr-base.xlsx"}),
                                   run_pairing="c" * 16)


def _valid_doc():
    return _doc()


# ------------------------------------------------------------------------ the mapping

def test_the_worked_fixture_ED_point01_pins_mean_p10_p90():
    # spec §7(a)'s own worked numbers: ED = 0.01 yr^-1, beta band [1,4] uniform ->
    # mean 2.5x0.01 = 0.025, p10 1.3x0.01 = 0.013, p90 3.7x0.01 = 0.037 decimal/yr real.
    assert mapping.demo_drift_prior(0.01) == (0.025, pytest.approx(0.013),
                                              pytest.approx(0.037))


def test_beta_quantiles_are_the_uniform_CDF_inverse():
    # q(p) = a + p(b - a) over [1.0, 4.0]: q10 = 1.0+0.1*3 = 1.3, q90 = 1.0+0.9*3 = 3.7,
    # mean = 2.5. These ARE the constants the producer computes from, not parallel copies.
    assert (mapping.BETA_Q10, mapping.BETA_Q90, mapping.BETA_MEAN) == (1.3, 3.7, 2.5)
    assert (mapping.BETA_LOW, mapping.BETA_HIGH) == (1.0, 4.0)


def test_negative_ED_reverses_the_quantiles_and_keeps_the_band_ordered():
    mean, p10, p90 = mapping.demo_drift_prior(-0.01)
    assert (mean, p10, p90) == (-0.025, pytest.approx(-0.037), pytest.approx(-0.013))
    assert p10 <= mean <= p90


def test_zero_ED_maps_to_a_degenerate_band_at_the_origin():
    # Zero intercept BY CONSTRUCTION: no demographic tilt at flow balance.
    assert mapping.demo_drift_prior(0.0) == (0.0, 0.0, 0.0)


def test_the_mapping_is_linear_through_the_origin():
    for ed in (-0.02, -0.001, 0.001, 0.02):
        mean, _, _ = mapping.demo_drift_prior(ed)
        assert mean == pytest.approx(2.5 * ed)
        assert mapping.demo_drift_prior(2 * ed)[0] == pytest.approx(2 * mean)


@pytest.mark.parametrize("attr,value", [("BETA_HIGH", 5.0), ("BETA_LOW", 0.5),
                                        ("P10_POSITION", 0.05), ("TILT_RULE_V0_NEUTRAL", "tilt")])
def test_changing_the_mapping_without_a_version_bump_FAILS(attr, value, monkeypatch):
    # Spec §7(a): "changing the mapping without a version bump fails a test" — enforced as a
    # runtime refusal in the producers, so there is no code path that maps past an unstamped
    # change. The fingerprint covers EVERY parameter, including the tilt rule token.
    monkeypatch.setattr(mapping, attr, value)
    with pytest.raises(CalibrationError, match="mapping_version"):
        mapping.demo_drift_prior(0.01)
    with pytest.raises(CalibrationError, match="mapping_version"):
        mapping.drawdown_weight_tilt(0.01)


def test_the_live_fingerprint_is_registered_under_the_declared_version():
    pinned = mapping._VERSION_PINNED_FINGERPRINTS[mapping.MAPPING_VERSION]
    assert mapping.mapping_fingerprint() == pinned


def test_an_unregistered_version_refuses_even_with_untouched_parameters(monkeypatch):
    monkeypatch.setattr(mapping, "MAPPING_VERSION", "999")
    with pytest.raises(CalibrationError, match="NO registered fingerprint"):
        mapping.demo_drift_prior(0.01)


# ------------------------------------------------------------- vintage identity fields

def test_prior_vintage_carries_the_fuller_seven_a_shape():
    v = prior_vintage({"x": {"sha256": "a" * 64, "extracted_at": "2026-07-21"}})
    assert set(v) == sp.DATA_VINTAGE_IDENTITY_FIELDS | {"source_hashes"}
    assert v["source_hashes"] == {"x": {"sha256": "a" * 64, "extracted_at": "2026-07-21"}}


def test_isq_edition_is_derived_from_the_scenario_label_junction():
    # 'Référence (A2026)' / 'Faible (D2026)' / 'Fort (E2026)' -> edition 2026. If the labels
    # disagree or lose their suffixes, the derivation REFUSES rather than invents.
    assert sp.ISQ_EDITION == "2026"


def test_census_year_is_the_PIT_base_year_the_loaders_enforce():
    assert sp.CENSUS_YEAR == str(_POP_BASE_YEAR) == "2021"


def test_constants_as_of_is_the_newest_dated_anchor_revision():
    import datetime
    dated = [datetime.date.fromisoformat(a.as_of.split()[0])
             for a in CONSTANTS.values()
             if a.as_of.split()[0].count("-") == 2]
    assert dated and sp.CONSTANTS_AS_OF == max(dated).isoformat()


# ------------------------------------------------------------------ the builder + rows

def test_build_emits_the_COMPLETE_cartesian_product_in_deterministic_order():
    rows = _rows()
    assert len(rows) == len(PRIOR_GEOGRAPHIES) * len(DWELLING_TYPES) * len(HORIZON_YEARS) * 3
    keys = [(r.geography, r.dwelling_type, r.horizon_year, r.scenario) for r in rows]
    assert len(set(keys)) == len(keys)                       # no duplicates
    expected_order = [(g, d, h, s)
                      for g in PRIOR_GEOGRAPHIES for s in Scenario for h in HORIZON_YEARS
                      for d in DWELLING_TYPES]
    assert keys == expected_order                            # enum-declared emission order


def test_horizon_aggregation_is_the_ENDPOINT_value_not_the_band_mean():
    # THE DISTINGUISHING FIXTURE (spec §13's debt): endpoint and band-mean differ here, and the
    # emitted rate MUST be the series value AT the horizon year.
    def series(geo_index, scen):
        return [_ed_value(geo_index, scen, y) for y in LATTICE]

    ed = {geo: {s: series(i, s) for s in Scenario}
          for i, geo in enumerate(PRIOR_GEOGRAPHIES)}
    # 2030 endpoint -0.02 vs a band mean that is strongly positive — the two aggregations
    # cannot be confused:
    ed[Geography.MTL_RMR][Scenario.REFERENCE] = [
        0.01 if y < 2030 else -0.02 for y in LATTICE]
    rows = build_scenario_prior_rows(ed, _lattices())
    row = next(r for r in rows if r.geography == Geography.MTL_RMR
               and r.horizon_year == 2030 and r.scenario == Scenario.REFERENCE)
    assert row.excess_demand_rate == -0.02                   # the endpoint, NOT the band mean


def test_a_horizon_outside_the_projected_lattice_refuses():
    short = {geo: [y for y in years if y != 2050]
             for geo, years in _lattices().items()}
    with pytest.raises(CalibrationError, match="horizon"):
        build_scenario_prior_rows(_ed_grid(), short)


def test_ragged_lattices_across_geographies_refuse():
    lats = _lattices()
    lats[PRIOR_GEOGRAPHIES[1]] = LATTICE[:-1]
    with pytest.raises(CalibrationError, match="lattice"):
        build_scenario_prior_rows(_ed_grid(), lats)


def test_a_prior_domain_geography_with_no_ED_refuses():
    ed = _ed_grid()
    del ed[Geography.HORS_RMR]
    with pytest.raises(CalibrationError, match="HORS_RMR"):
        build_scenario_prior_rows(ed, _lattices())


def test_ra_proxies_are_NEVER_emitted():
    rows = _rows()
    assert not ({r.geography for r in rows} & RA_PROXY_MEMBERS)
    assert {r.geography.value for r in rows} == {
        g.value for g in Geography if g not in RA_PROXY_MEMBERS}


def test_borrowed_prior_rides_every_row_of_the_geography_and_no_other():
    rows = _rows()
    laval = [r for r in rows if r.geography == Geography.LAVAL_RA13]
    assert laval and all("borrowed_prior" in r.flags for r in laval)
    others = [r for r in rows if r.geography != Geography.LAVAL_RA13]
    assert all("borrowed_prior" not in r.flags for r in others)
    # ...and the closed enum never gains a member by accident:
    assert all(set(r.flags) <= PRIOR_FLAGS_ALLOWED for r in rows)


def test_v0_tilt_is_neutral_on_every_row_so_no_row_relaxes_stress():
    # balance/mapping.py's declared residual: the ED->tilt rule is an open contract debt, so v0
    # emits the identity element everywhere — which also means `never_relax_stress` (the flag
    # every tilt<1.0 row must carry) legitimately appears NOWHERE yet.
    assert all(r.drawdown_weight_tilt == 1.0 for r in _rows())


def test_drift_trio_is_always_the_mapping_of_the_row_s_own_rate():
    for r in _rows():
        mean, p10, p90 = mapping.demo_drift_prior(r.excess_demand_rate)
        assert (r.demo_drift_mean, r.demo_drift_p10, r.demo_drift_p90) == (mean, p10, p90)
        assert r.demo_drift_p10 <= r.demo_drift_mean <= r.demo_drift_p90


# ------------------------------------------- row validator: one RED fixture per violation

def test_row_field_set_equals_the_allowlist_exactly_extra():
    row = _row_dict(crash_probability=0.35)
    with pytest.raises(ValueError, match="allowlist"):
        assert_scenario_prior_row_valid(row)


def test_row_field_set_equals_the_allowlist_exactly_missing():
    row = _row_dict()
    del row["drawdown_weight_tilt"]
    with pytest.raises(ValueError, match="allowlist"):
        assert_scenario_prior_row_valid(row)


def test_the_rename_to_excess_demand_rate_is_PINNED_both_directions():
    # Amendment #26(A): ruled-in-advance rename; the quantity is a yr^-1 RATE (unit note lives
    # at this module's header). Pinned against BOTH spellings so neither can silently revert.
    assert EXCESS_DEMAND_RATE_FIELD == "excess_demand_rate"
    assert "excess_demand_fraction" not in PRIOR_ROW_FIELDS
    assert "yr^-1" in sp.__doc__                              # the unit note, where the name lives


@pytest.mark.parametrize("override,match", [
    ({"geography": "MTL_RMR "}, "geography"),                # not an enum VALUE (trailing space)
    ({"geography": "crash_probability=0.35"}, "geography"),
    ({"dwelling_type": "plex"}, "dwelling_type"),
    ({"horizon_year": 2032}, "horizon_year"),
    ({"horizon_year": "2030"}, "horizon_year"),
    ({"scenario": "bearish"}, "scenario"),
])
def test_enum_positions_admit_only_the_declared_values(override, match):
    with pytest.raises(ValueError, match=match):
        assert_scenario_prior_row_valid(_row_dict(**override))


def test_a_non_finite_drift_value_refuses():
    with pytest.raises(ValueError, match="finite"):
        assert_scenario_prior_row_valid(_row_dict(demo_drift_mean=float("nan")))
    with pytest.raises(ValueError, match="finite"):
        assert_scenario_prior_row_valid(_row_dict(excess_demand_rate=float("inf")))


def test_crossed_band_refuses():
    row = _row_dict(demo_drift_mean=0.02, demo_drift_p10=0.03, demo_drift_p90=0.04)
    with pytest.raises(ValueError, match="band ordering"):
        assert_scenario_prior_row_valid(row)


def test_negative_tilt_refuses():
    with pytest.raises(ValueError, match="tilt"):
        assert_scenario_prior_row_valid(_row_dict(drawdown_weight_tilt=-0.5))


def test_unknown_or_value_bearing_flag_string_refuses():
    row = _row_dict(flags=["never_relax_stress", "crash_probability=0.35"],
                    drawdown_weight_tilt=0.5)
    with pytest.raises(ValueError, match="closed enum"):
        assert_scenario_prior_row_valid(row)
    # an enum member on a row whose tilt does not license it reaches the FLAG-IFF-TILT rule
    # instead — the closed-enum gate is not the only door a smuggled marker dies at:
    with pytest.raises(ValueError, match="never_relax_stress"):
        assert_scenario_prior_row_valid(_row_dict(flags=["never_relax_stress"],
                                                  drawdown_weight_tilt=1.5))


def test_duplicate_flags_refuse():
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        assert_scenario_prior_row_valid(
            _row_dict(flags=["never_relax_stress", "never_relax_stress"],
                      drawdown_weight_tilt=0.5))


def test_sub_neutral_tilt_without_never_relax_stress_REFUSES():
    row = _row_dict(drawdown_weight_tilt=0.8, flags=[])
    with pytest.raises(ValueError, match="never_relax_stress"):
        assert_scenario_prior_row_valid(row)


def test_never_relax_stress_on_a_neutral_row_is_a_false_claim_and_refuses():
    row = _row_dict(drawdown_weight_tilt=1.0, flags=["never_relax_stress"])
    with pytest.raises(ValueError, match="stress RELAXATION"):
        assert_scenario_prior_row_valid(row)


# --------------------------------------------------- document set contract + the writer

def test_dropping_one_row_breaks_the_COMPLETE_product_contract():
    doc = _valid_doc()
    del doc["scenario_priors"][0]
    with pytest.raises(ValueError, match="COMPLETE Cartesian product"):
        prior_document_complete(doc)


def test_a_duplicated_row_key_refuses():
    doc = _valid_doc()
    doc["scenario_priors"].append(dict(doc["scenario_priors"][0]))
    with pytest.raises(ValueError, match="repeats row key"):
        prior_document_complete(doc)


def test_allow_nan_false_serialization_refuses_a_non_finite_tree():
    with pytest.raises(ValueError):
        _canonical_bytes({"demo_drift_mean": float("nan")})
    with pytest.raises(ValueError):
        _canonical_bytes({"demo_drift_p90": float("inf")})


def test_the_writer_refuses_a_non_finite_row_before_any_byte_reaches_disk(tmp_path):
    doc = _valid_doc()
    nan = float("nan")
    doc["scenario_priors"][0].update(demo_drift_mean=nan, demo_drift_p10=nan,
                                     demo_drift_p90=nan, excess_demand_rate=nan)
    with pytest.raises(ValueError, match="non-finite"):
        write_json_strict(tmp_path / "scenario_prior.json", doc,
                          frozenset({"pop-as-rmr-base.xlsx"}))
    assert not (tmp_path / "scenario_prior.json").exists()


def test_the_writer_runs_the_row_contract_a_builder_assembled_document_cannot_skip(tmp_path):
    doc = _valid_doc()
    doc["scenario_priors"][0]["rank"] = 1          # a smuggled, allowlist-violating field
    # (the walk's key registry refuses it before the row validator sees it — either door is
    # the write path refusing, which is what this test exists to prove.)
    with pytest.raises(ValueError, match="closed field set|allowlist"):
        write_json_strict(tmp_path / "scenario_prior.json", doc,
                          frozenset({"pop-as-rmr-base.xlsx"}))
    assert not (tmp_path / "scenario_prior.json").exists()


def test_the_built_document_passes_the_full_write_path(tmp_path):
    doc = _valid_doc()
    assert doc["schema"] == SCENARIO_PRIOR_SCHEMA
    write_json_strict(tmp_path / "scenario_prior.json", doc,
                      frozenset({"pop-as-rmr-base.xlsx"}))
    parsed = json.loads((tmp_path / "scenario_prior.json").read_text(encoding="utf-8"))
    assert parsed == json.loads(json.dumps(doc))   # round-trips through strict bytes
    assert set(parsed["scenario_priors"][0]) == PRIOR_ROW_FIELDS


def test_mapping_version_lives_outside_the_identity_envelope_so_the_token_SEES_it():
    doc = _valid_doc()
    assert "mapping_version" in payload_of(doc)     # NOT subtracted with the envelope fields
    assert doc["mapping_version"] == mapping.MAPPING_VERSION


# ============================== the COMMITTED GOLDEN, read like hde's S4b loader would ====

def _golden():
    return json.loads((GOLDEN_DIR / "scenario_prior.json").read_text(encoding="utf-8"))


def test_the_committed_golden_passes_every_contract_off_its_own_bytes():
    doc = _golden()
    _assert_finite(doc)
    assert_no_open_strings(doc, frozenset(doc["data_vintage"]["source_hashes"]))
    for row in doc["scenario_priors"]:
        assert_scenario_prior_row_valid(row)
    prior_document_complete(doc)


def test_the_committed_golden_drift_is_the_mapping_of_its_own_published_rate():
    # A CONSUMER-side consistency read: the published band must be reproducible from the
    # published rate under the STAMPED mapping version alone — no pipeline rerun needed.
    for row in _golden()["scenario_priors"]:
        mean, p10, p90 = mapping.demo_drift_prior(row[EXCESS_DEMAND_RATE_FIELD])
        assert (row["demo_drift_mean"], row["demo_drift_p10"], row["demo_drift_p90"]) \
            == (mean, p10, p90)


def test_the_committed_golden_keys_are_string_enum_values_hde_can_match():
    values = {g.value for g in Geography}
    for row in _golden()["scenario_priors"]:
        assert isinstance(row["geography"], str) and row["geography"] in values
        assert isinstance(row["horizon_year"], int)
