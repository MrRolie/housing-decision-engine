# Housing Decision Engine — CLAUDE.md

Claude-specific guidance. Operational rules are in `AGENTS.md`.

## Working reflexes for this repo

- New feature design → design doc in `docs/specs/` before code (always)
- Multi-step implementation → write the plan in `docs/plans/` first, then execute it task-by-task
- Bug / unexpected behavior → reproduce with a failing test before proposing a fix
- MCP server questions → follow the existing FastMCP pattern in `mcp_server/main.py`

## What the MCP server exposes

Six tools registered in `mcp_server/main.py`, implemented in `mcp_server/tools.py`. Scenarios are
held in an in-process registry, so they reset when the server restarts.

- `define_scenario_tool(name, config)` — define a named scenario from a config dict
- `run_comparison_tool(name, mode)` — deterministic, monte_carlo, or both
- `sweep_param_tool(name, param_path, values)` — sweep one whitelisted scalar parameter
- `save_figure_tool(name, figure_type)` — write a figure to `~/.cache/hde/figures/`, return its path
- `list_scenarios_tool()` — list session scenarios and whether results are cached
- `delete_scenario_tool(name)` — drop a scenario from the registry

## Testing

```bash
uv run python -m pytest          # all tests
uv run python -m pytest -x -q   # fail-fast
```

## Scope

Personal decision-support tooling. Nothing here places trades or moves money, so changes do not
need the heavier adversarial-review process that live financial code would warrant.
