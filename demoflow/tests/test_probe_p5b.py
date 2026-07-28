"""P5b gates — does the committed note PICK a temporary-resident stock source with all
its evidence, or honestly record UNKNOWN?

The plan's version asserted `("VERDICT: source chosen" in text) or ("LIVE PULL FAILED" in
text)`. run_p5b.py's plan sketch writes `- VERDICT: source chosen.` UNCONDITIONALLY inside
its `try`, so that disjunction can never be False — it passes on a run that resolved
everything AND on a run that fabricated everything. A gate that cannot fail is not a gate.
The gates below assert the OUTCOME (RULING-2), against the R6 verdict vocabulary:

  PASS iff the note records EITHER
    (a) LOCATED carrying EVERY evidence token — the resolved product id, the live title,
        the cadence, the geography level, the CMA answer, the measure type, the currency,
        the pick, its recorded limit and the tripwire status — each INDEPENDENTLY gated so
        a bare or placeholder token fails, OR
    (b) UNKNOWN-PROBE-FAILED with a recorded reason (the spec:473 tripwire fallback).
  FAIL on an unresolved `[FILL`, a LOCATED missing any evidence, or neither.
  SKIP-with-reason ONLY if the hunt was attempted and the source is independently
    confirmed unreachable — and only when the RECORDED exception TYPE is network-class
    (a code fault must not launder into a skip), probed with the SAME HTTP method the
    probe uses against that host.

  The green path is OFFLINE — it reads the committed note. Only the failure branch probes
  reachability, and only to decide fail-vs-skip.

  test_p5b_no_unfilled_placeholder      -> the fabrication surface stays closed
  test_p5b_records_pick_or_unknown      -> the load-bearing RULING-2 / R6 gate
  test_p5b_floor_guard_earns_verdict    -> the floor guard is load-bearing (mutation test)
  test_p5b_records_tripwire_framing     -> the spec framing strings (additive, NON-JUDGING)
"""

import re
from pathlib import Path

import pytest

from ._probe_asserts import (
    NETWORK_EXCEPTIONS,
    recorded_failure_type as _recorded_failure_type,
    source_reachable,
    token as _token,
)

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P5b-temp-resident-stock.md"

# The ONE liveness target. Unlike p5 (two hosts), every VERDICT-GATING boundary in
# run_p5b.py is on www150.statcan.gc.ca — `getCodeSets`, `getAllCubesListLite` and
# `getCubeMetadata` — so a single probe covers the failure branch. It is a POST against
# `getCubeMetadata` because that is the method run_p5b.py uses for that host: a GET
# liveness check there reports a HEALTHY service as unreachable and would launder every
# recorded failure into a skip. (test_probe_contracts.py enforces this method match.)
WDS_LIVENESS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
LIVENESS_PID = 17100121
REACHABILITY_TIMEOUT = 10

# NOTE: "NONE" is deliberately ABSENT. R6 allows `DECISION-PICK-LIMIT: none` as a real
# answer (a pick with no limitation), so a shared set containing "NONE" would reject a
# legitimate outcome. PICK-LIMIT is gated by its own rule below instead.
UNRESOLVED = {"", "UNKNOWN-PROBE-FAILED", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL",
              "[FILL]", "N/A", "NOT-FOUND", "?"}

# The verdict-gating boundaries run_p5b.py can attribute a failure to.
BOUNDARIES = ("wds-codesets", "wds-list", "wds-meta")


def _note_text() -> str:
    assert NOTE.exists(), f"{NOTE} is missing — run `uv run python probes/run_p5b.py` first"
    return NOTE.read_text(encoding="utf-8")


def _recorded_failure_boundary(text: str) -> str | None:
    found = re.search(rf"LIVE PROBE FAILED-AT:\s*({'|'.join(BOUNDARIES)})", text)
    return found.group(1) if found else None


def _source_reachable() -> bool:
    """Cheap POST liveness probe against the WDS host every gating boundary uses.

    POST, not GET: `getCubeMetadata` REJECTS GET, so a GET-based check reports a healthy
    service as unreachable and every recorded failure then launders itself into
    `pytest.skip` — the cardinal cheap all-clear. Any exception means unreachable.
    """
    return source_reachable(
        WDS_LIVENESS,
        timeout=REACHABILITY_TIMEOUT,
        method="POST",
        data=f'[{{"productId": {LIVENESS_PID}}}]'.encode(),
        headers={"Content-Type": "application/json"},
    )


