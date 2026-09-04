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
from typing import Dict, List, Optional, Tuple


class AnchorError(Exception):
    """Raised at import time when an anchor violates citation discipline."""
    pass


ANCHOR_KINDS = frozenset({"cited", "reference", "neutral", "derivation", "unsourced"})

# Dotted-key prefixes of the REFERENCE TABLES (property tax by municipality,
# school tax and home insurance by province, and the posted mortgage rate a
# borrower with no quote can bracket against). These are NOT engine defaults: no
# dataclass falls back to one and the engine never applies one. They are
# published figures the user — or an assistant writing the YAML — chooses from,
# and `serialization.reference_matches` cites one by name when the user's own
# number equals the published number.
#
# Entries here carry two fields the rest of the registry does not need:
# `quoted` (the figure exactly as the source prints it) and `unit` (the base
# that figure is stated on). Both are required at import time, because a
# municipal rate quoted without its base is the most dangerous number in this
# file: a rate on ASSESSED value read as a rate on market value is wrong by
# however far the assessment roll lags the market.
REFERENCE_FAMILIES = ("property_tax.", "school_tax.", "home_insurance.",
                      "mortgage_rate.")

# The families whose entries a single bill can legitimately ADD UP: in Québec an
# owner's property-tax bill IS the municipal rate plus the province-wide school
# rate, and nothing else in the registry composes that way.
_SUMMABLE_WITH_SCHOOL = "property_tax."
_SCHOOL_FAMILY = "school_tax."
# Families whose entries must say which province they are in, because the sum
# above is only valid WITHIN a province: Toronto's total already contains
# Ontario's education rate, so adding Québec's school rate to it would invent a
# bill nobody pays.
_PROVINCE_REQUIRED = (_SUMMABLE_WITH_SCHOOL, _SCHOOL_FAMILY)

# How close a user's own figure must sit to a published one to be called the
# same number. The bar is EQUALITY, not resemblance, and the tolerance exists
# only to absorb rounding in the dollar amount the user typed: half a basis
# point (0.0005pp) covers rounding an annual amount to the nearest dollar on
# any plausible price, and nothing else.
#
# ANCHOR 2026-09-03: a looser 0.005pp window cited « Ville de Québec » for an
# illustrative 0.750%-of-price line in a MONTRÉAL scenario, because Québec
# City's published 0.7464% happened to land inside it. The citation was true
# and the impression it left was false. A near-miss must read "no anchor
# match" — which is itself the useful answer.
_MATCH_TOLERANCE: Dict[str, float] = {
    "property_tax.": 5e-6,
    "home_insurance.": 1.0,
}
# Every other figure is a rate or a fraction, so the rate window governs.
_DEFAULT_MATCH_TOLERANCE = 5e-6


def match_window(name: str) -> float:
    """The equality window for one anchor's figure — the same bar the read-back
    matcher applies, so `sources:` and the read-back can never disagree about
    whether a number IS a published one."""
    for family, tol in _MATCH_TOLERANCE.items():
        if name.startswith(family):
            return tol
    return _DEFAULT_MATCH_TOLERANCE


