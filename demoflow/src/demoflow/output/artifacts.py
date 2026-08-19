"""Golden-artifact JSON writers (spec §4/§7/§9) — the identity envelope, the strict writer,
and spec §7's GENERAL "no open string anywhere" rule.

Every shipped file opens with the same envelope {schema, schema_version, data_vintage (incl.
source_hashes), assumptions_hash} above its rows (codex r7-F6), is serialized with
`allow_nan=False` over a pre-asserted-finite tree (codex r4-F3), and is validated against a
closed schema on the way out.

THE WALK IS A WALK. The plan body shipped a function named `assert_no_open_strings` whose
docstring claimed spec §7's general rule — "a validator walks the full document tree" — and
whose code inspected exactly one path, `doc["data_vintage"]["source_hashes"]`. Every other
string in both artifacts was unchecked: the schema token, the assumptions hash, every row's
geography, every flag, every indicator/source/status/reason, and every dict KEY at every
level. A gate carrying a false derivation is part of the defect, so the name was not narrowed
— the quantifier was implemented. `_walk` descends the WHOLE emitted document; every position
is looked up in the tables below and a position with no declaration RAISES. That inverts the
failure mode: a future field addition cannot silently reopen the channel, because silence is
what raises.

IT DISPATCHES ON THE DECLARATION, NEVER ON THE VALUE — the correction review finding F1
forced, and the reason the paragraph above is now true rather than nearly true. A walk that
asks `isinstance(node, str)` before consulting its table consults the table only when the
value HAPPENS to be a string, so every declared position was silently unbound the moment it
held something else: `assumptions_hash: null`, `sha256: null` (a source entry with NO digest),
`schema_version: 2`, `rankings: null` all reached the scalar fall-through and shipped. Twelve
of the thirteen declared string positions were bypassable that way, and the region it left
open was the IDENTITY ENVELOPE — the one part of the document no row validator re-binds, and
the part §9's data-vs-code attribution rests on. So `_declared_kind(path)` decides what the
position must hold and the runtime kind must match it: a declared string holding null is not
a lenient pass, it is an UNDECLARED position, and a container that collapses to a scalar takes
every check below it with it.

THREE DECLARATIONS, all code-owned, and between them they close the tree:
  * `_KEY_REGISTRY` (+ `_DYNAMIC_KEY_PATHS`) — per node path, the (required, optional) field
    set, and which nodes are maps. Keys are bound by membership, so a smuggled field name
    refuses; required fields are bound by PRESENCE, so a dropped `assumptions_hash` or a
    `source_hashes` entry with no digest refuses too. An artifact that merely LOOKS
    provenanced is the shape `loaders/vintage.py` exists to refuse, and this is the same
    refusal at the last gate.
  * `_SEQ_PATHS` — the positions that carry a JSON array.
  * `_VALUE_VALIDATORS` — per string position, the enum/registry membership or the format
    parse. Registry-bound positions reuse the vocabularies their own modules own
    (`SOURCE_REGISTRY`, `RANKING_FLAGS_ALLOWED`, `UNRESOLVED_INPUTS`, `Geography`,
    `Status`, `Reason`) rather than restating them — one declaration, no drift. The two hex
    widths likewise read from their producers: 64 for `source_hashes` values (spec §7 by
    name), `constants.ASSUMPTIONS_HASH_CHARS` for the identity token.

COVERAGE IS MEASURED, NOT ASSERTED. `assert_no_open_strings` RETURNS every string position it
validated, and `tests/test_artifacts.py` compares that against an independent naive traversal
written in the test. If the walk ever skips a position the document contains, the counts
disagree and the suite reds — which is what makes the coverage claim in this docstring a
measurement rather than a promise.

THE ROW VALIDATORS STILL RUN. `assert_rankings_row_valid` / `assert_tripwire_record_valid`
bind NUMERIC types and cross-field rules the walk genuinely cannot see — `rank_stable: 1` (an
int where the sweep verdict must be a bool), `rank: 0`, a CROSSED record carrying `stale`, an
UNKNOWN record with a non-null `current_value`. All four are scalars at scalar positions, so
the walk passes them and the row contract is what refuses. The walk is the quantifier over
positions and their kinds; the row validators are the per-record contract. Neither subsumes
the other and both are called.

COMPLETENESS IS BOUND AT THIS BOUNDARY TOO, for both artifacts, because a partial file is a
false green rather than a small one: a tripwire baseline must carry EXACTLY the code-owned
required indicator set (mirroring `run_exit_code`, so the file and the exit code cannot
disagree), and a rankings artifact must account for at least one geography — ranked or
excluded. Neither costs a legitimate run anything.

THE ALLOWLIST A CALLER SUPPLIES MAY ONLY NARROW. `allowed_source_keys` names the sources a
particular run actually read, and it is checked to be a SUBSET of `SOURCE_KEY_REGISTRY`, the
code-owned set of files a run may declare it read — every file this package acquires, plus the
four DERIVED rate artifacts it generates and then opens at run time (see that constant). Without
that bound, the one gate whose premise is a code-owned vocabulary would be retunable from its own
call site — the shape `tripwires.check_registry` closed at review finding F4 (`required` was a
parameter there, and `check_registry(['x'], required={'x'})` returned "complete").
"""
import json
import math
import re
from datetime import datetime
from pathlib import Path

