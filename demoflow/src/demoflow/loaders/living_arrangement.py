"""Per-sex living-arrangement rates (spec §5, §11.3; steering ruling A).

Spec §5 partitions private-household persons per (geography, age, SEX) into three
buckets using SEX-SPECIFIC rates:

    Solo_s(a)    = pop_s(a) × living_alone_s(a)
    coupled_s(a) = pop_s(a) × (1 − living_alone_s(a)) × couple_share_s(a)
    Other_s(a)   = pop_s(a) × (1 − living_alone_s(a)) × (1 − couple_share_s(a))

so `couple_share` is CONDITIONAL on not living alone — that conditioning is the spec's
own decomposition, and the two Census members are disjoint by construction ("Persons
living alone" sits under "Persons not in census families"; "Married spouses and
common-law partners" under "Persons in census families"), so the conditional share is
well-defined and ≤ 1.

DERIVATION, NEVER TRANSCRIPTION (steering ruling B): every rate is computed by
`derive_living_arrangement` from the pinned WDS extract `data/living_arrangement_98100134.json`
(StatCan Table 98-10-0134-01). `data/living_arrangement.json` is a BUILD ARTIFACT of
`scripts/gen_living_arrangement.py`, never hand-edited, and
`test_committed_artifact_equals_generator_output` proves the two equal. No living-arrangement
rate is hand-written anywhere in this package — which is what makes steering ruling A's
"couple_share stays EXACTLY as cited" a property of the CODE rather than of a promise.

STALENESS REFUSES AT LOAD (steering ruling L): `load_living_arrangement` checks the
artifact's recorded `_provenance.sha256` against the pins registry on EVERY load and raises
on an absent or mismatched digest. Two independent legs, as in census.py: CI compares
CONTENT (artifact vs a fresh derivation), the load path compares IDENTITY (recorded source
digest vs the pin). Neither subsumes the other.

TWO DIVERGENCES FROM THE PLAN'S TASK-15b BODY, both measured, both reported:

  1. **No `_default` block, and no vitrine fallback path.** The plan gave `living_alone` a
     per-sex fallback to `CONSTANTS["living_alone_vitrine"]` (0.28) for a geography the
     Census cross-tab does not carry. Probe P3 measured `DECISION-FOUND-AT-CMA: YES` — the
     cube resolves BOTH rates for all seven wholly-Québec geographies at 75-84 and 85+, and
     every one of the eight modeled `Geography` members is served from that measurement
     (six directly or by netting, five RA members by an explicit flagged borrow). So the
     fallback branch is unreachable, and an unreachable fallback is not free: it would
     silently serve 0.28 for a malformed artifact cell instead of refusing. Both rates are
     therefore cited-or-raise here. This is STRICTER than spec §11.3, never weaker — §11.3's
     hard requirement is that a missing `couple_share` RAISES, and the vitrine remains the
     documented fallback in `constants.py` (with P3 §4c's direct 0.3091 cross-check inside
     its widened band) should a future geography extension need it.
  2. **Band labels are `75-84` / `85+`, not the plan's `75+` / `85+`.** The plan labelled the
     75–84 band `"75+"`, which reads as "75 and over" and COLLIDES with `census.py`'s `"75+"`
     band, which really is 75–200. Two adjacent loaders whose identically-spelled band means
     different domains is a silent-miscompose waiting to happen, and it also makes steering
     ruling A's "75+ AGGREGATE" ambiguous. Nothing downstream consumes the label yet.

WHAT THIS MODULE DOES *NOT* DO (steering ruling A, so the boundary is explicit): the 0.25
same-age couple-balance gate is GONE — live Census breaches it on 13/21 correct rows (probe
P3 §4b), which refutes its premise. Per-band imbalance is RECORDED here as a source-level
diagnostic in `_provenance`, never a gate. The engine-side hard gates (coupled_s ≥ 0,
coupled_s ≤ its sex pool, and the 75+ aggregate direction) fire on MODELLED counts and raise
`CalibrationError`. The first two fire inside `cohort/init.initialize_households`, on every
cell; the third is AGGREGATE-scoped and fires at `pipeline._standing_stock`'s 75+ slice, through
`pipeline._household_stock`'s `direction_ctx` — named precisely because this list asserted it
fired while it had ZERO production callers until 2026-08-22 (round-3 audit), and a gate list is
the wrong place to be optimistic. The one direction check that lives HERE is a different animal
with a different error class — see `_assert_coupled_direction`.
"""
import json
from collections.abc import Iterable
from pathlib import Path

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256, verify_pin
from demoflow.loaders.validate import assert_fraction

PRODUCT_ID = 98100134
EXTRACT = "living_arrangement_98100134.json"
ARTIFACT = "living_arrangement.json"

# --- cube address (the acquisition script builds coordinates from these NAMES) --------
TOTAL_HOUSEHOLD_TYPE = "Total - Household type of person"
TOTAL_GENDER = "Total - Gender"
MEN, WOMEN = "Men+", "Women+"
# The gender junction. StatCan 2021 publishes 'Men+'/'Women+' (the '+' folds non-binary
# respondents into the two published categories); the model's sex codes are M/F, which is
# also what `geography.SEX_CODE_TO_GENDER` maps the ISQ workbooks onto — so the two sides of
# the eventual pop × rate join speak the same alphabet.
GENDER_MEMBERS = (TOTAL_GENDER, MEN, WOMEN)
_GENDER_TO_SEX = {MEN: "M", WOMEN: "F"}
SEXES = ("M", "F")

