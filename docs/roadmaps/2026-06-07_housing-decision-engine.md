# Housing Decision Engine — Roadmap

## Status

**Overall:** S1–S4b complete; the 2026-09-01 readiness polish landed on `feat/readiness-polish` (anchors registry with verified citations, one decisiveness rule across every surface, `--json` provenance, a truthful `--print-schema`, the figure glossary). **Remote caveat (2026-09-01):** `origin` was rebuilt the same day as a fresh single-commit history (`fb840ee`); this branch shares no history with it. Reconcile by a fresh clone plus replaying these commits' content — never merge, rebase, or force-push the existing branch — and pass the operator's content scan before opening a PR. Then the deferred items in `docs/plans/2026-09-01-readiness-polish.md` (mypy ruling, the demoflow emitter citation path E.5).
**Created:** 2026-06-07
**Last Updated:** 2026-09-01
**Slug:** `housing-decision-engine`

### Session Status

| Session | Type | Status | Artifact path(s) (resume contract) | Notes |
| --- | --- | --- | --- | --- |
| 1 | decisive | `completed` | the repo root | Rename + uv + AGENTS.md/CLAUDE.md + docs structure |
| 2 | brainstorm-to-execute | `completed` | `mcp_server/` — PR #2 commit `79b3a56` | 6 MCP tools, 115 tests, FastMCP stdio |
| 3 | brainstorm-to-execute | `completed` | `docs/plans/archive/2026-06/2026-06-08-rent-income-model.md` — PR #3 commit `6121f1a` | ComparisonSpec refactor, RentParams + PV, IncomeParams + AffordabilityReport, 151 tests |
| 4a | brainstorm-to-execute | `completed` | `docs/specs/2026-06-08-net-wealth-foundation-design.md` — PR #4, branch tip `b99a6b3`, 176 tests pass (2026-07-21) | Net-wealth foundation: rent-vs-buy DCF (mortgage amortization + terminal equity, house+condo). Split out of original S4. |
| 4b | brainstorm-to-execute | `completed` | `docs/specs/2026-08-26-s4b-demographic-input-slot-sketch.md` — commits `8ceb010`, `0e2116e` (2026-08-26) | Market scenario layer: demographic drift priors (demoflow ScenarioPrior) + tilted price-shock channel; correlated market+income shocks and the pre-canned stress configs were NOT built — the prior replaced the hand-authored scenario menu. |
| readiness | plan-to-execute | `completed` | `docs/plans/2026-09-01-readiness-polish.md` (branch `feat/readiness-polish`) | Provenance + verdict + intake + glossary + hygiene; suite 440+ tests. |

Status values: `not_started`, `in_progress`, `blocked`, `completed`.
A `completed` row MUST carry a real, stat-able artifact path — repo-relative here, because this repo is public and an absolute path discloses the machine's layout.

### Hand-off Payload

- **Next session:** replay `feat/readiness-polish` onto a fresh clone of the rebuilt `origin` (content replay, not a push of this branch), run the operator's content scan, then PR + merge; then the deferred ruling on mypy (fix + gate, or drop the config) and whether demoflow's emitter should embed source citations (plan E.5, cross-contract).
- **Input artifacts it consumes:** the readiness plan, `docs/specs/2026-09-01-provenance-remediation-design.md` (citation table), `tests/test_anchors.py` (generative pins).
- **Mid-session resume state:** N/A.

### Decisions / Deviations

