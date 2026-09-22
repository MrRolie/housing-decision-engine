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

**slice 1 LANDED 2026-09-21** · design: `docs/specs/2026-09-21-unpriced-dimensions.md`

Slice 1 ships the channel itself, on the smallest dimension that needs nothing from the
renewal ladder (§14, §16): OSFI's minimum qualifying rate, anchored as its two published
legs, loaded onto the user's own contract rate on the as-quoted axis, and the affordability
ratio recomputed at it beside the ratio the run prices. The line names the gap the registry
itself records — this engine's numerator is broader than a lender's gross debt service — and
never says the household would fail to qualify, because the engine is not a lender and does
not have the lender's numerator. It also names WHICH authority sets the test for this loan:
OSFI's rule governs uninsured mortgages, and on an insured one the same two figures are the
federal government's, so a citation to one is not a citation to the other. Silence is real
and tested: no income block, no financed option, or no rate on the quoted axis, and nothing
prints.

**Corrected 2026-09-21, and the correction is the interesting part.** The line stated an
ORIGINATION test in the engine's own voice with a citation attached. On a run that also
prices a renewal that reads as a standing verdict on the household, and since 2024-11-21 it
is not one — OSFI no longer prescribes the rate for an uninsured straight switch at renewal.
The line now names which transaction its figures describe, in 39 words, and refuses rather
than explains — **and it is 43% longer for it: 89 words to 128 on a run with a ladder**, a
cost recorded here rather than argued away, because the households that meet the clause are
exactly the ones with a renewal to worry about: an exemption from OSFI's prescribed rate is not an exemption from being
assessed, and the engine cannot see which case the household is in, because a straight
switch is defined by the amount carried over and the amortization kept, which no config
states. The insured branch reports an absent source instead of borrowing the other branch's
relief: this engine's insured loan is high-ratio, and the federal removal of 2024-12-16 is
written for a prior low-ratio loan. **THE LINE CITES, THE ANCHORS RECITE** — the effective
dates, the three conditions and the B-20 mechanism all left the line and are stored verbatim
on the two anchors, one `--print-anchors` away. The first draft of the clause took the line
to 205 words, longer than a version already rejected for length; that is where the rule came
from. **The 89→128 growth is still a finding against this line, not a settled cost.** §4 and
§5 of the spec already warn that a line whose varying part is one figure inside a fixed
sentence drifts toward boilerplate and takes the genuinely run-specific warnings down with
it, and this line's invariant fraction is now the highest on the board. The rule that
produced the cut — the line cites, the anchors recite — may have one more level to run: the
fixed scaffolding belongs in the anchors and only the figures belong in the line.

Left for slice 2: the renewal dimension in state two, which needs item 1's ladder; then the
tenure field and its refusal (§10), which is independent of both and is the largest single
gain in who the tool serves honestly. §15's straight-switch exemption is no longer waiting on
renewal for its SCOPE clause — that shipped above — but the exemption as a priced effect on
the affordability line still rides item 1's ladder.

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

**doing** · designed 2026-09-22, all forks ruled · spec `docs/specs/2026-09-22-which-risk-decides-it.md`

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

**One piece of it measured, 2026-09-21, because a measurement beats an adjective.** For an
existing owner the alternative is not "rent instead of buying", it is SELL AND THEN RENT — and
selling costs money on the day they do it. The engine charges `selling_cost_rate` once, at the
HORIZON, on the owned side only (`_financing_pv`: `equity_N = value_N * (1 - selling_cost_rate)
- balance_N`). There is no field anywhere for a cost the RENT option incurs at year 0: `rent`
has no `purchase_costs` sibling, and an event is refused below year 1.

On a Laval bungalow worth $610,000 against a $212,000 balance, the 5% cost of selling is
$30,500. Charged as a year-1 event — the only workaround the schema allows, and nothing tells a
user to build it — the margin moves from $85,669 to $114,939. That is **34% of the margin the
engine reports without it**, on a verdict it reports as decisive.

A first correction was tried and was WRONG, which is worth recording: crediting the renter with
gross equity rather than net proceeds moves the margin by only $2,939, because the renter's
capital is charged at year 0 and credited at the horizon and therefore nearly PV-neutral by
construction. The gap is not in the capital figure. It is that the engine prices the cost of
BECOMING an owner and has no way to price the cost of CEASING to be one.