from demoflow.geography import Geography
from demoflow.loaders import census, hors_aligned, living_arrangement
from demoflow.loaders.constants import ASSUMPTIONS_HASH_CHARS
from demoflow.loaders.ircc import CSV_NAME as IRCC_CSV_NAME
from demoflow.loaders.pins import WORKBOOK_SHA256
from demoflow.output.rankings import (
    RANKING_FLAGS_ALLOWED,
    RANKINGS_ROW_FIELDS,
    UNRESOLVED_INPUTS,
    GeoRanking,
    RankingExclusion,
    assert_rankings_row_valid,
    ranking_row,
)
from demoflow.output.tripwires import (
    REQUIRED_INDICATORS,
    SOURCE_REGISTRY,
    TRIPWIRE_RECORD_REQUIRED,
    Reason,
    Status,
    TripwireResult,
    assert_tripwire_record_valid,
    tripwire_record,
)

SCHEMA_VERSION = "1"
RANKINGS_SCHEMA = "demoflow.rankings.v1"
TRIPWIRE_SCHEMA = "demoflow.tripwire_baseline.v1"

# Both are CLOSED vocabularies, not free strings — they ride the emitted document.
SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})

# TRANCHE-1 data_vintage, deliberately minimal and EXACT. Spec §7's shipped-file envelope
# mandates "data_vintage (incl. source_hashes)"; §7a's fuller {isq_edition, census_year,
# constants_as_of} shape belongs to the TRANCHE-2 ScenarioPrior emitter. The three are not
# pre-admitted here because an allowed-but-never-emitted field is an unfired allowance, and
# because `isq_edition` has no code-owned vocabulary anywhere in this tree today (measured
# 2026-08-18) — an unbound token in the envelope is precisely the channel §7 closes. The ISQ
# edition identity is already carried, by digest: the workbooks are byte-pinned and their
# digests ride `source_hashes`. Adding a field is one registry line PLUS a declared validator,
# and the walk reds until both exist. That is the intended cost.
DATA_VINTAGE_FIELDS = frozenset({"source_hashes"})
SOURCE_HASH_FIELDS = frozenset({"sha256", "extracted_at"})

# Run-level exclusion (codex r10 / spec §8 branch iii): a geography whose demand-side input is
# unresolvable is EXCLUDED FROM RANKINGS ENTIRELY — no ED row — and named in a typed record.
# BOTH positions are bound. The plan bound the key set and `unresolved_input` and left
# `geography` FREE TEXT, so `{"geography": "crash_probability=0.35", "unresolved_input":
# "immigrant_component_flows"}` passed the validator whose whole job is to make that quantity
# inexpressible — run 28's finding F3, one file over.
EXCLUSION_ROW_FIELDS = frozenset({"geography", "unresolved_input"})

