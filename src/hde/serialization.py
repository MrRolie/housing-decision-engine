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
    nearest_reference,
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
from .rates import ConvertedRate, converted_for, inflation_anchor_name
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


    `nearest` (2026-09-04) is set only on such an unmatched line: the published
    figure of the option's OWN province that the user's figure misses by no
    more than 2% (`anchors.nearest_reference`), with the signed gap — a hint
    that a rounded or mistyped copy of a published rate deserves a second
    look, rendered with "not a match" so it is never read as a citation. None
    when nothing is that close, or when the option states no province: a hint
    across provinces is the one thing this must never offer.
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
            near = (nearest_reference(family, probe, province)
                    if not citations else None)
            entries.append({
                "option": option_name,
                "cost_name": cost.name,
                "annual_amount": cost.annual_amount,
                "family": family,
                "implied_rate": implied,
                "province": province,
                "matches": [anchor_to_dict(a) for a in cited],
                "citations": citations,
                "nearest": None if near is None else {
                    "name": near.name,
                    "value": near.value,
                    "delta": probe - near.value,
                    "short_cite": near.short_cite,
                    "unit": near.unit,
                },
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


def _nearest_text(family: str, near: Dict[str, Any]) -> str:
    """The near-miss hint: the anchor by name, its figure, the signed gap in
    the family's own unit, and the words that keep it from reading as a
    citation."""
    if family == "property_tax.":
        gap = f"{near['delta'] * 100:+.4f} pt"
        figure = f"{near['value']:.4%}"
    else:
        gap = f"{'+' if near['delta'] >= 0 else '−'}${abs(near['delta']):,.0f}"
        figure = f"${near['value']:,.0f}"
    return f"nearest: {near['name']} {figure} (Δ {gap}) — not a match"


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
        if entry.get("nearest"):
            tail += "; " + _nearest_text(entry["family"], entry["nearest"])
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


def real_discount_rate(spec: ComparisonSpec) -> float:
    """The discount rate in REAL terms — the figure typed, or the anchored
    default, before nominal composition. The spec holds only the rate in use,
    so nominal mode inverts `(1 + real)(1 + π) − 1`; exact at display precision."""
    dr = spec.simulation.discount_rate
    if spec.economic.mode != "nominal":
        return dr
    return (1 + dr) / (1 + spec.economic.inflation_rate) - 1


def typed_discount_rate(spec: ComparisonSpec) -> Optional[ConvertedRate]:
    """The discount rate as the config typed it, when it was typed AS QUOTED
    (rates as quoted, 2026-09-05); None when defaulted or declared real."""
    return converted_for(spec.converted_rates, "discount_rate")


def discount_rate_note(spec: ComparisonSpec) -> Optional[str]:
    """How `discount_rate` relates to the figure stated (typed or the anchor)
    when the loader converted it: a quoted figure deflated in real mode, used
    as typed in nominal mode; a real figure — the anchor, or a typed one under
    `rates: real` — composed in nominal mode. None when the rate in use is the
    figure stated."""
    typed = typed_discount_rate(spec)
    pi = spec.economic.inflation_rate
    if spec.economic.mode == "nominal":
        if typed is not None:
            return f"as quoted: {typed.quoted:.1%} nominal, used as typed"
        return (f"composed at parse: (1 + {real_discount_rate(spec):.1%} real)"
                f"(1 + {pi:.1%} inflation_rate) − 1 = "
                f"{spec.simulation.discount_rate:.2%} nominal")
    if typed is not None:
        return (f"deflated at parse: (1 + {typed.quoted:.1%} as quoted)/(1 + {pi:.1%} "
                f"inflation_rate) − 1 = {spec.simulation.discount_rate:.2%} real")
    return None


def rates_line(spec: ComparisonSpec) -> str:
    """The `rates:` line (2026-09-05): the convention the typed rates were read
    under and, for every one the loader converted, both forms — the figure as
    quoted and the figure in use. One line, one clause per rate, byte-stable:
    the read-back carries it so an answer can never show a rate in a
    convention the user did not type it in.
    """
    pi = spec.economic.inflation_rate
    if spec.rates == "real":
        tail = (f"composed with {pi:.1%} inflation_rate at compute"
                if spec.economic.mode == "nominal" else "used as typed")
        return f"rates: real (declared) · typed rates are real figures, {tail}"
    if not spec.converted_rates:
        return "rates: as quoted · no typed rate to convert"
    if spec.economic.mode == "nominal":
        clauses = [f"{c.key} {c.quoted:.1%} as quoted = {c.effective:.1%} nominal, as typed"
                   for c in spec.converted_rates]
    else:
        clauses = [f"{c.key} {c.quoted:.1%} as quoted = {c.effective:.1%} after {pi:.1%} inflation"
                   for c in spec.converted_rates]
    return "rates: as quoted · " + " · ".join(clauses)


def rate_label(spec: ComparisonSpec, dotted: str, rate: float) -> str:
    """A rate for a sentence: the figure the run uses and, when the config
    typed that rate as quoted and the quoted figure differs, the quoted figure
    beside it — so "your X%" is never a number the user did not type. When
    the two coincide (nominal mode, or a zero deflator) the figure stands
    alone."""
    typed = converted_for(spec.converted_rates, dotted)
    if typed is None or abs(typed.quoted - rate) <= 5e-6:
        return f"{rate:.1%}"
    return f"{rate:.1%} real ({typed.quoted:.1%} as quoted)"


def growth_label(spec: ComparisonSpec, option_name: str) -> str:
    """An owned option's `value_growth_rate` for a sentence (`rate_label`)."""
    rate = getattr(spec, option_name).value_growth_rate
    return rate_label(spec, f"{option_name}.value_growth_rate", rate)


def converted_rates_to_list(spec: ComparisonSpec) -> List[Dict[str, Any]]:
    """`assumptions.converted_rates`: one `{key, quoted, effective}` per typed
    rate the loader converted — `effective` is the rate the run uses, in the
    run's terms (deflated in real mode; the quoted figure itself in nominal
    mode). Empty under `rates: real`."""
    return [{"key": c.key, "quoted": c.quoted, "effective": c.effective}
            for c in spec.converted_rates]


def default_anchor(spec: ComparisonSpec, key: str) -> Optional[Anchor]:
    """The registry entry that supplied one defaulted key. `economic.inflation_rate`
    is the one key two anchors can supply: the FP Canada planning figure when it
    is the deflator of as-quoted rates in real mode (rates as quoted,
    2026-09-05), else the real-mode inert zero — so the echo cites the anchor
    whose value it actually applied."""
    if key == "economic.inflation_rate":
        return ANCHORS[inflation_anchor_name(spec.economic.mode, spec.rates)]
    return ANCHORS.get(_ECHO_ALIASES.get(key, key))


def format_assumptions(
    spec: ComparisonSpec, prior: Optional[LoadedScenarioPrior] = None,
    raw: Optional[Dict[str, Any]] = None,
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

    `raw` is the YAML mapping the spec was loaded from. With it, the financing
    line's "covers 20% down up to a price of …" is solved through the loader
    (`sweep.cover_price`), so a `purchase_costs_rate` or a transfer-tax
    schedule is re-derived along the price; without it (a surface holding the
    spec alone) the line keeps the seed's dollar figure and says it holds it.
    """
    nominal = spec.economic.mode == "nominal"
    pi = spec.economic.inflation_rate

    def _g(rate: float, dotted: str) -> str:
        """A growth/escalation input beside the figure the user typed. The spec
        holds the REAL rate; a rate typed as quoted (2026-09-05) shows its
        quoted form beside it, and in nominal mode the effective composed rate
        leads, so a sticker rate is never shown in a convention the user did
        not type it in (2026-09-02 dogfood: the echo printed the raw rate and
        every nominal-thinking user was inflated twice)."""
        typed = converted_for(spec.converted_rates, dotted)
        if not nominal:
            if typed is None:
                return f"{rate:+.1%}/yr"
            return f"{rate:+.1%}/yr ({typed.quoted:.1%} as quoted)"
        eff = (1 + rate) * (1 + pi) - 1
        if typed is None:
            return f"{rate:+.1%}/yr real → {eff:+.1%}/yr nominal (incl. {pi:.1%} inflation)"
        return f"{typed.quoted:+.1%}/yr nominal, as quoted ({rate:.1%} real)"

    dr = spec.simulation.discount_rate
    typed_dr = typed_discount_rate(spec)
    if nominal and typed_dr is not None:
        dr_text = f"{typed_dr.quoted:.1%} as quoted, used as typed"
    elif nominal:
        # A REAL discount rate — the anchored default, or a figure typed under
        # `rates: real` — composed with inflation_rate at parse like every other
        # real rate in nominal mode; name both figures in the words `_g` uses.
        default = " default" if "simulation.discount_rate" in spec.defaults_applied else ""
        dr_text = f"{real_discount_rate(spec):.1%} real{default} → {dr:.1%} nominal (incl. {pi:.1%} inflation)"
    elif typed_dr is not None:
        dr_text = f"{typed_dr.quoted:.1%} as quoted → {dr:.1%} real (after {pi:.1%} inflation)"
    else:
        dr_text = f"{dr:.1%}"
    if not nominal:
        convention = ""
    elif spec.rates == "real":
        convention = (" (growth, escalation, investment-return and discount-rate inputs are REAL and "
                      "composed with inflation_rate; mortgage_rate is used as entered)")
    else:
        convention = (" (typed rates are as quoted and used as typed; anchored defaults are real "
                      "and composed with inflation_rate; mortgage_rate is used as entered)")
    lines = [f"mode: {spec.economic.mode} terms · discount_rate {dr_text}{convention}"]
    if spec.condo is not None:
        lines.append(
            f"condo: value growth {_g(spec.condo.value_growth_rate, 'condo.value_growth_rate')} · "
            f"fee escalation {_g(spec.condo.fee_escalation_rate, 'condo.fee_escalation_rate')} · "
            f"selling_cost_rate {spec.condo.selling_cost_rate:.1%}"
        )
    if spec.house is not None:
        lines.append(
            f"house: value growth {_g(spec.house.value_growth_rate, 'house.value_growth_rate')} · "
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
            solved = None
            if raw is not None:
                # Local import: sweep.py imports this module for its per-point
                # Monte Carlo serialization, so the dependency runs one way at
                # import time.
                from .sweep import cover_price
                solved = cover_price(raw, name)
            if solved is not None:
                price, costs_at = solved
                cover_clause = (
                    f" · this cash covers 20% down up to a price of ${price:,.0f} "
                    f"(purchase_costs ${costs_at:,.0f} at that price; above it the "
                    f"mortgage is insured)"
                )
            else:
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
            f"rent: escalation {_g(spec.rent.rent_escalation_rate, 'rent.rent_escalation_rate')} · "
            f"invested capital ${spec.rent.invested_down_payment:,.0f} at "
            f"{_g(spec.rent.investment_return_rate, 'rent.investment_return_rate')}"
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
            anchor = default_anchor(spec, key)
            cite = short_cite(anchor.name) if anchor is not None else short_cite(key)
            tag = f" [{cite}]" if cite else ""
            return f"{key}={echo_value(spec, key)}{tag}"
        joined = ", ".join(_echo_entry(key) for key in spec.defaults_applied)
        lines.append(f"defaults applied: {joined}")
    # The convention the typed rates were read under, each with both forms.
    lines.append(rates_line(spec))
    # Source classes (2026-09-03): which STATED values are the user's own, which
    # the assistant typed for them, which an anchor supplied — and, with no
    # `sources:` block, the one line saying the echo cannot tell them apart.
    lines.extend(source_lines(spec.sources))
    return lines


def assumptions_to_dict(
    spec: ComparisonSpec, prior: Optional[LoadedScenarioPrior] = None,
    raw: Optional[Dict[str, Any]] = None,
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
        resolved = spec_value(spec, key)
        anchor = default_anchor(spec, key)
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
                note = discount_rate_note(spec)
            elif field in _COMPOSED_AT_COMPUTE:
                note = (f"REAL rate; the engine composes inflation_rate on top at compute "
                        f"time: (1 + {resolved:.1%})(1 + {pi:.1%}) − 1 = {(1 + resolved) * (1 + pi) - 1:.2%} nominal")
        entries.append({
            "key": key,
            "value": resolved,
            "formatted": echo_value(spec, key),
            "cite": (short_cite(anchor.name) if anchor is not None else None),
            "kind": kind,
            "note": note,
            "anchor": anchor_to_dict(anchor) if anchor is not None else None,
        })
    return {
        "mode": spec.economic.mode,
        "years": spec.simulation.years,
        "discount_rate": spec.simulation.discount_rate,
        # The rate in use may be the engine's conversion of the `sources`
        # figure — a quoted rate deflated in real mode (2026-09-05), a real
        # figure composed in nominal mode (2026-09-04); this says which.
        "discount_rate_note": discount_rate_note(spec),
        # Rates as quoted (2026-09-05): the convention, the deflator, and every
        # typed rate converted — the figure as quoted and the figure in use.
        "rates": spec.rates,
        "inflation_rate": spec.economic.inflation_rate,
        "converted_rates": converted_rates_to_list(spec),
        "lines": format_assumptions(spec, prior, raw),
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
_SOURCE_PREFIXES = ("sources: none declared", "assistant-typed:", "unattributed:", "anchor-sourced:", "swept:")
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


# The short block (2026-09-05): a user who asked for the gist gets these
# sections alone — the warnings, the source lines, the decisiveness rule —
# closed by ONE engine line counting what the full block adds. Every other
# shape keeps the full block, byte for byte.
_SHORT_SECTIONS = ("warnings", "sources", "decisiveness")


def _read_back_sections(
    spec: ComparisonSpec,
    *,
    warnings: Sequence[str],
    verdict: Optional[Verdict],
    det: Optional[ComparisonDeterministicResult],
    prior: Optional[LoadedScenarioPrior],
    break_evens: Iterable[Dict[str, Any]],
    sweeps: Iterable[Dict[str, Any]],
    raw: Optional[Dict[str, Any]],
) -> List[Tuple[str, List[str]]]:
    """The block as labelled sections, in the block's order — the ONE assembly
    both views are cut from. The short block is a subsequence of the full one
    by construction, and its closing line names the labels of what it left
    out, never a second reading of finished lines (a classifier over prefixes
    would be the second formatter the header of this section warns against).
    """
    echo = format_assumptions(spec, prior, raw)
    decisiveness = decisiveness_line(verdict)
    sections: List[Tuple[str, List[str]]] = [
        ("warnings", [f"[warning] {warning}" for warning in warnings]),
        ("sources", [line for line in echo if line.startswith(_SOURCE_PREFIXES)]),
        # 2026-09-04 review: `selling_cost_rate` 5% and the discount rate — the
        # two largest numbers the engine set for that run — were named nowhere
        # in the answer, because the block did not carry the line that states
        # them.
        ("defaults applied", [line for line in echo if line.startswith("defaults applied:")]),
        # The convention the user's rates were read under, each in both forms
        # (2026-09-05): the one line that says what the engine did with the
        # numbers the user typed.
        ("rates", [line for line in echo if line.startswith("rates:")]),
        # In nominal mode the discount rate in use is the engine's composition
        # of a real figure — the default, or one declared `rates: real`
        # (2026-09-04) — or a quoted figure used as typed, and the `mode:` line
        # is the one that names both; in real mode the rate is the user's own
        # (the `rates:` line has its conversion) or on the `defaults applied:`
        # line, so the block has it.
        ("mode", [line for line in echo if line.startswith("mode:")]
                 if spec.economic.mode == "nominal" else []),
        ("decisiveness", [decisiveness] if decisiveness is not None else []),
        ("financing", _option_lines(echo, "financing:")),
        ("purchase costs", _option_lines(echo, "purchase costs:")),
        # Cash beside the PV view: an answer that carries only present values
        # has no figure for the question every user asks first ("what leaves
        # my account each month?") and reads the PV $/month equivalent as that
        # figure.
        ("year-1 cash", year1_cash_lines(det, spec.economic)),
        ("other costs", _option_lines(echo, "other costs:")),
    ]
    affordability: List[str] = []
    if det is not None:
        # One fact once (2026-09-04): an option's breach is already a
        # `[warning]` line above — the section keeps its header (the threshold
        # and the caps) and the max-ratio line of every option no warning
        # names. The warning is never the line that goes.
        warned = {w.split()[1] for w in warnings
                  if w.startswith("affordability: ") and " housing cost exceeds " in w}
        affordability = [line for line in affordability_lines(det.income_report)
                         if not any(line.startswith(f"{name.capitalize()}: max ratio")
                                    for name in warned)]
    sections.append(("affordability", affordability))
    break_evens = list(break_evens)
    thresholds: List[str] = []
    if break_evens:
        # Local import for the same reason as `sweep_lines` below: break_even
        # reaches this module through sweep, so the dependency runs one way at
        # import time.
        from .break_even import read_back_block
    notes_said: List[str] = []
    for result in break_evens:
        # The header, the base threshold, every `across` re-solution (without
        # these the block carried the base solve alone, and an answer reduced
        # a whole years bracket to one number) and the note — each fact once.
        thresholds.extend(read_back_block(result))
        if result.get("note"):
            notes_said.append(result["note"])
    sections.append(("thresholds", thresholds))
    sweeps = list(sweeps)
    sweep_block: List[str] = []
    if sweeps:
        # Local import: sweep.py imports this module for its per-point Monte
        # Carlo serialization, so the dependency runs one way at import time.
        from .sweep import sweep_lines
        for result in sweeps:
            sweep_block.extend(sweep_lines(result))
            note = result.get("note")
            if note and note not in notes_said:  # a price scan's note, said once
                sweep_block.append(f"sweep {result['key']} note: {note}")
                notes_said.append(note)
    sections.append(("sweeps", sweep_block))
    next_step = next_step_line(verdict=verdict, det=det, prior=prior,
                               break_evens=break_evens)
    sections.append(("next step", [next_step] if next_step is not None else []))
    return sections


def read_back_lines(
    spec: ComparisonSpec,
    *,
    warnings: Sequence[str] = (),
    verdict: Optional[Verdict] = None,
    det: Optional[ComparisonDeterministicResult] = None,
    prior: Optional[LoadedScenarioPrior] = None,
    break_evens: Iterable[Dict[str, Any]] = (),
    sweeps: Iterable[Dict[str, Any]] = (),
    raw: Optional[Dict[str, Any]] = None,
    short: bool = False,
) -> List[str]:
    """Every line an honest answer has to carry, in one order, ready to paste.

    Order: the `[warning]` lines; the source classes the user did not state (or
    the one line saying no `sources:` block was declared); the `defaults
    applied:` line, so the numbers the ENGINE chose are named with their
    citations; the `rates:` line — the convention the typed rates were read
    under and each one in both forms, as quoted and in use; in nominal mode the
    `mode:` line, which names the discount rate stated and the rate in use
    (a real figure composed, or a quoted figure used as typed); the
    decisiveness rule;
    each option's financing line and its
    `purchase costs:` line; the year-1 cash view; each option's other-costs
    line with its citation or `no anchor match`; the affordability summary;
    each break-even's sentence, its re-solutions across a sweep, and the
    block's note; each sweep's flip lines; and, on a coin flip under a prior,
    the run that would resolve it.

    `short=True` (2026-09-05, the gist shape): the `[warning]` lines, the
    source lines and the `decisiveness:` line alone — a strict subsequence of
    the full block — closed by one line counting the lines the full block adds
    and naming their sections (`full read-back: <n> more lines (defaults
    applied, financing, …) — rerun with --read-back full`); no closing line
    when nothing was left out. Every warning reaches the user either way.
    """
    sections = _read_back_sections(
        spec, warnings=warnings, verdict=verdict, det=det, prior=prior,
        break_evens=break_evens, sweeps=sweeps, raw=raw,
    )
    if not short:
        return [line for _, lines in sections for line in lines]
    kept = [line for label, lines in sections if label in _SHORT_SECTIONS for line in lines]
    omitted = [(label, len(lines)) for label, lines in sections
               if label not in _SHORT_SECTIONS and lines]
    count = sum(n for _, n in omitted)
    if count:
        kept.append(f"full read-back: {count} more line{'s' if count != 1 else ''} "
                    f"({', '.join(label for label, _ in omitted)}) — rerun with --read-back full")
    return kept
