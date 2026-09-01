"""The ScenarioPrior artifact (spec §7(a), TRANCHE 2) — the versioned JSON the hde S4b
market-scenario slots consume (hde spec sketch 2026-08-26). One row per
(geography, dwelling_type, horizon_year, scenario); the geography field carries the Geography
enum's STRING VALUE — the enum never crosses the file boundary, for the same str-Enum repr
reason `rankings.ranking_row` states at its own serializer.

WHAT THIS MODULE OWNS: the typed row, the builder that turns an ED grid into rows, the closed
vocabularies, and the vintage identity fields spec §7(a) adds to Tranche 1's envelope shape
({isq_edition, census_year, constants_as_of} around the same source_hashes map). The DOCUMENT
builder, the walk tables and the writer live in `output/artifacts.py`, exactly as they do for
the two Tranche-1 artifacts; this file stays leaf-ish so the contract vocabularies it owns can
be imported without pulling pandas.

THE GEOGRAPHY DOMAIN EXCLUDES THE RA PROXIES. Spec §7(b)/§8: LANAUDIERE/LAURENTIDES/MONTEREGIE
RA14/15/16 are RANKING MEMBERS carrying the periphery signal, "never balance participants,
never emitted in ScenarioPrior". The prior's domain is therefore
`MODELED_GEOGRAPHIES - RA_PROXY_MEMBERS` (5 members), derived from the same registries the
loaders enforce — never a second typed list.

DWELLING TYPE V0 EMITS `all` ONLY (spec §6): the schema field is retained for forward
compatibility; the plex demand compute is deferred to v1 alongside its supply source, because a
v0 plex row would have carried a self-discrediting `weak_identification` flag.

HORIZON AGGREGATION IS THE ENDPOINT VALUE, PINNED (spec §13 named the ED-trajectory →
horizon-row rule as an open contract debt; neither contract resolved it). Each horizon row
carries the ED computed AT the horizon year itself — not a mean over the band behind it. The
choice is stated here rather than improvised silently, and
`tests/test_scenario_prior.py` pins it with a DISTINGUISHING fixture (a series whose endpoint
and band-mean differ): the artifact reads as "the prior AT this horizon", matching the
horizon_year key, and the consumer composes bands piecewise-constant forward from each row. A
future re-ruling edits this docstring, the fixture, and bumps nothing else — the mapping_version
does NOT move, because the mapping (`balance/mapping.py`) is untouched by which year feeds it.

THE TILT IS NEUTRAL IN V0 and no row carries `never_relax_stress` today — see
`balance/mapping.py`'s residual ruling; the flag's contract (present on EVERY tilt < 1.0 row)
is enforced by `assert_scenario_prior_row_valid` and armed by RED fixtures, so it fires the day
a real tilt rule ships.

THE RENAME (amendment #26(A)): the raw structural signal rides the field
`excess_demand_rate`, NOT the stale `excess_demand_fraction`. The quantity is a yr^-1 RATE
(D and S are annual household flows over a household stock), the amendment rules the rename in
advance for exactly this unbuilt-Tranche-2 case, and the unit note required for keeping or
renaming lives here: `excess_demand_rate` carries units of yr^-1, REAL-terms, annual,
household-denominated — the same quantity Tranche 1's rankings publish under their per-scenario
mean_ed fields. A test pins the rename against both spellings.
"""
import math
import re
from dataclasses import dataclass
from datetime import datetime

from demoflow.balance import mapping
from demoflow.errors import CalibrationError
from demoflow.geography import (
    RA_PROXY_MEMBERS,
    SCENARIO_LABEL_TO_ENUM,
    Geography,
    Scenario,
)
from demoflow.loaders.constants import CONSTANTS as _CONSTANTS

SCENARIO_PRIOR_SCHEMA = "demoflow.scenario_prior.v1"

# The declared domains of the COMPLETE Cartesian product (spec §7(a)). Emission order is these
# tuples' order — deterministic, never caller-construction order.
HORIZON_YEARS = (2030, 2035, 2040, 2045, 2050)
DWELLING_TYPES = ("all",)                       # v0 emits `all` only (spec §6)
PRIOR_GEOGRAPHIES = tuple(g for g in Geography if g not in RA_PROXY_MEMBERS)
_SCENARIO_VALUES = frozenset(s.value for s in Scenario)

