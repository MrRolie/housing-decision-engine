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

- run id: (appended at dispatch)
- outcome: (appended at run close)
