import hashlib
from pathlib import Path

import pytest

from demoflow.loaders.pins import (
    DATA_DIR,
    RAW_SOURCE_MEMBER,
    RAW_SOURCE_SHA256,
    WORKBOOK_SHA256,
    raw_anchor,
    raw_member,
    verify_pin,
    verify_raw_anchor,
)
from demoflow.errors import LoaderError

PROBES = Path(__file__).resolve().parent.parent / "probes"
_P2_EXTRACT = "census_tenure_age_98100231.csv"


def test_committed_workbooks_match_pins():
    for name, expected in WORKBOOK_SHA256.items():
        digest = hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()
        assert digest == expected, f"{name} drifted: {digest} != {expected}"


def test_verify_pin_raises_on_drift(tmp_path):
    bad = tmp_path / "pop-as-rmr-base.xlsx"
    bad.write_bytes(b"not the workbook")
    with pytest.raises(LoaderError, match="sha256"):
        verify_pin(bad, "pop-as-rmr-base.xlsx")


def test_verify_pin_raises_on_unregistered_name(tmp_path):
    """ADDED beyond the plan's two bodies: the plan's drift test matches on
    "sha256", which `re.search`-matches BOTH branch messages ("sha256 drift
    for ..." and "no sha256 pin registered for ..."). A typo'd key in
    WORKBOOK_SHA256 would therefore leave that test green while the raised
    reason is wrong. This pins the unregistered-name branch with a
    DISCRIMINATING match so the two fail-loud paths cannot be confused."""
    unpinned = tmp_path / "pop-as-mrc-base.xlsx"
    unpinned.write_bytes(b"a workbook with no pin registered")
    with pytest.raises(LoaderError, match="no sha256 pin registered"):
        verify_pin(unpinned, "pop-as-mrc-base.xlsx")


# --- UPSTREAM RAW ANCHOR (T13b PART 2 / DIV F2) --------------------------------------
# The committed P2 extract is a FILTERED subset of an 850,971,474-byte raw StatCan member
# that cannot be committed. Until 2026-08-08 the raw member's digest lived ONLY in probe-note
# prose, so the whole legitimate-refresh motion (re-extract + re-pin + regen) compared
# co-moving objects and passed on a materially different vintage. These gates pin the
# promoted anchor and its two fail-loud paths.

def test_raw_source_anchor_pins_the_p2_inner_csv_and_cites_the_probe_note():
    """The registry value must be the digest the P2 note RECORDS, not a re-typed one.

    probes/P2-census-tenure-age.md:16 is the recorded observation; this reads that line and
    asserts the registry carries it verbatim, so the pin and its citation cannot drift apart
    (a re-extract that rewrites the note now reds here until the anchor is DELIBERATELY
    re-pinned — which is the whole point of an external anchor).
    """
    assert _P2_EXTRACT in RAW_SOURCE_SHA256, (
        f"{_P2_EXTRACT} has no upstream raw anchor — the refresh path has no external check")
    # The identity-table ROW, not the §3 prose sentence that also says "raw inner CSV".
    lines = [line for line in (PROBES / "P2-census-tenure-age.md").read_text(
        encoding="utf-8").splitlines() if line.startswith("| raw inner CSV")]
    assert len(lines) == 1, f"expected ONE recorded raw-inner-CSV row in the P2 note, got {lines}"
    assert RAW_SOURCE_SHA256[_P2_EXTRACT] in lines[0], (
        f"registry raw anchor {RAW_SOURCE_SHA256[_P2_EXTRACT]} is not the digest recorded in "
        f"probes/P2-census-tenure-age.md:16 ({lines[0]!r})")


def test_raw_anchors_are_a_separate_registry_from_the_committed_files():
    """A raw anchor may NEVER join WORKBOOK_SHA256.

    `test_committed_workbooks_match_pins` hashes every row of that registry off disk and
    `verify_pin` reads the named file — but the raw member is not committed, so a row there
    would red the registry gate and turn `verify_pin` into a FileNotFoundError path (a class
    no `except LoaderError` catches). The two registries are therefore disjoint by contract.
    """
    assert not (set(RAW_SOURCE_SHA256.values()) & set(WORKBOOK_SHA256.values())), (
        "a raw-source digest also appears in WORKBOOK_SHA256, whose every row is hashed off "
        "disk — the raw member is not committed")
    for name in RAW_SOURCE_SHA256:
        assert name in WORKBOOK_SHA256, (
            f"{name} carries a raw anchor but is not itself a pinned committed file — the "
            "PIT chain (raw member -> filter predicate -> committed extract) is broken")


def test_verify_raw_anchor_refuses_drift_and_unregistered_names():
    """The pure gate the re-extract path calls (probes/run_p2.py). Both branches are pinned
    with DISCRIMINATING matches: a bare "raw" match would accept either message and a typo'd
    registry key would leave the drift branch unexecuted."""
    verify_raw_anchor(RAW_SOURCE_SHA256[_P2_EXTRACT], _P2_EXTRACT)      # matching digest passes
    assert raw_anchor(_P2_EXTRACT) == RAW_SOURCE_SHA256[_P2_EXTRACT]
    with pytest.raises(LoaderError, match="raw-source drift"):
        verify_raw_anchor("0" * 64, _P2_EXTRACT)
    with pytest.raises(LoaderError, match="no raw-source anchor registered"):
        verify_raw_anchor("0" * 64, "census_tenure_age_99999999.csv")
    with pytest.raises(LoaderError, match="no raw-source anchor registered"):
        raw_anchor("census_tenure_age_99999999.csv")


def test_the_raw_anchor_registries_are_key_identical_and_read_through_accessors():
    """The anchor is TWO hand-maintained dicts keyed by the same extract name — a drift class.

    Found in review 2026-08-08: `RAW_SOURCE_SHA256` had the raising accessor and these gates,
    while `RAW_SOURCE_MEMBER` was read by bare subscript at four consumer sites, so a digest
    registered without its member name (or the reverse) raised `KeyError` — the taxonomy escape
    pins.py's own block argues the raw anchor exists separately to avoid. Two gates, because
    they fail on different days: the PARITY assert catches a half-registered row at edit time
    (it is green today and must STAY green when the second extract joins), the accessor branch
    catches whatever half-registered state still reaches runtime. `test_census_ownership.py::
    test_a_half_registered_raw_anchor_refuses_instead_of_crashing` is the one that discriminated
    the live defect — this file's job is the registry contract.
    """
    assert set(RAW_SOURCE_SHA256) == set(RAW_SOURCE_MEMBER), (
        f"the two halves of the raw anchor disagree on keys: digests {sorted(RAW_SOURCE_SHA256)} "
        f"vs members {sorted(RAW_SOURCE_MEMBER)} — a digest with no member name hashes an "
        "unidentified object, and a member name with no digest pins nothing")
    assert raw_member(_P2_EXTRACT) == RAW_SOURCE_MEMBER[_P2_EXTRACT] == "98100231.csv"
    with pytest.raises(LoaderError, match="no raw-source member registered"):
        raw_member("census_tenure_age_99999999.csv")
