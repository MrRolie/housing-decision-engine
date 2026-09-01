"""Contract tests for `output/artifacts.py` — the identity envelope, the strict writer, the
closed exclusion schema, and spec §7's GENERAL "no open string anywhere" rule.

FILE PLACEMENT DIVERGES FROM THE PLAN, which put these three bodies in `test_pipeline.py`.
The seat cut plan Task 29 into artifacts / pipeline / cli; the test file follows the code
split so `test_pipeline.py` stays free for the orchestrator's own contracts.

THE LOAD-BEARING TEST IN THIS FILE IS `test_walk_visits_every_string_in_the_document`.
Every other test pins one refusal; that one pins the QUANTIFIER — spec §7 ranges over EVERY
string-typed position, so a validator that merely refuses the instances someone thought of
does not implement the rule. Its oracle (`_every_string`) is written HERE, independently of
the module's own traversal, precisely so it cannot inherit the module's blind spot.
"""
import dataclasses
import json
import math
import pathlib
import subprocess
import sys
from collections import Counter

import pytest

from demoflow.geography import MODELED_GEOGRAPHIES, Geography, Scenario
from demoflow.loaders.constants import ASSUMPTIONS_HASH_CHARS, sweep_leg_labels, assumptions_hash
import demoflow.output.artifacts as artifacts_module
from demoflow.output.artifacts import (
    DATA_VINTAGE_FIELDS,
    DERIVED_ARTIFACT_KEYS,
    EXCLUSION_ROW_FIELDS,
    IDENTITY_ENVELOPE_FIELDS,
    PAIRED_IDENTITY_FIELDS,
    RANKINGS_SCHEMA,
    SCHEMA_VERSION,
    SOURCE_KEY_REGISTRY,
    TRIPWIRE_SCHEMA,
    _DYN,
    _ITEM,
    _KEY_REGISTRY,
    _ROOT_FIELDS,
    _ROOT_OPTIONAL,
    _SCALAR_VALIDATORS,
    _DOC_CONTRACTS,
    _ROW_CONTRACTS,
    _SEQ_PATHS,
    _VALUE_VALIDATORS,
    _dump_json,
    _assert_document_complete,
    _assert_finite,
    _assert_rows_valid,
    assert_exclusion_row_valid,
    assert_no_open_strings,
    pair_identity_mismatches,
    pairing_token,
    payload_digest,
    payload_of,
    rankings_document,
    scenario_prior_document,
    stamp_pairing_token,
    tripwire_document,
    write_json_strict,
)
from demoflow.output.rankings import (UNRESOLVED_INPUTS, GeoRanking, RankingExclusion,
                                       ranking_row)
from demoflow.output.scenario_prior import (
    PRIOR_GEOGRAPHIES as _PRIOR_GEOS,
    build_scenario_prior_rows,
    prior_vintage,
)
from demoflow.output.tripwires import (
    REQUIRED_INDICATORS,
    SOURCE_REGISTRY,
    Reason,
    SourceKind,
    Status,
    TripwireResult,
)

# Real members of the code-owned source registry — the subset bound refuses anything else,
# and a test that used an invented key would green on the WRONG guard.
_SRC_A = "pop-as-rmr-base.xlsx"
_SRC_B = "census_tenure_age_98100231.csv"
_KEYS = frozenset({_SRC_A, _SRC_B})
# The identity token's width is the PRODUCER's (`constants.ASSUMPTIONS_HASH_CHARS`), not
# sha256's full 64 — the emitter used to demand 64 and therefore refused every real run's
# hash (review finding F2). Read from the declaration so this fixture cannot drift from it.
_HASH = "a" * ASSUMPTIONS_HASH_CHARS
SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"

# `_SRC_B` IS THE RAW-ANCHOR KEY (`pipeline.RUN_SOURCES` marks it `publishes=_RAW_ANCHOR`), so
# it is the entry that carries amendment #20(C)(1)'s optional `committed_sha256` — the digest of
# the bytes the run READ, beside the raw upstream member's digest §7 puts in `sha256`. Only that
# class of key carries it, which is why `_SRC_A` does not: the optional field must be EXERCISED
# by the fixture (`test_a_declared_string_position_refuses_a_non_string` reds on a declared
# position no artifact reaches) AND must not be pinned as universal.
VINTAGE = {
    "source_hashes": {
        _SRC_A: {"sha256": "2" * 64, "extracted_at": "2026-07-21"},
        _SRC_B: {"sha256": "7" * 64, "extracted_at": "2026-08-08T12:30:00Z",
                 "committed_sha256": "9" * 64},
    }
}


def _vintage() -> dict:
    return json.loads(json.dumps(VINTAGE))          # fresh copy per test — no cross-test mutation


# THE FIXTURE COVERS THE MODELED DOMAIN, and since codex r12-F2 that is a CONTRACT rather than
# a courtesy: the rankings document's set contract binds ranked geographies UNION excluded
# geographies == `MODELED_GEOGRAPHIES`, so the two-row fixture this file shipped was a 3-of-8
# document — a shape no run emits and one the emitter now refuses. Seven ranked rows carrying
# the contiguous permutation 1..7 plus HORS_RMR's spec §8 branch-iii exclusion record is the
# smallest document that is actually VALID, and it still spans every branch the walk and the row
# contracts need: a `rank_stable: false` row, all three closed flags, and rows with none.
RANKINGS = [
    GeoRanking(rank=1, geography=Geography.LAVAL_RA13, mean_ed_reference=-0.01,
               mean_ed_low=-0.02, mean_ed_high=0.003, rank_stable=False,
               flags=("closed_cohort_exceedance",)),
    GeoRanking(rank=2, geography=Geography.LANAUDIERE_RA14_PROXY, mean_ed_reference=0.004,
               mean_ed_low=-0.001, mean_ed_high=0.009, rank_stable=True,
               flags=("borrowed_prior", "ra_proxy")),
    GeoRanking(rank=3, geography=Geography.LAURENTIDES_RA15_PROXY, mean_ed_reference=0.005,
               mean_ed_low=0.001, mean_ed_high=0.011, rank_stable=True, flags=("ra_proxy",)),
    GeoRanking(rank=4, geography=Geography.MONTEREGIE_RA16_PROXY, mean_ed_reference=0.006,
               mean_ed_low=0.002, mean_ed_high=0.012, rank_stable=True, flags=("ra_proxy",)),
    GeoRanking(rank=5, geography=Geography.MTL_RMR, mean_ed_reference=0.007,
               mean_ed_low=0.003, mean_ed_high=0.013, rank_stable=True),
    GeoRanking(rank=6, geography=Geography.MTL_ISLAND_RA06, mean_ed_reference=0.008,
               mean_ed_low=0.004, mean_ed_high=0.014, rank_stable=True),
    GeoRanking(rank=7, geography=Geography.QC_RMR, mean_ed_reference=0.009,
               mean_ed_low=0.005, mean_ed_high=0.015, rank_stable=True),
]
EXCLUSIONS = [RankingExclusion(Geography.HORS_RMR, "immigrant_component_flows")]

