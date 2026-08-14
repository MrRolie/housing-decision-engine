# Seat-run dispatch record — run 16 (P8: immigrant headship probe)

Probe-class task, dispatched ALONE (P5b/P6/P7 precedent: probe tasks are not batched). Seat-authored
— this task is NOT in the plan. It exists because plan Task 25b cannot be built honestly without it.

- date: 2026-08-14
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-14-sdd-run16-p8-immigrant-headship.args.json` (sha256
  `3f49658222865f31f4213ac187ea50f891e53b716994167fa8d6abfd8d0f2b7b`)
- models: opus/opus; load_bearing ×1; money_path: false; WAVE-0 vacuous
- preconditions (GROUND FIRST, seat's own run): tree clean at HEAD `9daac24` (ruling P's spec
  amendment), `./scripts/test-all.sh` green at hde 191 + demoflow 396, checkout free (run 15 closed
  and pushed)

## Why this probe exists

Ruling P settled the immigrant ownership RATIO. The other multiplicand in spec §6's immigrant chain
— immigrant HEADSHIP, households formed per immigrant person — has no source anywhere in the arc.
Plan Task 25b hardcodes 0.42 / 0.45 / 0.43; the seat grepped those to nothing (present in the plan's
own code block, absent from the spec and absent from the tree). The charter rule enforced in code by
`Anchor.__post_init__` — "every constant carries its documented anchor; a constant without an anchor
is a defect" — makes building on them impossible, so the value gets found, or its absence gets
established with evidence, before 25b runs.

Mandate carries the full charter probe discipline (generated note, depth-ladder entailment standard,
earned-verdict floor guard with mutation test, same-HTTP-method reachability per Law 1b,
`json.loads` not `pd.read_json`, WDS coordinate-keying not `zip`, `_wds.py` reuse per ruling E,
PYTHONDONTWRITEBYTECODE=1, glob-discovered contract gates, DECISION block in the P5b shape).

Two cheap checks are ordered FIRST: 98-10-0134-01 (P3) and 98-10-0231-01 (T13b) are already-hit
cubes with known-good wiring — if either crosses immigrant status with household-maintainer status,
the answer is one dimension query away. A recorded negative there is a result.

The operand-match requirement is stated explicitly: the chain's arrivals are ISQ compo "Immigrants
permanents", a recent-arrival FLOW, while Census immigrant status is normally a STOCK. A stock rate
is usable as `borrowed_prior` with the axis NAMED — the way P4 named its three for the ratio — but a
note reporting a stock rate without naming the flow-vs-stock gap is wrong even when the number is
right.

Three outcomes, and what each means for 25b: FOUND AT CMA → cited, no flag. FOUND COARSER →
`borrowed_prior`, axis named. ABSENT → an operator-class call in ruling P's shape, and the note's job
is to frame it (what exists, at what dimensions, what each candidate costs in transport).

## Advisor discipline

- `ADVISOR RATIFY FIRED @spec-amendment-7` (ruling P, committed `9daac24` — logged here because run
  15's record was already closed when the amendment was written). Cost: transcript-scale proxy, full
  forward at ~200k. Catches, all adopted: the BLOCKING r5-F4 contradiction (§6's "MTL_RMR/QC_RMR:
  their CMA values direct" tier survives the amendment and would have asserted both "direct" and
  "derives from the pinned anchor" about the same quantity — fixed with the empty-direct-tier
  clause); "not obtainable at all" → "not obtainable free" (P4's finding and ruling D both carry the
  qualifier); and the plan's `resolve_immigrant_inputs(MTL_RMR).flag is None` assertion being
  re-ruled by that clause, now named in the amendment so 25b does not discover it as a halt.
- `ADVISOR RULING SKIPPED @run-16 dispatch — no new ruling: the probe mandate applies the charter's
  standing probe discipline and ruling P's already-ratified scope split (ratio settled, headship
  unsourced). Framing only, no cap value or gate semantics set.`

## Carries for Task 25b (consolidated — 25b dispatches after this probe folds)

1. Ratio: pinned 0.911 per ruling P; the "CMA values direct" tier is EMPTY for the ratio, so every
   geography resolves to the pinned anchor `borrowed_prior`. The plan's `MTL_RMR.flag is None`
   assertion is RE-RULED.
2. `ImmigrantInputs` carries ONE flag for the (headship, ratio) PAIR. If P8 finds CMA-level
   headship, one field is cited and the other borrowed, and a single flag cannot say that honestly —
   **pre-rule per-field provenance in the mandate**, not at the implementer's discretion.
3. `CENTRAL_ASSUMPTIONS["immigrant_ratio_center"]` 0.62 → 0.911 with `CENTRAL_PROVENANCE` rewritten
   to cite ruling P (the "UNRULED / seat-or-operator call" paragraph goes). **No test red is
   expected**: `test_central_assumptions_and_hash` pins no hash literal and checks band containment
   only, and 0.911 ∈ [0.155, 1.033]. It DOES move `assumptions_hash()`, which is harmless while
   Task 30's goldens do not exist — if 25b ever lands after a golden, regenerate in the same commit
   and say why in the record.
4. `constants.py`'s q_live comment says "today the ONLY key read from this dict" — **stale as of run
   15**: `listings.py` now reads three keys read-through. Same depth-2 class; fix it in 25b's
   constants.py touch.
5. `immigrant_ownership_ratio_fresh_arrival`'s docstring gains the pointer to ruling P's refutation
   of the arrival-window reading (the amendment says it gains one, so something must actually make
   that edit).
6. From run 15: make `formation.py`'s i2 forward reference true and DELETE its caveat; the immigrant
   leg asserts nothing (negative arrivals → negative owner households); and the new cohort/demand →
   loaders import direction has no gate.

- run id: (appended at dispatch)
- outcome: (appended at run close)
