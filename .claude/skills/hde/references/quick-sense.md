# Quick-sense lane ("not a spreadsheet")

This lane fires on the user's own words asking for brevity — "quick sense",
"not a spreadsheet", "just roughly", "the gist", "short answer", "don't write
me an essay", "just tell me" — never because the question looks casual. A user
who did not ask for brevity gets the full answer and the story.

## Which shape — decide before the intake

Two triggers, two jobs. **Brevity words** ("the gist", "just roughly", "no
essay") set the CAP. **The no-listing test** sets the ASKS: does the user have
a listing, a price in mind, or a date to buy — or ask at what price or rent
the answer flips? Run it on the opening line, not after a pushback — "is it
dumb to just rent forever?" answers no to all four before any number is known.
No to all four → the "no listing, no plan" shape below (four short asks, about
170 words of prose). Yes to any → the threshold shape under its own heading
(six asks, 200 words, or 250–350 with a mortgage, an income and a threshold).
An "at what price would buying make sense?" / "what rent keeps renting ahead?"
question is a threshold question whatever else it lacks: it gets the full run
with its threshold (`references/threshold-lane.md`), never the no-listing
shape — brevity words only cap its prose. Never mix the shapes: the no-listing
shape never asks condo-vs-house or runs a price scan the user did not ask for.

## No listing, no plan — the shape

A user with no property in view and no plan to buy within about two years
("is it dumb to just rent forever?") is not asking for a price threshold. Ask
four short things in one message — rent, income, savings, and whether any
listing or date exists — then run ONE command and answer in about 170 words
of prose.

**The one command.** One horizon, stated (the one they gave, or the default
you labelled in the intake — never a `--sweep years`), and one break-even on
the price:

```
uv run hde scenarios/<slug>.yaml --break-even <option>.initial_value=<lo>:<hi> --read-back
```

Seed the config's price a step BELOW the 20%-down price the `financing:` line
prints for their cash (run once to read it; declare the seed `assistant` in
`sources:`), so the scan starts where their cash still covers 20% and the
engine re-derives the premium tier above it. If the engine reports no crossing
inside the bracket, widen to the bounds it prints and rerun — never call the
bracket asked for the answer.

**The prose.** Two sentences of verdict at their numbers ("renting at $1,600
with $35k saved is not throwing money away: over 10 years, the horizon you
named, it is the cheaper choice") plus ONE conditional naming what would
change it ("buying starts to compete only under roughly $330k — a band the
engine solved at that horizon with placeholder tax and insurance; the mortgage
insurance and the transfer tax it computed from its own schedules at every
price"). When the cash is thin, the conditional carries the `financing:`
line's 20%-down ceiling ("your $35k covers 20% down only up to about $140k;
above that the mortgage is insured and the engine priced the premium"). Then
one clause for the prior when the area has one (gate 2: what growth it encodes
and whether the verdict survives it), and one "not modelled" clause: renewal
risk, unit insurance, and — whenever the engine warned on it — the
rent-escalation default by name and direction ("1% real rent escalation is the
engine's default; a Québec continuing lease runs nearer 0%, which favours
renting"). State plainly that every property-specific figure is a placeholder
and offer the full pass for a real listing. The shape binds the ANSWER, not
only the intake: an intake that took this shape and an answer that runs a
price scan across several horizons and quotes a band three ways has failed the
lane. The engine's READ-BACK block is pasted after those sentences, outside
the cap. The dollar band is deferred, and said to be deferred, never dropped
silently. The follow-up round never asks the user to choose a method or a
dwelling they said they do not care about.

## A listing, a price or a date — the threshold shape

Ask only six things in one message — dwelling, rent, price, how they'd pay,
horizon, income — plus the labelled defaults you will take ("25-year
amortization when only the term was quoted, the engine's 3% real return, 1%
real rent escalation — 0% for a Québec continuing lease — and 0.6%
maintenance, unless you say otherwise"). Decide the sweep yourself from
whatever they were vague about, and offer the deeper pass at the end.

## The cap (threshold shape — a listing, a price, or a date exists)

Under 200 words. With a mortgage, an income and a threshold question
together, the answer checklist needs 250–350 words (the higher end when the
prior's verdict band is quoted too): exceed the cap before dropping an item
(this lane's cap overrides the answer template's 500). Cut in this order:

1. the story path;
2. the SOURCE of every default other than `selling_cost_rate` (5%, WOWA) and
   the discount rate — those two are named in one clause and never cut;
3. the years bracket to one clause that still carries the figure at the
   user's stated floor beside the base ("over 8 years, the short end of your
   8–10, buying wins by $6k; over 10 by $14k") so every PV figure has a
   horizon — never "barely moves": the floor is the year they may actually
   leave, and a shift that narrows the margin is said;
4. the prior to two sentences;
5. every reassurance phrase.

The cap ranks what stays, it never drops a checklist item: cut words, never
items. A dropped warning fails the answer at any length; if the cap binds,
the story path goes first — it is never the item you keep while a warning
goes. The flip point, when it rests on an estimate you chose, is quoted at
both ends of that estimate in the same sentence.
