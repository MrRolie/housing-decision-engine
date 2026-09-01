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
    provenanced is the shape this refusal exists for, and it is the LAST gate that can say so.
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

THE ROW VALIDATORS STILL RUN, AND THEY RUN ON THE WRITE PATH. `assert_rankings_row_valid` /
`assert_tripwire_record_valid` bind NUMERIC types and cross-field rules the walk genuinely
cannot see — `rank_stable: 1` (an int where the sweep verdict must be a bool), `rank: 0`, a
CROSSED record carrying `stale`, an UNKNOWN record with a non-null `current_value`. All four
are scalars at scalar positions, so the walk passes them and the row contract is what
refuses. The walk is the quantifier over positions and their kinds; the row validators are
the per-record contract. Neither subsumes the other.

THE CONTRACT HAS EXACTLY ONE OWNER, `_ROW_CONTRACTS` READ BY `write_json_strict`, and the
reason is a measured one (stress gate F6): while the BUILDERS owned it, the emit path had a
single enforcement point per document and that CALL SITE was deletion-survivable — remove it
and the whole suite still passed, after which `rank_stable: 1`, `rank: -3` and
`mean_ed_reference: true` all reached disk. Body-tested, wiring-unpinned. On the write path
there is no call left to delete, and a document assembled outside the two builders meets the
same contract as one they built.

THE SET CONTRACT IS BOUND AT THIS BOUNDARY TOO, for both artifacts, because a partial file is
a false green rather than a small one — and its rankings half was overstated here until codex
r12-F2 measured it. A tripwire baseline must carry EXACTLY the code-owned required indicator
set (mirroring `run_exit_code`, so the file and the exit code cannot disagree); a rankings
artifact must account for the modeled geography DOMAIN — every member ranked or excluded, the
two disjoint, neither repeated, and the ranks a contiguous permutation. The claim used to be
"at least one geography", which is the same sentence weakened by 7/8: it accepted a one-row
file that reads as one geography at risk and seven fine. `_DOC_CONTRACTS` declares one
validator per schema and both the builders and `write_json_strict` reach it, so a document
assembled outside the builders meets the same set rule as one they built. Neither costs a
legitimate run anything.

