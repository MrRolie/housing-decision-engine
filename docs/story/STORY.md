<!-- Regenerate with: uv run hde examples/showcase_demographic_prior.yaml --story docs/story (from the repo root) -->

# The story of this housing decision

**Renting wins by $32,072 over 25 years** — under MTL_RMR demographic conditions · 25-year horizon.

Demographic prior: MTL_RMR demand model (ISQ 2026 scenarios, 2021 census) · constants as of 2026-07-21 · simulation year 1 = calendar 2026, bands 2030/2035/2040/2045/2050 · mapping v1: excess-demand rate → real price drift through a linear-through-origin β prior with the uniform β demoflow pinned; horizon bands (2030…2050) are piecewise-constant with no interpolation; drawdown_weight_tilt multiplies the user's price-shock hazard (S4b sketch §1 slots 2–3, §3) · 13 pinned sources (sha256 in --json): StatCan 98-10-0231-01; ISQ arrival flows (RA); ISQ arrival flows (RMR); derived: headship rate by single year of age; StatCan 98-10-0232-01; derived: living-arrangement shares; StatCan 98-10-0134-01; CIA CPM2014 mortality + CPM-B scale; derived: ownership rate by geography × age; derived: HORS_RMR ownership curve; ISQ population scenarios (QC); ISQ population scenarios (RA); ISQ population scenarios (RMR).

## Act — The answer

Renting wins by $32,072 over 25 years

![The answer](act1_the_answer.png)

## Act — The race

Renting costs less out of pocket every single year — the ranking never flips (before the end-of-horizon equity credit, which decides the verdict).

![The race](act2_the_race.png)

## Act — The uncertainty

In 81% of 5,000 simulations, renting came out cheapest.

![The uncertainty](act3_the_uncertainty.png)

## Act — Your home's possible futures

Under MTL_RMR demographic demand scenarios, the home's value fans out around your 2.0% growth assumption.

![Your home's possible futures](act4_home_futures.png)

## Act — Why

The demographic signal itself: projected price drift from household demand in MTL_RMR (ISQ 2026 scenarios, 2021 census).

![Why](act5_demographic_signal.png)

## Act — The market line

Renting stays cheaper than buying a house until rent passes $2,544/mo — your $2,400 is $144/mo below that line.

![The market line](act6_the_market_line.png)

Full text report: [report.txt](report.txt)

---

## Assumptions

- mode: real terms · discount_rate 5.0%
- condo: value growth +2.0%/yr · fee escalation +3.0%/yr · selling_cost_rate 5.0%
- house: value growth +2.0%/yr · maintenance 1.2% of value/yr · selling_cost_rate 5.0%
- rent: escalation +2.5%/yr · invested capital $145,000 at +5.0%/yr
- demographic prior: MTL_RMR (ISQ 2026 scenarios, 2021 census) · constants as of 2026-07-21 · sha256 e73fff23ef46… [demoflow ScenarioPrior v1]
- defaults applied: economic.mode='real', economic.inflation_rate=0.0% [ref: FP Canada 2026 PAG], condo.selling_cost_rate=5.0% [WOWA 2026], house.selling_cost_rate=5.0% [WOWA 2026]
