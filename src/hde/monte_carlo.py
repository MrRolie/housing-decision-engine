"""
Monte Carlo simulation for condo vs house cost analysis.

This module provides functions for running Monte Carlo simulations
with randomness in:
- Annual cost levels (via volatility parameters)
- Event timing (via jitter or hazard models)
- Event costs (via cost volatility and distribution)
- Inflation-linked correlated shocks (optional)

One economy per path: the inflation path is drawn ONCE per iteration as a
`PathWorld` and handed to every option, so the three totals that
`prob_*_cheapest` ranks are three prices of the SAME future.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import numpy.typing as npt

from .models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
    MonteCarloSummary,
    ComparisonSpec,
    ComparisonMonteCarloResult,
    MonteCarloOptionResult,
    AffordabilityMCReport,
    RentParams,
    IncomeParams,
    PayDropEvent,
    PriceShockParams,
)
from .market_scenario import (
    LoadedScenarioPrior,
    SCENARIOS,
    band_drift,
    band_horizon_for_calendar_year,
    calendar_year_for_sim_year,
    load_scenario_prior,
)
from .pv import pv_single, pv_recurring_with_escalation
from .tax_treatment import TaxParams, after_tax_factor, terminal_from_growth


def _effective_growth_rate(base_rate: float, inflation_factor: float, econ: EconomicParams) -> float:
    """
    Combine user growth/escalation with inflation factor when in nominal mode.
    """
    if econ.mode == "nominal":
        return (1 + base_rate) * inflation_factor - 1
    return base_rate


def _draw_inflation_factor(
    rng: np.random.Generator,
    econ: EconomicParams,
) -> tuple[float, float]:
    """
    Draw an annual inflation factor and return (factor, z_inflation).
    Factor multiplies cash-flow escalation; z is used for correlated shocks.
    """
    base = 1.0 + (econ.inflation_rate if econ.mode == "nominal" else 0.0)
    if econ.inflation_vol <= 0:
        return base, 0.0
    z = float(rng.normal())
    factor = float(base * np.exp(econ.inflation_vol * z - 0.5 * econ.inflation_vol ** 2))
    return factor, z


@dataclass(frozen=True)
class PathWorld:
    """The economy ONE Monte Carlo path happens in.

    Drawn once at the top of each iteration and handed to every option, so the
    condo, the house and the renter are priced in the SAME future. Before
    2026-09-21 each owned option drew its own inflation path from the shared
    generator and the renter composed with the fixed scalar `inflation_rate`,
    so the three totals `np.argmin` ranks came from three unrelated economies
    and `prob_condo_cheapest` did not mean what it says
    (docs/specs/2026-09-21-one-world-simulation.md §2).

    `inflation_factors[t - 1]` and `z_inflation[t - 1]` are year t's factor and
    the standard normal behind it: the factor multiplies every escalation
    through `_effective_growth_rate`, the z drives every `corr_inflation_*`
    shock. In REAL mode `_effective_growth_rate` discards the factor by
    construction, so there only the z is live.
    """

    inflation_factors: Tuple[float, ...]
    z_inflation: Tuple[float, ...]
    # The HOUSING MARKET on this path. Every owned option reads the same
    # draws, so a crash is one market event and not one per property.
    # Empty when this run wires no crash channel.
    crash_uniforms: Tuple[float, ...] = ()
    crash_zs: Tuple[float, ...] = ()
    # (ISQ scenario, one z per declared horizon band): the population future
    # this path realizes. One per path, not one per option — Quebec does not
    # grow one way for the condo and another for the house. None with no prior.
    drift: Optional[Tuple[str, Dict[int, float]]] = None
    # Ordinary year-to-year variation in home value (simulation.value_growth_vol).
    # Empty when that key is 0.
    z_value: Tuple[float, ...] = ()
    # Whether `z_inflation` is a real draw or a constant zero. It decides
    # whether a `corr_inflation_*` key means anything: see `corr`.
    inflation_is_stochastic: bool = False

    def corr(self, rho: float) -> float:
        """`rho` as the shocks should actually use it.

        `_correlated_z` composes `rho * base_z + sqrt(1 - rho**2) * eps`, which
        is a unit normal ONLY when `base_z` is one. With `inflation_vol` at 0
        the inflation z is the constant 0.0, so the formula returns
        `sqrt(1 - rho**2) * eps` — a normal SHRUNK by that factor. A user who
        set `corr_inflation_house: 0.9` expecting a correlation got their
        maintenance shock damped by 56% instead (std 1.000 -> 0.436, measured
        2026-09-21 over 20,000 draws), and the schema note has always promised
        the opposite: "inert unless economic.inflation_vol > 0".

        There is nothing to correlate with when inflation has no variance, so
        the correlation is dropped and the shock keeps its full width.
        """
        return rho if self.inflation_is_stochastic else 0.0

    def crash_draw(self, year: int) -> Tuple[float, float]:
        """(uniform, severity z) for `year`.

        The `(1.0, 0.0)` fallback is reachable only when every wired
        `price_shock` has a non-positive hazard, because `_world_draws` gates
        the channel on `annual_hazard > 0` and `_apply_price_shock` returns
        before reading either figure at a hazard that low.
        """
        if not self.crash_uniforms:
            return 1.0, 0.0
        return self.crash_uniforms[year - 1], self.crash_zs[year - 1]

    def value_z(self, year: int) -> float:
        """The shared value-dispersion z for `year`; 0.0 when the channel is
        off, which `_apply_value_dispersion` discards before using it."""
        if not self.z_value:
            return 0.0
        return self.z_value[year - 1]


@dataclass(frozen=True)
class WorldDraws:
    """Which market channels this run's paths draw, derived ONCE per run.

    Each flag mirrors the condition that made the corresponding channel
    consume draws before the world existed, so a spec that wires none of them
    leaves the generator stream exactly where it was.
    """

    crash: bool = False
    drift_bands: Tuple[int, ...] = ()
    value_vol: float = 0.0


def _world_draws(spec: ComparisonSpec, prior_rows_by_option) -> WorldDraws:
    """Read the spec once for what the WORLD must draw per path.

    `crash` gates on a positive hazard rather than a present `price_shock`
    block: at a hazard of zero the old code consumed no draw, and a spec that
    spells out `annual_hazard: 0` must keep the stream it had.

    `drift_bands` is the SORTED union of the horizon bands the wired priors
    declare. Sorted because the band z's are drawn in this order and a run must
    be reproducible from its seed without depending on set iteration order.
    """
    crash = False
    for opt in (spec.condo, spec.house, spec.rent):
        shock = getattr(opt, "price_shock", None) if opt is not None else None
        if shock is not None and shock.annual_hazard > 0:
            crash = True
    bands: set = set()
    for rows in prior_rows_by_option:
        if rows is not None:
            bands.update(h for h, _ in rows.keys())
    return WorldDraws(
        crash=crash,
        drift_bands=tuple(sorted(bands)),
        value_vol=max(0.0, spec.simulation.value_growth_vol),
    )


def _draw_path_world(
    rng: np.random.Generator,
    econ: EconomicParams,
    years: int,
    draws: WorldDraws = WorldDraws(),
) -> PathWorld:
    """Draw one path's world: the economy, then the housing market in it.

    Consumes NO draws for a channel this run does not wire — the inflation
    guard lives inside `_draw_inflation_factor` and the other three are gated
    on `draws`. So a run with none of them leaves the generator stream exactly
    where it was before the world existed.

    The inflation loop stays FIRST and unchanged for the same reason: a spec
    that wires inflation uncertainty and nothing else keeps the stream it had
    when the world held only inflation.
    """
    n = max(0, years)
    factors: List[float] = []
    zs: List[float] = []
    for _ in range(n):
        factor, z = _draw_inflation_factor(rng, econ)
        factors.append(factor)
        zs.append(z)

    # The market. One crash uniform and one severity z per year, read by every
    # owned option: with equal hazards the condo and the house crash in the
    # same years, and with unequal ones the higher hazard's crash years are a
    # superset of the lower's. That coupling needs no correlation parameter —
    # it is the same market, not two markets to correlate
    # (docs/specs/2026-09-21-one-world-simulation.md §2).
    #
    # The severity z is drawn every year whether or not the hazard fires, so
    # the stream does not depend on which options crashed.
    crash_u: List[float] = []
    crash_z: List[float] = []
    if draws.crash:
        for _ in range(n):
            crash_u.append(float(rng.random()))
            crash_z.append(float(rng.normal()))

    drift: Optional[Tuple[str, Dict[int, float]]] = None
    if draws.drift_bands:
        scenario = SCENARIOS[int(rng.integers(0, len(SCENARIOS)))]
        drift = (scenario, {h: float(rng.normal()) for h in draws.drift_bands})

    z_value: List[float] = []
    if draws.value_vol > 0:
        z_value = [float(rng.normal()) for _ in range(n)]

    return PathWorld(
        tuple(factors), tuple(zs), tuple(crash_u), tuple(crash_z), drift,
        tuple(z_value), econ.inflation_vol > 0,
    )


def _is_flat(values: Sequence[float]) -> bool:
    """True when every entry is the same float — the test that lets a constant
    series take its exact closed form instead of accumulating a loop."""
    return not values or all(v == values[0] for v in values)


def _pv_escalating_series(
    annual_amount: float,
    growth_rates: Sequence[float],
    discount_rate: float,
    n_years: int,
) -> float:
    """PV of a recurring cost growing at `growth_rates[t - 1]` into year t,
    with year 1 already carrying one year of escalation — the convention of
    `pv_recurring_with_escalation`, which this generalises to a rate that
    varies by year.

    When every year's rate is identical the series is geometric and the closed
    form is exact, so it is used. That keeps a flat world — every real-mode
    run, and every nominal run with `inflation_vol` at zero — bit-for-bit on
    the arithmetic that shipped before the world existed.
    """
    if n_years <= 0:
        return 0.0
    if _is_flat(growth_rates):
        return pv_recurring_with_escalation(
            annual_amount, growth_rates[0], discount_rate, n_years
        )
    pv = 0.0
    amount = annual_amount
    for year in range(1, n_years + 1):
        amount *= (1 + growth_rates[year - 1])
        pv += pv_single(amount, discount_rate, year)
    return pv


def _pv_reset_series(
    own_annual: float,
    market_annual: float,
    growth_rates: Sequence[float],
    market_growth_rates: Sequence[float],
    discount_rate: float,
    n_years: int,
    reset_year: int,
) -> float:
    """PV of rent that runs on the tenant's own figure until `reset_year` and
    on the market figure from that year on.

    Two tracks escalate side by side, EACH AT ITS OWN RATE: the rent this
    household pays, and what a comparable unit asks. The tenant moves from the
    first to the second in the year the tenancy ends, so a reset in year 8
    lands on year 8's market rent rather than on today's figure — the market
    does not wait for the lease.

    The two rates have to be separate, and the engine's own anchor is why. A
    sitting tenant under Québec's continuing-lease protection renews near 0.0%
    real, and `rent.rent_escalation_rate`'s rationale records that landlords
    pass through only ~21% of market movements at renewal. So a tenant who
    correctly states their own escalation near zero would, under one shared
    rate, be told market rents are frozen for the whole horizon — which erases
    precisely the exposure this channel was built to show.

    Both tracks use the convention of `_pv_escalating_series`: year 1 already
    carries one year of escalation. So with equal figures AND equal rates this
    reproduces that function's series for any reset year, which is the
    cleanest statement of what a reset to your own rent costs: nothing.
    """
    if n_years <= 0:
        return 0.0
    pv = 0.0
    own = own_annual
    market = market_annual
    for year in range(1, n_years + 1):
        own *= (1 + growth_rates[year - 1])
        market *= (1 + market_growth_rates[year - 1])
        pv += pv_single(market if year >= reset_year else own, discount_rate, year)
    return pv


def _correlated_z(base_z: float, rho: float, rng: np.random.Generator) -> float:
    """
    Generate a correlated standard normal using base_z as common factor.
    """
    if rho == 0:
        return float(rng.normal())
    eps = float(rng.normal())
    residual = max(0.0, 1.0 - rho ** 2)
    return rho * base_z + (residual ** 0.5) * eps


def _shock_multiplier(vol: float, z: float, model: str) -> float:
    """
    Convert a standard normal draw into a multiplicative shock.
    """
    if vol <= 0:
        return 1.0
    if model == "lognormal":
        return float(np.exp(vol * z - 0.5 * vol ** 2))
    return max(0.0, 1.0 + vol * z)


# ----- S4b market-scenario composition (Slots 2 and 3) -----

def _load_prior_if_any(spec: ComparisonSpec):
    """Load the ScenarioPrior when the spec carries one; None otherwise."""
    if spec.market_scenario is None:
        return None
    return load_scenario_prior(
        spec.market_scenario.path, spec.market_scenario.geography
    )


# The prior's drift is a REAL rate. In nominal mode it is added to the (real)
# value_growth_rate and the sum is composed with inflation by
# _effective_growth_rate — the same contract as every other real input, so a
# nominal run with a prior is coherent. The S4b-era refusal of that
# combination was lifted 2026-09-02 (round-four evaluation: a financed Montréal
# buyer must run nominal mode for the lender's payment, and the shipped
# Montréal prior was unreachable from it).


def _drift_context(prior_rows, world: PathWorld):
    """This option's view of the path's demographic context.

    The context itself — the ISQ scenario and one z per declared band — is a
    property of the WORLD and is drawn once per path in `_draw_path_world`.
    This returns it only when the option actually has prior rows to look it up
    in, so an option with no prior composes no drift.

    Until 2026-09-21 this drew the context per option, so on the shipped
    showcase the condo and the house picked the same ISQ population scenario
    on 35% of paths — indistinguishable from the 33% you get by chance with
    three scenarios. Quebec realizes one population future per path
    (docs/specs/2026-09-21-one-world-simulation.md §2).
    """
    if prior_rows is None:
        return None
    return world.drift


def _band_growth_additive(prior_rows, drift_context, sim_year: int):
    """Demographic drift component for one simulation year (piecewise-constant
    horizon bands), composed ADDITIVELY onto the user's value_growth_rate."""
    if prior_rows is None or drift_context is None:
        return 0.0
    scenario, zs = drift_context
    horizon = band_horizon_for_calendar_year(calendar_year_for_sim_year(sim_year))
    row = prior_rows[(horizon, scenario)]
    return band_drift(row, zs[horizon])


