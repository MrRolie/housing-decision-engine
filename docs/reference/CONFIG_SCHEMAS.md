# Configuration Schema Reference

> **⚠ Partly out of date — do not write a config from the YAML sketches below.** They predate the
> rent, income, and mortgage/net-wealth features: a config built exactly to them is REJECTED
> (owned options require `initial_value > 0` and either `all_cash: true` or a mortgage block).
> The living contract is `uv run hde --print-schema`; `examples/*.yaml` are the working templates.
> **Current sections:** "Volatility Parameters", "Defaults Summary" (pinned to the registry by
> `tests/test_docs.py`), and "Validation Rules".

This document describes the YAML configuration format for the `cvh_cost` package.

## Top-Level Structure

```yaml
years: <integer>           # Required: Analysis horizon in years
discount_rate: <float>     # Optional: annual discount rate, your opportunity cost (e.g., 0.05 for 5%), AS QUOTED like every typed rate — deflated by inflation_rate in real mode, used as typed in nominal mode; default = the anchored 3% real, composed with inflation_rate in nominal mode
rates: <string>            # Optional: "as_quoted" (default) — every typed growth, escalation, return and discount rate is the figure as quoted, converted once at load — or "real" — your figures are already real and are read as before

economic:                  # Optional: Economic assumptions
  mode: <string>           # "real" or "nominal" (default: "real")
  inflation_rate: <float>  # The deflator of the quoted rates in real mode and the rate composed onto the real defaults in nominal mode (default: 0.021, the FP Canada planning figure, in real mode under rates: as_quoted; 0.0 otherwise)
  inflation_vol: <float>   # Volatility of annual inflation shock (default: 0.0)

condo:                     # Required: Condo parameters
  monthly_fee: <float>     # Required: Monthly HOA/condo fee
  fee_escalation_rate: <float>  # Optional: Annual fee growth (default: 0.0)
  events: <list>           # Optional: One-time events
  other_recurring_costs: <list>  # Optional: Other annual costs
  reserve_contribution_rate: <float>  # Optional: Fraction of annual fees saved (default: 0.0)
  reserve_initial_balance: <float>    # Optional: Starting reserve balance (default: 0.0)
  reserve_growth_rate: <float>        # Optional: Growth on reserves (default: 0.0)

house:                     # Required: House parameters
  initial_value: <float>   # Required: House value at year 0
  value_growth_rate: <float>    # Optional: Annual value growth (default: 0.0)
  annual_maintenance_rate: <float>  # Optional: Maintenance as % of value (default: 0.0)
  events: <list>           # Optional: One-time events
  other_recurring_costs: <list>  # Optional: Other annual costs
  maintenance_curve: <list>  # Optional: (year, rate) pairs for age/condition curve

simulation:                # Optional: Monte Carlo settings
  num_sims: <integer>      # Number of simulations (default: 10000)
  random_seed: <integer>   # RNG seed (default: 42)
  house_maintenance_vol: <float>  # Maintenance volatility (default: 0.0)
  condo_fee_vol: <float>   # Fee volatility (default: 0.0)
  other_cost_vol: <float>  # Volatility for other_recurring_costs (default: 0.0)
  corr_inflation_house: <float>       # Corr(inflation, house maintenance shock)
  corr_inflation_condo: <float>       # Corr(inflation, condo fee shock)
  corr_inflation_other: <float>       # Corr(inflation, other cost shock)
  corr_inflation_event_cost: <float>  # Corr(inflation, event cost shock)
  shock_model: <string>  # "lognormal" (default) or "normal" shock multiplier
```

## Event Configuration

```yaml
events:
  - name: <string>              # Required: Event name
    base_cost: <float>          # Required: Expected cost
    expected_year: <integer>    # Required: Typical year of occurrence
    timing_std_years: <float>   # Optional: Timing uncertainty (default: 0.0)
    min_year: <integer>         # Optional: Earliest possible year (default: 1)
    max_year: <integer>         # Optional: Latest possible year (default: years)
    cost_vol: <float>           # Optional: Cost volatility (default: 0.0)
    timing_model: <string>      # "jitter" (default) or "hazard"
    hazard_base: <float>        # Base hazard (probability) from hazard_start_year
    hazard_growth: <float>      # Increment added to hazard each year after hazard_start_year
    hazard_start_year: <integer>  # Year when hazard begins (default: 1)
    cost_distribution: <string> # "lognormal" (default) or "normal"
```

