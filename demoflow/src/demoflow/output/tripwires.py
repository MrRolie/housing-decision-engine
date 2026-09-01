"""Tripwire baselines (spec §7c). Fail-safe gate: REFUSES (UNKNOWN) when it cannot
verify; closed reason enum + `source`-bound-to-registry + record allowlist close the
string side-channel; the required set is CODE-owned (defeats co-deletion). Exit 0 iff
every required indicator is present-once, finite, fresh, well-banded, OK.

TWO LAYERS. Above the fold: the generic gate — `evaluate_indicator` and the record
contract, indicator-agnostic. Below it: `pr_landings_annual`, the one WIRED indicator
whose realized value is COMPUTED FROM THE FEED. That half exists because a hand-typed
realized value is not a weaker version of the gate, it is a defeat of it: a literal
compared against a band is a constant compared against a constant, green forever, on any
data, in any era. Six measured facts shape it, each stated at its gate below.

THE BAND IS THE CALLER'S. No band literal lives in this module. A threshold typed here
would be a parameter this module invented, and the same edit that widened it would silently
re-verdict every past run; bands arrive from the constants/spec surface the run declares.
`now` is injected for the same reason — a wall-clock read inside a verification gate makes
its verdict unreproducible, and freshness is exactly what an auditor re-checks."""
import math
from dataclasses import dataclass, field, replace
from enum import Enum

from demoflow.errors import LoaderError
from demoflow.loaders.ircc import (
    CMA_COLUMN, EN_MONTHS, MODELED_CMAS, MONTH_COLUMN, MONTH_INDEX, PROVINCE_COLUMN,
    QUEBEC_PROVINCE, QUEBEC_REQUIRED_CMAS, SUPPRESSED, TOTAL_COLUMN, YEAR_COLUMN, PRLandings,
)


class Status(str, Enum):
    OK = "OK"
    CROSSED = "CROSSED"
    UNKNOWN = "UNKNOWN"


class SourceKind(str, Enum):
    WIRED = "wired"
    OPERATOR_SUPPLIED = "operator_supplied"


class Reason(str, Enum):   # CLOSED machine-token enum — no free-text (codex r6-F4)
    STALE = "stale"
    SOURCE_UNAVAILABLE = "source_unavailable"
    OPERATOR_INPUT_MISSING = "operator_input_missing"
    NON_FINITE = "non_finite"
    MALFORMED_BAND = "malformed_band"
    FUTURE_AS_OF = "future_as_of"
    MISSING_INDICATOR = "missing_indicator"
    DUPLICATE_INDICATOR = "duplicate_indicator"
    # codex r10: `empty_registry` is NOT a per-indicator reason — an empty baseline is a RUN-level
    # terminal error (check_registry raises; NO artifact is emitted; the run exits nonzero).


# CODE-owned registry (spec §7c, codex r7-F1): indicator -> its DECLARED source string. The
# emitted record's `source` must equal this exactly (no smuggled content). REQUIRED_INDICATORS
# derives from it — one source of truth, NOT in the baseline file it validates.
SOURCE_REGISTRY = {
    "pr_landings_annual": "IRCC PR admissions by CMA (open.canada.ca monthly CSV)",
    "temp_resident_stock": "StatCan NPR estimates 17-10-0121 family (or IRCC TR tables)",
    "isq_edition_watch": "ISQ Perspectives demographiques edition watch (slug/pin)",
    "registre_foncier_volume": "Registre foncier monthly transfer counts (operator-supplied)",
    "cmhc_senior_sale_5yr": "CMHC senior-sale rate refresh (operator-supplied)",
    "natural_increase_sign": "ISQ compo natural-increase sign, annual release (operator-supplied)",
}
REQUIRED_INDICATORS = frozenset(SOURCE_REGISTRY)

# UNKNOWN-branch nullability (codex r7-F2/r8-F2): current_value + as_of are NULL exactly for these
# reasons (no honest measurement; a non_finite raw value goes to the run log, never the JSON).
#
# `DUPLICATE_INDICATOR` BELONGS HERE FOR THE SAME REASON THE OTHER FOUR DO, and its absence was a
# CONTRACT-vs-PRODUCER seam: `check_registry` emits its duplicate record with `current_value=None`
# and `as_of=None` — because a duplicated key names no honest measurement either — and that record
# then FAILED `assert_tripwire_record_valid`'s non-null branch. Latent rather than live (nothing in
# the run emits a duplicate today), which is exactly what let it ship: the two halves disagreed and
# no test crossed them. `test_a_duplicate_record_from_the_producer_validates` is that crossing.
NULLABLE_REASONS = frozenset({
    Reason.SOURCE_UNAVAILABLE, Reason.OPERATOR_INPUT_MISSING, Reason.MISSING_INDICATOR,
    Reason.NON_FINITE, Reason.DUPLICATE_INDICATOR})

TRIPWIRE_RECORD_REQUIRED = frozenset(
    {"indicator", "current_value", "source", "as_of", "band_low", "band_high", "status"})
# THE REQUIRED SET STAYS CLOSED; the OPTIONAL set gains spec amendment #21's two declarations.
# `freshness_years` is the freshness axis' own declaration — move it and a landed indicator's
# emitted `status` can flip (STALE to FRESH, a band verdict to UNKNOWN) while `assumptions_hash`
# and `data_vintage` stay byte-identical, because neither token covers it and, until this
# amendment, no emitted field showed it. It ships INERT here (all six indicators are
# structurally UNKNOWN, so no freshness comparison is evaluated at all) and that is the point:
# the declaration becomes checkable BEFORE the work that makes it load-bearing. `schema_version`
# does NOT bump — both are optional (amendment #20(C0)).
_OPTIONAL = {"reason", "freshness_years", "source_kind"}


