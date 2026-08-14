# Seat-run dispatch record — run 20 (P8 build, corrected gate)

Successor to run 19's task 2, which halted with a SEAT_QUESTION that caught a seat error in ruling
T's territory gate. The spec is amended (#11); this run builds the note on the corrected gate.

- date: 2026-08-14
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-14-sdd-run20-p8-build.args.json` (sha256
  `86aa606768661690533af298032bbd0606e2b5c1b13ee8579e2dcb9b90d7d0b7`), derived from run 19's task-2
  bytes with the gate section replaced and the rounding instruction inserted
- models: opus/opus; load_bearing ×1; money_path: false; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): tree CLEAN at HEAD `0e2f2bc`,
  `./scripts/test-all.sh` green at hde 191 + demoflow 427, checkout free. P9 is COMMITTED
  (`bb89161`), so its probe, note, index, fixtures, gate suite and pins rows are existing precedent
  rather than work to redo.

## What changed from run 19's task-2 mandate

1. **The gate section is replaced wholesale** with amendment #11's construction: the
   province-controlled share residual, using only ruling T's own two sources; the threshold DERIVED
   from innocent controls (the six wholly-QC CMAs, measured in the same construction) as
   max-innocent-residual plus a stated margin, with the derivation PRINTED; code axes recorded as
   Facts but explicitly not carrying the gate; census total population retained as a second
   diagnostic. The original wording is named as REFUSED so the implementer cannot reach for it.
2. **The ±5 rounding instruction is added** — bit-identity holds for the ruled Before-2016 triple
   but NOT cube-wide (popchar 10/11/14 differ by ±5 from independent per-cube rounding). The note
   asserts identity on the ruled triple and REPORTS the ±5 rows as measured. Without this the note
   would claim something its own data contradicts, and a regen gate would pin the falsehood.
3. Predecessor figures are given as "reproduce or contradict, and publish YOURS" — they are its
   measurements, not this run's.

## Advisor discipline

- `ADVISOR RULING SKIPPED @run-20 dispatch — no new ruling. The mandate executes amendment #11
  verbatim; the estimator, threshold-derivation method and code-axis treatment were all decided in
  the @territory-gate FIRED call recorded in run 19's record.`

- run id: `wf_c8156a9e-c7f` (dispatched 2026-08-14; task id wl6c2yo59)
- outcome: (appended at run close)
