# Examples — an ordered walkthrough

Four YAML scenarios, in the order to read them. Each is a complete run: `uv run hde examples/<file>.yaml`.
Add `--story DIR` to any of them to get the five-act plots plus a STORY.md one-pager in `DIR`.

## 1. `basic_config.yaml` — condo vs house

**Question:** all-cash condo vs all-cash house over 20 years — which costs less, and how sensitive is that to maintenance shocks and fee escalation?

```bash
uv run hde examples/basic_config.yaml
```

Five acts (`--story` renders acts 1–4; act 5 needs a demographic prior, which this config doesn't load):
1. **The answer** — total PV per option, cheapest highlighted, margin in words.
2. **The race** — cumulative out-of-pocket cost per year; where the lead changes hands; the end-of-horizon equity credit as a dotted drop.
3. **The uncertainty** — Monte Carlo cost distributions with p10/median/p90 and the probability each option is cheapest.
4. **Your home's possible futures** — home value under your growth assumption (a single honest line here; a demographic fan chart when a prior is loaded).
5. **Why** — the demographic demand signal behind the prior (only rendered when `market_scenario:` is set).

## 2. `rent_vs_condo_vs_house.yaml` — the full 3-way race

**Question:** with the condo's purchase capital invested instead (like-for-like opportunity cost), does renting beat both purchase options?

```bash
uv run hde examples/rent_vs_condo_vs_house.yaml
```

Same five acts, now three runners in the race. Watch act 2: renting starts cheapest (no down payment) and the crossover year — if any — is the whole decision.

## 3. `income_shock.yaml` — affordability under a pay cut

**Question:** after a 20% pay cut in year 3, which option keeps housing cost inside the affordability threshold?

```bash
uv run hde examples/income_shock.yaml
```

The run prints per-year housing-cost/income ratios (`affordability` in the report); the story acts show the cost race the ratios are measured against.

## 4. `showcase_demographic_prior.yaml` — the full stack (all five acts)

**Question:** what happens to the rent-vs-buy verdict when a real demographic demand prior — UN population projections → ISQ scenarios → demoflow's audited demand model — tilts price growth and crash risk?

```bash
uv run hde examples/showcase_demographic_prior.yaml --story docs/story
```

This is the repo's living showcase: [docs/story/STORY.md](../docs/story/STORY.md) renders all five acts, including act 4's fan chart (low/reference/high demand scenarios) and act 5's demographic signal itself. Regenerable with the command stamped at the top of the STORY.md.

## Parameter sources

The example configs are de-facto templates — users and agents copy them, so every
assumption-bearing number carries a provenance stamp: either a citation or an explicit
`illustrative` marker. Each YAML opens with a `# --- Parameter provenance ---` block and
carries inline `# <cite>` comments on the lines themselves.

**Convention:** values marked `illustrative` are calibration choices, not evidence —
sensitivity-test them (e.g. via `sweep_param` on the MCP server, or by editing and re-running).

| Assumption category | Source | Where used |
|---|---|---|
| Inflation (nominal mode) | FP Canada Standards Council, 2026 Projection Assumption Guidelines (fpcanada.ca): 2.1% long-term inflation | `advanced_config.yaml` `economic.inflation_rate` |
| Shelter-cost / fee / recurring-cost escalation | FP Canada 2026: shelter cost growth 3.1% nominal ⇒ ~1.0% real planning reference | `fee_escalation_rate`, `other_recurring_costs.escalation_rate` in all examples; engine default `rent_escalation` 0.01 real (`src/hde/anchors.py`) |
| Rent escalation | FP Canada 2026 shelter ≈ 1.0% real + NBER digest Oct 2025 (continuing-tenant pass-through ~21%; QC TAL guideline ≈ CPI for existing leases ⇒ ≈ 0.0% real) | `rent_escalation_rate` in `rent_vs_condo_vs_house.yaml`, `income_shock.yaml`, `showcase_demographic_prior.yaml` |
| Investment return (invested down payment / reserves) | FP Canada 2026: balanced 60/40 ≈ 3.0% real; equities ≈ 4.2% real, upper bound ≈ 5.2% (EM 7.5% nominal − 2.1% inflation) | `investment_return_rate` 0.03 in `rent_vs_condo_vs_house.yaml` / `income_shock.yaml`, 0.05 (equity-tilted) in `showcase_demographic_prior.yaml`; engine default 0.03 real (`src/hde/anchors.py`) |
| Salary / income growth | FP Canada 2026: 3.1% nominal ⇒ ~1.0% real planning reference | `income_shock.yaml` `income.income_growth_rate` |
| Affordability threshold | CMHC "Calculating GDS/TDS" (cmhc-schl.gc.ca): GDS cap 39%, TDS 44%; legacy guideline 32% | `income_shock.yaml` `affordability_threshold` (0.35); engine default 0.32 (`src/hde/anchors.py`) |
| Selling costs | WOWA.ca "Cost of Selling a House in Canada 2026" (wowa.ca): seller commissions ≈ 4–5% + notary/discharge ⇒ ~5% all-in | engine default `selling_cost` 0.05 (`src/hde/anchors.py`) |
| Maintenance rates | NAHB "Operating Costs of Owning a Home" (Siniavskaia, Jan 2021; 2019 AHS) Table 2: routine maintenance ≈ 0.6% of value/yr for all homes (0.8% pre-1960 → 0.2% 2010s; narrow definition excluding major repairs); "1% rule" budgeting heuristic (uncited) | `annual_maintenance_rate`, `maintenance_curve` in all owned-option examples |
| Crash severity | TREB 1989–96 via Better Dwelling: −27.6% nominal peak-trough (≈ −39% real) — Canada's largest observed metro correction | `price_shock.severity_mean` (≈ 0.25 anchor) in `showcase_demographic_prior.yaml`; engine default `severity_mean` 0.25 (`src/hde/anchors.py`) |
| Demographic price drift | demoflow ScenarioPrior: ISQ population scenarios (2021 Census base) → cohort roll-forward → excess demand → β-mapped real price drift; every source pinned by sha256 and cited in the run's `assumptions.demographic_prior` (`src/hde/anchors.py` `SOURCE_KEY_CITATIONS`) | `market_scenario` in `showcase_demographic_prior.yaml` |
| Discount rate (0.03–0.05 real) | illustrative — personal time-preference; sanity band [0.02, 0.06] | `discount_rate` in all examples |
| `value_growth_rate` | illustrative market view — no defensible universal long-run real appreciation default | all owned-option examples; see `showcase_demographic_prior.yaml` for the demographic alternative |
| Event costs, service lives, timings (roof, HVAC, water heater, appliances, paint, driveway, special assessments) | illustrative — calibrate to your reserve study or component inventory | `events:` blocks in all examples |
| Vols, correlations, hazard rates (`cost_vol`, `*_vol`, `corr_*`, `hazard_*`) | illustrative uncertainty calibration — sensitivity-test via sweep | `events:` and `simulation:` blocks in all examples |

Engine defaults cited above live in `src/hde/anchors.py`; per-file details are in each
YAML's provenance header.
