"""P4 gates — does the committed note RECORD a usable coarse-netting multiplier?

The plan's version asserted `("VERDICT: WIRED" in text) or ("LIVE PULL FAILED" in
text)` and `"multiplier" in text.lower()`. run_p4.py writes one of those markers
UNCONDITIONALLY, so that disjunction can never be False — it passes on a run that
fabricated nothing AND on a run that fabricated everything. A gate that cannot
fail is not a gate. The gates below assert the OUTCOME.

P4 has TWO legitimate success shapes (spec §6):
  (a) a real per-CMA differential — the immigrant/non-immigrant ownership ratio
      pulled live from a cube (FOUND-AT-CMA: YES, with per-CMA numbers), OR
  (b) a documented FALLBACK multiplier band — an inline CITATION + the
      `borrowed_prior` flag, because the exact CMA cross-tab is not free.
The forbidden outcomes: an unresolved `[FILL`, or a silent multiplier of 1.0
without a cited justification (that would collapse the netting), or neither a
differential nor a cited band.

  test_p4_no_unfilled_placeholder     -> the fabrication surface stays closed
  test_p4_records_cited_multiplier    -> a valid, cited, banded (or per-CMA) multiplier
  test_p4_verdict_and_content         -> the plan's content strings + the live verdict (additive)

  The green path is OFFLINE — it reads the committed note (the fallback band is
  external published literature, so it does not depend on the network). Only the
  degenerate no-deliverable branch probes reachability, and only to decide
  fail-vs-skip: an outage must never launder into a silent pass.
"""

import json
import math
import re
from pathlib import Path

import pytest

from ._probe_asserts import (
    NETWORK_EXCEPTIONS,
    recorded_failure_type as _recorded_failure_type,
    source_reachable,
    token as _token,
)

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P4-immigrant-ownership-diff.md"
WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
# Any valid product id: this asks "does the service answer?", not "does this cube exist?".
LIVENESS_PID = 98100231
REACHABILITY_TIMEOUT = 10

UNRESOLVED = {"", "UNRESOLVED-PROBE-FAILED", "UNCONFIRMED-PROBE-FAILED", "TBD",
              "FILL", "[FILL]", "N/A", "NONE", "NOT-FOUND"}


def _note_text() -> str:
    assert NOTE.exists(), f"{NOTE} is missing — run `uv run python probes/run_p4.py` first"
    return NOTE.read_text(encoding="utf-8")


def _parse_band(text: str) -> tuple[float, float, float] | None:
    """Parse `DECISION-RATIO-MULTIPLIER-BAND: [lo, center, hi]` into 3 floats."""
    raw = _token(text, "DECISION-RATIO-MULTIPLIER-BAND")
    if not raw:
        return None
    nums = re.findall(r"[-+]?\d*\.?\d+", raw)
    if len(nums) != 3:
        return None
    return tuple(float(n) for n in nums)  # type: ignore[return-value]


def _citation_ok(text: str) -> tuple[bool, str | None]:
    """The shared citation bar, used by BOTH success shapes (a) and (b).

    A resolved `DECISION-RATIO-CITATION` with a minimum-length source string AND a
    URL or catalogue/product id, so a reviewer can check the published figure. A
    bare `DECISION-RATIO-SOURCE` token is NOT a citation — the found-at-CMA path
    (shape a) is held to exactly this bar too, so a fabricated 'located' note with
    no inline citation cannot green the gate. Returns (ok, citation).
    """
    citation = _token(text, "DECISION-RATIO-CITATION")
    if citation is None or citation.strip().upper() in UNRESOLVED:
        return False, citation
    ok = len(citation) > 40 and bool(
        re.search(r"https?://|\d{2}-\d{2}-\d{4}|\b\d{8}\b", citation)
    )
    return ok, citation


def _has_cma_numbers(text: str) -> bool:
    """Per-CMA figures present for BOTH modeled CMAs — not merely the YES token."""
    return bool(re.search(r"(Montréal|Montreal).{0,60}\d", text)
                and re.search(r"(Québec|Quebec).{0,60}\d", text))


def _source_reachable() -> bool:
    """POST-parity liveness probe against the exact endpoint the hunt uses.

    MUST be a POST: getCubeMetadata rejects GET, so a GET check would report
    'unreachable' against a healthy service and let every recorded failure launder
    itself into a skip. Any exception means unreachable.
    """
    return source_reachable(
        WDS,
        timeout=REACHABILITY_TIMEOUT,
        method="POST",
        data=json.dumps([{"productId": LIVENESS_PID}]).encode(),
        headers={"Content-Type": "application/json"},
    )