# A COMPLETE baseline — every code-required indicator exactly once. The fixture used to carry
# two, which is the shape the emitter now refuses (review finding F3): a truncated baseline
# reads as that many green indicators, not as an incomplete file. It still spans the branches
# the string walk needs: a CROSSED record, an UNKNOWN carrying a `reason`, and OK records.
#
# AND IT SPANS AMENDMENT #21's TWO OPTIONAL MEMBERS in both directions. Five records carry the
# declarations (`freshness_years` + `source_kind`, both SourceKind arms represented, since
# `source_kind` is a declared string position and a declared position no fixture reaches is a
# guard that passes vacuously); ONE — `natural_increase_sign` — carries NEITHER, which is the
# shape a SYNTHETIC result has (`check_registry` builds missing/duplicate records from a name
# alone, with no spec behind them) and is why both members are optional rather than required.
TRIPWIRES = [
    TripwireResult("pr_landings_annual", 60010.0, SOURCE_REGISTRY["pr_landings_annual"],
                   2025, 40000.0, 50000.0, Status.CROSSED, None,
                   freshness_years=1, source_kind=SourceKind.WIRED),
    TripwireResult("registre_foncier_volume", None, SOURCE_REGISTRY["registre_foncier_volume"],
                   None, 1.0, 2.0, Status.UNKNOWN, Reason.OPERATOR_INPUT_MISSING,
                   freshness_years=1, source_kind=SourceKind.OPERATOR_SUPPLIED),
    TripwireResult("temp_resident_stock", 120000.0, SOURCE_REGISTRY["temp_resident_stock"],
                   2025, 90000.0, 150000.0, Status.OK, None,
                   freshness_years=1, source_kind=SourceKind.WIRED),
    TripwireResult("isq_edition_watch", 2025.0, SOURCE_REGISTRY["isq_edition_watch"],
                   2025, 2024.0, 2026.0, Status.OK, None,
                   freshness_years=1, source_kind=SourceKind.WIRED),
    TripwireResult("cmhc_senior_sale_5yr", 0.36, SOURCE_REGISTRY["cmhc_senior_sale_5yr"],
                   2024, 0.30, 0.45, Status.OK, None,
                   freshness_years=5, source_kind=SourceKind.OPERATOR_SUPPLIED),
    TripwireResult("natural_increase_sign", -1.0, SOURCE_REGISTRY["natural_increase_sign"],
                   2025, -2.0, 2.0, Status.OK, None),
]


# THE PER-RUN PAIRING TOKEN (spec amendment #20(C)(3)). Both builders REQUIRE it — every
# document this tree emits carries one, so a mismatched pair left by a failure between the two
# `os.replace` calls can be refused — while the SCHEMA keeps it optional so `schema_version`
# need not bump. A test-owned literal here rather than `pipeline._run_identity`: this file tests
# the emitter's contract on the token, never the producer's derivation of it.
_PAIRING = "a1b2c3d4e5f60718"


# One count per DECLARED sweep leg — the emitted `rows_moved` map (amendment #20(C)(2)). Built
# from `constants.sweep_leg_labels()` rather than typed out: the map's keys are bound to that
# vocabulary by the walk, so a fixture with hand-written labels would test a different gate. The
# counts are arbitrary; what this fixture exists to exercise is the key binding and the declared
# COUNT position, both of which pass VACUOUSLY on a document that omits the field.
ROWS_MOVED = {label: i % 3 for i, label in enumerate(sorted(sweep_leg_labels()))}


def _ranks_doc() -> dict:
    return rankings_document(RANKINGS, _vintage(), _HASH, _KEYS, run_pairing=_PAIRING,
                             exclusions=EXCLUSIONS, rows_moved=ROWS_MOVED)


def _trips_doc() -> dict:
    return tripwire_document(TRIPWIRES, _vintage(), _HASH, _KEYS, run_pairing=_PAIRING)


# The THIRD document (Tranche 2, spec §7a). Built from a synthetic but DETERMINISTIC ED grid
# over the full prior domain, so every row validator and walk position the schema declares is
# exercised: negative EDs (sign-reversed quantiles), borrowed_prior flags (LAVAL_RA13), the
# neutral tilt, and the fuller §7a vintage shape.
_PRIOR_LATTICE = list(range(2026, 2051))
_PRIOR_ED = {
    geo: {scen: [-0.004 + 0.0004 * (year - 2026)
                 + {"low": -0.002, "reference": 0.0, "high": 0.002}[scen.value]
                 + 0.001 * i
                 for year in _PRIOR_LATTICE]
          for scen in Scenario}
    for i, geo in enumerate(_PRIOR_GEOS)
}


def _priors_doc() -> dict:
    rows = build_scenario_prior_rows(
        _PRIOR_ED, {geo: list(_PRIOR_LATTICE) for geo in _PRIOR_GEOS},
        borrowed={Geography.LAVAL_RA13})
    return scenario_prior_document(rows, prior_vintage(_vintage()["source_hashes"]),
                                   _HASH, _KEYS, run_pairing=_PAIRING)


# --------------------------------------------------------------------- identity envelope

def test_rankings_document_carries_the_identity_envelope():
    doc = _ranks_doc()
    assert doc["schema"] == RANKINGS_SCHEMA
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["assumptions_hash"] == _HASH
    assert set(doc["data_vintage"]["source_hashes"]) == _KEYS
    assert [r["rank"] for r in doc["rankings"]] == [1, 2, 3, 4, 5, 6, 7]
    assert set(doc["rankings"][0]) == {"geography", "mean_ed_reference", "mean_ed_low",
                                       "mean_ed_high", "rank", "rank_stable", "flags"}
    assert isinstance(doc["rankings"][0]["rank_stable"], bool)
    assert doc["exclusions"] == [{"geography": "HORS_RMR",
                                  "unresolved_input": "immigrant_component_flows"}]


def test_tripwire_document_carries_the_same_envelope():
    ranks, trips = _ranks_doc(), _trips_doc()
    assert trips["schema"] == TRIPWIRE_SCHEMA
    assert trips["assumptions_hash"] == ranks["assumptions_hash"]
    assert trips["schema_version"] == ranks["schema_version"]
    assert trips["data_vintage"] == ranks["data_vintage"]
    assert {t["indicator"] for t in trips["indicators"]} == REQUIRED_INDICATORS


@pytest.mark.parametrize("vintage", [
    {},                                   # no source_hashes at all
    {"source_hashes": {}},                # present but EMPTY — looks provenanced, identifies nothing
    {"source_hashes": "none"},            # not a map
    "2026",                               # not a vintage at all
])
def test_envelope_refuses_a_vintage_that_identifies_nothing(vintage):
    with pytest.raises(ValueError, match="source_hashes"):
        rankings_document(RANKINGS, vintage, _HASH, _KEYS, run_pairing=_PAIRING)


def test_documents_must_carry_typed_rows_not_dicts():
    """`rank_geographies` / `exclude_from_rankings` / `evaluate_indicator` all return TYPED
    records. Accepting a bare dict here would reopen every field the dataclasses close."""
    with pytest.raises(ValueError, match="GeoRanking"):
        rankings_document([{"rank": 1}], _vintage(), _HASH, _KEYS, run_pairing=_PAIRING)
    with pytest.raises(ValueError, match="RankingExclusion"):
        rankings_document([], _vintage(), _HASH, _KEYS, run_pairing=_PAIRING,
                          exclusions=[{"geography": "HORS_RMR",
                                       "unresolved_input": "immigrant_component_flows"}])
    with pytest.raises(ValueError, match="TripwireResult"):
        tripwire_document([{"indicator": "pr_landings_annual"}], _vintage(), _HASH, _KEYS,
                          run_pairing=_PAIRING)


@pytest.mark.parametrize("results,shape", [
    ([], "empty"),
    (lambda: TRIPWIRES[:1], "truncated to one — reads as ONE GREEN indicator, not as a gap"),
    (lambda: TRIPWIRES[:-1], "one indicator short"),
    (lambda: TRIPWIRES + TRIPWIRES[:1], "duplicated"),
])
def test_tripwire_document_refuses_a_baseline_that_is_not_the_required_set(results, shape):
    """Review finding F3 — the class, not its weakest member. The landed emitter refused a
    ZERO-indicator baseline and accepted a TRUNCATED and a DUPLICATED one, on a derivation
    ("an emitter that skipped `check_registry` cannot ship a file whose zero indicators would
    read as zero problems") that applies verbatim to the siblings it did not check — and the
    truncated shape is the more dangerous one, since a one-indicator file reads as one green
    indicator rather than as an obviously empty file. Spec §7c names all three together:
    "empty registry, missing required indicator, or duplicate key ⇒ UNKNOWN/nonzero"."""
    with pytest.raises(ValueError, match="code-owned required indicator set"):
        tripwire_document(results() if callable(results) else results, _vintage(), _HASH, _KEYS,
                          run_pairing=_PAIRING)


def test_tripwire_document_accepts_the_complete_required_set():
    """The proof the gate above can PASS — a refusal that nothing satisfies is not a gate."""
    doc = _trips_doc()
    assert sorted(t["indicator"] for t in doc["indicators"]) == sorted(REQUIRED_INDICATORS)