THE ALLOWLIST A CALLER SUPPLIES MAY ONLY NARROW. `allowed_source_keys` names the sources a
particular run actually read, and it is checked to be a SUBSET of `SOURCE_KEY_REGISTRY`, the
code-owned set of files a run may declare it read — every file this package acquires, plus the
four DERIVED rate artifacts it generates and then opens at run time (see that constant). Without
that bound, the one gate whose premise is a code-owned vocabulary would be retunable from its own
call site — the shape `tripwires.check_registry` closed at review finding F4 (`required` was a
parameter there, and `check_registry(['x'], required={'x'})` returned "complete").
"""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

from demoflow.balance import mapping
from demoflow.cohort.basis import BASIS_SOURCE_KEY
from demoflow.geography import MODELED_GEOGRAPHIES, Geography, Scenario
from demoflow.loaders import census, hors_aligned, living_arrangement
from demoflow.loaders.constants import ASSUMPTIONS_HASH_CHARS, sweep_leg_labels
from demoflow.loaders.ircc import CSV_NAME as IRCC_CSV_NAME
from demoflow.loaders.pins import WORKBOOK_SHA256
from demoflow.output import scenario_prior as scenario_prior_mod
from demoflow.output.rankings import (
    RANKING_FLAGS_ALLOWED,
    RANKINGS_ROW_FIELDS,
    UNRESOLVED_INPUTS,
    GeoRanking,
    RankingExclusion,
    assert_rankings_row_valid,
    ranking_row,
)
from demoflow.output.scenario_prior import (
    DATA_VINTAGE_IDENTITY_FIELDS,
    PRIOR_FLAGS_ALLOWED,
    PRIOR_ROW_FIELDS,
    DWELLING_TYPES,
    SCENARIO_PRIOR_SCHEMA,
    ScenarioPriorRow,
    assert_scenario_prior_row_valid,
    prior_document_complete,
    prior_row_to_dict,
)
from demoflow.output.tripwires import (
    REQUIRED_INDICATORS,
    SOURCE_REGISTRY,
    TRIPWIRE_RECORD_REQUIRED,
    Reason,
    SourceKind,
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
# constants_as_of} shape belongs to the TRANCHE-2 ScenarioPrior emitter — and since that build
# landed, it is declared per-SCHEMA (`PRIOR_DATA_VINTAGE_FIELDS` + `_VINTAGE_FIELDS` below),
# never globally: these two Tranche-1 schemas still refuse the three fields, because an
# allowed-but-never-emitted field is an unfired allowance here. `isq_edition` HAS a code-owned
# vocabulary now (derived from the scenario-label junction; see scenario_prior.py), which was
# the measured gap that kept it unadmitted on 2026-08-18.
DATA_VINTAGE_FIELDS = frozenset({"source_hashes"})
# TRANCHE-2 (spec §7(a)): the ScenarioPrior's fuller data_vintage — the three identity fields
# AROUND the same source_hashes map. The values are DERIVED in `output/scenario_prior.py`
# (edition from the scenario-label junction, census year from the PIT base, constants_as_of
# from the anchors' own dated revisions) and bound per-position below; the field SET is the
# composition of that module's declaration, never a restatement.
PRIOR_DATA_VINTAGE_FIELDS = DATA_VINTAGE_IDENTITY_FIELDS | {"source_hashes"}
SOURCE_HASH_FIELDS = frozenset({"sha256", "extracted_at"})
# OPTIONAL, and populated ONLY for a source whose `publishes` is the RAW ANCHOR (spec amendment
# #20(C)(1)). `sha256` at such a key is the RAW upstream member's digest per §7's
# sha256-of-raw-response definition — the one link a re-extract cannot move with — so a consumer
# who reproduces the field the way §7's other twelve keys work gets ONE unexplained mismatch.
# This field is the digest of the bytes the run actually READ off disk, which `sha256sum`
# reproduces. Two semantics under one field name was the defect; two fields is the fix, and it
# costs an assignment because `pipeline._source_hashes` already computed and pin-checked it.
SOURCE_HASH_OPTIONAL = frozenset({"committed_sha256"})

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
#
# THE MORTALITY BASIS IS IN IT TOO, and it is the only member that is not a FILE (data-gate
# finding F1). Every q value the supply side rides on comes off it, it lives behind a uv path
# dependency with no digest, and the run hashes the q SURFACE it consumes rather than the CSVs
# behind it — spec §2 admits the engine's public entry point only. Same argument as the four
# derived artifacts, one boundary further out: without the key, two runs over different upstream
# mortality tables emit different rankings bytes under a byte-identical envelope. The name comes
# from `cohort/basis.py`, which owns the basis pair it is derived from.
_EVIDENCE_ONLY = frozenset({"catalogue_member_index_p9.json"})
DERIVED_ARTIFACT_KEYS = frozenset({
    census.OWNERSHIP_ARTIFACT, census.HEADSHIP_ARTIFACT,
    living_arrangement.ARTIFACT, hors_aligned.ARTIFACT,
})
SOURCE_KEY_REGISTRY = ((frozenset(WORKBOOK_SHA256) - _EVIDENCE_ONLY)
                       | frozenset({IRCC_CSV_NAME, BASIS_SOURCE_KEY}) | DERIVED_ARTIFACT_KEYS)

_GEOGRAPHY_VALUES = frozenset(g.value for g in Geography)
_STATUS_VALUES = frozenset(s.value for s in Status)
_REASON_VALUES = frozenset(r.value for r in Reason)
_SOURCE_KIND_VALUES = frozenset(k.value for k in SourceKind)
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


# `exclusions` is a REQUIRED root member of the rankings document, authorized by spec amendment
# #22(B) — which is RETROACTIVE: it shipped here first and #20(C)'s "the envelope widens by
# exactly three optional members" was false when written, because this fourth REQUIRED one was
# already present. `schema_version` does NOT bump; the amendment authorizes what every emitted
# document has carried since the member was added. Its row allowlist is `EXCLUSION_ROW_FIELDS`,
# bound to the declaration DIRECTLY in `tests/test_artifacts.py` — never through the golden,
# which re-ratifies whatever the emitter emits and is how this reached production unauthorized.
_ROOT_FIELDS = {
    RANKINGS_SCHEMA: frozenset({"schema", "schema_version", "data_vintage", "assumptions_hash",
                                "rankings", "exclusions"}),
    TRIPWIRE_SCHEMA: frozenset({"schema", "schema_version", "data_vintage", "assumptions_hash",
                                "indicators"}),
    # spec §7(a): mapping_version rides the document ROOT (the envelope discipline — the same
    # stack as schema_version/data_vintage/assumptions_hash), not a per-row copy; every row
    # carries it by belonging to exactly one document that declares one mapping version. It is
    # deliberately OUTSIDE `IDENTITY_ENVELOPE_FIELDS`, so the pairing token's payload digest
    # SEES it: changing the mapping re-mints the token even if no drift digit moved.
    SCENARIO_PRIOR_SCHEMA: frozenset({"schema", "schema_version", "mapping_version",
                                      "data_vintage", "assumptions_hash", "scenario_priors"}),
}

# ROOT-LEVEL OPTIONAL MEMBERS — spec amendment #20(C), which widens §7's closed envelope by
# EXACTLY three optional positions and leaves the refusal on an undeclared one UNCHANGED.
# `schema_version` does NOT bump (amendment #20(C0)): every one of them is optional, so a
# consumer written against version "1" reads every emitted document unchanged, and a bump would
# invalidate pinned consumers in order to announce fields they may ignore.
#
#   * `run_pairing` — BOTH documents. The per-run pairing token, deterministic over the
#     CANONICAL PAYLOAD DIGESTS OF BOTH DOCUMENTS (spec amendment #22(C) re-specified the
#     payload; `pairing_token` owns it and states what it does and does not see). Emission is
#     all-or-nothing but the two renames are a loop, so a failure between them leaves a
#     mismatched pair whose `assumptions_hash` and `data_vintage` are IDENTICAL: no consumer
#     could refuse it. POSIX bounds atomicity, not detection. Both BUILDERS require it — a
#     document this tree emits always carries one; the optionality is a statement about
#     CONSUMERS, never a producer licence.
#   * `rows_moved` — RANKINGS only. The per-leg sweep count, which existed in three unpinned
#     prose copies the module's own README declared "a dated reading". Emitting it converts a
#     self-declared drift residual into a computed field and DELETES prose.
_ROOT_OPTIONAL = {
    RANKINGS_SCHEMA: frozenset({"run_pairing", "rows_moved"}),
    TRIPWIRE_SCHEMA: frozenset({"run_pairing"}),
    SCENARIO_PRIOR_SCHEMA: frozenset({"run_pairing"}),
}

# path -> (REQUIRED fields, OPTIONAL fields). Both directions bind: an unknown key is a
# smuggled field, an absent required key is an artifact missing a piece of its own identity.
_KEY_REGISTRY: dict[tuple[str, ...], tuple[frozenset, frozenset]] = {
    # NOTE: ("data_vintage",) is NOT here — its field set is SCHEMA-dispatched
    # (`_VINTAGE_FIELDS` + `_fixed_keys`), because Tranche 1's minimal shape and §7(a)'s fuller
    # shape coexist across schemas and a single path can only declare one of them.
    ("data_vintage", "source_hashes", _DYN): (SOURCE_HASH_FIELDS, SOURCE_HASH_OPTIONAL),
    ("rankings", _ITEM): (RANKINGS_ROW_FIELDS, frozenset()),
    ("exclusions", _ITEM): (EXCLUSION_ROW_FIELDS, frozenset()),
    ("scenario_priors", _ITEM): (PRIOR_ROW_FIELDS, frozenset()),
    # `reason` is present exactly when status=UNKNOWN — the IFF is `assert_tripwire_record_valid`'s
    # to enforce; here it is simply an allowed key. `freshness_years` / `source_kind` are spec
    # amendment #21's two optional members: the declarations the row is GOVERNED by, published in
    # the row they govern, so the hash ledger's "what the output shows needs no token" argument is
    # true for BOTH tripwire ledgers instead of one.
    ("indicators", _ITEM): (frozenset(TRIPWIRE_RECORD_REQUIRED),
                            frozenset({"reason", "freshness_years", "source_kind"})),
}

# Nodes whose KEYS come from a REGISTRY rather than a fixed field set.
# Value = the label the refusal message uses, so the error names the channel it closed.
_DYNAMIC_KEY_PATHS = {("data_vintage", "source_hashes"): "source_hashes key",
                      ("rows_moved",): "sweep leg"}

# ...and where that registry comes from. `source_hashes` keys are narrowed PER RUN (a run may
# declare fewer sources than it could read, never more — `assert_no_open_strings` refuses a
# widened set against `SOURCE_KEY_REGISTRY`), so their vocabulary is the caller's argument. The
# sweep legs are not: the declared grid is CODE-owned and the same for every run, so the
# vocabulary is read straight off `loaders/constants.py`, which owns the grid AND the one
# spelling of a leg's name. A key here that is not a declared leg is a count for a leg the sweep
# never ran. Held as a CALLABLE, not as a frozen set: the grid is the producer's live declaration
# and a snapshot taken at import would admit a key for a leg the sweep no longer declares.
_CODE_OWNED_KEY_VOCABULARIES = {("rows_moved",): sweep_leg_labels}

# The positions that carry a JSON ARRAY. Declared, like every other position, because the walk
# dispatches on what a path IS DECLARED to hold — never on what the value happens to be.
_SEQ_PATHS = frozenset({("rankings",), ("exclusions",), ("indicators",),
                        ("scenario_priors",),
                        ("rankings", _ITEM, "flags"), ("scenario_priors", _ITEM, "flags")})

_VALUE_VALIDATORS = {
    ("schema",): _bind(_ROOT_FIELDS, "artifact schema"),
    ("schema_version",): _bind(SCHEMA_VERSIONS, "schema_version"),
    ("assumptions_hash",): _hex(ASSUMPTIONS_HASH_CHARS, "assumptions_hash"),
    ("run_pairing",): _hex(ASSUMPTIONS_HASH_CHARS, "run_pairing"),
    ("data_vintage", "source_hashes", _DYN, "sha256"): _hex(SHA256_HEX_CHARS,
                                                            "source_hashes sha256"),
    ("data_vintage", "source_hashes", _DYN, "committed_sha256"): _hex(
        SHA256_HEX_CHARS, "source_hashes committed_sha256"),
    ("data_vintage", "source_hashes", _DYN, "extracted_at"): _iso8601("source_hashes extracted_at"),
    ("rankings", _ITEM, "geography"): _bind(_GEOGRAPHY_VALUES, "rankings geography"),
    ("rankings", _ITEM, "flags", _ITEM): _bind(RANKING_FLAGS_ALLOWED, "rankings flag"),
    ("exclusions", _ITEM, "geography"): _bind(_GEOGRAPHY_VALUES, "exclusion geography"),
    ("exclusions", _ITEM, "unresolved_input"): _bind(UNRESOLVED_INPUTS, "exclusion unresolved_input"),
    ("indicators", _ITEM, "indicator"): _bind(_INDICATORS, "tripwire indicator"),
    ("indicators", _ITEM, "source"): _bind(_DECLARED_SOURCES, "tripwire source"),
    ("indicators", _ITEM, "status"): _bind(_STATUS_VALUES, "tripwire status"),
    ("indicators", _ITEM, "reason"): _bind(_REASON_VALUES, "tripwire reason"),
    ("indicators", _ITEM, "source_kind"): _bind(_SOURCE_KIND_VALUES, "tripwire source_kind"),
    # Tranche-2 ScenarioPrior (spec §7(a)). The three vintage identity fields are bound to the
    # DERIVED singletons their producer computes — a vocabulary of one, but a vocabulary: an
    # unbound vintage token is exactly the channel §7 closes, and the derivation moving (a new
    # ISQ edition, an anchor re-dated) must re-mint the artifact rather than slip past.
    ("mapping_version",): _bind({mapping.MAPPING_VERSION}, "mapping_version"),
    ("data_vintage", "isq_edition"): _bind(
        {scenario_prior_mod.ISQ_EDITION}, "isq_edition"),
    ("data_vintage", "census_year"): _bind(
        {scenario_prior_mod.CENSUS_YEAR}, "census_year"),
    ("data_vintage", "constants_as_of"): _bind(
        {scenario_prior_mod.CONSTANTS_AS_OF}, "constants_as_of"),
    ("scenario_priors", _ITEM, "geography"): _bind(_GEOGRAPHY_VALUES, "prior geography"),
    ("scenario_priors", _ITEM, "dwelling_type"): _bind(DWELLING_TYPES, "prior dwelling_type"),
    ("scenario_priors", _ITEM, "scenario"): _bind(
        {s.value for s in Scenario}, "prior scenario"),
    ("scenario_priors", _ITEM, "flags", _ITEM): _bind(PRIOR_FLAGS_ALLOWED, "prior flag"),
}


# DECLARED NON-STRING positions that carry a binding of their own. `_VALUE_VALIDATORS` binds
# every STRING position (spec §7's general rule); the numeric row fields are owned by the row
# validators, which know their types and nullability. `rows_moved`'s counts have no row validator
# — the field is a MAP, not an array of records, so `_ROW_CONTRACTS` cannot reach it — and a
# count is exactly the position where `true` or `null` would ride through the scalar residual.
# Declared here, dispatched from `_walk`, so the binding is a table entry rather than a special
# case: `rows_moved: {"q_live_per_year=0.11": true}` refuses.
def _count(label: str):
    def check(value, path: tuple[str, ...]) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} at {_fmt(path)}: {value!r} is not a non-negative whole "
                             "count — a bool or a float here is a measurement nothing made")
    return check


_SCALAR_VALIDATORS = {("rows_moved", _DYN): _count("rows_moved count")}


# The data_vintage field set, per schema — the one path whose declaration is schema-relative
# (see `_KEY_REGISTRY`'s note). Any schema not listed here has NO vintage declaration and its
# documents refuse at the root walk, which is the fail-closed direction.
_VINTAGE_FIELDS = {
    RANKINGS_SCHEMA: DATA_VINTAGE_FIELDS,
    TRIPWIRE_SCHEMA: DATA_VINTAGE_FIELDS,
    SCENARIO_PRIOR_SCHEMA: PRIOR_DATA_VINTAGE_FIELDS,
}


def _fixed_keys(path: tuple[str, ...], schema: str) -> tuple[frozenset, frozenset]:
    """The (required, optional) field set at a FIXED-key node.

    EVERY PATH THAT REACHES IT IS DECLARED, so it does not check. `_walk` calls it only from
    the _MAP branch at a non-dynamic path, and `_declared_kind` returns _MAP for nothing but
    `()`, `_KEY_REGISTRY`, `_DYNAMIC_KEY_PATHS` and `("data_vintage",)` — measured, the
    residual set `({(), ("data_vintage",)} | set(_KEY_REGISTRY) | set(_DYNAMIC_KEY_PATHS)) -
    {()} - _DYNAMIC_KEY_PATHS - _KEY_REGISTRY` is EMPTY. The undeclared-node refusal that used
    to sit here was therefore unreachable, and a permissive mutant of it survived the full
    suite (stress gate F7). A map planted at an undeclared position is refused by
    `_refuse_kind` — "declared string position $.rankings[].flags[] carries a map" — which is
    the message a reader actually sees. A live-sounding claim over code that cannot run is
    worse than no claim: a reader counts it."""
    if path == ():
        return _ROOT_FIELDS[schema], _ROOT_OPTIONAL[schema]
    if path == ("data_vintage",):
        return _VINTAGE_FIELDS[schema], frozenset()
    return _KEY_REGISTRY[path]


_MAP, _SEQ, _STR, _SCALAR = "a map", "an array", "a string", "a number/bool/null"


def _declared_kind(path: tuple[str, ...]) -> str:
    """What the DOCUMENT SCHEMA says this position holds. Derived from the tables that already
    declare it — the key registries name the maps, `_SEQ_PATHS` the arrays, `_VALUE_VALIDATORS`
    the strings — so a position is declared exactly once, in the table that binds it.

    `_SCALAR` is the residual, and deliberately: the allowlisted numeric row fields (`rank`,
    `mean_ed_*`, `current_value`, `as_of`, `band_*`) are bound as numbers by the row validators,
    which own types and nullability. What the residual must NOT do is swallow a string — it
    cannot, because a string at a `_SCALAR` position is a kind mismatch and raises."""
    if path == () or path in _KEY_REGISTRY or path in _DYNAMIC_KEY_PATHS \
            or path == ("data_vintage",):
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
            code_owned = _CODE_OWNED_KEY_VOCABULARIES.get(path)
            vocabulary = source_keys if code_owned is None else code_owned()
            for key in node:
                if key not in vocabulary:
                    raise ValueError(f"{label} {key!r} not in the declared registry "
                                     f"{sorted(vocabulary)}")
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
    else:
        scalar = _SCALAR_VALIDATORS.get(path)
        if scalar is not None:
            scalar(node, path)


def assert_no_open_strings(doc: dict, allowed_source_keys) -> tuple:
    """Spec §7's general rule: EVERY string-typed position in the emitted artifact — field
    values, enum members and map KEYS — is registry/enum-bound or format-validated.

    Enforced by DECLARATION, not by runtime type (review finding F1): every position's kind
    is looked up first and must match, so a declared string holding `null` is refused as an
    undeclared position rather than skipped as "not a string", and a container that collapses
    to a scalar cannot carry its whole subtree past the gate.

    Returns every STRING position it validated, as (kind, path, value) triples, so a caller
    (in practice `tests/test_artifacts.py`) can prove coverage against an independent
    traversal instead of taking this docstring's word for it. Declared COUNT positions
    (`_SCALAR_VALIDATORS`) are validated on the same walk and deliberately NOT returned: this
    return value is the coverage oracle for spec §7's no-open-string rule, and widening it to a
    second kind would make the independent traversal it is compared against ambiguous.
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


