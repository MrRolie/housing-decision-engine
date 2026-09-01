# Provenance remediation — design + verified citation table

**Status:** landed 2026-09-01 (this document is the design record the uncommitted
2026-08-28..09-01 work did not carry; see `docs/plans/2026-09-01-readiness-polish.md`
Step 0.1). **Scope:** `src/hde/anchors.py`, the three-way default pin, the assumptions
echo, the time-anchor guard, and the example provenance headers.

## 1. Why

A housing verdict is a function of a handful of rates the user rarely states: investment
return on the renter's capital, rent escalation, income growth, selling costs, crash
severity. Before this work those defaults were bare literals in `models.py` and
`config.py` (0.07 real return, 0.03 rent escalation, 0.35 affordability) with no
derivation — and two of them (0.07, 0.03) were nominal-looking numbers applied in real
mode. The product mandate is that a user can ask "where did that number come from?" about
any figure and get an answer. That requires every silently-applied default to carry a
source, a date, a rationale and a plausible band, in one place, enforced at import.

## 2. Design (as built)

- **Registry:** `ANCHORS: Dict[str, Anchor]` in `src/hde/anchors.py`. `Anchor` is a frozen
  dataclass: `name, value, as_of, source, url, rationale, band, short_cite, retrieved_on,
  replaces`. `__post_init__` raises `AnchorError` at import on an empty citation field, a
  band that does not bracket its own value, a live URL with no `retrieved_on`, or a
  `replaces` without a why.
- **Three-way pin:** dataclass defaults (`models.py`) and parser defaults (`config.py`)
  both read `ANCHORS[...].value`; `tests/test_anchors.py::TestThreeWayPin` asserts
  dataclass == parser == anchor.
- **Echo:** `spec.defaults_applied` (populated by `config._defaults_applied`) lists every
  assumption key the YAML did not provide; `reporting.format_assumptions` renders each
  with `anchors.short_cite(key)` as a `[tag]`. `_ECHO_ALIASES` folds
  `condo.selling_cost_rate` / `house.selling_cost_rate` onto the single
  `condo.house.selling_cost_rate` anchor so the two options cannot cite differently.