ARR_TOTAL = "Total - Census family status and household living arrangements"
ARR_ALONE = "Persons living alone"
ARR_COUPLED = "Married spouses and common-law partners"
ARRANGEMENT_MEMBERS = (ARR_TOTAL, ARR_ALONE, ARR_COUPLED)

# Model band -> (lo, hi, cube member). ONE member each: this cube publishes 75-84 and 85+
# as separate age-group members, so nothing is summed and no band can be silently
# half-populated.
_AGE_BAND_SPEC = (
    ("75-84", 75, 84, "75 to 84 years"),
    ("85+", 85, 200, "85 years and over"),
)
_BAND_LABELS = tuple(label for label, _lo, _hi, _m in _AGE_BAND_SPEC)
AGE_MEMBERS = tuple(member for _l, _lo, _hi, member in _AGE_BAND_SPEC)

_PROVINCE = "Quebec"
_MTL_CMA = "Montréal (CMA), Que."
_QC_CMA = "Québec (CMA), Que."
# The six WHOLLY-QUÉBEC CMAs. This tuple must DENOTE THE SAME TERRITORY as census.py's
# netting set, because the HORS_RMR ownership rate and the HORS_RMR living-arrangement rate
# multiply the same population in the cohort initialization — netting different CMA sets
# would mix two territories inside one product while every factor stayed a plausible
# fraction. The two modules deliberately keep their OWN tuples (the label spellings belong to
# two different upstream products and may drift independently), and
# `test_netted_cma_set_denotes_the_same_territory_as_the_ownership_loader` asserts the
# equality rather than an import enforcing it.
_QC_CMAS = (
    "Drummondville (CMA), Que.",
    _MTL_CMA,
    _QC_CMA,
    "Saguenay (CMA), Que.",
    "Sherbrooke (CMA), Que.",
    "Trois-Rivières (CMA), Que.",
)
SOURCE_GEOGRAPHIES = (_PROVINCE, *_QC_CMAS)

# StatCan names a CMA `"<name> (CMA), <province tags>"`. A WHOLLY-Québec CMA tags exactly one
# province; a cross-border one tags both (", Ont./Que.", ", N.B./Que.") and publishes no
# separable Québec-part row, so it belongs INSIDE the residual, never to the netting set
# (`_CA_CAVEAT`). Verified against the live cube's 166 Geography members 2026-08-08: of the 41
# members carrying "CMA", this pair of tests returns EXACTLY `_QC_CMAS`; Ottawa-Gatineau is
# the only Québec-touching CMA it declines; no member carries stray or non-breaking whitespace
# that would make the tail test miss one.
_CMA_MARK = "(CMA)"
_WHOLLY_QC_TAIL = ", Que."


def _is_wholly_quebec_cma(member_name: str) -> bool:
    """Is this cube Geography member one of the CMAs the residual must net out?"""
    return _CMA_MARK in member_name and member_name.endswith(_WHOLLY_QC_TAIL)


def assert_netted_cma_universe(member_names: Iterable[str],
                               source: str = "the live cube") -> None:
    """ACQUISITION gate: the cube's wholly-Québec CMA universe must BE `_QC_CMAS`.

    `_read_cells`'s geography-set equality gate defends a hand-edited or foreign extract, and
    only that: the puller builds its request set from `SOURCE_GEOGRAPHIES`, refuses any
    coordinate it did not request and refuses any it never got back, so EVERY extract the
    committed acquisition path can produce carries exactly `set(SOURCE_GEOGRAPHIES)`. A CMA
    PROMOTED upstream (a CA becoming a CMA at the next census — Drummondville's own 2021
    history) is therefore never requested and never missed: nothing downstream of the pull can
    observe it. The full member list IS in hand at acquisition, so the fact is checked at the
    one point where it exists.

    Both directions are checked and they mean different things, so the message separates them
    rather than dumping two sorted lists to be diffed by eye.
    """
    live = {name for name in member_names if _is_wholly_quebec_cma(name)}
    expected = set(_QC_CMAS)
    if live == expected:
        return
    arrived, absent = sorted(live - expected), sorted(expected - live)
    raise LoaderError(
        f"{source}: the wholly-Québec CMA universe is not this module's netting set. "
        f"ARRIVED (published upstream, not netted here): {arrived or 'none'}. "
        f"ABSENT (netted here, not published upstream): {absent or 'none'}. "
        "An ARRIVED member is a PROMOTION: it is never requested, so it can never appear in "
        "the extract — it simply stays INSIDE the HORS_RMR residual, silently changing what "
        "HORS_RMR denotes while every rate remains a plausible fraction. Grow BOTH "
        "`living_arrangement._QC_CMAS` and `census._QC_CMAS` (the two must denote ONE "
        "territory) and re-pull. An ABSENT member is a RE-SPELLING of a member that still "
        "exists: fix this tuple alone. Cross-border CMAs (', Ont./Que.') are deliberately not "
        "claimed — they publish no separable Québec-part row and stay inside the residual.")


