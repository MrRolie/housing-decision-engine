# Seat-run dispatch record — run 34 (operator ruling V: the age-resolved headship curve)

- date: 2026-08-19
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea`
- args: `2026-08-19-sdd-run34-headship-curve.args.json` (sha256
  `bdfed9c5a3122e78759b8f503733a60918ea72a3d83ca86347d43452717ceb38`)
- models: opus/opus; load_bearing ×2; money_path: false
- preconditions, DERIVED from the seat's own gate run: code tree as of `1a5eb41`, hde **191** +
  demoflow **1140**, tree clean

## This mandate POINTS at a committed design, it does not carry one

`docs/research/2026-08-19-headship-curve-design-panel.md` is the build specification — a five-agent
panel (constraint map → three independent designs → a judge that RE-DERIVED each from its own text
rather than accepting its claims), committed at `bd89400`. The mandate names the decision, layers the
seat's rulings on top, and sends the implementer to §5. Same discipline as run 33's: **a mandate that
retypes its own evidence is a transcription channel.**

## The decision, and the criterion it turned on

**P1's chassis — exposure-abscissa monotone cumulative Hermite, terminal rule pinned, with P2's and
P3's gate discipline grafted on.** It won because **its member closure is ALGEBRAIC, not numerical**:
the member endpoints ARE interpolation knots, so the sum telescopes exactly, independent of tangent
rule, refactor, seed, or convergence. Measured 0.0 on all 14 members under both arms and across 200
perturbed re-extracts. The alternatives conserve at ~1e-11 *because their solves converged today*.

## Seat rulings layered on the design

- **The naive 14-member STEP curve is REFUTED and must not be built** — measured the WORST option
  available (horizon-mean D_native +54.6%, 44-50% at the single age 25). Consuming granularity without
  a shape rule makes the artifact worse. **The minimal-change lens earned its slot by refuting
  itself**, which is exactly what an adversarial lens is for.
- **Compute your own refutation figures; never transcribe the design's.** The judge could NOT
  reproduce one of P1's quoted numbers and said so.
- **Use the shape-invariance identity as the cheapest closure check:** base-year OwnerStock under any
  member-closed curve is `2,245,600 − 1,150 − 17,170 = 2,227,280` exactly. Verify EARLY.
- **The under-15 zero is a POSITIVE BOUND, not an absence claim** — closure pins it below rounding
  scale, so 0.0 is the only admissible value. Never "the table is silent"; never "proved zero".
- **The osculatory overshoot at 74/75 is pinned by test, not papered and not clamped** — the design
  measured that a hull clamp produces `h(15) = −0.0061`.
- **The seat's own dispatch was CORRECTED by the panel and the correction rides in the mandate:** the
  members are NOT all five-year. Twelve are; `75 to 84` is ten-year and `85+` is open-ended, which is
  why Sprague/Beers/Karup-King-Newton were named and refused by all three designers.

## The cost carry, handed to this run because this run compounds it

Run 33 took `_rank_stability` from two legs to TEN and the demoflow suite from **168s to 270s (+61%)**.
Run 33's mandate asked for a session-scoped fixture or a configurable leg count; **neither landed.**
This run's design adds a `headship_shape` axis, making it twelve. The mandate therefore assigns the
bill explicitly: land one of them, and the committed golden must still be minted from the FULL sweep.

## What is expected to MOVE, declared so a re-mint cannot hide an unrelated change

The ranked ORDER, including a rank-1 sign flip and a 7/8 swap; `assumptions_hash`; the headship
artifact digest; and ~240 headship references across four test modules — contracts to rewrite
deliberately, not breakage to route around. **The ordering constraint is physically enforced:**
extending the ownership floor downward in the same commit takes out the headship generator with a
`LoaderError`.

**The judge's ranking magnitudes are probe-grade and it says so** (raw ISQ in place of P_resident,
~7% scale; ranks 2-4 unresolvable at its fidelity). A divergence THERE is expected and is not a
failure. A divergence in CLOSURE is.

- run id: `wf_f86aee90-ce0` (task `w620fb07v`)
- outcome: (appended at run close)
