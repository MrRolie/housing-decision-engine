# Architecture and figure glossary

Rewritten 2026-09-01 (readiness plan D). The first half is the module map; the
second half — **Figure glossary** — defines every number the engine prints or
emits, as the code computes it, so "what is this figure and how was it
calculated?" is answerable from `--json` plus this page without opening `src/`.
The glossary is pinned by `tests/test_docs.py`: a breakdown key or a serializer
key without a row here fails the suite.

## Module map

```text
src/hde/
├── __init__.py         # Library surface (what the CLI uses)
├── anchors.py          # Provenance registry: every engine default + source/url/band/kind;
│                       #   SOURCE_KEY_CITATIONS for the demographic prior's inputs
├── models.py           # Parameter + result dataclasses; Verdict + compute_verdict
├── pv.py               # Pure PV helpers (annuities, mortgage math, monthly equivalent)
├── deterministic.py    # Deterministic PV engine (compute_deterministic)
├── monte_carlo.py      # Monte Carlo engine (run_monte_carlo)
├── market_scenario.py  # ScenarioPrior loader/validation, drift banding, time-anchor guard
├── mortgage_insurance.py # Insured-mortgage premium: schedule, tier, financed premium, cash tax
├── land_transfer_tax.py # Welcome / land-transfer tax: bracket schedules, rebate, cash at closing
├── config.py           # YAML → ComparisonSpec; coherence + time-anchor warnings
├── sources.py          # Source classes: who stated each value (`sources:` block, the
│                       #   echo lines, the unstated-uncertainty warning's input set)
├── input_schema.py     # The input contract as data (--print-schema)
├── serialization.py    # THE typed core for agent output (--json)
├── reporting.py        # Text report (+ legacy matplotlib figures)
├── story_plots.py      # The six-act decision story (figures + sentences)
├── story_page.py       # STORY.md + report.txt package (--story)
└── cli.py              # `hde` entry point
```

Data flow: `load_config` → `ComparisonSpec` → `compute_deterministic` and
`run_monte_carlo` → `compute_verdict` → one of `format_text_report`,
`render_story_package`, or the serializers (`det_to_dict`, `mc_to_dict`,
`verdict_to_dict`, `assumptions_to_dict`). Every surface reads the same
verdict and the same assumption echo; none re-derives a figure.

Provenance chain: `anchors.py` is the single source of truth for every
bias-critical default (dataclass default == parser default == anchor, pinned
generatively in `tests/test_anchors.py`), for the mortgage-insurance premium
schedule — each CMHC band, the 95% maximum, the 0.20% amortization surcharge and
the Québec/Ontario taxes on the premium are registered entries, and
`mortgage_insurance.anchored_schedule` builds the schedule from them, so a rate
has exactly one home and `--print-anchors` shows the table the engine applies —
and for the land-transfer-tax schedules, where every bracket is an entry whose
NAME carries the threshold (`land_transfer_tax.montreal.to_552300` = 1.5%) so the
registry dump alone shows the whole table; `market_scenario.py` guards the
demographic prior (schema, closed enums, `constants_as_of` within a year of
`START_CALENDAR_YEAR = 2026`) and renders its provenance only from the file.

### Anchors: two kinds of entry

The registry holds **engine defaults** and, since 2026-09-03, **reference
tables** — jurisdiction tax and insurance figures, and since 2026-09-04 the
posted mortgage rate. They are opposite in how they reach a run.

| | engine default | jurisdiction reference |
|---|---|---|
| keys | `rent.investment_return_rate`, `condo.house.selling_cost_rate`, … | `property_tax.<municipality>`, `school_tax.<province>`, `home_insurance.<province>`, `mortgage_rate.posted_5y` |
| applied by the engine? | yes, when the YAML omits the key | **never** — the user supplies the figure |
| cited when? | in `defaults applied:`, because the engine supplied it | in `<option> other costs:`, when the user's own figure **equals** a published one; in `anchor-sourced:`, when a `sources:` line declares it |
| extra fields | — | `quoted` (the figure as printed by the source), `unit` (the base it is stated on), `province` (property/school tax), `restatements` (the same figure in another convention) |

Property tax and home insurance were the two largest unsourced numbers in a
typical run — together roughly 15% of an owned option's year-1 cash. They stay
the user's own `other_recurring_costs` dollar figures, per option: the engine
adds a published figure to compare against, not a default to apply, and it is
deliberately **not** wired to `market_scenario.geography` — a demographic prior
says where the population is going, not what a municipality levies.