@dataclass(frozen=True)
class TripwireSpec:
    indicator: str
    band_low: float
    band_high: float
    as_of: int
    freshness_years: int
    # COVERAGE DECLARATION (wired/operator), and since spec amendment #21 (2026-08-22) it is
    # EMITTED — in the row it governs, as its declared STRING and never the enum repr. It was
    # internal, and that left the identity ledger's own exclusion argument unsound: run 49 ruled
    # `TRIPWIRE_BANDS` out of `assumptions_hash` because its endpoints ARE published per row
    # ("a move announces itself in the diff") and ruled the DECLARATIONS out on the same ledger
    # while they were published nowhere. Publishing makes that argument true for both.
    source_kind: SourceKind


@dataclass(frozen=True)
class TripwireResult:
    indicator: str
    current_value: float | None
    source: str               # DECLARED source string (bound to SOURCE_REGISTRY), never SourceKind
    as_of: int | None
    band_low: float
    band_high: float
    status: Status
    reason: Reason | None = None
    # THE SPEC'S OWN DECLARATIONS, CARRIED THROUGH FROM THE SPEC RATHER THAN RE-DERIVED
    # (amendment #21). `None` is the shape a SYNTHETIC result has — `check_registry`'s
    # missing/duplicate records are built from a name alone and have no spec behind them — and
    # both members are OPTIONAL in the emitted record, so a synthetic result publishes neither
    # rather than inventing a declaration nothing declared.
    freshness_years: int | None = None
    source_kind: SourceKind | None = None


def _band_endpoints(indicator: str, band_low, band_high) -> tuple[float, float]:
    """Coerce the caller's band, or refuse in the module's own taxonomy. TWO named
    terminals, both deterministic and independent of the data, because both defects are the
    CALLER's and neither endpoint can ride the record.

    NON-COERCIBLE. A str endpoint used to reach `spec.band_low > spec.band_high` and die
    with `TypeError: '>' not supported between str and float` — a class no caller's handler
    catches, so the verification gate CRASHED rather than refused. It cannot become an
    UNKNOWN either: the endpoints ride the record's float-typed band fields, so a str
    endpoint has nowhere to go (review finding F2).

    NON-FINITE — the SAME defect one coercion later, and the shipped tree sent it down the
    opposite path (run-33 data gate F2). `evaluate_indicator` returned UNKNOWN
    (`malformed_band`) carrying ±Inf/NaN in `band_low`/`band_high`, and
    `assert_tripwire_record_valid` below REFUSED exactly that record — four of the five
    malformed-band sub-cases died at the contract boundary with a bare serialization
    ValueError and NO baseline at all, where §7c wants that indicator UNKNOWN and the other
    five still evaluated and emitted. §7 serializes this JSON with `allow_nan=False`, so a
    non-finite endpoint cannot ride those fields any more than a str can, and the band is
    INJECTED by the caller — a caller/config defect, which is the shape of a run-level
    terminal rather than of a per-indicator UNKNOWN.

    THE FINITE INVERSION (`lo > hi`) IS DELIBERATELY NOT HERE. It is serializable, it rides
    the record honestly, and §7c's "inverted band ⇒ UNKNOWN" governs it — see
    `evaluate_indicator`."""
    try:
        lo, hi = float(band_low), float(band_high)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"tripwire band for {indicator!r} must be two real numbers, got "
            f"({band_low!r}, {band_high!r}) — a band endpoint that is not a float cannot "
            "ride the record's band_low/band_high fields") from exc
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise ValueError(
            f"tripwire band for {indicator!r} must be two FINITE real numbers, got "
            f"({band_low!r}, {band_high!r}) — a non-finite endpoint makes BOTH boundary "
            "comparisons False (every value reads as within-band) and cannot ride the "
            "record's band_low/band_high fields, which §7 serializes with allow_nan=False")
    return lo, hi


def _src(indicator: str) -> str:
    return SOURCE_REGISTRY.get(indicator, "<unregistered>")


def _unknown_nullable(spec: TripwireSpec, reason: Reason) -> TripwireResult:
    # nullable-reason branch: no honest measurement -> current_value AND as_of null. The two
    # DECLARATIONS still ride: they say what this indicator is governed by, not what it measured,
    # and an UNKNOWN row is exactly where a reader needs to see the coverage class (amendment #21).
    return TripwireResult(spec.indicator, None, _src(spec.indicator), None,
                          spec.band_low, spec.band_high, Status.UNKNOWN, reason,
                          freshness_years=spec.freshness_years, source_kind=spec.source_kind)


def _unknown_measured(spec: TripwireSpec, v: float, reason: Reason) -> TripwireResult:
    # a real (finite) measurement exists but is stale/future/malformed -> keep value + as_of.
    return TripwireResult(spec.indicator, v, _src(spec.indicator), spec.as_of,
                          spec.band_low, spec.band_high, Status.UNKNOWN, reason,
                          freshness_years=spec.freshness_years, source_kind=spec.source_kind)