# ------------------------------------------------- canonical bytes, payload digests, pairing

# THE ONE SERIALIZATION DECLARATION. `_dump_json` writes these bytes and `payload_digest`
# hashes them, so the digest is taken over EXACTLY the form the file carries — there is no
# second convention that can drift from the writer's. `sort_keys=True` makes the bytes
# independent of dict insertion order (so a builder that assembles the same content in a
# different order digests the same), `allow_nan=False` keeps the JSON strict, `ensure_ascii=False`
# makes the utf-8 pin load-bearing rather than decorative, and `indent=2` + the trailing newline
# are the file's committed shape. A change to ANY of these re-mints every pairing token, which is
# correct: it is a change to what "the canonical payload" means.
def _canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, allow_nan=False, ensure_ascii=False, indent=2,
                       sort_keys=True) + "\n").encode("utf-8")


# The identity envelope's own positions — the five `_envelope` stamps. DECLARED here and bound to
# `_envelope`'s actual key set in `tests/test_artifacts.py`, because this set is what
# `payload_digest` SUBTRACTS: a sixth envelope field added to `_envelope` and not to this set
# would silently become part of every payload digest, and one that left this set without leaving
# `_envelope` would silently stop being covered.
IDENTITY_ENVELOPE_FIELDS = frozenset({"schema", "schema_version", "data_vintage",
                                      "assumptions_hash", "run_pairing"})

