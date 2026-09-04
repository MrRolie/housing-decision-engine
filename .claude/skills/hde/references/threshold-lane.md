# One side known — the threshold lane

Most people arrive certain about one side and vague about the other: "I'm
looking at houses in Duvernay around $650k — what rent would keep renting the
better deal?", "I pay $1,900; at what price is buying worth it?", "how long
would I have to stay?". That is a threshold question, not a verdict question.

## Author the config

Their known side is the config's number. The unknown side needs a placeholder
so the engine can run (a `monthly_rent`, an `initial_value`): for a rent
threshold their current rent or a market rent you label; for a price threshold
a first guess a step BELOW the price their cash supports at 20% down (with the
transfer tax and purchase costs netted, the engine's `financing:` line prints
the distance to the 20% line and, with `cash_available`, the price where the
cash stops covering 20% — take that figure, never cash × 5) — and say so in
the answer. Everything property-specific they cannot know yet
(tax, fees, maintenance, purchase costs) is an estimate you label; check
`--print-anchors` first. Declare the placeholder itself, and every estimate,
as `assistant` in the config's `sources:` block — the seed price is not the
user's number. A renter whose money sits in equities gets a bracketed return
(3% and 5% real; `references/translation.md`), never the 60/40 anchor
unnamed: on a price threshold the buy edge can move six figures between them. State the cash pile as `cash_available` (never a
hand-computed `down_payment`): along a price scan the engine re-nets it at
every point, so the loan-to-value, the 20% line and the premium tier move
with the price — quote the `financing:` line at the crossing. Dollar-form
inputs (a tax bill, `purchase_costs`, a premium) stay fixed along the scan:
either scale them with the rate forms (`property_tax_rate` as a fraction of
value, `purchase_costs_rate` as a fraction of price — the engine re-derives
both at every point) or read back the engine's coherence `note` with its
direction (sized for the seed, they favour buying above it and renting
below). Prefer the rate forms on any price threshold. The break-even also
prints affordability at the crossing and the band edges when an income is
given — quote it, and at every bracket end too: the `across` rows carry
affordability, and a growth-bracket "safe-buy ceiling" that sits at 44% of
income is a breach, not a ceiling.

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
  that flips the verdict at the user's number is therefore a claim about a
  combination (gate 5): name what that end holds fixed ("at 2% growth, with
  0.6% maintenance and 1% real rent escalation held, your $1,900 puts buying
  ahead"), then run the combination — a SECOND config with the other
  maintenance figure typed, the same `--break-even` + growth `--sweep`
  command — and quote both ("with 1.2% maintenance the 2% band moves up and
  renting still wins"). Never quote a combination you did not run; write
  "not run". Never call a single base rate "the point estimate".
- If the engine reports that the config refuses part of the bracket (a price
  below the down payment), quote the searched range, not the bracket asked
  for.

## Which brackets lead

Four `across` blocks give twelve threshold sentences; the answer does not
carry them all. The headline sentence is the base threshold plus the growth
bracket (the input with no evidence). Every other bracket gets one clause
each ("at 1.2% maintenance the band is $2,768–$3,052; at 0% rent escalation
$2,588–$2,853"), unless its end flips the verdict at the user's rent — then it
joins the headline with its conditions. A years bracket is quoted at the
user's stated floor beside the base, with its figures ("over 8 years, the
short end of your range, the band is $2,640–$2,910; over 10, $2,715–$2,993"),
never dismissed as "barely moves": the floor is the year they may actually
leave, and the shift it produces is the claim.

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

On a price threshold the sentence is the mirror, owned side first:

> the condo is cheaper below $412,000; too close to call between $412,000 and
> $455,000; renting is cheaper above $455,000.

The **shop-under edge** is the band edge on the buyer's side — the low edge,
$412,000 here, the highest price at which buying is still the decisive call.
It is the price the story runs at, the price the `financing:` line and
`Affordability` are quoted at, and the number the user shops with; the
crossing and the high edge are the other two clauses, never the headline.

## The prior and the second band

A `market_scenario` prior does NOT move `--break-even` (the header says so):
its drift enters the Monte Carlo only, so the prior run never replaces the
growth sweep — both run. What the prior run gives is the verdict BAND (where
the engine stops calling the user's side decisive), quoted beside the
deterministic band as the next section says. Quote the drift the assumptions
line prints for the horizon's bands, so a flat prior is never introduced as
"instead of flat prices".

With any uncertainty input on, the verdict's decisiveness is the Monte Carlo
floor, so quote BOTH bands: the deterministic tie band from `--break-even`,
and the verdict's band from the uncertainty config (prior or vols on, Monte
Carlo on):

```
uv run hde scenarios/<slug>-prior.yaml \
  --sweep rent.monthly_rent=<band low − 10%>:<band high + 10%>:11 --json
```

Read `decisive`, `prob_best` and `mc_mean_best` per row (densify the grid
around a flip before quoting an edge — a 45k-wide cell is not an edge) and
quote where `decisive` flips ("under the Laval prior the Monte Carlo calls rent decisive
up to $2,300 and buying from $2,800, neither between $2,400 and $2,700"). On a
threshold question that band IS the answer when uncertainty is on: the
deterministic edge is where the best-guess line crosses, the verdict band is
where the engine stops calling the user's side decisive — always quote both,
and lead with the verdict band's near edge ("renting is the decisive call up
to about $2,400 under the Laval prior; the best-guess crossing is $2,600").
Never drop the band you ran because the user's rent sits far from it. With only the owned side stochastic (a prior and
`investment_return_vol` 0) the engine warns `one-sided uncertainty`: the
probabilities are OVERconfident and the true toss-up zone is wider — never
"the simulation overstates the uncertainty". Cross-check the sweep's `mean
flip <key>:` line on the same input. `Affordability` and the `financing:` line are
quoted at the mean flip and at both probability edges too, not only at the
deterministic crossing: the sweep's per-point lines carry the max ratio, the
breach years and the insured tier at each grid point, so an edge that breaches
32% or crosses into an insured tier is said in the same clause that names it.