Three rules hold across the reference tables, enforced at import time by
`Anchor.__post_init__` and pinned in `tests/test_reference_anchors.py`:

1. **Assessed is not market.** Every municipal rate is levied on the assessment
   roll. Québec publishes the gap as the *proportion médiane*; Ontario's is
   dated — MPAC assesses the 2026 tax year on January 1, 2016 values, so an
   Ontario rate applied to a 2026 purchase price is a **ceiling**, not an
   estimate. `unit` says so on every entry and the read-back reprints it beside
   every citation it makes.
2. **Ad valorem only.** Flat per-dwelling charges (Laval's $486 water service,
   Québec City's $386 + $195 tariffs) are real money and are *not* in the rate.
3. **The band is published, not imagined** — narrowest to broadest reading of
   the same source (municipal-only to full ad-valorem bill), zero-width where
   the source publishes one figure.

`kind: "unsourced"` is a first-class state, not an omission: `value` is `None`,
`url` records what was tried, and it prints as `source: none`. Gatineau and
Ottawa hold it today — Gatineau because it taxes by neighbourhood unit, so no
single city-wide rate exists to cite; Ottawa because the rate by-law was not
reachable. An unsourced entry can never match a user's figure, so a run in
either city gets silence rather than a borrowed number.

**`mortgage_rate.posted_5y`** (2026-09-04) is the same idea for financing: the
Bank of Canada's weekly posted 5-year conventional rate (Valet series
V80691335), so a user with no lender quote has something to bracket a guess
against instead of an unanchored number. It is a POSTED rate — a list price. The
series makes the point itself: every one of the 52 weekly observations to
2026-09-02 reads 6.09, last changed 2025-05-14, hence the zero-width band, which
is the finding and not a gap. What borrowers actually contracted is in the
anchor's rationale, from the same API and equally cited, so the posted figure
brackets a guess from ABOVE and is never mistaken for a quote. It is quoted
semi-annually compounded while `mortgage_rate` takes an effective annual rate;
the conversion is a `restatement` on the entry, so a config stating either form
may cite it.

`serialization.reference_matches` does the matching: owned options only (a
renter's tenant policy and a mortgage-insurance line are different products and
never borrow a homeowner citation), a property-tax line compared as
`annual_amount / initial_value`, an insurance line as the amount itself. The
bar is **equality, not resemblance**: the property-tax window is half a basis
point, wide enough only to absorb rounding the annual amount to the nearest
dollar. A looser window once cited Québec City for a 0.750%-of-price line in a
Montréal scenario — the citation was true and the impression false. A near miss
reads `no anchor match`, which is the useful answer. Every match is reported —
two municipalities may levy the same rate, and choosing one would be a coin
flip presented as a fact.

**Sums of anchors** (2026-09-04). A Québec owner's property-tax bill IS the
municipal rate plus the province-wide school rate, and the two are separate
entries because separate bodies levy them. Three answers set `property_tax_rate`
to that sum — both halves anchored — and the read-back printed `no anchor match`
on a figure built entirely from anchors: the citation degraded exactly where the
care went in. `anchors.match_reference_sum` now recognises it and the line cites
BOTH, with both units and the arithmetic:

```
property tax (0.67% of value) $4,019/yr = 0.670% of price [Ville de Laval 2026
+ Québec taux unique 2026-2027 · 0.5909% + 0.0790% = 0.6699% · rate on ASSESSED
value (0,5909 $ per 100 $ …) — assessed ≠ market · rate on ASSESSED value
(0,07899 $ per 100 $ …, first $25,000 exempt) — assessed ≠ market]
```