# The CODE-OWNED source registry: every file a run may declare it READ, and can therefore hash
# into `data_vintage.source_hashes`. `catalogue_member_index_p9.json` is excluded on pins.py's
# own words — "NOT loaded by the module — it is EVIDENCE" — so no run can legitimately declare
# it read, and admitting it would be an allowance that can never fire. The IRCC feed joins from
# the other side: its digest is RECORDED rather than pinned (monthly refresh), which is exactly
# spec §7's "sha256-of-raw-response at extract time".
#
# THE DERIVED RATE ARTIFACTS ARE IN IT, and the reason is review finding F1. The registry was
# scoped to the files this package ACQUIRES, which put the four GENERATED artifacts outside it —
# and those four are where EVERY rate in the model is read from at run time. Their loaders
# verify each artifact's `_provenance`-recorded SOURCE digests against the pins and nothing
# hashes the payload, so editing one rate cell and leaving `_provenance` alone loads clean,
# moves every geography's excess demand and can reorder the rankings, all under a byte-identical
# envelope (measured). The envelope's whole claim is that a red is attributable to data-vs-code;
# it could not make that call for the inputs that drive the entire model. Naming their upstream
# sources — which the pipeline also does, and keeps doing — catches a re-derivation, never a
# payload edit. So the run publishes a digest of the bytes it actually read, and this is the
# vocabulary that admits the key.
#
# The names come from each loader's OWN constant, never restated here: the same "one
# declaration, no drift" rule this module applies to every other bound vocabulary.
_EVIDENCE_ONLY = frozenset({"catalogue_member_index_p9.json"})
DERIVED_ARTIFACT_KEYS = frozenset({
    census.OWNERSHIP_ARTIFACT, census.HEADSHIP_ARTIFACT,
    living_arrangement.ARTIFACT, hors_aligned.ARTIFACT,
})
SOURCE_KEY_REGISTRY = ((frozenset(WORKBOOK_SHA256) - _EVIDENCE_ONLY)
                       | frozenset({IRCC_CSV_NAME}) | DERIVED_ARTIFACT_KEYS)

_GEOGRAPHY_VALUES = frozenset(g.value for g in Geography)
_STATUS_VALUES = frozenset(s.value for s in Status)
_REASON_VALUES = frozenset(r.value for r in Reason)
_INDICATORS = frozenset(SOURCE_REGISTRY)
_DECLARED_SOURCES = frozenset(SOURCE_REGISTRY.values())

# `fullmatch`, not `match` with `^...$`: in Python `$` also matches before a trailing newline,
# so `re.match(r"^[0-9a-f]{64}$", "0"*64 + "\n")` SUCCEEDS. A digest with a newline welded on
# is not the digest, and it is the shape a sloppy file read produces.
#
# TWO WIDTHS, EACH READ FROM ITS OWN PRODUCER, never a single guessed constant. Spec §7 attaches
# 64-hex to `source_hashes` VALUES by name ("sha256-of-raw-response ... values must be 64-hex")
# and says nothing about `assumptions_hash`; `loaders/constants.py` declares that one's width and
# is its only producer. The landed body validated BOTH at 64, so the emitter refused the very hash
# every run computes — a gate whose premise was a plan-header parenthetical rather than either
# contract it sits between (review finding F2).
SHA256_HEX_CHARS = 64

_ITEM = "[]"     # list-index collapse in a canonical path
_DYN = "*"       # registry-keyed map collapse in a canonical path


def _fmt(path: tuple[str, ...]) -> str:
    out = "$"
    for seg in path:
        out += seg if seg == _ITEM else "." + seg
    return out


# ------------------------------------------------------------------ finiteness (codex r4-F3)

