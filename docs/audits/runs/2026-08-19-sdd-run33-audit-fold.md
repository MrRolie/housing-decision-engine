# Seat-run dispatch record — run 33 (fold the pre-PR audit gates)

- date: 2026-08-19
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea`
- args: `2026-08-19-sdd-run33-audit-fold.args.json` (sha256
  `2e561f62b4aec2949b95fba70ad725c8d537adadc0a079523dbd532904226385`)
- models: opus/opus; load_bearing ×3; money_path: false
- preconditions, DERIVED from the seat's own gate run: code tree as of `48513b3`, hde **191** +
  demoflow **1097**, tree clean

## The mandate POINTS at the evidence instead of retyping it

The three gate verdicts are COMMITTED at `docs/audits/{quant,stress,data}/2026-07-21-demoflow-tranche1.md`,
and the mandate names each finding by gate and number rather than re-transcribing its claim, evidence
and fix. **A mandate that retypes its own evidence is a transcription channel**, and this arc has paid
for that lesson repeatedly — most recently in run 29, where withholding 31 member names from a mandate
caught a real line-wrap corruption. Where the seat overrides a gate's proposed fix it says so
explicitly and the seat's ruling wins.

## Task order, and the seat says which part it MEASURED

1 identity coverage → 2 contract seams → 3 the sweep and a SINGLE golden re-mint. Tasks 1 and 2 change
the envelope and the record contract, so a golden minted before them would be re-minted anyway.
**Stated in the mandate as a precaution rather than a measurement** — run 31's task order was justified
by "several of these change what the artifacts contain" and the reviewer measured that FALSE. The seat
has not measured the byte deltas of tasks 1 and 2 here and says so in the mandate itself.
`tests/test_golden.py` is expected RED through tasks 1 and 2; the mandate tells the implementer to
report that rather than paper it, and forbids an early regeneration to make it green.

## RULED HERE: the non-finite band is a RUN-LEVEL TERMINAL (data F2)

The gate found the third producer/contract seam and **correctly refused to choose the fix**, calling it
amendment territory under the #16 precedent. The seat rules **option (b)**: a non-finite band endpoint
is a run-level terminal, not an UNKNOWN record.

The band is the CALLER's, injected — so a non-finite band is a caller/config defect, deterministic and
independent of the feed, which is the shape of a terminal and not of a per-indicator UNKNOWN. **The
module already ruled the sibling case exactly this way**: `_band_endpoints` raises a named terminal for
a NON-COERCIBLE endpoint because it cannot ride the record's float-typed band fields — and a non-finite
endpoint cannot ride them either under §7's `allow_nan=False`. Option (a) would send two near-identical
defects down opposite paths and would cost TWO spec amendments to accommodate a caller defect. **The
FINITE inversion case keeps its UNKNOWN(`malformed_band`)**, so §7c's "inverted band → UNKNOWN" stays
exactly true. Spec **amendment #17** is seat-authored at fold, in the same commit as the code.

## The generalizable instruction, worth more than any individual fix

All three seams share one shape — a PRODUCER and its CONTRACT disagreeing, green because no test
crosses them. The mandate therefore asks for the amendment-#16 test shape GENERALIZED: **assert that
every record each producer can emit validates against its contract validator, parametrized over the
full sub-case set.** That single property would have caught all three.

## Deliberately ABSENT: quant F2, the scope fork

The banded-headship-curve artifact in `D_native` (68–100% of it, ~2.5× the ranked signal, reorders all
eight rows) is **not in this run**. Landing an age-resolved curve is new modelling work and the
alternative is shipping with a row-level caveat — a call about what the deliverable is for, which sits
with the operator. The mandate names it as absent and forbids touching the headship curve or extending
the ownership lattice below 25 (spec §7 amendment #12's ordering constraint).

**Routing note:** the seat attempted to send this fork to the mm-infra master steering seat, as the
operator authorized. Three address forms were tried against the `ListAgents` row and none resolved —
**the peer channel is not reachable from this session.** Recorded as a property of the attempt, not as
a conclusion about the peer: the fork is surfaced to the operator directly instead, and this run
proceeds with everything that is not the fork.

- run id: `wf_0b8b9e78-cf5` (task `wkupo9nfr`)
- outcome: **APPROVE ×3, 0 unresolved** (fix rounds 2 / 1 / 1); 15 agents, 0 errors, 1,087,854
  subagent tokens. **The run was KILLED mid-flight by a session boundary and RESUMED** from 8 cached
  agents with its ~1,306 uncommitted insertions intact — see the resume note below.

## Outcome — folded 2026-08-19

**THE CRITICAL IS CLOSED AND THE HONEST VALUE SHIPPED.** All eight golden rows now carry
`rank_stable: false` — a five-axis verdict replacing a one-axis attestation. The sweep iterates every
declared `SWEEP_GRID` axis plus the join-table ratio override, and `constants.py`'s claim that "Task 29
perturbs the join table" is now TRUE rather than aspirational.

**Identity coverage closed on three fronts.** The CPM mortality basis is a thirteenth source entry,
digested through the §2-sanctioned public surface with **no private engine reach-in** (grep for
`_BASE_TABLES` / `_DATA_DIR` / `_base_cache` / `_SCALES` in `src/` returns comments only). The ruled
immigrant inputs and two previously-uncited money-path literals are inside `assumptions_hash`, which
moves `8b0779d17fcc2109` → `f39a8a240c60d777`.

**Spec amendment #17 landed in the same commit as its code** — a non-finite band endpoint is a
run-level terminal. Third amendment in a row to follow the #15 pattern.

## What the reviewers did that is worth keeping

- **The 33a reviewer ran a CLASS CENSUS on its own discrimination test and found the other half.** The
  test swapped only `_BASE_TABLES`; the sibling half is the improvement scale `_SCALES['CPM-B']`. It
  measured that leg too — digest moves, `assumptions_hash` does not, same pair. **A census that finds
  the half its own test missed is the motion this arc is trying to institutionalize.**
- **The golden RED was verified to be ENVELOPE-ONLY before it was accepted.** Against a live run at
  the golden's defaults: non-envelope bytes byte-identical for both documents, exactly one
  `source_hashes` key added, zero pre-existing entries moved, **no modeled number changed.** That is
  the difference between "the golden went red, expected" and knowing why.
- **A prior finding's fix landed STRICTLY STRONGER than what was proposed.** A re-typed year-range
  assertion was replaced by a test measuring a real run's RECORDED q consumption; the previous round's
  exact blind-spot mutant now REDs, and both directions on all three axes fire.

## Carries

- **`test_golden.py`'s `_match_golden` reports only the FIRST cause** (`data_vintage` tested first,
  if/elif short-circuit), so its message said "the DATA moved" while BOTH identity tokens had moved.
  Pre-existing; this fold is the first case where both move at once.
- **The internal layering gate is ONE-DIRECTIONAL.** `test_import_direction.py` scans the model trees
  for loader imports; nothing scans the reverse, and `constants.assumptions_hash` now imports
  `demand.immigrant_inputs` call-locally precisely to dodge the cycle its own comment names. No test
  would notice that import moving to module level.
- **A second declaration of the ownership floor survives** at `pipeline._ed_series`
  (`range(25, 101)` against `formation.OWNERSHIP_LATTICE_FLOOR = 25`) — the exact redeclaration class
  the new guard forbids for the two new choices. That guard is also literal-exact, so a whitespace
  variant slips past it.
- **RED-first has two disclosed holes out of seventeen new tests**, both stated in the implementer's
  report rather than papered: one passes on a clean tree by construction, one has a red condition that
  is a future upstream republish.
- **Spec §7b's enumeration sentence now understates the tree** — `assumptions_hash` covers
  CENTRAL_ASSUMPTIONS + SWEEP_GRID + MODEL_CHOICES + the immigrant-inputs join-table selection.

## Gate and cost

Seat's own run: **hde 191 / demoflow 1140 / both suites passed**, landed as `98c2f10` (code +
amendment #17) and `f5106aa` (the re-minted golden).

**COST CARRY, and it is the one the mandate itself warned about.** The demoflow suite went
**168s → 270s (+61%)**, because `_rank_stability` now runs ten legs where it ran two. The mandate told
task 3 to use a session-scoped fixture or make the leg count configurable with the full set as the
committed default; neither landed, and the golden tests still call `run_pipeline` directly. "A gate
slow enough that people stop running it" was the seat's own phrasing for the golden in run 31 — it now
applies to the sweep. **Not a defect in the fix; a bill the fix incurred, and it compounds with every
future task that calls the pipeline in a test.**

## Resume note — the run was killed and recovered

A session boundary killed this run mid-mutation with ~1,306 uncommitted insertions in the worktree and
8 of 15 agents journalled. Assessed before resuming: HEAD unmoved, the modified set coherent with
tasks 33a/33b rather than torn. Resumed from the cached prefix; the cached agents replayed and the run
completed. **The arc's standing rule — agents commit NOTHING, the seat commits after its own diff
review — is what made this survivable**: a killed mutator left its work in the worktree for the
resumed run to continue, and no half-finished state ever reached a commit. The rule's cost is exactly
that recovery window; its benefit is that the window is recoverable.
