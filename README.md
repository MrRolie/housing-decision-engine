# Housing Decision Engine

![The answer](docs/story/act1_the_answer.png)

A present-value comparison engine for housing decisions — rent vs condo vs house on a
net-wealth basis — with demographic scenario priors from a UN-data pipeline.

## What you get

- **3-way PV comparison** — rent / condo / house, leveraged or all-cash, with end-of-horizon equity credited back
- **Monte Carlo uncertainty** — full cost distributions and P(each option cheapest), seeded and reproducible
- **Demographic priors via `ScenarioPrior`** — UN WPP → ISQ scenario → demand-model drift bands that tilt price growth and crash risk by geography
- **Six-act story plots** — the verdict (with a decisiveness rule, never a coin flip dressed as a win), the cost race, uncertainty, home-value futures, the demographic signal, the break-even market line ([docs/story/STORY.md](docs/story/STORY.md))
- **Insured mortgages priced, not recalled** — `mortgage_insurance: auto` picks the CMHC tier from the anchored premium schedule, finances the premium and pays the provincial tax on it in cash, re-deriving the tier at every `--sweep` / `--break-even` grid point
- **A source class for every value you state** — an optional `sources:` block marks each input `user`, `assistant` or `anchor:<name>`, so the read-back can tell your numbers from the ones someone typed for you; when Monte Carlo decisiveness rests on uncertainty inputs you never stated, the engine says so and prices the deterministic alternative
- **Provenance for every default** — a registry with source, URL, band and retrieval date (`hde --print-anchors`), echoed as `assumptions` in `--json`, plus a figure glossary for every printed number ([docs/reference/ARCHITECTURE.md](docs/reference/ARCHITECTURE.md))
- **Published property-tax and home-insurance figures by jurisdiction** — municipal rates for Laval, Montréal, Québec City and Toronto, and provincial home-insurance figures for QC and ON, each with the figure as its source quotes it and the base it is levied on (assessed value, which is not market value). The engine applies none of them: they are there so your own figure gets cited when it matches, and so a jurisdiction with no source says `source: none` (Gatineau, Ottawa) instead of guessing

## Test drive

1. Install [uv](https://docs.astral.sh/uv/) and [Claude Code](https://docs.anthropic.com/en/docs/claude-code).
2. `git clone https://github.com/MrRolie/housing-decision-engine.git && cd housing-decision-engine`
3. `claude` — accept the one-time dialog listing what this folder pre-approves (running the
   engine, writing your scenario under `scenarios/`), then ask in plain words, e.g.
   *"I pay $2,100 rent and condos like mine go for $450k. Should I buy?"*

Claude follows the repo's `hde` skill: it asks for whatever your question is missing
(how long you'll stay, how you'd pay, …), writes your scenario to `scenarios/` (git-ignored),
runs the engine, reads every assumption back with its source, and gives the verdict with its
decisiveness. Nothing to install beyond `uv`: the first run fetches the engine's dependencies.

Without Claude:

```bash
uv run hde examples/basic_config.yaml   # a worked scenario
uv run hde --print-schema               # every input and what is required
uv run hde --print-anchors              # where every default comes from
uv run hde examples/mortgage_house_vs_rent.yaml --break-even rent.monthly_rent   # the rent at which renting and buying tie
```

## The showcase

```bash
uv run hde examples/showcase_demographic_prior.yaml --story docs/story
```

Renders the full six-act story under the MTL_RMR demographic prior — the committed
[docs/story/STORY.md](docs/story/STORY.md) is this command's output, regenerable at any time.

> **Surface doctrine (2026-08-26; MCP server removed 2026-09-01):** the interface is the **`hde` CLI + the repo-local `hde` skill** (`.claude/skills/hde/SKILL.md` plus its `references/`, the dispatch contract Claude follows). `uv run hde --print-schema` is the input contract, `--print-anchors` the provenance registry.

## Repo map

```
src/hde/             # Core engine: models, pv, deterministic, monte_carlo,
                     #   config (YAML → ComparisonSpec), market_scenario (prior loader),
                     #   reporting, story_plots (six acts), story_page (STORY.md), cli,
                     #   anchors (provenance registry), sources (who stated each value),
                     #   serialization (--json core), input_schema
examples/            # Scenario YAMLs + ordered walkthrough (examples/README.md)
tests/               # pytest suite (fixtures/ holds the golden ScenarioPrior)
docs/
  story/             # Living showcase: six-act PNGs + STORY.md + report.txt
  roadmaps/ specs/ plans/ reference/ research/ archive/
demoflow/            # Self-contained uv project — the upstream demand-model pipeline
```

## Going deeper

- **Example walkthrough** — [examples/README.md](examples/README.md): the smallest config that runs, then five scenarios in reading order
- **Every figure explained** — [docs/reference/ARCHITECTURE.md](docs/reference/ARCHITECTURE.md) § Figure glossary; every default's source — `uv run hde --print-anchors`
- **Library use** — all engines take a single `ComparisonSpec`; see `src/hde/__init__.py` exports
- **Roadmap** — `docs/roadmaps/2026-06-07_housing-decision-engine.md`

## Tests

```bash
uv run --extra dev python -m pytest -q
```
