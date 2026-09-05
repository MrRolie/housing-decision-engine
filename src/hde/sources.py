"""Source classes for the values in a config — who put each number there.

The honesty problem this solves (dogfood rounds 1–7, 2026-09-03): a value the
ASSISTANT typed on the user's behalf is indistinguishable, in every surface the
engine emits, from a value the user stated. It is not `defaults applied` (the
YAML did state it), it fires no coherence warning, and it never reaches the
read-back. Five reviews of real answers found the same failure, and in three of
them the Monte Carlo "too close to call" verdict rested entirely on
assistant-typed volatility inputs the user never saw — with those off, the
deterministic line was decisive.

The remedy is an optional top-level ``sources:`` block mapping a dotted config
key to ``user`` / ``assistant`` / ``anchor:<registry name>``. It changes NO
computation: it is provenance for the echo and for one warning. Keys the block
omits are echoed as ``unattributed`` — silence is reported, never inferred.

Import-light on purpose (anchors only): ``models`` imports the echo type, so
nothing here may import ``models`` or ``config``.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .anchors import ANCHORS, match_window
from .land_transfer_tax import anchor_families
from .rates import RateConventionError, deflate, is_convertible, resolve_convention

# The three declarable classes. `unattributed` is not declarable — it is what
# the echo calls a config key no `sources:` entry covers.
SOURCE_CLASSES: Tuple[str, ...] = ("user", "assistant", "anchor")

_VALUE_FORMS = ("'user', 'assistant' or 'anchor:<anchor name>' — and "
                "'anchor:<name>+<name>' when the value is the sum of two "
                "published figures, e.g. 'anchor:property_tax.laval+school_tax.qc'")


# ---------------------------------------------------------------------------
# Attributable keys: the leaves of the raw YAML
# ---------------------------------------------------------------------------

def attributable_keys(data: Dict[str, Any]) -> List[str]:
    """Dotted names of every VALUE the config states, in config order.

    A leaf is a scalar or a list (``house.events`` is attributed as one thing —
    the user either supplied that list or did not). A mapping is a container,
    not a value, so ``condo`` is not attributable; its leaves are.
    """
    out: List[str] = []

    def walk(prefix: str, block: Dict[str, Any]) -> None:
        for key, value in block.items():
            dotted = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                walk(dotted, value)
            else:
                out.append(dotted)

    for key, value in data.items():
        if key == "sources":
            continue  # the block describes the config; it is not part of it
        if isinstance(value, dict):
            walk(key, value)
        else:
            out.append(key)
    return out


# ---------------------------------------------------------------------------
# Lines declared by NAME: `<option>.other_recurring_costs.<line name>.<leaf>`
#
# The list is one attributable thing, and an anchor sources a number — so the
# property-tax and insurance lines, the two largest unsourced figures in a
# typical run, could carry no anchor at all (2026-09-04: an $813 insurance
# line that IS the StatCan figure echoed as `unattributed`). The named-leaf
# form reaches one line's `annual_amount` or `escalation_rate`. These keys are
# NOT in `attributable_keys`: the list stays one entry until a line is named,
# so an undeclared config does not sprout an entry per leaf.
# ---------------------------------------------------------------------------

_LINE_LIST = "other_recurring_costs"
_LINE_LEAVES = ("annual_amount", "escalation_rate")
# Anchor families stated as a rate on value: a dollar line compares to them as
# amount ÷ initial_value — the read-back matcher's own probe.
_RATE_ON_VALUE = ("property_tax.", "school_tax.")


def _split_line_key(key: str) -> Optional[Tuple[str, str, str]]:
    """(option, line name, leaf) for the named-line form, else None. The name
    is whatever sits between the fixed prefix and the leaf suffix, so a name
    with dots or spaces in it (`property tax (0.55% of value)`) resolves."""
    for option in ("condo", "house", "rent"):
        prefix = f"{option}.{_LINE_LIST}."
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        for leaf in _LINE_LEAVES:
            suffix = f".{leaf}"
            if rest.endswith(suffix) and len(rest) > len(suffix):
                return option, rest[:-len(suffix)], leaf
    return None


def _lines_of(data: Dict[str, Any], option: str) -> List[Dict[str, Any]]:
    block = data.get(option)
    lines = block.get(_LINE_LIST) if isinstance(block, dict) else None
    if not isinstance(lines, list):
        return []
    return [line for line in lines if isinstance(line, dict)]


def line_keys(data: Dict[str, Any], option: str) -> List[str]:
    """The named-line keys one option's list states, in config order — one
    per leaf each line actually sets. A name two lines share is not a key at
    all: it cannot say which line it means, and `_line_problem` says so."""
    lines = _lines_of(data, option)
    names = [str(line["name"]) for line in lines if "name" in line]
    out: List[str] = []
    for line in lines:
        if "name" not in line or names.count(str(line["name"])) > 1:
            continue
        for leaf in _LINE_LEAVES:
            if leaf in line:
                out.append(f"{option}.{_LINE_LIST}.{line['name']}.{leaf}")
    return out


def _line_problem(data: Dict[str, Any], key: str, option: str,
                  line_name: str, leaf: str) -> str:
    """Why a named-line key cannot be declared — always naming what exists."""
    lines = _lines_of(data, option)
    if not lines:
        return f"sources: '{key}' — {option} has no other_recurring_costs lines"
    named = [line for line in lines if str(line.get("name")) == line_name]
    if not named:
        existing = ", ".join(repr(str(line.get("name"))) for line in lines)
        return (f"sources: '{key}' names no line — {option}.{_LINE_LIST} has lines "
                f"named {existing}")
    if len(named) > 1:
        return (f"sources: two {option}.{_LINE_LIST} lines are named {line_name!r} — "
                f"give each a distinct name to declare one")
    return (f"sources: '{key}' — the line {line_name!r} does not state {leaf} (the "
            f"engine's default applies), so it has no source to declare")


def raw_value(data: Dict[str, Any], dotted: str) -> Any:
    """The value a dotted key holds in the raw YAML mapping — a named line's
    leaf, or the plain walk."""
    split = _split_line_key(dotted)
    if split is not None:
        option, line_name, leaf = split
        named = [line for line in _lines_of(data, option)
                 if str(line.get("name")) == line_name]
        if len(named) == 1 and leaf in named[0]:
            return named[0][leaf]
    node: Any = data
    for part in dotted.split("."):
        node = node[part]
    return node


# ---------------------------------------------------------------------------
# Presentation: the config's own units
# ---------------------------------------------------------------------------

_MONTHLY_MONEY = frozenset({"monthly_rent", "monthly_fee"})
_MONEY = frozenset({
    "initial_value", "down_payment", "cash_available", "purchase_costs",
    "financed_purchase_costs", "invested_down_payment", "annual_income",
    "reserve_initial_balance", "annual_amount", "base_cost",
})
_COUNTS = frozenset({"years", "num_sims", "random_seed"})
_FRACTIONS = frozenset({"severity_mean", "magnitude"})


def _number(value: Any) -> str:
    if isinstance(value, float) and value != int(value):
        return f"{value:g}"
    return f"{int(value):,}"


def format_source_value(key: str, value: Any) -> str:
    """One config value, in the units the config states it in.

    Deliberately NOT `serialization.echo_value`: that one formats the SPEC's
    resolved defaults (every one of which is a rate or a mode), while a source
    entry can be any typed key — dollars, counts, flags, a list of events.
    """
    leaf = key.rsplit(".", 1)[-1]
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return f"{len(value)} entry" if len(value) == 1 else f"{len(value)} entries"
    if isinstance(value, str):
        return repr(value)
    if value is None:
        return "null"
    if leaf in _MONTHLY_MONEY:
        return f"${value:,.0f}/mo"
    if leaf in _MONEY:
        return f"${value:,.0f}"
    if leaf in _COUNTS or leaf.endswith(("_year", "_years")):
        return _number(value)
    if leaf.endswith(("_rate", "_vol", "_hazard", "_threshold")) or leaf in _FRACTIONS:
        return f"{value:.1%}"
    return _number(value)


# ---------------------------------------------------------------------------
# Uncertainty inputs: what widens the Monte Carlo distribution
# ---------------------------------------------------------------------------
#
# This list MIRRORS `config.single_path_run` — the engine's own definition of
# "a path draws something". A test pins the mirror: turn off every key named
# here and `single_path_run` must be True, so the warning cannot miss an input
# the engine treats as uncertainty.

_SIM_VOLS = ("house_maintenance_vol", "condo_fee_vol", "other_cost_vol",
             "rent_escalation_vol", "investment_return_vol")
_EVENT_WIDENERS = ("timing_std_years", "cost_vol", "hazard_base", "hazard_growth")
_DROP_WIDENERS = ("year_jitter_std", "magnitude_vol")


def _nonzero(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0


def _entry_detail(entries: Sequence[Any], fields: Sequence[str],
                  hazard_only: Sequence[str] = ()) -> Optional[str]:
    """Which sub-fields of a list input do the widening, and with what value —
    a bare '1 entry' cannot tell the user WHAT in the list draws."""
    found: List[str] = []
    for name in fields:
        for entry in entries:
            if not isinstance(entry, dict) or not _nonzero(entry.get(name)):
                continue
            if name in hazard_only and entry.get("timing_model") != "hazard":
                continue
            found.append(f"{name} {format_source_value(name, entry[name])}")
            break
    return ", ".join(found) if found else None


def uncertainty_inputs(data: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """(dotted key, detail) for every stated input that widens the distribution."""
    out: List[Tuple[str, Optional[str]]] = []
    sim = data.get("simulation")
    if isinstance(sim, dict):
        for key in _SIM_VOLS:
            if _nonzero(sim.get(key)):
                out.append((f"simulation.{key}", None))
    econ = data.get("economic")
    if isinstance(econ, dict) and _nonzero(econ.get("inflation_vol")):
        out.append(("economic.inflation_vol", None))
    for option in ("condo", "house", "rent"):
        block = data.get(option)
        if not isinstance(block, dict):
            continue
        shock = block.get("price_shock")
        if isinstance(shock, dict) and _nonzero(shock.get("annual_hazard")):
            for sub in ("annual_hazard", "severity_mean", "severity_vol"):
                if sub in shock:
                    out.append((f"{option}.price_shock.{sub}", None))
        events = block.get("events")
        if isinstance(events, list):
            detail = _entry_detail(events, _EVENT_WIDENERS,
                                   hazard_only=("hazard_base", "hazard_growth"))
            if detail:
                out.append((f"{option}.events", detail))
    income = data.get("income")
    if isinstance(income, dict) and isinstance(income.get("pay_drop_events"), list):
        detail = _entry_detail(income["pay_drop_events"], _DROP_WIDENERS)
        if detail:
            out.append(("income.pay_drop_events", detail))
    scenario = data.get("market_scenario")
    if isinstance(scenario, dict):
        # The prior draws demographic drift per path (single_path_run says so).
        for key in ("path", "geography"):
            if key in scenario:
                out.append((f"market_scenario.{key}", None))
    return out


def uncertainty_keys(data: Dict[str, Any]) -> List[str]:
    """Just the dotted keys of `uncertainty_inputs`."""
    return [key for key, _ in uncertainty_inputs(data)]


# ---------------------------------------------------------------------------
# The echo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceEntry:
    """One stated config value and who put it there."""
    key: str
    value: Any
    formatted: str
    source: str                      # user | assistant | anchor | unattributed
    anchor: Optional[str] = None     # registry name when source == 'anchor'
    detail: Optional[str] = None     # widening sub-fields, for a list input


@dataclass(frozen=True)
class SourceEcho:
    """Every stated config value with its source class.

    `declared` is False when the config carries no `sources:` block at all —
    then every entry is `unattributed` and the echo says, in one line, that the
    read-back cannot tell the user's numbers from the assistant's.
    """
    declared: bool = False
    entries: Tuple[SourceEntry, ...] = ()
    uncertainty: Tuple[str, ...] = ()

    def classify(self, key: str) -> Optional[str]:
        entry = self.get(key)
        return entry.source if entry is not None else None

    def anchor_name(self, key: str) -> Optional[str]:
        entry = self.get(key)
        return entry.anchor if entry is not None else None

    def get(self, key: str) -> Optional[SourceEntry]:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None

    def of_class(self, source: str) -> List[SourceEntry]:
        return [e for e in self.entries if e.source == source]

    def uncertainty_entries(self) -> List[SourceEntry]:
        """The uncertainty inputs, in the order the detector found them."""
        return [e for key in self.uncertainty
                for e in [self.get(key)] if e is not None]


def _is_container(data: Dict[str, Any], dotted: str) -> bool:
    """True when the key IS set but holds a block rather than a value."""
    try:
        return isinstance(raw_value(data, dotted), dict)
    except (KeyError, TypeError):
        return False


def _key_problem(data: Dict[str, Any], key: str, known: Sequence[str]) -> str:
    if _is_container(data, key):
        leaves = [k for k in known if k.startswith(f"{key}.")][:3]
        example = ", ".join(leaves) if leaves else "its leaf keys"
        return (f"sources: '{key}' is a block, not a value — declare its leaves "
                f"({example}, …)")
    close = difflib.get_close_matches(key, sorted(known), n=1, cutoff=0.6)
    message = (f"sources: '{key}' is not a value this config states — a source "
               f"can only be declared for a key the config sets")
    if close:
        message += f"; did you mean '{close[0]}'?"
    return message


def _value_problem(key: str, value: Any) -> str:
    return f"sources: invalid source {value!r} for '{key}' — expected {_VALUE_FORMS}"


def _anchor_problem(key: str, name: str) -> str:
    close = difflib.get_close_matches(name, sorted(ANCHORS), n=1, cutoff=0.6)
    message = (f"sources: unknown anchor '{name}' for '{key}' — not in the "
               f"provenance registry (uv run hde --print-anchors)")
    if close:
        message += f"; did you mean '{close[0]}'?"
    return message


def _sibling_hint(data: Dict[str, Any], joined: str) -> str:
    """The one case where the registry holds a sibling anchor that DOES publish
    the figure a refused declaration states: `economic.inflation_rate` is the
    inert 0.0, while `economic.inflation_rate.nominal_planning` is the 2.1%
    planning figure a config means — in nominal mode, and in real mode where it
    deflates the rates typed as quoted (2026-09-04 review — the refusal was
    correct and left the user to find the sibling by hand).
    """
    if joined != "economic.inflation_rate":
        return ""
    sibling = ANCHORS["economic.inflation_rate.nominal_planning"]
    return (f". The planning figure is the sibling anchor "
            f"'{sibling.name}' ({sibling.value:.1%}) — declare that one")


def _anchor_declaration(
    data: Dict[str, Any], key: str, declaration: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Validate one `anchor:<name>` (or `anchor:<a>+<b>`) declaration against
    the value it claims to source. Returns (registry name(s), problem).

    BY NAME IS NOT ENOUGH (2026-09-04). A config declared
    `anchor:property_tax.quebec_city` on a 0.82539% rate — the anchor publishes
    0.7464% — and the same read-back printed "anchor-sourced" beside "no anchor
    match" for the one number. A name-only check lets a declaration claim
    provenance the figure does not have, which is worse than declaring nothing:
    it dresses an estimate as a citation. So the stated value must EQUAL the
    anchor's figure, within the same window the read-back matcher uses.

    The `+` form is for a value that is the sum of two anchors — a Québec
    owner's property-tax rate is the municipal rate plus the province's school
    rate — and is checked against the sum.
    """
    parts = [part.strip() for part in declaration[len("anchor:"):].split("+")]
    if not all(parts):
        return None, _value_problem(key, declaration)
    for name in parts:
        if name not in ANCHORS:
            return None, _anchor_problem(key, name)
    joined = "+".join(parts)
    anchors = [ANCHORS[name] for name in parts]

    unsourced = [a for a in anchors if a.value is None]
    if unsourced:
        return None, (
            f"sources: '{key}' declared anchor:{joined} — '{unsourced[0].name}' is a "
            f"'source: none' entry and holds no figure, so it cannot be the source of "
            f"a number (uv run hde --print-anchors)"
        )

    stated = raw_value(data, key)
    if isinstance(stated, bool) or not isinstance(stated, (int, float)):
        hint = ""
        if isinstance(stated, list) and key.endswith(f".{_LINE_LIST}"):
            hint = f" — declare the line by name: {key}.<line name>.annual_amount"
        return None, (
            f"sources: '{key}' declared anchor:{joined} but the config states "
            f"{stated!r} — an anchor sources a number, not {type(stated).__name__}{hint}"
        )

    # The figure the anchors are compared with, in THEIR units. A dollar tax
    # line against a rate on value compares as amount ÷ initial_value — the
    # same probe the other-costs read-back uses, so a line it cites is a line
    # this accepts, and a line it does not cite is refused here too.
    figure = float(stated)
    figure_text = f"{figure:g}"
    split = _split_line_key(key)
    if (split is not None and split[2] == "annual_amount"
            and all(a.name.startswith(_RATE_ON_VALUE) for a in anchors)):
        option = split[0]
        block = data.get(option)
        price = block.get("initial_value") if isinstance(block, dict) else None
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
            return None, (
                f"sources: '{key}' declared anchor:{joined} — a rate on assessed value "
                f"is compared with a dollar line as amount ÷ initial_value, and {option} "
                f"states no initial_value"
            )
        figure = float(stated) / float(price)
        figure_text = f"${float(stated):,.0f} = {figure:g} of initial_value"

    window = max(match_window(a.name) for a in anchors)
    # A sum is checked against the sum of the published figures; a single
    # anchor also accepts its declared restatements (the same figure in the
    # convention the engine's key is stated in).
    candidates = ([sum(a.value for a in anchors)] if len(anchors) > 1
                  else list(anchors[0].stated_values()))
    matched = any(abs(candidate - figure) <= window for candidate in candidates)
    published = " + ".join(f"{a.value:g}" for a in anchors)
    if len(anchors) > 1:
        published += f" = {sum(a.value for a in anchors):g}"
    # A typed growth, escalation, return or discount rate is AS QUOTED unless
    # the config declares `rates: real` (2026-09-05), and the anchor's figure
    # is real. So the comparison runs in the anchor's convention: the typed
    # figure DEFLATED by inflation_rate against the anchor's real value, or the
    # typed figure itself against the anchor's quoted restatements — never the
    # quoted figure against the real value, which is the double count this
    # convention exists to stop.
    if len(anchors) == 1 and is_convertible(key):
        try:
            rates, _, pi = resolve_convention(data)
        except RateConventionError:
            rates = "real"  # the loader refuses the `rates:` value itself
        if rates == "as_quoted":
            anchor = anchors[0]
            real = deflate(figure, pi)
            restated = [v for v, _ in anchor.restatements]
            matched = (abs(anchor.value - real) <= window
                       or any(abs(v - figure) <= window for v in restated))
            figure_text = (f"{figure:g} as quoted = {real:.6g} real after {pi:.1%} "
                           f"inflation_rate")
            published = f"{anchor.value:g} real" + (
                f" ({', '.join(f'{v:g}' for v in restated)} as quoted)" if restated else "")
    if not matched:
        return None, (
            f"sources: '{key}' declared anchor:{joined} but the anchor's figure is "
            f"{published} and the config states {figure_text} — a declaration says "
            f"where the number CAME FROM, so the two have to be the same number "
            f"(uv run hde --print-anchors)"
            + _sibling_hint(data, joined)
        )
    return joined, None


