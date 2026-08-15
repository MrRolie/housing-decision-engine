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

- run id: (appended at dispatch)
- outcome: (appended at run close)
