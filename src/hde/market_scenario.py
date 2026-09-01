"""
S4b market-scenario slot: load + validate a demoflow ScenarioPrior artifact.

The artifact contract is demoflow spec §7(a)
(docs/specs/2026-07-21-demoflow-demographic-scenario-module-design.md), as
ratified for consumption by docs/specs/2026-08-26-s4b-demographic-input-slot-sketch.md.
Every violation is a typed refusal naming the failing rows — never a partial load.
"""

import hashlib
import json
import math
import re

from .anchors import ANCHORS, describe_mapping_version, describe_source_key, source_key_label
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

# Closed enums declared by the emitter contract (§7(a)). The geography set is the
# demoflow Geography enum's string values; the enum never crosses the file boundary.
GEOGRAPHIES = (
    "MTL_RMR", "MTL_ISLAND_RA06", "LAVAL_RA13", "QC_RMR", "HORS_RMR",
    "LANAUDIERE_RA14_PROXY", "LAURENTIDES_RA15_PROXY", "MONTEREGIE_RA16_PROXY",
)
DWELLING_TYPES = ("all", "condo", "house")   # v0 emits 'all' — both options consume it
HORIZON_YEARS = (2030, 2035, 2040, 2045, 2050)
SCENARIOS = ("low", "reference", "high")
FLAG_ENUM = frozenset({"borrowed_prior", "ra_proxy", "never_relax_stress"})

# The emitter (demoflow §7(a)) is canonical for the container: rows live under
# `scenario_priors`, and `run_pairing`/`schema` ride at top level (amendment #22's
# content-binding token + artifact-type name). Corroborated against a live emitted
# artifact 2026-08-26 — the seam test that caught the original mismatch.
TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "mapping_version", "data_vintage", "assumptions_hash",
     "run_pairing", "schema", "scenario_priors"}
)
DATA_VINTAGE_FIELDS = frozenset(
    {"isq_edition", "census_year", "constants_as_of", "source_hashes"}
)
ROW_FIELDS = frozenset(
    {
        "geography", "dwelling_type", "horizon_year", "scenario",
        "demo_drift_mean", "demo_drift_p10", "demo_drift_p90",
        "drawdown_weight_tilt", "excess_demand_rate", "flags",
    }
)

# Normal fit through the published p10–p90 DECILE span: sigma = (p90 - p10) / (2 × 1.28155).
# The constant is a registered derivation anchor so its rationale travels with the number.
DRIFT_SIGMA_DIVISOR = ANCHORS["market_scenario.drift_sigma_divisor"].value

# Simulation year t maps to calendar year START_CALENDAR_YEAR + t; the band for a
# calendar year is the first declared horizon at or after it (last band holds).
START_CALENDAR_YEAR = 2026

# A prior's constants_as_of year within +/- this tolerance of START_CALENDAR_YEAR
# still bands sim years into the intended horizons; beyond it the mapping is off.
CONSTANTS_AS_OF_YEAR_TOLERANCE = 1
_CONSTANTS_AS_OF_YEAR_RE = re.compile(r"^(\d{4})")


class ScenarioPriorError(Exception):
    """Typed refusal for a ScenarioPrior file that violates its contract."""
    pass


def _reject_constant(token: str):
    raise ScenarioPriorError(
        f"non-finite JSON literal {token!r} (NaN/Infinity) violates the "
        f"allow_nan=False contract"
    )


@dataclass(frozen=True)
class ScenarioPriorRow:
    """One validated ScenarioPrior row (REAL CPI-deflated decimal/yr drift)."""
    geography: str
    dwelling_type: str
    horizon_year: int
    scenario: str
    demo_drift_mean: float
    demo_drift_p10: float
    demo_drift_p90: float
    drawdown_weight_tilt: float
    excess_demand_rate: float
    flags: Tuple[str, ...]

    @property
    def key(self) -> Tuple[str, int, str]:
        return (self.dwelling_type, self.horizon_year, self.scenario)

    @property
    def drift_sigma(self) -> float:
        return (self.demo_drift_p90 - self.demo_drift_p10) / DRIFT_SIGMA_DIVISOR


def band_drift(row: ScenarioPriorRow, z: float) -> float:
    """Demographic drift level for one draw of a band's Normal(mean, sigma) prior."""
    return row.demo_drift_mean + z * row.drift_sigma


def calendar_year_for_sim_year(sim_year: int) -> int:
    return START_CALENDAR_YEAR + sim_year


