"""
Story-driven decision plots: a five-act narrative rendering of a housing
decision, built for a non-technical viewer (operator doctrine: PLOTS ARE
FIRST-CLASS — each plot must TELL A STORY, not just chart data).

Acts:
  1. The answer       — headline bar chart with the verdict stated in words.
  2. The race         — cumulative cost curves and where the lead changes hands.
  3. The uncertainty  — Monte Carlo net-cost distributions (skipped silently
                         when no MC ran).
  4. Your home's possible futures — value fan chart under the ScenarioPrior,
                         or the honest single-growth line when none is loaded.
  5. Why              — the demographic signal itself (requires a prior).
  6. The market line  — the verdict's sensitivity to the quoted amounts:
                         total cost vs monthly rent and vs purchase price,
                         with the break-even (flip) points marked. The local
                         quotes are single data points; this act shows how much
                         room they have before the verdict flips. Needs rent +
                         an owned option; skipped silently otherwise.

House rules enforced here:
  - One style helper; large readable labels; colorblind-safe palette.
  - Every title is a sentence a person would say; subtitles carry assumptions.
  - Key numbers are annotated directly on the chart — no legend-hunting.
  - Every number is derived from the passed-in results, never invented.
  - matplotlib only; no seaborn.

`render_decision_story` is the orchestrator; it returns only the figures that
were actually rendered (degraded inputs render fewer acts).
"""

from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .deterministic import (
    _effective_growth_rate,
    _event_year_deterministic,
    _financing_pv,
    _maintenance_rate_for_year,
    compute_deterministic,
)
from .config import single_path_run
from .market_scenario import (
    LoadedScenarioPrior,
    band_horizon_for_calendar_year,
    calendar_year_for_sim_year,
)
from .models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    ComparisonSpec,
    CondoParams,
    HouseParams,
    RentParams,
)
from .pv import mortgage_payment, pv_single

# ---------------------------------------------------------------------------
# House style — one palette, one formatter, one axes dresser
# ---------------------------------------------------------------------------

# Okabe–Ito colorblind-safe palette.
OPTION_COLORS: Dict[str, str] = {
    "rent": "#0072B2",   # blue
    "condo": "#009E73",  # bluish green
    "house": "#D55E00",  # vermillion
}
OPTION_DISPLAY = {
    "rent": "Renting",
    "condo": "Buying a condo",
    "house": "Buying a house",
}
SCENARIO_COLORS = {"low": "#0072B2", "reference": "#555555", "high": "#D55E00"}

PRIOR_SOURCE_LINE = "Source: UN WPP 2024-derived demand model, ISQ 2026 scenarios"

# Act 6 sweep geometry: ±SWEEP_SPAN around the user's quoted amount,
# SWEEP_POINTS per axis. Illustrative presentation choice (not an engine
# default): wide enough to show the flip point when it exists, narrow enough
# to stay on-scale around the user's actual market.
SWEEP_SPAN = 0.35
SWEEP_POINTS = 41

_RC = {
    "font.size": 13,
    "axes.titlesize": 17,
    "axes.titleweight": "bold",
    "axes.labelsize": 13,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
}


def _new_figure(figsize=(11.0, 6.5)) -> tuple[Figure, Axes]:
    plt.rcParams.update(_RC)
    fig, ax = plt.subplots(figsize=figsize)
    return fig, ax


def _money_k(x: float, _pos=None) -> str:
    if abs(x) >= 1_000_000:
        return f"${x / 1_000_000:,.1f}M"
    return f"${x / 1000:,.0f}k"


def _set_money_axis(ax: Axes) -> None:
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_money_k))


def _save(fig: Figure, out_dir: Path, stem: str, fmt: str) -> Path:
    path = out_dir / f"{stem}.{fmt}"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Pure computation helpers (unit-tested directly; plots read these)
# ---------------------------------------------------------------------------

def verdict_sentence(det: ComparisonDeterministicResult, years: int) -> str:
    """
    Act 1 title, as words: e.g. "Renting wins by $84,000 over 25 years".

    The margin is vs the closest competitor (the decision-relevant gap).
    """
    costs = {
        key: opt.total_pv
        for key, opt in (("condo", det.condo), ("house", det.house), ("rent", det.rent))
        if opt is not None
    }
    if not costs:
        raise ValueError("no priced options in deterministic result")
    ranked = sorted(costs.items(), key=lambda kv: kv[1])
    if len(ranked) == 1:
        key, pv = ranked[0]
        return f"Only one option priced: {OPTION_DISPLAY[key]} at ${pv:,.0f} over {years} years"
    (best_key, best_pv), (runner_key, runner_pv) = ranked[0], ranked[1]
    margin = runner_pv - best_pv
    if margin < 0.50:
        a, b = OPTION_DISPLAY[best_key], OPTION_DISPLAY[runner_key]
        return f"It is effectively a tie between {a} and {b} over {years} years"
    return (
        f"{OPTION_DISPLAY[best_key]} wins by ${margin:,.0f} "
        f"over {years} years"
    )


