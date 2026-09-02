# The answer — what the user actually reads

After the checklist in SKILL.md, the prose, in this order:

1. **The verdict in words with its decisiveness** — "renting is the better
   deal at $1,900 unless Laval prices grow about 2%/yr above inflation", or
   "too close to call: X edges Y by $N (1.4%), cheapest in 57% of futures".
2. **The two or three things it rests on**, from the breakdown and `defaults
   applied`. The owner's driver is always "equity at sale = value after growth
   × (1 − selling cost) − remaining mortgage; purchase and selling costs are
   sunk; the renter's capital is credited at its terminal value too" — never
   "closing costs come back as equity" or "renting has no equity".
3. **The cash line** (gate 7) and the year-0 cash total the config commits,
   with the distance to the 20% down-payment line when it is within one price
   step.
4. **The two largest engine-set numbers** whenever an owned option is present
   — `selling_cost_rate` (5%, WOWA) and the discount rate — named with their
   source; every other uncertainty input and cost you proposed (a crash
   hazard, a vol, an illustrative insurance figure) named with its label
   ("illustrative, not cited") and what it sets ("this is what makes the
   p95").
5. **The flip point or threshold**, in the user's units, at both ends of any
   estimate it rests on; the sanity line.
6. **The affordability line** whenever an income was given, from the
   nominal-mode run when there is a mortgage: max ratio and breach years,
   quoting the engine's affordability warning (it names the 32% guideline,
   the 39% GDS cap and the 44% TDS cap — the ratio is GDS-shaped, so never
   compare it to the TDS cap unless other debts were asked, and never soften
   "exceeds" to "not a breach" without naming which threshold each refers
   to).
7. **No source for:** every figure you had to estimate because neither the
   user nor the anchor registry had it (a property-tax rate, an insurance
   quote, a purchase-cost rate) — said plainly, never filled silently; this
   line is what the engine anchors next.
8. **Not modelled:** each item with its direction of bias ("renewal risk —
   biases toward buying").
9. **Where the story is** (`scenarios/<slug>/STORY.md` and the act PNGs) and
   the one next step (usually: a real listing's tax bill and closing costs
   replace the estimates).

Under 500 words; the quick-sense lane's cap and cut order are in
`references/quick-sense.md`. The report is on disk for anyone who wants it.
