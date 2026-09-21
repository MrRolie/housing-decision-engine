# Board — what is open, ranked

The single home for OPEN work. `docs/roadmaps/` is the dated record of what happened;
nothing there is a to-do. If a thread is not on this board it is not being worked on.

**Ranked by one rule:** an item ranks above another when the other cannot be done, or
cannot be trusted, until it lands. Ties break toward the user seeing the difference.

Each item: **what**, *why now*, and what it unblocks. Status is `open`, `doing` or
`parked` — never a date, never a count.

---

## 1. Rate risk over the horizon — the renewal a Canadian mortgage actually has

**slice 1 LANDED 2026-09-21** · design: `docs/specs/2026-09-03-mortgage-renewal-risk.md`

Slice 1 ships: term and amortization separated, the payment re-solving at each renewal off a
user-stated path, the affordability ratio stepping with it, and no anchored renewal rate. Left
for slice 2, with the calibrated process of §11: drawing the renewal rate rather than stating
it, which arrives with item 3.

What remains here is the distribution. A stated ladder is one scenario the household chose;
the engine anchors no forward rate and says so on every run that prices one. Drawing that rate
from a calibrated process is slice 2 and belongs with item 3, because a rate distribution is
only worth having beside a price distribution.

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

**LANDED 2026-09-21** · unblocks 4 · three defects in one object, found by audit 2026-09-21,
and a fourth found while fixing them

The Monte Carlo produces `P(each option cheapest)`, the decisiveness rule reads it, and every
verdict rests on it. Three things are wrong with how it is produced. They are listed together
because they are one pass over the same file and because each one alone would mislead about
the other two.

**a. Every cost has dispersion; the asset has none.** `condo_fee_vol`,
`house_maintenance_vol`, `rent_escalation_vol`, `other_cost_vol`, `inflation_vol`,
`investment_return_vol` all exist. The home's value has no dispersion parameter at all — the
crash channel is a jump, not a spread. Meanwhile terminal equity is the largest UNCERTAIN term
in an owned option's total: -$218,959 of $518,779 in the shipped showcase, behind only the
$480,000 paid at year 0, which is certain. The biggest unknown is the one with no spread, and
it feeds the decisiveness rule.

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

**What landed.** All three, plus one the audit missed. (b) turned out to be THREE channels
rather than one: the inflation path went first, and building (a) and (c) surfaced that the
price-crash draw and the ISQ population scenario were still drawn per option. Measured on the
shipped showcase, two Montréal properties with identical crash parameters were essentially
uncorrelated (corr −0.038) and picked the same population future on 35% of paths against 33%
by chance. Both now come from the path's shared world; the rule is that the MARKET is shared
and the PROPERTY is not. Consequences: `prob_condo_cheapest` on the showcase fell from 0.317
to 0.140 — its one-in-three was almost all spurious variance — and the verdict moved from a
`tie` produced by noise to a named `disagreement` produced by signal. Six of seven shipped
examples are byte-identical.

(a) is `simulation.value_growth_vol` and (c) is `rent.reset_hazard` plus
`rent.reset_to_monthly_rent`, both opt-in, neither anchored, each refusing to guess a figure
nobody has published. Spec and measurements:
`docs/specs/2026-09-21-one-world-simulation.md`.

**What it leaves for later, and where each one went.** The two unanchored keys mean a run that
does not set them is SILENT about price movement and about a lease ending — which is item 2's
job, not this one's. A published Canadian house-price series is the anchor item 6 would carry.
Price ↔ income correlation is still independent and needs a calibrated rho, so it is a new
item rather than a quiet default.

## 4. Which risk actually decides it

**open, UNBLOCKED** · 1 and 3 have both landed

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
- The per-year market block is written twice, once in the condo simulator and once in the
  house one. They are not identical — the house carries a second value track and a year-1
  maintenance lag — so extracting them may cost more clarity than it saves. Worth one attempt
  and a look at the result.
- Under `shock_model: normal` a shock multiplier is clipped at zero, so a large volatility can
  drive a value track to exactly $0 where it stays for the rest of the run. The schema note
  now says so; whether the engine should refuse the combination instead is open.

## 11. Measure the engine again

**open**

Round 12: four question shapes on the current tip, scored, gaps folded into the engine
rather than into prose. The last round found the flat trap, worth 85% of one verdict's
margin. Run it on Opus and Sonnet, never on the steering model.

## 12. The shipped examples barely exercise uncertainty

**open** · a gate that mostly cannot fail

Six of the seven example configs set no inflation volatility, and until this week none of
them could have detected that the renter's total was one value across five hundred paths.
Only `showcase_demographic_prior.yaml` wires a prior and a crash, so it is the only example
whose Monte Carlo block moves when the simulation changes — every other example's uncertainty
output is a constant, and a constant cannot regress. That is why the one-world defect sat
undetected: the regression surface had nothing on it.

The fix is not to bolt volatility onto every example, which would change seven published
answers for no reader's benefit. It is one example whose job is to exercise the uncertainty
machinery, and whose Monte Carlo block is pinned, so a change to the simulation has to explain
itself against a committed figure.

*Why now:* it is the cheapest of the open items and it is what makes items 3 and 4 defensible
later. A variance decomposition nobody can regress is a study, not a product feature.

## 13. What still moves independently, and shouldn't

**open** · needs calibrated figures, not defaults

Three draws remain unrelated to everything else on their path. Sharing a draw was free for the
market channels because a crash IS the market and the coupling needed no parameter. Each of
these needs an actual number, so none may ship as an invented rho.

- **Price and income.** A leveraged owner's bad income year cannot coincide with their bad
  price year: the crash draw and the income channel share nothing.
- **The renter's portfolio and the economy.** `investment_return_vol` shocks the renter's
  capital from its own draw, so the owner-vs-renter axis is still in the zero-covariance
  regime that Part A removed from the owner-vs-owner axis. A 60/40 portfolio and a housing
  market do not move independently, and the comparison the verdict rests on is between those
  two sides.
- **The demographic prior and rent.** The prior moves the owned options' value track and
  reaches the rent side not at all, although population pressure is a rent story as much as a
  price one. Whether that is a modelling gap or a disclosure gap is the first question.

*Why now:* these are the last places where "the same future" is not yet literally true, and
item 4's variance decomposition will be read as though it were. Below 12 because they change
numbers rather than claims, and below 6 because each calibration is an anchor problem first.

## 14. One key, three meanings

**open** · cheap, and it makes a schema note true

`simulation.other_cost_vol` is applied three different ways: per year per cost on the condo and
house paths, and once per path as a level shock on the rent path. One key, three semantics, and
the schema note describes only the first — so it is false for the rent side, which is the side
a reader checking the renter's exposure would look at.

Decide which meaning is right, make the key mean it everywhere, and if the rent side genuinely
needs a level shock rather than an annual one, that is a second key with its own name.

*Why now:* it is a false sentence in a surface the honesty contract governs, and the fix is an
afternoon. Ranked here rather than higher because no verdict has been shown to turn on it.

---

## Settled — do not reopen

Rate convention (sticker rates in, converted once), the three-state verdict, the short
read-back, tax treatment with FHSA and HBP, the contracted-rate base with posted as
ceiling, the artifact boundary, forward-only cleanup of public bytes. Each is recorded
with its reasoning in `docs/roadmaps/` and enforced by tests.
