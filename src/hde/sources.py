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
from .anchors import ANCHORS
from .land_transfer_tax import anchor_families

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


def raw_value(data: Dict[str, Any], dotted: str) -> Any:
    """The value a dotted key holds in the raw YAML mapping."""
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
        return None, (
            f"sources: '{key}' declared anchor:{joined} but the config states "
            f"{stated!r} — an anchor sources a number, not {type(stated).__name__}"
        )

    window = max(match_window(a.name) for a in anchors)
    # A sum is checked against the sum of the published figures; a single
    # anchor also accepts its declared restatements (the same figure in the
    # convention the engine's key is stated in).
    candidates = ([sum(a.value for a in anchors)] if len(anchors) > 1
                  else list(anchors[0].stated_values()))
    if not any(abs(candidate - float(stated)) <= window for candidate in candidates):
        published = " + ".join(f"{a.value:g}" for a in anchors)
        if len(anchors) > 1:
            published += f" = {sum(a.value for a in anchors):g}"
        return None, (
            f"sources: '{key}' declared anchor:{joined} but the anchor's figure is "
            f"{published} and the config states {float(stated):g} — a declaration says "
            f"where the number CAME FROM, so the two have to be the same number "
            f"(uv run hde --print-anchors)"
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
                if key not in keys:
                    problems.append(_key_problem(data, str(key), keys))
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
    entries = []
    for key in keys:
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
    return SourceEcho(declared=declared, entries=tuple(entries),
                      uncertainty=tuple(details)), problems


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_LINE_LABELS = (("user", "user-stated"), ("assistant", "assistant-typed"),
                ("unattributed", "unattributed"))

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
    }


def unstated_uncertainty(echo: Optional[SourceEcho]) -> List[SourceEntry]:
    """Uncertainty inputs the user did not state (assistant-typed or unattributed)."""
    if echo is None:
        return []
    return [e for e in echo.uncertainty_entries()
            if e.source in ("assistant", "unattributed")]
