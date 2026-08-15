# Seat-run dispatch record — run 24 (P10 closeout, P11 aligned ρ, sentence corrections)

Successor to run 23, which halted at task 1 with a SEAT_QUESTION — correctly, and the question
overturned a seat ruling. Its task 2 never started and rides here.

- date: 2026-08-15
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-15-sdd-run24-p10-closeout-p11-sentences.args.json` (sha256
  `0f965c3093b9b2c9ebd218d43cd9c87c5632e010e2b84ce9e30eed482bdf0af2`)
- models: opus/opus; load_bearing ×3; money_path: false ×3; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): committed HEAD `8c2de6e`; the tree carries P10's five
  UNTRACKED files; suites hde 191 + demoflow 668 with them present (604 committed + 61 P10 gates + 3
  glob-discovered contract parametrizations)

## Run 23's result: task 1(A) complete, task 2 never started, and the files are UNREVIEWED

**P10 resolved the construction EXACTLY, and the mandate's fallback would have been wrong.**
98-10-0003-01 publishes the Ottawa-Gatineau CMA with its 25 constituent CSDs as geography children,
closing exactly on the CMA total; 16 are Québec-side, dual-selected by SGC prefix AND census-tree
ancestry, agreeing on all 25. Four CDs contribute — Gatineau entire, all 7 Les Collines, 7 of
Papineau, 1 of La Vallée-de-la-Gatineau — **so no whole-CD union is this territory**, and the
whole-CD bracket amendment #12(A) ranked second does NOT enclose the exact headship (0.5234 sits
above its own 0.5218-0.5228 range). The fallback would have published a headship no member of its
own range produces. Aligned: 48,120 settled persons, **headship 0.5234, ratio 1.0248**, immigrant
demand leg +8.083%, ratio crossing 1.0 with both envelope ends above it.

**The probe corrected two of the SEAT's own figures** — §6's "10.35% person weight" is the MAINTAINER
weight (10.336%; the person weight is 10.770%), and the "≈345,000" conversion measures 347,875
against the 347,710 the resolved membership actually carries. Same class as the suite-count slips:
seat-authored numbers a probe contradicted. They are corrected in the spec at this run's fold.

**The five files are held UNCOMMITTED because they are UNREVIEWED** — the halt fired at the
implementer, so the pipeline's reviewer never ran. Task 1 here is that review. Arc precedent: T13b's
delivery and run 12's T22 mechanism were both held the same way.

## SEAT RULING — amendment #12(B) is REVERSED; the aligned ρ extraction is ORDERED

#12(B) cleared HORS_RMR's ownership rate on the ground that a band-uniform scaling of ρ cancels
EXACTLY in ED. That clearance was PREMISE-CONDITIONAL and P10 measured the premise FALSE: the
contamination is **not** band-uniform (spread **1.202 pp**, same-signed), and the arrangement is
adversarial by structure rather than chance — the most-contaminated band (25-54, +1.425%) is the one
D_native is built from, the least (75+, +0.223%) is the one S rides through `initialize_households`,
so δ_D − δ_S sits at or near the full spread. ED's numerator being a DIFFERENCE of flows amplifies
rather than averages it: +1.0% relative at D/(D−S)=1.4, +8.4% at 7.7, **+54% at 46**, unbounded near
flow balance, and with the multiplier turning NEGATIVE for D < S so enough amplification carries ED
across zero rather than rescaling it. Rank 1 is most-negative ED.

**Why "stand with an amended rationale" was refused:** the bounded-absolute argument is true and
irrelevant — rankings are decided in relative terms near zero, which is exactly where that bound is
vacuous. An input with unbounded relative error on the ranked axis, whose fix is a third repetition
of an extraction pattern this arc has already run twice against a cube the seat verified live
(98-10-0232-01, the identical maintainer-age × tenure cross at CD/CSD grain), is not something to
clear on cost grounds. #12(B)'s "cost with no signal" was a cost/signal judgment, not a data absence.

**Two scope fences in the mandate**, because both could be confused with this gate: it re-points
HORS_RMR ONLY (any other geography moving is a FINDING), and the sub-floor ordering constraint does
NOT bind it — re-extracting the 25+ bands at aligned territory is orthogonal to extending the curve
below 25.

## Sequencing, and why the spec waits

The values are UNREVIEWED, so no ruled table is written from them yet. Order: this run reviews P10
and builds the aligned ρ → the seat writes §6 at the fold (amendment #13: the #12(B) reversal, the
exact-membership construction ruled as THE construction, the reviewed immigrant values with their
envelope, and the two seat-figure corrections) → a later run regenerates P8 and updates the join
table, where the citation coupling reds and then goes green → then Task 27.

**Verified before pinning that order:** `run_p8.py` reads no ownership artifact (`grep` for
`ownership_by_geo_age` / `load_ownership_rates` / `ownership_rate` returns nothing), so P8's ratio is
maintainer-propensity from 0621/0622 and is INDEPENDENT of the ρ extraction. Had it not been, the
order would invert.

## Advisor discipline

- `ADVISOR RULING FIRED @p10-fork` — ruled (ii) order the extraction over (i) stand-with-amended-
  rationale, on the grounds that #12(B)'s clearance was premise-conditional and the premise is
  measured false in its worst arrangement; required the reversal carry its lineage explicitly (the
  QFE NAMED the band-varying caveat and graded it second-order; P10 MEASURED it and found the
  adversarial structure; the ruling follows the measurement); required the exact-membership
  construction be ruled as THE construction rather than the preferred one, since the fallback bracket
  does not enclose the answer; and required the independence check above before pinning the wiring
  order.

- run id: `wf_67962903-589` (dispatched 2026-08-15; task id w1htxvp3a)
- outcome: (appended at run close)

---

## ⚠ PROCESS INCIDENT — the seat created a second concurrent mutator by answering a message

**What happened.** Run 24's task-2 implementer (P11) messaged the seat with a dependency question:
had task 1 confirmed the membership? The seat answered **via SendMessage** — which RESUMES the
agent. That produced a SECOND live instance of the same agent, in the same worktree, while the
workflow's own instance was still building. Two producers then built the identical deliverable
concurrently: one as a separate `hors_aligned` module with `census.py` refactored beneath it, the
other as a ~630-line in-`census.py` extension referencing `_MAINTAINER_TOTAL_MEMBER` — a symbol the
first had just renamed to `MAINTAINER_TOTAL_MEMBER`, so the second's work was both duplicative and
broken against the tree it sat in.

**The law violated is the prefab's own:** "args.worktree names the ONE checkout this run may mutate
— tasks run SEQUENTIALLY, one mutating agent at a time (SDD mutating-reviewer law)". The seat has
been careful about this at DISPATCH (checking occupancy before every run) and then broke it with a
reply.

**Root cause, stated so it generalizes: a SendMessage to a workflow-owned agent is not a reply, it
is a resume.** The pipeline owns its agents' lifecycle; answering one out-of-band forks it outside
the sequencing the pipeline exists to enforce. The seat read the SendMessage documentation's "a send
resumes it from its transcript" and still treated the exchange as conversation.

**CORRECT HANDLING, binding from here:** when a workflow-owned agent asks the seat a question, do
NOT answer it with SendMessage. Either (a) let the pipeline's SEAT_QUESTION machinery carry it — a
halt is the channel, a message is not — and answer in the successor's mandate, or (b) `TaskStop` the
run and re-dispatch a successor carrying the answer. Both keep one mutator per checkout. The
question P11 asked was a good one and deserved an answer; the channel was wrong, not the asking.

**Damage: contained, and the agent's handling was exemplary.** The resumed instance detected the
collision, stood down rather than racing, surgically removed exactly its own block (explicitly NOT
`git checkout`, which would have destroyed the peer's work), moved its test file out of the suite,
verified zero residue by grep, confirmed both modules import, and left 43 tests passing. The
worktree carries the surviving producer's work only. Nothing of the peer's was lost.

**What survives from the stood-down instance — and it is worth keeping:** an INDEPENDENT live
reproduction of P10's ρ table, built with its own member resolution and coordinate builder (not
P10's machinery, not the peer's), from a 272-cell live pull of 98-10-0232-01. **Every figure matches
P10's table digit for digit** — all-ages +0.918%, 25-54 +1.425%, 55-64 +0.315%, 65-74 +0.304%, 75+
+0.223%, spread 1.2024 pp — and it adds the suppression-bound corner: **at the bound the spread
WIDENS to 1.212 pp, so the adverse structure holds at both corners.** That is a genuine second
measurement of the numbers about to be folded into §6, not a re-read of them.

Three further facts it measured, each reusable by the surviving producer:
- Membership re-derived live and clean: member 594 → 25 geoLevel-5 children, 16 Québec-side by SGC
  prefix matching `PINNED_QC_PART_CODES` exactly, each resolving to a unique geoLevel-5 member in
  98-10-0232-01, four contributing CDs (2480/2481/2482/2483) with three partial.
- **ρ-side suppression, correctly scoped to its own cube and field set** (the task-1 carry applied):
  13 withheld cells at 7 of the 16 subdivisions, ALL in the 75+ band, with the 7 derived from its own
  pull rather than borrowed from the settled side's 7 — different sets. Two subdivisions have exactly
  one field of a pair withheld, so field-wise discipline is load-bearing here, not hypothetical.
  Holes return `status: FAILED` with an empty `vectorDataPoint`, never a null.
- **A free external anchor for the cross-cube universe guard:** 98-10-0232-01's Québec all-ages row
  is 3,749,035 households / 2,245,600 owners — bit-identical to 98-10-0231-01's and to the literals
  already in `test_census_ownership.py`. Second anchor: CSD Gatineau 2481017 all-ages 126,480 /
  76,090 (explicitly NOT P10 §4b's 17,465/10,190, which are `Before 2016` cells from a different
  cube and member).

Its scratchpad is preserved at `scratchpad/p11/` — `raw0232.json` (the full 272-cell pull, saving
the surviving producer a live round trip), 18 numbered contract tests verified RED before backout,
and the removed derivation.

**The design fork needs no arbitration:** one producer remains, it chose the separate-module design,
and the stood-down instance's own review of the alternatives found that design compatible with every
constraint it had resolved — including the important one that `load_ownership_rates` must NOT be
re-pointed, because the committed T13b external-anchor gates pin HORS_RMR's shipped residual at
`rel=1e-12` and re-pointing would force an edit to ruled gates before §6 records the reversal.

**Fourth mm-spine harvest candidate of this arc**, and the first about the seat's own tooling
discipline rather than an agent's: *answering a workflow-owned agent with SendMessage forks a second
mutator into the run's worktree.*
