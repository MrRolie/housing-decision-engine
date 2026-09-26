"""Every sentence the `--decompose` block prints, and a test of what it claims.

The block is built from sentence TEMPLATES: the lines `hde.decomposition_text`
writes, and the reason strings the assembler (`hde.decomposition_run`) and the
reversal register (`hde.break_even`) write for it. `LINES` holds every line
template as one pattern over one printed line; `REASONS` holds every
engine-written reason as one pattern over the reason string. The inventory is
closed in both directions:

  - every line the block prints on the renders below matches exactly one line
    template, and every reason in those runs' `--json` exactly one reason
    template;
  - every template is printed somewhere in them — or, for a reason only a
    patched seam can produce, names the test that produces it and checks its
    condition there.

Each template's CLAIM is checked where it prints: its figures and words
against the same run's `--json`, and what it says about the run — which side
of a threshold, which row is on top, what a larger run would do, what a draw
reaches — against the JSON's own fields, a second run, `--sweep`, the
read-back's source echo or the generators. The JSON's figures are re-derived
from the block's own matrices in `test_decomposition_contract_doc.py`, so a
printed sentence is tied to what is so by text -> JSON here and JSON ->
re-derivation there.

The renders: the shared corpus of real runs (`decomposition_runs.CORPUS`), a
config for each whole-block refusal, one run at a patched evaluation ceiling
(the only way to reach the spread register's own cap in test time), and the
hand-built households (`decomposition_households`), whose lines are checked
against their own serialized JSON and whose reason strings are test data.
"""
from __future__ import annotations

import copy
import dataclasses
import functools
import importlib
import math
import pathlib
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pytest
import yaml

import hde.break_even as be
import hde.decomposition as dc
import hde.decomposition_run as dr
import hde.decomposition_text as dt
from hde.anchors import ANCHORS
from hde.config import load_config_dict, single_path_run
from hde.decomposition_math import LEVEL_RESOLUTION_SIGMAS
from hde.deterministic import compute_deterministic
from hde.models import compute_verdict
from hde.monte_carlo import run_monte_carlo
from hde.rates import effective_mortgage_rate
from hde.serialization import decomposition_to_dict
from hde.sweep import _fmt_value

from tests import decomposition_households as hh
from tests.decomposition_runs import (
    _SCRATCH, CONDO_ONLY, EXAMPLES, FIXTURE, INCOME, MONTREAL, MORTGAGE, NO_REACH,
    REPO, _block_text, _cli, _load, _strict, _sweep_states, corpus, run)

BASIC = EXAMPLES / "basic_config.yaml"

# Two owners that price identically on every future: the market and the
# economy move both by the same factor, so the margin is one figure.
TWINS = {
    "years": 10, "discount_rate": 0.04,
    "economic": {"mode": "nominal", "inflation_rate": 0.02, "inflation_vol": 0.01},
    "condo": {"initial_value": 500000, "monthly_fee": 0, "fee_escalation_rate": 0.0,
              "all_cash": True, "value_growth_rate": 0.02},
    "house": {"initial_value": 500000, "all_cash": True, "value_growth_rate": 0.02,
              "annual_maintenance_rate": 0.0},
    "simulation": {"num_sims": 64, "random_seed": 3, "value_growth_vol": 0.06},
}

# The ceiling the capped run is priced under: small enough that the largest
# N it admits prices in well under a second.
CAPPED_CEILING = 2_000


# ---------------------------------------------------------------------------
# The renders
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Render:
    name: str
    text: str
    doc: Dict[str, Any]
    raw: Optional[Dict[str, Any]] = None       # the config, for a run of the engine
    path: Optional[pathlib.Path] = None
    extra: Tuple[str, ...] = ()
    source: Any = None                           # the corpus `Run`, when there is one
    ceiling: int = dr.EVALUATION_CEILING
    over: Optional["Render"] = None              # the run at one path more, when priced

    @property
    def engine(self) -> bool:
        return self.raw is not None

    @property
    def block(self) -> Dict[str, Any]:
        return self.doc["decomposition"]

    @property
    def verdict(self) -> Dict[str, Any]:
        return self.doc["verdict"]

    @functools.cached_property
    def spec(self):
        return load_config_dict(self.raw)


def _cli_render(name, source, *extra, ceiling=None):
    if isinstance(source, pathlib.Path):
        path, raw = source, _load(source)
    else:
        directory = pathlib.Path(_SCRATCH.name) / "sentences" / name
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "config.yaml"
        path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
        raw = copy.deepcopy(source)
    code, out, _ = _cli(path, "--decompose", *extra, "--json")
    assert code == 0, out
    doc = _strict(out)
    code, out, _ = _cli(path, "--decompose", *extra, "-q")
    assert code == 0
    return Render(name, _block_text(out), doc, raw=raw, path=path, extra=extra,
                  ceiling=dr.EVALUATION_CEILING if ceiling is None else ceiling)


REFUSALS = {
    "no_futures_two": (MONTREAL,),
    "no_futures_three": (FIXTURE, "--no-monte-carlo"),
    "no_futures_one": (CONDO_ONLY, "--no-monte-carlo"),
    "single_option": (CONDO_ONLY,),
    "one_channel": (INCOME,),
    "no_spread_unreached": (NO_REACH,),
    "no_spread_constant": (TWINS,),
    "budget": (FIXTURE, "30000"),
    "too_few": (MORTGAGE, "39"),
}