# THE CONSUMER PROTOCOL'S CROSS-DOCUMENT COMPARISON, as a set the CODE owns (spec amendment
# #24(C)). `artifacts/README.md` publishes the steps a consumer runs before reading either file;
# until #24(C) it published THREE of the four identity members and nothing in this tree compared
# the fourth across a pair. `schema_version` sits INSIDE the envelope, and `payload_of` subtracts
# the envelope, so the pairing token is blind to it BY CONSTRUCTION — the same property that makes
# the token computable at all. Measured on the committed goldens: flipping one file's
# `schema_version` leaves its payload digest bit-identical and the token unmoved, so a pair
# differing ONLY in `schema_version` passed every published step.
#
# `schema` IS DELIBERATELY EXCLUDED, and the exclusion is the ruling rather than an omission: the
# two documents carry DIFFERENT `schema` strings by design (`demoflow.rankings.v1` against
# `demoflow.tripwire_baseline.v1`), so comparing it would refuse EVERY honest pair. That makes
# this set exactly `IDENTITY_ENVELOPE_FIELDS - {"schema"}`, which `tests/test_artifacts.py` binds:
# a sixth envelope field lands in one set or the other by a DECISION, never by silence.
#
# ORDER IS THE PUBLISHED ORDER — the page tells a consumer to compare the token first.
PAIRED_IDENTITY_FIELDS = ("run_pairing", "data_vintage", "assumptions_hash", "schema_version")

# `.get()` on an absent key returns `None`, which compares EQUAL to another absent key — the
# vacuity the page names as "ABSENT IS NOT A MATCH". A sentinel makes present-vs-absent a
# mismatch, so only the one field the page rules non-evidence is skipped, and it is skipped by
# NAME below rather than by being un-comparable.
_ABSENT = object()

# The one member whose ABSENCE is NO PAIRING EVIDENCE rather than a mismatch — pre-amendment
# #20(C)(3) documents carry no `run_pairing` at all, they are still VALID, and refusing them
# would break exactly the backward compatibility the un-bumped `schema_version` was kept for.
# The other three are REQUIRED positions of both schemas, so absence there is a defect and is
# reported as one.
_NO_PAIRING_EVIDENCE = "run_pairing"


def pair_identity_mismatches(first: dict, second: dict) -> tuple[str, ...]:
    """The identity members that DISAGREE across one run's two documents, in published order.

    Empty means every comparison the page publishes passed. NON-EMPTY MEANS REFUSE THE PAIR —
    this returns the finding and never decides for the caller, because the two documents are
    emitted by one run here and the check is the CONSUMER's.

    WHAT AN EMPTY RESULT DOES NOT PROVE, stated because the page states it: equal tokens mean the
    two runs' PAYLOADS coincided, not that there was one run. On this tree the clock reaches no
    emitted value, so two runs separated only by `now` emit byte-identical documents and no field
    here can see it — the one pair no check can refuse, and `golden.py`'s pin is its only guard.
    """
    out = []
    for field in PAIRED_IDENTITY_FIELDS:
        left, right = first.get(field, _ABSENT), second.get(field, _ABSENT)
        if field == _NO_PAIRING_EVIDENCE and (left is _ABSENT or right is _ABSENT):
            continue
        if left != right:
            out.append(field)
    return tuple(out)


