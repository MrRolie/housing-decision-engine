"""Versioned scalar anchors (spec §4). Each carries as_of + source; tripwires compare
realized values against them (Task 28). NO couple_share here (folded §5: per-sex,
cited-or-raise in the living-arrangement loader). collective_share is a documented
anchor, probe-refinable and [0,1]-valid.

CHARTER CARRY, ENFORCED IN CODE: "every constant carries its documented anchor (source +
figure + date); a constant without an anchor is a defect." `Anchor.__post_init__` raises
LoaderError on an empty as_of/source, on a unit violation, on a band that does not bracket
its own central value, and on a flag outside the module's OWN closed anchor-provenance
vocabulary (ANCHOR_FLAGS below — deliberately NOT either of spec §7's emitter enums, which
bind output ROWS, not constants; the discriminator is spelled out there). The plan's module
carried NO assertions — its `collective_share ... asserted ∈[0,1]` contract was tested only
by reading back the literal the plan itself typed, which cannot catch the edit the plan
schedules ("the executor updates collective_share_75plus when P3 lands a firmer figure").

THE UNIT FIELD IS LOAD-BEARING, not decoration (codex r7-F8): fraction-valued anchors bind
[0,1]; the immigrant/non-immigrant ownership RATIO is nonneg-finite only and validly exceeds
1 (P4 measured New Brunswick at 1.033). Defaulting `unit` to "fraction" makes the strict
case the one you get for free — a count anchor must SAY it is a count.

ANTI-PATTERN, recorded so no future reader reaches for it: the POOLED all-immigrant
owned-occupancy ratio is 1.144 (StatCan 36-28-0001, "Housing use of immigrants and
non-permanent residents in ownership and rental markets", 2025-05-28 — immigrants 310 vs
Canadian-born 271 owned units per 1,000). A pooled ratio says arrivals add MORE owners than
natives and DEFEATS the §6 netting; P4 §4b records it as the anti-pattern, never a
candidate. It is deliberately NOT an entry below.
"""
import hashlib
import json
from dataclasses import dataclass

from demoflow.errors import LoaderError
from demoflow.loaders.validate import assert_fraction, assert_nonneg_finite

# ANCHOR-PROVENANCE VOCABULARY — closed, and NOT either of spec §7's emitter enums. §7 declares
# TWO different closed enums for two artifacts: ScenarioPrior rows {borrowed_prior, ra_proxy,
# never_relax_stress} (spec:352-353) and rankings rows {borrowed_prior, ra_proxy,
# closed_cohort_exceedance} (spec:434, third member by steering ruling K). NEITHER emitter may
# import this set, and this set is neither of theirs — each emitter binds its OWN §7 enum.
# Discriminator: an anchor flag says where this VALUE came from; the §7 members omitted here say
# what an output ROW means (ra_proxy = a geography-row caveat, spec:414 RA14/15/16; never_relax_
# stress rides a tilt<1.0 row; closed_cohort_exceedance rides an exceeding geography's rows).
# borrowed_prior is the only provenance caveat, so it is the only legal anchor flag — a second
# member lands loudly (import-time raise) when an anchor needs one, never pre-emptively.
ANCHOR_FLAGS = frozenset({"borrowed_prior"})

_UNIT_VALIDATORS = {
    "fraction": assert_fraction,          # [0, 1]
    "ratio": assert_nonneg_finite,        # nonneg-finite; >1 valid (r7-F8)
    "count": assert_nonneg_finite,        # persons/admissions per year
}


@dataclass(frozen=True)
class Anchor:
    value: object
    as_of: str
    source: str
    band: tuple | None = None
    flag: str | None = None
    unit: str = "fraction"

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, str) or not self.as_of.strip():
            raise LoaderError(f"anchor {self.source!r}: empty as_of — an undated constant is a defect")
        if not isinstance(self.source, str) or not self.source.strip():
            raise LoaderError(f"anchor as_of={self.as_of!r}: empty source — an uncited constant is a defect")
        validate = _UNIT_VALIDATORS.get(self.unit)
        if validate is None:
            raise LoaderError(f"anchor {self.source!r}: unknown unit {self.unit!r} "
                              f"(expected one of {sorted(_UNIT_VALIDATORS)})")
        if self.flag is not None and self.flag not in ANCHOR_FLAGS:
            raise LoaderError(f"anchor {self.source!r}: unknown flag {self.flag!r} "
                              f"(closed anchor-provenance vocabulary {sorted(ANCHOR_FLAGS)}; "
                              f"spec §7's two EMITTER enums are separate and not this set)")

        values = self.value if isinstance(self.value, tuple) else (self.value,)
        for v in values:
            validate(f"anchor[{self.unit}]", v)
        if isinstance(self.value, tuple):
            if len(self.value) != 2 or self.value[0] > self.value[1]:
                raise LoaderError(f"anchor {self.source!r}: band-valued anchor endpoints out of order: {self.value}")

        if self.band is not None:
            if not isinstance(self.band, tuple) or len(self.band) != 2:
                raise LoaderError(f"anchor {self.source!r}: band must be a 2-tuple, got {self.band!r}")
            lo, hi = [validate(f"anchor[{self.unit}]", b) for b in self.band]
            if lo > hi:
                raise LoaderError(f"anchor {self.source!r}: band endpoints out of order: {self.band}")
            if not isinstance(self.value, tuple) and not lo <= float(self.value) <= hi:
                raise LoaderError(f"anchor {self.source!r}: central value {self.value} "
                                  f"outside its own band {self.band}")


