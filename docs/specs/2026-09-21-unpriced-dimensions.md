# Unpriced dimensions — design

**Status:** proposed, 2026-09-21. Design only, no engine code. One open question, named in §10.

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

## 4. What fires, and what prints

A dimension reaches the line only if all three hold:

1. **This run does not price it** (§3).
2. **Its size is solvable from the user's own inputs**, under §2's rule, with no forecast.
3. **That size is at least the verdict's margin in dollars.** Below the margin the unknown
   cannot reach the decision.

**The cap is one line.** The value of the feature is the ranking, so printing two is the engine
declining to rank. And the runner-up is by construction the smaller exposure: if the largest
unpriced dimension already exceeds the margin, the verdict is not safe and a second line
changes nothing the reader does.

**When nothing qualifies, nothing prints.** Not a reassurance — `references/quick-sense.md`
lists reassurance phrases as the first thing to cut, so a line reporting survival is exactly
what the repo already refuses. Silence gets its documented meaning in `PROMPTS.md`, which is
user-facing and outside the skill's word budget.

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

**State one** (all-cash, renewal irrelevant, no price spread). Nothing above owns it, so it
carries the mechanism and closes on what the registry lacks:

```
[warning] condo prices: this run follows one price path, your 2.0%/yr, with no year-to-year
spread around it, so nothing here says how often prices alone would change the answer.
Prices would have to run 0.6 points slower than you typed to flip this verdict. No anchored
figure for how far a decade of prices misses that mark.
```

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
| Ordinary price variation | nameable | no `value_growth_vol` exists to stress |
| Rental income | measurable on cue | mechanically solvable, but the engine cannot see whether a suite exists — belongs to the intake's missing-information gate |
| Break / prepayment cost | qualifier | bounds the early-exit figure in a known direction |
| Unpriced tax items | qualifier | direction already recorded in the schema notes |
| Existing-owner state | nameable, direction REFUSED | see §10 |

**Qualifier** is the class worth naming. A nameable-only omission that bounds a MEASURED number
in a known direction should print attached to that number, never as a free-standing disclaimer.
A break penalty makes early exit worse than the measured early-exit figure. Printed alone it is
noise; printed on that line it makes the measured number honest.

## 10. The cohort the engine cannot detect — OPEN

Every owned option starts at a purchase. A household that already owns cannot be described:
no existing balance, no years already paid, no equity accrued. Whether selling helps or hurts
depends on that equity, on their rate against today's, and on whether the principal-residence
exemption covers the gain — which pull opposite ways, so the direction is genuinely
indeterminate. Claiming one would be the cheap all-clear in a new costume.

It cannot be a per-run line: the engine has no input that detects it, so the line would fire
unconditionally, which §5 forbids by name.

**Provisional resolution, and the open question.** The organ that CAN detect this cohort is the
intake, because the assistant is talking to the person. The skill's missing-information gate
asks whether they already own, and on a yes the answer says plainly that the tool cannot take
their situation yet, before anything runs.

The objection to that is serious and unresolved: this whole feature exists because disclosure
must not depend on the assistant remembering to be honest, and the resolution puts the most
important case back in the assistant's hands. Open until answered: whether anything in the
ENGINE can make that question unskippable, and whether any config carries a reliable signature
that its author already owns. If such a signature exists, the line can fire conditionally and
this section is unnecessary.

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

## 14. Smallest shippable slice

The renewal dimension alone, state two, on financed runs, after the renewal ladder lands. One
solve, one comparison, one line, both pinning assertions, and the `PROMPTS.md` sentence that
gives silence its meaning.

Deliberately left out of round one: price variation (it needs the diffusion channel first),
early exit, every qualifier, the registry for state-one dimensions, and §10.
