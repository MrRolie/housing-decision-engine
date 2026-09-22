# Unpriced dimensions — design

**Status:** proposed, 2026-09-21, revised the same day after the open question in §10 was answered. Design only, no engine code.

## 1. Why

This engine discloses what it does not KNOW, and it does it well. A figure with no published
source says so. An estimate the assistant chose rather than the user is labelled with the
direction it biases the verdict. When decisiveness rests on uncertainty inputs the user never
stated, the run names them and reports what the deterministic line alone says.

It discloses nothing about what it cannot SEE. Renewal risk was never an input a user forgot
to supply; it was a dimension the model lacked, so no channel fired and the answer read as
complete. A household renewing a mortgage got an answer that was truthful about everything
except the thing that mattered most to them. That is the old failure — a confident number
whose basis you cannot check — wearing this engine's honesty clothes.

**The finding that justifies the feature.** An unsupplied renewal path falls through every
channel the engine has. It is not blind by the strict definition, because the input exists
once the ladder ships. It is not an unstated uncertainty input, because `unstated_uncertainty`
reads a detector that lists only inputs which are set and nonzero, and a renewal ladder runs
deterministically on every path regardless. It is not a missing anchor. Without this feature
it has no home at all.

**What this is not.** Not a list of limitations; `PROMPTS.md` holds that and is read before
anyone asks. Not a second name for a gap the coherence warnings already name. This is one
measured claim about one run.

## 2. The rule that makes it honest

**The engine may choose the SHAPE of a counterfactual, never its MAGNITUDE.**

Shape is which key moves and over what structure. Magnitude comes from exactly three places:
the user's own figure, a registry anchor used for the purpose the registry itself states, or
the solve. A dimension needing a magnitude from anywhere else is not measurable here.

The consequence is that the primary form is a THRESHOLD, not a stressed point. Not "renewing
two points higher costs you $X" — that number is a convention the engine imported. Instead:
solve for where the verdict changes, and situate that value against figures that carry their
own provenance (the user's contract rate, `mortgage_rate.contracted_5y_uninsured`,
`mortgage_rate.posted_5y`). The user judges plausibility. The engine invents nothing.

The precedent is already in the tree. `break_even.RATE_BRACKETS` is a labelled convention with
no anchor behind it and the engine prints it on every solve, which is permitted because a
search bracket only bounds where the engine looked; the crossing itself is a property of the
user's config. A stress value is the opposite: the convention IS the number in the answer.

**Guard on the posted anchor.** Its own rationale records that the series has not moved in
sixteen months and that it is a list price for bracketing today's contracting from above. It
is not a ceiling on a 2031 renewal. It prints as "today's posted five-year rate", never as a
worst case. No renewal-rate anchor ships, per `2026-09-03-mortgage-renewal-risk.md` §11.

## 3. Three states, one owner each

A dimension does not go from invisible to modelled. It passes through three states.

| State | Meaning | Owner |
|---|---|---|
| **Not priceable** | no input exists; the engine cannot represent it at any setting | this line |
| **Priceable, unpriced here** | the input exists, the user supplied nothing, the engine holds a silent default | this line, and the coherence warning owns the fix |
| **Priced from a stated path** | the user gave the figures and the engine ran them | nothing; the assumptions block already shows the ladder and its source class |

Holding one rate for twenty-five years is not the absence of an assumption. It is a strong
assumption wearing an absence. That is why state two earns the line and is the loudest of the
three.

**The gate is therefore "this run does not price it",** not "no input exists". A reader cannot
act on the difference between a dimension the engine cannot see and one it could have seen if
somebody had filled in a field. Both mean the number in front of them omits it.

**The anti-accretion invariant.** Every capability the engine gains moves a dimension toward
state three, and state three prints nothing. So this line's population SHRINKS as the product
grows. A future reviewer should be able to check that and find fewer entries firing, not more.

## 4. What fires, what leads, and what prints

**Rarity was the wrong variable.** What kills a disclosure channel is INVARIANCE, not
frequency. The existing `[warning]` lines and the `decisiveness:` line fire on nearly every run
and nobody proposes gating them, because their text differs every time. So the guard belongs on
variance, and admission and prominence are separate decisions.

**Admission.** The line carries at least one quantity from THIS run, and it either states a
direction or refuses one with a stated reason. A line that can offer neither does not print.

