# Board — what is open, ranked

The single home for OPEN work. `docs/roadmaps/` is the dated record of what happened;
nothing there is a to-do. If a thread is not on this board it is not being worked on.

**Ranked by one rule:** an item ranks above another when the other cannot be done, or
cannot be trusted, until it lands. Ties break toward the user seeing the difference.

Each item: **what**, *why now*, and what it unblocks. Status is `open`, `doing` or
`parked` — never a date, never a count.

---

## 1. Rate risk over the horizon — the renewal a Canadian mortgage actually has

**open** · blocks: 2, 3, the project's core claim

Today a mortgage carries ONE rate for the whole amortization. That is a US 30-year fixed.
A Canadian household signs a 5-year term against a 25-year amortization and re-prices four
times before the horizon ends. The engine is silent on the single largest buy-side risk in
the market it models, and every verdict it has ever produced assumes that risk away.

Build: `mortgage_term_years` becomes the TERM, amortization becomes its own field, and the
payment re-solves at each renewal off a rate path. Deterministic mode takes a stated
renewal path; Monte Carlo draws one. A renewal is a read-back line with its new payment,
because a user who learns this at renewal instead of at decision time has been failed.

*Why now:* it is the one modelling gap that can flip a shipped verdict, and everything
below that compares risks needs a rate path to compare against.

## 2. Price risk as a distribution, not just a crash

**open** · blocks: 3

`value_growth_vol` does not exist. House prices move only through a jump channel
(`price_shock`) and inflation. So the Monte Carlo's picture of owning is a straight line
with occasional disasters, and `P(each option cheapest)` is narrower than the truth.

Build: a diffusion on the value track beside the jump channel, anchored to Canadian
house-price series, with the anchor stating what window it was measured over.

*Why now:* without it, any statement about price risk versus rate risk is a comparison
against zero.

## 3. Which risk actually decides it

**open** · needs 1 and 2

With both channels live, decompose the verdict's variance: how much comes from renewal
rates, how much from prices, how much from the household's own inputs. Ship it as a
first-class output, not a one-off study, and state the conditions under which the verdict
reverses.

*Why now:* this is the question the product exists to answer, and the finding a reader
would cite. It is also the first thing the engine will have said that nobody else is
saying: the rent-versus-buy literature is shaped by a 30-year fixed rate, under which
renewal risk does not exist.

## 4. Anchors that survive their author

**open** · artifact boundary, clause 3

Twenty anchors carry a validity date and warn once it passes. Nothing in the repo can
refresh them. Every figure was fetched by hand from a session, so in January the engine
degrades to a wall of warnings and only the author can repair it. A product whose numbers
decay to unusable without one specific person is a habitat wearing a product's clothes.

Build: a refresh path in the repo, fetching from the sources the anchors already name,
with the run refusing to silently substitute.

*Why now:* the first anchors expire 2026-12-31. It is the last resident-builder assumption
left after the 2026-09-20 pass.

## 5. What the owner never gets back

**open**

The breakdown prints year-1 cash, principal and appreciation. Over the horizon the
interest/principal split and selling costs are not separated, so the owner's unrecoverable
cost is not a line anyone can read. That figure is the honest counterpart to rent.

## 6. The decision the user actually faces

**open**

Three items, one theme: rank on the figure the user cares about (`expected`, `p95`, end
wealth) rather than always the mean; let the horizon itself be uncertain ("we might move
for work"); and solve the crossing act 6 draws instead of sweeping ±35% around it.

## 7. Cuts, and what is in them

**parked** · needs a delivery decision

A user clones 57 MB to run a 2.2 MB engine; the rest is a sibling project, research data
and the build record. `v0.4.0` exists, so cuts exist. What a cut CONTAINS is undecided
because the delivery form is undecided: a repo people clone, a package, or something
hosted. Parked deliberately, not forgotten.

## 8. Smaller, real, and cheap

**open**

- `--sweep` accepts sticker points in nominal mode instead of hand-authored real decimals.
- `--print-schema` / `--print-anchors` filter by section or key; both are multi-KB blobs.
- `--break-even` under the verdict's own criterion, not only the deterministic tie band.
- Gatineau still has no published property-tax rate, so it is the one jurisdiction that
  says `source: none`.
- Whether the 200-word quick-sense cap should rise, now that disclosures are ranked and
  never dropped.

## 9. Measure the engine again

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