def _verdict_subtitle(spec: ComparisonSpec) -> str:
    horizon = f"{spec.simulation.years}-year horizon"
    if spec.market_scenario is not None:
        return (
            f"under {spec.market_scenario.geography} demographic conditions · "
            f"{horizon}"
        )
    return f"under your stated assumptions · {horizon}"


def _cumulative_cost_curves(
    spec: ComparisonSpec,
) -> Dict[str, Dict[str, List[float]]]:
    """
    Cumulative present-value cost per year (index 0..N) for each option present,
    mirroring the deterministic engine's year-by-year arithmetic.

    Returns per option {"paid": [...], "net": [...]}:
      - "paid": running total of out-of-pocket payments (the race viewers see);
      - "net":  paid minus the end-of-horizon equity credit (rent: the invested
        down-payment benefit), so net[-1] reconciles to OptionResult.total_pv
        exactly.

    Uses the engine's own helpers (_financing_pv, mortgage_payment,
    _maintenance_rate_for_year) rather than re-deriving any math.
    """
    sim = spec.simulation
    econ = spec.economic
    dr = sim.discount_rate
    n = sim.years
    curves: Dict[str, Dict[str, List[float]]] = {}

    def _flows_to_curves(flows_by_year: Dict[int, float],
                         credits_by_year: Dict[int, float]) -> Dict[str, List[float]]:
        paid_cum, net_cum = [0.0] * (n + 1), [0.0] * (n + 1)
        paid_running = net_running = 0.0
        for y in range(0, n + 1):
            paid_running += pv_single(flows_by_year.get(y, 0.0), dr, y)
            net_running += pv_single(
                flows_by_year.get(y, 0.0) + credits_by_year.get(y, 0.0), dr, y,
            )
            paid_cum[y], net_cum[y] = paid_running, net_running
        return {"paid": paid_cum, "net": net_cum}

    def _owned_financing_flows(params) -> tuple[Dict[int, float], Dict[int, float]]:
        g_eff = _effective_growth_rate(params.value_growth_rate, econ)
        value_n = params.initial_value * (1 + g_eff) ** n
        dp_pv, mort_pv, term_eq_pv = _financing_pv(
            params.initial_value, params.down_payment, params.mortgage_rate,
            params.mortgage_term_years, params.all_cash, params.selling_cost_rate,
            value_n, dr, n,
        )
        flows: Dict[int, float] = {0: dp_pv}
        if not params.all_cash:
            loan = params.initial_value - params.down_payment
            payment = mortgage_payment(loan, params.mortgage_rate, params.mortgage_term_years)
            for y in range(1, min(n, params.mortgage_term_years) + 1):
                flows[y] = flows.get(y, 0.0) + payment
        # Terminal equity credit lands at year N; keep PV-exact by lifting the
        # already-discounted credit back to a year-N flow (discounted once below).
        credits: Dict[int, float] = {n: term_eq_pv * ((1 + dr) ** n)}
        return flows, credits

    if spec.condo is not None:
        condo: CondoParams = spec.condo
        fee_growth = _effective_growth_rate(condo.fee_escalation_rate, econ)
        reserve_growth = _effective_growth_rate(condo.reserve_growth_rate, econ)
        other_growth = [_effective_growth_rate(c.escalation_rate, econ) for c in condo.other_recurring_costs]
        event_years = {e.name: _event_year_deterministic(e, n) for e in condo.events}
        flows, credits = _owned_financing_flows(condo)
        fee = condo.monthly_fee * 12
        reserve_balance = condo.reserve_initial_balance
        for year in range(1, n + 1):
            fee *= (1 + fee_growth)
            reserve_balance *= (1 + reserve_growth)
            reserve_balance += fee * condo.reserve_contribution_rate
            flows[year] = flows.get(year, 0.0) + fee
            for idx, rec in enumerate(condo.other_recurring_costs):
                flows[year] += rec.annual_amount * (1 + other_growth[idx]) ** year
            for event in condo.events:
                if event_years[event.name] == year:
                    covered = min(reserve_balance, event.base_cost)
                    reserve_balance -= covered
                    flows[year] += event.base_cost - covered  # net out-of-pocket
        curves["condo"] = _flows_to_curves(flows, credits)

    if spec.house is not None:
        house: HouseParams = spec.house
        g_eff = _effective_growth_rate(house.value_growth_rate, econ)
        other_growth = [_effective_growth_rate(c.escalation_rate, econ) for c in house.other_recurring_costs]
        event_years = {e.name: _event_year_deterministic(e, n) for e in house.events}
        flows, credits = _owned_financing_flows(house)
        value = house.initial_value
        for year in range(1, n + 1):
            if year > 1:
                value *= (1 + g_eff)
            flows[year] = flows.get(year, 0.0) + _maintenance_rate_for_year(house, year) * value
            for idx, rec in enumerate(house.other_recurring_costs):
                flows[year] += rec.annual_amount * (1 + other_growth[idx]) ** year
            for event in house.events:
                if event_years[event.name] == year:
                    flows[year] += event.base_cost
        curves["house"] = _flows_to_curves(flows, credits)

    if spec.rent is not None:
        rent: RentParams = spec.rent
        esc = _effective_growth_rate(rent.rent_escalation_rate, econ)
        flows: Dict[int, float] = {}
        credits: Dict[int, float] = {}
        annual_rent = rent.monthly_rent * 12
        for year in range(1, n + 1):
            flows[year] = flows.get(year, 0.0) + annual_rent * (1 + esc) ** year
            for event in rent.events:
                if _event_year_deterministic(event, n) == year:
                    flows[year] += event.base_cost
            for rec in rent.other_recurring_costs:
                g = _effective_growth_rate(rec.escalation_rate, econ)
                flows[year] += rec.annual_amount * (1 + g) ** year
        if rent.invested_down_payment > 0:
            r_inv = rent.investment_return_rate
            # benefit PV = FV/(1+dr)^N (engine arithmetic); lift to a year-N
            # flow so the curve discounts it exactly once.
            credits[n] = -rent.invested_down_payment * ((1 + r_inv) ** n)
        curves["rent"] = _flows_to_curves(flows, credits)

    return curves


