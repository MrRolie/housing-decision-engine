# S4a — Net-Wealth Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use mm-spine:subagent-driven-development (recommended) or mm-spine:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the carrying-cost comparison with a canonical net-wealth rent-vs-buy DCF — mortgage amortization + terminal home equity for house and condo, required explicit capital structure, oracle-anchored test rewrite.

**Architecture:** Pure scalar financing math (`mortgage_payment`, `outstanding_balance`) added to `pv.py`; a single shared `_financing_pv(...)` helper in `deterministic.py` composes them with `pv_annuity`/`pv_single` (and a fail-loud guard) and is called from both deterministic option computers and the MC simulators. Net-wealth is canonical (no legacy mode); capital structure (mortgage XOR `all_cash`) is required and enforced at both config and engine layers. Tests are rewritten compositionally (`total == Σ breakdown keys`) with each new breakdown key independently anchored to an external oracle.

**Tech Stack:** Python 3.10+, dataclasses, numpy, pytest, uv.

**Spec:** `docs/specs/2026-06-08-net-wealth-foundation-design.md` (read §2.1 audit record + §3 model). **money-path: no** (per repo CLAUDE.md, no `audit-skipped` marker — this is a non-money-path personal-tooling repo). Elegance-gate verdict already recorded in spec §2.1 (architectural + strategic both PROCEED-WITH-MODIFICATIONS, no second split) — **cite, do not re-invoke**.

---

## Model reference (from spec §3 — implementers read this first)

Notation: `P0` = `initial_value`; `g` = effective appreciation; `dr` = `discount_rate`; `N` = `sim.years`; `sc` = `selling_cost_rate`. For an owned option:

- **all_cash:** `D = P0`, `L0 = 0`, no mortgage payments, `B_N = 0`.
- **mortgage:** `D = down_payment`, `L0 = P0 − D`, `i = mortgage_rate`, `T = mortgage_term_years`.
  - `M = L0·i / (1 − (1+i)^−T)` (`L0/T` when `i=0`) — **equals** `pv_annuity` inverse; the discounted carry is `pv_annuity(M, dr, min(N,T))`.
  - `B_N = 0` if `N≥T`; else `L0·(1+i)^N − M·[(1+i)^N − 1]/i` (`L0 − M·N` when `i=0`).
- **Terminal home value:** `value_N = P0 · (1+g)^N` (N full years of growth, t=0 buy → year-N sale). Computed **separately** from the maintenance-basis `house_value` (which keeps its existing year-1=initial convention — do NOT change maintenance).
- **Terminal equity:** `E_N = value_N·(1−sc) − B_N`. Stored as `terminal_equity_pv = −pv_single(E_N, dr, N)` (negative cost).
- **downpayment_pv** = `D` (undiscounted t=0 outflow). **mortgage_pv** = `pv_annuity(M, dr, min(N,T))`.
- **Owning total** = `maintenance/fee/events/other` (unchanged) `+ downpayment_pv + mortgage_pv + terminal_equity_pv`.

`pv_single(cost, rate, year)` and `pv_annuity(payment, rate, n_years)` — **positional order matters** (S3 bug: it is `(payment, rate, n_years)`, NOT `(payment, n_years, rate)`).

---

## File structure (what changes, and why)

| File | Change |
|---|---|
| `AGENTS.md` | Strike the "do not add mortgage/leverage modeling" line (Task 0). |
| `src/hde/pv.py` | Add pure scalar `mortgage_payment`, `outstanding_balance` (Task 2). |
| `src/hde/models.py` | New capital-structure fields on `HouseParams`/`CondoParams`; condo `initial_value`+`value_growth_rate`; extend `HOUSE_/CONDO_BREAKDOWN_KEYS` (Task 3). |
| `src/hde/deterministic.py` | `_financing_pv` helper + guard (Task 4); wire into `_compute_house_option`/`_compute_condo_option` (Task 6); mortgage in `_annual_costs_for_option` (Task 7). |
| `src/hde/config.py` | Parse new fields; capital-structure validation; condo `initial_value` required (Task 8). |
| `src/hde/monte_carlo.py` | Wire `_financing_pv` + per-path terminal value into house/condo simulators (Task 9). |
| `mcp_server/tools.py` | New `_SWEEP_PATHS` entries (Task 10). |
| `src/hde/reporting.py` | Surface new breakdown lines (Task 11). |
| `tests/*` | Oracle tests (Task 1); `all_cash=True` stub pass + compositional rewrites (Tasks 5,6,9); config tests (Task 8); sweep drift-guard `base` (Task 10). |
| `examples/*.yaml` | Declare capital structure (Task 10). |

---

## Task 0: Strike the false AGENTS.md constraint (do this FIRST)

**Files:**
- Modify: `AGENTS.md` (the "## Do not" section)

- [ ] **Step 1: Replace the line**

In `AGENTS.md`, under `## Do not`, replace:
```
- Add mortgage optimization / leverage modeling (out of scope)
```
with:
```
- Add mortgage *optimization* / refinancing / variable-rate modeling (out of scope). NOTE: mortgage amortization + terminal equity ARE modeled as of S4a (2026-06-08); the rent-vs-buy DCF is leveraged.
```

- [ ] **Step 2: Commit**
```bash
git add AGENTS.md
git commit -m "docs(s4a): strike false 'no mortgage modeling' constraint; amortization is now in scope"
```

---

## Task 1: Oracle tests FIRST (the independent trust root)

