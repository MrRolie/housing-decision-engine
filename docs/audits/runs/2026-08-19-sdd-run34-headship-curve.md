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
- outcome: **FINDINGS on task 34a** (1 LOW, seat-fixed at fold), 3 fix rounds; **task 34b never ran** —
  the pipeline halts on a FINDINGS verdict, so the golden re-mint is a successor. 9 agents,
  1,282,139 subagent tokens.

## Outcome — the curve LANDED as `c83595e`

Gate, seat's own run: **hde 191 passed / demoflow 1160 passed with exactly TWO expected failures**
(`test_golden.py`'s two diff tests). Golden re-mint deliberately deferred: task 35a moves artifact
provenance prose, so minting first would mint twice.

**CLOSURE VERIFIED BY THE SEAT, not transcribed: worst |residual| = 0.000e+00 on all 15 members
(14 published + the declared `(0,14,0)`) on BOTH arms**, at a 1e-6 construction tolerance. The
reviewer independently got `2227280.0` exact on fc for the base-year OwnerStock identity the seat
specified as the cheap check (`2,245,600 − 1,150 − 17,170`) and −9.3e-10 on fb. **All six legacy band
rates recompute BIT-IDENTICALLY on both arms** — the change is a pure within-band refinement, so the
+5 aggregate closure is preserved rather than re-argued. Two generator runs produced byte-identical
artifacts.

**The ranked order moved as ruled:** HORS_RMR 1→4 with a sign flip, LANAUDIERE 3→1, LAVAL 4→2,
LAURENTIDES 2→3, MTL_RMR 6→5, MONTEREGIE 5→6. **The 7/8 swap the design panel predicted did NOT
occur**, reported rather than smoothed over — consistent with the panel's own statement that its
magnitudes were probe-grade.

## THE ACCEPTANCE METRIC WAS THE SEAT'S, AND THE METRIC IS THE PART THAT WAS WRONG

The mandate required the largest single-age share of `D_native` to land in **14-18%**. Measured live:
MTL_RMR **79.81% → 26.72%** (fc), HHI **0.6585 → 0.1763**; HORS_RMR 49.13% → 12.20%. The collapse is
real and large. But the reviewer **could not reproduce the seat's own quoted BASELINE** ("committed is
65-77%") under any convention it tried, which makes the 14-18% target convention-dependent rather
than cleanly missed. **The seat took the design panel's explicitly probe-grade figures and wrote them
into a mandate as an acceptance gate** — that is the error, and it is the same class as citing a
figure without deriving it. The residual peak sits at **age 26, the ownership lattice's entry step**,
which spec §7 amendment #12 orders as the NEXT step and which this commit was forbidden to touch.

## Two false claims caught, neither of which reached the code

- **The LOW finding:** a new comment called the floor-probed-at-18 counterfactual "inside the target
  band" when 12.6% sits BELOW the 14-18% band the same block declares eleven lines above. Seat-fixed
  at fold — and the correction makes the attribution STRONGER, since fc undershooting means the floor
  accounts for more than the whole gap.
- **The implementer's report claimed the arm spread was inside the panel's predicted band**; live
  figures fall outside at both ends. The reviewer verified the substantive claim survives (the spread
  is real, non-common-mode, and the fb arm alone reorders ranks 2/3/4) and — the part that matters —
  **the live figures appear nowhere in `demoflow/**`**, so no false number landed in the tree.

## The cost carry run 33 left unpaid was PAID here

The suite went **270s → 205s** while GAINING an axis, because `_sweep_legs` is now configurable with
the full set as the committed default — the option run 33's mandate offered and did not get. **The
golden still mints from the full sweep and it is protected structurally, not by convention: a reduced
sweep CANNOT certify rank stability at all.** The reviewer mutated that fail-safe away and it returns
`true` off an unevaluated grid.

## Mutation battery — 4 pins, all real

The terminal end rule (a plain last secant reintroduces the `h(90)→h(100)` rise the pinned rule
refuses); the ED grid reading the LEG shape rather than the artifact default; the reduced-sweep
fail-safe; and the strict shape join. Also reproduced from the design's §5.8 expectations, unreported
by the implementer: the 2026-2029 negative D_native window (−25.1%/−19.7%/−15.5%/−13.2%) and the
negative first differences of h landing at exactly the four ages the design named.
