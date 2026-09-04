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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .anchors import (
    ANCHORS,
    _ECHO_ALIASES,
    Anchor,
    match_reference,
    match_reference_sum,
    short_cite,
)
from .market_scenario import LoadedScenarioPrior
from .land_transfer_tax import option_province, purchase_costs_clause
from .mortgage_insurance import financing_clause
from .models import (
    AffordabilityReport,
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    ComparisonSpec,
    EconomicParams,
    MonteCarloSummary,
    Verdict,
)
from .sources import source_echo_to_dict, source_lines


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
    doc["restatements"] = [{"value": value, "why": why}
                           for value, why in anchor.restatements]
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


def cost_family(cost_name: str) -> Optional[str]:
    """Which jurisdiction table a recurring-cost line belongs to, or None.

    Separators are normalised first: the repo's own examples write
    `property_tax` and `home_insurance`, and a matcher that only saw
    "property tax" would silently skip exactly the configs it ships with.
    The loader's coherence checks reuse this same test, so "a line named like
    property tax" means one thing across the engine.
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


_SCHOOL_WORDS = ("school", "scolaire")


def school_tax_line(cost_name: str) -> bool:
    """True for a line that names the Québec school tax (`school tax`, `taxe
    scolaire`) — the levy a municipal rate leaves out, which is why the
    property-tax matcher above refuses these names."""
    low = cost_name.lower().replace("_", " ").replace("-", " ")
    return any(word in low for word in _SCHOOL_WORDS)


def _citations(family: str, probe: Optional[float]) -> Tuple[
    List[Anchor], List[Dict[str, Any]],
]:
    """The anchors cited for one cost line, and how they combine into a claim.

    Two shapes: `single` — one published figure equals the user's — and `sum`,
    a municipal property-tax rate plus its province's school rate, which is the
    bill a Québec owner actually pays. Singles are tried first; the sum is only
    consulted when nothing published equals the figure on its own, so a value
    that IS a published rate can never be re-explained as somebody's sum.

    Returns (anchors cited, in citation order and de-duplicated; the citation
    records). Both are empty when nothing agrees — the honest "no source for
    this", which is reported rather than hidden.
    """
    cited: List[Anchor] = []
    citations: List[Dict[str, Any]] = []
    for anchor in match_reference(family, probe):
        cited.append(anchor)
        citations.append({"kind": "single", "anchors": [anchor.name],
                          "total": anchor.value})
    if not citations:
        for pair in match_reference_sum(family, probe):
            citations.append({
                "kind": "sum",
                "anchors": [a.name for a in pair],
                "total": sum(a.value for a in pair),
            })
            cited.extend(a for a in pair if a not in cited)
    return cited, citations


def reference_matches(spec: ComparisonSpec) -> List[Dict[str, Any]]:
    """One entry per OWNED-option recurring cost that names a property tax or a
    home-insurance premium, with every jurisdiction anchor whose published
    figure equals it — alone, or summed with the school tax of its province.

    `matches` carries the full record of every anchor cited for the line, so a
    consumer that reads only that list still sees BOTH halves of a summed rate;
    `citations` says how they combine (`single` or `sum`), which is what the
    text line renders. Both are empty when nothing published agrees — reported,
    not hidden: an unmatched tax line is the honest "no source for this" the
    answer is required to say out loud. `province` is where the option sits
    (stated, or implied by its municipality; `None` when neither is given), so
    an unmatched Ontario tax line can say what an Ontario rate is levied on.
    """
    entries: List[Dict[str, Any]] = []
    for option_name in ("condo", "house"):
        option = getattr(spec, option_name, None)
        if option is None:
            continue
        province = option_province(option.province, option.municipality)
        for cost in option.other_recurring_costs:
            family = cost_family(cost.name)
            if family is None:
                continue
            if family == "property_tax.":
                implied = (cost.annual_amount / option.initial_value
                           if option.initial_value else None)
                probe = implied
            else:
                implied = None
                probe = cost.annual_amount
            cited, citations = _citations(family, probe)
            entries.append({
                "option": option_name,
                "cost_name": cost.name,
                "annual_amount": cost.annual_amount,
                "family": family,
                "implied_rate": implied,
                "province": province,
                "matches": [anchor_to_dict(a) for a in cited],
                "citations": citations,
            })
    return entries


def _cite_text(citation: Dict[str, Any], by_name: Dict[str, Dict[str, Any]]) -> str:
    """One citation, rendered. A citation ALWAYS carries the unit of every
    anchor in it: a municipal rate names the base it is levied on, because that
    base is not the price the user typed — and on a SUM both units have to
    survive, since one of them may carry a caveat the other does not (Montréal's
    says « city-wide lines only — the borough adds more », and a compact joint
    unit would quietly drop it)."""
    parts = [by_name[name] for name in citation["anchors"]]
    names = " + ".join(p["short_cite"] for p in parts)
    units = " · ".join(p["unit"] for p in parts)
    if citation["kind"] == "single":
        return f"{names} · {units}"
    arithmetic = " + ".join(f"{p['value']:.4%}" for p in parts)
    return f"{names} · {arithmetic} = {citation['total']:.4%} · {units}"


def _reference_line(entry: Dict[str, Any]) -> str:
    """One recurring-cost line for the assumption echo."""
    head = f"{entry['cost_name']} ${entry['annual_amount']:,.0f}/yr"
    if entry["implied_rate"] is not None:
        head += f" = {entry['implied_rate']:.3%} of price"
    if not entry["citations"]:
        tail = "no anchor match — hde --print-anchors"
        # An Ontario rate is levied on the MPAC assessment, which for the 2026
        # tax year is a January 1, 2016 value (the property_tax.toronto and
        # property_tax.ottawa rationales in anchors.py). Served answers showed
        # an Ottawa run applying a rate to the purchase price with nothing
        # beside `no anchor match` saying that reading overstates the bill.
        if entry["family"] == "property_tax." and entry.get("province") == "ON":
            tail += ("; a rate on the purchase price overstates an Ontario bill: "
                     "assessments are on a 2016 base")
        return f"{head} [{tail}]"
    by_name = {m["name"]: m for m in entry["matches"]}
    cites = " ; ".join(_cite_text(c, by_name) for c in entry["citations"])
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
    the value without stating it. The block closes with the source-class echo
    (sources.source_lines): who STATED the values the YAML does carry — or, with
    no `sources:` block, the one line saying the read-back cannot tell the
    user's numbers from the assistant's.
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
    # The transfer tax gets its OWN line rather than a clause on `financing:`:
    # the financing line is skipped for an all-cash purchase, and an all-cash
    # buyer pays the welcome tax like everyone else. It sits next to the
    # financing line so the two `purchase_costs` figures reconcile by eye.
    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None or opt.land_transfer_tax is None:
            continue
        premium_tax = (opt.mortgage_insurance.premium_tax
                       if opt.mortgage_insurance is not None and opt.cash_available is None
                       else 0.0)
        lines.append(
            f"{name} purchase costs: "
            + purchase_costs_clause(opt.land_transfer_tax, opt.purchase_costs, premium_tax)
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
        # With a derived insurance premium the headline loan-to-value is the one
        # the TIER was chosen on — before the premium is rolled in; the insured
        # clause then states the premium and the loan it produces (round 7).
        record = opt.mortgage_insurance
        loan = opt.initial_value - opt.down_payment + opt.financed_purchase_costs
        ltv = loan / opt.initial_value if opt.initial_value else 0.0
        if record is not None:
            ltv = record.ltv
        # The premium tax is cash at closing, so it is a term of BOTH cash
        # sentences: it comes out of the pile before the down payment, and it is
        # part of the year-0 cash a stated down payment commits. An equation
        # that silently omits it does not balance (round 7).
        taxed = record is not None and record.premium_tax
        if opt.cash_available is not None:
            tax_term = f" − premium tax ${record.premium_tax:,.0f}" if taxed else ""
            head = (f"cash available ${opt.cash_available:,.0f} − purchase_costs "
                    f"${opt.purchase_costs:,.0f}{tax_term} = down payment "
                    f"${opt.down_payment:,.0f}")
            # year-0 cash IS the pile in this form; naming it twice is noise.
            year0_clause = ""
        else:
            head = f"down payment ${opt.down_payment:,.0f}"
            parts = "down payment + purchase_costs" + (" + premium tax" if taxed else "")
            year0_clause = f" · year-0 cash ${year0:,.0f} ({parts})"
        # Where the pile stops covering 20% down (2026-09-04 review: a real
        # answer hand-solved "your $140,000 covers 20% down up to $642,893").
        # The netted cash IS the down payment, so the fixed point is
        # (cash − cash purchase_costs) / 20%; at that price no premium is due,
        # which is why the premium tax is not a term of it. Stated with what it
        # holds fixed: a dollar purchase_costs figure — a derived transfer tax
        # included — does not rescale with the price.
        cover_clause = ""
        if opt.cash_available is not None:
            covered = (opt.cash_available - opt.purchase_costs) / 0.20
            if covered > 0:
                cover_clause = (
                    f" · this cash covers 20% down up to a price of ${covered:,.0f} "
                    f"(purchase_costs held at ${opt.purchase_costs:,.0f}; above it the "
                    f"mortgage is insured)"
                )
        lines.append(
            f"{name} financing: {head} = {down_frac:.2%} of price, "
            f"${abs(gap):,.0f} {side} the 20% mortgage-insurance line (${line:,.0f}) · "
            f"loan-to-value {ltv:.2%}"
            + year0_clause
            # The premium the engine derived is never echoed as a typed
            # financed_purchase_cost: the user did not type it.
            + (f" · financed_purchase_costs ${opt.financed_purchase_costs:,.0f} on the loan"
               if opt.financed_purchase_costs and record is None else "")
            + (f" · {financing_clause(record)}" if record is not None else "")
            + cover_clause
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
    # Source classes (2026-09-03): which STATED values are the user's own, which
    # the assistant typed for them, which an anchor supplied — and, with no
    # `sources:` block, the one line saying the echo cannot tell them apart.
    lines.extend(source_lines(spec.sources))
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

    `sources` is the other half of the provenance question — `defaults_applied`
    says what the engine filled in, `sources` says who stated the rest.
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
        "sources": source_echo_to_dict(spec.sources),
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


# ---------------------------------------------------------------------------
# The read-back block (2026-09-04)
#
# Eight reviewed answers in two days each dropped a line the engine had printed
# — a `[warning]`, the `assistant-typed:` line, the decisiveness rule — though a
# checklist named every one. So the engine assembles them: one ordered block the
# answer carries verbatim, built from the SAME functions that print each line
# (`format_assumptions`, `affordability_lines`, a break-even's own `sentence`,
# `sweep.flip_lines`). A second formatter here would be a second thing to drift.
#
# `user-stated:` is deliberately absent: the user knows their own numbers. What
# has to travel is what the assistant chose, what nothing attributes, and what
# the engine refuses to let pass silently.
# ---------------------------------------------------------------------------

READ_BACK_HEADER = "READ-BACK — carry these lines into any answer, verbatim:"

# The source-echo lines the read-back carries (sources.py builds them).
_SOURCE_PREFIXES = ("sources: none declared", "assistant-typed:", "unattributed:", "anchor-sourced:")
_OWNED = ("condo", "house")


def decisiveness_line(verdict: Optional[Verdict]) -> Optional[str]:
    """`decisiveness: <the rule, measured>` — the report's own line, built once.

    None when nothing was compared (no verdict, or a single priced option).
    """
    if verdict is None or verdict.runner_up is None:
        return None
    return f"decisiveness: {verdict.reason}"


def affordability_lines(report: Optional[AffordabilityReport]) -> List[str]:
    """The affordability summary: the header naming the threshold and the caps
    it is judged against, then one line per option (max ratio, breach years).

    Unindented — the text report indents the per-option lines under its own
    header; the read-back carries them as they are.
    """
    if report is None:
        return []
    lines = [
        f"Affordability (threshold: {report.threshold:.0%} — a GDS-shaped ratio, housing cost incl. "
        f"maintenance over income; the 32% figure is the legacy guideline, CMHC caps GDS at 39%, "
        f"TDS at 44%)"
    ]
    for name, ratios, exceeds in (
        ("Rent", report.rent_ratios, report.years_rent_exceeds),
        ("Condo", report.condo_ratios, report.years_condo_exceeds),
        ("House", report.house_ratios, report.years_house_exceeds),
    ):
        if ratios is not None:
            exceed_str = str(exceeds) if exceeds else "none"
            lines.append(f"{name}: max ratio {max(ratios):.1%}  years exceeding: {exceed_str}")
    return lines


def year1_cash_lines(
    det: Optional[ComparisonDeterministicResult],
    econ: Optional[EconomicParams] = None,
) -> List[str]:
    """Year-1 cash, undiscounted: the header, then one line per option — $/yr
    and $/mo, the principal repaid (the part of a payment that is not a cost),
    and the expected appreciation, which is not cash at all.

    Unindented like `affordability_lines`: the text report indents the
    per-option lines under the same header and the read-back carries them as
    they are. Round-four dogfood: the PV $/month equivalent was read as
    out-of-pocket and had the wrong sign for that reading. Round 9: the block
    an answer carries held no cash line, so the answer quoted no cash figure.
    """
    if det is None:
        return []
    rows: List[str] = []
    for name, r in (("Condo", det.condo), ("House", det.house), ("Rent", det.rent)):
        if r is None or r.cash_year1 is None:
            continue
        line = f"{name}: ${r.cash_year1:>10,.0f}/yr (${r.cash_year1 / 12:,.0f}/mo)"
        if r.principal_year1:
            line += (f" — of which ${r.principal_year1:,.0f} principal repaid; "
                     f"the rest is unrecoverable")
        if r.appreciation_year1:
            # Round 5b: at 0 real growth in nominal mode this is inflation carry
            # alone; say what the growth is so it is not read as a market view.
            how = ("value × nominal growth = real growth composed with inflation; not cash"
                   if econ is not None and econ.mode == "nominal"
                   else "value × real growth, not cash")
            line += f"; expected appreciation ${r.appreciation_year1:,.0f} ({how})"
        rows.append(line)
    if not rows:
        return []
    return ["Year-1 cash (undiscounted; PV totals above credit equity at sale)"] + rows


def _option_lines(echo: Sequence[str], suffix: str) -> List[str]:
    """The per-option assumption lines with one suffix (`financing:`,
    `other costs:`), in the engine's own option order."""
    return [line for name in _OWNED for line in echo if line.startswith(f"{name} {suffix}")]