def test_rankings_document_refuses_an_artifact_that_accounts_for_nothing():
    """The NARROWEST member of the rankings set contract, kept as its own refusal because its
    message is the informative one: zero ranked rows AND zero exclusion records accounts for
    nothing at all. The coverage clause below would refuse it too, less legibly.

    THE OLD SECOND HALF OF THIS DOCSTRING WAS WRONG and is the finding, one sentence over: it
    said "`rankings: []` WITH an exclusion is spec §8 branch iii and is pinned as accepted
    below". One exclusion beside an empty rankings array leaves SEVEN modeled geographies
    unaccounted for; what §8 licenses is an empty rankings array whose EXCLUSIONS COVER THE
    DOMAIN, which is pinned in the set-contract section."""
    with pytest.raises(ValueError, match="accounts for no geography"):
        rankings_document([], _vintage(), _HASH, _KEYS, run_pairing=_PAIRING)


# ------------------------------------------------ spec §7's GENERAL no-open-string rule

def _every_string(node, path=()):
    """INDEPENDENT ORACLE — the test's own traversal, deliberately not the module's.

    Yields ('key'|'value', string) for every string-typed position in `node`. Written naively
    and completely: if the module's walk skips a position this oracle finds, the Counter
    comparison below reds. That is the bound carry A1 demands — "a test that fails when a new
    unvalidated string position is added" — and it is what makes the coverage claim MEASURED
    rather than asserted."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                yield ("key", key)
            yield from _every_string(value, path + (key,))
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _every_string(item, path)
    elif isinstance(node, str):
        yield ("value", node)


@pytest.mark.parametrize("build", [_ranks_doc, _trips_doc, _priors_doc])
def test_walk_visits_every_string_in_the_document(build):
    doc = build()
    visited = assert_no_open_strings(doc, _KEYS)
    assert Counter((kind, value) for kind, _path, value in visited) == Counter(_every_string(doc))
    # and the document really does contain strings — an empty-vs-empty comparison is vacuous.
    assert len(visited) > 10


def test_no_open_string_rejects_smuggled_source_hashes_key():
    doc = _ranks_doc()
    doc["data_vintage"]["source_hashes"]["crash_probability=0.35"] = {
        "sha256": "0" * 64, "extracted_at": "2026-07-21"}
    with pytest.raises(ValueError, match="source_hashes key"):
        assert_no_open_strings(doc, _KEYS)


@pytest.mark.parametrize("mutate", [
    lambda d: d.__setitem__("note", "crash_probability=0.35"),
    lambda d: d["rankings"][0].__setitem__("note", "crash_probability=0.35"),
    lambda d: d["exclusions"][0].__setitem__("note", "crash_probability=0.35"),
    lambda d: d["data_vintage"].__setitem__("note", "crash_probability=0.35"),
    lambda d: d["data_vintage"]["source_hashes"][_SRC_A].__setitem__("note", "x"),
])
def test_a_new_field_cannot_open_a_string_channel(mutate):
    doc = _ranks_doc()
    mutate(doc)
    with pytest.raises(ValueError, match="not in the closed field set|source_hashes key"):
        assert_no_open_strings(doc, _KEYS)


def test_an_absent_required_field_is_refused_too():
    """The walk binds the keys that are PRESENT; without this it would also have to bind the
    ones that are absent, or `{}` under `source_hashes[src]` ships an entry with no digest."""
    doc = _ranks_doc()
    del doc["assumptions_hash"]
    with pytest.raises(ValueError, match="missing"):
        assert_no_open_strings(doc, _KEYS)

    doc = _ranks_doc()
    doc["data_vintage"]["source_hashes"][_SRC_A].pop("sha256")
    with pytest.raises(ValueError, match="missing"):
        assert_no_open_strings(doc, _KEYS)


def test_a_registered_key_with_no_value_validator_is_still_refused():
    """The second half of carry A1's bound. `as_of` is a REGISTERED tripwire-record key with
    no string validator (it is an int year), so a string there is a position the key registry
    admits and the value table does not cover — it must raise, not pass."""
    doc = _trips_doc()
    doc["indicators"][0]["as_of"] = "crash_probability=0.35"
    with pytest.raises(ValueError, match="no validator for string position"):
        assert_no_open_strings(doc, _KEYS)


@pytest.mark.parametrize("mutate", [
    lambda d: d.__setitem__("schema", "demoflow.crash.v1"),
    lambda d: d.__setitem__("schema_version", "0.35"),
    lambda d: d.__setitem__("assumptions_hash", "crash_probability=0.35"),
    lambda d: d["rankings"][0].__setitem__("geography", "crash_probability=0.35"),
    lambda d: d["rankings"][0].__setitem__("flags", ["crash_probability=0.35"]),
    lambda d: d["exclusions"][0].__setitem__("geography", "crash_probability=0.35"),
    lambda d: d["exclusions"][0].__setitem__("unresolved_input", "crash_probability=0.35"),
])
def test_every_rankings_string_position_is_enum_or_format_bound(mutate):
    doc = _ranks_doc()
    mutate(doc)
    with pytest.raises(ValueError):
        assert_no_open_strings(doc, _KEYS)


@pytest.mark.parametrize("mutate", [
    lambda d: d["indicators"][0].__setitem__("indicator", "crash_probability=0.35"),
    lambda d: d["indicators"][0].__setitem__("source", "crash_probability=0.35"),
    lambda d: d["indicators"][0].__setitem__("status", "crash_probability=0.35"),
    lambda d: d["indicators"][1].__setitem__("reason", "crash_probability=0.35"),
])
def test_every_tripwire_string_position_is_enum_or_format_bound(mutate):
    doc = _trips_doc()
    mutate(doc)
    with pytest.raises(ValueError):
        assert_no_open_strings(doc, _KEYS)


def _slots(node, path):
    """Every CONCRETE (container, key) slot in `node` matching a canonical module path.

    `[]` expands to every list index and `*` to every map key, so a canonical path resolves to
    all the places it actually occurs — including `indicators[].reason`, which exists on the
    UNKNOWN record only. Written HERE rather than reusing the module's traversal, same reason
    as `_every_string`: an oracle that shares the walk's blind spot cannot see it."""
    if not path:
        return
    head, rest = path[0], path[1:]
    if head == _ITEM:
        if isinstance(node, list):
            for i, item in enumerate(node):
                yield from (_slots(item, rest) if rest else iter([(node, i)]))
    elif head == _DYN:
        if isinstance(node, dict):
            for key, value in node.items():
                yield from (_slots(value, rest) if rest else iter([(node, key)]))
    elif isinstance(node, dict) and head in node:
        yield from (_slots(node[head], rest) if rest else iter([(node, head)]))


def _every_slot_refuses(path, bad):
    """Plant `bad` at every occurrence of `path` in both artifacts; each must refuse. Returns
    how many slots were exercised so a caller can refuse a vacuous pass."""
    exercised = 0
    for build in (_ranks_doc, _trips_doc, _priors_doc):
        for index in range(len(list(_slots(build(), path)))):
            doc = build()
            container, key = list(_slots(doc, path))[index]
            container[key] = bad
            with pytest.raises(ValueError):
                assert_no_open_strings(doc, _KEYS)
            exercised += 1
    return exercised


@pytest.mark.parametrize("bad", [None, 42, 0.35, True])
@pytest.mark.parametrize("path", sorted(_VALUE_VALIDATORS))
def test_a_declared_string_position_refuses_a_non_string(path, bad):
    """Review finding F1, and the reason this test is derived from `_VALUE_VALIDATORS` rather
    than from a hand-list: the walk dispatched on `isinstance(node, str)`, so EVERY declared
    string position was silently unvalidated whenever its value was not a string.
    `assumptions_hash: null`, `sha256: null` (an entry with NO digest), `schema_version: 2`
    all passed the sanctioned builders and landed on disk. The identity envelope is the one
    region with no second owner — row positions are re-bound by the row validators, envelope
    positions by the walk alone — so a null there is a false-green on artifact identity, and
    carry A6's data-vs-code attribution dies with it.

    Parametrizing over the TABLE is what makes this a class bound: a position added tomorrow
    is covered the day it is declared, with no test edit."""
    assert _every_slot_refuses(path, bad), (
        f"declared string position {path} occurs in neither artifact — the guard would pass "
        "vacuously; either the fixture no longer exercises it or the declaration is dead")