# ---------------------------------------------------------------------------
# Derived attributions: a value the ENGINE looked up
# ---------------------------------------------------------------------------
#
# `land_transfer_tax: auto` is not a figure the user or the assistant typed —
# it is a directive to read the anchored schedule, so the echo attributes it to
# the registry it was read from. A `sources:` entry the user DID declare still
# wins: their statement about their own config is never overwritten.

def _derived_anchor_sources(data: Dict[str, Any]) -> Dict[str, Tuple[str, str]]:
    out: Dict[str, Tuple[str, str]] = {}
    top_province = data.get("province")
    for option in ("condo", "house"):
        block = data.get(option)
        if not isinstance(block, dict):
            continue
        setting = block.get("land_transfer_tax")
        if not (isinstance(setting, str) and setting.strip().lower() == "auto"):
            continue
        province = block.get("province", top_province)
        if isinstance(province, str):
            province = province.strip().upper()
        municipality = block.get("municipality")
        if isinstance(municipality, str):
            municipality = municipality.strip().lower()
        families = anchor_families(province, municipality)
        if families:
            out[f"{option}.land_transfer_tax"] = (
                "anchor", " + ".join(f"{f}.*" for f in families))
    return out


def build_source_echo(data: Dict[str, Any]) -> Tuple[SourceEcho, List[str]]:
    """Parse `sources:` against the config it describes.

    Returns the echo and a list of refusal messages (the caller raises, so this
    module stays free of the config exception type).
    """
    problems: List[str] = []
    keys = attributable_keys(data)
    named = {option: line_keys(data, option) for option in ("condo", "house", "rent")}
    all_named = [key for option_keys in named.values() for key in option_keys]
    declared_map: Dict[str, Tuple[str, Optional[str]]] = {}
    declared = "sources" in data

    if declared:
        block = data["sources"]
        if not isinstance(block, dict):
            problems.append(
                f"sources: must be a mapping of dotted config key → {_VALUE_FORMS}, "
                f"got {type(block).__name__}"
            )
            declared = False
        else:
            for key, value in block.items():
                key = str(key)
                if key not in keys and key not in all_named:
                    split = _split_line_key(key)
                    problems.append(_line_problem(data, key, *split) if split is not None
                                    else _key_problem(data, key, keys + all_named))
                    continue
                if not isinstance(value, str):
                    problems.append(_value_problem(key, value))
                elif value in ("user", "assistant"):
                    declared_map[key] = (value, None)
                elif value.startswith("anchor:"):
                    name, problem = _anchor_declaration(data, key, value)
                    if problem is not None:
                        problems.append(problem)
                    else:
                        declared_map[key] = ("anchor", name)
                else:
                    problems.append(_value_problem(key, value))

    details = dict(uncertainty_inputs(data))
    derived = _derived_anchor_sources(data)
    entries: List[SourceEntry] = []

    def add(key: str) -> None:
        source, anchor = declared_map.get(key, derived.get(key, ("unattributed", None)))
        value = raw_value(data, key)
        entries.append(SourceEntry(
            key=key,
            value=value,
            formatted=format_source_value(key, value),
            source=source,
            anchor=anchor,
            detail=details.get(key),
        ))

    suffix = f".{_LINE_LIST}"
    for key in keys:
        option = key[:-len(suffix)] if key.endswith(suffix) else None
        if option in named and any(k in declared_map for k in named[option]):
            # A line was declared by name: the list is echoed per leaf — the
            # declared ones with their class, the rest `unattributed`, so
            # silence is still reported figure by figure — and the bare list
            # key only when it too was declared.
            if key in declared_map:
                add(key)
            for line_key in named[option]:
                add(line_key)
        else:
            add(key)
    return SourceEcho(declared=declared, entries=tuple(entries),
                      uncertainty=tuple(details)), problems


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_LINE_LABELS = (("user", "user-stated"), ("assistant", "assistant-typed"),
                ("unattributed", "unattributed"), ("sweep", "swept"))