def band_horizon_for_calendar_year(calendar_year: int) -> int:
    """Piecewise-constant banding: first declared horizon >= the calendar year;
    the last declared band holds to the horizon end."""
    for h in HORIZON_YEARS:
        if h >= calendar_year:
            return h
    return HORIZON_YEARS[-1]


def _constants_as_of_year(constants_as_of: object) -> int | None:
    """Leading 4-digit year of constants_as_of ('2026', '2026-06-01', '2026-Q3');
    None when unparseable (including non-string values)."""
    if not isinstance(constants_as_of, str):
        return None
    m = _CONSTANTS_AS_OF_YEAR_RE.match(constants_as_of)
    return int(m.group(1)) if m else None


def time_anchor_violations(current_year: int, constants_as_of: str | None = None) -> List[str]:
    """Time-anchor drift violations for the sim-year -> calendar-year -> band
    mapping, as human-readable strings (empty = clean). Pure: the year arrives
    as a parameter, never the wall clock.

    Two checks:
    - staleness: current_year > START_CALENDAR_YEAR — the wall clock has moved
      past the mapping anchor, so every sim year lands on a stale calendar year
      and band. Warning class (math internally consistent, just anchored to an
      old year); enforced at the CLI/MCP edges, never here.
    - prior-vs-constant drift: constants_as_of's year more than
      CONSTANTS_AS_OF_YEAR_TOLERANCE from START_CALENDAR_YEAR, or unparseable —
      the prior's bands were built against a different calendar, so the band
      mapping is misaligned. Hard-fail class: load_scenario_prior raises on it
      (silent drift here would produce confidently wrong bands).
    """
    violations: List[str] = []
    if current_year > START_CALENDAR_YEAR:
        violations.append(
            f"time anchor stale: current year {current_year} is past "
            f"START_CALENDAR_YEAR={START_CALENDAR_YEAR}; every simulation year "
            f"is being mapped to a stale calendar year and demographic band"
        )
    if constants_as_of is not None:
        prior_year = _constants_as_of_year(constants_as_of)
        if prior_year is None:
            violations.append(
                f"data_vintage.constants_as_of {constants_as_of!r} has no "
                f"leading 4-digit year; cannot verify alignment with "
                f"START_CALENDAR_YEAR={START_CALENDAR_YEAR}"
            )
        elif abs(prior_year - START_CALENDAR_YEAR) > CONSTANTS_AS_OF_YEAR_TOLERANCE:
            violations.append(
                f"data_vintage.constants_as_of {constants_as_of!r} resolves to "
                f"year {prior_year}, which is more than "
                f"{CONSTANTS_AS_OF_YEAR_TOLERANCE} year(s) from "
                f"START_CALENDAR_YEAR={START_CALENDAR_YEAR}; the sim-year -> "
                f"calendar-year -> horizon-band mapping is misaligned"
            )
    return violations


