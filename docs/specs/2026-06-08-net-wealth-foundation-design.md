# S4a — Net-Wealth Foundation (Rent-vs-Buy DCF) — Design Spec

**Date:** 2026-06-08
**Session:** S4a (foundation half of the split S4; see Roadmap deviation below)
**Scope:** personal tooling — nothing here places trades or moves money.
**Status:** DRAFT — awaiting operator review before plan.

---

## 1. Goal

Replace the engine's carrying-cost-only comparison with a **canonical net-wealth
rent-vs-buy DCF**: owned options (house, condo) are modeled as financed (or
all-cash) purchases with mortgage amortization, appreciation, and terminal home
equity. This makes the rent / condo / house comparison reflect the buyer's
actual leveraged wealth position — the prerequisite for S4b's market-shock and
crash scenarios to mean anything.

This is the **foundation** half of S4. The **scenario layer** (price-drop events,
discount-rate sensitivity, correlated market+income shocks, crisis/forced-sell,
`sensitivity_sweep` + `stress_test` tools, pre-canned configs) is S4b and gets
its own spec.

## 2. Context — why this is here, and the decisions behind it

S4's headline feature ("what if the market drops 20% in year 5?") was premised
on home value driving the rent-vs-buy decision. Code inspection (deterministic.py
`_compute_house_option`, monte_carlo.py `_simulate_house_pv_once`) confirmed it
does **not** today:

- House PV = `maintenance_pv + events_pv + other_pv`. `house_value` compounds but
  is *only* the basis for maintenance — never harvested as terminal equity.
- No purchase outflow, no mortgage, no interest rate (only the PV `discount_rate`).
- The rent side already credits `invested_dp_benefit_pv` (a negative/benefit),
  so the model is **one-sidedly asymmetric**: renting accounts for the
  down-payment opportunity cost; buying accounts for neither the capital tied up
  nor the equity recovered.

Consequence in the current model: a price drop makes owning look *cheaper* (less
maintenance) — wrong-signed. A "price-drop scenario" built on that surface would
ship a feature that does the opposite of its name.

### Decisions (operator-confirmed, 2026-06-08)

| # | Decision | Choice |
|---|---|---|
| D1 | Comparator character | **Net-wealth**, not carrying-cost. |
| D2 | Equity mechanism | **Full-value − financing carry** — full terminal home value, with mortgage amortization charging interest on the borrowed principal. (Operator: "the long-term correct pick.") |
| D3 | "Interest rate shock" scope | Reinterpreted as **discount-rate sensitivity** (S4b). Mortgage *rate* is now a real model input (this spec); rate *shocks* on it are S4b. |
| D4 | Session scope | **Split** S4 → S4a (this foundation) + S4b (scenario layer). |
| D5 | Backward compatibility | **Net-wealth is canonical** — no legacy carrying-cost mode. Existing house/condo PVs change; affected test expectations are rewritten against an independent oracle (§7). |
| D6 | Owned-option input contract | **Require explicit capital structure** — every owned option must declare either a mortgage (`down_payment` + `mortgage_rate` + `mortgage_term_years`) or `all_cash: true`. No silent default. A correct model makes you state your leverage. |

### Roadmap deviation (recorded)