def is_reference(name: str) -> bool:
    """True for a jurisdiction reference entry (never an engine default)."""
    return name.startswith(REFERENCE_FAMILIES)


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
    # None ONLY for kind="unsourced": a jurisdiction with no fetchable primary
    # source holds no figure at all, rather than a plausible-looking guess.
    value: Optional[float]
    as_of: str
    source: str
    url: str
    rationale: str
    band: Tuple[float, float]
    short_cite: str
    # The figure EXACTLY as the source prints it, in the source's own notation
    # (e.g. "0,4973 $ par 100 $ d'évaluation municipale"). Required for a
    # jurisdiction reference entry: `value` is the engine's decimal reading of
    # it, and a reader who opens the URL must be able to reconcile the two.
    quoted: str = ""
    # What `value` is a rate or amount OF — the base, stated plainly. Required
    # for a jurisdiction reference entry.
    unit: str = ""
    # Province code (e.g. "qc", "on") — required for a property-tax or
    # school-tax entry, because those two are summed only within one province.
    province: str = ""
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
    # The SAME published figure restated in another convention, each with the
    # conversion that produced it: `(value, why)`. A posted Canadian mortgage
    # rate is quoted semi-annually compounded while the engine takes an
    # effective annual rate — 6.09% posted and 6.1827% effective are one figure
    # in two conventions, not two figures, so a config stating either one may
    # cite this anchor as its source.
    restatements: Tuple[Tuple[float, str], ...] = ()
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
        if self.kind not in ANCHOR_KINDS:
            raise AnchorError(
                f"anchor {self.name!r}: kind must be one of {sorted(ANCHOR_KINDS)}, "
                f"got {self.kind!r}"
            )
        if self.kind == "unsourced":
            # The whole point of the state: no source, therefore no figure. An
            # unsourced entry carrying a number would be exactly the defect —
            # a plausible value with nothing behind it — that this registry exists
            # to make impossible.
            if self.value is not None:
                raise AnchorError(
                    f"anchor {self.name!r}: kind='unsourced' carries value "
                    f"{self.value} — a figure with no source does not go in"
                )
            if self.url.startswith("http"):
                raise AnchorError(
                    f"anchor {self.name!r}: kind='unsourced' with a live URL — "
                    f"if the URL carries the figure, cite it"
                )
            if len(self.url.strip()) <= len("none") + 4:
                raise AnchorError(
                    f"anchor {self.name!r}: an unsourced entry must say WHAT WAS "
                    f"TRIED in `url`, not just {self.url!r}"
                )
            if not self.short_cite.strip().startswith("source: none"):
                raise AnchorError(
                    f"anchor {self.name!r}: an unsourced entry must read "
                    f"'source: none' wherever it is cited, got {self.short_cite!r}"
                )
        else:
            if self.value is None:
                raise AnchorError(
                    f"anchor {self.name!r}: only kind='unsourced' may hold no value"
                )
            if not lo <= self.value <= hi:
                raise AnchorError(
                    f"anchor {self.name!r}: central value {self.value} outside its "
                    f"own band {self.band}"
                )
            if is_reference(self.name):
                for field_name in ("quoted", "unit"):
                    if not getattr(self, field_name).strip():
                        raise AnchorError(
                            f"anchor {self.name!r}: a jurisdiction reference entry "
                            f"needs {field_name} — a published figure without the "
                            f"base it is stated on cannot be applied safely"
                        )
        if self.name.startswith(_PROVINCE_REQUIRED) and not self.province.strip():
            raise AnchorError(
                f"anchor {self.name!r}: a property-tax or school-tax entry needs "
                f"`province` — the municipal + school sum is only a real bill "
                f"within one province"
            )
        if self.url.startswith("http") and not self.retrieved_on.strip():
            raise AnchorError(
                f"anchor {self.name!r}: a live URL needs retrieved_on (the date the source was retrieved)"
            )
        for entry in self.restatements:
            if (not isinstance(entry, tuple) or len(entry) != 2
                    or not isinstance(entry[1], str) or not entry[1].strip()):
                raise AnchorError(
                    f"anchor {self.name!r}: each restatement must be "
                    f"(value, the conversion that produced it), got {entry!r}"
                )
            if self.value is None:
                raise AnchorError(
                    f"anchor {self.name!r}: a restatement of a figure that does "
                    f"not exist — an unsourced entry has nothing to restate"
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

    def stated_values(self) -> Tuple[float, ...]:
        """Every form in which this anchor's figure may legitimately appear in
        a config — the published value and its declared restatements."""
        if self.value is None:
            return ()
        return (self.value,) + tuple(v for v, _ in self.restatements)


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

    # --- JURISDICTION REFERENCE TABLES (2026-09-03) -------------------------
    #
    # Property tax and home insurance were the two largest UNSOURCED numbers in
    # a typical run — together roughly 15% of an owned option's year-1 cash,
    # and both were whatever percentage of value the assistant reached for. The
    # engine still applies neither: `other_recurring_costs` stays the user's own
    # dollar figure. What the registry adds is a published figure to compare it
    # against, and a citation when the two agree.
    #
    # THREE RULES HOLD ACROSS THIS SECTION.
    #
    # 1. ASSESSED IS NOT MARKET. Every municipal rate below is levied on the
    #    ASSESSMENT ROLL, not on what the property would sell for today, and no
    #    entry converts one to the other. Québec publishes the gap as the
    #    `proportion médiane` — "un indicateur du niveau général des valeurs
    #    inscrites au rôle d'évaluation d'une municipalité", the ratio of roll
    #    value to actual sale price — and warns that a roll value scaled by the
    #    facteur comparatif is an "évaluation foncière uniformisée", explicitly
    #    a standardised figure rather than a market estimate
    #    (quebec.ca/habitation-territoire/information-fonciere/evaluation-fonciere/
    #    proportions-medianes/a-propos, retrieved 2026-09-03). Ontario's gap is
    #    larger and precisely dated: MPAC states that "Property assessments for
    #    the 2026 property tax year will continue to be based on fully phased-in
    #    January 1, 2016 current values", the province-wide reassessment having
    #    been postponed by regulation filed 2023-08-16
    #    (mpac.ca/en/UnderstandingYourAssessment/AssessmentCycle, retrieved
    #    2026-09-03). An Ontario rate applied to a 2026 PURCHASE PRICE therefore
    #    OVERSTATES the tax by however much the property has appreciated since
    #    January 2016. `unit` says this on every entry, and the read-back
    #    reprints it beside any citation it makes.
    #
    # 2. AD VALOREM ONLY. `value` is the sum of the rate lines charged per
    #    dollar of assessment. Flat per-dwelling charges — Laval's $486 water
    #    service, Québec City's $386 aqueduct and $195 waste tariffs — are real
    #    money and are NOT in the rate; a user's own figure that includes them
    #    will legitimately fail to match, and the rationale says so.
    #
    # 3. THE BAND IS PUBLISHED, NOT IMAGINED. It spans the narrowest to the
    #    broadest reading of the SAME source (municipal-only to full ad-valorem
    #    bill), never an invented plausible range. Where the source publishes
    #    one figure, the band has zero width.
    #
    # School tax is a separate provincial levy in Québec and the education rate
    # is set by Ontario, not the municipality; each entry says which of the two
    # it includes.
    "property_tax.laval": Anchor(
        name="property_tax.laval",
        value=0.005909,
        as_of="2026",
        source="Ville de Laval, budget 2026 — « Autres statistiques : Évolution de "
               "certains taux de taxation, de tarification et de redevance » (p. 73), "
               "régime des taux variés, taux de base (résidentiel 1–5 logements)",
        url="https://www.laval.ca/wp-content/uploads/2026/02/evolution-taux-taxation-tarification.pdf",
        quoted="2026, taux de base, par 100 $ d'évaluation municipale : taxe foncière "
               "générale 0,4973 $ ; taxe foncière spéciale — infrastructures d'eau potable "
               "et d'eaux usées 0,0111 $ ; taxe foncière spéciale — financement de la "
               "contribution à l'ARTM 0,0825 $",
        unit="rate on ASSESSED value (0,5909 $ per 100 $ of municipal assessment) "
             "— assessed ≠ market",
        rationale=(
            "The three ad-valorem lines a Laval residential owner pays, summed: "
            "0,4973 + 0,0111 + 0,0825 = 0,5909 $ per 100 $ = 0.5909% of assessed "
            "value. Band bottom is the general tax alone (0,4973 $), band top the "
            "full ad-valorem total. EXCLUDED and material: the water-service "
            "tariff, a FLAT 486,00 $ per dwelling in 2026 (up from 337,00 $), plus "
            "85,00 $ per pool — not a rate, so not in this figure. Also excluded: "
            "the Québec school tax, levied provincially. Laval's rate fell from "
            "0,5562 $ in 2025 because the roll rose; the rate alone does not say "
            "which way a bill moved. School tax excluded — cited separately as "
            "`school_tax.qc`, which a Laval owner also pays."
        ),
        band=(0.004973, 0.005909),
        short_cite="Ville de Laval 2026",
        province="qc",
        retrieved_on="2026-09-03",
    ),
    "property_tax.montreal": Anchor(
        name="property_tax.montreal",
        value=0.005556,
        as_of="2026",
        source="Ville de Montréal, « Taux de taxes 2026 » (table « Taux de taxation "
               "2026 (en $ / 100 $) », document 2026_taux_taxes.pdf linked from the "
               "city's 2026 tax-rates article; the PDF itself sits behind a document "
               "viewer with no stable direct URL), column « Immeubles résidentiels », "
               "whose footnote reads « le taux applicable aux immeubles de la sous-"
               "catégorie des immeubles 6 logements ou plus et celle qui est "
               "résiduelle » — i.e. it covers ordinary houses and condos",
        url="https://montreal.ca/articles/taux-de-taxes-pour-2026-106147",
        quoted="Taux de taxation 2026 (en $ / 100 $), immeubles résidentiels — taxes "
               "applicables à tous les immeubles de la Ville de Montréal : taxe "
               "foncière générale 0,4631 ; taxe relative à l'ARTM 0,0070 ; taxe "
               "relative au service de la voirie 0,0024 ; taxe relative au service de "
               "l'eau 0,0831",
        unit="rate on ASSESSED value (0,5556 $ per 100 $ of municipal assessment, "
             "CITY-WIDE LINES ONLY — the borough adds more) — assessed ≠ market",
        rationale=(
            "MONTRÉAL HAS NO SINGLE RESIDENTIAL RATE, and the anchor is honest about "
            "which half it holds. The four lines above are levied on every property "
            "in the city and sum to 0,5556 $ per 100 $ = 0.5556% of assessed value; "
            "that is `value`. On top of it every owner also pays two BOROUGH-VARYING "
            "lines from the same table — « taxe relative aux dettes des anciennes "
            "villes » (residential 0,0010 in Lachine to 0,0196 in nine boroughs, « s. "
            "o. » in L'Île-Bizard–Sainte-Geneviève and Pierrefonds–Roxboro) and the "
            "arrondissement's own services + investissements taxes. Worked totals "
            "from the same table: Le Plateau-Mont-Royal 0,5556 + 0,0196 + 0,0513 + "
            "0,0246 = 0,6511 $ per 100 $ (0.6511%); Ville-Marie 0,6229% is the "
            "lowest borough total and Anjou 0,7403% the highest. The band spans "
            "city-wide-only to the highest borough total, so a Montréal figure "
            "matches this anchor only when it is deliberately the city-wide part. "
            "NOT IN THIS SOURCE, and not folded in from anywhere else: the Québec "
            "school tax, levied by the centre de services scolaire — cited "
            "separately as `school_tax.qc`, which a Montréal owner also pays."
        ),
        band=(0.005556, 0.007403),
        short_cite="Ville de Montréal 2026 (city-wide lines)",
        province="qc",
        retrieved_on="2026-09-03",
    ),
    "property_tax.quebec_city": Anchor(
        name="property_tax.quebec_city",
        value=0.007464,
        as_of="2026",
        source="Ville de Québec, « Taux de taxes » (profil financier), exercice "
               "financier 2026, adopted by Règlement sur l'imposition des taxes et "
               "des compensations pour l'exercice financier 2026, R.V.Q. 3492",
        url="https://www.ville.quebec.qc.ca/apropos/profil-financier/taux-taxation.aspx",
        quoted="Par 100 $ d'évaluation — « Immeubles résidentiels de 1 à 5 "
               "logements » : 0.7464 (2026)",
        unit="rate on ASSESSED value (0,7464 $ per 100 $ of municipal assessment) "
             "— assessed ≠ market",
        rationale=(
            "The single ad-valorem residential rate in the city's own 2026 table: "
            "0,7464 $ per 100 $ = 0.7464% of assessed value. Zero-width band — the "
            "source publishes one rate for this class, so there is no second "
            "reading to bracket it with. EXCLUDED and material: the flat per-"
            "dwelling tariffs the same table lists — 386 $ aqueduc et égout and "
            "195 $ matières résiduelles — which together add roughly $580 a year "
            "regardless of value. School tax excluded — cited separately as "
            "`school_tax.qc`, which a Québec owner also pays."
        ),
        band=(0.007464, 0.007464),
        short_cite="Ville de Québec 2026",
        province="qc",
        retrieved_on="2026-09-03",
    ),
    "property_tax.toronto": Anchor(
        name="property_tax.toronto",
        value=0.00767311,
        as_of="2026",
        source="City of Toronto, « Property Tax Rates & Fees », 2026 residential "
               "rate table (municipal rate set by Council; education rate set by "
               "the Province of Ontario)",
        url="https://www.toronto.ca/services-payments/property-taxes-utilities/property-tax/property-tax-rates-and-fees/",
        quoted="Residential (2026): City Tax Rate 0.605295%, Education Tax Rate "
               "0.153000%, City Building Fund 0.009016%, Total Tax Rate 0.767311%",
        unit="rate on ASSESSED value (MPAC CVA — a January 1, 2016 value in the "
             "2026 tax year) — assessed ≠ market",
        rationale=(
            "Total 2026 residential rate 0.767311% of CVA, education included. "
            "Band bottom is the municipal share alone (City 0.605295% + City "
            "Building Fund 0.009016% = 0.614311%), band top the total with the "
            "provincial education rate. THE ASSESSMENT LAG IS A DECADE: MPAC "
            "assesses the 2026 tax year on fully phased-in January 1, 2016 "
            "values, the province-wide reassessment having been postponed. "
            "Applying this rate to a 2026 purchase price overstates the tax by "
            "the whole 2016→2026 appreciation — for the engine's purposes that "
            "makes it a CEILING on the true bill, not an estimate of it."
        ),
        band=(0.00614311, 0.00767311),
        short_cite="City of Toronto 2026",
        province="on",
        retrieved_on="2026-09-03",
    ),
    "school_tax.qc": Anchor(
        name="school_tax.qc",
        value=0.0007899,
        as_of="2026-2027",
        source="Centre de services scolaire des Patriotes (gouv.qc.ca), « Taxe "
               "scolaire » — the single province-wide school tax rate set by the "
               "Québec government under the Loi visant l'instauration d'un taux "
               "unique de taxation scolaire",
        url="https://cssp.gouv.qc.ca/a-propos/taxe-scolaire/",
        quoted="« Un taux unique de taxation scolaire applicable dans l'ensemble du "
               "Québec pour 2026-2027, fixé à 0,07899 $ par 100 $ d'évaluation » ; "
               "« Une exemption pour les premiers 25 000 $ de valeur de l'immeuble »",
        unit="rate on ASSESSED value (0,07899 $ per 100 $ of évaluation uniformisée "
             "ajustée, first $25,000 exempt) — assessed ≠ market",
        rationale=(
            "SEPARATE FROM THE MUNICIPAL RATE, and deliberately in its own family so "
            "the read-back can never cite it for a municipal line. Québec's school "
            "tax is levied by the centre de services scolaire, not the city, and none "
            "of the municipal sources above includes it — so a Québec owner's total "
            "property-tax bill is the municipal rate PLUS this. One rate covers the "
            "whole province for 2026-2027. Two adjustments the flat rate hides: the "
            "base is the évaluation uniformisée AJUSTÉE (the roll value scaled by the "
            "municipality's comparative factor), not the raw roll value, and the "
            "first $25,000 is exempt — on a $600,000 assessment the exemption alone "
            "cuts the effective rate by about 4%. Zero-width band: one published "
            "rate."
        ),
        band=(0.0007899, 0.0007899),
        short_cite="Québec taux unique 2026-2027",
        province="qc",
        retrieved_on="2026-09-03",
    ),
    "property_tax.gatineau": Anchor(
        name="property_tax.gatineau",
        value=None,
        as_of="2026",
        source="none — no single city-wide residential rate exists to cite",
        url="none — tried gatineau.ca's taxes municipales pages and the 2026 budget "
            "documents; the budget's « Taux de taxes 2026 » pages are image-only "
            "scans with no extractable text, and the 2026 explanatory notes PDF "
            "(gatineau.ca/docs/guichet_municipal/taxes_municipales/"
            "notes_explicatives.fr-CA.pdf) likewise carries no machine-readable text",
        rationale=(
            "NOT merely a failed fetch — a structural absence, which is the more "
            "useful finding. Since 2024 Gatineau levies a rate per NEIGHBOURHOOD "
            "UNIT rather than one rate across the city, expressly to damp the "
            "assessment roll's effect on individual bills, so 'the Gatineau "
            "residential rate' is not a quantity that exists. A Gatineau run must "
            "take the rate from the property's own tax bill or the city's online "
            "tax roll for that address; any single percentage offered for the city "
            "is the assistant's own estimate and must be labelled one. The only "
            "2026 figure confirmed is the budgeted residential increase, which is "
            "a change, not a rate."
        ),
        band=(0.0, 0.0),
        short_cite="source: none",
        province="qc",
        kind="unsourced",
    ),
    "property_tax.ottawa": Anchor(
        name="property_tax.ottawa",
        value=None,
        as_of="2026",
        source="none — the 2026 rate-setting by-law was not located in fetchable form",
        url="none — tried ottawa.ca's property-tax-rates and calculating-your-property-"
            "taxes pages (both returned empty), the City's 2026 final-tax mailer at "
            "documents.ottawa.ca (dollar totals only, no rate), and the 2026 tax-policy "
            "report on the Council agenda portal (tax RATIOS by class, not rates); the "
            "Ontario education rate on e-Laws sits behind a JavaScript shell",
        rationale=(
            "No figure is registered rather than a plausible one. Ottawa's rate is "
            "set annually by by-law and the components (city-wide, transit, police, "
            "urban-area, provincial education) are published separately; none was "
            "reached. An Ottawa run must take the rate from the property's own tax "
            "bill, the City's online property-tax estimator, or the rate by-law; a "
            "percentage typed from anywhere else is the assistant's estimate and "
            "must be labelled one. What DOES carry over from the Toronto entry is "
            "the base: Ontario assesses the 2026 tax year on January 1, 2016 MPAC "
            "values (mpac.ca AssessmentCycle, retrieved 2026-09-03), so any Ontario "
            "rate applied to a 2026 purchase price overstates the bill."
        ),
        band=(0.0, 0.0),
        short_cite="source: none",
        province="on",
        kind="unsourced",
    ),
    "home_insurance.qc": Anchor(
        name="home_insurance.qc",
        value=813.0,
        as_of="2023",
        source="Statistics Canada, table 11-10-0222-01, Household spending by "
               "province (Survey of Household Spending), reference year 2023, "
               "released 2025-05-21; line item « Homeowners' insurance premiums "
               "for owned living quarters », statistic « Average expenditure per "
               "household », Quebec",
        url="https://www150.statcan.gc.ca/n1/tbl/csv/11100222-eng.zip",
        quoted="Quebec, Homeowners' insurance premiums for owned living quarters, "
               "average expenditure per household (2023): $813",
        unit="$/yr averaged over ALL Québec households, renters included at $0 "
             "— a floor, not a typical premium",
        rationale=(
            "BIASED LOW AS A HOMEOWNER'S PREMIUM, and by an amount this source "
            "cannot quantify: the denominator is every household in the province, "
            "so every renter enters at $0. Treat it as a FLOOR, not a typical "
            "premium — an owner's actual premium is above it, and a placeholder "
            "the assistant scales up from this floor must be labelled as the "
            "assistant's estimate, never as this figure. No per-province "
            "'average among insured homeowners' source was found: the Insurance "
            "Bureau of Canada Facts Book publishes national totals only, and "
            "StatCan's conditional (reporting-households) series is archived at "
            "2009. Zero-width band: one published figure, no second reading. "
            "Reference year 2023 — three years before the run."
        ),
        band=(813.0, 813.0),
        short_cite="StatCan SHS 2023 (QC)",
        retrieved_on="2026-09-03",
    ),
    "home_insurance.on": Anchor(
        name="home_insurance.on",
        value=1053.0,
        as_of="2023",
        source="Statistics Canada, table 11-10-0222-01, Household spending by "
               "province (Survey of Household Spending), reference year 2023, "
               "released 2025-05-21; line item « Homeowners' insurance premiums "
               "for owned living quarters », statistic « Average expenditure per "
               "household », Ontario",
        url="https://www150.statcan.gc.ca/n1/tbl/csv/11100222-eng.zip",
        quoted="Ontario, Homeowners' insurance premiums for owned living quarters, "
               "average expenditure per household (2023): $1,053",
        unit="$/yr averaged over ALL Ontario households, renters included at $0 "
             "— a floor, not a typical premium",
        rationale=(
            "BIASED LOW AS A HOMEOWNER'S PREMIUM, same construction as the Québec "
            "entry: every renter enters the average at $0. A FLOOR, not a typical "
            "premium; a placeholder scaled up from it is the assistant's estimate "
            "and must be labelled so. No per-province 'average among insured "
            "homeowners' source was found (IBC Facts Book is national-only; the "
            "StatCan conditional series is archived at 2009). Zero-width band. "
            "Reference year 2023."
        ),
        band=(1053.0, 1053.0),
        short_cite="StatCan SHS 2023 (ON)",
        retrieved_on="2026-09-03",
    ),
    # --- Mortgage rate: a POSTED rate, which is a list price -----------------
    "mortgage_rate.posted_5y": Anchor(
        name="mortgage_rate.posted_5y",
        value=0.0609,
        as_of="2026-09-02",
        source="Bank of Canada, Valet series V80691335 « Conventional mortgage: "
               "5-year » — « The interest rate for a 5-year conventional mortgage "
               "offered by chartered banks in Canada », published weekly on "
               "« Interest rates posted for selected products by the major "
               "chartered banks » (bankofcanada.ca/rates/banking-and-financial-"
               "statistics/posted-interest-rates-offered-by-chartered-banks/, "
               "where the same series is labelled « Conventional mortgage - "
               "5-year »)",
        url="https://www.bankofcanada.ca/valet/observations/V80691335/json?recent=52",
        quoted='{"d": "2026-09-02", "V80691335": {"v": "6.09"}} — the latest of '
               'the 52 weekly observations returned, 2025-09-10 through 2026-09-02',
        unit="POSTED conventional 5-year rate, percent per year, semi-annually "
             "compounded (Canadian convention) — 6.09% posted = 6.1827% EFFECTIVE "
             "annual, which is what `mortgage_rate` takes. A list price, not a "
             "quote: rates actually contracted are LOWER (see rationale), so a "
             "run at the posted rate is a CEILING on the financing cost",
        rationale=(
            "THE POSTED RATE IS NOT WHAT ANYONE PAYS, and the series says so "
            "itself: all 52 weekly observations from 2025-09-10 to 2026-09-02 "
            "read 6.09, and the last change in the series was 2025-05-14 "
            "(6.49 → 6.09). A rate that has not moved in sixteen months is a "
            "posted list price that moves in steps, not a market rate — hence "
            "the zero-width band, which is the finding rather than a gap. What "
            "borrowers actually contracted, from the same Valet API (group "
            "A4_RATES_MORTGAGES, « Interest rates charged for new and existing "
            "lending by chartered banks », funds advanced, fixed rate 5 years "
            "and over, reference month 2026-06-01, retrieved 2026-09-04): "
            "V122667786 uninsured 4.35%, V122667780 insured 4.01%. Use the "
            "posted figure to bracket a guess from ABOVE and the borrower's own "
            "quote whenever there is one; a rate typed between them is the "
            "assistant's estimate and must be labelled one."
        ),
        band=(0.0609, 0.0609),
        short_cite="BoC posted 5-yr 2026-09-02",
        retrieved_on="2026-09-04",
        restatements=((0.0618270225,
                       "the engine's `mortgage_rate` is an EFFECTIVE annual rate "
                       "and the posted figure is semi-annually compounded: "
                       "(1 + 0.0609/2)^2 − 1 = 0.0618270225"),),
    ),
}


