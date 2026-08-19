# Seat-run dispatch record — run 31 (ledger close + Task 30 golden artifacts)

- date: 2026-08-19
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea`
- args: `2026-08-19-sdd-run31-ledger-golden.args.json` (sha256
  `57dcb6de321744d4689c62af540d07f8a45e5b3be08878188b072be615eb50c6`); Task 30's plan bytes extracted
  MECHANICALLY; args + dispatch script emitted from ONE object so they cannot drift
- models: opus/opus; load_bearing ×2; money_path: false
- preconditions, DERIVED from the seat's own gate run: tree CLEAN at HEAD `37f4dc7`,
  hde **191** + demoflow **1085**

## Task order is load-bearing

Task 1 closes eight ledger defects and **changes what the artifacts contain**; task 2 generates the
committed golden. Reversed, the golden would pin the defects and then red when they were fixed.

## What the ledger task is, and why it is not cleanup

Five of its eight items live in code a review **already APPROVED**, and two were proven pre-existing
at HEAD. The headline: **two of ruling U's three completeness clauses pin the first one, so the first
is unpinned** — mutating the province-wide month check to a bare count survives the FULL suite (58 /
53 passed), and `test_closed_year_check_is_vocabulary_bound_not_a_count` is killed by the
modeled-member clause rather than by the rule in its own name. Same class as the §6-coupling defect
amendment #14 recorded: a guard whose test passes for the wrong reason.

**One item is the SEAT's own defect and is labelled as such in the mandate:** `HORIZON_YEARS` has no
Tranche-1 consumer and its test asserts a module literal against itself — carried in because the
run-30 mandate transcribed the plan's named test cases without auditing them.

## Advisor discipline

- `ADVISOR RATIFY FIRED @run-31 dispatch — ledger-before-golden order + mandate corrections.`
- `ADVISOR RULING FIRED @run-31 dispatch — nullability enumeration (amendment #16).`

The advisor caught **two places where the seat's own mandate delegated a SPEC-CONTRACT choice
in-lane**, the exact fork-class this arc refuses:

1. **L2 directed an implementer to widen a spec-closed enumeration.** §7c enumerates the nullable
   reasons as a closed set; adding `duplicate_indicator` moves that enumeration, and run 29's own
   mandate had forbidden the sibling act ("do NOT add a Reason member — spec-closed, fork-class").
   Ruled: the direction is obvious (a duplicate record has no honest measurement — the identical
   r7-F2 logic that put the other four in), so **the seat authors amendment #16 at fold, in the same
   commit as the code**, and the implementer does the code change plus the seam test. Draft script
   held ready, the amendment-#15 pattern.
2. **G3 delegated the golden's determinism contract**, and one of the two options was not reachable
   in-lane anyway — the envelope allowlist is spec-closed and the artifacts walk raises on undeclared
   positions, so recording `now` in the document is amendment territory. **RULED: one pinned `now`
   shared by generator and test, with the generation path COMMITTED**; normalizing the diff is
   REJECTED because byte-equality is the golden's entire value. Recording `now` in the document is a
   future amendment for when the first real input lands.

Also adopted: **G1's fork pre-ruled DECLARED-ABSENT** (a fixture-backed golden would stamp a non-live
vintage into a committed artifact and muddy the data-vs-code attribution the task exists to protect);
**L4's expected outcome stated as REMOVAL**, since "or give it a consumer" invites an invented
consumer that makes dead weight look load-bearing; and **the ledger was sampling itself** — two
charter blockers were missing and are now L7/L8, because a ledger task that leaves unlisted items
open forces the PR gate to re-litigate what "closed" meant.

**A seat premise was VERIFIED before being written in as fact** (the run-26 class): G4 claimed
`extracted_at` was already settled. Checked — run 30's B6 fix made it per-source DECLARED provenance
read from each artifact's `_provenance`, there is NO wall-clock read in `pipeline.py` or
`artifacts.py`, and the live emitted values genuinely differ per source (2026-07-21 / 2026-08-08 /
2026-08-15). Stable, belongs in the golden, and the mandate says so as a verified fact.

- run id: `wf_0dee300e-e08` (task `wjmtlvrmg`)
- outcome: **APPROVE ×2, 0 unresolved** (fix rounds 2 / 0); 9 agents, 0 errors, 1,262,256 subagent
  tokens, 3h25m