NO_BLOCK_LINE = ("sources: none declared — the read-back cannot tell the user's "
                 "numbers from the assistant's")


def source_lines(echo: Optional[SourceEcho]) -> List[str]:
    """The assumption-block lines for the source echo (pure presentation)."""
    if echo is None or not echo.entries:
        return []
    if not echo.declared:
        return [NO_BLOCK_LINE]
    lines: List[str] = []
    for source, label in _LINE_LABELS:
        listed = echo.of_class(source)
        if listed:
            joined = ", ".join(f"{e.key}={e.formatted}" for e in listed)
            lines.append(f"{label}: {joined}")
    anchored = echo.of_class("anchor")
    if anchored:
        joined = ", ".join(f"{e.key}={e.formatted} [{e.anchor}]" for e in anchored)
        lines.append(f"anchor-sourced: {joined}")
    return lines


def source_echo_to_dict(echo: Optional[SourceEcho]) -> Dict[str, Any]:
    """The structured echo: `assumptions.sources` in the --json document."""
    def _list(source: str) -> List[Dict[str, Any]]:
        return [{"key": e.key, "value": e.value, "formatted": e.formatted}
                for e in (echo.of_class(source) if echo is not None else [])]

    return {
        "declared": bool(echo is not None and echo.declared),
        "user": _list("user"),
        "assistant": _list("assistant"),
        "anchor": {e.key: e.anchor for e in (echo.of_class("anchor") if echo else [])},
        "unattributed": _list("unattributed"),
        "sweep": _list("sweep"),
    }


def unstated_uncertainty(echo: Optional[SourceEcho]) -> List[SourceEntry]:
    """Uncertainty inputs the user did not state (assistant-typed or unattributed)."""
    if echo is None:
        return []
    return [e for e in echo.uncertainty_entries()
            if e.source in ("assistant", "unattributed")]