def find_crossovers(curves: Dict[str, List[float]]) -> List[tuple[int, str, str]]:
    """
    Years where the cheapest option changes, as (year, from_key, to_key).
    Judged on the paid (out-of-pocket) race — what a viewer sees crossing.
    """
    keys = list(curves.keys())
    leaders = [min(keys, key=lambda k: curves[k][t]) for t in range(1, len(next(iter(curves.values()))))]
    crossovers = []
    for i in range(1, len(leaders)):
        if leaders[i] != leaders[i - 1]:
            crossovers.append((i + 1, leaders[i - 1], leaders[i]))
    return crossovers


# ---------------------------------------------------------------------------
# Act 6 pure helpers: sensitivity of the verdict to the quoted amounts
# ---------------------------------------------------------------------------

def _sweep_axis(center: float) -> List[float]:
    """Sweep grid around the user's quoted amount (±SWEEP_SPAN)."""
    return list(np.linspace(center * (1 - SWEEP_SPAN), center * (1 + SWEEP_SPAN), SWEEP_POINTS))


def _owned_at_price(params, price: float):
    """
    An owned option re-priced at ``price`` with its capital structure held
    fixed: the down-payment FRACTION (not the dollar amount) stays constant,
    so a pricier unit means a proportionally bigger loan, not a silently
    smaller down payment. Fees/events/other costs do not scale with price
    (they attach to the building and its components, not the listing).
    """
    updates: Dict[str, float] = {"initial_value": price}
    if (
        not params.all_cash
        and params.down_payment is not None
        and params.initial_value > 0
    ):
        fraction = params.down_payment / params.initial_value
        updates["down_payment"] = price * fraction
    return replace(params, **updates)


def sweep_rent_totals(
    spec: ComparisonSpec, monthly_rents: Sequence[float],
) -> Dict[str, List[float]]:
    """
    Total deterministic PV per option across a grid of monthly rents (owned
    options do not move; the rent line rises with the rent). The renter's
    invested_down_payment is deliberately held fixed: it is the capital tied
    to the buy side's down payment, not to the rent level.
    """
    totals: Dict[str, List[float]] = {
        k: [] for k in ("rent", "condo", "house")
        if getattr(spec, k) is not None
    }
    for monthly in monthly_rents:
        swept = replace(spec, rent=replace(spec.rent, monthly_rent=float(monthly)))
        det = compute_deterministic(swept)
        for key in totals:
            totals[key].append(getattr(det, key).total_pv)
    return totals


def sweep_price_totals(
    spec: ComparisonSpec, owned_key: str, prices: Sequence[float],
) -> Dict[str, List[float]]:
    """
    Total deterministic PV per option across a grid of purchase prices for
    ``owned_key`` ("condo" or "house"). The swept option moves; every other
    option (rent, the other dwelling) stays at the user's quoted values.
    """
    totals: Dict[str, List[float]] = {
        k: [] for k in ("rent", "condo", "house") if getattr(spec, k) is not None
    }
    base_owned = getattr(spec, owned_key)
    for price in prices:
        swept = replace(
            spec, **{owned_key: _owned_at_price(base_owned, float(price))},
        )
        det = compute_deterministic(swept)
        for key in totals:
            totals[key].append(getattr(det, key).total_pv)
    return totals


def find_break_evens(
    xs: Sequence[float], ya: Sequence[float], yb: Sequence[float],
) -> List[float]:
    """
    X positions where the cheaper of two total-PV series flips, with the
    crossing linearly interpolated between the bracketing grid points.
    Monotonic or not: every sign change of (ya - yb) is one break-even.
    """
    break_evens: List[float] = []
    for i in range(1, len(xs)):
        d0, d1 = ya[i - 1] - yb[i - 1], ya[i] - yb[i]
        if d0 == 0.0:
            break_evens.append(float(xs[i - 1]))
        elif d0 * d1 < 0:
            t = d0 / (d0 - d1)
            break_evens.append(float(xs[i - 1] + t * (xs[i] - xs[i - 1])))
    if ya[-1] == yb[-1]:
        break_evens.append(float(xs[-1]))
    return break_evens


