# One world per path, and the two missing risks — design

**Status:** proposed, 2026-09-21. Design only, no engine code. Three parts; part A is a defect
fix and parts B and C are opt-in channels.

## 1. Why

`run_monte_carlo` produces `prob_condo_cheapest`, `prob_house_cheapest` and
`prob_rent_cheapest`. The decisiveness rule reads them. The three-state verdict names a
disagreement when they contradict the deterministic line. Every verdict this engine issues
rests on them.

They do not mean what they say. Three separate problems, one object.

**A. The options are not compared in the same future.** Inside one iteration,
`_simulate_condo_pv_once` draws its own inflation factor per year and `_simulate_house_pv_once`
draws a separate, unrelated one from the same generator. `_simulate_rent_pv_once` draws none at
all: it composes escalation with the fixed scalar `econ.inflation_rate`. The three totals are
then stacked and `np.argmin` picks a winner per index. So the reported probability is

> P( condo's total in world X < house's total in unrelated world Y < rent's total in world Z )

and it is published as the chance each option is cheapest. A reader takes that as "in the same
future". It is not.

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
not a spread. Terminal equity is the largest single term in an owned option's total — in the
shipped showcase, −$218,959 of $518,779 — so the biggest term is the one with no spread.

**C. The owner gets a tail and the renter does not.** The owned side has a discrete price-shock
channel with a hazard. The rent side can only drift smoothly. So the model hands the owner a
crash and the renter nothing, biasing the comparison toward renting looking safer. It bites
hardest where rent control is strongest: a long-tenure tenant far below market, whose real
exposure is a reset that can double their figure in one year. The engine already anchors the
continuing-tenant protection (the board rate, and the 21% pass-through to sitting tenants), so
it knows the protection exists. It has no way to say that it can end.

## 2. Part A — one world per path

**The fix.** Draw the shared economy ONCE per iteration and hand the same draw to every option.

A `PathWorld` built at the top of each iteration, holding the year-indexed factors every option
must agree on: the inflation factor per year and its `z_inf`. `_simulate_condo_pv_once`,
`_simulate_house_pv_once` and `_simulate_rent_pv_once` take it instead of drawing their own.

Rent joins the same world. Today it composes with the fixed scalar, which is not merely
independent but *deterministic*, so the renter's costs cannot move with the economy at all.

**What must NOT change.** The deterministic engine, which draws nothing. Every non-Monte-Carlo
number in every report. The absence invariant does not apply here: this changes Monte Carlo
output by design, so the obligation is to MEASURE the change on every shipped example and state
it, not to avoid it.

**What this is not.** Not a correlation model. Sharing one inflation path is not the same as
calibrating a covariance between house prices and incomes; it is the minimum required for the
argmin to mean what it says. Correlations between the price shock and the income shock stay out
of this slice and get their own item.

**The number that moves and how to report it.** Probabilities move toward the extremes as the
spurious variance comes out. Re-run every shipped example, record `prob_*` before and after,
and put the table in the commit, because a change that moves every published probability must
be legible to someone reading the history later.

## 3. Part B — dispersion on the value track

`simulation.value_growth_vol`, applied to the value track the way the cost volatilities are
applied to theirs, drawn inside the shared world so a high-inflation year and a price move are
one event rather than two.

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
market figure and escalates from there. Drawn inside the shared world.

**Why this is the honest shape.** The engine must not guess either number. A household knows
roughly what a comparable unit asks, which makes the market rent a fact the user possesses —
the same test that put tenure behind a required field. The hazard is not a fact anyone
possesses, so it stays opt-in and unanchored, and its absence is disclosed rather than filled.

**The asymmetry this closes** is worth stating in the spec because it is the point: an engine
that models a crash for the owner and nothing for the renter is not neutral between them.

## 5. What each part costs

| Part | Changes shipped numbers | New keys | Absence-invariant |
|---|---|---|---|
| A. one world | YES — every Monte Carlo probability | none | n/a by design |
| B. value dispersion | no, until a user sets the key | 1 | holds |
| C. reset hazard | no, until a user sets the keys | 2 | holds |

Part A is a defect fix and ships alone, with its measurement table. B and C are opt-in channels
and can follow without re-measuring A.

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
