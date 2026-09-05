<!-- Regenerate with: uv run hde examples/showcase_demographic_prior.yaml --story docs/story (from the repo root) -->

# The story of this housing decision

**Too close to call — effectively a tie: Buying a house edges buying a condo by $4,135 (0.8%) over 25 years, cheapest in only 36% of 5,000 simulations** — under MTL_RMR demographic conditions · 25-year horizon.

> warning: decisiveness rests on uncertainty inputs the user did not state: simulation.investment_return_vol=10.0% (assistant), condo.price_shock.annual_hazard=3.0% (assistant), condo.price_shock.severity_mean=20.0% (assistant), condo.events=1 entry (cost_vol 20.0%) (assistant), house.price_shock.annual_hazard=3.0% (assistant), house.price_shock.severity_mean=20.0% (assistant), house.events=1 entry (cost_vol 15.0%) (assistant), market_scenario.path='tests/fixtures/scenario_prior_golden.json' (assistant) — the deterministic line alone says house by $4,135 (0.8% of its PV — not decisive under the 5% band)

Demographic prior: MTL_RMR demand model (ISQ 2026 scenarios, 2021 census) · constants as of 2026-07-21 · simulation year 1 = calendar 2026, bands 2030/2035/2040/2045/2050 · mapping v1: excess-demand rate → real price drift through a linear-through-origin β prior with the uniform β demoflow pinned; horizon bands (2030…2050) are piecewise-constant with no interpolation; drawdown_weight_tilt multiplies the user's price-shock hazard (S4b sketch §1 slots 2–3, §3) · encoded REAL drift by band, added to value_growth_rate in the Monte Carlo — all: reference 2030 +0.27%/yr, 2035 +0.25%/yr, 2040 +0.09%/yr, 2045 +0.03%/yr, 2050 +0.01%/yr (scenarios -0.94%…+1.35%) · 13 pinned sources (sha256 in --json): StatCan 98-10-0231-01; ISQ arrival flows (RA); ISQ arrival flows (RMR); derived: headship rate by single year of age; StatCan 98-10-0232-01; derived: living-arrangement shares; StatCan 98-10-0134-01; CIA CPM2014 mortality + CPM-B scale; derived: ownership rate by geography × age; derived: HORS_RMR ownership curve; ISQ population scenarios (QC); ISQ population scenarios (RA); ISQ population scenarios (RMR).

## Act — The answer

Too close to call — effectively a tie: Buying a house edges buying a condo by $4,135 (0.8%) over 25 years, cheapest in only 36% of 5,000 simulations

![The answer](act1_the_answer.png)

## Act — The race

Renting costs less out of pocket every single year — the ranking never flips (before the end-of-horizon equity credit, which decides the verdict).

![The race](act2_the_race.png)

## Act — The uncertainty

In 36% of 5,000 simulations, buying a house came out cheapest.

![The uncertainty](act3_the_uncertainty.png)

## Act — Your home's possible futures

Under MTL_RMR demographic demand scenarios, the home's value fans out around your 2.0% real (4.1% as quoted) growth assumption.