CONSTANTS = {
    "cmhc_senior_sale_5yr": Anchor(
        0.36, "2021",
        "CMHC senior-sale rate, 75+, QC (survivor-conditional, 5yr) — the q_live calibration "
        "anchor (spec §5, Invariant I3); the Myers all-cause numbers are NEVER the target"),
    "q_live_annual": Anchor(
        0.085, "2021 (annualized from cmhc_senior_sale_5yr)",
        "Annualized CMHC survivor-conditional sale rate: 1-(1-0.36)^(1/5) = 0.0854 -> 0.085; "
        "band [6%, 11%]/yr per spec §5. UNITS: this anchor is PER YEAR — the 5-year figure it "
        "derives from lives in cmhc_senior_sale_5yr and a tripwire must not compare the two",
        band=(0.06, 0.11)),
    # WRONG-PAPER TRIPWIRE, recorded so the correction does not cost twice: the retention figure
    # is Myers & SIMMONS (Fannie Mae). Myers & RYU, JAPA 74(1) Winter 2008 is a DIFFERENT paper —
    # seller age-structure / senior:working-age ratio +67% (dossier demo_literature.md:26) — and
    # carries NO retention figure. `as_of` stays the dossier's own "~2018": the source was read at
    # one remove, and a precise-but-unsupported date is the smaller version of a wrong citation.
    "myers_retention_envelope": Anchor(
        (0.26, 0.31), "~2018",
        "Myers & Simmons, 'The Coming Exodus of Older Homeowners', Fannie Mae Housing Insights "
        "(~2018) — cohort homeownership retention tracked on Census/ACS: of 75+ owners, only "
        "~26-31% remain after ten years (dossier demo_literature.md:30). SANITY CHECK ONLY: "
        "all-cause including death, so it maps to TOTAL exit and is never a calibration target "
        "for the non-mortality curves (spec §5, I1/I3)"),
    "reconciliation_band": Anchor(
        (0.20, 0.40), "2026-07-21 (spec §5)",
        "Myers 0.26-0.31 envelope WIDENED -> the decade all-cause retention gate; outside -> "
        "CalibrationError. A coarse gross-mortality-double-count backstop, never a proof of "
        "exactly-once (that lives in the stock-flow equation + mutation test)"),
    "living_alone_vitrine": Anchor(
        0.28, "2021",
        "ISQ vitrine vieillissement (65+, QC-wide) — POOLED fallback the living-arrangement "
        "loader applies per-sex when the Census cross-tab is absent. SUPERSEDED IN PRACTICE: probe "
        "P3 landed DIRECT per-sex living-alone at CMA level from StatCan 98-10-0134-01 "
        "(DECISION-FOUND-AT-CMA: YES), and Task 15b's loader serves EVERY modeled geography from "
        "that measurement — so NO code path reads this anchor today. It is cited-or-raise there, "
        "deliberately: an unreachable fallback branch would serve 0.28 for a malformed artifact "
        "cell instead of refusing. Retained as the documented fallback (P3 §4c measured the direct "
        "QC 65+ pooled rate at 0.3091, inside the widened band below) for a future geography "
        "extension the cube does not carry",
        band=(0.24, 0.34), flag="borrowed_prior"),
    "collective_share_75plus": Anchor(
        0.04, "2021",
        "Census collective-dwelling share, 75+ (excluded before household conversion, spec §5). "
        "STILL borrowed_prior after P3: P3 §5 measured a 2.27% all-ages QC collective gap "
        "(8,308,475 private-household persons vs 8,501,833 published) and states a 75+-SPECIFIC "
        "share is NOT derivable from 98-10-0134-01 alone (it needs total population BY AGE) — "
        "'Task 15's collective_share_75plus keeps its existing flag; P3 does not land it'",
        band=(0.02, 0.08), flag="borrowed_prior"),
    "mifi_pr_annual_plan": Anchor(
        45000, "2025-11-06",
        "MIFI Plan d'immigration du Quebec 2026-2029 (released 2025-11-06): ~45,000 permanent "
        "admissions/yr for Quebec. TRIPWIRE TARGET ONLY (spec §7, probe P5): realized IRCC "
        "PR-by-CMA landings are compared against this plan level; it never feeds the demand "
        "model, which uses ISQ compo 'Immigrants permanents'",
        unit="count"),

    # ---- immigrant/non-immigrant ownership RATIO: the tenure fork, BOTH readings (charter carry).
    # P4 (probes/P4-immigrant-ownership-diff.md) records three defensible tenure anchors and
    # "rules between NONE". Both forks land as documented constants; neither is promoted here.
    #
    # NONE OF THEM IS THE MODEL'S RATIO SOURCE, and that is a ruling, not a preference. Spec §6
    # states the layering explicitly — measured (98-10-0621-01) > sibling-measured (43-10-0060-01)
    # > borrowed (these) — so the ratio the demand chain multiplies is the MEASURED per-geography
    # value in `demand/immigrant_inputs.py`. These three stay for the job they still do: the
    # robustness SWEEP's span is sourced from them (immigrant_ownership_ratio_sweep_span below),
    # and P8's measurement never narrows a robustness range.
    # All three are borrowed_prior on THREE stated transport axes (P4 §4c): GEOGRAPHY (Quebec is
    # not a covered province — CHSP homeownership coverage excludes it, so ROC provinces stand in
    # for the MTL/QC CMAs), METRIC (individual property ownership ages 25-54 vs the spec's
    # household-maintainer propensity), and TENURE-PROFILE (a single year stands in for the
    # arrival stock's tenure distribution).
    "immigrant_ownership_ratio_fresh_arrival": Anchor(
        0.210, "2021 (released 2026-06-16)",
        "FRESH-ARRIVAL reading (P4 §4b #1): min/mean/max of the 7 province YEAR-1 "
        "recent-immigrant vs Canadian-born homeownership ratios. Statistics Canada, catalogue "
        "46-28-0001, 'The homeownership trajectories of recent immigrants', Chart 1, released "
        "2026-06-16. Its READING IS REFUSED by spec §6 (ruling P, carried unchanged through "
        "rulings S/T): p_imm does NOT capture arrival-window ownership. §6's own equations "
        "settle it — I2 subtracts the FULL surviving arrival stock from P_resident in every "
        "year while the demand chain credits each arrival cohort exactly ONCE, in its arrival "
        "year, so years 2+ of every cohort belong to NEITHER channel and the arrival-year "
        "credit necessarily stands in for the cohort's whole residency; an arrival-window rate "
        "would systematically undercount it. The MEASUREMENT is untouched and the anchor STAYS: "
        "it is the sweep span's floor (see immigrant_ownership_ratio_sweep_span), and deleting "
        "it would break the sweep's own source. What is refused is the reading, not the number",
        band=(0.155, 0.268), flag="borrowed_prior", unit="ratio"),
    "immigrant_ownership_ratio_year3": Anchor(
        0.614, "2021 (released 2026-06-16)",
        "YEAR-3 tenure anchor (P4 DECISION-RATIO-TENURE-SENSITIVITY): min/mean/max of the 7 "
        "province year-3 ratios. Statistics Canada, catalogue 46-28-0001, 'The homeownership "
        "trajectories of recent immigrants', Chart 1, released 2026-06-16. This is the DOMINANT "
        "uncertainty axis — the tenure anchor swings the ratio ~33% (year-3 0.614 vs year-5 "
        "0.911), a swing NOT contained in either cross-province band",
        band=(0.451, 0.754), flag="borrowed_prior", unit="ratio"),
    "immigrant_ownership_ratio_settled": Anchor(
        0.911, "2021 (released 2026-06-16)",
        "SETTLED reading (P4 §4a, DECISION-RATIO-MULTIPLIER-BAND): min/mean/max of the 7 province "
        "FIFTH-YEAR ratios. Statistics Canada, catalogue 46-28-0001, 'The homeownership "
        "trajectories of recent immigrants', Chart 1, released 2026-06-16. P4 calls this its "
        "RECOMMENDED anchor (a projection to 2051 is dominated by settled-state ownership, not "
        "the first-year rental skew) — a RECOMMENDATION, explicitly NOT a ruling. Band width is "
        "cross-PROVINCIAL dispersion at fixed tenure, a SECONDARY axis. Spans >1.0 honestly: New "
        "Brunswick recent immigrants OUT-own Canadian-born (1.033)",
        band=(0.765, 1.033), flag="borrowed_prior", unit="ratio"),
    "immigrant_ownership_ratio_sweep_span": Anchor(
        (0.155, 1.033), "2021 (released 2026-06-16)",
        "The robustness-sweep span across BOTH uncertainty axes — tenure anchor (year 1/3/5) AND "
        "cross-province dispersion — per P4's instruction to Task 15 by name: 'Task 15's "
        "robustness sweep grid must span BOTH axes, not the fifth-year cross-province spread "
        "alone'. Endpoints are the year-1 floor and the year-5 ceiling of the three bands above. "
        "Tranche 2 replaces this coarse ratio with the years-since-landing S-curve",
        flag="borrowed_prior", unit="ratio"),
}