## Recurring Other Cost Configuration

```yaml
other_recurring_costs:
  - name: <string>              # Required: Cost name
    annual_amount: <float>      # Required: Annual amount
    escalation_rate: <float>    # Optional: Annual growth (default: 0.0)
```

A line's source is declared by its name in the top-level `sources:` block —
`house.other_recurring_costs.<name>.annual_amount: user | assistant |
anchor:<name>` (also `.escalation_rate`); an anchor declaration must equal the
published figure (a dollar tax line is compared as amount ÷ `initial_value`).
The bare `house.other_recurring_costs` key stays `user` | `assistant`. Name
lines for what they are: a Québec option with a property-tax line and no line
named for the school tax gets a coherence warning naming `school_tax.qc`.

## Example: Simple Configuration

```yaml
# Simple 20-year comparison
years: 20
discount_rate: 0.03

condo:
  monthly_fee: 400
  fee_escalation_rate: 0.02

house:
  initial_value: 400000
  annual_maintenance_rate: 0.015
  events:
    - name: "roof"
      base_cost: 12000
      expected_year: 15

simulation:
  num_sims: 10000
  random_seed: 42
```

## Example: Advanced Configuration

```yaml
# Comprehensive 25-year analysis
years: 25
discount_rate: 0.035

economic:
  mode: real
  inflation_rate: 0.025

condo:
  monthly_fee: 550
  fee_escalation_rate: 0.03
  events:
    - name: "special_assessment_exterior"
      base_cost: 8000
      expected_year: 10
      timing_std_years: 2
      min_year: 5
      max_year: 15
      cost_vol: 0.30
    - name: "special_assessment_amenities"
      base_cost: 5000
      expected_year: 18
      timing_std_years: 2
      cost_vol: 0.25
  other_recurring_costs:
    - name: "unit_insurance"
      annual_amount: 600
      escalation_rate: 0.02
    - name: "parking_fee"
      annual_amount: 1200
      escalation_rate: 0.01

house:
  initial_value: 500000
  value_growth_rate: 0.02
  annual_maintenance_rate: 0.015
  events:
    - name: "roof_replacement"
      base_cost: 15000
      expected_year: 20
      timing_std_years: 3
      min_year: 15
      max_year: 25
      cost_vol: 0.25
    - name: "hvac_replacement"
      base_cost: 8000
      expected_year: 15
      timing_std_years: 2
      cost_vol: 0.20
    - name: "water_heater"
      base_cost: 2000
      expected_year: 12
      timing_std_years: 2
      cost_vol: 0.15
  other_recurring_costs:
    - name: "home_insurance"
      annual_amount: 1800
      escalation_rate: 0.03
    - name: "landscaping"
      annual_amount: 2400
      escalation_rate: 0.02

simulation:
  num_sims: 20000
  random_seed: 12345
  house_maintenance_vol: 0.25
  condo_fee_vol: 0.08
```

## Field Reference

### Rates and Percentages

All rates are expressed as decimals:

- 3% = 0.03
- 1.5% = 0.015
- 25% = 0.25

### Volatility Parameters

Volatility is the dispersion of a multiplicative shock around the base cost.
The default shock model is **lognormal** (see `_shock_multiplier` in
`src/hde/monte_carlo.py`):

- Default (`shock_model: "lognormal"`): `cost_actual = cost_base * exp(volatility * z − volatility²/2)` with `z ~ Normal(0, 1)`; the `− volatility²/2` term centers the multiplier at 1.0, so expected cost equals base cost
- Legacy (`shock_model: "normal"`): `cost_actual = cost_base * max(0, 1 + volatility * z)`
- A volatility of 0.25 means costs typically vary on the order of ±25% from baseline

