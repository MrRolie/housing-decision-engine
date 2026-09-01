"""P5 gates — does the committed note LOCATE the IRCC PR-by-CMA source, or honestly
record UNKNOWN?

The plan's version asserted `("VERDICT: located" in text) or ("LIVE SEARCH FAILED" in
text)`. run_p5.py writes exactly one of those markers UNCONDITIONALLY, so that
disjunction can never be False — it passes on a run that resolved everything AND on a
run that fabricated everything. A gate that cannot fail is not a gate. The gates below
assert the OUTCOME (RULING-2):

  PASS iff the note records EITHER
    (a) LOCATED with a resolved package id AND a CSV url AND an observed column schema
        (the tripwire's real source), OR
    (b) UNKNOWN-PROBE-FAILED with a recorded reason (the spec §7 tripwire fallback).
  FAIL on an unresolved `[FILL`, a LOCATED missing any evidence, or neither.
  SKIP-with-reason ONLY if a search was attempted and the source is independently
    confirmed unreachable — and only when the RECORDED exception TYPE is network-class
    (a code fault must not launder into a skip) AND the recorded BOUNDARY (ckan|csv) is
    the host actually probed for reachability (point B: two boundaries, so the liveness
    check must match the one that failed — P3's "must match the endpoint" lesson).

  The green path is OFFLINE — it reads the committed note. Only the failure branch
  probes reachability, and only to decide fail-vs-skip.

  test_p5_no_unfilled_placeholder      -> the fabrication surface stays closed
  test_p5_records_located_or_unknown   -> the load-bearing RULING-2 gate
  test_p5_floor_guard_earns_verdict    -> the floor guard is load-bearing (mutation test)
  test_p5_records_tripwire_framing     -> the plan's content strings (additive)
"""

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

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P5-ircc-pr-by-cma.md"

# Documented endpoints the probe actually hits — the reachability targets, one per
# boundary. Both are GET (matching the probe's GET method; a mismatched method would
# report a healthy host as unreachable and launder every failure into a skip).
CKAN_LIVENESS = "https://open.canada.ca/data/api/3/action/package_search?rows=0"
CSV_LIVENESS = "https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_CMA.csv"
REACHABILITY_TIMEOUT = 15

UNRESOLVED = {"", "UNKNOWN-PROBE-FAILED", "UNRESOLVED-PROBE-FAILED", "TBD",
              "FILL", "[FILL]", "N/A", "NONE", "NOT-FOUND", "?"}


def _note_text() -> str:
    assert NOTE.exists(), f"{NOTE} is missing — run `uv run python probes/run_p5.py` first"
    return NOTE.read_text(encoding="utf-8")


def _recorded_failure_boundary(text: str) -> str | None:
    found = re.search(r"LIVE PROBE FAILED-AT:\s*(ckan|csv)", text)
    return found.group(1) if found else None


def _source_reachable(boundary: str) -> bool:
    """Cheap GET liveness probe against the boundary that was RECORDED as failing.

    Point B: with two boundaries, probing the wrong host would FAIL a genuine outage
    as 'the probe is broken'. A tiny Range keeps the CSV check from downloading 1.7MB;
    a server that ignores it answers 200, one that honors it answers 206 — both live.
    Any exception means unreachable.
    """
    return source_reachable(
        CSV_LIVENESS if boundary == "csv" else CKAN_LIVENESS,
        timeout=REACHABILITY_TIMEOUT,
        method="GET",
        headers={"Range": "bytes=0-1024"},
        ok_statuses=(200, 206),
    )


def _fail_or_skip_on_recorded_failure(text: str) -> None:
    """Failure-branch policy for an UNKNOWN-PROBE-FAILED verdict. Never a silent pass."""
    if "LIVE PROBE FAILED" not in text:
        pytest.fail(
            f"{NOTE} records DECISION-VERDICT: UNKNOWN-PROBE-FAILED but no `LIVE PROBE FAILED` "
            f"reason — an unexplained UNKNOWN is not a recorded observation. Re-run run_p5.py."
        )
    recorded = _recorded_failure_type(text)
    if recorded is None:
        pytest.fail(f"{NOTE} records LIVE PROBE FAILED with no parseable exception type.")
    if recorded not in NETWORK_EXCEPTIONS:
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED: {recorded} — a code/structural fault, not a "
            f"network outage, so an unreachable source does not excuse it. Re-run run_p5.py."
        )
    boundary = _recorded_failure_boundary(text) or "ckan"
    if _source_reachable(boundary):
        host = "ircc.canada.ca" if boundary == "csv" else "open.canada.ca"
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED ({recorded}) at boundary '{boundary}' while "
            f"{host} answers — the probe is broken, not the source. Re-run run_p5.py."
        )
    pytest.skip(
        f"{NOTE} records a network-class failure ({recorded}) at boundary '{boundary}', "
        f"independently confirmed unreachable — the schema is genuinely unrecordable here, "
        f"NOT a pass. The PR-landings tripwire reports UNKNOWN per spec §7."
    )