# RUN CONTRACT (codex r8-F1): the headline run evaluates every banded assumption at its declared
# CENTRAL value; band ENDPOINTS enter ONLY the robustness sweep (per-geography rank_stable). The
# central values + sweep grid are enumerated HERE and covered by assumptions_hash — the hash
# identifies the selection; the spec's central-value rule DETERMINES it.
#
# SINGLE SOURCE, forward-binding on the consumers: a consumer that REDECLARES one of these
# values as its own literal moves the run's numbers while the hash stays byte-identical —
# breaking spec:532's artifact identity. Every consumer reads its central value FROM here
# (spec:475 names constants.py as the enumeration's home); a second declaration site is a
# defect, not a convenience. `assumptions_hash` covers THREE selections now, not this dict
# alone — see its docstring; the rule above binds each of them identically.
CENTRAL_ASSUMPTIONS = {
    "q_live_per_year": 0.085,          # flat age-shape (annualized 1-(1-0.36)^(1/5))
    "phi_voluntary": 0.9,
    "estate_eventual_fraction": 0.725,
    "estate_lag_years": 2,
    # NO immigrant-ratio scalar. The plan's `immigrant_ratio_center` (0.62, pinned PRE-P4 and
    # matching none of its anchors) was DELETED at Task 25b together with its SWEEP_GRID twin
    # and its provenance entry: rulings S/T measure the ratio PER GEOGRAPHY, so it lives in
    # `demand/immigrant_inputs.py` and a scalar here would be the second declaration this
    # dict's own comment above forbids. The robustness axis survives UNCHANGED — Task 29
    # perturbs the join table with a uniform override spanning
    # `CONSTANTS["immigrant_ownership_ratio_sweep_span"]` = [0.155, 1.033], which is why P4's
    # three anchors and that span stay above.
    #
    # THE ONE CATEGORICAL MEMBER (operator ruling V, 2026-08-19). `headship_shape` names which
    # of the age-resolved headship curve's two tangent rules the headline run reads. It is NOT
    # a banded scalar and it does NOT belong in `MODEL_CHOICES` either: that dict exists for
    # discrete picks with NOTHING to sweep, and this one has a measured, admissible
    # alternative — both arms reproduce all 14 published maintainer-age members EXACTLY, so
    # neither is a degraded version of the other and choosing between them is a shape
    # assumption the sweep can actually price. The design panel measured the arm spread at
    # 0.00026 … 0.00052 of ED per geography and NON-common-mode, i.e. larger than the spread
    # across entirely different construction families — an axis this size left undeclared is a
    # `rank_stable` verdict over a grid it never varied. The VALUE is a bare string here rather
    # than an import from `loaders.census` because this module is the leaf every model module
    # reads; `tests/test_pipeline.py` binds the two declarations plus the artifact's own
    # `central_shape` so none can drift alone.
    "headship_shape": "expo_cum_fc",
    #
    # THE SEVENTH AXIS, AND ITS VALUE IS READ THROUGH FROM `CONSTANTS` (spec amendment #20(D),
    # 2026-08-22). `collective_share_75plus` is a LIVE headline input — `pipeline._household_stock`
    # hands it to `initialize_households` for every 75+ stock slice — with a declared band
    # (0.02, 0.08) and, until this amendment, no sweep leg. Moving it to its OWN band high
    # reorders the published ranking (HORS_RMR 4->5, MTL_RMR 5->4), so `rank_stable` was
    # attesting robustness over a grid that never varied a +/-2x axis which alone reorders. By
    # the MODEL_CHOICES header's membership rule — a discrete pick with a measured, admissible
    # alternative is a sweep axis — it qualifies, and being BANDED it belongs in this dict and
    # its twin rather than in `MODEL_CHOICES`.
    #
    # `CONSTANTS[...].value`, NEVER 0.04. This dict's own header forbids a second declaration
    # site, and the anchor is the first one: the registry carries the citation, the band and the
    # `borrowed_prior` flag, and `assumptions_hash` covers the registry since the round-3 audit.
    # A literal here would let the anchor move while the run's central value did not.
    "collective_share_75plus": CONSTANTS["collective_share_75plus"].value,
}
SWEEP_GRID = {                          # endpoints for the robustness sweep, never the headline
    "q_live_per_year": (0.06, 0.11),
    "phi_voluntary": (0.7, 1.0),
    "estate_eventual_fraction": (0.6, 0.85),
    "estate_lag_years": (1, 3),
    # THE ANCHOR'S OWN DECLARED BAND, read through for the reason its central value is
    # (amendment #20(D)). Both endpoints get a leg even though the axis is measurably ONE-SIDED
    # — 0.08 reorders, 0.02 leaves the order intact — because the sweep's contract is "every
    # declared axis at BOTH declared endpoints" and a leg dropped for being quiet today is a
    # leg nobody re-checks tomorrow.
    "collective_share_75plus": CONSTANTS["collective_share_75plus"].band,
    # An ADMISSIBLE SET, not an interval — the two carried constructions, both member-exact.
    # One of them IS the central value, so its leg is a provable no-op; `pipeline._sweep_legs`
    # still declares it and `tests/test_pipeline.py` names it as the ONLY exempt leg, so a
    # numeric endpoint drifting onto its central value cannot hide behind the exemption.
    "headship_shape": ("expo_cum_fc", "expo_cum_fb"),
}