### Timing Parameters

- `expected_year`: The "typical" year when an event occurs (used in deterministic mode)
- `timing_std_years`: Standard deviation for Monte Carlo timing jitter
- `min_year`, `max_year`: Hard bounds for event timing

### Defaults Summary

| Field | Default | Source |
|-------|---------|--------|
| `economic.mode` | "real" | — |
| `economic.inflation_rate` | 0.0 | ref: FP Canada 2026 PAG |
| `economic.inflation_vol` | 0.0 | — |
| `condo.fee_escalation_rate` | 0.0 | ref: FP Canada 2026 PAG |
| `condo.value_growth_rate` | 0.0 | neutral, uncited |
| `condo.reserve_contribution_rate` | 0.0 | — |
| `condo.reserve_initial_balance` | 0.0 | — |
| `condo.reserve_growth_rate` | 0.0 | — |
| `condo.selling_cost_rate` | 0.05 | WOWA 2026 |
| `house.value_growth_rate` | 0.0 | neutral, uncited |
| `house.annual_maintenance_rate` | 0.0 | neutral, uncited |
| `house.maintenance_curve` | [] | — |
| `house.selling_cost_rate` | 0.05 | WOWA 2026 |
| `rent.rent_escalation_rate` | 0.01 | FP Canada 2026 PAG |
| `rent.invested_down_payment` | 0.0 | like-for-like: set explicitly |
| `simulation.discount_rate` | 0.03 | FP Canada 2026 PAG (60/40 real) |
| `condo.purchase_costs` | 0.0 | — |
| `house.purchase_costs` | 0.0 | — |
| `rent.investment_return_rate` | 0.03 | FP Canada 2026 PAG |
| `income.income_growth_rate` | 0.01 | FP Canada 2026 PAG |
| `income.affordability_threshold` | 0.32 | CMHC GDS/TDS |
| `price_shock.severity_mean` | 0.25 | TREB 1989–96 |
| `price_shock.severity_vol` | 0.10 | TREB 1989–96 (calibrated) |
| `event.timing_std_years` | 0.0 | — |
| `event.min_year` | 1 | — |
| `event.max_year` | years | — |
| `event.cost_vol` | 0.0 | — |
| `event.timing_model` | "jitter" | — |
| `event.hazard_base` | 0.0 | — |
| `event.hazard_growth` | 0.0 | — |
| `event.hazard_start_year` | 1 | — |
| `event.cost_distribution` | "lognormal" | — |
| `other.escalation_rate` | 0.0 | — |
| `simulation.num_sims` | 10000 | — |
| `simulation.random_seed` | 42 | — |
| `simulation.house_maintenance_vol` | 0.0 | — |
| `simulation.condo_fee_vol` | 0.0 | — |
| `simulation.other_cost_vol` | 0.0 | — |
| `simulation.rent_escalation_vol` | 0.0 | — |
| `simulation.investment_return_vol` | 0.0 | — |
| `simulation.corr_inflation_house` | 0.0 | — |
| `simulation.corr_inflation_condo` | 0.0 | — |
| `simulation.corr_inflation_other` | 0.0 | — |
| `simulation.corr_inflation_event_cost` | 0.0 | — |
| `simulation.shock_model` | "lognormal" | — |

**Rates as quoted (2026-09-05).** Every rate you TYPE — `discount_rate`, `value_growth_rate`, `fee_escalation_rate`, `reserve_growth_rate`, `rent_escalation_rate`, `investment_return_rate`, `income_growth_rate`, every `other_recurring_costs[].escalation_rate` — is the figure as you see it quoted, and the engine converts it once at load: deflated by `inflation_rate` in real mode (`(1 + r)/(1 + π) − 1`), used as typed in nominal mode. The read-back's `rates:` line shows each converted rate in both forms (`rent.rent_escalation_rate 3.0% as quoted = 0.9% after 2.1% inflation`). The defaults in the table above are REAL and untouched: in `mode: nominal` the engine composes `inflation_rate` onto them (`(1 + real)(1 + π) − 1`) and the echo names both figures — `discount_rate 3.0% real default → 5.2% nominal (incl. 2.1% inflation)`. A config that states real figures says `rates: real` at the top level and is read as before. `economic.inflation_rate`'s table row is the registry's inert zero; under the default convention an omitted `inflation_rate` in real mode is the FP Canada 2.1% planning figure (`economic.inflation_rate.nominal_planning`), because it is the deflator there — the run echoes it under `defaults applied`. A quoted `mortgage_rate` is a contract rate and is used as typed in both modes.