Write the external/invariant-anchored oracle tests **before any engine code**. They fail now (functions don't exist) and stay as the trust root the rest of the rewrite is checked against. Invariants are implementation-independent; the pinned scalars must be verified against an external amortization calculator before they are trusted.

**Files:**
- Create: `tests/test_financing_oracle.py`

- [ ] **Step 1: Write the oracle test (it will fail — functions don't exist yet)**

```python
"""Independent oracle for the financing math (Task 1, written before the engine).

The PINNED scalars below must be cross-checked against an EXTERNAL amortization
calculator (e.g. an online mortgage calculator, or numpy_financial.pmt with the
sign convention pmt = -mortgage_payment) to the cent before trusting them. The
INVARIANT assertions are implementation-independent and catch most defects.
"""
import math
import pytest
from hde.pv import mortgage_payment, outstanding_balance, pv_annuity, pv_single


# --- Pinned scalar oracle: L0=400_000, i=5%, T=25 -------------------------------
# Standard formula M = L0*i / (1 - (1+i)^-T). VERIFY EXTERNALLY before trusting.
def test_mortgage_payment_pinned_value():
    M = mortgage_payment(400_000.0, 0.05, 25)
    assert M == pytest.approx(28_380.98, abs=0.01)  # external-calc verified

def test_mortgage_payment_zero_rate():
    assert mortgage_payment(360_000.0, 0.0, 30) == pytest.approx(12_000.0, abs=1e-9)


# --- Implementation-independent invariants --------------------------------------
def test_amortization_invariants():
    """Principal repaid over the full term sums to L0; balance hits 0 at term."""
    L0, i, T = 400_000.0, 0.05, 25
    M = mortgage_payment(L0, i, T)
    balances = [outstanding_balance(L0, i, T, year, M) for year in range(0, T + 1)]
    # outstanding_balance(...,0,...) is L0; at/after term it is 0.
    assert balances[0] == pytest.approx(L0, rel=1e-9)
    assert balances[T] == pytest.approx(0.0, abs=1e-6)
    # Each year's interest = prev_balance*i, principal = M - interest, sums to L0.
    total_principal = 0.0
    for year in range(1, T + 1):
        prev = outstanding_balance(L0, i, T, year - 1, M)
        interest = prev * i
        principal = M - interest
        total_principal += principal
    assert total_principal == pytest.approx(L0, rel=1e-6)
    # Monotonic non-increasing balance.
    assert all(balances[k] >= balances[k + 1] - 1e-6 for k in range(T))

def test_outstanding_balance_after_term_is_zero():
    M = mortgage_payment(400_000.0, 0.05, 25)
    assert outstanding_balance(400_000.0, 0.05, 25, 30, M) == 0.0
    assert outstanding_balance(400_000.0, 0.05, 25, 25, M) == 0.0

def test_mortgage_pv_is_annuity_identity():
    """Discounting the level payment over the paid years IS pv_annuity."""
    L0, i, T, dr, N = 400_000.0, 0.05, 25, 0.04, 30
    M = mortgage_payment(L0, i, T)
    assert pv_annuity(M, dr, min(N, T)) == pytest.approx(pv_annuity(M, dr, 25), rel=1e-12)


# --- Terminal equity pinned oracle: all-cash P0=500_000, g=3%, N=10, sc=5% ------
def test_terminal_equity_pinned_value():
    P0, g, N, sc, dr = 500_000.0, 0.03, 10, 0.05, 0.05
    value_N = P0 * (1 + g) ** N          # 671_958.19
    E_N = value_N * (1 - sc) - 0.0       # all-cash, B_N=0  -> 638_360.28
    terminal_equity_pv = -pv_single(E_N, dr, N)
    assert value_N == pytest.approx(671_958.19, abs=0.01)
    assert E_N == pytest.approx(638_360.28, abs=0.01)
    assert terminal_equity_pv == pytest.approx(-391_897.84, abs=0.05)  # verify externally
```

- [ ] **Step 2: Run, confirm it fails on import**

Run: `uv run python -m pytest tests/test_financing_oracle.py -q`
Expected: FAIL — `ImportError: cannot import name 'mortgage_payment' from 'hde.pv'`.

- [ ] **Step 3: Commit the failing oracle**
```bash
git add tests/test_financing_oracle.py
git commit -m "test(s4a): financing oracle tests (fail first; external-verified pins + invariants)"
```

**Done-criterion:** the pinned values in Steps 1 are cross-checked against an external amortization calculator and corrected to the cent if off, BEFORE Task 2 makes them pass. Do not adjust a pin to match the implementation — adjust it to match the external calculator.

---

## Task 2: Pure financing math in pv.py

**Files:**
- Modify: `src/hde/pv.py` (add two functions)

- [ ] **Step 1: Implement the helpers**

Add to `src/hde/pv.py`:
```python
def mortgage_payment(principal: float, rate: float, term_years: int) -> float:
    """
    Level (constant) annual mortgage payment that amortizes `principal` over
    `term_years` at annual `rate`. M = P*r / (1 - (1+r)^-T); P/T when r == 0.
    """
    if term_years <= 0:
        raise ValueError(f"term_years must be positive, got {term_years}")
    if principal <= 0:
        return 0.0
    if rate == 0:
        return principal / term_years
    return principal * rate / (1 - (1 + rate) ** -term_years)


def outstanding_balance(
    principal: float, rate: float, term_years: int, year: int, payment: float
) -> float:
    """
    Remaining mortgage balance at the END of `year`, closed form (no loop).
    Zero at/after the term. B = L0*(1+r)^y - M*[(1+r)^y - 1]/r; L0 - M*y when r==0.
    """
    if year >= term_years:
        return 0.0
    if year <= 0:
        return principal
    if rate == 0:
        return max(0.0, principal - payment * year)
    return principal * (1 + rate) ** year - payment * ((1 + rate) ** year - 1) / rate
```

- [ ] **Step 2: Run the oracle**

Run: `uv run python -m pytest tests/test_financing_oracle.py -q`
Expected: PASS (all oracle tests green). If a pinned value is off, FIRST re-verify it against the external calculator; only fix the implementation if the calculator agrees with the test.

- [ ] **Step 3: Commit**
```bash
git add src/hde/pv.py
git commit -m "feat(s4a): mortgage_payment + outstanding_balance (closed-form, oracle-verified)"
```

---

## Task 3: New dataclass fields + breakdown keys (no behavior change yet)

Add the capital-structure fields and condo value fields, and extend the breakdown frozensets. The option computers do NOT use them yet, so all existing tests stay green.

**Files:**
- Modify: `src/hde/models.py` (`HouseParams`, `CondoParams`, frozensets)
- Test: `tests/test_models_new.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models_new.py`:
```python
def test_house_params_capital_structure_fields():
    from hde.models import HouseParams
    h = HouseParams(initial_value=400_000)
    assert h.down_payment is None
    assert h.mortgage_rate is None
    assert h.mortgage_term_years is None
    assert h.all_cash is False
    assert h.selling_cost_rate == 0.05

def test_condo_params_value_and_capital_structure_fields():
    from hde.models import CondoParams
    c = CondoParams(monthly_fee=400)
    assert c.initial_value == 0.0
    assert c.value_growth_rate == 0.0
    assert c.down_payment is None
    assert c.all_cash is False
    assert c.selling_cost_rate == 0.05

def test_breakdown_keys_include_financing():
    from hde.models import HOUSE_BREAKDOWN_KEYS, CONDO_BREAKDOWN_KEYS
    for k in ("downpayment_pv", "mortgage_pv", "terminal_equity_pv"):
        assert k in HOUSE_BREAKDOWN_KEYS
        assert k in CONDO_BREAKDOWN_KEYS
```

- [ ] **Step 2: Run to confirm it fails**

Run: `uv run python -m pytest tests/test_models_new.py -k "capital_structure or value_and_capital or breakdown_keys_include" -q`
Expected: FAIL (`TypeError: unexpected keyword` / missing attribute / key not in frozenset).

- [ ] **Step 3: Implement — add fields to `HouseParams`** (append after `maintenance_curve`):
```python
    # --- S4a capital structure (net-wealth model) ---
    down_payment: Optional[float] = None
    mortgage_rate: Optional[float] = None
    mortgage_term_years: Optional[int] = None
    all_cash: bool = False
    selling_cost_rate: float = 0.05
```

- [ ] **Step 4: Implement — add fields to `CondoParams`** (append after `reserve_growth_rate`):
```python
    # --- S4a: condo as an owned, appreciating asset + capital structure ---
    initial_value: float = 0.0
    value_growth_rate: float = 0.0
    down_payment: Optional[float] = None
    mortgage_rate: Optional[float] = None
    mortgage_term_years: Optional[int] = None
    all_cash: bool = False
    selling_cost_rate: float = 0.05
```

- [ ] **Step 5: Extend the breakdown frozensets** (replace lines 288–289):
```python
CONDO_BREAKDOWN_KEYS: FrozenSet[str] = frozenset(
    {"fee_pv", "events_pv", "other_pv", "reserve_pv",
     "downpayment_pv", "mortgage_pv", "terminal_equity_pv"}
)
HOUSE_BREAKDOWN_KEYS: FrozenSet[str] = frozenset(
    {"maintenance_pv", "events_pv", "other_pv",
     "downpayment_pv", "mortgage_pv", "terminal_equity_pv"}
)
```

- [ ] **Step 6: Run the new tests AND the full suite**

Run: `uv run python -m pytest tests/test_models_new.py -q`  → PASS
Run: `uv run python -m pytest -q`
Expected: the `_compute_*_option` asserts (`set(breakdown.keys()) == *_BREAKDOWN_KEYS`) now FAIL because the computers don't yet emit the new keys. **This is expected** — Task 6 closes it. Note the count of failures so Task 6 can confirm it returns to green. (If you prefer a green checkpoint here, temporarily skip Task 6's targeted tests — but do NOT commit a red full suite; commit only after Step 7 below scopes the failures.)

- [ ] **Step 7: Commit (models change only)**
```bash
git add src/hde/models.py tests/test_models_new.py
git commit -m "feat(s4a): capital-structure + condo-value fields; extend breakdown keys"
```

---

## Task 4: `_financing_pv` helper + fail-loud guard

**Files:**
- Modify: `src/hde/deterministic.py` (new helper near the top, after `_effective_growth_rate`)
- Test: `tests/test_deterministic.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_deterministic.py`:
```python
def test_financing_pv_all_cash():
    from hde.deterministic import _financing_pv
    # all_cash: D = initial_value, no mortgage, terminal = value_N*(1-sc)
    dp, mort, term_eq = _financing_pv(
        initial_value=500_000, down_payment=None, mortgage_rate=None,
        mortgage_term_years=None, all_cash=True, selling_cost_rate=0.05,
        value_N=671_958.19, dr=0.05, n_years=10,
    )
    assert dp == 500_000
    assert mort == 0.0
    assert term_eq == pytest.approx(-391_897.84, abs=0.05)

def test_financing_pv_mortgage():
    from hde.deterministic import _financing_pv
    from hde.pv import mortgage_payment, pv_annuity, outstanding_balance, pv_single
    dp, mort, term_eq = _financing_pv(
        initial_value=500_000, down_payment=100_000, mortgage_rate=0.05,
        mortgage_term_years=25, all_cash=False, selling_cost_rate=0.05,
        value_N=671_958.19, dr=0.04, n_years=10,
    )
    M = mortgage_payment(400_000, 0.05, 25)
    assert dp == 100_000
    assert mort == pytest.approx(pv_annuity(M, 0.04, 10), rel=1e-9)
    B_N = outstanding_balance(400_000, 0.05, 25, 10, M)
    assert term_eq == pytest.approx(-pv_single(671_958.19 * 0.95 - B_N, 0.04, 10), rel=1e-9)

def test_financing_pv_guard_raises():
    from hde.deterministic import _financing_pv
    with pytest.raises(ValueError):
        _financing_pv(
            initial_value=500_000, down_payment=None, mortgage_rate=None,
            mortgage_term_years=None, all_cash=False, selling_cost_rate=0.05,
            value_N=600_000, dr=0.04, n_years=10,
        )
```

- [ ] **Step 2: Run to confirm it fails**

Run: `uv run python -m pytest tests/test_deterministic.py -k financing_pv -q`
Expected: FAIL (`ImportError: cannot import name '_financing_pv'`).

- [ ] **Step 3: Implement `_financing_pv`** in `deterministic.py` (add `Optional, Tuple` to the `typing` import; import `mortgage_payment, outstanding_balance` from `.pv`):
```python
def _financing_pv(
    initial_value: float,
    down_payment: Optional[float],
    mortgage_rate: Optional[float],
    mortgage_term_years: Optional[int],
    all_cash: bool,
    selling_cost_rate: float,
    value_N: float,
    dr: float,
    n_years: int,
) -> Tuple[float, float, float]:
    """
    (downpayment_pv, mortgage_pv, terminal_equity_pv) for an owned option.

    Fail-loud (strategic Mod 5): direct-construction callers that declare neither
    all_cash nor a complete mortgage block raise here, not compute silent garbage.
    """
    if not all_cash and (
        down_payment is None or mortgage_rate is None or mortgage_term_years is None
    ):
        raise ValueError(
            "owned option requires all_cash=True OR a full mortgage block "
            "(down_payment + mortgage_rate + mortgage_term_years)"
        )
    if all_cash:
        downpayment_pv = initial_value
        mortgage_pv = 0.0
        balance_N = 0.0
    else:
        downpayment_pv = down_payment
        loan = initial_value - down_payment
        payment = mortgage_payment(loan, mortgage_rate, mortgage_term_years)
        mortgage_pv = pv_annuity(payment, dr, min(n_years, mortgage_term_years))
        balance_N = outstanding_balance(
            loan, mortgage_rate, mortgage_term_years, n_years, payment
        )
    equity_N = value_N * (1 - selling_cost_rate) - balance_N
    terminal_equity_pv = -pv_single(equity_N, dr, n_years)
    return downpayment_pv, mortgage_pv, terminal_equity_pv
```

- [ ] **Step 4: Run to confirm pass**

Run: `uv run python -m pytest tests/test_deterministic.py -k financing_pv -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/hde/deterministic.py tests/test_deterministic.py
git commit -m "feat(s4a): _financing_pv helper with fail-loud capital-structure guard"
```

---

## Task 5: Stub `all_cash=True` onto financing-agnostic fixtures (behavioral no-op)

The engine doesn't use financing yet (Task 6 wires it). Adding `all_cash=True` now is a **no-op** that pre-positions every fixture so the guard never detonates the whole suite when Task 6 lands. After this task the only fixtures WITHOUT capital structure are the ones a financing-specific test will set explicitly.

**Files:**
- Modify: `tests/test_deterministic.py`, `tests/test_monte_carlo.py`, `tests/test_models_new.py` (every `HouseParams(...)` / `CondoParams(...)` site, except those a test will give a real mortgage block in Task 6/9)

- [ ] **Step 1: Mechanical pass — add `all_cash=True`**

For every `HouseParams(...)` and `CondoParams(...)` construction in the three test files, add `all_cash=True`. Pattern:
```python
# before
house = HouseParams(initial_value=400_000, value_growth_rate=0.01, annual_maintenance_rate=0.015)
# after
house = HouseParams(initial_value=400_000, value_growth_rate=0.01, annual_maintenance_rate=0.015, all_cash=True)
```
```python
# before
condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.0)
# after
condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.0, all_cash=True)
```
Leave `initial_value` UNSET on condo fixtures that don't care about equity → it defaults to `0.0` → terminal equity `0` → those condo totals are **unchanged** by Task 6 (minimizes churn). House fixtures keep their real `initial_value` and WILL gain a terminal-equity term in Task 6.

Done-criterion: `grep -rn "HouseParams(\|CondoParams(" tests/ | grep -vc "all_cash"` returns 0 EXCEPT for the handful of sites a financing-specific test deliberately gives a mortgage block (track those explicitly).

- [ ] **Step 2: Run full suite — still green (no-op)**

Run: `uv run python -m pytest -q`
Expected: same pass/fail state as end of Task 4 (the only reds are the `*_BREAKDOWN_KEYS` asserts from Task 3, if you haven't reached Task 6 yet). Adding `all_cash=True` changes nothing behaviorally because no computer reads it yet.

- [ ] **Step 3: Commit**
```bash
git add tests/test_deterministic.py tests/test_monte_carlo.py tests/test_models_new.py
git commit -m "test(s4a): stub all_cash=True on financing-agnostic fixtures (pre-position for guard)"
```

---

## Task 6: Wire `_financing_pv` into the deterministic computers (compositional rewrite)

Now the deterministic options emit the financing terms. House fixtures gain terminal equity → their `total_pv` assertions change → rewrite them compositionally. Condo (initial_value=0) totals are unchanged.

**Files:**
- Modify: `src/hde/deterministic.py` (`_compute_house_option`, `_compute_condo_option`)
- Test: `tests/test_deterministic.py`

- [ ] **Step 1: Write the new compositional + oracle-anchored tests**

Add to `tests/test_deterministic.py`:
```python
def test_house_total_equals_sum_of_breakdown():
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_house_option
    h = HouseParams(initial_value=400_000, value_growth_rate=0.03,
                    annual_maintenance_rate=0.01, down_payment=80_000,
                    mortgage_rate=0.05, mortgage_term_years=25)
    sim = SimulationParams(years=10, discount_rate=0.04)
    econ = EconomicParams(mode="real")
    res = _compute_house_option(h, sim, econ)
    assert res.total_pv == pytest.approx(sum(res.breakdown.values()), rel=1e-12)
    for k in ("downpayment_pv", "mortgage_pv", "terminal_equity_pv"):
        assert k in res.breakdown
    assert res.breakdown["downpayment_pv"] == 80_000
    assert res.breakdown["terminal_equity_pv"] < 0  # equity is a benefit

def test_house_terminal_equity_oracle():
    """value_N = P0*(1+g)^N pinned; all-cash so equity = value_N*(1-sc)."""
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_house_option
    from hde.pv import pv_single
    h = HouseParams(initial_value=500_000, value_growth_rate=0.03,
                    annual_maintenance_rate=0.0, all_cash=True, selling_cost_rate=0.05)
    sim = SimulationParams(years=10, discount_rate=0.05)
    res = _compute_house_option(h, sim, EconomicParams(mode="real"))
    value_N = 500_000 * (1.03 ** 10)
    assert res.breakdown["terminal_equity_pv"] == pytest.approx(
        -pv_single(value_N * 0.95, 0.05, 10), rel=1e-9)

def test_price_drop_makes_owning_costlier():
    """Sign check the whole point of S4b: lower appreciation -> higher net cost."""
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_house_option
    sim = SimulationParams(years=10, discount_rate=0.04)
    econ = EconomicParams(mode="real")
    base = dict(initial_value=400_000, annual_maintenance_rate=0.01, all_cash=True)
    high = _compute_house_option(HouseParams(value_growth_rate=0.05, **base), sim, econ)
    low = _compute_house_option(HouseParams(value_growth_rate=-0.02, **base), sim, econ)
    assert low.total_pv > high.total_pv  # a price crash makes owning more expensive

def test_condo_zero_value_all_cash_unchanged_total():
    """Condo with default initial_value=0 + all_cash -> zero equity -> carrying-cost total."""
    from hde.models import CondoParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_condo_option
    c = CondoParams(monthly_fee=400, fee_escalation_rate=0.02, all_cash=True)
    sim = SimulationParams(years=10, discount_rate=0.04)
    res = _compute_condo_option(c, sim, EconomicParams(mode="real"))
    assert res.breakdown["terminal_equity_pv"] == 0.0
    assert res.breakdown["downpayment_pv"] == 0.0
    assert res.breakdown["mortgage_pv"] == 0.0
    # carrying total == fee+events+other+reserve (financing terms are all 0)
    assert res.total_pv == pytest.approx(
        res.breakdown["fee_pv"] + res.breakdown["events_pv"]
        + res.breakdown["other_pv"] + res.breakdown["reserve_pv"], rel=1e-12)
```

- [ ] **Step 2: Run to confirm new tests fail**

Run: `uv run python -m pytest tests/test_deterministic.py -k "sum_of_breakdown or terminal_equity_oracle or price_drop or zero_value_all_cash" -q`
Expected: FAIL (KeyError on new breakdown keys / assert mismatch).

- [ ] **Step 3: Implement — house** (in `_compute_house_option`, replace the `total_pv`/`breakdown` tail):
```python
    value_N = house.initial_value * (1 + house_value_growth) ** sim.years
    downpayment_pv, mortgage_pv, terminal_equity_pv = _financing_pv(
        house.initial_value, house.down_payment, house.mortgage_rate,
        house.mortgage_term_years, house.all_cash, house.selling_cost_rate,
        value_N, discount_rate, sim.years,
    )
    total_pv = (maintenance_pv + events_pv + other_pv
                + downpayment_pv + mortgage_pv + terminal_equity_pv)
    breakdown = {
        "maintenance_pv": maintenance_pv,
        "events_pv": events_pv,
        "other_pv": other_pv,
        "downpayment_pv": downpayment_pv,
        "mortgage_pv": mortgage_pv,
        "terminal_equity_pv": terminal_equity_pv,
    }
    assert set(breakdown.keys()) == HOUSE_BREAKDOWN_KEYS
    return OptionResult(total_pv=total_pv, breakdown=breakdown)
```

- [ ] **Step 4: Implement — condo** (in `_compute_condo_option`, compute `value_N` with condo growth and replace the tail):
```python
    condo_value_growth = _effective_growth_rate(condo.value_growth_rate, econ)
    value_N = condo.initial_value * (1 + condo_value_growth) ** sim.years
    downpayment_pv, mortgage_pv, terminal_equity_pv = _financing_pv(
        condo.initial_value, condo.down_payment, condo.mortgage_rate,
        condo.mortgage_term_years, condo.all_cash, condo.selling_cost_rate,
        value_N, discount_rate, sim.years,
    )
    total_pv = (fee_pv + events_pv + other_pv + reserve_pv
                + downpayment_pv + mortgage_pv + terminal_equity_pv)
    breakdown = {
        "fee_pv": fee_pv,
        "events_pv": events_pv,
        "other_pv": other_pv,
        "reserve_pv": reserve_pv,
        "downpayment_pv": downpayment_pv,
        "mortgage_pv": mortgage_pv,
        "terminal_equity_pv": terminal_equity_pv,
    }
    assert set(breakdown.keys()) == CONDO_BREAKDOWN_KEYS
    return OptionResult(total_pv=total_pv, breakdown=breakdown)
```

- [ ] **Step 5: Rewrite the now-failing existing house-total assertions compositionally**

Run `uv run python -m pytest tests/test_deterministic.py -q` and for EACH failing assertion on `house.total_pv == <magic>`:
- If the test's intent was a **component** (maintenance, events): assert on `res.breakdown["maintenance_pv"]` etc. (unchanged value).
- If it genuinely meant the **total**: convert to `assert res.total_pv == pytest.approx(sum(res.breakdown.values()))` plus, where a number is wanted, anchor the new keys via `_financing_pv`/oracle — never a hand-typed magic total.
Condo-total tests should already pass (initial_value=0 → financing terms 0).

- [ ] **Step 6: Run the deterministic suite green**

Run: `uv run python -m pytest tests/test_deterministic.py -q`
Expected: PASS (new + rewritten).

- [ ] **Step 7: Commit**
```bash
git add src/hde/deterministic.py tests/test_deterministic.py
git commit -m "feat(s4a): wire financing into deterministic house+condo; compositional test rewrite"
```

---

## Task 7: Affordability includes the mortgage payment

**Files:**
- Modify: `src/hde/deterministic.py` (`_annual_costs_for_option`)
- Test: `tests/test_deterministic.py`

- [ ] **Step 1: Write the failing test**
```python
def test_affordability_house_cost_includes_mortgage():
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _annual_costs_for_option
    from hde.pv import mortgage_payment
    h = HouseParams(initial_value=400_000, value_growth_rate=0.0,
                    annual_maintenance_rate=0.01, down_payment=80_000,
                    mortgage_rate=0.05, mortgage_term_years=25)
    sim = SimulationParams(years=5, discount_rate=0.04)
    costs = _annual_costs_for_option("house", h, sim, EconomicParams(mode="real"))
    M = mortgage_payment(320_000, 0.05, 25)
    # year 1 cost = maintenance(=0.01*400000) + mortgage payment
    assert costs[0] == pytest.approx(400_000 * 0.01 + M, rel=1e-9)

def test_affordability_all_cash_house_no_mortgage_term():
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _annual_costs_for_option
    h = HouseParams(initial_value=400_000, annual_maintenance_rate=0.01, all_cash=True)
    sim = SimulationParams(years=3, discount_rate=0.04)
    costs = _annual_costs_for_option("house", h, sim, EconomicParams(mode="real"))
    assert costs[0] == pytest.approx(400_000 * 0.01, rel=1e-9)  # no mortgage term
```

- [ ] **Step 2: Run to confirm fail**

Run: `uv run python -m pytest tests/test_deterministic.py -k "affordability_house_cost_includes or affordability_all_cash" -q`
Expected: FAIL.

- [ ] **Step 3: Implement** — in `_annual_costs_for_option`, add a mortgage term to the `condo` and `house` branches. At the top of the function (before the loop) compute the level payment once:
```python
    mort_payment = 0.0
    mort_term = 0
    if option_type in ("house", "condo") and not getattr(params, "all_cash", False):
        if params.down_payment is not None and params.mortgage_rate is not None \
           and params.mortgage_term_years is not None:
            from .pv import mortgage_payment
            loan = params.initial_value - params.down_payment
            mort_payment = mortgage_payment(loan, params.mortgage_rate, params.mortgage_term_years)
            mort_term = params.mortgage_term_years
```
Then in the `condo` and `house` branches, add the year's payment to the appended cost:
```python
            mort_t = mort_payment if (year <= mort_term) else 0.0
```
Concretely, change the two existing `costs.append(...)` lines:
```python
# condo branch — before:
            costs.append(base + ev_cost + other_cost)
# condo branch — after:
            costs.append(base + ev_cost + other_cost + (mort_payment if year <= mort_term else 0.0))

# house branch — before:
            costs.append(house_val * maint_rate + ev_cost + other_cost)
# house branch — after:
            costs.append(house_val * maint_rate + ev_cost + other_cost + (mort_payment if year <= mort_term else 0.0))
```
(The `rent` branch is unchanged — renters have no mortgage.)

- [ ] **Step 4: Run to confirm pass + affordability regressions**

Run: `uv run python -m pytest tests/test_deterministic.py -k affordability -q`
Expected: PASS. Update any existing affordability tests whose owned-option ratios now include the mortgage (compositional: the ratio numerator = old cost + mortgage payment).

- [ ] **Step 5: Commit**
```bash
git add src/hde/deterministic.py tests/test_deterministic.py
git commit -m "feat(s4a): affordability annual cost includes mortgage payment for owned options"
```

---

## Task 8: Config parsing + dual-layer capital-structure validation

**Files:**
- Modify: `src/hde/config.py` (`_parse_house`, `_parse_condo`, `validate_config`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**
```python
def test_config_house_requires_capital_structure():
    from hde.config import load_config_dict, ConfigValidationError
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "annual_maintenance_rate": 0.01}}
    with pytest.raises(ConfigValidationError):
        load_config_dict(cfg)  # neither all_cash nor mortgage block

def test_config_house_all_cash_ok():
    from hde.config import load_config_dict
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "annual_maintenance_rate": 0.01, "all_cash": True}}
    spec = load_config_dict(cfg)
    assert spec.house.all_cash is True

def test_config_house_mortgage_block_ok():
    from hde.config import load_config_dict
    cfg = {"years": 10, "discount_rate": 0.04,
           "house": {"initial_value": 400_000, "down_payment": 80_000,
                     "mortgage_rate": 0.05, "mortgage_term_years": 25}}
    spec = load_config_dict(cfg)
    assert spec.house.down_payment == 80_000

def test_config_condo_requires_initial_value_and_capital_structure():
    from hde.config import load_config_dict, ConfigValidationError
    cfg = {"years": 10, "discount_rate": 0.04,
           "condo": {"monthly_fee": 500, "all_cash": True}}  # missing initial_value
    with pytest.raises(ConfigValidationError):
        load_config_dict(cfg)
```

- [ ] **Step 2: Run to confirm fail**

Run: `uv run python -m pytest tests/test_config.py -k "capital_structure or all_cash_ok or mortgage_block or initial_value_and" -q`
Expected: FAIL.

- [ ] **Step 3: Implement — parse new fields** in `_parse_house` (add to the returned `HouseParams(...)`):
```python
        down_payment=(None if "down_payment" not in house_data else float(house_data["down_payment"])),
        mortgage_rate=(None if "mortgage_rate" not in house_data else float(house_data["mortgage_rate"])),
        mortgage_term_years=(None if "mortgage_term_years" not in house_data else int(house_data["mortgage_term_years"])),
        all_cash=bool(house_data.get("all_cash", False)),
        selling_cost_rate=float(house_data.get("selling_cost_rate", 0.05)),
```
And in `_parse_condo` add `initial_value`, `value_growth_rate`, and the same capital-structure fields:
```python
        initial_value=float(condo_data.get("initial_value", 0.0)),
        value_growth_rate=float(condo_data.get("value_growth_rate", 0.0)),
        down_payment=(None if "down_payment" not in condo_data else float(condo_data["down_payment"])),
        mortgage_rate=(None if "mortgage_rate" not in condo_data else float(condo_data["mortgage_rate"])),
        mortgage_term_years=(None if "mortgage_term_years" not in condo_data else int(condo_data["mortgage_term_years"])),
        all_cash=bool(condo_data.get("all_cash", False)),
        selling_cost_rate=float(condo_data.get("selling_cost_rate", 0.05)),
```

- [ ] **Step 4: Implement — validation** in `validate_config`, add a helper and call it for each present owned option:
```python
    def _check_capital_structure(name, opt):
        if opt is None:
            return
        if name == "condo" and (opt.initial_value is None or opt.initial_value <= 0):
            warnings.append(f"{name}: initial_value must be > 0 in the net-wealth model")
        if not opt.all_cash:
            if opt.down_payment is None or opt.mortgage_rate is None or opt.mortgage_term_years is None:
                warnings.append(
                    f"{name}: declare all_cash: true OR a mortgage block "
                    f"(down_payment + mortgage_rate + mortgage_term_years)")
            elif not (0 <= opt.down_payment <= opt.initial_value):
                warnings.append(f"{name}: down_payment must be in [0, initial_value]")
            elif opt.mortgage_rate < 0 or opt.mortgage_term_years <= 0:
                warnings.append(f"{name}: mortgage_rate >= 0 and mortgage_term_years > 0 required")
        if not (0 <= opt.selling_cost_rate < 1):
            warnings.append(f"{name}: selling_cost_rate must be in [0, 1)")

    _check_capital_structure("condo", spec.condo)
    _check_capital_structure("house", spec.house)
```

- [ ] **Step 5: Run to confirm pass + config regressions**

Run: `uv run python -m pytest tests/test_config.py -q`
Expected: PASS. Existing `test_config.py` fixtures that load a house/condo via dict now need `all_cash: true` or a mortgage block (and condo needs `initial_value`). Update those config dicts.

- [ ] **Step 6: Commit**
```bash
git add src/hde/config.py tests/test_config.py
git commit -m "feat(s4a): parse capital-structure fields + dual-layer validation (config layer)"
```

---

## Task 9: Wire financing into the Monte Carlo simulators (zero-vol convergence)

**Files:**
- Modify: `src/hde/monte_carlo.py` (`_simulate_house_pv_once`, `_simulate_condo_pv_once`; import `_financing_pv`)
- Test: `tests/test_monte_carlo.py`

- [ ] **Step 1: Write the failing tests**
```python
def test_mc_house_zero_vol_converges_with_mortgage():
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_house_option
    from hde.monte_carlo import _simulate_house_pv_once
    import numpy as np
    h = HouseParams(initial_value=400_000, value_growth_rate=0.03,
                    annual_maintenance_rate=0.01, down_payment=80_000,
                    mortgage_rate=0.05, mortgage_term_years=25)
    sim = SimulationParams(years=10, discount_rate=0.04, house_maintenance_vol=0.0)
    econ = EconomicParams(mode="real", inflation_vol=0.0)
    det = _compute_house_option(h, sim, econ).total_pv
    rng = np.random.default_rng(0)
    mc = _simulate_house_pv_once(h, sim, econ, rng)
    assert mc == pytest.approx(det, rel=1e-9)

def test_mc_condo_zero_vol_converges_with_value():
    from hde.models import CondoParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_condo_option
    from hde.monte_carlo import _simulate_condo_pv_once
    import numpy as np
    c = CondoParams(monthly_fee=500, fee_escalation_rate=0.02, initial_value=300_000,
                    value_growth_rate=0.03, down_payment=60_000, mortgage_rate=0.05,
                    mortgage_term_years=25)
    sim = SimulationParams(years=10, discount_rate=0.04, condo_fee_vol=0.0)
    econ = EconomicParams(mode="real", inflation_vol=0.0)
    det = _compute_condo_option(c, sim, econ).total_pv
    rng = np.random.default_rng(0)
    mc = _simulate_condo_pv_once(c, sim, econ, rng)
    assert mc == pytest.approx(det, rel=1e-9)
```

- [ ] **Step 2: Run to confirm fail**

Run: `uv run python -m pytest tests/test_monte_carlo.py -k "zero_vol_converges_with_mortgage or zero_vol_converges_with_value" -q`
Expected: FAIL (MC totals lack the financing terms).

- [ ] **Step 3: Implement — house simulator.** In `_simulate_house_pv_once`, track a per-path terminal value compounding **every** year (separate from the maintenance `house_value`), then add the financing terms to the returned `pv`. Add `terminal_value = house.initial_value` before the loop; inside the loop (after `inflation_factor` is drawn) add:
```python
        terminal_value *= (1 + _effective_growth_rate(value_growth_base, inflation_factor, econ))
```
After the loop, before `return pv`:
```python
    from .deterministic import _financing_pv
    dp_pv, mort_pv, term_eq_pv = _financing_pv(
        house.initial_value, house.down_payment, house.mortgage_rate,
        house.mortgage_term_years, house.all_cash, house.selling_cost_rate,
        terminal_value, r, sim.years,
    )
    pv += dp_pv + mort_pv + term_eq_pv
    return pv
```
**No new `rng` draws** — `terminal_value` reuses the per-year `inflation_factor` already drawn. RNG order preserved.

- [ ] **Step 4: Implement — condo simulator.** Same pattern in `_simulate_condo_pv_once`: add `terminal_value = condo.initial_value` before the loop; inside, after `inflation_factor`:
```python
        terminal_value *= (1 + _effective_growth_rate(condo.value_growth_rate, inflation_factor, econ))
```
and the identical `_financing_pv` block before `return pv` (using `condo.*` fields and `terminal_value`).

- [ ] **Step 5: Run convergence + reproducibility canary**

Run: `uv run python -m pytest tests/test_monte_carlo.py -k "zero_vol or reproducibility" -q`
Expected: PASS, including the existing `test_reproducibility_with_seed` (RNG-order canary — must still pass, proving no draw-order change).

- [ ] **Step 6: Run the whole MC suite green**

Run: `uv run python -m pytest tests/test_monte_carlo.py -q`
Expected: PASS. Rewrite any remaining MC total assertions compositionally (financing-specific MC fixtures get real mortgage blocks; financing-agnostic condo fixtures stay initial_value=0).

- [ ] **Step 7: Commit**
```bash
git add src/hde/monte_carlo.py tests/test_monte_carlo.py
git commit -m "feat(s4a): wire financing into MC house+condo (per-path terminal value, RNG order preserved)"
```

---

## Task 10: MCP sweep paths + drift guard + example configs

**Files:**
- Modify: `mcp_server/tools.py` (`_SWEEP_PATHS`)
- Modify: `tests/test_tools.py` (drift-guard `base` config)
- Modify: `examples/*.yaml`

- [ ] **Step 1: Add sweep paths** to `_SWEEP_PATHS`:
```python
    "house.down_payment":            ("house", "down_payment"),
    "house.mortgage_rate":           ("house", "mortgage_rate"),
    "house.mortgage_term_years":     ("house", "mortgage_term_years"),
    "house.selling_cost_rate":       ("house", "selling_cost_rate"),
    "condo.initial_value":           ("condo", "initial_value"),
    "condo.value_growth_rate":       ("condo", "value_growth_rate"),
    "condo.down_payment":            ("condo", "down_payment"),
    "condo.mortgage_rate":           ("condo", "mortgage_rate"),
    "condo.mortgage_term_years":     ("condo", "mortgage_term_years"),
    "condo.selling_cost_rate":       ("condo", "selling_cost_rate"),
```
Add `mortgage_term_years` to `INT_FIELDS` if such a coercion set exists (it coerces JSON floats → int for integer fields).

- [ ] **Step 2: Update the drift-guard `base`** in `test_sweep_paths_resolve_against_live_dataclass_fields` so house+condo declare capital structure (else `load_config_dict` rejects every path):
```python
        "condo": {"monthly_fee": 500, "fee_escalation_rate": 0.02, "reserve_contribution_rate": 0.01,
                  "initial_value": 300_000, "value_growth_rate": 0.02, "all_cash": True},
        "house": {"initial_value": 400_000, "value_growth_rate": 0.01, "annual_maintenance_rate": 0.015,
                  "all_cash": True},
```
For the mortgage-block sweep paths (`*.down_payment` etc.), the per-path injection must produce a VALID config — switch those owned options to a mortgage block when the swept field is a mortgage field, or seed `down_payment`/`mortgage_rate`/`mortgage_term_years` together in `base` and drop `all_cash`. Verify by running the test.

- [ ] **Step 3: Update example YAMLs** — every `house:`/`condo:` block in `examples/*.yaml` gets `all_cash: true` or a mortgage block; condo blocks get `initial_value`. Run each example through the CLI:
```bash
for f in examples/*.yaml; do uv run hde "$f" --no-monte-carlo --quiet || echo "FAILED: $f"; done
```

- [ ] **Step 4: Run tool tests**

Run: `uv run python -m pytest tests/test_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add mcp_server/tools.py tests/test_tools.py examples/
git commit -m "feat(s4a): sweep paths for financing params; update drift-guard + example configs"
```

---

## Task 11: Reporting surfaces the new breakdown lines

**Files:**
- Modify: `src/hde/reporting.py`
- Test: `tests/` (a light assertion that the report text mentions the new lines)

- [ ] **Step 1: Write a light failing test** (add to the existing reporting/smoke test file, or `tests/test_deterministic.py`):
```python
def test_report_mentions_financing_lines():
    from hde.models import HouseParams, SimulationParams, EconomicParams, ComparisonSpec
    from hde.deterministic import compute_deterministic
    from hde.reporting import format_text_report  # reporting.py:27 — confirm its arg signature
    spec = ComparisonSpec(
        simulation=SimulationParams(years=10, discount_rate=0.04),
        economic=EconomicParams(mode="real"),
        house=HouseParams(initial_value=400_000, value_growth_rate=0.03,
                          annual_maintenance_rate=0.01, all_cash=True),
    )
    text = format_text_report(compute_deterministic(spec))  # pass args per reporting.py:27
    assert "terminal_equity" in text.lower() or "equity" in text.lower()
```
(Confirm `format_text_report`'s real signature at `reporting.py:27` and pass the matching args.)

- [ ] **Step 2: Run → fail; implement; run → pass.** Add the new breakdown keys to whatever per-option breakdown the report prints. Keep it display-only.

- [ ] **Step 3: Commit**
```bash
git add src/hde/reporting.py tests/
git commit -m "feat(s4a): report surfaces down payment / mortgage / terminal-equity lines"
```

---

## Task 12: Full-suite verification + fracture-line check

**Files:** none (verification)

- [ ] **Step 1: Full suite**

Run: `uv run python -m pytest -q`
Expected: ALL green. Count must be ≥ 151 (existing) + new tests. No `total_pv == <magic number>` assertions remain (grep to confirm):
```bash
grep -rn "total_pv == " tests/ | grep -vE "approx|sum\(" || echo "no magic-number totals — good"
```

- [ ] **Step 2: Examples smoke**

Run: `for f in examples/*.yaml; do uv run hde "$f" --quiet || echo "FAILED: $f"; done`
Expected: every example runs.

- [ ] **Step 3: Fracture-line check (spec §8).** If at this point house is green but condo is not finished, the acceptable interim recovery point is: house net-wealth complete + green, condo carrying-cost-only with an explicit interim-asymmetry docstring on `_compute_condo_option`, condo financing in an immediate follow-on. Default expectation: both done.

- [ ] **Step 4: Final commit (if any verification fixups)**
```bash
git add -A
git commit -m "test(s4a): full-suite green — net-wealth foundation complete"
```

---

## Self-review notes (for the executor)

- **Oracle independence:** never edit a Task-1 pinned value to match the implementation — only to match an external calculator. The invariant assertions are the backstop.
- **Maintenance basis unchanged:** `value_N` (terminal sale value, compounds N times) is computed SEPARATELY from the maintenance `house_value` (year-1 = initial). Do not refactor the maintenance loop.
- **Condo initial_value=0 + all_cash → zero equity → old total:** this is the intentional low-churn path for financing-agnostic condo fixtures.
- **RNG order:** no new `rng.normal()` draws in the MC simulators; `terminal_value` reuses the per-year `inflation_factor`. `test_reproducibility_with_seed` must stay green.
- **money-path: no** — no `audit-skipped` marker (repo CLAUDE.md), no fund-repo imports.