- **Honesty markings:** an anchor whose value is a calibration choice says so in
  `source` (`price_shock.severity_vol`: "CALIBRATED TO ANCHOR, NOT INDEPENDENTLY
  SOURCED"); a deliberately neutral default says "neutral, uncited"
  (`house.value_growth_rate`, `condo.value_growth_rate`). A plausible-sounding source is
  never invented for a number the source does not state.
- **Time anchor:** `market_scenario.time_anchor_violations(current_year, constants_as_of)`
  flags a wall clock past `START_CALENDAR_YEAR` (warning at the CLI/MCP edge) and a prior
  whose `constants_as_of` is more than one year from it (hard refusal in the loader).
- **Examples:** every YAML opens with a `# --- Parameter provenance ---` block; each
  assumption-bearing line is either cited or marked `illustrative`.

## 3. Verified citation table (retrieved 2026-09-01)

Method: each URL fetched live; the quoted figure located in the source text; primary
sources substituted for secondary summaries where one exists. "Figure quoted" is the
source's own number; "Anchor value" is what the engine applies and how it is derived.

| Anchor | Anchor value | Source (primary) | Figure quoted in source | Derivation / note |
|---|---|---|---|---|
| `rent.investment_return_rate` | 0.03 real | FP Canada Standards Council + Institute of Financial Planning, *2026 Projection Assumption Guidelines* (April 2026), §5 — [PDF](https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf) | U.S. equities 6.4%, fixed income 3.2%, inflation 2.1% (nominal geometric means, before fees); emerging markets 7.5% | 0.6×6.4 + 0.4×3.2 = 5.12% nominal ⇒ (1.0512/1.021)−1 ≈ 2.96% ≈ 3.0% real. Equity ceiling: (1.075/1.021)−1 ≈ 5.3% real (was misquoted as ~5.2%). Replaces 0.07 (uncited). |
| `rent.rent_escalation_rate` | 0.01 real | FP Canada 2026 PAG §5 "Shelter Projection Considerations" (new in 2026) | 3.1% (inflation + 1%) | 3.1 − 2.1 = 1.0% real. Floor 0.0% real: Québec TAL 2026 base rate 3.1% = 3-year CPI average ([TAL notice](https://www.tal.gouv.qc.ca/fr/actualites/detail?code=diffusion-des-pourcentages-applicables-a-la-fixation-de-loyer-2026)); continuing tenants receive ~21% pass-through of market-rent moves — Ball & Koh, NBER WP 34113, [NBER Digest Oct 2025](https://www.nber.org/digest/202510/understanding-lag-between-cpi-shelter-inflation-and-market-rents). Replaces 0.03. |
| `income.income_growth_rate` | 0.01 real | FP Canada 2026 PAG §5 "YMPE, MPE growth rate or salary" | 3.1% (inflation + 1%) | 3.1 − 2.1 = 1.0% real; population-level figure, individual career growth is a user input. Replaces 0.03. |
| `income.affordability_threshold` | 0.32 | CMHC, [*Calculating GDS / TDS*](https://www.cmhc-schl.gc.ca/professionals/project-funding-and-mortgage-financing/mortgage-loan-insurance/calculating-gds-tds); Ratehub, [*Debt Service Ratios*](https://www.ratehub.ca/debt-service-ratios) | CMHC: "restricts debt service ratios to 39% (GDS) and 44% (TDS)". Ratehub: industry standard 32% GDS / 40% TDS | 32% is the industry guideline (NOT on the CMHC page — corrected 2026-09-01); chosen below CMHC's 39% because hde's numerator is broader than lender PITH. Band 0.32–0.44. Replaces 0.35. |
| `condo.house.selling_cost_rate` | 0.05 | WOWA, [*Cost of Selling a House in Canada 2026*](https://wowa.ca/calculators/cost-selling-house) | Ontario combined commission 3.5–5%; BC 3–4% on first $100k then 1–2%; seller legal $1,000–$1,600; worked Ontario example 5.9% all-in incl. 13% HST | 5% = commission + notary before sales tax; band 3–8% brackets discount brokerage to taxed full commission. Rationale corrected 2026-09-01 to state the 5.9% example. |
| `price_shock.severity_mean` | 0.25 | TREB average-price series 1989–96 via [Better Dwelling](https://betterdwelling.com/city/toronto/it-took-22-years-for-prices-to-recover-from-the-last-toronto-real-estate-crash) | peak $273,698 (1989) → trough $198,150 (1996): −27.6% nominal, ≈ −39.4% in 2017 dollars | Mean set just under the observed nominal peak-trough of Canada's largest metro correction; channel is default-off (`annual_hazard=0`). Replaces 0.20. Secondary source; TRREB historical stats are the underlying series. |
| `price_shock.severity_vol` | 0.10 | none — CALIBRATED TO ANCHOR | n/a | Dispersion around the severity mean; lognormal draw gives ±1σ ≈ 0.225–0.275 (rationale text to be corrected in C.5 — it currently says 0.21–0.30). Not a citation. |
| `condo.fee_escalation_rate` | 0.0 real | FP Canada 2026 PAG §5 shelter 3.1% as the UPPER reference | 3.1% nominal ≈ 1.0% real | Value is a neutrality choice (fees track inflation absent aging-building pressure); the PAG figure is a reference, not an endorsement of 0.0 — echo tag to become `[ref: …]` (C.3). |
| `house.value_growth_rate` | 0.0 real | none — hde neutrality ruling | n/a | No defensible universal long-run real appreciation default; user sets a view or wires a `market_scenario` prior. |
| `condo.value_growth_rate` | 0.0 real | none — hde neutrality ruling | n/a | Same. |
| `economic.inflation_rate` | 0.0 (real mode) | FP Canada 2026 PAG §5 inflation; PAG p.6 realised CPI | 2.1%; "As of December 2025, CPI has averaged 3.9% over the last five years and 2.5% over the last 10 years" | 0.0 is the real-mode inert value; nominal-mode planning figure 2.1%. The PAG's 2.4% is the SHORT-TERM INVESTMENT return, not a short-term inflation assumption (anchor text corrected 2026-09-01); band top 2.5% = the 10-year CPI average. |

**Example-header sources (not engine defaults, cited in `examples/`):**

| Claim | Source | Figure quoted | Correction |
|---|---|---|---|
| Routine maintenance as % of home value | NAHB, *Operating Costs of Owning a Home* (Siniavskaia, Jan 2021; 2019 AHS) — [PDF](https://www.nahb.org/-/media/04F57989FBC74C82BEF51C382C654E54.ashx) Table 2 | Maintenance 0.6% of value (all homes); 0.8% pre-1960 … 0.2% 2010s; narrow AHS definition (minor routine repairs only, excludes major repairs/replacement); total operating costs ≈ 4.9% | Examples said "≈ 0.54%" — corrected to 0.6% (2026-09-01). The "1% rule" remains a budgeting heuristic, uncited. |
| Discount rate 0.03–0.05 | illustrative | — | unchanged |
| Event costs / service lives / vols | illustrative | — | unchanged |

## 4. Discrepancies found by the 2026-09-01 source check

1. `economic.inflation_rate` cited "short-term inflation 2.4%" — the PAG has no such
   figure; 2.4% is the short-term return. Fixed.
2. `rent.investment_return_rate` rationale said the 100%-equity real ceiling is ~5.2%;
   EM 7.5% nominal deflated is ≈ 5.3%. Fixed.
3. `income.affordability_threshold` attributed the 32% guideline to the CMHC page; it is
   the Ratehub/industry figure. Source string fixed, URL retained (CMHC for the caps).
4. `condo.house.selling_cost_rate` rationale omitted that WOWA's own worked example is
   5.9% including HST. Fixed; the 5% value and band stand.
5. Four FP Canada anchors pointed at a third-party summary; all now point at the primary
   PDF (figures identical).
6. Examples quoted NAHB routine maintenance as 0.54% of value; Table 2 says 0.6%. Fixed in
   `examples/`.
7. `price_shock.severity_vol` rationale overstates the ±1σ span (0.21–0.30 vs the
   lognormal draw's 0.225–0.275). Scheduled (plan C.5).

## 5. What this does not claim

- The registry covers the eleven bias-critical defaults, not every numeric literal in the
  engine; `house.annual_maintenance_rate` (silently 0.0) and the verdict-decisiveness
  constants are the known gaps, scheduled in the readiness plan (C.1, B.2).
- `as_of="2026"` means the source edition, not a promise the figure is current after the
  next PAG (April 2027). The time-anchor guard covers the demographic prior only.