def _assert_finite(obj) -> None:
    """Refuse any non-finite float anywhere in the tree, KEYS INCLUDED.

    The plan body recursed over dict VALUES only. `json.dump` stringifies a float key, so
    `{float('nan'): 1}` walked straight past a gate whose entire purpose is that no such value
    reaches the artifact. One line, and the gate now ranges over what it claims to."""
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError(f"non-finite value in artifact: {obj}")
    if isinstance(obj, dict):
        for key, value in obj.items():
            _assert_finite(key)
            _assert_finite(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _assert_finite(value)


# ------------------------------------------------------- the string-position binding tables

def _bind(allowed, label: str):
    """Membership in a closed, code-owned vocabulary."""
    frozen = frozenset(allowed)

    def check(value: str, path: tuple[str, ...]) -> None:
        if value not in frozen:
            raise ValueError(f"{label} at {_fmt(path)}: {value!r} is outside the closed set "
                             f"{sorted(frozen)}")
    return check


def _hex(chars: int, label: str):
    pattern = re.compile(f"[0-9a-f]{{{chars}}}")

    def check(value: str, path: tuple[str, ...]) -> None:
        if not pattern.fullmatch(value):
            raise ValueError(f"{label} at {_fmt(path)}: {value!r} is not a {chars}-hex "
                             "lowercase digest")
    return check


def _iso8601(label: str):
    """PARSE the timestamp — carry A3. The plan's `^\\d{4}-\\d{2}-\\d{2}([T ].*)?$` validates
    SHAPE and accepts `9999-99-99`, `2026-02-30` and `2026-07-21 whenever`. A regex is not a
    calendar; `datetime.fromisoformat` is (verified on the 3.12.3 interpreter this project
    pins: it accepts a bare date, `T`-separated times and a trailing `Z`, and refuses all
    three shapes above)."""
    def check(value: str, path: tuple[str, ...]) -> None:
        try:
            datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} at {_fmt(path)}: {value!r} is not an ISO-8601 instant "
                             f"({exc})") from exc
    return check


_ROOT_FIELDS = {
    RANKINGS_SCHEMA: frozenset({"schema", "schema_version", "data_vintage", "assumptions_hash",
                                "rankings", "exclusions"}),
    TRIPWIRE_SCHEMA: frozenset({"schema", "schema_version", "data_vintage", "assumptions_hash",
                                "indicators"}),
}

# path -> (REQUIRED fields, OPTIONAL fields). Both directions bind: an unknown key is a
# smuggled field, an absent required key is an artifact missing a piece of its own identity.
_KEY_REGISTRY: dict[tuple[str, ...], tuple[frozenset, frozenset]] = {
    ("data_vintage",): (DATA_VINTAGE_FIELDS, frozenset()),
    ("data_vintage", "source_hashes", _DYN): (SOURCE_HASH_FIELDS, frozenset()),
    ("rankings", _ITEM): (RANKINGS_ROW_FIELDS, frozenset()),
    ("exclusions", _ITEM): (EXCLUSION_ROW_FIELDS, frozenset()),
    # `reason` is present exactly when status=UNKNOWN — the IFF is `assert_tripwire_record_valid`'s
    # to enforce; here it is simply an allowed key.
    ("indicators", _ITEM): (frozenset(TRIPWIRE_RECORD_REQUIRED), frozenset({"reason"})),
}

# Nodes whose KEYS come from the run's declared source registry rather than a fixed field set.
# Value = the label the refusal message uses, so the error names the channel it closed.
_DYNAMIC_KEY_PATHS = {("data_vintage", "source_hashes"): "source_hashes key"}

# The positions that carry a JSON ARRAY. Declared, like every other position, because the walk
# dispatches on what a path IS DECLARED to hold — never on what the value happens to be.
_SEQ_PATHS = frozenset({("rankings",), ("exclusions",), ("indicators",),
                        ("rankings", _ITEM, "flags")})

