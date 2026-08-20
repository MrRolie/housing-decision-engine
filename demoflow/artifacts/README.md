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

## The published ORDER moved at operator ruling V

The ranking in `rankings.json` is **not** the one that shipped before `c83595e`. That commit
replaced the six-band headship rate — one flat value reused at every age inside a band — with a
single-year graduation that closes on every published maintainer-age member (operator ruling V,
2026-08-19), and this order is its ordered consequence. Measured at this mint:

| Geography | rank before | rank now | `mean_ed_reference` before | now |
|---|---|---|---|---|
| `LANAUDIERE_RA14_PROXY` | 3 | **1** | +0.000196 | +0.000851 |
| `LAVAL_RA13` | 4 | **2** | +0.000613 | +0.000958 |
| `LAURENTIDES_RA15_PROXY` | 2 | **3** | +0.000085 | +0.001031 |
| `HORS_RMR` | 1 | **4** | -0.000290 | +0.001102 |
| `MTL_RMR` | 6 | **5** | +0.002768 | +0.001911 |
| `MONTEREGIE_RA16_PROXY` | 5 | **6** | +0.001902 | +0.002250 |
| `QC_RMR` | 7 | **7** | +0.005461 | +0.005586 |
| `MTL_ISLAND_RA06` | 8 | **8** | +0.007213 | +0.006003 |

**Why it moved.** The retired band curve put the whole 0–19 → 20–34 rise on the single age 20,
where `ownership(20) = 0` zeroed it; the resolved curve spreads that rise across ages 20–34, most
of it *above* the lattice floor. `demand/formation.py` carries the measurement (MTL_RMR at
`Scenario.REFERENCE`, the 26 projected years pooled): the largest single-age share of native demand
falls from 79.9% at age 35 to 26.1% at age 26. Formation mass is redistributed WITHIN each band, so
a geography's own population age mix now converts into owner demand at a resolution the band rate
could not express — and the eight geographies have different age mixes, so their excess demands
move by different amounts. Nothing about the ED equation, the ownership lattice or the immigrant
leg changed here.

Three consequences a reader should carry:

* **Rank 1 changed hands** — `HORS_RMR` → `LANAUDIERE_RA14_PROXY`, with `HORS_RMR` dropping to 4.
* **`HORS_RMR`'s central ED flipped sign** (−0.000290 → +0.001102). It was the only negative
  `mean_ed_reference` in the committed golden; **the golden now carries none.** Read that as the
  central point estimate only — six of the eight rows still carry a negative `mean_ed_low`.
* **Ranks 7 and 8 did NOT swap.** `QC_RMR` and `MTL_ISLAND_RA06` hold their positions, so the
  7/8 swap the curve's design panel predicted did not occur — but the gap between them narrowed
  by ~76% (0.001752 → 0.000417), which is the direction the panel expected at a magnitude short
  of a swap.

**The design panel's order table is PROBE-GRADE and only partly reproduced — this table is the
record, that one is not.** `docs/research/2026-08-19-headship-curve-design-panel.md` priced the
order first-order (raw ISQ population standing in for `P_resident`, per-year ED replaced by its
mean) and got the direction right where it mattered most — `HORS_RMR`'s sign flip (+0.001165 /
+0.001232 predicted against +0.001102 live) and every row turning positive — while missing the
permutation: it predicted `HORS_RMR` would HOLD rank 1 and that 7/8 would swap. Two of its eight
predicted positions landed (`LAVAL_RA13` 4→2, `LAURENTIDES` 2→3). Read the panel for the design,
never for the numbers.

`rank_stable` is `false` on every row **before and after** — see the next section.

**BOTH identity tokens moved at this mint, and a reader must expect both.**
`assumptions_hash` `f39a8a240c60d777` → `9a876ab547fcafdd`, because ruling V put `headship_shape`
into the hashed selection twice — as a `CENTRAL_ASSUMPTIONS` pick (`expo_cum_fc`) and as a
`SWEEP_GRID` axis. That attribution is checked, not asserted: recomputing the token from payload
copies with `headship_shape` dropped from both dicts reproduces `f39a8a240c60d777` exactly, so the
axis is the SOLE cause of the move. `data_vintage` moved too — the `headship_by_age.json` digest,
whose `_provenance` prose was rewritten in the same run (`extracted_at` is declared provenance and
correctly did NOT move, and no other entry in `source_hashes` changed). `tests/test_golden.py`
names only the FIRST cause it finds, so a reader who sees "the DATA moved" must still check the
other token — the "Reading a red" table below says so.

## `rank_stable` is a SIX-AXIS verdict, and `false` everywhere is the measured state

Every row of `rankings.json` carries `"rank_stable": false`. That is the honest output of the
robustness sweep, **not** a regression and not a hole — do not read it as a broken gate, and do
not expect a re-mint to turn it green.

Spec §7b asks one question: *does the ordering change anywhere in the sweep grid?* The run
answers it over **six declared axes at both endpoints each — twelve legs**, unioned. Rows moved
out of the published order, per leg, **measured at this mint**:

| Axis | Endpoints | Does the published order move? |
|---|---|---|
| `q_live_per_year` | 0.06 / 0.11 | 0 rows / **2 rows** |
| `phi_voluntary` | 0.7 / 1.0 | 0 rows / **3 rows** |
| `estate_eventual_fraction` | 0.6 / 0.85 | no / no |
| `estate_lag_years` | 1 / 3 | no / no |
| `headship_shape` (ruling V) | `expo_cum_fc` / `expo_cum_fb` | central leg, no-op / **3 rows** |
| immigrant/non-immigrant ownership ratio, uniform override | 0.155 / 1.033 | **all 8 rows** / **6 rows** |