# CLOSED flags enum (codex r2-F3) — value-bearing or unknown flag strings are REJECTED at
# validation; an open flags[] is a serialization side-channel for the prohibited quantities.
PRIOR_FLAGS_ALLOWED = frozenset({"borrowed_prior", "ra_proxy", "never_relax_stress"})
_FLAG_EMIT_ORDER = ("ra_proxy", "borrowed_prior", "never_relax_stress")

# The rename (amendment #26(A)) — one declaration, pinned by test against BOTH spellings.
EXCESS_DEMAND_RATE_FIELD = "excess_demand_rate"

# THE ROW ALLOWLIST — the per-row half of spec §7(a)'s field list; the envelope half
# (schema_version / mapping_version / data_vintage / assumptions_hash) rides the document root,
# the same envelope discipline as the two Tranche-1 artifacts.
PRIOR_ROW_FIELDS = frozenset({
    "geography", "dwelling_type", "horizon_year", "scenario",
    "demo_drift_mean", "demo_drift_p10", "demo_drift_p90",
    "drawdown_weight_tilt", EXCESS_DEMAND_RATE_FIELD, "flags",
})

# spec §7(a)'s fuller data_vintage shape: the three identity fields AROUND the same
# source_hashes map Tranche 1 already carries. Declared once, here; `output/artifacts.py`
# composes the schema-dispatched vintage field set from this.
DATA_VINTAGE_IDENTITY_FIELDS = frozenset({"isq_edition", "census_year", "constants_as_of"})


def _derive_isq_edition() -> str:
    """The ISQ edition token, DERIVED from the scenario-label junction the loader already
    refuses a workbook without ('Référence (A2026)' etc.) — the workbooks' own labels are the
    only code-owned statement of which edition this tree consumes, so the vintage claim cannot
    drift from what actually loaded."""
    years = set()
    for label in SCENARIO_LABEL_TO_ENUM:
        found = re.search(r"\(([A-Z])(\d{4})\)$", label)
        if found is None:
            raise CalibrationError(
                f"ISQ scenario label {label!r} carries no '(Xyyyy)' edition suffix — the "
                f"ScenarioPrior's isq_edition is derived from these labels and refuses to "
                f"invent one")
        years.add(found.group(2))
    if len(years) != 1:
        raise CalibrationError(
            f"ISQ scenario labels disagree on their edition year ({sorted(years)}) — the "
            f"ScenarioPrior's isq_edition would be ambiguous")
    return years.pop()


def _derive_constants_as_of() -> str:
    """The anchor registry's most recent DATED revision, derived from the anchors' own as_of
    fields (only full ISO dates qualify; bare years and prose do not parse and are skipped).
    This is a VINTAGE claim about the constants, parked here by `loaders/constants.py`'s own
    note — never folded into `assumptions_hash`, which identifies the SELECTION."""
    candidates = []
    for anchor in _CONSTANTS.values():
        try:
            candidates.append(datetime.fromisoformat(anchor.as_of.split()[0]))
        except ValueError:
            continue                      # '~2018', '2021', prose — dated elsewhere, skip
    if not candidates:
        raise CalibrationError(
            "no constant anchor carries an ISO-dated as_of — constants_as_of cannot be "
            "derived and the ScenarioPrior refuses to invent a vintage")
    return max(candidates).date().isoformat()


ISQ_EDITION = _derive_isq_edition()
CENSUS_YEAR = "2021"      # Census 2021 headship/ownership base — bound by test to
                          # loaders.census._POP_BASE_YEAR, the producer of every PIT rate.
CONSTANTS_AS_OF = _derive_constants_as_of()


def prior_vintage(source_hashes: dict) -> dict:
    """spec §7(a)'s fuller data_vintage, wrapped around the run's own source_hashes map (the
    SAME map the sibling documents carry — one read, one set of digests, three envelopes)."""
    return {"isq_edition": ISQ_EDITION, "census_year": CENSUS_YEAR,
            "constants_as_of": CONSTANTS_AS_OF, "source_hashes": dict(source_hashes)}


@dataclass(frozen=True)
class ScenarioPriorRow:
    """One artifact row. `flags` is a tuple, not a list: a list default is mutable on a frozen
    row, which would reopen the closed enum after construction (rankings.py's own ruling)."""
    geography: Geography
    dwelling_type: str
    horizon_year: int
    scenario: Scenario
    excess_demand_rate: float          # yr^-1 — the raw structural signal (amendment #26(A))
    demo_drift_mean: float             # decimal/yr REAL, from balance.mapping (single path)
    demo_drift_p10: float
    demo_drift_p90: float
    drawdown_weight_tilt: float        # >= 0 multiplier; 1.0 neutral; S4b composes it
    flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.geography, Geography):
            raise ValueError(f"prior row geography {self.geography!r} is not a Geography enum "
                             f"member (str-Enum hash equality would let a bare string through)")
        if not isinstance(self.scenario, Scenario):
            raise ValueError(f"prior row scenario {self.scenario!r} is not a Scenario enum "
                             f"member")