def _fail_or_skip_on_recorded_failure(text: str) -> None:
    """Failure-branch policy for an UNKNOWN-PROBE-FAILED verdict. Never a silent pass."""
    if "LIVE PROBE FAILED" not in text:
        pytest.fail(
            f"{NOTE} records DECISION-VERDICT: UNKNOWN-PROBE-FAILED but no `LIVE PROBE FAILED` "
            f"reason — an unexplained UNKNOWN is not a recorded observation. Re-run run_p5b.py."
        )
    recorded = _recorded_failure_type(text)
    if recorded is None:
        pytest.fail(f"{NOTE} records LIVE PROBE FAILED with no parseable exception type.")
    if recorded not in NETWORK_EXCEPTIONS:
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED: {recorded} — a code/structural fault, not a "
            f"network outage, so an unreachable source does not excuse it. Re-run run_p5b.py."
        )
    boundary = _recorded_failure_boundary(text)
    if boundary is None:
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED with no parseable `LIVE PROBE FAILED-AT` "
            f"boundary (expected one of {BOUNDARIES}) — the skip gate cannot confirm which "
            f"host to probe, and an unattributed failure must not launder into a skip."
        )
    if _source_reachable():
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED ({recorded}) at boundary '{boundary}' while "
            f"www150.statcan.gc.ca answers — the probe is broken, not the source. "
            f"Re-run run_p5b.py."
        )
    pytest.skip(
        f"{NOTE} records a network-class failure ({recorded}) at boundary '{boundary}', "
        f"independently confirmed unreachable — the source is genuinely unpickable here, "
        f"NOT a pass. The temporary-resident-stock tripwire reports UNKNOWN per spec:473."
    )


def test_p5b_no_unfilled_placeholder():
    """Gate 1 — the committed note must never carry an unfilled `[FILL` slot.

    The plan's sketch emitted THREE (`- FILL: does 17100121 carry...`, `[FILL: NPR-stock |
    compo-net-flow | IRCC-TR-tables]`), which is the fabrication surface this probe family
    was hardened against: a placeholder is an invitation to hand-fill a generated note.
    """
    text = _note_text()
    assert "[FILL" not in text, (
        f"{NOTE} still contains an unresolved `[FILL` placeholder — the note must be GENERATED "
        f"by probes/run_p5b.py, never hand-filled. Re-run: uv run python probes/run_p5b.py"
    )