def _apply_price_shock(value_tracks, shock: PriceShockParams, tilt: float,
                       u: float, sev_z: float):
    """
    S4b Slot 3: with probability annual_hazard × tilt a drawdown begins this year;
    severity reuses the lognormal shock machinery. Returns the (possibly
    shocked) value tracks — callers must rebind their locals from the return.
    No-op when the effective hazard is 0 — this keeps default-off
    byte-identical.

    `u` and `sev_z` come from the path's `PathWorld` and are the SAME figures
    for every option on that path. Until 2026-09-21 each option drew its own
    `rng.random()` here, so on the shipped Montréal showcase — two properties
    in one market with identical hazard and severity — the condo and the house
    crashed in unrelated years and their totals came out essentially
    uncorrelated (measured: corr −0.038 over 400 paths, and
    std(condo − house) LARGER than either option's own std). That is the same
    defect the shared inflation path fixed, in the channel that carries all of
    this engine's price risk
    (docs/specs/2026-09-21-one-world-simulation.md §2).
    """
    # tilt is an unbounded multiplier from the prior (validated >= 0 only), so
    # the composed hazard is capped at certainty — the same clamp the event
    # hazard channel applies (readiness plan C.7).
    hazard = min(shock.annual_hazard * tilt, 1.0)
    if hazard <= 0:
        return value_tracks
    if u < hazard:
        severity = min(
            shock.severity_mean * _shock_multiplier(shock.severity_vol, sev_z, "lognormal"),
            1.0,
        )
        for i in range(len(value_tracks)):
            value_tracks[i] *= (1 - severity)
    return value_tracks