Every row with a Source is a registered anchor in `src/hde/anchors.py` (value, as_of,
source, url, rationale, band, retrieved_on, kind); `uv run hde --print-anchors` prints
them. `ref:` marks a source that informs the value without stating it; `neutral,
uncited` is a deliberate zero the engine will not invent a value for (the assumptions
echo warns when `house.annual_maintenance_rate` is omitted). Rows marked "—" are
structural or presentation defaults with no evidentiary content. This table is pinned
to the registry by `tests/test_docs.py`.

### Mortgage-insurance premium schedule

Not a per-field default but a table, so it sits outside the summary above; the
bands are registry entries all the same (`mortgage_insurance.*` in
`--print-anchors`), and `mortgage_insurance.anchored_schedule` builds the
schedule from them. CMHC, "Mortgage Loan Insurance: Premium Information for
Homeowner and Small Rental Loans", retrieved 2026-09-03; Sagen publishes the
identical bands and rates.

| Loan-to-value | Premium on the loan |
|---|---|
| up to and including 65% | 0.60% |
| 65.01% to 75% | 1.70% |
| 75.01% to 80% | 2.40% |
| 80.01% to 85% | 2.80% |
| 85.01% to 90% | 3.10% |
| 90.01% to 95% | 4.00% |

Maximum loan-to-value 95% (refused above it, quoting both figures). An
amortization beyond 25 years adds a 0.20% surcharge. A purchase at or under 80%
is conventional and pays nothing, whatever the sub-80% rows say — those belong
to CMHC's other products. The 4.50% non-traditional-down-payment row is recorded
in the anchor's source text but has no config key.

Tax on the premium, paid in CASH at closing (CMHC: it "can't be added to the
loan amount"): Québec 9% (Revenu Québec; rising to 9.975% for premiums paid
after 2026-12-31 under Bill 99 — re-read the anchor for a 2027 closing),
Ontario 8% (Ontario RST), `other` 0%. Saskatchewan taxes the premium but its
rate is not anchored: state an explicit schedule rather than be charged 0%.

### Land-transfer tax schedules

Also a table rather than a per-field default, and registered the same way: one
anchor per bracket, whose NAME carries the threshold, so `--print-anchors` alone
shows the whole schedule and `land_transfer_tax.anchored_schedule` builds it
from the registry.

Key: `land_transfer_tax: none` (default) | `auto` | `{brackets: [{up_to, rate}],
first_time_buyer_rebate}`, with `municipality: montreal | toronto` and
`first_time_buyer: true | false` beside it. `auto` needs a `province`, on the
option or at the top level. Omit `up_to` on an explicit schedule's last bracket
for the uncapped top band.

The duty is CASH at closing: it is ADDED to `purchase_costs` /
`purchase_costs_rate` — which go on covering notary, inspection and the rest —
and so netted out of `cash_available` when one is stated. It is derived on every
load, so `--sweep` and `--break-even` re-derive it at each price.