def evaluate_indicator(spec: TripwireSpec, current_value, available: bool, now: int) -> TripwireResult:
    # THE COERCED BAND IS THE ONE THAT RIDES THE RECORD (run-33 stress gate F4). The
    # endpoints were coerced here and every constructor below then re-read the RAW
    # `spec.band_low`/`spec.band_high`, so a coercible-STRING band verdicted OK on the
    # `demoflow tripwires` listing path (six OK, exit 0) while the emit path CRASHED on the
    # record this same function had just built — two verification paths disagreeing about
    # one input, and the GREEN one is the cheap one. Rebuilding the spec from the coerced
    # endpoints is what `evaluate_pr_landings` already does with its `year_spec`.
    lo, hi = _band_endpoints(spec.indicator, spec.band_low, spec.band_high)
    spec = replace(spec, band_low=lo, band_high=hi)
    if not available:
        return _unknown_nullable(spec, Reason.SOURCE_UNAVAILABLE)
    if current_value is None:
        return _unknown_nullable(spec, Reason.OPERATOR_INPUT_MISSING)
    try:
        v = float(current_value)
        if not math.isfinite(v):
            raise ValueError
    except (TypeError, ValueError):
        return _unknown_nullable(spec, Reason.NON_FINITE)   # raw value -> run log, NEVER the JSON
    if spec.as_of > now:
        return _unknown_measured(spec, v, Reason.FUTURE_AS_OF)
    # VALUE INTEGRITY APPLIES TO THE BAND, NOT ONLY TO THE VALUE (review finding F2). An
    # INVERTED band admits no value at all and would otherwise read as an ordinary
    # comparison, so §7c rules it UNKNOWN — and the record carries its two FINITE endpoints
    # honestly. Its NON-FINITE sibling is NOT judged here: `_band_endpoints` raises a
    # run-level terminal on it, because an endpoint the artifact cannot serialize is not a
    # threshold and has nowhere to ride (run-33 data gate F2). The reason token is unchanged
    # and the enum stays spec-closed: a new member would be fork-class.
    if lo > hi:
        return _unknown_measured(spec, v, Reason.MALFORMED_BAND)
    if now - spec.as_of > spec.freshness_years:
        return _unknown_measured(spec, v, Reason.STALE)
    status = Status.CROSSED if (v <= lo or v >= hi) else Status.OK
    return TripwireResult(spec.indicator, v, _src(spec.indicator), spec.as_of,
                          spec.band_low, spec.band_high, status, None,
                          freshness_years=spec.freshness_years, source_kind=spec.source_kind)


def check_registry(indicators: list[str]) -> list[TripwireResult]:
    """Synthetic UNKNOWN results for completeness violations (missing/duplicate) — drive the
    EXIT CODE (not emitted as JSON records in the normal path). Empty list => registry complete.

    `required` is NOT a parameter. It was a caller-overridable default on the one function
    whose entire premise is that the required set is CODE-owned and not co-deletable —
    `check_registry(['x'], required=frozenset({'x'}))` returned "complete" (review finding F4).

    TWO RUN-LEVEL TERMINALS, both raising rather than returning a record, and for the same
    reason: the per-indicator reason enum is spec-closed and carries no token for either.
    An EMPTY registry has nothing to attach an UNKNOWN to (codex r10). An UNREGISTERED key
    is not a failing indicator at all — spec §7c asks for exact-key EQUALITY against the
    code-owned set, and `required - set(indicators)` is one-directional, so an extra key
    rode through as "complete" and, if OK, carried the run to exit 0."""
    out: list[TripwireResult] = []
    if not indicators:
        # RUN-level terminal (codex r10): no artifact emitted; the run exits nonzero.
        raise LoaderError("empty tripwire registry — NO artifact emitted, run exits nonzero")
    unregistered = sorted(set(indicators) - REQUIRED_INDICATORS)
    if unregistered:
        raise LoaderError(
            f"unregistered tripwire indicator(s) {unregistered} — the required set is "
            f"CODE-owned {sorted(REQUIRED_INDICATORS)}; NO artifact is emitted and the run "
            "exits nonzero (an extra key has no token in the closed reason enum)")
    seen: set[str] = set()
    for name in indicators:
        if name in seen:
            out.append(TripwireResult(name, None, _src(name), None, 0.0, 0.0,
                                      Status.UNKNOWN, Reason.DUPLICATE_INDICATOR))
        seen.add(name)
    for missing in sorted(REQUIRED_INDICATORS - set(indicators)):
        out.append(TripwireResult(missing, None, _src(missing), None, 0.0, 0.0,
                                   Status.UNKNOWN, Reason.MISSING_INDICATOR))
    return out


def exit_code(results: list[TripwireResult]) -> int:
    """Verdict-only gate: are ALL the results it was handed OK? It cannot answer the run's
    question, because it never sees which indicators were supposed to be there."""
    return 0 if results and all(r.status is Status.OK for r in results) else 1


def run_exit_code(results: list[TripwireResult]) -> int:
    """The RUN's exit code (spec §7c: "0 only when every code-required indicator is present
    exactly once, finite, fresh, well-banded, and OK").

    Composed on top of `exit_code` rather than folded into it, deliberately. `exit_code`
    ranges over what it is HANDED — one OK result exits 0, however short of the required
    set — and that semantics is pinned by contract above; changing it would silently
    re-verdict every caller. The coverage question is a different question, so it gets its
    own gate: the evaluated indicator multiset must EQUAL the code-owned required set (which
    catches an omission, a duplicate, and an unregistered extra in one comparison), and only
    then does the verdict gate get a say (review finding F4)."""
    evaluated = sorted(r.indicator for r in results)
    if evaluated != sorted(REQUIRED_INDICATORS):
        return 1
    return exit_code(results)


def tripwire_record(r: TripwireResult) -> dict:
    rec = {"indicator": r.indicator, "current_value": r.current_value, "source": r.source,
           "as_of": r.as_of, "band_low": r.band_low, "band_high": r.band_high, "status": r.status.value}
    if r.reason is not None:
        rec["reason"] = r.reason.value
    # `.value`, NEVER the enum: under py3.12 str-Enum `str(SourceKind.WIRED)` is the REPR
    # 'SourceKind.WIRED', so an f-string path would ship a Python repr into the artifact — the
    # same trap `output/rankings.ranking_row` states for the geography position.
    if r.freshness_years is not None:
        rec["freshness_years"] = r.freshness_years
    if r.source_kind is not None:
        rec["source_kind"] = r.source_kind.value
    return rec


