# Housing Decision Engine — Roadmap

## Status

**Overall:** S1–S4b complete; the 2026-09-01 readiness polish (anchors registry with verified citations, one decisiveness rule across every surface, `--json` provenance, a truthful `--print-schema`, the figure glossary, the clone-and-ask user flow; MCP server removed) is on branch `feat/readiness-polish`, followed by four rounds of user-model dogfood (persona runs on the models users will have — Sonnet/Opus — each critiqued) whose fixes landed 2026-09-02: a mortgage means nominal mode (defaults compose with inflation; a real-mode mortgage with an income warns), the verdict carries the Monte Carlo mean and the story headline says when it disagrees, a demographic prior runs in nominal mode, the report prints year-1 cash beside the PV view, sweeps track Monte Carlo mean flips and name their decisiveness rule. Round-four critic scores 18 / 18 / 20 out of 25 with every verdict correct for the facts. Next: PR + merge; then the deferred items in `docs/plans/2026-09-01-readiness-polish.md` (mypy ruling, the demoflow emitter citation path E.5).
**Created:** 2026-06-07
**Last Updated:** 2026-09-02
**Slug:** `housing-decision-engine`

### Session Status

| Session | Type | Status | Artifact path(s) (resume contract) | Notes |
| --- | --- | --- | --- | --- |
| 1 | decisive | `completed` | the repo root | Rename + uv + AGENTS.md/CLAUDE.md + docs structure |
| 2 | brainstorm-to-execute | `completed` | `mcp_server/` — PR #2 commit `79b3a56` | 6 MCP tools, 115 tests, FastMCP stdio |
| 3 | brainstorm-to-execute | `completed` | `docs/plans/archive/2026-06/2026-06-08-rent-income-model.md` — PR #3 commit `6121f1a` | ComparisonSpec refactor, RentParams + PV, IncomeParams + AffordabilityReport, 151 tests |
| 4a | brainstorm-to-execute | `completed` | `docs/specs/2026-06-08-net-wealth-foundation-design.md` — PR #4, branch tip `b99a6b3`, 176 tests pass (2026-07-21) | Net-wealth foundation: rent-vs-buy DCF (mortgage amortization + terminal equity, house+condo). Split out of original S4. |
| 4b | brainstorm-to-execute | `completed` | `docs/specs/2026-08-26-s4b-demographic-input-slot-sketch.md` (2026-08-26) | Market scenario layer: demographic drift priors (demoflow ScenarioPrior) + tilted price-shock channel; correlated market+income shocks and the pre-canned stress configs were NOT built — the prior replaced the hand-authored scenario menu. |
| readiness | plan-to-execute | `completed` | `docs/plans/2026-09-01-readiness-polish.md` (branch `feat/readiness-polish`) | Provenance + verdict + intake + glossary + hygiene; suite 440+ tests. |

Status values: `not_started`, `in_progress`, `blocked`, `completed`.
A `completed` row MUST carry a real, stat-able artifact path — repo-relative here, because this repo is public and an absolute path discloses the machine's layout.

### Hand-off Payload

- **Next session:** PR + merge of `feat/readiness-polish`; then the deferred ruling on mypy (fix + gate, or drop the config) and whether demoflow's emitter should embed source citations (plan E.5, cross-contract).
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
- **2026-09-02 (dogfood rounds 1–4, steering session):** the skill routes every financed purchase to `mode: nominal` (the lender collects the nominal payment; a real-rate level payment hid GDS breaches of 33% and 36% against 32% in two persona runs) — reversible, verdict drift measured at $83.2k → $81.9k and 3.1% → 2.9%, and it interacts with the open nominal-semantics ruling below; the S4b nominal-mode refusal of a prior was lifted (the drift is real and composes)..
- **2026-09-01 (MCP removed):** operator ruling — the MCP server (S2) is superseded; the only surface is the CLI plus the repo-local skill, and the user flow is clone → launch Claude Code in the repo → ask, with the skill eliciting whatever the question lacks.

### Next Recommended Action