*Why here and not higher:* items 1, 3 and 4 are on a clock that this one is not. That is a
scheduling reason, not a judgment that this matters less. It is the largest hole in who the
tool serves, and the ranking is worth re-arguing.

## 6. Anchors that survive their author

**LANDED 2026-09-22** · artifact boundary, clause 3 · design:
`docs/specs/2026-09-22-anchor-refresh-path.md`

Twenty anchors carry a validity date and warn once it passes. Nothing in the repo could
refresh them. Every figure was fetched by hand from a session, so in January the engine
degrades to a wall of warnings and only the author can repair it. A product whose numbers
decay to unusable without one specific person is a habitat wearing a product's clothes.

**What landed.** Not nineteen new numbers — **zero of the nineteen values change today**,
and that is the finding, not a shortfall. Canadian tax parameters for a year are published
once the indexation factor is known: November for the CRA and Finances Québec, December
for the T4032 tables. Checked 2026-09-21 against every primary source: the CRA indexation
page prints no 2027 column, the rates page reads "For income earned in: 2026", T4032-ON is
the 2025-12-17 edition, both Finances Québec 2027 parameter PDFs are 404 and
TP-1015.F-V(2027-01) is 410, and the 2027 TFSA limit is a press projection rather than the
CRA's figure. Computing an indexation factor here would be an estimate wearing a citation's
clothes. The one exception is Québec's insurance-premium tax: Bill 99 is enacted and the
2027 rate is 9.975%, which the registry has carried in the anchor's band and rationale
since 2026-09-03. It does not change the value, because 9% is still correct for a premium
paid on or before 2026-12-31 — a known edit on a known date, not a fetch.

What DID land is the path. `Anchor.refresh_group` names the publishing RELEASE behind each
figure, and `__post_init__` now refuses a dated anchor without one, or without `quoted` and
`unit` — a promise that a figure will be replaced is unkeepable if nobody can say who
publishes the replacement or how this source printed it.

Grouping them exposed a defect that would have made the whole thing ornamental: five
releases shared the constant `_TAX_RETRIEVED` and four shared `_TAX_YEAR_END`, with
`as_of="2026"` a literal inside a generator that runs for all three jurisdictions. The CRA
publishes in November and Revenu Québec in December, so a refresher updating the federal
figures had to move a constant that also stamped Québec's and Ontario's — leaving the
registry asserting Québec's 2026 brackets were the 2027 brackets, read on a day nobody read
them. No guard could catch it: each release stayed internally coherent while three of them
lied. `_RELEASE_EDITION` now holds one `(as_of, retrieved_on, valid_until)` row per release
and every grouped anchor spreads `**_edition(group, dated=…)`, so a refresh edits exactly
the row it read; `_TAX_YEAR_END` is deleted and `_TAX_RETRIEVED` survives only for the seven
entries in no release at all. The refactor moved no figure, date or citation — all 117
anchor records are byte-identical before and after, which is how it was checked. It is the
repo's own "sweep the siblings of any single-instance fix", one level up.

`REFRESH_SOURCES` holds six
release records (publisher, the edition to look for, where it appears, **when it was last
checked and what was found**) and derives its members from the anchors, so membership has
one home. The check record is what stops a lapsing figure reading as neglect: "the CRA
indexation page prints 2023–2026 and no 2027 column, checked 2026-09-21" is completed work.
`hde --refresh-plan` prints the work order — grouped by release, ranked by how soon a
figure lapses, with every member's full anchor record, the resolved URL, the check, and the
steps of a correct refresh — and exits 3 once anything has actually lapsed, 0 while a
figure is merely approaching its date.

Verification is the half that matters: `tests/test_anchor_refresh.py` turns red on a value
retyped with its citation left stale, a vintage moved to the new year with `valid_until`
left behind, and one sibling refreshed while the rest of its release stays at the old
edition. Each was run against its own mutation first. The sibling check is honest about its
reach — `test_tax_anchors.py`'s literal pins already catch a partial edit today, and the
relational check is what survives those literals being updated on the 2027 pass, which a
mutation demonstrates: with the literals updated exactly as a refresher must, it is the
only test that fires.

*What it leaves:* nothing in this repo RUNS the plan on a schedule, because the repo has no
CI at all. The alarms that fire unprompted are unchanged in kind — the suite reddens the
day after a figure lapses, and a run that used one warns. What changed is that both now
have a work order behind them that a stranger can execute. Standing up a scheduler is a
delivery decision and belongs with item 9.

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