def _apply_value_dispersion(value_tracks, vol: float, z: float, model: str):
    """Ordinary year-to-year variation in the home's value.

    The crash channel is a rare large drawdown; this is the everyday movement
    that sat at exactly zero while every cost in the model had a spread.
    Terminal equity is the largest term in an owned option's total that depends
    on an UNKNOWN: -$218,959 of the shipped showcase's $518,779, second in
    magnitude only to the $480,000 paid at year 0, which is certain. So the
    biggest uncertain term was the one term with no dispersion
    (docs/specs/2026-09-21-one-world-simulation.md §1.B).

    `z` is the world's, shared with every other owned option on the path, so
    the condo and the house move together. Mean-preserving under the lognormal
    model, and a no-op at `vol <= 0` consuming nothing: the z was drawn by the
    world or not at all.
    """
    if vol <= 0:
        return value_tracks
    mult = _shock_multiplier(vol, z, model)
    for i in range(len(value_tracks)):
        value_tracks[i] *= mult
    return value_tracks


def _maintenance_rate_for_year(house: HouseParams, year: int) -> float:
    """
    Return maintenance rate for a given year using an optional age/condition curve.
    """
    if not house.maintenance_curve:
        return house.annual_maintenance_rate
    points = house.maintenance_curve
    if year <= points[0][0]:
        return points[0][1]
    if year >= points[-1][0]:
        return points[-1][1]
    for (y0, r0), (y1, r1) in zip(points[:-1], points[1:]):
        if y0 <= year <= y1:
            span = y1 - y0
            weight = (year - y0) / span
            return r0 + weight * (r1 - r0)
    return house.annual_maintenance_rate


def _sample_event_year_hazard(
    event: EventConfig,
    max_year: int,
    rng: np.random.Generator,
) -> Optional[int]:
    """
    Sample event year using a simple hazard that can rise over time.
    Returns None if the event never occurs within the horizon.
    """
    hazard_start = max(1, event.hazard_start_year)
    for year in range(1, max_year + 1):
        hazard = 0.0
        if year >= hazard_start:
            hazard = event.hazard_base + event.hazard_growth * max(0, year - hazard_start)
        hazard = min(max(hazard, 0.0), 1.0)
        if hazard <= 0:
            continue
        if rng.random() < hazard:
            return year
    return None