Open the PR for `feat/readiness-polish` (run `bash scripts/test-all.sh` first; regenerate `docs/story/` and confirm `git status` clean on a second render).


### Backlog from the 2026-09-03 fresh-shape dogfood (five question shapes; engine gaps the reviews hit)

Scores on the shipped skill, one smaller-model serve each, reviewed on the session model against the
engine's own reruns: reverse price threshold 16/25, condo comparison 21, numberless quick-sense 13,
Ottawa buyer 19, Duvernay re-serve 21. The lower scores share engine causes; the first six landed the
same day, the rest are open.

- **Landed 2026-09-03:** `cash_available` (the engine nets purchase costs into the down payment and
  prints the loan-to-value, re-derived per grid point); property-tax anchors on ASSESSED value for
  Laval, Montréal, Québec City, Toronto and the Québec school tax, explicit no-source entries for
  Gatineau (neighbourhood-unit rates) and Ottawa (rate by-law not fetchable), StatCan household
  insurance floors for QC/ON, cited by the read-back on an exact match; act 6 calls the break-even
  solver and carries the band-first sentence; a `sources:` block with `user-stated:` /
  `assistant-typed:` read-back lines and a warning when Monte Carlo decisiveness rests on inputs the
  user did not state; price-scan coherence (`property_tax_rate`, `purchase_costs_rate`, a note when
  dollar inputs are held fixed along a price scan, affordability at the break-even crossing and band
  edges, integer-sweep dedupe, default brackets for rate keys, one-decimal probabilities at the
  floor); the mortgage-insurance premium computed in-engine from an anchored schedule with the
  provincial premium tax (see the commit for which parts of the schedule were fetched).
- **Mortgage renewal risk:** designed in `docs/specs/2026-09-03-mortgage-renewal-risk.md`; smallest
  slice is the deterministic re-amortization at each term end. Open question: what a renewal shock
  means in real mode.
- **Townhouse shape:** a fee plus a maintenance rate on one option (today condo = fee, house =
  maintenance); every Ontario townhouse question guesses which block to use.
- **Deferred purchase:** "I might buy in a couple of years" has no input; the renter keeps investing
  and the buyer's horizon starts later.
- **GDS-threshold solve:** the price or rent at which the affordability ratio crosses 32% / 39%,
  as `--break-even` solves the cost crossing; the console sweep should show the affordability column
  the JSON already carries.
- **Price-level anchors:** a user with no listing gets an invented price band; a median-price anchor
  per shipped geography (StatCan / CREA / APCIQ, fetched) would make the seed a cited figure.
- **Ontario anchors:** land-transfer tax schedule and first-time-buyer rebate, Ottawa's rate once
  the by-law is fetchable, the Ontario education rate (e-Laws is a JavaScript shell to a fetch).
- **A Monte Carlo-floor flip line** separate from the deterministic-keyed `decisive` flag, and a
  break-even under the verdict's own criterion (where `prob_best` crosses 65%).
- **Renter capital anchor:** a named all-equity return/vol pair for "it's in an index fund", so the
  assistant's 3% real default is not applied to an equity investor unlabelled.
- **`--json` stderr echo:** the `[warning]` lines print to stderr and inside the JSON `warnings[]`;
  document the split in `--help` (a `2>&1` redirect corrupts the document).

### Backlog from the 2026-09-04 re-serve of the three weakest shapes (round 8)

