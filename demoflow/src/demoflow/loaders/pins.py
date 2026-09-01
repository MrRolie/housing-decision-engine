"""sha256 pins for every committed data source — the ISQ workbooks AND the P2 Census
tenure x age extract. The loader loads from a configurable path defaulting to
demoflow/data/; a pinned re-download (spec §4 slug URLs) is a FALLBACK only, and any
drift (404/size/checksum) raises LoaderError.

The registry name is historical (`WORKBOOK_SHA256`); its contract is "committed source
file -> sha256", not "workbook". The Census extract joined it at Task 13, the first
CONSUMER read of that file: `derive_ownership_from_csv` verifies the extract against
this pin before deriving a single rate, so the PIT chain (raw response -> filter
predicate -> committed extract -> derived rates) is enforced in code rather than only
recorded in probes/P2-census-tenure-age.md.

A SECOND registry, `RAW_SOURCE_SHA256`, pins the UPSTREAM member behind a committed
extract — the one link in that chain a re-extract cannot move with. Its rows are never
hashed off disk (the raw member is not committed); the block below carries the argument."""
import hashlib
from pathlib import Path

from demoflow.errors import LoaderError

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

WORKBOOK_SHA256 = {
    "pop-as-rmr-base.xlsx": "288d8c9f03d05ece6ae1271e2cf55226a534d4fe27005ca76fb2ef305f0882d7",
    "pop-as-ra-base.xlsx": "ae9de62fd8631668e127e5cd37ec10028959a38a18831e1c5e4d102a1c8779fe",
    "pop-as-qc-base.xlsx": "1d286d252a75195db6ab66ac767e352d9f74e4e2359c68eba4a43301c9c61fd4",
    "compo-rmr-base.xlsx": "096246df47a95f729d46bacdb655cf297f4779163d62ee25e95254b5cc23844b",
    "compo-ra-base.xlsx": "1b81a82b0f0588a3217eb93b74d37044addf08934731dfd612e846e6de7b728f",
    # P2 Census extract (StatCan 98-10-0231-01, extracted_at 2026-07-21). Digest recomputed
    # from the committed file at Task 13 and cross-checked against the identity chain
    # recorded in probes/P2-census-tenure-age.md §2.
    "census_tenure_age_98100231.csv": "74673e57d1ae05824726b815e7263c18bb1b7d0419a3fbc52b8f6d6c704ee8da",
    # P3 living-arrangement WDS extract (StatCan 98-10-0134-01, pulled 2026-08-08 by
    # scripts/pull_living_arrangement.py). Same PIT role as the P2 extract above:
    # `derive_living_arrangement` verifies this pin before reading a single cell, and the
    # generated artifact records the digest so the load path can refuse a stale vintage
    # (steering ruling L). Two independent pulls of this cube produced byte-identical output,
    # so re-pinning is only ever a VINTAGE change, never pull noise.
    "living_arrangement_98100134.json":
        "2dfb73b91c7346576acf9e352002d101dcfede3abbdb152545474414a0838a39",
    # P11 operand-aligned CSD extract (StatCan 98-10-0232-01, pulled 2026-08-15 by
    # scripts/pull_hors_aligned_csd.py). The Québec-side census subdivisions of the
    # Ottawa-Gatineau CMA, plus the Québec province row the universe guard binds against —
    # the territory SUBTRACTED from the shipped HORS_RMR residual so the ownership rate's
    # territory matches the ISQ hors-RMR flow it multiplies (spec §6, the #12(B) reversal).
    # Same PIT role as the P2 and P3 extracts above: `derive_aligned_ownership` verifies this
    # pin before reading a cell, and the artifact records the digest so the load path can
    # refuse a stale vintage (steering ruling L). NO raw-source anchor row: unlike the P2
    # extract this is a WDS COORDINATE pull with no uncommittable upstream member behind it —
    # the committed file IS the response, projected and sorted (pins.py's ISQ parenthetical
    # argument). Two independent pulls minutes apart produced byte-identical output and
    # reproduced probe P10's own 259 published cells and 13 withheld addresses exactly, so
    # re-pinning is only ever a VINTAGE change, never pull noise.
    "hors_aligned_csd_98100232.json":
        "92821b9dad0d7aae7211300d11d3f721b8d7a0e2d19efcfa50ca78fb8cf24d3f",
    # P9 catalogue closure index (StatCan WDS full-catalogue member-level sweep, pulled
    # 2026-08-14 by probes/run_p9.py). NOT loaded by the module — it is EVIDENCE, the
    # compact derived form of a 5.29 GB pull that cannot be committed, and it is what turns
    # "the search is closed at member level" from a session measurement into a re-checkable
    # claim. Pinned here for the same reason the extracts are: this registry's rows are
    # hashed off disk by test_pins.py, so a silent edit to the evidence reds, and its
    # upstream anchor in RAW_SOURCE_SHA256 below fixes the pull the closure is scoped to.
    "catalogue_member_index_p9.json":
        "4e5f5bcff318cc7c25090582a2adbb1f85f3c23b9c2cf7ea429dde0c8e053fec",
}

