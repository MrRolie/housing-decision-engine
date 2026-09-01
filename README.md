# Housing Decision Engine

![The answer](docs/story/act1_the_answer.png)

A present-value comparison engine for housing decisions — rent vs condo vs house on a
net-wealth basis — with demographic scenario priors from a UN-data pipeline.

## What you get

- **3-way PV comparison** — rent / condo / house, leveraged or all-cash, with end-of-horizon equity credited back
- **Monte Carlo uncertainty** — full cost distributions and P(each option cheapest), seeded and reproducible
- **Demographic priors via `ScenarioPrior`** — UN WPP → ISQ scenario → demand-model drift bands that tilt price growth and crash risk by geography
- **Five-act story plots** — verdict, the cost race, uncertainty, home-value futures, the demographic signal ([docs/story/STORY.md](docs/story/STORY.md))
- **MCP server for Claude** — six tools, no notebooks required

## Quickstart

```bash
git clone https://github.com/MrRolie/housing-decision-engine.git
cd housing-decision-engine
uv sync --extra dev
uv run hde examples/basic_config.yaml
```

## The showcase

```bash
uv run hde examples/showcase_demographic_prior.yaml --story docs/story
```

Renders the full five-act story under the MTL_RMR demographic prior — the committed
[docs/story/STORY.md](docs/story/STORY.md) is this command's output, regenerable at any time.

> **Surface doctrine (2026-08-26):** the primary interface is the **`hde` CLI + the `hde` skill** (dispatch contract for agents — `~/.claude/skills/hde/`). The MCP server below remains for non-shell consumers (claude.ai web) only; it is not the registered surface for local sessions.

## MCP server

```bash
uv run hde-mcp
# Register with Claude Code:
claude mcp add hde -- uv --directory /path/to/housing-decision-engine run hde-mcp
```

For Claude Desktop, add this to `claude_desktop_config.json` (replace
`/ABS/PATH/housing-decision-engine` with your clone's absolute path):

```json
{
  "mcpServers": {
    "hde": {
      "command": "uv",
      "args": ["--directory", "/ABS/PATH/housing-decision-engine", "run", "hde-mcp"]
    }
  }
}
```

Claude Desktop does not inherit your shell `PATH` — if the server fails to start, replace `"command": "uv"` with the absolute path to your uv binary (find it with `which uv`).

Six tools: `define_scenario_tool`, `run_comparison_tool`, `sweep_param_tool` (24 whitelisted
parameters), `save_figure_tool`, `list_scenarios_tool`, `delete_scenario_tool`. Scenarios live
in an in-process registry that resets on restart.

## Repo map

```
src/hde/             # Core engine: models, pv, deterministic, monte_carlo,
                     #   config (YAML → ComparisonSpec), market_scenario (prior loader),
                     #   reporting, story_plots (five acts), story_page (STORY.md), cli
mcp_server/          # FastMCP server (stdio): main, registry, tools
examples/            # Scenario YAMLs + ordered walkthrough (examples/README.md)
tests/               # pytest suite (fixtures/ holds the golden ScenarioPrior)
docs/
  story/             # Living showcase: five-act PNGs + STORY.md + report.txt
  roadmaps/ specs/ plans/ reference/ research/ archive/
demoflow/            # Self-contained uv project — the upstream demand-model pipeline
```

## Going deeper

- **Example walkthrough** — [examples/README.md](examples/README.md): four scenarios in reading order
- **Library use** — all engines take a single `ComparisonSpec`; see `src/hde/__init__.py` exports
- **Roadmap** — `docs/roadmaps/2026-06-07_housing-decision-engine.md`

## Tests

```bash
uv run --extra dev python -m pytest -q
```