**Promotion.** A line whose size is computed and exceeds the verdict's margin leads. Lines whose
size cannot be computed follow it. The margin is an ordering rule, not an admission rule —
demoting it is what lets an uncomputable dimension be disclosed at all, and §9 shows why that
matters.

**Cap.** At most a small fixed number per run, in that order.

**When nothing qualifies, nothing prints.** Not a reassurance — `references/quick-sense.md`
lists reassurance phrases as the first thing to cut, so a line reporting survival is exactly
what the repo already refuses. Silence gets its documented meaning in `PROMPTS.md`.

**The honest limit of this, recorded rather than argued away.** Specificity contains the
boilerplate failure; it does not eliminate it. A line whose only varying part is one dollar
figure inside a fixed sentence is nearer to boilerplate than "run-specific" suggests. The cap
and the ordering contain that. Nothing in this design proves it solved, and a future round that
measures block words per shape should look here first.

## 5. The guard

**The line prints a number solved from this run, and the same feature must be able to print
nothing. A line that cannot come out silent is a disclaimer. A line that can is a
measurement.**

Pinned by two assertions in `tests/test_read_back.py`:

- two configs differing ONLY in the margin, one printing and one silent;
- two configs differing ONLY in loan size, both printing, with different figures.

If either passes trivially, the line has become text and the test says so.

**The failure mode these guard against**, stated so a future reviewer recognises it: the gate
loosens from "exceeds the margin" to "is material". The line then prints on nearly every
financed run, degenerates into a template that reads identically every time, and the assistant
— seeing a constant line — paraphrases it into the prose. The restatement bloat this repo
measured once (about 320 of 1,048 words) returns. The reader learns the last warning is
boilerplate and skips the channel, which costs the run-specific warnings too, because they
share it. That end state is WORSE than not building this, because the block keeps the
appearance of disclosure while nobody reads it.

## 6. Placement

The warnings channel, appended after `compute_verdict` in `cli.py`, in the same position as
`uncertainty_source_warnings` — it needs `verdict.margin_pv`, so it cannot live in
`coherence_warnings`, which runs before the verdict exists.

That buys four things: it lands in the full block and the short block with no change to the
short block's ordering; the closing count line stays honest untouched, because the warnings
section is never named as omitted; it inherits the cut order, where a dropped warning fails the
answer at any length; and it costs ZERO skill words.

**The subject must be restated in the line.** `cli.py` builds warnings in four passes —
coherence, then affordability breaches, then decisiveness provenance, then the one-sided sweep
note. So on exactly the runs where this fires, other warnings sit between it and the coherence
warning it refers back to. A bare magnitude clause landing after that distance is unreadable.
This is a checkable fact about the ordering, not a matter of taste.

## 7. Wording

Prefix `unpriced:` — "not modelled" belongs to the coherence warnings. Option name first,
matching the existing `{name}: …` convention.

**State two** (financed, rate held for the whole amortization, small margin). The coherence
warning owns the mechanism and the fix, so this carries the size:

```
[warning] house: unpriced — your rate is fixed for 5 years; this run prices all 25 at 4.65%.
Renewing 0.44 points higher and holding it there flips the verdict; 1 point higher costs
$14,900 in PV against a margin of $6,517. A sensitivity on your own loan, not a forecast.
```

**State one** (all-cash, renewal irrelevant, no price dispersion). The first draft of this line
solved for where the central case flips — "prices would have to run 0.6 points slower than you
typed" — and that draft was WRONG in a way worth recording, because it is the failure mode in
its purest form. The solve answers where the central case flips. The blind spot is the absence
of DISPERSION around that case, which is a different quantity: it feeds `P(each option
cheapest)` and therefore the decisiveness rule that settles most runs. A reader told the flip
point will reasonably conclude the price dimension has been handled. It has not, and the solved
number makes that conclusion MORE likely, not less. A computable number standing where an
uncomputable one belongs is worse than silence.

So this line refuses its direction and says what is absent:

```
[warning] condo: unpriced — every cost in this run varies across the 5,000 futures and the
home's value does not; it follows one path, your 2.0%/yr, plus the crash you set. Terminal
equity is -$218,959 of this option's $518,779, so the largest figure that turns on something
nobody knows is the one with no spread. How often prices alone would change the answer is not in this run, and P(cheapest)
below reads narrower than the truth because of it. Set simulation.value_growth_vol to price
it — the engine anchors no figure for it, so the number would be yours.
```

