# Board — what is open, ranked

The single home for OPEN work. `docs/roadmaps/` is the dated record of what happened;
nothing there is a to-do. If a thread is not on this board it is not being worked on.

**Ranked by one rule:** an item ranks above another when the other cannot be done, or
cannot be trusted, until it lands. Ties break toward the user seeing the difference.

Each item: **what**, *why now*, and what it unblocks. Status is `open`, `doing` or
`parked` — never a date, never a count.

---

## 1. Rate risk over the horizon — the renewal a Canadian mortgage actually has

**doing** · blocks: 3, 4 · design: `docs/specs/2026-09-03-mortgage-renewal-risk.md`

Today a mortgage carries ONE rate for the whole amortization. That is a US 30-year fixed.
A Canadian household signs a 5-year term against a 25-year amortization and re-prices four
times before the horizon ends. The engine is silent on the single largest buy-side risk in
the market it models, and every verdict it has ever produced assumes that risk away.

Build, slice 1: `mortgage_renewal_years` joins `mortgage_term_years`, which keeps its
meaning as the amortization so no shipped config changes meaning silently. The payment
re-solves over the REMAINING amortization at each renewal off a rate the user states. A
renewal is an assumptions line with its new payment and the step in dollars, because a user
who learns this at renewal instead of at decision time has been failed. Slice 2 draws the
rate from a calibrated process and arrives with item 2.

*Why now:* it is the one modelling gap that can flip a shipped verdict, and everything
below that compares risks needs a rate path to compare against.

## 2. Name the unknown that changes the verdict

**designed** · design: `docs/specs/2026-09-21-unpriced-dimensions.md` · builds after item 1

The engine says a great deal about what it does not KNOW: a figure with no source, an
estimate the assistant chose, decisiveness resting on inputs the user never stated. It says
nothing about what it cannot SEE. Renewal risk is not an input a user forgot to supply, it
is a dimension the model lacks, so no warning fires and the answer reads as complete.

Build: one line in the warnings channel, after the verdict, naming the single dimension this
run does not price whose measured size exceeds the verdict's own margin — and printing
NOTHING when nothing qualifies. The size is solved, never stressed: the engine may choose
which input moves, never by how much, so the figure is a property of the user's own config.
"Renewing 0.44 points higher flips the verdict; 1 point higher costs $14,900 against a
$6,517 margin."

*Why second:* every other item on this board changes the engine and helps the next user.
This one makes the answers already being given more honest, and it is the smallest thing
here. An instrument that refuses to be falsely confident should be able to say what it
cannot see, not only what it was not told.

## 3. The simulation's risk model, and what it does to the verdict

**open** · blocks: 4 · three defects in one object, found by audit 2026-09-21

The Monte Carlo produces `P(each option cheapest)`, the decisiveness rule reads it, and every
verdict rests on it. Three things are wrong with how it is produced. They are listed together
because they are one pass over the same file and because each one alone would mislead about
the other two.

**a. Every cost has dispersion; the asset has none.** `condo_fee_vol`,
`house_maintenance_vol`, `rent_escalation_vol`, `other_cost_vol`, `inflation_vol`,
`investment_return_vol` all exist. The home's value has no dispersion parameter at all — the
crash channel is a jump, not a spread. Meanwhile terminal equity is the largest single term in
an owned option's total: -$218,959 of $518,779 in the shipped showcase. The biggest term is
the one with no spread, and it feeds the decisiveness rule.

**b. The three options are not compared in the same future.** Within one iteration, the condo
draws its own inflation path and the house draws a separate, unrelated one; rent draws none at
all and composes with the fixed scalar. Then the three are stacked and compared
index-for-index, and the result is reported as the probability each option is cheapest. That
number reads as "the chance buying beats renting in the same future". It is not: it is three
unrelated draws compared by position. Independence also maximises the variance of the
difference, so the comparison is noisier than the world it models, and a leveraged owner's bad
income year can never coincide with their bad price year.

**c. The owner gets a tail; the renter does not.** The owned side has a discrete price-shock
channel. The rent side can only drift smoothly — no level jump, no lease-reset hazard. So the
model hands the owner a crash and the renter nothing, which biases the comparison toward
renting looking safer than it is. It bites hardest exactly where rent control is strongest: a
long-tenure Montréal or Toronto tenant paying far below market, whose real exposure is a
renoviction or lease-end reset that can double the figure in one year. The engine already
anchors the continuing-tenant protection, so it knows the protection exists; it has no way to
say that it can end.

