"""IRCC PR-landings loader (spec §7c tripwire input). Absent file -> UNAVAILABLE
(the tripwire reports UNKNOWN). Present-but-malformed -> LoaderError.

WHO USES THIS: the PR-landings TRIPWIRE only — realized IRCC permanent-resident landings
vs the MIFI plan level. It is NOT the demand model (demand uses the ISQ compo "Immigrants
permanents"). Per steering RULING D the TOTAL-by-CMA axis SUFFICES here: immigration
CATEGORY is published province-level only (probe P5 §4: 0 of the package's 52 resources
cross a CMA term with a category term), and a category-by-CMA figure is never to be
synthesized.

ASYMMETRY, AND WHY IT IS NOT SLOPPINESS: absence returns a signal, malformation raises.
An absent feed is the spec's own fallback — the tripwire says UNKNOWN, which is a REFUSAL,
never a fabricated zero. A PRESENT file is a different claim: something asserts this is the
feed, so every way it can lie has to be a raise.

DELIMITER — MEASURED, NOT ASSUMED (live pull 2026-08-08: HTTP 200, 1,714,674 bytes,
21,217 data rows x 11 columns, 172 CMA members, 2015..2026): the feed is TAB-delimited
despite shipping as `.csv`. This is the one fact the loader most needs, because reading it
with the comma default does not merely mis-parse — three member names contain a comma
(`Territories (outside Census agglomeration, Nunavut)` and its Yukon / Northwest Territories
siblings), so a comma read of the real bytes dies with `pandas.errors.ParserError`: a class
no `except LoaderError` catches, which would crash the tripwire rather than let it report.

EXCEPTION TRANSLATION (the same taxonomy argument `census.py::_count` makes about bare
`int()`): every pandas read failure is re-raised as LoaderError. `ParserError` and
`EmptyDataError` are precisely the classes a malformed feed produces, so leaking them would
route the loudest failures around the one handler written to catch them. It also closes the
whitespace-only file, which has size > 0 and so slips the empty-file gate.

`dtype=str` + `keep_default_na=False` (both load-bearing): a suppressed cell is the literal
token `--` (values 0-5, per the live package notes) and MUST stay distinguishable. Under
pandas' default NA handling a blank cell would arrive as NaN, and naive band comparisons
classify NaN as INSIDE every band (spec §7c value integrity, codex r3-F5) — a suppressed or
blank cell degrading into a float is exactly how a verification gate false-greens. Nothing
here converts `--` into a number: its 0-band interval semantics is VALUE MODELING and belongs
to the tripwire task, not to a loader.

MODELED-CMA PRESENCE IS SCHEMA, so it is checked here (precedent: `census.py::_read_totals_cube`
asserts the extract's GEO set). If Montréal or Québec silently left the feed, the tripwire's
selection would sum to 0 realized landings — a number that reads as a total immigration
collapse and evaluates as CROSSED, when the truth is that the loader lost its address.

ROUNDING FLOOR, RECORDED NOT CORRECTED: TOTAL is rounded to the nearest 5 — MEASURED HERE
2026-08-08: 0 of 16,539 numeric cells are non-multiples of 5, min 5, 0 negative, alongside
4,678 suppressed cells. That there is no unrounded ESCAPE source is NOT this session's
measurement: probe P5 §3 (2026-07-21) records it, from the package notes plus 16 of 16 CSV
resources carrying the "[rounded... not for calculations]" label. So +/-2.5 per monthly cell
is the irreducible floor — negligible against the MIFI plan level (~45k/yr), and never
silently adjusted here.

NOT PINNED, DELIBERATELY: the ISQ workbooks and the Census extract are committed VINTAGES
with sha256 pins; this feed is refreshed MONTHLY, so a digest pin would red on every upstream
publication. Its integrity contract is the schema gate below, not identity. Committing a copy
under `data/` would also flip the tripwire's live state from UNKNOWN to wired — a wiring
decision that belongs to the tripwire task, not to this loader.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from demoflow.errors import LoaderError
from demoflow.loaders.pins import DATA_DIR

CSV_NAME = "ircc_pr_by_cma.csv"
SOURCE_URL = "https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_CMA.csv"
DELIMITER = "\t"

# Observed live 2026-08-08 (and at probe P5, 2026-07-21) — order included: the header is
# compared as an ordered list, so a reordered feed reds rather than silently re-addressing
# columns. Note the accents: `FR_ANNEÉ` is the feed's own spelling (not `FR_ANNÉE`).
EXPECTED_COLUMNS = (
    "EN_YEAR", "EN_QUARTER", "EN_MONTH",
    "FR_ANNEÉ", "FR_TRIMESTRE", "FR_MOIS",
    "EN_CENSUS_METROPOLITAN_AREA", "FR_RÉGION_MÉTROPOLITAINE_DE_RECENSEMENT",
    "EN_PROVINCE_TERRITORY", "FR_PROVINCE_TERRITOIRE",
    "TOTAL",
)

CMA_COLUMN = "EN_CENSUS_METROPOLITAN_AREA"
TOTAL_COLUMN = "TOTAL"

# The EN column carries ACCENTED French member names ('Montréal', 'Québec' — verified live,
# both present with 137 monthly rows and 0 suppressed cells). The feed publishes no 'Total'
# or 'Canada' aggregate member (0 matches live), so a member selection cannot double-count.
MODELED_CMAS = ("Montréal", "Québec")

SUPPRESSED = "--"
_COUNT = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class PRLandings:
    """`available=False` carries a `reason` and no frame; `available=True` carries a frame
    that has passed every gate below. There is no third state: a present-but-drifted feed
    raises rather than arriving as an available-looking record."""

    available: bool
    reason: str = ""
    frame: pd.DataFrame | None = None


def _read(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, sep=DELIMITER, dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError, OSError) as exc:
        raise LoaderError(
            f"IRCC PR CSV is unparseable as {DELIMITER!r}-delimited: {path} ({exc}). The feed "
            f"ships as `.csv` but is TAB-delimited ({SOURCE_URL})") from exc


def _check_header(frame: pd.DataFrame, path: Path) -> None:
    found = tuple(frame.columns)
    if found != EXPECTED_COLUMNS:
        raise LoaderError(
            f"{path.name}: schema drift — columns are {list(found)}, expected "
            f"{list(EXPECTED_COLUMNS)} (a comma-delimited or reordered feed lands here)")


def _check_totals(frame: pd.DataFrame, path: Path) -> None:
    """TOTAL's whole vocabulary is a nonnegative integer or the suppressed token `--`.
    A new token (`N/A`, a blank, a thousands separator) would otherwise reach the tripwire's
    arithmetic as a bare ValueError instead of a named drift."""
    bad = sorted({
        value for value in frame[TOTAL_COLUMN]
        if value != SUPPRESSED and not _COUNT.fullmatch(str(value))
    })
    if bad:
        raise LoaderError(
            f"{path.name}: {TOTAL_COLUMN} carries {len(bad)} unrecognized token(s) {bad[:5]} — "
            f"expected a nonnegative integer or the suppressed marker {SUPPRESSED!r}")


def _check_modeled_cmas(frame: pd.DataFrame, path: Path) -> None:
    members = set(frame[CMA_COLUMN])
    missing = [cma for cma in MODELED_CMAS if cma not in members]
    if missing:
        raise LoaderError(
            f"{path.name}: modeled CMA(s) {missing} absent from {CMA_COLUMN} "
            f"({len(members)} members present) — the tripwire would sum an empty selection "
            "to 0 realized landings, reporting CROSSED on a lost address")


def load_pr_landings(data_dir: Path | None = None) -> PRLandings:
    """Load the IRCC PR-by-CMA feed, or report it UNAVAILABLE.

    Gate order is deliberate — each stage names the cause a reader should act on:
    absent -> UNAVAILABLE; size 0 -> empty; unreadable -> unparseable; wrong columns ->
    schema drift; header-only -> no data rows; bad TOTAL token / missing modeled CMA ->
    named drift. Header BEFORE row count, so a garbage file reports the schema it failed
    rather than "no data rows", which would send the reader to the upstream publication
    calendar instead of to the parse.
    """
    path = (data_dir or DATA_DIR) / CSV_NAME
    if not path.exists():
        return PRLandings(available=False, reason=f"IRCC PR CSV not found: {path}")
    if path.stat().st_size == 0:
        raise LoaderError(f"IRCC PR CSV is empty: {path}")
    frame = _read(path)
    _check_header(frame, path)
    if frame.empty:
        raise LoaderError(f"IRCC PR CSV has no data rows: {path}")
    _check_totals(frame, path)
    _check_modeled_cmas(frame, path)
    return PRLandings(available=True, frame=frame)