def _sample_reset_year(
    hazard: float, max_year: int, rng: np.random.Generator
) -> Optional[int]:
    """First year the tenancy ends, from a constant annual hazard; None when it
    never does inside the horizon.

    Drawn per option rather than in the `PathWorld` because a tenancy ending is
    a HOUSEHOLD event, not a market one — unlike the crash, which is the market
    and therefore shared. Consumes NO draw at a non-positive hazard, which is
    what keeps every spec that does not wire the channel byte-identical. The
    clamp to certainty mirrors `_sample_event_year_hazard`.
    """
    if hazard <= 0:
        return None
    h = min(hazard, 1.0)
    for year in range(1, max_year + 1):
        if rng.random() < h:
            return year
    return None


def _summarize_array(arr: npt.NDArray[np.float64]) -> MonteCarloSummary:
    """
    Compute summary statistics for a Monte Carlo distribution.
    """
    return MonteCarloSummary(
        mean=float(np.mean(arr)),
        std=float(np.std(arr)),
        p5=float(np.percentile(arr, 5)),
        p50=float(np.percentile(arr, 50)),
        p95=float(np.percentile(arr, 95)),
    )


def _sample_event_year(
    event: EventConfig,
    max_year: int,
    rng: np.random.Generator,
) -> Optional[int]:
    """
    Sample the year when an event occurs.
    
    Uses Option 1: jitter around expected year with Normal distribution,
    clamped to valid range.
    
    Args:
        event: Event configuration
        max_year: Maximum year (analysis horizon)
        rng: Random number generator
    
    Returns:
        Sampled year in range [1, max_year]
    """
    if event.timing_model == "hazard":
        return _sample_event_year_hazard(event, max_year, rng)
    
    mu = event.expected_year
    sigma = event.timing_std_years
    min_y = max(1, event.min_year)
    max_y = event.max_year if event.max_year is not None else max_year
    max_y = min(max_y, max_year)  # Ensure we don't exceed analysis horizon
    
    if sigma <= 0:
        # No jitter, just clamp to valid range
        return int(max(min_y, min(mu, max_y)))
    
    # Draw from Normal distribution
    y_raw = rng.normal(mu, sigma)
    
    # Clamp to valid range
    y_clamped = max(min_y, min(y_raw, max_y))
    
    # Round to nearest integer
    year = int(round(y_clamped))
    
    # Final bounds check
    return max(1, min(year, max_year))


def _sample_event_cost(
    event: EventConfig,
    z_cost: float,
) -> float:
    """
    Sample the cost of an event using the chosen distribution and z draw.
    """
    if event.cost_vol <= 0:
        return event.base_cost
    
    model = "lognormal" if event.cost_distribution == "lognormal" else "normal"
    multiplier = _shock_multiplier(event.cost_vol, z_cost, model)
    return event.base_cost * multiplier


def _simulate_condo_pv_once(
    condo: CondoParams,
    sim: SimulationParams,
    econ: EconomicParams,
    world: PathWorld,
    rng: np.random.Generator,
    prior_rows=None,
    shock: Optional[PriceShockParams] = None,
    hbp_repayment_pv: float = 0.0,
) -> float:
    """
    Run one simulation of condo PV with randomness.

    Randomness applied to:
    - Annual fees (if condo_fee_vol > 0)
    - Event costs and timing (hazard or jitter)
    - Other recurring costs (if other_cost_vol > 0)
    - S4b: demographic drift (if a ScenarioPrior is wired) and the price-drawdown
      channel (if PriceShockParams are wired); both default-off, consuming no
      rng draws when absent.

    The inflation path comes from `world`, shared with every other option on
    this path; this function draws no inflation of its own.
    """
    pv = 0.0
    r = sim.discount_rate

    fee_growth_base = condo.fee_escalation_rate
    reserve_growth_base = condo.reserve_growth_rate

    fee_amount = condo.monthly_fee * 12
    reserve_balance = condo.reserve_initial_balance
    terminal_value = condo.initial_value

    other_amounts = [c.annual_amount for c in condo.other_recurring_costs]

    # Precompute event years
    event_years = {event.name: _sample_event_year(event, sim.years, rng) for event in condo.events}

    drift_context = _drift_context(prior_rows, world)

    for year in range(1, sim.years + 1):
        inflation_factor = world.inflation_factors[year - 1]
        z_inf = world.z_inflation[year - 1]
        growth_base = condo.value_growth_rate + _band_growth_additive(prior_rows, drift_context, year)
        terminal_value *= (1 + _effective_growth_rate(growth_base, inflation_factor, econ))
        # Ordinary variation first, then the rare drawdown on top of it: the
        # two are different channels, and the crash is a shock to the value
        # the market had reached this year.
        terminal_value, = _apply_value_dispersion(
            [terminal_value], sim.value_growth_vol, world.value_z(year), sim.shock_model)
        if shock is not None:
            tilt = 1.0
            if prior_rows is not None:
                horizon = band_horizon_for_calendar_year(calendar_year_for_sim_year(year))
                tilt = prior_rows[(horizon, drift_context[0])].drawdown_weight_tilt
            crash_u, crash_z = world.crash_draw(year)
            terminal_value, = _apply_price_shock(
                [terminal_value], shock, tilt, crash_u, crash_z)

        # Condo fee with escalation and volatility
        fee_growth = _effective_growth_rate(fee_growth_base, inflation_factor, econ)
        fee_amount *= (1 + fee_growth)
        z_fee = _correlated_z(z_inf, world.corr(sim.corr_inflation_condo), rng)
        fee_amount *= _shock_multiplier(sim.condo_fee_vol, z_fee, sim.shock_model)
        pv += pv_single(fee_amount, r, year)

        # Reserves
        reserve_growth = _effective_growth_rate(reserve_growth_base, inflation_factor, econ)
        reserve_balance *= (1 + reserve_growth)
        reserve_contribution = fee_amount * condo.reserve_contribution_rate
        reserve_balance += reserve_contribution

        # Other recurring costs with volatility
        for idx, rec_cost in enumerate(condo.other_recurring_costs):
            growth = _effective_growth_rate(rec_cost.escalation_rate, inflation_factor, econ)
            other_amounts[idx] *= (1 + growth)
            z_other = _correlated_z(z_inf, world.corr(sim.corr_inflation_other), rng)
            other_amounts[idx] *= _shock_multiplier(sim.other_cost_vol, z_other, sim.shock_model)
            pv += pv_single(other_amounts[idx], r, year)

        # Events
        for event in condo.events:
            if event_years[event.name] is None:
                continue
            if event_years[event.name] == year:
                z_event = _correlated_z(z_inf, world.corr(sim.corr_inflation_event_cost), rng)
                event_cost = _sample_event_cost(event, z_event)
                covered = min(reserve_balance, event_cost)
                reserve_balance -= covered
                net_cost = event_cost - covered
                pv += pv_single(net_cost, r, year)

    # The financing leg is DETERMINISTIC on every path (spec §2): the renewal
    # ladder rides along with it, or the central case and the paths would
    # disagree on an input neither of them draws.
    from .deterministic import _financing_pv, renewal_args_for
    dp_pv, mort_pv, term_eq_pv = _financing_pv(
        condo.initial_value, condo.down_payment, condo.mortgage_rate,
        condo.mortgage_term_years, condo.all_cash, condo.selling_cost_rate,
        terminal_value, r, sim.years, condo.financed_purchase_costs,
        **renewal_args_for(condo),
    )
    # The HBP repayment leg is a constant (priced at the renter's unshocked
    # return), added on every path exactly as the deterministic engine adds it.
    pv += dp_pv + mort_pv + term_eq_pv + condo.purchase_costs + hbp_repayment_pv
    return pv