![Your home's possible futures](act4_home_futures.png)

## Act — Why

The demographic signal itself: projected price drift from household demand in MTL_RMR (ISQ 2026 scenarios, 2021 census).

![Why](act5_demographic_signal.png)

## Act — The market line

Your $2,400/mo sits inside the tie band around the crossing — renting is cheaper below $2,189/mo; too close to call between $2,189/mo and $2,413/mo; buying a house is cheaper above $2,413/mo (crossing $2,298/mo; band = 5% of the cheaper option's PV).

![The market line](act6_the_market_line.png)

Full text report: [report.txt](report.txt)

---

## Assumptions

- mode: real terms · discount_rate 7.2% as quoted → 5.0% real (after 2.1% inflation)
- condo: value growth +2.0%/yr (4.1% as quoted) · fee escalation +3.0%/yr (5.2% as quoted) · selling_cost_rate 5.0%
- house: value growth +2.0%/yr (4.1% as quoted) · maintenance 1.2% of value/yr · selling_cost_rate 5.0%
- condo other costs: property_tax $3,600/yr = 0.750% of price [no anchor match — hde --print-anchors]
- house other costs: property_tax $4,700/yr = 0.855% of price [no anchor match — hde --print-anchors] · home_insurance $1,200/yr [no anchor match — hde --print-anchors]
- rent: escalation +2.5%/yr (4.7% as quoted) · invested capital $145,000 at +5.0%/yr (7.2% as quoted)
- conventions: end-of-year cash flows discounted at (1+dr)^-t · fees, rent and other costs escalate before year 1, maintenance from year 1 · mortgage = level annual payment at an effective annual rate · $/mo equivalent at (1+dr)^(1/12)−1 (docs/reference/ARCHITECTURE.md figure glossary)
- demographic prior: MTL_RMR (ISQ 2026 scenarios, 2021 census) · constants as of 2026-07-21 · sha256 e73fff23ef46… [demoflow ScenarioPrior v1] · reference REAL drift over this 25-year run — all: +0.27%/yr (2030 band), +0.25%/yr (2035 band), +0.09%/yr (2040 band), +0.03%/yr (2045 band), +0.01%/yr (2050 band) (added to value_growth_rate in the Monte Carlo; all bands and the scenario range in --json)
- defaults applied: economic.mode='real', economic.inflation_rate=2.1% [FP Canada 2026 PAG], condo.selling_cost_rate=5.0% [WOWA 2026], house.selling_cost_rate=5.0% [WOWA 2026]
- rates: as quoted · discount_rate 7.2% as quoted = 5.0% after 2.1% inflation · condo.fee_escalation_rate 5.2% as quoted = 3.0% after 2.1% inflation · condo.value_growth_rate 4.1% as quoted = 2.0% after 2.1% inflation · condo.other_recurring_costs.property_tax.escalation_rate 2.1% as quoted = 0.0% after 2.1% inflation · house.value_growth_rate 4.1% as quoted = 2.0% after 2.1% inflation · house.other_recurring_costs.property_tax.escalation_rate 2.1% as quoted = 0.0% after 2.1% inflation · house.other_recurring_costs.home_insurance.escalation_rate 2.1% as quoted = 0.0% after 2.1% inflation · rent.rent_escalation_rate 4.7% as quoted = 2.5% after 2.1% inflation · rent.investment_return_rate 7.2% as quoted = 5.0% after 2.1% inflation
- user-stated: years=25, market_scenario.geography='MTL_RMR', condo.monthly_fee=$800/mo, condo.initial_value=$480,000, condo.all_cash=true, house.initial_value=$550,000, house.all_cash=true, rent.monthly_rent=$2,400/mo, rent.invested_down_payment=$145,000
- assistant-typed: discount_rate=7.2%, market_scenario.path='tests/fixtures/scenario_prior_golden.json', condo.fee_escalation_rate=5.2%, condo.value_growth_rate=4.1%, condo.purchase_costs=$7,200, condo.other_recurring_costs=1 entry, condo.price_shock.annual_hazard=3.0%, condo.price_shock.severity_mean=20.0%, condo.events=1 entry, house.value_growth_rate=4.1%, house.annual_maintenance_rate=1.2%, house.purchase_costs=$8,200, house.other_recurring_costs=2 entries, house.price_shock.annual_hazard=3.0%, house.price_shock.severity_mean=20.0%, house.events=1 entry, rent.rent_escalation_rate=4.7%, rent.investment_return_rate=7.2%, simulation.num_sims=5,000, simulation.random_seed=42, simulation.investment_return_vol=10.0%
- anchor-sourced: condo.price_shock.severity_vol=10.0% [price_shock.severity_vol], house.price_shock.severity_vol=10.0% [price_shock.severity_vol]