# THE ROBUSTNESS SWEEP'S DECLARED GRID AND ITS LEG VOCABULARY — ONE declaration, read by the
# producer AND by the emitter's key registry.
#
# `SWEEP_GRID` above is the BANDED/CATEGORICAL half. The immigrant/non-immigrant ownership ratio
# is the axis with NO central scalar (rulings S/T measure it per geography, so `CENTRAL_
# ASSUMPTIONS` deliberately carries none and this dict's keyset is held EQUAL to that one), and
# its span is the anchor below. It is therefore declared HERE rather than in `pipeline.py`, where
# it used to live: since spec amendment #20(C)(2) the rankings artifact PUBLISHES a per-leg
# `rows_moved` map, so `output/artifacts.py` has to bind that map's keys to the declared legs —
# and `artifacts` cannot import `pipeline` (the arrow runs the other way). A second copy of the
# axis name or of the label spelling is the drift vector this module refuses everywhere else.
RATIO_SWEEP_AXIS = "immigrant_ownership_ratio"
RATIO_SWEEP_SPAN_ANCHOR = "immigrant_ownership_ratio_sweep_span"


def declared_sweep_grid() -> dict:
    """{axis: declared endpoints} over the WHOLE declared grid, axes sorted.

    A FUNCTION, NOT A MODULE-LEVEL SNAPSHOT, and the difference is a live gate rather than
    style: `pipeline._sweep_legs` REFUSES a declared axis the ED grid has no field to carry —
    the forward guard stress F1 asked for by name ("a future axis added to the constant cannot go
    unswept") — and `tests/test_pipeline.py` reaches that refusal by adding an axis to
    `SWEEP_GRID` at runtime. A dict built at import time would freeze the guard's input and the
    refusal would become unreachable from the one direction anything tests it from."""
    return {**{axis: SWEEP_GRID[axis] for axis in sorted(SWEEP_GRID)},
            RATIO_SWEEP_AXIS: CONSTANTS[RATIO_SWEEP_SPAN_ANCHOR].value}


def sweep_leg_label(axis: str, endpoint) -> str:
    """The ONE spelling of a sweep leg's published name: `<axis>=<endpoint>`.

    `str()` rather than `repr()` so the categorical endpoint reads as `headship_shape=
    expo_cum_fb` and not with quotes welded on; on this interpreter `str(float)` IS `repr(float)`,
    so a numeric endpoint round-trips exactly and the emitted key is byte-stable under a fixed
    grid — which the golden rests on."""
    return f"{axis}={endpoint}"