# UPSTREAM RAW ANCHOR — committed extract -> sha256 of the RAW upstream member it was
# filtered from (T13b PART 2, DIV F2 2026-08-08). A SEPARATE registry, and deliberately so:
# WORKBOOK_SHA256's contract is "committed file -> digest" and test_pins.py hashes every one
# of its rows off disk, but the raw member here is 850,971,474 bytes and is NOT committed
# (~8x GitHub's hard file limit) — a row in that registry would red the registry gate and
# turn `verify_pin` into a FileNotFoundError path, a class no `except LoaderError` catches.
#
# WHY IT EXISTS: every other check on the derived tables compares CO-MOVING objects. Re-cut
# the extract and its own pin, the artifact's recorded digest and a fresh derivation all move
# together — so the whole legitimate-refresh motion (re-extract + re-pin + regen) passes on a
# materially different vintage, with the only external anchor being ONE published cell out of
# twelve. This digest does NOT move with a re-extract: `probes/run_p2.py` refuses a raw member
# that does not match it, so a new vintage cannot be extracted without a DELIBERATE, reviewed
# re-pin here, and both derived artifacts embed the value so a load can refuse a stale one.
RAW_SOURCE_SHA256 = {
    # P2: StatCan 98-10-0231-01, raw zip member '98100231.csv' (850,971,474 bytes), the
    # value recorded at the 2026-07-21 pull in probes/P2-census-tenure-age.md:16. The ZIP's
    # digest is deliberately NOT the anchor: archive metadata can shift across re-downloads
    # without the data changing, so the inner member is what a re-pull must reproduce.
    "census_tenure_age_98100231.csv":
        "773f7af8deac87087f02d5464292f8a3e71351a7b1d735e47d983b7fd32b7b2b",
    # P9: the FULL StatCan WDS catalogue metadata pull of 2026-08-14 (8,226 cubes,
    # 5,292,400,322 bytes on disk), the value recorded in
    # probes/P9-catalogue-closure.md's DECISION-RAW-PULL-SHA256. Same role as the P2 row
    # and a sharper one: the committed index is a COUNT-bearing summary of that pull, and
    # its whole product is a scoped NEGATIVE claim ("the search is closed at member level
    # over this catalogue"). A scope with no identified pull behind it is a session memory,
    # so this digest is what a re-derivation must reproduce before the closure may be
    # republished. Taken over a CANONICAL re-serialization, not the wire bytes: batch
    # boundaries and key order are not stable across pulls (the index's
    # `raw_pull_canonical_form` states the exact form).
    "catalogue_member_index_p9.json":
        "ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a",
}
# The digest's OTHER half: which member inside the upstream download it was taken over. Kept
# in its own dict rather than a record so `RAW_SOURCE_SHA256` stays a plain name->digest map
# (test_pins.py reads it as one, as does the probe-note citation gate) — but two dicts keyed by
# the same string ARE a drift class, so read them through the accessors below and never by
# subscript, and test_pins.py gates their key sets identical. Measured 2026-08-08: with the
# digest half present and the member half dropped, all four consumer sites raised bare
# `KeyError` — the taxonomy escape this block's own argument names.
RAW_SOURCE_MEMBER = {
    "census_tenure_age_98100231.csv": "98100231.csv",
    # Not a file inside an archive, unlike the P2 row — the P9 pull is a stream of API
    # responses, and what was hashed is their canonical re-serialization. Named as the
    # OPERATION rather than as a filename so no reader looks for a member that never
    # existed on any server.
    "catalogue_member_index_p9.json":
        "getAllCubesListLite + getCubeMetadata for every catalogue productId "
        "(canonical re-serialization; the exact form is stated in the index's "
        "_provenance.raw_pull_canonical_form)",
}