| Jurisdiction | Tranche of the base | Rate |
|---|---|---|
| Québec provincial | up to $62,900 | 0.5% |
| | $62,900.01 to $315,000 | 1.0% |
| | over $315,000 | 1.5% |
| Ville de Montréal | up to $62,900 | 0.5% |
| | $62,900 to $315,000 | 1% |
| | $315,000 to $552,300 | 1.5% |
| | $552,300 to $1,104,700 | 2% |
| | $1,104,700 to $2,136,500 | 2.5% |
| | $2,136,500 to $3,113,000 | 3.5% |
| | from $3,113,000 | 4% |
| Ontario | up to and including $55,000 | 0.5% |
| | $55,000 to $250,000 | 1.0% |
| | $250,000 to $400,000 | 1.5% |
| | over $400,000 | 2.0% |
| | over $2,000,000 (one or two single family residences) | 2.5% |
| Toronto MLTT | up to and including $55,000 | 0.5% |
| | $55,000.01 to $250,000 | 1.0% |
| | $250,000.01 to $400,000 | 1.5% |
| | $400,000.01 to $2,000,000 | 2.0% |
| | $2,000,000.01 to $3,000,000 | 2.5% |
| | over $3,000,000 to $4,000,000 | 4.40% |
| | over $4,000,000 to $5,000,000 | 5.45% |
| | over $5,000,000 to $10,000,000 | 6.50% |
| | over $10,000,000 to $20,000,000 | 7.55% |
| | over $20,000,000 | 8.60% |

Sources, all retrieved 2026-09-04: Gouvernement du Québec, « Droits sur les
mutations immobilières » (2026 thresholds, indexed annually to Québec CPI —
re-read for a 2027 closing); Ville de Montréal, « Comment sont calculés les
droits sur les mutations immobilières » (2026 table); Ontario Ministry of
Finance, "Calculating land transfer tax"; City of Toronto, "MLTT Rates & Fees"
(luxury tiers as of April 1, 2026). The anchor `source` strings carry each
table exactly as its page prints it.

Two structures, and they are not interchangeable. **Montréal REPLACES** the
Québec provincial table — the province lets Montréal set its own rates above
$500,000 with no 3% ceiling, and montreal.ca's own worked example balances only
against the single table. **Toronto ADDS** to Ontario's: the MLTT "has been
applied to purchases on all properties in the City of Toronto in addition to the
Provincial Land Transfer Tax as of February 1, 2008", so a Toronto purchase pays
both, and both rebates.

First-time buyers: Ontario refunds up to **$4,000**, Toronto up to **$4,475**,
each capped at its own leg's tax so a rebate never becomes a payment to the
buyer. Neither Québec schedule has an anchored first-time-buyer rebate of the
duty — both carry a `source: none` entry naming what was tried, and the
read-back says so rather than implying a zero was computed. `first_time_buyer`
is the USER's assertion of eligibility: the engine applies the published
maximum and cannot check age, occupancy or prior ownership.

The base the engine applies is the **PRICE**. In Québec the duty is really
levied on the greater of the price paid, the price stated in the deed, and the
municipal assessment × the year's comparative factor; a purchase well under
assessment is therefore under-taxed by this model. A municipality other than
Montréal that legislated its own band above $500,000 (the province permits up
to 3%) is NOT in the registry — state an explicit schedule for it.

### Income-tax, FHSA, HBP and TFSA reference figures

Reference entries, not defaults: the engine applies **none** of these until a
config opts into a tax block, and there is no tax key today. They are
registered so an answer that touches tax cites the published figure instead
of an estimate, and so the block, when it lands, reads the schedule the
registry already holds (`tax_rates.marginal_rate`). One anchor per bracket —
`tax.<jur>.bracket_<k>_ceiling` (the upper edge, inclusive) and `_rate`; the
top bracket has no ceiling anchor. All fetched 2026-09-05; every threshold is
a 2026 figure and must be re-fetched for 2027.

| Jurisdiction | Taxable income (2026) | Rate |
|---|---|---|
| Federal (CRA) | $0 to $58,523 | 14% |
| | $58,523.01 to $117,045 | 20.5% |
| | $117,045.01 to $181,440 | 26% |
| | $181,440.01 to $258,482 | 29% |
| | $258,482.01 and up | 33% |
| Québec (Revenu Québec TP-1015.F-V 2026) | not more than $54,345 | 14% |
| | more than $54,345, not more than $108,680 | 19% |
| | more than $108,680, not more than $132,245 | 24% |
| | more than $132,245 | 25.75% |
| Ontario (CRA) | $0 to $53,891 | 5.05% |
| | $53,891.01 to $107,785 | 9.15% |
| | $107,785.01 to $150,000 | 11.16% |
| | $150,000.01 to $220,000 | 12.16% |
| | $220,000.01 and up | 13.16% |

