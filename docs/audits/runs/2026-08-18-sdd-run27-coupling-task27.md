# Seat-run dispatch record — run 27 (coupling strengthening + Task 27 rankings)

- date: 2026-08-18
- script: `mm-spine/.claude/workflows/mm-sdd-pipeline.js` sha256
  `d7743e42b0ebe6499f8f5af986b471ea3417aff067710048dc39aa8756e315ea` @ mm-spine `f4d7cca`
- args: `2026-08-18-sdd-run27-coupling-task27.args.json` (sha256
  `2d6dfa980db072af847f1b06aacab12dd5e10463054a4efcb0b0979ae5af6ec9`); Task 27 bytes extracted
  MECHANICALLY from the plan, followed by seat carries
- models: opus/opus; load_bearing ×2; money_path: false ×2; WAVE-0 vacuous
- preconditions, **DERIVED at authoring time** per the rule minted after run 25's fabricated-sha:
  tree CLEAN at HEAD `1202e46`, hde **191** + demoflow **757**

## Task 1 closes the open defect amendment #14 records against our own machinery

The §6 → P8 → join-table chain exists so a moved RULED VALUE cannot land quietly, and measurement
says it does not do that: garbage in the table row reds one gate, but swapping the row between the
two LEGITIMATE pairs — ruled `0.5234/1.0248` against superseded `0.5169/0.9600` — **reds nothing in
either direction**, because the note carries both and the gate is satisfied by PRESENCE rather than
IDENTITY with the ruled pair. The machinery catches a typo and cannot catch a supersession.

The mandate fixes the CLASS, not the instance: all five ruled rows sit behind the same gates, so
MTL_RMR, QC_RMR, RA06 and LAVAL_RA13 are exposed identically to a prose-only amendment. The mutation
census must show EACH row's swap redding, in BOTH directions. And it explicitly forbids getting
there by weakening what exists — if the new property requires relaxing a gate, STOP and report,
because that trade is the seat's call.

## Task 2 is the Tranche-1 CORE OUTPUT

The rankings table. Carries: **ruling K's `closed_cohort_exceedance`** riding every LAVAL_RA13 row
(Laval's 75+ net-migration measured 1.672/1.156/1.041 %/yr against the ruling-J 1%/yr tripwire; the
operator ruled STAND + FLAG); the **enum serialization trap measured twice in this arc** (`str(Geography.X)`
yields `'Geography.MTL_RMR'` — emitters use `.value`; and `Series.astype(str)` yields the REPR, so a
string filter silently matches NOTHING); **HORS_RMR RANKS** because resolution branch (i) fired
(compo carries its own hors-RMR row, 78 rows, REFERENCE mean 4,669/yr) — so the run-level exclusion
record is empty, but the exclusion PATH must still exist and be tested for a future vintage without
that row; RA14/15/16 rank carrying `ra_proxy`, never balance participants, never emitted in the
GATED ScenarioPrior; and **four closed vocabularies that are not each other** — `ANCHOR_FLAGS`, the
ScenarioPrior row enum, the rankings row enum, and the join table's input-provenance set.

## Advisor discipline

- `ADVISOR RULING SKIPPED @run-27 dispatch — no new ruling. Task 1 executes the OPEN DEFECT recorded
  in amendment #14 (seat-measured, already written); task 2 is plan Task 27 verbatim plus carries
  that cite rulings K/J and measured traps by name. No cap value or gate semantics is set here.`

- run id: `wf_052812cb-199` (dispatched 2026-08-18; task id w3b301m2k)
- outcome: (appended at run close)

---

## OUTCOME — 2/2 APPROVE → landed `f791c24` (coupling) + `a3c772a` (Task 27); suites 191+781

Task 1 APPROVE with **0 fix rounds**; Task 27 APPROVE after 1 (test-only).

**Task 1 closed the open defect amendment #14 recorded against our own machinery.** The gate now
reads the ruled HEADSHIP and RATIO from the table's COLUMNS (`_guard_s6_ruled_columns`) and binds
them to what the note publishes under `DECISION-HEADSHIP` / `DECISION-RATIO`
(`_guard_ruled_columns_match`) — identity, not presence. **The mutation census shows EVERY one of the
five ruled rows redding on a moved pair, in BOTH directions**, not just HORS_RMR's, which was the
point of fixing the class rather than the instance. Nothing was weakened to get there: the
presence-keyed guards stay wired beside the identity one, pinned by a test.

