"""
Reporting and visualization utilities.

This module provides functions for generating text reports and
plots from the analysis results.
"""

from typing import Dict, List, Optional

import numpy as np
import numpy.typing as npt
import matplotlib.pyplot as plt
import matplotlib.figure
from matplotlib.figure import Figure

from .config import single_path_run
from .market_scenario import LoadedScenarioPrior
from .models import (
    compute_verdict,
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    ComparisonSpec,
    AffordabilityReport,
    OptionResult,
    SimulationParams,
    EconomicParams,
)
from .pv import pv_to_monthly_savings
# The assumption echo lives in the typed serialization core (readiness plan
# A.1); re-exported here so existing callers keep importing from reporting.
from .serialization import echo_value as _echo_value, format_assumptions  # noqa: F401


_LABEL = {"condo": "Condo", "house": "House", "rent": "Rent"}


def format_text_report(
    det: ComparisonDeterministicResult,
    mc: Optional[ComparisonMonteCarloResult],
    sim: SimulationParams,
    econ: EconomicParams,
    spec: Optional[ComparisonSpec] = None,
    prior: Optional["LoadedScenarioPrior"] = None,
) -> str:
    """
    Generate a formatted text report of the analysis results.

    Args:
        det: Deterministic comparison results
        mc: Monte Carlo comparison results (optional)
        sim: Simulation parameters
        econ: Economic parameters
        spec: Full ComparisonSpec (optional) — emits the assumption echo
            header (audit U1) when provided

    Returns:
        Formatted string report
    """
    lines = []

    if spec is not None:
        lines.append("Assumptions")
        lines.extend(f"  {line}" for line in format_assumptions(spec, prior))
        lines.append("")

    # Per-option PV totals
    if det.condo is not None:
        lines.append(f"Condo  total PV:  ${det.condo.total_pv:>12,.0f}")
        for k, v in det.condo.breakdown.items():
            lines.append(f"  {k}: ${v:>12,.0f}")
    if det.house is not None:
        lines.append(f"House  total PV:  ${det.house.total_pv:>12,.0f}")
        for k, v in det.house.breakdown.items():
            lines.append(f"  {k}: ${v:>12,.0f}")
    if det.rent is not None:
        lines.append(f"Rent   total PV:  ${det.rent.total_pv:>12,.0f}")
        for k, v in det.rent.breakdown.items():
            lines.append(f"  {k}: ${v:>12,.0f}")

    # Year-1 cash, undiscounted — what leaves the account, as opposed to the
    # PV totals above (round-four dogfood: the $/month PV equivalent was read
    # as out-of-pocket and had the wrong sign for that reading).
    cash_lines = []
    for name, r in (("Condo", det.condo), ("House", det.house), ("Rent", det.rent)):
        if r is None or r.cash_year1 is None:
            continue
        line = f"  {name}: ${r.cash_year1:>10,.0f}/yr (${r.cash_year1 / 12:,.0f}/mo)"
        if r.principal_year1:
            line += f" — of which ${r.principal_year1:,.0f} principal repaid; the rest is unrecoverable"
        cash_lines.append(line)
    if cash_lines:
        lines.append("Year-1 cash (undiscounted; PV totals above credit equity at sale)")
        lines.extend(cash_lines)

    # Verdict (readiness plan B.4): the SAME computation the story headline
    # and --json use — runner-up margin, decisiveness rule stated in words.
    single_path = spec is not None and single_path_run(spec)
    verdict = compute_verdict(
        det, mc, years=sim.years, discount_rate=sim.discount_rate,
        single_path=single_path,
    )
    if verdict is not None and verdict.runner_up is not None:
        best, runner = _LABEL[verdict.best], _LABEL[verdict.runner_up]
        if verdict.decisive:
            lines.append(
                f"\nCheapest: {best} saves ${verdict.margin_pv:,.0f} vs {runner} (runner-up)"
            )
        else:
            lines.append(
                f"\nToo close to call: {best} edges {runner} by "
                f"${verdict.margin_pv:,.0f} ({verdict.margin_frac:.1%})"
            )
        if verdict.monthly_equivalent is not None:
            lines.append(f"  ≈ ${verdict.monthly_equivalent:,.0f}/month equivalent")
        lines.append(f"  decisiveness: {verdict.reason}")

    # Affordability
    if det.income_report is not None:
        rpt = det.income_report
        lines.append(f"\nAffordability (threshold: {rpt.threshold:.0%})")
        for name, ratios, exceeds in [
            ("Rent",  rpt.rent_ratios,  rpt.years_rent_exceeds),
            ("Condo", rpt.condo_ratios, rpt.years_condo_exceeds),
            ("House", rpt.house_ratios, rpt.years_house_exceeds),
        ]:
            if ratios is not None:
                max_ratio = max(ratios)
                exceed_str = str(exceeds) if exceeds else "none"
                lines.append(f"  {name}: max ratio {max_ratio:.1%}  years exceeding: {exceed_str}")

    # MC summary — a single-path run (every uncertainty input off) is stamped
    # 'not a forecast' and its degenerate 100% probabilities are not printed
    # (audit U3; readiness plan B.4 — the story surface already did this).
    if mc is not None:
        if single_path:
            lines.append("\nMonte Carlo: single-path run: all uncertainty inputs off — not a forecast")
            return "\n".join(lines)
        lines.append("\nMonte Carlo:")
        for name, opt in [("Condo", mc.condo), ("House", mc.house), ("Rent", mc.rent)]:
            if opt is not None:
                s = opt.summary
                lines.append(
                    f"  {name}: mean ${s.mean:,.0f}  p5 ${s.p5:,.0f}"
                    f"  p50 ${s.p50:,.0f}  p95 ${s.p95:,.0f}"
                )
        probs = [
            (name, prob)
            for name, prob in [
                ("P(condo cheapest)", mc.prob_condo_cheapest),
                ("P(house cheapest)", mc.prob_house_cheapest),
                ("P(rent cheapest)",  mc.prob_rent_cheapest),
            ]
            if prob is not None
        ]
        for label, prob in probs:
            lines.append(f"  {label}: {prob:.1%}")
        if mc.affordability_mc is not None:
            a = mc.affordability_mc
            lines.append(f"  Affordability MC (threshold {a.threshold:.0%}):")
            for name, prob in [
                ("condo", a.prob_condo_exceeds),
                ("house", a.prob_house_exceeds),
                ("rent",  a.prob_rent_exceeds),
            ]:
                if prob is not None:
                    lines.append(f"    P({name} exceeds threshold): {prob:.1%}")

    return "\n".join(lines)


