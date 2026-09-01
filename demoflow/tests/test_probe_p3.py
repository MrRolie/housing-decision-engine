"""P3 gates — does the committed note RESOLVE the hunt, or only look like it does?

The plan's version of this test asserted that five static strings appear in the note
("SEX-SPECIFIC", "0.24", "0.34", "borrowed_prior", "couple_share"). `run_p3.py` writes
every one of them UNCONDITIONALLY, so that assertion cannot be False — it passes on a
run where every WDS call 404'd and both `[FILL:]` slots were left unfilled. A gate that
cannot fail is not a gate, so those checks are kept here only as ADDITIVE boilerplate
(gate 3); the load-bearing gates below assert the OUTCOME.

    test_p3_decision_is_resolved   ->  "is the hunt answered, and by a live run?"
    test_p3_couple_share_is_cited  ->  "is couple_share cited, or explicitly NOT-FOUND?"
    test_p3_records_sex_specific_fallbacks -> the plan's content strings (additive)
    test_p3_note_regenerates_byte_identically_from_the_fixture
                                   ->  "is this file what the producer produces?" — the
                                       guard under the header's own "nothing in this file is
                                       hand-edited" claim, which nothing checked until
                                       2026-08-21. See section 4 at the bottom.
    test_p3_reads_no_clock         ->  the regen gate's own precondition.

One gate per question so a red names its own cause.

  RESOLUTION gate
    * a literal `[FILL:` anywhere        -> FAIL, naming the note path. The committed
                                            note must never carry a placeholder for a
                                            human to fill in — that is the fabrication
                                            surface this whole probe was hardened against.
    * `DECISION-FOUND-AT-CMA: YES|NO`    -> pass (an actual answer is recorded)
    * `LIVE PROBE FAILED: <NetExc>`      -> skip WITH THE REASON RECORDED, but only if the
                                            source is independently confirmed unreachable;
                                            if it answers 200 the probe is broken -> FAIL.
                                            A non-network exception type is a code fault
                                            and FAILS even offline, so an outage cannot
                                            launder a real bug into a green-looking skip.
    * anything else                      -> FAIL. Unknown is not OK.
    A `YES` additionally requires the live verdict token `LIVE PROBE VERDICT: FOUND-AT-CMA`:
    the cross-tab's DIMENSIONS existing does not prove VALUES survive at CMA x age x sex,
    and only the live pull establishes that. So "found" cannot be claimed from metadata alone.

  CITATION gate
    * a real source + a non-empty citation   -> pass
    * `NOT-FOUND` + the raise-path named     -> pass. A recorded not-found is a legitimate
                                                outcome here (spec §11.3 designed for it).
    * an unresolved/placeholder value        -> FAIL.
    Consistency is enforced both ways: FOUND-AT-CMA: YES may not sit beside a NOT-FOUND
    couple_share, and NO may not sit beside a cited one.

  The green path is OFFLINE — it reads the committed note and never touches the network.
  Only the failure branch probes reachability, and only to decide fail-vs-skip.
"""

import ast
import copy
import json
import re
from pathlib import Path

import pytest

from ._probe_asserts import (
    NETWORK_EXCEPTIONS,
    recorded_failure_type as _recorded_failure_type,
    source_reachable,
    token as _token,
)

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P3-living-arrangement.md"
WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
# Any valid product id works: this asks "does the service answer?", not "does this cube
# exist?" — a withdrawn cube still returns HTTP 200 with a FAILED status body.
LIVENESS_PID = 98100134
REACHABILITY_TIMEOUT = 10