def test_p5_no_unfilled_placeholder():
    """Gate 1 — the committed note must never carry an unfilled `[FILL` slot: the
    fabrication surface this probe family was hardened against."""
    text = _note_text()
    assert "[FILL" not in text, (
        f"{NOTE} still contains an unresolved `[FILL` placeholder — the note must be GENERATED "
        f"by probes/run_p5.py, never hand-filled. Re-run: uv run python probes/run_p5.py"
    )


def test_p5_records_located_or_unknown():
    """Gate 2 — the RULING-2 outcome gate: LOCATED-with-evidence OR UNKNOWN-with-reason."""
    text = _note_text()
    verdict = _token(text, "DECISION-VERDICT")
    assert verdict in {"LOCATED", "UNKNOWN-PROBE-FAILED"}, (
        f"{NOTE} records no resolved `DECISION-VERDICT` (got {verdict!r}). It must be LOCATED "
        f"(with evidence) or UNKNOWN-PROBE-FAILED (with a reason)."
    )

    if verdict == "UNKNOWN-PROBE-FAILED":
        _fail_or_skip_on_recorded_failure(text)  # -> fail (bad) or skip (confirmed outage)
        return

    # --- LOCATED must carry ALL THREE evidence pieces (a bare token is rejected) ---
    pkg = _token(text, "DECISION-PACKAGE-ID")
    assert pkg is not None and pkg.upper() not in UNRESOLVED and len(pkg) >= 8, (
        f"{NOTE} claims LOCATED but records no usable `DECISION-PACKAGE-ID` (got {pkg!r}). A "
        f"located verdict must carry the package id resolved from the live search."
    )

    url = _token(text, "DECISION-CSV-URL")
    assert url is not None and url.lower().startswith("http") and ".csv" in url.lower(), (
        f"{NOTE} claims LOCATED but records no usable `DECISION-CSV-URL` (got {url!r}). A "
        f"located verdict must carry the actual CSV resource url the tripwire reads."
    )

    cols = _token(text, "DECISION-COLUMNS")
    assert cols is not None and cols.upper() not in UNRESOLVED and "|" in cols, (
        f"{NOTE} claims LOCATED but records no multi-column `DECISION-COLUMNS` schema "
        f"(got {cols!r}). The column list must be the observed header, not a bare token."
    )
    # The observed schema must actually be the CMA×TOTAL table — the two columns the
    # tripwire depends on. This rejects a 200-but-wrong-body 'schema' from greening the gate.
    assert "TOTAL" in cols.upper(), (
        f"{NOTE}'s DECISION-COLUMNS has no TOTAL column — not the PR-admissions table: {cols!r}"
    )
    assert ("METROPOLITAN" in cols.upper()) or ("CMA" in cols.upper()), (
        f"{NOTE}'s DECISION-COLUMNS has no CMA/metropolitan column: {cols!r}"
    )

    found = _token(text, "DECISION-FOUND-AT-CMA")
    assert found in {"YES", "NO"}, (
        f"{NOTE} claims LOCATED but `DECISION-FOUND-AT-CMA` is unresolved ({found!r})."
    )


