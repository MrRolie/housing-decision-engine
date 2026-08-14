"""P9 gates — is the CLOSURE claim earned, and is it earned at MEMBER level?

P9's whole product is a NEGATIVE claim with a stated scope ("the search is closed at member
level over the full catalogue as of vintage X"). That is the most dangerous artifact shape in
this arc: three previous absence claims in it were refuted by a cube the SEARCH could not see,
never by the data. So these gates hold the note to the two things that make its claim
falsifiable rather than reassuring:

  1. the sweep really was MEMBER-level and really was WHOLE-catalogue (the floor guards that
     refuse a gappy pull, an unread member set, or a missing positive control are mutation-
     tested — a guard that cannot fire is not a guard); and
  2. every number the note publishes is the number the committed index carries, and the pull
     the closure is scoped to is the pull the pins registry anchors (registry digest ==
     artifact header digest == the digest the note records). A closure scoped to a pull nobody
     can identify is a session memory with a table around it.

  PASS iff the note records EITHER
    (a) CLOSED-AT-MEMBER-LEVEL carrying every evidence token — catalogue count, resolved
        count, vintage, raw-pull sha, index artifact + its sha, flagged count, positive
        control and the residual — each independently gated, each agreeing with the committed
        index; OR
    (b) UNKNOWN-PROBE-FAILED with a recorded reason and boundary.
  FAIL on an unresolved `[FILL`, a token missing or unresolved under a CLOSED verdict, a note
    figure that disagrees with the committed index, or a digest triple that does not close.
  SKIP-with-reason ONLY if the recorded exception TYPE is network-class AND the WDS host is
    independently confirmed unreachable, probed with the SAME HTTP METHOD run_p9.py uses for
    it (POST — `getCubeMetadata` rejects GET, so a GET liveness check reports a healthy
    service as down and launders every recorded failure into a skip).

  The green path is entirely OFFLINE: it reads the committed note, the committed index and a
  committed FIXTURE CACHE. Only the failure branch touches the network, and only to decide
  fail-vs-skip.
"""

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from demoflow.loaders.pins import DATA_DIR, RAW_SOURCE_MEMBER, raw_anchor

from . import test_probes_common as common
from ._probe_asserts import (
    NETWORK_EXCEPTIONS,
    recorded_failure_type as _recorded_failure_type,
    source_reachable,
    token as _token,
)

PROBES = Path(__file__).resolve().parent.parent / "probes"
NOTE = PROBES / "P9-catalogue-closure.md"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_CACHE = FIXTURES / "p9_cache"
FIXTURE_INDEX = FIXTURES / "p9_index_expected.json"

# The liveness target. POST, because every metadata request run_p9.py makes is a POST and
# `getCubeMetadata` rejects GET — see the module docstring. `productId` 98100621 is one of the
# two positive-control cubes, so the liveness call is also a real request.
WDS_LIVENESS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
LIVENESS_PID = 98100621
REACHABILITY_TIMEOUT = 10

# "NOT-FOUND" and "NONE" are deliberately INSIDE this set: unlike p3/p6, P9 has no legitimate
# not-found outcome — its only earned verdict is a scoped CLOSURE, and every DECISION token it
# emits is a count, a digest, a vintage or a level. A token reading NONE here would be an
# unresolved field wearing an answer's clothes.
UNRESOLVED = {"", "UNKNOWN-PROBE-FAILED", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL", "[FILL]",
              "N/A", "NONE", "NOT-FOUND", "?"}

CLOSED = "CLOSED-AT-MEMBER-LEVEL"
EVIDENCE_TOKENS = (
    "DECISION-CLOSURE-LEVEL",
    "DECISION-CATALOGUE-COUNT",
    "DECISION-RESOLVED-COUNT",
    "DECISION-CUBE-LIST-VINTAGE",
    "DECISION-RAW-PULL-SHA256",
    "DECISION-INDEX-ARTIFACT",
    "DECISION-FLAGGED-COUNT",
    "DECISION-POSITIVE-CONTROL",
    "DECISION-RESIDUAL",
)


