"""P2 gates — three INDEPENDENT verification questions, deliberately not merged.

    test_p2_live_pull_verdict_is_wired   ->  "did the live pull actually succeed?"
    test_p2_extract_matches_its_pin      ->  "is the committed anchor still the one recorded?"
    test_p2_extract_content_invariants   ->  "was the anchor CORRECT when it was generated?"

One gate per question, so a red names its own cause. Folded together, a checksum drift and
a false-failure verdict produce the SAME red — a diagnostic loss on gates whose whole job
is to be trustworthy.

The third gate exists because the byte-pin cannot catch a filter-logic bug: a pin only
proves the file has not changed SINCE commit, never that it was right when generated.
Demonstrated concretely — deleting all 7,200 Saguenay rows and re-pinning the result passes
both of the other two gates. The content gate therefore recomputes the invariants straight
from the CSV and deliberately does NOT import `run_p2.py`: reusing the producer's filter
logic would make the gate inherit the very bug it exists to catch.

Neither gate is `assert "WIRED" in text or "FAILED" in text`: that shape is satisfied by
every outcome the probe can produce, so it can never fail and would happily rubber-stamp a
broken pull. Required semantics instead:

  VERDICT gate
    * `VERDICT: WIRED` recorded    -> pass
    * `LIVE PULL FAILED` recorded  -> FAIL, naming the recorded observation, UNLESS the
                                      source is independently confirmed unreachable
                                      -> skip, with the reason recorded
    * neither recorded             -> FAIL. Unknown is not OK.
    The green path is OFFLINE — it never touches the network. Only the failure branch
    probes reachability, and only to decide fail-vs-skip.

  EXTRACT-DRIFT gate
    * committed extract hashes to the pin the probe recorded      -> pass
    * anything else, INCLUDING a note that records no pin at all  -> FAIL.
    A gate that cannot verify must refuse, never false-green. So a note clobbered by a
    re-run against a down source reds here — the identity chain's record is gone (restore
    the note from git) — rather than going quiet.
    This gate assumes an LF checkout, true on this Linux-only stack. Under a hypothetical
    CRLF checkout it would false-FAIL, never false-green: it errs safe by construction.

  CONTENT-INVARIANT gate
    Recomputed from the committed CSV, offline: the exact 7 GEO members, the single
    statistic, 7,200 rows per GEO, the spec oracle, and the absence of Ottawa-Gatineau.
    Every expected value below is stated literally, independent of the producer.
"""

import csv
import hashlib
import re
import urllib.request
from collections import Counter
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
NOTE = _ROOT / "probes" / "P2-census-tenure-age.md"
EXTRACT = _ROOT / "data" / "census_tenure_age_98100231.csv"
WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/98100231/en"
REACHABILITY_TIMEOUT = 10

# --- content invariants, stated independently of the producer -----------------
EXPECTED_GEOS = {
    "Quebec",
    "Montréal (CMA), Que.",
    "Québec (CMA), Que.",
    "Saguenay (CMA), Que.",
    "Sherbrooke (CMA), Que.",
    "Trois-Rivières (CMA), Que.",
    "Drummondville (CMA), Que.",
}
EXPECTED_STATISTIC = "Number of private households"
EXPECTED_ROWS_PER_GEO = 7200  # 10 structural x 3 condo x 16 hh-type x 15 age
EXPECTED_TOTAL_ROWS = 50_400
FORBIDDEN_GEO = "Ottawa - Gatineau (CMA), Ont./Que."
# spec-pinned oracle: Montréal CMA, 75+, `Total -` member of every non-age dimension
ORACLE_OWNER = 113_730
ORACLE_TOTAL = 202_535

# Row COUNTS are a proxy: they cannot see a duplicated row, a geography whose payload was
# replaced by another's, a corrupted value column, or a re-tagged identifier. These pinned
# literals reach the values themselves, for every geography rather than only Montréal.
PINNED_DGUID = {
    "Quebec": "2021A000224",
    "Montréal (CMA), Que.": "2021S0503462",
    "Québec (CMA), Que.": "2021S0503421",
    "Saguenay (CMA), Que.": "2021S0503408",
    "Sherbrooke (CMA), Que.": "2021S0503433",
    "Trois-Rivières (CMA), Que.": "2021S0503442",
    "Drummondville (CMA), Que.": "2021S0503447",
}
PINNED_OWNER_SUM = {
    "Quebec": 89_113_620,
    "Montréal (CMA), Que.": 41_668_130,
    "Québec (CMA), Que.": 9_082_545,
    "Saguenay (CMA), Que.": 1_891_315,
    "Sherbrooke (CMA), Que.": 2_247_610,
    "Trois-Rivières (CMA), Que.": 1_712_210,
    "Drummondville (CMA), Que.": 1_015_555,
}