@pytest.mark.parametrize("bad", [None, 42, "crash_probability=0.35"])
@pytest.mark.parametrize("path", [
    ("data_vintage",),
    ("data_vintage", "source_hashes"),
    ("data_vintage", "source_hashes", _DYN),
    ("rankings",),
    ("rankings", _ITEM),
    ("rankings", _ITEM, "flags"),
    ("exclusions",),
    ("exclusions", _ITEM),
    ("indicators",),
    ("indicators", _ITEM),
    ("scenario_priors",),
    ("scenario_priors", _ITEM),
    ("scenario_priors", _ITEM, "flags"),
])
def test_a_container_position_refuses_a_scalar(path, bad):
    """The structural half of F1's root cause. The same `isinstance` dispatch let a CONTAINER
    position hold a scalar: `source_hashes[src] = None`, `rankings = 5`, `exclusions = None`
    all fell through to the scalar pass, taking every child position (and its key registry
    check) with them — an artifact can lose its whole rankings array and still validate."""
    assert _every_slot_refuses(path, bad), f"container position {path} occurs in neither artifact"


def test_the_document_must_declare_which_contract_it_claims():
    with pytest.raises(ValueError, match="schema"):
        assert_no_open_strings({"schema": "demoflow.rankings.v2"}, _KEYS)


def test_a_non_string_key_is_refused():
    doc = _ranks_doc()
    doc["data_vintage"][2026] = "x"
    with pytest.raises(ValueError, match="non-string key"):
        assert_no_open_strings(doc, _KEYS)


# ----------------------------------------------------- the code-owned source-key registry

def test_allowed_source_keys_cannot_widen_the_code_owned_registry():
    """Same class as tripwires' review finding F4: a caller-supplied allowlist on a gate whose
    premise is a CODE-owned vocabulary is a gate the caller can retune. The run may NARROW to
    the sources it actually read; it may not mint a key.

    The minted key is the P9 catalogue index — a file that really is in the tree and really is
    outside the registry (pins.py: "NOT loaded by the module — it is EVIDENCE"), so this binds
    a reachable mistake rather than a typo. It was `ownership_by_geo_age.json` until review
    finding F1 put the four DERIVED artifacts INSIDE the registry: the run genuinely reads
    them, so declaring one is no longer minting anything."""
    with pytest.raises(ValueError, match="code-owned source registry"):
        assert_no_open_strings(_ranks_doc(), frozenset({"catalogue_member_index_p9.json"}))


def test_the_source_registry_names_every_file_a_run_may_declare_read():
    assert _SRC_A in SOURCE_KEY_REGISTRY and _SRC_B in SOURCE_KEY_REGISTRY
    assert "ircc_pr_by_cma.csv" in SOURCE_KEY_REGISTRY
    # THE DERIVED RATE ARTIFACTS (review finding F1). Every rate in the model is read from one
    # of these four files at run time, so the envelope must be able to publish a digest of the
    # bytes the run consumed — `SOURCE_KEY_REGISTRY` is what admits the key. They are GENERATED
    # rather than acquired, which is why they were outside the registry and why the hole was
    # invisible: naming their upstream SOURCES catches a provenance edit and nothing else.
    assert DERIVED_ARTIFACT_KEYS == frozenset({
        "ownership_by_geo_age.json", "headship_by_age.json",
        "living_arrangement.json", "ownership_hors_aligned.json"})
    assert DERIVED_ARTIFACT_KEYS <= SOURCE_KEY_REGISTRY
    # ...and they are named by their OWN loaders' constants, never restated here — the same
    # "one declaration, no drift" rule this module applies to every other bound vocabulary.
    from demoflow.loaders import census, hors_aligned, living_arrangement
    assert DERIVED_ARTIFACT_KEYS == frozenset({
        census.OWNERSHIP_ARTIFACT, census.HEADSHIP_ARTIFACT,
        living_arrangement.ARTIFACT, hors_aligned.ARTIFACT})
    # pins.py: the P9 catalogue index is "NOT loaded by the module — it is EVIDENCE". A run
    # can never legitimately declare it read, so admitting it would be an unfired allowance.
    assert "catalogue_member_index_p9.json" not in SOURCE_KEY_REGISTRY


# ------------------------------------------------------------------- format validators

@pytest.mark.parametrize("bad", ["0" * 63, "0" * 65, "A" * 64, "0" * 64 + "\n", "", "z" * 64])
def test_source_hash_digests_must_be_64_hex(bad):
    """Spec §7 attaches 64-hex to `source_hashes` VALUES by name: "sha256-of-raw-response ...
    values must be 64-hex". `pipeline._source_hashes` produces them off `hashlib.sha256`."""
    doc = _ranks_doc()
    doc["data_vintage"]["source_hashes"][_SRC_A]["sha256"] = bad
    with pytest.raises(ValueError, match="64-hex"):
        assert_no_open_strings(doc, _KEYS)


def test_the_emitter_accepts_the_trees_own_assumptions_hash():
    """Review finding F2 — THE SEAM, which is why this test exists at all.

    The landed emitter validated `assumptions_hash` as 64-hex, a length spec §7 never states
    (it attaches 64-hex to `source_hashes` values) and which the tree's ONLY producer
    contradicts: `constants.assumptions_hash()` returns a 16-char digest, itself pinned by
    `test_constants.py`. Two committed contracts disagreed and the suite was green because no
    test crossed the seam — so the emitter REFUSED the very hash every run computes, and
    carry A6's "a correct hash drops in with no reshaping" was false. The fix binds the gate
    to the producer instead of to a guessed length; this test is what keeps them bound."""
    h = assumptions_hash()
    assert len(h) == ASSUMPTIONS_HASH_CHARS
    assert rankings_document(RANKINGS, _vintage(), h, _KEYS, run_pairing=_PAIRING,
                             exclusions=EXCLUSIONS)["assumptions_hash"] == h
    assert tripwire_document(TRIPWIRES, _vintage(), h, _KEYS,
                         run_pairing=_PAIRING)["assumptions_hash"] == h


@pytest.mark.parametrize("bad", ["0" * 15, "0" * 17, "0" * 64, "A" * 16, "0" * 16 + "\n",
                                 "", "z" * 16])
def test_assumptions_hash_must_be_the_producers_digest_form(bad):
    """`"0" * 64` is in the RED list deliberately: it is the shape the landed validator
    demanded, and it is NOT what any run produces."""
    doc = _ranks_doc()
    doc["assumptions_hash"] = bad
    with pytest.raises(ValueError, match="hex"):
        assert_no_open_strings(doc, _KEYS)


@pytest.mark.parametrize("bad", ["9999-99-99", "2026-02-30", "2026-02-29", "2026-13-01",
                                 "2026-07-21 whenever", "yesterday", ""])
def test_extracted_at_must_be_a_real_calendar_instant(bad):
    """Carry A3: the plan's `^\\d{4}-\\d{2}-\\d{2}([T ].*)?$` accepts 9999-99-99. A regex is
    not a calendar — the value is PARSED."""
    doc = _ranks_doc()
    doc["data_vintage"]["source_hashes"][_SRC_A]["extracted_at"] = bad
    with pytest.raises(ValueError, match="ISO-8601"):
        assert_no_open_strings(doc, _KEYS)


@pytest.mark.parametrize("good", ["2026-07-21", "2026-08-08T12:30:00Z", "2026-08-08T12:30",
                                  "2024-02-29"])   # a REAL leap day; 2026-02-29 is in the RED list
def test_extracted_at_accepts_real_iso8601_instants(good):
    doc = _ranks_doc()
    doc["data_vintage"]["source_hashes"][_SRC_A]["extracted_at"] = good
    assert_no_open_strings(doc, _KEYS)


# --------------------------------------------------------- the closed exclusion schema