# ---------------------------------------------------------------------------
# Mortgage loan insurance (round 7, 2026-09-03).
#
# An insured mortgage's premium is a step function of loan-to-value, and every
# insured serve of round 7 computed it by hand from recalled tiers — twice with
# the wrong provincial tax rate, once held fixed while a price scan walked the
# loan-to-value across a band edge. The schedule below was FETCHED on
# 2026-09-03 and every band is registered as its own anchor, so
# `hde --print-anchors` shows the table the engine actually applies and
# src/hde/mortgage_insurance.py builds the schedule FROM this registry (one
# edit, not two).
#
# CMHC, Sagen and Canada Guaranty publish the identical standard schedule;
# CMHC is the anchor and Sagen was fetched the same day as a cross-check.
# ---------------------------------------------------------------------------

_CMHC_URL = (
    "https://www.cmhc-schl.gc.ca/professionals/project-funding-and-mortgage-financing/"
    "mortgage-loan-insurance/mortgage-loan-insurance-homeownership-programs/"
    "premium-information-for-homeowner-and-small-rental-loans"
)
_CMHC_SOURCE = (
    "CMHC, 'Mortgage Loan Insurance: Premium Information for Homeowner and Small "
    "Rental Loans' — premium schedule for homeowner loans, quoted as published: "
    "up to and including 65% 0.60%; 65.01% to 75% 1.70%; 75.01% to 80% 2.40%; "
    "80.01% to 85% 2.80%; 85.01% to 90% 3.10%; 90.01% to 95% 4.00%; "
    "90.01% to 95% with a non-traditional down payment 4.50%. Maximum "
    "loan-to-value 95%. 'An amortization period beyond 25 years is subject to a "
    "0.20% surcharge.' 'Some provinces (currently Ontario, Quebec and "
    "Saskatchewan) apply provincial sales tax to the mortgage loan insurance "
    "premium. The sales tax can't be added to the loan amount.' Sagen's premium "
    "rates chart (https://www.sagen.ca/tools-and-resources/premium-rates-chart/, "
    "retrieved 2026-09-03) carries the identical bands and rates."
)
# (registry key suffix, upper LTV edge inclusive, rate, the band as published)
_CMHC_PREMIUM_BANDS = (
    ("ltv_65", 0.65, 0.0060, "up to and including 65%"),
    ("ltv_65_75", 0.75, 0.0170, "65.01% to 75%"),
    ("ltv_75_80", 0.80, 0.0240, "75.01% to 80%"),
    ("ltv_80_85", 0.85, 0.0280, "80.01% to 85%"),
    ("ltv_85_90", 0.90, 0.0310, "85.01% to 90%"),
    ("ltv_90_95", 0.95, 0.0400, "90.01% to 95%"),
)