**LANDED 2026-09-21** · a gate that mostly could not fail

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

**What landed.** One config, and it is a FIXTURE rather than an eighth example:
`tests/fixtures/uncertainty_surface.yaml`, pinned by
`tests/fixtures/uncertainty_surface_mc_golden.json` and read by
`tests/test_uncertainty_surface.py`. It wires every stochastic channel the engine has —
inflation vol and its four correlations, the four cost vols, return vol, the shared value
dispersion, a price shock on both owned options, the demographic prior, the lease-reset pair
and a pay-drop event — across a cash condo, a leveraged house and a sitting tenant, in one
world, in nominal mode (`inflation_vol` is inert on escalation in real mode, so a real-mode
fixture would wire the month's biggest defect half dead).

It sits outside `examples/` for two reasons and the second decides it. `examples/` is a
reading-order walkthrough and these figures are chosen for mechanism coverage, not because
a household has them. And `test_no_shipped_example_wires_either_channel` asserts that EVERY
file in `examples/` reads `value_growth_vol` as 0 and wires no lease reset — the absence
invariant checked by RUNNING the shipped configs. Landing a fully-stochastic config there
would have forced that assertion down to "every example that existed before", which is a
gate with no failure state: trading one such gate for another. Outside `examples/`, it keeps
its full form and the seven published answers are byte-identical.

The pin was proved able to fail before it was trusted: reverting the shared crash draw in
`monte_carlo._apply_price_shock` — the exact defect fixed that morning — moves
P(house cheapest) from 0.0905 to 0.172 and P(condo cheapest) from 0.5705 to 0.4915, and the
failure names all 21 moved figures with pinned, observed and delta, plus which side of the
engine each moved figure points at. The companion tests perturb each channel one at a time,
SCALING it rather than switching it off so the draw count is unchanged, and require it to
move the options it belongs to and leave the others bit-identical — because a channel that
went inert would otherwise sit on this surface as a constant wearing a volatility's name,
which is this same item one level down.

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

**LANDED 2026-09-21**

`simulation.other_cost_vol` was applied two ways, not three: the condo and house paths ran the
same code (one shock per year per cost line, compounding on the carried amount), and the rent
path ran one level shock per path on the whole series. Measured over 40,000 paths with the key
the only stochastic input and an identical $10,000/yr line on each option, the owned lines
carried a level spread of `vol·√t` — 0.25 at 25 years against the renter's flat 0.05 — and the
renter's PV dispersion from the channel ran 3.0x narrower. The schema note said "annual vol of
other recurring costs", true of the owned side only.

The owned meaning is the right one and the renter now shares it: an assessor re-assesses from
last year's assessment and an insurer re-prices from last year's premium, so the innovation is
annual and the level is sticky. A one-off level shock is not that process — it is uncertainty
about today's figure, which is a `--sweep`. No second key, and no second correlation key:
`corr_inflation_other` is named for the cost CATEGORY, as `corr_inflation_event_cost` already
is, and it now governs the renter's lines too. The note states the compounding, because "annual
vol" alone would have been the next false sentence.

No shipped example moved: `other_cost_vol` is set only in `advanced_config.yaml`, which has no
rent block, and no example gives the renter `other_recurring_costs` — which is item 12's point,
and why this cost nothing to land.

## 15. The other-cost channel's siblings

**open** · found by the item-14 sweep, not yet priced

Three findings, none of which item 14 was allowed to touch without moving published answers for
a reason outside its scope:

- Every OWNED cost channel consumes its draws while switched off. `_correlated_z` always calls
  `rng.normal()`, and `_shock_multiplier(0, …)` then discards the result, so a 10-year condo
  path spends 10 draws on the fee at `condo_fee_vol: 0` and a further 10 per other-cost line at
  `other_cost_vol: 0` (measured: 0 / 1 / 2 lines → 10 / 20 / 30 draws). A channel that consumes
  a draw while off is exactly what `test_no_channel_consumes_a_draw_while_switched_off` exists
  to forbid; these predate that test and are baked into every shipped example's numbers, so
  fixing them moves published answers. The rent side does NOT leak — item 14 kept its gate.
- `condo_fee_vol` has item 14's shape and item 14's old note: `fee_amount` is carried, so the
  shock compounds. Measured at 0.05 over 25 years with the knob the only stochastic input, the
  fee line's PV sd runs 20.8% of its base (`other_cost_vol` runs 15.0% on the same test; the
  fee is higher because the reserve contribution rides it). The note says only "annual vol of
  condo fees".