Exactly one combination is recognised, and the limits are the point: singles are
tried first (a figure that IS a published rate is never re-explained as
somebody's sum); a sum of two municipal rates is not a bill anyone pays; and the
pairing is within ONE province — Toronto's published total already contains
Ontario's education rate, so adding Québec's school rate to it would invent a
bill. That is what the required `province` field enforces. Both units are
printed rather than a compact joint one, because a unit can carry a caveat its
neighbour does not: Montréal's says *city-wide lines only — the borough adds
more*, and dropping it would understate the bill the citation appears to vouch
for.

## Conventions (every figure below obeys these)

- **Years are 1-indexed; cash flows fall at the END of year t and discount at
  `(1 + dr)^-t`** (`pv_single`). Year-0 outlays (the buyer's down payment and purchase costs, the renter's invested capital) are undiscounted.
  `dr` = `discount_rate`, in the same terms (real or nominal) as every rate.
  An omitted `discount_rate` is the anchored 3% real return, composed with
  `inflation_rate` in nominal mode (`(1 + 0.03)(1 + π) − 1`) and echoed as such.
- **Nominal mode composes inflation into every escalation:** `g_eff = (1 + g)(1 + π) − 1`
  (`_effective_growth_rate`); in real mode `g_eff = g`. Defaults are REAL terms.
- **Two escalation-start conventions coexist by design.** Condo fees, rent and
  "other recurring" costs escalate before year 1: year-t amount = `base × (1 + e_eff)^t`.
  House maintenance and home value do not: year-t value = `V0 × (1 + g_eff)^(t−1)`.
- **Mortgage = level ANNUAL payment at an EFFECTIVE ANNUAL rate**, `M = L·r / (1 − (1 + r)^−T)`
  (`P/T` when `r = 0`), `L = initial_value − down_payment + financed_purchase_costs` (a financed
  mortgage-insurance premium rides in the loan, never in year-0 cash). A Canadian posted rate compounds
  semi-annually with monthly payments — convert first: `r_eff = (1 + r_posted/2)^2 − 1`
  (≈ 1.7% difference on the annual outlay at 5%).
- **The land-transfer tax is derived in the loader** (`land_transfer_tax.py`,
  key `land_transfer_tax: auto | none | {brackets, first_time_buyer_rebate}`,
  with `municipality` and `first_time_buyer`). The duty is CASH at closing, so
  it is added to `purchase_costs` BEFORE the `cash_available` netting — it
  leaves the buyer's pile like the notary's bill, and `purchase_costs` /
  `purchase_costs_rate` go on covering notary, inspection and the rest. Derived
  per load, so `--sweep` and `--break-even` re-derive it at every price (a
  Montréal scan crosses the $552,300 knee from 1.5% to 2%). Montréal's schedule
  REPLACES the Québec provincial one; Toronto's is charged IN ADDITION to
  Ontario's. A first-time-buyer rebate is capped both at its published maximum
  and at its own leg's tax, so it never becomes a payment to the buyer. The base
  is the PRICE: in Québec the duty is levied on the greater of price and
  municipal assessment × the year's comparative factor, and the engine has no
  assessment roll.
- **Mortgage insurance is derived in the loader** (`mortgage_insurance.py`, key
  `mortgage_insurance: auto | none | {bands, premium_tax_rate}`). Above 80%
  loan-to-value the tier is chosen on `L₀ = initial_value − down_payment`, i.e.
  BEFORE the premium: `premium = rate(L₀ / initial_value) · L₀`, added to
  `financed_purchase_costs` so it rides the loan (`L = L₀ + premium`, routinely
  above 95% of price — by design, never a refusal). The provincial tax on the
  premium is CASH at closing (CMHC: it "can't be added to the loan amount"):
  netted out of `cash_available` when stated, else added to `purchase_costs`.
  `mortgage_term_years > 25` adds the 0.20% amortization surcharge. Netting the
  tax out of a cash pile is circular — the tax shrinks the down payment, which
  raises the loan and can raise the tier — so the loader solves
  `L = (price − cash + purchase_costs) / (1 − t·r(L / price))` by iteration; `r`
  is non-decreasing in `L`, so iterating from the zero-tax loan reaches the
  least self-consistent tier. Deriving it in the loader is what makes `--sweep`
  and `--break-even` re-derive the tier at every grid point. A loan-to-value
  above the schedule maximum (95%) is refused with both figures, so a scan
  records the point under `refused` and shrinks its search.
- **Monthly equivalent** annuitizes a PV over `12N` months at `m = (1 + dr)^(1/12) − 1`,
  so it decomposes the same PV the annual figures discount.
- **A cost is positive; a credit is negative.** Every option's `total_pv` is a net
  cost; the cheapest option is the smallest `total_pv`.

## Figure glossary

Sections follow the text report and the `--json` document. Keys in backticks are
the exact breakdown / JSON keys.

### Owned options (condo, house) — `breakdown`

| Key | What it is | As computed |
|---|---|---|
| `fee_pv` (condo) | PV of condo fees | `Σ_{t=1..N} 12·fee·(1 + e_eff)^t · (1 + dr)^-t`, `e_eff` from `fee_escalation_rate` |
| `maintenance_pv` (house) | PV of maintenance | `Σ_t rate(t) · V0 (1 + g_eff)^(t−1) · (1 + dr)^-t`; `rate(t)` = `annual_maintenance_rate`, or the `maintenance_curve` linearly interpolated by year (flat outside its endpoints) |
| `events_pv` | PV of one-time events, GROSS of reserve coverage | each event at its `expected_year` clamped to `[min_year, max_year] ∩ [1, N]`: `base_cost · (1 + dr)^-year` |
| `other_pv` | PV of "other recurring" costs | `Σ_t amount · (1 + e_eff)^t · (1 + dr)^-t` per cost |
| `reserve_pv` (condo) | reserve-fund coverage of events, as a NEGATIVE offset | balance evolves yearly `B ← B(1 + r_res,eff) + 12·fee_t · reserve_contribution_rate`; at an event `covered = min(B, cost)`, `reserve_pv −= covered · (1 + dr)^-year` |
| `purchase_costs_pv` | closing costs paid at purchase (land-transfer tax, notary, inspection, a cash-paid mortgage-insurance premium) | `purchase_costs`, year 0, undiscounted; excluded from the affordability ratio |
| `downpayment_pv` | capital paid at year 0 | `initial_value` when `all_cash`, else `down_payment`; undiscounted |
| `mortgage_pv` | PV of the level annual payments | `M · [1 − (1 + dr)^−n] / dr`, `n = min(N, mortgage_term_years)`; 0 when `all_cash` |
| `terminal_equity_pv` | the end-of-horizon equity credit (NEGATIVE = reduces cost) | `−[V_N (1 − selling_cost_rate) − B_N] · (1 + dr)^-N`, `V_N = V0 (1 + g_eff)^N`, `B_N = L(1 + r)^N − M[(1 + r)^N − 1]/r` (0 once `N ≥ T`) |
| `total_pv` | net cost of the option | sum of that option's breakdown |

The deterministic engine ignores the demographic prior: `g_eff` is the user's
`value_growth_rate` (plus inflation in nominal mode). The prior enters only the
Monte Carlo (below). A price-shock block likewise affects only the Monte Carlo.

### Rent — `breakdown`

| Key | What it is | As computed |
|---|---|---|
| `rent_pv` | PV of rent | `Σ_t 12·rent·(1 + e_eff)^t · (1 + dr)^-t` (closed form: growing annuity with first payment `12·rent·(1 + e_eff)`), `e_eff` from `rent_escalation_rate` |
| `events_pv` | one-time events (e.g. moving) | `base_cost · (1 + dr)^-year` at `expected_year` clamped to `[1, N]` |
| `other_pv` | other recurring costs | as for owned options |
| `invested_capital_pv` | the renter's capital charged at year 0 — the mirror of `downpayment_pv` | `D = invested_down_payment`, undiscounted |
| `invested_dp_benefit_pv` | that capital's terminal value, as a NEGATIVE offset | `−D (1 + r_inv)^N / (1 + dr)^N`, `r_inv = investment_return_rate` (REAL; composed with inflation in nominal mode like `value_growth_rate`). Net capital term `D − D(1 + r_inv)^N/(1 + dr)^N` is 0 when `r_inv = dr`, so omitting `D` assumes the renter earns exactly the discount rate. (Until 2026-09-02 the year-0 charge was missing — every verdict leaned toward renting by exactly `D`) |
| `total_pv` | net cost of renting | sum of the five |

### The verdict — `verdict`

Computed once (`models.compute_verdict`) and read by the story headline, the
text report ("Cheapest … / decisiveness:") and `--json`.

| Key | What it is | As computed |
|---|---|---|
| `best` / `runner_up` | cheapest option and the closest competitor | options ranked by deterministic `total_pv` |
| `margin_pv` | the decision-relevant gap ("saves $X vs runner-up") | `total_pv(runner_up) − total_pv(best)` — never best-vs-costliest |
| `margin_frac` | the gap as a fraction of the winner's PV | `margin_pv / |total_pv(best)|` (`|total_pv(runner_up)|` when the winner's PV is exactly 0) |
| `monthly_equivalent` | "≈ $/month equivalent" | `pv_to_monthly_savings(margin_pv, dr, N)` = `margin · m / (1 − (1 + m)^−12N)`, `m = (1 + dr)^(1/12) − 1`; `null` when `dr = 0` |
| `prob_best` | Monte Carlo probability the deterministic winner is cheapest | `prob_<best>_cheapest` from the MC run; `null` without MC or on a single-path run |
| `mc_mean_best` | the option with the lowest Monte Carlo MEAN total PV | argmin of the per-option MC `mean`; `null` without MC or on a single-path run. When it differs from `best` (a jump process such as `price_shock` moves the mean without moving the deterministic line) `reason` says so with both means — "lowest expected cost" is then the mean, not `best` |
| `cash_year1` | undiscounted year-1 cash outlay per option | the affordability numerator's first year: fees/maintenance + other recurring costs + year-1 events + the full mortgage payment (owned); rent × 12 (rent). Not a PV — the PV totals credit equity at sale |
| `principal_year1` | principal repaid in year 1 | `mortgage_payment(loan, r, N) − loan × r` with `loan = initial_value − down_payment + financed_purchase_costs`; 0 without a mortgage. `cash_year1 − principal_year1` is the owner's year-1 unrecoverable cash before amortised purchase/selling costs |
| `appreciation_year1` | expected year-1 appreciation of an owned option (not cash) | `initial_value × g_eff`, `g_eff` = `value_growth_rate` composed with inflation in nominal mode; 0 for rent. The owner's year-1 economic cost ≈ `cash_year1 − principal_year1 − appreciation_year1` (+ amortised purchase/selling costs) — the term a cash-only sanity line omits |
| `decisive` / `rule` / `reason` | whether the gap clears the anchored threshold | `mc_floor`: `prob_best ≥ verdict.prob_floor` (0.65); `margin_band` (no MC, or every uncertainty input off): `margin_frac ≥ verdict.tie_band` (0.05); `single_option`: nothing to compare. `reason` quotes the measured quantity and the threshold; both constants are `--print-anchors` entries. The two are printed at whole percent, escalating to as many decimals (up to 4) as it takes for them to differ on the page — 0.6499 must not read "65% < 65% floor"; an exact tie still reads "65% ≥ 65%", which is true |

