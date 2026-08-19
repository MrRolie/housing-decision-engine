# Seat-run dispatch record — run 29 (ruling U: the completeness contract)

- date: 2026-08-18
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` (unchanged from run 28;
  mm-spine HEAD has since moved `f4d7cca` → `aa70949`, the prefab itself did not)
- args: `2026-08-18-sdd-run29-ruling-u.args.json` (sha256
  `9e34adeb5261456aee7d674ae23f6d093063f56359330736ab16ad6259c01cd2`)
- models: opus/opus; load_bearing ×1; money_path: false
- preconditions, DERIVED at authoring time from the seat's OWN gate run: tree CLEAN at HEAD
  `e14e3f6`, hde **191** + demoflow **844**

## Why this is a successor and not a resume

Run 28 halted at SEAT_QUESTION in the fix stage. The pipeline does not resume fix-stage halts —
the ruling has to enter as a fresh brownfield mandate, because the tree it edits is now the
REVIEWED tree (Task 28 landed as `43961c7`), not the tree the halted agent was holding.

## The anti-transcription device, deliberate

**The mandate does not list the 31 member names.** They are accented French place-name tokens, and
a hand-typed list of them is exactly where a silent selection bug lives — the arc's depth-1 ladder
says a hand-typed value is not evidence. The implementer must DERIVE the set by computing the
cross-year intersection against the live feed, and then verify what it emitted against the
committed fixture. The mandate states the derivation's expected PROPERTIES (stable at 31, one
member present 6 of 12 years, zero regression, the 2020 anchor) and requires each to be reproduced
independently, with a STOP-and-report if any disagrees — a disagreement means the vintage moved
under the ruling, which is the seat's call.

Test case 5 exists for the one failure a derivation cannot self-detect: the constant is asserted to
be a subset of the fixture's real 2025 member set, so a transcription error in the constant reds
against committed bytes.

## What the fixture can carry, verified by the seat before dispatch

`ircc_pr_qc_slice.csv` holds the **COMPLETE real 2025 Quebec slice — 355 rows, identical row count
to the live feed's 2025 QC slice** — plus the 2026 partial (174 rows), and all 31 required members
appear in both. So every case runs against committed bytes; the live fetch is for the DERIVATION
only, never for the tests. This is what makes the ruling testable without planting a feed under
`data/` (which would itself flip the tripwire's live state from UNKNOWN to wired).

## Advisor discipline

- `ADVISOR RULING FIRED @run-28 fold — completeness contract (ruling U).` The ruling this run
  implements was advisor-reviewed at the fold that produced it; see run 28's record for the
  confirmation and the two precision corrections the seat adopted. No NEW ruling is set here — this
  mandate transcribes U and its measured derivation.

- run id: `wf_40941a59-2f6` (task `wajw5jyxd`)
- outcome: (appended at run close)