## Outcome — folded 2026-08-19 as `cab9c95` (ledger) and `867ad91` (golden)

Gate, seat's own run: **hde 191 / demoflow 1097 / both suites passed.** Tree clean, pushed. Spec
amendment #16 landed in the SAME commit as L2's code, the #15 pattern.

**A SEAT PREMISE WAS MEASURED FALSE, and it is recorded because it is the premise that set this
run's task order.** The mandate sequenced the ledger before the golden because "several of these
change what the artifacts contain". **None of them do.** The reviewer emitted both documents from
pristine-HEAD sources (`git archive HEAD` into a canaried shadow) and from the working tree and got
byte-identical files — `rankings.json` sha256 `8a8fccf0…`, `tripwire_baseline.json` sha256
`f3abec66…`. Mechanically: L2 is unreachable on the committed tree, L3 unreachable by construction,
L5 touches only the CLI print, and the run log is not a document field, so L8 cannot reach the golden
either. **The ordering was harmless and the reasoning behind it was wrong** — the golden would have
been the same bytes either way.

**Every ledger item discharged with mutation evidence, not assertion.** L1: the province-wide clause
is now `_months_are_the_closed_vocabulary`, and the bare-count mutant AND the delete-the-wiring
mutant both red — each on a test whose name describes the rule it defends, which was the whole
defect. L2: the seam is **live, not merely latent** — `pipeline.py:501` appends `check_registry`
output into the results that `tripwire_record` emits, so a duplicate record really would have failed
its own contract validator. L3: door closed, and the class census found NO open sibling (it checked
`formation.py:125/158`, `listings.py:73/76`, `init.py:190`, `tripwires.py:582` and correctly
classified `pipeline.py:715` as a clamp rather than a lookup). L4: `HORIZON_YEARS` and its vacuous
test removed, zero references repo-wide. L5/L7/L8 pinned; L8's note now rides all five
frame-carrying branches, each mutation-killed individually.

**Class census on `NULLABLE_REASONS` is worth keeping:** all five members are individually pinned by
drop-one mutation, but **no exact-membership pin of the frozenset exists anywhere** — the set is not
co-deletable member-by-member, yet nothing asserts the set itself. Recorded rather than fixed; the
audit gates should decide whether that matters.

**LIVE-SURFACE CHANGE nothing in the ledger asked for, fail-safe direction.** `evaluate_tripwires`
now builds the data vintage, so `demoflow tripwires` REFUSES with a named `LoaderError` (exit 1) if
any of the 12 declared inputs is absent or pin-drifted, where it previously listed regardless. It
still lists normally when they are intact — **seat-verified live**: identity `8b0779d17fcc2109` and
all 12 digests print above the rows, matching the emitted `tripwire_baseline.json` exactly. One
review aside stated this as "now refuses the whole listing" without the conditional; the live
measurement is the accurate one.

**The golden implements the ruled contract exactly.** One pinned `now` (2026-12) shared by generator
and test; the generation path committed as SOURCE (`scripts/gen_golden.py` + `golden.py`) because
that file is the artifact's only provenance for the clock; nothing normalized out of the diff; the
data source declared rather than ambient; and `artifacts/README.md` tells a future reader which kind
of red they are looking at and names the amendment to take when the first real input lands.

## Carries

- **The canonical gate runs NO linter**, and `pyproject.toml` configures none. Surfaced by a
  120-char line at `demand/immigrant_inputs.py:31` against the file's ~100 ceiling, which nothing
  catches. Cosmetic today; it is the absence of the check that is worth recording.
- **Amendments are placed BESIDE the text they amend, not in numeric order** — #16 sits at spec:835
  next to the nullability enumeration it widens, #15 at spec:850 next to the completeness text.
  Deliberate and more useful for a reader, but a reader scanning for amendment order should know.
- **PLAN DEFECT IN THE AUDIT GATES THEMSELVES, caught before it cost a cycle:** Task 31 writes
  `subagent_type: mm-spine:quant-financial-engineer` and warns in-line that "a bare name fails to
  resolve"; Task 33 uses the prefix; **Task 32 writes `subagent_type: stress-tester` BARE** and would
  therefore fail to resolve. The gate that hunts for guards that cannot fire could not itself have
  fired.
