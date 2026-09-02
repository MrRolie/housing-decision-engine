# One side known — the threshold lane

Most people arrive certain about one side and vague about the other: "I'm
looking at houses in Duvernay around $650k — what rent would keep renting the
better deal?", "I pay $1,900; at what price is buying worth it?", "how long
would I have to stay?". That is a threshold question, not a verdict question.

## Author the config

Their known side is the config's number. The unknown side needs a placeholder
so the engine can run (a `monthly_rent`, an `initial_value`): use their
current rent or the middle of the price band, and say so in the answer.
Everything property-specific they cannot know yet (tax, fees, maintenance,
purchase costs) is an estimate you label. A price break-even holds
`down_payment` fixed (a fixed cash pile), so the loan-to-value and any
insurance premium change along the scan — say so.

## One command, several brackets

`--break-even` solves the threshold on the deterministic line; beside
`--sweep` it is re-solved at every sweep point (the `across` block), so the
threshold at both ends of an estimate is one command:

```
uv run hde scenarios/<slug>.yaml --break-even rent.monthly_rent \
  --sweep house.value_growth_rate=0:0.02:3 \
  --sweep house.annual_maintenance_rate=0.006,0.012 \
  --sweep rent.rent_escalation_rate=0,0.01 \
  --no-monte-carlo --json
```

- **Growth first.** With no price-growth view, `value_growth_rate` is the
  least certain estimate by construction (the engine's default is neutral,
  uncited): quote the threshold at 0% and at the top of the band.
- **Then the largest labelled dollar estimate** (maintenance 1.2% vs 0.6%).
- **Then every default the engine warned on** (the 1% real rent escalation:
  a Québec continuing lease is ≈ 0% real).
- Each `--sweep` varies ONE input with every other held at its base value;
  the `across` blocks are single-axis, never a cross-product. A bracket end
  that flips the verdict is therefore a claim about a combination (gate 5):
  say what else that end assumes ("at 2% growth, with 0.6% maintenance and
  1% real rent escalation held, your $1,900 puts buying ahead"), and when the
  combination matters, run it — edit the config to the other maintenance
  figure and repeat the growth sweep — or write "not run". Never call a
  single base rate "the point estimate".
- If the engine reports that the config refuses part of the bracket (a price
  below the down payment), quote the searched range, not the bracket asked
  for.

## Which brackets lead

Four `across` blocks give twelve threshold sentences; the answer does not
carry them all. The headline sentence is the base threshold plus the growth
bracket (the input with no evidence). Every other bracket gets one clause
each ("at 1.2% maintenance the band is $2,768–$3,052; at 0% rent escalation
$2,588–$2,853; ten years barely moves it"), unless its end flips the verdict
at the user's rent — then it joins the headline with its conditions.

## The threshold sentence

Band-first, edges named. Every break-even entry and `across` row carries a
`sentence` field in that shape — quote it in the user's units:

> renting is cheaper below $2,715/month, too close to call between $2,715 and
> $2,993, buying is cheaper above $2,993.

Never the crossing-first form ("the crossing is $2,850 — below that renting is
cheaper; between $2,715 and $2,993 it's too close"): the crossing sits inside
the band and the reader cannot tell which clause wins on $2,715–$2,850. Never
"above that" after a band — name the edge. Fold the growth bracket into the
same sentence: "renting is cheaper below $2,715 if Laval prices only track
inflation, below $1,864 if they grow 2%/yr above it — at 2% your $1,900 is a
toss-up".

## The prior and the second band

A `market_scenario` prior does NOT move `--break-even` (the header says so):
its drift enters the Monte Carlo only. The prior run answers "does the verdict
at their rent survive the demographic view?", never "where is the threshold?"
— it is not the growth sweep and does not replace it. Quote the drift the
assumptions line prints for the horizon's bands, so a flat prior is never
introduced as "instead of flat prices".

With any uncertainty input on, the verdict's decisiveness is the Monte Carlo
floor, so quote BOTH bands: the deterministic tie band from `--break-even`,
and the verdict's band from the uncertainty config (prior or vols on, Monte
Carlo on):

```
uv run hde scenarios/<slug>-prior.yaml \
  --sweep rent.monthly_rent=<band low − 10%>:<band high + 10%>:11 --json
```

Read `decisive`, `prob_best` and `mc_mean_best` per row and quote where
`decisive` flips ("under the Laval prior the Monte Carlo calls rent decisive
up to $2,300 and buying from $2,800, neither between $2,400 and $2,700"). When
the user's rent sits outside both bands one clause suffices; inside either,
both bands lead. With only the owned side stochastic (a prior and
`investment_return_vol` 0) the engine warns `one-sided uncertainty`: the
probabilities are OVERconfident and the true toss-up zone is wider — never
"the simulation overstates the uncertainty". Cross-check the sweep's `mean
flip:` line on the same input.