def cheapest_owned_key(spec: ComparisonSpec, det: ComparisonDeterministicResult) -> str:
    """The decision-relevant buy-side competitor to rent (lowest total PV)."""
    keys = [k for k in ("condo", "house") if getattr(spec, k) is not None]
    return min(keys, key=lambda k: getattr(det, k).total_pv)


def market_line_sentence(spec: ComparisonSpec, det: ComparisonDeterministicResult) -> str:
    """
    Act 6 narrative, as words: where the user's rent sits against the
    break-even rent vs the cheapest owned option.
    """
    owned_key = cheapest_owned_key(spec, det)
    user_rent = spec.rent.monthly_rent
    xs = _sweep_axis(user_rent)
    totals = sweep_rent_totals(spec, xs)
    break_evens = find_break_evens(xs, totals["rent"], totals[owned_key])
    lo, hi = xs[0], xs[-1]
    if break_evens:
        be = break_evens[0]
        if user_rent < be:
            return (
                f"Renting stays cheaper than buying a "
                f"{OPTION_DISPLAY[owned_key].lower().removeprefix('buying a ')} "
                f"until rent passes ${be:,.0f}/mo — your ${user_rent:,.0f} is "
                f"${be - user_rent:,.0f}/mo below that line."
            )
        return (
            f"Rent is past the break-even: ${user_rent:,.0f}/mo quoted vs a "
            f"${be:,.0f}/mo flip point — buying the cheaper option already wins "
            f"at these rent levels."
        )
    if totals["rent"][-1] < totals[owned_key][-1]:
        return (
            f"Renting is cheaper across the whole swept range "
            f"(${lo:,.0f}–${hi:,.0f}/mo) — the flip point sits above it."
        )
    return (
        f"Buying the cheaper owned option wins across the whole swept rent "
        f"range (${lo:,.0f}–${hi:,.0f}/mo) — renting does not catch up."
    )


# ---------------------------------------------------------------------------
# Acts
# ---------------------------------------------------------------------------

def plot_act1_the_answer(
    spec: ComparisonSpec,
    det: ComparisonDeterministicResult,
    mc: Optional[ComparisonMonteCarloResult],
    fmt: str,
    out_dir: Path,
) -> Path:
    """Headline bar chart: total PV cost per option, cheapest highlighted."""
    fig, ax = _new_figure()
    keys = [k for k, o in (("rent", det.rent), ("condo", det.condo), ("house", det.house)) if o is not None]
    totals = [getattr(det, k).total_pv for k in keys]
    cheapest = min(range(len(keys)), key=lambda i: totals[i])

    colors = [OPTION_COLORS[k] for k in keys]
    alphas = [1.0 if i == cheapest else 0.45 for i in range(len(keys))]
    for i, (k, total) in enumerate(zip(keys, totals)):
        ax.bar(i, total, color=colors[i], alpha=alphas[i], width=0.62)

    # Error bars from MC percentiles when the arrays are available.
    if mc is not None:
        for i, k in enumerate(keys):
            opt = getattr(mc, k)
            if opt is None or opt.pvs is None or len(opt.pvs) == 0:
                continue
            p10, p50, p90 = (float(np.percentile(opt.pvs, q)) for q in (10, 50, 90))
            ax.errorbar(
                i, p50,
                yerr=[[max(0.0, p50 - p10)], [max(0.0, p90 - p50)]],
                fmt="none", ecolor="#333333", elinewidth=2, capsize=7,
            )

    # Value labels straight on the bars — no legend-hunting.
    for i, total in enumerate(totals):
        marker = "  ✓ cheapest" if i == cheapest else ""
        ax.annotate(
            f"${total / 1000:,.0f}k{marker}",
            xy=(i, total), xytext=(0, 8), textcoords="offset points",
            ha="center", fontsize=13,
            fontweight="bold" if i == cheapest else "normal",
        )

    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([OPTION_DISPLAY[k] for k in keys])
    ax.set_ylabel("Total cost, present value")
    ax.set_title(verdict_sentence(det, spec.simulation.years), pad=24)
    ax.text(
        0.0, 1.01, _verdict_subtitle(spec),
        transform=ax.transAxes, fontsize=12, color="#555555", va="bottom",
    )
    if mc is not None:
        ax.text(
            0.99, 0.97, "whiskers: middle 80% of simulations (p10–p90)",
            transform=ax.transAxes, fontsize=10.5, color="#555555",
            ha="right", va="top",
        )
    if mc is not None and single_path_run(spec):
        # Audit U3: MC ran but every uncertainty input is off — stamp the
        # headline act so the zero-width whiskers are not misread as certainty.
        ax.text(
            0.5, -0.12,
            "single-path run: all uncertainty inputs off — not a forecast",
            transform=ax.transAxes, fontsize=11, color="#555555", ha="center",
        )
    _set_money_axis(ax)
    fig.tight_layout()
    return _save(fig, out_dir, "act1_the_answer", fmt)