@functools.lru_cache(maxsize=None)
def _capped() -> Render:
    """basic_config at the largest N a patched ceiling admits, and the run at
    one path more, which that ceiling refuses."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dr, "EVALUATION_CEILING", CAPPED_CEILING)
        k = len(dr.live_channels(load_config_dict(_load(BASIC))))
        cap = dr.largest_affordable_paths(k)
        render = _cli_render("capped", BASIC, str(cap), ceiling=CAPPED_CEILING)
        render.over = _cli_render("capped_over", BASIC, str(cap + 1),
                                  ceiling=CAPPED_CEILING)
    return render


HOUSEHOLDS: Dict[str, Callable[[], Any]] = {
    "uncertainty_surface": hh.uncertainty_surface,
    "uncertainty_surface_resolved":
        lambda: hh.uncertainty_surface(interaction=hh.resolved_interaction()),
    "seven_channel": hh.seven_channel_other_household,
    "two_channel": hh.two_channel_option_state,
}


def _household(name) -> Render:
    outcome = HOUSEHOLDS[name]()
    doc = {"verdict": dataclasses.asdict(outcome.verdict),
           "decomposition": decomposition_to_dict(outcome)}
    return Render(name, dt.format_decomposition(outcome), doc)


@functools.lru_cache(maxsize=None)
def renders() -> Tuple[Render, ...]:
    out: List[Render] = []
    for name, got in corpus().items():
        out.append(Render(name, got.text, got.doc, raw=got.raw, path=got.path,
                          extra=got.extra, source=got))
    for name, (source, *extra) in REFUSALS.items():
        out.append(_cli_render(name, source, *extra))
    out.append(_capped())
    for name in HOUSEHOLDS:
        out.append(_household(name))
    return tuple(out)


# ---------------------------------------------------------------------------
# The line templates
# ---------------------------------------------------------------------------

# The words the block must print for each verdict field, each zero kind and
# each source class — written here, not read from the formatter, so a mapping
# changed there is caught here rather than agreed with.
FIELD_WORDS = {
    "best": "the central case's winner",
    "runner_up": "the runner-up",
    "mc_best": "the option most futures call cheapest",
    "decisive": "the decisiveness verdict",
}
DRAWN_WORDS = {
    "stated_path": "no draw touches it",
    "no_pv_reach": "drawn, and reaching no option's present value",
    "dead_draw": "drawn, and reaching no cash flow",
}
CLASS_WORDS = {
    "assistant": "the assistant chose",
    "unattributed": "that no sources: entry claims",
    "user": "you stated",
    "anchor": "anchor-sourced",
}

LABEL = "(?:" + "|".join(re.escape(c.label) for c in dc.CHANNELS) + ")"
OPTION = r"(?:condo|house|rent)"
BOUND = "(?:" + "|".join(re.escape(v) for v in FIELD_WORDS.values()) + ")"
STATE = r"(?:decisive for \w+|not decisive|condo|house|rent)"
SHARE = r"-?\d+\.\d+"
CI = rf"\[{SHARE}, {SHARE}\]"
MONEY = r"-?\$[\d,]+"
SHIFT = r"[+-]\$[\d,]+"
PROB = r"\d+\.\d+"
PCT = r"\d+\.\d+%"
N = r"[\d,]+"
DEV = r"\d\.\de[+-]\d+"

_SUM = rf"the first-order shares add to (?P<sum>{SHARE}) (?P<sum_ci>{CI})"
_WHERE = (r"(?P<where>above 1 across its whole interval, which is estimator noise: "
          r"first-order shares cannot add to more than the whole|an interval that reaches 1)")
_FIG = (rf"(?P<label>{LABEL}) at (?P<delta>{SHIFT}) ± (?P<se>\$[\d,]+) "
        rf"\(P\((?P<best>{OPTION}) cheapest\) -> (?P<p>{PROB}) priced the central case's way\)")
_SO = (r"(?P<so>this register cannot name a channel to check before trusting the tie"
       r"|this run cannot say which channel puts the central case and the futures on "
       r"different winners|this run cannot say which one the futures price and the "
       r"central case does not)")
_HEAD = r"(?P<head>moving it |replacing that path with one flat rate, )"
_BRACKET = rf"inside a (?P<lo>{PCT})–(?P<hi>{PCT}) bracket \[(?P<src>\w+)\]"
_CROSS = (rf"        as it rises past (?P<value>{{value}}), (?P<field>{BOUND}) changes from "
          rf"(?P<was>{STATE}) to (?P<becomes>{STATE})(?: \(further changes lie "
          rf"(?P<further>above|below) it inside the searched range; this row reports the "
          rf"nearest\))?")
_CROSS_SOLVED = _CROSS.format(value=r"\d+\.\d{4}%")
_CROSS_SAMPLED = _CROSS.format(value=r"\d+\.\d{2}%")

LINES: Dict[str, "re.Pattern"] = {name: re.compile(pattern) for name, pattern in {
    "BLANK": r"^$",
    "HEADER": rf"^which risk decides it — (?P<paths>{N}) futures, (?P<live>\d+) channels live$",
    "REFUSAL": (rf"^(?:which risk decides it|(?P<label>{LABEL}) (?:carries|carry) all of "
                rf"this run's spread) — not split: (?P<reason>.+)$"),
    "VERDICT": r"^  (?P<reason>.*\[hde verdict rule\].*)$",
    "CENTRAL": (rf"^  the central case says (?P<best>{OPTION}) by (?P<margin>{MONEY}); across "
                rf"this block's own (?P<paths>{N}) futures, not the run's Monte Carlo "
                rf"sample, that margin averages (?P<mean>{MONEY})(?: \((?P<side>above|below) "
                rf"zero: on average (?P<best2>{OPTION}) costs (?P<cmp>less|more) than the "
                rf"cheapest other option\))? and scatters by (?P<sd>{MONEY}) \(1 s\.d\.\)"
                rf"(?: — (?P<ratio>\d+\.\d+)x the margin itself)?$"),
    "SPREAD_HEAD": rf"^  THE SPREAD — where the (?P<sd>{MONEY}) comes from$",
    "SPREAD_REFUSED": r"^  (?P<reason>no share is apportioned: .+)$",
    "SPREAD_COLS": (rf"^  channel +alone +with interaction +flips whether "
                    rf"(?P<best>{OPTION}) is cheapest$"),
    "SPREAD_ROW": (rf"^  (?P<label>{LABEL}) +(?:(?P<unresolved>not resolved +not resolved)"
                   rf"|(?P<alone>{SHARE}) (?P<alone_ci>{CI}) +(?P<both>{SHARE}) "
                   rf"(?P<both_ci>{CI})) +(?P<flip>{PCT} \[\d+\.\d+, \d+\.\d+\])$"),
    "PROVISIONAL": (rf"^      (?P<alone>{SHARE}) (?P<alone_ci>{CI}) alone and "
                    rf"(?P<both>{SHARE}) (?P<both_ci>{CI}) with interaction, at "
                    rf"(?P<paths>{N}) futures$"),
    "WIDTHS": r"^      sized by (?P<cells>.+)$",
    "INTERACTION_RESOLVED": (rf"^  {_SUM}, leaving (?P<res>{SHARE}) (?P<res_ci>{CI}) that "
                             rf"no single channel owns(?:; (?P<unstated>{SHARE}) of the "
                             rf"shares above is a sum over channels sized entirely by "
                             rf"figures the assistant chose)?$"),
    "INTERACTION_NONE": (rf"^  {_SUM} — {_WHERE}, so no residual is printed; no channel's "
                         rf"with-interaction figure resolves above its alone figure "
                         rf"either, so interaction is not measurable at (?P<paths>{N}) "
                         rf"futures; (?P<route>.+)$"),
    "INTERACTION_SOME": (rf"^  {_SUM} — {_WHERE}, so no residual is printed; interaction "
                         rf"does resolve, as a with-interaction figure above its alone "
                         rf"figure: (?P<named>.+)$"),
    "SPREAD_TOP_UNRESOLVED": (rf"^  the largest share is on (?P<label>{LABEL}): "
                              rf"(?P<alone>{SHARE}) (?P<alone_ci>{CI}) alone, not resolved "
                              rf"at (?P<paths>{N}) futures — so no channel leads this "
                              rf"table; (?P<route>.+)$"),
    "SPREAD_TWO_FIGURES": (rf"^  on (?P<label>{LABEL}) the two figures are different kinds "
                           rf"of number: (?P<alone>{SHARE}) of the spread's variance, "
                           rf"(?P<flip>{PCT}) of the futures flipping whether "
                           rf"(?P<best>{OPTION}) is cheapest \[(?P<glossary>[^\]]+)\]$"),
    "LEVEL_HEAD": (rf"^  THE LEVEL — what (?P<m>{N}) of these futures price that the "
                   rf"central case does not: a cost or saving it leaves out, not a risk$"),
    "LEVEL_COLS": (rf"^  channel +the margin moves by \(± 1 s\.e\.\) "
                   rf"P\((?P<best>{OPTION}) cheapest\), from (?P<p>{PROB})$"),
    "LEVEL_ROW": (rf"^  (?P<label>{LABEL}) +(?P<delta>{SHIFT}) \(± (?P<se>\$[\d,]+)\) +-> "
                  rf"(?P<p>{PROB})$"),
    "LEVEL_FLAT": (rf"^  within (?P<k>\d+) s\.e\. of zero, so indistinguishable from it "
                   rf"at (?P<m>{N}) futures: (?P<cells>.+)$"),
    "LEVEL_GAP": (rf"^  on its own (?P<m>{N}) paths: the central case (?P<best>{OPTION}) by "
                  rf"(?P<frozen>{MONEY}), the futures (?P<futures>{MONEY}), a "
                  rf"(?P<gap>{MONEY}) gap of which these (?P<n>\d+) shifts account for "
                  rf"(?P<sum>{MONEY}); every channel frozen reproduces the central case to "
                  rf"within (?P<dev>{DEV}) dollars$"),
    "LEVEL_TOP_SOME": (rf"^  (?P<tie>this run is too close to call as drawn, and )?the "
                       rf"largest shift by point estimate, {_FIG}, does not resolve at "
                       rf"(?P<m>{N}) futures — so {_SO}; (?P<route>.+)$"),
    "LEVEL_TOP_NONE": (rf"^  (?P<tie>this run is too close to call as drawn, and )?no "
                       rf"channel's shift resolves at (?P<m>{N}) futures, the largest by "
                       rf"point estimate included: {_FIG} — so {_SO}; (?P<route>.+)$"),
    "LEVEL_CLOSE_DISAGREE": (rf"^  (?P<label>{LABEL})(?: \((?P<share>{SHARE}) of the "
                             rf"spread\))? (?:moves|move) the margin by (?P<delta>{SHIFT}), "
                             rf"and pricing it the central case's way takes "
                             rf"P\((?P<best>{OPTION}) cheapest\) to (?P<p>{PROB})"
                             rf"(?P<because> — that channel is why the central case and "
                             rf"the futures name different winners)?$"),
    "LEVEL_CLOSE_TIE": (rf"^  this run is too close to call as drawn, and the largest "
                        rf"single shift is (?P<label>{LABEL})(?: \((?P<share>{SHARE}) of the "
                        rf"spread\))?, (?P<delta>{SHIFT}), taking P\((?P<best>{OPTION}) "
                        rf"cheapest\) to (?P<p>{PROB}) — the channel to check before "
                        rf"trusting the tie$"),
    "LEVEL_CLOSE_OPTION": (rf"^  (?:(?P<either>{OPTION}) is cheapest either way, and the "
                           rf"largest shift is|the largest shift is) (?P<label>{LABEL})"
                           rf"(?: \((?P<share>{SHARE}) of the spread\))?, "
                           rf"(?P<delta>{SHIFT}): with it priced the central case's way "
                           rf"P\((?P<best>{OPTION}) cheapest\) is (?P<p>{PROB}) against "
                           rf"(?P<p0>{PROB}) as drawn(?: — (?P<fell>as drawn and priced that "
                           rf"way|as drawn|priced that way), (?P<best2>{OPTION}) is cheapest "
                           rf"in no more than half of these futures)?$"),
    "LEVEL_SIBLING": (rf"^  (?P<label>{LABEL}) (?:is|are) (?P<share>{SHARE}) of that spread "
                      rf"and (?:moves|move) the margin by nothing that resolves at "
                      rf"(?P<m>{N}) futures \((?P<delta>{SHIFT}) ± (?P<se>\$[\d,]+)\): "
                      rf"(?:it widens|they widen) the futures, and this run cannot tell "
                      rf"(?:its|their) shift from zero$"),
    "ZERO_HEAD": r"^  ZERO SPREAD BY CONSTRUCTION, NOT BY MEASUREMENT$",
    "ZERO_ROW": (r"^  (?P<label>[^—]+?) — (?P<keys>[\w.*]+(?:, [\w.*]+)*)"
                 r"(?: \((?P<stated>[^)]*)\))?, (?P<fact>no draw touches it|drawn, and "
                 r"reaching no option's present value|drawn, and reaching no cash flow): "
                 r"(?P<reason>.+)$"),
    "EXACT_HEAD": r"^  WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly$",
    "ESTIMATED_HEAD": r"^  WHAT WOULD HAVE TO CHANGE — keys the engine cannot re-price exactly$",
    "NO_DISTANCE": r"^  WHAT WOULD HAVE TO CHANGE — (?P<reason>(?!keys the engine ).+)$",
    "ROW_HEAD": (rf"^  (?P<key>[a-z_]+(?:\.[a-z_]+)+) \((?P<option>{OPTION})\), stated "
                 rf"(?P<stated>.+)$"),
    "STATED_BY": (r"^      (?P<words>you stated this (?P<w1>value|path)|the assistant typed "
                  r"this (?P<w2>value|path), not you|this (?P<w3>value|path) is "
                  r"anchor-sourced|no sources: entry says who typed this "
                  r"(?P<w4>value|path)) \[(?P<source>\w+)\]$"),
    "LICENCE": (rf"^      re-priced exactly: moving this key shifts (?P<option>{OPTION})'s "
                rf"present value by the same amount on every path \(to within "
                rf"(?P<dev>{DEV}) of its s\.d\., over (?P<probe>{N}) probe paths\) and "
                rf"leaves every other option's untouched$"),
    "GATE_REFUSED": (r"^      the exactness gate refused this key(?:; (?P<measured>.+?))? — so "
                     r"(?P<then>each distance below is located by re-simulating, inside an "
                     r"interval|no distance on it is solved or estimated in this run)$"),
    "GROUP_SOLVED": rf"^      {_HEAD}{_BRACKET} — solved on the central case:$",
    "GROUP_SAMPLED": rf"^      {_HEAD}{_BRACKET}, bisected on the futures rather than solved:$",
    "GROUP_SAMPLED_AFTER": r"^      on the same axis, bisected on the futures rather than solved:$",
    "GROUP_ESTIMATED": rf"^      {_HEAD}{_BRACKET}:$",
    "CROSS_SOLVED": (rf"^{_CROSS_SOLVED}"
                     rf"(?: — re-simulated there: (?P<probs>.+))?$"),
    "CROSS_SAMPLED": (rf"^{_CROSS_SAMPLED}(?:, where the futures sit "
                      rf"at (?P<probs>.+?))? — bisected on (?P<paths>{N}) paths at seed "
                      rf"(?P<seed>\d+), so the crossing moves with the seed$"),
    "CROSS_ESTIMATED": (rf"^        as it rises past (?P<value>\d+\.\d{{2}}%) \(inside "
                        rf"(?P<lo>{PCT})–(?P<hi>{PCT}) on (?P<n>{N}) re-simulated paths\), "
                        rf"(?P<field>{BOUND}) changes from (?P<was>{STATE}) to "
                        rf"(?P<becomes>{STATE})(?: \(further changes lie (?P<further>above|"
                        rf"below) it inside the searched range; this row reports the "
                        rf"nearest\))?$"),
    "NO_BOUNDARY": rf"^      no boundary solved {_BRACKET}$",
    "PATH_NOTE": (r"^      (?P<note>the config states (?P<key>[\w.]+) as a path "
                  r"\((?P<stated>[^)]+)\); every grid point replaces the whole path with "
                  r"ONE figure applied at each renewal, so the threshold reported is a flat "
                  r"renewal rate rather than the rate at the next renewal, and the stated "
                  r"path is not a point on this grid)$"),
    "REFUSED_BOUNDARY": (rf"^      no boundary printed for (?P<fields>{BOUND}(?:(?:, | or )"
                         rf"{BOUND})*) — (?P<reason>.+)$"),
    "REFERENCES": r"^      on the same axis: (?P<refs>.+)$",
    "PROVENANCE": (rf"^  the (?P<n>\d+) inputs? sizing the channels above: (?P<parts>.+?) — "
                   rf"so this ranking rests (?P<extent>entirely|partly) on inputs not "
                   rf"marked as yours or an anchor's(?: — check first what sizes "
                   rf"(?P<leader>{LABEL}), the table's leading row: (?P<cells>.+))?$"),
    "LICENSED": (rf"^  (?P<label>{LABEL}) (?:decides|decide) the spread of this answer, "
                 rf"and every width behind that row is yours or an anchor's$"),
}.items()}


# ---------------------------------------------------------------------------
# Reading a render line by line, with what each line is about
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Line:
    render: Render
    template: str
    m: "re.Match"
    section: str
    spread_row: Optional[Dict[str, Any]]
    reversal_row: Optional[Dict[str, Any]]
    zero: Optional[Dict[str, Any]]


def _hits(text):
    return [(name, pattern.match(text)) for name, pattern in LINES.items()
            if pattern.match(text)]


def _by_label(rows, label):
    return next(r for r in rows if r["label"] == label)


@functools.lru_cache(maxsize=None)
def _lines(render: Render) -> Tuple[Line, ...]:
    out: List[Line] = []
    section, spread_row, reversal_row, zero = "head", None, None, None
    block = render.block
    for text in render.text.splitlines():
        hits = _hits(text)
        assert len(hits) == 1, (render.name, text, [h[0] for h in hits])
        name, m = hits[0]
        if name == "SPREAD_HEAD":
            section = "spread"
        elif name == "SPREAD_ROW":
            spread_row = _by_label(block["spread"]["rows"], m["label"])
        elif name == "LEVEL_HEAD":
            section = "level"
        elif name == "ZERO_HEAD":
            section = "zero"
        elif name == "ZERO_ROW":
            zero = next(z for z in block["reversal"]["structural_zeros"]
                        if z["label"] == m["label"] and ", ".join(z["keys"]) == m["keys"])
            reversal_row = next((r for r in block["reversal"]["exact"]
                                 if r["key"] == zero["reversal_key"]), None)
        elif name == "EXACT_HEAD":
            section = "exact"
        elif name == "ESTIMATED_HEAD":
            section = "estimated"
        elif name == "ROW_HEAD":
            reversal_row = next(r for r in block["reversal"][section] if r["key"] == m["key"])
        elif name == "NO_DISTANCE":
            section = "empty"
        elif name in ("PROVENANCE", "LICENSED"):
            section = "tail"
        out.append(Line(render, name, m, section, spread_row, reversal_row, zero))
    return tuple(out)


Render.__hash__ = lambda self: hash(self.name)   # cached per render, by name


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------

def _whole(text: str) -> int:
    return int(text.replace(",", "").replace("$", ""))


def _ci(node) -> dc.Interval:
    return dc.Interval(node["low"], node["high"])


def _point(row) -> float:
    return row["alone"] if row["resolved"] else row["provisional_alone"]


def _together(row) -> float:
    return row["with_interaction"] if row["resolved"] else row["provisional_with_interaction"]


def _shift(row) -> float:
    return row["delta"] if row["resolved"] else row["provisional_delta"]


def _width_cells(widths) -> str:
    return "; ".join(dt._width_cell(dc.Width(**w)) for w in widths)


def _priced(raw) -> List[str]:
    return [o for o in ("condo", "house", "rent") if o in raw]


def _echo_class(doc, key) -> Optional[str]:
    """The class the read-back's source echo gives `key`."""
    echo = doc["assumptions"]["sources"]
    for source in ("user", "assistant", "unattributed", "sweep"):
        if any(entry["key"] == key for entry in echo.get(source) or ()):
            return source
    return "anchor" if key in (echo.get("anchor") or {}) else None