def test_hors_rmr_fallback_iii_excluded_from_rankings_with_typed_record():
    """codex r10: an unresolvable demand input -> EXCLUDED from rankings entirely (no ED row),
    named in a typed run-level exclusion record.

    THE DOCUMENT IS THE ONE THE BRANCH ACTUALLY PRODUCES, which this test used to shortcut: it
    passed `rankings=[]` beside HORS_RMR's exclusion, a 1-of-8 file the set contract now refuses
    (codex r12-F2). Nothing about branch iii makes the other seven geographies unrankable —
    §8 says the rankings cover the REMAINING members — so the honest fixture is seven ranked
    rows plus the one exclusion, and the claim under test is sharper for it: "excluded ENTIRELY"
    is HORS_RMR appearing in `exclusions` and in NO ranking row, which is what is asserted."""
    doc = rankings_document(RANKINGS, _vintage(), _HASH, _KEYS, run_pairing=_PAIRING,
                            exclusions=EXCLUSIONS)
    assert doc["exclusions"] == [{"geography": "HORS_RMR",
                                  "unresolved_input": "immigrant_component_flows"}]
    assert "HORS_RMR" not in {row["geography"] for row in doc["rankings"]}


@pytest.mark.parametrize("row,match", [
    ({"geography": "HORS_RMR", "unresolved_input": "crash_probability=0.35"}, "closed schema"),
    ({"geography": "crash_probability=0.35",
      "unresolved_input": "immigrant_component_flows"}, "closed schema"),
    ({"geography": "HORS_RMR"}, "closed schema"),
    ({"geography": "HORS_RMR", "unresolved_input": "immigrant_component_flows",
      "crash_probability": 0.35}, "closed schema"),
])
def test_exclusion_record_is_closed_on_every_position(row, match):
    """Carry A2: the plan bound the KEY SET and `unresolved_input` and left `geography` FREE
    TEXT — run 28's finding F3 one file over. All three positions are bound here."""
    with pytest.raises(ValueError, match=match):
        assert_exclusion_row_valid(row)


def test_the_exclusion_field_set_is_the_two_declared_positions():
    assert EXCLUSION_ROW_FIELDS == frozenset({"geography", "unresolved_input"})


def test_the_EMITTER_emits_exactly_the_declared_exclusion_allowlist():
    """Amendment #22(B), and the gap it names: `exclusions` reached production as a REQUIRED root
    member of the rankings document with NO schema home in the spec — `exclusions` and
    `unresolved_input` appear zero times in it — taken on no authority but the code's.
    #22(B) authorizes it retroactively (`schema_version` does NOT bump: every emitted document has
    carried it since the member was added, so no consumer's reading changes) and requires the
    binding this test is.

    IT BINDS THE EMITTER TO THE DECLARATION, DIRECTLY — never through the golden, which
    re-ratifies whatever the emitter emits and is exactly how an unauthorized required member
    shipped. `RankingExclusion.as_row` is the one function that serializes the record, so a field
    added there reaches every emitted rankings document; the assertion is that its key set EQUALS
    the declared allowlist, not that it contains it. `test_the_exclusion_field_set_is_the_two_
    declared_positions` above pins the CONSTANT to the two names #22(B) rules; this pins the
    EMITTED ROW to the constant, and neither alone closes the gap: the constant could be widened
    with the allowlist test updated, or the emitter could grow a field the constant never sees.

    THE ROOT MEMBERSHIP IS BOUND IN THE SAME BODY, because "REQUIRED" is the half of the ruling a
    row-field test cannot see: `exclusions` must sit in the rankings schema's REQUIRED root set
    and NOT in the optional one, so a run that computed no exclusions emits `[]` rather than
    omitting the member and leaving a consumer unable to tell "none" from "not recorded"."""
    row = RankingExclusion(Geography.HORS_RMR, sorted(UNRESOLVED_INPUTS)[0]).as_row()
    assert set(row) == EXCLUSION_ROW_FIELDS == frozenset({"geography", "unresolved_input"}), (
        f"the exclusion emitter serializes {sorted(row)}; amendment #22(B) rules the row field "
        f"allowlist EXACTLY {sorted(EXCLUSION_ROW_FIELDS)}")
    assert "exclusions" in _ROOT_FIELDS[RANKINGS_SCHEMA], (
        "`exclusions` is a REQUIRED root member of the rankings document (amendment #22(B)) and "
        "the root field set does not require it")
    assert "exclusions" not in _ROOT_OPTIONAL[RANKINGS_SCHEMA], (
        "`exclusions` is declared OPTIONAL — an absent member cannot be distinguished from an "
        "empty one, so 'no geography was excluded' would read the same as 'nothing recorded it'")
    assert "exclusions" not in _ROOT_FIELDS[TRIPWIRE_SCHEMA]      # rankings only


def test_the_two_phase_stamp_REFUSES_a_builder_that_folds_the_token_into_its_payload():
    """`stamp_pairing_token`'s own refusal, which is a raise-path this tree added and nothing else
    exercises — an unfired guard is a guard nobody has shown can fire.

    THE DEFECT IT CATCHES IS SELF-REFERENCE. The token is computed from the payloads of the FIRST
    pass and stamped on the SECOND, so a builder that copies the token (or any envelope field)
    into its CONTENT makes the second pass's payload differ from the one the token was computed
    over: the shipped documents would then carry a token that does not identify their own bytes,
    silently, with every other gate green. Same class for a non-deterministic builder.

    THE HONEST BUILDER LEG IS NOT DECORATION: a `stamp_pairing_token` that raised unconditionally
    would satisfy the refusal above, so the well-behaved builder must come back stamped with
    `pairing_token`'s value over exactly the payloads it built."""
    def folding(token):
        # `note` sits OUTSIDE the identity envelope, so it is payload — and it carries the token.
        return {"x.json": {"schema": "s", "schema_version": "1", "data_vintage": {},
                           "assumptions_hash": _HASH, "run_pairing": token, "note": token}}

    def honest(token):
        return {"x.json": {"schema": "s", "schema_version": "1", "data_vintage": {},
                           "assumptions_hash": _HASH, "run_pairing": token, "note": "constant"}}

    with pytest.raises(ValueError, match="self-referential"):
        stamp_pairing_token(folding)

    stamped = stamp_pairing_token(honest)
    assert stamped["x.json"]["run_pairing"] == pairing_token(stamped), (
        "the stamped token is not the pairing function of the documents it was stamped on")
    assert payload_digest(stamped["x.json"]) == payload_digest(honest("whatever")["x.json"]), (
        "the payload moved with the token — this builder was supposed to be token-independent")


def test_the_identity_envelope_field_set_is_what_the_payload_digest_subtracts():
    """`IDENTITY_ENVELOPE_FIELDS` is what `payload_of` subtracts to get the content the pairing
    token binds (amendment #22(C)), and `_envelope` is what stamps those positions. TWO
    declarations of one set, bound here in BOTH directions: a sixth envelope field added to
    `_envelope` alone would silently become part of every payload digest — making the token a
    function of provenance it is specified not to see — and a field dropped from this set while
    `_envelope` still stamps it would silently stop being subtracted."""
    stamped = artifacts_module._envelope(RANKINGS_SCHEMA, _vintage(), _HASH, _PAIRING)
    assert set(stamped) == IDENTITY_ENVELOPE_FIELDS
    assert payload_of(stamped) == {}, "the envelope alone must leave NO payload"
    doc = _ranks_doc()
    assert set(payload_of(doc)) == set(doc) - IDENTITY_ENVELOPE_FIELDS
    assert "run_pairing" in IDENTITY_ENVELOPE_FIELDS, (
        "the token would be hashed into its own input — self-reference, which is the reason the "
        "digest is taken over the payload rather than the whole document")


