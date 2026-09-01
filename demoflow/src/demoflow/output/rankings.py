"""Rankings table (spec §7b) — deterministic ordering from a multi-year x 3-scenario ED
trajectory, plus the emitted row's closed contracts.

COLLAPSE RULE: rank by MEAN ED under the REFERENCE scenario, ASCENDING (most negative ED =
highest demographic-flow risk = rank 1); exact ties break by the scenario-named FAIBLE mean
(worst case), then by enum declaration order as the final deterministic tiebreak.

FAN FIELDS ARE SCENARIO-NAMED, NOT MIN/MAX (spec §7b, codex r6-F6 — the earlier min/max
sentence is GONE from the spec): `mean_ed_low` is the Faible (D2026) mean and `mean_ed_high`
the Fort (E2026) mean, whatever their numeric order. They CAN cross, and a crossing is a
legitimate reading, not a defect — any min/max envelope is derived at display time, never
stored. Storing a sorted pair would silently relabel which scenario produced which number.

TEMPORAL DOMAIN IS THE CALLER'S (codex r8-F3): these functions average whatever series they
are handed. The spec's domain — PROJECTED years only, first projected year through 2051,
both endpoints included — is applied by the Task-29 pipeline when it slices the frame. The
domain is load-bearing (an all-years average can REVERSE a pair's order), so the slice is
pinned by a fixture here and by the orchestrator there.

THREE CLOSED VOCABULARIES MEET IN THIS FILE AND NONE OF THEM IS ANOTHER:
  * `RANKING_FLAGS_ALLOWED` — this module's emitter enum, what a ranking ROW may claim;
  * `UNRESOLVED_INPUTS` — the run-level exclusion record's reason enum (branch iii below);
  * `loaders.constants.ANCHOR_FLAGS` — where a CONSTANT came from (input provenance), a
    different question with a deliberately overlapping token (`borrowed_prior`).
The Tranche-2 ScenarioPrior row enum is a fourth and is NOT built here.

DIVERGENCE FROM THE PLAN BODY, SPEC-RULED: the plan's `RANKING_FLAGS_ALLOWED` carried two
members. Spec §7 closes it at THREE — `closed_cohort_exceedance` was added by steering ruling
K (2026-08-07) after the plan was written. See `CLOSED_COHORT_EXCEEDANCE_MEMBERS` below.

WHY THE GUARDS BELOW EXIST BEYOND THE PLAN BODY (precedent: `balance/excess_demand.py`, same
reason): the shapes they refuse are silently wrong rather than loudly wrong, and this module
is the last stop before a shipped artifact. A NaN mean compares False against everything, so
it sorts by input order and two conforming runs emit DIFFERENT rankings from identical data —
the exact outcome §7b's determinism contract forbids. A partial ED (missing scenario, empty
year slice) would otherwise surface as a KeyError far from its cause or, worse, as an implicit
default. An under-covering `rank_stable` mapping would report the missing geographies STABLE,
which is a verification verdict fabricated from absence.
"""
import math
from dataclasses import dataclass

from demoflow.errors import CalibrationError
from demoflow.geography import Geography, RA_PROXY_MEMBERS, Scenario

_ENUM_ORDER = {g: i for i, g in enumerate(Geography)}
_GEOGRAPHY_VALUES = frozenset(g.value for g in Geography)

RANKINGS_ROW_FIELDS = frozenset(
    {"geography", "mean_ed_reference", "mean_ed_low", "mean_ed_high", "rank", "rank_stable", "flags"})

# CLOSED emitter enum (spec §7b). An open flags[] is a serialization side-channel for the
# prohibited quantities, so membership is checked at emit, not by convention.
RANKING_FLAGS_ALLOWED = frozenset({"borrowed_prior", "ra_proxy", "closed_cohort_exceedance"})

# Canonical emission order — spec §7b's own listing order. Fixed so the Task-30 golden diff
# moves only when a modeled quantity moves, never because a flag was appended on another path.
_FLAG_EMIT_ORDER = ("borrowed_prior", "ra_proxy", "closed_cohort_exceedance")

# Geographies whose MEASURED 75+ net-migration rate exceeded the 1 %/yr materiality cap that
# spec §5 r3-F2 attaches to the closed-cohort assumption. Per operator ruling K (2026-08-07)
# the omission STANDS and every ranking row of an exceeding geography carries the flag, marking
# that rank lower-confidence. The set is MEASURED, not declared: `probes/closed-cohort-migration.md`
# records max 1.6722 %/yr at LAVAL_RA13 2007/08 (3 exceeding geography-periods, 1 of 7 measured
# geographies, full published span 2001/02-2024/25; HORS_RMR NOT-COVERED by the source). It is a
# module constant rather than a caller argument on purpose — a parameter would let a caller drop
# the flag, and the ruling says every row carries it. A re-measurement (new probe run) edits it.
CLOSED_COHORT_EXCEEDANCE_MEMBERS = frozenset({Geography.LAVAL_RA13})

