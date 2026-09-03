"""Result + assumption serialization — THE typed core for agent-facing output.

One source of truth: the CLI's `--json` and any future
surface render from THESE functions, so no two surfaces can drift. The result
serializers were lifted from the retired MCP server (2026-08-26; the server
itself was removed 2026-09-01 — the CLI + repo-local skill is the only
surface); the assumption echo moved here from reporting.py (2026-09-01,
readiness plan A.1) so the text report, STORY.md footer and JSON document all
read one function. reporting.py re-exports `format_assumptions` for its callers.

Nothing here imports matplotlib: this module must stay importable by an agent
that only wants numbers.
"""
from __future__ import annotations

import dataclasses
from importlib import metadata
from typing import Any, Dict, List, Optional

from .anchors import ANCHORS, _ECHO_ALIASES, Anchor, match_reference, short_cite
from .market_scenario import LoadedScenarioPrior
from .models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    ComparisonSpec,
    MonteCarloSummary,
    Verdict,
)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def engine_version() -> str:
    """Installed package version, so a stored result records which defaults
    produced it (the anchors registry changes verdicts across versions)."""
    try:
        return metadata.version("housing-decision-engine")
    except metadata.PackageNotFoundError:  # pragma: no cover - source checkout without install
        return "unknown"


# ---------------------------------------------------------------------------
# Anchors (provenance records)
# ---------------------------------------------------------------------------

# Rates _effective_growth_rate composes with inflation in nominal mode (the
# spec keeps the REAL value; the PV engine and affordability numerator compose).
_COMPOSED_AT_COMPUTE = frozenset({
    "value_growth_rate", "fee_escalation_rate", "rent_escalation_rate",
    "investment_return_rate", "income_growth_rate",
})


def anchor_to_dict(anchor: Anchor) -> Dict[str, Any]:
    """Every field of one anchor, JSON-shaped (tuples become lists)."""
    doc = dataclasses.asdict(anchor)
    doc["band"] = list(anchor.band)
    doc["replaces"] = (
        {"value": anchor.replaces[0], "why": anchor.replaces[1]}
        if anchor.replaces is not None else None
    )
    return doc


def anchors_to_dict() -> Dict[str, Dict[str, Any]]:
    """The whole registry — what `hde --print-anchors` prints."""
    return {name: anchor_to_dict(anchor) for name, anchor in ANCHORS.items()}


# ---------------------------------------------------------------------------
# Assumption echo (audit U1) — text lines and the structured form
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Jurisdiction reference match (2026-09-03)
#
# The registry's jurisdiction tables are never applied by the engine, so the
# defaults echo — which cites what the engine SUPPLIED — can never reach them.
# Their trigger is the opposite one: the user supplied a figure, and it happens
# to BE a published figure. Then, and only then, the read-back names the source.
#
# Two lines are deliberately never matched. A rent option's tenant insurance is
# a different product from a homeowner's premium, and a mortgage-insurance line
# is not property insurance at all; borrowing either citation would be a false
# statement of provenance dressed as a helpful one.
# ---------------------------------------------------------------------------

_TAX_WORDS = ("property tax", "property taxes", "municipal tax", "taxe fonci",
              "taxe municipale", "taxes municipales")
_INSURANCE_WORDS = ("insurance", "assurance")
# A line naming one of these is some other product, whatever else it says.
_NOT_HOME_INSURANCE = ("mortgage", "hypothéc", "hypothec", "tenant", "renter", "locataire")
# The Québec school tax is a provincial levy, not the municipal rate.
_NOT_PROPERTY_TAX = ("school", "scolaire", "welcome", "bienvenue", "mutation")


def _cost_family(cost_name: str) -> Optional[str]:
    """Which jurisdiction table a recurring-cost line belongs to, or None.

    Separators are normalised first: the repo's own examples write
    `property_tax` and `home_insurance`, and a matcher that only saw
    "property tax" would silently skip exactly the configs it ships with.
    """
    low = cost_name.lower().replace("_", " ").replace("-", " ")
    if any(word in low for word in _NOT_PROPERTY_TAX):
        return None
    if any(word in low for word in _TAX_WORDS):
        return "property_tax."
    if any(word in low for word in _NOT_HOME_INSURANCE):
        return None
    if any(word in low for word in _INSURANCE_WORDS):
        return "home_insurance."
    return None


