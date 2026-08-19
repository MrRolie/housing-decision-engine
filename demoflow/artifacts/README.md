# The committed golden (spec §10)

`rankings.json` and `tripwire_baseline.json` are **build artifacts**, generated from the
committed data vintage and committed alongside the code that produces them. Never hand-edit
them: regenerate and commit what the generator emits.

```bash
cd demoflow && uv run python scripts/gen_golden.py
```

`tests/test_golden.py` re-runs the pipeline and diffs both files — parsed first, then byte for
byte. Nothing is normalized out of that diff; a golden with holes in it has stopped pinning the
thing it was built to pin.

## What is pinned, and what is not

| Input | Pin | Where |
|---|---|---|
| data directory | `demoflow/data/` | `golden.GOLDEN_DATA_DIR` |
| `now` (freshness clock) | `2026-12` | `golden.GOLDEN_NOW_YEAR` / `GOLDEN_NOW_MONTH` |
| every source's bytes | sha256, in the file | `data_vintage.source_hashes` |
| the CPM mortality basis | sha256 of the q surface, in the file | `data_vintage.source_hashes["mortality_basis:…"]` |
| the assumption selection | 16 hex chars, in the file | `assumptions_hash` |

**`now` is an input and the documents do not record it.** The freshness gate takes an injected
`(year, month)` so a verdict is reproducible, and spec §7 closes the envelope at
`{schema, schema_version, data_vintage, assumptions_hash}` — `output/artifacts.py` RAISES on any
undeclared position, so the document cannot carry its own `now` without a spec amendment. Until
that amendment, `demoflow/golden.py` is the artifact's only provenance for the clock, which is
why the generation path is committed source rather than a remembered shell line. Taking the
amendment is the right move the day the first real indicator value lands; that same event
re-mints the golden anyway.

`extracted_at` inside `source_hashes` is **declared provenance**, read from each derived
artifact's own `_provenance` block (hence the three different dates) — never a wall-clock
stamp. It is stable across runs and it belongs in the diff.

**The mortality basis rides the envelope and is not a file.** Every `q` value the supply side
uses comes from actuarial-system's CPM2014 + CPM-B tables, which live outside this repo behind a
uv path dependency with no digest — so before run 33 two runs over *different upstream mortality
tables* emitted different `rankings.json` bytes under a **byte-identical** envelope, and the
table at the bottom of this page then sent the reader hunting a code defect that did not exist.
The run now publishes `mortality_basis:CPM2014_combined+CPM-B`: a sha256 over the **q surface**
the model consumes (ages 75–100 × M/F × 2021–2051), taken through the same guarded public entry
point every lookup uses — spec §2 forbids reaching into the engine's private table registry.
It is **recorded, not pinned**, like the IRCC feed: a legitimate re-publish upstream is a
**re-mint**, not a refusal. Its `extracted_at` is the one date in this envelope that is neither
an upstream pull nor an artifact's own `_provenance` — the dependency publishes no date through
any public surface, so the entry declares the day its surface was measured into the envelope
(`pipeline.BASIS_RECORDED_AT`), and a test reds if the digest moves off that declaration.

`demoflow run`'s `--out` defaults to the relative `artifacts`, so a run invoked from `demoflow/`
lands here by design. That is a convenience, not the minting path: use the script above, so the
committed bytes carry the pinned `now` rather than today's date.

## The IRCC feed is DECLARED ABSENT

`data/ircc_pr_by_cma.csv` is deliberately **not committed**. Committing it would flip
`pr_landings_annual` from structurally UNKNOWN to a live verdict, so the honest committed state
of this repo is the one the golden pins: `UNKNOWN` / `source_unavailable`, and no IRCC key in
`data_vintage.source_hashes`.

Two consequences, both intended:

* Drop the feed into `data/` and the diff tests red **with no code change**. That is the
  expected **re-mint**, not a regression — re-run the generator and commit the new bytes.
* A golden minted *with* the feed then fails in any checkout *without* it. This is the one
  input whose absence is load-bearing, so `test_golden_declares_the_absent_ircc_feed` names it:
  a red there tells you which direction you are in before you read a byte diff.

**A fixture-backed golden is rejected.** It would stamp a non-live vintage into a committed
artifact and destroy exactly the data-vs-code attribution the table below rests on.

## The tripwire exit code pins nothing today