@dataclass
class LoadedScenarioPrior:
    """A validated ScenarioPrior filtered to one requested geography."""
    schema_version: str
    mapping_version: str
    assumptions_hash: str
    file_sha256: str
    geography: str
    rows: Dict[Tuple[str, int, str], ScenarioPriorRow] = field(default_factory=dict)
    # Identity envelope member `data_vintage` (isq_edition, census_year,
    # constants_as_of, source_hashes) — carried so consumers can cite the
    # vintage alongside the geography. Empty dict when absent (defaults only).
    data_vintage: Dict[str, object] = field(default_factory=dict)

    def rows_for_dwelling(self, dwelling_type: str) -> Dict[Tuple[int, str], ScenarioPriorRow]:
        exact = {
            (h, s): row for (d, h, s), row in self.rows.items()
            if d == dwelling_type
        }
        if exact:
            return exact
        return {  # v0 emits 'all': both dwelling options consume those rows
            (h, s): row for (d, h, s), row in self.rows.items() if d == "all"
        }

    # ---- provenance, rendered ONLY from what the file carries (E.1–E.3) ----

    def vintage_clause(self) -> str:
        """' (ISQ 2026 scenarios, 2021 census)' — empty when the vintage is absent."""
        vintage = self.data_vintage
        parts = []
        if vintage.get("isq_edition"):
            parts.append(f"ISQ {vintage['isq_edition']} scenarios")
        if vintage.get("census_year"):
            parts.append(f"{vintage['census_year']} census")
        return " (" + ", ".join(parts) + ")" if parts else ""

    def sources(self) -> List[Dict[str, object]]:
        """Every pinned source: key, human citation, digest(s), extraction date."""
        raw = self.data_vintage.get("source_hashes")
        if not isinstance(raw, dict):
            return []
        out: List[Dict[str, object]] = []
        for key in sorted(raw):
            entry = raw[key] if isinstance(raw[key], dict) else {}
            out.append({
                "key": key,
                "citation": describe_source_key(key),
                "sha256": entry.get("sha256"),
                "extracted_at": entry.get("extracted_at"),
            })
        return out

    def source_line(self) -> str:
        """Plot-footer citation: the primary source FAMILIES actually present
        in the file, compacted (ISQ workbooks → one entry, StatCan tables →
        their ids); derived artifacts collapse into their parents."""
        labels = sorted({
            source_key_label(s["key"]) for s in self.sources()
            if not source_key_label(s["key"]).startswith(("derived:", "uncited source:"))
        })
        uncited = sum(1 for s in self.sources() if source_key_label(s["key"]).startswith("uncited source:"))
        isq = sorted({lbl.split(" (")[0] for lbl in labels if lbl.startswith("ISQ ")})
        statcan = sorted(lbl.removeprefix("StatCan ") for lbl in labels if lbl.startswith("StatCan "))
        other = [lbl for lbl in labels if not lbl.startswith(("ISQ ", "StatCan "))]
        families = []
        if isq:
            families.append(" + ".join(isq))
        if statcan:
            families.append("StatCan " + ", ".join(statcan))
        families.extend(other)
        text = "Source: " + (" · ".join(families) if families else "no pinned sources")
        if uncited:
            text += f" (+{uncited} uncited)"
        return text + f"\ndemoflow ScenarioPrior v{self.schema_version}"

    def describe(self) -> str:
        """One sentence a user can read: what the prior is, its vintage, the
        calendar anchor, the mapping, and its pinned sources."""
        vintage = self.data_vintage
        parts = [f"{self.geography} demand model{self.vintage_clause()}"]
        constants_as_of = vintage.get("constants_as_of")
        if isinstance(constants_as_of, str) and constants_as_of:
            parts.append(f"constants as of {constants_as_of}")
        parts.append(
            f"simulation year 1 = calendar {START_CALENDAR_YEAR}, bands "
            f"{'/'.join(str(h) for h in HORIZON_YEARS)}"
        )
        parts.append(f"mapping v{self.mapping_version}: {describe_mapping_version(self.mapping_version)}")
        srcs = self.sources()
        if srcs:
            parts.append(
                f"{len(srcs)} pinned sources (sha256 in --json): "
                + "; ".join(source_key_label(s["key"]) for s in srcs)
            )
        return " · ".join(parts)

    def provenance_block(self) -> Dict[str, object]:
        """Machine-readable provenance that rides every result payload."""
        vintage = self.data_vintage
        return {
            "file_sha256": self.file_sha256,
            "assumptions_hash": self.assumptions_hash,
            "geography": self.geography,
            "schema_version": self.schema_version,
            "mapping_version": self.mapping_version,
            "isq_edition": vintage.get("isq_edition"),
            "census_year": vintage.get("census_year"),
            "constants_as_of": vintage.get("constants_as_of"),
            "start_calendar_year": START_CALENDAR_YEAR,
            "horizon_years": list(HORIZON_YEARS),
            "source_keys": [s["key"] for s in self.sources()],
        }


def _require_finite_number(value, label: str, errors: list) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{label} must be a number, got {value!r}")
    elif not math.isfinite(value):
        errors.append(f"{label} must be finite, got {value!r}")