def _source_reachable() -> bool:
    """Is the WDS metadata endpoint answering? POST, the method run_p9.py uses for it."""
    return source_reachable(
        WDS_LIVENESS,
        timeout=REACHABILITY_TIMEOUT,
        method="POST",
        data=json.dumps([{"productId": LIVENESS_PID}]).encode(),
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture(scope="module")
def note() -> str:
    assert NOTE.exists(), f"{NOTE} was never written — run probes/run_p9.py"
    return NOTE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def probe():
    return common._load_probe("p9")


@pytest.fixture(scope="module")
def index() -> dict:
    path = DATA_DIR / "catalogue_member_index_p9.json"
    assert path.exists(), f"{path} was never written — run probes/run_p9.py"
    return json.loads(path.read_text(encoding="utf-8"))


def _verdict(note: str) -> str:
    value = _token(note, "DECISION-VERDICT")
    assert value, "the note carries no DECISION-VERDICT token at all"
    return value


def _require_closed_or_skip(note: str) -> None:
    """Every gate below asserts something about an EARNED closure. A recorded failure is a
    legitimate outcome, but only when the failure is network-class AND the host is really
    down: a code fault must fail here, never skip."""
    verdict = _verdict(note)
    if verdict == CLOSED:
        return
    assert verdict == "UNKNOWN-PROBE-FAILED", f"unknown verdict {verdict!r}"
    failure = _recorded_failure_type(note)
    assert failure, "an UNKNOWN verdict must record the exception TYPE that produced it"
    assert failure in NETWORK_EXCEPTIONS, (
        f"the note records a {failure} — a code/structural fault, not an outage. It must FAIL "
        f"here rather than launder into a skip.")
    assert not _source_reachable(), (
        f"the note records a {failure} but the WDS metadata endpoint answers POST right now — "
        f"a recorded failure against a healthy service is a real defect, not an outage.")
    pytest.skip(f"P9 recorded {failure} and the WDS endpoint is confirmed unreachable")


# ---------------------------------------------------------------------------
# The note: is the verdict resolved, and is every piece of evidence present?
# ---------------------------------------------------------------------------
def test_p9_no_unfilled_placeholder(note):
    assert "[FILL" not in note, "an unresolved placeholder survived into the committed note"


def test_p9_records_a_resolved_verdict(note):
    _require_closed_or_skip(note)
    for name in EVIDENCE_TOKENS:
        value = _token(note, name)
        assert value is not None, f"a {CLOSED} verdict is missing its `{name}` token"
        assert value not in UNRESOLVED, f"`{name}` is unresolved: {value!r}"


def test_p9_the_closure_is_scoped_and_the_residual_is_named(note):
    """A closure with no named residual is the absence claim this probe exists to replace.

    The four residuals are asserted individually rather than by a single "does the word
    residual appear" search: a note that dropped the LANGUAGE residual while keeping the
    vocabulary one would still contain the word, and the missing one is the honest limit a
    reader most needs.
    """
    _require_closed_or_skip(note)
    assert "does NOT close" in note, "the note states no residual at all"
    for needle, what in (
        ("Vocabulary.", "the vocabulary residual"),
        ("Language.", "the English-names-only residual"),
        ("Punctuation forms.", "the punctuation/normalization residual"),
        ("outside StatCan WDS", "the outside-WDS residual"),
    ):
        assert needle in note, f"the note does not name {what}"
    assert "no such source exists" not in note, (
        "the note makes an unscoped absence claim — the exact form ruling S forbids")


def test_p9_prints_the_vocabularies_it_actually_used(note, probe):
    """The residual is only judgeable if the lists are IN the note — and are the real ones.

    A note that printed a tidied-up vocabulary while the code matched another would publish a
    residual a reader cannot evaluate. Every term of both tuples is asserted present, and the
    counts are asserted too so a silently ADDED term (a wider search than the note claims)
    reds as well.
    """
    _require_closed_or_skip(note)
    for term in probe.IMMIGRANT_TERMS + probe.HOUSEHOLD_TERMS:
        assert f"`{term}`" in note, f"vocabulary term {term!r} is not printed in the note"
    assert f"IMMIGRANT-ish ({len(probe.IMMIGRANT_TERMS)} terms)" in note
    assert f"HOUSEHOLD-ish ({len(probe.HOUSEHOLD_TERMS)} terms)" in note


# ---------------------------------------------------------------------------
# The coupling: note <-> committed index <-> pins registry
# ---------------------------------------------------------------------------
def test_p9_note_figures_are_the_committed_indexs_figures(note, index, probe):
    """Every count the note publishes must be the count the artifact carries.

    The note is prose around an index; if the two can drift, the prose is decoration. Parsed
    from the DECISION tokens (stable, machine-shaped) rather than the tables.
    """
    _require_closed_or_skip(note)
    prov = index["_provenance"]
    assert (_token(note, "DECISION-CATALOGUE-COUNT")
            == str(prov["cube_list_vintage"]["catalogue_rows"]))
    assert _token(note, "DECISION-RESOLVED-COUNT") == str(prov["scanned"]["cubes"])
    assert _token(note, "DECISION-FLAGGED-COUNT") == str(prov["class_counts"]["flagged"])
    assert prov["class_counts"]["flagged"] > 0, (
        "a closure sweep that flagged nothing has no positive control and no evidence that "
        "its member-level match ever fired")
    assert prov["scanned"]["members"] > prov["scanned"]["dimensions"] > 0, (
        "the artifact records no member-level scan — a MEMBER-level closure over zero members")
    listed = {c["pid"] for c in index["cubes"]}
    for pid in probe.POSITIVE_CONTROL:
        assert pid in listed, f"positive-control cube {pid} is absent from the committed index"
        entry = next(c for c in index["cubes"] if c["pid"] == pid)
        assert entry["class"] == "flagged", (
            f"{entry['table']} is listed as {entry['class']!r}, not flagged — it is one of the "
            f"two cubes a dimension-name search missed, and it must land in the class that "
            f"models that miss")


def test_p9_the_digest_triple_closes(note, index):
    """registry raw anchor == artifact header digest == the digest the note records.

    This is what makes the closure reproducible rather than a session memory: the raw pull is
    5.29 GB (measured 2026-08-14; this docstring said ~400 MB when it was written, which is the
    same estimated-figure defect the probe's own docstring carried) and is NOT committed, so the
    ONLY thing tying the published closure to a specific
    catalogue vintage is this digest — and it exists in three places that can drift apart.
    Same shape as `test_pins.py::test_raw_source_anchor_pins_the_p2_inner_csv...`, one level up.
    """
    _require_closed_or_skip(note)
    artifact_name = "catalogue_member_index_p9.json"
    pinned = raw_anchor(artifact_name)
    assert index["_provenance"]["raw_pull_sha256"] == pinned, (
        f"the committed index records raw pull {index['_provenance']['raw_pull_sha256']} but "
        f"pins.RAW_SOURCE_SHA256 anchors {pinned} — the artifact and its anchor describe "
        f"different pulls")
    assert _token(note, "DECISION-RAW-PULL-SHA256") == pinned, (
        f"the note's DECISION-RAW-PULL-SHA256 is not the pinned anchor {pinned}")
    assert RAW_SOURCE_MEMBER[artifact_name], "the raw anchor names no upstream member"

    on_disk = hashlib.sha256((DATA_DIR / artifact_name).read_bytes()).hexdigest()
    recorded = _token(note, "DECISION-INDEX-ARTIFACT")
    assert on_disk in recorded, (
        f"the note records index sha {recorded!r} but the committed file hashes to {on_disk} — "
        f"the note describes an artifact that is not the one in the tree")


def test_p9_the_maintainer_cross_line_is_the_indexs_own_measurement(note, index, probe):
    """The DIRECT fork-class result must be COMPUTED here, never remembered from a prior run.

    "Exactly four cubes cross a household-maintainer dimension with immigrant vocabulary" is
    the finding that produced ruling T, and a figure of that shape is precisely the one that
    survives as prose long after the run that measured it — this arc's depth-1 defect class.
    So three things are tied together: the note's line to the index's `maintainer_cross`, the
    cross rule to the vocabulary the sweep ACTUALLY searched (a cross defined on a term
    outside `HOUSEHOLD_TERMS` would be measuring something the sweep never looked for), and
    every cross cube to the index listing — it matches both vocabularies by construction, so
    its absence there would mean the listing rule and the cross rule disagree.
    """
    _require_closed_or_skip(note)
    prov = index["_provenance"]["maintainer_cross"]
    cross = prov["product_ids"]
    assert cross, "the index records no maintainer cross at all"
    assert cross == sorted(set(cross)), f"the cross list is unsorted or repeats: {cross}"
    assert probe.MAINTAINER_DIMENSION_TERM in probe.HOUSEHOLD_TERMS, (
        f"the cross is defined on {probe.MAINTAINER_DIMENSION_TERM!r}, which is not a term the "
        f"sweep searches for — it would be counting a match that was never made")
    assert probe.MAINTAINER_DIMENSION_TERM in prov["rule"], (
        "the index states a cross rule that does not name the dimension term it used")

    recorded = _token(note, "DECISION-MAINTAINER-CROSS")
    assert recorded.startswith(f"{len(cross)} cubes"), (
        f"the note records {recorded!r} against an index carrying {len(cross)} cross cubes")
    listed = {c["pid"]: c for c in index["cubes"]}
    for pid in cross:
        assert probe.table_number(pid) in recorded, (
            f"cross cube {pid} is counted but not named in the note's line")
        assert pid in listed, (
            f"cross cube {pid} is missing from the index listing — it matches BOTH "
            f"vocabularies by construction, so the listing rule and the cross rule disagree")
        entry = listed[pid]
        assert any(probe.MAINTAINER_DIMENSION_TERM in terms
                   for terms in entry["household"]["dimension_matches"].values()), (
            f"{entry['table']} is recorded as a cross cube but carries no maintainer DIMENSION")
        assert entry["immigrant"]["level"] != "none", (
            f"{entry['table']} is recorded as a cross cube with no immigrant vocabulary at all")


# ---------------------------------------------------------------------------
# The producer: regen equality + the floor guards, offline on a committed fixture cache
# ---------------------------------------------------------------------------
def _fixture_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "cache"
    dest.mkdir()
    for name in ("catalogue.json", "meta.jsonl", "manifest.json"):
        (dest / name).write_bytes((FIXTURE_CACHE / name).read_bytes())
    return dest


def _render(payload: dict) -> str:
    """Exactly the bytes `write_index` emits, so the gate compares what ships."""
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def test_p9_index_regenerates_byte_identically_from_the_fixture_cache(probe, tmp_path):
    """REGEN EQUALITY on the PRODUCER, not on the artifact.

    A gate that only re-read the committed index would go green under any producer mutation
    the moment the artifact was regenerated through it — the defect
    `test_census_ownership.py` records four times over. This runs the real
    `sweep` -> `build_index` -> serialize path over a committed fixture cache and compares
    BYTES against a committed expectation, so a mutated matcher, a mutated class rule or a
    mutated header shape reds without any network.
    """
    cache = _fixture_copy(tmp_path)
    got = _render(probe.build_index(probe.sweep(cache)))
    expected = FIXTURE_INDEX.read_text(encoding="utf-8")
    assert got == expected, "the producer no longer reproduces the pinned fixture index"
    # Twice, from the same cache: the derivation must read no clock and no ambient state.
    assert _render(probe.build_index(probe.sweep(cache))) == got


def test_p9_product_id_normalizes_the_two_endpoints_disagreeing_types(probe):
    """The WDS junction fact, pinned: `getAllCubesListLite` types productId as an INT while
    `getCubeMetadata` types the SAME id as a STRING.

    A REGRESSION pin — green the day it was written — and it earns its place on its failure
    MODE, not on novelty. Compare the two raw and every catalogue-vs-pull set operation goes
    vacuously disjoint, so `_guard_complete` reports 100% of the catalogue unresolved AND 100%
    of the pull extraneous simultaneously (it did, on the first full run: 8,226 and 8,226), and
    the pull loop re-requests every pid singly because each one reads as missing from its own
    batch. A guard whose broken form says "everything is missing" is not read as a type bug —
    it is read as an outage or a bad endpoint, and then tuned away. So the normalization is
    pinned here directly instead of being left inferable from a red suite.
    """
    assert probe.product_id({"productId": "98100621"}) == 98100621
    assert probe.product_id({"productId": 98100621}) == 98100621
    catalogue_typed = {98100621, 43100060}
    metadata_typed = {"98100621", "43100060"}
    assert not (catalogue_typed & metadata_typed), (
        "the two raw forms now intersect — this test's premise, and the guard's failure mode, "
        "no longer hold")
    assert catalogue_typed == {probe.product_id({"productId": p}) for p in metadata_typed}


def test_p9_the_fixture_cache_carries_that_mixed_typing_for_real(probe):
    """...and the normalization is exercised END TO END, not only in the unit above.

    The regen and floor-guard gates run `sweep` over the fixture cache, which crosses exactly
    this boundary — but only while the fixture keeps the shape the live endpoints have. A
    fixture rebuilt with homogenized types would leave both those gates green with the
    normalization deleted, so the fixture's own typing is asserted rather than assumed.
    """
    catalogue = json.loads((FIXTURE_CACHE / "catalogue.json").read_text(encoding="utf-8"))
    assert catalogue and all(isinstance(c["productId"], int) for c in catalogue), (
        "the fixture catalogue no longer types productId as getAllCubesListLite does")
    lines = (FIXTURE_CACHE / "meta.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines and all(isinstance(json.loads(line)["object"]["productId"], str)
                         for line in lines), (
        "the fixture metadata no longer types productId as getCubeMetadata does")


def test_p9_derivation_reads_no_clock(probe):
    """Every clock call must be lexically inside `pull()`.

    The artifact header carries a run date and a wall clock, and the artifact must regenerate
    byte-identically. Both are true only because those fields come from the cache's own
    manifest. A `datetime.now()` in the derivation would look perfectly correct on the day the
    artifact was built and break the regen gate on the next one — a failure with a one-day
    fuse, which no single-day test run can see.
    """
    tree = ast.parse((PROBES / "run_p9.py").read_text(encoding="utf-8"))
    pull = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "pull")
    inside = {id(n) for n in ast.walk(pull)}
    clocks = {("datetime", "now"), ("date", "today"), ("time", "time"), ("time", "monotonic")}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id, node.func.attr) in clocks
                and id(node) not in inside):
            raise AssertionError(
                f"run_p9.py calls {node.func.value.id}.{node.func.attr}() at line "
                f"{node.lineno}, outside pull(). Every dated field in the artifact must come "
                f"from the cache manifest or the artifact stops regenerating byte-identically.")