# The provisional token the two-phase build below stamps on its FIRST pass. 16 hex so it passes
# the same `_VALUE_VALIDATORS` gate the real token does — a first pass that could not validate
# would move the ordering problem rather than solve it. It never reaches disk: the documents that
# ship are REBUILT with the real token.
_PROVISIONAL_PAIRING = "0" * ASSUMPTIONS_HASH_CHARS


def payload_of(doc: dict) -> dict:
    """The document's CONTENT — everything outside its identity envelope.

    This is the half of the file that says what the run MEASURED. `run_pairing` sits inside the
    envelope and therefore outside this, which is what makes the token below computable at all:
    a token over the whole document would have to hash itself."""
    return {k: v for k, v in doc.items() if k not in IDENTITY_ENVELOPE_FIELDS}


def payload_digest(doc: dict) -> str:
    """sha256 over the canonical bytes of `payload_of(doc)` — full width, this is an input to the
    token rather than an emitted field."""
    return hashlib.sha256(_canonical_bytes(payload_of(doc))).hexdigest()


def pairing_token(documents) -> str:
    """The per-run pairing token — spec amendment #22(C), which SELECTS the OR-branch #20(C)(3)
    already authorized ("a sibling manifest carrying both documents' digests").

    DETERMINISTIC OVER THE CANONICAL PAYLOAD DIGESTS OF BOTH DOCUMENTS, keyed by the file name
    each ships under. So it moves whenever either payload moves, FOR ANY CAUSE — including a
    computation change that touches no constant, no data byte and no schema, which is exactly
    what the ruled (assumption selection, source bytes, `now`) payload could not see. Measured
    before the change: an ED-collapse-rule change reordered the published ranking (HORS_RMR 4->6,
    MTL_RMR 5->4, MONTEREGIE_RA16_PROXY 6->5) and the token did not move, so a consumer comparing
    it accepted a mixed pair. The file NAMES are in the digest input, so swapping the two
    documents' bodies moves it too.

    WHAT IT IS NOT A FUNCTION OF, stated because #20(C)(3)'s payload was: the identity envelope.
    `data_vintage` and `assumptions_hash` are excluded and lose nothing — both ride BOTH files
    where a consumer can compare them directly. `now` is excluded and that IS a narrowing, stated
    at the pipeline call site and on `artifacts/README.md`: on today's tree every tripwire
    indicator is structurally UNKNOWN, so the clock reaches neither payload and two runs
    separated only by it produce the same token. The pair that leaves is byte-identical in every
    content field of both documents, so refusing it protects nothing; the moment an indicator
    carries a real value the clock reaches the tripwire payload and this token sees it through
    CONTENT, which is the axis that matters.

    NEVER A NONCE. A pure function of emitted content: identical inputs and identical code give
    identical bytes, which is what the goldens rest on."""
    return hashlib.sha256(_canonical_bytes(
        {name: payload_digest(doc) for name, doc in documents.items()}
    )).hexdigest()[:ASSUMPTIONS_HASH_CHARS]


def stamp_pairing_token(build) -> dict[str, dict]:
    """Build the run's documents and stamp the pairing token that binds BOTH their payloads.

    THIS IS AN ORDERING CONSTRAINT, AND IT IS WHY THIS FUNCTION EXISTS rather than a token
    computed at the call site: the token is a function of both payloads, so both payloads must
    exist before either envelope can be stamped. `build` is called with a token and returns
    `{file name -> document}`; it is called TWICE — once with a provisional token to obtain the
    payloads, then again with the real one — and the documents that SHIP come out of the ordinary
    validated builder path carrying the real token, never out of a validated document patched
    afterwards.

    THE SECOND PASS IS RE-CHECKED, and the check can fail. Equal payload digests across the two
    passes is precisely the claim "the token binds the bytes that ship": it reds if a builder ever
    folds the token (or anything else envelope-borne) into the payload — which would make the
    token self-referential — and it reds if a builder is not deterministic."""
    provisional = build(_PROVISIONAL_PAIRING)
    token = pairing_token(provisional)
    final = build(token)
    before = {name: payload_digest(doc) for name, doc in provisional.items()}
    after = {name: payload_digest(doc) for name, doc in final.items()}
    if before != after:
        moved = sorted(name for name in before if before[name] != after[name])
        raise ValueError(
            f"the pairing token does not bind the payload that ships: document(s) {moved} "
            f"digest differently once the token is stamped, so the payload depends on the "
            f"envelope. Either a builder is non-deterministic or it copies an envelope field "
            f"into its content — both make `run_pairing` self-referential")
    return final


# --------------------------------------------------------------------------- the documents

def _envelope(schema: str, vintage, assumptions_hash: str, run_pairing: str) -> dict:
    """The identity envelope (codex r7-F6), shape-checked before it is stamped on a file.

    An empty `source_hashes` REFUSES, on the derivation this package has carried since the
    rate-vintage carry: an envelope field that silently degrades to '' or {} publishes an
    artifact that merely LOOKS provenanced. Every real run reads at least the byte-pinned ISQ
    workbooks, so a run declaring no sources at all has failed upstream and must not ship a
    file.

    `run_pairing` IS REQUIRED HERE AND OPTIONAL IN THE SCHEMA, deliberately (amendment
    #20(C)(3); its payload re-specified by #22(C) — see `pairing_token`, and note that the
    token cannot be computed until BOTH documents' payloads exist, which is what
    `stamp_pairing_token` orders). The schema keeps it optional so `schema_version` need not
    bump and a consumer pinned to version "1" reads every emitted document unchanged; the
    PRODUCER has no such licence — a document this tree emits without a pairing token is exactly the
    mismatched-pair-undetectable state the field exists to close."""
    if not isinstance(vintage, dict) or not isinstance(vintage.get("source_hashes"), dict):
        raise ValueError(f"data_vintage must be a map carrying a source_hashes map, got "
                         f"{vintage!r}")
    if not vintage["source_hashes"]:
        raise ValueError("data_vintage.source_hashes is EMPTY — an artifact that identifies no "
                         "source merely looks provenanced; the run must refuse instead")
    return {"schema": schema, "schema_version": SCHEMA_VERSION, "data_vintage": vintage,
            "assumptions_hash": assumptions_hash, "run_pairing": run_pairing}


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


