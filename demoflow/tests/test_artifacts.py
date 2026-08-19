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
import json
import math
import pathlib
import subprocess
import sys
from collections import Counter

import pytest

from demoflow.geography import Geography
from demoflow.loaders.constants import ASSUMPTIONS_HASH_CHARS, assumptions_hash
from demoflow.output.artifacts import (
    DATA_VINTAGE_FIELDS,
    DERIVED_ARTIFACT_KEYS,
    EXCLUSION_ROW_FIELDS,
    RANKINGS_SCHEMA,
    SCHEMA_VERSION,
    SOURCE_KEY_REGISTRY,
    TRIPWIRE_SCHEMA,
    _DYN,
    _ITEM,
    _KEY_REGISTRY,
    _ROOT_FIELDS,
    _ROW_CONTRACTS,
    _SEQ_PATHS,
    _VALUE_VALIDATORS,
    _dump_json,
    _assert_finite,
    _assert_rows_valid,
    assert_exclusion_row_valid,
    assert_no_open_strings,
    rankings_document,
    tripwire_document,
    write_json_strict,
)
from demoflow.output.rankings import GeoRanking, RankingExclusion
from demoflow.output.tripwires import (
    REQUIRED_INDICATORS,
    SOURCE_REGISTRY,
    Reason,
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

VINTAGE = {
    "source_hashes": {
        _SRC_A: {"sha256": "2" * 64, "extracted_at": "2026-07-21"},
        _SRC_B: {"sha256": "7" * 64, "extracted_at": "2026-08-08T12:30:00Z"},
    }
}


def _vintage() -> dict:
    return json.loads(json.dumps(VINTAGE))          # fresh copy per test — no cross-test mutation


RANKINGS = [
    GeoRanking(rank=1, geography=Geography.LAVAL_RA13, mean_ed_reference=-0.01,
               mean_ed_low=-0.02, mean_ed_high=0.003, rank_stable=False,
               flags=("closed_cohort_exceedance",)),
    GeoRanking(rank=2, geography=Geography.LANAUDIERE_RA14_PROXY, mean_ed_reference=0.004,
               mean_ed_low=-0.001, mean_ed_high=0.009, rank_stable=True,
               flags=("borrowed_prior", "ra_proxy")),
]
EXCLUSIONS = [RankingExclusion(Geography.HORS_RMR, "immigrant_component_flows")]

# A COMPLETE baseline — every code-required indicator exactly once. The fixture used to carry
# two, which is the shape the emitter now refuses (review finding F3): a truncated baseline
# reads as that many green indicators, not as an incomplete file. It still spans the branches
# the string walk needs: a CROSSED record, an UNKNOWN carrying a `reason`, and OK records.
TRIPWIRES = [
    TripwireResult("pr_landings_annual", 60010.0, SOURCE_REGISTRY["pr_landings_annual"],
                   2025, 40000.0, 50000.0, Status.CROSSED, None),
    TripwireResult("registre_foncier_volume", None, SOURCE_REGISTRY["registre_foncier_volume"],
                   None, 1.0, 2.0, Status.UNKNOWN, Reason.OPERATOR_INPUT_MISSING),
    TripwireResult("temp_resident_stock", 120000.0, SOURCE_REGISTRY["temp_resident_stock"],
                   2025, 90000.0, 150000.0, Status.OK, None),
    TripwireResult("isq_edition_watch", 2025.0, SOURCE_REGISTRY["isq_edition_watch"],
                   2025, 2024.0, 2026.0, Status.OK, None),
    TripwireResult("cmhc_senior_sale_5yr", 0.36, SOURCE_REGISTRY["cmhc_senior_sale_5yr"],
                   2024, 0.30, 0.45, Status.OK, None),
    TripwireResult("natural_increase_sign", -1.0, SOURCE_REGISTRY["natural_increase_sign"],
                   2025, -2.0, 2.0, Status.OK, None),
]


def _ranks_doc() -> dict:
    return rankings_document(RANKINGS, _vintage(), _HASH, _KEYS, exclusions=EXCLUSIONS)


def _trips_doc() -> dict:
    return tripwire_document(TRIPWIRES, _vintage(), _HASH, _KEYS)


# --------------------------------------------------------------------- identity envelope

def test_rankings_document_carries_the_identity_envelope():
    doc = _ranks_doc()
    assert doc["schema"] == RANKINGS_SCHEMA
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["assumptions_hash"] == _HASH
    assert set(doc["data_vintage"]["source_hashes"]) == _KEYS
    assert [r["rank"] for r in doc["rankings"]] == [1, 2]
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
        rankings_document(RANKINGS, vintage, _HASH, _KEYS)


def test_documents_must_carry_typed_rows_not_dicts():
    """`rank_geographies` / `exclude_from_rankings` / `evaluate_indicator` all return TYPED
    records. Accepting a bare dict here would reopen every field the dataclasses close."""
    with pytest.raises(ValueError, match="GeoRanking"):
        rankings_document([{"rank": 1}], _vintage(), _HASH, _KEYS)
    with pytest.raises(ValueError, match="RankingExclusion"):
        rankings_document([], _vintage(), _HASH, _KEYS,
                          exclusions=[{"geography": "HORS_RMR",
                                       "unresolved_input": "immigrant_component_flows"}])
    with pytest.raises(ValueError, match="TripwireResult"):
        tripwire_document([{"indicator": "pr_landings_annual"}], _vintage(), _HASH, _KEYS)


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
        tripwire_document(results() if callable(results) else results, _vintage(), _HASH, _KEYS)


def test_tripwire_document_accepts_the_complete_required_set():
    """The proof the gate above can PASS — a refusal that nothing satisfies is not a gate."""
    doc = _trips_doc()
    assert sorted(t["indicator"] for t in doc["indicators"]) == sorted(REQUIRED_INDICATORS)


def test_rankings_document_refuses_an_artifact_that_accounts_for_nothing():
    """The rankings sibling of the same class. Every modeled geography is either ranked or
    carries an exclusion record, so a document with NEITHER accounts for nothing and is never
    a legitimate shape — while `rankings: []` WITH an exclusion is spec §8 branch iii and is
    pinned as accepted below."""
    with pytest.raises(ValueError, match="accounts for no geography"):
        rankings_document([], _vintage(), _HASH, _KEYS)


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


@pytest.mark.parametrize("build", [_ranks_doc, _trips_doc])
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
    for build in (_ranks_doc, _trips_doc):
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
    values must be 64-hex". `loaders/vintage.py` produces them through its own `_hexdigest`."""
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
    assert rankings_document(RANKINGS, _vintage(), h, _KEYS,
                             exclusions=EXCLUSIONS)["assumptions_hash"] == h
    assert tripwire_document(TRIPWIRES, _vintage(), h, _KEYS)["assumptions_hash"] == h


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
    # codex r10: unresolvable demand input -> EXCLUDED from rankings entirely (no ED row),
    # named in a typed run-level exclusion record.
    doc = rankings_document([], _vintage(), _HASH, _KEYS, exclusions=EXCLUSIONS)
    assert doc["rankings"] == []
    assert doc["exclusions"][0]["geography"] == "HORS_RMR"


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
    is a `_VALUE_VALIDATORS` position the walk already binds."""
    return tuple(sorted(field for field in _ROOT_FIELDS[schema]
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