ANCHORS.update({
    f"mortgage_insurance.premium_rate.{key}": Anchor(
        name=f"mortgage_insurance.premium_rate.{key}",
        value=rate,
        as_of="2026",
        source=_CMHC_SOURCE,
        url=_CMHC_URL,
        rationale=(
            f"The published premium on the total loan amount for the {label} "
            f"loan-to-value band. A quoted schedule rate, not an estimate: it has "
            f"no plausible range, so its band is the rate itself. The premium is "
            f"charged on the loan BEFORE it is added to the loan, and a purchase "
            f"at or under 80% loan-to-value is conventional and pays no premium "
            f"at all — the sub-80% rows belong to CMHC's other products and are "
            f"registered for provenance, not applied to a purchase."
        ),
        band=(rate, rate),
        short_cite="CMHC 2026 premium schedule",
        retrieved_on="2026-09-03",
    )
    for key, _edge, rate, label in _CMHC_PREMIUM_BANDS
})

ANCHORS["mortgage_insurance.max_ltv"] = Anchor(
    name="mortgage_insurance.max_ltv",
    value=0.95,
    as_of="2026",
    source=_CMHC_SOURCE,
    url=_CMHC_URL,
    rationale=(
        "'Maximum Loan-to-Value Ratio: 95%' — the schedule's top band ends there "
        "and no insured purchase is written above it, so a config asking for more "
        "is refused with both figures rather than silently priced at the top "
        "tier. Measured on the loan BEFORE the financed premium: the premium "
        "itself pushes the balance past 95% of price by design."
    ),
    band=(0.95, 0.95),
    short_cite="CMHC 2026 premium schedule",
    retrieved_on="2026-09-03",
)

