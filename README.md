# Housing Decision Engine

Present value comparison engine for housing decisions — rent vs condo vs house —
with employment cash flow modeling, real estate market scenario analysis,
and an MCP server so Claude can run comparisons directly.

## Features

- **3-way PV comparison** — rent / condo / house, on a net-wealth basis
- **Deterministic + Monte Carlo** — fixed-parameter estimate + full uncertainty distribution
- **Leveraged purchases** — mortgage amortization and terminal equity, or all-cash
- **Employment cash flow** — income trajectories, pay-drop events, per-year affordability ratios
- **Parameter sensitivity** — sweep any of 24 whitelisted parameters (rates, growth, fees, financing)
- **MCP server** — 6 Claude-callable tools, no notebooks required
- **CLI** — `hde` command for standalone use
- **YAML scenarios** — config files for reproducible comparisons

A dedicated market-scenario layer (correlated price shocks driven by scenario priors) is designed
but not built — see the roadmap.

## Installation

```bash
git clone https://github.com/MrRolie/housing-decision-engine.git
cd housing-decision-engine
uv sync --extra dev
```

## Quick Start

```bash
# Run a scenario
uv run hde examples/basic_config.yaml

# Deterministic only
uv run hde examples/basic_config.yaml --no-monte-carlo

# Summary line only
uv run hde examples/basic_config.yaml --quiet
```

## MCP Server

Claude can call the engine directly over MCP — no YAML file required. The server runs on stdio
via FastMCP:

```bash
uv run hde-mcp

# Register with Claude Code:
claude mcp add hde -- uv --directory /path/to/housing-decision-engine run hde-mcp
```

Six tools are registered:

| Tool | What it does |
|------|--------------|
| `define_scenario_tool(name, config)` | Define a named scenario from a config dict |
| `run_comparison_tool(name, mode)` | Run `deterministic`, `monte_carlo`, or `both` |
| `sweep_param_tool(name, param_path, values)` | Sweep one whitelisted scalar parameter |
| `save_figure_tool(name, figure_type)` | Save a figure to `~/.cache/hde/figures/`, return its path |
| `list_scenarios_tool()` | List session scenarios and their cached-result status |
| `delete_scenario_tool(name)` | Remove a scenario from the registry |

Scenarios live in an in-process registry — they reset when the server restarts.

## As a Library

```python
from hde.models import CondoParams, HouseParams, SimulationParams, EconomicParams, ComparisonSpec
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo

# Owned options need a capital structure: all_cash=True OR a mortgage block
# (down_payment + mortgage_rate + mortgage_term_years). Condo needs initial_value > 0.
condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.02,
                    initial_value=350_000, all_cash=True)
house = HouseParams(initial_value=400_000, annual_maintenance_rate=0.015, all_cash=True)
sim = SimulationParams(years=20, discount_rate=0.03)
econ = EconomicParams()

# All engines take a single ComparisonSpec (condo/house/rent/income are optional).
spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)

det = compute_deterministic(spec)
mc = run_monte_carlo(spec)

print(f"Condo net-wealth PV: ${det.condo.total_pv:,.0f}")
print(f"House net-wealth PV: ${det.house.total_pv:,.0f}")
print(f"P(condo cheapest):   {mc.prob_condo_cheapest:.1%}")
```

## Configuration

YAML scenario files. See `examples/` for templates.

```yaml
years: 20
discount_rate: 0.03

condo:
  monthly_fee: 400
  fee_escalation_rate: 0.02
  initial_value: 350000   # required (> 0) in the net-wealth model
  all_cash: true          # declare all_cash OR a mortgage block
                          # (down_payment + mortgage_rate + mortgage_term_years)

house:
  initial_value: 400000
  annual_maintenance_rate: 0.015
  all_cash: true
  events:
    - name: "roof"
      base_cost: 12000
      expected_year: 15
      timing_std_years: 2
      cost_vol: 0.25

simulation:
  num_sims: 10000
  random_seed: 42
  house_maintenance_vol: 0.30
  condo_fee_vol: 0.05
```

## Project Structure

```
src/hde/            # Core engine
  models.py         # Dataclasses: params + results
  pv.py             # PV utility functions
  deterministic.py  # Deterministic engine
  monte_carlo.py    # Monte Carlo engine
  config.py         # YAML config loader
  reporting.py      # Reports + plots
  cli.py            # CLI entry point
mcp_server/         # MCP server (FastMCP, stdio)
  main.py           # Entry point + tool registrations
  registry.py       # In-memory scenario store
  tools.py          # Tool implementations
examples/           # Scenario YAML files
tests/              # Test suite
docs/
  roadmaps/         # Project roadmaps
  specs/            # Design docs
  plans/            # Implementation plans
  reference/        # Architecture + API docs
  research/         # Research dossiers
  archive/          # Deprecated notebooks
```

## Tests

```bash
uv run python -m pytest
```

## Roadmap

See `docs/roadmaps/2026-06-07_housing-decision-engine.md` for the full arc:
- S1 ✅ Repo foundation (rename, uv, AGENTS.md, CLAUDE.md)
- S2 ✅ MCP server
- S3 ✅ Rent option + employment cash flow
- S4a ✅ Net-wealth foundation (mortgage amortization + terminal equity)
- S4b Market scenario layer — not started
