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