def _validate_row(index: int, row) -> tuple:
    """Validate one raw row dict; returns (key_fields, errors)."""
    errors: list = []
    if not isinstance(row, dict):
        return None, [f"rows[{index}] is not an object"]
    unknown = sorted(set(row.keys()) - ROW_FIELDS)
    missing = sorted(ROW_FIELDS - set(row.keys()))
    if unknown:
        errors.append(f"rows[{index}] has unknown field(s): {unknown} (exact allowlist)")
    if missing:
        errors.append(f"rows[{index}] is missing field(s): {missing}")

    geo = row.get("geography")
    dwelling = row.get("dwelling_type")
    horizon = row.get("horizon_year")
    scenario = row.get("scenario")
    label = f"rows[{index}] ({geo!r}, {dwelling!r}, {horizon!r}, {scenario!r})"

    if geo not in GEOGRAPHIES:
        errors.append(f"{label}: unknown geography {geo!r}; declared enum only")
    if dwelling not in DWELLING_TYPES:
        errors.append(f"{label}: unknown dwelling_type {dwelling!r}; declared enum only")
    if (isinstance(horizon, bool) or not isinstance(horizon, int)
            or horizon not in HORIZON_YEARS):
        errors.append(f"{label}: horizon_year must be one of {list(HORIZON_YEARS)}, got {horizon!r}")
    if scenario not in SCENARIOS:
        errors.append(f"{label}: unknown scenario {scenario!r}; declared enum only")

    p10 = row.get("demo_drift_p10")
    mean = row.get("demo_drift_mean")
    p90 = row.get("demo_drift_p90")
    tilt = row.get("drawdown_weight_tilt")
    edf = row.get("excess_demand_rate")
    _require_finite_number(p10, f"{label}.demo_drift_p10", errors)
    _require_finite_number(mean, f"{label}.demo_drift_mean", errors)
    _require_finite_number(p90, f"{label}.demo_drift_p90", errors)
    _require_finite_number(tilt, f"{label}.drawdown_weight_tilt", errors)
    _require_finite_number(edf, f"{label}.excess_demand_rate", errors)

    if all(isinstance(v, (int, float)) and not isinstance(v, bool)
           and math.isfinite(v) for v in (p10, mean, p90)):
        if not (p10 <= mean <= p90):
            errors.append(
                f"{label}: band ordering violated (p10={p10}, mean={mean}, p90={p90}); "
                f"requires p10 <= mean <= p90")
    if isinstance(tilt, (int, float)) and not isinstance(tilt, bool) and math.isfinite(tilt):
        if tilt < 0:
            errors.append(f"{label}: drawdown_weight_tilt must be >= 0, got {tilt}")

    flags = row.get("flags")
    if not isinstance(flags, list) or any(not isinstance(f, str) for f in flags):
        errors.append(f"{label}: flags[] must be a list of strings, got {flags!r}")
    else:
        bad = sorted(set(flags) - FLAG_ENUM)
        if bad:
            errors.append(
                f"{label}: flags[] contains value(s) outside the closed enum "
                f"{sorted(FLAG_ENUM)}: {bad}")
        if isinstance(tilt, (int, float)) and not isinstance(tilt, bool) \
                and math.isfinite(tilt) and tilt < 1.0 \
                and "never_relax_stress" not in flags:
            errors.append(
                f"{label}: drawdown_weight_tilt < 1.0 requires never_relax_stress in flags[]")

    if all(isinstance(v, str) for v in (geo, dwelling, scenario)) \
            and isinstance(horizon, int) and not isinstance(horizon, bool) \
            and geo in GEOGRAPHIES and dwelling in DWELLING_TYPES \
            and horizon in HORIZON_YEARS and scenario in SCENARIOS:
        return (geo, dwelling, horizon, scenario), errors
    return None, errors