def _simulate_house_pv_once(
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,
    world: PathWorld,
    rng: np.random.Generator,
    prior_rows=None,
    shock: Optional[PriceShockParams] = None,
    hbp_repayment_pv: float = 0.0,
) -> float:
    """
    Run one simulation of house PV with randomness.

    Randomness applied to:
    - Annual maintenance (if house_maintenance_vol > 0)
    - Event costs and timing
    - S4b: demographic drift (if a ScenarioPrior is wired) and the price-drawdown
      channel (if PriceShockParams are wired); both default-off, consuming no
      rng draws when absent.

    The inflation path comes from `world`, shared with every other option on
    this path; this function draws no inflation of its own.
    """
    pv = 0.0
    r = sim.discount_rate

    value_growth_base = house.value_growth_rate
    house_value = house.initial_value
    terminal_value = house.initial_value

    other_amounts = [c.annual_amount for c in house.other_recurring_costs]
    event_years = {event.name: _sample_event_year(event, sim.years, rng) for event in house.events}

    drift_context = _drift_context(prior_rows, world)

    for year in range(1, sim.years + 1):
        inflation_factor = world.inflation_factors[year - 1]
        z_inf = world.z_inflation[year - 1]
        growth_base = value_growth_base + _band_growth_additive(prior_rows, drift_context, year)
        terminal_value *= (1 + _effective_growth_rate(growth_base, inflation_factor, econ))

        if year > 1:
            value_growth = _effective_growth_rate(growth_base, inflation_factor, econ)
            house_value *= (1 + value_growth)

        # Both tracks are the same asset, so both take the same move — the
        # treatment `_apply_price_shock` has always given them.
        house_value, terminal_value = _apply_value_dispersion(
            [house_value, terminal_value], sim.value_growth_vol,
            world.value_z(year), sim.shock_model)

        if shock is not None:
            tilt = 1.0
            if prior_rows is not None:
                horizon = band_horizon_for_calendar_year(calendar_year_for_sim_year(year))
                tilt = prior_rows[(horizon, drift_context[0])].drawdown_weight_tilt
            crash_u, crash_z = world.crash_draw(year)
            house_value, terminal_value = _apply_price_shock(
                [house_value, terminal_value], shock, tilt, crash_u, crash_z)

        maintenance_rate = _maintenance_rate_for_year(house, year)
        maint_t = maintenance_rate * house_value
        z_house = _correlated_z(z_inf, world.corr(sim.corr_inflation_house), rng)
        maint_t *= _shock_multiplier(sim.house_maintenance_vol, z_house, sim.shock_model)
        pv += pv_single(maint_t, r, year)

        # Other recurring costs with volatility
        for idx, rec_cost in enumerate(house.other_recurring_costs):
            growth = _effective_growth_rate(rec_cost.escalation_rate, inflation_factor, econ)
            other_amounts[idx] *= (1 + growth)
            z_other = _correlated_z(z_inf, world.corr(sim.corr_inflation_other), rng)
            other_amounts[idx] *= _shock_multiplier(sim.other_cost_vol, z_other, sim.shock_model)
            pv += pv_single(other_amounts[idx], r, year)

        # Events
        for event in house.events:
            if event_years[event.name] is None:
                continue
            if event_years[event.name] == year:
                z_event = _correlated_z(z_inf, world.corr(sim.corr_inflation_event_cost), rng)
                event_cost = _sample_event_cost(event, z_event)
                pv += pv_single(event_cost, r, year)

    from .deterministic import _financing_pv, renewal_args_for
    dp_pv, mort_pv, term_eq_pv = _financing_pv(
        house.initial_value, house.down_payment, house.mortgage_rate,
        house.mortgage_term_years, house.all_cash, house.selling_cost_rate,
        terminal_value, r, sim.years, house.financed_purchase_costs,
        **renewal_args_for(house),
    )
    pv += dp_pv + mort_pv + term_eq_pv + house.purchase_costs + hbp_repayment_pv
    return pv


