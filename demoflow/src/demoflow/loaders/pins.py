"""sha256 pins for the committed ISQ workbooks. The loader loads from a
configurable path defaulting to demoflow/data/; a pinned re-download (spec §4
slug URLs) is a FALLBACK only, and any drift (404/size/checksum) raises
LoaderError."""
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
