# HDE deployment-readiness polish plan (approved 2026-09-01)

## Context

**Why:** system-evaluation mode (operator, 2026-09-01). The product mandate is a housing-decision
engine that (G1) gets to know the user and their housing goals first, (G2) tells them whether a
clear winning option exists, and (G3) can answer any question about the figures, calculations,
rates, hyperparameters and where the data came from. G3 is why every number needs an anchor.

**How this was measured:** a read-only audit against each goal facet (intake, verdict, JSON surface, constants, formulas, prior provenance, a reproduce-by-hand probe, docs drift, tests of claims), every finding re-checked for correctness and materiality, then re-read in the working tree.
**Not measured:** nominal-mode paths, leveraged (mortgage) paths, the library API in `src/hde/__init__.py`, and the example YAML provenance headers' accuracy against their citations were not swept; and nothing checked whether a cited figure is what its source actually says — every anchor was checked for internal consistency only (see Step 0.0).

**Minimum readiness cut:** Step 0 + A + B + F.1–F.3 + E.1 flips the verdict from not-ready to
ready. C, D, E.2–E.6, F.4–F.5, G are polish behind it and can run afterwards or in parallel.

**Readiness verdict (2026-09-01): not deployable on G2 and on the agent path of G3; G1 partial.**

| Goal | State | The gap in one line |
|---|---|---|
| G1 intake | partial | `--print-schema` lies about 3 required keys and 11 notes are placeholders; the skill elicits schema keys, never goals |
| G2 clear winner | **blocked** | tie branch is dead (`margin < $0.50`), MC P(cheapest) never qualifies the headline, text report prints `P(x cheapest): 100%` on zero-uncertainty runs |
| G3 explain (human path) | partial | text report echoes defaults with cites; formulas for 10 of 13 breakdown keys live only in specs/plans, reference docs describe the retired engine |
| G3 explain (agent path) | **blocked** | `--json` carries no assumptions, no verdict, no anchor record; no command exposes an anchor's source/url/band; prior "Source:" line is a hard-coded, uncorroborated string |
| Hygiene | dirty | ~1,060 lines uncommitted (registry + tests untracked), no spec/plan for it, docs say five acts / MCP-first / S4b not started, 61 mypy errors under a strict config nobody gates |

**What is already right (do not regress):** `anchors.py` is a disciplined registry (import-time
citation checks, `replaces` notes, honest "neutral, uncited" and "CALIBRATED" markings); the text
report's `defaults applied … [cite]` echo; `serialization.py` as the declared single serializer;
`single_path_run` and the "not a forecast" stamp on the story path; the time-anchor guard is
pinned at all three layers; both suites green (hde 362, demoflow 1377); story PNGs byte-stable.

## Fix order

Ordered by what unblocks a stated goal. Each numbered task is one commit-sized unit. Tests
first where a behaviour changes (CLAUDE.md reflex). Reuse targets named per task; **no new
modules** except the two docs this plan requires.

### Step 0 — land the baseline (hygiene, blocks everything)

0.0 **Verify the anchors against their sources (live boundary, execution task one).** For each of
    the 11 `ANCHORS` entries: fetch the cited URL, confirm the quoted figure, record `retrieved_on`;
    replace secondary URLs with the primary where one exists (`objectivefinancialpartners.com` → the
    FP Canada 2026 PAG PDF at fpcanada.ca; TREB-via-Better-Dwelling → TRREB series if reachable;
    NAHB-via-Investopedia → NAHB). A figure the source does not state gets its anchor re-marked
    `kind="reference"` or `neutral`, never left as a citation. Nothing commits `as_of="2026"` as
    verified before this runs. Output = the citation table in 0.1.
0.1 Write the design doc the uncommitted work never got: `docs/specs/2026-09-01-provenance-remediation-design.md`
    containing the verified citation table `anchors.py:13` refers to (source, URL, retrieved-on, figure
    quoted, derivation) — mostly a transposition of `ANCHORS` fields — plus this plan's readiness
    findings. Copy this plan to `docs/plans/2026-09-01-readiness-polish.md`.