_VALUE_VALIDATORS = {
    ("schema",): _bind(_ROOT_FIELDS, "artifact schema"),
    ("schema_version",): _bind(SCHEMA_VERSIONS, "schema_version"),
    ("assumptions_hash",): _hex(ASSUMPTIONS_HASH_CHARS, "assumptions_hash"),
    ("data_vintage", "source_hashes", _DYN, "sha256"): _hex(SHA256_HEX_CHARS,
                                                            "source_hashes sha256"),
    ("data_vintage", "source_hashes", _DYN, "extracted_at"): _iso8601("source_hashes extracted_at"),
    ("rankings", _ITEM, "geography"): _bind(_GEOGRAPHY_VALUES, "rankings geography"),
    ("rankings", _ITEM, "flags", _ITEM): _bind(RANKING_FLAGS_ALLOWED, "rankings flag"),
    ("exclusions", _ITEM, "geography"): _bind(_GEOGRAPHY_VALUES, "exclusion geography"),
    ("exclusions", _ITEM, "unresolved_input"): _bind(UNRESOLVED_INPUTS, "exclusion unresolved_input"),
    ("indicators", _ITEM, "indicator"): _bind(_INDICATORS, "tripwire indicator"),
    ("indicators", _ITEM, "source"): _bind(_DECLARED_SOURCES, "tripwire source"),
    ("indicators", _ITEM, "status"): _bind(_STATUS_VALUES, "tripwire status"),
    ("indicators", _ITEM, "reason"): _bind(_REASON_VALUES, "tripwire reason"),
}


def _fixed_keys(path: tuple[str, ...], schema: str) -> tuple[frozenset, frozenset]:
    if path == ():
        return _ROOT_FIELDS[schema], frozenset()
    try:
        return _KEY_REGISTRY[path]
    except KeyError:
        raise ValueError(
            f"artifact node {_fmt(path)} declares no field set — spec §7's closed-schema rule "
            "cannot rule on a node whose vocabulary is undeclared, so it refuses") from None


_MAP, _SEQ, _STR, _SCALAR = "a map", "an array", "a string", "a number/bool/null"


def _declared_kind(path: tuple[str, ...]) -> str:
    """What the DOCUMENT SCHEMA says this position holds. Derived from the tables that already
    declare it — the key registries name the maps, `_SEQ_PATHS` the arrays, `_VALUE_VALIDATORS`
    the strings — so a position is declared exactly once, in the table that binds it.

    `_SCALAR` is the residual, and deliberately: the allowlisted numeric row fields (`rank`,
    `mean_ed_*`, `current_value`, `as_of`, `band_*`) are bound as numbers by the row validators,
    which own types and nullability. What the residual must NOT do is swallow a string — it
    cannot, because a string at a `_SCALAR` position is a kind mismatch and raises."""
    if path == () or path in _KEY_REGISTRY or path in _DYNAMIC_KEY_PATHS:
        return _MAP
    if path in _SEQ_PATHS:
        return _SEQ
    if path in _VALUE_VALIDATORS:
        return _STR
    return _SCALAR


def _actual_kind(node) -> str | None:
    if isinstance(node, dict):
        return _MAP
    if isinstance(node, (list, tuple)):
        return _SEQ
    if isinstance(node, str):
        return _STR
    if node is None or isinstance(node, (bool, int, float)):
        return _SCALAR
    return None


def _refuse_kind(path: tuple[str, ...], declared: str, actual: str, node) -> ValueError:
    if declared == _SCALAR and actual == _STR:
        return ValueError(
            f"no validator for string position {_fmt(path)} (value {node!r}) — spec §7 "
            "binds EVERY string position; an undeclared one is an open channel, so it "
            "refuses rather than passes")
    if declared == _STR:
        return ValueError(
            f"declared string position {_fmt(path)} carries {actual} ({node!r}) — a declared "
            "string position holding a non-string is an UNDECLARED position: its binding is "
            "never consulted, so `null` would ship where a digest belongs")
    return ValueError(
        f"artifact position {_fmt(path)} is declared {declared} and carries {actual} "
        f"({node!r}) — every position below it, and the field/registry checks that guard "
        "them, are skipped when a container collapses to a scalar")