def test_the_paired_identity_fields_are_the_ENVELOPE_MINUS_the_schema_string():
    """Spec amendment #24(C). The consumer protocol compares identity ACROSS the two documents,
    and the set it compares is `IDENTITY_ENVELOPE_FIELDS` less exactly one member.

    BOTH DIRECTIONS, because both failures are silent. A sixth envelope field that never joins
    `PAIRED_IDENTITY_FIELDS` is a fifth member of the class this amendment exists to close — an
    identity declaration no cross-pair check reads. A field in this tuple that is NOT an envelope
    member would be compared out of the payload, which `run_pairing` already binds.

    `schema` IS THE ONE EXCLUSION AND IT IS ASSERTED BY NAME, never as "some member is dropped":
    the two documents' `schema` strings differ BY DESIGN, so a set that included it would refuse
    every honest pair — the failure mode a gate that refuses everything hides best."""
    assert set(PAIRED_IDENTITY_FIELDS) == IDENTITY_ENVELOPE_FIELDS - {"schema"}
    assert len(set(PAIRED_IDENTITY_FIELDS)) == len(PAIRED_IDENTITY_FIELDS), "duplicate member"
    ranks, trips = _ranks_doc(), _trips_doc()
    assert ranks["schema"] != trips["schema"], (
        "the two documents no longer carry different `schema` strings — the exclusion above rests "
        "on that difference, and if it is gone the field belongs in the compared set")


def test_a_pair_differing_ONLY_in_schema_version_is_REFUSED():
    """THE RED amendment #24(C) names: `schema_version` is invisible to the pairing token BY
    CONSTRUCTION, so the three published steps all pass on a pair that disagrees about the
    document format it declares.

    THE NON-VACUITY LEGS ARE THE TEST. First the three retired steps are asserted to PASS on the
    mutated pair — token equal, `data_vintage` equal, `assumptions_hash` equal, and the payload
    digest bit-identical — so what the fourth comparison catches is provably not reachable by any
    of them. Then the honest pair is asserted ACCEPTED: a comparison that refused every pair would
    satisfy the refusal leg and be worthless."""
    ranks, trips = _ranks_doc(), _trips_doc()
    assert pair_identity_mismatches(ranks, trips) == (), (
        f"the honest pair one run emits is refused on {pair_identity_mismatches(ranks, trips)}")

    moved = dict(trips) | {"schema_version": SCHEMA_VERSION + "-mutant"}
    assert moved["run_pairing"] == ranks["run_pairing"]                       # step 1 passes
    assert moved["data_vintage"] == ranks["data_vintage"]                     # step 2 passes
    assert moved["assumptions_hash"] == ranks["assumptions_hash"]             # step 3 passes
    assert payload_digest(moved) == payload_digest(trips), (
        "`schema_version` reached the payload — then the token could see it and this whole "
        "amendment is about a hole that does not exist")
    assert pair_identity_mismatches(ranks, moved) == ("schema_version",), (
        f"a pair declaring two different `schema_version`s is accepted: "
        f"{pair_identity_mismatches(ranks, moved)}")


def test_an_ABSENT_pairing_token_is_no_evidence_while_an_absent_REQUIRED_member_is_a_mismatch():
    """The page's own two rules, which pull in opposite directions and are therefore both pinned.

    `run_pairing` absent on either file is NO PAIRING EVIDENCE — pre-amendment-#20(C)(3) documents
    carry none, they are still VALID, and refusing them would break the backward compatibility the
    un-bumped `schema_version` was kept for. But absence must not read as a MATCH either, which is
    what `.get()` would do on both sides, so the other three members treat absent-vs-present as
    the disagreement it is."""
    ranks, trips = _ranks_doc(), _trips_doc()
    legacy = {k: v for k, v in trips.items() if k != "run_pairing"}
    assert pair_identity_mismatches(ranks, legacy) == (), (
        "a legacy document carrying no pairing token is REFUSED — absence is not a refusal")
    for field in set(PAIRED_IDENTITY_FIELDS) - {"run_pairing"}:
        stripped = {k: v for k, v in trips.items() if k != field}
        assert pair_identity_mismatches(ranks, stripped) == (field,), (
            f"a document that dropped `{field}` entirely compares EQUAL to one that carries it")


# ------------------------------------------------------------------------- the writer

def test_artifacts_reject_nan(tmp_path):
    with pytest.raises(ValueError):
        write_json_strict(tmp_path / "x.json", {"schema": "t", "v": math.nan}, _KEYS)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_finiteness_is_asserted_before_the_write(tmp_path, bad):
    doc = _ranks_doc()
    doc["rankings"][0]["mean_ed_reference"] = bad
    with pytest.raises(ValueError, match="non-finite"):
        write_json_strict(tmp_path / "x.json", doc, _KEYS)
    assert not (tmp_path / "x.json").exists()       # refuse means NOTHING lands on disk


def test_assert_finite_inspects_dict_keys():
    """Carry A5's note, closed rather than recorded: the plan's `_assert_finite` recursed over
    VALUES only, and `json.dump` stringifies a float key — so a NaN key rode through the
    finiteness gate."""
    with pytest.raises(ValueError, match="non-finite"):
        _assert_finite({math.nan: 1})


def test_the_writer_refuses_a_document_that_never_passed_the_walk(tmp_path):
    """`vintage.py` states the derivation this test pins: "spec §7's `write_json_strict`
    re-checks 64-hex on the way out". A writer that only serialized would make that committed
    claim false, and would let a document assembled outside the two builders reach disk."""
    doc = _ranks_doc()
    doc["data_vintage"]["source_hashes"][_SRC_A]["sha256"] = "not-a-digest"
    out = tmp_path / "rankings.json"
    with pytest.raises(ValueError, match="64-hex"):
        write_json_strict(out, doc, _KEYS)
    assert not out.exists()


@pytest.mark.parametrize("field_name,bad", [
    ("rank_stable", 1), ("rank", 0), ("rank", -3), ("mean_ed_reference", True),
])
def test_the_writer_owns_the_rankings_row_type_contract(tmp_path, field_name, bad):
    """Stress gate F6. The row TYPE contract had exactly ONE enforcement point on the emit
    path — `rankings_document`'s per-row call — and deleting that CALL SITE passed the whole
    suite, after which `rank_stable: 1`, `rank: 0`, `rank: -3` and `mean_ed_reference: true`
    all shipped. Classic body-tested / wiring-unpinned: no-op'ing the FUNCTION was killed by
    `tests/test_rankings.py`, deleting its call was not. Nor was it redundant with the walk:
    all four are scalars at scalar positions, so `assert_no_open_strings` passes them.

    THE CONTRACT NOW HAS ONE OWNER AND IT SITS ON THE WRITE PATH — there is no builder call
    left to delete, and a document assembled outside the two builders meets it too. These
    four payloads are exactly the ones the gate measured reaching disk."""
    doc = _ranks_doc()
    doc["rankings"][0][field_name] = bad
    out = tmp_path / "rankings.json"
    with pytest.raises(ValueError, match="rankings row"):
        write_json_strict(out, doc, _KEYS)
    assert not out.exists()                       # refuse means NOTHING lands on disk


@pytest.mark.parametrize("index,field_name,bad,match", [
    (1, "current_value", 1.5, "must be NULL"),        # UNKNOWN(nullable) carrying a value
    (0, "reason", "stale", "exactly when"),           # CROSSED carrying a reason
    (0, "as_of", None, "non-null"),                   # a verdict with no measurement date
])
def test_the_writer_owns_the_tripwire_record_contract(tmp_path, index, field_name, bad, match):
    """The same move on the sibling document. Every one of these is a CROSS-FIELD rule the
    string walk cannot see — it dispatches on declared position, and each of these positions
    holds a legal value in isolation."""
    doc = _trips_doc()
    doc["indicators"][index][field_name] = bad
    out = tmp_path / "tripwire_baseline.json"
    with pytest.raises(ValueError, match=match):
        write_json_strict(out, doc, _KEYS)
    assert not out.exists()


def test_the_writer_emits_sorted_stable_bytes(tmp_path):
    out = tmp_path / "rankings.json"
    write_json_strict(out, _ranks_doc(), _KEYS)
    first = out.read_bytes()
    write_json_strict(out, _ranks_doc(), _KEYS)
    assert out.read_bytes() == first                        # byte-stable across runs
    text = first.decode("utf-8")
    assert text.endswith("}\n") and "\r" not in text        # LF-pinned, trailing newline
    body = json.loads(text)
    assert body == _ranks_doc()
    top = [line.split('"')[1] for line in text.splitlines()[1:] if line.startswith('  "')]
    assert top == sorted(top)                               # sort_keys=True, golden-diff stable