# RA-level rows are not in this CMA-level cube, so each borrows its parent CMA's COMPUTED
# rates — the same borrow census.py makes for ownership, with the same v0 imprecision
# (understates island, overstates couronne) and the same `borrowed_prior` flag.
_BORROWS_FROM = {
    Geography.MTL_ISLAND_RA06: Geography.MTL_RMR,
    Geography.LAVAL_RA13: Geography.MTL_RMR,
    Geography.LANAUDIERE_RA14_PROXY: Geography.MTL_RMR,
    Geography.LAURENTIDES_RA15_PROXY: Geography.MTL_RMR,
    Geography.MONTEREGIE_RA16_PROXY: Geography.MTL_RMR,
}

# Census random-rounds every published count to a multiple of 5, so |published − true| ≤ 4
# per cell and a three-cell identity (Total-Gender vs Men+ + Women+) can miss by up to 12.
# 15 is the next multiple of the rounding base above that bound. This is a ROUNDING
# tolerance, not a model parameter: it is wide enough that base-5 noise never reds, and
# narrow enough that a mis-resolved gender member (which moves counts by thousands) always
# does. Measured on the committed extract: worst deviation 5 persons.
_ROUNDING_BASE = 5
_GENDER_ADDITIVITY_TOLERANCE = 15

# Spec §5's own reversal bound, reused verbatim — NOT a new threshold. See
# `_assert_coupled_direction`.
_REVERSAL_BOUND = 0.25

_CA_CAVEAT = (
    "HORS_RMR here denotes: Québec outside the six WHOLLY-QUÉBEC CMAs — INCLUDING all Census "
    "Agglomerations AND the Québec side of Ottawa-Gatineau. Ottawa-Gatineau is parented to "
    "Ontario in StatCan's geography and this cube publishes no separable Québec-part row, so "
    "its Québec side is INSEPARABLE here and falls inside the residual. The residual is "
    "COMPUTED (province counts net of the six CMA counts), never a published row — the same "
    "denotation census.py's ownership residual carries, and deliberately so: the two rates "
    "multiply the same population."
)
_ISQ_TERRITORY_NOTE = (
    "TERRITORY MISMATCH INHERITED, NOT RESOLVED HERE: this residual's territory is NOT the "
    "territory of the ISQ HORS_RMR population it will multiply. ISQ's pop-as-rmr-base.xlsx "
    "publishes \"RMR d'Ottawa-Gatineau\" as Québec-part-only, so its literal 'Territoire hors "
    "des RMR' row EXCLUDES the Québec side of Ottawa-Gatineau while this Census residual "
    "INCLUDES it. The magnitudes are measured and recorded ONCE, in census.py's "
    "`_provenance.isq_territory_note` (355,971 persons = 12.99% of the Census residual "
    "territory / 14.93% of the ISQ hors-RMR population, 2021 Référence). Recorded here by "
    "reference rather than re-derived: two independently maintained copies of one measurement "
    "drift, and the rate × population join that must reconcile them is downstream of BOTH "
    "loaders."
)
_ROUNDING_NOTE = (
    "StatCan random-rounds counts to the nearest 5, so the living-arrangement hierarchy does "
    "not reconcile exactly to its totals (probe P3 §5 measured a worst deviation of 10 persons "
    "across 126 identities). Rates are computed directly from the published band counts; no "
    "reconciliation is asserted and no correction is applied. The one identity that IS gated "
    "here — Total-Gender vs Men+ + Women+ — is gated with a rounding tolerance, never exactly."
)


# --- extract reading ------------------------------------------------------------------

def _count(raw: object, ctx: str) -> int:
    """Parse one published count under THIS module's error taxonomy. A bare `int()` leaks
    ValueError — a class no `except LoaderError` catches — on exactly the malformation
    (a blanked or suppressed cell) the gate exists to surface."""
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise LoaderError(f"{ctx}: non-integer person count {raw!r}") from exc
    if value < 0:
        raise LoaderError(f"{ctx}: negative person count {value}")
    return value


_REQUIRED_PULL_FIELDS = ("product_id", "statcan_table", "census_year", "release_time",
                         "pulled_at", "puller", "citation", "universe")

# The only (status, status_code) pair the 126 committed cells carry — measured, not assumed
# (`test_a_cell_the_acquisition_path_did_not_verify_is_refused_at_derivation` asserts it on the
# extract). `status` is the WDS REQUEST status the puller recorded; `status_code` is the DATA
# POINT's own code.
_CELL_STATUS_OK = "SUCCESS"
_CELL_STATUS_CODE_OK = 0


def _check_cell_status(cell: dict, key: tuple, path: Path) -> None:
    """SIBLING OF THE PULLER'S TRAP 2: a cell the acquisition path did not verify REFUSES.

    The puller refuses a cell that came back with an EMPTY `vectorDataPoint`. It does NOT refuse
    a cell that came back WITH a data point but a non-SUCCESS request status, or with a non-zero
    point-level `statusCode` — that cell is written to the extract, and before this gate it
    divided straight into a rate that stayed a plausible fraction (measured 2026-08-08).

    What a non-zero code MEANS is deliberately not decoded here: all 126 committed cells carry
    `SUCCESS` / `0`, so anything else is a cell whose number this package cannot account for —
    which is the reason to refuse rather than to guess a codebook. An ABSENT status refuses too,
    on this module's own `.get`-and-raise precedent (`_verify_artifact_provenance`): an
    unrecorded status is not an all-clear, and it is the more dangerous shape, since a bad status
    announces itself while a missing one is indistinguishable from a verified cell.

    Checked BEFORE the value is parsed: a suppressed cell often carries a blanked value, and
    `_count`'s "non-integer person count" would then send the reader to the number instead of to
    the status that explains it.
    """
    status, code = cell.get("status"), cell.get("status_code")
    if status == _CELL_STATUS_OK and code == _CELL_STATUS_CODE_OK:
        return
    raise LoaderError(
        f"{path.name}: cell {key} records status {status!r} / status_code {code!r}, not "
        f"{_CELL_STATUS_OK!r} / {_CELL_STATUS_CODE_OK} — and it carries a value "
        f"({cell.get('value')!r}) anyway. A value the acquisition path did not verify divides "
        "into a rate that stays a plausible fraction, so it is refused here rather than served: "
        "re-pull the extract and inspect that cell (never hand-fix the value).")