# Exception types that may legitimately excuse a recorded failure. Anything outside this
# set is a code/structural fault and must FAIL even when the source is unreachable —
# otherwise an offline run converts a real bug into a silent skip.
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
    }
)


def _source_reachable() -> bool:
    """Cheap, robust liveness probe. Any exception means unreachable."""
    try:
        with urllib.request.urlopen(WDS, timeout=REACHABILITY_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


def _recorded_failure_type(note_text: str) -> str | None:
    """The exception TYPE the probe recorded, e.g. 'URLError' or 'ValueError'."""
    found = re.search(r"LIVE PULL FAILED:\s*([A-Za-z_][A-Za-z0-9_.]*)\s*:", note_text)
    return found.group(1) if found else None


def _pinned_extract_sha256(note_text: str) -> str:
    """The EXTRACT's own sha256, from the recorded identity chain.

    Matches only the line naming the extract file. The raw inner CSV is recorded on its
    own line under the short name `98100231.csv`, which is not a substring of the
    extract's filename, so the raw and extract pins cannot be confused.
    """
    for line in note_text.splitlines():
        if EXTRACT.name in line:
            found = re.search(r"\b([0-9a-f]{64})\b", line)
            if found:
                return found.group(1)
    raise AssertionError(
        f"{NOTE} records no sha256 pin for {EXTRACT.name} — the identity chain "
        "(raw hash -> filter predicate -> extract hash) is broken. This gate REFUSES "
        "rather than passing unverified; restore the note or re-run probes/run_p2.py."
    )


def test_p2_live_pull_verdict_is_wired():
    """Gate 1 — the recorded verdict must be a genuine live success."""
    assert NOTE.exists(), "run probes/run_p2.py first"
    text = NOTE.read_text(encoding="utf-8")

    if "LIVE PULL FAILED" in text:
        # Never silently pass. Two conditions must BOTH hold before a recorded failure is
        # excused, and the exception type is checked FIRST — reachability alone would let
        # any offline run launder a structural bug (e.g. the TARGET_GEOS guard firing)
        # into a green-looking skip.
        recorded = _recorded_failure_type(text)
        if recorded is None:
            pytest.fail(
                f"P2 records LIVE PULL FAILED with no parseable exception type — the "
                f"failure cannot be classified, so it cannot be excused. See: {NOTE}"
            )
        if recorded not in NETWORK_EXCEPTIONS:
            pytest.fail(
                f"P2 records LIVE PULL FAILED: {recorded} — that is a code/structural "
                "fault, not a network outage, so an unreachable source does not excuse "
                f"it. See the recorded observation: {NOTE}"
            )
        if _source_reachable():
            pytest.fail(
                f"P2 records LIVE PULL FAILED ({recorded}) while {WDS} answers 200 — the "
                f"probe is broken, not the source. See the recorded observation: {NOTE}"
            )
        pytest.skip(
            f"P2 records a network-class failure ({recorded}) and {WDS} is independently "
            f"confirmed unreachable (timeout {REACHABILITY_TIMEOUT}s). "
            f"Recorded observation: {NOTE}"
        )

    assert "VERDICT: WIRED" in text, (
        f"{NOTE} records neither 'VERDICT: WIRED' nor 'LIVE PULL FAILED' — the probe's "
        "outcome is unknown, and unknown is not OK. Re-run probes/run_p2.py."
    )


def test_p2_extract_matches_its_pin():
    """Gate 2 — the committed offline anchor must still be the one that was recorded."""
    assert NOTE.exists(), "run probes/run_p2.py first"
    assert EXTRACT.exists(), (
        f"{EXTRACT} is missing — the committed offline reproducibility anchor is gone; "
        "re-run probes/run_p2.py"
    )
    pinned = _pinned_extract_sha256(NOTE.read_text(encoding="utf-8"))
    actual = hashlib.sha256(EXTRACT.read_bytes()).hexdigest()
    assert actual == pinned, (
        f"{EXTRACT.name} has DRIFTED from the sha256 pinned in {NOTE.name}: "
        f"recorded {pinned}, on disk {actual}"
    )


def test_p2_extract_content_invariants():
    """Gate 3 — the anchor must be CORRECT, not merely unchanged.

    Recomputed straight from the CSV. Does not import run_p2.py: a gate that reused the
    producer's filter logic would inherit the bug it exists to catch.
    """
    assert EXTRACT.exists(), f"{EXTRACT} is missing — re-run probes/run_p2.py"

    per_geo: Counter = Counter()
    statistics: set[str] = set()
    dguids: dict[str, set] = {}
    owner_sums: Counter = Counter()
    coords_per_geo: dict[str, set] = {}
    all_coords: set[str] = set()
    coord_rows = 0
    owner = total = 0
    with EXTRACT.open(encoding="utf-8", newline="") as fh:
        rows = csv.reader(fh)  # positional: duplicate `Symbol` headers collapse in a dict
        header = next(rows)
        i_geo = header.index("GEO")
        i_dguid = header.index("DGUID")
        i_coord = header.index("Coordinate")
        i_stat = header.index("Statistics (3C)")
        i_age = header.index("Age of primary household maintainer (15)")
        i_struct = header.index("Structural type of dwelling (10)")
        i_condo = header.index("Condominium status (3)")
        i_hh = header.index("Household type including census family structure (16)")
        i_total = header.index("Tenure (4):Total - Tenure[1]")
        i_owner = header.index("Tenure (4):Owner[2]")
        for row in rows:
            geo = row[i_geo]
            per_geo[geo] += 1
            statistics.add(row[i_stat])
            dguids.setdefault(geo, set()).add(row[i_dguid])
            owner_sums[geo] += int(row[i_owner])
            coords_per_geo.setdefault(geo, set()).add(row[i_coord])
            all_coords.add(row[i_coord])
            coord_rows += 1
            if (
                row[i_geo] == "Montréal (CMA), Que."
                and row[i_struct] == "Total - Structural type of dwelling"
                and row[i_condo] == "Total - Condominium status"
                and row[i_hh] == "Total - Household type including census family structure"
                and row[i_age] in ("75 to 84 years", "85 years and over")
            ):
                total += int(row[i_total])
                owner += int(row[i_owner])

    assert set(per_geo) == EXPECTED_GEOS, (
        "extract GEO set is wrong — "
        f"missing {sorted(EXPECTED_GEOS - set(per_geo))}, "
        f"unexpected {sorted(set(per_geo) - EXPECTED_GEOS)}"
    )
    assert FORBIDDEN_GEO not in per_geo, (
        f"{FORBIDDEN_GEO} must NOT be in the extract: it is not wholly-Québec and its "
        "Québec side belongs inside the computed HORS_RMR residual"
    )
    assert statistics == {EXPECTED_STATISTIC}, (
        f"extract must carry exactly one statistic {EXPECTED_STATISTIC!r}, got "
        f"{sorted(statistics)}"
    )
    wrong = {g: n for g, n in per_geo.items() if n != EXPECTED_ROWS_PER_GEO}
    assert not wrong, (
        f"every GEO must carry exactly {EXPECTED_ROWS_PER_GEO} rows (the full "
        f"10x3x16x15 cross-product); these do not: {wrong}"
    )
    assert sum(per_geo.values()) == EXPECTED_TOTAL_ROWS, (
        f"expected {EXPECTED_TOTAL_ROWS:,} rows, got {sum(per_geo.values()):,}"
    )
    assert (owner, total) == (ORACLE_OWNER, ORACLE_TOTAL), (
        f"spec oracle broken: expected owner {ORACLE_OWNER:,} / total {ORACLE_TOTAL:,}, "
        f"got owner {owner:,} / total {total:,}"
    )

    # --- value-level invariants (row counts alone are a proxy) --------------------
    # `Coordinate` is the row's dimension address; a repeat means a row was duplicated
    # or a geography's payload was copied from another.
    assert len(all_coords) == coord_rows, (
        f"Coordinate must be unique across the extract: {coord_rows:,} rows carry only "
        f"{len(all_coords):,} distinct coordinates ({coord_rows - len(all_coords):,} "
        "duplicated)"
    )
    dup_within = {
        g: n - len(coords_per_geo[g]) for g, n in per_geo.items()
        if len(coords_per_geo[g]) != n
    }
    assert not dup_within, f"duplicate Coordinates within a geography: {dup_within}"

    observed_dguid = {g: sorted(v) for g, v in dguids.items()}
    expected_dguid = {g: [d] for g, d in PINNED_DGUID.items()}
    assert observed_dguid == expected_dguid, (
        "GEO->DGUID identity does not match the pinned map (a geography was re-tagged "
        f"or its payload swapped): expected {expected_dguid}, got {observed_dguid}"
    )

    assert dict(owner_sums) == PINNED_OWNER_SUM, (
        "per-GEO Owner column sums do not match the pinned values — the extract's "
        "VALUES have changed, not merely its shape. "
        f"differences: {
            {
                g: (PINNED_OWNER_SUM.get(g), owner_sums.get(g))
                for g in set(PINNED_OWNER_SUM) | set(owner_sums)
                if PINNED_OWNER_SUM.get(g) != owner_sums.get(g)
            }
        }"
    )
