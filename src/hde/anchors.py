"""Parameter-provenance anchors: the single source of truth for every numeric
default the engine silently applies (provenance remediation, Task A).

Provenance audit finding: the engine's bias-critical defaults were uncited
"vibes" — literals scattered across models.py and config.py with no derivation.
This module is the remedy, modeled on demoflow's Anchor discipline
(demoflow/src/demoflow/loaders/constants.py): a frozen dataclass carrying
value + as_of + source + band, with a registry keyed by dotted parameter name.
`Anchor.__post_init__` refuses an empty source/as_of/rationale and a band that
does not bracket its own value — an uncited or self-inconsistent constant is a
defect at import time, not a review comment.

CITATION POLICY: every source below was fetched and its figure confirmed on the
`retrieved_on` date; the citation table (source, URL, figure quoted, derivation)
lives in docs/specs/2026-09-01-provenance-remediation-design.md. A default with no citation is marked as such ("neutral,
uncited" / "calibrated") in `short_cite`/`rationale` — never dressed in a
plausible-sounding source. Where a number is a calibration choice rather than a
measurement (e.g. price_shock.severity_vol), the rationale says so explicitly.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


class AnchorError(Exception):
    """Raised at import time when an anchor violates citation discipline."""
    pass


ANCHOR_KINDS = frozenset({"cited", "reference", "neutral", "derivation"})


# Echo aliases: dotted keys as they appear in spec.defaults_applied -> registry
# name. condo.selling_cost_rate and house.selling_cost_rate share ONE anchor
# (condo.house.selling_cost_rate) so the citation cannot drift between options.
_ECHO_ALIASES: Dict[str, str] = {
    "condo.selling_cost_rate": "condo.house.selling_cost_rate",
    "house.selling_cost_rate": "condo.house.selling_cost_rate",
    # price_shock sub-keys echo per option but cite the one shock anchor
    "condo.price_shock.severity_mean": "price_shock.severity_mean",
    "house.price_shock.severity_mean": "price_shock.severity_mean",
    "condo.price_shock.severity_vol": "price_shock.severity_vol",
    "house.price_shock.severity_vol": "price_shock.severity_vol",
}


@dataclass(frozen=True)
class Anchor:
    """One cited engine default: value + provenance + plausible band."""

    name: str
    value: float
    as_of: str
    source: str
    url: str
    rationale: str
    band: Tuple[float, float]
    short_cite: str
    # ISO date the cited URL was fetched and the quoted figure confirmed
    # (provenance remediation 0.0, 2026-09-01). Required whenever `url` is a
    # live http(s) source; calibration/neutral entries carry no URL and no date.
    retrieved_on: str = ""
    # What the citation IS to the value: `cited` = the source states the value
    # (or it is a direct derivation from stated figures); `reference` = the
    # source informs the value but does not state it (echo renders `[ref: …]`);
    # `neutral` = a deliberate uncited neutral default; `derivation` = a
    # calibration or mathematical derivation with no external source.
    kind: str = "cited"
    replaces: Optional[Tuple[float, str]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or "." not in self.name or not self.name.strip():
            raise AnchorError(f"anchor name must be a dotted key, got {self.name!r}")
        for field_name in ("as_of", "source", "url", "rationale", "short_cite"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise AnchorError(
                    f"anchor {self.name!r}: empty {field_name} — an uncited or "
                    f"unmotivated constant is a defect"
                )
        if not isinstance(self.band, tuple) or len(self.band) != 2:
            raise AnchorError(f"anchor {self.name!r}: band must be a 2-tuple, got {self.band!r}")
        lo, hi = self.band
        if not lo <= hi:
            raise AnchorError(f"anchor {self.name!r}: band endpoints out of order: {self.band}")
        if not lo <= self.value <= hi:
            raise AnchorError(
                f"anchor {self.name!r}: central value {self.value} outside its "
                f"own band {self.band}"
            )
        if self.kind not in ANCHOR_KINDS:
            raise AnchorError(
                f"anchor {self.name!r}: kind must be one of {sorted(ANCHOR_KINDS)}, "
                f"got {self.kind!r}"
            )
        if self.url.startswith("http") and not self.retrieved_on.strip():
            raise AnchorError(
                f"anchor {self.name!r}: a live URL needs retrieved_on (the date the source was retrieved)"
            )
        if self.replaces is not None:
            if not isinstance(self.replaces, tuple) or len(self.replaces) != 2:
                raise AnchorError(
                    f"anchor {self.name!r}: replaces must be (old_value, why), got {self.replaces!r}"
                )
            if not isinstance(self.replaces[1], str) or not self.replaces[1].strip():
                raise AnchorError(
                    f"anchor {self.name!r}: replaces entry must state why the default changed"
                )


ANCHORS: Dict[str, Anchor] = {
    # --- Re-anchored defaults (values changed; old defaults were uncited) ---
    "rent.investment_return_rate": Anchor(
        name="rent.investment_return_rate",
        value=0.03,
        as_of="2026",
        source="FP Canada Standards Council / Institute of Financial Planning, "
               "2026 Projection Assumption Guidelines (April 2026), §5 "
               "Financial assumptions: U.S. equities 6.4%, fixed income 3.2%, "
               "inflation 2.1% (nominal geometric means, before fees)",
        url="https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf",
        rationale=(
            "60/40 balanced portfolio ≈ 0.6×6.4% (US equities) + 0.4×3.2% "
            "(fixed income) ≈ 5.1% nominal; deflated by 2.1% PAG inflation "
            "≈ 3.0% real. The old 0.07 real default exceeded even the PAG "
            "100%-equity real ceiling (emerging markets 7.5% nominal ⇒ ≈ 5.3% "
            "real), i.e. it assumed an all-stock portfolio beating every PAG "
            "asset class in real terms."
        ),
        band=(0.02, 0.05),
        short_cite="FP Canada 2026 PAG",
        retrieved_on="2026-09-01",
        replaces=(0.07, "uncited default above any PAG-derived real return; "
                        "re-anchored to the 60/40 real figure"),
    ),
    "rent.rent_escalation_rate": Anchor(
        name="rent.rent_escalation_rate",
        value=0.01,
        as_of="2026",
        source="FP Canada 2026 PAG §5 'Shelter Projection Considerations' "
               "3.1% (inflation + 1%), new in the 2026 edition; NBER Digest "
               "Oct 2025 on Ball & Koh, NBER WP 34113 (21% pass-through to "
               "continuing tenants, nber.org/digest/202510/understanding-lag-"
               "between-cpi-shelter-inflation-and-market-rents); Québec TAL "
               "2026 base rate 3.1% = 3-year CPI average (tal.gouv.qc.ca, "
               "'Pourcentages applicables à la fixation de loyer 2026')",
        url="https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf",
        rationale=(
            "PAG shelter projection 3.1% nominal − 2.1% inflation = 1.0% real. "
            "Québec continuing-tenant leases renew at the TAL base rate, which "
            "since 2026 is the 3-year CPI average (3.1% for Apr 2026–Apr 2027 "
            "renewals) ⇒ ≈ 0.0% real; landlords pass through only ~21% of "
            "market-rent movements at renewal (Ball & Koh 2025), so 0.0% real "
            "is the floor of the plausible band."
        ),
        band=(0.0, 0.02),
        short_cite="FP Canada 2026 PAG",
        retrieved_on="2026-09-01",
        replaces=(0.03, "old default read like a nominal escalation applied in "
                        "real mode; re-anchored to the PAG real shelter-cost figure"),
    ),
    "income.income_growth_rate": Anchor(
        name="income.income_growth_rate",
        value=0.01,
        as_of="2026",
        source="FP Canada 2026 PAG §5 'YMPE, MPE growth rate or salary' 3.1% "
               "(inflation + 1% for productivity, merit and advancement)",
        url="https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf",
        rationale=(
            "PAG Salary Growth 3.1% nominal − 2.1% inflation = 1.0% real. "
            "Individual lifecycle salary growth (promotions, career changes) is "
            "a user input, not an engine default; this anchor is the "
            "population-level planning figure."
        ),
        band=(0.0, 0.02),
        short_cite="FP Canada 2026 PAG",
        retrieved_on="2026-09-01",
        replaces=(0.03, "old default conflated nominal salary growth with real "
                        "terms; re-anchored to the PAG real salary-growth figure"),
    ),
    "income.affordability_threshold": Anchor(
        name="income.affordability_threshold",
        value=0.32,
        as_of="2026",
        source="CMHC 'Calculating GDS/TDS': 'CMHC restricts debt service ratios "
               "to 39% (GDS) and 44% (TDS)'; industry guideline 32% GDS / 40% "
               "TDS per Ratehub 'Debt Service Ratios' (ratehub.ca/debt-service-"
               "ratios) — the 32% is NOT on the CMHC page",
        url="https://cmhc-schl.gc.ca/professionals/project-funding-and-mortgage-financing/mortgage-loan-insurance/calculating-gds-tds",
        rationale=(
            "Legacy GDS guideline 32%, deliberately below CMHC's current 39% "
            "GDS cap: hde's numerator is broader than GDS PITH (full condo "
            "fees, maintenance, stochastic events), so the same-income ratio "
            "runs higher than a lender's GDS — 32% on the broader numerator is "
            "the conservative reading. Band spans the legacy 32% guideline to "
            "CMHC's 44% TDS ceiling."
        ),
        band=(0.32, 0.44),
        short_cite="CMHC GDS/TDS",
        retrieved_on="2026-09-01",
        replaces=(0.35, "uncited midpoint between the legacy and CMHC caps; "
                        "re-anchored to the legacy 32% GDS guideline"),
    ),
    "condo.house.selling_cost_rate": Anchor(
        name="condo.house.selling_cost_rate",
        value=0.05,
        as_of="2026",
        source="WOWA.ca, 'Cost of Selling a House in Canada 2026'; PropertyMesh "
               "2026 Ontario example (5% total commission)",
        url="https://wowa.ca/calculators/cost-selling-house",
        rationale=(
            "WOWA 2026: combined commission 3.5–5% in Ontario, BC graduated "
            "(3–4% on the first $100k, 1–2% above), seller legal fees "
            "$1,000–$1,600; WOWA's own Ontario worked example totals 5.9% "
            "including 13% HST on the commission. 5% is the commission-plus-"
            "notary figure before sales tax; the band (3–8%) brackets a "
            "discount brokerage at the low end and a taxed full-commission "
            "sale at the high end. One anchor serves both condo and house so "
            "the citation cannot drift between options."
        ),
        band=(0.03, 0.08),
        short_cite="WOWA 2026",
        retrieved_on="2026-09-01",
    ),
    "price_shock.severity_mean": Anchor(
        name="price_shock.severity_mean",
        value=0.25,
        as_of="2026",
        source="TREB average price series 1989–96 (via Better Dwelling)",
        url="https://betterdwelling.com/city/toronto/it-took-22-years-for-prices-to-recover-from-the-last-toronto-real-estate-crash",
        rationale=(
            "Toronto 1989–96 correction: peak $273,698 (1989) → trough $198,150 "
            "(1996) = −27.6% nominal (≈ −39.4% real in 2017 dollars). Mean set "
            "just under the observed nominal peak-trough severity of Canada's "
            "largest metro correction; the channel is default-off "
            "(annual_hazard=0)."
        ),
        band=(0.15, 0.40),
        short_cite="TREB 1989–96",
        retrieved_on="2026-09-01",
        replaces=(0.20, "uncited; re-anchored near the observed 1989–96 nominal "
                        "peak-trough severity (−27.6%)"),
    ),
    "price_shock.severity_vol": Anchor(
        name="price_shock.severity_vol",
        value=0.10,
        as_of="2026",
        source="CALIBRATED TO ANCHOR, NOT INDEPENDENTLY SOURCED (dispersion "
               "choice around price_shock.severity_mean)",
        url="none — calibration choice, see rationale",
        rationale=(
            "Dispersion around the TREB-anchored severity mean. The draw is "
            "severity_mean × exp(vol·z − vol²/2) capped at 1.0 (lognormal, "
            "median-centred: the z=0 draw is 0.249, not 0.25), so ±1σ spans "
            "≈ 0.225–0.275 and p10–p90 ≈ 0.219–0.283 — inside the observed "
            "nominal (−27.6%) → real (−39.4%) span of the 1989–96 event. "
            "Calibrated to the severity anchor, not independently sourced; the "
            "band is an illustrative plausible range for the calibration."
        ),
        band=(0.05, 0.15),
        short_cite="TREB 1989–96 (calibrated)",
        kind="derivation",
    ),
    # --- Rationale-only anchors (value unchanged; registered so the echo and
    #     the config parsers cite a single source instead of a bare literal) ---
    "condo.fee_escalation_rate": Anchor(
        name="condo.fee_escalation_rate",
        value=0.0,
        as_of="2026",
        source="FP Canada 2026 PAG §5 'Shelter Projection Considerations' "
               "3.1% nominal (≈ 1.0% real) as the upper reference",
        url="https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf",
        rationale=(
            "Condo fees track inflation absent aging-building pressure ⇒ 0.0% "
            "real. FP Canada 2026 shelter-cost growth 1.0% real is the upper "
            "reference — a fee growing faster than that in real terms is an "
            "aging-building judgment the user should set explicitly."
        ),
        band=(0.0, 0.01),
        short_cite="FP Canada 2026 PAG",
        retrieved_on="2026-09-01",
        kind="reference",
    ),
    "house.value_growth_rate": Anchor(
        name="house.value_growth_rate",
        value=0.0,
        as_of="2026",
        source="hde neutrality ruling — deliberately uncited",
        url="none (deliberately uncited)",
        rationale=(
            "Neutral by construction: no defensible universal long-run real "
            "appreciation default exists for Canadian home prices. Users "
            "should set their own view or wire a market_scenario prior "
            "(ISQ-grounded demographic drift). Band is an illustrative "
            "neutrality range, not a citation."
        ),
        band=(-0.01, 0.02),
        short_cite="neutral, uncited",
        kind="neutral",
    ),
    "condo.value_growth_rate": Anchor(
        name="condo.value_growth_rate",
        value=0.0,
        as_of="2026",
        source="hde neutrality ruling — deliberately uncited",
        url="none (deliberately uncited)",
        rationale=(
            "Neutral by construction: no defensible universal long-run real "
            "appreciation default exists for Canadian home prices. Users "
            "should set their own view or wire a market_scenario prior "
            "(ISQ-grounded demographic drift). Band is an illustrative "
            "neutrality range, not a citation."
        ),
        band=(-0.01, 0.02),
        short_cite="neutral, uncited",
        kind="neutral",
    ),
    "house.annual_maintenance_rate": Anchor(
        name="house.annual_maintenance_rate",
        value=0.0,
        as_of="2026",
        source="hde neutrality ruling — deliberately uncited (operator default "
               "2026-09-01, readiness plan C.1)",
        url="none (deliberately uncited)",
        rationale=(
            "0.0 = no maintenance modelled. The engine does not invent a cost "
            "the user did not state — but it must say it assumed none, so "
            "coherence_warnings fires whenever this key is omitted (a zero-"
            "maintenance house silently favours buying). Reference points for "
            "the user's own value: NAHB 'Operating Costs of Owning a Home' "
            "(2019 AHS) Table 2 — routine maintenance ≈ 0.6% of value/yr for "
            "all homes (0.8% pre-1960 … 0.2% 2010s; narrow definition, minor "
            "repairs only); the '1% rule' budgeting heuristic ≈ 1%. Band spans "
            "none to 1.5%."
        ),
        band=(0.0, 0.015),
        short_cite="neutral, uncited",
        kind="neutral",
    ),
    "simulation.discount_rate": Anchor(
        name="simulation.discount_rate",
        value=0.03,
        as_of="2026",
        source="derivation: equals rent.investment_return_rate — FP Canada 2026 PAG "
               "60/40 balanced ≈ 3.0% real, the household's opportunity cost",
        url="https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf",
        rationale=(
            "A present-value comparison discounts at the return the household could "
            "otherwise earn. With the renter's alternative anchored at 3.0% real, the "
            "same figure is the coherent default: a renter earning the default return "
            "then nets exactly zero on the capital leg, and neither side is handed a "
            "spread by construction. A stronger personal time preference overrides "
            "it; the coherence tripwire warns outside [0, 15%] (units typo)."
        ),
        band=(0.02, 0.06),
        short_cite="FP Canada 2026 PAG (60/40 real)",
        retrieved_on="2026-09-01",
        kind="derivation",
    ),
    "rent.invested_down_payment": Anchor(
        name="rent.invested_down_payment",
        value=0.0,
        as_of="2026",
        source="hde like-for-like ruling — the renter's equivalent capital is a "
               "user input, never a default",
        url="none (deliberately uncited)",
        rationale=(
            "$0 is the only honest default: the engine cannot know what the "
            "renter would invest instead of a down payment. It is charged at year 0 "
            "exactly like the buyer's down payment and credited at its terminal "
            "value, so leaving it at 0 while an owned option puts capital down "
            "assumes the renter's equivalent capital earns exactly the discount "
            "rate (net present value 0) — coherence_warnings says so. Zero-width band: any non-zero value "
            "is the user's, not the engine's."
        ),
        band=(0.0, 0.0),
        short_cite="like-for-like: set explicitly",
        kind="neutral",
    ),
    "economic.inflation_rate": Anchor(
        name="economic.inflation_rate",
        value=0.0,
        as_of="2026",
        source="FP Canada 2026 PAG §5 inflation 2.1%; PAG p.6: CPI averaged "
               "2.5% over the 10 years to Dec 2025 (3.9% over 5 years)",
        url="https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf",
        rationale=(
            "0.0 is the real-mode inert value (inflation is already stripped "
            "from real-terms rates). In nominal mode the FP Canada 2026 "
            "long-term planning assumption is 2.1% — set inflation_rate: 0.021 "
            "when mode=nominal. The PAG publishes no separate short-term "
            "inflation figure (its 2.4% is the short-term INVESTMENT return); "
            "the band top 2.5% is the 10-year realised CPI average the PAG "
            "quotes, a defensible nominal-mode ceiling."
        ),
        band=(0.0, 0.025),
        short_cite="FP Canada 2026 PAG",
        retrieved_on="2026-09-01",
        kind="reference",
    ),
    # --- Planning constants consumed by code paths other than a dataclass
    #     default (warnings text, the drift-sigma fit). Registered so the
    #     number lives in one place and carries its source. ---
    "economic.inflation_rate.nominal_planning": Anchor(
        name="economic.inflation_rate.nominal_planning",
        value=0.021,
        as_of="2026",
        source="FP Canada 2026 PAG §5 inflation 2.1%; PAG p.6: CPI averaged "
               "2.5% over the 10 years to Dec 2025",
        url="https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf",
        rationale=(
            "The nominal-mode planning figure the engine SUGGESTS (never "
            "applies): the coherence warning for nominal mode with "
            "inflation_rate=0 and the --print-schema note both format this "
            "value. Band top 2.5% = the realised 10-year CPI average the PAG "
            "quotes."
        ),
        band=(0.021, 0.025),
        short_cite="FP Canada 2026 PAG",
        retrieved_on="2026-09-01",
    ),
    "market_scenario.drift_sigma_divisor": Anchor(
        name="market_scenario.drift_sigma_divisor",
        value=2.5632,
        as_of="2026",
        source="derivation: standard-normal p10–p90 span = 2 × z₀.₉₀ = 2 × 1.28155",
        url="none — derivation",
        rationale=(
            "The demoflow emitter publishes demo_drift_p10 / demo_drift_p90 per "
            "band. A Normal fitted so its 10th and 90th percentiles match that "
            "band has σ = (p90 − p10) / 2.5631, so the per-path drift draws "
            "reproduce the published deciles. A mathematical identity, not a "
            "measurement; the band is a rounding tolerance."
        ),
        band=(2.5, 2.6),
        short_cite="p10–p90 Normal fit",
        kind="derivation",
    ),
    # --- Verdict decisiveness rule (operator-ruled 2026-09-01, readiness plan
    #     B.2). Derivations, no external source: they define what the engine
    #     is willing to call a clear winner. ---
    "verdict.prob_floor": Anchor(
        name="verdict.prob_floor",
        value=0.65,
        as_of="2026",
        source="hde verdict rule — derivation (operator-ruled 2026-09-01)",
        url="none — derivation",
        rationale=(
            "When Monte Carlo ran with real uncertainty, the deterministic winner "
            "is called a clear winner only if it is cheapest in at least 65% of "
            "simulated futures (≈ 2:1 odds). Below that the user's own stated "
            "uncertainty says the ranking can flip, so the verdict reads 'too "
            "close to call' and quotes the probability. Band: 55% is barely "
            "better than a coin flip; 80% would demand near-certainty from "
            "inputs the user only estimated."
        ),
        band=(0.55, 0.80),
        short_cite="hde verdict rule",
        kind="derivation",
    ),
    "verdict.tie_band": Anchor(
        name="verdict.tie_band",
        value=0.05,
        as_of="2026",
        source="hde verdict rule — derivation (operator-ruled 2026-09-01)",
        url="none — derivation",
        rationale=(
            "Fallback when no Monte Carlo ran or every uncertainty input is off: "
            "the winner must beat the runner-up by at least 5% of its own total "
            "PV. Derivation (measured 2026-09-01 on examples/basic_config.yaml "
            "with house.initial_value 460000): sweeping ONE defaulted input, "
            "selling_cost_rate, across its anchor band 0.03–0.08 moves the margin "
            "by 2.25% of the winner's PV and inverts the Monte Carlo ranking at "
            "the band top; a typical config defaults two or three such inputs, "
            "so a margin inside ~5% sits within the defaults' own uncertainty "
            "and is not a decision."
        ),
        band=(0.02, 0.08),
        short_cite="hde verdict rule",
        kind="derivation",
    ),
}


# ---------------------------------------------------------------------------
# Demographic-prior provenance (readiness plan E.2, 2026-09-01).
#
# A ScenarioPrior file carries source FILE NAMES + sha256 digests under
# data_vintage.source_hashes; the human citation for each lives upstream in
# demoflow's pipeline.RUN_SOURCES (`why` strings) and loaders/pins.py (StatCan
# table ids) and is copied here so hde can say what a source IS from the file
# alone. Form: "<short label> — <detail>"; the label precedes " — ". An unknown
# key renders "uncited source: <key>" — never an invented citation. The emitter
# contract binds these keys to a code-owned registry (demoflow spec §7), so
# this is a closed vocabulary, not free text.
# ---------------------------------------------------------------------------
SOURCE_KEY_CITATIONS: Dict[str, str] = {
    "pop-as-rmr-base.xlsx": (
        "ISQ population scenarios (RMR) — Institut de la statistique du Québec, "
        "Perspectives démographiques, population by age and sex for the census "
        "metropolitan areas, base scenario workbook (edition per data_vintage.isq_edition)"),
    "pop-as-ra-base.xlsx": (
        "ISQ population scenarios (RA) — ISQ Perspectives démographiques, population by "
        "age and sex for the administrative regions, base scenario workbook"),
    "pop-as-qc-base.xlsx": (
        "ISQ population scenarios (QC) — ISQ Perspectives démographiques, Québec total by "
        "single year of age; the headship curve's denominator"),
    "compo-rmr-base.xlsx": (
        "ISQ arrival flows (RMR) — ISQ Perspectives démographiques, components of growth "
        "(migration/arrival flows) for the census metropolitan areas, base scenario"),
    "compo-ra-base.xlsx": (
        "ISQ arrival flows (RA) — ISQ Perspectives démographiques, components of growth "
        "for the administrative regions, base scenario"),
    "census_tenure_age_98100231.csv": (
        "StatCan 98-10-0231-01 — Statistics Canada, 2021 Census, tenure × age of primary "
        "household maintainer; source of the ownership and headship surfaces"),
    "living_arrangement_98100134.json": (
        "StatCan 98-10-0134-01 — Statistics Canada, 2021 Census, living arrangements by sex"),
    "hors_aligned_csd_98100232.json": (
        "StatCan 98-10-0232-01 — Statistics Canada, 2021 Census, census-subdivision extract "
        "aligning the outside-CMA (HORS_RMR) ownership curve"),
    "living_arrangement.json": (
        "derived: living-arrangement shares — computed in demoflow from StatCan "
        "98-10-0134-01 (its _provenance records the extraction date)"),
    "ownership_hors_aligned.json": (
        "derived: HORS_RMR ownership curve — computed in demoflow from StatCan 98-10-0232-01 "
        "census subdivisions"),
    "ownership_by_geo_age.json": (
        "derived: ownership rate by geography × age — computed in demoflow from StatCan "
        "98-10-0231-01"),
    "headship_by_age.json": (
        "derived: headship rate by single year of age — StatCan 98-10-0231-01 maintainers ÷ "
        "ISQ persons (pop-as-qc-base.xlsx)"),
    "mortality_basis:CPM2014_combined+CPM-B": (
        "CIA CPM2014 mortality + CPM-B scale — Canadian Institute of Actuaries, Canadian "
        "Pensioners' Mortality 2014 (combined) with improvement scale CPM-B; the cohort "
        "roll-forward's survival basis (via the actuarial-system package)"),
}

MAPPING_VERSION_NOTES: Dict[str, str] = {
    "1": (
        "excess-demand rate → real price drift through a linear-through-origin β prior "
        "with the uniform β demoflow pinned; horizon bands (2030…2050) are piecewise-"
        "constant with no interpolation; drawdown_weight_tilt multiplies the user's "
        "price-shock hazard (S4b sketch §1 slots 2–3, §3)"),
}


def describe_source_key(key: str) -> str:
    """Human citation for one data_vintage.source_hashes key, or an honest
    'uncited source: <key>' when the registry does not know it."""
    return SOURCE_KEY_CITATIONS.get(key, f"uncited source: {key}")


def source_key_label(key: str) -> str:
    """The short label before ' — ' (e.g. 'StatCan 98-10-0231-01')."""
    return describe_source_key(key).split(" — ", 1)[0]


def describe_mapping_version(version: str) -> str:
    return MAPPING_VERSION_NOTES.get(version, f"undescribed mapping version {version}")


def short_cite(name: str) -> str:
    """Short citation tag for a (possibly defaulted) dotted key, e.g.
    "FP Canada 2026 PAG" — empty string when no anchor exists for the key.
    A `reference` anchor renders as "ref: <tag>" so the echo never credits a
    source with a value it does not state."""
    anchor = ANCHORS.get(_ECHO_ALIASES.get(name, name))
    if anchor is None:
        return ""
    return f"ref: {anchor.short_cite}" if anchor.kind == "reference" else anchor.short_cite