ANCHORS["mortgage_insurance.amortization_surcharge"] = Anchor(
    name="mortgage_insurance.amortization_surcharge",
    value=0.0020,
    as_of="2026",
    source=_CMHC_SOURCE,
    url=_CMHC_URL,
    rationale=(
        "'An amortization period beyond 25 years is subject to a 0.20% "
        "surcharge.' Added to the band rate whenever mortgage_term_years — the "
        "amortization — exceeds 25. Sagen states the same surcharge for "
        "amortizations up to 30 years; beyond 30 the engine still applies only "
        "this surcharge, and insured eligibility beyond 30 years is not modelled."
    ),
    band=(0.0020, 0.0020),
    short_cite="CMHC 2026 premium schedule",
    retrieved_on="2026-09-03",
)

ANCHORS["mortgage_insurance.premium_tax_rate.qc"] = Anchor(
    name="mortgage_insurance.premium_tax_rate.qc",
    value=0.09,
    as_of="2026",
    source=(
        "Revenu Québec, 'Harmonization of the insurance premiums tax rate with "
        "the QST rate' (tax news, 2026-04-09), enacting Bill 99 (2025, c. 27): "
        "the tax on insurance premiums rises from 9% to 9.975% for premiums paid "
        "after 2026-12-31. revenuquebec.ca refused automated retrieval (HTTP 403 "
        "on 2026-09-03), so the figure is cited through two independently fetched "
        "quotations of that notice — Norton Rose Fulbright (the URL here) and "
        "Baker Tilly Canada "
        "(https://www.bakertilly.ca/insights/taxalert-qc-2026-budget) — and not "
        "from the primary page"
    ),
    url="https://www.nortonrosefulbright.com/en/knowledge/publications/252de415/quebec-ipt-rate-increase-and-fapi-clarifications",
    rationale=(
        "Québec taxes the mortgage-insurance premium at 9%, paid in cash at "
        "closing — CMHC: 'The sales tax can't be added to the loan amount.' 9% is "
        "the rate for a closing on or before 2026-12-31; a closing after that pays "
        "9.975%, so the band spans the step and this anchor must be re-read for "
        "any 2027 closing. The engine applies 9% and the assumptions line names "
        "the rate it used."
    ),
    band=(0.09, 0.09975),
    short_cite="Revenu Québec IPT",
    retrieved_on="2026-09-03",
)

ANCHORS["mortgage_insurance.premium_tax_rate.on"] = Anchor(
    name="mortgage_insurance.premium_tax_rate.on",
    value=0.08,
    as_of="2026",
    source=(
        "Ontario Ministry of Finance, Retail Sales Tax — Insurance and Benefits "
        "Plans: 'Retail Sales Tax (RST) at the rate of eight per cent applies to "
        "premiums paid under taxable insurance contracts.' The same page notes "
        "that 'Initiation and underwriting fees in respect of mortgage insurance "
        "are also non-taxable' — the fees, not the premium; CMHC names Ontario as "
        "a province that applies provincial sales tax to the mortgage loan "
        "insurance premium"
    ),
    url="https://www.ontario.ca/document/retail-sales-tax/insurance-and-benefits-plans",
    rationale=(
        "Ontario's 8% RST on the mortgage-insurance premium, paid in cash at "
        "closing (it cannot be added to the loan). A legislated rate: the band is "
        "the rate itself."
    ),
    band=(0.08, 0.08),
    short_cite="Ontario RST",
    retrieved_on="2026-09-03",
)