def plot_act2_the_race(
    spec: ComparisonSpec,
    curves: Dict[str, Dict[str, List[float]]],
    fmt: str,
    out_dir: Path,
) -> Path:
    """
    The race: cumulative out-of-pocket cost curves, crossover year(s) called
    out, and the end-of-horizon equity credit shown as a dashed drop to the
    net total (so the line never tells a false "costs went down" story).
    """
    fig, ax = _new_figure()
    n = spec.simulation.years
    years = list(range(0, n + 1))
    paid_curves = {k: c["paid"] for k, c in curves.items()}
    net_leader = min(curves, key=lambda k: curves[k]["net"][-1])
    for key, curve in curves.items():
        paid = curve["paid"]
        ax.plot(
            years, paid, color=OPTION_COLORS[key],
            linewidth=3.0 if key == net_leader else 2.2,
            label=f"{OPTION_DISPLAY[key]} (net ${curve['net'][-1] / 1000:,.0f}k)",
        )
        credit = paid[-1] - curve["net"][-1]
        if abs(credit) > 1.0:
            credit_label = (
                "down payment kept invested" if key == "rent"
                else "equity returned at sale"
            )
            ax.plot(
                [n, n], [paid[-1], curve["net"][-1]], color=OPTION_COLORS[key],
                linestyle=":", linewidth=2.0, marker="o", markersize=5,
            )
            ax.annotate(
                f"−${credit / 1000:,.0f}k {credit_label}",
                xy=(n, curve["net"][-1]), xytext=(-8, -4),
                textcoords="offset points", fontsize=10.5,
                color=OPTION_COLORS[key], ha="right", va="top",
            )

    crossovers = find_crossovers(paid_curves)
    if crossovers:
        for year, from_key, to_key in crossovers[:4]:  # keep the chart readable
            ax.axvline(year, color="#888888", linestyle="--", linewidth=1.2)
            ax.annotate(
                f"{OPTION_DISPLAY[to_key]} overtakes\n{OPTION_DISPLAY[from_key]} in year {year}",
                xy=(year, max(paid_curves[k][min(year, n)] for k in paid_curves)),
                xytext=(6, 10), textcoords="offset points",
                fontsize=11, color="#333333",
            )
        first_to = OPTION_DISPLAY[crossovers[0][2]]
        ax.set_title(f"The lead changes hands — {first_to} pulls ahead", pad=24)
    else:
        paid_leader = min(paid_curves, key=lambda k: paid_curves[k][-1])
        ax.set_title(
            f"No crossover — {OPTION_DISPLAY[paid_leader]} costs less every single year",
            pad=24,
        )
    ax.text(
        0.0, 1.01,
        f"running total of what you pay out of pocket, discounted to today · "
        f"{spec.simulation.discount_rate:.0%} discount rate · dotted drop: "
        f"value you keep at the end",
        transform=ax.transAxes, fontsize=12, color="#555555", va="bottom",
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative cost, present value")
    ax.set_xlim(0, n)
    ax.legend(loc="upper left", frameon=False)
    _set_money_axis(ax)
    fig.tight_layout()
    return _save(fig, out_dir, "act2_the_race", fmt)


def plot_act3_the_uncertainty(
    spec: ComparisonSpec,
    mc: ComparisonMonteCarloResult,
    fmt: str,
    out_dir: Path,
) -> Path:
    """Overlaid MC net-cost distributions with median + p10/p90 annotated."""
    fig, ax = _new_figure()
    options = [
        (k, getattr(mc, k))
        for k in ("rent", "condo", "house")
        if getattr(mc, k) is not None
    ]
    for key, opt in options:
        arr = np.asarray(opt.pvs, dtype=float)
        p10, p50, p90 = (float(np.percentile(arr, q)) for q in (10, 50, 90))
        ax.hist(
            arr, bins=40, alpha=0.5, color=OPTION_COLORS[key],
            edgecolor="white", label=OPTION_DISPLAY[key], density=True,
        )
        ax.axvline(p50, color=OPTION_COLORS[key], linewidth=2.4)
        ax.annotate(
            f"median ${p50 / 1000:,.0f}k",
            xy=(p50, ax.get_ylim()[1]), xytext=(4, -4),
            textcoords="offset points", rotation=90,
            fontsize=11, color=OPTION_COLORS[key], va="top",
        )
        ax.annotate(
            f"p10 ${p10 / 1000:,.0f}k",
            xy=(p10, 0), xytext=(-4, 12), textcoords="offset points",
            rotation=90, fontsize=10, color=OPTION_COLORS[key], ha="right",
        )
        ax.annotate(
            f"p90 ${p90 / 1000:,.0f}k",
            xy=(p90, 0), xytext=(4, 12), textcoords="offset points",
            rotation=90, fontsize=10, color=OPTION_COLORS[key],
        )

    probs = [
        (key, getattr(mc, f"prob_{key}_cheapest"))
        for key in ("rent", "condo", "house") if getattr(mc, f"prob_{key}_cheapest") is not None
    ]
    if probs:
        best_key, best_prob = max(probs, key=lambda kv: kv[1])
        subtitle = (
            f"in {best_prob:.0%} of {spec.simulation.num_sims:,} simulations, "
            f"{OPTION_DISPLAY[best_key].lower()} came out cheapest"
        )
    else:
        subtitle = f"{spec.simulation.num_sims:,} simulations of your assumptions"
    ax.set_title("How sure are we? It depends on the future", pad=24)
    ax.text(0.0, 1.01, subtitle, transform=ax.transAxes, fontsize=12,
            color="#555555", va="bottom")
    ax.set_xlabel("Total cost, present value")
    ax.set_ylabel("Share of simulations")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: _money_k(x)))
    ax.legend(loc="upper right", frameon=False)
    fig.tight_layout()
    return _save(fig, out_dir, "act3_the_uncertainty", fmt)