def _walk(node, path: tuple[str, ...], schema: str, source_keys: frozenset, seen: list) -> None:
    # KIND FIRST, from the DECLARATION — review finding F1's root cause. The landed body
    # dispatched on the runtime type, so a position's binding was consulted only when its value
    # happened to be of the bound type: `assumptions_hash: null`, `sha256: null` (an entry with
    # NO digest), `schema_version: 2`, `rankings: null` all reached the scalar fall-through and
    # passed. 12 of the 13 declared string positions were bypassable that way, and the identity
    # envelope — the one region no row validator re-binds — was the region it left open.
    declared = _declared_kind(path)
    actual = _actual_kind(node)
    if actual is None:
        raise ValueError(f"artifact position {_fmt(path)} carries a "
                         f"{type(node).__name__}, which no JSON artifact can hold")
    if actual != declared:
        raise _refuse_kind(path, declared, actual, node)

    if declared == _MAP:
        label = _DYNAMIC_KEY_PATHS.get(path)
        for key in node:
            if not isinstance(key, str):
                raise ValueError(f"artifact node {_fmt(path)} carries a non-string key {key!r} "
                                 "— JSON stringifies it, so it would ship unvalidated")
        if label is not None:
            for key in node:
                if key not in source_keys:
                    raise ValueError(f"{label} {key!r} not in the run's declared source "
                                     f"registry {sorted(source_keys)}")
        else:
            required, optional = _fixed_keys(path, schema)
            missing = sorted(required - set(node))
            if missing:
                raise ValueError(f"artifact node {_fmt(path)} is missing required field(s) "
                                 f"{missing} — an envelope that silently drops a field "
                                 "publishes an artifact that merely LOOKS complete")
            extra = sorted(set(node) - required - optional)
            if extra:
                raise ValueError(f"artifact node {_fmt(path)} carries field(s) {extra} not in "
                                 f"the closed field set {sorted(required | optional)}")
        for key, value in node.items():
            seen.append(("key", path, key))
            _walk(value, path + (_DYN if label is not None else key,), schema, source_keys, seen)
    elif declared == _SEQ:
        for item in node:
            _walk(item, path + (_ITEM,), schema, source_keys, seen)
    elif declared == _STR:
        _VALUE_VALIDATORS[path](node, path)
        seen.append(("value", path, node))


def assert_no_open_strings(doc: dict, allowed_source_keys) -> tuple:
    """Spec §7's general rule: EVERY string-typed position in the emitted artifact — field
    values, enum members and map KEYS — is registry/enum-bound or format-validated.

    Enforced by DECLARATION, not by runtime type (review finding F1): every position's kind
    is looked up first and must match, so a declared string holding `null` is refused as an
    undeclared position rather than skipped as "not a string", and a container that collapses
    to a scalar cannot carry its whole subtree past the gate.

    Returns every string position it validated, as (kind, path, value) triples, so a caller
    (in practice `tests/test_artifacts.py`) can prove coverage against an independent
    traversal instead of taking this docstring's word for it.
    """
    source_keys = frozenset(allowed_source_keys)
    widened = sorted(source_keys - SOURCE_KEY_REGISTRY)
    if widened:
        raise ValueError(
            f"declared source key(s) {widened} are outside the code-owned source registry "
            f"{sorted(SOURCE_KEY_REGISTRY)} — a run may NARROW to the sources it read, never "
            "mint a key (the gate's vocabulary is not the caller's to extend)")

    schema = doc.get("schema") if isinstance(doc, dict) else None
    if schema not in _ROOT_FIELDS:
        raise ValueError(
            f"artifact declares schema {schema!r}, not one of {sorted(_ROOT_FIELDS)} — the root "
            "field set is schema-dispatched, so an undeclared contract cannot be validated")

    seen: list = []
    _walk(doc, (), schema, source_keys, seen)
    return tuple(seen)


# --------------------------------------------------------------------------- the documents