def test_p5b_records_pick_or_unknown():
    """Gate 2 — the RULING-2 outcome gate over the R6 vocabulary.

    Every evidence token is asserted INDEPENDENTLY: a LOCATED that resolved the product id
    but left the cadence, the geography level, the CMA answer or the measure type bare must
    FAIL here, not pass on the strength of the tokens that did resolve.
    """
    text = _note_text()
    verdict = _token(text, "DECISION-VERDICT")
    assert verdict in {"LOCATED", "UNKNOWN-PROBE-FAILED"}, (
        f"{NOTE} records no resolved `DECISION-VERDICT` (got {verdict!r}). It must be LOCATED "
        f"(with ALL evidence) or UNKNOWN-PROBE-FAILED (with a reason)."
    )

    if verdict == "UNKNOWN-PROBE-FAILED":
        _fail_or_skip_on_recorded_failure(text)  # -> fail (bad) or skip (confirmed outage)
        return

    # --- a LOCATED must carry EVERY evidence token ---------------------------------
    pid = _token(text, "DECISION-SOURCE-PID")
    assert pid is not None and pid.upper() not in UNRESOLVED and re.fullmatch(r"\d{8}", pid), (
        f"{NOTE} claims LOCATED but records no usable 8-digit `DECISION-SOURCE-PID` (got "
        f"{pid!r}). The pick must be the product id RESOLVED from the live sweep."
    )

    title = _token(text, "DECISION-SOURCE-TITLE")
    assert title is not None and title.upper() not in UNRESOLVED and len(title) >= 20, (
        f"{NOTE} claims LOCATED but records no usable `DECISION-SOURCE-TITLE` (got {title!r}); "
        f"it must be the cubeTitleEn read off the live response."
    )

    cadence = _token(text, "DECISION-CADENCE")
    assert cadence is not None and cadence.upper() not in UNRESOLVED, (
        f"{NOTE} claims LOCATED but records no `DECISION-CADENCE` (got {cadence!r})."
    )
    # Cadence must carry BOTH halves the spec asks for: the frequency AND the span it is
    # observed over. A bare "Quarterly" is a label with no evidence that anything was read.
    assert "frequencyCode" in cadence, (
        f"{NOTE}'s DECISION-CADENCE carries no frequencyCode provenance: {cadence!r}. The label "
        f"must be resolved from the live code set, not typed beside a raw integer."
    )
    assert re.search(r"\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}", cadence), (
        f"{NOTE}'s DECISION-CADENCE carries no reference-period span: {cadence!r}. Cadence "
        f"without the observed span cannot support a freshness limit (spec:473)."
    )

    geo = _token(text, "DECISION-GEO-LEVEL")
    assert geo is not None and geo.upper() not in UNRESOLVED, (
        f"{NOTE} claims LOCATED but records no `DECISION-GEO-LEVEL` (got {geo!r})."
    )
    assert re.search(r"\d+ members", geo), (
        f"{NOTE}'s DECISION-GEO-LEVEL states no geography MEMBER COUNT: {geo!r}. A level named "
        f"without a member count is a gloss, not a measurement."
    )

    cma = _token(text, "DECISION-CMA-AVAILABLE")
    assert cma in {"YES", "NO"}, (
        f"{NOTE} claims LOCATED but `DECISION-CMA-AVAILABLE` is unresolved ({cma!r}). It must "
        f"be the YES/NO computed by searching the geography members BY NAME."
    )

    measure = _token(text, "DECISION-MEASURE-TYPE")
    assert measure in {"STOCK", "FLOW", "AMBIGUOUS"}, (
        f"{NOTE} claims LOCATED but `DECISION-MEASURE-TYPE` is unresolved ({measure!r}). "
        f"spec:473 consumes a STOCK, so stock-vs-flow must be STATED, never elided."
    )

    currency = _token(text, "DECISION-CURRENCY")
    assert currency is not None and currency.upper() not in UNRESOLVED and len(currency) >= 10, (
        f"{NOTE} claims LOCATED but records no `DECISION-CURRENCY` (got {currency!r}) — whether "
        f"the source is maintained or archived is what makes it usable for a tripwire."
    )

    pick = _token(text, "DECISION-PICK")
    assert pick is not None and pick.upper() not in UNRESOLVED and pid in pick, (
        f"{NOTE} claims LOCATED but `DECISION-PICK` ({pick!r}) does not name the resolved "
        f"product id {pid!r} — spec §11.5b is 'pick one', so the PICK is the verdict."
    )

    # PICK-LIMIT is gated by its OWN rule, not against UNRESOLVED: R6 allows the literal
    # "none" as a real answer, so it must be accepted — while an empty or placeholder value
    # must still fail. A substantive limit must actually say something.
    limit = _token(text, "DECISION-PICK-LIMIT")
    assert limit is not None and limit.upper() not in UNRESOLVED, (
        f"{NOTE} claims LOCATED but records no `DECISION-PICK-LIMIT` (got {limit!r}). R6 "
        f"requires the limitation recorded as EVIDENCE, or an explicit 'none'."
    )
    assert limit.strip().lower() == "none" or len(limit) >= 30, (
        f"{NOTE}'s DECISION-PICK-LIMIT is neither an explicit 'none' nor a substantive "
        f"recorded limitation: {limit!r}."
    )
    # The limit and the CMA answer must AGREE. A `CMA-AVAILABLE: NO` beside a `PICK-LIMIT:
    # none` is the conditional-value-beside-unconditional-gloss shape this probe family
    # keeps reintroducing — caught here rather than read past.
    if cma == "NO":
        assert limit.strip().lower() != "none", (
            f"{NOTE} records DECISION-CMA-AVAILABLE: NO but DECISION-PICK-LIMIT: none — the "
            f"missing CMA axis IS a limitation and must be recorded as one (Ruling D)."
        )

    tripwire = _token(text, "DECISION-TRIPWIRE-STATUS")
    assert tripwire is not None and tripwire.upper().startswith("UNKNOWN"), (
        f"{NOTE} claims LOCATED but `DECISION-TRIPWIRE-STATUS` does not record the spec:473 "
        f"fallback firing (got {tripwire!r}). Until the source is wired the indicator reports "
        f"UNKNOWN, never a stale within-band."
    )