def _held(overrides=None):
    seeds = {c: 1000 + c for c in range(8)}
    seeds.update(overrides or {})
    return {c: np.random.default_rng(s) for c, s in seeds.items()}


def _pv_bytes(spec, overrides=None):
    mc = run_monte_carlo(spec, _held(overrides))
    return {o: np.asarray(getattr(mc, o).pvs).tobytes()
            for o in ("condo", "house", "rent") if getattr(mc, o) is not None}


def _moved_streams(spec):
    streams = _held()
    before = {c: g.bit_generator.state["state"]["state"] for c, g in streams.items()}
    run_monte_carlo(spec, streams)
    return {c for c, g in streams.items()
            if g.bit_generator.state["state"]["state"] != before[c]}


def _draws_and_reaches_nothing(spec, channel_id):
    """The channel's stream advances on this spec, and re-drawing it leaves
    every priced option's present value bit-identical."""
    small = dr._spec_at(spec, 40)
    assert channel_id in _moved_streams(small), channel_id
    assert _pv_bytes(small, {channel_id: 101}) == _pv_bytes(small, {channel_id: 202})


# ---------------------------------------------------------------------------
# The route clause, one claim for every site that prints it
# ---------------------------------------------------------------------------

_BELOW = re.compile(r"raise the path count \(simulation\.num_sims, or N in --decompose=N\) — "
                    r"this register prices at most (?P<cap>[\d,]+) futures on this run")
_AT = re.compile(r"this register prices at most (?P<cap>[\d,]+) futures on this run and is "
                 r"at that count, so no larger run resolves it here")


def _route_claim(line: Line, route: str, paths: int, register: str) -> None:
    """"at most CAP futures on this run": CAP is the most the budget admits at
    this many live channels (and, for the level register, the most it prices
    at any N). Below it a larger run prices more; at it, the larger run is
    refused, or prices the same level futures again."""
    render, block = line.render, line.render.block
    k = len(block["live_channel_ids"])
    cap = (block["max_paths"] if register == "spread"
           else min(dc.LEVEL_PATHS, block["max_paths"]))
    largest = block["max_paths"]
    assert (dr.planned_evaluations(largest, k, dr._level_paths(largest)) <= render.ceiling
            < dr.planned_evaluations(largest + 1, k, dr._level_paths(largest + 1)))
    below, at = _BELOW.fullmatch(route), _AT.fullmatch(route)
    assert (below is None) != (at is None), route
    assert _whole((below or at)["cap"]) == cap
    if below:
        assert paths < cap
        return
    assert paths == cap
    if cap == largest:
        if render.engine:
            assert render.over is not None, "a run at the cap is checked one path above it"
            assert render.over.block["refusal"]["code"] == "budget"
    else:
        assert register == "level" and dr._level_paths(paths + 1) == paths


# ---------------------------------------------------------------------------
# What each line claims
# ---------------------------------------------------------------------------

def _header(line):
    m, block = line.m, line.render.block
    assert _whole(m["paths"]) == block["paths"]
    assert int(m["live"]) == len(block["live_channel_ids"])


def _refusal(line):
    m, refusal = line.m, line.render.block["refusal"]
    assert m["reason"] == refusal["reason"]
    if refusal["code"] == "one_channel":
        assert m["label"] == refusal["label"] == dc.channel(refusal["channel_id"]).label
    else:
        assert m["label"] is None


def _verdict(line):
    assert line.m["reason"] == line.render.verdict["reason"]


def _central(line):
    m, block, verdict = line.m, line.render.block, line.render.verdict
    assert m["best"] == verdict["best"]
    assert m["margin"] == dt._money(verdict["margin_pv"])
    assert _whole(m["paths"]) == block["paths"]
    assert m["mean"] == dt._money(block["mean_margin"])
    mean = block["mean_margin"]
    if mean == 0:
        assert m["side"] is None
    else:
        # the margin is the cheapest OTHER option's PV minus the winner's: above
        # zero, the winner costs less on average
        assert m["side"] == ("above" if mean > 0 else "below")
        assert m["cmp"] == ("less" if mean > 0 else "more")
        assert m["best2"] == verdict["best"]
    assert m["sd"] == dt._money(block["sd_margin"])
    if verdict["margin_pv"] == 0:
        assert m["ratio"] is None
    else:
        ratio = block["sd_margin"] / abs(verdict["margin_pv"])
        assert m["ratio"] == dt._ratio(ratio)
        assert abs(float(m["ratio"]) - ratio) <= 0.05 * max(ratio, 0.1)


def _spread_head(line):
    assert line.m["sd"] == dt._money(line.render.block["sd_margin"])


def _spread_refused(line):
    spread = line.render.block["spread"]
    assert set(spread) == {"refusal"}
    assert line.m["reason"] == spread["refusal"]["reason"]


def _spread_cols(line):
    assert line.m["best"] == line.render.verdict["best"]


def _spread_row(line):
    m, row = line.m, line.spread_row
    assert (m["unresolved"] is not None) == (not row["resolved"])
    if row["resolved"]:
        assert m["alone"] == dt._share(row["alone"])
        assert m["alone_ci"] == dt._interval(_ci(row["alone_ci"]))
        assert m["both"] == dt._share(row["with_interaction"])
        assert m["both_ci"] == dt._interval(_ci(row["with_interaction_ci"]))
        # resolved: both point estimates lie in [0, 1]
        assert 0.0 <= row["alone"] <= 1.0 and 0.0 <= row["with_interaction"] <= 1.0
    else:
        assert not (0.0 <= row["provisional_alone"] <= 1.0
                    and 0.0 <= row["provisional_with_interaction"] <= 1.0)
    assert m["flip"] == dt._flip_cell(row["flip"], _ci(row["flip_ci"]))


def _provisional(line):
    m, row = line.m, line.spread_row
    assert not row["resolved"]
    assert m["alone"] == dt._share(row["provisional_alone"])
    assert m["alone_ci"] == dt._interval(_ci(row["provisional_alone_ci"]))
    assert m["both"] == dt._share(row["provisional_with_interaction"])
    assert m["both_ci"] == dt._interval(_ci(row["provisional_with_interaction_ci"]))
    assert _whole(m["paths"]) == line.render.block["paths"]


def _widths(line):
    assert line.m["cells"] == _width_cells(line.spread_row["widths"])
    if line.render.engine:
        for width in line.spread_row["widths"]:
            assert width["source"] == _echo_class(line.render.doc, width["key"]), width


def _sum_claim(line):
    interaction = line.render.block["spread"]["interaction"]
    assert line.m["sum"] == dt._share(interaction["first_order_sum"])
    assert line.m["sum_ci"] == dt._interval(_ci(interaction["first_order_sum_ci"]))
    rows = line.render.block["spread"]["rows"]
    if line.render.engine:
        assert math.isclose(interaction["first_order_sum"], sum(_point(r) for r in rows),
                            rel_tol=1e-9, abs_tol=1e-12)
    return interaction


def _interaction_resolved(line):
    interaction = _sum_claim(line)
    m = line.m
    assert interaction["resolved"] and interaction["first_order_sum_ci"]["high"] < 1.0
    assert m["res"] == dt._share(interaction["residual"])
    assert math.isclose(interaction["residual"], 1.0 - interaction["first_order_sum"],
                        abs_tol=1e-12)
    assert m["res_ci"] == dt._interval(_ci(interaction["residual_ci"]))
    rows = line.render.block["spread"]["rows"]
    typed = [r for r in rows if r["widths"]
             and all(w["source"] == "assistant" for w in r["widths"])]
    if m["unstated"] is None:
        assert interaction["unstated_first_order_sum"] is None and not typed
    else:
        assert m["unstated"] == dt._share(interaction["unstated_first_order_sum"])
        # "a sum over channels sized entirely by figures the assistant chose"
        assert typed
        if line.render.engine:
            assert math.isclose(interaction["unstated_first_order_sum"],
                                sum(_point(r) for r in typed), rel_tol=1e-9, abs_tol=1e-12)