def assert_rankings_document_complete(doc: dict) -> None:
    """Spec §7(b)'s WHOLE-DOCUMENT set contract: the ranked and excluded geographies are
    UNIQUE and DISJOINT, their union is exactly the modeled geography domain, and the ranks are
    the contiguous permutation 1..len(rankings).

    IT EXISTS BECAUSE §7(b) WAS THE ONE TRANCHE-1 ARTIFACT WITH NO SET CONTRACT (codex r12-F2).
    Its two siblings both have one: §7(a) mandates that the Tranche-2 ScenarioPrior row keys
    form "the COMPLETE Cartesian product ... with NO duplicates", and §7(c) mandates that every
    code-required indicator is "present exactly once" — multiset equality in the validator
    below. §7(b)
    is the artifact that actually SHIPS, and it had neither: measured on the committed tree, this
    module built, validated and WROTE a geography that was simultaneously ranked and excluded,
    duplicated exclusion records, duplicate rank values, a rank-99 gap, 2-based ranks,
    all-ranks-1, the same geography ranked twice, and a ONE-row ranking (1 of 8 modeled
    geographies). Spec §8 states the obligation — a geography is either ranked or carries an
    exclusion record naming the unresolved input, and "the rankings cover the remaining members"
    — and nothing held it, so every one of those shapes read as a complete result.

    THE DOMAIN IS THE CODE-OWNED REGISTRY, never a literal list typed here:
    `geography.MODELED_GEOGRAPHIES` is the union of the per-workbook expected sets the loaders
    already refuse a workbook for losing (`require_all_geographies`), so the artifact is checked
    against the same declaration the inputs are. A typed list is the stale-constant class this
    repo keeps re-finding, and it would go wrong silently in the one direction that matters —
    quietly SMALLER than the domain.

    WHY EACH CLAUSE, since a set gate that only counts is not a set gate:
      * DUPLICATE geography — the same geography twice carries two verdicts under one name; a
        consumer keyed by geography keeps whichever it read last.
      * RANKED AND EXCLUDED — the two arrays make opposite claims (this geography has an ED
        trajectory / its input could not be resolved at all). The exclusion record binds
        `geography` to the WHOLE `Geography` enum, not to §8's HORS_RMR terminal branch, so
        the overlap is reachable at every member.
      * UNION == DOMAIN — the coverage §8 states. This is the clause the one-row document
        violated, and the reason it is the dangerous one: a 1-of-8 file reads as "one geography
        at risk, seven fine", where an empty file at least reads as empty.
      * CONTIGUOUS PERMUTATION — a rank is a position in a total order; duplicate, gapped or
        2-based ranks are not one, and "rank 1" is what the whole artifact is read for.
    NOT checked, deliberately: that the rows are SORTED by rank (emission order is
    `rank_geographies`, and a consumer sorts), and any restriction on WHICH geography may be
    excluded (§8 branch iii is input-driven — DISJOINTNESS is what catches the contradiction).
    """
    rows, exclusions = doc["rankings"], doc["exclusions"]
    if not rows and not exclusions:
        # The narrowest case, refused FIRST because its message is the informative one: a
        # document with zero ranked rows AND zero exclusion records accounts for nothing at all,
        # and a consumer reading it sees "no geography is at risk" rather than "this run produced
        # nothing". The coverage clause below would also refuse it, less legibly.
        raise ValueError("rankings artifact accounts for no geography — zero ranked rows AND "
                         "zero exclusion records is a vacuous file, not a result; the run "
                         "emits NO file and reports the failure through its exit code")

    ranked = [row["geography"] for row in rows]
    excluded = [row["geography"] for row in exclusions]
    for label, seen in (("ranks", ranked), ("excludes", excluded)):
        repeated = sorted({geo for geo in seen if seen.count(geo) > 1})
        if repeated:
            raise ValueError(
                f"rankings artifact {label} a geography more than once: {repeated} — one "
                f"geography carries one verdict, and a duplicate leaves a consumer keyed by "
                f"geography holding whichever record it read last")
    both = sorted(set(ranked) & set(excluded))
    if both:
        raise ValueError(
            f"geography(ies) {both} are both RANKED and EXCLUDED — the two arrays make opposite "
            f"claims about the same geography (an ED trajectory exists / its input could not be "
            f"resolved), so the document contradicts itself")

    domain = {geo.value for geo in MODELED_GEOGRAPHIES}
    accounted = set(ranked) | set(excluded)
    if accounted != domain:
        raise ValueError(
            f"rankings artifact does not account for the modeled geography domain: "
            f"unaccounted={sorted(domain - accounted)}, not in the domain="
            f"{sorted(accounted - domain)} (spec §8 — every modeled geography is either RANKED "
            f"or carries an exclusion record naming the input that could not be resolved; a "
            f"partial file reads as that many geographies at risk and the rest fine)")

    ranks = sorted(row["rank"] for row in rows)
    if ranks != list(range(1, len(rows) + 1)):
        raise ValueError(
            f"rankings ranks {ranks} are not the contiguous permutation 1..{len(rows)} — a rank "
            f"is a position in a total order, so a duplicate, a gap or a non-1-based start makes "
            f"the ordering the artifact is read for unreadable")


def assert_tripwire_document_complete(doc: dict) -> None:
    """Spec §7(c)'s set contract: the baseline carries EXACTLY the code-owned required indicator
    set, as ONE comparison over the whole class (codex r10-F6).

    The landed body refused only the EMPTY baseline, on a derivation that applies verbatim to
    its siblings — and the truncated shape is the more dangerous one: a one-indicator file reads
    as one green indicator, where an empty file at least reads as empty. Multiset equality
    against the code-owned set catches empty, short and duplicated together, and mirrors
    `run_exit_code`'s coverage gate exactly, so the artifact and the exit code cannot disagree
    about what a complete baseline is. It costs a legitimate run nothing: every baseline that
    ships carries exactly the six, evaluated or synthesized."""
    emitted = sorted(record["indicator"] for record in doc["indicators"])
    if emitted != sorted(REQUIRED_INDICATORS):
        missing = sorted(REQUIRED_INDICATORS - set(emitted))
        duplicated = sorted({i for i in emitted if emitted.count(i) > 1})
        raise ValueError(
            f"tripwire baseline is not the code-owned required indicator set: emitted "
            f"{emitted}, required {sorted(REQUIRED_INDICATORS)} (missing={missing}, "
            f"duplicated={duplicated}) — an incomplete baseline reads as that many green "
            "indicators rather than as a gap, so NO file is emitted and the run exits nonzero")


