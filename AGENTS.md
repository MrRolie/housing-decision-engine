# Housing Decision Engine — AGENTS.md

Canonical operational rules for this repo. Claude reads this first.

## What This Repo Is

Present value comparison engine for housing decisions: rent vs condo vs house.
Extends to employment cash flow modeling and real estate market scenario analysis.
Primary surface: the `hde` CLI — `--json` for agents, `--print-schema` for the input
contract, `--print-anchors` for provenance (surface doctrine, `CLAUDE.md`). The MCP
server remains for non-shell consumers only.

## Scope

Personal financial tooling, for the author's own use. Nothing here places trades or moves
money — it computes present-value comparisons from parameters you supply.

## Package layout

```
src/hde/            # Core engine (Python package)
  anchors.py        # Provenance registry: every engine default with source/url/band/kind;
                    #   SOURCE_KEY_CITATIONS for the demographic prior's inputs
  models.py         # Dataclasses: params + results (ComparisonSpec, …), Verdict + compute_verdict
  pv.py             # Pure PV utility functions (annuities, mortgage math, monthly equivalent)
  deterministic.py  # Deterministic PV engine (compute_deterministic(spec: ComparisonSpec))
  monte_carlo.py    # Monte Carlo simulation engine (run_monte_carlo(spec: ComparisonSpec))
  market_scenario.py# ScenarioPrior loader + validation, time-anchor guard, prior.describe()
  config.py         # YAML config loader (load_config_dict → ComparisonSpec), warnings
  input_schema.py   # The input contract as data (--print-schema)
  serialization.py  # THE typed core for agent output: results, assumptions, verdict, anchors
  reporting.py      # Text report + legacy matplotlib figures
  story_plots.py    # The six-act decision story (plots)
  story_page.py     # STORY.md one-pager + report.txt package (--story)
  cli.py            # CLI entry point (hde)
mcp_server/         # MCP server (FastMCP, stdio transport) — non-shell consumers only
  main.py           # FastMCP entry point + @mcp.tool wrappers
  registry.py       # In-memory ScenarioEntry store (spec: ComparisonSpec)
  tools.py          # 6 tool implementations (serialization via hde.serialization)
tests/              # pytest suite (fixtures/ holds the golden ScenarioPrior)
examples/           # Example YAML scenario configs + ordered walkthrough (README.md)
docs/
  roadmaps/         # Roadmap spines (do not edit arc spine)
  specs/            # Design docs (incl. the provenance-remediation citation table)
  plans/            # Implementation plans (incl. the 2026-09-01 readiness plan)
  reference/        # ARCHITECTURE (figure glossary), API_CONTRACT, CONFIG_SCHEMAS, DEV_NOTES
  research/         # Research records
  story/            # Living showcase: six-act PNGs + STORY.md + report.txt
  archive/notebooks/# Deprecated Jupyter notebooks
```

## Consumer layers (operator doctrine, 2026-08-24)

This repo serves TWO consumer layers, and every output surface is designed for both:

1. **Agents and other systems** — the `hde-mcp` MCP server, the `hde` CLI, and the Python
   library. Typed inputs/outputs, deterministic, seeded. demoflow consumes the actuarial
   package through this layer's discipline.
2. **The personal consumer using Claude as the interface** — Mike making his own
   rent/buy/house decisions through conversation. Not a separate build yet; today's CLI,
   YAML scenarios, and reports are its seed.

Binding design constraint: anything emitted by this engine must be **person-readable** —
a number that cannot be explained to the layer-2 consumer in one paragraph does not ship.
Layer 1 is built; layer 2 is a constraint on everything built now, not a build item.

## Entry points

```bash
# CLI (the registered surface)
uv run hde --print-schema                                   # input contract
uv run hde --print-anchors                                  # provenance registry
uv run hde <config.yaml> [--no-monte-carlo] [--quiet] [--json] [--story DIR]

# Tests
uv run --extra dev python -m pytest -q

# MCP server — non-shell consumers (claude.ai web) only; needs the `mcp` extra
uv run --extra mcp hde-mcp
# claude mcp add hde -- uv --directory /path/to/housing-decision-engine run --extra mcp hde-mcp
```

## Development setup