### Monte Carlo — `monte_carlo`

Per option, `num_sims` paths seeded by `random_seed`; each path recomputes the
option's net cost with randomness, then the same `_financing_pv` closes it.

| Key | What it is | As computed |
|---|---|---|
| `mean`, `std` | distribution of the per-path `total_pv` | `numpy.mean`, `numpy.std` (population, ddof = 0) |
| `p5`, `p50`, `p95` | percentiles of the per-path `total_pv` | `numpy.percentile` (linear interpolation); act 3 annotates p10 / median / p90 of the same array |
| `prob_condo_cheapest` / `prob_house_cheapest` / `prob_rent_cheapest` | share of paths in which that option has the lowest PV | `mean(argmin over present options == option)`; exact ties go to the first present option in condo → house → rent order; `null` with fewer than two options |

**What is random on a path** (all default-off; every vol at 0 = one repeated
path, which the report stamps "not a forecast"):

- **Cost-level shocks.** Each year, condo fees / house maintenance / other costs
  are multiplied by a shock: `shock_model: lognormal` → `exp(σ z − σ²/2)` (mean 1,
  median `exp(−σ²/2)`); `normal` → `max(0, 1 + σ z)`. `z` is standard normal,
  correlated with the year's inflation draw through `corr_inflation_*`
  (`z = ρ z_π + √(1 − ρ²) ε`).