def load_scenario_prior(path: str, geography: str) -> LoadedScenarioPrior:
    """
    Load and fully validate a ScenarioPrior JSON file, filtered to ``geography``.

    Raises ScenarioPriorError naming every failing row on any contract violation.
    """
    prior_path = Path(path)
    if not prior_path.exists():
        raise ScenarioPriorError(f"ScenarioPrior file not found: {path}")
    raw_bytes = prior_path.read_bytes()
    try:
        data = json.loads(raw_bytes.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ScenarioPriorError(f"ScenarioPrior file is not valid JSON: {e}") from e

    # ---- file-level shape ----
    if not isinstance(data, dict):
        raise ScenarioPriorError("ScenarioPrior top level must be a JSON object")
    errors: list = []
    unknown_top = sorted(set(data.keys()) - TOP_LEVEL_FIELDS)
    missing_top = sorted(TOP_LEVEL_FIELDS - set(data.keys()))
    if unknown_top:
        errors.append(f"unknown top-level field(s): {unknown_top} (exact allowlist)")
    if missing_top:
        errors.append(f"missing top-level field(s): {missing_top}")
    if errors:
        raise ScenarioPriorError("\n".join(errors))

    for str_field in ("schema_version", "mapping_version", "assumptions_hash"):
        if not isinstance(data[str_field], str) or not data[str_field]:
            errors.append(f"{str_field} must be a non-empty string")
    vintage = data["data_vintage"]
    if not isinstance(vintage, dict):
        errors.append("data_vintage must be an object")
    else:
        v_unknown = sorted(set(vintage.keys()) - DATA_VINTAGE_FIELDS)
        v_missing = sorted(DATA_VINTAGE_FIELDS - set(vintage.keys()))
        if v_unknown:
            errors.append(f"data_vintage has unknown field(s): {v_unknown}")
        if v_missing:
            errors.append(f"data_vintage is missing field(s): {v_missing}")
        source_hashes = vintage.get("source_hashes")
        # Values are PROVENANCE OBJECTS per the emitter (codex r3-F6): each maps a
        # raw-response extraction to {sha256, extracted_at[, committed_sha256]}.
        def _bad_source_entry(k, v) -> bool:
            if not isinstance(k, str) or not isinstance(v, dict):
                return True
            sha = v.get("sha256")
            if not isinstance(sha, str) or len(sha) != 64:
                return True
            if not all(isinstance(x, str) for x in v.values()):
                return True
            return not {"sha256", "extracted_at"} <= set(v)

        if not isinstance(source_hashes, dict) or not source_hashes or any(
                _bad_source_entry(k, v) for k, v in source_hashes.items()):
            errors.append(
                "data_vintage.source_hashes must map source names to "
                "{sha256: 64-hex, extracted_at, ...} provenance objects")
    if errors:
        raise ScenarioPriorError("\n".join(errors))

    # ---- prior-vs-constant cross-check (fail loud on drift) ----
    # constants_as_of half only: current_year == START_CALENDAR_YEAR keeps the
    # staleness half (a side-effecty edge-layer concern) silent here. A prior
    # whose constants were built against a misaligned calendar silently bands
    # every sim year wrong — refuse rather than compute confidently wrong bands.
    anchor_violations = time_anchor_violations(
        START_CALENDAR_YEAR, vintage.get("constants_as_of"))
    if anchor_violations:
        raise ScenarioPriorError("\n".join(anchor_violations))

    # ---- row-level validation (collect ALL violations, then refuse once) ----
    rows_raw = data["scenario_priors"]
    if not isinstance(rows_raw, list) or not rows_raw:
        raise ScenarioPriorError("rows must be a non-empty list")

    seen: Dict[tuple, int] = {}
    parsed: Dict[tuple, ScenarioPriorRow] = {}
    geographies_present: set = set()
    for i, raw in enumerate(rows_raw):
        key, row_errors = _validate_row(i, raw)
        if key is None:
            errors.extend(row_errors)
            continue
        geo, dwelling, horizon, scenario = key
        if key in seen:
            errors.append(
                f"rows[{i}] duplicates row {seen[key]} for key "
                f"({geo}, {dwelling}, {horizon}, {scenario})")
            continue
        seen[key] = i
        geographies_present.add(geo)
        parsed[key] = ScenarioPriorRow(
            geography=geo,
            dwelling_type=dwelling,
            horizon_year=horizon,
            scenario=scenario,
            demo_drift_mean=float(raw["demo_drift_mean"]),
            demo_drift_p10=float(raw["demo_drift_p10"]),
            demo_drift_p90=float(raw["demo_drift_p90"]),
            drawdown_weight_tilt=float(raw["drawdown_weight_tilt"]),
            excess_demand_rate=float(raw["excess_demand_rate"]),
            flags=tuple(raw["flags"]),
        )
        errors.extend(row_errors)

    # ---- complete Cartesian grid per declared geography, no gaps ----
    # The dwelling dimension is whatever the FILE declares per geography (v0
    # emits exactly 'all'); each declared (geography, dwelling) pair must cover
    # the full horizon × scenario grid. A file mixing 'all' with 'condo'/'house'
    # for one geography is ambiguous and refuses.
    for g in geographies_present:
        dwellings = {d for (gg, d, h, s) in parsed if gg == g}
        if len(dwellings - {"all"}) and "all" in dwellings:
            errors.append(
                f"geography {g} mixes 'all' rows with condo/house rows — "
                "ambiguous which a consumer follows")
            continue
        expected_keys = {
            (g, d, h, s)
            for d in dwellings
            for h in HORIZON_YEARS
            for s in SCENARIOS
        }
        missing_keys = sorted(expected_keys - set(parsed))
        for g_, d_, h_, s_ in missing_keys:
            errors.append(f"missing Cartesian row ({g_}, {d_}, {h_}, {s_})")
    if errors:
        raise ScenarioPriorError("\n".join(errors))

    # ---- geography match rule: requested geography must match >= 1 row ----
    if geography not in geographies_present:
        raise ScenarioPriorError(
            f"requested geography {geography!r} matches no row in {path}; "
            f"geographies present: {sorted(geographies_present)}")

    kept = {
        (d, h, s): row
        for (g, d, h, s), row in parsed.items()
        if g == geography
    }
    return LoadedScenarioPrior(
        schema_version=data["schema_version"],
        mapping_version=data["mapping_version"],
        assumptions_hash=data["assumptions_hash"],
        file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        geography=geography,
        rows=kept,
        data_vintage=vintage if isinstance(vintage, dict) else {},
    )