# Saskatchewan also taxes the premium (CMHC names Ontario, Québec and
# Saskatchewan) but its rate was not fetched, so there is NO anchor for it: a
# config declaring province: SK is refused with a pointer to an explicit
# schedule rather than silently charged 0% tax.
PREMIUM_TAX_UNANCHORED = ("SK",)


# ---------------------------------------------------------------------------
# Land-transfer tax (round 8, 2026-09-04).
#
# In Québec the droits sur les mutations immobilières — the "welcome tax" — are
# the largest one-time cost of a purchase after the down payment, and they are a
# PUBLISHED BRACKET SCHEDULE. Eight of eight real answers in the week to
# 2026-09-04 priced them inside a 1.5%-of-price guess labelled "no source": on a
# $650,000 Montréal house that guess reads $9,750 against a published $8,349.
#
# All four schedules below were FETCHED on 2026-09-04 and every bracket is its
# own anchor, so `hde --print-anchors` shows the tables the engine applies and
# src/hde/land_transfer_tax.py builds its schedules FROM this registry. The
# THRESHOLD lives in the anchor's NAME (`…to_62900`, `…over_315000`) and the
# RATE is its value, so the registry dump alone carries the whole schedule.
#
# Two structures, and they are not interchangeable:
#   * Montréal REPLACES the provincial schedule (montreal.ca publishes one
#     complete table, and its own worked example balances only that way);
#   * Toronto ADDS to Ontario's — toronto.ca: the MLTT "has been applied to
#     purchases on all properties in the City of Toronto in addition to the
#     Provincial Land Transfer Tax as of February 1, 2008".
#
# The base d'imposition / value of consideration is the GREATER of the price
# paid and the municipal assessment times the year's comparative factor. The
# engine applies the PRICE: for a market transaction the price is normally the
# greater, and the engine has no assessment roll. A purchase well under
# assessment is under-taxed by this model, which the schema note says.
# ---------------------------------------------------------------------------

_QC_LTT_URL = ("https://www.quebec.ca/gouvernement/gestion-municipale/"
               "finances-fiscalite-municipales/fiscalite/droits-mutations-immobilieres")
_QC_LTT_SOURCE = (
    "Gouvernement du Québec, « Droits sur les mutations immobilières » (Loi "
    "concernant les droits sur les mutations immobilières, RLRQ c. D-15.1), "
    "quoted as published: « Le droit de mutation est ensuite calculé sur ce "
    "montant en y appliquant, pour l'exercice financier 2026, les taux "
    "suivants : 0,5 % sur les premiers 62 900 $; 1,0 % sur la tranche de "
    "62 900,01 $ à 315 000 $; 1,5 % sur la tranche qui excède 315 000 $. » The "
    "thresholds are indexed annually to Québec's CPI, so this table is a 2026 "
    "table and must be re-fetched for a 2027 closing. The page adds: « Une "
    "municipalité peut, par règlement, fixer un taux supérieur sur toute "
    "tranche supérieure à 500 000 $. Un tel taux ne peut toutefois excéder 3 %, "
    "sauf dans le cas de la Ville de Montréal qui peut fixer un taux "
    "supérieur. » — so this provincial table is the floor outside Montréal, and "
    "a municipality that legislated its own higher band above $500,000 is NOT "
    "in this registry")
_QC_LTT_UNIT = ("fraction of the tranche of the base d'imposition (the greater of the "
                "price paid and the municipal assessment × the year's comparative "
                "factor); the engine applies the price")

_MTL_LTT_URL = ("https://montreal.ca/articles/"
                "comment-sont-calcules-les-droits-sur-les-mutations-immobilieres-9279")
_MTL_LTT_SOURCE = (
    "Ville de Montréal, « Comment sont calculés les droits sur les mutations "
    "immobilières », 2026 table quoted as published: « Jusqu'à 62 900 $ 0,5 % · "
    "62 900 $ à 315 000 $ 1 % · 315 000 $ à 552 300 $ 1,5 % · 552 300 $ à "
    "1 104 700 $ 2 % · 1 104 700 $ à 2 136 500 $ 2,5 % · 2 136 500 $ à "
    "3 113 000 $ 3,5 % · À partir de 3 113 000 $ 4 % ». The same page prints a "
    "2026 worked example on a 700 000 $ base — 62 900 $ x 0,5 % = 314,50 $; "
    "252 100 $ x 1 % = 2 521,00 $; 237 300 $ x 1,5 % = 3 559,50 $; 147 700 x "
    "2 % = 2 954,00 $; total 9 349,00 $ — which the engine reproduces exactly "
    "(tests/test_land_transfer_tax.py). Montréal's table REPLACES the "
    "provincial one: the province lets Montréal set its own rates above "
    "500 000 $ with no 3% ceiling")

_ON_LTT_URL = "https://www.ontario.ca/document/land-transfer-tax/calculating-land-transfer-tax"
_ON_LTT_SOURCE = (
    "Ontario Ministry of Finance, 'Land Transfer Tax — Calculating land "
    "transfer tax', rates for agreements entered into after 2016-11-14, quoted "
    "as published: 'amounts up to and including $55,000: 0.5%; amounts "
    "exceeding $55,000, up to and including $250,000: 1.0%; amounts exceeding "
    "$250,000, up to and including $400,000: 1.5%; amounts exceeding $400,000: "
    "2.0%; amounts exceeding $2,000,000, where the land contains one or two "
    "single family residences: 2.5%'. The engine models a home purchase, so the "
    "2.5% band applies above $2,000,000; land that is NOT one or two single "
    "family residences stays at 2.0% and needs an explicit schedule")
_ON_LTT_UNIT = "fraction of the tranche of the value of consideration"

_TO_LTT_URL = ("https://www.toronto.ca/services-payments/property-taxes-utilities/"
               "municipal-land-transfer-tax-mltt/"
               "municipal-land-transfer-tax-mltt-rates-and-fees/")
_TO_LTT_SOURCE = (
    "City of Toronto, 'Municipal Land Transfer Tax (MLTT) & Municipal "
    "Non-Resident Speculation Tax — Rates & Fees' (Toronto Municipal Code "
    "Chapter 760), graduated MLTT rates 'for high value residential properties "
    "containing at least one, and not more than two, single family residences', "
    "quoted as published: 'Up to and including $55,000.00 0.5% · $55,000.01 to "
    "$250,000.00 1.0% · $250,000.01 to $400,000.00 1.5% · $400,000.01 to "
    "$2,000,00.00 2.0% · $2,000,000.01 and up to 3,000,000.00 2.5%' then, "
    "'Rates as of April 1, 2026': 'Over $3,000,000 and up to $4,000,000 4.40% · "
    "Over $4,000,000 and up to $5,000,000 5.45% · Over $5,000,000 and up to "
    "$10,000,000 6.50% · Over $10,000,000 and up to $20,000,000 7.55% · Over "
    "$20,000,000 8.60%'. The page prints '$2,000,00.00' for the fourth band's "
    "ceiling — a missing digit, read as $2,000,000.00, which the neighbouring "
    "'$2,000,000.01 and up to 3,000,000.00' row confirms. The MLTT 'has been "
    "applied to purchases on all properties in the City of Toronto in addition "
    "to the Provincial Land Transfer Tax as of February 1, 2008', so the engine "
    "charges Ontario's schedule AND this one. Non-single-family residences pay "
    "a flat 2.0% above $400,000 and need an explicit schedule")