The roadmap (`docs/roadmaps/2026-06-07_housing-decision-engine.md`) lists
"mortgage optimization / leverage modeling" as **out of scope**. D2 deliberately
re-opens leverage/amortization. Operator's in-conversation instruction overrides
the roadmap boundary (Authority Hierarchy #1). The roadmap's Decisions/Deviations
table and session list are updated to reflect the S4a/S4b split and the
leverage re-scope.

### 2.1 Audit verdicts (elegance-gate, 2026-06-08)

Architectural + strategic facets both returned **PROCEED-WITH-MODIFICATIONS**;
no redesign, model decisions D1–D6 locked, and **S4a is NOT split again** (the
strategic facet's headline call). Mods folded into this spec:

- **Closed-form mortgage math, reuse `pv_annuity`** (arch MOD-1, verified):
  `mortgage_pv = pv_annuity(M, dr, min(N,T))` — the payment stream IS an ordinary
  annuity, so no hand-rolled O(N) schedule. Remaining balance `B_N` via closed
  form, no loop. See §3/§6.
- **Shared `_financing_pv` helper** (arch MOD-2): down-payment + mortgage +
  terminal-equity logic is identical across house, condo, and the MC path —
  extract once, don't triplicate. See §6.
- **Compositional test assertions** (strategic Mod 2): rewritten `total_pv`
  expectations assert `total == sum(breakdown keys)` with each NEW key
  independently oracle-anchored — never hand-bless an integrated magic number.
  This closes the rubber-stamp gap the original §7 left open. See §7.
- **Oracle-first task ordering** (strategic Mod 1): the amortization + terminal-
  equity oracle tests are written FIRST (plan Task 1), before any engine code, so
  the oracle stays independent. Enforced in the plan (writing-plans), noted in §7.
- **`all_cash=True` stub convention** (strategic Mod 3): the 74 fixture sites
  (verified: 32 HouseParams + 42 CondoParams) get a mechanical pass — ~60 get
  `all_cash=True` (financing-agnostic), ~14 get real mortgage blocks. Explicit
  plan task. See §7.
- **Dual-layer capital-structure enforcement** (strategic Mod 5): config loader
  raises `ConfigValidationError`; the engine also raises `ValueError` if
  `all_cash=False and down_payment is None` so direct-construction callers can't
  get silent garbage. See §5/§6.
- **AGENTS.md deliverable** (arch MOD-3): strike the "do not add mortgage/leverage
  modeling" line — it is now a false constraint for the executor of this very
  plan. See §8/§10.
- **RNG-order claim verified** (strategic Mod 4): condo already consumes draws via
  `_draw_inflation_factor`/`_correlated_z`; appreciation reuses the per-year
  `inflation_factor`, adding no new draw → order preserved. `test_reproducibility_with_seed`
  is the regression canary.

**The real cost the operator must see (strategic):** D5 (canonical) + D6 (required
capital structure) together eliminate every intermediate green-test checkpoint
inside the core rewrite — all 74 fixtures + deterministic + MC + house + condo
break atomically until the rewrite completes (a ~3–4h dark window). This is the
unavoidable consequence of the canonical choice, not a fixable defect. Mitigation
is strict task ordering (oracle-first + stub-pass + compositional assertions), and
a **pre-authorized fracture line** (§8) as a safety valve if the session runs long.

## 3. The model (precise)

Notation: `N` = `sim.years`; `dr` = `sim.discount_rate`. For an owned option `o`
with price `P₀ = o.initial_value` and effective appreciation rate `g`
(from `o.value_growth_rate`, adjusted by `econ` exactly as today via
`_effective_growth_rate`):

**Capital structure (required per owned option):**
- `all_cash: true` → `D = P₀`, `L₀ = 0`, no mortgage payments.
- mortgage → `D = o.down_payment`, `L₀ = P₀ − D`, `i = o.mortgage_rate` (annual),
  `T = o.mortgage_term_years`.

**Annual amortization (level payment):**
```
M = L₀ · i / (1 − (1+i)^(−T))      for i > 0
M = L₀ / T                          for i = 0
balance₀ = L₀
for t in 1..N:
    if t <= T:
        interest_t  = balance_{t−1} · i
        principal_t = M − interest_t
        balance_t   = balance_{t−1} − principal_t
        M_t = M
    else:                       # loan paid off
        M_t = 0 ; balance_t = 0
B_N = balance_N
```
(Annual amortization is chosen for consistency with the engine's annual cash-flow
structure — every existing term uses `pv_single(amount, dr, year)`. Monthly
amortization is noted as a future refinement, not S4a.)

The loop above is the *definition*. The implementation does **not** loop: the
discounted mortgage carry is `pv_annuity(M, dr, min(N, T))` (the payment stream is
an ordinary annuity — reuses `pv.py`), and the year-`N` balance has a closed form:
```
B_N = 0                                          for N ≥ T
B_N = L₀·(1+i)^N − M·[(1+i)^N − 1]/i             for 0 < i, N < T
B_N = L₀ − M·N                                   for i = 0, N < T
```

**Appreciation & terminal equity:**
```
value_t = P₀ · Π_{k=1..t} (1 + g_k)          # same per-year growth as today
P_N     = value_N
E_N     = P_N · (1 − sc) − B_N                # sc = o.selling_cost_rate (default 0.05)
```

**Owning PV:**
```
PV(o) = D
      + Σ_{t=1..N} M_t / (1+dr)^t             # mortgage carry
      + carrying_PV(o)                        # maintenance/fees/events/other — unchanged
      − E_N / (1+dr)^N                        # terminal equity, a negative cost
```

**Rent PV:** unchanged —
`rent_PV + events_PV + other_PV − invested_dp_benefit_PV`.
Documented convention: for a strict apples-to-apples read against a given owned
option, set `rent.invested_down_payment = that option's down_payment` (the
renter deploys the capital they'd otherwise put down). Per-option down payments
are intentional — house and condo cost different amounts, so a single shared DP
would misstate a 3-way comparison.

Principal does not double-count: it is paid via `M_t` and recovered via the
lower `B_N` in `E_N`. Net of those, the buyer is charged interest on the borrowed
principal — exactly the financing carry D2 calls for.

## 4. Data model changes (`src/hde/models.py`)

- **HouseParams** gains: `down_payment: Optional[float]`, `mortgage_rate:
  Optional[float]`, `mortgage_term_years: Optional[int]`, `all_cash: bool = False`,
  `selling_cost_rate: float = 0.05`. (`initial_value`, `value_growth_rate` already
  exist.)
- **CondoParams** gains: `initial_value: float` (now **required** — a condo is an
  owned, appreciating asset), `value_growth_rate: float = 0.0`, plus the same
  capital-structure fields as HouseParams (`down_payment`, `mortgage_rate`,
  `mortgage_term_years`, `all_cash`, `selling_cost_rate`).
- **Breakdown key frozensets** extended (drift-guarded by the existing asserts):
  - `HOUSE_BREAKDOWN_KEYS` += `{"downpayment_pv", "mortgage_pv", "terminal_equity_pv"}`
  - `CONDO_BREAKDOWN_KEYS` += `{"downpayment_pv", "mortgage_pv", "terminal_equity_pv"}`
  - `terminal_equity_pv` is stored **negative** (a benefit). `downpayment_pv = D`
    (positive, undiscounted t=0 outflow). `mortgage_pv = Σ M_t/(1+dr)^t`.
- No new top-level `MarketScenarioParams` field in this spec — that is the S4b
  Optional addition to `ComparisonSpec`. (S4a leaves `ComparisonSpec` shape
  unchanged; financing fields live on the option dataclasses.)

## 5. Config & validation changes (`src/hde/config.py`)

- Parse the new owned-option fields.
- **Capital-structure validation** (new `ConfigValidationError` paths), per owned
  option present:
  - Exactly one of {`all_cash: true`} XOR {mortgage block} must be satisfied. If
    neither → error: "owned option '<name>' must declare all_cash or a mortgage
    (down_payment + mortgage_rate + mortgage_term_years)".
  - Mortgage block validity: `0 ≤ down_payment ≤ initial_value`,
    `mortgage_rate ≥ 0`, `mortgage_term_years > 0`.
  - `0 ≤ selling_cost_rate < 1`.
  - Condo `initial_value` now required and `> 0`.
- Existing example configs (`examples/*.yaml`) updated to declare capital
  structure. This is part of the canonical rewrite, not optional.
- **Dual-layer enforcement** (strategic Mod 5): config-load raises
  `ConfigValidationError` (gate for YAML runs); the engine's `_financing_pv` also
  raises `ValueError` on `all_cash=False and down_payment is None` (gate for
  direct-construction callers — the 74 fixtures bypass the loader). Both layers
  required; config-only would let direct callers compute silent garbage.

## 6. Engine changes

- **`pv.py` / helpers**: two scalar pure functions — `_mortgage_payment(L0, i, T)`
  (level payment; `L0/T` when `i=0`) and `_outstanding_balance(L0, i, T, N, M)`
  (closed form per §3; `0` when `N≥T`). A `_terminal_equity_pv(value_N, sc, B_N,
  dr, N)` 1-liner wraps `pv_single`. No hand-rolled amortization loop.
- **Shared `_financing_pv(...)` helper** (arch MOD-2): given an owned option's
  capital-structure fields + terminal home value `value_N` + `dr` + `N`, returns
  `(downpayment_pv, mortgage_pv, terminal_equity_pv)` where
  `mortgage_pv = pv_annuity(M, dr, min(N,T))`. Called from `_compute_house_option`,
  `_compute_condo_option`, and the MC simulators — the financing logic is written
  once. It also raises `ValueError` if `all_cash=False and down_payment is None`
  (engine-level guard, strategic Mod 5) so direct-construction callers fail loud,
  not silent.
- **`deterministic.py`**: `_compute_house_option` / `_compute_condo_option` call
  `_financing_pv` and add `downpayment_pv` + `mortgage_pv` + `terminal_equity_pv`
  to total + breakdown. Condo gains the appreciation + terminal-equity path it
  currently lacks.
- **`monte_carlo.py`**: `_simulate_house_pv_once` / `_simulate_condo_pv_once` call
  `_financing_pv` with the path's `value_N`. Mortgage carry + down payment are
  **deterministic** (closed-form, path-independent); terminal equity is
  **per-path** via the path's `value_N`. **RNG draw order is preserved** —
  verified: condo already consumes draws (`_draw_inflation_factor`/`_correlated_z`),
  and S4a's appreciation reuses the per-year `inflation_factor` already drawn, so
  **no new `rng.normal()` draws** are introduced. `test_reproducibility_with_seed`
  is the regression canary. Appreciation/rate *volatility* is **S4b**, not S4a.
- **Affordability** (`_annual_costs_for_option`, used by both
  `_compute_affordability_report` and the MC affordability path): owned-option
  annual housing cost now **includes the year's mortgage payment `M_t`** plus
  maintenance/fees/events-in-year/other. The down payment (one-time t=0) and
  terminal equity (an asset, not a cash outflow) are **excluded** from the annual
  affordability ratio. This makes the affordability ratio reflect real annual
  cash-flow burden — the mortgage is the dominant housing cost.
- **`reporting.py`**: surface the new breakdown lines (down payment, mortgage PV,
  terminal equity) in text reports.
- **MCP layer**: the existing 6 tools wrap the engine and reflect the new model
  automatically. `_SWEEP_PATHS` gains the new sweepable params
  (`house.down_payment`, `house.mortgage_rate`, `house.mortgage_term_years`,
  `house.selling_cost_rate`, and the condo equivalents + `condo.initial_value`,
  `condo.value_growth_rate`); the `_SWEEP_PATHS` drift-guard test is updated. The
  new tools `sensitivity_sweep` / `stress_test` are **S4b**.

## 7. Test strategy (the load-bearing risk)

Canonical net-wealth changes existing house/condo `total_pv` values, so affected
expectations are rewritten. The danger (flagged by adversarial review): if both
the implementation and the rewritten expectations are born from the same
reasoning in the same session, the tests rubber-stamp the implementation. To
prevent that, the rewrite is **anchored to an independent oracle**:

1. **One fully hand-worked annual amortization schedule** (e.g. L₀=400k, i=5%,
   T=25, N=10) — interest/principal/balance per year — **verified against an
   external mortgage calculator**, pinned as golden values in a dedicated test.
2. **One hand-computed terminal-equity figure** for a known appreciation path —
   pinned.
3. **Zero-vol MC→deterministic convergence** (`test_zero_volatility_converges_to_deterministic`)
   extended to the new terms — with zero vol, per-path `house_value_N` equals the
   deterministic value, so MC total equals deterministic total. This is the
   canonical correctness gate; any new MC term must pass it.

**Compositional `total_pv` assertions, not magic numbers** (strategic Mod 2): the
~11 affected integrated-total assertions are rewritten as
`total_pv == sum(all breakdown keys)` (a structural invariant), where each NEW key
(`downpayment_pv`, `mortgage_pv`, `terminal_equity_pv`) is independently anchored
to the external oracle and old keys (`maintenance_pv`, `fee_pv`, …) keep their
existing independent tests. The total is then transitively oracle-anchored without
ever hand-blessing a magic number — closing the rubber-stamp gap. Component-level
breakdown tests are **unaffected** (separate keys).

**Oracle-first task ordering** (strategic Mod 1, enforced in the plan): the
amortization + terminal-equity oracle tests are written as **plan Task 1**, before
any engine code — they fail until the engine exists. If engine + tests are written
together, the oracle stops being independent.

**The 74-fixture pass** (strategic Mod 3, verified 32+42): a discrete, explicit
plan task. Every fixture site that doesn't care about financing gets a single
`all_cash=True` field (~60 sites); the financing-specific tests get realistic
mortgage blocks (~14). Stated as its own task with an explicit done-criterion so
the executor doesn't discover the scope mid-rewrite and lose the plan thread.

New tests: amortization schedule (vs oracle); all_cash path (L₀=0, no payments,
terminal = P_N(1−sc)); terminal-equity sign & magnitude; capital-structure
validation errors; affordability-includes-mortgage; condo appreciation +
terminal equity; price drop → owning correctly costlier (sign check, the feature
S4b builds on); MC zero-vol convergence with mortgage; MC RNG-order preserved.

## 8. Scope boundary

**IN (S4a):** mortgage amortization (annual), terminal equity, appreciation for
condo, required capital structure + validation, canonical net-wealth model,
affordability-includes-mortgage, breakdown keys, new sweep paths, oracle-anchored
test rewrite, example-config updates.

**OUT (→ S4b):** price-drop events (year/magnitude/recovery), discount-rate
sensitivity / "rate spike", correlated market+income shocks, crisis/forced-sell
model, `sensitivity_sweep` + `stress_test` MCP tools, pre-canned scenario configs,
and the 4 S3-deferred items (nominal-mode affordability cash-flow consistency,
per-sim affordability housing costs, rent-event z_inf correlation, crisis model).

**OUT (entirely, this initiative):** monthly amortization, refinancing, variable
mortgage rates over time, leverage on the equity *credit* beyond what the
mortgage already implies, geographic tax rules.

**AGENTS.md deliverable** (arch MOD-3): the "Do not — Add mortgage optimization /
leverage modeling" line is struck and replaced with "Mortgage amortization +
terminal equity added in S4a (2026-06-08); leverage *optimization* remains out of
scope." Done early in the plan so the executor isn't reading a false constraint
while implementing exactly that.

**Pre-authorized fracture line (safety valve, not a mandate).** Because D5+D6
remove every intermediate green checkpoint, if mid-session the test-rewrite time
exceeds budget, the declared recovery point is: **house net-wealth complete + all
house/rent tests green; condo left at `initial_value`-required-but-carrying-cost-
only with an explicit interim-asymmetry docstring**, condo net-wealth finished in
an immediate follow-on. This avoids an all-red session end without mandating the
split upfront. The default remains: finish both house and condo in one session
(the S3 empirical anchor — comparable new-surface scope — shipped clean).

## 9. Open items for the operator review gate

- The leverage-free→leveraged shift means owning will frequently dominate renting
  on net-wealth PV when appreciation `g` exceeds the renter's `r_inv` — that is
  *correct* model behavior, not a bug. Confirm this is the intended interpretation
  (it surfaces the real rent-vs-buy tradeoff: home appreciation vs investment
  return on the same capital, net of financing carry).
- Per-option down payment vs documented apples-to-apples rent convention (§3) —
  confirm acceptable for the 3-way.

## 10. Success criteria

- [ ] Owned options model down payment + annual mortgage amortization + terminal
      equity, deterministic and MC, per §3.
- [ ] Capital structure required & validated; missing/invalid → clear config error.
- [ ] Condo modeled symmetrically to house (price, appreciation, terminal equity).
- [ ] Affordability annual cost includes the mortgage payment.
- [ ] Amortization matches the external-calculator oracle; terminal equity matches
      the hand-computed oracle; zero-vol MC converges to deterministic.
- [ ] All tests green (existing rewritten via compositional + oracle-anchored
      assertions, new tests added); no integrated `total_pv` magic numbers.
- [ ] Capital structure enforced at BOTH config and engine layers (fail-loud).
- [ ] AGENTS.md "do not add mortgage/leverage" line struck and replaced.
- [ ] Scope honored; no dependencies on private or unpublished repos.