def _simulate_rent_pv_once(
    rent: RentParams,
    sim: SimulationParams,
    econ: EconomicParams,
    world: PathWorld,
    rng: np.random.Generator,
    tax: Optional[TaxParams] = None,
    reset_year: Optional[int] = None,
) -> float:
    """
    Run one simulation of rent PV with randomness.

    Mirrors the deterministic rent model (`_compute_rent_option`) but layers on:
    - Rent escalation shock (if sim.rent_escalation_vol > 0)
    - Event costs and timing (jitter or hazard)
    - Other recurring cost volatility (if sim.other_cost_vol > 0)
    - Investment-return shock on the invested down payment
      (if sim.investment_return_vol > 0)
    - A lease reset: `reset_year` is the year the tenancy ends on this path, or
      None. It is drawn by the CALLER rather than here, because the
      affordability channel has to price the same reset on the same path — a
      second draw would give one path two different tenancies.

    Inflation comes from `world`, the same economy the owned options are priced
    in. Until 2026-09-21 this function composed with the fixed scalar
    `econ.inflation_rate`, which is not merely independent of the owners' draws
    but deterministic — the renter's costs could not move with the economy at
    all, so the argmin that produces `prob_rent_cheapest` compared a stochastic
    owner against a frozen renter.

    Discounting uses `sim.discount_rate` directly, matching the condo/house
    simulators and the deterministic rent model.
    """
    dr = sim.discount_rate

    # One path-level escalation shock, scaling the composed rate exactly as it
    # did when that rate was a single scalar for the whole horizon.
    if sim.rent_escalation_vol > 0:
        z_esc = float(rng.normal())
        esc_shock = _shock_multiplier(sim.rent_escalation_vol, z_esc, sim.shock_model)
    else:
        esc_shock = 1.0
    esc_rates = [
        _effective_growth_rate(rent.rent_escalation_rate, factor, econ) * esc_shock
        for factor in world.inflation_factors
    ]

    annual_rent = rent.monthly_rent * 12
    if reset_year is None:
        rent_pv = _pv_escalating_series(annual_rent, esc_rates, dr, sim.years)
    else:
        # Config validation pairs the two keys, so a live hazard always has a
        # market figure to reset to.
        # The market track composes with the SAME world (so a high-inflation
        # year lifts both tracks) but carries its own real rate.
        market_rates = [
            _effective_growth_rate(rent.reset_market_escalation_rate, factor, econ)
            for factor in world.inflation_factors
        ]
        rent_pv = _pv_reset_series(
            annual_rent, rent.reset_to_monthly_rent * 12, esc_rates, market_rates,
            dr, sim.years, reset_year,
        )

    # Events (same pattern as condo/house: None-guarded, correlated z draw
    # against the world's z for the year the event lands in — before the world
    # this passed a hardcoded 0.0, because the renter had no z of their own).
    events_pv = 0.0
    event_years = {event.name: _sample_event_year(event, sim.years, rng) for event in rent.events}
    for event in rent.events:
        year = event_years[event.name]
        if year is None:
            continue
        z_event = _correlated_z(
            world.z_inflation[year - 1], world.corr(sim.corr_inflation_event_cost), rng
        )
        event_cost = _sample_event_cost(event, z_event)
        events_pv += pv_single(event_cost, dr, year)

    # Other recurring costs, optionally shocked (level shock applied to the
    # series; it carries no year index, so it keeps its own independent draw —
    # there is no `corr_inflation_rent_other` key and this slice invents none).
    other_pv = 0.0
    for cost in rent.other_recurring_costs:
        if sim.other_cost_vol > 0:
            z_other = float(rng.normal())
            shock = _shock_multiplier(sim.other_cost_vol, z_other, sim.shock_model)
            annual = cost.annual_amount * shock
        else:
            annual = cost.annual_amount
        esc_series = [
            _effective_growth_rate(cost.escalation_rate, factor, econ)
            for factor in world.inflation_factors
        ]
        other_pv += _pv_escalating_series(annual, esc_series, dr, sim.years)

    # Capital leg, mirroring the owned side (downpayment_pv + terminal equity):
    # the renter's capital is charged at year 0 and its terminal value credited.
    refunds = tax.refunds if tax is not None else 0.0
    capital = rent.invested_down_payment + refunds
    if capital > 0:
        # investment_return_rate is a REAL input, composed with the world's
        # inflation year by year exactly as value growth is on the owned side.
        inv_rates = [
            _effective_growth_rate(rent.investment_return_rate, factor, econ)
            for factor in world.inflation_factors
        ]
        # investment_return_vol is the ANNUAL volatility of the gross return
        # (1 + r): one mean-preserving shock per year on (1 + r), so a run of
        # bad years can leave the renter's capital below principal, exactly as
        # the owned side can be hit by a price shock. (Before 2026-09-02 the
        # knob scaled the RATE once per path — the renter could never lose and
        # 0.10 moved a 3% return by ±0.3pp; the evaluation found both.)
        # Under a `tax:` block (2026-09-05) the taxable share compounds the
        # after-tax factor of the SAME shocked gross factor each year, so a
        # zero-vol path reproduces the deterministic engine exactly.
        # `after_tax_factor` keeps the FIXED inflation_rate: in nominal mode it
        # ignores that argument outright, and in real mode the world's factor
        # never reaches a growth rate, so no stochastic figure belongs there.
        growth = 1.0
        taxed = 1.0
        if sim.investment_return_vol > 0:
            for t in range(sim.years):
                z_inv = float(rng.normal())
                gross = (1 + inv_rates[t]) * _shock_multiplier(sim.investment_return_vol, z_inv, sim.shock_model)
                growth *= gross
                if tax is not None:
                    taxed *= after_tax_factor(gross, econ.mode, econ.inflation_rate,
                                              tax.marginal_rate, tax.inclusion)
        elif sim.years > 0 and _is_flat(inv_rates):
            # Constant rate: the power is exact, so a flat world reproduces the
            # pre-world arithmetic bit for bit.
            growth = (1 + inv_rates[0]) ** sim.years
            if tax is not None:
                taxed = after_tax_factor(1 + inv_rates[0], econ.mode, econ.inflation_rate,
                                         tax.marginal_rate, tax.inclusion) ** sim.years
        else:
            for t in range(sim.years):
                gross = 1 + inv_rates[t]
                growth *= gross
                if tax is not None:
                    taxed *= after_tax_factor(gross, econ.mode, econ.inflation_rate,
                                              tax.marginal_rate, tax.inclusion)
        benefit = terminal_from_growth(tax, capital, growth, taxed) / ((1 + dr) ** sim.years)
    else:
        benefit = 0.0

    return rent_pv + events_pv + other_pv + capital - benefit