- **Inflation (nominal mode).** The year's escalation factor is
  `(1 + π) · exp(σ_π z_π − σ_π²/2)` when `inflation_vol > 0`.
- **Events.** Timing: `jitter` → `round(clamp(Normal(expected_year, timing_std_years)))`
  within `[min_year, max_year]` and the horizon; `hazard` → the first year a uniform
  draw falls under `hazard_base + hazard_growth · (year − hazard_start_year)` (clamped
  to `[0, 1]`), possibly never. Cost: `base_cost × shock(cost_vol)` under `cost_distribution`.
- **Rent side.** `rent_escalation_vol` shocks the escalation RATE once per path
  (`e × shock`); `investment_return_vol` is the ANNUAL volatility of the gross return:
  one mean-preserving shock per year on `(1 + r_inv)`, so the capital's terminal value is
  `D · Π_t (1 + r_inv)·shock_t` and can end below principal (0.10 ≈ a 60/40 portfolio);
  `other_cost_vol` shocks the level of each other cost.
- **Demographic drift (only with `market_scenario`).** Per path: one scenario drawn
  uniformly from {low, reference, high}, and one `z_h` per horizon band. For simulation
  year t the band is the first of {2030, 2035, 2040, 2045, 2050} ≥ 2026 + t (the last band
  holds); the year's growth is `value_growth_rate + demo_drift_mean(h, s) + z_h · σ_h`,
  `σ_h = (demo_drift_p90 − demo_drift_p10) / 2.5632` (a Normal fitted through the published
  decile span; the divisor is the anchor `market_scenario.drift_sigma_divisor`). The drift
  is a real rate: in nominal mode the sum composes with inflation like `value_growth_rate`
  (the S4b-era refusal of a nominal run with a prior was lifted 2026-09-02).