def _where_claim(line, interaction):
    low = interaction["first_order_sum_ci"]["low"]
    assert not interaction["resolved"] and interaction["first_order_sum_ci"]["high"] >= 1.0
    assert line.m["where"].startswith("above 1") == (low > 1.0)


def _interaction_none(line):
    interaction = _sum_claim(line)
    _where_claim(line, interaction)
    spread = line.render.block["spread"]
    assert spread["interaction_channel_ids"] == []
    for row in spread["rows"]:
        assert not row["interaction_gap_ci"]["low"] > 0.0, row["label"]
    assert _whole(line.m["paths"]) == line.render.block["paths"]
    _route_claim(line, line.m["route"], line.render.block["paths"], "spread")


def _interaction_some(line):
    interaction = _sum_claim(line)
    _where_claim(line, interaction)
    spread = line.render.block["spread"]
    resolved = [r for r in spread["rows"] if r["interaction_gap_ci"]["low"] > 0.0]
    assert resolved and [r["channel_id"] for r in resolved] == sorted(
        spread["interaction_channel_ids"], key=lambda c: [r["channel_id"] for r in
                                                          spread["rows"]].index(c))
    expected = "; ".join(
        f"{r['label']} by {dt._share(r['interaction_gap'])} "
        f"{dt._interval(_ci(r['interaction_gap_ci']))}"
        for r in (next(x for x in spread["rows"] if x["channel_id"] == c)
                  for c in spread["interaction_channel_ids"]))
    assert line.m["named"] == expected
    for row in resolved:
        assert math.isclose(row["interaction_gap"], _together(row) - _point(row),
                            rel_tol=1e-9, abs_tol=1e-12)


def _spread_top_unresolved(line):
    m, spread = line.m, line.render.block["spread"]
    row = _by_label(spread["rows"], m["label"])
    assert spread["unresolved_top_channel_id"] == row["channel_id"]
    assert spread["leading_channel_id"] is None and not row["resolved"]
    assert _point(row) == max(_point(r) for r in spread["rows"])
    assert m["alone"] == dt._share(row["provisional_alone"])
    assert m["alone_ci"] == dt._interval(_ci(row["provisional_alone_ci"]))
    assert _whole(m["paths"]) == line.render.block["paths"]
    _route_claim(line, m["route"], line.render.block["paths"], "spread")


def _spread_two_figures(line):
    m, spread = line.m, line.render.block["spread"]
    row = _by_label(spread["rows"], m["label"])
    assert spread["leading_channel_id"] == row["channel_id"] and row["resolved"]
    if line.render.engine:
        assert _point(row) == max(_point(r) for r in spread["rows"])
    assert m["alone"] == dt._share(row["alone"])
    assert m["flip"] == dt._flip(row["flip"])
    assert m["best"] == line.render.verdict["best"]
    assert m["glossary"] == dt.GLOSSARY
    contract = REPO / "docs" / "reference" / "API_CONTRACT.md"
    assert contract.is_file()
    assert "## The `decomposition` block" in contract.read_text(encoding="utf-8")


def _level_head(line):
    level, block = line.render.block["level"], line.render.block
    assert _whole(line.m["m"]) == level["paths"]
    if line.render.engine:
        assert level["paths"] == min(block["paths"], dc.LEVEL_PATHS)


def _level_cols(line):
    assert line.m["best"] == line.render.verdict["best"]
    assert line.m["p"] == dt._prob(line.render.block["level"]["prob_best_base"])


def _level_row(line):
    m = line.m
    row = _by_label(line.render.block["level"]["rows"], m["label"])
    assert row["resolved"] and abs(row["delta"]) > LEVEL_RESOLUTION_SIGMAS * row["se"]
    assert m["delta"] == dt._shift(row["delta"])
    assert m["se"] == f"${row['se']:,.0f}"
    assert m["p"] == dt._prob(row["prob_best_frozen"])


_FLAT_CELL = re.compile(rf"(?P<label>{LABEL}) \((?P<delta>{SHIFT}) ± (?P<se>\$[\d,]+), "
                        rf"P -> (?P<p>{PROB})\)")


def _level_flat(line):
    m, level = line.m, line.render.block["level"]
    assert int(m["k"]) == LEVEL_RESOLUTION_SIGMAS
    assert _whole(m["m"]) == level["paths"]
    cells = list(_FLAT_CELL.finditer(m["cells"]))
    assert ", ".join(c.group(0) for c in cells) == m["cells"]
    assert {c["label"] for c in cells} == {r["label"] for r in level["rows"]
                                           if not r["resolved"]}
    for cell in cells:
        row = _by_label(level["rows"], cell["label"])
        assert abs(row["provisional_delta"]) <= LEVEL_RESOLUTION_SIGMAS * row["se"]
        assert cell["delta"] == dt._shift(row["provisional_delta"])
        assert cell["se"] == f"${row['se']:,.0f}"
        assert cell["p"] == dt._prob(row["prob_best_frozen"])


def _level_gap(line):
    m, level, verdict = line.m, line.render.block["level"], line.render.verdict
    assert _whole(m["m"]) == level["paths"]
    assert m["best"] == verdict["best"]
    # "the central case ... by X": the all-frozen margin, printed, IS the
    # central case's margin printed
    assert m["frozen"] == dt._money(level["all_frozen_margin"]) == dt._money(verdict["margin_pv"])
    assert m["futures"] == dt._money(level["futures_margin"])
    # the gap and the sum are the printed figures' own arithmetic
    assert _whole(m["gap"]) == _whole(m["frozen"]) - _whole(m["futures"])
    assert int(m["n"]) == len(level["rows"])
    printed = [(_whole(dt._shift(_shift(r)))) for r in level["rows"]]
    assert _whole(m["sum"]) == sum(printed)
    assert m["dev"] == dt._deviation(level["all_frozen_deviation"])
    # "every channel frozen reproduces the central case to within DEV"
    assert level["all_frozen_path_spread"] == 0.0
    assert abs(level["all_frozen_margin"] - verdict["margin_pv"]) <= (
        level["all_frozen_deviation"] * (1 + 1e-9) + 1e-300)


def _level_top(line, some: bool):
    m, level, verdict = line.m, line.render.block["level"], line.render.verdict
    row = _by_label(level["rows"], m["label"])
    assert level["unresolved_top_channel_id"] == row["channel_id"] and not row["resolved"]
    assert level["leading_channel_id"] is None
    # the top row is the largest shift IN SIZE, resolved or not
    assert abs(_shift(row)) == max(abs(_shift(r)) for r in level["rows"])
    assert some == any(r["resolved"] for r in level["rows"])
    assert m["delta"] == dt._shift(row["provisional_delta"])
    assert m["se"] == f"${row['se']:,.0f}"
    assert m["best"] == verdict["best"]
    assert m["p"] == dt._prob(row["prob_best_frozen"])
    assert _whole(m["m"]) == level["paths"]
    assert (m["tie"] is not None) == (verdict["state"] == "tie")
    expected = {"tie": "this register cannot name a channel",
                "disagreement": "this run cannot say which channel puts"}.get(
        verdict["state"], "this run cannot say which one the futures price")
    assert m["so"].startswith(expected)
    _route_claim(line, m["route"], level["paths"], "level")


def _mover(line):
    m, level = line.m, line.render.block["level"]
    row = _by_label(level["rows"], m["label"])
    assert level["leading_channel_id"] == row["channel_id"] and row["resolved"]
    assert abs(row["delta"]) == max(abs(_shift(r)) for r in level["rows"])
    assert m["delta"] == dt._shift(row["delta"])
    assert m["best"] == line.render.verdict["best"]
    spread = line.render.block["spread"]
    share = next((r for r in spread.get("rows", ()) if r["channel_id"] == row["channel_id"]),
                 None)
    if share is not None and share["resolved"]:
        assert m["share"] == dt._share(share["alone"])
    else:
        assert m["share"] is None
    return row


def _level_close_disagree(line):
    row = _mover(line)
    assert line.render.verdict["state"] == "disagreement"
    assert line.m["p"] == dt._prob(row["prob_best_frozen"])
    assert (line.m["because"] is not None) == (row["prob_best_frozen"] > 0.5)


def _level_close_tie(line):
    row = _mover(line)
    assert line.render.verdict["state"] == "tie"
    assert line.m["p"] == dt._prob(row["prob_best_frozen"])


def _level_close_option(line):
    row = _mover(line)
    m, level, verdict = line.m, line.render.block["level"], line.render.verdict
    assert verdict["state"] not in ("tie", "disagreement")
    assert m["p"] == dt._prob(row["prob_best_frozen"])
    assert m["p0"] == dt._prob(level["prob_best_base"])
    fell = [where for where, p in (("as drawn", level["prob_best_base"]),
                                   ("priced that way", row["prob_best_frozen"]))
            if not p > 0.5]
    assert (m["either"] is not None) == (not fell)
    if m["either"] is not None:
        assert m["either"] == verdict["best"]
    assert (m["fell"] or None) == (" and ".join(fell) or None)


def _level_sibling(line):
    m, block = line.m, line.render.block
    spread, level = block["spread"], block["level"]
    srow = _by_label(spread["rows"], m["label"])
    lrow = _by_label(level["rows"], m["label"])
    assert spread["leading_channel_id"] == srow["channel_id"] != level["leading_channel_id"]
    assert srow["resolved"] and not lrow["resolved"]
    assert abs(lrow["provisional_delta"]) <= LEVEL_RESOLUTION_SIGMAS * lrow["se"]
    assert m["share"] == dt._share(srow["alone"])
    assert _whole(m["m"]) == level["paths"]
    assert m["delta"] == dt._shift(lrow["provisional_delta"])
    assert m["se"] == f"${lrow['se']:,.0f}"


def _zero_head(line):
    """"zero spread by construction": no row under it is a live channel, and on
    a run, no key under it moves the spread — checked per kind at the
    generators in `_zero_row` and in `test_decomposition_contract_doc.py`."""
    block = line.render.block
    zeros = block["reversal"]["structural_zeros"]
    assert zeros
    for zero in zeros:
        assert zero["channel_id"] not in block["live_channel_ids"]


def _zero_row(line):
    m, zero = line.m, line.zero
    assert m["keys"] == ", ".join(zero["keys"])
    assert (m["stated"] or None) == zero["stated_formatted"]
    assert m["fact"] == DRAWN_WORDS[zero["kind"]]
    assert m["reason"] == zero["reason"]
    render = line.render
    if not render.engine:
        return
    spec = render.spec
    if zero["kind"] == "stated_path":
        # no draw touches it: moving the stated key moves no generator's state
        assert zero["reversal_key"] in {r["key"] for r in render.block["reversal"]["exact"]}
        moved = copy.deepcopy(render.raw)
        option, leaf = zero["reversal_key"].split(".", 1)
        value = moved[option][leaf]
        moved[option][leaf] = ([v + 0.01 for v in value] if isinstance(value, list)
                               else value + 0.01)
        moved.get("sources", {}).pop(zero["reversal_key"], None)
        before, after = _held(), _held()
        run_monte_carlo(dr._spec_at(spec, 40), before)
        run_monte_carlo(dr._spec_at(load_config_dict(moved), 40), after)
        assert ({c: g.bit_generator.state for c, g in before.items()}
                == {c: g.bit_generator.state for c, g in after.items()})
    elif zero["kind"] == "no_pv_reach":
        assert zero["channel_id"] is None
        _draws_and_reaches_nothing(spec, 7)
    else:
        assert zero["channel_id"] in dr.channels_that_draw(spec)
        assert zero["channel_id"] not in dr.live_channels(spec)
        _draws_and_reaches_nothing(spec, zero["channel_id"])