- `house_maintenance_vol` has a DIFFERENT shape — `maint_t` is rebuilt from `house_value` each
  year, so its shock is iid on the level and does not accumulate: 1.0% on the same test, twenty
  times narrower than the fee knob at the same typed figure. Two cost knobs, two processes, and
  nothing on any surface says which is which.

*Why now:* not urgent — no verdict is known to turn on any of them — but the second and third
are the same false-sentence class item 14 just closed, and the first is a live draw-order leak.

---

## 16. A partial `sources:` block reads as diligence

**open** · found by round 12, measured · the honesty machinery's own blind spot

`sources:` classes every input as the user's, the assistant's, or an anchor's, and the
read-back prints the classes. Declaring a key is OPTIONAL, and the party the rule polices
decides whether to declare. Omit a line and the key lands under `unattributed:` — which is
where the STRUCTURAL keys live, the ones nobody would think to declare. A run that states an
income the assistant invented and never classes it prints that income beside `years=10` and
`province='QC'`, in one comma-separated list, and exits 0 with nothing further said.

So an omission is CHEAPER than a declaration for anyone who would rather not own a figure,
which inverts what the mechanism is for. A config with NO block at all is handled well — it
says `sources: none declared` plainly. The hole is the PARTIAL block, which reads as diligence.

The fix is not obvious and is the reason this is an item rather than a patch. Candidates: a
third class distinguishing "nobody declares this" from "the party who should have did not"; a
warning when a partial block omits a key the verdict reads; or a rule that a declared block
must be complete. The last is the strictest and would refuse configs that are honest today.

*Why now:* this defeats, quietly, the mechanism the whole honesty contract rests on, and it
was found only because someone ran the engine as a user rather than reading it. It also
retires a claim in `docs/specs/2026-09-21-unpriced-dimensions.md` §10 that the shortcut was
already caught; that paragraph is corrected with the measurement.

## 17. The renter cannot be charged anything on day one

**open** · structural, measured on the existing-owner cohort

`rent` has no year-0 cost channel at all. There is no `purchase_costs` sibling, and an event is
refused below year 1 (`Event '...' has expected_year < 1`). So moving costs on the day of the
move, a lease-break penalty, and the selling cost of a home being left are all inexpressible.

Measured on a household that already owns, which is where it bites hardest. A Laval bungalow
worth $610,000 against a $212,000 balance: the 5% cost of selling to become a renter is
$30,500, and it has no home. Charged through the only workaround the schema allows — a year-1
event, which also discounts it to $28,993 — the margin moves from $31,776 to $58,180. The
engine tells the household staying wins by $31,776 when on their own numbers it is $58,180,
nearly double.

A correction that does NOT work, recorded because it is the intuitive one and it makes things
worse: shrinking `rent.invested_down_payment` from gross equity to net proceeds expresses only
$2,598 of the $30,500, because the renter's capital is charged at year 0 and credited at the
horizon and is therefore near PV-neutral by construction. Applied ALONE it moves the answer
FURTHER from the truth than doing nothing. Only a cost line carries the full weight, and there
is no cost line.

Shape of the fix: a `rent.purchase_costs` sibling, or admitting `expected_year: 0`. The
refusal message names its constraint precisely, so the year-1 floor is deliberate rather than
accidental — read why before relaxing it.

*Why now:* it is the smallest piece of item 5 that can ship without the existing-owner frame,
and it is the largest single numerical distortion round 12 found.

## Item 4's control, and why the renewal finding is stronger than stated (2026-09-21)

Measured by the reversal solver on `tests/fixtures/uncertainty_surface.yaml`, and not
anticipated by the design: **`mortgage_rate` reverses no winner anywhere in [1%, 10%]**. The
rate a household shops for, negotiates, and is told to compare lenders on cannot change which
option wins, across the entire plausible bracket. Its runner-up boundary is at 1.9171% and its
majority boundary at 1.5999%, both outside any real quote.

The renewal rate flips the verdict at **1.6052%**, inside the bracket the engine already uses
for a mortgage rate.