def reference_matches(spec: ComparisonSpec) -> List[Dict[str, Any]]:
    """One entry per OWNED-option recurring cost that names a property tax or a
    home-insurance premium, with every jurisdiction anchor whose published
    figure equals it.

    `matches` is empty when nothing published agrees — which is reported, not
    hidden: an unmatched tax line is the honest "no source for this" the answer
    is required to say out loud.
    """
    entries: List[Dict[str, Any]] = []
    for option_name in ("condo", "house"):
        option = getattr(spec, option_name, None)
        if option is None:
            continue
        for cost in option.other_recurring_costs:
            family = _cost_family(cost.name)
            if family is None:
                continue
            if family == "property_tax.":
                implied = (cost.annual_amount / option.initial_value
                           if option.initial_value else None)
                probe = implied
            else:
                implied = None
                probe = cost.annual_amount
            entries.append({
                "option": option_name,
                "cost_name": cost.name,
                "annual_amount": cost.annual_amount,
                "family": family,
                "implied_rate": implied,
                "matches": [anchor_to_dict(a) for a in match_reference(family, probe)],
            })
    return entries


def _reference_line(entry: Dict[str, Any]) -> str:
    """One recurring-cost line for the assumption echo. A citation ALWAYS
    carries the anchor's unit: a municipal rate names the base it is levied
    on, because that base is not the price the user typed."""
    head = f"{entry['cost_name']} ${entry['annual_amount']:,.0f}/yr"
    if entry["implied_rate"] is not None:
        head += f" = {entry['implied_rate']:.3%} of price"
    if not entry["matches"]:
        return f"{head} [no anchor match — hde --print-anchors]"
    cites = " ; ".join(
        f"{m['short_cite']} · {m['unit']}" for m in entry["matches"]
    )
    return f"{head} [{cites}]"


def spec_value(spec: ComparisonSpec, dotted: str) -> Any:
    """Walk a dotted key (any depth, e.g. condo.price_shock.severity_mean)."""
    obj: Any = spec
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def echo_value(spec: ComparisonSpec, dotted: str) -> str:
    """Format one defaults-applied value for the assumption echo (pure presentation)."""
    key = dotted.rsplit(".", 1)[1]
    value = spec_value(spec, dotted)
    if key == "mode":
        return repr(value)
    if key == "invested_down_payment":
        return f"${value:,.0f}"
    return f"{value:.1%}"


