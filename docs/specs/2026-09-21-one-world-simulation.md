# One world per path, and the two missing risks — design

**Status:** LANDED, 2026-09-21. All three parts are in the engine.

Part A landed first as the shared inflation path. Building parts B and C then surfaced that
Part A had been UNDER-COUNTED: two more channels were still drawn per option, and both
describe the market rather than the property. §2 now carries all three, with the measurements
that found the two the first pass missed.

## 1. Why

`run_monte_carlo` produces `prob_condo_cheapest`, `prob_house_cheapest` and
`prob_rent_cheapest`. The decisiveness rule reads them. The three-state verdict names a
disagreement when they contradict the deterministic line. Every verdict this engine issues
rests on them.

They do not mean what they say. Three separate problems, one object.

**A. The options are not compared in the same future.** Three channels, not one. Inside one
iteration, `_simulate_condo_pv_once` draws its own inflation factor per year and
`_simulate_house_pv_once` draws a separate, unrelated one from the same generator.
`_simulate_rent_pv_once` draws none at all: it composes escalation with the fixed scalar
`econ.inflation_rate`. Each owned option ALSO draws its own price-crash Bernoulli and severity,
and its own ISQ population scenario. The three totals are then stacked and `np.argmin` picks a
winner per index. So the reported probability is