def _row_head(line):
    m, row = line.m, line.reversal_row
    assert (m["key"], m["option"], m["stated"]) == (row["key"], row["option"],
                                                    row["stated_formatted"])


_STATED_WORDS = {"user": "you stated this", "assistant": "the assistant typed this",
                 "anchor": "this", "unattributed": "no sources: entry says who typed this"}


def _stated_by(line):
    m, row = line.m, line.reversal_row
    assert m["source"] == row["stated_source"]
    assert m["words"].startswith(_STATED_WORDS[row["stated_source"]])
    if row["stated_source"] == "anchor":
        assert m["words"].endswith("is anchor-sourced")
    what = m["w1"] or m["w2"] or m["w3"] or m["w4"]
    assert what == ("path" if row["path_note"] is not None else "value")
    if line.render.engine:
        # the read-back's own class for the same key, on the same run
        assert _echo_class(line.render.doc, row["key"]) == row["stated_source"]


def _licence(line):
    m, row = line.m, line.reversal_row
    assert row in line.render.block["reversal"]["exact"]
    assert m["option"] == row["option"]
    assert m["dev"] == dt._deviation(row["max_path_deviation_over_sd"])
    assert _whole(m["probe"]) == row["probe_paths"]
    assert row["max_path_deviation_over_sd"] <= be.REVERSAL_GATE_TOLERANCE


def _gate_refused(line):
    m, row = line.m, line.reversal_row
    assert row in line.render.block["reversal"]["estimated"]
    assert (m["then"].startswith("each distance")) == bool(row["boundaries"])
    deviation = row["max_path_deviation_over_sd"]
    finite = deviation is not None and math.isfinite(deviation)
    if finite:
        assert m["measured"] == (f"moving it shifts {row['option']}'s present value by "
                                 f"amounts that differ across paths by up to "
                                 f"{deviation:.1e} of its s.d.")
    else:
        assert "could not be measured" in m["measured"]


def _solved(row):
    return [b for b in row["boundaries"] if b["verdict_field"] in ("best", "runner_up")
            and "curve_paths" not in b and "value_ci" not in b]


def _sampled(row):
    return [b for b in row["boundaries"] if "curve_paths" in b]


def _bracket(line):
    m, row = line.m, line.reversal_row
    assert m["lo"] == dt._rate(row["bracket_low"]) and m["hi"] == dt._rate(row["bracket_high"])
    assert m["src"] == row["bracket_source"]
    if "head" in m.groupdict() and m["head"] is not None:
        assert m["head"].startswith("replacing") == (row["path_note"] is not None)
    if line.render.engine:
        assert (row["bracket_low"], row["bracket_high"]) == be.reversal_bracket(row["key"])


def _group_solved(line):
    _bracket(line)
    assert _solved(line.reversal_row)


def _group_sampled(line):
    _bracket(line)
    assert not _solved(line.reversal_row) and _sampled(line.reversal_row)


def _group_sampled_after(line):
    assert _solved(line.reversal_row) and _sampled(line.reversal_row)


def _group_estimated(line):
    _bracket(line)
    assert line.reversal_row in line.render.block["reversal"]["estimated"]
    assert line.reversal_row["boundaries"]


def _boundary(line, fmt):
    m, row = line.m, line.reversal_row
    field = next(f for f, label in FIELD_WORDS.items() if label == m["field"])
    found = [b for b in row["boundaries"] if b["verdict_field"] == field
             and fmt(b["value"]) == m["value"] and b["was"] == m["was"]
             and b["becomes"] == m["becomes"]]
    assert len(found) == 1, (m.group(0), row["boundaries"])
    boundary = found[0]
    assert m["further"] == boundary["further_changes"]
    return boundary


def _probs(pairs):
    return dt._probabilities([tuple(p) for p in pairs])


def _cross_solved(line):
    boundary = _boundary(line, dt._solved_rate)
    assert boundary in _solved(line.reversal_row)
    pairs = boundary["confirming_probabilities"]
    assert (line.m["probs"] or None) == (_probs(pairs) if pairs else None)


def _cross_sampled(line):
    boundary = _boundary(line, dt._sampled_rate)
    assert "curve_paths" in boundary
    pairs = boundary["confirming_probabilities"]
    assert (line.m["probs"] or None) == (_probs(pairs) if pairs else None)
    assert _whole(line.m["paths"]) == boundary["curve_paths"]
    assert int(line.m["seed"]) == boundary["seed"]
    if line.render.engine:
        # the sample it was bisected on is this run's own
        assert boundary["seed"] == line.render.spec.simulation.random_seed
        assert boundary["curve_paths"] == line.render.spec.simulation.num_sims
        # "as it rises past X": at the printed X the field still says `was`,
        # and one printed step up it says `becomes`, on this run's own futures
        printed = float(line.m["value"].rstrip("%")) / 100.0
        field = boundary["verdict_field"]
        at, above = _sweep_states(line.render.path, line.reversal_row["key"],
                                  [printed, printed + 1e-4], futures=True)
        assert at[field] == boundary["was"], (line.m.group(0), at)
        assert above[field] == boundary["becomes"], (line.m.group(0), above)


def _cross_estimated(line):
    boundary = _boundary(line, dt._rate)
    assert line.m["lo"] == dt._rate(boundary["value_ci"]["low"])
    assert line.m["hi"] == dt._rate(boundary["value_ci"]["high"])
    assert _whole(line.m["n"]) == boundary["resimulation_paths"]


def _no_boundary(line):
    _bracket(line)
    row = line.reversal_row
    assert row["boundaries"] == []
    if line.render.engine:
        assert {r["verdict_field"] for r in row["refused_boundaries"]} == set(dc.BOUNDARY_FIELDS)


def _path_note(line):
    row = line.reversal_row
    assert line.m["note"] == row["path_note"] and line.m["key"] == row["key"]
    if line.render.engine:
        option, leaf = row["key"].split(".", 1)
        stated = line.render.raw[option][leaf]
        # a path of more than one rate, which no single grid point is
        assert isinstance(stated, list) and len(set(stated)) > 1
        assert line.m["stated"] == ", ".join(_fmt_value(row["key"], float(v)) for v in stated)


def _refused_boundary(line):
    m, row = line.m, line.reversal_row
    named = [r for r in row["refused_boundaries"] if r["reason"] == m["reason"]]
    labels = [FIELD_WORDS[r["verdict_field"]] for r in named]
    expected = labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} or {labels[-1]}"
    assert m["fields"] == expected


def _references(line):
    row = line.reversal_row
    refs = [dc.AxisReference(**r) for r in row["references"]]
    assert line.m["refs"] == "; ".join(dt._reference_clause(r) for r in refs)
    if not line.render.engine:
        return
    option = row["option"]
    compounding = line.render.raw[option].get("mortgage_rate_compounding", "semi_annual")
    for ref in row["references"]:
        published = float(ANCHORS[ref["anchor"]].value)
        if compounding == "effective_annual":
            # on this axis the semi-annual quote is converted by the loader's rule
            assert math.isclose(ref["value"], effective_mortgage_rate(published, "semi_annual"))
            assert f"published as {_fmt_value(row['key'], published)} compounded " \
                   f"semi-annually" in ref["note"]
        else:
            assert ref["value"] == published
            assert "published as" not in (ref["note"] or "")
        assert ref["formatted"] == _fmt_value(row["key"], ref["value"])


def _exact_head(line):
    zero_keys = {z["reversal_key"] for z in line.render.block["reversal"]["structural_zeros"]}
    assert [r for r in line.render.block["reversal"]["exact"] if r["key"] not in zero_keys]


def _estimated_head(line):
    assert line.render.block["reversal"]["estimated"]


def _no_distance(line):
    reversal = line.render.block["reversal"]
    assert reversal["exact"] == [] and reversal["estimated"] == []
    assert line.m["reason"] == reversal["no_distance_reason"]


def _provenance(line):
    m, spread = line.m, line.render.block["spread"]
    distinct: Dict[str, str] = {}
    for row in spread["rows"]:
        for width in row["widths"]:
            distinct.setdefault(width["key"], width["source"])
    counts: Dict[str, int] = {}
    for source in distinct.values():
        counts[source] = counts.get(source, 0) + 1
    assert int(m["n"]) == len(distinct)
    parts = re.findall(r"(\d+) ([^\[]+?) \[(\w+)\]", m["parts"])
    assert {source: int(n) for n, _, source in parts} == counts
    for _, words, source in parts:
        assert words == CLASS_WORDS.get(source, f"of source class {source}")
    unstated = [k for k, s in distinct.items() if s not in ("user", "anchor")]
    assert unstated and not spread["superlative_licensed"]
    assert m["extent"] == ("entirely" if len(unstated) == len(distinct) else "partly")
    leader = spread["leading_channel_id"]
    check = spread["check_first"]
    assert (m["cells"] is not None) == bool(check)
    if check:
        row = next(r for r in spread["rows"] if r["channel_id"] == leader)
        assert m["leader"] == row["label"]
        assert check == [w for w in row["widths"] if w["source"] not in ("user", "anchor")]
        assert m["cells"] == _width_cells(check)
    else:
        assert leader is None


def _licensed(line):
    spread = line.render.block["spread"]
    row = _by_label(spread["rows"], line.m["label"])
    assert spread["superlative_licensed"] and spread["leading_channel_id"] == row["channel_id"]
    assert row["widths"] and all(w["source"] in ("user", "anchor") for w in row["widths"])


