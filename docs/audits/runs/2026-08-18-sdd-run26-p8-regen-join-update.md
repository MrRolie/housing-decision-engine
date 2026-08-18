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