def sweep_leg_labels() -> frozenset:
    """The emitted `rows_moved` map's KEY VOCABULARY — `output/artifacts.py` binds the map's keys
    to it. Derived from `declared_sweep_grid()` on every call, for that function's reason: a
    frozen copy here and a live grid there would let a run emit a count under a key the gate
    could not admit, or admit a key for a leg the sweep no longer declares."""
    return frozenset(sweep_leg_label(axis, endpoint)
                     for axis, endpoints in declared_sweep_grid().items()
                     for endpoint in endpoints)

# The charter carry applies to these bare floats too. CENTRAL_ASSUMPTIONS cannot hold Anchors —
# a consumer reads a member as `CENTRAL_ASSUMPTIONS["phi_voluntary"]`, a float — so the citation
# lives alongside, keyset-locked by test. WHAT READS IT TODAY (stated because a wrong why about
# reach is what makes a member look safe to delete): `cohort/listings.py` binds THREE keys
# read-through at import — phi_voluntary, estate_eventual_fraction, estate_lag_years, which
# are its DEFAULTS for a caller that states nothing; `q_live_per_year` is read by the cohort
# tests and gate discharge. ALL FOUR are read by the pipeline, which builds
# `pipeline.CENTRAL_LEG` = `Assumptions(**CENTRAL_ASSUMPTIONS)` and passes every one of them
# EXPLICITLY down the ED path — a key added here without a leg field raises at import rather
# than dropping out of the robustness sweep (run-32 quant F1 / stress F1).
CENTRAL_PROVENANCE = {
    "q_live_per_year":
        "CONSTANTS['q_live_annual'] — CMHC 36%/5yr annualized, spec §5 band [0.06, 0.11]/yr; "
        "central = the annualized point estimate itself, not a band midpoint",
    "phi_voluntary":
        "spec §5 transfer-vs-market split: voluntary exits list promptly, phi~0.9, band [0.7, 1.0]; "
        "central = the spec's stated point value",
    "estate_eventual_fraction":
        "spec §5 estate eventual-listing fraction band [0.6, 0.85] (US survey prior, borrowed_prior); "
        "central 0.725 = the exact band midpoint, the spec's central-value rule with no point estimate",
    "estate_lag_years":
        "spec §5 estate-lag convolution L in [1, 3] years; central 2 = the exact band midpoint, the "
        "spec's central-value rule with no point estimate",
    "collective_share_75plus":
        "CONSTANTS['collective_share_75plus'] — the 2021 Census collective-dwelling share at "
        "75+, excluded before household conversion (spec §5), flagged `borrowed_prior`; central "
        "= the anchor's own value and the sweep endpoints = the anchor's own band [0.02, 0.08], "
        "both READ THROUGH so this dict states no second value. Made a declared robustness axis "
        "by spec amendment #20(D) (2026-08-22): an in-band move to the band high reorders the "
        "published ranking (HORS_RMR 4->5, MTL_RMR 5->4), which `rank_stable` could not have "
        "seen while the axis was undeclared",
    "headship_shape":
        "operator ruling V (2026-08-19), design panel `docs/research/2026-08-19-headship-curve-"
        "design-panel.md` §5: the age-resolved headship curve is a monotone cubic Hermite on the "
        "cumulative maintainer count against the CUMULATIVE-PERSONS abscissa, and the tangent "
        "rule is the one degree of freedom left free by per-member closure. Central "
        "`expo_cum_fc` = three-point width-weighted tangents under the Fritsch-Carlson circle "
        "filter, chosen because its closure is ALGEBRAIC (member endpoints ARE interpolation "
        "knots, so the sum telescopes independently of the tangent rule) rather than a converged "
        "solve. Sweep endpoint `expo_cum_fb` = Fritsch-Butland weighted-harmonic-mean interior "
        "slopes, member-exact on the same knots. This is a SHAPE ASSUMPTION, not a measurement: "
        "closure pins one linear functional per published member and leaves 4, 9 or 15 degrees "
        "of freedom, and the artifact's own `shape_note` carries the generator-computed "
        "refutation of the age-abscissa alternative",
}