ISQ_SLUG_URL = "https://statistique.quebec.ca/fr/fichier/{slug}.xlsx"


def verify_pin(path: Path, name: str) -> None:
    """Raise LoaderError if `path` does not match the pinned sha256 for `name`."""
    expected = WORKBOOK_SHA256.get(name)
    if expected is None:
        raise LoaderError(f"no sha256 pin registered for {name!r}")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != expected:
        raise LoaderError(f"sha256 drift for {name}: expected {expected}, got {digest}")


def raw_anchor(name: str) -> str:
    """The pinned digest of the RAW upstream member behind committed extract `name`.

    Raises rather than returning None: a derivation whose upstream anchor has been dropped
    from the registry has lost the one check a re-extract cannot move, and `.get`-style
    silence there is exactly the unpinning this anchor exists to prevent.
    """
    digest = RAW_SOURCE_SHA256.get(name)
    if digest is None:
        raise LoaderError(
            f"no raw-source anchor registered for {name!r} — the upstream member's digest is "
            "the only check a re-extract cannot move with (DIV F2); register it in "
            "pins.RAW_SOURCE_SHA256 from the probe note that recorded the pull")
    return digest


def raw_member(name: str) -> str:
    """The upstream member name the raw anchor for committed extract `name` was taken over.

    Raises for the same reason `raw_anchor` does, one level down: this value is written into
    every derived artifact's `_provenance`, so a `.get`-style fallback would emit a
    HALF-PROVENANCED artifact — a recorded upstream digest with no statement of what was
    hashed, which no reader can reproduce. Refusal messages are the deliberate exception and
    use `RAW_SOURCE_MEMBER.get(name, '?')` instead: they are already refusing for a better
    reason (vintage drift), and raising there would destroy it.
    """
    member = RAW_SOURCE_MEMBER.get(name)
    if member is None:
        raise LoaderError(
            f"no raw-source member registered for {name!r} — the pinned upstream digest names "
            "nothing reproducible without it, so provenance would record a hash of an "
            "unidentified object; register the member in pins.RAW_SOURCE_MEMBER alongside its "
            "digest in pins.RAW_SOURCE_SHA256 (the two halves are gated key-identical)")
    return member


def verify_raw_anchor(digest: str, name: str) -> None:
    """Raise unless `digest` (freshly computed over the raw upstream member) matches the pin.

    Called by the RE-EXTRACT path (probes/run_p2.py), which is the only place the raw member
    is ever on disk. A mismatch means the upstream table has a new vintage: the extract must
    NOT be re-cut silently — re-pin here deliberately, then re-derive and re-commit.
    """
    expected = raw_anchor(name)
    if digest != expected:
        raise LoaderError(
            f"raw-source drift for {name} (upstream member "
            f"{RAW_SOURCE_MEMBER.get(name, '?')}): expected {expected}, got {digest} — the "
            "upstream table is a DIFFERENT vintage than the one this extract was cut from; "
            "re-pin pins.RAW_SOURCE_SHA256 deliberately, then re-derive every artifact")