def _compute_income_affordability_once(
    income: IncomeParams,
    sim: SimulationParams,
    econ: EconomicParams,
    condo_annual_costs: List[float],
    house_annual_costs: List[float],
    rent_annual_costs: List[float],
    rng: np.random.Generator,
) -> dict:
    """
    For one MC path, draw a stochastic income trajectory and report, per option,
    whether the housing cost/income ratio exceeded the affordability threshold in
    any year.

    A single income trajectory is drawn per call and shared across all present
    options (pay-drop timing/magnitude are common to the household, not the
    housing choice).
    """
    threshold = income.affordability_threshold
    growth = income.income_growth_rate
    if econ.mode == "nominal":  # REAL input, composed like the cost numerator
        growth = (1 + growth) * (1 + econ.inflation_rate) - 1

    # Pre-draw jittered years for each pay-drop event (once per sim path).
    # Drawing inside the year loop would allow a single event to fire in
    # multiple years or be missed entirely within one simulation path.
    event_years: dict = {}
    for event in income.pay_drop_events:
        if event.year_jitter_std > 0:
            ev_year = max(1, min(sim.years, round(event.year + rng.normal(0, event.year_jitter_std))))
        else:
            ev_year = event.year
        event_years[id(event)] = ev_year

    # One stochastic income trajectory, shared across options.
    traj: List[float] = []
    inc = income.annual_income
    for t in range(sim.years):
        year = t + 1
        for event in income.pay_drop_events:
            if event_years[id(event)] == year:
                if event.magnitude_vol > 0:
                    mag = event.magnitude * float(np.exp(rng.normal(0, event.magnitude_vol)))
                    # A pay-drop event is a CUT by definition: the retained
                    # fraction is clamped to [0.01, 1.0] — the floor keeps a
                    # 99% cut as the worst representable outcome, the ceiling
                    # truncates upside draws (a shocked raise is not modelled),
                    # so the realised mean sits below event.magnitude whenever
                    # magnitude_vol > 0. Stated in the pay_drop_events schema note.
                    mag = min(max(mag, 0.01), 1.0)
                else:
                    mag = event.magnitude
                inc *= mag
        traj.append(inc)
        if t < sim.years - 1:
            inc *= (1 + growth)

    result = {}
    for option_type, costs in [
        ("condo", condo_annual_costs),
        ("house", house_annual_costs),
        ("rent", rent_annual_costs),
    ]:
        if not costs:
            continue
        exceeds = any(c / i > threshold for c, i in zip(costs, traj) if i > 0)
        result[option_type] = exceeds

    return result