# Figures the run's OWN measurement contradicts, with what it measured instead. Both were
# hand-typed into run_p9.py before the first full pull existed to contradict them: the pull is
# 5.29 GB (`stat()`, published as the index header's `raw_pull_bytes`) and 1,211 s (the cache
# manifest's `wall_clock_seconds`, published as the note's wall clock), not ~400 MB and not
# ~16 min. The module NARRATES that correction on purpose, so a retrospective mention is legal
# and a live claim is not — that distinction is the whole gate.
_CONTRADICTED_FIGURES = (
    ("400 MB", "5.29 GB — the index header's raw_pull_bytes, stat()-ed by sweep()"),
    ("16 min", "1,211 s / ~20 min — the cache manifest's wall_clock_seconds"),
    ("16-minute", "1,211 s / ~20 min — the cache manifest's wall_clock_seconds"),
)
_RETROSPECTION_MARKERS = ("estimated", "used to", "first draft", "no longer",
                          "when it was written")


def test_p9_no_contradicted_figure_survives_as_a_live_claim(probe):
    """No figure the run measured against may still be STATED as current in the generator.

    The depth-1 defect this probe exists to grade is a hand-typed number the run's own
    measurement contradicts. Correcting the emitted artifacts is not enough: the artifacts are
    derived, so they were never the place a stale literal could hide. It hid in the prose the
    generator carries — a docstring and, worse, an argparse `--help` string a user reads before
    ever seeing an artifact. Two rounds of correction each fixed the sites someone happened to
    grep for and left others standing, which is precisely why this is a gate and not a habit.

    Retrospective mentions are EXEMPT and must stay legal: the module deliberately tells the
    story of the ~400 MB estimate to anchor why every size now comes off `stat()`. So the rule
    is about tense, not about the digits — a line stating a contradicted figure passes only if
    it also marks that figure as the superseded one.
    """
    source = (PROBES / "run_p9.py").read_text(encoding="utf-8").splitlines()
    live = [
        f"  line {n}: states {stale!r}; measured {measured}\n    {line.strip()}"
        for n, line in enumerate(source, start=1)
        for stale, measured in _CONTRADICTED_FIGURES
        if stale.casefold() in line.casefold()
        and not any(m in line.casefold() for m in _RETROSPECTION_MARKERS)
    ]
    assert not live, (
        "run_p9.py states a figure its own run measured against, as a live claim:\n"
        + "\n".join(live)
        + "\n\nEither correct it to the measured value (attributed, with the measurement date, "
          "the way the module docstring's Run block and pull()'s docstring already are — no "
          "line numbers here on purpose: a pinned line number is this same defect) "
          "or mark it retrospective — "
        + f"any of {_RETROSPECTION_MARKERS} on the same line.")