- **Price-shock channel (only with a `price_shock` block).** Each year, with probability
  `min(annual_hazard × tilt, 1)` — `tilt` = the path scenario's `drawdown_weight_tilt`
  row, 1 without a prior — the value drops by `severity = min(severity_mean · exp(σ_s z − σ_s²/2), 1)`.
  For a house the drop hits both the maintenance base and the terminal value; for a
  condo the terminal value. More than one drawdown can occur on a path.

### Affordability — `affordability` (deterministic) and `affordability_mc`

Present only with an `income` block.

| Key | What it is | As computed |
|---|---|---|
| `annual_incomes` | income by year | `income_1 = annual_income`; each later year `× (1 + g_eff)` with `income_growth_rate` a REAL input (inflation-composed in nominal mode, like the cost numerator); a `pay_drop_events` entry multiplies income by `magnitude` in its year and the cut persists |
| `threshold` | the ratio that counts as a breach | `affordability_threshold` (default anchored, 0.32) |
| `ratios` | year-t housing cost ÷ year-t income | numerator = UNDISCOUNTED year-t outlay: fees `12·fee(1 + e_eff)^(t−1)` or maintenance `rate(t)·V0(1 + g_eff)^(t−1)` or rent `12·rent(1 + e_eff)^(t−1)`, plus the mortgage payment while `t ≤ term`, events in their year, other costs `(1 + e_eff)^(t−1)`. Note the exponent: the affordability numerator escalates from year 2, one year later than the PV engine's fee/rent convention — a documented divergence, not a rounding difference |
| `years_exceeding` | years whose ratio exceeds the threshold | `[t : ratio_t > threshold]` |
| `prob_condo_exceeds` / `prob_house_exceeds` / `prob_rent_exceeds` | Monte Carlo breach probability | share of paths on which ANY year's ratio exceeds the threshold, using the path's stochastic income (pay-drop `year_jitter_std`, `magnitude_vol` with the retained fraction clamped to `[0.01, 1]`) against the deterministic cost trajectory |

### The story's own figures (`--story`)

| Act | Figure | As computed |
|---|---|---|
| 1 The answer | the headline sentence and the bar per option | `verdict` above; bars are `total_pv` |
| 2 The race | cumulative cost curves and crossover years | running sums of `pv_single` of each year's out-of-pocket flow ("paid"); "net" adds the year-N equity credit so it reconciles to `total_pv`; a crossover is a year where the cheaper option flips |
| 3 The uncertainty | overlaid per-path `total_pv` histograms | p10 / median / p90 of the same arrays `p5`–`p95` summarise |
| 4 Home-value futures | a fan of value paths | the user's growth plus the prior row's `demo_drift_p10` / mean / `demo_drift_p90` per band, compounded yearly (deterministic quantile paths, not MC paths) |
| 5 The demographic signal | the prior itself | `demo_drift_mean` with the p10–p90 band per horizon and scenario, footer from the file's own vintage fields |
| 6 The market line | the solved break-even rent vs the cheapest owned option | the rent threshold is SOLVED, not read off the grid: `story_plots.solve_rent_threshold` calls the same `break_even.solve_crossings` as `--break-even rent.monthly_rent`, on the same ¼×–4× bracket and the verdict's tie band, so a crossing outside the drawn window is found rather than reported absent. The left panel draws 41 points over the ±35% window WIDENED to hold the crossing and its band (the window stays drawn, shaded, when it did widen); the crossing is marked at its exact height (one more engine run), the tie band shaded, and the caption is the engine's own band-first `sentence` rendered in $/mo with the acts' option names. No crossing in the bracket: the act and the caption name the bracket and which option is cheaper throughout. The right panel still sweeps the purchase price ±35% and interpolates its crossing between grid points |