LINE_CLAIMS: Dict[str, Callable[[Line], None]] = {
    "BLANK": lambda line: None,
    "HEADER": _header,
    "REFUSAL": _refusal,
    "VERDICT": _verdict,
    "CENTRAL": _central,
    "SPREAD_HEAD": _spread_head,
    "SPREAD_REFUSED": _spread_refused,
    "SPREAD_COLS": _spread_cols,
    "SPREAD_ROW": _spread_row,
    "PROVISIONAL": _provisional,
    "WIDTHS": _widths,
    "INTERACTION_RESOLVED": _interaction_resolved,
    "INTERACTION_NONE": _interaction_none,
    "INTERACTION_SOME": _interaction_some,
    "SPREAD_TOP_UNRESOLVED": _spread_top_unresolved,
    "SPREAD_TWO_FIGURES": _spread_two_figures,
    "LEVEL_HEAD": _level_head,
    "LEVEL_COLS": _level_cols,
    "LEVEL_ROW": _level_row,
    "LEVEL_FLAT": _level_flat,
    "LEVEL_GAP": _level_gap,
    "LEVEL_TOP_SOME": lambda line: _level_top(line, True),
    "LEVEL_TOP_NONE": lambda line: _level_top(line, False),
    "LEVEL_CLOSE_DISAGREE": _level_close_disagree,
    "LEVEL_CLOSE_TIE": _level_close_tie,
    "LEVEL_CLOSE_OPTION": _level_close_option,
    "LEVEL_SIBLING": _level_sibling,
    "ZERO_HEAD": _zero_head,
    "ZERO_ROW": _zero_row,
    "EXACT_HEAD": _exact_head,
    "ESTIMATED_HEAD": _estimated_head,
    "NO_DISTANCE": _no_distance,
    "ROW_HEAD": _row_head,
    "STATED_BY": _stated_by,
    "LICENCE": _licence,
    "GATE_REFUSED": _gate_refused,
    "GROUP_SOLVED": _group_solved,
    "GROUP_SAMPLED": _group_sampled,
    "GROUP_SAMPLED_AFTER": _group_sampled_after,
    "GROUP_ESTIMATED": _group_estimated,
    "CROSS_SOLVED": _cross_solved,
    "CROSS_SAMPLED": _cross_sampled,
    "CROSS_ESTIMATED": _cross_estimated,
    "NO_BOUNDARY": _no_boundary,
    "PATH_NOTE": _path_note,
    "REFUSED_BOUNDARY": _refused_boundary,
    "REFERENCES": _references,
    "PROVENANCE": _provenance,
    "LICENSED": _licensed,
}

# Line templates only a hand-built outcome reaches, and why the engine cannot:
# a financing key always passes the exactness gate (`_financing_pv` shifts
# every path by one constant), so no engine row is estimated, and an estimated
# row carries no boundary (slice 1 estimates nothing); and every exact row the
# engine builds is joined to its stated-path zero, so it prints under that zero
# rather than under a heading and a row head of its own.
HOUSEHOLD_ONLY = {
    "GROUP_ESTIMATED", "CROSS_ESTIMATED", "ESTIMATED_HEAD", "GATE_REFUSED",
    "EXACT_HEAD", "ROW_HEAD",
}


# ---------------------------------------------------------------------------
# The inventory, closed both ways
# ---------------------------------------------------------------------------

def test_every_template_has_a_claim_check():
    assert set(LINE_CLAIMS) == set(LINES)
    assert set(REASON_CLAIMS) | set(SEAM_ONLY) == set(REASONS)
    assert not set(REASON_CLAIMS) & set(SEAM_ONLY)


def test_every_printed_line_is_a_template():
    """Each line of every render matches exactly one template — a line no
    template knows is a sentence with no truth test."""
    for render in renders():
        _lines(render)


def test_every_line_template_is_printed():
    """By a run of the engine, unless the engine cannot reach it (then by a
    household, and the reason is recorded in `HOUSEHOLD_ONLY`)."""
    by_engine = {line.template for r in renders() if r.engine for line in _lines(r)}
    anywhere = {line.template for r in renders() for line in _lines(r)}
    assert anywhere == set(LINES)
    assert set(LINES) - by_engine <= HOUSEHOLD_ONLY, set(LINES) - by_engine - HOUSEHOLD_ONLY
    # and a template the engine does reach is not excused as household-only
    assert not (by_engine & HOUSEHOLD_ONLY), by_engine & HOUSEHOLD_ONLY


@pytest.mark.parametrize("template", list(LINES))
def test_the_line_says_what_is_so(template):
    checked = 0
    for render in renders():
        for line in _lines(render):
            if line.template == template:
                LINE_CLAIMS[template](line)
                checked += 1
    assert checked, template


# ---------------------------------------------------------------------------
# The reasons the engine writes
# ---------------------------------------------------------------------------

_ROUTE = (r"--break-even <key> solves the crossing on the central case with the solver "
          r"the --decompose reversal register uses(?:, one pair of options at a time — on "
          r"this (?P<options>\d+)-option config it needs one option's section dropped first)?")

REASONS: Dict[str, "re.Pattern"] = {name: re.compile(pattern) for name, pattern in {
    "NO_FUTURES": (r"^there are no futures to decompose: this run priced the central case "
                   r"only \(--no-monte-carlo, or every uncertainty input is off\)\. The "
                   r"deterministic line is the whole answer here\.(?: What would have to "
                   rf"change for that answer to change needs no futures: {_ROUTE}, and "
                   r"--sweep <key>=<values> prints the verdict at each point of a grid\.)?$"),
    "TOO_FEW": (r"^this decomposition was asked for (?P<n>[\d,]+) future\(s\), below the "
                r"(?P<min>\d+) it takes to put an interval on a figure: every bound here is "
                r"a percentile over resampled PATHS, so one future weighs 1/(?P<n2>\d+) of "
                r"every figure and the 2\.5% tail this interval claims to cut is narrower "
                r"than a single path\. Ask for at least (?P<min2>\d+) with --decompose N, or "
                r"read the run's own verdict instead\.$"),
    "SINGLE_OPTION": (r"^fewer than two options are priced, so no decision margin exists "
                      r"and there is nothing to decompose\.$"),
    "ONE_CHANNEL": (rf"^no other channel's draws reach a cash flow on this run, so there is "
                    rf"nothing to split: a table would give (?P<label>{LABEL}) the whole "
                    rf"spread by construction, not by measurement\.$"),
    "NO_SPREAD_UNREACHED": (r"^no channel on this run reaches a cash flow, so every future "
                            r"prices the same margin and there is no spread to apportion: "
                            r"(?:no channel draws on this run either|(?P<labels>.+?) "
                            r"(?:draws|draw) on every path all the same, and no draw reaches "
                            r"a cash flow), which is why this is a refusal and not an empty "
                            r"table\.$"),
    "NO_SPREAD_CONSTANT": (r"^the decision margin is identical on all (?P<n>[\d,]+) futures "
                           r"\((?P<value>-?[\d,]+\.\d\d)\), so there is no decision spread "
                           r"to apportion and every index would be 0/0\. The live channels "
                           r"move both sides of this comparison by the same amount\.$"),
    "BUDGET": (r"^the spread and level registers would run up to (?P<work>[\d,]+) path "
               r"evaluations \((?P<n>[\d,]+) paths x (?P<k2>\d+) matrices, plus "
               r"(?P<m>[\d,]+) x (?P<k1>\d+) for the level register: one freeze per live "
               r"channel and one with all of them frozen\), above this engine's ceiling of "
               r"(?P<ceiling>[\d,]+) \[set in the engine, not by a published figure and not "
               r"in your config\]\. Run it at a smaller sample of its own with --decompose=N: "
               r"on this run the largest N whose work stays within the ceiling is "
               r"(?P<largest>[\d,]+) \(--decompose=(?P<largest2>\d+)\)\.$"),
    "FREEZE_LEAK": (r"^with every channel frozen, the [\d,]+ paths should price one margin, "
                    r"and they differ by up to \$.+: a draw escaped the freeze mask, .+ "
                    r"prints none of them\.$"),
    "IDENTITY_FAILED": (r"^with every channel frozen, all [\d,]+ paths price one margin, .+ "
                        r"so it prints none of them\.$"),
    "NO_SIGN_VARIATION": (rf"^no share is apportioned: (?:(?P<all>{OPTION}) is cheapest in "
                          rf"all (?P<n1>[\d,]+) of these futures|(?P<none>{OPTION}), the "
                          rf"central case's winner, is cheapest in none of these "
                          rf"(?P<n2>[\d,]+) futures), so every future sits on the same side "
                          rf"of the line the flip column counts — whether (?P<best>{OPTION}) "
                          rf"is cheapest — and no channel moved one across it: there is "
                          rf"nothing to split in decision space\. The shares themselves are "
                          rf"defined; they would rank the scatter of a margin whose sign "
                          rf"never changes\.$"),
    "DEAD_ECONOMY": "^" + re.escape(dr._dead_draw_reason(None, 0)) + "$",
    "DEAD_MARKET": "^" + re.escape(dr._dead_draw_reason(None, 1)) + "$",
    "DEAD_COSTS": "^" + re.escape(dr._dead_draw_reason(None, 3)) + "$",
    "INCOME": (r"^income\.pay_drop_events moves the affordability report, not any option's "
               r"present value, so it cannot move this margin$"),
    "STATED_LADDER": (rf"^(?P<key>[\w.]+) is a path this config states, not a distribution "
                      rf"— the engine anchors no forward rate, so (?P<option>{OPTION})'s "
                      rf"renewals carry no spread here at all\. (?P<tail>They carry a solved "
                      rf"distance instead|No crossing of the central case's verdict on it is "
                      rf"solved; the lines below say why, field by field)$"),
    "STATED_RATE": (rf"^(?P<key>[\w.]+) is one rate this config states, (?P<held>held for "
                    rf"the opening term|held for the whole (?P<term>\d+)-year amortization|"
                    rf"held for every year this run prices — the stated ladder's first "
                    rf"renewal, in year (?P<year>\d+), falls past its (?P<horizon>\d+)-year "
                    rf"horizon), so (?P<option>{OPTION})'s financing carries no spread here "
                    rf"at all\. (?P<tail>It carries a solved distance instead|No crossing of "
                    rf"the central case's verdict on it is solved; the lines below say why, "
                    rf"field by field)$"),
    "PATH_NOTE": (r"^the config states (?P<key>[\w.]+) as a path \((?P<stated>[^)]+)\); every "
                  r"grid point replaces the whole path with ONE figure applied at each "
                  r"renewal, so the threshold reported is a flat renewal rate rather than the "
                  r"rate at the next renewal, and the stated path is not a point on this "
                  r"grid$"),
    "UNCHANGED": (rf"^(?P<field>best|runner_up) is '(?P<value>\w+)' at every point of "
                  rf"(?P<lo>{PCT})–(?P<hi>{PCT}), so no boundary of it lies in the range this "
                  rf"axis searches$"),
    "FUTURES_UNCHANGED": (rf"^(?P<field>mc_best|decisive) says '(?P<value>[^']+)' at every "
                          rf"one of (?P<n>\d+) points across (?P<lo>{PCT})–(?P<hi>{PCT}), so "
                          rf"no boundary of it lies in the range this axis searches$"),
    "SAYS_SO_NOWHERE": (r"^(?P<field>\w+) says '[^']+' in this run and says so nowhere in "
                        r".+, so no distance along this axis is a distance from what the run "
                        r"says(?: \(scanned at \d+ points\))?$"),
    "NOT_IDENTIFIED": (r"^across the bracket the probabilities this boundary turns on move by "
                       r"\d\.\d{4}, inside the \d\.\d{4} that \d+ paths cannot resolve — the "
                       r"boundary is not identified and is not reported$"),
    "NO_PROBABILITY": (r"^no probability is attached to this boundary, so it cannot be "
                       r"identified$"),
    "RESIMULATION_DISAGREES": (r"^the re-simulation at .+ disagrees with the free curve "
                               r"\(free .+, re-simulated .+\) — the shift this boundary rests "
                               r"on is not exact after all, so it is withheld$"),
    "GATE_NOT_FINITE": (r"^a present value this gate compares is not a finite number — .+ — "
                        r"so whether .+ shifts .+ by one constant cannot be measured, and no "
                        r"curve over it is licensed$"),
    "GATE_MOVES_OTHERS": (r"^moving .+ moves .+ too, and this key names neither — it changes "
                          r"the draw stream, so no curve over it is free$"),
    "GATE_NOT_CONSTANT": (r"^moving .+ shifts \w+ by a DIFFERENT amount on different paths "
                          r"\(.+\) — the futures at another value have to be re-simulated, "
                          r"not shifted$"),
    "WITHOUT_FUTURES_DECISIVE": (r"^this solver locates decisive only on the futures curve, "
                                 r"so on a run without futures .+ read no path$"),
    "WITHOUT_FUTURES_MC_BEST": (r"^mc_best is read off this run's futures and this run has "
                                r"none .+ read no path$"),
    "NO_DISTANCE": (rf"^no reversal distance is solved here: this block searches only a "
                    rf"financed option's mortgage_renewal_rates and mortgage_rate, and "
                    rf"(?P<found>this config states no such key|this config states .+)\. "
                    rf"That is the reach of this search, not a finding that nothing would "
                    rf"reverse the verdict: for any other key this config states, "
                    rf"{_ROUTE}\.$"),
    "NO_DISTANCE_NO_MAPPING": (r"^no reversal distance is solved here: this block was handed "
                               r"no config mapping, so it had no stated key to search$"),
    "NO_DISTANCE_ONE_OPTION": (r"^fewer than two options are priced, so there is no verdict "
                               r"to reverse$"),
}.items()}