def _home_value_path(
    initial_value: float,
    user_growth: float,
    rows: Dict[tuple[int, str], object],
    scenario: str,
    quantile_attr: str,
    years: int,
) -> List[float]:
    """
    Home-value path compounding the user's growth plus the prior's piecewise-
    constant demographic drift (same banding rule monte_carlo applies),
    reading the requested quantile off each band row.
    """
    value = initial_value
    path = [value]
    for t in range(1, years + 1):
        horizon = band_horizon_for_calendar_year(calendar_year_for_sim_year(t))
        row = rows[(horizon, scenario)]
        drift = getattr(row, quantile_attr)
        value *= (1 + user_growth + drift)
        path.append(value)
    return path


def plot_act4_home_futures(
    spec: ComparisonSpec,
    prior: Optional[LoadedScenarioPrior],
    fmt: str,
    out_dir: Path,
) -> Path:
    """Fan chart of home value paths under the prior (or the honest fallback)."""
    dwelling_key = "house" if spec.house is not None else "condo"
    params = getattr(spec, dwelling_key)
    assert params is not None, "act 4 requires an owned option"
    years = spec.simulation.years
    year_axis = list(range(0, years + 1))

    fig, ax = _new_figure()

    if prior is not None:
        rows = prior.rows_for_dwelling(dwelling_key)
        for scenario in ("low", "reference", "high"):
            mean_path = _home_value_path(
                params.initial_value, params.value_growth_rate, rows,
                scenario, "demo_drift_mean", years,
            )
            p10_path = _home_value_path(
                params.initial_value, params.value_growth_rate, rows,
                scenario, "demo_drift_p10", years,
            )
            p90_path = _home_value_path(
                params.initial_value, params.value_growth_rate, rows,
                scenario, "demo_drift_p90", years,
            )
            color = SCENARIO_COLORS[scenario]
            ax.fill_between(year_axis, p10_path, p90_path, color=color, alpha=0.18)
            ax.plot(
                year_axis, mean_path, color=color, linewidth=2.4,
                label=f"{scenario} scenario (${mean_path[-1] / 1000:,.0f}k)",
            )
        title = "Where could your home's value go?"
        subtitle = (
            f"demographic demand scenarios for {prior.geography}, on top of your "
            f"{params.value_growth_rate:.1%} growth assumption · shaded: p10–p90"
        )

        shock = params.price_shock
        if shock is not None and shock.annual_hazard > 0:
            ref_rows = rows
            # Expected timing of the first drawdown under the reference tilts.
            surv = 1.0
            exp_t = 0.0
            for t in range(1, years + 1):
                horizon = band_horizon_for_calendar_year(calendar_year_for_sim_year(t))
                tilt = ref_rows[(horizon, "reference")].drawdown_weight_tilt
                hazard = min(max(shock.annual_hazard * tilt, 0.0), 1.0)
                exp_t += t * hazard * surv
                surv *= (1 - hazard)
            crash_year = int(round(exp_t)) if exp_t > 0 else None
            if crash_year is not None and 1 <= crash_year <= years:
                base = _home_value_path(
                    params.initial_value, params.value_growth_rate, ref_rows,
                    "reference", "demo_drift_mean", years,
                )
                shocked = [
                    v * (1 - shock.severity_mean) if t >= crash_year else v
                    for t, v in enumerate(base)
                ]
                ax.plot(
                    year_axis, shocked, color="#444444", linestyle=":",
                    linewidth=2.0,
                    label=(
                        f"after one typical crash "
                        f"(−{shock.severity_mean:.0%}, ~year {crash_year})"
                    ),
                )
    else:
        line = [params.initial_value * (1 + params.value_growth_rate) ** t
                for t in range(years + 1)]
        ax.plot(year_axis, line, color=OPTION_COLORS[dwelling_key], linewidth=2.4,
                label=f"your assumption (${line[-1] / 1000:,.0f}k)")
        title = "Your home's value under a single growth assumption"
        subtitle = "no demographic prior loaded — single growth assumption"

    ax.set_title(title, pad=24)
    ax.text(0.0, 1.01, subtitle, transform=ax.transAxes, fontsize=12,
            color="#555555", va="bottom")
    ax.set_xlabel("Year from now")
    ax.set_ylabel("Home value")
    ax.set_xlim(0, years)
    ax.legend(loc="upper left", frameon=False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: _money_k(x)))
    fig.tight_layout()
    return _save(fig, out_dir, "act4_home_futures", fmt)