| Figure | 2026 value | Source |
|---|---|---|
| Federal basic personal amount (`tax.federal.basic_personal_amount`) | $16,452, phasing down to $14,829 between $181,440 and $258,482 of net income | CRA 2026 indexation |
| Québec basic personal amount (`tax.qc.basic_personal_amount`) | $18,952 | Revenu Québec 2026 rates |
| Ontario basic personal amount (`tax.on.basic_personal_amount`) | $12,989 | CRA T4032-ON 2026 |
| Québec abatement (`tax.federal.quebec_abatement`) | 16.5% of basic federal tax | Finance Canada Quebec abatement |
| Ontario surtax (`tax.on.surtax_1_threshold` / `_rate`, `surtax_2_…`) | 20% of basic Ontario tax over $5,818, plus 36% over $7,446 | CRA T4032-ON 2026 |
| Capital-gains inclusion rate (`tax.capital_gains_inclusion_rate`) | ½ — the proposed two-thirds was cancelled 2025-03-21 | ITA s. 38(a) |
| Principal-residence exemption (`tax.principal_residence_exempt_fraction`) | 1.0 of the gain on a home that was the principal residence every year owned | CRA principal residence |
| FHSA (`fhsa.annual_limit`, `fhsa.lifetime_limit`, `fhsa.carry_forward_max`, `fhsa.max_years_open`) | $8,000 a year; $40,000 lifetime; at most $8,000 carried forward; open at most 15 years | CRA FHSA |
| HBP (`hbp.withdrawal_limit`, `hbp.repayment_years`, `hbp.repayment_grace_years`) | $60,000; 15 years; first repayment year − withdrawal year = 5 for a first withdrawal in 2026–2028 (2026 → 2031), 2 under the standard rule | CRA HBP |
| TFSA (`tfsa.annual_limit`, `tfsa.cumulative_room_since_2009`) | $7,000; $109,000 through 2026 for someone eligible every year since 2009 — the sum of the quoted table, no page prints the total | CRA TFSA |

The marginal rate `tax_rates.marginal_rate(taxable_income, province)` reports
is the statutory bracket rate: in Québec the federal component is × (1 − 0.165);
in Ontario the provincial component is × 1.20 inside the first surtax tier and
× 1.56 above the second, with basic Ontario tax netting the basic personal
credit and no other. At $100,000: Québec 36.1% (20.5% × 0.835 + 19%), Ontario
31.5% (20.5% + 9.15% × 1.2). Revenu Québec's web pages refused automated
retrieval; the Québec figures are read from its TP-1015.F-V (2026-01) PDF and
corroborated by the Finances Québec 2026 parameters document.

## Validation Rules

The config loader validates:

1. `years >= 1`
2. `discount_rate > -1` (a quoted rate below inflation deflates to a small negative real rate, which a coherence warning names), with a coherence warning outside `[-0.15, 0.15]` (a decimal/percent typo tripwire; the examples' real figures sit in 0.03–0.05)
3. `num_sims >= 1`
4. `condo.monthly_fee >= 0`
5. `house.initial_value >= 0`
6. `house.annual_maintenance_rate` in [0, 1]
7. Each event has `name`, `base_cost`, `expected_year`
8. Each event `expected_year >= 1`
9. Each event `base_cost >= 0`
10. `province` and `municipality` are strings — quote the code (`province:
    "ON"`). An unquoted `ON`, `NO`, `YES` or `OFF` is a YAML boolean and is
    refused with that hint: `province: True is not a province code — YAML reads
    an unquoted ON as a boolean; quote it: province: "ON"`
11. A `sources:` entry names a key the config sets — an `other_recurring_costs`
    line by its name (`<option>.other_recurring_costs.<name>.annual_amount`);
    an unknown line name is refused naming the lines that exist, and a name two
    lines share cannot be declared

Validation failures raise `ConfigValidationError` with descriptive messages.