def format_assumptions(
    spec: ComparisonSpec, prior: Optional[LoadedScenarioPrior] = None,
) -> List[str]:
    """
    Assumption echo block (audit U1), serialized from the spec — pure presentation.

    Lines: terms mode + discount rate, per-option growth/escalation (with
    selling-cost rate for owned options, invested capital + return for rent),
    and a 'defaults applied' list for any echoed assumption the user YAML did
    not provide (spec.defaults_applied, populated by the config loader). Each
    defaulted key carries its anchor's short citation tag (anchors.py) so the
    consumer can ask "where did this number come from?" and get an answer;
    a reference-only anchor renders as `[ref: …]` because the source informs
    the value without stating it.
    """
    nominal = spec.economic.mode == "nominal"
    pi = spec.economic.inflation_rate

    def _g(rate: float) -> str:
        """A growth/escalation input, with its effective composed rate in
        nominal mode so a sticker rate typed into nominal mode is visible
        as the double count it is (2026-09-02 dogfood: the echo printed the
        raw rate and every nominal-thinking user was inflated twice)."""
        if not nominal:
            return f"{rate:+.1%}/yr"
        eff = (1 + rate) * (1 + pi) - 1
        return f"{rate:+.1%}/yr real → {eff:+.1%}/yr nominal (incl. {pi:.1%} inflation)"

    dr_note = ""
    if nominal and "simulation.discount_rate" in spec.defaults_applied:
        dr_note = (f" ({ANCHORS['simulation.discount_rate'].value:.1%} real default composed "
                   f"with inflation_rate)")
    lines = [
        f"mode: {spec.economic.mode} terms · discount_rate {spec.simulation.discount_rate:.1%}{dr_note}"
        + (" (growth, escalation and investment-return inputs are REAL and composed with "
           "inflation_rate; discount_rate and mortgage_rate are used as entered)" if nominal else "")
    ]
    if spec.condo is not None:
        lines.append(
            f"condo: value growth {_g(spec.condo.value_growth_rate)} · "
            f"fee escalation {_g(spec.condo.fee_escalation_rate)} · "
            f"selling_cost_rate {spec.condo.selling_cost_rate:.1%}"
        )
    if spec.house is not None:
        lines.append(
            f"house: value growth {_g(spec.house.value_growth_rate)} · "
            f"maintenance {spec.house.annual_maintenance_rate:.1%} of value/yr · "
            f"selling_cost_rate {spec.house.selling_cost_rate:.1%}"
        )
    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None or opt.all_cash or opt.down_payment is None:
            continue
        # Loan-to-value and the distance to the 20% insurance line (round-6
        # dogfood: every persona computed it by hand and landed $250 over).
        # With cash_available the head shows the netting itself (round-7: the
        # subtraction was done FOR the user, off-engine and unchecked) — the
        # down payment still appears exactly once, as its result.
        down_frac = opt.down_payment / opt.initial_value if opt.initial_value else 0.0
        year0 = opt.down_payment + opt.purchase_costs
        line = 0.20 * opt.initial_value
        gap = opt.down_payment - line
        side = "above" if gap >= 0 else "below"
        # The loan the engine actually finances, financed_purchase_costs and all.
        loan = opt.initial_value - opt.down_payment + opt.financed_purchase_costs
        ltv = loan / opt.initial_value if opt.initial_value else 0.0
        if opt.cash_available is not None:
            head = (f"cash available ${opt.cash_available:,.0f} − purchase_costs "
                    f"${opt.purchase_costs:,.0f} = down payment ${opt.down_payment:,.0f}")
            # year-0 cash IS the pile in this form; naming it twice is noise.
            year0_clause = ""
        else:
            head = f"down payment ${opt.down_payment:,.0f}"
            year0_clause = f" · year-0 cash ${year0:,.0f} (down payment + purchase_costs)"
        lines.append(
            f"{name} financing: {head} = {down_frac:.2%} of price, "
            f"${abs(gap):,.0f} {side} the 20% mortgage-insurance line (${line:,.0f}) · "
            f"loan-to-value {ltv:.2%}"
            + year0_clause
            + (f" · financed_purchase_costs ${opt.financed_purchase_costs:,.0f} on the loan"
               if opt.financed_purchase_costs else "")
        )
    matches = reference_matches(spec)
    for option_name in ("condo", "house"):
        own = [e for e in matches if e["option"] == option_name]
        if own:
            lines.append(
                f"{option_name} other costs: "
                + " · ".join(_reference_line(entry) for entry in own)
            )
    if spec.rent is not None:
        lines.append(
            f"rent: escalation {_g(spec.rent.rent_escalation_rate)} · "
            f"invested capital ${spec.rent.invested_down_payment:,.0f} at "
            f"{_g(spec.rent.investment_return_rate)}"
        )
    lines.append(
        "conventions: end-of-year cash flows discounted at (1+dr)^-t · fees, rent and "
        "other costs escalate before year 1, maintenance from year 1 · mortgage = level "
        "annual payment at an effective annual rate · $/mo equivalent at (1+dr)^(1/12)−1 "
        "(docs/reference/ARCHITECTURE.md figure glossary)"
    )
    if prior is not None:
        constants_as_of = prior.data_vintage.get("constants_as_of")
        as_of = f" · constants as of {constants_as_of}" if isinstance(constants_as_of, str) else ""
        drift = prior.horizon_drift_clause(spec.simulation.years)
        lines.append(
            f"demographic prior: {prior.geography}{prior.vintage_clause()}{as_of} · "
            f"sha256 {prior.file_sha256[:12]}… [demoflow ScenarioPrior v{prior.schema_version}]"
            + (f" · {drift}" if drift else "")
        )
    if spec.defaults_applied:
        def _echo_entry(key: str) -> str:
            cite = short_cite(key)
            tag = f" [{cite}]" if cite else ""
            return f"{key}={echo_value(spec, key)}{tag}"
        joined = ", ".join(_echo_entry(key) for key in spec.defaults_applied)
        lines.append(f"defaults applied: {joined}")
    return lines