def _check_pull_provenance(payload: object, path: Path) -> dict:
    """The extract must carry the citation and vintage the ARTIFACT will publish.

    The charter carry — "a constant without an anchor is a defect" — applies to a rate table
    as much as to a scalar, and `_provenance` is assembled from these fields. A `.get`-only
    read would ship an artifact whose `citation` and `statcan_table` are `null` while every
    rate stayed correct, which is precisely an uncited rate table. `product_id` is checked
    against this module's own constant so that re-pulling a DIFFERENT cube into this filename
    (and dutifully re-pinning it) surfaces here rather than as plausible numbers.
    """
    pull = payload.get("_pull") if isinstance(payload, dict) else None
    if not isinstance(pull, dict):
        raise LoaderError(f"{path.name}: no `_pull` block — the extract records no citation or "
                          "vintage, so the artifact derived from it would be uncited")
    absent = [f for f in _REQUIRED_PULL_FIELDS if not pull.get(f)]
    if absent:
        raise LoaderError(f"{path.name}: `_pull` is missing {absent} — the artifact publishes "
                          "these verbatim and must not publish them empty")
    # `_count`'s taxonomy argument: a bare int() would leak ValueError on a malformed
    # product id — a class no `except LoaderError` catches.
    if _count(pull["product_id"], f"{path.name} `_pull.product_id`") != PRODUCT_ID:
        raise LoaderError(f"{path.name}: `_pull.product_id` is {pull['product_id']}, expected "
                          f"{PRODUCT_ID} — this extract is not the cited cube")
    return pull