def rankings_document(rankings, vintage, assumptions_hash, allowed_source_keys,
                      *, run_pairing: str, exclusions=(), rows_moved=None) -> dict:
    # The per-row TYPE contracts are NOT re-run here: `_ROW_CONTRACTS` owns them on the write
    # path (see the module docstring). What stays is what the writer cannot ask — that the
    # records are the PRODUCERS' typed returns rather than bare dicts — plus the whole-document
    # SET contract, which the writer DOES ask and which is checked here too so that a document
    # this builder hands back is already accountable for the domain.
    rows = [ranking_row(gr) for gr in _typed(rankings, GeoRanking, "rankings",
                                             "rank_geographies")]
    exclusion_rows = [exc.as_row() for exc in _typed(exclusions, RankingExclusion,
                                                     "exclusions", "exclude_from_rankings")]

    doc = {**_envelope(RANKINGS_SCHEMA, vintage, assumptions_hash, run_pairing),
           "rankings": rows, "exclusions": exclusion_rows}
    # `rows_moved=None` MEANS "no per-leg claim", and the field is then ABSENT rather than empty
    # (amendment #20(C)(2)). `pipeline._rank_stability` returns None exactly when it did not
    # evaluate the DECLARED grid — the reduced-sweep knob — and an empty map beside
    # `rank_stable: false` would read as "no leg moved anything", which is the opposite of what a
    # sweep that never ran measured. Absence is data; a zero is a claim.
    if rows_moved is not None:
        doc["rows_moved"] = dict(rows_moved)
    # THE SET CONTRACT, through the same validator `_DOC_CONTRACTS` dispatches on the write path
    # (spec §7b; codex r12-F2) — one declaration, reached from both doors. `rankings: []` is a
    # legitimate document when the exclusion records cover the domain, and nothing else is.
    assert_rankings_document_complete(doc)
    assert_no_open_strings(doc, allowed_source_keys)
    return doc


def tripwire_document(results, vintage, assumptions_hash, allowed_source_keys,
                      *, run_pairing: str) -> dict:
    # Record contract on the write path (`_ROW_CONTRACTS`); the COMPLETENESS of the SET, which
    # no per-record validator can see, through `assert_tripwire_document_complete` — the same
    # validator `_DOC_CONTRACTS` dispatches on the write path.
    records = [tripwire_record(result)
               for result in _typed(results, TripwireResult, "indicators", "evaluate_indicator")]
    doc = {**_envelope(TRIPWIRE_SCHEMA, vintage, assumptions_hash, run_pairing),
           "indicators": records}
    assert_tripwire_document_complete(doc)
    assert_no_open_strings(doc, allowed_source_keys)
    return doc


def scenario_prior_document(rows, vintage, assumptions_hash, allowed_source_keys,
                            *, run_pairing: str) -> dict:
    """The ScenarioPrior document (spec §7(a), Tranche 2). `vintage` is the FULLER §7(a) shape
    (`scenario_prior.prior_vintage`), not Tranche 1's minimal map — the walk's schema-dispatched
    vintage declaration refuses anything else under this schema. The mapping version is read
    from `balance.mapping.MAPPING_VERSION` at BUILD time, so a stamp that outlived its mapping
    cannot exist: `mapping.check_mapping_version` has already refused every row value by the
    time this assembles."""
    row_dicts = [prior_row_to_dict(row)
                 for row in _typed(rows, ScenarioPriorRow, "scenario_priors",
                                   "build_scenario_prior_rows")]
    doc = {**_envelope(SCENARIO_PRIOR_SCHEMA, vintage, assumptions_hash, run_pairing),
           "mapping_version": mapping.MAPPING_VERSION,
           "scenario_priors": row_dicts}
    # The SET contract (§7(a)'s COMPLETE Cartesian product), at the builder AND at the writer —
    # the same both-doors discipline codex r12-F2 mandated for the rankings.
    prior_document_complete(doc)
    assert_no_open_strings(doc, allowed_source_keys)
    return doc


# ------------------------------------------------------------------------------ the writer

def _dump_json(path, obj) -> None:
    """Serialize — `_canonical_bytes` and a BINARY write, which is the whole body.

    THE SERIALIZATION IS DECLARED AT `_canonical_bytes`, NOT HERE (amendment #22(C)).
    `payload_digest` hashes those same bytes, so the pairing token binds the form the file
    actually carries; two copies of a serialization convention drift, and here the drift would be
    a digest over bytes nobody ships. Which keywords are pinned, and why each is load-bearing, is
    stated at that function.

    THE WRITE IS `"wb"`, AND THAT SUBSUMES TWO PINS THIS DOCSTRING USED TO NAME (carry A4).
    `encoding="utf-8"` and `newline="\\n"` were guarding the TEXT layer: bare `open(path, "w")`
    takes the LOCALE's encoding, so a non-ASCII token mojibakes or raises under a non-UTF-8
    locale — an ENVIRONMENTAL failure a UTF-8 dev box never shows — and default newline
    translation emits CRLF on a platform that asks for it, moving the golden diff for no modeled
    reason. A binary write has no text layer to configure: the utf-8 encode and the LF happen
    inside `_canonical_bytes`, once, on the bytes the digest also sees. So encoding and line
    endings CANNOT differ between the file and its digest — which a second text-mode `json.dump`
    could not promise."""
    with open(path, "wb") as fh:
        fh.write(_canonical_bytes(obj))


# THE PER-RECORD CONTRACT, BY SCHEMA: which sequence position carries the records, and which
# validator owns them — one declaration, dispatched, like every other vocabulary in this module.
#
# THE DISPATCH IS FAIL-CLOSED AND THE TABLE IS PINNED, because this header used to CLAIM that
# being a dispatched table means "a third document type cannot arrive with its rows unbound"
# over a `.get(schema, ())` lookup and an unpinned table: an unlisted schema validated NO rows
# and returned silently, and the `exclusions` entry could be deleted with the whole suite still
# green (measured, review finding on the F6 repair). A live-sounding claim over bytes that
# cannot deliver it is stress gate F7's defect, reproduced inside F6's repair — so the
# mechanism was BUILT rather than the sentence narrowed. The lookup below REFUSES an unlisted
# schema instead of defaulting to "no contract", and `tests/test_artifacts.py` pins the table in
# both directions: no document type without a
# contract, no contract without a document type, and per schema EXACTLY the root positions
# that `_SEQ_PATHS` and `_KEY_REGISTRY` declare to be arrays of records.
#
# `exclusions` rides the table for the CONTRACT, not for today's coverage: every sub-case
# `assert_exclusion_row_valid` refuses is refused EARLIER by the walk (measured — both of its
# positions are `_VALUE_VALIDATORS`-bound and its key set `_KEY_REGISTRY`-bound), so no
# writer-path test can discriminate on that entry. But subsumption is a property of today's
# key/value tables, not of the record contract: the first cross-field rule that validator
# grows — the shape `assert_tripwire_record_valid` already has — reaches the write path only
# through this row.
_ROW_CONTRACTS = {
    RANKINGS_SCHEMA: (("rankings", assert_rankings_row_valid),
                      ("exclusions", assert_exclusion_row_valid)),
    TRIPWIRE_SCHEMA: (("indicators", assert_tripwire_record_valid),),
    SCENARIO_PRIOR_SCHEMA: (("scenario_priors", assert_scenario_prior_row_valid),),
}