def plot_diff_distribution(
    diff_pvs: npt.NDArray[np.float64],
    title: str = "Diff Distribution (House − Condo PV)",
    bins: int = 50,
    figsize: tuple = (10, 6),
) -> Figure:
    """
    Plot a histogram of a cost-difference distribution.

    Args:
        diff_pvs: Pre-computed array of PV differences (e.g. house_pv - condo_pv)
        title: Plot title
        bins: Number of histogram bins
        figsize: Figure size (width, height) in inches

    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Summary stats
    mean_val = float(np.mean(diff_pvs))
    p5_val   = float(np.percentile(diff_pvs, 5))
    p95_val  = float(np.percentile(diff_pvs, 95))
    prob_positive = float(np.mean(diff_pvs > 0))

    # Plot histogram
    ax.hist(diff_pvs, bins=bins, edgecolor='black', alpha=0.7, color='steelblue')

    # Add vertical line at zero (break-even)
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even (costs equal)')

    # Add vertical line at mean
    ax.axvline(x=mean_val, color='green', linestyle='-', linewidth=2,
               label=f'Mean: ${mean_val:,.0f}')

    # Add vertical lines for percentiles
    ax.axvline(x=p5_val, color='orange', linestyle=':', linewidth=1.5,
               label=f'5th %: ${p5_val:,.0f}')
    ax.axvline(x=p95_val, color='orange', linestyle=':', linewidth=1.5,
               label=f'95th %: ${p95_val:,.0f}')

    ax.set_xlabel('Cost Difference [$]')
    ax.set_ylabel('Frequency')
    ax.set_title(title)
    ax.legend(loc='upper right')

    # Format x-axis with dollar amounts
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

    # Add annotation for probability
    prob_text = f'P(positive) = {prob_positive:.1%}'
    ax.annotate(prob_text, xy=(0.02, 0.98), xycoords='axes fraction',
                fontsize=11, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=1.0))

    # Add explanatory note
    note_text = 'Positive = first option more expensive\nNegative = second option more expensive'
    ax.annotate(note_text, xy=(0.02, 0.88), xycoords='axes fraction',
                fontsize=9, verticalalignment='top', color='gray')

    plt.tight_layout()
    return fig


def plot_pv_distributions(
    option_arrays: Dict[str, npt.NDArray[np.float64]],
    title: str = "PV Distributions by Option",
    bins: int = 50,
    figsize: tuple = (10, 6),
) -> Figure:
    """
    Plot overlapping histograms of PV distributions for multiple housing options.

    Args:
        option_arrays: Dict mapping option name (e.g. "Condo", "House", "Rent") to
                       its array of simulated PV values.
        title: Plot title
        bins: Number of histogram bins
        figsize: Figure size (width, height) in inches

    Returns:
        matplotlib Figure object
    """
    colors = ['royalblue', 'forestgreen', 'darkorange', 'purple', 'crimson']
    fig, ax = plt.subplots(figsize=figsize)

    for (name, arr), color in zip(option_arrays.items(), colors):
        mean_val = float(np.mean(arr))
        ax.hist(arr, bins=bins, edgecolor='black', alpha=0.5, color=color,
                label=f'{name} (mean ${mean_val/1000:.0f}k)')
        ax.axvline(x=mean_val, color=color, linestyle='-', linewidth=2)

    ax.set_xlabel('Ownership Cost PV [$]')
    ax.set_ylabel('Frequency')
    ax.set_title(title + '\n(Higher PV = More Expensive)')
    ax.legend()
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x/1000:.0f}k'))

    plt.tight_layout()
    return fig


def plot_sensitivity(
    param_values: list[float],
    probabilities: list[float],
    param_name: str = "Parameter",
    title: str = "Sensitivity Analysis",
    figsize: tuple[float, float] = (8, 5),
) -> matplotlib.figure.Figure:
    """
    Plot sensitivity of P(House costs more) to a parameter.

    Args:
        param_values: List of parameter values tested
        probabilities: List of corresponding probabilities
        param_name: Name of the parameter (for x-axis label)
        title: Plot title
        figsize: Figure size

    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)

    ax.plot(param_values, probabilities, marker='o', linewidth=2, markersize=8, color='navy')

    ax.set_xlabel(param_name)
    ax.set_ylabel('P(House ownership costs more)')
    ax.set_title(title)

    # Format y-axis as percentage
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.0%}'))

    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig
