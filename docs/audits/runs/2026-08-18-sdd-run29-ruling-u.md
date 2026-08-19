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
- outcome: **APPROVE, 0 unresolved**, 1 fix round; 5 agents, 0 errors, 642,397 subagent tokens, 79 min

## Outcome — folded 2026-08-18 as `c35d908`

Code AND spec amendment #15 in ONE commit, per amendment #14's standing rule. Tree clean, pushed.

**The withheld-names device earned itself on its first use.** The mandate deliberately did not list
the 31 members; the implementer derived them and recorded that **its emitting script's first pass
wrapped a line INSIDE `"Ottawa - Gatineau (Quebec part)"`** — the exact silent-selection failure the
device exists to prevent, caught because the constant is checked back against committed fixture
bytes rather than against a human's reading of it. **Generalizes: withhold the values a mandate
would otherwise have the implementer transcribe, and make the derivation prove itself against
committed bytes.**

**Verified independently at three levels, not one.** The reviewer re-fetched the feed live (sha256
`d5af3237…`, vintage did not move) and reproduced EVERY seat fact: intersection 31, union 32,
Hawkesbury in exactly {2016, 2017, 2019, 2020, 2021, 2025} and absent in the other six; 2020 =
25,005 with all 31 published; 2025 = 60,010 / pair 45,895 over 24 cells; Saguenay deltas −60..−675
with no verdict flip; 2025 = 32 members with 11 interior-gapped. It also proved the committed fixture
is set- AND ORDER-identical to the live feed for both years. **The seat then re-derived the constant
itself against the live bytes — symmetric difference empty in both directions.**

**Mutation: ten mutants, ten killed** — five mandated (delete the required clause → kills the
CRITICAL case plus two more; drop one member → kills the fixture-binding case; plus the log and
partial-year mutants) and five reviewer-authored. The sharpest is **subset → equality, which fails
10 tests**: the documented `<=` asymmetry is genuinely pinned, not just documented.

**GATE FIGURE CORRECTED. The reviewer reported demoflow 849; the seat's own run of the final bytes
gives 851** — hde **191** + demoflow **851**, "both suites passed", re-run again after the seat's own
edits. The gap is exactly the two tests the reviewer's fix round added AFTER its gate run
(`test_a_wholly_absent_member_set_is_named_not_read_as_pre_era_silence`,
`test_an_intact_partial_year_reports_the_member_gap_without_claiming_its_cause`). Not a defect in the
work — but it is the transcribed-figure class again, and **851 is the figure of record.**

**Seat precision fix at fold.** The landed derivation comment called 25,005-vs-60,010 "a ~58% COVID
collapse" — that compares 2020 to 2025, four years later. The collapse is **38% against 2019's
40,315**; 58% is the gap to 2025. Both now stated as the different claims they are, in the comment
and in amendment #15. Small, but derivation comments in this arc are load-bearing and a loose one
is the seed of the false-why class run 28 corrected twice.

**What the fix round resolved (reviewer's round-1 findings, all verified closed):** the log was
silent on the MAXIMAL truncation (a province with zero rows has no member to call absent, so a
member-by-member note missed it — now named, with the other-province row count quoted as the
evidence that publication order cannot explain it); and the note made a FALSE CATEGORICAL claim on
an intact partial year. That second fix carries the best measurement of the run: **IRCC genuinely
fills its member set over a year's first months — 24 of 31 required members reporting after Jan, 29
after Feb, 30 after Mar and Apr, 31 only from May.** So the note now reports the gap always and
claims a CAUSE only at twelve-of-twelve months. A line that called the January state "truncation"
would have been asserting something false about the feed.

## OPEN DEFECT for the ledger — pre-existing, NOT introduced here

The reviewer proved these survive at HEAD as well as in the working tree, so they are not findings
against this task, but they are real and they are ours:

1. **`test_closed_year_check_is_vocabulary_bound_not_a_count` does not test what it names.** Mutating
   the province-wide month check from vocabulary equality to a bare `len(set(months)) != 12` survives
   the FULL suite at both trees (58 / 53 passed). The test is killed by the modeled-member clause,
   not by the vocabulary rule in its own name.
2. **Deleting the province-wide month clause outright also survives at both trees.** The first of the
   three completeness rules is currently unpinned; clauses two and three carry it.

Same class as the §6-coupling defect amendment #14 recorded: a guard whose test passes for the wrong
reason. **Owner: the next run that touches `tripwires.py`; MUST close before the Tranche-1 PR.**

## Carries

- **`test_ircc_loader.py` was in the mandate's file list and went untouched** — the loader's new
  public constant has no pin in its own test module. Coverage is real (bound to fixture bytes from
  `test_tripwires.py`), so this is placement, not absence.
- **`closed_plan_years(frame, province=…)` applies a Quebec-shaped required set to whatever province
  it is handed**, so a non-Quebec caller gets permanent UNKNOWN. Fail-closed and now documented; a
  pre-existing shape (`MODELED_CMAS` already had it) that this change makes more visible.
- **`_member_set_note` is wired only into the empty-closed-years branch**, so a truncated 2027 while
  2026 is closed is never named. Bounded by the freshness gate and by `year = max(years)` selecting
  the honest year — not a verdict risk, but the third unchecked sibling of the discriminator's cause
  set.