The first five live in `constants.SWEEP_GRID`; the sixth is the uniform join-table override over
`CONSTANTS["immigrant_ownership_ratio_sweep_span"]` (rulings S/T measure the ratio per geography,
so it has no central scalar and therefore no grid entry — `pipeline.Assumptions` carries it as a
sweep-only field). `headship_shape` is the one CATEGORICAL axis and the one whose low endpoint IS
the central choice, so that leg is a provable no-op and `_rank_stability` reuses the headline grid
for it.

At 0.155 the ranking is a near-complete reversal and **rank 1 changes hands**
(`LANAUDIERE_RA14_PROXY` → `MTL_RMR`); at 1.033 it changes hands again
(→ `LAVAL_RA13`), so BOTH ratio endpoints now displace the published leader. The 0.155 leg alone
moves every ranked geography, which is what saturates the union and holds `rank_stable` at `false`
on all eight rows.

**RULING V MADE THREE MORE AXES ORDER-SENSITIVE, and that is a change in the VERDICT'S CAUSE, not
in the verdict.** Before the curve, the four `SWEEP_GRID` axes left the published order intact at
both endpoints and the ratio override was the only axis that reordered anything (run 33, measured
on the band curve; the 1.033 leg moved four rows then, six now). At this mint `q_live_per_year`,
`phi_voluntary` and the new `headship_shape` axis each reorder the middle of the table on their
high endpoint. The ranking is *tighter* than it was — four of the eight rows sit inside 2.6e-4 of
each other — so a smaller ED perturbation is now enough to swap neighbours. Read the union verdict
as still resting on the ratio axis (it is the only one that moves ALL eight), and read a
`rank_stable` that ever returns to `true` as needing all six axes re-checked, not one.

**What in that table is test-pinned, and what is not.** Pinned and re-checked on every run: the
union verdict (`rank_stable is False` on every row), that the 0.155 leg moves all eight rows, and
that rank 1 changes hands there (`tests/test_pipeline.py`), plus that every declared axis actually
MOVES the ED numbers. The per-leg row COUNTS above are not pinned by any test — they were measured
at this mint by re-running `_rank_stability`'s own leg loop over `_sweep_legs()`, whose central
order reproduces the committed `rankings.json` exactly. Treat them as a dated reading, and
re-measure rather than trust them after any model change.

**Before run 33 this field shipped `true` on all eight rows as a verdict over ONE of those axes**
(the grid was five-axis then — ruling V added `headship_shape` at `c83595e`).
`_rank_stability` iterated `q_live_per_year` alone while `constants.py` stated the ratio override
as an existing fact of the pipeline — two committed contracts in contradiction, green because no
test crossed them, and **on the band curve** the axis that was swept happened to be one that did
not move the order. That last clause is history and no longer describes the model:
`q_live_per_year` DOES reorder two rows at 0.11 on the resolved curve (table above), so that same
one-axis sweep would today report `false` on the two rows q_live moves and still `true` on the
other six: the unearned attestation SHRINKS BUT DOES NOT VANISH, which changes nothing about why
it was a defect. Two checks now stand where none did, and they cover DIFFERENT doors.
`pipeline._sweep_legs` refuses the run outright if a declared axis has no leg FIELD to carry it
— declared → field. `tests/test_pipeline.py::test_every_declared_sweep_axis_actually_REACHES_the_ED_NUMBERS`
pins that each leg's field actually MOVES the ED numbers — field → consumed. The second is not
redundant: `phi_voluntary` was a declared axis carried in name and inert in effect, which the
refusal cannot see, and a mutant that reproduces that shape passes the other 1139 tests (the
central run does not move, so no golden byte moves, and the ratio axis alone holds these
booleans at `false`).

**What would make a row `true` again** is a narrower sweep or a moved band. For the five
`SWEEP_GRID` axes that is an `assumptions_hash` event and the envelope names the cause — including
`headship_shape`, which is what moved that token at this mint. For the
ratio span it is **not** — `CONSTANTS` is outside that token, so narrowing
`immigrant_ownership_ratio_sweep_span` would flip these booleans under a byte-identical
`assumptions_hash` and land in the "the code moved" row of the table below. That residual is
stated at `pipeline._sweep_legs`' section note rather than papered over; closing it is one payload
key in `constants.assumptions_hash` and an owner's call, not a side effect of wiring the sweep.

## Reading a red

**The attribution names the FIRST cause only.** `tests/test_golden.py::_match_golden` checks
`data_vintage` before `assumptions_hash` and fails on the first that differs, so a red that reads
"the DATA moved" does **not** mean the assumption selection held. This mint is the worked example:
both tokens moved (`assumptions_hash` `f39a8a240c60d777` → `9a876ab547fcafdd`; the
`headship_by_age.json` digest moved with its provenance prose), and the failure message named only
the data. Diff both tokens before you accept either row below.

| What moved | What it means | What to do |
|---|---|---|
| `data_vintage.source_hashes` | an upstream source was refreshed or re-pinned (IRCC restates overlapping cells; ISQ re-publishes workbooks; actuarial-system re-publishes the CPM tables) | confirm the refresh was deliberate, then re-mint |
| `assumptions_hash` | the assumption selection changed — the banded central/sweep values (`CENTRAL_ASSUMPTIONS` / `SWEEP_GRID`), the unbanded model choices (`MODEL_CHOICES`), or a ruled immigrant input (`demand/immigrant_inputs.py`) | confirm the ruling behind it, then re-mint |
| neither, but values differ | **the code moved** — a model change | this is the default-defect case: explain it before re-minting |
| nothing — values identical, bytes differ | the serialization moved (indent, key order, encoding, line endings) | `artifacts._dump_json` pins all four; treat as a code red |
| the file is missing | the golden was never minted in this checkout | run the generator |