That last clause was added 2026-09-21, when `simulation.value_growth_vol` landed. The line's
job did not change: the key defaults to zero and no anchor supports a value, so the dimension
is still unpriced in every run that does not set it. What changed is that the user can now DO
something, and a disclosure that names the key beats one that only names the gap. The clause
also keeps the line honest in the other direction: it says plainly that any figure they put
there is theirs, not the engine's.

**Nothing qualifying:** no line.

## 8. Division of labour

One sentence each, so no channel drifts into another's job.

- **Decisiveness provenance:** the inputs that decided the verdict were not the user's, and
  here is the verdict without them.
- **The coherence warnings:** this dimension is switched off, and here is the input that
  switches it on.
- **`no anchor match` and "no source for" lines:** a figure inside the model has no citation —
  a missing number, not a missing mechanism.
- **The `PROMPTS.md` limits list:** the complete static inventory, read before you ask.
- **This line:** the one dimension this run does not price whose measured size exceeds this
  verdict's margin, printed after the run.

## 9. Classification

Three classes, not two.

| Dimension | Class | Note |
|---|---|---|
| Renewal rate held for life | measurable | solve `mortgage_renewal_rates` once the ladder ships |
| Early exit / horizon | measurable | solve `years` over the user's own range |
| Dispersion on the home's value | nameable, direction REFUSED | see below — NOT covered by solving `value_growth_rate` |
| Rental income | measurable on cue | mechanically solvable, but the engine cannot see whether a suite exists — belongs to the intake's missing-information gate |
| Break / prepayment cost | qualifier | bounds the early-exit figure in a known direction |
| Unpriced tax items | qualifier | direction already recorded in the schema notes |
| Existing-owner state | nameable, direction REFUSED | see §10 |

**The asymmetry that makes dispersion the sharpest entry.** As this spec was written, every
cost input carried a volatility — `condo_fee_vol`, `house_maintenance_vol`,
`rent_escalation_vol`, `other_cost_vol`, `inflation_vol`, `investment_return_vol` — and the
home's value carried none; `severity_vol` was the crash channel and `magnitude_vol` events. So
the engine modelled dispersion on every cost and none on the asset, while the asset drives the
largest UNCERTAIN term in an owned option's total: in the shipped showcase the condo's terminal
equity is -$218,959 against a $518,779 total, second in magnitude only to the $480,000 paid at
year 0 — which is certain, and therefore not where dispersion belongs.

**Amended 2026-09-21, and the amendment sharpens the case rather than closing it.**
`simulation.value_growth_vol` now exists, so the MECHANISM is there. But it ships with no
default and no anchor, because a defensible figure needs a published Canadian price series
with a stated window and nobody has cited one here. So the state of affairs this section
describes is unchanged for every run that does not set the key, which is every run today
including all seven shipped examples: the dispersion of the biggest unknown is still not modelled,
and it still feeds the decisiveness rule.

What changed is WHAT THIS LINE MUST SAY. It can no longer say the engine cannot represent the
dimension — it can, and naming an absent capability would be false. It has to say that the
dimension is representable, is currently zero, and that zero is a choice nobody sourced. That
is a better line than the original: it points at a key the user can set and sweep, rather than
at a limitation they can do nothing about.

Its siblings, for the same reason: correlation between house prices and the user's own income,
which is still independent (board item 13), and regime change in any anchored series.

**Qualifier** is the class worth naming. A nameable-only omission that bounds a MEASURED number
in a known direction should print attached to that number, never as a free-standing disclaimer.
A break penalty makes early exit worse than the measured early-exit figure. Printed alone it is
noise; printed on that line it makes the measured number honest.

## 10. The cohort the engine cannot detect — REFUSE, do not disclose

Every owned option starts at a purchase. A household that already owns cannot be described:
no existing balance, no years already paid, no equity accrued. Whether selling helps or hurts
depends on that equity, on their rate against today's, and on whether the principal-residence
exemption covers the gain — which pull opposite ways, so the direction is genuinely
indeterminate. Claiming one would be the cheap all-clear in a new costume.

It cannot be a per-run line. The engine has no input that detects it, so the line would fire
unconditionally, which §5 forbids by name. Worse, the exclusion is invisible BY CONSTRUCTION:
the people the frame excludes are exactly the people whose configs cannot record that they are
excluded. Their config is indistinguishable from a first-time buyer's.