@pytest.mark.parametrize("mutation", [
    "empty-catalogue", "catalogue-without-positive-control", "duplicate-cube",
    "missing-cube", "no-manifest", "deflag-positive-control", "failed-status",
    "cube-without-dimensions",
])
def test_p9_floor_guards_are_load_bearing(probe, tmp_path, mutation):
    """Each guard must actually fire. A guard that cannot fail is not a guard.

    An UNREACHABLE mutant would prove nothing, so every mutation below is applied to the
    fixture cache the green path really reads, and the unmutated cache is asserted to pass in
    `test_p9_index_regenerates_byte_identically_from_the_fixture_cache`.
    """
    cache = _fixture_copy(tmp_path)
    catalogue = json.loads((cache / "catalogue.json").read_text(encoding="utf-8"))
    lines = (cache / "meta.jsonl").read_text(encoding="utf-8").splitlines()
    control = probe.POSITIVE_CONTROL[0]

    def _pid(line: str) -> int:
        return int(json.loads(line)["object"]["productId"])

    if mutation == "empty-catalogue":
        (cache / "catalogue.json").write_text("[]", encoding="utf-8")
    elif mutation == "catalogue-without-positive-control":
        (cache / "catalogue.json").write_text(
            json.dumps([c for c in catalogue if c["productId"] != control]), encoding="utf-8")
    elif mutation == "duplicate-cube":
        lines.append(lines[0])
        (cache / "meta.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mutation == "missing-cube":
        (cache / "meta.jsonl").write_text(
            "\n".join(line for line in lines if _pid(line) != control) + "\n", encoding="utf-8")
    elif mutation == "no-manifest":
        (cache / "manifest.json").unlink()
    elif mutation == "deflag-positive-control":
        # Strip every MEMBER name from the control cube, keeping its dimensions. The cube is
        # still resolved, still matched at dimension level — only the member-level evidence
        # is gone, which is exactly the blindness ruling S was caused by.
        out = []
        for line in lines:
            obj = json.loads(line)
            if int(obj["object"]["productId"]) == control:
                for dim in obj["object"]["dimension"]:
                    dim["member"] = [dict(m, memberNameEn="x") for m in dim["member"]]
            out.append(json.dumps(obj, ensure_ascii=False))
        (cache / "meta.jsonl").write_text("\n".join(out) + "\n", encoding="utf-8")
    elif mutation == "failed-status":
        out = []
        for line in lines:
            obj = json.loads(line)
            if int(obj["object"]["productId"]) == control:
                obj["status"] = "FAILED"
            out.append(json.dumps(obj, ensure_ascii=False))
        (cache / "meta.jsonl").write_text("\n".join(out) + "\n", encoding="utf-8")
    elif mutation == "cube-without-dimensions":
        out = []
        for line in lines:
            obj = json.loads(line)
            if int(obj["object"]["productId"]) == control:
                obj["object"]["dimension"] = []
            out.append(json.dumps(obj, ensure_ascii=False))
        (cache / "meta.jsonl").write_text("\n".join(out) + "\n", encoding="utf-8")

    with pytest.raises(probe.ProbeRefusal):
        probe.sweep(cache)


def test_p9_refusal_is_not_a_network_exception_name(probe):
    """`ProbeRefusal` must never be excusable as an outage.

    Every mutation above raises it, and `_require_closed_or_skip` skips only on a
    NETWORK_EXCEPTIONS type — so a refusal whose NAME joined that set would turn every one of
    those failures into a green skip.
    """
    assert probe.ProbeRefusal.__name__ not in NETWORK_EXCEPTIONS
    assert issubclass(probe.ProbeRefusal, RuntimeError)
    assert not issubclass(probe.ProbeRefusal, OSError)


# ---------------------------------------------------------------------------
# The match rule itself — the thing the whole closure rests on
# ---------------------------------------------------------------------------
def _cube(pid: int, dims: list) -> dict:
    return {"productId": pid, "cubeTitleEn": f"cube {pid}", "archiveStatusCode": "2",
            "dimension": [{"dimensionPositionId": i + 1, "dimensionNameEn": name,
                           "member": [dict({"memberId": j + 1, "memberNameEn": m,
                                            "geoLevel": None}, **extra)
                                      for j, (m, extra) in enumerate(members)]}
                          for i, (name, members) in enumerate(dims)]}


def test_p9_flags_the_member_only_class_a_dimension_search_cannot_see(probe):
    """The load-bearing behaviour, on a synthetic cube shaped like 98-10-0621-01.

    Immigrant status lives ONLY in member names; the household axis is a dimension name. A
    dimension-name search sees a household cube with no immigrant axis and moves on — which is
    precisely how 98-10-0621-01 was missed. The class rule must call this FLAGGED.
    """
    cube = _cube(98999999, [
        ("Population characteristics (46)", [("Non-immigrants", {}), ("Before 2016", {}),
                                             ("Immigrants", {})]),
        ("Primary household maintainer", [("Total", {})]),
    ])
    record = probe.scan_cube(cube)
    assert record["vocab"]["immigrant"]["level"] == "member-only"
    assert record["vocab"]["household"]["level"] == "dimension"
    assert probe.classify(record) == "flagged"
    # And the falsifier: with the immigrant members renamed, the very same cube drops out.
    blind = _cube(98999999, [("Population characteristics (46)", [("A", {}), ("B", {})]),
                             ("Primary household maintainer", [("Total", {})])])
    assert probe.classify(probe.scan_cube(blind)) == "single-vocabulary"


def test_p9_flags_the_mirror_class_too(probe):
    """The 43-10-0060-01 shape: immigrant at DIMENSION level, household ONLY in members."""
    cube = _cube(43999999, [
        ("Immigrant and generation status", [("Total", {})]),
        ("Indicators", [("Owner households spending 30% or more", {}), ("Living alone", {})]),
    ])
    record = probe.scan_cube(cube)
    assert record["vocab"]["immigrant"]["level"] == "dimension"
    assert record["vocab"]["household"]["level"] == "member-only"
    assert probe.classify(record) == "flagged"


def test_p9_normalization_reaches_names_a_plain_match_would_miss(probe):
    """NBSP and case, both measured live: 43-10-0060-01's labels carry trailing NBSPs."""
    assert probe.normalize("Montréal (CMA), Que.\xa0\xa0") == "montréal (cma), que."
    assert probe.normalize("TOTAL  -\tIMMIGRANT\xa0STATUS") == "total - immigrant status"
    cube = _cube(11999999, [
        ("Some axis", [("TOTAL\xa0- Immigrant status", {})]),
        ("Another axis", [("Owner\xa0occupied", {})]),
    ])
    assert probe.classify(probe.scan_cube(cube)) == "flagged"


def test_p9_geography_is_detected_structurally_and_cma_reach_is_a_union(probe):
    """A geography axis is found by `geoLevel`, never by the dimension being NAMED Geography.

    A name test is the same class of selection rule that hid 98-10-0621-01, so it must not be
    the thing deciding whether a candidate cube reaches the modeled CMAs.
    """
    by_code = _cube(1, [("Région", [("Montréal", {"geoLevel": 503})]),
                        ("Immigrant status", [("Total", {})]),
                        ("Tenure", [("Owner", {})])])
    assert probe._geo_dimension_positions(by_code["dimension"]) == [1]
    reach, levels = probe._cma_reach(by_code["dimension"])
    assert reach is True and levels == [503]

    by_name = _cube(2, [("Région", [("Québec (CMA), Que.\xa0", {"geoLevel": 97})])])
    assert probe._cma_reach(by_name["dimension"]) == (True, [97])

    province_only = _cube(3, [("Région", [("Quebec", {"geoLevel": 2})])])
    assert probe._cma_reach(province_only["dimension"]) == (False, [2])

    no_geo = _cube(4, [("Indicators", [("Owner", {})])])
    assert probe._geo_dimension_positions(no_geo["dimension"]) == []
    assert probe._cma_reach(no_geo["dimension"]) == (False, [])


def test_p9_class_rule_separates_flagged_from_dimension_level_matches(probe):
    """`flagged` requires at least one MEMBER-ONLY vocabulary — the rest is not the class."""
    both_dims = _cube(5, [("Immigrant status", [("Total", {})]), ("Tenure", [("Total", {})])])
    assert probe.classify(probe.scan_cube(both_dims)) == "both-dimension-level"
    one_only = _cube(6, [("Tenure", [("Owner", {})])])
    assert probe.classify(probe.scan_cube(one_only)) == "single-vocabulary"
    neither = _cube(7, [("Industry", [("Total", {})])])
    assert probe.classify(probe.scan_cube(neither)) == "none"


def test_p9_the_maintainer_cross_rule_needs_both_halves_and_a_DIMENSION(probe):
    """The cross rule, falsified in both directions on synthetic cubes.

    It is deliberately NARROWER than the FLAGGED class — the maintainer axis must be a
    DIMENSION, while the immigrant vocabulary may sit at either level. Both halves are pinned
    because either one silently widening turns a four-cube finding into a long list nobody
    can act on, and the member-only maintainer case is the one a careless `in` test would let
    through.
    """
    both = _cube(1, [("Primary household maintainer", [("Total", {})]),
                     ("Population characteristics (46)", [("Immigrants", {})])])
    assert probe.maintainer_cross(probe.scan_cube(both)) is True

    no_immigrant = _cube(2, [("Primary household maintainer", [("Total", {})]),
                             ("Population characteristics (46)", [("Total", {})])])
    assert probe.maintainer_cross(probe.scan_cube(no_immigrant)) is False

    maintainer_only_as_member = _cube(3, [
        ("Indicators", [("Household maintainer rate", {})]),
        ("Immigrant status", [("Total", {})])])
    record = probe.scan_cube(maintainer_only_as_member)
    assert record["vocab"]["household"]["level"] == "member-only"
    assert probe.maintainer_cross(record) is False

    other_household_dimension = _cube(4, [("Tenure", [("Owner", {})]),
                                          ("Immigrant status", [("Total", {})])])
    assert probe.classify(probe.scan_cube(other_household_dimension)) == "both-dimension-level"
    assert probe.maintainer_cross(probe.scan_cube(other_household_dimension)) is False


def test_p9_note_is_generated_by_the_probe_that_claims_it(note):
    """House rule #1's visible half: the note names its own writer and nothing else."""
    assert "Written by `probes/run_p9.py`; nothing in this file is hand-edited." in note
    assert re.search(r"This run registered \d+ provenance-tagged figures", note)