def _read_cells(payload: object, path: Path) -> dict[tuple[str, str, str, str], int]:
    """{(geography, gender, age member, arrangement): count} from the committed extract.

    Duplicate addresses raise: a duplicated or copied cell would otherwise be silently
    absorbed into a rate, and every resulting rate would still be a plausible fraction.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("cells"), list):
        raise LoaderError(f"{path.name}: no `cells` list — this is not a living-arrangement extract")
    cube: dict[tuple[str, str, str, str], int] = {}
    for i, cell in enumerate(payload["cells"]):
        if not isinstance(cell, dict):
            raise LoaderError(f"{path.name}: cells[{i}] is {type(cell).__name__}, expected an object")
        try:
            key = (cell["geography"], cell["gender"], cell["age_group"], cell["arrangement"])
        except KeyError as exc:
            raise LoaderError(f"{path.name}: cells[{i}] is missing the {exc.args[0]!r} address "
                              f"field (keys: {sorted(cell)})") from exc
        if key in cube:
            raise LoaderError(
                f"{path.name}: duplicate cell for {key} — the extract's dimension address is not "
                "unique (row duplicated or payload copied?)")
        _check_cell_status(cell, key, path)
        cube[key] = _count(cell.get("value"), f"{path.name} {key}")

    found = {geo for geo, _g, _a, _m in cube}
    if found != set(SOURCE_GEOGRAPHIES):
        raise LoaderError(
            f"{path.name}: geography set is {sorted(found)}, expected {sorted(SOURCE_GEOGRAPHIES)} "
            "— HORS_RMR nets the province against ALL SIX wholly-Québec CMAs, so an added or "
            "removed geography changes what the residual denotes")
    expected = {(g, s, a, m) for g in SOURCE_GEOGRAPHIES for s in GENDER_MEMBERS
                for a in AGE_MEMBERS for m in ARRANGEMENT_MEMBERS}
    missing = expected - set(cube)
    if missing:
        raise LoaderError(f"{path.name}: {len(missing)} required cells absent, e.g. "
                          f"{sorted(missing)[:3]}")
    return cube


def _assert_gender_additivity(cube: dict, path: Path) -> None:
    """GENDER-JUNCTION gate: Total-Gender ≈ Men+ + Women+ on every published cell.

    Cheap, and it catches the one failure `_assert_coupled_direction` cannot: a member
    resolved to the WRONG gender entirely (e.g. `Total - Gender` read as `Men+` after a cube
    re-index). That failure leaves every rate a plausible fraction and leaves the male/female
    direction intact, so nothing else here would notice. Tolerance is base-5 rounding only.
    """
    for geo in SOURCE_GEOGRAPHIES:
        for age in AGE_MEMBERS:
            for member in ARRANGEMENT_MEMBERS:
                total = cube[(geo, TOTAL_GENDER, age, member)]
                parts = cube[(geo, MEN, age, member)] + cube[(geo, WOMEN, age, member)]
                if abs(total - parts) > _GENDER_ADDITIVITY_TOLERANCE:
                    raise LoaderError(
                        f"{path.name}: gender junction broken at [{geo}, {age}, {member}]: "
                        f"{TOTAL_GENDER}={total:,} vs {MEN}+{WOMEN}={parts:,} "
                        f"(|Δ|={abs(total - parts):,} > {_GENDER_ADDITIVITY_TOLERANCE}, the "
                        f"base-{_ROUNDING_BASE} rounding tolerance) — a mis-resolved gender member?")


def _rates_from_counts(pop: int, alone: int, coupled: int, ctx: str) -> dict[str, float]:
    """living_alone = alone/pop; couple_share = coupled/(pop − alone).

    Every degenerate is named and every guard PRECEDES its division, so a zero or inverted
    denominator surfaces as LoaderError rather than ZeroDivisionError or a nonsense fraction.
    """
    if pop <= 0:
        raise LoaderError(f"{ctx}: non-positive private-household population {pop}")
    if alone > pop:
        raise LoaderError(f"{ctx}: persons living alone {alone} exceed the population {pop}")
    not_alone = pop - alone
    if not_alone <= 0:
        raise LoaderError(f"{ctx}: nobody lives with anyone (pop {pop} − alone {alone} = "
                          f"{not_alone}) — couple_share has no denominator")
    if coupled > not_alone:
        raise LoaderError(f"{ctx}: coupled persons {coupled} exceed the not-living-alone "
                          f"population {not_alone} — the two Census members are not disjoint?")
    return {
        "living_alone": assert_fraction(f"{ctx}.living_alone", alone / pop),
        "couple_share": assert_fraction(f"{ctx}.couple_share", coupled / not_alone),
    }


def _counts_for(cube: dict, geo: str, gender: str, age: str) -> tuple[int, int, int]:
    return (cube[(geo, gender, age, ARR_TOTAL)],
            cube[(geo, gender, age, ARR_ALONE)],
            cube[(geo, gender, age, ARR_COUPLED)])


def _residual_counts(cube: dict, gender: str, age: str) -> tuple[int, int, int]:
    """HORS_RMR = province NET of all six wholly-Québec CMAs, netted COUNT BY COUNT.

    Never a difference of rates (a rate difference is not a rate): each of population,
    living-alone and coupled is netted separately and the division happens afterwards, in
    `_rates_from_counts`, behind its own degenerate guards.
    """
    pop, alone, coupled = _counts_for(cube, _PROVINCE, gender, age)
    for cma in _QC_CMAS:
        c_pop, c_alone, c_coupled = _counts_for(cube, cma, gender, age)
        pop -= c_pop
        alone -= c_alone
        coupled -= c_coupled
    return pop, alone, coupled


def _source_counts(cube: dict) -> dict[str, dict[str, dict[str, tuple[int, int, int]]]]:
    """Per-sex (pop, alone, coupled) for every PUBLISHED geography, in the shape the direction
    gate reads. Keyed by the extract's own geography label, so a reversal reported against one
    names the published row rather than a derived geography that merely contains it."""
    return {label: {sex: {age: _counts_for(cube, label, gender, age) for age in AGE_MEMBERS}
                    for gender, sex in _GENDER_TO_SEX.items()}
            for label in SOURCE_GEOGRAPHIES}


def _assert_coupled_direction(counts: dict, path: Path) -> None:
    """SOURCE-LEVEL direction check on the 75+ aggregate coupled counts.

    NOT the engine's calibration gate, and deliberately a different error class. Spec §5 (as
    amended by steering ruling A) gates MODELLED coupled counts inside the cohort
    initialization and raises `CalibrationError`; this reads the SOURCE and raises
    `LoaderError`, because what it can actually detect is a source/junction defect: if `Men+`
    and `Women+` were transposed anywhere between the cube and this extract, every rate would
    still be a fraction in [0,1], the gender-additivity identity would still hold exactly, and
    the artifact would ship a female living-alone rate as male. At 75+ the male coupled count
    genuinely exceeds the female one everywhere (older men partner younger; women outlive
    men), so a transposition reverses the sign of that difference by 29–33 percentage points
    on the committed extract — far outside the bound below.

    The bound is spec §5's OWN reversal bound (a reversal beyond |Δ|/max > 0.25 at the 75+
    aggregate is the error), reused verbatim: a mild reversal stays tolerated, exactly as the
    spec rules, and no new threshold is introduced here.

    TWO ARMS, fed from one call site: the three DERIVED geographies AND the seven PUBLISHED ones
    (`_source_counts`). The published arm is not redundant, and the hole it closes was measured
    2026-08-08: a transposition confined to ONE SMALL CMA (Drummondville, Saguenay, Sherbrooke,
    Trois-Rivières) passed every gate in this module — the swap is internally consistent so no
    degenerate guard fires, additivity is untouched because the counts merely change sides, and
    one small CMA cannot reverse a province-net residual — while moving the served HORS_RMR
    75-84 Men living_alone rate by up to 0.019 (Saguenay alone: 0.2443 -> 0.2306). The DERIVED
    arm still carries what the published arm cannot see: a reversal created by the netting
    itself. Power is a per-geography measurement (P3 §4 shows M>F at 75+ in every published
    Québec geography, weakest margin Trois-Rivières at 0.2759 — 0.0259 of headroom over the
    bound), pinned in
    `test_the_source_direction_gate_has_measured_power_at_every_published_geography` so a
    re-pull that narrows it reds as lost power instead of going blind.
    """
    for geo, per_sex in counts.items():
        coupled_m = sum(per_sex["M"][age][2] for age in AGE_MEMBERS)
        coupled_f = sum(per_sex["F"][age][2] for age in AGE_MEMBERS)
        if coupled_f <= coupled_m:
            continue
        imbalance = (coupled_f - coupled_m) / coupled_f
        if imbalance > _REVERSAL_BOUND:
            raise LoaderError(
                f"{path.name}: 75+ AGGREGATE coupled-count direction reversed for {geo}: "
                f"coupled_F={coupled_f:,} > coupled_M={coupled_m:,} by |Δ|/max={imbalance:.4f} "
                f"> {_REVERSAL_BOUND} (spec §5 reversal bound). At 75+ the male coupled count "
                f"exceeds the female one in every published Québec geography — a reversal this "
                f"large means the {MEN}/{WOMEN} junction is transposed, not that the population "
                "changed shape.")


def _couple_balance_diagnostic(counts: dict) -> dict:
    """Per-band coupled-count imbalance, RECORDED (steering ruling A), never gated.

    Probe P3 §4b measured live Census breaching the retired 0.25 SAME-AGE band gate on 13 of
    21 correct rows — the breach is real population structure (cross-age coupling), which is
    what spec §5's `Couple(a) = min(coupled_m, coupled_f)` matching plus `max − min → Other`
    absorbs. This is the SOURCE-level profile of that imbalance. It is NOT spec §5's run-
    artifact diagnostic (that one profiles MODELLED counts and belongs to the rankings
    artifact); it is the input-side record that makes the retirement of the gate auditable.
    """
    out: dict = {
        "_what": (
            "Source-level coupled-person counts from the cited cube, per geography × band × "
            "sex, with |Δ|/max. RECORDED, NOT GATED (steering ruling A): per-band imbalance "
            "under the same-age approximation is expected, and the retired 0.25 same-age gate "
            "was refuted by probe P3 §4b (breached on 13/21 correct rows). Distinct from the "
            "run-artifact diagnostic over MODELLED counts. Geographies flagged borrowed_prior "
            "inherit their parent's profile and are not repeated here."),
    }
    for geo, per_sex in counts.items():
        rows = {}
        for label, _lo, _hi, member in _AGE_BAND_SPEC:
            m, f = per_sex["M"][member][2], per_sex["F"][member][2]
            rows[label] = {"coupled_M": m, "coupled_F": f,
                           "imbalance": round(abs(m - f) / max(m, f), 6) if max(m, f) else 0.0}
        m_total = sum(per_sex["M"][member][2] for member in AGE_MEMBERS)
        f_total = sum(per_sex["F"][member][2] for member in AGE_MEMBERS)
        rows["75+"] = {"coupled_M": m_total, "coupled_F": f_total,
                       "imbalance": round(abs(m_total - f_total) / max(m_total, f_total), 6),
                       "direction": "M>=F" if m_total >= f_total else "F>M"}
        out[geo] = rows
    return out


def derive_living_arrangement(extract_path: Path | str) -> dict:
    """Compute the per-sex living-arrangement rate table from the pinned WDS extract.

    The ONLY producer of living-arrangement rates in this package (steering ruling B).
    Verifies the extract against its sha256 pin FIRST — a derivation run on an unpinned or
    drifted vintage would break the PIT chain (live response → committed extract → derived
    rates) while emitting perfectly plausible fractions.
    """
    extract_path = Path(extract_path)
    verify_pin(extract_path, extract_path.name)
    payload = json.loads(extract_path.read_text(encoding="utf-8"))
    pull = _check_pull_provenance(payload, extract_path)
    cube = _read_cells(payload, extract_path)
    _assert_gender_additivity(cube, extract_path)

    # {Geography value: {sex: {age member: (pop, alone, coupled)}}} for the three DERIVED
    # geographies — the residual included, so the direction gate and the diagnostic see it too.
    counts: dict[str, dict[str, dict[str, tuple[int, int, int]]]] = {
        geo.value: {sex: {age: _counts_for(cube, label, gender, age) for age in AGE_MEMBERS}
                    for gender, sex in _GENDER_TO_SEX.items()}
        for geo, label in ((Geography.MTL_RMR, _MTL_CMA), (Geography.QC_RMR, _QC_CMA))
    }
    counts[Geography.HORS_RMR.value] = {
        sex: {age: _residual_counts(cube, gender, age) for age in AGE_MEMBERS}
        for gender, sex in _GENDER_TO_SEX.items()}

    # CELL-level sanity BEFORE the aggregate direction check, and the order is load-bearing:
    # one degenerate published cell (or one that survives netting as a negative residual)
    # reaches the 75+ aggregate as a huge fake reversal, so a direction-first pass reports
    # "the gender junction is transposed" about a cell that is simply malformed — sending the
    # reader to the junction instead of to the count. Measured 2026-08-08 while building the
    # degenerate-count gate.
    rates: dict[str, dict] = {}
    for geo_value, per_sex in counts.items():
        rates[geo_value] = {
            label: {sex: _rates_from_counts(*per_sex[sex][member],
                                            ctx=f"living_arrangement[{geo_value},{label},{sex}]")
                    for sex in SEXES}
            for label, _lo, _hi, member in _AGE_BAND_SPEC
        }
    # Both arms, ONE call site — the ordering above is why. The PUBLISHED rows are merged in
    # only here: `_couple_balance_diagnostic` below profiles the DERIVED counts and nothing else
    # (its scope is asserted), so the merge must not leak into `counts` itself.
    _assert_coupled_direction({**_source_counts(cube), **counts}, extract_path)
    for geo, parent in _BORROWS_FROM.items():
        rates[geo.value] = dict(rates[parent.value], _flag="borrowed_prior")

    missing = [g.value for g in Geography if g.value not in rates]
    if missing:
        raise LoaderError(f"derivation emitted no rates for: {missing} (strict join)")

    return {
        "_provenance": {
            "source": extract_path.name,
            "sha256": WORKBOOK_SHA256[extract_path.name],
            "statcan_table": pull["statcan_table"],
            "product_id": pull["product_id"],
            "ref_date": pull["census_year"],
            "released": pull["release_time"],
            "extracted_at": pull["pulled_at"],
            "derived_by": "demoflow.loaders.living_arrangement.derive_living_arrangement",
            "generator": "demoflow/scripts/gen_living_arrangement.py",
            "acquired_by": pull["puller"],
            "citation": pull["citation"],
            "universe": pull["universe"],
            "measure": (
                "living_alone = `Persons living alone` / `Total - Census family status and "
                "household living arrangements`; couple_share = `Married spouses and common-law "
                "partners` / (total − living alone), CONDITIONAL on not living alone per spec §5's "
                "coupled_s = pop_s × (1 − living_alone_s) × couple_share_s. Both per SEX, at the "
                "`Total - Household type of person` member, Census year 2021."),
            "couple_share_rule": (
                "CITED-OR-RAISE (spec §11.3): couple_share has NO invented default. Every value "
                "here is derived from the cited table above; a cell that carries no couple_share "
                "raises LoaderError at lookup rather than falling back to anything. Values stay "
                "EXACTLY as cited — steering ruling A retired the 0.25 same-age balance gate "
                "rather than calibrate a cited rate away from its source."),
            "living_alone_rule": (
                "Also cited-or-raise here. Spec §11.3's per-sex vitrine fallback (0.28, widened "
                "band [0.24, 0.34], `borrowed_prior`) is MEASURED UNNEEDED: probe P3 landed "
                "DECISION-FOUND-AT-CMA: YES and every modeled geography is served from the cited "
                "cube. The vitrine anchor stays defined in constants.py for a future geography "
                "extension; no code path invents a living_alone rate."),
            "multiplicand_note": (
                "WHAT THESE RATES MAY MULTIPLY — recorded here because getting it wrong is "
                "invisible: the denominators are PRIVATE-HOUSEHOLD persons, so the population "
                "they multiply must ALSO be private-household persons. ISQ's projected "
                "population includes collective/institutional residents, and at 75+ that "
                "population is exactly where collectives concentrate. The initialization must "
                "therefore remove the collective share (CONSTANTS['collective_share_75plus'], "
                "still borrowed_prior — probe P3 §5 states a 75+-SPECIFIC share is NOT derivable "
                "from this cube, which needs total population BY AGE) BEFORE applying these "
                "rates. Applying them to the raw ISQ stock double-counts collective residents "
                "into Solo/Couple/Other; removing the share twice undercounts. RECORDED, NOT "
                "RESOLVED: the join is downstream of this loader."),
            "hors_rmr_method": (
                "Québec-province counts NET of all six WHOLLY-QUÉBEC CMA counts; population, "
                "living-alone and coupled netted separately THEN divided (never a difference of "
                "rates). Same netting and same denotation as census.py's ownership residual."),
            "netted_cmas": list(_QC_CMAS),
            "ca_caveat": _CA_CAVEAT,
            "isq_territory_note": _ISQ_TERRITORY_NOTE,
            "rounding_note": _ROUNDING_NOTE,
            "borrowed_prior": (
                "RA-level members are absent from this CMA-level cube; each reuses its parent "
                "CMA's computed rates and carries `_flag: borrowed_prior` inline (spec §8). All "
                "five borrow MTL_RMR — understates island, overstates couronne (v0), the same "
                "imprecision census.py's ownership borrow carries."),
            "couple_balance_diagnostic": _couple_balance_diagnostic(counts),
        },
        # The borrow flags live INSIDE `rates` because they are part of the table a CONSUMER
        # reads: `load_living_arrangement` returns this sub-tree and nothing else, so a flag
        # recorded only in `_provenance` prose would be invisible to every caller.
        "rates": {geo.value: rates[geo.value] for geo in Geography},
    }


# --- loaders --------------------------------------------------------------------------

def _verify_artifact_provenance(payload: object, path: Path) -> None:
    """STEERING RULING L — always-on load-path staleness check (census.py's shape).

    The no-drift gate proves the COMMITTED artifact equals a fresh derivation, but it is a
    TEST: it defends the repo, not a runtime load. Rates are exactly the payload whose
    wrongness is invisible downstream — every value still a plausible fraction — so identity
    is checked on EVERY load and a failure REFUSES rather than serving.
    """
    expected = WORKBOOK_SHA256.get(EXTRACT)
    if expected is None:
        # `.get` + raise, never a bare subscript: a KeyError is a class no `except LoaderError`
        # catches, so the loudest failure would be the least catchable one.
        raise LoaderError(
            f"{path.name}: no sha256 pin registered for {EXTRACT!r} — the living-arrangement "
            "artifact cannot be checked against its source (PIT chain unpinned)")
    provenance = payload.get("_provenance") if isinstance(payload, dict) else None
    if not isinstance(provenance, dict) or "sha256" not in provenance:
        raise LoaderError(
            f"{path.name}: no `_provenance.sha256` — an artifact that records no source digest "
            "cannot be shown to derive from the pinned extract, so it is indistinguishable from "
            "a hand-authored rate table (steering ruling B) and its rates are refused (ruling L)")
    if provenance["sha256"] != expected:
        raise LoaderError(
            f"{path.name}: STALE living-arrangement artifact — recorded `_provenance.sha256` "
            f"{provenance['sha256']} does not match the pinned {EXTRACT} digest {expected}. "
            "Regenerate with `uv run python scripts/gen_living_arrangement.py`; never hand-edit it.")


def load_living_arrangement(data_dir: Path | None = None) -> dict:
    """Return the per-sex rate table {geography: {band: {sex: {rate: value}}}}.

    STRICT JOIN over every `Geography` member × band × sex: a geography, band or sex that
    went missing must surface HERE, at the file, rather than downstream as a lookup miss on
    one cell that a caller might read as a bad age. Individual RATE keys are deliberately NOT
    checked here — `couple_share`'s absence is spec §11.3's own cited-or-raise condition and
    belongs to the lookup, where the message can name the rule.
    """
    path = (data_dir or DATA_DIR) / ARTIFACT
    if not path.exists():
        raise LoaderError(f"living-arrangement artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Provenance BEFORE the strict join: a stale artifact whose `rates` are also thin would
    # otherwise report a missing-geography error, sending the reader to the geography map
    # instead of to the vintage that is actually wrong.
    _verify_artifact_provenance(payload, path)
    # STRICT key, never `.get("rates", {})`: an absent or renamed top-level key would degrade
    # into an empty table and the strict join below would then report a missing GEOGRAPHY for
    # a fault in the FILE's shape — sending the reader to the geography map instead of to the
    # file. census.py's `load_headship_rates` names and avoids the same degradation.
    if "rates" not in payload:
        raise LoaderError(f"{path.name}: no 'rates' key (keys: {sorted(payload)})")
    rates = payload["rates"]
    for geo in Geography:
        cells = rates.get(geo.value)
        if not isinstance(cells, dict):
            raise LoaderError(f"{path.name}: no living-arrangement rates for {geo.value} "
                              "(strict join)")
        for label in _BAND_LABELS:
            band = cells.get(label)
            if not isinstance(band, dict):
                raise LoaderError(f"{path.name}: {geo.value} carries no {label!r} band "
                                  f"(bands present: {sorted(k for k in cells if k != '_flag')})")
            absent = [sex for sex in SEXES if not isinstance(band.get(sex), dict)]
            if absent:
                raise LoaderError(f"{path.name}: {geo.value} {label} is missing per-sex cells "
                                  f"for {absent} — spec §5 needs SEX-SPECIFIC rates")
    return rates


def _band(age: int) -> str:
    for label, lo, hi, _member in _AGE_BAND_SPEC:
        if lo <= age <= hi:
            return label
    raise LoaderError(f"no living-arrangement band for age {age} (75+ only)")


def _cell(la: dict, geography: Geography, age: int, sex: str) -> tuple[str, dict]:
    """(band label, per-sex cell). The band is returned rather than re-derived by each caller:
    two `_band(age)` calls per lookup is two places for the two to disagree."""
    band = _band(age)
    cells = la.get(geography.value)
    if not isinstance(cells, dict):
        raise LoaderError(f"no living-arrangement rates for {geography.value}")
    cell = (cells.get(band) or {}).get(sex)
    if not isinstance(cell, dict):
        raise LoaderError(f"no living-arrangement cell for {geography.value} {band} {sex!r} "
                          f"(sexes present: {sorted(cells.get(band) or {})})")
    return band, cell


def living_alone_rate(la: dict, geography: Geography, age: int, sex: str) -> float:
    band, cell = _cell(la, geography, age, sex)
    if "living_alone" not in cell:
        raise LoaderError(
            f"living_alone missing for {geography.value} {band} {sex} — every rate in this "
            "table is derived from the cited Census cross-tab (spec §11.3, probe P3 "
            "DECISION-FOUND-AT-CMA: YES); the vitrine fallback is measured unneeded and is NOT "
            "applied silently")
    return assert_fraction(f"living_alone[{geography.value},{band},{sex}]", cell["living_alone"])


def couple_share(la: dict, geography: Geography, age: int, sex: str) -> float:
    band, cell = _cell(la, geography, age, sex)
    if "couple_share" not in cell:
        # NO invented default (spec §11.3): cited-or-raise.
        raise LoaderError(
            f"couple_share missing for {geography.value} {band} {sex} — Census cross-tab or "
            "cited province value required (no invented default, spec §11.3)")
    return assert_fraction(f"couple_share[{geography.value},{band},{sex}]", cell["couple_share"])