def next_step_line(
    *,
    verdict: Optional[Verdict] = None,
    det: Optional[ComparisonDeterministicResult] = None,
    prior: Optional[LoadedScenarioPrior] = None,
    break_evens: Sequence[Dict[str, Any]] = (),
) -> Optional[str]:
    """The one run that resolves a coin flip decided under a demographic prior:
    `--break-even <owned>.value_growth_rate`, whose note places the prior's own
    reference drift against the tie band.

    2026-09-04: one round ran exactly that and answered the question; the next
    shipped the coin flip without it. So the block says what to run — naming
    the cheapest owned option, since that is the growth rate in question.

    Silent unless the prior is loaded, Monte Carlo DECIDED the verdict
    (`--no-monte-carlo` falls back to the margin band and has nothing to
    resolve), the verdict is not decisive, and the run is not already that
    break-even.
    """
    if prior is None or det is None or verdict is None:
        return None
    if verdict.rule != "mc_floor" or verdict.decisive:
        return None
    priced = [(name, getattr(det, name)) for name in _OWNED if getattr(det, name) is not None]
    if not priced:
        return None
    option = min(priced, key=lambda pair: pair[1].total_pv)[0]
    key = f"{option}.value_growth_rate"
    if any(result.get("key") == key for result in break_evens):
        return None
    return (f"next: not decisive under the prior — run --break-even {key} to see where "
            f"the prior's drift sits against the tie band")