def _engine_reasons(render):
    """Every reason string the engine wrote into this run's JSON, with where."""
    block = render.block
    if "refusal" in block:
        return [("refusal", block["refusal"]["reason"], None)]
    out = []
    spread = block["spread"]
    if "refusal" in spread:
        out.append(("spread", spread["refusal"]["reason"], None))
    reversal = block["reversal"]
    for zero in reversal["structural_zeros"]:
        out.append(("zero", zero["reason"], zero))
    for kind in ("exact", "estimated"):
        for row in reversal[kind]:
            for refused in row["refused_boundaries"]:
                out.append(("refused", refused["reason"], (row, refused)))
            if row["path_note"] is not None:
                out.append(("path_note", row["path_note"], row))
    if reversal["no_distance_reason"] is not None:
        out.append(("no_distance", reversal["no_distance_reason"], reversal))
    return out


def _reason_hits(text):
    return [(name, p.match(text)) for name, p in REASONS.items() if p.match(text)]


@functools.lru_cache(maxsize=None)
def _reasons_of(render):
    out = []
    for where, text, node in _engine_reasons(render):
        hits = _reason_hits(text)
        assert len(hits) == 1, (render.name, where, text, [h[0] for h in hits])
        out.append((hits[0][0], hits[0][1], where, node))
    return tuple(out)


# The reasons only a patched seam or a direct library call produces, each with
# the test that produces it and checks the condition it states.
SEAM_ONLY = {
    "FREEZE_LEAK": "tests/test_decomposition_run.py::TestTheFreezeIdentity::"
                   "test_a_draw_that_escapes_the_mask_refuses_the_whole_block",
    "IDENTITY_FAILED": "tests/test_decomposition_run.py::TestTheIdentityIsGated::"
                       "test_a_margin_off_the_central_case_refuses_the_whole_block",
    "NOT_IDENTIFIED": "tests/test_reversal_register.py::TestTheConfirmingResimulation::"
                      "test_a_futures_boundary_inside_monte_carlo_noise_is_not_reported",
    "RESIMULATION_DISAGREES": "tests/test_reversal_register.py::"
                              "TestTheConfirmingResimulation::"
                              "test_a_disagreeing_re_simulation_withholds_every_boundary",
    "GATE_NOT_FINITE": "tests/test_reversal_register.py::TestTheExactnessGate::"
                       "test_a_non_finite_present_value_in_the_named_option_refuses_by_name",
    "GATE_MOVES_OTHERS": "tests/test_reversal_register.py::TestTheExactnessGate::"
                         "test_a_key_that_moves_the_draw_stream_is_refused_by_clause_a",
    "GATE_NOT_CONSTANT": "tests/test_reversal_register.py::TestTheExactnessGate::"
                         "test_a_key_whose_shift_is_not_constant_is_refused",
    "WITHOUT_FUTURES_DECISIVE": "tests/test_reversal_register.py::TestRefusals::"
                                "test_without_futures_decisiveness_still_changes_so_its_"
                                "reason_cannot_be_none",
    "WITHOUT_FUTURES_MC_BEST": "tests/test_reversal_register.py::TestRefusals::"
                               "test_without_futures_the_register_still_carries_its_"
                               "solved_half",
    "SAYS_SO_NOWHERE": "tests/test_decomposition_sentences.py::"
                       "test_a_field_the_axis_never_reproduces_says_so",
    "NO_PROBABILITY": "tests/test_decomposition_sentences.py::"
                      "test_a_boundary_with_no_probability_is_not_identified",
    "NO_DISTANCE_NO_MAPPING": "tests/test_decomposition_sentences.py::"
                              "test_a_block_handed_no_config_mapping_searched_no_key",
    "NO_DISTANCE_ONE_OPTION": "tests/test_decomposition_sentences.py::"
                              "test_a_register_on_one_option_has_no_verdict_to_reverse",
}


def _run_inputs(render):
    spec = render.spec
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    return det, mc, verdict


def _r_no_futures(render, m, node):
    # "priced the central case only (--no-monte-carlo, or every uncertainty
    # input is off)": one or the other is so of this run
    assert "--no-monte-carlo" in render.extra or single_path_run(render.spec)
    priced = _priced(render.raw)
    route = " What would have to change" in m.group(0)
    assert route == (len(priced) >= 2)
    if route:
        assert (m["options"] is not None) == (len(priced) > 2)
        if m["options"] is not None:
            assert int(m["options"]) == len(priced)


def _r_too_few(render, m, node):
    n = _whole(m["n"])
    assert n == int(render.extra[0]) == int(m["n2"])
    assert int(m["min"]) == int(m["min2"]) == dr.MIN_INTERVALLED_FUTURES
    assert n < dr.MIN_INTERVALLED_FUTURES
    assert 0.025 < 1.0 / n   # the 2.5% tail is narrower than one future


def _r_single_option(render, m, node):
    assert len(_priced(render.raw)) < 2


def _r_one_channel(render, m, node):
    spec = render.spec
    only = dr.live_channels(spec)
    assert len(only) == 1 and dc.channel(only[0]).label == m["label"]
    small = dr._spec_at(spec, 40)
    assert _pv_bytes(small, {only[0]: 101}) != _pv_bytes(small, {only[0]: 202})
    for other in dr.channels_that_draw(spec):
        if other != only[0]:
            _draws_and_reaches_nothing(spec, other)


def _r_no_spread_unreached(render, m, node):
    spec = render.spec
    assert dr.live_channels(spec) == ()
    drawing = dr.channels_that_draw(spec)
    assert m["labels"] == dr._joined([dc.channel(c).label for c in drawing])
    for channel_id in drawing:
        _draws_and_reaches_nothing(spec, channel_id)
    # every future prices the same margin
    best = render.verdict["best"]
    margin = dr.margin_per_path(dr._run(dr._spec_at(spec, 40), dr.MATRIX_A), best)
    assert np.ptp(margin) == 0.0


def _r_no_spread_constant(render, m, node):
    spec = render.spec
    assert dr.live_channels(spec)
    n = _whole(m["n"])
    assert n == spec.simulation.num_sims
    margin = dr.margin_per_path(dr._run(dr._spec_at(spec, n), dr.MATRIX_A),
                                render.verdict["best"])
    assert np.ptp(margin) == 0.0 and m["value"] == f"{float(margin[0]):,.2f}"


def _r_budget(render, m, node):
    spec = render.spec
    k = len(dr.live_channels(spec))
    n, mm = _whole(m["n"]), _whole(m["m"])
    assert n == int(render.extra[0]) and mm == min(n, dc.LEVEL_PATHS)
    assert (int(m["k2"]), int(m["k1"])) == (k + 2, k + 1)
    assert _whole(m["work"]) == n * (k + 2) + mm * (k + 1) == dr.planned_evaluations(n, k, mm)
    assert _whole(m["ceiling"]) == dr.EVALUATION_CEILING < _whole(m["work"])
    largest = _whole(m["largest"])
    assert largest == int(m["largest2"])
    assert (dr.planned_evaluations(largest, k, dr._level_paths(largest))
            <= dr.EVALUATION_CEILING
            < dr.planned_evaluations(largest + 1, k, dr._level_paths(largest + 1)))
    # the N it names is one the gate admits
    det, mc, verdict = _run_inputs(render)
    live, drawing = dr.live_channels(spec), dr.channels_that_draw(spec)
    assert dr._refusal_before_pricing(spec, mc, verdict, live, largest,
                                      drawing=drawing) is None


def _r_no_sign_variation(render, m, node):
    block = render.block
    f_a = render.source.f_a()
    share = float(np.mean(f_a > 0.0))
    assert m["best"] == render.verdict["best"]
    if m["all"] is not None:
        assert share == 1.0 and m["all"] == render.verdict["best"]
        assert _whole(m["n1"]) == block["paths"] == f_a.size
    else:
        assert share == 0.0 and m["none"] == render.verdict["best"]
        assert _whole(m["n2"]) == block["paths"] == f_a.size
    # the shares are defined: the margin does scatter
    assert block["sd_margin"] > 0.0 and np.std(f_a) > 0.0


def _r_dead(render, m, node):
    spec = render.spec
    channel_id = node["channel_id"]
    assert node["kind"] == "dead_draw"
    assert channel_id in dr.channels_that_draw(spec)
    assert channel_id not in dr.live_channels(spec)
    _draws_and_reaches_nothing(spec, channel_id)
    return spec, channel_id


def _r_dead_economy(render, m, node):
    spec, channel_id = _r_dead(render, m, node)
    assert channel_id == 0 and spec.economic.mode == "real"
    # no corr_inflation_* key is both non-zero and pulling on a live shock
    assert dr._inflation_pulls(spec) == []
    # one figure per year, on every path
    small = dr._spec_at(spec, 40)
    streams = _held()
    run_monte_carlo(small, streams)
    expected = np.random.default_rng(1000)
    expected.normal(size=40 * spec.simulation.years)
    assert streams[0].bit_generator.state == expected.bit_generator.state


def _r_dead_market(render, m, node):
    spec, channel_id = _r_dead(render, m, node)
    assert channel_id == 1
    assert spec.simulation.value_growth_vol == 0.0
    assert not dr._crash_moves_a_value(spec)


def _r_dead_costs(render, m, node):
    spec, channel_id = _r_dead(render, m, node)
    assert channel_id in (3, 4, 5)


def _r_income(render, m, node):
    assert node["kind"] == "no_pv_reach" and node["keys"] == ["income.pay_drop_events"]
    assert render.raw["income"]["pay_drop_events"]
    _draws_and_reaches_nothing(render.spec, 7)


def _joined_row(render, node):
    return next(r for r in render.block["reversal"]["exact"]
                if r["key"] == node["reversal_key"])


