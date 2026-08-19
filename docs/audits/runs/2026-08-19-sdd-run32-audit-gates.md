# Seat-run dispatch record — run 32 (the three pre-PR audit gates)

- date: 2026-08-19
- **shape: NOT the sdd prefab.** These are read-only AUDITS, not implementation tasks, so the
  prefab's implement → review → fix shape does not fit. This run is a custom fan-out: three
  independent gates in PARALLEL via `agent(..., {agentType})`, which keeps the work inside the
  sanctioned workflow lane while using the specialist agent types the plan names.
- script: `2026-08-19-sdd-run32-audit-gates.script.js`, committed beside this record, sha256
  `ee130838da79250635a61b12f4486bb213a6d1d2ecc76facbdf1e20ecec3a62a`. **There is no args.json — the script IS the args**, so it is committed to keep the arc's
  reproducibility convention from lapsing just because the shape changed.
- agent types: `mm-spine:quant-financial-engineer`, `mm-spine:stress-tester`,
  `mm-spine:data-integrity-validator`
- preconditions, DERIVED from the seat's own gate run: code tree as of `aaf8e1f`, hde **191** +
  demoflow **1097**, tree clean

## The gates were MIS-AIMED in the plan, and that is why they are re-framed here

All three plan tasks say "audit everything in *this plan*, against the implemented code" and list the
plan FIRST among the reads. **The plan is no longer the governing description of this system** — the
spec has since taken amendments #7–#16 and rulings A–U, several of which refuted plan premises
outright. An auditor pointed at the plan would grade correct code against superseded requirements and
report drift where the tree is RIGHT and the plan is WRONG. Every gate now gets: the SPEC governs;
the plan is historical; classify each divergence as plan-superseded / code-defect / genuine-drift;
the ruling ledger and run records are INPUTS, and a finding that restates a recorded ruling is
DERIVATIVE.

**Task 32's own dispatch could not have fired.** Plan Task 31 writes
`subagent_type: mm-spine:quant-financial-engineer` and warns in-line that "a bare name fails to
resolve"; Task 33 uses the prefix; **Task 32 writes `stress-tester` BARE.** The gate that hunts for
guards that cannot fire could not itself have fired. Fixed here.

## What the seat handed them that the plan could not

The plan predates the findings. Each gate carries named targets from the ledger: the aligned-ρ
operand question (dead code until run 30 wired it — does consuming it move ED's sign or the ranking
order?); the band-entry construction that replaced the uncited `* 0.1`; the one-sided suppression
envelope (`±2.5 × n_cells` centres a `--` cell's [0,5] interval on a contributed 0, but suppression
can only ADD); the unpinned `NULLABLE_REASONS` set; and **ruling U's presence-bar inference**, handed
to the data gate as the single most valuable thing it could refute.

**A seam class is named and the gates are told to find the third instance.** Two producer/contract
pairs have disagreed while staying green because no test crossed them — the 64-vs-16 assumptions-hash
width, and `check_registry` emitting a record its own validator rejected. Both fixed.

## Advisor discipline

- `ADVISOR RATIFY FIRED @run-32 dispatch — gate fan-out shape + schema seam.`