def _fail_or_skip_when_no_deliverable(text: str) -> None:
    """Reached only when NO differential and NO band exist. Never a silent pass."""
    if "LIVE PROBE FAILED" not in text:
        pytest.fail(
            f"{NOTE} records neither a per-CMA differential nor a documented multiplier band, "
            f"and no live-probe failure to explain it. spec §6 forbids leaving the coarse "
            f"multiplier unrecorded. Re-run probes/run_p4.py."
        )
    recorded = _recorded_failure_type(text)
    if recorded is None:
        pytest.fail(f"{NOTE} records LIVE PROBE FAILED with no parseable exception type.")
    if recorded not in NETWORK_EXCEPTIONS:
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED: {recorded} — a code/structural fault, not a "
            f"network outage, so an unreachable source does not excuse it."
        )
    if _source_reachable():
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED ({recorded}) while {WDS} answers — the probe is "
            f"broken, not the source. Re-run probes/run_p4.py."
        )
    pytest.skip(
        f"{NOTE} produced no multiplier deliverable and records a network-class failure "
        f"({recorded}) while {WDS} is independently confirmed unreachable — genuinely "
        f"unanswerable here, NOT a pass."
    )


def test_p4_no_unfilled_placeholder():
    """Gate 1 — the committed note must never carry an unfilled `[FILL` slot.

    That placeholder is the fabrication surface this probe family was hardened
    against: a slot left for a human to type a number into.
    """
    text = _note_text()
    assert "[FILL" not in text, (
        f"{NOTE} still contains an unresolved `[FILL` placeholder — the note must be GENERATED "
        f"by probes/run_p4.py, never hand-filled. Re-run: uv run python probes/run_p4.py"
    )


def test_p4_records_cited_multiplier():
    """Gate 2 — a real, cited multiplier: a per-CMA differential OR a documented band.

    Rejects the forbidden outcomes: a degenerate/inverted band, a silent 1.0
    without a cited justification, an uncited or unflagged fallback, and the
    "neither differential nor band" gap.
    """
    text = _note_text()
    found = _token(text, "DECISION-FOUND-AT-CMA")

    # Success shape (a): a live per-CMA differential. Held to the SAME bar as the
    # fallback band — per-CMA numbers, a resolved source, AND a real inline
    # citation. A located-at-CMA verdict with no citation FAILS (a bare
    # DECISION-RATIO-SOURCE token is not a citation); this closes the escape hatch
    # so P5/P5b, which reuse this shape and DO have real located paths, cannot
    # green a fabricated 'found' note.
    if found == "YES":
        assert _has_cma_numbers(text), (
            f"{NOTE} claims DECISION-FOUND-AT-CMA: YES but shows no per-CMA numbers for both "
            f"Montréal AND Québec. A YES may not be asserted from the token alone."
        )
        source = _token(text, "DECISION-RATIO-SOURCE")
        assert source is not None and source.strip().upper() not in UNRESOLVED, (
            f"{NOTE} claims FOUND-AT-CMA: YES but records no resolved DECISION-RATIO-SOURCE."
        )
        ok, citation = _citation_ok(text)
        assert ok, (
            f"{NOTE} claims FOUND-AT-CMA: YES but its DECISION-RATIO-CITATION is missing or too "
            f"thin to verify ({citation!r}). A located per-CMA differential must carry a real "
            f"inline citation (URL or catalogue/product id) — the SAME bar as the fallback "
            f"band; a bare source token is not a citation."
        )
        return

    # Success shape (b): the documented fallback band.
    band = _parse_band(text)
    if band is None:
        # No deliverable at all -> outage-vs-fault, never a silent pass.
        _fail_or_skip_when_no_deliverable(text)
        return  # pragma: no cover — _fail_or_skip always raises

    lo, center, hi = band
    assert all(math.isfinite(x) for x in band), f"{NOTE} band has a non-finite endpoint: {band}"
    # 0 < lo < center < hi rejects an inverted band, a degenerate point band
    # ([x, x, x] — a point masquerading as a band), and a silent point-1.0 ([1,1,1]).
    assert 0 < lo < center < hi, (
        f"{NOTE} multiplier band {band} is not a proper 0 < lo < center < hi band. A point "
        f"masquerading as a band (or an inverted one) is not a recorded band. NOTE: the ratio "
        f"MAY exceed 1 (spec:129-131 — immigrants can out-own non-immigrants); only < 1 is "
        f"NOT asserted."
    )

    ok, citation = _citation_ok(text)
    flag = _token(text, "DECISION-RATIO-FLAG")

    # Forbidden silent 1.0: a multiplier centered at exactly 1.0 needs a cited justification.
    if abs(center - 1.0) < 1e-9:
        assert ok, (
            f"{NOTE} records a multiplier centered at 1.0 with no cited justification "
            f"({citation!r}) — the FORBIDDEN silent 1.0 (spec §6: it would collapse the netting)."
        )

    # Fallback band -> must carry the borrowed_prior flag AND an inline citation.
    assert flag is not None and "borrowed_prior" in flag.lower(), (
        f"{NOTE} records a fallback multiplier band but not `DECISION-RATIO-FLAG: "
        f"borrowed_prior` — a borrowed band that does not declare the borrow is not honest "
        f"provenance (spec §6)."
    )
    assert ok, (
        f"{NOTE} records a fallback band with no usable `DECISION-RATIO-CITATION:` "
        f"({citation!r}) — a band without a published source is an invented number, exactly "
        f"what spec §6 forbids. It must name a catalogue/product id or URL so a reviewer can "
        f"check the published figure."
    )

    # Consistency: the band path may not sit beside a claimed CMA differential.
    assert found in {"NO", "UNCONFIRMED-PROBE-FAILED"}, (
        f"{NOTE} records a fallback band but DECISION-FOUND-AT-CMA is {found!r}. A YES must be "
        f"backed by per-CMA numbers + a citation (success shape a), not a fallback band."
    )


