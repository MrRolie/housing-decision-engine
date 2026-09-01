<!-- Regenerate with: uv run hde examples/showcase_demographic_prior.yaml --story docs/story (from the repo root) -->

# The story of this housing decision

**Renting wins by $32,072 over 25 years** — under MTL_RMR demographic conditions · 25-year horizon.

Demographic prior: MTL_RMR demand model (ISQ 2026 scenarios, 2021 census). Source: UN WPP 2024-derived demand model, ISQ 2026 scenarios.

## Act — The answer

Renting wins by $32,072 over 25 years

![The answer](act1_the_answer.png)

## Act — The race

Renting costs less out of pocket every single year — the ranking never flips.

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
- house: value growth +2.0%/yr · selling_cost_rate 5.0%
- rent: escalation +2.5%/yr · invested capital $145,000 at +5.0%/yr
- defaults applied: economic.mode='real', economic.inflation_rate=0.0% [ref: FP Canada 2026 PAG], condo.selling_cost_rate=5.0% [WOWA 2026], house.selling_cost_rate=5.0% [WOWA 2026]