def plot_act5_demographic_signal(
    spec: ComparisonSpec,
    prior: LoadedScenarioPrior,
    fmt: str,
    out_dir: Path,
) -> Path:
    """The trust-building plot: the demographic drift prior itself."""
    fig, ax = _new_figure()
    horizons = sorted({h for (_, h, _) in prior.rows})
    for scenario in ("low", "reference", "high"):
        means, p10s, p90s = [], [], []
        for h in horizons:
            row = prior.rows[(next(iter(k for k in prior.rows if k[1] == h and k[2] == scenario)))]
            means.append(row.demo_drift_mean)
            p10s.append(row.demo_drift_p10)
            p90s.append(row.demo_drift_p90)
        color = SCENARIO_COLORS[scenario]
        ax.fill_between(horizons, p10s, p90s, color=color, alpha=0.18)
        ax.plot(horizons, means, color=color, linewidth=2.4, marker="o",
                label=f"{scenario}")
        ax.annotate(
            f"{means[-1] * 100:+.2f}%/yr",
            xy=(horizons[-1], means[-1]), xytext=(8, 0),
            textcoords="offset points", fontsize=11, color=color, va="center",
        )

    ax.set_title("Why: what demography says about demand", pad=24)
    ax.text(
        0.0, 1.01,
        f"projected price drift from household demand, {prior.geography} · "
        f"added on top of your own assumptions · shaded: p10–p90",
        transform=ax.transAxes, fontsize=12, color="#555555", va="bottom",
    )
    ax.text(
        0.99, 0.03, PRIOR_SOURCE_LINE, transform=ax.transAxes,
        fontsize=10, color="#777777", ha="right", va="bottom",
    )
    ax.set_xlabel("Horizon year")
    ax.set_ylabel("Annual real price drift")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y * 100:+.1f}%"))
    ax.set_xticks(horizons)
    ax.legend(title="ISQ scenario", loc="upper left", frameon=False)
    fig.tight_layout()
    return _save(fig, out_dir, "act5_demographic_signal", fmt)


