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

---

## OUTCOME — CLOSED CLEAN: APPROVE, 1 fix round → LANDED at `44f3519`

5 agents, 0 errors. Whole-set verify PASS with a full boundary ledger. Suites 191 + **494**,
seat-verified stable across repeat runs with zero skips.

**The note regenerates BYTE-IDENTICALLY against live WDS and both pinned workbooks today** (the
reviewer reran the real producer with `OUT` rebound to scratchpad, sha `c7f3f51e…`), and the three
ruled pairs re-derive from the reviewer's OWN metadata walk and OWN coordinate builder. The
mutation-battery boundary census fired all 18 mutants at their intended guard, zero mismatches.

**Two findings the run made that strengthen the gate beyond its arithmetic:**
1. The six innocent controls join on EXACT classification codes, looked up under the ISQ workbook's
   own `Code` axis — a census code the workbook does not publish REFUSES the run rather than
   printing.
2. The RMR workbook DECLARES its delineation in its own header note — "selon le découpage
   géographique et la dénomination du Recensement de 2021" — while the RA workbook declares an
   ADMINISTRATIVE one dated 2025-07-01. That is the real justification for the calibration: the six
   controls are census territories by the publisher's own statement, and the two under test are not.
   The gate's design was sound for a reason better than the one the amendment gave.

**Threshold derived, not inherited:** 1.586% = max innocent |residual| 1.269% (Trois-Rivières) +
25% margin. RA06 +0.279%, RA13 +0.611% — both PASS, and both sit inside the innocent range, with 3
of 6 settled territories further out in absolute value.

**What the note refuses to claim is the best part.** The SIGNED decomposition does not run the same
way (innocent span −1.269% to +0.325%, 4 of 6 negative; both under test positive; LAVAL_RA13 above
every positive innocent control) and it is PUBLISHED rather than hidden inside the absolute value,
deliberately un-attributed because six controls cannot fix a direction. §4c states what the gate
CANNOT do — passing does not establish that a census division IS an ISQ région administrative, it
fails to refute it at this resolution — and prints the trip point in PERSONS (31,976 at RA06, 6,987
at RA13) so a reader can price the claim rather than take it.

Both seat instructions landed exactly: bit-identity asserted on the RULED triple only with the four
±5 rounding rows reported as measured; floor-gate coverage stated honestly (binds at MTL_RMR and
QC_RMR; NOT COVERED at HORS_RMR/RA06/RA13 after searching all 63 sibling geography members, no
stand-in substituted). The catalogue closure is read live from P9's own DECISION tokens rather than
restated, so a re-run of P9 that narrows its closure narrows this note with it.

**Carries (none blocking):**
- The mutation battery asserts only `pytest.raises(ProbeRefusal)` and never the BOUNDARY, though
  `exc.boundary` is already on the exception — a mutant that later starts firing at an earlier guard
  would leave its own guard unexercised while the battery stays green. Cheap strengthening.
- Guard-class census: several refusal branches have no test driving them (`_guard_meta`'s
  non-SUCCESS / length-mismatch / missing-pid, `_dimension`'s missing-position, `_guard_isq`'s
  missing-province-row, `share_residual_pct`'s zero denominator, `_p9_note`'s absent-file, and
  `_require_measured_or_skip`'s fail branch). All reachable by construction, none wrong today.
- §4d inherits "no correspondence between the two code systems exists in this tree" from spec §6
  rather than scoping it to a search this run performed — a small tension with the note's own header
  rule that every absence claim is scoped to the search that produced it. The P9 closure, by
  contrast, is carefully attributed.
- `run_p8.py:1094` has a dead local (`label` assigned, never read); no lint gate exists in the
  demoflow project to catch it — which is the same "no lint anywhere in this arc" observation cf1's
  run 7 raised, now seen on both sides of the arc.
- Two test-strength notes: the code-axis test asserts the Facts exist rather than that §4d renders
  them, and the signed-residual sweep keys on the literal phrase "inside the innocent", so a
  reworded range claim would slip past it.
- The implementer report's §4c persons figures (~31,972 / ~6,986) disagree with the note's generated
  31,976 / 6,987; the NOTE is correct (threshold × each geography's ISQ population, truncated).
  Report-only, artifact right — recorded because this arc grades reports as well as artifacts.

- outcome: **APPROVE / landed `44f3519` / suites 191+494.** Both immigrant inputs are now MEASURED,
  cited, and gated. **Task 25b is UNBLOCKED** — its two value questions are ruled, its mechanism is
  pre-ruled, and this note is the justification its `cited` flags will point at.
