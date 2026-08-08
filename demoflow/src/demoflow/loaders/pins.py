"""sha256 pins for every committed data source — the ISQ workbooks AND the P2 Census
tenure x age extract. The loader loads from a configurable path defaulting to
demoflow/data/; a pinned re-download (spec §4 slug URLs) is a FALLBACK only, and any
drift (404/size/checksum) raises LoaderError.

The registry name is historical (`WORKBOOK_SHA256`); its contract is "committed source
file -> sha256", not "workbook". The Census extract joined it at Task 13, the first
CONSUMER read of that file: `derive_ownership_from_csv` verifies the extract against
this pin before deriving a single rate, so the PIT chain (raw response -> filter
predicate -> committed extract -> derived rates) is enforced in code rather than only
recorded in probes/P2-census-tenure-age.md."""
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
