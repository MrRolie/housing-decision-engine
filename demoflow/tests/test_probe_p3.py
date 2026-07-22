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

import json
import re
import urllib.request
from pathlib import Path

import pytest

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P3-living-arrangement.md"
WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
# Any valid product id works: this asks "does the service answer?", not "does this cube
# exist?" — a withdrawn cube still returns HTTP 200 with a FAILED status body.
LIVENESS_PID = 98100134
REACHABILITY_TIMEOUT = 10

# Values that mean "this slot was never resolved". A note carrying one of these in a
# DECISION slot is not an answer, and must never be accepted as one.
UNRESOLVED = {"", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL", "[FILL]", "N/A", "NONE"}

# Exception types that may legitimately excuse a recorded failure. Anything outside this
# set is a code/structural fault and must FAIL even when the source is unreachable.
NETWORK_EXCEPTIONS = frozenset(
    {
        "URLError",
        "HTTPError",
        "ContentTooShortError",
        "TimeoutError",
        "timeout",
        "socket.timeout",
        "gaierror",
        "herror",
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
        "RemoteDisconnected",
        "IncompleteRead",
        "BadStatusLine",
        "SSLError",
        "SSLEOFError",
        "NoResponse",  # run_p3's own marker for "nothing answered at all"
    }
)


def _note_text() -> str:
    assert NOTE.exists(), f"{NOTE} is missing — run `uv run python probes/run_p3.py` first"
    return NOTE.read_text(encoding="utf-8")


def _token(text: str, name: str) -> str | None:
    """The value of a `DECISION-...: value` token, or None if the token is absent."""
    found = re.search(rf"{re.escape(name)}:\s*(.+)", text)
    return found.group(1).strip().rstrip("`").strip() if found else None


def _recorded_failure_type(text: str) -> str | None:
    found = re.search(r"LIVE PROBE FAILED:\s*([A-Za-z_][A-Za-z0-9_.]*)\s*:", text)
    return found.group(1) if found else None


def _source_reachable() -> bool:
    """Cheap liveness probe against the exact endpoint run_p3.py uses.

    It MUST be a POST. `getCubeMetadata` rejects GET, so a GET-based check reports
    'unreachable' even against a perfectly healthy service — and every recorded failure
    would then launder itself into a skip, which is the cheap all-clear this gate exists
    to prevent. Caught while proving the gate fails when it should: with a GET probe,
    the fail-when-reachable branch was dead code.

    Any exception means unreachable.
    """
    try:
        req = urllib.request.Request(
            WDS,
            data=json.dumps([{"productId": LIVENESS_PID}]).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=REACHABILITY_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


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