def plot_act6_the_market_line(
    spec: ComparisonSpec,
    det: ComparisonDeterministicResult,
    fmt: str,
    out_dir: Path,
) -> Path:
    """
    The market line: total cost vs the quoted amounts.

    Left panel sweeps the monthly rent (owned lines flat, rent line rising);
    right panel sweeps the purchase price of the cheapest owned option with
    its down-payment fraction held constant (rent flat at the user's quote).
    Break-even points — where the verdict flips — are annotated directly, and
    the user's actual quotes are marked so the distance to the flip point is
    readable at a glance. Deterministic sweep; the uncertainty act (3) carries
    the spread.
    """
    if spec.rent is None:
        raise ValueError("act 6 requires the rent option")
    if spec.condo is None and spec.house is None:
        raise ValueError("act 6 requires an owned option")

    user_rent = spec.rent.monthly_rent
    swept_key = cheapest_owned_key(spec, det)
    user_price = getattr(spec, swept_key).initial_value

    plt.rcParams.update(_RC)
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(15.5, 6.5), sharey=True)

    def _plot_totals(ax: Axes, xs: List[float], totals: Dict[str, List[float]],
                     leader_key: str) -> None:
        for key, ys in totals.items():
            ax.plot(
                xs, ys, color=OPTION_COLORS[key],
                linewidth=3.0 if key == leader_key else 2.2,
                label=OPTION_DISPLAY[key],
            )

    # --- Left panel: verdict vs the rent you'd pay ---
    rent_xs = _sweep_axis(user_rent)
    rent_totals = sweep_rent_totals(spec, rent_xs)
    rent_leader = min(rent_totals, key=lambda k: rent_totals[k][len(rent_xs) // 2])
    _plot_totals(ax_l, rent_xs, rent_totals, rent_leader)
    ax_l.axvline(user_rent, color="#666666", linestyle="--", linewidth=1.6)
    ax_l.annotate(
        f"your rent: ${user_rent:,.0f}/mo",
        xy=(user_rent, ax_l.get_ylim()[1]), xytext=(4, -2),
        textcoords="offset points", fontsize=11, color="#444444",
        ha="left", va="top",
    )
    for owned_key in [k for k in ("condo", "house") if k in rent_totals]:
        for be in find_break_evens(rent_xs, rent_totals["rent"], rent_totals[owned_key])[:2]:
            # At the break-even both series are equal; interpolate either one.
            y_at = float(np.interp(be, rent_xs, rent_totals["rent"]))
            ax_l.plot(be, y_at, marker="o", color="#333333", markersize=7, zorder=5)
            ax_l.annotate(
                f"${be:,.0f}/mo — the verdict flips\n"
                f"vs {OPTION_DISPLAY[owned_key].lower()}",
                xy=(be, y_at), xytext=(6, 14), textcoords="offset points",
                fontsize=11, color="#333333", fontweight="bold",
            )
    ax_l.set_xlabel("Monthly rent")
    ax_l.set_title("vs the rent you'd pay", fontsize=14)
    ax_l.legend(loc="lower right", frameon=False)
    ax_l.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # --- Right panel: verdict vs the price you'd pay ---
    price_xs = _sweep_axis(user_price)
    price_totals = sweep_price_totals(spec, swept_key, price_xs)
    det_totals = {
        k: getattr(det, k).total_pv
        for k in ("rent", "condo", "house") if getattr(det, k) is not None
    }
    flat_keys = [k for k in price_totals if k != swept_key]
    for key in flat_keys:
        price_totals[key] = [det_totals[key]] * len(price_xs)
    price_leader = min(price_totals, key=lambda k: price_totals[k][len(price_xs) // 2])
    _plot_totals(ax_r, price_xs, price_totals, price_leader)
    ax_r.axvline(user_price, color="#666666", linestyle="--", linewidth=1.6)
    ax_r.annotate(
        f"your price: {_money_k(user_price)}",
        xy=(user_price, ax_r.get_ylim()[1]), xytext=(4, -2),
        textcoords="offset points", fontsize=11, color="#444444",
        ha="left", va="top",
    )
    for be in find_break_evens(price_xs, price_totals["rent"], price_totals[swept_key])[:2]:
        y_at = np.interp(be, price_xs, price_totals[swept_key])
        ax_r.plot(be, y_at, marker="o", color="#333333", markersize=7, zorder=5)
        ax_r.annotate(
            f"{_money_k(be)} — the verdict flips\n"
            f"vs {OPTION_DISPLAY[swept_key].lower()}",
            xy=(be, y_at), xytext=(6, 14), textcoords="offset points",
            fontsize=11, color="#333333", fontweight="bold",
        )
    ax_r.set_xlabel(f"Purchase price — {OPTION_DISPLAY[swept_key].lower()}")
    ax_r.set_title("vs the price you'd pay", fontsize=14)
    ax_r.legend(loc="lower right", frameon=False)
    ax_r.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: _money_k(x)))

    _set_money_axis(ax_l)
    fig.suptitle(
        "The market line: how much room before the verdict flips?",
        fontsize=17, fontweight="bold", y=1.02,
    )
    fig.text(
        0.0, 1.005,
        f"total cost vs the quoted amounts · deterministic sweep ±"
        f"{SWEEP_SPAN:.0%}, your other assumptions held fixed",
        fontsize=12, color="#555555",
    )
    fig.tight_layout()
    return _save(fig, out_dir, "act6_the_market_line", fmt)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def render_decision_story(
    spec: ComparisonSpec,
    deterministic_result: ComparisonDeterministicResult,
    mc_summary: Optional[ComparisonMonteCarloResult],
    prior: Optional[LoadedScenarioPrior] = None,
    out_dir: str | Path = "story_plots",
    fmt: str = "png",
) -> list[Path]:
    """
    Render the six-act decision story into ``out_dir``; returns only the acts
    actually rendered (Act 3 needs MC results, Act 5 needs a loaded prior,
    Act 6 needs rent + an owned option; Act 4 degrades to an honestly-labelled
    single-growth line without a prior).
    """
    if deterministic_result is None:
        raise ValueError("render_decision_story requires deterministic results")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    rendered: List[Path] = []
    rendered.append(plot_act1_the_answer(spec, deterministic_result, mc_summary, fmt, out_path))
    rendered.append(plot_act2_the_race(spec, _cumulative_cost_curves(spec), fmt, out_path))
    # Audit U3: with every uncertainty input off, MC paths are identical — Act 3
    # would fabricate spread that does not exist, so degrade like the no-MC path.
    if mc_summary is not None and not single_path_run(spec) and any(
        getattr(mc_summary, k) is not None for k in ("rent", "condo", "house")
    ):
        rendered.append(plot_act3_the_uncertainty(spec, mc_summary, fmt, out_path))
    owned_present = spec.house is not None or spec.condo is not None
    if owned_present:
        rendered.append(plot_act4_home_futures(spec, prior, fmt, out_path))
    if prior is not None:
        rendered.append(plot_act5_demographic_signal(spec, prior, fmt, out_path))
    if spec.rent is not None and owned_present:
        rendered.append(plot_act6_the_market_line(spec, deterministic_result, fmt, out_path))
    return rendered
