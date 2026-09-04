# Quick-sense lane ("not a spreadsheet")

This lane fires on the user's own words asking for brevity — "quick sense",
"not a spreadsheet", "just roughly", "the gist", "short answer", "don't write
me an essay", "just tell me" — never because the question looks casual. A user
who did not ask for brevity gets the full answer and the story.

## Which shape — decide before the intake

Two shapes, one test: **does the user have a listing, a price in mind, or a
date to buy?** No to all three → the "no listing, no plan" shape below (at most
three asks, under 120 words). Yes to any → the threshold shape under "The
cap" (six asks, 200 words, or 250–350 with a mortgage, an income and a
threshold). Never mix them: the no-listing shape never asks condo-vs-house or
runs a price scan the user did not ask for.

## No listing, no plan — the shape

A user with no property in view and no plan to buy within about two years
("is it dumb to just rent forever?") is not asking for a price threshold. Ask
at most three things in one message (rent, income, savings — and whether a
listing or a date exists), then answer in under 120 words: two sentences of
verdict at their numbers ("renting at $1,600 with $35k saved is not throwing
money away: over 5 years it is the cheaper choice and over 10 it is too close
to call") plus ONE conditional naming what would change it ("buying starts to
compete only if you would stay 10+ years in a place under roughly $330k — a
band the engine solved with placeholders for tax, insurance and the insurance
premium, held fixed while the price moved, so it is generous to buying").
State plainly that every property-specific figure is a placeholder and offer
the full pass for a real listing. The shape binds the ANSWER, not only the
intake: an intake that took this shape and an answer that runs a price scan
and quotes a band three ways has failed the lane. The engine's READ-BACK block
is pasted after those sentences, outside the 120-word cap. The dollar band is deferred, and said to be
deferred, never dropped silently. The follow-up round never asks the user to
choose a method or a dwelling they said they do not care about.

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
3. the years bracket to one clause ("barely moves at 8 or 10 years"), keeping
   one statement of which end of their range is the base ("over 8 years, the
   short end of your 8–10") so every PV figure has a horizon;
4. the prior to two sentences;
5. every reassurance phrase.

The cap ranks what stays, it never drops a checklist item: cut words, never
items. A dropped warning fails the answer at any length; if the cap binds,
the story path goes first — it is never the item you keep while a warning
goes. The flip point, when it rests on an estimate you chose, is quoted at
both ends of that estimate in the same sentence.