All six indicators are structurally UNKNOWN — one wired feed uncommitted, two wired to nothing,
three operator-supplied with no operator input — so `run_exit_code` returns **1 on every
vintage**. Do not read that 1 as a verdict about Québec housing, and do not treat it as
something the golden asserts: it is a constant, and it will change the day the first real input
lands. That change is **success**, and it re-mints this golden.

Supplying a value to make it green would be a fabricated operator input. Don't.

## `rank_stable` is a FIVE-AXIS verdict, and `false` everywhere is the measured state

Every row of `rankings.json` carries `"rank_stable": false`. That is the honest output of the
robustness sweep, **not** a regression and not a hole — do not read it as a broken gate, and do
not expect a re-mint to turn it green.

Spec §7b asks one question: *does the ordering change anywhere in the sweep grid?* The run
answers it over **five declared axes at both endpoints each — ten legs**, unioned:

| Axis | Endpoints | Does the published order move? |
|---|---|---|
| `q_live_per_year` | 0.06 / 0.11 | no |
| `phi_voluntary` | 0.7 / 1.0 | no |
| `estate_eventual_fraction` | 0.6 / 0.85 | no |
| `estate_lag_years` | 1 / 3 | no |
| immigrant/non-immigrant ownership ratio, uniform override | 0.155 / 1.033 | **yes — all 8 rows at 0.155, 4 rows at 1.033** |

The first four live in `constants.SWEEP_GRID`; the fifth is the uniform join-table override over
`CONSTANTS["immigrant_ownership_ratio_sweep_span"]` (rulings S/T measure the ratio per geography,
so it has no central scalar and therefore no grid entry — `pipeline.Assumptions` carries it as a
sweep-only field). At 0.155 the ranking is a near-complete reversal and **rank 1 changes hands**
(HORS_RMR → LAVAL_RA13); the union over both ratio endpoints moves every ranked geography, so no
row is stable.

**Before run 33 this field shipped `true` on all eight rows as a verdict over one of those five
axes.** `_rank_stability` iterated `q_live_per_year` alone while `constants.py` stated the ratio
override as an existing fact of the pipeline — two committed contracts in contradiction, green
because no test crossed them, and the axis that was swept happened to be one that does not move
the order. Two checks now stand where none did, and they cover DIFFERENT doors.
`pipeline._sweep_legs` refuses the run outright if a declared axis has no leg FIELD to carry it
— declared → field. `tests/test_pipeline.py::test_every_declared_sweep_axis_actually_REACHES_the_ED_NUMBERS`
pins that each leg's field actually MOVES the ED numbers — field → consumed. The second is not
redundant: `phi_voluntary` was a declared axis carried in name and inert in effect, which the
refusal cannot see, and a mutant that reproduces that shape passes the other 1139 tests (the
central run does not move, so no golden byte moves, and the ratio axis alone holds these
booleans at `false`).

**What would make a row `true` again** is a narrower sweep or a moved band. For the four
`SWEEP_GRID` axes that is an `assumptions_hash` event and the envelope names the cause. For the
ratio span it is **not** — `CONSTANTS` is outside that token, so narrowing
`immigrant_ownership_ratio_sweep_span` would flip these booleans under a byte-identical
`assumptions_hash` and land in the "the code moved" row of the table below. That residual is
stated at `pipeline._sweep_legs`' section note rather than papered over; closing it is one payload
key in `constants.assumptions_hash` and an owner's call, not a side effect of wiring the sweep.

## Reading a red

| What moved | What it means | What to do |
|---|---|---|
| `data_vintage.source_hashes` | an upstream source was refreshed or re-pinned (IRCC restates overlapping cells; ISQ re-publishes workbooks; actuarial-system re-publishes the CPM tables) | confirm the refresh was deliberate, then re-mint |
| `assumptions_hash` | the assumption selection changed — the banded central/sweep values (`CENTRAL_ASSUMPTIONS` / `SWEEP_GRID`), the unbanded model choices (`MODEL_CHOICES`), or a ruled immigrant input (`demand/immigrant_inputs.py`) | confirm the ruling behind it, then re-mint |
| neither, but values differ | **the code moved** — a model change | this is the default-defect case: explain it before re-minting |
| nothing — values identical, bytes differ | the serialization moved (indent, key order, encoding, line endings) | `artifacts._dump_json` pins all four; treat as a code red |
| the file is missing | the golden was never minted in this checkout | run the generator |