# ---------------------------------------------------------------------------
# Gate 3 — the floor guard is load-bearing (mutation test, runs OFFLINE).
# ---------------------------------------------------------------------------
def _load_run_p5():
    """Import run_p5.py as a fresh module (probes/ is not an importable package).

    The `sys.path` insert is load-bearing, not tidiness: run_p5.py imports its shared
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
    spec = importlib.util.spec_from_file_location("run_p5_under_test", NOTE.parent / "run_p5.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_search(csv_url: str = "https://x.example/y.csv") -> dict:
    """A minimal but VALID CKAN search response resolving one IRCC monthly package with
    a CMA CSV resource — so the run reaches the CSV boundary under test."""
    return {
        "success": True,
        "result": {
            "count": 1,
            "results": [{
                "id": "pkg-under-test",
                "name": "pkg-under-test",
                "title": "Permanent Residents – Monthly IRCC Updates",
                "organization": {"title": "Immigration, Refugees and Citizenship Canada"},
                "notes": 'Values between 0 and 5 are shown as "--" and all other values are '
                         "rounded to the nearest multiple of 5.",
                "resources": [{
                    "name": "Canada - Permanent Residents by Province/Territory and CMA",
                    "format": "CSV", "url": csv_url, "id": "res-under-test",
                }],
            }],
        },
    }


def test_p5_floor_guard_earns_verdict(tmp_path):
    """Gate 3 — a LOCATED must be EARNED over a non-empty, plausibly-shaped response
    (NS #1). Three vacuous/wrong-body responses that never RAISE on their own must each
    route to UNKNOWN-PROBE-FAILED, and neutering the CSV-shape guard must FLIP the
    header-only case into a fabricated LOCATED (proving THAT guard is load-bearing).

    Note which guard each scenario proves: `_guard_csv_shape` is safety-load-bearing —
    neutering it fabricates a LOCATED (the mutation below). `_guard_search` is
    message-quality only: neutered, the empty-search case falls to `chosen[0]` ->
    IndexError -> still UNKNOWN (and IndexError is outside NETWORK_EXCEPTIONS, so the
    gate FAILs rather than skips), so safety holds without it; it exists to attribute
    the failure cleanly to the ckan boundary rather than as a bare IndexError.

    Runs OFFLINE — both boundaries are patched; the committed note is untouched.
    """
    HTML = "<!DOCTYPE html>\n<html><body>503 Service Unavailable</body></html>"
    HEADER_ONLY = "EN_CENSUS_METROPOLITAN_AREA\tEN_PROVINCE_TERRITORY\tTOTAL\n"

    scenarios = {
        # (patch_search, patch_fetch, expected_boundary)
        "empty search (count 0)": (
            lambda: {"success": True, "result": {"count": 0, "results": []}},
            None, "ckan",
        ),
        "200-but-wrong-body CSV (HTML error page)": (
            lambda: _fake_search(), lambda url: HTML, "csv",
        ),
        "header-only CSV (zero data rows)": (
            lambda: _fake_search(), lambda url: HEADER_ONLY, "csv",
        ),
    }
    for label, (patch_search, patch_fetch, boundary) in scenarios.items():
        mod = _load_run_p5()
        mod.OUT = tmp_path / f"note_{boundary}.md"
        mod._search = patch_search
        if patch_fetch is not None:
            mod._fetch_csv = patch_fetch
        mod.main()
        text = mod.OUT.read_text(encoding="utf-8")
        assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED", (
            f"[{label}] a vacuous/wrong-body response was laundered into a verdict other than "
            f"UNKNOWN — the floor guard did not fire. A LOCATED must be EARNED (NS #1)."
        )
        assert _recorded_failure_boundary(text) == boundary, (
            f"[{label}] the failure must be attributed to boundary '{boundary}', got "
            f"{_recorded_failure_boundary(text)!r} — the skip-gate needs the right host."
        )

    # MUTATION: neuter the CSV-shape guard on the header-only case; the run must now
    # emit a fabricated LOCATED over a zero-row table (RED against the UNKNOWN assertion).
    mod = _load_run_p5()
    mod.OUT = tmp_path / "note_neutered.md"
    mod._search = lambda: _fake_search()
    mod._fetch_csv = lambda url: HEADER_ONLY
    mod._guard_csv_shape = lambda header, rows: None  # neutered
    mod.main()
    neutered = mod.OUT.read_text(encoding="utf-8")
    assert _token(neutered, "DECISION-VERDICT") == "LOCATED", (
        "neutering `_guard_csv_shape` did NOT flip the header-only case into a fabricated "
        "LOCATED — the guard is then not the thing keeping the verdict honest, so the gate "
        "above proves nothing. The floor guard must be load-bearing."
    )


def test_p5_records_tripwire_framing():
    """Gate 4 — the plan's content strings + the spec framing. ADDITIVE.

    Every string here is written unconditionally by run_p5.py, so this gate cannot fail
    on a bad outcome; it pins the plan's intent (the suppressed-cell convention and the
    tripwire fallback). Gates 1-3 are what judge the run.
    """
    text = _note_text()
    low = text.lower()
    assert "tripwire" in low
    assert ("suppress" in low) or ("0-band" in low)
    assert ("located" in low) or ("unknown-probe-failed" in low)