The reason is structural: the opening term runs five of twenty-five years. The rate you can see
is attached to a fifth of the debt; the rate nobody can see arrives for the other four fifths,
and this engine anchors nothing for it and draws no distribution over it. So the finding is not
"renewal risk is unpriced" — it is that **the priceable rate cannot decide this and the
unpriceable one does**, and the rate-shopping advice households actually receive is aimed at the
term that cannot move the answer. `mortgage_rate` is the control that makes the renewal figure
mean something instead of being one number among many.

---

## Round 12 — what a user actually meets, ranked by encounter rate (2026-09-21)

Round 12 ran the engine as four households rather than reading the diff, and its headline is
the one worth keeping in view: **this week's work changed nothing a user would notice.** Five
configs run on last week's tip and on this week's; no number moved anywhere — not a verdict, a
margin, a probability, a threshold, a ratio or a cash line. The entire delta was one clause on
one warning, firing only where a run carries both an income block and a stated renewal ladder.
The week bought correctness and maintainability. The week before moved a household's
P(condo cheapest) from 0.0% to 19.8%. **Rank by encounter rate, not by severity**, is the
lesson, and this list is ordered that way.

1. **The capital-spread warning describes one of its two causes. LANDED 2026-09-21, and the
   seat's own diagnosis of it was wrong in a way worth recording.** Its guard is a disjunction
   — the rates differ, OR a `tax:` block's drag moves a dollar — and its sentence only ever
   described the first. 4 of 4 households met it; on one it is 96% of the margin and the
   difference between a tie and a decisive call.

   The seat reproduced *"earns 5.2% … vs discount_rate 5.2% — net capital term $6,978 … set
   investment_return_rate = discount_rate"* and concluded the rates were equal, the remedy a
   no-op and the term entirely tax drag. **All three were wrong.** Measured: the rates differ
   by 3.70 basis points — 5.200% against 5.163%, the engine's 3% real default composed with
   2.1% inflation — so that config is the BOTH state, and the rate remedy moves 3.9% of the
   term rather than none of it.

   **What made it read as a no-op was a second, separate defect: `rate_label` rounds to one
   decimal, so two different figures both render "5.2%".** The sentence displayed two equal
   numbers and claimed a spread between them. That is the falsehood actually on the screen, and
   it is a display defect rather than a missing fork — a reader cannot audit a figure the
   formatter has rounded into agreement with its neighbour. The line now spells out the first
   decimal that separates them: *"vs discount_rate 5.2% (the two round alike: 5.200% against
   5.163%)"*.

   Both defects were real and both are fixed. The lesson is narrower than the fix: **a
   reproduction shows you what the screen says, not why it says it.** The seat diagnosed the
   cause from the rendered string and got the cause wrong while correctly identifying that the
   string was false.

   A third correction from the same builder: `tax.renter_capital` is only a PARTIAL remedy. On
   that household the FHSA rollover haircut is 80% of the term and moves only with
   `tax.retirement_marginal_rate`. The fixed sentence names two legs with two levers.
2. **The threshold seed describes a purchase the household cannot make.** Operator ruled
   2026-09-21: seed ABOVE the insurance line, not below. See the convergence note below.
3. **The no-crossing branch drops affordability entirely.** A sweep the lane forbids finds max
   ratio 44.6% at the top of the searched range on $54,000 of income — past CMHC's 39% GDS cap
   — while the run prints one ratio, 17.1%, at the seed. Two instances in two lanes. Not a
   skill defect: `quick-sense.md` and `threshold-lane.md` both withhold the price sweep here,
   so the disclosure cannot depend on the assistant running a forbidden command.
4. **Neither side's p95 reaches the verbatim channel.** 23 block lines, zero hits for `p95` or
   `P(condo cheapest)`. "Smallest worst case" is one of the three criteria the intake asks for
   by name. The block already carries two report sections, so adding the percentiles is
   consistent rather than novel.
5. **`rent` has no year-0 cost channel** — item 17. Largest magnitude in the round: reports
   House by $31,776, correctly encoded House by $58,180. Understates staying's advantage by
   $26,404, **83% of the margin it prints.**
6. **The Québec school-tax warning cannot be cleared on a price threshold.** Every Québec
   property outside three cities. Each refusal is individually correct; together they leave no
   path, while `translation.md` says to prefer the rate forms on any price threshold.
