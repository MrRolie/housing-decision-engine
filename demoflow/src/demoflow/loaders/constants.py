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
        "loader applies per-sex when the Census cross-tab is absent. SUPERSEDED IN PRACTICE for "
        "P3-covered geographies: probe P3 landed DIRECT per-sex living-alone at CMA level from "
        "StatCan 98-10-0134-01 (DECISION-FOUND-AT-CMA: YES), so Task 15b must prefer the measured "
        "rate and reach this fallback only for a geography the cube does not carry",
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
        "2026-06-16. Right if p_imm captures arrival-window ownership — the §6 netting target IS "
        "the recent-arrival stock, which owns near the year-1 rate before accumulating tenure",
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
# SINGLE SOURCE, forward-binding on the consumers: assumptions_hash covers only what THIS dict
# holds, so a consumer that REDECLARES one of these values as its own literal moves the run's
# numbers while the hash stays byte-identical — breaking spec:532's artifact identity. Every
# consumer reads its central value FROM here (spec:475 names constants.py as the enumeration's
# home); a second declaration site is a defect, not a convenience.
CENTRAL_ASSUMPTIONS = {
    "q_live_per_year": 0.085,          # flat age-shape (annualized 1-(1-0.36)^(1/5))
    "phi_voluntary": 0.9,
    "estate_eventual_fraction": 0.725,
    "estate_lag_years": 2,
    "immigrant_ratio_center": 0.62,    # per-geography ownership ratio band center — SEE PROVENANCE
}
SWEEP_GRID = {                          # endpoints for the robustness sweep, never the headline
    "q_live_per_year": (0.06, 0.11),
    "phi_voluntary": (0.7, 1.0),
    "estate_eventual_fraction": (0.6, 0.85),
    "estate_lag_years": (1, 3),
    "immigrant_ratio_center": CONSTANTS["immigrant_ownership_ratio_sweep_span"].value,
}

# The charter carry applies to these bare floats too. CENTRAL_ASSUMPTIONS cannot hold Anchors
# (the pipeline reads a member as `CENTRAL_ASSUMPTIONS["q_live_per_year"]`, a float — plan Task 29,
# today the ONLY key read from this dict), so the citation lives alongside, keyset-locked by test.
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
    "immigrant_ratio_center":
        "UNRULED — 0.62 was pinned by the plan on 2026-07-21, BEFORE probe P4 measured the tenure "
        "anchors, and it is NOT derived from any of them: P4's three centers are year-1 0.210, "
        "year-3 0.614 (nearest to 0.62, delta 0.006), year-5 0.911, and P4 states it 'rules between "
        "NONE'. The charter landed both fork readings as CONSTANTS above; the headline SELECTION "
        "between them is a seat/operator call, not this module's. Whatever is ruled, the sweep "
        "already spans the full [0.155, 1.033] range, so rank_stable is honest either way. NOTE: "
        "no code reads this key — the authoritative per-geography ratios live in the join table "
        "(demand/immigrant_inputs.py, plan Task 25b; the plan's Task-15 prose calls it 'Task 24b', "
        "which does not exist in the plan), which is where the fork bites materially",
}


def assumptions_hash() -> str:
    """Identity of the central/sweep SELECTION (spec §7 identity envelope). Not a proof the
    selection is right — a proof that two runs used the same one."""
    payload = json.dumps({"central": CENTRAL_ASSUMPTIONS, "sweep": SWEEP_GRID}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