Same facts, same smaller model, engine with the round-7 folds: quick-sense 17/25 (from 13), condo 20
(from 21), reverse 18 (from 16). Every round-7 engine fold reproduced in the answers (the
engine-priced premium, the growth band against the prior's drift, the netted down payment); the
remaining misses were lines the engine printed and the assistant dropped — hence the read-back block.

- **Landing 2026-09-04:** an engine-assembled READ-BACK block (`assumptions.read_back`, `--read-back`)
  the answer pastes verbatim — every warning, the `assistant-typed:` / `unattributed:` lines, the
  decisiveness rule, the financing and other-costs lines, affordability, break-even sentences and
  notes; one-sided uncertainty warned symmetrically (renter-only dispersion too); the growth
  break-even names where the prior's drift sits against the tie band; `sources:` anchor declarations
  validated on VALUE, not name alone, plus a summed form for municipal + school tax; the reference
  matcher cites a municipal + school-tax sum; a Bank of Canada posted 5-year mortgage-rate anchor;
  land-transfer tax computed in-engine from anchored bracket schedules (QC provincial, Montréal,
  Ontario, Toronto, first-time-buyer rebates) with `land_transfer_tax: auto`.
- **Québec City flat tariffs:** the rate anchor excludes about $581/yr of flat water/waste tariffs
  that a real bill carries; anchor them (Ville de Québec tarification) so the placeholder is not low.
- **Lender-shaped GDS:** the affordability ratio is housing cost over income; a lender's GDS adds
  heating and half the condo fee and uses the qualifying rate — a `lender GDS` line, or a note that the
  insured loan itself may not be approvable above 39%.
- **Coherence note at the crossing:** the "held fixed in dollars" note sizes its figures at the seed;
  print them at the crossing too, where the answer quotes them.
- **Placeholder seed attribution:** a break-even's seed price the assistant invented should be
  declared `assistant` in `sources:`; the skill now says so, the engine could default it.
- **Deferred purchase, price-level anchors:** still open from round 7.

### Round 9 (2026-09-04, same three shapes on the read-back tip) — open items

Decided 2026-09-04 (mechanism, next fold — no ruling needed):

- **One fact once in the READ-BACK block.** The gist-shape block ran 479 words after a 120-word
  answer; the affordability warning, the Affordability section and the two max-ratio lines state one
  fact, and the tier-change note runs 74 words. The block keeps every warning and source line (the
  honesty contract) and drops nothing on a brevity request; it stops repeating itself and the cliff
  note compresses to a sentence. Measure: block words per shape, before and after.
- **Anchor validity dates.** `Anchor` gains an optional `valid_until`; `--print-anchors` prints it and
  a run past that date warns (the Québec insurance-premium tax steps to 9.975% for premiums after
  2026-12-31; the Toronto rebate page was read 2026-09-03 with no 2026 amendment shown). Unanchored
  figures stay `source: none` — that line is the contract working, not a gap to fill by hand.
- **The short-answer prose cap is an engineering number**, tuned by measurement each round, not a
  figure to ratify.
- **`PROMPTS.md`** now sits beside the README (what to ask, what to front-load, what comes back, what
  is not modelled); the next round's opening prompts are shaped by it so the round measures the doc.

Scores: quick-sense 17 (17), reverse 20 (18), condo 21 (20); the pasted READ-BACK block was
byte-identical to the engine's in all three and every base-run warning reached the user. Ontario has
not been re-served since round 7 (19).

- **Inflation anchor citation:** `anchor:economic.inflation_rate` is refused on a nominal config because
  that anchor's value is 0.0 (real-mode inert); the nominal twin `economic.inflation_rate.nominal_planning`
  (0.021) is the one to declare — the skill now names it; the schema note should too.
- **Borough lines for Montréal:** the anchor holds the city-wide lines only; Le Sud-Ouest (Griffintown)
  and the other 18 boroughs' service/investment and former-city debt lines are in the same fetched
  table — register them as `property_tax.montreal.<borough>` sums so a Griffintown bill is not a guess.
- **Console sweep affordability column:** still text-invisible (JSON rows carry it).
- **Run at the crossing:** `--break-even` reports the crossing but nothing prints the full run
  (cash line, financing, affordability) AT that price without editing the config; an `--at KEY=VALUE`
  override, or the break-even carrying the crossing's financing line, would remove the hand edit.
- **Seed price under a fixed cash pile:** the financing line now prints the price at which a stated
  `cash_available` stops covering 20% down (transfer tax and costs netted); what remains open is
  starting `--break-even <option>.initial_value` from that fixed point automatically instead of the
  assistant reading it off a first run.

### Backlog from the 2026-09-02 user-model dogfood (engine gaps the personas hit; operator rulings needed where marked)

- **Nominal-mode semantics (RULING):** today `mode: nominal` keeps growth/escalation inputs REAL and composes `inflation_rate` on top, while discount and mortgage rates are used as entered; every nominal-thinking user typed sticker rates and was inflated twice. Options: make nominal literal (all rates as quoted; `inflation_vol` becomes the surprise around expectation) — changes `advanced_config` outputs and the MC inflation machinery — or keep and echo effective rates. The skill states the current contract (gate 3) meanwhile.
- Mortgage term vs amortization: one rate for the whole amortization; no renewal-rate scenario for a 5-year fixed — the largest buy-side risk in Canada is invisible.
- Financed mortgage-insurance premium (CMHC/Sagen by LTV band, provincial tax on the premium); today `purchase_costs` approximates it as cash at purchase.
- `value_growth_vol`: ordinary price uncertainty for the Monte Carlo (today only the jump `price_shock` channel exists).
- An objective flag (`expected` / `p95` / end-wealth) so "smallest worst case" ranks on the figure the user cares about.
- Probabilistic or early exit ("might move for work"); a TAL continuing-tenant rent-control anchor; anchored defaults for property tax and purchase costs by jurisdiction (Québec welcome-tax brackets, notary) so a user's "no idea" becomes an engine-computed illustrative figure.
- Interest/principal split of `mortgage_pv` and a `selling_cost_pv` line in the breakdown, so the owner's unrecoverable cost is a read-back over the horizon (today only year 1 is printed: `cash_year1` / `principal_year1` / `appreciation_year1`).
- `--sweep` in the user's units: accept sticker (nominal) points in nominal mode and deflate in-engine; today the bracket is authored in real decimals by hand.
- Mortgage-insurance premium schedule (CMHC/Sagen by LTV band + provincial tax): `financed_purchase_costs` now carries a hand-computed premium on the loan; the schedule itself is not anchored (the CMHC fetch was blocked from the build sandbox).
- The 200-word quick-sense cap versus the mandatory disclosures: the skill now ranks content and never drops a warning; whether the cap should rise is a product call.
- **Decisiveness keys to the deterministic best (RULING):** with the prior on, P(house)=66.4% at rent $1,900 reads "not decisive" (rent is the deterministic best at 33.6%) and 66.6% at $1,950 reads "decisive" — the reason line now says when the other side clears the floor; whether `decisive`/`best` should key to the max-probability option instead is the operator's call (rule ruled 2026-09-01).
- `--break-even` under the verdict's own criterion: alongside the deterministic tie band, the interval where `decisive` is false and the Monte Carlo-mean crossing on the same bracket (today a hand-densified `--sweep`; Monte Carlo per bisection point is the cost).
- Laval vs metro prior: `LAVAL_RA13` reads materially differently from `MTL_RMR` on the same house (buying lean 55.8% vs 66.4%; Laval's reference drift turns negative from 2040) — the geography list is now on `--print-schema` and pinned to the fixture, and the prior's provenance line prints the real drift it encodes per band.
- A `cash_available` input for the owned option: the engine nets `purchase_costs` (and a computed insurance premium) out of a stated cash pile into `down_payment`, prints the loan-to-value and the distance to the 20% line under `assumptions` — today that arithmetic is the agent's, unchecked (every threshold persona landed at 20.04% down by hand).
- `--print-schema` / `--print-anchors` filtering by section or key (both are multi-KB blobs loaded for a two-field check).
- Anchors for property tax and home insurance by jurisdiction: both are placeholders in every persona run (about 15% of a Laval house's year-1 cash); the `--print-anchors` registry has 18 entries and neither.
- Act 6 solves the crossing it draws: today the market line sweeps ±35% around the quoted rent and reports "renting is cheaper across the whole swept range" when the crossing lies outside it; `--break-even` already solves it — act 6 should call the same solver.
- Typed values flagged on the assumptions line: a value the assistant types on the user's behalf (a 0% rent escalation, a 25-year amortization) leaves `defaults applied` and silences its warning; an `assistant-typed:` marker (or an `inputs-not-in-the-question` echo from the skill's intake) would let the read-back surface it.

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