def _envelope(schema: str, vintage, assumptions_hash: str) -> dict:
    """The identity envelope (codex r7-F6), shape-checked before it is stamped on a file.

    An empty `source_hashes` REFUSES. `loaders/vintage.py` states the derivation: "an envelope
    field that silently degrades to '' or {} publishes an artifact that merely LOOKS
    provenanced". Every real run reads at least the byte-pinned ISQ workbooks, so a run
    declaring no sources at all has failed upstream and must not ship a file."""
    if not isinstance(vintage, dict) or not isinstance(vintage.get("source_hashes"), dict):
        raise ValueError(f"data_vintage must be a map carrying a source_hashes map, got "
                         f"{vintage!r}")
    if not vintage["source_hashes"]:
        raise ValueError("data_vintage.source_hashes is EMPTY — an artifact that identifies no "
                         "source merely looks provenanced; the run must refuse instead")
    return {"schema": schema, "schema_version": SCHEMA_VERSION, "data_vintage": vintage,
            "assumptions_hash": assumptions_hash}


def assert_exclusion_row_valid(row) -> None:
    """The run-level exclusion record's closed schema — ALL THREE positions bound (carry A2).

    `geography` is bound to the `Geography` enum's values, not merely present: the key set
    check and the `unresolved_input` enum leave the geography VALUE free text, and a free text
    position in a shipped artifact is the serialization side-channel §7 exists to close."""
    if not isinstance(row, dict) or set(row) != EXCLUSION_ROW_FIELDS:
        raise ValueError(f"exclusion record is not in the closed schema "
                         f"{{geography, unresolved_input}}: {row!r}")
    if row["geography"] not in _GEOGRAPHY_VALUES:
        raise ValueError(f"exclusion record violates the closed schema: geography "
                         f"{row['geography']!r} is not a Geography enum value")
    if row["unresolved_input"] not in UNRESOLVED_INPUTS:
        raise ValueError(f"exclusion record violates the closed schema: unresolved_input "
                         f"{row['unresolved_input']!r} is outside the closed enum "
                         f"{sorted(UNRESOLVED_INPUTS)}")


def _typed(records, kind: type, what: str, origin: str) -> list:
    """Refuse a bare dict where a typed record belongs. The producers (`rank_geographies`,
    `exclude_from_rankings`, `evaluate_indicator`) all return typed records whose
    `__post_init__`/enum fields already close positions a dict reopens."""
    out = []
    for record in records:
        if not isinstance(record, kind):
            raise ValueError(f"{what} must carry {kind.__name__} records ({origin}'s own return "
                             f"type), got {type(record).__name__}: {record!r}")
        out.append(record)
    return out


def rankings_document(rankings, vintage, assumptions_hash, allowed_source_keys,
                      exclusions=()) -> dict:
    rows = []
    for gr in _typed(rankings, GeoRanking, "rankings", "rank_geographies"):
        row = ranking_row(gr)
        assert_rankings_row_valid(row)      # closed allowlist + flags enum + typed rank_stable
        rows.append(row)

    exclusion_rows = []
    for exc in _typed(exclusions, RankingExclusion, "exclusions", "exclude_from_rankings"):
        row = exc.as_row()
        assert_exclusion_row_valid(row)
        exclusion_rows.append(row)

    if not rows and not exclusion_rows:
        # The rankings sibling of the completeness rule below. Every modeled geography is
        # either RANKED or carries an exclusion record naming the input that could not be
        # resolved (spec §8 branch iii) — so a document with neither accounts for nothing,
        # and a consumer reading it sees "no geography is at risk" rather than "this run
        # produced nothing". `rankings: []` WITH an exclusion is the legitimate branch-iii
        # shape and is emitted normally.
        raise ValueError("rankings artifact accounts for no geography — zero ranked rows AND "
                         "zero exclusion records is a vacuous file, not a result; the run "
                         "emits NO file and reports the failure through its exit code")

    doc = {**_envelope(RANKINGS_SCHEMA, vintage, assumptions_hash),
           "rankings": rows, "exclusions": exclusion_rows}
    assert_no_open_strings(doc, allowed_source_keys)
    return doc