def build_scenario_prior_rows(ed: dict[Geography, dict[Scenario, list[float]]],
                              lattices: dict[Geography, list[int]],
                              borrowed: set[Geography] | None = None) -> list[ScenarioPriorRow]:
    """Every artifact row, from the central-assumption ED grid.

    `ed` maps geography -> scenario -> ED series over PROJECTED years; `lattices` maps each
    geography to ITS projected-year lattice. The five prior geographies must share ONE lattice
    (they are slices of one ISQ projection; disagreement is upstream drift, not a formatting
    question) and every declared horizon must sit inside it — a horizon the frame does not
    project is a missing row, refused HERE at the builder rather than at the writer's set
    contract, where the cause would already be anonymous.

    ENDPOINT aggregation (see the module docstring ruling): the row's ED is the series value AT
    the horizon year, looked up by POSITION in the contiguous lattice — never a mean over the
    band behind it.
    """
    borrowed = borrowed or set()
    domain = set(PRIOR_GEOGRAPHIES)
    missing = sorted(g.value for g in domain - set(ed))
    if missing:
        raise CalibrationError(
            f"no ED computed for prior-domain geography(ies) {missing} — the ScenarioPrior "
            f"covers its whole domain or emits nothing (spec §7(a)'s COMPLETE product)")

    distinct = {tuple(lattices[g]) for g in domain}
    if len(distinct) != 1:
        raise CalibrationError(
            f"the prior geographies do not share one projected-year lattice "
            f"({len(distinct)} distinct lattices) — horizon lookup by position would index a "
            f"different year per geography")
    years = distinct.pop()
    absent = [h for h in HORIZON_YEARS if h not in years]
    if absent:
        raise CalibrationError(
            f"declared horizon(s) {absent} outside the projected lattice {years[0]}..{years[-1]}"
            f" — emitting them would require inventing an ED the frame never computed")
    index_of = {year: i for i, year in enumerate(years)}

    rows = []
    for geo in PRIOR_GEOGRAPHIES:
        for scen in Scenario:
            series = ed[geo][scen]
            for horizon in HORIZON_YEARS:
                ed_h = series[index_of[horizon]]
                mean, p10, p90 = mapping.demo_drift_prior(ed_h)
                tilt = mapping.drawdown_weight_tilt(ed_h)
                flags = set()
                if geo in borrowed:
                    flags.add("borrowed_prior")     # immigrant-input provenance, same rule as §7b
                if tilt < 1.0:
                    flags.add("never_relax_stress")
                rows.append(ScenarioPriorRow(
                    geography=geo, dwelling_type="all", horizon_year=horizon, scenario=scen,
                    excess_demand_rate=ed_h,
                    demo_drift_mean=mean, demo_drift_p10=p10, demo_drift_p90=p90,
                    drawdown_weight_tilt=tilt,
                    flags=tuple(f for f in _FLAG_EMIT_ORDER if f in flags)))
    return rows


def prior_row_to_dict(row: ScenarioPriorRow) -> dict:
    """The emitted (serialized) row — geography and scenario as their enum VALUES (an f-string/
    str() path would ship the py3.12 str-Enum REPR into the artifact; rankings.py states the
    same trap at its own serializer)."""
    return {"geography": row.geography.value,
            "dwelling_type": row.dwelling_type,
            "horizon_year": row.horizon_year,
            "scenario": row.scenario.value,
            EXCESS_DEMAND_RATE_FIELD: row.excess_demand_rate,
            "demo_drift_mean": row.demo_drift_mean,
            "demo_drift_p10": row.demo_drift_p10,
            "demo_drift_p90": row.demo_drift_p90,
            "drawdown_weight_tilt": row.drawdown_weight_tilt,
            "flags": list(row.flags)}


