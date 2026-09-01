"""Geography + Scenario enums and per-source label junction maps (spec §8).
Junction rule: NORMALIZE first (strip whitespace + trailing footnote digits),
THEN the explicit label->enum map; unknown-after-normalization raises."""
import re
from enum import Enum

from demoflow.errors import LoaderError


class Geography(str, Enum):
    MTL_RMR = "MTL_RMR"
    MTL_ISLAND_RA06 = "MTL_ISLAND_RA06"
    LAVAL_RA13 = "LAVAL_RA13"
    QC_RMR = "QC_RMR"
    HORS_RMR = "HORS_RMR"
    LANAUDIERE_RA14_PROXY = "LANAUDIERE_RA14_PROXY"
    LAURENTIDES_RA15_PROXY = "LAURENTIDES_RA15_PROXY"
    MONTEREGIE_RA16_PROXY = "MONTEREGIE_RA16_PROXY"


class Scenario(str, Enum):
    REFERENCE = "reference"
    LOW = "low"
    HIGH = "high"


# RA rows used as couronne/periphery proxies: ranking members, never balance
# participants, never emitted in ScenarioPrior (spec §7b/§8).
RA_PROXY_MEMBERS = frozenset({
    Geography.LANAUDIERE_RA14_PROXY,
    Geography.LAURENTIDES_RA15_PROXY,
    Geography.MONTEREGIE_RA16_PROXY,
})

# ISQ scenario labels -> enum (spec §8). Missing any of the three for a
# geography x year -> raise (enforced in the loader, Task 10).
SCENARIO_LABEL_TO_ENUM = {
    "Référence (A2026)": Scenario.REFERENCE,
    "Faible (D2026)": Scenario.LOW,
    "Fort (E2026)": Scenario.HIGH,
}

# ISQ numeric sex codes {1,2,3}. 1->M, 2->F. Code 3 is TOTAL, kept out of this
# map and used ONLY for the additivity check (code3 ~= code1+code2) in the loader.
# NOTE (measured 2026-08-07): the workbooks' `Sexe` column reads back from pandas as
# FLOATS {1.0, 2.0, 3.0}. These int keys are float-safe by hash equality
# (hash(1.0) == hash(1)), so lookups work either way; the explicit int cast belongs
# in the Task 10/11 loader, not here.
SEX_CODE_TO_GENDER = {1: "M", 2: "F"}

# Normalized ISQ pop/compo geography label -> Geography. RMR labels come from
# pop-as-rmr-base / compo-rmr-base; RA labels from the -ra- workbooks.
_LABEL_TO_GEOGRAPHY = {
    "RMR de Montréal": Geography.MTL_RMR,
    "RMR de Québec": Geography.QC_RMR,
    "Montréal": Geography.MTL_ISLAND_RA06,     # RA06 (île) from pop-as-ra-base
    "Laval": Geography.LAVAL_RA13,             # RA13 == ville (exact)
    "Lanaudière": Geography.LANAUDIERE_RA14_PROXY,
    "Laurentides": Geography.LAURENTIDES_RA15_PROXY,
    "Montérégie": Geography.MONTEREGIE_RA16_PROXY,
    # codex r7-F4: the RMR workbook's OWN literal row supplies HORS_RMR POPULATION directly —
    # HORS_RMR is a modeled geography, NEVER IGNORED and NEVER a residual on the population side.
    # Measured 2026-08-07: pop-as-rmr-base ships 'Territoire hors des RMR', compo-rmr-base
    # ships 'Hors RMR' — two spellings of the same geography, both live, both required.
    "Territoire hors des RMR": Geography.HORS_RMR,
    "Hors RMR": Geography.HORS_RMR,
    # The plan's provisional map also carried 'Ailleurs au Québec' -> HORS_RMR. REMOVED
    # 2026-08-07: it appears in NO committed workbook, and spec §8 rules this a TOTAL map
    # over the workbook's VERIFIED label set. An unmeasured string pre-bound to a MODELED
    # geography is the one failure classify_geography's raise exists to prevent — if a
    # future edition ships that label meaning anything else, it would be silently absorbed
    # into the population side instead of surfacing as drift.
}

_TRAILING_FOOTNOTE = re.compile(r"\d+$")


def normalize_label(raw: str) -> str:
    """Strip surrounding whitespace, then strip a trailing footnote digit run
    (e.g. 'RMR d'Ottawa-Gatineau2' -> "RMR d'Ottawa-Gatineau")."""
    return _TRAILING_FOOTNOTE.sub("", str(raw).strip()).strip()


class _Ignored:
    """Sentinel: a recognized-but-unmodeled geography (spec §8 r4-F2)."""
    __slots__ = ()
    def __repr__(self) -> str:  # noqa: E704
        return "IGNORED"


IGNORED = _Ignored()