# (registry key suffix, upper edge inclusive — None for the uncapped top band,
#  rate, the band exactly as the source prints it)
_QC_LTT_BRACKETS = (
    ("to_62900", 62_900.0, 0.005, "0,5 % sur les premiers 62 900 $"),
    ("to_315000", 315_000.0, 0.010, "1,0 % sur la tranche de 62 900,01 $ à 315 000 $"),
    ("over_315000", None, 0.015, "1,5 % sur la tranche qui excède 315 000 $"),
)
_MTL_LTT_BRACKETS = (
    ("to_62900", 62_900.0, 0.005, "Jusqu'à 62 900 $ : 0,5 %"),
    ("to_315000", 315_000.0, 0.010, "62 900 $ à 315 000 $ : 1 %"),
    ("to_552300", 552_300.0, 0.015, "315 000 $ à 552 300 $ : 1,5 %"),
    ("to_1104700", 1_104_700.0, 0.020, "552 300 $ à 1 104 700 $ : 2 %"),
    ("to_2136500", 2_136_500.0, 0.025, "1 104 700 $ à 2 136 500 $ : 2,5 %"),
    ("to_3113000", 3_113_000.0, 0.035, "2 136 500 $ à 3 113 000 $ : 3,5 %"),
    ("over_3113000", None, 0.040, "À partir de 3 113 000 $ : 4 %"),
)
_ON_LTT_BRACKETS = (
    ("to_55000", 55_000.0, 0.005, "amounts up to and including $55,000: 0.5%"),
    ("to_250000", 250_000.0, 0.010,
     "amounts exceeding $55,000, up to and including $250,000: 1.0%"),
    ("to_400000", 400_000.0, 0.015,
     "amounts exceeding $250,000, up to and including $400,000: 1.5%"),
    ("to_2000000", 2_000_000.0, 0.020, "amounts exceeding $400,000: 2.0%"),
    ("over_2000000", None, 0.025,
     "amounts exceeding $2,000,000, where the land contains one or two single "
     "family residences: 2.5%"),
)
_TO_LTT_BRACKETS = (
    ("to_55000", 55_000.0, 0.005, "Up to and including $55,000.00 — 0.5%"),
    ("to_250000", 250_000.0, 0.010, "$55,000.01 to $250,000.00 — 1.0%"),
    ("to_400000", 400_000.0, 0.015, "$250,000.01 to $400,000.00 — 1.5%"),
    ("to_2000000", 2_000_000.0, 0.020, "$400,000.01 to $2,000,00.00 [sic] — 2.0%"),
    ("to_3000000", 3_000_000.0, 0.025, "$2,000,000.01 and up to 3,000,000.00 — 2.5%"),
    ("to_4000000", 4_000_000.0, 0.0440, "Over $3,000,000 and up to $4,000,000 — 4.40%"),
    ("to_5000000", 5_000_000.0, 0.0545, "Over $4,000,000 and up to $5,000,000 — 5.45%"),
    ("to_10000000", 10_000_000.0, 0.0650, "Over $5,000,000 and up to $10,000,000 — 6.50%"),
    ("to_20000000", 20_000_000.0, 0.0755, "Over $10,000,000 and up to $20,000,000 — 7.55%"),
    ("over_20000000", None, 0.0860, "Over $20,000,000 — 8.60%"),
)

# family -> (label, url, source, unit, brackets, short cite)
TRANSFER_TAX_SCHEDULES = {
    "land_transfer_tax.qc": (
        "Québec droits sur les mutations immobilières 2026",
        _QC_LTT_URL, _QC_LTT_SOURCE, _QC_LTT_UNIT, _QC_LTT_BRACKETS,
        "Québec DMI 2026"),
    "land_transfer_tax.montreal": (
        "Ville de Montréal droits de mutation 2026",
        _MTL_LTT_URL, _MTL_LTT_SOURCE, _QC_LTT_UNIT, _MTL_LTT_BRACKETS,
        "Ville de Montréal DMI 2026"),
    "land_transfer_tax.ontario": (
        "Ontario land transfer tax",
        _ON_LTT_URL, _ON_LTT_SOURCE, _ON_LTT_UNIT, _ON_LTT_BRACKETS,
        "Ontario LTT"),
    "land_transfer_tax.toronto": (
        "Toronto municipal land transfer tax",
        _TO_LTT_URL, _TO_LTT_SOURCE, _ON_LTT_UNIT, _TO_LTT_BRACKETS,
        "Toronto MLTT"),
}

for _family, (_label, _url, _source, _unit, _rows, _cite) in TRANSFER_TAX_SCHEDULES.items():
    for _key, _edge, _rate, _quoted in _rows:
        _ceiling = ("with no ceiling" if _edge is None
                    else f"up to and including ${_edge:,.2f}")
        ANCHORS[f"{_family}.{_key}"] = Anchor(
            name=f"{_family}.{_key}",
            value=_rate,
            as_of="2026",
            source=_source,
            url=_url,
            rationale=(
                f"{_label}: the marginal rate on the tranche {_ceiling}. A "
                f"legislated schedule rate, not an estimate — it has no plausible "
                f"range, so its band is the rate itself. The threshold is in this "
                f"anchor's NAME, so --print-anchors carries the whole schedule. "
                f"The tax is a ONE-TIME cash cost at closing, paid on top of "
                f"notary and inspection fees."
            ),
            band=(_rate, _rate),
            short_cite=_cite,
            quoted=_quoted,
            unit=_unit,
            retrieved_on="2026-09-04",
        )

ANCHORS["land_transfer_tax.ontario.first_time_buyer_refund_max"] = Anchor(
    name="land_transfer_tax.ontario.first_time_buyer_refund_max",
    value=4_000.0,
    as_of="2026",
    source=(
        "Ontario Ministry of Finance, 'Land Transfer Tax Refunds for First-Time "
        "Homebuyers': 'Beginning January 1, 2017, the maximum amount of the "
        "refund is $4,000.' The refund applies to conveyances or dispositions "
        "occurring on or after 2017-01-01 regardless of when the agreement of "
        "purchase and sale was signed; before that date the maximum was $2,000"
    ),
    url=("https://www.ontario.ca/document/land-transfer-tax/"
         "land-transfer-tax-refunds-first-time-homebuyers"),
    rationale=(
        "Applied to the ONTARIO leg only, and capped at that leg's tax: a "
        "refund never exceeds the duty it refunds. The engine models the "
        "MAXIMUM, not eligibility — the buyer's age, residency, spouse's "
        "ownership history and occupancy deadline are conditions the engine "
        "cannot check, so first_time_buyer: true is the user's assertion that "
        "they qualify."
    ),
    band=(4_000.0, 4_000.0),
    short_cite="Ontario LTT first-time refund",
    quoted="the maximum amount of the refund is $4,000",
    unit="dollars, maximum refund of Ontario land transfer tax",
    retrieved_on="2026-09-04",
)

