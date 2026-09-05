# Examples — an ordered walkthrough

## 0. Start here: the smallest config that runs

```yaml
years: 15
discount_rate: 0.03
condo:
  initial_value: 480000
  monthly_fee: 400
  all_cash: true
rent:
  monthly_rent: 2400
  invested_down_payment: 480000   # like-for-like: the renter invests what the buyer paid
```

Every other key is optional; each one you omit shows up in the run's `defaults applied:`
line with its source (`uv run hde --print-anchors` for the full record). `uv run hde
--print-schema` is the living contract — `required` flags, `required_if` for the
capital-structure rule, and a note per key.

Six walkthrough scenarios follow, in reading order, plus `advanced_config.yaml` — the
every-knob, nominal-mode reference. Each is a complete run: `uv run hde examples/<file>.yaml`.
Add `--story DIR` to any of them to get the story plots plus a STORY.md one-pager in `DIR`.
Acts render by what the config supports: acts 1 and 2 always; act 4 ("Your home's possible
futures") with an owned option; act 3 ("The uncertainty") only when at least one uncertainty
input is on (a single-path run skips it); act 5 ("Why") only with a `market_scenario:` prior;
act 6 ("The market line", the break-even rent) only with `rent` plus an owned option.

## 1. `basic_config.yaml` — condo vs house

**Question:** all-cash condo vs all-cash house over 20 years — which costs less, and how sensitive is that to maintenance shocks and fee escalation?

```bash
uv run hde examples/basic_config.yaml
```

Acts 1–4 render here (no rent option, no prior). The six acts:
1. **The answer** — total PV per option, cheapest highlighted, the margin vs the runner-up in words, or "too close to call" under the decisiveness rule.
2. **The race** — cumulative out-of-pocket cost per year; where the lead changes hands; the end-of-horizon equity credit as a dotted drop.
3. **The uncertainty** — Monte Carlo cost distributions with p10/median/p90 and the probability each option is cheapest.
4. **Your home's possible futures** — home value under your growth assumption (a single honest line here; a demographic fan chart when a prior is loaded).
5. **Why** — the demographic demand signal behind the prior (only rendered when `market_scenario:` is set).
6. **The market line** — break-even rent vs the cheapest owned option, and where your rent sits against it (only with `rent` plus an owned option).

## 2. `rent_vs_condo_vs_house.yaml` — the full 3-way race

**Question:** with the condo's purchase capital invested instead (like-for-like opportunity cost), does renting beat both purchase options?

```bash
uv run hde examples/rent_vs_condo_vs_house.yaml
```

Acts 1–4 and 6, now three runners in the race. Watch act 2: the renter's invested capital is charged at year 0 exactly like the buyer's down payment, so each runner starts with its own capital outlay and they separate on carrying costs; the crossover year — if any — is the whole decision.

## 3. `income_shock.yaml` — affordability under a pay cut

**Question:** after a 20% pay cut in year 3, which option keeps housing cost inside the affordability threshold?

```bash
uv run hde examples/income_shock.yaml
```

The run prints per-year housing-cost/income ratios (`affordability` in the report); the story acts show the cost race the ratios are measured against.

## 4. `showcase_demographic_prior.yaml` — the full stack (all six acts)

**Question:** what happens to the rent-vs-buy verdict when a real demographic demand prior — ISQ population scenarios on a 2021 Census base → demoflow's audited demand model — tilts price growth and crash risk?

```bash
uv run hde examples/showcase_demographic_prior.yaml --story docs/story
```

This is the repo's living showcase: [docs/story/STORY.md](../docs/story/STORY.md) renders all six acts, including act 4's fan chart (low/reference/high demand scenarios) and act 5's demographic signal itself. Regenerable with the command stamped at the top of the STORY.md.

## 5. `mortgage_house_vs_rent.yaml` — the leveraged path

**Question:** a financed house (20% down, 25-year amortization at the FP Canada nominal borrowing
rate) against renting with that same down payment invested — does leverage change the answer?
This is the reference for any financed purchase: a mortgage is a nominal contract, so the example runs
`economic.mode: nominal` with the 2.1% planning inflation, keeps every growth/escalation/return
input REAL (the engine composes inflation on top), and omits `discount_rate` so the engine's 3%
real default is composed to 5.2% and echoed. A typed `discount_rate` is the household's REAL
opportunity cost and is composed the same way (`advanced_config.yaml` types 3.5% real and runs at
6.1%; the echo names both) — only the quoted `mortgage_rate` is used as entered. Running a mortgage in real mode prices a level
real-rate payment that understates the lender's cash payment — the engine warns when an income
block is present.

```bash
uv run hde examples/mortgage_house_vs_rent.yaml
```

The report's `mortgage_pv` and the outstanding balance netted inside `terminal_equity_pv`
are non-zero here and in the next example. `mortgage_rate` is an EFFECTIVE ANNUAL rate with
annual payments; a posted Canadian rate compounds semi-annually — convert it first (the
schema note and the figure glossary state the formula).

## 6. `first_time_buyer_montreal.yaml` — the financed first home, under 20% down

**Question:** a first-time buyer with $60k saved, renting at $1,850 in Montréal and looking at
a $450k condo with $380 fees — does buying beat renting over 10 years when the down payment
lands under 20%?

This is the template for a financed purchase where the cash pile is known and the split is
not. The cash goes in as `cash_available` and the engine nets the closing costs out of it;
the Montréal welcome tax is priced from the published brackets (`land_transfer_tax: auto` +
`province: "QC"` + `municipality: montreal` — the province code is quoted because an unquoted
`ON` is a YAML boolean); the CMHC premium tier is picked on the loan that remains
(`mortgage_insurance: auto`, the premium added to the loan and the 9% Québec tax on it paid
in cash); `first_time_buyer: true` is recorded and the run says it applied nothing, because
no Québec rebate is anchored — the engine reports that rather than guess a refund. The
listing's tax bill is entered as two lines, municipal and school, because a Québec bill is
both. The `income` block turns on the affordability ratios, and every value the file sets is
declared in `sources:`.

```bash
uv run hde examples/first_time_buyer_montreal.yaml
```

Read the `financing:` line first: the $60,000 less the $4,860 duty, $2,000 of notary and
inspection and the $1,110 tax on the premium leaves a down payment of about $52k (11.6% of
price), an insured mortgage at the 3.10% CMHC tier, and the price up to which that cash
would still cover 20% down. The verdict is "too close to call" — a single-path run, so the
rule is the 5% tie band — and the affordability line shows the condo above the 32%
guideline (under the 39% GDS cap) for the first seven years. The two things the run warns
on are the next step: the 0% real growth default (`--sweep condo.value_growth_rate=0:0.02:3`,
or the `MTL_ISLAND_RA06` prior copied from the showcase) and the 1% real rent escalation for
a continuing Québec lease (`--sweep rent.rent_escalation_rate=0,0.01`).

## Parameter sources

The example configs are de-facto templates — users and agents copy them, so every
assumption-bearing number carries a provenance stamp: either a citation or an explicit
`illustrative` marker. Each YAML opens with a `# --- Parameter provenance ---` block and
carries inline `# <cite>` comments on the lines themselves.

Comments are for the reader; the ENGINE reads the optional `sources:` block, which
`showcase_demographic_prior.yaml`, `rent_vs_condo_vs_house.yaml` and
`first_time_buyer_montreal.yaml` carry. It maps
each key the config sets to `user` (the household's own figure), `assistant` (a
calibration typed on their behalf — every line marked `illustrative`) or
`anchor:<name>` (exactly a registry value, `uv run hde --print-anchors`). The
assumption echo then splits into `user-stated:` / `assistant-typed:` /
`anchor-sourced:` / `unattributed:` lines, and a run whose decisiveness rests on
uncertainty inputs the user never stated says so as a `[warning]`. Copy the block with
the config and re-classify every line for your own scenario — a config with no block
echoes one line saying the read-back cannot tell the two apart.

**Convention:** values marked `illustrative` are calibration choices, not evidence —
sensitivity-test them (edit the value and re-run; act 6 sweeps rent and purchase price for you).

| Assumption category | Source | Where used |
|---|---|---|
| Inflation (nominal mode) | FP Canada Standards Council, 2026 Projection Assumption Guidelines (fpcanada.ca): 2.1% long-term inflation | `advanced_config.yaml` `economic.inflation_rate` |
| Shelter-cost / fee / recurring-cost escalation | FP Canada 2026: shelter cost growth 3.1% nominal ⇒ ~1.0% real planning reference | `fee_escalation_rate`, `other_recurring_costs.escalation_rate` in all examples; engine default `rent.rent_escalation_rate` 0.01 real (`src/hde/anchors.py`) |
| Rent escalation | FP Canada 2026 shelter ≈ 1.0% real + NBER digest Oct 2025 (continuing-tenant pass-through ~21%; QC TAL guideline ≈ CPI for existing leases ⇒ ≈ 0.0% real) | `rent_escalation_rate` in `rent_vs_condo_vs_house.yaml`, `income_shock.yaml`, `showcase_demographic_prior.yaml` |
| Investment return (invested down payment / reserves) | FP Canada 2026: balanced 60/40 ≈ 3.0% real; U.S. equities 6.4% nominal ≈ 4.2% real, ceiling EM 7.5% nominal ≈ 5.3% real | `investment_return_rate` 0.03 in `rent_vs_condo_vs_house.yaml` / `income_shock.yaml`, 0.05 (equity-tilted) in `showcase_demographic_prior.yaml`; engine default 0.03 real (`src/hde/anchors.py`) |
| Salary / income growth | FP Canada 2026: 3.1% nominal ⇒ ~1.0% real planning reference | `income_shock.yaml` `income.income_growth_rate` |
| Affordability threshold | CMHC "Calculating GDS/TDS" (cmhc-schl.gc.ca): GDS cap 39%, TDS 44%; legacy guideline 32% | `income_shock.yaml` `affordability_threshold` (0.35); engine default 0.32 (`src/hde/anchors.py`) |
| Selling costs | WOWA.ca "Cost of Selling a House in Canada 2026" (wowa.ca): seller commissions ≈ 4–5% + notary/discharge ⇒ ~5% all-in | engine default `selling_cost_rate` 0.05 (`src/hde/anchors.py`) |
| Maintenance rates | NAHB "Operating Costs of Owning a Home" (Siniavskaia, Jan 2021; 2019 AHS) Table 2: routine maintenance ≈ 0.6% of value/yr for all homes (0.8% pre-1960 → 0.2% 2010s; narrow definition excluding major repairs); "1% rule" budgeting heuristic (uncited) | `annual_maintenance_rate`, `maintenance_curve` in all owned-option examples |
| Crash severity | TREB 1989–96 via Better Dwelling: −27.6% nominal peak-trough (≈ −39% real) — Canada's largest observed metro correction | `price_shock.severity_mean` (≈ 0.25 anchor) in `showcase_demographic_prior.yaml`; engine default `severity_mean` 0.25 (`src/hde/anchors.py`) |
| Demographic price drift | demoflow ScenarioPrior: ISQ population scenarios (2021 Census base) → cohort roll-forward → excess demand → β-mapped real price drift; every source pinned by sha256 and cited in the run's `assumptions.demographic_prior` (`src/hde/anchors.py` `SOURCE_KEY_CITATIONS`) | `market_scenario` in `showcase_demographic_prior.yaml` |
| Discount rate (0.03–0.05 real) | DEFAULT 0.03 real = the anchored investment return (FP Canada 2026 PAG 60/40), the household's opportunity cost; the examples state their own view; typed or defaulted it is REAL and composed with inflation in nominal mode like every other rate (`advanced_config.yaml`: 3.5% real → 6.1%); sanity band [0.02, 0.06]; the engine warns outside [0, 0.15] (units tripwire) | `discount_rate` in all examples |
| Property tax, insurance (`other_recurring_costs`) | the listing's tax bill and an insurance quote — the engine applies no default for either. Registry checks (`uv run hde --print-anchors`): `property_tax.laval` / `.montreal` / `.quebec_city` / `.toronto` are rates on ASSESSED value, not market value; `school_tax.qc` is the separate Québec school levy a Québec bill also carries; `home_insurance.qc` / `.on` are household-average floors, not premiums. The read-back cites a match by name and says "no anchor match" otherwise; Gatineau and Ottawa have no registered source | every owned option; `first_time_buyer_montreal.yaml` enters the municipal and school lines separately |
| Purchase costs (`purchase_costs`, `land_transfer_tax`) | the welcome / land-transfer tax is priced by the ENGINE from the anchored bracket schedules — Québec and Ontario provincial, Montréal (which replaces Québec's table) and Toronto (which adds to Ontario's), first-time-buyer rebates where one is sourced — with `land_transfer_tax: auto` + a quoted `province: "QC"` / `"ON"` (+ `municipality`), re-derived at every `--sweep` / `--break-even` price; notary and inspection are the household's own quotes in `purchase_costs`. A mortgage-insurance premium is priced by `mortgage_insurance: auto` (the anchored CMHC schedule, the provincial tax on the premium in cash); `financed_purchase_costs` only carries a premium the lender quoted | `first_time_buyer_montreal.yaml`; `mortgage_house_vs_rent.yaml` types a hand-figured `purchase_costs` because it sets no province |
| Mortgage / financing | FP Canada 2026 borrowing rate 4.4% nominal, run in nominal mode as entered; a lender's quote is the household's own figure (`first_time_buyer_montreal.yaml`); with no quote the registry's Bank of Canada contracted 5-year rates (`mortgage_rate.contracted_5y_uninsured` / `mortgage_rate.contracted_5y_insured`) are the base and the posted 5-year rate (`mortgage_rate.posted_5y`) the ceiling; engine convention: level ANNUAL payment at an EFFECTIVE ANNUAL rate (posted Canadian rates compound semi-annually — convert) | `mortgage_house_vs_rent.yaml`, `first_time_buyer_montreal.yaml` |
| `value_growth_rate` | illustrative market view — no defensible universal long-run real appreciation default | all owned-option examples; see `showcase_demographic_prior.yaml` for the demographic alternative |
| Event costs, service lives, timings (roof, HVAC, water heater, appliances, paint, driveway, special assessments) | illustrative — calibrate to your reserve study or component inventory | `events:` blocks in all examples |
| Vols, correlations, hazard rates (`cost_vol`, `*_vol`, `corr_*`, `hazard_*`) | illustrative uncertainty calibration — sensitivity-test via sweep | `events:` and `simulation:` blocks in all examples |

Engine defaults cited above live in `src/hde/anchors.py`; per-file details are in each
YAML's provenance header.