The advisor ratified the fan-out (and said not to add verify stages: **the seat is the verify
stage**) and caught four things, one of which is the seam class **inside the seat's own dispatch**:
the preamble told gates to classify into "exactly one of" THREE classes while the schema enum carried
FOUR — `spec-gap` existed in the contract and nowhere in the prose, and the schema forced the field
on findings that are not divergences at all. Two committed vocabularies, one wider, green because
nothing crossed them. Now defined explicitly. Also adopted: `decision_critical` made REQUIRED (the
one field the plan's original framing demanded, and optional fields get omitted); an explicit
CONCURRENCY line, since this is the arc's first parallel execution in the live checkout and three
simultaneous suite runs in one venv is contention plus wasted minutes; and the HEAD pin rephrased as
CODE-STATE, because committing this very record moves HEAD before any gate reads the tree.

## Fold discipline, pre-stated so a round-1 green cannot quietly become "gates done"

1. The seat REPRODUCES every CRITICAL and HIGH before folding it.
2. **A missing gate is NOT RUN** — re-dispatch it; never grade on 2 of 3.
3. Surviving decision-critical findings become a PIPELINE run, because fixes are mutations and get
   the commit-nothing / review shape rather than in-lane patching.
4. Then re-dispatch THAT gate once on the folded bytes — the plan's own Step 5, and the
   loop-until-dry ethos: a round is dry when it yields only refuted or derivative findings.
5. The seat writes the three audit documents at the plan's paths; **the gates return verdicts only
   and write nothing.**

- run id: `wf_19bc200b-298` (task `wre987dr2`)
- outcome: **PROCEED-WITH-MODIFICATIONS ×3**, none dry; 20 findings (2 CRITICAL, 3 HIGH, 9 MED,
  6 LOW); 3 agents, 0 errors, 975,646 subagent tokens, 47 min. Verdicts written to
  `docs/audits/{quant,stress,data}/2026-07-21-demoflow-tranche1.md`.

## THE GATES EARNED THEIR SLOT. Tranche 1 does not ship as it stands.

**TWO GATES INDEPENDENTLY FOUND THE SAME CRITICAL, and the seat has now REPRODUCED it.**

`rank_stable: true` ships on **all eight rows of the committed golden** as a verdict over **ONE of
FIVE declared robustness axes.** Confirmed structurally by the seat before measuring anything:
`_rank_stability` (`pipeline.py:890`) iterates only `SWEEP_GRID["q_live_per_year"]`, while
`SWEEP_GRID` declares FOUR axes and `constants.py:229-232` states as FACT that a fifth exists —
"Task 29 perturbs the join table with a uniform override spanning
`CONSTANTS["immigrant_ownership_ratio_sweep_span"]` = [0.155, 1.033]". **No such code exists
anywhere in the tree** — `sweep_span` appears only in `constants.py` and `test_constants.py`, never
in `pipeline.py`.

**This is the THIRD PRODUCER/CONTRACT SEAM**, the class the dispatch explicitly told the gates to
hunt after the 64-vs-16 assumptions-hash width and the `check_registry`/validator mismatch. It is
also the worst of the three, because the other two would have failed loudly the moment they were
exercised; this one ships a false all-clear in a committed artifact and announces nothing.

**SEAT REPRODUCTION**, out-of-tree harness patching `resolve_immigrant_inputs` at the public entry
point, nothing in the worktree touched. Harness validity established first: the unpatched central run
reproduces the committed `rankings.json` EXACTLY, so the legs below count.

- **uniform ratio 0.155 → 8 of 8 geographies change rank, and every mean ED FLIPS SIGN.** HORS_RMR
  1→4 (−0.000290 → −0.002180), LAVAL_RA13 4→1, MTL_RMR 6→2, MTL_ISLAND_RA06 8→5, QC_RMR 7→8,
  MONTEREGIE 5→3, LAURENTIDES 2→6, LANAUDIERE 3→7.
- **uniform ratio 1.033 → 4 of 8 change rank.**
- **Union over both DECLARED endpoints: every one of the eight rows moves.** The honest value of
  `rank_stable` is therefore **`false` on every row.**

Spec basis is double: §7b's run contract (codex r8-F1) mandates that band endpoints enter through the
sweep grid, and **§6 amendment #12(C) LEANS on this override existing** for its containment argument
("a `rank_stable` verdict is evidence, not proof, on this axis"). It is not evidence at all — the
axis was never evaluated.

## The second decision-critical finding puts the ranking ORDER in question

`D_native` is **68–100% band-step artifact.** `pipeline.py:804` materialises the BANDED headship
curve at single years of age — the reuse `census.py:778-779` explicitly forbids in its own words
("It is NOT an age-resolved rate ... must land an age-resolved curve rather than reuse this one")
and which spec §7 amendment #12 quotes as binding. Measured share of `D_native` that is band-step
mass: MTL_RMR 100.00%, MTL_ISLAND_RA06 100.00%, LAVAL_RA13 99.40%, HORS_RMR 78.32% — and the spread
across the ranked set is ~30pp, so it is **not common-mode**. Scale: MTL_RMR's 2026 step mass is
0.689%/yr against a committed mean reference ED of 0.277%/yr — **the artifact is ~2.5× the entire
ranked signal.** A perturbation probe (monotone piecewise-linear through the same band values)
reorders every row and flips rank 1's sign.

**And run 15's reopening condition SILENTLY FAILED.** That record wrote "it reopens when Task 29
lands an age-resolved headship curve"; Task 29 landed WITHOUT one, and nothing reopened. A condition
whose trigger nobody checks is not a condition — this is the same class as the mis-aimed audit gates,
one layer down.

## What the gates CONFIRMED, so a later round does not re-spend on it

- **RULING U's presence-bar inference SURVIVED its strongest available falsification**, probed
  independently by TWO gates, one of them against three real Wayback vintages of the IRCC feed. The
  residual measures NARROWER than the seat's own record claimed. The inference stands as an
  inference — evidence, not proof — and the record's honesty about it was the right call.
- **All six cohort oracle fixtures pass independent recomputation** from the spec §5 branch algebra
  alone using exact `fractions.Fraction`. A wrong oracle would have pinned a wrong implementation;
  they are right.

## Disposition

**F1 (the sweep) is NOT a fork — it is code failing its own committed, operator-ratified contract**,
and it goes to a fix run: wire every declared axis plus the join-table ratio override, set
`rank_stable` from the union, re-mint the golden (all eight booleans flip to `false`, which is the
honest state), and record in `artifacts/README.md` that the flag is a five-axis verdict. The only
fork would be RETRACTING the contract instead, which would require `constants.py:228-232` and spec §6
amendment #12(C)'s containment sentence to be struck in the same commit.

**F2 (the headship curve) IS a scope fork and is going to the operator / mm-infra steering**, because
landing an age-resolved, population-weight-conserving headship curve is new modelling work, and the
alternative — shipping rankings whose order is ~2.5× artifact with a row-level caveat — is a claim
about what the deliverable is for. The seat does not rule that alone.
