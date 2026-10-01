# Threshold seed above the line, and affordability where no crossing is found (2026-10-01)

**Status:** ruled. S1 builds the operator's ruling; S2 is separate engine scope, see §4.
**Anchored by:** board round 12, items 2 and 3, and the convergence note beneath them.

## 1. The ruling

On 2026-09-22 the operator ruled on the card "Threshold seed": seed ABOVE the insurance line,
not below. The board had recorded it as 2026-09-21, the day the card was raised, and this
change corrects that. A threshold run's
base block has to describe the insured purchase a household short of 20% would actually make,
with the premium, its tax and the higher loan-to-value all present. The operator was told this
is a one-line change to the lane doc with no new prose.

## 2. What was measured (origin/main 83ea552, before any change)

All on `examples/first_time_buyer_montreal.yaml` with `condo.initial_value` changed, and
`--no-monte-carlo`. The household has $60,000 of cash, a $15,000 HBP withdrawal, $2,889 of
FHSA refunds and $95,000 of income over 10 years.

- **The 20%-down ceiling.** At the shipped $450,000 the `financing:` line reads `this cash covers
  20% down up to a price of $361,762 (purchase_costs $5,537 at that price; above it the mortgage
  is insured)`.
- **Below the line, as both lane docs say today.** At a $330,000 seed the block reads
  `mortgage_insurance: auto → none required (77.93% ≤ 80%)`, and the qualifying-rate warning
  reads `Your loan is uninsured, so that rate is OSFI's`. `--break-even condo.initial_value`
  crosses at 468,398, with the band 438,607 to 503,436. At 468,398 the loan is insured:
  `85.13% LTV → 3.10% tier = $12,361 financed; premium tax 9% (QC) = $1,113 cash`. The base
  block therefore describes the one structure this household will not have in the band that
  matters: no premium, no premium tax, and OSFI as the rate's authority.
- **Above the line.** At $370,000, the next $10,000 above $361,762, the block reads
  `insured: 80.68% LTV → 2.80% tier = $8,359 financed; premium tax 9% (QC) = $752 cash → loan
  $306,882 = 82.94% LTV`, and the warning reads `Your loan is insured, so that rate is the
  federal government's`. At $380,000 the clause is `81.24% LTV → 2.80% tier = $8,644 financed;
  … $778 cash`. The crossing, the band and the affordability at them are the same at $330,000
  and $370,000, because the scan re-derives the tier at every point: 468,398; 438,607 to
  503,436; condo 37.7% (7 yr(s) over) at the crossing.
- **No crossing.** At the $380,000 seed, `--break-even condo.initial_value=250000:420000`
  prints `no crossing between 250,000 and 420,000: condo is cheaper at both ends — widen with
  --break-even condo.initial_value=250000:590000` and no affordability at all. The JSON
  `no_crossing` record holds `lo, hi, cheaper, narrows_toward, at_floor, widen` and nothing on
  income. `--sweep condo.initial_value=250000:420000:3` on the same config finds condo 20.9%
  (none over) at 250,000 and 34.0% (years 1, 2 and 3 over the 32% threshold) at 420,000. The
  break-even withholds both figures. Beside `--sweep rent.monthly_rent=1500,1850`, the 1,850
  `across` row has no crossing and prints no affordability, while the 1,500 row crosses and
  prints it.

## 3. S1, the seed (lane docs only)

The placeholder price for a price threshold is the first round figure ABOVE the price the
`financing:` line names in `this cash covers 20% down up to a price of $X`: the next $10,000.
The assistant runs once to read X, as the lanes already say, and the seed stays declared
`assistant` in `sources:`.

- **The user's range lies wholly below X.** Their cash covers 20% throughout, so the seed goes
  inside their range, and the block's `none required` is then true. The $330,000 run above is
  that block.
- **A step above X passes the price the engine refuses.** The engine has one refusal here, and
  no purchase-price cap. The refusal is the `mortgage_insurance.max_ltv` anchor, 95% of the loan
  before the premium. Measured on the same file with the `tax:` block removed and
  `cash_available` / `invested_down_payment` at $2,400: the cash covers 20% only up to $1,951. At
  $2,000 the run prices `80.70% LTV → 2.80% tier`, and at $6,000 `94.17% LTV → 4.00% tier`. At
  $7,000 and at $10,000 the run prints `Configuration error: condo: loan-to-value 96.50% exceeds
  the maximum insurable 95.00% — no insurer writes this loan. Raise the down payment or lower
  the price` (95.13% at $7,000) and exits 1, with no report. So an overshooting seed is never
  priced silently. The lane sentence says to take a finer step when the engine refuses the
  seed that way. A $10,000 step overshoots only when the cash left after purchase costs is a few
  hundred dollars. When the cash does not cover the purchase costs at all ($1,900 here), every
  price is refused (`cash_available $1,900 does not cover purchase_costs $2,050 — nothing is left
  for a down payment`). No X is printed and no seed rule applies. That refusal predates this
  change and is out of scope.