```bash
uv sync --extra dev
./scripts/test-all.sh          # CANONICAL full-suite check (hde + demoflow) — run this before any PR
uv run python -m pytest        # hde suite ONLY: root testpaths excludes demoflow/tests/ (a separate uv project)
uv run hde examples/basic_config.yaml
```

`demoflow/` is a self-contained uv project (own env, own tests); the repo-root `pytest` never
runs it. `scripts/test-all.sh` runs BOTH suites and fails if either fails — it is the canonical
full-suite invocation.

## Key design decisions (stable)

- **ComparisonSpec** is the single input bundle for all engines — replaces the old `(condo, house, sim, econ)` 4-tuple. All options (condo, house, rent, income) are Optional; at least one of condo/house/rent must be present.
- **3-way comparison** — rent, condo, house are all first-class options. Rent PV includes `invested_dp_benefit_pv = dp × (1+r_inv)^N / (1+dr)^N` (negative, reduces total cost).
- **Affordability layer** — `IncomeParams` + `PayDropEvent` produce per-year housing-cost/income ratios returned inline in `run_comparison` as `"affordability"` key.
- **Deterministic + Monte Carlo** run as separate engines; deterministic is the sanity check, MC is the uncertainty surface.
- **YAML config** is the input contract — scenarios are files, not code. `load_config_dict` returns `ComparisonSpec`.
- **Pure functions** throughout — no global state, seeded RNG for reproducibility.
- **MCP tools** wrap the existing engine; no engine logic in the MCP layer.
- **Session registry** (`registry.py`) is in-process, process-scoped — cleared on server restart. Stores `spec: ComparisonSpec` (not a 4-tuple).
- **MC numpy arrays** never cross the MCP boundary; only `MonteCarloSummary` scalars + `prob_X_cheapest` returned.
- **store_results** uses total-replace semantics — running deterministic-only clears cached MC results.
- **Scenario names** are sanitized via `Path(name).name` before joining figure paths.
- **sweep_param** whitelist has 24 paths; rent paths require `spec.rent is not None`.
- **Breakdown keys** centralized as `CONDO_BREAKDOWN_KEYS`, `HOUSE_BREAKDOWN_KEYS`, `RENT_BREAKDOWN_KEYS` frozensets.
- **Anchors doctrine** — `src/hde/anchors.py` is the single source of truth for every bias-critical engine default (the rates, thresholds and shock hyperparameters that shape a verdict; structural knobs such as `num_sims` and the zero vols are not anchored, by design). An uncited entry is a defect (`AnchorError` at import); re-anchoring requires a `replaces` note; a live URL requires `retrieved_on`. `tests/test_anchors.py` is generative: every anchor is wired to a dataclass default or declared consumed elsewhere, and every key the assumptions echo can emit resolves to an anchor. Examples cite sources inline or mark values `illustrative`; the `defaults_applied` echo carries citation tags; `--print-anchors` and the `assumptions` JSON block expose the full records.
- **One verdict** — `models.compute_verdict` (MC probability floor 0.65, else 5% tie band; both anchored) is consumed by the story headline, the text report, `--json` and MCP. No surface computes its own margin.

## Roadmap

Active roadmap: `docs/roadmaps/2026-06-07_housing-decision-engine.md`

Sessions:
- S1 ✅ Repo foundation (2026-06-07, PR #2)
- S2 ✅ MCP server — 6 tools (2026-06-08, PR #2)
- S3 ✅ 3-way comparison + income model (2026-06-08, PR #3)
- S4a ✅ Net-wealth foundation: mortgage amortization + terminal equity (2026-07-21, PR #4)
- S4b ✅ Market scenario layer: demographic drift priors + tilted price-shock channel (2026-08-26, 8ceb010 / 0e2116e; `docs/specs/2026-08-26-s4b-demographic-input-slot-sketch.md`)
- Surface + provenance ✅ CLI-first doctrine, anchors registry, one verdict, figure glossary (2026-08-26 → 2026-09-01; `docs/plans/2026-09-01-readiness-polish.md`, `docs/specs/2026-09-01-provenance-remediation-design.md`)

## Do not

- Add geographic tax rules (explicitly out of scope — see roadmap)
- Add mortgage *optimization* / refinancing / variable-rate modeling (out of scope). NOTE: mortgage amortization + terminal equity ARE modeled as of S4a (2026-06-08); the rent-vs-buy DCF is leveraged.
- Add dependencies on private or unpublished repos — this is standalone personal tooling