- **2026-06-07:** Selected 4-session structure (S1 structural, S2 MCP, S3 rent+income, S4 market scenarios). Operator confirmed.
- **2026-06-07:** New repo/package name: `housing-decision-engine` (dir) / `hde` (Python package slug). Operator chose `hde` over `housing_decision_engine`.
- **2026-06-07:** Scope expanded beyond original cost-sim to include employment cash flow modeling and real estate market scenario/sensitivity analysis — making this a personal financial scenario engine, not just a cost comparator.
- **2026-06-07 (S1 complete):** `src/cvh_cost/` → `src/hde/`, setuptools → hatchling, entry point `cvh-cost` → `hde`, Python floor bumped 3.9→3.10. 76 tests pass; `uv.lock` committed.
- **2026-06-08 (S2 complete):** FastMCP server with 6 tools (define_scenario, run_comparison, sweep_param, save_figure, list_scenarios, delete_scenario). Session registry with total-replace store_results semantics. 11 PR review findings addressed (path traversal, stale MC, mode validation, backend import order). 115 tests pass. PR #2 merged.
- **2026-06-08 (S4 design — split + leverage re-scope):** Code inspection found the engine is carrying-cost-only — `house_value` compounds but is never harvested as equity, no mortgage/interest rate, and the rent side is one-sidedly credited the invested-DP benefit. Price-drop scenarios were therefore wrong-signed/inert. Operator decisions: (D1) net-wealth comparator; (D2) **full mortgage/amortization DCF** ("full-value − financing carry", the long-term-correct model) — **re-opens the "mortgage/leverage modeling" out-of-scope boundary** (in-conversation instruction overrides roadmap, Authority Hierarchy #1); (D3) "interest rate shock" reinterpreted as discount-rate sensitivity (S4b); (D4) **split S4 → S4a foundation + S4b scenario layer**; (D5) net-wealth canonical (no legacy mode; affected tests rewritten against an independent oracle); (D6) required explicit capital structure (mortgage XOR all_cash) on owned options. Elegance-gate (architectural + strategic) both PROCEED-WITH-MODIFICATIONS, no second split; mods folded (pv_annuity reuse + closed-form balance, shared `_financing_pv`, compositional oracle-anchored test assertions, oracle-first ordering, 74-fixture `all_cash` stub pass, dual-layer fail-loud, AGENTS.md "do not add mortgage" line struck). Spec: `docs/specs/2026-06-08-net-wealth-foundation-design.md`.
- **2026-08-26 (S4b, surface doctrine):** S4b built as demographic input slots consuming demoflow's ScenarioPrior instead of a hand-authored shock menu; CLI-first doctrine — MCP demoted to non-shell consumers.
- **2026-09-01 (readiness):** decisiveness rule ruled (MC floor 0.65, tie band 5%); `house.annual_maintenance_rate` a registered neutral with a warning; mortgage convention disclosed, not changed; prior citations hde-side (`SOURCE_KEY_CITATIONS`), emitter contract untouched; mypy deferred.
- **2026-09-01 (MCP removed):** operator ruling — the MCP server (S2) is superseded; the only surface is the CLI plus the repo-local skill, and the user flow is clone → launch Claude Code in the repo → ask, with the skill eliciting whatever the question lacks.

### Next Recommended Action

Operator-triggered: fresh clone of the rebuilt `origin`, replay the `feat/readiness-polish` commits' content onto it, content scan, then the PR (run `bash scripts/test-all.sh` there first; regenerate `docs/story/` and confirm `git status` clean on a second render). Do not push, merge, or rebase this clone's existing branches.

---

## Goal

- **Core goal:** Transform `condo-vs-house-cost-sim` into `housing-decision-engine` — a Claude Code native agent system that provides a 3-way rent/condo/house PV comparison engine with employment cash flow modeling and real estate market scenario analysis, callable via MCP.
- **Intended end-state:** Claude can invoke MCP tools to run housing comparisons, model income trajectories with pay-drop events, stress-test scenarios against real estate market shocks, and produce structured decision reports — all without opening a notebook.
- **Scope boundary:**
  - IN: 3-way comparison (rent / condo / house); employment cash flow with income-shock events; real estate market scenarios (price drops, rate shocks); MCP server with Claude-callable tools; CLI for standalone use; YAML scenario configs; repo aligned with projects/ conventions.
  - OUT: Geographic tax rules; mortgage optimization / leverage modeling; investment portfolio returns (opportunity cost of down payment deferred to S3 design decision); multi-user / SaaS product concerns; production deployment beyond a single local host.
- **Repo:** this repository (renamed to `housing-decision-engine` in S1) · **Target repo:** same

## Success Criteria

- [ ] Repo renamed to `housing-decision-engine/`; Python package slug finalized; all existing tests pass under uv
- [ ] AGENTS.md and CLAUDE.md present and aligned with projects/ conventions
- [ ] MCP server running locally; Claude can call `compare_housing`, `run_scenario`, `sensitivity_sweep` tools
- [ ] Rent modeled as a first-class option alongside condo and house in all engines (deterministic + Monte Carlo)
- [ ] Employment cash flow model: income trajectory, pay-drop events, and their effect on affordability/comparison scores
- [ ] Market scenario layer: real estate price shock, interest rate sensitivity, correlated income + market shocks in Monte Carlo
- [ ] No notebooks required for any comparison — MCP tools cover all prior notebook use cases
- [ ] Scope honored — personal tooling only

## Session Plan

Sessions are work chunks delimited by **recovery-point value**. Each session
internally runs the 5-phase arc collapsed per its type.

### Session 1 — Decisive: Repo Foundation

**Type:** decisive (all decisions made; purely structural execution)

**Pre-flight checklist (run at session start):**
1. Confirm final Python package slug (`hde` vs `housing_decision_engine`) — one `AskUserQuestion` at session top
2. `uv` installed locally (`which uv`)
3. Current test suite green under existing setup (`pytest`)

**Phase 4 Execute:**
- Rename Python package: `src/cvh_cost/` → `src/<slug>/`; update all internal imports and pyproject.toml entry points
- Migrate build system: setuptools → hatchling; generate `uv.lock` via `uv sync`
- Add `AGENTS.md` covering: repo purpose, entry points, how to run MCP server (placeholder), test commands, key design decisions
- Add `CLAUDE.md` covering: Claude-specific hints, skill reflexes for this repo, what the MCP server exposes
- Move `context/` → `docs/reference/`; create `docs/roadmaps/`, `docs/specs/`; move roadmap file to new path
- Archive `notebooks/` → `docs/archive/notebooks/` with a deprecation note
- Update `README.md` with new name, new install commands, and placeholder MCP section

**Phase 5 Verify:**
- `uv run pytest` — all existing tests green
- `uv run <new_entry_point> examples/basic_config.yaml` — CLI smoke-test
- `git diff --stat` confirms no logic files changed, only structure

**End-of-session gate:** All existing tests pass; `uv sync` clean; AGENTS.md + CLAUDE.md committed; repo dir renamed (or noted as deferred to a post-session `mv` if git history preservation requires it).

---

### Session 2 — Brainstorm-to-Execute: Agent-Native Layer (MCP Server)

**Type:** brainstorm-to-execute

**Phase 2 — Design:**
- What tools should the MCP server expose? (e.g. `compare_housing`, `run_scenario`, `list_scenarios`, `sensitivity_sweep`, `explain_result`)
- Input/output contract: structured JSON vs YAML passthrough vs natural language?
- FastMCP vs raw MCP SDK (pattern from `actuarial-system`)
- Tool granularity: one fat tool vs many thin tools

**Phase 3 — Plan:**
- Spec written to `docs/specs/YYYY-MM-DD-mcp-server-design.md`
- Plan covers: `mcp_server/` directory structure, tool implementations, error handling, stdio transport config

**Phase 4 — Execute:**
- Scaffold `mcp_server/` with FastMCP
- Implement tools wrapping existing `deterministic.py` + `monte_carlo.py`
- Add MCP entry point to `pyproject.toml`
- Update AGENTS.md with MCP server launch command

**Phase 5 Verify:**
- Claude can call the MCP tools in-session (invoke `compare_housing` with `examples/basic_config.yaml`)
- All existing tests still green
- MCP smoke-test: structured result returned for basic scenario

**End-of-session gate:** Claude can call at least `compare_housing` via MCP and get a structured result; no regressions.

---

### Session 3 — Brainstorm-to-Execute: Model Extensions (Rent + Employment Cash Flow)

**Type:** brainstorm-to-execute

**Phase 2 — Design:**
- Rent model: `RentParams` dataclass — monthly rent, escalation rate, lease events (renewal shocks, moving costs), opportunity cost of down payment (include? defer?), lease optionality
- Employment cash flow: `EmploymentParams` — income trajectory, pay-drop events (year + magnitude), employment gap events; how income integrates with the comparison (affordability ratio? affordability-adjusted PV?)
- Does income affect the *cost comparison* or is it a separate affordability overlay?
- 3-way comparison output shape: deterministic + MC for rent alongside condo + house

**Phase 3 — Plan:**
- Spec: `docs/specs/YYYY-MM-DD-rent-income-model-design.md`
- Plan: `RentParams` + `EmploymentParams` dataclasses; `compute_deterministic` extended for 3-way; `run_monte_carlo` extended; new MCP tools (`compare_all_three`, `model_income_scenario`)

**Phase 4 — Execute:**
- Add `RentParams` + rent PV logic to `deterministic.py` and `monte_carlo.py`
- Add `EmploymentParams` + income shock modeling
- Extend `reporting.py` for 3-way output
- Add new MCP tools for rent + income scenarios
- Update example YAML configs

**Phase 5 Verify:**
- `uv run pytest` — all tests green including new rent + income tests
- MCP tool: 3-way comparison callable from Claude
- Sanity check: renting a $2500/month apartment vs buying — deterministic result makes intuitive sense

**End-of-session gate:** 3-way rent/condo/house comparison works; income shock scenarios callable via MCP.

---

### Session 4 — Brainstorm-to-Execute: Market Scenario Layer

**Type:** brainstorm-to-execute

**Phase 2 — Design:**
- Real estate market scenarios: price-drop events (year + magnitude + recovery rate), interest rate shocks, how correlated market + income shocks work in Monte Carlo
- Sensitivity sweep API: which parameters to sweep, how results are returned for Claude to interpret
- "What if market drops 20% in year 5?" — how does this change the PV comparison?
- Stress-test surface: which scenarios should be pre-canned in example configs?

**Phase 3 — Plan:**
- Spec: `docs/specs/YYYY-MM-DD-market-scenario-design.md`
- Plan: `MarketScenarioParams`; correlated shock model; `sensitivity_sweep` MCP tool; stress-test example configs

**Phase 4 — Execute:**
- Add `MarketScenarioParams` + market shock logic to Monte Carlo
- Implement correlated income + real estate shocks
- Add `sensitivity_sweep` and `stress_test` MCP tools
- Add pre-canned scenario configs (market crash, rate spike, pay cut)

**Phase 5 Verify:**
- All tests green
- Correlated shock sanity check: market drop + pay cut produces worse rent break-even than either alone
- MCP `stress_test` callable; result is interpretable structured JSON
- verification-before-completion pass

**End-of-session gate:** Full scenario engine operational; wrap-up performed after merge.

---

## Session Sequencing

| Session | Type | Internal arc | Est. duration | End-of-session gate |
| --- | --- | --- | --- | --- |
| 1 | decisive | Phase 4 + 5 only | 1–2h | All tests green, uv clean, AGENTS.md committed |
| 2 | brainstorm-to-execute | Full 5-phase arc | 3–4h | Claude can call MCP tools against existing engine |
| 3 | brainstorm-to-execute | Full 5-phase arc | 4–5h | 3-way comparison + income shocks callable via MCP |
| 4 | brainstorm-to-execute | Full 5-phase arc | 3–4h | Market scenario layer complete; plan-completion-wrap-up done |

## Session Count Rationale

**Why 4 and not 3:** S3 (rent + income) and S4 (market scenarios) have meaningfully different design surfaces — rent is a parallel cost stream; market scenarios require correlated shock modeling and Monte Carlo extension. Combining them would rush two genuinely separate brainstorm passes into one session. The S3 artifact (3-way comparison with income) is a real recovery point that S4 consumes as input.

**Why S1 is its own session and not a pre-flight checklist:** The rename + uv migration involves judgment calls (final package slug, deciding what to put in AGENTS.md) that make it slightly more than purely pre-enumerable. If it turns out to be fully mechanical, it can be collapsed into a pre-flight checklist at the top of S2 — note this in the S2 hand-off.

**Why S2 is brainstorm-to-execute:** The MCP surface (tool granularity, input/output contracts, which tools Claude actually needs) requires real design work — it should not be decided on the fly during execution.

**Executor calibration:** a large-context coding agent fanning work out to subagents. S3 and S4 fan out model + test work in parallel subagents; S2 MCP scaffolding is mostly serial. Estimates are conservative.

## Assumptions and Open Questions

- **Package slug** (`hde` vs `housing_decision_engine`): resolved in S1 pre-flight.
- **Opportunity cost of down payment in rent comparison:** deferred to S3 design — rent model may or may not include the investment return on the forgone down payment. This is load-bearing for the PV comparison and needs the brainstorm.
- **Income → comparison integration:** does employment cash flow affect the *cost comparison* or is it an *affordability overlay*? Resolved in S3 design.
- **Correlated shock model design:** how correlated are real estate price drops and income drops? What distribution? Resolved in S4 design.
- **Repo dir rename timing:** `condo-vs-house-cost-sim/` → `housing-decision-engine/` may require a projects-level `mv` + git history note. If the GitHub remote needs updating too, surface that in S1.
- **Scope: personal tooling** — adversarial review not required.

## Notes

- The **Status section** (above `---`) is mutable — update after each session. The **arc spine** (below) changes only if a session is added/dropped or the goal is genuinely redefined.
- This roadmap lives at `docs/roadmaps/2026-06-07_housing-decision-engine.md` in the repo; it will survive the S1 rename since it's committed before the move.