def tripwire_document(results, vintage, assumptions_hash, allowed_source_keys) -> dict:
    records = []
    for result in _typed(results, TripwireResult, "indicators", "evaluate_indicator"):
        record = tripwire_record(result)
        assert_tripwire_record_valid(record)   # allowlist + reason enum + registry-bound source
        records.append(record)
    # COMPLETENESS, as one comparison over the whole class (spec §7c: "empty registry, missing
    # required indicator, or duplicate key ⇒ UNKNOWN/nonzero"; codex r10-F6). The landed body
    # refused only the EMPTY baseline, on a derivation that applies verbatim to its siblings —
    # and the truncated shape is the more dangerous one: a one-indicator file reads as one
    # green indicator, where an empty file at least reads as empty. Multiset equality against
    # the code-owned required set catches empty, short and duplicated together, and mirrors
    # `run_exit_code`'s coverage gate exactly, so the artifact and the exit code cannot
    # disagree about what a complete baseline is. It costs a legitimate run nothing: every
    # baseline that ships carries exactly the six, evaluated or synthesized.
    emitted = sorted(record["indicator"] for record in records)
    if emitted != sorted(REQUIRED_INDICATORS):
        missing = sorted(REQUIRED_INDICATORS - set(emitted))
        duplicated = sorted({i for i in emitted if emitted.count(i) > 1})
        raise ValueError(
            f"tripwire baseline is not the code-owned required indicator set: emitted "
            f"{emitted}, required {sorted(REQUIRED_INDICATORS)} (missing={missing}, "
            f"duplicated={duplicated}) — an incomplete baseline reads as that many green "
            "indicators rather than as a gap, so NO file is emitted and the run exits nonzero")

    doc = {**_envelope(TRIPWIRE_SCHEMA, vintage, assumptions_hash), "indicators": records}
    assert_no_open_strings(doc, allowed_source_keys)
    return doc


# ------------------------------------------------------------------------------ the writer

def _dump_json(path, obj) -> None:
    """Serialize. `encoding="utf-8"` is PINNED (carry A4): bare `open(path, "w")` takes the
    LOCALE's encoding, so a non-ASCII token mojibakes or raises under a non-UTF-8 locale —
    an ENVIRONMENTAL failure a UTF-8 dev box never shows. `newline="\\n"` pins LF so the
    Task-30 golden diff moves only when a modeled quantity moves. `ensure_ascii=False` keeps
    the bytes readable AND makes the encoding pin load-bearing rather than decorative."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def write_json_strict(path: Path, doc: dict, allowed_source_keys) -> None:
    """Validate, then serialize. The file is opened only after both gates pass, so a refusal
    leaves NOTHING on disk.

    `loaders/vintage.py` already states the first gate as a fact of the system — "spec §7's
    `write_json_strict` re-checks 64-hex on the way out" — and a writer that merely serialized
    would make that committed claim false while letting any document assembled outside the two
    builders ship.

    EXACTLY WHAT IS RE-CHECKED HERE, because a gate description broader than the gate is the
    defect this module was written to remove: finiteness over the whole tree (codex r4-F3) and
    every position's declared kind and binding (spec §7). ROW-LEVEL NUMERIC types and
    cross-field contracts are NOT re-run — `rank: 0`, `rank_stable: 1`, an UNKNOWN record with
    a non-null `current_value`, all pass this function (measured, not assumed). Nor is
    completeness: this function will write a one-indicator baseline that `tripwire_document`
    would refuse. Those belong to `assert_rankings_row_valid` / `assert_tripwire_record_valid`,
    which the two builders call on every row; re-running them here would duplicate a contract
    that already has one owner. The builders are therefore the only sanctioned producers, and
    that is a contract on callers — not a property this function can enforce."""
    _assert_finite(doc)
    assert_no_open_strings(doc, allowed_source_keys)
    _dump_json(path, doc)