ANCHORS["land_transfer_tax.toronto.first_time_buyer_rebate_max"] = Anchor(
    name="land_transfer_tax.toronto.first_time_buyer_rebate_max",
    value=4_475.0,
    as_of="2026",
    source=(
        "City of Toronto, 'Municipal Land Transfer Tax & Municipal "
        "Non-Resident Speculation Tax Rebate Opportunities': 'For conveyances "
        "and dispositions of beneficial interest in land of an eligible home "
        "and a rebate of up to $4,475.00.' The same page states the "
        "first-time-purchaser conditions (at least 18; occupy as principal "
        "residence within nine months; never owned a home anywhere in the "
        "world; spouse conditions)"
    ),
    url=("https://www.toronto.ca/services-payments/property-taxes-utilities/"
         "municipal-land-transfer-tax-mltt/"
         "municipal-land-transfer-tax-mltt-rebate-opportunities/"),
    rationale=(
        "Applied to the TORONTO leg only and capped at that leg's tax; it "
        "stacks with Ontario's $4,000 refund because the two taxes stack. A "
        "2026 City Council item was reported to raise this to a full rebate "
        "for values of consideration from $400,000 to $800,000 effective "
        "2026-03-01; the rebate page as fetched on 2026-09-04 still prints "
        "$4,475.00 and no such range, so the engine applies $4,475 and names "
        "it — re-read this anchor before relying on a Toronto first-time "
        "figure."
    ),
    band=(4_475.0, 4_475.0),
    short_cite="Toronto MLTT first-time rebate",
    quoted="a rebate of up to $4,475.00",
    unit="dollars, maximum rebate of Toronto municipal land transfer tax",
    retrieved_on="2026-09-04",
)

# No first-time-buyer rebate of the transfer duty was found for either Québec
# schedule, so neither holds a figure. An absent rebate is REPORTED — a 0.0
# would read as "the province has none", which is a claim this registry has no
# source for.
ANCHORS["land_transfer_tax.qc.first_time_buyer_rebate"] = Anchor(
    name="land_transfer_tax.qc.first_time_buyer_rebate",
    value=None,
    as_of="2026",
    source=("no source: the Québec droits-sur-les-mutations-immobilières page "
            "describes no first-time-buyer rebate or exemption of the duty, and "
            "no provincial program page stating one was found"),
    url=("tried: quebec.ca droits-mutations-immobilieres (fetched 2026-09-04, "
         "no first-time-buyer rebate of the duty described)"),
    rationale=("first_time_buyer: true against the Québec provincial schedule "
               "changes nothing, and the read-back says so rather than "
               "implying a rebate of zero was computed"),
    band=(0.0, 0.0),
    short_cite="source: none (no Québec first-time-buyer transfer-duty rebate found)",
    kind="unsourced",
)

ANCHORS["land_transfer_tax.montreal.first_time_buyer_rebate"] = Anchor(
    name="land_transfer_tax.montreal.first_time_buyer_rebate",
    value=None,
    as_of="2026",
    source=("no source: Montréal runs a « Programme d'appui à l'acquisition "
            "résidentielle » that can reimburse the mutation duty for some "
            "first buyers, but it is a subsidy with eligibility conditions "
            "rather than a rebate of the schedule, and no page stating its "
            "amount was retrieved"),
    url=("tried: montreal.ca/en/topics/property-transfer-duties-welcome-tax "
         "(HTTP 404 on 2026-09-04); the droits-de-mutation article carries the "
         "brackets but no first-time-buyer rebate"),
    rationale=("first_time_buyer: true against the Montréal schedule applies "
               "nothing and the read-back names the gap — a buyer who may "
               "qualify for the city's acquisition program should check it "
               "outside the engine"),
    band=(0.0, 0.0),
    short_cite="source: none (Montréal acquisition program not retrieved)",
    kind="unsourced",
)


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


def match_reference(family: str, value: Optional[float], tol: Optional[float] = None) -> List[Anchor]:
    """Every jurisdiction entry in `family` whose published figure equals
    `value`, within the family's tolerance.

    The read-back's whole trigger: the engine never applies these figures, so
    the only honest moment to name one is when the user's own number IS it.
    Returns ALL matches in name order — two jurisdictions can levy the same
    rate, and picking one of them would be a coin flip presented as a fact.
    An unsourced entry (no value) can never match.
    """
    if value is None:
        return []
    if tol is None:
        tol = _MATCH_TOLERANCE.get(family, 0.0)
    return [
        anchor for name, anchor in sorted(ANCHORS.items())
        if name.startswith(family) and anchor.value is not None
        and abs(anchor.value - value) <= tol
    ]


def match_reference_sum(
    family: str, value: Optional[float], tol: Optional[float] = None,
) -> List[Tuple[Anchor, Anchor]]:
    """Every (municipal property tax, school tax) pair whose published rates SUM
    to `value`, within the family's tolerance.

    A Québec owner's property-tax bill IS the municipal rate plus the province-
    wide school rate — the two are separate entries precisely because separate
    bodies levy them, and a config that sets `property_tax_rate` to their sum is
    the most careful configuration there is. Before this, that number matched
    nothing and the read-back printed "no anchor match" on a figure built
    entirely from anchors: the citation degraded exactly where the care went in.

    Only this ONE combination is recognised. A sum of two municipal rates is not
    a bill anyone pays, and a municipal rate from one province plus another
    province's school rate is not either — Toronto's published total already
    contains Ontario's education rate. Pairing is therefore municipal + school
    WITHIN one province, by the `province` field both are required to carry.
    Returns the pairs in municipal-name order (the school anchor is second).
    """
    if value is None or family != _SUMMABLE_WITH_SCHOOL:
        return []
    if tol is None:
        tol = _MATCH_TOLERANCE.get(family, 0.0)
    schools = {
        anchor.province: anchor
        for name, anchor in sorted(ANCHORS.items())
        if name.startswith(_SCHOOL_FAMILY) and anchor.value is not None
    }
    pairs: List[Tuple[Anchor, Anchor]] = []
    for name, municipal in sorted(ANCHORS.items()):
        if not name.startswith(_SUMMABLE_WITH_SCHOOL) or municipal.value is None:
            continue
        school = schools.get(municipal.province)
        if school is None:
            continue
        if abs(municipal.value + school.value - value) <= tol:
            pairs.append((municipal, school))
    return pairs


def short_cite(name: str) -> str:
    """Short citation tag for a (possibly defaulted) dotted key, e.g.
    "FP Canada 2026 PAG" — empty string when no anchor exists for the key.
    A `reference` anchor renders as "ref: <tag>" so the echo never credits a
    source with a value it does not state."""
    anchor = ANCHORS.get(_ECHO_ALIASES.get(name, name))
    if anchor is None:
        return ""
    return f"ref: {anchor.short_cite}" if anchor.kind == "reference" else anchor.short_cite
