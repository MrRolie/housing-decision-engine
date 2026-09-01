# demoflow

`demoflow/` is the upstream demand-model pipeline — a self-contained uv project
(ISQ population scenarios → cohort roll-forward → excess-demand rankings) whose
`ScenarioPrior` JSON artifacts feed hde's `market_scenario` slot. hde does NOT
need it to run: the golden prior used by the tests and the living showcase is
committed at `../tests/fixtures/scenario_prior_golden.json`, and the engine
consumes finished artifacts over a validated file contract (demoflow spec §7(a)),
never demoflow code. One deliberate teaser: demoflow's dev environment depends
on a private `actuarial-system` package (see `pyproject.toml`), so a public
cloner can read and audit this pipeline but cannot `uv sync` it. To run its
suite: `cd demoflow && uv sync --extra dev && uv run python -m pytest` — or run
both suites from the repo root with `./scripts/test-all.sh`.