def _stated_tail(render, m, node):
    row = _joined_row(render, node)
    assert m["key"] == node["reversal_key"] and m["option"] == row["option"]
    solved = bool(_solved(row))
    assert m["tail"].endswith("solved distance instead") == solved
    if not solved:
        refused = {r["verdict_field"] for r in row["refused_boundaries"]}
        assert {"best", "runner_up"} <= refused
    return row


def _r_stated_ladder(render, m, node):
    _stated_tail(render, m, node)
    option, leaf = node["reversal_key"].split(".", 1)
    assert isinstance(render.raw[option][leaf], list)


def _r_stated_rate(render, m, node):
    _stated_tail(render, m, node)
    from hde.deterministic import renewals_priced_inside
    option = m["option"]
    params = getattr(render.spec, option)
    horizon = render.spec.simulation.years
    assert not isinstance(render.raw[option]["mortgage_rate"], list)
    priced = renewals_priced_inside(params, horizon)
    if m["held"] == "held for the opening term":
        assert priced > 0
    elif m["term"] is not None:
        assert priced == 0 and int(m["term"]) == params.mortgage_term_years
        assert (params.mortgage_renewal_years is None
                or params.mortgage_renewal_years >= params.mortgage_term_years)
    else:
        assert priced == 0
        assert int(m["year"]) == params.mortgage_renewal_years + 1 > horizon
        assert int(m["horizon"]) == horizon


def _r_path_note(render, m, node):
    option, leaf = node["key"].split(".", 1)
    stated = render.raw[option][leaf]
    assert m["key"] == node["key"] and isinstance(stated, list) and len(set(stated)) > 1
    assert m["stated"] == ", ".join(_fmt_value(node["key"], float(v)) for v in stated)


def _r_unchanged(render, m, node):
    row, refused = node
    assert m["field"] == refused["verdict_field"]
    assert (m["lo"], m["hi"]) == (dt._rate(row["bracket_low"]), dt._rate(row["bracket_high"]))
    grid = list(np.linspace(row["bracket_low"], row["bracket_high"], 7))
    states = _sweep_states(render.path, row["key"], grid, futures=False)
    assert {s[m["field"]] for s in states} == {m["value"]}


def _r_futures_unchanged(render, m, node):
    row, refused = node
    assert m["field"] == refused["verdict_field"]
    assert int(m["n"]) == be.REVERSAL_SCAN_POINTS
    assert (m["lo"], m["hi"]) == (dt._rate(row["bracket_low"]), dt._rate(row["bracket_high"]))
    states = _sweep_states(render.path, row["key"],
                           [row["bracket_low"], row["bracket_high"]], futures=True)
    assert {s[m["field"]] for s in states} == {m["value"]}


def _r_no_distance(render, m, node):
    priced = _priced(render.raw)
    assert (m["options"] is not None) == (len(priced) > 2)
    candidates = be.reversal_candidates(render.raw)
    if m["found"] == "this config states no such key":
        assert candidates == []
        return
    named = re.findall(r"this config states ([\w.]+), and (moving it to the far end of the "
                       r"bracket moves no option's present value|the loader refuses it at "
                       r"the far end of the bracket)", m["found"])
    assert "; ".join(f"this config states {k}, and {w}" for k, w in named) == m["found"]
    assert [k for k, _ in named] == [k for k, _ in candidates]
    for key, words in named:
        admitted, record = be.reversal_admission(render.raw, key, be.reversal_bracket(key)[1])
        assert not admitted
        if words.startswith("moving it"):
            assert record["deltas"] and all(d == 0.0 for d in record["deltas"].values())
        else:
            assert record["why"].startswith("the loader refuses")


REASON_CLAIMS: Dict[str, Callable[..., None]] = {
    "NO_FUTURES": _r_no_futures,
    "TOO_FEW": _r_too_few,
    "SINGLE_OPTION": _r_single_option,
    "ONE_CHANNEL": _r_one_channel,
    "NO_SPREAD_UNREACHED": _r_no_spread_unreached,
    "NO_SPREAD_CONSTANT": _r_no_spread_constant,
    "BUDGET": _r_budget,
    "NO_SIGN_VARIATION": _r_no_sign_variation,
    "DEAD_ECONOMY": _r_dead_economy,
    "DEAD_MARKET": _r_dead_market,
    "DEAD_COSTS": _r_dead_costs,
    "INCOME": _r_income,
    "STATED_LADDER": _r_stated_ladder,
    "STATED_RATE": _r_stated_rate,
    "PATH_NOTE": _r_path_note,
    "UNCHANGED": _r_unchanged,
    "FUTURES_UNCHANGED": _r_futures_unchanged,
    "NO_DISTANCE": _r_no_distance,
}


def test_every_engine_reason_is_a_template():
    for render in renders():
        if render.engine:
            _reasons_of(render)


def test_every_reason_template_is_printed_or_forced():
    """Every reason reaches a run of the engine, or names the test that forces
    it — and that test exists."""
    reached = {name for r in renders() if r.engine for name, *_ in _reasons_of(r)}
    assert reached == set(REASON_CLAIMS), set(REASON_CLAIMS) ^ reached
    for name, node_id in SEAM_ONLY.items():
        path, *names = node_id.split("::")
        module = importlib.import_module(path[:-3].replace("/", "."))
        target = module
        for part in names:
            target = getattr(target, part)
        assert callable(target), (name, node_id)


@pytest.mark.parametrize("template", list(REASON_CLAIMS))
def test_the_reason_says_what_is_so(template):
    checked = 0
    for render in renders():
        if not render.engine:
            continue
        for name, m, where, node in _reasons_of(render):
            if name == template:
                REASON_CLAIMS[template](render, m, node)
                checked += 1
    assert checked, template


# ---------------------------------------------------------------------------
# The seams the engine reaches only by a direct call
# ---------------------------------------------------------------------------

def test_a_field_the_axis_never_reproduces_says_so():
    """"says so nowhere": the run's own state appears in none of the regions."""
    found, anomaly = be._region_boundaries(
        "house.mortgage_rate", "best", "rent", ["condo", "house"],
        [(0.01, 0.05), (0.05, 0.10)], lambda i, step: 0.05, (0.01, 0.10))
    assert found == [] and REASONS["SAYS_SO_NOWHERE"].match(anomaly["why"])
    assert "rent" not in ["condo", "house"]


def test_a_boundary_with_no_probability_is_not_identified():
    record = be._identification("mc_best", {"was": "condo", "becomes": "house"},
                                {"lo": {}, "hi": {}, "at": {}}, "condo", 100)
    assert not record["identified"] and record["watched"] == []
    assert REASONS["NO_PROBABILITY"].match(record["why"])


def test_a_gate_handed_no_figures_for_its_option_raises():
    """The key's option is in the config, so a run with no present values for
    it is a producer defect: the gate raises rather than printing a reason for
    a case the engine cannot produce."""
    raw = _load(MORTGAGE)

    def without_the_house(spec):
        return dataclasses.replace(run_monte_carlo(spec), house=None)

    with pytest.raises(ValueError, match="nothing to measure"):
        be.reversal_gate(raw, "house.mortgage_rate", 0.10, paths=40,
                         simulate=without_the_house)


def test_a_block_handed_no_config_mapping_searched_no_key():
    got = run("fixture")
    det, mc, verdict = got.inputs()
    spec = dr._spec_at(got.spec, 40)
    outcome = dr.decompose(spec, det=det, mc=mc, verdict=verdict, raw=None, prior=None,
                           paths=40)
    reversal = outcome.reversal
    assert reversal.exact == () and reversal.estimated == ()
    assert REASONS["NO_DISTANCE_NO_MAPPING"].match(reversal.no_distance_reason)


def test_a_register_on_one_option_has_no_verdict_to_reverse():
    spec = load_config_dict(CONDO_ONLY)
    register = be.reversal_register(copy.deepcopy(CONDO_ONLY), compute_deterministic(spec),
                                    run_monte_carlo(spec))
    assert len(_priced(CONDO_ONLY)) == 1
    assert register.exact == () and register.estimated == ()
    assert REASONS["NO_DISTANCE_ONE_OPTION"].match(register.no_distance_reason)


def test_a_key_the_loader_refuses_at_the_far_end_is_named_as_that(monkeypatch):
    """The empty register never calls a refused probe a key that moved
    nothing: the loader's refusal is named as the loader's."""
    raw = copy.deepcopy(run("inert").raw)
    real_load_at = be.load_at

    def refuse_far_end(doc, key, value):
        if key == "condo.mortgage_rate" and value == be.reversal_bracket(key)[1]:
            raise be.ConfigValidationError("a refusal the test put there")
        return real_load_at(doc, key, value)

    monkeypatch.setattr(be, "load_at", refuse_far_end)
    spec = load_config_dict(raw)
    register = be.reversal_register(raw, compute_deterministic(spec), run_monte_carlo(spec))
    reason = register.no_distance_reason
    assert REASONS["NO_DISTANCE"].match(reason)
    assert ("this config states condo.mortgage_rate, and the loader refuses it at the far "
            "end of the bracket") in reason
    assert "moves no option's present value" not in reason


# ---------------------------------------------------------------------------
# Claims a single render cannot check
# ---------------------------------------------------------------------------

def test_at_the_level_cap_a_larger_run_prices_the_same_level_register():
    """"this register prices at most 2,000 futures on this run and is at that
    count, so no larger run resolves it here" — on basic_config at 2,000
    futures. A run at 2,400 prices the same first 2,000 futures for the level
    register and prints the same figures, so its top row does not resolve
    there either."""
    at_cap = run("basic_2000")
    assert "no larger run resolves it here" in at_cap.text
    larger = _cli_render("basic_2400", BASIC, "2400")
    assert larger.block["level"] == at_cap.block["level"]
    assert larger.block["level"]["unresolved_top_channel_id"] is not None


def test_the_capped_run_is_at_its_cap_on_both_registers():
    """The patched run exists to print the spread register's own cap; if a
    later change resolved its figures there, the at-cap route would go
    unprinted and `test_every_line_template_is_printed` would not notice which
    register lost it."""
    capped = _capped()
    routes = [line.m["route"] for line in _lines(capped) if "route" in line.m.groupdict()]
    assert sum("is at that count" in route for route in routes) >= 2, routes
    assert capped.block["paths"] == capped.block["max_paths"]
    assert capped.over.block["refusal"]["code"] == "budget"


def test_the_level_top_row_is_named_by_its_size_on_a_shipped_example():
    """advanced_config: the house's costs shift the margin by -$1,575 and the
    economy by +$93. The top row is the house's costs — by SIZE — and the
    closing names it. Signed, the economy's +$93 is "the largest", which is
    the smaller-figure-called-the-largest defect.
    *Kills it:* dropping `abs` from `decomposition_run._level_point`."""
    got = run("advanced")
    level = got.block["level"]
    top = level["unresolved_top_channel_id"]
    assert top == 4, level
    row = next(r for r in level["rows"] if r["channel_id"] == 4)
    assert _shift(row) < 0
    assert f"the house's costs at {dt._shift(_shift(row))}" in got.text
    assert any(_shift(r) > 0 for r in level["rows"])