def assert_tripwire_record_valid(record: dict) -> None:
    """Contract: exact allowlist; EVERY string-typed position bound (spec §7's general "no
    open string anywhere" rule, not just the one instance the plan body tested); numeric
    fields finite; UNKNOWN-branch nullability (current_value/as_of null IFF a nullable
    reason).

    THE RECORD HAS FOUR STRING-TYPED POSITIONS and the shipped validator bound ONE. `status`
    and `indicator` were free-form, and the `source` binding was CONDITIONAL on the indicator
    being registered — so an unregistered indicator skipped it, and a record that literally
    announces a crash probability passed the validator whose whole job is to make that
    quantity inexpressible (review finding F3). Binding `indicator` to SOURCE_REGISTRY makes
    the source check unconditional as a consequence, which is the actual repair."""
    extra = set(record) - (set(TRIPWIRE_RECORD_REQUIRED) | _OPTIONAL)
    if extra or not set(TRIPWIRE_RECORD_REQUIRED) <= set(record):
        raise ValueError(f"tripwire record fields {sorted(record)} violate allowlist "
                         f"{sorted(TRIPWIRE_RECORD_REQUIRED)}(+reason?); extra={sorted(extra)}")
    reason = record.get("reason")
    if reason is not None and reason not in {r.value for r in Reason}:
        raise ValueError(f"tripwire reason {record['reason']!r} outside closed enum "
                         f"{sorted(r.value for r in Reason)}")
    status = record["status"]
    if status not in {s.value for s in Status}:
        raise ValueError(f"tripwire status {status!r} outside closed enum "
                         f"{sorted(s.value for s in Status)}")
    ind = record["indicator"]
    if ind not in SOURCE_REGISTRY:
        raise ValueError(f"tripwire indicator {ind!r} is not in the CODE-owned registry "
                         f"{sorted(SOURCE_REGISTRY)} — an unregistered indicator skips the "
                         "source binding entirely, reopening the string side-channel")
    if record["source"] != SOURCE_REGISTRY[ind]:
        raise ValueError(f"tripwire source {record['source']!r} != registry-declared "
                         f"{SOURCE_REGISTRY[ind]!r} for {ind}")
    # spec §7 writes the state as `UNKNOWN(reason)`: an UNKNOWN with no reason names no
    # cause, and a CROSSED carrying `stale` is two incompatible verdicts in one record.
    if (status == Status.UNKNOWN.value) != (reason is not None):
        raise ValueError(f"tripwire reason must be present exactly when status=UNKNOWN; "
                         f"status={status!r} reason={reason!r}")
    # §7 emits this JSON with `allow_nan=False`. A non-finite number in ANY numeric field
    # would only be discovered at serialization; the contract boundary is where it dies.
    # AMENDMENT #21's TWO OPTIONAL MEMBERS. `source_kind` is bound by the walk's own table too;
    # `freshness_years` has no string position to bind, so it is typed HERE — the freshness gate
    # is `now - as_of > freshness_years`, and a bool or a float there is a threshold nobody set.
    kind = record.get("source_kind")
    if kind is not None and kind not in {k.value for k in SourceKind}:
        raise ValueError(f"tripwire source_kind {kind!r} outside closed enum "
                         f"{sorted(k.value for k in SourceKind)} — the enum REPR is the shape "
                         "an f-string path ships, and it is not a declared value")
    freshness = record.get("freshness_years")
    if freshness is not None and (isinstance(freshness, bool)
                                  or not isinstance(freshness, int) or freshness < 0):
        raise ValueError(f"tripwire freshness_years {freshness!r} must be a non-negative whole "
                         "number of years — it is compared against `now - as_of`")
    for numeric in ("current_value", "band_low", "band_high"):
        value = record.get(numeric)
        if value is None:
            continue
        # TYPE first, then finiteness. `float("40000")` succeeds, so a coercion-only check
        # lets a STRING ride a numeric field — the same side-channel one position over.
        # `bool` is excluded explicitly: it is an int subclass, and True is not a threshold.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"tripwire {numeric} {value!r} must be a number, not "
                             f"{type(value).__name__}")
        if not math.isfinite(value):
            raise ValueError(f"tripwire {numeric} {value!r} must be a finite number "
                             "(the artifact is emitted with allow_nan=False)")
    nullable = (status == Status.UNKNOWN.value
                and reason in {r.value for r in NULLABLE_REASONS})
    for f in ("current_value", "as_of"):
        if nullable and record.get(f) is not None:
            raise ValueError(f"tripwire {f} must be NULL for status=UNKNOWN reason={reason}")
        if not nullable and record.get(f) is None:
            raise ValueError(f"tripwire {f} must be non-null for status={record['status']} reason={reason}")


# =======================================================================================
# `pr_landings_annual` — the one indicator whose realized value is MEASURED, not typed.
# =======================================================================================
#
# SCOPE. The numerator is the PROVINCIAL sum, because the plan level it is compared against
# is provincial. The Montréal+Québec CMA PAIR is a DIFFERENT QUANTITY and belongs to the
# demand model, not here: measured on the 2026-08-18 vintage the pair is 44,310 (2023) /
# 47,070 (2024) / 45,895 (2025) while the province is 52,615 / 59,225 / 60,010, and the
# pair's provincial share DECAYS 0.842 -> 0.795 -> 0.765, ~4pp/yr. So no fixed offset
# converts one into the other, and the near-match "45,895 ≈ 45,000 plan" is a coincidence of
# mismatched scopes — the pair sits ~24% under the provincial level it appears to match.
# `Not stated` province rows are excluded (admissions not attributable to Québec; measured
# ≤20/yr, inside the rounding envelope below).
#
# ERA. The 45,000 level is the MIFI Plan d'immigration du Québec 2026-2029 (released
# 2025-11-06) and it is a REDUCTION from the ~60k realized under its predecessor. Comparing a
# pre-plan year against it is a cross-era artifact, not a crossing — so only years the plan in
# force GOVERNS are evaluable, and the first of those is 2026 full-year.
PLAN_GOVERNED_YEARS = range(2026, 2030)

# FRESHNESS. Publication lag on this feed runs 1.5-4 months across three measured Wayback
# vintages, so any limit tighter than ~5 months makes the indicator permanently UNKNOWN —
# a gate that can never clear is not a gate. Five months admits the measured lag and still
# discriminates an abandoned mirror.
FEED_FRESHNESS_MONTHS = 5