0.2 Split the working tree into four commits, staging by explicit path (never `git add -A`; leave
    `demoflow/uv.lock` out — sibling churn, CLAUDE.md gotcha):
    (a) anchors registry + three-way pin: `src/hde/anchors.py`, `models.py`, `config.py`, `input_schema.py`,
        `reporting.py`, `tests/test_anchors.py`, `tests/test_config.py`, `tests/test_models_new.py`, `tests/test_reporting.py`;
    (b) time-anchor guard: `market_scenario.py`, `cli.py`, `mcp_server/tools.py`, `tests/test_time_anchor.py`, `tests/test_market_scenario.py`;
    (c) act-6 market line: `story_plots.py`, `story_page.py`, `tests/test_story_*.py`, `docs/story/*` incl. untracked `act6_the_market_line.png`, SKILL.md six-act edits;
    (d) provenance headers + docs: `examples/*`, `docs/reference/*`, `AGENTS.md`, the new spec + plan.
0.3 `pyproject.toml`: bump `0.2.0 → 0.3.0` (four defaults changed → verdicts change), drop `pandas`
    (zero imports), move `fastmcp` to an optional extra `mcp` (CLI-first doctrine) **and add it to the
    `dev` extra** so `tests/test_mcp_smoke.py`, `test_tools.py`, `test_registry.py` still import
    (the alternative, `pytest.importorskip("fastmcp")` in those three files, hides a real failure —
    not taken). The root `uv.lock` changes and IS committed (only demoflow's lock is off-limits).
    Verify with `uv sync --extra dev`, pytest, and a CLI smoke run.

### Workstream A — the last hop to the agent (G3 agent path, G2 JSON)

A.1 `src/hde/serialization.py`: add `anchor_to_dict(a)` (all `Anchor` fields via `dataclasses.asdict`)
    and `assumptions_to_dict(spec)` — zip `spec.defaults_applied` with `ANCHORS.get(_ECHO_ALIASES.get(k,k))`,
    emitting `{key, value, formatted, cite, as_of, source, url, rationale, band, replaces, kind}` where
    `kind ∈ {cited, reference, neutral, mode}` (see C.3). Value read the way `reporting._echo_value` does.
A.2 `src/hde/cli.py:163`: `doc["assumptions"]`, `doc["verdict"]` (from B.1), `doc["engine_version"]`
    (from `importlib.metadata`), and `warnings` = coherence + time-anchor violations (today the CLI drops
    the time-anchor warnings from JSON while MCP includes them — hoist one `all_warnings(spec, prior)` helper
    next to `coherence_warnings` and call it from both edges).
A.3 `--print-anchors` flag modelled on the `--print-schema` pair (`cli.py:75-96`): dumps `{name: anchor_to_dict}`.
A.4 `mcp_server/tools.py`: `run_comparison` adds `assumptions` + `verdict`; `define_scenario` returns the
    structured form instead of `format_assumptions` strings; `sweep_param` attaches `anchor` and per-row
    `outside_band` when the swept path resolves to an anchor (7 of 24 paths do).
A.5 Tests: `tests/test_cli.py` `TestJsonContract` — exact top-level key set, `--no-monte-carlo` yields
    `monte_carlo: null`, every anchored `defaults_applied` key appears with non-empty `source`, stale-anchor
    config puts "stale" in `doc["warnings"]` (mirror `test_time_anchor.py:75`). `test_tools.py` parity.
A.6 `.claude/skills/hde/SKILL.md`: dispatch row `"where did that number come from?" → uv run hde --print-anchors`;
    Verification line lists `assumptions` + `verdict` keys; fourth judgment gate "anything in `assumptions`
    is a default, not the user's input — say so and name its source".

### Workstream B — one verdict, four surfaces (G2)

B.1 `src/hde/models.py`: `compute_verdict(det, mc, sim) -> Verdict` dataclass
    `{best, runner_up, margin_pv, margin_frac, monthly_equivalent, prob_best, decisive: bool, reason}`.
    Lives in models.py (reporting imports models; story_plots must not import matplotlib the wrong way).
    Lift the `max(probs)` block from `story_page.py:87-94` and the min/max/diff block from `reporting.py:124-137`.
B.2 Decisiveness rule, both constants registered in `anchors.py` with `source="derivation"`:
    - primary, when MC ran and is not single-path: `decisive ⇔ prob_best ≥ verdict.prob_floor` (candidate 0.65, ≈2:1 odds; band (0.55, 0.80));
    - fallback (no MC / single-path): `decisive ⇔ margin_frac ≥ verdict.tie_band` (candidate 0.05; derivation: sweeping one defaulted input, `selling_cost_rate`, across its own anchor band (0.03–0.08) moves the margin 2.25% of the winner's PV on the basic example and inverts the MC ranking at the band top; 2–3 defaults moving together ≈ 5%; band (0.02, 0.08)).
    **Operator fork — see "Decisions needed".** The Anchor dataclass gains no new fields for this; `source="derivation"` follows the `severity_vol` precedent.
B.3 Failing tests first (`tests/test_story_plots.py` `TestVerdictSentence`): `{condo: 400_000, rent: 401_000}` must read as a tie
    (fails today); 15% margin still "wins by"; 57% P(cheapest) never renders confident "wins by"; boundary tests on both constants.
B.4 Consumers: `story_plots.verdict_sentence(det, years, mc=None)` → "Too close to call: X edges Y by $N (1.4%) — cheapest in 57% of 10,000 simulations";
    `reporting.format_text_report` "Cheapest:" line quotes the runner-up margin (today it quotes cheapest-vs-costliest, 2.1× the decision figure)
    and gates the Monte Carlo block on `single_path_run(spec)` with the existing "not a forecast" stamp (today prints `P(x cheapest): 100.0%`);
    `serialization.verdict_to_dict`; MCP `run_comparison["verdict"]`.
B.5 `config.py:273` like-for-like warning: `owned_down` must count `initial_value` when `all_cash` (today the warning never
    fires for all-cash purchases, the case with the largest unmodeled renter capital). Test with an all-cash condo + rent config.
B.6 Act 6 on-the-line branch: when `|user_rent − be| ≤ one grid step`, say so instead of "buying already wins" (`story_plots.py:415-427`;
    tolerance = the sweep's own resolution, no new constant). Round-trip test: the dollar figure from `find_break_evens` appears in `market_line_sentence`.
B.7 Act 2 no-crossover sentence gets "(before the end-of-horizon equity credit, which decides the verdict)" so act 1 and act 2 stop reading as contradictory.
B.8 SKILL.md gate: "Decisiveness is not the headline — read `verdict.decisive` / `reason`; if not decisive, say too close to call and name what breaks the tie."

### Workstream C — registry gaps (G3, values that shape the verdict)

C.1 `house.annual_maintenance_rate`: today silently 0.0, no anchor, structurally excluded from `_ASSUMPTION_KEYS` (a $112k swing on a
    $600k house over 25y). **Operator fork:** (a) re-anchor to NAHB 2019 AHS routine maintenance ≈ 0.54%/yr with band (0.005, 0.015) and a
    `replaces` note, or (b) keep 0.0 as a registered neutral (the `house.value_growth_rate` pattern). Either way add it to `_ASSUMPTION_KEYS["house"]`
    and to the echo. Recommended: (b) neutral + a coherence warning when omitted, matching how `value_growth_rate` is handled — the engine
    should not invent a maintenance cost the user did not state, but it must say it assumed none.
C.2 Price-shock anchors unreachable by the echo: extend `_ASSUMPTION_KEYS` with `condo.price_shock.severity_mean/_vol` (only when a
    `price_shock` block is present and the sub-key absent); alias both option paths to the single `price_shock.*` anchors via `_ECHO_ALIASES`;
    `reporting._echo_value` split becomes `rsplit(".", 1)`-aware for three-segment keys.
C.3 Rationale-only anchors mis-cite: `economic.inflation_rate=0.0% [FP Canada 2026 PAG]` credits FP Canada with a value it does not publish
    (its figure is 2.1%); same for `condo.fee_escalation_rate`. Add `Anchor.kind: Literal["cited","reference","neutral","derivation"]`
    (default `cited`); `short_cite()` renders `[ref: FP Canada 2026 PAG]` for `reference`, `[neutral, uncited]` stays; test that the two
    0.0 entries echo without a bare `[FP Canada …]` tag. Register `rent.invested_down_payment` as a zero-width-band anchor with
    `short_cite="like-for-like: set explicitly"` so the most verdict-distorting default stops echoing bare.
C.4 Wire the four rationale-only anchors through `ANCHORS[...].value` at `config.py:482,489,530,622` and `models.py` so the ARCHITECTURE.md
    three-way-pin claim becomes true; make `TestThreeWayPin` generative over `ANCHORS` (name → dataclass factory + field, aliases resolved)
    so an unwired new anchor fails; invert `test_registry_covers_the_wired_defaults` to iterate `_ASSUMPTION_KEYS` and assert every key
    resolves to an anchor, with an explicit reviewed exclusion set for structural keys.
C.5 Registry text fixes: `price_shock.severity_vol` rationale states ±1σ ≈ 0.21–0.30 but the lognormal draw gives 0.225–0.275 (p10–p90
    0.219–0.283); rewrite and add a test recomputing the endpoints from the two anchors. Nominal-planning inflation 2.1% is quoted in a
    warning string and a schema note but exists in no anchor field: add `economic.inflation_rate.nominal_planning` (0.021, band (0.021, 0.024))
    and format `config.py:236-240` + `input_schema` from it.
C.6 Derivable constants: `DRIFT_SIGMA_DIVISOR = 2.5632` — fix the comment ("quartiles" → p10–p90 decile span) and register as
    `market_scenario.drift_sigma_divisor` with `source="derivation"`, `market_scenario.py` reads it. Coherence thresholds in `config.py`
    (0.04 nominal-quote tripwire, 0.15 discount cap, 0.20/0.25 validation bounds whose messages say "inclusive" for a strict `<`): drive the
    soft tier from `ANCHORS[key].band`, keep the hard tripwires with a one-line rationale comment each, fix the two messages.
C.7 Two numerics: clamp the composed price-shock hazard `min(annual_hazard × tilt, 1.0)` (`monte_carlo.py:147`, mirrors the event-hazard clamp at
    `:194`; today a tilt > 1 can push it past certainty); document the pay-drop magnitude clamp `[0.01, 1.0]` (`monte_carlo.py:560`) in a comment and in the
    `pay_drop_events` schema note.

### Workstream D — the figure glossary (G3 human path)

D.1 Rewrite `docs/reference/ARCHITECTURE.md` §"Deterministic vs Monte Carlo Logic" into a **Figure glossary** keyed by the exact
    breakdown keys the report prints (`fee_pv`, `events_pv`, `other_pv`, `reserve_pv`, `downpayment_pv`, `mortgage_pv`, `terminal_equity_pv`,
    `maintenance_pv`, `rent_pv`, `invested_dp_benefit_pv`, `total_pv`, "Cheapest … saves", "≈ $/month equivalent", MC `mean/std/p5/p50/p95`,
    `prob_X_cheapest`, affordability ratios, demographic drift composition, price-shock channel, act-6 break-even). One line per figure as the
    code implements it, plus a shared-conventions preamble: end-of-year cash flows, 1-indexed years, `(1+dr)^-t`; **two escalation-start
    conventions coexist** (fee/rent/other escalate before year 1: `base·(1+e)^t`; maintenance does not: `rate·V0·(1+g)^(t-1)`); mortgage is a
    level ANNUAL payment at an effective annual rate; terminal equity = `V_N(1−sc) − B_N` discounted N years; `≈ $/mo` annuitizes the PV gap
    over N×12 months at `dr/12`. Source text: `docs/plans/2026-06-08-net-wealth-foundation.md:17-24`, `pv.py:130`, `_financing_pv` docstring;
    the two escalation conventions are already stated in `DEV_NOTES.md:213-234` (the one finding the refute pass corrected) — move, don't rewrite.
    Delete the stale additive-normal shock prose (CONFIG_SCHEMAS.md:184-192 is already correct — point there).
D.2 Pin it: `tests/test_reporting.py::test_glossary_covers_every_emitted_figure` — parse the glossary's backticked keys and assert they cover
    `CONDO_BREAKDOWN_KEYS ∪ HOUSE_BREAKDOWN_KEYS ∪ RENT_BREAKDOWN_KEYS` and the keys `det_to_dict`/`mc_to_dict` emit (template: `test_schema_covers_every_parser_key`).
D.3 Echo the conventions where the numbers are: one line in `format_assumptions` ("escalation before year 1 for fees/rent; maintenance from year 1;
    mortgage annual-effective") so it travels with every run and lands in `assumptions` JSON.
D.4 `pv.py:186` `pv_to_monthly_savings` docstring describes a sinking fund; the code is an amortizing payment at `rate/12`. Rewrite the docstring;
    **operator fork (minor):** keep `rate/12` and label it, or switch to `(1+r)^(1/12)−1` so the monthly line decomposes the PV the report printed.
    Recommended: switch and say so; the two figures currently disagree by ~1%.
D.5 Mortgage convention disclosure: `_NOTES` for `condo.mortgage_rate`/`house.mortgage_rate` state "effective annual, annual payments — a Canadian
    posted rate is semi-annually compounded: `r_eff = (1 + r_posted/2)^2 − 1`"; same line in `mortgage_payment`'s docstring and the glossary.
    **Operator fork:** disclose only (recommended now) vs implement monthly payments with Canadian compounding (changes every leveraged verdict by ~1.7%
    on the mortgage leg, one-directional). Add a mortgage variant to `examples/rent_vs_condo_vs_house.yaml` so the leveraged path README advertises is demonstrated.
D.6 Dead code the docs keep describing: delete `_compute_condo_base_pv`, `_compute_house_base_pv` (zero callers), legacy `DeterministicResult` /
    `MonteCarloResult` and their `__init__` exports; delete `API_CONTRACT.md` "Result Classes" + the four-arg signatures (regenerate the file as a
    pointer to `--print-schema`, `--json`, and the glossary). `_annual_costs_for_option`'s unused `econ` parameter: apply `_effective_growth_rate`
    so nominal-mode affordability composes inflation like the PV engine does, with a nominal-mode affordability test.
D.7 `DEV_NOTES.md`: fix `cvh_cost` paths, widen the banner to cover the four superseded design-rationale sections, fold "Annuity Timing" into the glossary preamble.

### Workstream E — prior provenance chain (G3, demographic path)

E.1 Delete `PRIOR_SOURCE_LINE` (`story_plots.py:83`, "UN WPP 2024" — corroborated by nothing in the prior file or demoflow; demoflow reads no UN input).
    Add `LoadedScenarioPrior.describe()` on `market_scenario.py` rendering only what the file carries: geography, `isq_edition`, `census_year`,
    `constants_as_of`, "simulation year 1 = calendar {START_CALENDAR_YEAR} (bands {HORIZON_YEARS})", source count + sha256 prefix, `mapping_version` gloss.
    `story_page._vintage_clause` and the act-5 plot render from it. Test with a fixture whose vintage values cannot come from any literal (`"A2026"` pattern
    already in `test_market_scenario.py:79`).
E.2 `anchors.py`: `SOURCE_KEY_CITATIONS` keyed on the emitter's declared source-key names (`census_tenure_age_98100231.csv` → "StatCan 98-10-0231-01,
    2021 Census tenure × age, URL"; the ISQ workbooks; the StatCan JSON extracts; `mortality_basis:CPM2014…`) copied verbatim from demoflow's
    `pipeline.py` `RUN_SOURCES` `why` strings; unknown key renders `"uncited source: <key>"`, never invented. `MAPPING_VERSION_NOTES = {"1": …}` quoting
    the S4b sketch (linear-through-origin β, uniform β as pinned, piecewise-constant bands). Test: every key in the committed golden resolves.
E.3 `provenance_block()` (`market_scenario.py:190`) gains `isq_edition`, `census_year`, `constants_as_of`, `mapping_version`, source key list;
    amend S4b sketch §2's field list in the same commit. `format_assumptions` gains a `demographic prior:` line so `report.txt` (the default and the
    MCP `report`) stops being silent about the prior; thread the already-loaded prior from `cli.py:131` / `tools.py:105` rather than reloading.
E.4 Persist fired `time_anchor_violations` into STORY.md's prior line and `assumptions`, not just stderr.
E.5 **Cross-contract path, surfaced not taken:** the emitter could embed `_Source.why` + URLs into `data_vintage.source_hashes[*]` (demoflow
    `output/scenario_prior.py`, spec §7(a)). That is a demoflow contract change and stays out of this plan unless the operator rules it in;
    E.2 keys off a closed vocabulary so it stays correct meanwhile.
E.6 Align the three spellings of the chain (`examples/README.md:72`, `demoflow/README.md:4`, the deleted literal) to the one `describe()` sentence.

### Workstream F — intake truth (G1)

F.1 `input_schema._NOTES` corrections (parser is the truth, the note is the lie): `condo.monthly_fee` → required; `income.annual_income` →
    required-if-section; capital structure: add a third tuple element `required_if` emitted beside `required`/`note`, quoting the validator's own
    sentence ("declare all_cash: true OR a mortgage block …") on all four keys; per-section `__section__` entry stating optionality and the
    "at least one of condo/house/rent" rule; `top_level` enumerates the seven section names `_TOP_LEVEL_KEYS` accepts.
F.2 Write the 11 missing notes (condo reserve trio; the four `*_vol`; the four `corr_inflation_*`) echoing the existing "all default 0 = single-path
    run, NOT a forecast" wording; change the fallback `"see docs/examples"` (path does not exist) to `"see examples/README.md"`.
F.3 Tests: replace the tautological `test_schema_covers_every_parser_key` (compares `_SECTION_KEYS` to itself) with `set(_NOTES[section]) >= set(keys)`;
    add a required-flag round-trip (drop one key at a time from a known-good minimal dict, assert `ConfigValidationError` iff `required`); assert no note
    contains a placeholder; move these to `tests/test_input_schema.py`. Add `tests/test_skill_contract.py`: every `uv run hde --flag` in SKILL.md is a real
    argparse option and the required-key list the skill implies matches `input_schema()`.
F.4 SKILL.md: new "Elicit first" section above the judgment gates — five questions in the user's language, each mapped to what it decides
    (how long / how sure → `years` + the <5y selling-cost warning; might you move or need the money → run a second shorter-horizon config; what does
    "best" mean: lowest expected cost / smallest worst case / most wealth at the end → which `verdict` field is the answer; income and stability →
    `income` block + pay-drop events; what uncertainties matter → which `simulation` vols to turn on). Routine becomes "config → run → **assumptions
    read-back** → warnings → story". Fix the act-gating claim (acts 1–4 always; 5 iff `market_scenario`; 6 iff rent + owned). Replace "ask for the
    REQUIRED fields only" with "REQUIRED fields, then which uncertainties matter — every vol at 0 means P(x)=100% is 'nothing modelled', not certainty".
    No new intake module; the skill and the schema notes are the whole G1 surface.
F.5 `examples/README.md`: "Start here" section inlining an 8-line minimal rent-vs-condo config; count is five files (name `advanced_config.yaml` as the
    nominal-mode reference); six acts with the gating rule; fix the two wrong key names in the Parameter-sources table (`rent_escalation` → `rent.rent_escalation_rate`,
    `selling_cost` → `selling_cost_rate`).

### Workstream G — docs and repo hygiene

G.1 `AGENTS.md`: line 9 → CLI-first sentence pointing at CLAUDE.md's surface doctrine; Entry points list `--print-schema`, `--json`, `--story`, demote
    the MCP block to "non-shell consumers only"; package layout adds `anchors`, `serialization`, `input_schema`, `market_scenario`, `story_plots`,
    `story_page` and `docs/{plans,research,story}`; Sessions: S4b ✅ 2026-08-26 (sketch path) + the provenance remediation row;
    line 98 reworded to "every bias-critical engine default" with the covered set named (the "every default" claim is not enforced and C.4's test is what makes it true).
G.2 Roadmap Status block (mutable half only): overall, Last Updated, row 4b completed with its stat-able path, hand-off payload, delete the stale
    "Start Session 1" action.
G.3 `README.md`: six acts (four sites), skill path is repo-local `.claude/skills/hde/` (not `~/.claude/skills/hde/`, which does not exist), "five
    scenarios". `CONFIG_SCHEMAS.md`: scope the banner to exempt the Defaults Summary, add the missing `condo.value_growth_rate` /
    `rent.invested_down_payment` / two vol rows, reconcile the three discount-rate bands (0.15 code, ≥0 doc, [0.02, 0.06] examples) to one cited band,
    generate the Source column from `anchors.short_cite` in a tiny script rather than by hand. `ARCHITECTURE.md`: tree root `src/hde/`, complete module list.
G.4 Fix the two real annotation defects only: `render_story_package`'s return type → `TypedDict` with `act_images` (also fixes `cli.py:245`).
    The remaining ~59 mypy errors are **deferred, not a readiness gap** — see "Deferred" below.
G.5 Byte-stability regression test: render the story package twice into two `tmp_path` dirs with the same `command=` string and assert byte equality
    per file (never compare against committed PNGs in a unit test — matplotlib stamps its version). Pin act-2/act-3 sentences via `_act_sentences`.
G.6 Regenerate `docs/story/` after A–E land (STORY.md footer and act-5 caption change); confirm `git status` clean on a second render.

## Decisions (operator, 2026-09-01)

1. **Decisiveness rule (B.2): RULED** — MC probability floor 0.65 + fallback tie band 5% of the winner's PV, both registered in `anchors.py`
   with `source="derivation"`, bands (0.55, 0.80) and (0.02, 0.08).
2. **Scope: RULED — full plan**, workstreams A–G in the stated order; the minimum cut is the first milestone, not the stopping point.
3. **`house.annual_maintenance_rate` (C.1):** registered neutral 0.0 + warning when omitted (default taken; reversible, changes no example output).
4. **Mortgage convention (D.5):** disclose the annual-effective convention (default taken; implementing Canadian semi-annual compounding stays a listed alternative).
5. **Prior citations (E.5):** hde-side `SOURCE_KEY_CITATIONS` (default taken; the demoflow emitter change stays surfaced, not made).

## Verification (end-to-end, after each workstream and at close)

```bash
uv sync --extra dev
uv run --extra dev python -m pytest -q                 # hde suite green, count > 362
bash scripts/test-all.sh                               # both suites + (after G.4) mypy
uv run hde --print-schema | grep -c 'docs/examples'    # must be 0
uv run hde --print-anchors | python -c 'import json,sys; d=json.load(sys.stdin); assert all(v["source"] for v in d.values())'
uv run hde examples/rent_vs_condo_vs_house.yaml --json | python -c 'import json,sys; d=json.load(sys.stdin); assert {"warnings","deterministic","monte_carlo","assumptions","verdict","engine_version"} <= set(d)'
uv run hde examples/showcase_demographic_prior.yaml --story docs/story && git status --short docs/story   # clean on 2nd run
```

Readiness probe re-run (the acceptance test for G3): reproduce `rent_pv`, `terminal_equity_pv`, `invested_dp_benefit_pv`, `≈ $/mo` using ONLY
`--json` + `docs/reference/` — every figure must reproduce without opening `src/`. G2 acceptance: `examples/basic_config.yaml` with
`house.initial_value: 460000` renders "too close to call" (1.4% margin, P=57%), the showcase still renders "Renting wins". G1 acceptance: a config
built from exactly the `required`/`required_if` keys runs.

## Deferred (real, not readiness)

- **mypy:** 61 errors under a strict `[tool.mypy]` config that nothing gates. Two options, operator's call later: fix all and add a mypy
  stanza to `scripts/test-all.sh`, or strip the `mypy src` commands from ARCHITECTURE.md / DEV_NOTES.md and note in AGENTS.md that typing is
  aspirational. A documented gate that fails is worse than none; either option ends that state.

## Not in scope (stated so it is not inferred)

Geographic tax rules; mortgage optimization; a separate intake module; changing demoflow's emitter contract (E.5 unless ruled in); CI provisioning
(no `.github/` exists — a one-job workflow running `scripts/test-all.sh` is a reasonable follow-up but is not a readiness gap for a local CLI).