# ---------------------------------------------------------------------------
# Gate 3 — the floor guard is load-bearing (mutation test, runs OFFLINE).
# ---------------------------------------------------------------------------
def _load_run_p5b():
    """Import run_p5b.py as a fresh module (probes/ is not an importable package).

    The `sys.path` insert is load-bearing, not tidiness: run_p5b.py imports its shared
    machinery FLAT (`from _wds import …`) because probes/ is deliberately not a package and
    script mode resolves it via `sys.path[0]`. `spec_from_file_location` does NOT put the
    file's directory on the path, so without this `exec_module` dies
    `ModuleNotFoundError: No module named '_wds'`.
    """
    import importlib.util
    import sys

    probes_dir = str(NOTE.parent)
    if probes_dir not in sys.path:
        sys.path.insert(0, probes_dir)
    spec = importlib.util.spec_from_file_location("run_p5b_under_test",
                                                  NOTE.parent / "run_p5b.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PID = "17100121"

_FAKE_CODESETS = {"object": {"frequency": [{"frequencyCode": 9, "frequencyDescEn": "Quarterly"}]}}
_FAKE_CATALOGUE = [{
    "productId": int(PID),
    "cubeTitleEn": "Estimates of the number of non-permanent residents by type, quarterly",
    "frequencyCode": 9,
}]


def _fake_meta_object(*, dimension) -> dict:
    """A metadata object that is STRUCTURALLY COMPLETE except for its `dimension` list.

    This is the vacuous body that matters: everything the pick rule reads (title, cadence,
    span, archive status) is present and valid, so nothing raises on its own and the run
    sails through to publish a verdict. Only the geography evidence is missing — which is
    exactly what `_guard_pick` exists to refuse, and what the mutation below proves.
    """
    return {
        "productId": int(PID),
        "cubeTitleEn": "Estimates of the number of non-permanent residents by type, quarterly",
        "frequencyCode": 9,
        "cubeStartDate": "2021-07-01",
        "cubeEndDate": "2026-04-01",
        "archiveStatusEn": "CURRENT - a cube available to the public and that is current",
        "releaseTime": "2026-06-17T08:30",
        "nbSeriesCube": 154,
        "footnote": [{"footnotesEn": "Estimates of the number of non-permanent residents: "
                                     "Q1 = January 1; Q2 = April 1; Q3 = July 1; "
                                     "Q4 = October 1."}],
        "dimension": dimension,
    }


def _neutralise_non_gating(mod) -> None:
    """Silence the two NON-GATING comparisons so the mutation test runs fully offline.

    They cannot move the verdict by construction, but they DO reach the network and the
    filesystem; patching them keeps this gate hermetic and fast rather than dependent on
    CKAN being up.
    """
    mod._ckan_search = lambda: {"result": {"count": 0, "results": []}}
    mod._isq_rows = lambda: (_ for _ in ()).throw(FileNotFoundError("patched out"))


def test_p5b_floor_guard_earns_verdict(tmp_path):
    """Gate 3 — a LOCATED must be EARNED over a non-empty, plausibly-shaped response
    (NS #1). Four vacuous-but-200 responses that never RAISE on their own must each route
    to UNKNOWN-PROBE-FAILED at the right boundary; then NEUTERING `_guard_pick` must FLIP
    the empty-dimension case into a FABRICATED LOCATED — proving that guard is what keeps
    the verdict honest.

    Which guard each scenario proves, stated honestly (p5's pattern):
      * `_guard_pick` is SAFETY-load-bearing — neutered, the run publishes LOCATED over a
        cube with zero geography members, `CMA-AVAILABLE: NO` computed from an empty list
        and a cadence resolved for a code the run never verified. That is the mutation.
      * `_guard_codesets` is ALSO safety-load-bearing on the cadence axis: neutered, an
        empty code set yields `DECISION-CADENCE: (frequencyCode 9 …)` with an EMPTY label.
      * `_guard_sweep` is MESSAGE-QUALITY only: neutered, the empty-catalogue case still
        reaches the `eligible_current` emptiness check and raises there, so safety holds
        without it; it exists to attribute the failure to the `wds-list` boundary rather
        than surfacing as a misleading downstream error.

    Runs OFFLINE — every boundary is patched; the committed note is untouched.
    """
    scenarios = {
        "empty code set (200, no frequency codes)": (
            lambda: {"object": {"frequency": []}}, None, None, "wds-codesets",
        ),
        "empty catalogue (200, zero cubes)": (
            lambda: _FAKE_CODESETS, lambda: [], None, "wds-list",
        ),
        "catalogue with zero matching titles": (
            lambda: _FAKE_CODESETS,
            lambda: [{"productId": 12345678, "cubeTitleEn": "Sales of fluid milk products"}],
            None, "wds-list",
        ),
        "pick metadata with an EMPTY dimension list": (
            lambda: _FAKE_CODESETS, lambda: _FAKE_CATALOGUE,
            lambda pids: {PID: _fake_meta_object(dimension=[])}, "wds-meta",
        ),
        "pick geography dimension with ZERO members": (
            lambda: _FAKE_CODESETS, lambda: _FAKE_CATALOGUE,
            lambda pids: {PID: _fake_meta_object(
                dimension=[{"dimensionPositionId": 1, "dimensionNameEn": "Geography",
                            "member": []}])},
            "wds-meta",
        ),
    }
    for label, (codesets, catalogue, meta, boundary) in scenarios.items():
        mod = _load_run_p5b()
        mod.OUT = tmp_path / f"note_{abs(hash(label))}.md"
        _neutralise_non_gating(mod)
        mod._codesets = codesets
        if catalogue is not None:
            mod._catalogue = catalogue
        if meta is not None:
            mod._meta = meta
        mod.main()
        text = mod.OUT.read_text(encoding="utf-8")
        assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED", (
            f"[{label}] a vacuous 200 was laundered into a verdict other than UNKNOWN — the "
            f"floor guard did not fire. A LOCATED must be EARNED (NS #1)."
        )
        assert _recorded_failure_boundary(text) == boundary, (
            f"[{label}] the failure must be attributed to boundary '{boundary}', got "
            f"{_recorded_failure_boundary(text)!r} — the skip gate needs the right host."
        )

    # MUTATION: neuter `_guard_pick` on the empty-dimension case. The run must now publish a
    # FABRICATED LOCATED — a pick whose geography evidence is an empty list. If this does NOT
    # flip, the guard is not what keeps the verdict honest and the loop above proves nothing.
    mod = _load_run_p5b()
    mod.OUT = tmp_path / "note_neutered.md"
    _neutralise_non_gating(mod)
    mod._codesets = lambda: _FAKE_CODESETS
    mod._catalogue = lambda: _FAKE_CATALOGUE
    mod._meta = lambda pids: {PID: _fake_meta_object(dimension=[])}
    mod._guard_pick = lambda pid, obj, geo_dim, members, freq_map: None  # neutered
    mod.main()
    neutered = mod.OUT.read_text(encoding="utf-8")
    assert _token(neutered, "DECISION-VERDICT") == "LOCATED", (
        "neutering `_guard_pick` did NOT flip the empty-dimension case into a fabricated "
        "LOCATED — the guard is then not the thing keeping the verdict honest, so the gate "
        "above proves nothing. The floor guard must be load-bearing."
    )
    # And the fabrication is exactly what the guard exists to stop: a geography answer
    # computed over zero members, published as if it were measured.
    assert "0 members" in (_token(neutered, "DECISION-GEO-LEVEL") or ""), (
        "the neutered run must publish a geography level over ZERO members — that is the "
        "fabricated claim `_guard_pick` refuses."
    )


def test_p5b_records_tripwire_framing():
    """Gate 4 — the spec framing strings. ADDITIVE and explicitly NON-JUDGING.

    Every string asserted here is written UNCONDITIONALLY by run_p5b.py on at least one
    branch, so this gate CANNOT fail on a bad outcome and judges nothing about the run. It
    pins the spec's intent (the STOCK discriminator and the UNKNOWN tripwire fallback) so a
    later edit cannot quietly drop the framing. Gates 1-3 are what judge the run.
    """
    text = _note_text()
    low = text.lower()
    assert "tripwire" in low
    assert "stock" in low
    assert "unknown" in low
    assert ("located" in low) or ("unknown-probe-failed" in low)
