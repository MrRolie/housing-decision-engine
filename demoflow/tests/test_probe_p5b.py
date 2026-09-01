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

from ._prose_binding import says
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
    assert verdict in {"LOCATED", "LOCATED-NOT-STOCK", "UNKNOWN-PROBE-FAILED"}, (
        f"{NOTE} records no resolved `DECISION-VERDICT` (got {verdict!r}). It must be LOCATED "
        f"(with ALL evidence), LOCATED-NOT-STOCK (a real source whose measure type is not a "
        f"stock), or UNKNOWN-PROBE-FAILED (with a reason)."
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
    assert re.search(r"[1-9]\d* members", geo), (
        f"{NOTE}'s DECISION-GEO-LEVEL states no NON-ZERO geography MEMBER COUNT: {geo!r}. A "
        f"level named without a member count is a gloss; '0 members' is the fabrication "
        f"signature the floor-guard mutation asserts on, so it must not pass here either."
    )

    cma = _token(text, "DECISION-CMA-AVAILABLE")
    assert cma in {"YES", "NO"}, (
        f"{NOTE} claims LOCATED but `DECISION-CMA-AVAILABLE` is unresolved ({cma!r}). It must "
        f"be the YES/NO computed by searching the geography members BY NAME."
    )

    measure = _token(text, "DECISION-MEASURE-TYPE")
    assert measure in {"STOCK", "FLOW", "AMBIGUOUS"}, (
        f"{NOTE} claims a located source but `DECISION-MEASURE-TYPE` is unresolved "
        f"({measure!r}). spec:473 consumes a STOCK, so stock-vs-flow must be STATED."
    )
    # The DISCRIMINATOR, enforced rather than displayed: a plain LOCATED asserts the pick is
    # the stock source spec:473 consumes, so it must actually compute as STOCK. A non-stock
    # pick is a real finding and gets its own token — but it must NOT ride in under LOCATED.
    if verdict == "LOCATED":
        assert measure == "STOCK", (
            f"{NOTE} records DECISION-VERDICT: LOCATED with DECISION-MEASURE-TYPE: {measure!r}. "
            f"spec:473 consumes a STOCK; a pick that does not compute as one must be published "
            f"as LOCATED-NOT-STOCK, never laundered through the plain LOCATED token."
        )
    else:
        assert measure != "STOCK", (
            f"{NOTE} records DECISION-VERDICT: LOCATED-NOT-STOCK while the measure type IS "
            f"STOCK — the verdict contradicts its own evidence."
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
POP_TITLE = "Estimates of the number of non-permanent residents by type, quarterly"

_FAKE_CODESETS = {"object": {"frequency": [{"frequencyCode": 9, "frequencyDescEn": "Quarterly"}]}}
_FAKE_CATALOGUE = [{"productId": int(PID), "cubeTitleEn": POP_TITLE, "frequencyCode": 9}]


_GEO_DIM = [{"dimensionPositionId": 1, "dimensionNameEn": "Geography",
             "member": [{"memberNameEn": "Canada"}, {"memberNameEn": "Quebec"}]}]


def _fake_meta_object(*, dimension, pid: str = PID, title: str | None = None,
                      end: str = "2026-04-01",
                      archive: str = "CURRENT - a cube available to the public and that is "
                                     "current") -> dict:
    """A metadata object that is STRUCTURALLY COMPLETE except for its `dimension` list.

    This is the vacuous body that matters: everything the pick rule reads (title, cadence,
    span, archive status) is present and valid, so nothing raises on its own and the run
    sails through to publish a verdict. Only the geography evidence is missing — which is
    exactly what `_guard_pick` exists to refuse, and what the mutation below proves.
    """
    return {
        "productId": int(pid),
        "cubeTitleEn": title or POP_TITLE,
        "frequencyCode": 9,
        "cubeStartDate": "2021-07-01",
        "cubeEndDate": end,
        "archiveStatusEn": archive,
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
    (NS #1). Seven vacuous-but-200 responses that never RAISE on their own must each route
    to UNKNOWN-PROBE-FAILED at the right boundary; then NEUTERING `_guard_pick` must FLIP
    the empty-dimension case into a FABRICATED LOCATED — proving that guard is what keeps
    the verdict honest.

    Which guard each scenario proves, stated honestly (p5's pattern):
      * `_guard_pick` is the ONLY SAFETY-load-bearing guard here — neutered, the run
        publishes LOCATED over a cube with zero geography members, `CMA-AVAILABLE: NO`
        computed from an empty list. That is the mutation at the end of this test.
      * `_guard_codesets` is ATTRIBUTION-ONLY, and structurally cannot be otherwise: it
        fires only when `freq_map` is EMPTY, and an empty map makes `_guard_pick`'s
        `code not in freq_map` True for EVERY code. Neutering it therefore leaves the
        verdict UNKNOWN and moves only `FAILED-AT` (verified: wds-codesets -> wds-meta,
        both scenarios). An earlier version of this docstring called it "ALSO safety-load-
        bearing on the cadence axis" — that was wrong, and a wrong self-grade propagates
        into every risk list that reads it. This file grades `_guard_sweep` honestly
        below, so the standard was set here and missed one guard over.
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
        # The proven false-green, in BOTH of its real shapes. A code set that DEFINES the
        # pick's code but gives it no description used to pass `_guard_codesets` (map
        # non-empty) AND `_guard_pick` (`code in freq_map`), publishing a LOCATED whose
        # cadence label was the empty string — the exact claim `_guard_codesets`'s docstring
        # says it prevents. Dropping label-less codes from the map closes it, and WHICH
        # guard catches it depends on whether any labelled code survives:
        #   (a) the label-less code is the ONLY one -> map empties -> `wds-codesets`;
        #   (b) other codes are labelled -> map non-empty, so `_guard_codesets` passes and
        #       `_guard_pick`'s `code not in freq_map` is the one that must catch it.
        # (b) is the reviewer's exact repro shape; without it, only (a) would be covered and
        # the guard that actually does the work here would go untested.
        "(a) code set whose ONLY code has no description": (
            lambda: {"object": {"frequency": [{"frequencyCode": 9}]}},
            lambda: _FAKE_CATALOGUE,
            lambda pids: {PID: _fake_meta_object(dimension=_GEO_DIM)},
            "wds-codesets",
        ),
        "(b) code set where OTHER codes are labelled but the pick's code 9 is not": (
            lambda: {"object": {"frequency": [{"frequencyCode": 12,
                                               "frequencyDescEn": "Annual"},
                                              {"frequencyCode": 9, "frequencyDescEn": "  "}]}},
            lambda: _FAKE_CATALOGUE,
            lambda pids: {PID: _fake_meta_object(dimension=_GEO_DIM)},
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


def test_p5b_non_stock_pick_gets_its_own_verdict(tmp_path):
    """Gate 5 — the STOCK discriminator is ENFORCED, not displayed (runs OFFLINE).

    The committed note computes STOCK, so nothing in the green path ever reaches the
    non-stock branch — which is exactly how a discriminator becomes decoration. This drives
    a pick whose markers compute FLOW and asserts the verdict token changes.

    Deliberately NOT routed through `VacuousProbeError`: every boundary answered correctly
    here, so recording a boundary failure would put a false statement in a generated note.
    The limit is in the ANSWER, and R6's vocabulary exists to say so.
    """
    flow_title = ("Solde: net migration of non-permanent residents, quarterly")
    mod = _load_run_p5b()
    mod.OUT = tmp_path / "note_flow.md"
    _neutralise_non_gating(mod)
    mod._codesets = lambda: _FAKE_CODESETS
    mod._catalogue = lambda: [{"productId": int(PID), "cubeTitleEn": flow_title,
                               "frequencyCode": 9}]
    obj = _fake_meta_object(dimension=_GEO_DIM)
    obj["cubeTitleEn"] = flow_title
    obj["footnote"] = []  # no point-in-time footnote, so nothing argues for a level
    mod._meta = lambda pids: {PID: obj}
    mod.main()
    text = mod.OUT.read_text(encoding="utf-8")

    assert _token(text, "DECISION-MEASURE-TYPE") == "FLOW", (
        "the fixture must actually compute FLOW, or this gate proves nothing about the "
        f"discriminator: got {_token(text, 'DECISION-MEASURE-TYPE')!r}"
    )
    assert _token(text, "DECISION-VERDICT") == "LOCATED-NOT-STOCK", (
        "a pick whose measure type computes FLOW was published under a verdict other than "
        "LOCATED-NOT-STOCK. spec:473 consumes a STOCK, so the discriminator must GATE the "
        "verdict — otherwise it is prose beside a value it cannot affect."
    )
    # And the level-vs-movement gloss must NOT appear: it is the sentence that would make
    # the note assert a stock while the token says otherwise.
    # `says` here and at the second fixture below (run 48): the gloss is prose the probe
    # writes, and "NOT A MOVEMENT" is the same contradiction in this corpus's emphasis style.
    assert not says(text, "not a movement"), (
        "the note asserted the value is a level while its own measure type computed FLOW — "
        "a gloss contradicting the token beside it."
    )

    # SECOND fixture — the one that actually reaches the gloss. Above, no point-in-time
    # footnote exists, so the gloss branch is never entered and un-conditioning it would go
    # UNCAUGHT (verified: that mutation survived until this case was added). Here the
    # footnote IS found while flow markers are ALSO present, so the measure computes
    # AMBIGUOUS and the gloss branch is reached with a non-STOCK token beside it.
    mod2 = _load_run_p5b()
    mod2.OUT = tmp_path / "note_ambiguous.md"
    _neutralise_non_gating(mod2)
    mod2._codesets = lambda: _FAKE_CODESETS
    mod2._catalogue = lambda: [{"productId": int(PID), "cubeTitleEn": flow_title,
                                "frequencyCode": 9}]
    obj2 = _fake_meta_object(dimension=_GEO_DIM)   # keeps the "Q1 = January 1; …" footnote
    obj2["cubeTitleEn"] = flow_title
    mod2._meta = lambda pids: {PID: obj2}
    mod2.main()
    text2 = mod2.OUT.read_text(encoding="utf-8")

    assert _token(text2, "DECISION-MEASURE-TYPE") == "AMBIGUOUS", (
        "the fixture must compute AMBIGUOUS (point-in-time footnote AND flow markers), or it "
        f"does not reach the gloss: got {_token(text2, 'DECISION-MEASURE-TYPE')!r}"
    )
    assert "Q1 = January 1" in text2, "the fixture must actually surface the point-in-time quote"
    assert _token(text2, "DECISION-VERDICT") == "LOCATED-NOT-STOCK"
    assert not says(text2, "not a movement"), (
        "the note quoted a point-in-time footnote and concluded the value is a level while its "
        "own measure type computed AMBIGUOUS — the gloss must be conditioned on the MEASURE, "
        "not merely on the footnote being found."
    )


def test_p5b_pick_rule_discriminators_are_load_bearing(tmp_path):
    """Gate 6 — ELIGIBILITY and CURRENCY actually DECIDE the pick (runs OFFLINE).

    Both are claimed load-bearing by run_p5b.py's own comments ("the eligibility filter runs
    FIRST so the freshness ranking cannot be hijacked by a cube that is not a temporary-
    resident population source at all") and both were UNPINNED: dropping `eligible` published
    an agriculture temporary-foreign-worker cube as the temporary-resident STOCK source under
    a plain LOCATED, whole suite green.

    Why no earlier test caught it: the LIVE pick happens to hold the latest `cubeEndDate`, so
    neither discriminator changes today's outcome and both mutants are invisible. This
    fixture inverts that — it makes the NON-eligible and the NON-current cubes the FRESHEST
    in the catalogue, so a pick rule that skips either filter must pick the wrong cube.
    """
    peripheral_pid, archived_pid = "32100220", "17100023"
    cat = [
        {"productId": int(PID), "cubeTitleEn": POP_TITLE, "frequencyCode": 9},
        # NOT eligible (peripheral term only) and FRESHER than the population cube.
        {"productId": int(peripheral_pid), "frequencyCode": 12,
         "cubeTitleEn": "Temporary foreign workers in the agriculture sector, by category of "
                        "farm revenue"},
        # Eligible but ARCHIVED, and the freshest of all.
        {"productId": int(archived_pid), "frequencyCode": 9,
         "cubeTitleEn": "Estimates of non-permanent residents, quarterly, inactive"},
    ]
    meta = {
        PID: _fake_meta_object(dimension=_GEO_DIM, end="2026-04-01"),
        peripheral_pid: _fake_meta_object(
            dimension=_GEO_DIM, pid=peripheral_pid, end="2027-01-01",
            title="Temporary foreign workers in the agriculture sector, by category of farm "
                  "revenue"),
        archived_pid: _fake_meta_object(
            dimension=_GEO_DIM, pid=archived_pid, end="2028-01-01",
            title="Estimates of non-permanent residents, quarterly, inactive",
            archive="ARCHIVED -  a cube publicly available but no longer being updated"),
    }

    mod = _load_run_p5b()
    mod.OUT = tmp_path / "note_pickrule.md"
    _neutralise_non_gating(mod)
    mod._codesets = lambda: _FAKE_CODESETS
    mod._catalogue = lambda: cat
    mod._meta = lambda pids: meta
    mod.main()
    text = mod.OUT.read_text(encoding="utf-8")

    # Guard against a vacuous fixture: the decoys must really be the fresher ones, or this
    # gate proves nothing about either discriminator.
    assert meta[peripheral_pid]["cubeEndDate"] > meta[PID]["cubeEndDate"]
    assert meta[archived_pid]["cubeEndDate"] > meta[peripheral_pid]["cubeEndDate"]

    assert _token(text, "DECISION-SOURCE-PID") == PID, (
        f"the pick rule chose {_token(text, 'DECISION-SOURCE-PID')!r} over the eligible, "
        f"current cube {PID}. A cube that is not a temporary-resident population source "
        f"({peripheral_pid}, agriculture TFW) or is ARCHIVED ({archived_pid}) must never win "
        f"the freshness ranking — the eligibility and currency filters run FIRST precisely so "
        f"the ranking cannot be hijacked."
    )
    assert _token(text, "DECISION-VERDICT") == "LOCATED"


def test_p5b_declared_province_must_be_corroborated(tmp_path):
    """Gate 7 — the DECLARED containing province is falsifiable (runs OFFLINE).

    Declaring `MODELED_CMA_PROVINCE` made the containment claim honest about its provenance
    but left it unfalsifiable: flipping it to "Ontario" republished a false geography claim
    with the whole suite green, because a member named "Ontario" exists in the response too.
    The independent witness is the province abbreviation in each CMA member's OWN live name
    ("Montréal (CMA), Que."), which no declaration in this file controls.
    """
    bearer = "98100361"
    cma_dim = [{"dimensionPositionId": 1, "dimensionNameEn": "Geography", "member": [
        {"memberNameEn": "Canada"}, {"memberNameEn": "Quebec"}, {"memberNameEn": "Ontario"},
        {"memberNameEn": "Montréal (CMA), Que."}, {"memberNameEn": "Québec (CMA), Que."},
    ]}]
    cat = [
        {"productId": int(PID), "cubeTitleEn": POP_TITLE, "frequencyCode": 9},
        {"productId": int(bearer), "frequencyCode": 18,
         "cubeTitleEn": "Non-permanent resident type by place of birth: Canada, provinces and "
                        "territories, census metropolitan areas"},
    ]
    meta = {
        PID: _fake_meta_object(dimension=_GEO_DIM, end="2026-04-01"),
        bearer: _fake_meta_object(
            dimension=cma_dim, pid=bearer, end="2021-01-01",
            title="Non-permanent resident type by place of birth: Canada, provinces and "
                  "territories, census metropolitan areas"),
    }
    mod = _load_run_p5b()
    mod.OUT = tmp_path / "note_province.md"
    _neutralise_non_gating(mod)
    mod._codesets = lambda: _FAKE_CODESETS
    mod._catalogue = lambda: cat
    mod._meta = lambda pids: meta
    mod.main()
    text = mod.OUT.read_text(encoding="utf-8")

    # Fixture guard: the bearer must actually have been recognised, or there is nothing to
    # corroborate and this gate would pass vacuously.
    assert "Declared-province corroboration" in text, (
        "the fixture did not produce a CMA-bearing cube, so the corroboration never ran"
    )
    assert "NOT CORROBORATED" not in text, (
        "the declared containing province disagrees with the province abbreviation in the CMA "
        "members' own live names — the note would publish a false containment claim."
    )
    assert "NOT CHECKABLE" not in text, (
        "no CMA member carried a province suffix, so the declaration was not actually checked "
        "— an unchecked declaration must not read as a corroborated one."
    )
    assert text.count("CORROBORATED") >= len(mod.MODELED_CMAS), (
        "every modeled CMA must have its declared province corroborated, not just one"
    )

    # The FAILURE behaviour is what proves the check works (NS #1: the live run's failure,
    # not its pass, is the teacher). Without this half, `_province_corroborated -> True` and
    # deleting its call site BOTH survive — verified: the positive assertions above hold
    # under either mutation, because a check that always says CORROBORATED never says NOT.
    mod2 = _load_run_p5b()
    mod2.OUT = tmp_path / "note_province_wrong.md"
    _neutralise_non_gating(mod2)
    mod2._codesets = lambda: _FAKE_CODESETS
    mod2._catalogue = lambda: cat
    mod2._meta = lambda pids: meta
    mod2.MODELED_CMA_PROVINCE = {k: "Ontario" for k in mod2.MODELED_CMAS}
    mod2.main()
    wrong = mod2.OUT.read_text(encoding="utf-8")
    assert "NOT CORROBORATED" in wrong, (
        "a DELIBERATELY WRONG declared province ('Ontario' for Québec CMAs, whose live member "
        "names carry ', Que.') was still reported as corroborated. The check cannot detect a "
        "false declaration, so the corroboration above proves nothing."
    )


def _abbrev_missed_count(text: str) -> int:
    """The count the note STATES for npr-titles absent from the swept set."""
    found = re.search(r"of which \*\*(\d+)\*\* are ABSENT from the swept set", text)
    assert found, "the note states no abbreviation-cross-check missed-count"
    return int(found.group(1))


def test_p5b_abbreviation_check_measures_what_it_concludes(tmp_path):
    """Gate 8 — the abbreviation cross-check counts the set that BEARS on its conclusion.

    The original counted npr-titles that ALSO matched a population phrase — i.e. the ones the
    phrase predicate had ALREADY caught — then concluded from a zero that nothing was missed.
    That inference is inverted: the set that could be missed is the COMPLEMENT. Both branches
    stated the opposite of what the number meant, and no test looked at this section at all.

    Two fixtures, one per direction (the audit's):
      * a cube the phrase predicate genuinely MISSES must be counted as missed;
      * a cube the phrase predicate CATCHES must not be.
    """
    def run(dest, extra_cat, extra_meta):
        mod = _load_run_p5b()
        mod.OUT = tmp_path / dest
        _neutralise_non_gating(mod)
        mod._codesets = lambda: _FAKE_CODESETS
        mod._catalogue = lambda: [
            {"productId": int(PID), "cubeTitleEn": POP_TITLE, "frequencyCode": 9}, extra_cat]
        mod._meta = lambda pids: {PID: _fake_meta_object(dimension=_GEO_DIM), **extra_meta}
        mod.main()
        return mod.OUT.read_text(encoding="utf-8")

    # (a) MISSED: matches "npr" but no population/peripheral phrase -> never swept.
    missed_title = "Estimates of NPR stock by province, quarterly"
    a = run("note_abbrev_missed.md",
            {"productId": 17109999, "cubeTitleEn": missed_title, "frequencyCode": 9}, {})
    assert _abbrev_missed_count(a) == 1, (
        f"a cube titled {missed_title!r} is matched by the bare abbreviation and swept by NO "
        f"phrase, so it IS a title the phrase predicate misses — the note counted "
        f"{_abbrev_missed_count(a)}. Counting the cubes the predicate already caught cannot "
        f"support a claim about the ones it missed."
    )
    assert "| `17109999` |" in a and "| NO |" in a, (
        "the missed cube must appear in the emitted table marked as NOT swept, so a reader "
        "can check the count rather than take it"
    )

    # (b) CAUGHT: matches "npr" AND a population phrase -> swept, so NOT missed.
    caught_title = "Estimates of non-permanent residents (NPR), monthly"
    b = run("note_abbrev_caught.md",
            {"productId": 17108888, "cubeTitleEn": caught_title, "frequencyCode": 9},
            {"17108888": _fake_meta_object(dimension=_GEO_DIM, pid="17108888",
                                           title=caught_title, end="2020-01-01")})
    assert _abbrev_missed_count(b) == 0, (
        f"a cube titled {caught_title!r} IS swept by the phrase predicate, so it is not a "
        f"title the abbreviation adds — the note counted {_abbrev_missed_count(b)}."
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