*Why now:* (b) changes what the headline number MEANS, and nothing downstream of it can be
trusted until it is right. (a) and (c) are the two asymmetries that bias which way it points.

## 4. Which risk actually decides it

**open** · needs 1 and 3

With both channels live, decompose the verdict's variance: how much comes from renewal
rates, how much from prices, how much from the household's own inputs. Ship it as a
first-class output, not a one-off study, and state the conditions under which the verdict
reverses.

*Why now:* this is the question the product exists to answer, and the finding a reader
would cite. It is also the first thing the engine will have said that nobody else is
saying: the rent-versus-buy literature is shaped by a 30-year fixed rate, under which
renewal risk does not exist.

## 5. A household that already owns

**open** · a whole cohort, not a refinement

Every owned option starts at a purchase: a price, a down payment, a fresh mortgage. There
is no way to state an existing mortgage, its balance, the years already paid or the equity
accrued. So the person whose payment is about to jump — the first user named when the
purpose of this thing was written down — cannot describe their situation to it at all.
Their question is not rent or buy, it is stay, downsize, or sell and rent.

Build: an existing-mortgage starting state, and the owned option able to begin mid-life.
Much of the machinery exists; the renewal schedule from item 1 is most of the hard part.

*Why here and not higher:* items 1, 3 and 4 are on a clock that this one is not. That is a
scheduling reason, not a judgment that this matters less. It is the largest hole in who the
tool serves, and the ranking is worth re-arguing.

## 6. Anchors that survive their author

**open** · artifact boundary, clause 3

Twenty anchors carry a validity date and warn once it passes. Nothing in the repo can
refresh them. Every figure was fetched by hand from a session, so in January the engine
degrades to a wall of warnings and only the author can repair it. A product whose numbers
decay to unusable without one specific person is a habitat wearing a product's clothes.

Build: a refresh path in the repo, fetching from the sources the anchors already name,
with the run refusing to silently substitute.

*Why now:* the first anchors expire 2026-12-31. It is the last resident-builder assumption
left after the 2026-09-20 pass.

## 7. What the owner never gets back

**open**

The breakdown prints year-1 cash, principal and appreciation. Over the horizon the
interest/principal split and selling costs are not separated, so the owner's unrecoverable
cost is not a line anyone can read. That figure is the honest counterpart to rent.

## 8. The decision the user actually faces

**open**

Three items, one theme: rank on the figure the user cares about (`expected`, `p95`, end
wealth) rather than always the mean; let the horizon itself be uncertain ("we might move
for work"); and solve the crossing act 6 draws instead of sweeping ±35% around it.

## 9. Cuts, and what is in them

**parked** · needs a delivery decision

A user clones 57 MB to run a 2.2 MB engine; the rest is a sibling project, research data
and the build record. `v0.4.0` exists, so cuts exist. What a cut CONTAINS is undecided
because the delivery form is undecided: a repo people clone, a package, or something
hosted. Parked deliberately, not forgotten.

## 10. Smaller, real, and cheap

**open**

- The fixed-payment variable-rate mortgage, where the payment holds while the rate floats and
  the cost lands in a growing balance. The engine can express a payment that moves with the
  rate and one fixed for years, never one that stays put while the true cost does not, so the
  balance can never grow. Measured on a plausible shock, the mortgage leg is understated by
  about 1.4% structurally and 9.7% under the encoding a user would naturally reach for. The
  sharper harm is misplacement: the ladder asserts a payment step this household does not
  take, and stays silent on the balance growth they do.
- `--sweep` accepts sticker points in nominal mode instead of hand-authored real decimals.
- `--print-schema` / `--print-anchors` filter by section or key; both are multi-KB blobs.
- `--break-even` under the verdict's own criterion, not only the deterministic tie band.
- Gatineau still has no published property-tax rate, so it is the one jurisdiction that
  says `source: none`.
- Whether the 200-word quick-sense cap should rise, now that disclosures are ranked and
  never dropped.

## 11. Measure the engine again

**open**

Round 12: four question shapes on the current tip, scored, gaps folded into the engine
rather than into prose. The last round found the flat trap, worth 85% of one verdict's
margin. Run it on Opus and Sonnet, never on the steering model.

---

## Settled — do not reopen

Rate convention (sticker rates in, converted once), the three-state verdict, the short
read-back, tax treatment with FHSA and HBP, the contracted-rate base with posted as
ceiling, the artifact boundary, forward-only cleanup of public bytes. Each is recorded
with its reasoning in `docs/roadmaps/` and enforced by tests.