def assumptions_to_dict(
    spec: ComparisonSpec, prior: Optional[LoadedScenarioPrior] = None,
) -> Dict[str, Any]:
    """
    The structured assumption echo: what the text report's "Assumptions" block
    says, plus — for every defaulted key — the full anchor record, so an agent
    can answer "where did that number come from?" without reading source.

    `kind` per entry: the anchor's kind (`cited` / `reference` / `neutral` /
    `derivation`), `mode` for a mode flag, or `uncited` when a defaulted key has
    no registry entry at all (that last case is a defect the tests pin against).
    """
    entries: List[Dict[str, Any]] = []
    nominal = spec.economic.mode == "nominal"
    pi = spec.economic.inflation_rate
    for key in spec.defaults_applied:
        field = key.rsplit(".", 1)[1]
        raw = spec_value(spec, key)
        anchor = ANCHORS.get(_ECHO_ALIASES.get(key, key))
        if anchor is not None:
            kind = anchor.kind
        elif field == "mode":
            kind = "mode"
        else:
            kind = "uncited"
        # Nominal mode: the anchor is a REAL rate. The discount rate is composed
        # at parse time (value ≠ anchor.value); growth/escalation/return rates
        # keep the real value and are composed at compute time. Say which, so an
        # agent can reconcile `value` with `anchor.value` without reading source.
        note: Optional[str] = None
        if nominal and anchor is not None:
            if key == "simulation.discount_rate":
                note = (f"composed at parse: (1 + {anchor.value:.1%} real)(1 + {pi:.1%} "
                        f"inflation_rate) − 1 = {raw:.2%} nominal")
            elif field in _COMPOSED_AT_COMPUTE:
                note = (f"REAL rate; the engine composes inflation_rate on top at compute "
                        f"time: (1 + {raw:.1%})(1 + {pi:.1%}) − 1 = {(1 + raw) * (1 + pi) - 1:.2%} nominal")
        entries.append({
            "key": key,
            "value": raw,
            "formatted": echo_value(spec, key),
            "cite": short_cite(key) or None,
            "kind": kind,
            "note": note,
            "anchor": anchor_to_dict(anchor) if anchor is not None else None,
        })
    return {
        "mode": spec.economic.mode,
        "years": spec.simulation.years,
        "discount_rate": spec.simulation.discount_rate,
        "lines": format_assumptions(spec, prior),
        "defaults_applied": entries,
        # Jurisdiction figures the USER supplied that a published source agrees
        # with (empty `matches` = the engine knows of no source for that line).
        "reference_matches": reference_matches(spec),
        "demographic_prior": (
            {**prior.provenance_block(), "description": prior.describe(),
             "sources": prior.sources()}
            if prior is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def verdict_to_dict(verdict: Optional[Verdict]) -> Optional[Dict[str, Any]]:
    """The shared verdict (models.compute_verdict), JSON-shaped; None when no
    option was priced (e.g. a Monte-Carlo-only run)."""
    return dataclasses.asdict(verdict) if verdict is not None else None


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def det_to_dict(det: ComparisonDeterministicResult) -> dict:
    def _opt(r):
        if r is None:
            return None
        return {"total_pv": r.total_pv, "breakdown": r.breakdown,
                "cash_year1": r.cash_year1, "principal_year1": r.principal_year1,
                "appreciation_year1": r.appreciation_year1}

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