def _assert_rows_valid(doc: dict) -> None:
    """Run the schema's per-record contract. Called AFTER the walk, which is what has already
    established that the schema is declared and that the sequence positions exist and hold
    arrays — so this reads them without re-checking either.

    The lookup REFUSES an undeclared schema instead of defaulting to "no contract". The walk's
    schema set (`_ROOT_FIELDS`) and this table are two independent declarations, and the day
    they disagree is exactly the day a document type's rows ship unbound — which is the one
    outcome the table exists to rule out. `ValueError`, not the bare `KeyError` an index gives:
    `cli.REFUSALS` turns that class into a named nonzero exit, and a KeyError would escape it
    as a traceback."""
    schema = doc["schema"]
    if schema not in _ROW_CONTRACTS:
        raise ValueError(
            f"no per-record contract is declared for schema {schema!r} — a document type whose "
            f"rows no validator owns must not be written; contracts exist for "
            f"{sorted(_ROW_CONTRACTS)}")
    for field_name, validator in _ROW_CONTRACTS[schema]:
        for row in doc[field_name]:
            validator(row)


# THE PER-DOCUMENT SET CONTRACT, BY SCHEMA — the properties of the whole ROW SET, which no
# per-record validator can see because each of them sees one record. Same shape as
# `_ROW_CONTRACTS` above, one level up, and FAIL-CLOSED for the same measured reason.
#
# IT IS A TABLE RATHER THAN TWO CALLS BECAUSE OF WHERE THE HOLE WAS (codex r12-F2). Spec §7's
# three emitted documents each carry a set rule — §7(a) the Tranche-2 ScenarioPrior keys as "the
# COMPLETE Cartesian product ... with NO duplicates", §7(b) the rankings covering the modeled
# geographies, §7(c) every required indicator "present exactly once" — and only §7(c) was built,
# at its builder. §7(b), the artifact that actually ships, had NO set contract at either door:
# `write_json_strict`, the sole artifact-contract validator, wrote a 1-of-8 rankings document.
# Declaring the contracts as a dispatched, PINNED table (`tests/test_artifacts.py` binds
# `set(_DOC_CONTRACTS) == set(_ROOT_FIELDS)`) is what makes the third document type — the
# Tranche-2 emitter whose §7(a) rule is exactly this class of check — unable to arrive with its
# SET unbound the way §7(b) did.
#
# BOTH BUILDERS ALSO CALL THEIR OWN VALIDATOR, and that is not the deletion-survivable shape
# stress gate F6 removed for the ROW contracts: there the builder call site was the ONLY
# enforcement point, so deleting it shipped `rank: -3` with a green suite. Here the write-path
# entry is the owner that cannot be deleted — remove a builder call and every set red still
# fires at the writer — while the builder call refuses at the point the SET is ASSEMBLED, which
# matters concretely: `stamp_pairing_token` builds BOTH documents twice and digests them before
# the writer sees either, so without it an unaccountable rankings document would be minted into
# a pairing token and refused only afterwards.
_DOC_CONTRACTS = {
    RANKINGS_SCHEMA: assert_rankings_document_complete,
    TRIPWIRE_SCHEMA: assert_tripwire_document_complete,
    SCENARIO_PRIOR_SCHEMA: prior_document_complete,
}


def _assert_document_complete(doc: dict) -> None:
    """Run the schema's SET contract. Called AFTER the row contracts, which have already
    established that every record is well-typed — so this reads `row["rank"]` and
    `row["geography"]` without re-checking either.

    The lookup REFUSES an undeclared schema instead of defaulting to "no contract", exactly as
    `_assert_rows_valid` does: a document type whose SET no validator owns is §7(b)'s hole
    reproduced for the next schema. `ValueError`, not the bare `KeyError` an index gives —
    `cli.REFUSALS` turns that class into a named nonzero exit."""
    schema = doc["schema"]
    if schema not in _DOC_CONTRACTS:
        raise ValueError(
            f"no document-level contract is declared for schema {schema!r} — a document type "
            f"whose row SET no validator owns must not be written; contracts exist for "
            f"{sorted(_DOC_CONTRACTS)}")
    _DOC_CONTRACTS[schema](doc)


def write_json_strict(path: Path, doc: dict, allowed_source_keys) -> None:
    """Validate, then serialize. The file is opened only after every gate passes, so a
    refusal leaves NOTHING on disk.

    THE FIRST GATE RUNS HERE AND NOT ONLY AT THE BUILDERS: spec §7's 64-hex is re-checked on
    the way out, so a writer that merely serialized would let any document assembled outside
    the two builders ship unvalidated.

    EXACTLY WHAT IS CHECKED HERE, because a gate description broader than the gate is the
    defect this module was written to remove: finiteness over the whole tree (codex r4-F3),
    every position's declared kind and binding — every STRING position through
    `_VALUE_VALIDATORS` and the declared COUNT positions through `_SCALAR_VALIDATORS`
    (spec §7) — and, since stress gate F6, the per-ROW contracts, which this function OWNS
    rather than re-runs. `rank: 0`,
    `rank_stable: 1`, `mean_ed_reference: true` and an UNKNOWN record with a non-null
    `current_value` used to pass this function (measured, not assumed) while their only
    enforcement sat at a deletion-survivable builder call site; they now die here.

    COMPLETENESS IS CHECKED HERE TOO, and that is a CORRECTION to what this docstring used to
    say (codex r12-F2). It read "WHAT IS STILL NOT CHECKED HERE, and deliberately: COMPLETENESS
    ... both are properties of the SET, which the builders own because they are the ones that
    know what a complete set is" — and the builders did not know: `tripwire_document` owned the
    indicator set, `rankings_document` owned only "at least one geography", and this function,
    the SOLE artifact-contract validator, wrote a 1-of-8 rankings document, a geography both
    ranked and excluded, and duplicate ranks. The set properties are code-owned
    (`REQUIRED_INDICATORS`, `geography.MODELED_GEOGRAPHIES`), so the writer can read them as
    well as a builder can, and it is the one gate a document assembled OUTSIDE the two builders
    still meets. `_DOC_CONTRACTS` owns them, dispatched per schema and fail-closed."""
    _assert_finite(doc)
    assert_no_open_strings(doc, allowed_source_keys)
    _assert_rows_valid(doc)
    _assert_document_complete(doc)
    _dump_json(path, doc)