def read_back_lines(
    spec: ComparisonSpec,
    *,
    warnings: Sequence[str] = (),
    verdict: Optional[Verdict] = None,
    det: Optional[ComparisonDeterministicResult] = None,
    prior: Optional[LoadedScenarioPrior] = None,
    break_evens: Iterable[Dict[str, Any]] = (),
    sweeps: Iterable[Dict[str, Any]] = (),
) -> List[str]:
    """Every line an honest answer has to carry, in one order, ready to paste.

    Order: the `[warning]` lines; the source classes the user did not state (or
    the one line saying no `sources:` block was declared); the `defaults
    applied:` line, so the numbers the ENGINE chose are named with their
    citations; the decisiveness rule; each option's financing line and its
    `purchase costs:` line; the year-1 cash view; each option's other-costs
    line with its citation or `no anchor match`; the affordability summary;
    each break-even's sentence, its re-solutions across a sweep, and the
    block's note; each sweep's flip lines; and, on a coin flip under a prior,
    the run that would resolve it.
    """
    lines = [f"[warning] {warning}" for warning in warnings]
    echo = format_assumptions(spec, prior)
    lines.extend(line for line in echo if line.startswith(_SOURCE_PREFIXES))
    # 2026-09-04 review: `selling_cost_rate` 5% and the discount rate — the two
    # largest numbers the engine set for that run — were named nowhere in the
    # answer, because the block did not carry the line that states them.
    lines.extend(line for line in echo if line.startswith("defaults applied:"))
    decisiveness = decisiveness_line(verdict)
    if decisiveness is not None:
        lines.append(decisiveness)
    lines.extend(_option_lines(echo, "financing:"))
    lines.extend(_option_lines(echo, "purchase costs:"))
    # Cash beside the PV view: an answer that carries only present values has
    # no figure for the question every user asks first ("what leaves my account
    # each month?") and reads the PV $/month equivalent as that figure.
    lines.extend(year1_cash_lines(det, spec.economic))
    lines.extend(_option_lines(echo, "other costs:"))
    if det is not None:
        lines.extend(affordability_lines(det.income_report))
    break_evens = list(break_evens)
    if break_evens:
        # Local import for the same reason as `flip_lines` below: break_even
        # reaches this module through sweep, so the dependency runs one way at
        # import time.
        from .break_even import across_row_sentence, threshold_sentences
    for result in break_evens:
        key = result["key"]
        band = result["tie_band_fraction"]
        for sentence in threshold_sentences(key, result, band):
            lines.append(f"break-even {key}: {sentence}")
        # The threshold re-solved at every sweep point: without these the block
        # carried the base solve alone, and an answer reduced a whole years
        # bracket to one number.
        for across in result.get("across", []):
            skey = across["key"]
            for row in across["rows"]:
                lines.append(f"break-even {key} at {across_row_sentence(key, skey, row, band)}")
        if result.get("note"):
            lines.append(f"break-even {key} note: {result['note']}")
    if sweeps:
        # Local import: sweep.py imports this module for its per-point Monte
        # Carlo serialization, so the dependency runs one way at import time.
        from .sweep import flip_lines
        for result in sweeps:
            lines.extend(flip_lines(result))
    next_step = next_step_line(verdict=verdict, det=det, prior=prior,
                               break_evens=break_evens)
    if next_step is not None:
        lines.append(next_step)
    return lines