# CLOSED reason enum for the run-level exclusion record (spec §8 resolution branch iii).
UNRESOLVED_INPUTS = frozenset({"immigrant_component_flows"})


@dataclass(frozen=True)
class GeoRanking:
    rank: int
    geography: Geography
    mean_ed_reference: float
    mean_ed_low: float          # Faible (D2026 / Scenario.LOW) mean — scenario-named, not min
    mean_ed_high: float         # Fort   (E2026 / Scenario.HIGH) mean — scenario-named, not max
    rank_stable: bool = True    # robustness-sweep verdict (codex r8-F1/r9-F1) — TYPED, never a flag string
    flags: tuple[str, ...] = ()  # tuple, not list: a list default is mutable on a "frozen" row,
                                 # which reopens the closed enum after construction


@dataclass(frozen=True)
class RankingExclusion:
    """A geography EXCLUDED FROM RANKINGS ENTIRELY because a required input is unresolvable
    (spec §8 branch iii) — never a partial ED, never an unstated default."""
    geography: Geography
    unresolved_input: str

    def __post_init__(self) -> None:
        if not isinstance(self.geography, Geography):
            raise ValueError(f"exclusion geography {self.geography!r} is not a Geography enum member "
                             f"(str-Enum hash equality would let a bare string through to `.value`)")
        if self.unresolved_input not in UNRESOLVED_INPUTS:
            raise ValueError(f"unresolved_input {self.unresolved_input!r} is outside the closed enum "
                             f"{sorted(UNRESOLVED_INPUTS)} (no free-text channel on the exclusion record)")

    def as_row(self) -> dict:
        """The emitted (serialized) exclusion record — geography as its enum VALUE."""
        return {"geography": self.geography.value, "unresolved_input": self.unresolved_input}


def exclude_from_rankings(
    ed: dict[Geography, dict[Scenario, list[float]]],
    unresolved: dict[Geography, str],
) -> tuple[dict[Geography, dict[Scenario, list[float]]], list[RankingExclusion]]:
    """Split the ED map into (rankable, exclusion records) — spec §8's three-way HORS_RMR
    resolution, branch (iii). Branch (i) fired for the committed vintage (compo-rmr-base.xlsx
    ships its own hors-RMR row), so `unresolved` is EMPTY on the current run and every modeled
    geography ranks; the path exists because a future vintage without that row must EXCLUDE
    rather than emit a partial ED. A named geography with no ED entry at all is the normal
    shape — no ED is computed for it — and still produces a record."""
    excluded = {geo: RankingExclusion(geo, reason) for geo, reason in unresolved.items()}
    rankable = {geo: by_scen for geo, by_scen in ed.items() if geo not in excluded}
    # enum order, not caller-construction order: the record set ships in a golden artifact.
    return rankable, [excluded[geo] for geo in sorted(excluded, key=_ENUM_ORDER.__getitem__)]


def refuse_cross_vintage(vintages: set[str]) -> None:
    """Rankings are computed within a SINGLE run — one data vintage / assumptions_hash (§7b);
    cross-vintage comparison is refused at the emitter. An EMPTY set is refused too: a run that
    recorded no identity at all would pass a bare `> 1` check vacuously, and a same-vintage
    gate that cannot fail is not a gate."""
    if len(vintages) != 1:
        raise CalibrationError(
            f"single-vintage rankings required; refused vintage set {sorted(vintages)} "
            f"({'no data vintage recorded' if not vintages else 'cross-vintage comparison'})")


def _scenario_mean(geo: Geography, scen: Scenario, series) -> float:
    xs = list(series)
    if not xs:
        raise CalibrationError(f"{geo.value}/{scen.value}: empty ED series — a geography with no "
                               f"years in the ranking domain is a partial ED, never a default")
    m = sum(xs) / len(xs)
    if not math.isfinite(m):
        raise CalibrationError(f"{geo.value}/{scen.value}: mean ED is not finite ({m}) — a non-finite "
                               f"mean sorts by input order and destroys the deterministic ordering")
    return m