# COMPLETENESS. TWELVE DISTINCT MONTHS on the selected year (the loader's closed month
# vocabulary is what makes "distinct" mean something) kills the partial-year false-CROSSED:
# six months of 2026 sum to 21,720 against a 40k-50k band, a crash headline manufactured by a
# publication calendar.
#
# IT DOES NOT, ON ITS OWN, KILL MEMBER GAPS — the earlier claim that it did was wrong and is
# corrected here. `set(province_rows[EN_MONTH])` is a UNION over every member, satisfied by
# two members alone: measured on the frozen slice, real 2025 has 355 of a 384-cell grid with
# 11 of 32 members carrying interior gaps, and the province still shows twelve distinct
# months. Drop Montréal's Jan-May and the year counts CLOSED at 46,640 — status OK, exit 0,
# against a true 60,010 that is CROSSED. So coverage is checked PER MODELED MEMBER as well,
# against the code-owned `MODELED_CMAS`. That rule is clearable (both modeled members are
# 12/12 in the real data) where a whole-province "every member 12/12" rule never would be.
#
# THIRD CLAUSE — MEMBER-SET COMPLETENESS (Ruling U, seat 2026-08-18). The two rules above
# verify MONTH presence and never MEMBER coverage, so the same scope confusion the SCOPE
# block above exists to prevent re-entered through a DATA path instead of a literal: truncate
# the feed to the two `MODELED_CMAS` and both rules pass, the year closes, and 45,895 over 24
# cells — the Montréal+Québec CMA PAIR — is published wearing the province's name against a
# true provincial 60,010. A year is therefore CLOSED only when, in addition, every member of
# the code-owned `QUEBEC_REQUIRED_CMAS` is PRESENT in that province-year. The derivation, the
# `<=`-not-`==` direction and the rejected threshold live beside the constant in `ircc.py`.
#
# PRESENCE, NOT 12/12, for the non-modeled members — and this is the NAMED RESIDUAL. The bar
# is >= 1 cell in the year, because 11 of 32 members carry interior month gaps in the real
# 2025 data (Hawkesbury missing 9 of 12, Lachute 4, Sainte-Marie 3, Dolbeau-Mistassini 3,
# Sainte-Agathe 3, Cowansville 2, five others 1). A whole-province "every member 12/12" rule
# would never clear, and a gate that can never clear is not a gate — `FEED_FRESHNESS_MONTHS`
# makes the same argument one constant down. A `--` COUNTS as presence, as it does for the
# month rules: suppression is a published statement about a cell.
#
# THE ASSUMPTION THAT BAR RESTS ON, STATED AS AN ASSUMPTION: that an unpublished month means
# ZERO landings rather than missing data — the feed publishing `--` for 1-5 and omitting true
# zeros. That is the SEAT'S READING of IRCC publication behaviour, NOT a documented IRCC
# statement, and it is recorded here so a reader can re-test it rather than inherit it. If it
# is false, an interior gap hides landings and the annual sum is low by an unknown amount.
#
# WHAT THE TWO SHIPPED RULES ALSO MISSED, and this clause catches: dropping a SINGLE
# non-modeled member leaves them closing every year — measured, Saguenay dropped publishes
# 59,335 against a true 60,010. A VALUE-INTEGRITY breach, not a verdict change: measured at
# the (55000, 65000) probe band the drop moves NO year's verdict, deltas running -60 to -675,
# so no band comparison could ever have caught it. The member-set clause is what refuses it,
# and it refuses a RENAME on the same footing.
MONTHS_PER_CLOSED_YEAR = len(EN_MONTHS)

# DEGENERATE FLOOR. A suppressed cell is `--`, which absorbs the whole 0-5 band; the feed has
# NO zeros, so `--` must never be read as one. Two floors follow, both DERIVED from the feed's
# own arithmetic rather than tuned: a member that reports nothing but markers contributes an
# unknown, not a zero (an all-marker Montréal drops the provincial sum 62% and the CMA pair
# 81% — comfortably CROSSED, on a feed that measured nothing), and a total no larger than what
# the suppressed cells alone could carry is indistinguishable from silence.
SUPPRESSED_CELL_MAX = 5.0
# TOTAL is rounded to the nearest 5 (0 of 16,539 numeric cells are non-multiples), so every
# PUBLISHED cell carries ±2.5 — recorded and never silently corrected. It applies to the
# numeric cells alone: a `--` publishes no number to round, and what IT contributes is the
# one-sided [0, SUPPRESSED_CELL_MAX] the constant above already states. See
# `RealizedLandings.interval`, which is where the two legs are combined.
CELL_ROUNDING_HALFWIDTH = 2.5

PR_LANDINGS_INDICATOR = "pr_landings_annual"
# QUEBEC_PROVINCE and QUEBEC_REQUIRED_CMAS are the LOADER's (imported above, beside
# MODELED_CMAS): they are selection-key vocabularies into the feed, so the schema module that
# refuses a drifted token has to own them. Only QUEBEC_PROVINCE is RE-EXPORTED — this module
# is where its consumers read it. QUEBEC_REQUIRED_CMAS is imported for this module's OWN gate
# and nothing reads it off here; its consumers go to the loader, which is the direction
# finding F6 settled and the direction the constant's derivation comment lives in.


