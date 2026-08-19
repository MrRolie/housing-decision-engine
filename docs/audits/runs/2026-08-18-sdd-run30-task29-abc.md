# Seat-run dispatch record — run 30 (plan Task 29, cut into 29a / 29b / 29c)

- date: 2026-08-18
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea`
- args: `2026-08-18-sdd-run30-task29-abc.args.json` (sha256
  `302935485eb4fc4f4becfdb4f60fdefb6fad7d6b6ab6ab356446463412ca72ce`); plan bytes for each file
  extracted MECHANICALLY by a generator that emits the `.args.json` and the dispatch script from ONE
  object, so the two cannot drift
- models: opus/opus; load_bearing ×3; money_path: false
- preconditions, DERIVED from the seat's own gate run: tree CLEAN at HEAD `5926f13`,
  hde **191** + demoflow **851**

## Why plan Task 29 was CUT INTO THREE

418 plan lines, the arc's most carry-laden task, and a single dropped carry drops a ruling. Three
sequential tasks in dependency order — `artifacts.py` → `pipeline.py` → `cli.py` — each with its own
review and its own fix round.

## The plan body for this task is defective in TWELVE places, audited by the seat pre-dispatch

**And left as written it would UNDO Task 28 and ruling U.** `_tripwire_results` rebuilds the exact
false-green those two runs existed to kill: `TripwireSpec("pr_landings_annual", 40000.0, 50000.0, …)`
fed a hardcoded **`45000.0`** — a literal inside its own band, compared against that band, green
forever — never calling `evaluate_pr_landings`, so the measured-realized path, the plan-era gate, the
degenerate floor, the freshness gate and the member-set contract are all bypassed.

The other eleven, each verified against the tree rather than inferred: `exit_code` where
`run_exit_code` belongs (F4 stays half-closed and `run_exit_code` stays dead code); **nothing imports
`hors_aligned`**, so ED is still computed from the contaminated curve and four earlier runs are
decoration; `refuse_cross_vintage({ah})` called with a ONE-element set while `assumptions_hash()`
does not hash the data vintage at all; **the identity envelope covers 3 of 13 committed inputs**,
omitting every population and immigrant-flow workbook — and wiring the aligned join adds a tenth
uncovered input in the same commit; `_source_hashes` silently drops a missing file; a hardcoded
`extracted_at`; **three of six tripwire bands vacuous**, one of them fed a fabricated `-1200.0` so it
reports OK forever; an uncited magic `0.1` on the model path; `_scale(t-1)` silently returning 1.0 at
the base year; the `borrowed` set derived from geography instead of the per-field provenance that
already exists on `ImmigrantInputs`; and a pipeline test that binds ambiently to the real data dir.

## Advisor discipline

- `ADVISOR RATIFY FIRED @run-30 dispatch — decomposition + mandate corrections.` The advisor
  ratified the three-way cut and returned **seven corrections the seat ADOPTED**, two of which were
  defects in the seat's own mandate:
  - **A false premise, the run-26 class.** The seat's carry claimed "RULING K is not wired — the
    pipeline never sets `closed_cohort_exceedance`". Verified before shipping: `rankings.py` ALREADY
    carries `CLOSED_COHORT_EXCEEDANCE_MEMBERS` and emits it on every LAVAL_RA13 row. The carry now
    says do not re-implement it and do not break it, and reduces to the real defect — the `borrowed`
    set conflating provenance with geography.
  - **A vacuously satisfiable carry.** "Do not let a sweep leg trip the central reconciliation gate"
    is satisfied by calling it NOWHERE — and the plan's pipeline never calls `check_reconciliation`
    at all (seat-verified absent; it lives at `cohort/gates.py:53`). Restated as an OBLIGATION: the
    central run MUST invoke it, the sweep legs MUST NOT, with a required RED case. **A gate that
    cannot fail is exactly what this task is full of; the seat had written one into its own mandate.**
  - Bands are RULED VALUES: a band not derivable from an existing cited constant is a SEAT_QUESTION,
    and the in-lane answer is UNKNOWN — closing the door on in-lane invention of a threshold.
  - The oracle-red disposition is PRE-RULED, so the implementer neither halts nor quietly skips the
    aligned-join wiring: a red is expected, the oracle is re-derived BY HAND, never transcribed from
    the new output.
  - A1's escape hatch was wider than the spec; "state what remains uncovered" is cut, leaving only
    the real walk or provable coverage by composition.
  - The `demoflow run` / `demoflow tripwires` exit-code contract is RULED by the seat rather than
    delegated — it is an interface promise, not an implementation choice.

## Carried into this run's context, not left to memory

The plan is HISTORICAL and the SPEC governs (now through amendment #15). Every plan-vs-tree
divergence must be classified plan-superseded / code-defect / genuine-drift rather than reported
flat. `loaders/hors_aligned.py` is read-and-import only: task 2 must CONSUME it.

- run id: `wf_a425b526-7ba` (task `wcc6b9n0k`)
- outcome: **APPROVE ×3, 0 unresolved** (fix rounds 1 / 3 / 1); 17 agents, 0 errors, 2,650,233
  subagent tokens, 6h22m

## Outcome — folded 2026-08-19 as `3a38b27` (29a), `943ca31` (29b), `f04b195` (29c)

**THE PIPELINE RUNS END TO END AND EMITS THE TRANCHE-1 CORE OUTPUT.** Verified live by the seat, not
read from a report: `demoflow run --out <dir>` exits 0 having written both documents; eight
geographies ranked, `exclusions: []`, `assumptions_hash` 16 chars, `rank_stable` true throughout.
HORS_RMR ranks 1 at mean ED −0.00029; LAVAL_RA13 carries `closed_cohort_exceedance` (ruling K
intact); RA14/15/16 carry `borrowed_prior` + `ra_proxy`; HORS_RMR carries NO flag because its
provenance is `computed_residual` — the flags now reflect rulings Q/S/T instead of a geography list.

Gate, seat's own run: **hde 191 / demoflow 1085 / both suites passed** (+234 tests). The reviewer
reported 1084 — the transcribed-figure gap again, one test wide; **1085 is the figure of record.**

**CARRY DISCHARGE, seat-verified against the code rather than the report.** B1: no `45000.0` literal
survives (the only occurrences are inside comments explaining its removal); `evaluate_pr_landings` is
wired and only its `.result` reaches the artifact. B2: `exit_code` is not imported at all;
`run_exit_code` has its first production consumer. B3: `hors_aligned` is imported and consumed — the
aligned ρ curve is no longer dead code, which is what makes the #12(B) reversal real. B4:
`refuse_cross_vintage` now samples identity BEFORE the ED grid and AGAIN after the sweep, so it
refuses a run whose identity moved mid-computation — reachable, since `CENTRAL_ASSUMPTIONS` is a
mutable dict bound read-through at import. **B5b: source_hashes covers 12 inputs, up from 3**,
including every population and immigrant-flow workbook. B7: the three vacuous bands and the
fabricated `-1200.0` are gone; all six indicators now report honest UNKNOWN with a named cause. B8:
the uncited `0.1` is replaced by a spec-derived band-entry construction — and the review found the
deeper defect, that it was booking a tenth of the gap to the ISQ stock, a partial re-anchoring
`rollforward.py`'s own contract forbids. B10: `borrowed_prior` derives from `ImmigrantInputs`
per-field provenance.

**THE BEST CATCH OF THE RUN IS A CROSS-SEAM ONE.** `artifacts.py` validated a 64-character
assumptions hash while `assumptions_hash()` emits 16 — the emitter would have REFUSED the only hash
any run computes. Two committed contracts in direct contradiction, **green because no test crossed
the seam.** Now one declaration (`ASSUMPTIONS_HASH_CHARS`) read by producer and gate alike, with a
third test-owned literal so widening is PR-visible in three places.

**A POSITIVE CENSUS RESULT worth recording:** the `rank_stable` sweep is a real measurement, not a
verdict that cannot go false. At q_live 0.06 / 0.085 / 0.11 every geography's mean ED moves
materially and HORS_RMR crosses zero across the band (+0.000853 → −0.000290 → −0.000944). The flag
reporting "stable" everywhere is therefore a finding, not a stuck gate.

**Commit-split note, for honesty about the boundary:** task 29c legitimately edited `pipeline.py`
(adding public `evaluate_tripwires` and an `artifacts` key) and `test_pipeline.py`. Since the seat
commits at file granularity, 29b's commit carries those 29c additions. The final tree is what was
gated; the boundary is approximate, and this is the record of it.

**Reviewer battery-hygiene incident, self-caught and worth keeping:** 29c's first mutation battery hit
a tool timeout and left a mutant written into the COPY, so the second run read a MUTATED file as its
baseline and mis-attributed kills. Detected by an inconsistency in the attribution, corrected, and
disclosed. The battery then ran 10 mutants, 10 RED, zero survivors.

## New carries — Task 30 and pre-PR

1. **`run_exit_code` returns 1 on EVERY vintage today.** All six indicators are structurally UNKNOWN
   (one wired feed uncommitted, two wired to nothing, three operator-supplied with no operator
   input). So the exit code **discriminates nothing for a Task-30 golden** — pinning it pins a
   constant. Task 30 must not read a green into it.
2. **Freshness becomes WALL-CLOCK dependent the moment a real indicator value lands, and no artifact
   field records the injected `now`.** The tripwire document's keys are
   `[assumptions_hash, data_vintage, indicators, schema, schema_version]`. A golden pinned today is
   reproducible only because everything is UNKNOWN. **This is the golden-determinism question and it
   belongs to Task 30**, together with the `extracted_at` decision (charter D3).
3. **`Reason.DUPLICATE_INDICATOR` is absent from `NULLABLE_REASONS` while `MISSING_INDICATOR` is
   present** — so a synthetic duplicate record from `check_registry` (which carries null value and
   null as_of) FAILS `assert_tripwire_record_valid`. A latent defect in Task 28's committed code,
   surfaced here, unreachable only because nothing currently emits a duplicate. **Add to the pre-PR
   blockers.**
4. **One silent-zero door survives on the model path** — `listings.get(t, 0.0)` at `pipeline.py:732`
   — in a module whose own docstring says every such door refuses instead. Unreachable as written
   (the supply loop keys `voluntary` at every year 2021–2051), but it is the deflating-door shape.
5. **`HORIZON_YEARS` has no consumer in Tranche 1**, and the plan-mandated
   `test_horizons_are_the_declared_set` asserts a module literal against the same literal — it
   cannot fail for any reason connected to the run. **The seat mandated it by transcribing the plan's
   named test cases**; that is the mandate carrying a vacuous test in, and it is the seat's to
   remove or give a consumer.
6. **The `demoflow tripwires` listing carries no identity or vintage line** — no `assumptions_hash`,
   no `data_vintage` — so a listing is unattributable to the data it was computed from, and it can
   disagree with a `tripwire_baseline.json` on disk with no field on either side revealing it.
7. **Citation imprecision, low severity:** `demand/immigrant_inputs.py:25` attributes the per-field
   provenance split to ruling T; the seat's carry attributed it to ruling Q. Checked — **both are
   defensible**, since Q (MTL/QC cited ratio beside borrowed headship) and T (RA06/RA13 measured, not
   borrowed) each produce mixed pairs. Not a contradiction; worth one word of precision if the file
   is touched again.