def test_p4_verdict_and_content():
    """Gate 3 — the live verdict + the plan's content strings. ADDITIVE.

    Pins the plan's original `multiplier` requirement and the fact that the note
    records a live hunt verdict; gates 1-2 are what judge the run.
    """
    text = _note_text()
    assert "multiplier" in text.lower()
    # Either the hunt resolved (NOT-FOUND-AT-CMA) or it recorded its own failure — not silence.
    assert ("NOT-FOUND-AT-CMA" in text) or ("LIVE PROBE FAILED" in text), (
        f"{NOTE} records no live hunt verdict at all."
    )


def _load_run_p4():
    """Import run_p4.py as a fresh module (probes/ is not an importable package).

    The `sys.path` insert is load-bearing, not tidiness: run_p4.py imports its shared
    machinery FLAT (`from _wds import …`) because probes/ is deliberately not a
    package and script mode resolves it via `sys.path[0]`. `spec_from_file_location`
    does NOT put the file's directory on the path, so without this `exec_module` dies
    `ModuleNotFoundError: No module named '_wds'`.
    """
    import importlib.util
    import sys

    probes_dir = str(NOTE.parent)
    if probes_dir not in sys.path:
        sys.path.insert(0, probes_dir)
    spec = importlib.util.spec_from_file_location("run_p4_under_test", NOTE.parent / "run_p4.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_p4_vacuous_wds_response_is_unconfirmed_not_notfound(tmp_path):
    """Gate 4 — a NOT-FOUND must be EARNED over a non-empty audit (NS #1).

    A WDS-up-but-EMPTY response (200 -> [] / {}) never raises, so without the floor
    guard it launders straight into NOT-FOUND-AT-CMA over a population of zero — the
    cardinal cheap-all-clear the hardening ruling exists to prevent. The guard must
    REFUSE and route to UNCONFIRMED-PROBE-FAILED. Both WDS boundaries are patched, so
    this runs OFFLINE and does not touch the committed note.
    """
    fake_cubes = [
        {"productId": 98100231, "cubeTitleEn": "Age of primary household maintainer by tenure"},
        {"productId": 98100300,
         "cubeTitleEn": "Immigrant status and period of immigration by mother tongue"},
    ]
    scenarios = {
        "empty catalogue (getAllCubesListLite -> [])": (lambda: [], lambda pids: {}),
        "empty metadata (catalogue non-empty, getCubeMetadata -> {})": (
            lambda: list(fake_cubes),
            lambda pids: {},
        ),
    }
    for label, (catalogue, meta_batch) in scenarios.items():
        mod = _load_run_p4()
        mod.OUT = tmp_path / "note.md"
        mod._catalogue = catalogue
        mod._meta_batch = meta_batch
        mod.main()
        text = mod.OUT.read_text(encoding="utf-8")
        assert "LIVE HUNT VERDICT: NOT-FOUND-AT-CMA" not in text, (
            f"[{label}] a vacuous WDS response was laundered into a NOT-FOUND — the floor guard "
            f"did not fire. A NOT-FOUND must be EARNED over a non-empty audit (NS #1)."
        )
        assert _token(text, "DECISION-FOUND-AT-CMA") == "UNCONFIRMED-PROBE-FAILED", (
            f"[{label}] a vacuous WDS response must record DECISION-FOUND-AT-CMA: "
            f"UNCONFIRMED-PROBE-FAILED (the audit could not run), not a silent pass."
        )
        # The fallback band is network-independent, so it still emits even when the audit refuses.
        assert _parse_band(text) is not None, (
            f"[{label}] the cited fallback band must still emit even when the audit is refused."
        )