def run_monte_carlo(spec: ComparisonSpec) -> ComparisonMonteCarloResult:
    """
    Run Monte Carlo simulation for all options present in the spec.

    Simulates each present option (condo / house / rent) over `num_sims` paths,
    deriving per-option PV distributions, pairwise ranking probabilities
    (which option is cheapest), and — if income params are present — the
    probability that each option's cost/income ratio breaches the affordability
    threshold in any year.

    Args:
        spec: ComparisonSpec bundling simulation/economic params and the
            present option parameters (condo/house/rent/income).

    Returns:
        ComparisonMonteCarloResult with per-option results, ranking
        probabilities, and an optional affordability MC report.

    Note:
        - Only options present in the spec are simulated.
        - RNG is seeded with sim.random_seed for reproducibility.
        - Per-iteration draw order is world -> condo -> house -> rent -> income.
          The world consumes no draws for a channel the spec does not wire, so
          a run that wires none of them keeps the stream it had before the
          world existed. `inflation_vol` is only one of four such channels: the
          crash uniforms, the demographic scenario and the value-dispersion z
          are also drawn there and also gated, so a spec WITH a prior or a live
          price_shock does consume world draws even at `inflation_vol` 0 — the
          shipped showcase is exactly that case.
        - Every option on one iteration is priced in the SAME world: the
          inflation path, the housing market's crash draws and the path's
          demographic scenario are drawn once into a `PathWorld` and handed to
          all three simulators, which is what makes `prob_*_cheapest` the
          chance an option is cheapest in one future rather than across three
          unrelated ones (docs/specs/2026-09-21-one-world-simulation.md §2).
          What stays per-option is what belongs to the PROPERTY rather than the
          market: its fee or maintenance shock, its own events, and — on the
          rent side — the tenancy's own reset hazard and the renter's portfolio.
        - This function has no side effects and does not print anything.
    """
    sim = spec.simulation
    econ = spec.economic

    # Reject impossible appreciation once per run: the per-sim loops compound
    # terminal_value by (1 + value_growth_rate) year-by-year, which flips sign by
    # year parity when value_growth_rate <= -1 (mirrors the deterministic guard;
    # config validation covers the config path, this covers direct construction).
    from .deterministic import _require_valued_growth
    if spec.condo is not None:
        _require_valued_growth(spec.condo.value_growth_rate, "condo")
    if spec.house is not None:
        _require_valued_growth(spec.house.value_growth_rate, "house")

    # The lease-reset pair travels together. Config validation already refuses
    # one without the other, and this covers the direct-construction path the
    # config never sees — the same reason `_require_valued_growth` is repeated
    # here. Without it a hazard with no market figure reaches `_pv_reset_series`
    # and dies on `None * 12`, which tells the caller nothing.
    if (spec.rent is not None and spec.rent.reset_hazard > 0
            and spec.rent.reset_to_monthly_rent is None):
        raise ValueError(
            "rent.reset_hazard is set but rent.reset_to_monthly_rent is None: "
            "the engine will not guess what a comparable unit asks. State the "
            "monthly market rent, or leave reset_hazard at 0."
        )

    # S4b: nominal-mode refusal + ScenarioPrior load/validation (fail-loud).
    prior = _load_prior_if_any(spec)
    condo_prior_rows = prior.rows_for_dwelling("condo") if prior is not None and spec.condo is not None else None
    house_prior_rows = prior.rows_for_dwelling("house") if prior is not None and spec.house is not None else None
    provenance = prior.provenance_block() if prior is not None else None

    rng = np.random.default_rng(sim.random_seed)

    # The HBP repayment leg per owned option — a constant on every path.
    from .deterministic import hbp_repayment_pv_for
    condo_hbp = hbp_repayment_pv_for(spec, "condo") if spec.condo is not None else 0.0
    house_hbp = hbp_repayment_pv_for(spec, "house") if spec.house is not None else 0.0

    n = sim.num_sims
    condo_pvs = np.empty(n, dtype=np.float64) if spec.condo is not None else None
    house_pvs = np.empty(n, dtype=np.float64) if spec.house is not None else None
    rent_pvs = np.empty(n, dtype=np.float64) if spec.rent is not None else None

    # Pre-compute deterministic annual costs for affordability (done once, not per-sim).
    afford_condo_costs: List[float] = []
    afford_house_costs: List[float] = []
    afford_rent_costs: List[float] = []
    if spec.income is not None:
        from .deterministic import _annual_costs_for_option
        if spec.condo is not None:
            afford_condo_costs = _annual_costs_for_option("condo", spec.condo, sim, econ)
        if spec.house is not None:
            afford_house_costs = _annual_costs_for_option("house", spec.house, sim, econ)
        if spec.rent is not None:
            afford_rent_costs = _annual_costs_for_option("rent", spec.rent, sim, econ)

    afford_condo_flags = (
        np.zeros(n, dtype=bool) if spec.condo is not None and spec.income is not None else None
    )
    afford_house_flags = (
        np.zeros(n, dtype=bool) if spec.house is not None and spec.income is not None else None
    )
    afford_rent_flags = (
        np.zeros(n, dtype=bool) if spec.rent is not None and spec.income is not None else None
    )

    # What the world must draw per path: read once from the spec, not per path.
    world_draws = _world_draws(spec, (condo_prior_rows, house_prior_rows))

    # The affordability channel reads an UNDISCOUNTED cost array per option and
    # compares it against a per-path income. A lease reset changes that array,
    # so when the channel is wired the arrays are precomputed once per possible
    # reset year and indexed per path. Without this the affordability report
    # read one array for the whole run and said `prob_rent_exceeds: 0.0` on a
    # config whose reset pushed the burden from 23.8% to 70.3% of income on 998
    # of 1,000 paths — a probability of zero for something close to certain.
    afford_rent_by_reset: dict = {}
    if (spec.income is not None and spec.rent is not None
            and spec.rent.reset_hazard > 0):
        from .deterministic import _annual_costs_for_option as _costs
        for k in range(1, sim.years + 1):
            afford_rent_by_reset[k] = _costs("rent", spec.rent, sim, econ,
                                             rent_reset_year=k)

    for i in range(n):
        # ONE economy and ONE housing market per iteration, drawn before any
        # option is priced.
        world = _draw_path_world(rng, econ, sim.years, world_draws)
        # The tenancy's own hazard: a HOUSEHOLD event, so it is drawn here
        # rather than in the world, but drawn ONCE per path — the PV leg and
        # the affordability leg must price the same tenancy. Consumes nothing
        # at a hazard of zero, which is every spec shipped before 2026-09-21.
        reset_year = (_sample_reset_year(spec.rent.reset_hazard, sim.years, rng)
                      if spec.rent is not None else None)
        if spec.condo is not None:
            condo_pvs[i] = _simulate_condo_pv_once(
                spec.condo, sim, econ, world, rng,
                prior_rows=condo_prior_rows,
                shock=spec.condo.price_shock,
                hbp_repayment_pv=condo_hbp,
            )
        if spec.house is not None:
            house_pvs[i] = _simulate_house_pv_once(
                spec.house, sim, econ, world, rng,
                prior_rows=house_prior_rows,
                shock=spec.house.price_shock,
                hbp_repayment_pv=house_hbp,
            )
        if spec.rent is not None:
            rent_pvs[i] = _simulate_rent_pv_once(
                spec.rent, sim, econ, world, rng, spec.tax, reset_year=reset_year)
        if spec.income is not None:
            rent_costs_this_path = (
                afford_rent_by_reset.get(reset_year, afford_rent_costs)
                if reset_year is not None else afford_rent_costs
            )
            flags = _compute_income_affordability_once(
                spec.income, sim, econ,
                afford_condo_costs, afford_house_costs, rent_costs_this_path,
                rng,
            )
            if afford_condo_flags is not None:
                afford_condo_flags[i] = flags.get("condo", False)
            if afford_house_flags is not None:
                afford_house_flags[i] = flags.get("house", False)
            if afford_rent_flags is not None:
                afford_rent_flags[i] = flags.get("rent", False)

    def _make_opt(pvs):
        if pvs is None:
            return None
        return MonteCarloOptionResult(pvs=pvs, summary=_summarize_array(pvs))

    condo_result = _make_opt(condo_pvs)
    house_result = _make_opt(house_pvs)
    rent_result = _make_opt(rent_pvs)

    # Ranking probabilities — require the arrays, so computed here (not recoverable
    # from scalar summaries). Only meaningful with >= 2 present options.
    present = [
        (name, pvs)
        for name, pvs in [("condo", condo_pvs), ("house", house_pvs), ("rent", rent_pvs)]
        if pvs is not None
    ]
    prob_condo = prob_house = prob_rent = None
    if len(present) >= 2:
        stacked = np.stack([pvs for _, pvs in present], axis=0)  # (n_options, n_sims)
        winners = np.argmin(stacked, axis=0)  # index of cheapest option per sim
        idx = {name: k for k, (name, _) in enumerate(present)}
        if "condo" in idx:
            prob_condo = float(np.mean(winners == idx["condo"]))
        if "house" in idx:
            prob_house = float(np.mean(winners == idx["house"]))
        if "rent" in idx:
            prob_rent = float(np.mean(winners == idx["rent"]))

    affordability_mc = None
    if spec.income is not None:
        affordability_mc = AffordabilityMCReport(
            threshold=spec.income.affordability_threshold,
            prob_condo_exceeds=(
                float(np.mean(afford_condo_flags)) if afford_condo_flags is not None else None
            ),
            prob_house_exceeds=(
                float(np.mean(afford_house_flags)) if afford_house_flags is not None else None
            ),
            prob_rent_exceeds=(
                float(np.mean(afford_rent_flags)) if afford_rent_flags is not None else None
            ),
        )

    return ComparisonMonteCarloResult(
        condo=condo_result,
        house=house_result,
        rent=rent_result,
        prob_condo_cheapest=prob_condo,
        prob_house_cheapest=prob_house,
        prob_rent_cheapest=prob_rent,
        affordability_mc=affordability_mc,
        market_scenario=provenance,
    )
