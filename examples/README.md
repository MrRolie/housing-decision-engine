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
