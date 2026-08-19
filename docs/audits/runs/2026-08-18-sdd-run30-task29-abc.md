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

- run id: (appended at dispatch)
- outcome: (appended at run close)