### Sweeps — `--sweep KEY=v1,v2,…` or `KEY=start:stop:n`

Each point re-runs the comparison through the same loader (validated, defaults
echoed) and the same verdict rule; `rows` carry per-option `total_pv` and the
verdict fields, `flips` list consecutive points whose cheapest option differs.
Integer inputs (`years`, `num_sims`, `mortgage_term_years`) are rounded, and
the duplicates that rounding creates collapse — `years=7:8:5` is five requested
points and two distinct ones, run once each, with a `note` saying so; a
point the loader refuses (e.g. an event past a shortened horizon) is reported
as `error`, not skipped silently. Monte Carlo runs per point unless
`--no-monte-carlo` or the point is a single-path run. A sweep of an owned
option's `initial_value` also carries the price-scan coherence note below.

### Break-evens — `--break-even KEY` or `KEY=lo:hi`

The threshold on one input (`src/hde/break_even.py`): with exactly two priced
options, a nine-point scan of the bracket finds every sign change of
`total_pv(A) − total_pv(B)` on the deterministic line, bisection refines each
crossing, and the tie-band edges around it are solved the same way on the
verdict's own denominator (`|gap| / |cheaper PV| = verdict.tie_band`), walking
outward from the crossing one grid cell at a time — a second crossing ends the
band (that edge is `null`). Grid points the loader refuses (a price below the
fixed `down_payment`) are recorded under `refused` and the search shrinks to
the accepted run(s), reported as `searched`; a bracket refused throughout is a
clean error. Money inputs default to a ¼×–4× bracket around the YAML value;
rate inputs take an ABSOLUTE default bracket instead (a multiple of a rate is
meaningless — 0% growth × 4 is still 0%): `value_growth_rate` −2%…5%,
`rent_escalation_rate` −1%…5%, `annual_maintenance_rate` 0…3%, `mortgage_rate`
1%…10%, `discount_rate` 0…8%, and a rate key absent from the YAML still gets
its bracket. The bracket actually used is always printed. Every other key takes
`=lo:hi`. Integer inputs (`years`, amortization) are step
functions and report the first value where the other side is cheaper. The
crossing is deterministic: with uncertainty inputs on, the verdict's
decisiveness is the Monte Carlo floor, and the sweep's `mean flip:` line is the
criterion-consistent cross-check. Beside `--sweep`, the threshold is re-solved
at every sweep point (`across`): "the rent threshold at 0% and at 2% growth"
is one command. Every entry leads with a band-first `sentence` ("A is cheaper
below L; too close to call between L and H; B is cheaper above H") — the
shape the user should read. With an `income` block each entry also carries
`affordability` at the crossing and at both band edges (per option, the highest
cost/income ratio and the years above the threshold, printed too): a threshold
that says "buy up to $X" has to say what $X costs against income, and the band's
high edge is where it bites hardest. A `market_scenario` prior never moves it
(`note`). Rides `--json` as `break_evens`; the story's act 6 calls the same
solver for the rent threshold, so the crossing it draws, the band it shades and
the sentence it prints are the ones described here.

### Price-scan coherence — `--break-even` / `--sweep` on `initial_value`

Every grid point re-runs the whole loader, so whatever the loader DERIVES from
the price moves with the price and whatever is typed in dollars does not. The
property-tax bill, `purchase_costs`, `financed_purchase_costs` and insurance
are all price-proportional in reality, so a price scan holds them at the seed
price's size and the band it reports is wrong by that much (two reviewed
answers, 2026-09-03: a "buying wins above" edge that moved ~$50k, and a
clear-win edge that moved $35k). Two things close it:

