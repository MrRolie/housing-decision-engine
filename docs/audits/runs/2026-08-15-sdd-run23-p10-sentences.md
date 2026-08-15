# Seat-run dispatch record — run 23 (P10 operand alignment + sentence corrections)

Both tasks execute spec amendment #12, which came out of the QFE re-triage discharge. Neither is in
the plan.

- date: 2026-08-15
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-15-sdd-run23-p10-sentences.args.json` (sha256
  `feb9770fb94252b8d9d527154d36a1f340efca690585ae3834e98f1a29203724`)
- models: opus/opus; load_bearing ×2; money_path: false ×2; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): tree CLEAN at HEAD `23f3928`, `./scripts/test-all.sh`
  green at hde 191 + demoflow 604; checkout free

## MEASURE-THEN-WIRE, deliberately split across two runs

P10 MEASURES the operand-aligned HORS_RMR values and wires NOTHING. The reason is the citation
coupling this arc built on purpose: `P8-immigrant-inputs.md` asserts its computed values against §6's
stated figures, and §6 currently marks HORS_RMR's two immigrant values SUPERSEDED PENDING RECOMPUTE.
Wiring inside this run would couple the note to numbers the spec no longer carries. So: P10 measures →
the SEAT writes the measured values into §6 at this run's fold → a later run regenerates P8 and
updates the join table, where the coupling reds first and then goes green. That is the mechanism
proving itself in reverse, and it is worth one extra run rather than hand-editing around it.

**Sequencing against Task 27, ruled:** the fix lands BEFORE the rankings emitter. HORS_RMR's immigrant
demand leg is presently ~8% pessimistic with a sign-crossing at 1.0; if 27 went first its goldens
would pin wrong-by-known-amount values and the fix would re-red them.

## What P10 must settle

The exact construction if it is resolvable — the contaminant is the Ottawa-Gatineau CMA's QUÉBEC
PART, defined at CSD level, so whole-CD subtraction errs in both directions; 98-10-0622-01 carries
CSDs, and a source publishing the QC part directly (43-10-0060-01 has the two halves at geoLevel 505)
beats any subtraction. Otherwise the whole-CD bracket with the variant selected by matching the ISQ
row it aligns to, not by feel: ISQ's Gatineau QC-part row is 355,971 TOTAL-population persons ≈
345,000 private-household at this tree's measured universe ratio, against census-side variants of
285,715 / 340,000 / 363,985. The bracket publishes as sensitivity either way.

It also measures the OWNERSHIP contamination — not to correct it, since #12(B) rules the cancellation,
but because the cancellation IS the claim: if the contamination proves materially BAND-VARYING rather
than near-uniform, the cancellation argument fails and that is fork-class, SEAT_QUESTION and stop.

## What the sentence task corrects (behavior changes nowhere)

`census._zero_support_note`'s premise is false for the committed extract — the sub-25 bands ARE
published and the same module reads them for headship — so the sentence becomes "the derivation spec
omits the two youngest published bands", a choice in our code rather than the data's silence. **The
behavior explicitly stays**, under #12's binding ordering constraint, and the mandate says that if the
implementer feels the pull to fix it, the impulse is the finding and not the action.

Every place the tree calls the convention's effect "optimistic" is corrected to the measured two-leg
statement — the numerator leg dominates by 30×-200× and BOTH legs push PESSIMISTIC for ED < 0 — with
ΔD stated as the order-of-magnitude bound it is. And `excess_demand.py` gets the yr⁻¹ relabel plus a
disclaimer that MIN_OWNER_STOCK is a structural floor, not a plausibility check calibrated to a frame
whose real minimum is 99,692.3.

## Advisor discipline

- `ADVISOR RULING SKIPPED @run-23 dispatch — no new ruling. Both tasks execute amendment #12 verbatim;
  the measure-then-wire split and the fix-before-27 sequencing were both decided in the @qfe-verdict
  FIRED call recorded against amendment #12.`

- run id: `wf_51deae84-be4` (dispatched 2026-08-15; task id wx1oodeok)
- outcome: (appended at run close)

---

## OUTCOME — HALTED at task 1 with a SEAT_QUESTION that overturned a seat ruling

1 agent. Task 2 (sentence corrections) NEVER STARTED and rides run 24. **P10's five delivered files
are UNREVIEWED — the halt fired at the implementer, so the pipeline's reviewer never ran — and the
seat is holding them uncommitted** (arc precedent: T13b's delivery, run 12's T22 mechanism).

**Task 1(A) came back COMPLETE, and better than the mandate asked for.** The mandate ranked an exact
construction first and a whole-CD bracket second; the probe got the exact one. 98-10-0003-01
publishes the Ottawa-Gatineau CMA with its 25 constituent CSDs as geography children, closing exactly
on the CMA total (1,488,307 = QC 353,293 + ON 1,135,014); 16 are Québec-side, dual-selected by SGC
prefix AND census-tree ancestry in 98-10-0622-01, agreeing on all 25. Four CDs contribute — Gatineau
entire, all 7 Les Collines, 7 of Papineau, 1 of La Vallée-de-la-Gatineau — **so no whole-CD union is
this territory.** Aligned: 48,120 settled persons, headship **0.5234**, ratio **1.0248** (envelope
0.5225-0.5236 / 1.0228-1.0264), immigrant demand leg **+8.083%**, ratio crossing 1.0 with both
envelope ends above it. Membership gate −0.752% against a 1.109% threshold from the six wholly-QC
CMAs; 18 of 48 settled counts suppressed at 7 tiny CSDs, bounded FIELD-WISE at ≤20 persons against a
36,665-person subtraction.

**The fallback my own amendment ranked second would have been wrong:** the whole-CD bracket does NOT
enclose the exact headship (0.5234 sits above its 0.5218-0.5228 range), so it would have published a
headship no member of its own range produces. Recorded because it is the second time this week a
seat-authored fallback prescription was refuted by the measurement it was meant to stand in for.

**Two of the seat's §6 figures corrected by the probe:** "10.35% person weight" is the MAINTAINER
weight (10.336%) — the person weight is 10.770%; and "≈345,000" measures 347,875 at the recorded
province ratio against 347,710 the resolved membership carries (local ratio 0.9842 vs 0.9773). Same
class as this session's suite-count slips: seat-authored numbers a probe contradicted. They land in
the spec at run 24's fold.

**THE HALT'S QUESTION overturned amendment #12(B)** — see run 24's record for the ruling. In short:
#12(B) cleared HORS_RMR's ownership rate because "a band-uniform relative scaling cancels EXACTLY",
and P10 measured the scaling NOT band-uniform (spread 1.202 pp, same-signed) in the structurally
worst arrangement — most-contaminated band feeds D_native, least feeds S — with ED's numerator being
a difference of flows amplifying rather than averaging it. The seat RULED the extraction.

- outcome: **HALTED (SEAT_QUESTION), task 1(A) complete but UNREVIEWED, task 2 never started.**
  Superseded by run 24 = [P10 closeout/review, P11 aligned ρ extraction, sentence corrections].
- `ADVISOR RULING FIRED @p10-fork` — recorded in run 24's record with its catches.