# Values that mean "this slot was never resolved". A note carrying one of these in a
# DECISION slot is not an answer, and must never be accepted as one.
UNRESOLVED = {"", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL", "[FILL]", "N/A", "NONE"}


def _note_text() -> str:
    assert NOTE.exists(), f"{NOTE} is missing — run `uv run python probes/run_p3.py` first"
    return NOTE.read_text(encoding="utf-8")


def _source_reachable() -> bool:
    """Cheap liveness probe against the exact endpoint run_p3.py uses.

    It MUST be a POST. `getCubeMetadata` rejects GET, so a GET-based check reports
    'unreachable' even against a perfectly healthy service — and every recorded failure
    would then launder itself into a skip, which is the cheap all-clear this gate exists
    to prevent. Caught while proving the gate fails when it should: with a GET probe,
    the fail-when-reachable branch was dead code.

    Any exception means unreachable.
    """
    return source_reachable(
        WDS,
        timeout=REACHABILITY_TIMEOUT,
        method="POST",
        data=json.dumps([{"productId": LIVENESS_PID}]).encode(),
        headers={"Content-Type": "application/json"},
    )


def _fail_or_skip_on_recorded_failure(text: str) -> None:
    """Shared failure-branch policy. Returns only if no failure was recorded."""
    if "LIVE PROBE FAILED" not in text:
        return
    recorded = _recorded_failure_type(text)
    if recorded is None:
        pytest.fail(
            f"P3 records LIVE PROBE FAILED with no parseable exception type — the failure "
            f"cannot be classified, so it cannot be excused. See: {NOTE}"
        )
    if recorded not in NETWORK_EXCEPTIONS:
        pytest.fail(
            f"P3 records LIVE PROBE FAILED: {recorded} — that is a code/structural fault, "
            f"not a network outage, so an unreachable source does not excuse it. See: {NOTE}"
        )
    if _source_reachable():
        pytest.fail(
            f"P3 records LIVE PROBE FAILED ({recorded}) while {WDS} answers — the probe is "
            f"broken, not the source. Re-run probes/run_p3.py. See: {NOTE}"
        )
    pytest.skip(
        f"P3 records a network-class failure ({recorded}) and {WDS} is independently "
        f"confirmed unreachable (timeout {REACHABILITY_TIMEOUT}s), so the hunt is genuinely "
        f"unanswerable here — NOT a pass. Recorded observation: {NOTE}"
    )


def test_p3_decision_is_resolved():
    """Gate 1 — the hunt must be ANSWERED, and a YES must rest on a live pull."""
    text = _note_text()

    assert "[FILL:" not in text, (
        f"{NOTE} still contains an unresolved `[FILL:` placeholder. The committed note must "
        "carry a decision computed by probes/run_p3.py from live WDS responses — a slot left "
        "for a human to fill in is exactly the fabrication surface this probe guards. "
        "Re-run: uv run python probes/run_p3.py"
    )

    _fail_or_skip_on_recorded_failure(text)

    found = _token(text, "DECISION-FOUND-AT-CMA")
    assert found in {"YES", "NO"}, (
        f"{NOTE} must record an actual yes/no for CMA-granularity availability via "
        f"`DECISION-FOUND-AT-CMA:`; got {found!r}. Unknown is not OK — re-run probes/run_p3.py."
    )

    if found == "YES":
        assert "LIVE PROBE VERDICT: FOUND-AT-CMA" in text, (
            f"{NOTE} claims DECISION-FOUND-AT-CMA: YES but records no "
            "`LIVE PROBE VERDICT: FOUND-AT-CMA`. A cube's dimensions existing does not prove "
            "non-suppressed VALUES at CMA x age x sex; only the live pull establishes that, "
            "so 'found' may not be claimed from metadata alone."
        )


def test_p3_couple_share_is_cited():
    """Gate 2 — couple_share is cited, or explicitly NOT-FOUND with the raise-path named.

    Separate from gate 1 because it is a separate question: the cross-tab could resolve
    while the couple_share slot is left dangling, and folding the two would let one red
    stand for either cause.
    """
    text = _note_text()
    _fail_or_skip_on_recorded_failure(text)

    source = _token(text, "DECISION-COUPLE-SHARE-SOURCE")
    assert source is not None, (
        f"{NOTE} records no `DECISION-COUPLE-SHARE-SOURCE:` token at all — couple_share has "
        "NO invented default (spec §11.3), so its provenance must be recorded either way."
    )
    assert source.upper() not in UNRESOLVED, (
        f"{NOTE} leaves DECISION-COUPLE-SHARE-SOURCE unresolved ({source!r}). Record a real "
        "source with citation, or an explicit NOT-FOUND — a placeholder is neither."
    )

    found = _token(text, "DECISION-FOUND-AT-CMA")

    if source.upper() == "NOT-FOUND":
        assert found == "NO", (
            f"{NOTE} is self-contradictory: couple_share NOT-FOUND but "
            f"DECISION-FOUND-AT-CMA: {found!r}. The CMA cross-tab supplies couple_share, so a "
            "YES cannot coexist with a not-found couple_share."
        )
        assert re.search(r"initialization RAISES", text, re.I), (
            f"{NOTE} records couple_share NOT-FOUND but never names the consequence. A "
            "recorded not-found is a legitimate outcome ONLY when the raise-path is stated: "
            "initialization RAISES (LoaderError). Silence here reads as a benign gap."
        )
        return

    # A real source was named -> it must carry a citation.
    citation = _token(text, "DECISION-COUPLE-SHARE-CITATION")
    assert citation is not None and citation.upper() not in UNRESOLVED, (
        f"{NOTE} names a couple_share source ({source[:60]!r}...) but records no usable "
        f"`DECISION-COUPLE-SHARE-CITATION:`; got {citation!r}. A source without a citation is "
        "an assertion, not a provenance record."
    )
    assert len(citation) > 40 and re.search(r"\d{2}-\d{2}-\d{4}|\d{8}|https?://", citation), (
        f"{NOTE}'s couple_share citation is too thin to verify: {citation!r}. It must name the "
        "table/product id or a URL so a reviewer can re-derive the value."
    )
    assert found == "YES", (
        f"{NOTE} cites a couple_share source but records DECISION-FOUND-AT-CMA: {found!r}. "
        "If the cited source is not the CMA cross-tab, say so explicitly; as written the two "
        "tokens disagree."
    )


def test_p3_records_sex_specific_fallbacks():
    """Gate 3 — the plan's content strings. ADDITIVE ONLY.

    Every string here is written unconditionally by run_p3.py, so this gate cannot fail on
    a bad outcome. It is retained because it pins the spec-named fallback VALUES (the
    vitrine band) into the note; gates 1 and 2 are what actually judge the run.
    """
    text = _note_text()
    assert "SEX-SPECIFIC" in text and "0.24" in text and "0.34" in text
    assert "borrowed_prior" in text
    assert "couple_share" in text and "no invented default" in text.lower()


# ===========================================================================
# 4. The producer, offline: regen equality against the committed note
#
# WHY THIS SECTION EXISTS. The header this note publishes says "nothing in this file is
# hand-edited", and until 2026-08-21 nothing behind that claim could fail. Gates 1-3 above
# read the COMMITTED TEXT, so an edit that keeps the tokens well-formed passes all three:
# measured, writing the spec's fallback band BACKWARDS (`[0.34, 0.24]` at both of its sites,
# §4c and the DECISION block) shipped the full demoflow suite green, and
# `test_probes_common.py::test_provenance_header_matches_pinned_goldens` does not reach it
# either — it pins the `provenance_header` FUNCTION against synthetic fact mixes, never this
# file. The seat's ruling is that byte-identity regeneration is STRONGER than binding each
# claim to its attribution, and P8/P10 already carry that shape, so this is theirs applied
# here: run the REAL producer over a recorded capture of its two boundaries and compare BYTES.
#
# A gate that re-read the committed note to build its own inputs would be circular — it would
# go green under any edit, because the edit would move both sides. Nothing below reads the
# note: `fixtures/p3_wds_capture.json` is a frozen recording of the live WDS responses (see
# `fixtures/make_p3_fixture.py` for the recipe and for the ONE field in it that is pinned
# rather than captured, the catalogue size).
#
# WHAT IT DOES AND DOES NOT ESTABLISH. It establishes that every line of the note is the
# output of `run_p3.py` over those responses — so a hand edit anywhere, in prose or in a
# figure, reds. It does NOT re-verify that the responses are what StatCan publishes today;
# that is what a re-run of the maker does, and on the 2026-08-21 capture the pristine probe
# reproduced the committed note at every line except the catalogue count, which is how §5's
# "a re-pull must reproduce these counts" came to be verified rather than asserted.
# ===========================================================================
CAPTURE = Path(__file__).resolve().parent / "fixtures" / "p3_wds_capture.json"
_CAPTURE = json.loads(CAPTURE.read_text(encoding="utf-8"))
_CELLS = {tuple(k.split("|", 1)): v for k, v in _CAPTURE["cells"].items()}
# The `refPer` every captured point carried. Read but never printed by the producer; kept so
# the offline response has the live SHAPE rather than a minimal one the source never sends.
_REF_PER = "2021-01-01"
# Filler for the catalogue's non-matching bulk. `10*` is outside the `981*` Census family AND
# the title carries none of the sweep's three title keys, so filler can only ever be counted,
# never shortlisted — if it could match, this fixture would manufacture the sweep's own finding.
_FILLER_PID = 10100001
_FILLER_TITLE = "filler cube, outside the Census product family"


def _cube(pid: int) -> dict:
    """One `getCubeMetadata` object, rebuilt from the capture."""
    entry = _CAPTURE["cubes"][str(pid)]
    return {"productId": str(pid), "cubeTitleEn": entry["title"],
            "releaseTime": entry["release"], "archiveStatusEn": entry["archive"],
            "dimension": [{"dimensionPositionId": dim["pos"], "dimensionNameEn": dim["name"],
                           "member": [{"memberId": m["id"], "memberNameEn": m["name"]}
                                      for m in dim["members"]]}
                          for dim in entry["dimensions"]]}


def _fake_catalogue(cubes: dict | None = None) -> list:
    """`getAllCubesListLite`, at the size the committed run observed.

    The captured cubes carry their REAL titles, so the sweep's title predicate does the same
    work it does live — the seven hits are selected here, not listed. The rest of the
    catalogue is inert filler, present only so `len(cubes)` reproduces the count the note
    records. See `fixtures/make_p3_fixture.py`: that count is the one pinned field, because
    the live catalogue grows and the note is a point-in-time observation.
    """
    table = _CAPTURE["cubes"] if cubes is None else cubes
    out = [{"productId": int(pid), "cubeTitleEn": entry["title"]}
           for pid, entry in sorted(table.items())]
    filler = _CAPTURE["sweep"]["catalogue_size"] - len(out)
    assert filler >= 0, f"the capture holds more cubes ({len(out)}) than the catalogue size"
    out += [{"productId": _FILLER_PID + i, "cubeTitleEn": _FILLER_TITLE}
            for i in range(filler)]
    return out


def _fake_post(url: str, payload: list, cells: dict | None = None) -> list:
    """The WDS POST boundary, served from the capture.

    Data responses come back SORTED BY COORDINATE, not in request order — that is what the
    live endpoint does (recorded in this probe's own §5b), and a producer that zipped the two
    would pair every value with the wrong meaning while the note still looked plausible. A
    cell absent from the capture is returned the way the live endpoint returns a withheld one:
    `status: FAILED` with an EMPTY `vectorDataPoint`.
    """
    table = _CELLS if cells is None else cells
    if url == WDS_META_URL:
        return [{"status": "SUCCESS", "object": copy.deepcopy(_cube(int(r["productId"])))}
                for r in payload]
    assert url == WDS_DATA_URL, f"the offline boundary was asked for {url!r}"
    out = []
    for request in payload:
        key = (str(int(request["productId"])), request["coordinate"])
        points = ([{"refPer": _REF_PER, "value": table[key]}] if key in table else [])
        out.append({"status": "SUCCESS" if points else "FAILED",
                    "object": {"productId": key[0], "coordinate": key[1],
                               "vectorDataPoint": points}})
    out.sort(key=lambda o: (o["object"]["coordinate"], o["object"]["productId"]))
    return out


WDS_META_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
WDS_DATA_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"


def _wire(probe, tmp_path: Path, **overrides):
    """Point the probe's two boundary seams at the capture and its output at `tmp_path`.

    `main()` opens its own `new_run()`, so the registry needs no priming here — and OUT is
    redirected BEFORE `main()` runs, because a test that wrote the committed note would turn
    the byte-equality below into a tautology.
    """
    probe._post = overrides.get("post", _fake_post)
    probe._catalogue = overrides.get("catalogue", _fake_catalogue)
    probe.OUT = tmp_path / "P3-offline.md"
    return probe.OUT


def _run_offline(probe, tmp_path: Path, **overrides) -> str:
    out = _wire(probe, tmp_path, **overrides)
    probe.main()
    return out.read_text(encoding="utf-8")


@pytest.fixture
def offline(tmp_path):
    """A fresh probe module wired to the capture — module-scoped state cannot leak.

    `test_probes_common` is imported HERE rather than at module scope: it imports THIS module
    (it gates the shared provenance header against p3/p4/p5), so a top-level import would
    close an import cycle.
    """
    from . import test_probes_common as common

    return common._load_probe("p3"), tmp_path


def test_p3_note_regenerates_byte_identically_from_the_fixture(offline):
    """REGEN EQUALITY ON THE PRODUCER — the guard under "nothing in this file is hand-edited".

    A gate that only re-read the committed note would go green under any producer mutation the
    moment the note was regenerated through it, and green under any hand edit that kept the
    tokens well-formed. This runs the real derivation over the recorded responses and compares
    BYTES with what ships.
    """
    mod, tmp_path = offline
    got = _run_offline(mod, tmp_path)
    assert got == _note_text(), (
        f"{NOTE} is no longer what `probes/run_p3.py` produces from "
        f"{CAPTURE.name}. Either the note was hand-edited — the header says it never is — or "
        "the producer changed. If the live source moved, regenerate BOTH together: "
        "`uv run python probes/run_p3.py` then "
        "`uv run python tests/fixtures/make_p3_fixture.py`; they are the two halves of one "
        "claim, and updating either alone lands a note no run produced.")
    # Twice from the same capture: no clock, no ambient state, no response-order dependence.
    assert _run_offline(mod, tmp_path) == got, "the note is not deterministic across two runs"


def test_p3_reads_no_clock():
    """No date may enter the note from the wall clock.

    Every dated field in this note is a `releaseTime` a live response carried. A
    `date.today()` would look right on the day the note was built and break regen equality on
    the next — a failure with a one-day fuse that no single run can see.
    """
    tree = ast.parse((NOTE.parent / "run_p3.py").read_text(encoding="utf-8"))
    clocks = {("datetime", "now"), ("date", "today"), ("time", "time"), ("time", "monotonic")}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id, node.func.attr) in clocks):
            raise AssertionError(f"run_p3.py calls {node.func.value.id}.{node.func.attr}() at "
                                 f"line {node.lineno} — the note would stop regenerating")