def test_dump_json_pins_utf8_independently_of_the_locale(tmp_path):
    """Carry A4. `open(path, "w")` takes the LOCALE's encoding; under LC_ALL=C that is ASCII,
    so a non-ASCII payload raises — an ENVIRONMENTAL failure this suite would never show,
    because the dev locale is UTF-8. Run in a C-locale subprocess so the pin is exercised."""
    out = tmp_path / "accents.json"
    code = (f"import sys; sys.path.insert(0, {str(SRC_DIR)!r});\n"
            "from demoflow.output.artifacts import _dump_json\n"
            f"_dump_json({str(out)!r}, {{'k': 'Montr\\u00e9al / Qu\\u00e9bec'}})\n")
    env = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin", "PYTHONUTF8": "0",
           "PYTHONCOERCECLOCALE": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_bytes().decode("utf-8"))["k"] == "Montréal / Québec"


def test_the_vintage_field_set_is_declared_and_minimal():
    """Tranche 1's envelope carries source_hashes and nothing else. §7a's isq_edition /
    census_year / constants_as_of belong to the Tranche-2 ScenarioPrior emitter; adding one
    here is a one-line registry edit PLUS a declared validator, which is the point."""
    assert DATA_VINTAGE_FIELDS == frozenset({"source_hashes"})


# ------------------------------------------------- the per-record contract table itself

def _row_positions(schema: str) -> tuple:
    """The root positions of `schema` that carry an ARRAY OF RECORDS — derived from the
    module's own declarations rather than restated: a ROOT field that `_SEQ_PATHS` declares
    an array and whose ITEM node `_KEY_REGISTRY` declares a map. `rankings[].flags` is out
    because it is not a root field, and a root array of STRINGS would be out because its item
    is a `_VALUE_VALIDATORS` position the walk already binds.

    IT RANGES OVER THE OPTIONAL ROOT FIELDS TOO (spec amendment #20(C) added the first ones).
    Today neither is an array of records — `run_pairing` is a string and `rows_moved` a map — so
    the derived tuple is unchanged; the union is here so that the FIRST optional root field that
    IS an array of records cannot ship with its rows unbound, which is the exact door this test
    exists to keep shut and the one an amendment is most likely to open."""
    fields = _ROOT_FIELDS[schema] | _ROOT_OPTIONAL[schema]
    return tuple(sorted(field for field in fields
                        if (field,) in _SEQ_PATHS and (field, _ITEM) in _KEY_REGISTRY))


def test_every_document_types_record_positions_are_bound_by_the_contract_table():
    """The review finding on the F6 repair: `_ROW_CONTRACTS`' header claimed that declaring
    the contracts as ONE DISPATCHED TABLE means "a third document type cannot arrive with its
    rows unbound" — but nothing pinned the table's shape, so dropping the `exclusions` entry
    passed the whole suite (measured) and a third schema could be registered in `_ROOT_FIELDS`
    with no entry at all. This is that claim as a MEASUREMENT, in both directions: no document
    type without a contract, no contract without a document type, and per schema exactly the
    record positions it declares — no more (a stray entry never dispatches) and no fewer (an
    unbound position is a row that reaches disk unchecked).

    It is what makes the `exclusions` entry load-bearing rather than decorative. That row is
    subsumed by the walk TODAY — every sub-case `assert_exclusion_row_valid` refuses is
    refused earlier by `assert_no_open_strings` (measured), so no writer-path test can
    discriminate on it — but subsumption is a property of today's key/value tables, not of the
    contract: the first cross-field rule that validator grows (the shape
    `assert_tripwire_record_valid` already has) is enforced on the write path only if the
    entry is there."""
    assert set(_ROW_CONTRACTS) == set(_ROOT_FIELDS)
    for schema in _ROOT_FIELDS:
        bound = tuple(sorted(field for field, _ in _ROW_CONTRACTS[schema]))
        assert bound == _row_positions(schema), schema
        assert len(_ROW_CONTRACTS[schema]) == len(bound)          # no duplicated entry


def test_a_document_type_with_no_declared_contract_refuses_instead_of_passing():
    """The dispatch is FAIL-CLOSED, which is what the header comment above the table asserts.
    It read `_ROW_CONTRACTS.get(doc["schema"], ())`, so an unlisted schema validated NO rows
    and returned silently — the one thing the table's stated reason for existing rules out.
    `ValueError`, not a bare `KeyError`: `cli.REFUSALS` turns exactly that class into a named
    nonzero exit, and a KeyError would escape it as a traceback."""
    with pytest.raises(ValueError, match="no per-record contract"):
        _assert_rows_valid({"schema": "demoflow.some.future.v1"})


# ---------------------------------------------------- the declared COUNT positions (§7's sibling)

@pytest.mark.parametrize("bad", [True, False, 1.0, -1, None, "2"])
@pytest.mark.parametrize("path", sorted(_SCALAR_VALIDATORS))
def test_a_declared_count_position_refuses_anything_that_is_not_a_count(path, bad):
    """`_VALUE_VALIDATORS` binds every STRING position (spec §7's general rule) and the row
    validators own the numeric ROW fields, which left one class with no owner: a numeric position
    at a node that is NOT an array of records, so `_ROW_CONTRACTS` cannot reach it. `rows_moved`
    is the first — a MAP of per-leg counts — and a count is exactly where `true` (an int
    subclass), `1.0` and `null` ride the scalar fall-through looking like measurements.

    Parametrized over the TABLE, like its string sibling: a count position declared tomorrow is
    covered the day it is declared, with no edit here. `False`/`0`-adjacent cases are in the list
    because `isinstance(True, int)` is True in Python, so the bool exclusion has to be explicit;
    `"2"` is there because `float("2")` succeeds and a coercion-only check would admit a string
    into a numeric field, which is the same side-channel one position over."""
    assert _every_slot_refuses(path, bad), (
        f"declared count position {path} occurs in neither artifact — the guard would pass "
        "vacuously; either the fixture no longer exercises it or the declaration is dead")


def test_the_rows_moved_map_admits_only_DECLARED_leg_labels():
    """The map's keys are a CODE-owned vocabulary, not the caller's. `source_hashes` keys are
    narrowed per run (a run may declare fewer sources than it could read); the declared sweep grid
    is the same for every run, so a key that is not a declared leg is a count for a leg the sweep
    never ran — which is what the emitted field exists to make impossible."""
    doc = _ranks_doc()
    assert set(doc["rows_moved"]) == sweep_leg_labels()
    doc["rows_moved"]["q_live_per_year=0.07"] = 1          # an endpoint the grid does not declare
    with pytest.raises(ValueError, match="sweep leg"):
        assert_no_open_strings(doc, _KEYS)


def test_a_rankings_document_may_omit_rows_moved_ENTIRELY():
    """`rows_moved=None` means "no per-leg claim" and the field is then ABSENT, not empty — the
    reduced-sweep path, where `_rank_stability` evaluated no leg at all. An empty map beside
    `rank_stable: false` would read as "no leg moved anything", which is the opposite of what a
    sweep that never ran measured, so the OPTIONALITY has to be real at the emitter."""
    doc = rankings_document(RANKINGS, _vintage(), _HASH, _KEYS, run_pairing=_PAIRING,
                            exclusions=EXCLUSIONS)
    assert "rows_moved" not in doc
    assert_no_open_strings(doc, _KEYS)                     # and it still validates