> P( condo's total in world X < house's total in unrelated world Y < rent's total in world Z )

and it is published as the chance each option is cheapest. A reader takes that as "in the same
future". It is not.

The measurements, taken on `examples/showcase_demographic_prior.yaml` — two Montréal
properties wired with the SAME 3% annual hazard and the SAME 20% mean severity, under one
demographic prior:

| what should be shared | measured before the fix | what it should be |
|---|---|---|
| the crash | 325 condo crashes vs 308 house crashes over 400 paths, in unrelated years | the same years |
| the population future | condo and house picked the same ISQ scenario on 105/300 paths (35%) | every path (100%) |
| consequence | corr(condo total, house total) = **−0.038** | strongly positive |
| consequence | std(condo − house) = **68,852**, LARGER than std(condo) = 50,478 | smaller than either leg |

A correlation of −0.038 between two properties in one city is the signature of a covariance
pinned at zero by construction. And 35% against a 33% coin flip is the signature of a draw
that was never shared at all.

The direction is knowable without measuring: Var(A − B) = Var(A) + Var(B) − 2·Cov(A, B), and
independence sets the covariance to zero, which MAXIMISES the variance of the difference. So
the comparison is noisier than the world it models, probabilities are pulled toward the middle,
and `mc_floor` is reached less often than it should be. The error is conservative on
decisiveness and wrong on meaning. It also makes one real risk unrepresentable: a leveraged
owner's bad income year can never coincide with their bad price year, because the draws share
no factor.

**B. Every cost has dispersion; the asset has none.** `condo_fee_vol`, `house_maintenance_vol`,
`rent_escalation_vol`, `other_cost_vol`, `inflation_vol` and `investment_return_vol` all exist.
The home's value has no dispersion parameter. `severity_vol` is the crash channel's magnitude,
not a spread.

Stated precisely, because the loose version is wrong: in the shipped showcase's condo
breakdown the largest term by magnitude is `downpayment_pv` at $480,000, and that figure is
CERTAIN — it is the price the household pays at year 0. Terminal equity, −$218,959 of the
$518,779 total, is second in magnitude and FIRST among the terms that depend on something
nobody knows. So the engine put a spread on every cost and left the largest unknown without
one.

**C. The owner gets a tail and the renter does not.** The owned side has a discrete price-shock
channel with a hazard. The rent side can only drift smoothly. So the model hands the owner a
crash and the renter nothing, biasing the comparison toward renting looking safer. It bites
hardest where rent control is strongest: a long-tenure tenant far below market, whose real
exposure is a reset that can double their figure in one year. The engine already anchors the
continuing-tenant protection (the board rate, and the 21% pass-through to sitting tenants), so
it knows the protection exists. It has no way to say that it can end.

## 2. Part A — one world per path

**The fix.** Draw the shared world ONCE per iteration and hand the same draw to every option.

A `PathWorld` built at the top of each iteration, holding everything the options must agree on.
`_simulate_condo_pv_once`, `_simulate_house_pv_once` and `_simulate_rent_pv_once` take it
instead of drawing their own.

**The line: the market is shared, the property is not.** This is the rule that decides what
goes in the world, and it is worth stating because someone will ask why the crash is shared
while the roof is not.

| in the `PathWorld` (one per path) | still per option (one per property or household) |
|---|---|
| the inflation factor and its `z` per year | the condo's fee shock, the house's maintenance shock |
| the crash uniform and severity `z` per year | each option's own events: timing and cost |
| the ISQ population scenario and its band `z`s | the renter's escalation shock and portfolio return |
| ordinary value dispersion's `z` per year (Part B) | the tenancy's own reset hazard (Part C) |

A crash is a market event: one city, one `geography` key, one prior, the same anchored
severity. A roof is a fact about a building. A tenancy ending is a fact about a household.
The income channel stays independent too, for the reason stated below: price ↔ income needs a
calibrated correlation, and independence is the honest default until there is one.

**Shared state, per-option parameters.** The world holds the crash uniform and severity `z`;
each option fires iff `u < min(own_hazard × own_tilt, 1)` and applies its OWN `severity_mean`
and `severity_vol` to the shared `z`. Equal EFFECTIVE hazards — the product, after the prior's
per-dwelling tilt — give identical crash years; a higher effective hazard's crash years are a
SUPERSET of a lower one's. Severities differ freely: the same `z` scaled by each option's own
mean and vol. That coupling is comonotone, takes no
parameter, and invents no correlation — which matters, because a correlation between two
markets would need calibrating and this is one market.

The world likewise holds the ISQ scenario and one `z` per horizon band; each option looks its
own rows up in it, so the per-dwelling `drawdown_weight_tilt` lookup is unchanged.

Rent joins the same world. Before this it composed with the fixed scalar, which is not merely
independent but *deterministic*, so the renter's costs could not move with the economy at all.

**What must NOT change.** The deterministic engine, which draws nothing. Every non-Monte-Carlo
number in every report. The absence invariant does not apply here: this changes Monte Carlo
output by design, so the obligation is to MEASURE the change on every shipped example and state
it, not to avoid it.

**What this is not.** Not a correlation model. Sharing a draw is not the same as calibrating a
covariance between house prices and incomes; it is the minimum required for the argmin to mean
what it says. Correlations between the price shock and the income shock stay out of this slice
and get their own item.

**The number that moves and how to report it.** Probabilities move toward the extremes as the
spurious variance comes out. Re-run every shipped example, record `prob_*` before and after,
and put the table in the commit, because a change that moves every published probability must
be legible to someone reading the history later.

**What it actually did.** Six of seven shipped examples are byte-identical, because they wire
neither a prior nor a crash. The showcase, which wires both:

| | before | after |
|---|---|---|
| `prob_condo_cheapest` | 0.3166 | **0.1398** |
| `prob_house_cheapest` | 0.3636 | 0.4198 |
| `prob_rent_cheapest` | 0.3198 | 0.4404 |
| corr(condo, house) | −0.038 | **0.991** |
| std(condo − house) | 68,852 | **7,721** |
| `verdict.state` | `tie` | `disagreement` |

The condo's one-in-three chance of being cheapest was almost entirely spurious variance. Priced
in the same market as the house, which is structurally cheaper here by about $6,000 of mean PV,
the condo wins one run in seven rather than one in three. The old figure was noise wearing the
clothes of a probability.

The verdict state moving from `tie` to `disagreement` is the same story. Before, all three
probabilities sat near a third because the comparison was mostly noise, so no option cleared
the decisiveness floor and the rule read that as a tie. Now the probabilities carry signal, and
they contradict the central case — which is exactly the situation the third verdict state
exists to name. The engine went from a tie produced by noise to a disagreement produced by
signal, and says so.

## 3. Part B — dispersion on the value track

`simulation.value_growth_vol`, applied to the value track the way the cost volatilities are
applied to theirs, from a `z` drawn in the shared world.

**One draw, not one per option.** The spec's first pass said "drawn inside the shared world"
and left it there, which reads as though the cost volatilities were the pattern to copy. They
are not: `condo_fee_vol` and `house_maintenance_vol` are different cost items on different
buildings and belong apart. The home's VALUE is one asset class in one market, and the key is
one sim-level parameter, so a per-option draw would have reintroduced the Part A defect in a
new channel — condo and house prices moving independently in the same city. The z is the
world's, and both properties take the same multiplier.

Applied to the same tracks the crash applies to, at the same point in the year: ordinary
variation first, then the rare drawdown on the value the market had reached. Mean-preserving
under the lognormal model, so switching it on widens the distribution without moving its
centre — a test pins that, because an uncertainty input that shifted the mean would be a
forecast change in disguise.

**No default, and no anchor in this slice.** Absent, it is zero and nothing changes, so the
absence invariant holds for every existing config. Inventing a figure would breach the honesty
contract, and anchoring one properly means a published Canadian house-price series with a
stated window — that is its own item, and the disclosure line of
`2026-09-21-unpriced-dimensions.md` is what covers the gap until it lands.

This is deliberate: the mechanism ships first, the number ships when it can be cited.

## 4. Part C — a lease-reset hazard on the rent side

The mirror of the owned side's price shock: a hazard per year that the tenancy ends and rent
resets to a stated market level.

`rent.reset_hazard` (annual probability) and `rent.reset_to_monthly_rent` (the market figure it
resets to), both opt-in, neither defaulted. When the reset fires in a path, rent steps to the
market track and escalates from there.

**Drawn per path but NOT in the shared world** — this spec's first draft said "inside the
shared world", which contradicts §2's table and is wrong for a reason worth keeping: a tenancy
ending is a HOUSEHOLD event, not a market one. The crash is shared because one city has one
housing market; a lease does not end because the market moved. It is drawn once per path in
`run_monte_carlo` rather than inside the rent simulator, though, because the PV leg and the
AFFORDABILITY leg must price the same tenancy — two draws would give one path two different
tenancies, and the affordability report would contradict the verdict.

**Why this is the honest shape.** The engine must not guess either number. A household knows
roughly what a comparable unit asks, which makes the market rent a fact the user possesses —
the same test that put tenure behind a required field. The hazard is not a fact anyone
possesses, so it stays opt-in and unanchored, and its absence is disclosed rather than filled.

**Both keys or neither, and both refusals matter.** A hazard with no market figure has nothing
to reset to; that refusal is obvious. The reverse refusal is the one worth defending: a market
rent with a zero hazard would be a figure the user took the trouble to supply that the engine
would silently ignore. Under the honesty contract that is the worse failure of the two, because
the user would believe their exposure had been priced. So both raise, and each message says
what to do.

**The reset lands on the market's rent for that year, not today's.** Two tracks escalate side
by side — what this household pays, and what a comparable unit asks — and the tenant moves from
the first to the second in the year the tenancy ends. A reset in year 8 lands on year 8's
asking rent. Stepping to today's figure eight years later would understate the exposure, and
the whole point of the channel is that the exposure is real. The degenerate case is the
cleanest statement of the mechanism: reset to your own rent, at the same rate, and it costs
nothing for any reset year.

**The two tracks grow at DIFFERENT rates, and the engine's own anchor is the reason.**
`rent.rent_escalation_rate` defaults to the FP Canada shelter projection, 1.0% real, and its
rationale records that a Québec continuing tenant renews at the TAL base rate — the three-year
CPI average, ≈ 0.0% real — because landlords pass through only about 21% of market movements at
renewal. So the household this channel exists for correctly states their own escalation near
zero. Under one shared rate that would freeze the MARKET too, and the engine would price a
reset to a rent that never grew.

`rent.reset_market_escalation_rate` carries the market's own rate, defaulting to that same
anchor, which is a cited market figure rather than the user's protected one or an invention.
Measured on a 25-year Montréal run at 4,000 paths: sharing the rate understated the renter's
mean present value by $23,105 and read P(condo cheapest) as 0.715 instead of 0.742. The channel
built to show a tenant's exposure was erasing it.

**The asymmetry this closes** is worth stating in the spec because it is the point: an engine
that models a crash for the owner and nothing for the renter is not neutral between them.

## 5. What each part costs

| Part | Changes shipped numbers | New keys | Absence-invariant |
|---|---|---|---|
| A. one world | YES — the showcase only; six of seven examples byte-identical | none | n/a by design |
| B. value dispersion | no, until a user sets the key | 1 | holds |
| C. reset hazard | no, until a user sets the keys | 3 | holds |

Part C's third key is `reset_market_escalation_rate`, which has a default and so is accepted
only alongside the other two. The reset also reaches the AFFORDABILITY channel: that report
compares an undiscounted cost array against a per-path income, so the array has to know the
path's reset year or it reports a ratio the verdict does not share. Without that threading it
said `prob_rent_exceeds: 0.0` on a config whose reset pushed the burden from 23.8% to 70.3% of
income on 998 of 1,000 paths.

Part A shipped first as the inflation path alone. The crash and the population scenario landed
with B and C once building them revealed they were still per-option.

## 6. Test plan

- **Same-world identity.** With every volatility at zero, one world and three worlds give
  identical results; the fix must be invisible when nothing is random.
- **The variance claim, measured.** On a fixed seed, the standard deviation of (condo total −
  rent total) must FALL when the inflation path is shared, because the covariance term stops
  being zero. Pin the direction, not the figure.
- **Rent moves with the economy.** With `inflation_vol` on and every other volatility off, the
  renter's total must vary across paths. Today it cannot, and a test that fails before the fix
  and passes after is the cleanest statement of what was wrong.
- **Deterministic untouched.** Every deterministic figure in every shipped example is
  byte-identical.
- **B and C absent.** Every shipped example, which sets neither, is byte-identical including
  Monte Carlo, because both default to off.
- **C fires.** With a hazard of 1.0 the reset happens in year 1 on every path; with 0.0 it never
  fires; the post-reset series escalates from the market figure.

## 7. Smallest shippable slice

Part A alone: the shared world, the three call sites, the four tests, and the before/after
table. It fixes a defect in the number the verdict rests on and adds no user-facing surface.

## 8. What this slice deliberately leaves open

Named here so the next reader does not mistake silence for completeness.

**No anchor for `value_growth_vol`.** The mechanism ships; the number does not. A defensible
figure needs a published Canadian house-price series with a stated window, and until it exists
every run that does not set the key prices the home's value with no everyday dispersion while
every cost in the model has a spread. That gap is a DISCLOSURE problem, and the disclosure
belongs to `2026-09-21-unpriced-dimensions.md`, not here — this slice must not print a number
it cannot source.

**No anchor for `reset_hazard`.** Same shape. Nobody possesses the probability that a tenancy
ends, so the engine asks rather than guesses.

**Price ↔ income stays independent.** A leveraged owner's bad income year still cannot coincide
with their bad price year. Sharing a draw was free; this needs a calibrated correlation, and it
gets its own item rather than a made-up rho.

**Events stay per option.** A roof and an assessment are facts about buildings. If a future
item wants a market-wide construction-cost shock, that is a new channel in the world, not a
re-reading of these.
