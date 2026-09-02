# S4b — demographic input-slot sketch

**Date:** 2026-08-26
**Status:** Draft for operator ratification. This is the unblocking artifact named by
demoflow's Tranche-2 deferral (`demoflow` spec §7(a)); ratification opens that build.
**Scope:** where demoflow's ScenarioPrior artifact plugs into hde's engines — nothing
here builds the emitter (that is Tranche 2's own task list).

## 0. What exists today (measured, this tree)

`value_growth_rate` is a scalar on `CondoParams`/`HouseParams`, applied
DETERMINISTICALLY every year inside `monte_carlo.py` (`terminal_value *= 1 +
_effective_growth_rate(...)`). There is no appreciation uncertainty, no price-shock
channel, and no geography anywhere in hde. EconomicParams carries `mode`
(real|nominal); the ScenarioPrior is REAL (CPI-deflated) decimal/yr.

## 1. The three input slots

### Slot 1 — `market_scenario` on ComparisonSpec (optional, default None)

```python
@dataclass
class MarketScenario:
    path: str                 # ScenarioPrior JSON file
    geography: str            # exact Geography string value, e.g. "MTL_RMR"
```

Loading rules (all refusals typed, fail-loud):
- File must validate against the emitter's OWN contract: exact field allowlist,
  closed `flags[]` enum, complete Cartesian row keys, `p10 ≤ mean ≤ p90`,
  `drawdown_weight_tilt ≥ 0`, declared enums only, `allow_nan=False`. A file that
  fails any check refuses naming the failing rows — never a partial load.
- `spec.market_scenario.geography` must match ≥1 row; rows for other geographies are
  ignored (they exist because the artifact is whole-of-grid).
- Dwelling type maps: `CondoParams → "condo"`, `HouseParams → "house"`; rent has no
  slot (renters face rent escalation, not price drift — out of scope v0, stated).
- **Nominal-mode refusal:** if `econ.mode == "nominal"` and a prior is loaded →
  InputError. Composing a real-terms prior into a nominal run is the
  confident-wrong-answer class.

### Slot 2 — demographic drift composes ADDITIVELY onto the user's growth rate

Per year t, real drift used by the engine =
`user_value_growth_rate + demo_drift(draw)`.

Ruled semantics (stated here so neither side improvises):
  *(Lifted 2026-09-02: the drift is a real rate and nominal mode composes it with inflation like every other real input; a financed buyer runs nominal mode and must reach the prior.)*
- The user's scalar remains their NON-demographic view (their macro view); the prior
  contributes the demographic component. Additive keeps both meaningful and keeps
  `value_growth_rate = 0` runs interpretable ("drift is exactly what demography says").
- Horizon bands are PIECEWISE CONSTANT: years 1–2030−start use the 2030 row,
  then 2035 row, etc.; the last declared band holds to the horizon end. No
  interpolation is invented (a knot scheme would be an unvalidated model).
- Per MC DRAW: scenario drawn uniformly from {low, reference, high} (the ISQ fan IS
  the scenario uncertainty; no re-weighting v0), then a drift level drawn once per
  band from Normal(mean, σ) with σ = (p90 − p10) / (2 × 1.2816) (normal fit through
  the published quartiles' span; asymmetry between the tails is below the noise this
  layer can defend). One Z per (draw, band) — constant within a band, independent
  across bands, seeded from the same rng (reproducibility preserved).
- **No floor.** Drift passes through unfloored; the existing
  `value_growth_rate ≤ −1` guard remains the only protection. Flooring is an
  operator decision explicitly deferred (demoflow spec records the same deferral).

### Slot 3 — `drawdown_weight_tilt` on a NEW price-shock channel

hde has no crash channel, so v0 adds one, default-off:

```python
@dataclass
class PriceShockParams:
    annual_hazard: float = 0.0      # P(price drawdown begins this year)
    severity_mean: float = 0.20     # mean fractional drawdown
    severity_vol: float = 0.10
```

When a prior is loaded, the effective hazard = `annual_hazard ×
drawdown_weight_tilt(row for the current band)`; severity draws reuse the existing
lognormal `_shock_multiplier` machinery. A tilt of 1.0 is neutral; `< 1.0` rows carry
`never_relax_stress` and the emitted flag is CONTRACT-CHECKED at load (a tilt < 1
whose row lacks the flag fails load — mirrors the emitter's test).
With no prior loaded, behavior is byte-identical to today (hazard defaults 0).

## 2. Provenance and output

When a prior is loaded, every result payload (deterministic summary, MC summary,
affordability block) gains `"market_scenario": {"file_sha256", "assumptions_hash",
"mapping_version", "isq_edition", "census_year", "constants_as_of", "start_calendar_year",
"horizon_years", "source_keys"}` (widened 2026-09-01, readiness plan E.3 — was {"file_sha256", "assumptions_hash",
"geography", "schema_version"}`. Two runs over different priors cannot share an
identity silently — the same law as every other input this repo takes.

## 3. What is deliberately out

- Rent-side demographic pass-through (no slot).
- Interpolation/knots between horizon bands; β-prior reshaping (linear-through-origin,
  uniform β stays as demoflow pinned it).
- Any absolute crash probability from demoflow (locus rule: substrate emits the tilt;
  hde owns the hazard).
- MCP tool changes beyond passing `market_scenario` through the existing spec
  ingestion (tools wrap engines; no logic crosses).

## 4. Build order on ratification

1. Tranche-2 emitter (`demoflow.output.scenario_prior`) + its §10 RED fixtures.
2. Slots above in hde (`models.py`, `config.py`, `monte_carlo.py`) + loader/validator.
3. Cross-repo golden: one emitted artifact consumed by one recorded hde run, both
   committed, both suites green.
