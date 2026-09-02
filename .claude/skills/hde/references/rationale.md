# Rationale — why these rules exist

Anchors for the hot path's rules, so the rules can be re-earned or culled
when the engine changes.

- **Why only the CLI.** hde holds no session state, needs no protocol gating,
  and every consumer has a shell — an MCP layer would be pure context tax. The
  MCP server that existed until 2026-09-01 was removed as superseded; this
  skill plus the CLI is the whole surface.
- **Invent no values.** A plausible invented growth rate produces a
  confident-looking wrong verdict, the exact failure this engine exists to
  prevent. Every number you do not ask for becomes a default the engine
  echoes back with its source, which is the honest form.
- **A mortgage means nominal mode** (2026-09-02 dogfood, two persona runs):
  the real-rate level payment reported 27.9% and 30.2% housing-cost ratios
  where the lender's nominal payment gave 33.2% and 35.8% — the 32% breaches
  were hidden. The engine now warns; the routing lives in gate 3.
- **Warnings never dropped** (three threshold serves, 2026-09-02): the 1%
  real rent-escalation default was warned on in every run and dropped from
  every answer; at the Québec 0% real figure the threshold moved by about
  $120/month. The answer checklist reads the `[warning]` lines back as its
  first item because a rule stated inside a lane fired before the moment it
  had to be applied.
- **Band-first threshold sentences** (three serves): every serve copied the
  engine's crossing-first output into the user's text, which contradicts
  itself on the gap between the crossing and the band edge. The engine now
  emits a band-first `sentence` field; the lane quotes it.
- **The growth bracket on a threshold** (serve 1 of 3 scored 12/25): a 2%
  real growth stacked on a demographic prior, plus 1.2% maintenance, cancelled
  into a threshold that read "on the fence, leaning buy" where the skill's
  process yields "renting unless prices grow ~2%/yr above inflation".
- **The prior does not move a break-even** (serve 2): a Laval prior run was
  substituted for the growth sweep; it cannot move a deterministic crossing
  and encoded roughly flat drift, so "instead of flat prices" checked nothing.
- **One-sided uncertainty reads overconfident** (serve 2): with the renter's
  return vol at 0 the persona wrote that the simulation "overstates the
  uncertainty"; the like-for-like rerun widened the toss-up zone from $50 to
  about $300 of rent.
- **GDS, not TDS** (serve 1): the engine's ratio is housing cost over income
  with no other debts; the 44% cap the persona reached for is the TDS cap.
  The affordability warning now names all three thresholds.
- **The quick-sense cap** (serves 2 and 3): 200 words is unreachable with a
  mortgage, an income and a threshold together; the never-drop items were shed
  to make weight while the story path stayed. The cut order in
  `quick-sense.md` is the fix; the cap is stated once.
- **Cash on hand, not a percentage** (round-4 Montréal renter): a config
  assumed $97.3k of cash against a stated $95k; on the user's own numbers the
  mortgage was insured and the verdict flipped to a tie.