# ============================================================================================
# THE WHOLE-DOCUMENT SET CONTRACT (spec §7b — codex r12-F2)
# ============================================================================================
#
# THE ASYMMETRY IS THE FINDING. Spec §7(a) mandates as a contract test that the Tranche-2
# ScenarioPrior row keys form "the COMPLETE Cartesian product ... with NO duplicates" (unbuilt);
# §7(c) mandates that "every code-required indicator is present exactly once" (built, and
# enforced as multiset equality in `tripwire_document`). §7(b) — the TRANCHE-1 CORE OUTPUT, the
# artifact that actually ships — had NEITHER. Measured on the committed tree: both
# `rankings_document` and `write_json_strict` built, validated and wrote a geography that was
# simultaneously RANKED and EXCLUDED, duplicated exclusion records, duplicate rank values, a
# rank-99 gap, 2-based ranks, all-ranks-1, the same geography ranked twice, and a ONE-row
# ranking (1 of 8 modeled geographies). §8 states the obligation — "the rankings cover the
# remaining members" — and nothing held it.
#
# EVERY SHAPE IS RED AT BOTH DOORS, deliberately: the builder is where a run assembles the set
# and the writer is the one gate a document assembled OUTSIDE the builders (a future Tranche-2
# emitter, a hand-patched file) still meets. The two arms below are the same fixture list
# through the two doors.

_UNRESOLVED = sorted(UNRESOLVED_INPUTS)[0]


def _renumber(rankings, ranks):
    """The same rows carrying a different rank vector — `dataclasses.replace` so the frozen
    row's every other field, and its type, are the shipped ones."""
    return [dataclasses.replace(gr, rank=rank) for gr, rank in zip(rankings, ranks, strict=True)]


_SET_REDS = [
    # ranked AND excluded, and the exclusion names a member that is NOT §8's HORS_RMR terminal
    # branch — the record's `geography` position is bound to the WHOLE enum, so the overlap is
    # reachable at every member.
    pytest.param(RANKINGS, EXCLUSIONS + [RankingExclusion(Geography.MTL_RMR, _UNRESOLVED)],
                 "both RANKED and EXCLUDED", id="ranked_and_excluded"),
    pytest.param(RANKINGS, EXCLUSIONS + EXCLUSIONS,
                 "excludes a geography more than once", id="duplicated_exclusion_records"),
    pytest.param(_renumber(RANKINGS, [1, 2, 3, 3, 5, 6, 7]), EXCLUSIONS,
                 "contiguous permutation", id="duplicate_rank_values"),
    pytest.param(_renumber(RANKINGS, [1, 2, 3, 4, 5, 6, 99]), EXCLUSIONS,
                 "contiguous permutation", id="rank_99_gap"),
    pytest.param(_renumber(RANKINGS, [2, 3, 4, 5, 6, 7, 8]), EXCLUSIONS,
                 "contiguous permutation", id="contiguous_but_2_based"),
    pytest.param(_renumber(RANKINGS, [1] * len(RANKINGS)), EXCLUSIONS,
                 "contiguous permutation", id="all_ranks_1"),
    pytest.param(RANKINGS[:-1] + [dataclasses.replace(RANKINGS[-1],
                                                      geography=RANKINGS[0].geography)],
                 EXCLUSIONS, "ranks a geography more than once", id="same_geography_ranked_twice"),
    pytest.param(RANKINGS[:1], EXCLUSIONS,
                 "modeled geography domain", id="one_row_of_eight"),
]


def _swap_rows(rankings, exclusions) -> dict:
    """A document that passes every OTHER gate — envelope, walk, row contracts — and differs
    from the shipped shape ONLY in its row SET, so a red on the write path is attributable to
    the set contract and to nothing else. The arrays are built through the producers' own
    serializers (`ranking_row`, `RankingExclusion.as_row`), never hand-shaped dicts."""
    doc = _ranks_doc()
    doc["rankings"] = [ranking_row(gr) for gr in rankings]
    doc["exclusions"] = [exc.as_row() for exc in exclusions]
    return doc


@pytest.mark.parametrize("rankings,exclusions,match", _SET_REDS)
def test_the_rankings_set_contract_refuses_the_shape_AT_THE_BUILDER(rankings, exclusions, match):
    with pytest.raises(ValueError, match=match):
        rankings_document(rankings, _vintage(), _HASH, _KEYS, run_pairing=_PAIRING,
                          exclusions=exclusions, rows_moved=ROWS_MOVED)


@pytest.mark.parametrize("rankings,exclusions,match", _SET_REDS)
def test_the_rankings_set_contract_refuses_the_shape_ON_THE_WRITE_PATH(
        tmp_path, rankings, exclusions, match):
    """The writer is the door a document the builders never saw comes through, and it is the
    one this module calls "the sole artifact-contract validator". A refusal must also leave
    NOTHING on disk — the file is opened only after every gate passes."""
    out = tmp_path / "rankings.json"
    with pytest.raises(ValueError, match=match):
        write_json_strict(out, _swap_rows(rankings, exclusions), _KEYS)
    assert not out.exists()


def test_the_set_contract_ACCEPTS_the_document_the_run_emits(tmp_path):
    """A refusal nothing satisfies is not a gate: the covering document passes both doors."""
    out = tmp_path / "rankings.json"
    write_json_strict(out, _ranks_doc(), _KEYS)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert [row["rank"] for row in written["rankings"]] == list(range(1, len(RANKINGS) + 1))
    assert ({row["geography"] for row in written["rankings"]}
            | {row["geography"] for row in written["exclusions"]}
            == {geo.value for geo in MODELED_GEOGRAPHIES})


def test_an_EMPTY_rankings_array_is_legitimate_when_the_exclusions_cover_the_domain(tmp_path):
    """COVERAGE, not "everything must be ranked". Spec §8 branch iii excludes a geography whose
    demand-side input is unresolvable, and the branch has no cardinality limit — a vintage that
    resolved NO geography's arrivals excludes all eight, and that document is honest: it claims
    no ranking and names, per geography, the input that could not be resolved. The shape the
    emitter refuses is the one that accounts for LESS than the domain, in either array."""
    doc = rankings_document([], _vintage(), _HASH, _KEYS, run_pairing=_PAIRING,
                            exclusions=[RankingExclusion(geo, _UNRESOLVED)
                                        for geo in sorted(MODELED_GEOGRAPHIES,
                                                          key=lambda g: g.value)])
    assert doc["rankings"] == []
    out = tmp_path / "rankings.json"
    write_json_strict(out, doc, _KEYS)
    assert len(json.loads(out.read_text(encoding="utf-8"))["exclusions"]) == 8


@pytest.mark.parametrize("mutate,shape", [
    (lambda records: records[:1], "truncated to one"),
    (lambda records: records[:-1], "one short"),
    (lambda records: records + records[:1], "duplicated"),
    (lambda records: [], "empty"),
])
def test_the_writer_owns_the_tripwire_COMPLETENESS_contract_TOO(tmp_path, mutate, shape):
    """The sibling entry in the same table, and it is load-bearing rather than decorative: the
    tripwire completeness rule used to live at the BUILDER only, so a baseline assembled
    anywhere else reached disk as "that many green indicators". Same set, same message, now
    also on the write path."""
    doc = _trips_doc()
    doc["indicators"] = mutate(doc["indicators"])
    out = tmp_path / "tripwire_baseline.json"
    with pytest.raises(ValueError, match="code-owned required indicator set"):
        write_json_strict(out, doc, _KEYS)
    assert not out.exists()


def test_every_document_type_has_a_declared_SET_contract():
    """The `_ROW_CONTRACTS` pin, one level up. A document type registered in `_ROOT_FIELDS`
    with no SET contract is exactly §7(b)'s hole reproduced for the next schema — which is the
    Tranche-2 ScenarioPrior emitter, whose §7(a) Cartesian-product-with-no-duplicates rule is
    the same class of check and lands in this table. Both directions: no document type without
    a set contract, no set contract without a document type."""
    assert set(_DOC_CONTRACTS) == set(_ROOT_FIELDS)


def test_a_document_type_with_no_declared_SET_contract_refuses_instead_of_passing():
    """FAIL-CLOSED, like the row dispatch beside it: a `.get(schema, None)` that returned
    "no contract" would make the table's stated reason for existing false. `ValueError`, not
    `KeyError` — `cli.REFUSALS` turns that class into a named nonzero exit."""
    with pytest.raises(ValueError, match="no document-level contract"):
        _assert_document_complete({"schema": "demoflow.some.future.v1"})