def rank_geographies(ed: dict[Geography, dict[Scenario, list[float]]],
                     borrowed: set[Geography] | None = None,
                     rank_stable: dict[Geography, bool] | None = None) -> list[GeoRanking]:
    """Rank the geographies in `ed` (spec §7b collapse rule). `ed` carries the ranking-domain
    slice already; `borrowed` names the geographies whose inputs were borrowed from a coarser
    geography; `rank_stable` carries the robustness-sweep verdict per geography.

    `rank_stable=None` means NO SWEEP WAS RUN and every row defaults to True — that default is
    the plan body's and is kept for unit-level ordering use. The Task-29 orchestrator MUST pass
    the sweep result: a run that ships `rank_stable: true` without sweeping is claiming a
    verification verdict it never computed. A PROVIDED mapping is required to cover every ranked
    geography, which closes the partial-mapping half of that hole here."""
    borrowed = borrowed or set()
    if rank_stable is not None:
        uncovered = sorted(g.value for g in set(ed) - set(rank_stable))
        if uncovered:
            raise CalibrationError(f"rank_stable mapping does not cover ranked geographies {uncovered} "
                                   f"— an absent sweep verdict must not default to STABLE")
        untyped = sorted(g.value for g in ed if not isinstance(rank_stable[g], bool))
        if untyped:
            raise CalibrationError(f"rank_stable values must be TYPED bools (codex r9-F1), "
                                   f"never flag strings: {untyped}")

    rows = []
    for geo, by_scen in ed.items():
        if not isinstance(geo, Geography):
            raise CalibrationError(f"ranking key {geo!r} is not a Geography enum member — str-Enum "
                                   f"hash equality would let a bare string rank and then fail at emit")
        missing = sorted(s.value for s in Scenario if s not in by_scen)
        if missing:
            raise CalibrationError(f"{geo.value}: ED missing scenario(s) {missing} — the fan is "
                                   f"scenario-named and cannot be emitted partially")
        rows.append((
            geo,
            _scenario_mean(geo, Scenario.REFERENCE, by_scen[Scenario.REFERENCE]),
            _scenario_mean(geo, Scenario.LOW, by_scen[Scenario.LOW]),      # Faible
            _scenario_mean(geo, Scenario.HIGH, by_scen[Scenario.HIGH]),    # Fort
        ))
    # ascending by (ref mean, Faible mean, enum order): most negative ref ED = rank 1.
    rows.sort(key=lambda r: (r[1], r[2], _ENUM_ORDER[r[0]]))

    out = []
    for i, (geo, mref, mlow, mhigh) in enumerate(rows, start=1):
        flags = set()
        if geo in RA_PROXY_MEMBERS:
            flags.add("ra_proxy")
        if geo in borrowed:
            flags.add("borrowed_prior")
        if geo in CLOSED_COHORT_EXCEEDANCE_MEMBERS:
            flags.add("closed_cohort_exceedance")     # operator ruling K — rides EVERY row of the geography
        out.append(GeoRanking(rank=i, geography=geo, mean_ed_reference=mref, mean_ed_low=mlow,
                              mean_ed_high=mhigh, rank_stable=(rank_stable or {}).get(geo, True),
                              flags=tuple(f for f in _FLAG_EMIT_ORDER if f in flags)))
    return out


def ranking_row(gr: GeoRanking) -> dict:
    """The emitted (serialized) rankings row — geography as its enum VALUE, flags as a list.
    `.value` is not cosmetic: under py3.12 str-Enum `str(Geography.MTL_RMR)` is the REPR
    'Geography.MTL_RMR', so an f-string/str() path would ship a Python repr into the artifact."""
    return {"rank": gr.rank, "geography": gr.geography.value,
            "mean_ed_reference": gr.mean_ed_reference, "mean_ed_low": gr.mean_ed_low,
            "mean_ed_high": gr.mean_ed_high, "rank_stable": gr.rank_stable, "flags": list(gr.flags)}


def assert_rankings_row_valid(row: dict) -> None:
    """Emitter gate (Task 29 calls it per row): the field set equals the allowlist EXACTLY, every
    string position is enum-bound, and every field carries its declared TYPE. The allowlist alone
    binds vocabulary, not types — without the type checks an enum repr, a stringly-typed sweep
    verdict, or a NaN mean would all ship inside allowed field names."""
    if set(row) != RANKINGS_ROW_FIELDS:
        raise ValueError(f"rankings row fields {sorted(row)} != allowlist {sorted(RANKINGS_ROW_FIELDS)}")

    if row["geography"] not in _GEOGRAPHY_VALUES:
        raise ValueError(f"rankings row geography {row['geography']!r} is not a Geography enum value "
                         f"(a str-Enum repr or a free string cannot ride this position)")

    for name in ("mean_ed_reference", "mean_ed_low", "mean_ed_high"):
        v = row[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"rankings row {name} must be a finite number, got {v!r}")

    if isinstance(row["rank"], bool) or not isinstance(row["rank"], int) or row["rank"] < 1:
        raise ValueError(f"rankings row rank must be a positive int (1-based), got {row['rank']!r}")

    if not isinstance(row["rank_stable"], bool):
        raise ValueError(f"rankings row rank_stable must be a TYPED bool — the robustness-sweep "
                         f"verdict never rides as a string — got {row['rank_stable']!r}")

    flags = row["flags"]
    if not isinstance(flags, (list, tuple)):
        raise ValueError(f"rankings row flags must be a list, got {type(flags).__name__}")
    bad = [f for f in flags if f not in RANKING_FLAGS_ALLOWED]
    if bad:
        raise ValueError(f"rankings flag(s) outside closed enum {sorted(RANKING_FLAGS_ALLOWED)}: {bad}")
    if len(set(flags)) != len(flags):
        raise ValueError(f"duplicate rankings flag(s) in {list(flags)}")