# ===========================================================================================
# MODEL CHOICES — the discrete, UNBANDED picks the model makes (run-32 stress gate F2)
# ===========================================================================================
#
# TWO LITERALS SAT ON THE MONEY PATH WITH NO ANCHOR AND NO IDENTITY COVERAGE. `pipeline.py`
# carried `ROLL_AGE = 80` and `p_nonimm = read_ownership(geo, 40)` as bare numbers; each swings
# the SHIPPED headline `mean_ed_*` figures by 55-66% (measured, run 32), and neither was inside
# `assumptions_hash` or `data_vintage.source_hashes` — so editing either moved every emitted
# number under a byte-identical envelope. Lifting them here closes both halves in one move: the
# citation lands beside the value (spec:621 "Binds Task 25b: no uncited literals") and the hash
# covers the selection.
#
# WHY THIS IS A THIRD DICT AND NOT `CENTRAL_ASSUMPTIONS`. That dict's contract is a central
# value WITH a DECLARED ALTERNATIVE — its keyset is held EQUAL to `SWEEP_GRID`'s by test, on
# the stated ground that "an unswept central assumption silently claims rank_stable it never
# tested". Neither of these has one: no band, and no second admissible value either. Inventing
# a band would be the fabricated anchor this file exists to refuse, and adding a sweep axis
# would widen the robustness sweep's DECLARED grid — a modelling decision, not an identity fix.
# THE LINE IS "IS THERE SOMETHING TO SWEEP", NOT "IS IT A FLOAT" (sharpened at ruling V, when
# `headship_shape` joined `CENTRAL_ASSUMPTIONS` as a categorical member): a discrete pick with
# a measured, admissible alternative is a sweep axis; a discrete pick with none — `roll_age`
# is not "one of two lattices", it is the coarseness Tranche 2 removes — has nothing to sweep,
# and saying so plainly is cheaper than either lie.
#
# THAT CRITERION ONCE CUT AGAINST `p_nonimm_age`, AND THE FORK IS DISSOLVED RATHER THAN SWEPT
# (operator ruling X2, 2026-08-21). The retired entry was an AGE (40) selecting whichever
# ownership band contained it. That qualified for this dict while the 30-year `25-54` band made
# every age in the cited reasoning range return the SAME rate — nothing to sweep. Ruling W
# (2026-08-20) split that band three ways, so the same reasoning range began offering three
# measured admissible values, one of which flipped rank 1: by this dict's own line, a sweep axis.
# Ruling X2 removed the pick instead of parameterizing it. The immigrant leg's propensity is now
# the 25-54 aggregate formed BY CONSTRUCTION from owner and total counts
# (`census.ownership_union_rates`), so NO age inside the span is chosen and there is no discrete
# alternative for a sweep leg to move to. What is left is the SPAN — this dict's
# `p_nonimm_range` — which is still honestly uncited and is a strictly SMALLER exposure than the
# point pick was: a band rather than a point inside one. `MODEL_CHOICES` stays disjoint from
# `SWEEP_GRID`, which is why no pin in `tests/test_constants.py` retires with the fork.
#
# BOTH ARE HONESTLY UNCITED, and the marker is the point: this arc has removed several
# fabricated citations, so an absent anchor is RECORDED as absent, with the measured
# sensitivity and the thing that would close it, rather than dressed in a plausible source.
MODEL_CHOICES = {
    "p_nonimm_range": (25, 54),
    "roll_age": 80,
}

MODEL_CHOICE_PROVENANCE = {
    "p_nonimm_range":
        "UNCITED. Spec §6 defines p_imm(a) = p_nonimm(a) x ratio age-indexed, but the ISQ compo "
        "arrival flow carries NO age axis, so the leg needs ONE rate over the span PR arrivals "
        "concentrate in, and §6 never says which span. 25-54 is that span, on a reasoning no "
        "committed source in this tree carries — which is why this entry is marked uncited "
        "rather than anchored to it. "
        "WHAT IS READ, AND HOW: the 25-54 aggregate BY CONSTRUCTION — owner counts and total "
        "counts summed over the 25-34 / 35-44 / 45-54 bands and divided ONCE "
        "(`census.ownership_union_rates`, and `hors_aligned.aligned_ownership_union` for the one "
        "operand-aligned geography). MTL_RMR 0.511996, QC_RMR 0.577577, HORS_RMR 0.690149 on the "
        "aligned territory; the five RA-level rows borrow MTL_RMR's with the rest of its curve. "
        "NEVER a mean of the three band rates: that gives MTL_RMR 0.501945, off by -1.005 pp, "
        "because the three bands carry materially different household counts. "
        "THE EXPOSURE IS SPAN SELECTION, NOT POINT SELECTION, since operator ruling X2 "
        "(2026-08-21), and the history is kept because it inverted twice. The entry was an AGE "
        "(40). Under the retired 30-year 25-54 band, ages 25/40/54 all returned the SAME rate, "
        "so only the band mattered and the point was measured INERT. Operator ruling W "
        "(2026-08-20) split that band and made the point LIVE — 40 resolved to 35-44 alone "
        "(MTL_RMR 0.540707) against the 25-54 union (0.511996) the reasoning had always wanted, "
        "an undeclared +2.87 pp shift, and reading 25-34 instead flipped rank 1 from "
        "LANAUDIERE_RA14_PROXY to MTL_RMR. Ruling X2 removed the point rather than sweeping it, "
        "so both of those readings are now history: there is no age to pick and the sub-band "
        "sensitivities that priced the pick are NOT carried forward, because they measured a "
        "choice the model no longer makes. "
        "WHAT WOULD CLOSE THIS ENTRY is unchanged in kind and smaller in size: no committed "
        "source in this tree carries a PR arrival age distribution, and weighting p_nonimm by "
        "one is what turns the span into a measurement. Until then the span is a declared, "
        "uncited model choice inside `assumptions_hash`",
    "roll_age":
        "UNCITED. Tranche-1 coarseness, stated as such in `pipeline.py`'s own header: the 75+ "
        "owner stock is a SINGLE lumped bucket rather than an age-indexed lattice, so it is "
        "decremented at ONE age and this is that age. A MODEL choice, not an index — the whole "
        "bucket's hazard rides it. MEASURED: ROLL_AGE 75 gives HORS_RMR mean reference ED "
        "-0.00025067 and 85 gives -0.00012999, a 55% swing across the pair (run-32 stress F2, "
        "measured on the pre-ruling-V curve and kept as that run's record). "
        "IT NO LONGER SELECTS AN OWNERSHIP BAND (operator ruling X1, 2026-08-21). Between "
        "ruling W and ruling X1 this age ALSO chose the rate the whole bucket was valued at, and "
        "chose one NARROWER than the bucket: 80 resolved to `75-84` alone, which sits above each "
        "geography's OWN served age>=75 household-weighted union by +1.073 pp (MTL_RMR), "
        "+2.593 pp (QC_RMR) and +1.670 pp (HORS_RMR, on the OPERAND-ALIGNED curve that geography "
        "actually reads) because 85+ households are 21.7-25.8% of the block and own at a "
        "materially lower rate. THE BASELINE IS NAMED DELIBERATELY (operator ruling X5, "
        "2026-08-21): HORS_RMR's figure stood here as +1.654 pp, which is the CENSUS-NET curve's "
        "reading and not the curve the model serves that geography — an unnamed baseline is how "
        "it drifted, and the aligned reading is 1.670. `_standing_stock` now values the bucket at "
        "the POPULATION-WEIGHTED mean of the per-age rates over the ages it holds, so the "
        "ownership weighting is the slice's own and the narrowing is GONE rather than priced — a "
        "small DECLARED model change on S, never a restoration: the weighted mean sits BELOW the "
        "retired flat band's household-weighted union by -0.162 pp (MTL_RMR), -0.636 pp (QC_RMR) "
        "and -0.361 pp (HORS_RMR), and no weight aggregates the couple bucket exactly (ruling "
        "X3; see `pipeline._standing_stock` for the four reasons the choice is still right). "
        "What still rides this age is the hazard and the living-arrangement read (that lumping "
        "is pre-existing and separately documented). "
        "THE INTERNAL INCONSISTENCY RULING X1 CLOSED, stated because it was recorded here as "
        "open: ED's DENOMINATOR is age-resolved (`balance/owner_stock.py` sums over every single "
        "year of age, valuing QC_RMR's 85+ households at 0.4405) while the S NUMERATOR valued "
        "those same households at 0.5598 through one band read. Numerator and denominator now "
        "read the same per-age rates; what remains coarse is the BUCKET — one hazard age and one "
        "household-state mix for the whole 75+ block — which is Tranche 2's age-indexed lattice "
        "to remove. Note that per-age summation of `_household_stock` is NOT that removal and "
        "was measured wrong: it re-does couple matching per age and forces spouses to share an "
        "age (see `_standing_stock`). "
        "`_band_entry_stock` is NOT affected and never was — it reads at BAND_ENTRY_AGE 75 on a "
        "single age-75 cohort, where the point read IS the right one. "
        "Neither the spec, the plan nor the dossier names an age, so nothing is cited here; "
        "Tranche 2's age-indexed lattice REMOVES the choice rather than anchoring it",
}