@dataclass(frozen=True)
class RealizedLandings:
    """What the feed actually says for one (province, year) — the arithmetic, plus the
    facts the gates need to judge whether it is honest. Never a verdict."""

    year: int
    province: str
    value: float
    months: tuple[str, ...]
    n_cells: int
    n_numeric: int
    n_suppressed: int
    numeric_by_member: dict = field(default_factory=dict)

    @property
    def interval(self) -> tuple[float, float]:
        """The honest bound on the annual total — ASYMMETRIC, because its two legs are
        different arithmetic (quant gate F3 / stress gate F9).

        ROUNDING is two-sided and applies to PUBLISHED cells ONLY: TOTAL is rounded to the
        nearest 5, so each of `n_numeric` cells carries ±CELL_ROUNDING_HALFWIDTH.

        SUPPRESSION IS ONE-SIDED. A `--` contributes 0 to `value`, and its true contribution
        lies in [0, SUPPRESSED_CELL_MAX] — it can only ADD. The shipped property published a
        symmetric ±2.5·n_cells and its docstring called that "±(rounding + suppression)",
        which centred the interval 2.5·n_suppressed BELOW the arithmetic and understated the
        upper end by the same amount: measured on the committed 2025 Québec slice (355
        cells, 304 numeric, 51 suppressed, value 60,010) it published ±887.5 =>
        [59,122.5, 60,897.5] where the arithmetic is [59,250.0, 61,025.0].

        THE STRONGEST ARGUMENT IS INTERNAL: `_degenerate` one screen down already models the
        suppressed cell correctly one-sided, as `SUPPRESSED_CELL_MAX * n_suppressed`, so the
        symmetric envelope contradicted its own neighbour one constant away."""
        rounding = CELL_ROUNDING_HALFWIDTH * self.n_numeric
        return (self.value - rounding,
                self.value + rounding + SUPPRESSED_CELL_MAX * self.n_suppressed)


@dataclass(frozen=True)
class PRLandingsEvaluation:
    """`result` is the only thing that may reach the artifact. `realized` and
    `vintage_sha256` ride the RUN, for the identity envelope (spec §7 puts data_vintage
    above the rows — the tripwire record's field allowlist is closed and cannot carry it).
    `log` is run-log detail: the record is a closed vocabulary, so every cause narrower
    than the reason token is spoken here or nowhere."""

    result: TripwireResult
    realized: RealizedLandings | None
    vintage_sha256: str | None
    log: str


def _province_rows(frame, year: int, province: str):
    return frame[(frame[YEAR_COLUMN] == str(year)) & (frame[PROVINCE_COLUMN] == province)]


def pr_landings_realized(frame, year: int, province: str = QUEBEC_PROVINCE) -> RealizedLandings:
    """Sum the province's published cells for one year. A `--` contributes NOTHING to the
    value and ONE to `n_suppressed` — it is an unknown in 0-5, and the difference between
    those two treatments is the whole degenerate-feed defence."""
    rows = _province_rows(frame, year, province)
    value = 0.0
    n_numeric = n_suppressed = 0
    numeric_by_member: dict[str, int] = {}
    for member, total in zip(rows[CMA_COLUMN], rows[TOTAL_COLUMN]):
        numeric_by_member.setdefault(member, 0)
        if total == SUPPRESSED:
            n_suppressed += 1
            continue
        value += float(int(total))          # loader has already closed TOTAL's vocabulary
        n_numeric += 1
        numeric_by_member[member] += 1
    months = tuple(sorted(set(rows[MONTH_COLUMN]), key=MONTH_INDEX.__getitem__))
    return RealizedLandings(year=year, province=province, value=value, months=months,
                            n_cells=len(rows), n_numeric=n_numeric, n_suppressed=n_suppressed,
                            numeric_by_member=numeric_by_member)


def _missing_required(rows) -> list[str]:
    """Required members with NO cell at all in this province-year, sorted.

    ONE helper, called by BOTH the gate and the run-log discriminator. If the two computed
    membership independently they would drift, and a discriminator that disagrees with the
    gate it explains is a new defect class, not a smaller one."""
    return sorted(QUEBEC_REQUIRED_CMAS - set(rows[CMA_COLUMN]))


def _months_are_the_closed_vocabulary(rows) -> bool:
    """Does this province-year's month column carry EXACTLY the twelve closed tokens?

    EQUALITY AGAINST THE VOCABULARY, never a count of distinct values — twelve DISTINCT tokens
    is not twelve MONTHS. The threat is a directly-constructed frame and nothing else:
    `ircc._check_periods` refuses an unrecognized month token at LOAD, so no frame carrying one
    can arrive through the loader. `closed_plan_years` is importable, and a caller that hands it
    a frame assembled anywhere else — a fixture, a notebook, a future in-memory splice — must
    still be refused rather than counted.

    IT IS ITS OWN FUNCTION BECAUSE THE RULE IS NOT OBSERVABLE THROUGH `closed_plan_years`.
    The per-modeled-member clause below demands `by_member[m] == set(EN_MONTHS)` for both
    `MODELED_CMAS`, which already forces the province-wide union to CONTAIN all twelve tokens;
    on any frame that satisfies it, `len(set(months)) == 12` and `set(months) == set(EN_MONTHS)`
    agree on every input. A bare-count rewrite is therefore an EQUIVALENT MUTANT at the
    function's boundary and no black-box test of `closed_plan_years` can kill it — measured,
    and it is why the test that claimed to defend this rule was passing on the member clauses
    instead. Handed the rows directly, the rule is killable; wired in above, its WIRING is
    killable (an extra token on a non-modeled member reds a year every other clause accepts).
    """
    return set(rows[MONTH_COLUMN]) == set(EN_MONTHS)


def closed_plan_years(frame, province: str = QUEBEC_PROVINCE) -> list[int]:
    """Years the plan in force GOVERNS that the feed has CLOSED. THREE rules, all required:
    all twelve month tokens present province-wide; all twelve present for each MODELED
    member; and every member of `QUEBEC_REQUIRED_CMAS` present with at least one cell
    (`REQUIRED <= present` — a SUBSET test, so a delineation addition still closes while a
    removal or rename reds). A partial year is not a small year; it is not a year, and
    neither is a year missing half of Montréal, nor a province that has lost 29 of its 31
    members and is quietly reporting a two-CMA total under the province's name.

    `MODELED_CMAS` and `QUEBEC_REQUIRED_CMAS` are both Quebec-shaped, so `province` is a
    selection key here, not a genericity claim — the same scope the module has carried since
    `QUEBEC_PROVINCE` became its default.

    A `--` cell COUNTS as present: suppression is a published statement about a cell, and
    what an all-marker member means is the degenerate floor's question, not this one."""
    closed = []
    for year in PLAN_GOVERNED_YEARS:
        rows = _province_rows(frame, year, province)
        if not _months_are_the_closed_vocabulary(rows):
            continue
        if _missing_required(rows):
            continue
        by_member: dict[str, set] = {}
        for member, month in zip(rows[CMA_COLUMN], rows[MONTH_COLUMN]):
            by_member.setdefault(member, set()).add(month)
        if all(by_member.get(m, set()) == set(EN_MONTHS) for m in MODELED_CMAS):
            closed.append(year)
    return closed


