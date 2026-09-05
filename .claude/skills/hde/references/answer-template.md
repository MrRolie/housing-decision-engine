# The answer — what the user actually reads

After the checklist in SKILL.md, the prose, in this order:

1. **The verdict in words with its decisiveness** — the engine's three-state
   line, quoted: "renting is the better deal at $1,900 unless Laval prices
   grow about 2%/yr above inflation", or "too close to call: X edges Y by $N
   (1.4%), cheapest in 57% of futures", or on a disagreement both figures
   with neither option chosen — "best guess says rent by $6,517 (1.9%); most
   futures say house (60% cheapest) — the two disagree".
2. **The two or three things it rests on**, from the breakdown and `defaults
   applied`. The owner's driver is always "equity at sale = value after growth
   × (1 − selling cost) − remaining mortgage; purchase and selling costs are
   sunk; the renter's capital is credited at its terminal value too" — never
   "closing costs come back as equity" or "renting has no equity".
3. **The cash line** (gate 7) and the `financing:` line — the netting, the
   loan-to-value, the distance to the 20% line; on a price threshold, quoted
   at the crossing.
4. **The two largest engine-set numbers** whenever an owned option is present
   — `selling_cost_rate` (5%, WOWA) and the discount rate — named with their
   source; every other uncertainty input and cost you proposed (a crash
   hazard, a vol, an illustrative insurance figure) named with its label
   ("illustrative, not cited") and what it sets ("this is what makes the
   p95").
5. **The flip point or threshold** — the engine's `sentence` verbatim, at both
   ends of any estimate it rests on, every bracket that ran in one clause
   each; when a story exists, the story's headline and the answer agree (a
   story at the placeholder seed is never linked as if it were the verdict at
   the user's number — say which price it is at).
6. **The affordability line** whenever an income was given, from the
   nominal-mode run when there is a mortgage: max ratio and breach years,
   quoting the engine's affordability warning (it names the 32% guideline,
   the 39% GDS cap and the 44% TDS cap — the ratio is GDS-shaped, so never
   compare it to the TDS cap unless other debts were asked, and never soften
   "exceeds" to "not a breach" without naming which threshold each refers
   to).
7. **No source for:** every figure you had to estimate because neither the
   user nor the anchor registry had it (an Ottawa tax rate, an insurance
   quote, a purchase-cost rate, an Ontario land-transfer tax) — said plainly,
   never filled silently; outside the anchored jurisdictions say the registry
   does not cover them; this line is what the engine anchors next.
8. **Not modelled:** each item with its direction of bias ("renewal risk —
   biases toward buying").
9. **Where the story is** (`scenarios/<slug>/STORY.md` and the act PNGs) and
   the one next step (usually: a real listing's tax bill and closing costs
   replace the estimates).

10. **The engine's READ-BACK block**, pasted verbatim, last — the full block:
    every warning, the typed values, the decisiveness rule, financing, other
    costs, affordability, the break-even sentences. The gist shape pastes the
    short block (`--read-back short`: every warning, the source lines, the
    decisiveness rule) and turns its closing line into a one-line offer of
    the full block (`references/quick-sense.md`). It is the engine speaking;
    the prose above never contradicts it.

Under 500 words of prose (the block is outside the cap); the quick-sense
lane's cap and cut order are in `references/quick-sense.md`. The report is on
disk for anyone who wants it.
