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
├── __init__.py         # Library surface (what the CLI and MCP tools use)
├── anchors.py          # Provenance registry: every engine default + source/url/band/kind;
│                       #   SOURCE_KEY_CITATIONS for the demographic prior's inputs
├── models.py           # Parameter + result dataclasses; Verdict + compute_verdict
├── pv.py               # Pure PV helpers (annuities, mortgage math, monthly equivalent)
├── deterministic.py    # Deterministic PV engine (compute_deterministic)
├── monte_carlo.py      # Monte Carlo engine (run_monte_carlo)
├── market_scenario.py  # ScenarioPrior loader/validation, drift banding, time-anchor guard
├── config.py           # YAML → ComparisonSpec; coherence + time-anchor warnings
├── input_schema.py     # The input contract as data (--print-schema)
├── serialization.py    # THE typed core for agent output (--json, MCP)
├── reporting.py        # Text report (+ legacy matplotlib figures)
├── story_plots.py      # The six-act decision story (figures + sentences)
├── story_page.py       # STORY.md + report.txt package (--story)
└── cli.py              # `hde` entry point
mcp_server/             # FastMCP wrappers over the same functions (non-shell consumers)
```

Data flow: `load_config` → `ComparisonSpec` → `compute_deterministic` and
`run_monte_carlo` → `compute_verdict` → one of `format_text_report`,
`render_story_package`, or the serializers (`det_to_dict`, `mc_to_dict`,
`verdict_to_dict`, `assumptions_to_dict`). Every surface reads the same
verdict and the same assumption echo; none re-derives a figure.

Provenance chain: `anchors.py` is the single source of truth for every
bias-critical default (dataclass default == parser default == anchor, pinned
generatively in `tests/test_anchors.py`); `market_scenario.py` guards the
demographic prior (schema, closed enums, `constants_as_of` within a year of
`START_CALENDAR_YEAR = 2026`) and renders its provenance only from the file.

## Conventions (every figure below obeys these)

- **Years are 1-indexed; cash flows fall at the END of year t and discount at
  `(1 + dr)^-t`** (`pv_single`). Year-0 outlays (the down payment) are undiscounted.
  `dr` = `discount_rate`, in the same terms (real or nominal) as every rate.
- **Nominal mode composes inflation into every escalation:** `g_eff = (1 + g)(1 + π) − 1`
  (`_effective_growth_rate`); in real mode `g_eff = g`. Defaults are REAL terms.
- **Two escalation-start conventions coexist by design.** Condo fees, rent and
  "other recurring" costs escalate before year 1: year-t amount = `base × (1 + e_eff)^t`.
  House maintenance and home value do not: year-t value = `V0 × (1 + g_eff)^(t−1)`.
- **Mortgage = level ANNUAL payment at an EFFECTIVE ANNUAL rate**, `M = L·r / (1 − (1 + r)^−T)`
  (`P/T` when `r = 0`), `L = initial_value − down_payment`. A Canadian posted rate compounds
  semi-annually with monthly payments — convert first: `r_eff = (1 + r_posted/2)^2 − 1`
  (≈ 1.7% difference on the annual outlay at 5%).
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
| `invested_dp_benefit_pv` | the renter's invested capital, as a NEGATIVE offset | `−D (1 + r_inv)^N / (1 + dr)^N`, `D = invested_down_payment`, `r_inv = investment_return_rate` as entered (not inflation-composed); 0 when `D = 0` |
| `total_pv` | net cost of renting | sum of the four |

### The verdict — `verdict`

Computed once (`models.compute_verdict`) and read by the story headline, the
text report ("Cheapest … / decisiveness:"), `--json` and MCP.

| Key | What it is | As computed |
|---|---|---|
| `best` / `runner_up` | cheapest option and the closest competitor | options ranked by deterministic `total_pv` |
| `margin_pv` | the decision-relevant gap ("saves $X vs runner-up") | `total_pv(runner_up) − total_pv(best)` — never best-vs-costliest |
| `margin_frac` | the gap as a fraction of the winner's PV | `margin_pv / |total_pv(best)|` (`|total_pv(runner_up)|` when the winner's PV is exactly 0) |
| `monthly_equivalent` | "≈ $/month equivalent" | `pv_to_monthly_savings(margin_pv, dr, N)` = `margin · m / (1 − (1 + m)^−12N)`, `m = (1 + dr)^(1/12) − 1`; `null` when `dr = 0` |
| `prob_best` | Monte Carlo probability the deterministic winner is cheapest | `prob_<best>_cheapest` from the MC run; `null` without MC or on a single-path run |
| `decisive` / `rule` / `reason` | whether the gap clears the anchored threshold | `mc_floor`: `prob_best ≥ verdict.prob_floor` (0.65); `margin_band` (no MC, or every uncertainty input off): `margin_frac ≥ verdict.tie_band` (0.05); `single_option`: nothing to compare. `reason` quotes the measured quantity and the threshold; both constants are `--print-anchors` entries |

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
  (`e × shock`); `investment_return_vol` shocks `r_inv` the same way; `other_cost_vol`
  shocks the level of each other cost.
- **Demographic drift (only with `market_scenario`).** Per path: one scenario drawn
  uniformly from {low, reference, high}, and one `z_h` per horizon band. For simulation
  year t the band is the first of {2030, 2035, 2040, 2045, 2050} ≥ 2026 + t (the last band
  holds); the year's growth is `value_growth_rate + demo_drift_mean(h, s) + z_h · σ_h`,
  `σ_h = (demo_drift_p90 − demo_drift_p10) / 2.5632` (a Normal fitted through the published
  decile span; the divisor is the anchor `market_scenario.drift_sigma_divisor`). Real
  terms only — a nominal run with a prior is refused.
- **Price-shock channel (only with a `price_shock` block).** Each year, with probability
  `min(annual_hazard × tilt, 1)` — `tilt` = the path scenario's `drawdown_weight_tilt`
  row, 1 without a prior — the value drops by `severity = min(severity_mean · exp(σ_s z − σ_s²/2), 1)`.
  For a house the drop hits both the maintenance base and the terminal value; for a
  condo the terminal value. More than one drawdown can occur on a path.

### Affordability — `affordability` (deterministic) and `affordability_mc`

Present only with an `income` block.

| Key | What it is | As computed |
|---|---|---|
| `annual_incomes` | income by year | `income_1 = annual_income`; each later year `× (1 + income_growth_rate)`; a `pay_drop_events` entry multiplies income by `magnitude` in its year and the cut persists |
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
| 6 The market line | break-even rent vs the cheapest owned option | rent swept ±35% around the quoted rent on 41 points; each point re-runs the deterministic engine; the break-even is the linearly interpolated crossing of `total_pv(rent)` and `total_pv(cheapest owned)`; "on the line" = within one grid step |

### Assumptions block — `assumptions`

`mode`, `years`, `discount_rate`; `lines` (the text echo, including the
`conventions:` line and the `demographic prior:` line); `defaults_applied`
(every key the YAML omitted, with its value, citation tag, `kind`, and the full
anchor record — `uv run hde --print-anchors` lists the same records);
`demographic_prior` (the loaded file's provenance and cited sources, or `null`).