# Present-but-UNMODELED labels (the workbooks' verified label set minus the 8 modeled ones):
# RMR workbook's other RMRs + 'Le Québec'; RA workbook's other 12 administrative regions.
# Byte-exact spellings CONFIRMED 2026-08-07 by dumping every distinct normalized `Région1`
# value from all five committed workbooks (29 distinct labels; reconciliation in the Task 9
# run report). DUAL-DASH ENTRIES ARE NOT REDUNDANT — do not "clean up" the near-duplicates:
# the SAME nominal region ships under two different dash codepoints across editions,
# U+2013 EN DASH in pop-as-ra-base.xlsx vs U+002D HYPHEN-MINUS in compo-ra-base.xlsx.
# Dropping either variant makes a valid committed workbook fail to LOAD.
_IGNORED_LABELS = frozenset({
    "RMR d'Ottawa-Gatineau", "RMR de Saguenay", "RMR de Sherbrooke",
    # ('Ensemble du Québec' was in the plan's provisional set; REMOVED 2026-08-07 — it
    # appears in no committed workbook. The QC-total row's real label is 'Le Québec'.)
    "RMR de Trois-Rivières", "RMR de Drummondville", "Le Québec",
    "Bas-Saint-Laurent", "Capitale-Nationale", "Mauricie",
    "Estrie", "Outaouais", "Abitibi-Témiscamingue", "Côte-Nord", "Nord-du-Québec",
    "Chaudière-Appalaches", "Centre-du-Québec",
    "Saguenay–Lac-Saint-Jean",          # U+2013, pop-as-ra-base.xlsx
    "Saguenay-Lac-Saint-Jean",               # U+002D, compo-ra-base.xlsx
    "Gaspésie–Îles-de-la-Madeleine",    # U+2013, pop-as-ra-base.xlsx
    "Gaspésie-Îles-de-la-Madeleine",         # U+002D, compo-ra-base.xlsx
})


def classify_geography(raw: str) -> "Geography | _Ignored":
    """TOTAL label map over the workbook's verified label set (spec §8 r4-F2):
    modeled label -> Geography; known-unmodeled label -> IGNORED (recognized-and-
    excluded, so a valid workbook LOADS); a label OUTSIDE the verified set -> raise
    (schema drift). Fail-loud is BOTH here (unknown label) AND in
    `require_all_geographies` (a modeled label that went missing)."""
    key = normalize_label(raw)
    geo = _LABEL_TO_GEOGRAPHY.get(key)
    if geo is not None:
        return geo
    if key in _IGNORED_LABELS:
        return IGNORED
    raise LoaderError(f"geography label outside verified set (drift?): {key!r} (from {raw!r})")


def require_all_geographies(found: set[Geography], expected: set[Geography], ctx: str) -> None:
    """Positive completeness check (fail-loud). Raises if any EXPECTED in-scope
    geography is absent after mapping — the guard against a drifted/renamed label
    silently vanishing from the rankings (spec §8 'unknown-after-normalization'
    relocated to 'expected-not-found', which is stronger for model correctness)."""
    missing = expected - found
    if missing:
        raise LoaderError(f"{ctx}: expected geographies not found (schema drift?): "
                          f"{sorted(g.value for g in missing)}")


# In-scope enum members EXPECTED per committed workbook (the positive completeness set).
# VERIFIED 2026-08-07: every set below is exactly the modeled-label hit set measured in
# that workbook's own `Région1` column.
WORKBOOK_GEOGRAPHIES: dict[str, frozenset[Geography]] = {
    "pop-as-rmr-base.xlsx": frozenset({Geography.MTL_RMR, Geography.QC_RMR, Geography.HORS_RMR}),
    "compo-rmr-base.xlsx": frozenset({Geography.MTL_RMR, Geography.QC_RMR, Geography.HORS_RMR}),
    "pop-as-ra-base.xlsx": frozenset({
        Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13, Geography.LANAUDIERE_RA14_PROXY,
        Geography.LAURENTIDES_RA15_PROXY, Geography.MONTEREGIE_RA16_PROXY}),
    "compo-ra-base.xlsx": frozenset({
        Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13, Geography.LANAUDIERE_RA14_PROXY,
        Geography.LAURENTIDES_RA15_PROXY, Geography.MONTEREGIE_RA16_PROXY}),
    "pop-as-qc-base.xlsx": frozenset(),   # QC total: no in-scope enum geography (not used in T1 rankings)
}

# THE MODELED GEOGRAPHY DOMAIN — the set an emitted artifact must account for (spec §8: a
# geography is either RANKED or carries an exclusion record, and "the rankings cover the
# remaining members"). DERIVED from the registry above rather than restated as a second literal
# list, which is the whole point: the loaders already refuse a workbook that has lost any member
# of its own expected set (`require_all_geographies`), so this union is the domain the run is
# guaranteed to have loaded, and it cannot go stale against the registry the way a typed list
# would. `pop-as-qc-base.xlsx` contributes nothing (the QC total is no in-scope member), so the
# union is the same set whether it is taken over the population workbooks the run concatenates
# or over every registered workbook — `tests/test_geography.py` measures both directions plus
# `set(Geography)`, n=8, because a derivation cannot compare itself to the enum it draws from.
MODELED_GEOGRAPHIES: frozenset[Geography] = frozenset().union(*WORKBOOK_GEOGRAPHIES.values())