7. **A false `--print-schema` note on `rent.reset_to_monthly_rent`** — it claims the reset
   carries the tenant's own escalation; the code uses `reset_market_escalation_rate`, whose own
   note says the opposite. Typing them equal moves the answer, which it could not if the note
   were true.
8. **"Asymmetric tails" is gated on `investment_return_vol == 0`** — a smooth annual vol, not a
   tail. A renter with a return vol but no lease-reset channel meets an owned side with a
   discrete crash and gets no warning. Worth P(condo cheapest) 14.1% → 19.8%.
9. **"purchase_costs not modelled … biases toward buying" is false for an existing owner** —
   disclaimed cohort, closes when §10's tenure refusal ships.

**The convergence, which is the thing to act on before any individual fix.** Items 2 and 3 and
the missing financing leg all land on the SAME household — the one whose cash is under 20% of
the prices they are considering — and all three descend from one decision, that the threshold
lane seeds a price BELOW the 20%-down ceiling. `PROMPTS.md` advertises that household by name.
One design choice generating three defects means the sibling sweep here is the seed rule
itself, not the three lines. Operator ruling: seed above the line.

**The category sweep found EIGHT reachable-and-false warnings, not one, and one of them was in
the skill rather than the engine.** The sweep was the more valuable half of that fix, as
briefed. Beyond the capital term and the rounding: the affordability warning's RENT row claimed
a GDS shape with maintenance in the numerator and CMHC's 39% cap, to a tenant who has no
mortgage and faces no lender test; the owned-down ask said *"owned options put $150,000 down"*
on a $50k and a $100k option, a sum no option puts down; the decisiveness line said *"the user
did not state"* of a figure the user typed but never declared, inferring an answer from silence;
the firing gate could print *"net capital term $0 … set investment_return_rate =
discount_rate"*; a zero-growth warning printed *"=0.0%"* to a household that had typed 2.1%; and
the tax-only lead said the tax was *charged* where drag goes negative on a negative return,
contradicting its own leg. All fixed.

**The eighth was one layer up, in the instruction that drives every answer.**
`.claude/skills/hde/references/gates.md` told the assistant *"When the return equals the
discount rate the capital term nets to zero in PV"* — false under a `tax:` block, which is the
same defect as the engine's, in the document that tells Claude what to say about it. An engine
fix alone would have left the wrong sentence being spoken.

Thirteen non-findings are recorded in `tests/test_warning_cause_sweep.py`'s module docstring, so
the next sweep starts where this one stopped. Two test-reach limits were reported rather than
hidden: the spread-plus-tax identity test pins the invariant in `tax_treatment.py` and cannot
fail on any `config.py` mutation, and two mutations bite only on the FHSA fixtures.

**One skill defect from round 12 survives, and it is the only "the assistant should have said X"
in that round.** Nothing in `SKILL.md` or its seven references routes a reader to `PROMPTS.md`'s limits
inventory — one grep hit across all of them, and it is about a long-tenure tenant. It cannot
move into the engine: a complete static inventory printed every run is the degeneration §5
forbids by name, and §8 assigns that inventory to a document. Only a skill can route a reader
to a document.

**Four non-findings, recorded so the next sweep does not re-find them.** The one-world sibling
sweep was already complete (both reset keys and `value_growth_vol` are in the unstated-
uncertainty detector). The read-back drops no warning — five of five present verbatim; its gap
is a missing SECTION, not leakage. Quick-sense's one-horizon rule cost nothing on the household
that tempted breaking it. And the anchor staleness warning is a real code path, not prose.
Four absence claims checked, three came back present — consistent with the 79%-false figure
this repo measured for absence-hunting sweeps, and the reason the round ran greps and ablations
rather than reporting what it did not see.

**One withdrawn finding, recorded as withdrawn.** Round 12 had reported gate 4's like-for-like
rule as a small real defect. Correcting the renter's capital in isolation moves the margin
$2,599 the WRONG way; it is a tax-drag residual, not a measure of anything. A near-null
mis-read as small-but-real.

---

## Settled — do not reopen

Rate convention (sticker rates in, converted once), the three-state verdict, the short
read-back, tax treatment with FHSA and HBP, the contracted-rate base with posted as
ceiling, the artifact boundary, forward-only cleanup of public bytes. Each is recorded
with its reasoning in `docs/roadmaps/` and enforced by tests.