**The first answer was wrong and is recorded because the reason generalises.** It was to move
the detection into the intake, where the assistant can simply ask. That fails on this repo's
own evidence: the `you said:` line exists because two consecutive rounds of served answers lost
the user's own figures from the prose, which is why that fact was moved into the engine's
block. Instructions in prose fail here — measured, twice. Routing the single highest-stakes
case through the one mechanism already proven unreliable is worse than either alternative,
because a missed cohort question does not degrade an answer, it invalidates all of it.

**The answer is a required field and a refusal.** A tenure input, REQUIRED on any config that
prices an owned option. The engine refuses a config that omits it, the same way it refuses any
other missing required key. On a value that says the household already owns, it refuses to run
at all, and the refusal names the limit and the one substitute question it can still answer.
Detection stops depending on anyone remembering, because there is no run to produce without it.

**The principle that decides which organ applies, and it generalises past tenure:** a required
field works when the missing dimension is a fact THE USER POSSESSES. It fails when the missing
dimension is a fact NOBODY IN THE TRANSACTION POSSESSES. Tenure is the first kind — the
household knows whether they own — which is why refusal fits it exactly. A price volatility is
the second: requiring a household to state one would be requiring them to supply the very thing
the engine should anchor, and `2026-09-03-mortgage-renewal-risk.md` §11 already made this
argument in the other direction, that a household can reason about renewing two points higher
and cannot reason about a calibrated diffusion. Renewal escapes by reframing to a scenario the
user chooses. Dispersion cannot take that route, by §11's own reasoning.

So: **refusal is the organ for a dangerous dimension the user could state; the line is the organ
for one nobody can.** The two designs stop competing once that is said.

This is the repo's existing law, not a new one: a surface that cannot verify must REFUSE.
Refusal is the correct organ for a dimension whose bite is unbounded. An uncomputable bite IS
more dangerous than a computable one — the person gets a full page of internally consistent
numbers answering a question they did not ask, and no line at the bottom undoes a page of them.

**The obvious shortcut is already visible** — this was the claim, and it is WRONG. It read:
"An assistant that types the tenure itself to clear the gate is caught by machinery that
exists: `sources:` classes every input, so an assistant-supplied tenure surfaces in the
read-back as an `assistant-typed:` entry, in BOTH blocks, where the user can see that nobody
asked them. No new mechanism."

**Corrected 2026-09-21, measured.** The key does surface. It does not surface as
`assistant-typed:`.

Declaring a key in `sources:` is OPTIONAL, and the party the rule polices is the party who
decides whether to declare. Omit the line and the key lands under `unattributed:` instead — and
`unattributed:` is where the STRUCTURAL keys live, the ones no one would think to declare. A run
that states income but never classes it prints:

```
assistant-typed: discount_rate=4.2%, condo.value_growth_rate=4.2%
unattributed: years=10, province='QC', economic.mode='nominal',
              economic.inflation_rate=2.1%, income.annual_income=$94,000
```

The invented income sits in a comma-separated list beside `years=10` and `province='QC'`, read
as the same class of thing, and the run exits 0 with nothing else said. An omission is
therefore CHEAPER than a declaration for anyone who would rather not own a figure, which
inverts what the mechanism is for.

One case IS handled well and is worth keeping: a config with NO `sources:` block at all prints
`sources: none declared — the read-back cannot tell the user's numbers from the assistant's`.
The hole is the PARTIAL block, which reads as diligence.

So §10's refusal stands — the organ is right, and a dimension with an unbounded bite must
REFUSE rather than disclose. What does not stand is "no new mechanism". Something has to
distinguish "nobody declares this key" from "the party who should have declared it did not",
and today one list holds both. Whether that is a third class, a warning when a partial block
omits a key the verdict reads, or a rule that a declared block must be complete, is open and
belongs on the board rather than in this paragraph.

The ladder in §3 gains a state at the top: **refused**, then not priced with no input, then not
priced with the input unfilled, then priced.

## 11. Staleness

Not guarded — DERIVED. The repo has solved this once already: the schema's note about cities
with no property-tax source is computed from the registry by filtering on unsourced entries, so
it cannot claim a city is unsourced after someone sources it. A disclosure must be derived from
the structure it describes, and where it cannot be derived, that structure must refuse it.

Here the derivation is §3's gate. A dimension leaves this line when the run prices it, which
happens because the user supplied the input a landed capability created. Nothing to retire by
hand.

