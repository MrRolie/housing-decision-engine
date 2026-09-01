"""Result serialization — THE typed core for agent-facing output.

One source of truth (TOOL-SURFACES doctrine): the CLI's `--json`, the MCP
tools' responses, and any future surface all render from THESE functions, so
CLI-json-vs-MCP-schema drift dies by construction. The functions moved here
verbatim from mcp_server/tools.py (2026-08-26); the MCP layer now imports them.
"""
from __future__ import annotations

from .models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    MonteCarloSummary,
)


def det_to_dict(det: ComparisonDeterministicResult) -> dict:
    def _opt(r):
        if r is None:
            return None
        return {"total_pv": r.total_pv, "breakdown": r.breakdown}

    result = {
        "condo": _opt(det.condo),
        "house": _opt(det.house),
        "rent": _opt(det.rent),
    }
    if det.income_report is not None:
        rpt = det.income_report

        def _opt_afford(ratios, exceeds):
            if ratios is None:
                return None
            return {"ratios": ratios, "years_exceeding": exceeds}

        result["affordability"] = {
            "annual_incomes": rpt.annual_incomes,
            "threshold": rpt.threshold,
            "rent": _opt_afford(rpt.rent_ratios, rpt.years_rent_exceeds),
            "condo": _opt_afford(rpt.condo_ratios, rpt.years_condo_exceeds),
            "house": _opt_afford(rpt.house_ratios, rpt.years_house_exceeds),
        }
    else:
        result["affordability"] = None
    if det.market_scenario is not None:
        result["market_scenario"] = det.market_scenario
    return result


def mc_to_dict(mc: ComparisonMonteCarloResult) -> dict:
    def _s(s: MonteCarloSummary) -> dict:
        return {"mean": s.mean, "std": s.std, "p5": s.p5, "p50": s.p50, "p95": s.p95}

    def _opt(r):
        if r is None:
            return None
        return _s(r.summary)  # pvs arrays NEVER cross a surface boundary

    result = {
        "condo": _opt(mc.condo),
        "house": _opt(mc.house),
        "rent": _opt(mc.rent),
        "prob_condo_cheapest": mc.prob_condo_cheapest,
        "prob_house_cheapest": mc.prob_house_cheapest,
        "prob_rent_cheapest": mc.prob_rent_cheapest,
    }
    if mc.affordability_mc is not None:
        result["affordability_mc"] = {
            "threshold": mc.affordability_mc.threshold,
            "prob_condo_exceeds": mc.affordability_mc.prob_condo_exceeds,
            "prob_house_exceeds": mc.affordability_mc.prob_house_exceeds,
            "prob_rent_exceeds": mc.affordability_mc.prob_rent_exceeds,
        }
    else:
        result["affordability_mc"] = None
    if mc.market_scenario is not None:
        result["market_scenario"] = mc.market_scenario
    return result