# The keyset lock lives in `tests/test_constants.py`, not in an import-time guard — the same
# place and the same reason as `CENTRAL_PROVENANCE`'s: these are bare values, not `Anchor`s,
# so there is no constructor to raise from and a second mechanism would guard nothing the
# neighbouring dict does not already have.


# The DECLARED width of the identity token below, exported because the artifact emitter has to
# validate the same form this function produces. `output/artifacts.py` guessed 64 (sha256's full
# width) and therefore REFUSED the only hash any run computes — two committed contracts in
# contradiction, green because no test crossed the seam (review finding F2, run 30). One
# declaration, read by producer and gate alike; `test_constants.py` keeps a third, test-owned
# literal so a widening is a PR-visible act in three places rather than a silent re-mint.
ASSUMPTIONS_HASH_CHARS = 16


def resolved_constants() -> dict[str, dict[str, object]]:
    """The ANCHOR REGISTRY as plain data — VALUE and BAND per key, sorted — the fourth thing
    `assumptions_hash` identifies.

    ROUND-3 AUDIT FINDING (2026-08-22): `CONSTANTS` was outside BOTH identity tokens, and one
    of its members is a LIVE HEADLINE INPUT — `pipeline._household_stock` reads
    `CONSTANTS["collective_share_75plus"].value` into `initialize_households` for every 75+
    stock slice. MEASURED by full-pipeline execution: moving that anchor to 0.08 — its OWN
    declared band high, an in-band move needing no new citation — REORDERS the published
    ranking (HORS_RMR 4->5, MTL_RMR 5->4; LAVAL_RA13's ED moves +82.9%, HORS_RMR's +304%)
    while `assumptions_hash` stayed `fe7c631104c5182b` and `data_vintage` stayed byte-identical.
    THAT IS A DATED FINDING, measured at the forbid-casing hardening commit BEFORE this widening, and
    `fe7c631104c5182b` is the token of those bytes rather than of this tree — the tense is
    deliberate: a reader who finds the hash moving on an anchor edit has found the fix.
    A consumer holding two such artifacts is routed by `artifacts/README.md`'s reading table to
    "neither token moved but the values differ => the code moved" — a WRONG verdict, the same
    class run 33 closed for the mortality basis and the ruled join table. The aggravation was
    that this module's own header RECORDS the edit as SCHEDULED ("the executor updates
    collective_share_75plus when P3 lands a firmer figure") while the anchor alone carried no
    pin of its own, unlike its siblings' exact pins — so the one anchor left loose on purpose
    was the one that reordered the ranking silently.

    THE HASH AND THE PIN COVER DIFFERENT DEFECTS, AND THE TREE NOW CARRIES ONE OF EACH. This
    payload covers the INVISIBLE move: an in-band edit that re-mints nothing, which no pin can
    see. `tests/test_constants.py` covers the OUT-OF-BAND one, pinning the anchor's own declared
    band — since amendment #20(D) that band IS the declared sweep's endpoint pair, so a value
    outside it is not a refinement at all but a central value the grid does not bracket. AN EXACT
    PIN AT 0.04 IS STILL REFUSED, and that is the half the looseness argument had right: it would
    close the refinement path the plan schedules. In-band refinement stays open, out-of-band reds,
    and neither leg substitutes for the other.

    IT RANGES OVER THE WHOLE REGISTRY, not over an allowlist of the members that are live
    today. An allowlist inside this module would be a SECOND declaration of which anchors
    matter — the exact shape that let `collective_share_75plus` sit outside — and its failure
    mode is silent: the next anchor added defaults to UNCOVERED. Registry-wide is fail-safe
    (a new anchor is covered without an edit here) and its cost is bounded to a re-mint on a
    ruled value's move, which is a PR-visible act either way. Two members are covered on that
    granularity ground rather than because they move an emitted number:
    `reconciliation_band` is a REFUSAL threshold (`cohort/gates.RECONCILIATION_BAND` holds the
    second, test-bound copy, so hashing this one covers the gate transitively), and the
    tenure-fork anchors feed only the sweep span. One is a genuine emitted-field gap that this
    widening closes and `pipeline._sweep_legs`' section note named by number:
    `immigrant_ownership_ratio_sweep_span` IS the robustness sweep's span, so narrowing it
    flips `rank_stable` — an EMITTED field — and before this payload member that move landed in
    the reading table's "the code moved" bucket.

    VALUE AND BAND, AND NOTHING ELSE OFF THE ANCHOR. `band` is in because it is CONSUMED: it is
    the sweep's own endpoint pair (`tests/test_q_live.py` binds `Q_LIVE_BAND ==
    CONSTANTS["q_live_annual"].band == SWEEP_GRID["q_live_per_year"]`), and a band that no
    longer brackets its value changes what the anchor admits. `as_of`, `source`, `flag` and
    `unit` are OUT, on the discriminator the immigrant join table already uses: a field rides
    this payload when an emitter CONSUMES it. No emitter reads an anchor's `flag` — the
    `borrowed_prior` tokens on an emitted rankings row come from the join table's per-field
    provenance, which `pipeline._borrowed_inputs` does read — and `source` is prose, where
    coupling identity would re-mint every artifact on a reworded note (the residual
    `assumptions_hash` states below). `as_of` is a VINTAGE claim, not a selection: spec §7a
    parks `constants_as_of` in the Tranche-2 `data_vintage` shape, which is the other token.
    """
    return {key: {"value": list(a.value) if isinstance(a.value, tuple) else a.value,
                  "band": list(a.band) if a.band is not None else None}
            for key, a in sorted(CONSTANTS.items())}


