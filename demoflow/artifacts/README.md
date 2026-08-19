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

## Reading a red

| What moved | What it means | What to do |
|---|---|---|
| `data_vintage.source_hashes` | an upstream source was refreshed or re-pinned (IRCC restates overlapping cells; ISQ re-publishes workbooks) | confirm the refresh was deliberate, then re-mint |
| `assumptions_hash` | the assumption selection changed (`CENTRAL_ASSUMPTIONS` / `SWEEP_GRID`) | confirm the ruling behind it, then re-mint |
| neither, but values differ | **the code moved** — a model change | this is the default-defect case: explain it before re-minting |
| nothing — values identical, bytes differ | the serialization moved (indent, key order, encoding, line endings) | `artifacts._dump_json` pins all four; treat as a code red |
| the file is missing | the golden was never minted in this checkout | run the generator |