def _member_set_note(frame, province: str) -> str:
    """Run-log text NAMING member-set truncation, or ''.

    CALLED ON EVERY PATH THAT HAS A FRAME, not only where no year closed. It ranges over the
    WHOLE plan era, so it speaks about years the evaluated one does not cover — a 2027 losing
    members while 2026 is closed and verdicted is exactly the state the empty-years-only wiring
    could not report.

    The reason enum is spec-closed and CORRECTLY stays closed, so a gutted feed surfaces as
    `source_unavailable` exactly like a pre-era refusal does. Without this line a reader
    cannot tell "IRCC has not published 2026 yet" from "the feed lost 29 of its 31 members",
    and those call for opposite actions. `PRLandingsEvaluation.log` is where every cause
    narrower than the reason token is spoken.

    THREE STATES per plan-governed year, and what separates them is which CLAIM the line has
    EARNED. The header names the suspicion; the certainty is attached PER YEAR, because a
    mixed feed (one year gutted at a full calendar, the next partial) owes different claims
    to each.

    1. The FRAME carries no rows for the year at all — nobody has published it. Silent: that
       is the pre-era case, and calling all 31 members 'absent' there is the same scope
       confusion pointed the other way.
    2. The frame carries the year for OTHER PROVINCES while this province has ZERO rows — the
       maximal truncation, and the one a member-by-member note would miss, since with no rows
       there is no member to call absent. The year's presence elsewhere is the proof it is not
       publication order, so the categorical claim is EARNED and the other-province row count
       is quoted as its evidence.
    3. The province has rows and required members are missing. The gap is always REPORTED —
       silence would hide a truncation arriving mid-year, the shape one would arrive in today
       while 2026 is 6 months deep. The CAUSE is claimed only at TWELVE of twelve months,
       where the publication calendar is exhausted as an explanation. Below twelve it is
       withheld, because IRCC genuinely fills its member set over a year's first months:
       measured on this repo's committed 2025 Quebec bytes, 24 of the 31 required members had
       reported after Jan, 29 after Feb, 30 after Mar and Apr, and 31 only from May. A line
       that called that state truncation would be asserting something false about the feed."""
    notes = []
    for year in PLAN_GOVERNED_YEARS:
        rows = _province_rows(frame, year, province)
        if rows.empty:
            n_elsewhere = len(frame[frame[YEAR_COLUMN] == str(year)])
            if not n_elsewhere:
                continue                                   # state 1: pre-era, and silent
            notes.append(                                  # state 2
                f"{year}: {province} has NO rows at all while the feed publishes "
                f"{n_elsewhere} rows for other provinces that year — the WHOLE member set is "
                f"absent, and the year's presence elsewhere is why publication order "
                f"cannot explain it")
            continue
        missing = _missing_required(rows)
        if missing:                                        # state 3
            n_months = len(set(rows[MONTH_COLUMN]))
            verdict = (" — the calendar is COMPLETE, so publication order cannot explain it"
                       if n_months == MONTHS_PER_CLOSED_YEAR else
                       " — a PARTIAL year, where publication ORDER also produces member "
                       "absences, so the gap is reported and its cause is NOT claimed")
            notes.append(
                f"{year}: {len(missing)} of {len(QUEBEC_REQUIRED_CMAS)} required {province} "
                f"members absent (e.g. {missing[:3]}) at {n_months} of "
                f"{MONTHS_PER_CLOSED_YEAR} months published" + verdict)
    if not notes:
        return ""
    return (" MEMBER-SET TRUNCATION SUSPECTED — " + "; ".join(notes)
            + ". A province-wide month count is a UNION over members and cannot see this.")


def _degenerate(realized: RealizedLandings) -> str | None:
    """Run-log token naming why this realized value is silence rather than a measurement,
    or None. Every branch is derived from the feed's suppression semantics."""
    if realized.n_numeric == 0:
        return f"no numeric cell in {realized.province} {realized.year} " \
               f"({realized.n_suppressed} suppressed) — `--` is not a zero"
    for member in MODELED_CMAS:
        if realized.numeric_by_member.get(member, 0) == 0:
            return (f"modeled member {member!r} reports no numeric cell in {realized.year} — "
                    "present in the feed but all-marker; presence is not content")
    floor = SUPPRESSED_CELL_MAX * realized.n_suppressed
    if realized.value <= floor:
        return (f"realized {realized.value} is inside what suppression alone could carry "
                f"({realized.n_suppressed} cells x {SUPPRESSED_CELL_MAX} = {floor})")
    return None


def _months_behind(latest: tuple[int, int], now: tuple[int, int]) -> int:
    return (now[0] - latest[0]) * 12 + (now[1] - latest[1])


