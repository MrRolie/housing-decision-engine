# Seat-run dispatch record — run 26 (P8 regeneration + join-table update)

The wiring run. Amendment #13 ruled HORS_RMR's immigrant values at exact territory; this run makes
the note and the join table say so, and lets the citation coupling do it.

- date: 2026-08-18
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-18-sdd-run26-p8-regen-join-update.args.json` (sha256
  `ce99ff074389b96850ced9bc42e1ed3b8fc6545b59ba328cf9d29433a7507db4`)
- models: opus/opus; load_bearing ×2; money_path: false ×2; WAVE-0 vacuous
- preconditions, **DERIVED at authoring time** (`git rev-parse --short HEAD` and live suite runs
  piped into the args, per the binding rule minted after run 25's X-1): tree CLEAN at HEAD
  `ddc0a9b`, hde **191** + demoflow **734**

## The chain gets its first live exercise

§6 → P8 → join table was built so a moved value cannot land quietly. Amendment #13 moved one, so the
coupling is RED right now for HORS_RMR. Task 1 regenerates the note (making it true, never by
loosening a gate — if a gate must be relaxed to get green, the mandate says STOP and report); task 2
is the join table's red going green against the regenerated note. The mandate forbids short-circuiting
by typing the new digits in first: re-run, watch it red, update, watch it green.

Untouched and provable: MTL_RMR, QC_RMR, RA06, RA13 and the three RA proxies. Their territories were
never contaminated, so any movement there is a finding rather than rounding.

## ⚠ BINDING CARRY FOR TASK 29 — the reversal is currently INERT, and will stay inert unless wired

Seat-verified after amendment #13: **nothing in `balance/`, `demand/` or `cohort/` reads
`hors_aligned`.** The aligned ρ curve exists as a module, a committed artifact, a pins row and a test
suite — and no model path consumes it. That is per #13 (re-pointing `load_ownership_rates` would red
the T13b external-anchor gates, which pin the SHIPPED residual at `rel=1e-12`), but the consequence
must not be lost: **the #12(B) reversal was ordered because the contamination distorts ED, and ED is
still computed from the contaminated curve.** A correction nobody consumes is decoration.

The mechanism is already built and needs no new design. `hors_aligned` ships
`load_aligned_ownership_rates()`, `load_aligned_ownership_join()`, `load_aligned_ownership_vintage()`
and `aligned_ownership_rate()`, and the artifact carries a **`join` map naming every modeled geography
exactly once with a `why` per row** — `_verify_join` refuses a join that re-points the wrong geography
or blanks a reason, a defect the closeout proved by mutation. So **Task 29's pipeline reads the join
map and routes HORS_RMR to the aligned curve**; `load_ownership_rates` and its T13b gates are not
touched, because the shipped artifact remains correct for what it describes.

If Task 29 lands without consuming that join, the QFE finding, the P10 measurement, the P11
extraction and amendment #13 will all have changed nothing the model computes.

## Advisor discipline

- `ADVISOR RULING SKIPPED @run-26 dispatch — no new ruling. Both tasks execute amendment #13
  verbatim; the Task-29 carry above states a consequence of #13 as already written and designs
  nothing new (the join map and its accessors already exist and are gate-verified).`

- run id: `wf_a594e264-ace` (dispatched 2026-08-18; task id wh16s0n8c)
- outcome: (appended at run close)

---

## OUTCOME — 2/2 APPROVE (1 fix round each) → LANDED `8cde877`; suites 191+757

The regeneration was verified FOUR independent ways: a LIVE regen from a scratchpad copy against real
www150 reproducing the working-tree note byte for byte; an independent recompute from P10's COMMITTED
capture importing no part of `run_p8.py`, reproducing every figure in #13 including the +8.083% leg;
RED-first replicated by running the new gates against `git show HEAD`'s note; and the four untouched
geographies verified present verbatim, with only HORS_RMR's digits moving. **No gate was relaxed** —
confirmed by reading every deleted line of both files.

## THE RUN'S PREMISE — MINE — WAS MEASURED FALSE, and that is the run's most valuable output

I wrote "the coupling is RED right now for HORS_RMR". It was not. `immigrant_inputs.py:192` and HEAD's
note both carried 0.5169 / 0.9600, so `test_i2` was green. **The gates key on §6 TABLE ROWS while
amendment #13 stated its supersession in PROSE** — so the spec moved somewhere the coupling could not
see, and the chain built to stop a moved value landing quietly did not notice a moved value.

**The seat then measured the gate itself, by mutation, rather than trusting the diagnosis:** garbage
in the row (0.9999 / 7.7777) DOES red one gate, so the coupling is not decorative — but swapping the
row between the two LEGITIMATE pairs (ruled 0.5234/1.0248 ↔ superseded 0.5169/0.9600) reds NOTHING in
either direction, because the note carries both and the gate is satisfied by PRESENCE rather than
identity with the RULED pair. **The machinery catches a typo and cannot catch a supersession, which
is the one thing an amendment does.**

→ **Amendment #14 (`f6231c8`)**: the table now carries the ruled pair; a STANDING RULE binds every
future amendment to update the table in the same commit (the other four rows sit behind the same
gates, so a prose-only amendment moving any of them is invisible the same way); and the gate weakness
is recorded as an OPEN DEFECT with a named owner rather than smoothed.

## NEXT RUN — two tasks, in this order

1. **Strengthen the §6-table coupling**: bind the table row to the note's DECISION-token (ruled)
   pair, and prove by mutation that a ruled↔superseded swap REDS IN BOTH DIRECTIONS. Until this
   lands, the table's correctness rests on the seat updating it, not on anything that fails.
2. **Task 27** — the rankings table (scenario-named fans, closed flags enum, row allowlist), carrying
   ruling K's `closed_cohort_exceedance` wiring and the `.value` enum carry.

**And the standing Task-29 carry is unchanged and still binding:** nothing in `balance/`, `demand/`
or `cohort/` reads `hors_aligned`, so the #12(B) reversal remains INERT until Task 29's pipeline
routes HORS_RMR through the artifact's verified `join` map.

### Carries from this run

- Implementer-report figures disagreed with the artifact on the provenance count (49→70 reported vs
  the note's own internally-consistent 69 = 56 DERIVED + 13 CITED). **Artifact governs**; recorded
  because this arc grades reports as well as artifacts.
- `test_p8_hors_rmr_carries_the_suppression_envelope_amendment_13_rules` asserts substring presence
  of the four envelope ends, and one of them (0.5236) was ALREADY in the pre-regen note as
  QC_PROVINCE's headship — so that end is satisfiable by coincidence. The producer-side
  `_guard_amendment13_match` binds all four exactly, so the property holds; the artifact-side gate
  alone does not enforce it.
- Mutant-census gaps named per guard: `_guard_amendment13_match`'s ratio/envelope branches,
  `_guard_p10`'s note-absent and verdict≠MEASURED branches, `_member_by_code`'s 0-hit and >1-hit
  ambiguity refusals, and `_guard_required_complete`'s `Non-immigrants` leg are all UNCHECKED by
  mutation (each covered positively).
- §2a's per-member table prints the superseded pair under a bare geography label with the
  "superseded" sentence three paragraphs below, unlike §2's headline table which labels its row
  inline. Both DECISION tokens are unambiguous, so no machine consumer is exposed.

- outcome: **2/2 APPROVE / landed `8cde877` + `f6231c8` / suites 191+757.**