**Task 27 landed the Tranche-1 core output.** Ruling K wired — `closed_cohort_exceedance` on every
LAVAL_RA13 row, with the member set matching the closed-cohort probe's measured exceedance exactly
(3 geography-periods, all LAVAL_RA13, max 1.6722 %/yr). The 8 plan test bodies are byte-verbatim; the
plan→tree implementation diff drops nothing semantically; the flags enum and row fields match
spec:428-437; enum order is the spec's own §8 order. The fix round was TEST-ONLY (implementation diff
against the round-1 snapshot is EMPTY) and killed 14 of 15 ordering mutants where round 1 had a
survivor.

### A review misattribution, corrected

The Task-27 reviewer recorded "qfe-task26's uncommitted edits to run_p8.py and test_probe_p8.py were
in-tree" during its gate run. **They were TASK 1's edits** — verified by the seat: the diff adds
`_guard_s6_ruled_columns`, `_guard_ruled_columns_match` and tests named
`..._reds_IN_BOTH_DIRECTIONS` / `..._EVERY_ruled_row...`, which is task 1's mandate verbatim.
Sequential tasks share the worktree by design, so task 1's work being present during task 2's gate is
correct. No uncontrolled mutator. Recorded because this arc grades reports as well as artifacts, and
an author misattribution in a review is the kind of thing that would justify a false alarm later.

### ⚠ CARRY — the same presence-vs-identity defect exists ONE PROBE OVER, and my amendment created it

`probes/P10-hors-operand-alignment.md:179` states "the ruled §6 table still carries 0.5169 / 0.9600".
**That is now FALSE** — §6's ruled columns have carried 0.5234 / 1.0248 since amendment #14, which I
wrote. And it is not stale text: it **re-renders from `shipped_pair` at `run_p10.py:2136`, so a
regeneration reproduces the falsehood**, while run_p10's presence-keyed `_guard_citation` cannot see
it because both 0.5169 and 0.9600 still appear elsewhere in §6's prose. Exactly the class task 1 just
closed in P8, one probe over — and created by a seat edit. Owner: a later pass re-points that §8
sentence and gives run_p10 the identity-keyed treatment P8 now has.

### Other carries

- `_guard_citation("spec §6", ...)` remains pure `tok not in text` for ~30 NON-TABLE figures
  (province readings, envelope ends, recent-member and sibling ratios) — a supersession there is
  still invisible. Pre-existing shape, not a regression, now named.
- `_GEO_ROW_TOKENS` is a hardcoded five-tuple, so a SIXTH ruled row added to §6 would be uncoupled
  **without refusing**. Worth a refusal rather than silence.
- Task 27: `assert_rankings_row_valid` enforces flag VOCABULARY but not ruling-K PRESENCE — a
  LAVAL_RA13 row with flags stripped passes the gate; presence is enforced only at the single
  producer, where the ruling-K set is hard-wired rather than caller-supplied.
- `borrowed` defaults to an empty set, so a caller omitting it emits RA/HORS rows with NO
  `borrowed_prior`, while spec §8 has every RA row borrowing its parent and HORS_RMR borrowing
  province-level. The docstring records the Task-29 obligation for `rank_stable` only; the borrowed
  half has no coverage guard.
- Two mutation survivors, both named: the flags list/tuple type check is near-equivalent, and
  replacing the enum-ordered exclusion list with caller-insertion order stays green — so
  `rankings.py:118`'s golden-stability claim is UNTESTED.
- `rank_geographies({})` returns `[]` (the vacuous-empty sibling of `refuse_cross_vintage`'s
  deliberate empty-set refusal), and the str-Enum key refusal is ordered AFTER the rank_stable
  coverage check, so a bad key raises `AttributeError` instead of the intended `CalibrationError` —
  loud either way, wrong exception class.
- Emitter key order (rank, geography, means, rank_stable, flags) differs from the spec's allowlist
  ordering; the allowlist is a set and Task 30's golden is a JSON diff over whatever order the
  emitter fixes — so this is a Task-30 input, not a defect.

### Seat error, corrected forward rather than rewritten

The coupling commit's message lost two symbol names: I used an UNQUOTED heredoc (needed for the
derived suite figures) and the backtick-quoted `_guard_s6_ruled_columns` /
`_guard_ruled_columns_match` were command-substituted to empty strings. Both commits were already
pushed, and a force-push is a shared-state operation I will not take unconfirmed, so the correction
lands here rather than as rewritten history. **Mechanism fix: commit messages that need BOTH variable
expansion and backticks get written to a file by python, never by an unquoted shell heredoc.**

- outcome: **2/2 APPROVE / landed `f791c24` + `a3c772a` / suites 191+781.** Next: Task 28 (five-input
  tripwire redesign), then 29/30, the 31-33 pre-PR audit gates, the Tranche-1 PR — and the standing
  Task-29 carry: nothing reads `hors_aligned`, so the #12(B) reversal stays INERT until 29 routes
  HORS_RMR through the artifact's verified `join` map.