def assert_scenario_prior_row_valid(row: dict) -> None:
    """Emitter gate, called per row on the WRITE path (artifacts._ROW_CONTRACTS): the field set
    equals the allowlist EXACTLY, every string position is enum-bound, every numeric is a finite
    non-bool number, the band orders, the tilt is non-negative, and `never_relax_stress` is
    present on EVERY tilt < 1.0 row — and on NO other row, because a stress-relaxation marker on
    a neutral/amplifying row is a false claim, the same direction as a missing one."""
    if set(row) != PRIOR_ROW_FIELDS:
        raise ValueError(f"scenario-prior row fields {sorted(row)} != allowlist "
                         f"{sorted(PRIOR_ROW_FIELDS)}")

    if row["geography"] not in {g.value for g in Geography}:
        raise ValueError(f"prior row geography {row['geography']!r} is not a Geography enum value")
    if row["dwelling_type"] not in DWELLING_TYPES:
        raise ValueError(f"prior row dwelling_type {row['dwelling_type']!r} outside the declared "
                         f"v0 domain {list(DWELLING_TYPES)}")
    horizon = row["horizon_year"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon not in HORIZON_YEARS:
        raise ValueError(f"prior row horizon_year {horizon!r} outside the declared enum "
                         f"{list(HORIZON_YEARS)}")
    if row["scenario"] not in _SCENARIO_VALUES:
        raise ValueError(f"prior row scenario {row['scenario']!r} outside the declared enum "
                         f"{sorted(_SCENARIO_VALUES)}")

    for name in ("demo_drift_mean", "demo_drift_p10", "demo_drift_p90",
                 "drawdown_weight_tilt", EXCESS_DEMAND_RATE_FIELD):
        v = row[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"prior row {name} must be a finite number, got {v!r}")

    if not (row["demo_drift_p10"] <= row["demo_drift_mean"] <= row["demo_drift_p90"]):
        raise ValueError(f"prior row band ordering violated: p10 {row['demo_drift_p10']} > "
                         f"mean {row['demo_drift_mean']} or mean > p90 {row['demo_drift_p90']}")
    if row["drawdown_weight_tilt"] < 0:
        raise ValueError(f"prior row drawdown_weight_tilt {row['drawdown_weight_tilt']} < 0 — "
                         f"a negative multiplier on a hazard is not a weight")

    flags = row["flags"]
    if not isinstance(flags, (list, tuple)):
        raise ValueError(f"prior row flags must be a list, got {type(flags).__name__}")
    bad = [f for f in flags if f not in PRIOR_FLAGS_ALLOWED]
    if bad:
        raise ValueError(f"prior flag(s) outside closed enum {sorted(PRIOR_FLAGS_ALLOWED)}: {bad}")
    if len(set(flags)) != len(flags):
        raise ValueError(f"duplicate prior flag(s) in {list(flags)}")

    relaxed = "never_relax_stress" in flags
    if row["drawdown_weight_tilt"] < 1.0 and not relaxed:
        raise ValueError("prior row has drawdown_weight_tilt < 1.0 and no `never_relax_stress` "
                         "flag — spec §7(a) requires the flag on EVERY sub-neutral row")
    if row["drawdown_weight_tilt"] >= 1.0 and relaxed:
        raise ValueError("prior row carries `never_relax_stress` at tilt >= 1.0 — the flag marks "
                         "a stress RELAXATION and is false on a neutral or amplifying row")


def prior_document_complete(doc: dict) -> None:
    """Spec §7(a)'s WHOLE-DOCUMENT set contract: the row keys form the COMPLETE Cartesian
    product of the declared (geography x dwelling_type x horizon_year x scenario) domains with
    NO duplicates. Lives beside its two siblings in artifacts.py; imported there."""
    rows = doc["scenario_priors"]
    seen = [(r["geography"], r["dwelling_type"], r["horizon_year"], r["scenario"])
            for r in rows]
    duplicated = sorted({k for k in seen if seen.count(k) > 1})
    if duplicated:
        raise ValueError(
            f"scenario-prior artifact repeats row key(s) {duplicated} — a consumer keyed by "
            f"(geography, dwelling, horizon, scenario) keeps whichever it read last")
    expected = {(g.value, d, h, s.value)
                for g in PRIOR_GEOGRAPHIES for d in DWELLING_TYPES
                for h in HORIZON_YEARS for s in Scenario}
    unaccounted = sorted(expected - set(seen))
    outside = sorted(set(seen) - expected)
    if unaccounted or outside:
        raise ValueError(
            f"scenario-prior artifact is not the COMPLETE Cartesian product of its declared "
            f"domains: missing={unaccounted}, outside={outside}")