- **Sentences that change with the rule.** `quick-sense.md` ("Seed the config's price a step
  BELOW …, so the scan starts where their cash still covers 20% and the engine re-derives the
  premium tier above it") and `threshold-lane.md` ("a first guess a step BELOW the price their
  cash supports at 20% down"). `grep -n -i "seed\|below" gates.md` finds no sentence that reasons
  about a seed below the line. Line 102 is about sweep brackets ("one step below" the user's
  value), line 172 is about a tenant's rent below market, and lines 214–215 give the coherence
  note's direction about the seed, which holds on either side. `SKILL.md` and `answer-template.md` mention the seed only as a placeholder that is
  never the verdict, which still holds.

## 4. S2, affordability at both searched ends (engine; separate scope)

**This is engine work beyond the one-line lane change the operator was shown.** The steering
seat decided it under board item 3, which says the defect is "not a skill defect". Both lanes
withhold the price sweep in this shape, so the disclosure cannot depend on the assistant
running one. The seed flip does not close item 3. At the $380,000 seed above, the no-crossing
branch still prints no affordability.

When a break-even finds no crossing and an `income` block exists, the engine prices
affordability at both ends it searched, `no_crossing.lo` and `no_crossing.hi`. Both are grid
points the loader accepted, because `searched` is built from accepted runs only. So both ends
were priced by construction:

- `--break-even condo.monthly_fee=0:200` at a $600,000 seed takes the `at_floor` branch
  (`no crossing down to 0 on condo.monthly_fee`), and its fee of 0 is priced.
- `--break-even condo.initial_value=0:300000` refuses 3 points (`… nets a down payment of
  $75,889, above the price $0`). It searches 112,500–300,000 and takes the plain branch.

The at_floor variant therefore prints at both of its ends too.

- **Text** (the `format_break_even` block), under the no-crossing sentence, in the crossing
  branch's leaf shape:
  `affordability at both searched ends (highest cost/income ratio; years above the 32% threshold):`,
  then `rent 23.4% (0 yr(s) over) at every quoted point`, `at the low end 250,000: condo …`,
  `at the high end 420,000: condo …`.
- **Read-back and `across` rows**: the same phrases on one line, through the same clause
  function the crossing branch uses. The read-back header's `affordability = …` and
  `at every quoted point` fold now count the no-crossing points too.
- **JSON**: `no_crossing.affordability` = `{threshold, lo, hi}`. `lo` and `hi` are each the
  per-option `{max_ratio, years_exceeding}` mapping that the crossing branch's `value` and
  `tie_band` entries hold. Without an `income` block it is `null`, the convention the crossing
  branch uses, and nothing new prints.
- **One home**: the per-point pricing (`load_at` → `compute_deterministic` → `affordability_of`)
  and the point formatter are shared with the crossing branch, not copied. The record is attached
  in `solve_break_even`. `solve_crossings` and `no_crossing_record` stay pure, because the story's
  act 6 and the reversal register call the solver directly.

Docs updated: `API_CONTRACT.md` (the `break_evens` row and the read-back line),
`ARCHITECTURE.md` (the no-crossing paragraph and read-back item 9), and both lane docs, so the
assistant quotes the new line and no sentence implies the no-crossing affordability is missing.

**Measured after the change**, on the same runs:

- `--break-even condo.initial_value=250000:420000` at the $380,000 seed prints `at the low end
  250,000: condo 20.9% (0 yr(s) over)` and `at the high end 420,000: condo 34.0% (3 yr(s)
  over)`, with `rent 23.4% (0 yr(s) over) at every quoted point`. These are the figures the
  sweep found at those two prices.
- The $600,000 fee run prints `at the low end 0: condo 42.7% (10 yr(s) over)` and `at the high
  end 200: condo 45.3% (10 yr(s) over)`.
- The same household with the `income` block removed (and `tax.marginal_rate` typed, since
  nothing is left to resolve it from) serializes `"affordability": null`, and no line containing
  `affordab` prints.
- The seven shipped examples' `--json` is byte-identical to origin/main's. None of them runs
  a break-even.

## 5. Out of scope

- A purchase-price cap on insured mortgages. The engine anchors none, and adding one would be
  a registry change with its own source.
- The refusal when cash does not cover the purchase costs (§3).
- The rest of board round 12 (items 4–9).
- Whether a threshold run should print a single-price block at all. That was the other branch
  of the card, and the operator did not take it.