def assumptions_hash() -> str:
    """Identity of the ASSUMPTION SELECTION (spec §7 identity envelope). Not a proof the
    selection is right — a proof that two runs used the same one.

    IT COVERS FOUR SELECTIONS, and every one after the first was added because a ruled value
    could move and re-mint NOTHING (quant gate F4 and stress gate F2 at run 33; the round-3
    audit's HIGH finding at run 36):

      * `central` + `sweep` — the run contract's banded assumptions (codex r8-F1).
      * `model_choices` — the discrete unbanded picks; each swings the shipped headline numbers
        by 55-66% and both were bare literals in `pipeline.py`.
      * `immigrant_inputs` — the ruled per-geography headship/ratio pairs that amendments
        #13/#14 exist to govern. Task 25b moved them out of `CENTRAL_ASSUMPTIONS` into
        `demand/immigrant_inputs.py` and they left hash coverage with them; being source
        literals rather than files under `data/`, they are outside `source_hashes` too. The
        exact scenario #14 was written about — a ruled value swapping between two legitimate
        pairs — moved every geography's ED under a byte-identical envelope, and a ratio change
        of that class reorders up to 7 of 8 geographies (measured).
      * `constants` — THIS MODULE'S OWN anchor registry, value and band (`resolved_constants`
        above carries the finding and the scope argument). `collective_share_75plus` is a LIVE
        headline input and an in-band move of it reordered the published ranking under a
        byte-identical envelope.

    IT DOES NOT COVER THE DATA, and that separation is the whole design (see
    `pipeline._run_identity`): `source_hashes` answers "which bytes", this answers "which
    selection", and one token that moved for either cause would answer neither.

    STATED RESIDUAL: the join table's `source` CITATIONS are excluded on purpose — coupling
    artifact identity to prose would re-mint every artifact on a reworded note, and the prose
    is already bound where it belongs, to the DIGITS, by `tests/test_i2.py`'s coupling to P8's
    DECISION tokens. The per-field provenance TOKENS are in, because they are consumed: a
    `borrowed_prior` on either field puts a flag on the emitted rankings row.

    TRUNCATED to `ASSUMPTIONS_HASH_CHARS`: this is a collision-resistance question over the
    handful of assumption selections one project ever emits, not a security boundary — 64 bits
    is ample there, and the artifact stays readable. Widening it RE-MINTS every artifact
    identity (§9: "a change in any re-mints the artifact BY DESIGN"), so it is a change to make
    before a golden pins bytes, never after."""
    # THE IMPORT IS LOCAL, deliberately: the arrow points the other way everywhere else in this
    # tree — `demand/` and `cohort/` read THIS module (the import-direction gate admits
    # `constants` and `validate` as their only loader leaves) and `cohort/listings.py` binds
    # three central assumptions at import. A module-level import would make the leaf every model
    # module reads depend on a model package at import time, one edit from a cycle. The hash
    # needs the RESOLVED table rather than the module, so call time costs nothing.
    from demoflow.demand.immigrant_inputs import resolved_selection

    payload = json.dumps({"central": CENTRAL_ASSUMPTIONS, "sweep": SWEEP_GRID,
                          "model_choices": MODEL_CHOICES,
                          "immigrant_inputs": resolved_selection(),
                          "constants": resolved_constants()}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:ASSUMPTIONS_HASH_CHARS]