- **Rate alternatives, re-derived every load.** `purchase_costs_rate` (fraction
  of the price; mutually exclusive with `purchase_costs`, and the figure
  `cash_available` nets) and `property_tax_rate` (fraction of value per year;
  mutually exclusive with an `other_recurring_costs` line whose name says tax —
  the schema has no dollar property-tax key, only that line). The derived tax
  bill is `rate × initial_value` escalating at the option's own
  `value_growth_rate`, so it stays that fraction of the home's value; it rides
  the other-recurring-cost escalation convention, one year ahead of the value's
  (§ Conventions), which is the documented divergence, not a second choice.
- **The coherence note.** Whenever a price scan leaves a dollar form in place,
  the break-even / sweep block's `note` names each held-fixed key with its
  value, the seed price it was sized for, and which side of the price it biases
  (understated owner costs above the seed favour buying; overstated below
  favour renting). The check reads the RAW YAML, so a figure the loader itself
  derived from the price is never flagged.

### Assumptions block — `assumptions`

`mode`, `years`, `discount_rate`; `lines` (the text echo, including the
`conventions:` line, a `<option> financing:` line for each mortgaged option — down payment as a share of price, the dollar distance above or below the 20% mortgage-insurance line, the loan-to-value (the loan the engine finances, `financed_purchase_costs` included), the year-0 cash the config commits, and any `financed_purchase_costs`; where the option states `cash_available` the same line leads with the netting itself — pile − `purchase_costs` = down payment — and drops the year-0 cash clause, which is the pile; with `mortgage_insurance` active the quoted loan-to-value is the one the TIER was chosen on (before the premium) and an `insured:` clause states the tier, the financed premium, the provincial tax paid in cash and the resulting loan and loan-to-value — `insured: 88.46% LTV → 3.10% tier = $14,260 financed; premium tax 9% (QC) = $1,283 cash → loan $474,260 = 91.20% LTV` — reading `mortgage_insurance: auto → none required (…)` when the option clears 80%, and the derived premium is never echoed as a typed `financed_purchase_costs` — and the `demographic prior:` line, which quotes the prior's reference REAL drift for the bands the horizon touches); `defaults_applied`
(every key the YAML omitted, with its value, citation tag, `kind`, and the full
anchor record — `uv run hde --print-anchors` lists the same records);
`reference_matches` (each owned-option property-tax or home-insurance line, its
implied rate, and every jurisdiction anchor whose published figure equals it —
empty `matches` says plainly that no source agrees);
`demographic_prior` (the loaded file's provenance and cited sources, or `null`);
and `sources` — the source-class echo.

**Source classes (`sources`).** `defaults_applied` answers "what did the engine
fill in?"; the source echo answers the other half, "who stated the rest?". The
optional top-level `sources:` block maps a dotted key the config SETS
(`rent.monthly_rent`, `simulation.investment_return_vol`, `house.events` for a
whole list) to `user`, `assistant`, or `anchor:<registry name>` — and, for a
value that is the sum of two published figures, `anchor:<name>+<name>`
(`anchor:property_tax.laval+school_tax.qc`), which echoes both. A declaration is
checked by FIGURE, not only by name: the stated value must equal the anchor's
(or the sum, or a declared restatement — 6.09% posted and 6.1827% effective
annual are one figure) within the read-back matcher's own window, and a
`source: none` entry can never be declared, because it holds no figure. Anchor
2026-09-04: `anchor:property_tax.quebec_city` was accepted on a 0.82539% rate
and the same read-back printed `anchor-sourced` beside `no anchor match` for
that one number — a name-only check dresses an estimate as a citation, which is
worse than declaring nothing. It feeds four echo lines — `user-stated:`, `assistant-typed:`, `anchor-sourced: key=value
[anchor name]`, and `unattributed:` for stated keys the block omits — and, with
no block at all, the single line `sources: none declared — the read-back cannot
tell the user's numbers from the assistant's`. Values are echoed in the config's
own units ($/mo, dollars, percentages, counts, `N entries` for a list). It
changes NO computation: a declared key the config does not set, a class outside
those three forms, an anchor name outside the registry, and an anchor whose
figure is not the one the config states all refuse at load.

Its one consequence is the decisiveness-provenance `[warning]`: when the
`mc_floor` rule decides the verdict, every uncertainty input that is
`assistant`-typed or unattributed is named with its value, followed by what the
deterministic line alone says and whether that margin clears the tie band.
`sources.uncertainty_inputs` mirrors `config.single_path_run` — one definition
of "widens the distribution", pinned by a test — so the warning cannot miss an
input the engine treats as uncertainty.