def evaluate_pr_landings(
    landings: PRLandings,
    *,
    band: tuple[float, float],
    now: tuple[int, int],
    freshness_years: int = 1,
    source_kind: SourceKind = SourceKind.WIRED,
) -> PRLandingsEvaluation:
    """Evaluate realized PR landings against a CALLER-SUPPLIED band, fail-safe throughout.

    GATE ORDER, and it is load-bearing — each stage can only be reached once the previous
    one has established that a number worth judging exists:

      1. feed absent                      -> UNKNOWN, nothing emitted
      2. no CLOSED plan-governed year     -> UNKNOWN, nothing emitted
      3. degenerate read                  -> UNKNOWN, nothing emitted
      4. feed itself stale (>5 months)    -> UNKNOWN, measurement retained
      5. band comparison (generic gate)   -> OK / CROSSED / UNKNOWN

    Degenerate precedes staleness deliberately: a gutted sum must never ride a record, and
    stage 4 is the one UNKNOWN branch that keeps its value.

    THE MEMBER-SET NOTE RIDES EVERY BRANCH THAT HAS A FRAME, not only the empty-closed-years
    one. Wired into that branch alone, a truncated 2027 standing beside a closed 2026 was never
    named anywhere: `closed_plan_years` drops 2027, `year = max(years)` selects 2026, and the
    run reports an honest verdict on an honest year while the feed quietly loses members in the
    next one. That is not a verdict risk — it is a REPORTING gap, and the note is the only place
    a reader can learn the feed is degrading before the degradation reaches the evaluated year.
    Computed ONCE, from the same frame, and appended to each returning branch: two call sites
    with the same intent drift, and a discriminator that disagrees with itself is a new defect.

    THE REASON TOKEN AT STAGES 1-3 is `source_unavailable`, and the derivation matters
    because the enum is closed and no member says "the era has not arrived". The choice is
    forced by the nullability contract, not by taste. This indicator is DEFINED over a
    closed year the plan in force governs; before 2026 closes, no such datum is published,
    so there is no honest measurement — and the only reasons permitted to emit none are the
    nullable four. `stale` is not among them, so choosing it would force the newest pre-plan
    number (2025 provincial 60,010) into a record whose band comes from the 2026 plan: a
    cross-era pairing one field away from a status token, and misleading precisely because
    that year's OWN plan level was ~60k and it was on target. Refusing with nothing beats
    refusing with a number that reads like a crossing.
    """
    province, indicator = QUEBEC_PROVINCE, PR_LANDINGS_INDICATOR
    band_low, band_high = _band_endpoints(indicator, band[0], band[1])
    # BOTH DECLARATIONS ARRIVE FROM THE CALLER (amendment #21). `source_kind` was hardcoded
    # `SourceKind.WIRED` here while `pipeline._TRIPWIRE_DECLARATIONS` declares the same value one
    # module away — a second declaration site, harmless only while the two agreed, and now
    # PUBLISHED, so a divergence would ship as a coverage claim the declaration does not make.
    spec = TripwireSpec(indicator, band_low, band_high, as_of=now[0],
                        freshness_years=freshness_years, source_kind=source_kind)

    if not landings.available or landings.frame is None:
        return PRLandingsEvaluation(
            _unknown_nullable(spec, Reason.SOURCE_UNAVAILABLE), None, landings.sha256,
            f"IRCC PR feed unavailable: {landings.reason or 'no frame'}")

    # ONE computation, appended to every branch below (see the gate note in the docstring).
    note = _member_set_note(landings.frame, province)

    years = closed_plan_years(landings.frame, province)
    if not years:
        return PRLandingsEvaluation(
            _unknown_nullable(spec, Reason.SOURCE_UNAVAILABLE), None, landings.sha256,
            f"no CLOSED year in the plan era {min(PLAN_GOVERNED_YEARS)}-{max(PLAN_GOVERNED_YEARS)} "
            f"({MONTHS_PER_CLOSED_YEAR} distinct months province-wide AND per modeled member, "
            f"plus all {len(QUEBEC_REQUIRED_CMAS)} required members present); feed "
            f"latest_period={landings.as_of}. Pre-plan years are NOT substitutes." + note)

    year = max(years)
    realized = pr_landings_realized(landings.frame, year, province)
    year_spec = TripwireSpec(indicator, band_low, band_high, as_of=year,
                             freshness_years=freshness_years, source_kind=source_kind)

    degenerate = _degenerate(realized)
    if degenerate is not None:
        return PRLandingsEvaluation(
            _unknown_nullable(year_spec, Reason.SOURCE_UNAVAILABLE), realized, landings.sha256,
            f"degenerate feed read, RAISED to UNKNOWN (never CROSSED): {degenerate}" + note)

    behind = _months_behind(landings.latest_period, now) if landings.latest_period else None
    # A feed dated AHEAD of `now` is an impossible vintage, and the staleness test is signed:
    # only `behind > limit` acted, so a negative `behind` fell straight through to the band
    # comparison with nothing recorded. The generic gate's own `as_of > now` guard is silent
    # here — it sees the SELECTED year, which is in the past (review finding F8). The
    # measurement exists, so this is the value-RETAINING branch; `future_as_of` is not a
    # nullable reason, and a null-valued record under it would fail the nullability contract.
    if behind is not None and behind < 0:
        return PRLandingsEvaluation(
            _unknown_measured(year_spec, realized.value, Reason.FUTURE_AS_OF), realized,
            landings.sha256,
            f"feed latest_period {landings.as_of} is AHEAD of {now[0]:04d}-{now[1]:02d} by "
            f"{-behind} month(s) — an impossible vintage, not a fresh one" + note)
    if behind is not None and behind > FEED_FRESHNESS_MONTHS:
        return PRLandingsEvaluation(
            _unknown_measured(year_spec, realized.value, Reason.STALE), realized, landings.sha256,
            f"feed latest_period {landings.as_of} is {behind} months behind "
            f"{now[0]:04d}-{now[1]:02d} (limit {FEED_FRESHNESS_MONTHS})" + note)

    result = evaluate_indicator(year_spec, realized.value, available=True, now=now[0])
    lo_bound, hi_bound = realized.interval
    return PRLandingsEvaluation(
        result, realized, landings.sha256,
        f"{province} {year} realized={realized.value} in [{lo_bound}, {hi_bound}] over "
        f"{realized.n_cells} cells (rounding +/-{CELL_ROUNDING_HALFWIDTH} on "
        f"{realized.n_numeric} numeric; suppression one-sided [0, +{SUPPRESSED_CELL_MAX}] on "
        f"{realized.n_suppressed}, {len(realized.months)} months); "
        f"band=({band_low}, {band_high})" + note)