Where a registry entry is still needed for a state-one dimension, it carries the config keys
AND the anchors whose absence it asserts, and a test fails if any appear. That pair covers
every capability needing a number, since a number comes either from the user through a pinned
key or from the engine as a registered anchor (an uncited constant raises at import). What it
does not cover is a capability that is pure restructuring of numbers already held; an entry
whose retirement nothing can police does not ship, and its insight goes to prose instead.

## 12. What must never go in

- Anything the user can fix by typing — that is a coherence warning.
- Anything whose size cannot be solved from the user's own inputs under §2.
- Any dimension below the margin.
- More than one line.
- A reassurance.

## 13. The four hand-written gap warnings stay

The committed engine already writes this kind of disclosure four times by hand, in prose, in
`config.coherence_warnings`: untaxed renter capital, understated owner costs, zero
appreciation, and the missing Québec school-tax line. They stay where they are. Each names a
key or block the config can already state, which is the omitted-input state, and moving them
would create the second home this design exists to avoid.

What IS duplicated is the direction vocabulary, currently written three different ways across
those four. That taxonomy gets one home in the new module and the coherence warnings format
from it.

## 14. The qualifying rate — one citation, two channels

A published figure converts the common case from a convention into an anchor. The banking
regulator's minimum qualifying rate for uninsured mortgages is the greater of the contract rate
plus two points, or 5.25%, unchanged through 2026. Anchor it with the FULL greater-of rule so
the stored figure reconciles with the source verbatim, and record in the rationale that the
floor leg binds only below a 3.25% contract rate. The spread lands on the as-quoted axis, which
`mortgage_rate_compounding` then converts, so it must never be added to an effective-annual
figure.

**Where it must NOT go: the marker row beside a solved threshold.** The markers flanking a
threshold are all rates that were or could be charged, so a reader scans the row on one axis.
A qualifying rate is a TEST threshold, not a price, and a fourth figure in a row of prices gets
read as a price whatever the label says. The posted anchor passes that test and this does not.

**Where it goes instead:** inside the affordability clause. The break-even read-back already
attaches one to every threshold entry (`_affordability_at`, `quoted_points`,
`_affordability_clause`, all at HEAD), and there the sentence and the quantity agree. So it can
ride the renewal line after all, in the clause rather than the row.

**What it buys on the affordability line, which is better:** there the citation is exactly on
label, because the affordability channel already runs a cost-over-income test and the
qualifying rate is the published rule FOR that test. Move `mortgage_rate` by the rule, run
deterministically, read only the income report and discard the present value.

**One guard, from the registry itself.** The `income.affordability_threshold` anchor records
that its numerator is broader than a lender's gross debt service measure. So the line prints
the ratio on the engine's own measure and NAMES that gap. It must never print that the user
would fail to qualify. That is the sentence that would fail contact with a reader.

**This ships on the committed engine today**, with no dependency on the renewal ladder.

## 15. The channel must sometimes carry good news

Every qualifier in §9 makes the stated answer worse: the break penalty, the deferral, the
understated owner costs. A disclosure channel that only ever says the answer is worse than it
looks is not calibrated, it is pessimistic, and a reader learns to discount it.

One published rule runs the other way. Since 2024-11-21 a straight switch to a new lender at
renewal — same loan amount, same amortization — is exempt from the qualifying rate, so the
household qualifies at their contract rate. It belongs as a qualifier on the affordability
line, not the verdict line, because it changes whether the stress binds and moves no present
value. Its wording branches on the insured tier, which `sweep.insured_of` already derives.

It is the most valuable entry on the list, and not because of renewal. It tells a household
that a lever exists in their favour. That is what makes the channel credible rather than
decorative, and it should be treated as a design requirement: **a channel that can only deliver
bad news will be discounted, so a qualifier that helps the user ranks above one that hurts
them, all else equal.**

## 16. Smallest shippable slice

The affordability application of §14 alone: one cited load, one ratio, one named gap, on the
committed engine. It needs nothing from the renewal ladder and proves the whole mechanism.

Then the renewal dimension, state two, on financed runs, after the ladder lands: one solve, one
comparison, one line, both pinning assertions, and the `PROMPTS.md` sentence that gives silence
its meaning.

Then the tenure field and its refusal (§10), which is independent of both and is the largest
single gain in who the tool serves honestly.

Deliberately left out of round one: price variation (it needs the diffusion channel first),
early exit, the remaining qualifiers, and the registry for state-one dimensions.
