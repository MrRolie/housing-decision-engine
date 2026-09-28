"""Every sentence the `--decompose` block prints, and a test of what it claims.

The block is built from sentence TEMPLATES: the lines `hde.decomposition_text`
writes, and the reason strings the assembler (`hde.decomposition_run`) and the
reversal register (`hde.break_even`) write for it. Every template is one of
the six KINDS of spec §0.1 items 35 and 41 (`SIX_KINDS`) — a heading, a figure
row, a crossing, a path note, a refusal (its code and the one measured fact
that fired it) or a structural-zero row — and `KINDS` records which, so a
template that is none of them has nowhere to go.

`LINES` holds every line template as one pattern over one printed line;
`REASONS` holds every engine-written reason as one pattern over the reason
string. The inventory is closed in both directions:

  - every line the block prints on the renders below matches exactly one line
    template, and every reason in those runs' `--json` exactly one reason
    template;
  - every template is printed somewhere in them — or, for a reason only a
    patched seam can produce, names the test that produces it.

Each template's CLAIM is checked where it prints: its figures and words
against the same run's `--json`, and what it says about the run — which side
of a threshold, which row is on top, what a key reads either side of a
crossing, what a draw reaches — against the JSON's own fields, the
read-back's source echo, a `--sweep`, the free curve, or the instruments in
`tests/decomposition_oracles.py`, never the engine's own measurement. The
JSON's figures are re-derived from the block's own matrices in
`test_decomposition_contract_doc.py`, so a printed sentence is tied to what is
so by text -> JSON here and JSON -> re-derivation there.

The renders: the shared corpus of real runs (`decomposition_runs.CORPUS`), a
config for each whole-block refusal, and the hand-built households
(`decomposition_households`), whose lines are checked against their own
serialized JSON.
"""
from __future__ import annotations

import copy
import dataclasses
import decimal
import functools
import importlib
import math
import pathlib
import re
import types
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pytest
import yaml

import hde.break_even as be
import hde.decomposition as dc
import hde.decomposition_math as dm
import hde.decomposition_run as dr
import hde.decomposition_text as dt
from hde.anchors import ANCHORS
from hde.config import load_config_dict, single_path_run
from hde.decomposition_math import LEVEL_RESOLUTION_SIGMAS
from hde.rates import effective_mortgage_rate
from hde.serialization import decomposition_to_dict
from hde.sweep import _fmt_value, stated_path

from tests import decomposition_households as hh
from tests.decomposition_oracles import oracle_drawn, oracle_moves
from tests.decomposition_runs import (
    _SCRATCH, CONDO_ONLY, CRASH_EVERY_YEAR, FIXTURE, INCOME, INCOME_ONLY, MONTREAL,
    MORTGAGE, NO_REACH, RARE2, THIRD_FAR, THIRD_FAR_ONE, CONTRACT, _block_text, _cli, _load,
    _strict, _sweep_states, corpus, run)
from tests.test_decomposition_liveness import RESET_TO_OWN_RENT_ALONE

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


def _cli_render(name, source, *extra):
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
    return Render(name, _block_text(out), doc, raw=raw, path=path, extra=extra)


REFUSALS = {
    "no_futures_two": (MONTREAL,),
    "no_futures_three": (FIXTURE, "--no-monte-carlo"),
    "no_futures_one": (CONDO_ONLY, "--no-monte-carlo"),
    "single_option": (CONDO_ONLY,),
    "one_channel": (INCOME,),
    # one channel moves a present value, and never the margin: the margin is
    # one figure on every future
    "no_spread_third_far_one": (THIRD_FAR_ONE,),
    # the real-mode inflation trap: one figure on every future
    "no_spread_real_trap": (NO_REACH,),
    # the income pay-drop draw moves the affordability report and no margin
    "no_spread_income_only": (INCOME_ONLY,),
    # the margin differs in its last bits only, and no channel is live
    "no_spread_unreached": (RESET_TO_OWN_RENT_ALONE,),
    "no_spread_constant": (TWINS,),
    # the same, on a margin below zero
    "no_spread_constant_below_zero": (CRASH_EVERY_YEAR,),
    # two channels move rent, which never enters the margin (§0.1 item 37)
    "no_spread_third_far": (THIRD_FAR,),
    # the fixture's eight streams draw, and 23,201 futures are one past the
    # largest count the ceiling admits at eight
    "budget": (FIXTURE, "23201"),
    # more futures than the ceiling, refused before anything is priced
    "budget_n": (FIXTURE, "250001"),
    "too_few": (MORTGAGE, "39"),
    "too_few_one": (MORTGAGE, "1"),
    # a bootstrap resample holding one value of the margin
    "degenerate_resample": (RARE2, "400"),
}


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
    for name in HOUSEHOLDS:
        out.append(_household(name))
    return tuple(out)


# ---------------------------------------------------------------------------
# The line templates
# ---------------------------------------------------------------------------

# The words the block must print for each verdict field — written here, not
# read from the formatter, so a mapping changed there is caught here rather
# than agreed with.
FIELD_WORDS = {
    "best": "the central case's winner",
    "runner_up": "the runner-up",
    "mc_best": "the option most futures call cheapest",
    "decisive": "the decisiveness verdict",
}

LABEL = "(?:" + "|".join(re.escape(c.label) for c in dc.CHANNELS) + ")"
OPTION = r"(?:condo|house|rent)"
BOUND = "(?:" + "|".join(re.escape(v) for v in FIELD_WORDS.values()) + ")"
STATE = r"(?:decisive for \w+|not decisive|condo|house|rent)"
SHARE = r"-?\d+\.\d+"
CI = rf"\[{SHARE}, {SHARE}\]"
MONEY = r"-?\$[\d,]+"
# A level row's dollars carry cents or more where the row's judgment needs
# them (§0.1 item 62).
DOLLARS = r"\$[\d,]+(?:\.\d+)?"
SHIFT = rf"(?:[+-]{DOLLARS}|\$0(?:\.0+)?)"
PROB = r"\d+\.\d+"
PCT = r"\d+\.\d+%"
N = r"[\d,]+"

_CROSS = (rf"as it rises past (?P<value>{{value}}), (?P<field>{BOUND}) changes from "
          rf"(?P<was>{STATE}) to (?P<becomes>{STATE})(?: \(and changes again "
          rf"(?P<further>above|below) it, inside the bracket\))?")
# Either kind widens its precision until the field says `was` at the figure
# (§0.1 item 54), so a figure's decimals do not tell the kinds apart: the
# line's prefix does, and the claims below pin the prefix to the kind.
_CROSS_SOLVED = _CROSS.format(value=r"\d+\.\d{4,}%")
_CROSS_SAMPLED = _CROSS.format(value=r"\d+\.\d{2,}%")
_CROSS_ESTIMATED = _CROSS.format(value=rf"\d+\.\d{{2}}% \(inside (?P<lo>{PCT})–(?P<hi>{PCT})\)")

LINES: Dict[str, "re.Pattern"] = {name: re.compile(pattern) for name, pattern in {
    "BLANK": r"^$",
    "HEADER": (rf"^which risk decides it — (?P<paths>{N}) futures, (?P<live>\d+) channels "
               rf"live on them$"),
    "REFUSAL": r"^which risk decides it — not split \((?P<code>\w+)\): (?P<reason>.+)$",
    "MARGIN": (rf"^  margin, the cheapest other option's present value minus "
               rf"(?P<best>{OPTION})'s: central case (?P<margin>{MONEY}); over this block's "
               rf"own (?P<paths>{N}) futures, mean (?P<mean>{MONEY}) and s\.d\. "
               rf"(?P<sd>{MONEY})$"),
    "SPREAD_HEAD": r"^  THE SPREAD$",
    "SPREAD_REFUSED": r"^  not split \((?P<code>\w+)\): (?P<reason>.+)$",
    "SPREAD_COLS": (rf"^  channel +alone +with interaction +flips whether "
                    rf"(?P<best>{OPTION}) is cheapest$"),
    "SPREAD_ROW": (rf"^  (?P<label>{LABEL}) +(?:(?P<alone>{SHARE}) (?P<alone_ci>{CI}) +"
                   rf"(?P<both>{SHARE}) (?P<both_ci>{CI})|not resolved: (?P<p_alone>{SHARE}) "
                   rf"(?P<p_alone_ci>{CI}) +not resolved: (?P<p_both>{SHARE}) "
                   rf"(?P<p_both_ci>{CI})) +(?P<flip>{PCT} \[\d+\.\d+, \d+\.\d+\])$"),
    "WIDTHS": r"^      sized by (?P<cells>.+)$",
    "SPREAD_SUMS": (rf"^  alone shares summed before rounding: (?P<sum>{SHARE}) "
                    rf"(?P<sum_ci>{CI})(?:; 1 minus that sum: (?:(?P<res>{SHARE}) "
                    rf"(?P<res_ci>{CI})|(?P<unresolved>not resolved)))?$"),
    "SPREAD_GAPS": r"^  with interaction minus alone, before rounding: (?P<parts>.+)$",
    "SPREAD_TOP": rf"^  largest alone share: (?P<label>{LABEL})$",
    "LEVEL_HEAD": rf"^  THE LEVEL — the first (?P<m>{N}) of these futures$",
    "LEVEL_BASE": (rf"^  as drawn: mean margin (?P<futures>{MONEY}), P\((?P<best>{OPTION}) "
                   rf"cheapest\) (?P<p>{PROB}); the central case's margin minus that mean: "
                   rf"(?P<gap>{MONEY})$"),
    "LEVEL_COLS": (rf"^  channel +margin shift, channel frozen \(± 1 s\.e\.\) +"
                   rf"P\((?P<best>{OPTION}) cheapest\), channel frozen$"),
    "LEVEL_ROW": (rf"^  (?P<label>{LABEL}) +(?P<unresolved>not resolved: )?(?P<delta>{SHIFT}) "
                  rf"\(± (?P<se>{DOLLARS})\) +(?P<p>{PROB})$"),
    "LEVEL_SUM": rf"^  the (?P<n>\d+) shifts above, summed: (?P<sum>-?{DOLLARS})$",
    "LEVEL_TOP": rf"^  largest shift in size: (?P<label>{LABEL})$",
    "ZERO_DRAWN": (rf"^  (?P<label>[^—:]+?): drawn on these (?P<n>{N}) futures, and "
                   rf"re-drawing it moved no option's present value by more than "
                   rf"\$(?P<threshold>[\d.e+-]+)(?:; sized by (?P<keys>[\w.]+(?:, "
                   rf"[\w.]+)*))?$"),
    "ZERO_HEAD": r"^  NO ROW IN THE SPREAD OR THE LEVEL$",
    "ZERO_STATED": (r"^  (?P<label>[^—:]+?) — (?P<keys>[\w.]+(?:, [\w.]+)*): no draw "
                    r"touches it$"),
    "EXACT_HEAD": r"^  WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly$",
    "ESTIMATED_HEAD": r"^  WHAT WOULD HAVE TO CHANGE — keys the engine cannot re-price exactly$",
    "NO_DISTANCE": (r"^  WHAT WOULD HAVE TO CHANGE — not solved \((?P<code>\w+)\): "
                    r"(?P<reason>.+)$"),
    "ROW_HEAD": (r"^  (?P<key>[a-z_]+(?:\.[a-z_]+)+), stated (?P<stated>.+) "
                 r"\[(?P<tag>[\w.]+)\]$"),
    "BRACKET": (rf"^      bracket searched: (?P<lo>{PCT})–(?P<hi>{PCT}) "
                rf"\[(?P<src>[\w ]+)\]$"),
    "PATH_NOTE": (r"^      (?P<note>each crossing on this key is priced with the stated "
                  r"path \((?P<stated>[^)]+)\) replaced by one rate at every renewal)$"),
    "CROSS_SOLVED": rf"^      solved on the central case: {_CROSS_SOLVED}$",
    "CROSS_SAMPLED": (rf"^      sampled on (?P<paths>{N}) paths at seed (?P<seed>\d+): "
                      rf"{_CROSS_SAMPLED}$"),
    "CROSS_ESTIMATED": (rf"^      estimated on (?P<n>{N}) re-simulated paths: "
                        rf"{_CROSS_ESTIMATED}$"),
    "REFUSED_BOUNDARY": (rf"^      (?P<head>no boundary printed|a boundary not printed) for "
                         rf"(?P<fields>{BOUND}(?:(?:, | or ){BOUND})*) \((?P<code>\w+)\): "
                         rf"(?P<reason>.+)$"),
    "REFERENCES": r"^      on the same axis: (?P<refs>.+)$",
}.items()}

# The six kinds a line may be (spec §0.1 items 35 and 41). A line that is none
# of them is interpretation, and interpretation is the assistant's.
SIX_KINDS = {"header", "figure row", "crossing", "path note", "refusal", "structural zero"}

# What each template IS.
KINDS = {
    "BLANK": "layout",
    "HEADER": "header", "SPREAD_HEAD": "header", "SPREAD_COLS": "header",
    "LEVEL_HEAD": "header", "LEVEL_COLS": "header", "ZERO_HEAD": "header",
    "EXACT_HEAD": "header", "ESTIMATED_HEAD": "header",
    "MARGIN": "figure row", "SPREAD_ROW": "figure row", "WIDTHS": "figure row",
    "SPREAD_SUMS": "figure row", "SPREAD_GAPS": "figure row", "SPREAD_TOP": "figure row",
    "LEVEL_BASE": "figure row", "LEVEL_ROW": "figure row", "LEVEL_SUM": "figure row",
    "LEVEL_TOP": "figure row", "ROW_HEAD": "figure row", "BRACKET": "figure row",
    "REFERENCES": "figure row",
    "CROSS_SOLVED": "crossing", "CROSS_SAMPLED": "crossing", "CROSS_ESTIMATED": "crossing",
    "PATH_NOTE": "path note",
    "REFUSAL": "refusal", "SPREAD_REFUSED": "refusal", "REFUSED_BOUNDARY": "refusal",
    "NO_DISTANCE": "refusal",
    "ZERO_STATED": "structural zero", "ZERO_DRAWN": "structural zero",
}


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


def _hits(text):
    return [(name, pattern.match(text)) for name, pattern in LINES.items()
            if pattern.match(text)]


def _by_label(rows, label):
    return next(r for r in rows if r["label"] == label)


@functools.lru_cache(maxsize=None)
def _lines(render: Render) -> Tuple[Line, ...]:
    out: List[Line] = []
    section, spread_row, reversal_row = "head", None, None
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
        elif name == "EXACT_HEAD":
            section = "exact"
        elif name == "ESTIMATED_HEAD":
            section = "estimated"
        elif name == "ROW_HEAD":
            reversal_row = next(r for r in block["reversal"][section] if r["key"] == m["key"])
        elif name == "NO_DISTANCE":
            section = "empty"
        out.append(Line(render, name, m, section, spread_row, reversal_row))
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


def _read_back_tag(doc, key) -> Optional[str]:
    """The tag the contract gives `key`: for a key the config states, the
    anchor `assumptions.sources` names where it files the key under `anchor`,
    and otherwise the class it files the key under (`user`, `assistant` or
    `unattributed`); for a key the run defaulted, the cite the `defaults
    applied:` line brackets beside it, read off that line's TEXT, character
    for character. None otherwise."""
    echo = doc["assumptions"]["sources"]
    anchored = echo.get("anchor") or {}
    if key in anchored:
        return anchored[key]
    for source in ("user", "assistant", "unattributed"):
        if any(entry["key"] == key for entry in echo.get(source) or ()):
            return source
    for line in doc["assumptions"]["lines"]:
        label, _, rest = line.strip().partition(": ")
        if label == "defaults applied":
            m = re.search(rf"(?:^|, ){re.escape(key)}=[^\[]*? \[(?P<tag>[^\]]+)\]", rest)
            if m:
                return m["tag"]
    return None


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
    from hde.monte_carlo import run_monte_carlo
    mc = run_monte_carlo(spec, _held(overrides))
    return {o: np.asarray(getattr(mc, o).pvs).tobytes()
            for o in ("condo", "house", "rent") if getattr(mc, o) is not None}


def _run_inputs(render):
    from hde.deterministic import compute_deterministic
    from hde.models import compute_verdict
    from hde.monte_carlo import run_monte_carlo
    spec = render.spec
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    return det, mc, verdict


@functools.lru_cache(maxsize=None)
def _threshold(render):
    """The identity's budget on this run, read from its one home."""
    det, _, verdict = _run_inputs(render)
    return dr.identity_budget(det, verdict)


@functools.lru_cache(maxsize=None)
def _instruments(render, paths):
    """What the held-generator instruments say about this run's streams on
    `paths` futures: `(drawn, largest move per drawing stream)`."""
    drawn = oracle_drawn(render.spec)
    moves = oracle_moves(render.spec, paths)
    return drawn, {c: moves[c] for c in drawn}


def _live_by_instrument(render, paths):
    drawn, moves = _instruments(render, paths)
    limit = _threshold(render)
    return tuple(sorted(c for c in drawn if c < dc.INCOME_STREAM_ID and moves[c] > limit))


# ---------------------------------------------------------------------------
# What each line claims
# ---------------------------------------------------------------------------

def _requested(render):
    return (int(render.extra[0]) if render.extra and render.extra[0].isdigit()
            else render.spec.simulation.num_sims)


def _header(line):
    """"N futures, k channels live on them": the count against the JSON, and
    the JSON's live channels against the held-generator instruments on the
    same count of futures."""
    m, block, render = line.m, line.render.block, line.render
    assert _whole(m["paths"]) == block["paths"]
    assert int(m["live"]) == len(block["live_channel_ids"])
    if render.engine:
        assert block["paths"] == _requested(render)
        assert tuple(block["live_channel_ids"]) == _live_by_instrument(
            render, block["paths"])


def _refusal(line):
    m, refusal = line.m, line.render.block["refusal"]
    assert m["code"] == refusal["code"] and m["code"] in dc.REFUSAL_CODES
    assert m["reason"] == refusal["reason"]
    assert _REFUSAL_REASON[m["code"]].fullmatch(m["reason"]), m["reason"]


def _margin(line):
    m, block, verdict = line.m, line.render.block, line.render.verdict
    assert m["best"] == verdict["best"]
    assert m["margin"] == dt._money(verdict["margin_pv"])
    assert _whole(m["paths"]) == block["paths"]
    assert m["mean"] == dt._money(block["mean_margin"])
    assert m["sd"] == dt._money(block["sd_margin"])
    if line.render.engine:
        # "the cheapest other option's present value minus <best>'s", on the
        # central case this run printed
        pvs = {o: line.render.doc["deterministic"][o]["total_pv"]
               for o in ("condo", "house", "rent") if line.render.doc["deterministic"][o]}
        others = [pv for o, pv in pvs.items() if o != verdict["best"]]
        assert math.isclose(min(others) - pvs[verdict["best"]], verdict["margin_pv"],
                            rel_tol=1e-12, abs_tol=1e-6)


def _spread_refused(line):
    spread = line.render.block["spread"]
    assert set(spread) == {"refusal", "structural_zeros"}
    assert line.m["code"] == spread["refusal"]["code"] == "no_sign_variation"
    assert line.m["reason"] == spread["refusal"]["reason"]


def _spread_cols(line):
    assert line.m["best"] == line.render.verdict["best"]


def _spread_row(line):
    m, row = line.m, line.spread_row
    unresolved = m["p_alone"] is not None
    assert unresolved == (not row["resolved"])
    # the resolution rule, both ways: both point estimates in [0, 1]
    inside = (0.0 <= _point(row) <= 1.0 and 0.0 <= _together(row) <= 1.0)
    assert row["resolved"] == inside
    prefix, group = ("", "") if row["resolved"] else ("provisional_", "p_")
    assert m[f"{group}alone"] == dt._share(row[f"{prefix}alone"])
    assert m[f"{group}alone_ci"] == dt._interval(_ci(row[f"{prefix}alone_ci"]))
    assert m[f"{group}both"] == dt._share(row[f"{prefix}with_interaction"])
    assert m[f"{group}both_ci"] == dt._interval(_ci(row[f"{prefix}with_interaction_ci"]))
    assert m["flip"] == dt._flip_cell(row["flip"], _ci(row["flip_ci"]))


def _defaulted(doc, key):
    """The read-back's `defaults applied` entry for `key`, or None."""
    return next((e for e in doc["assumptions"]["defaults_applied"] if e["key"] == key),
                None)


def _widths(line):
    assert line.m["cells"] == _width_cells(line.spread_row["widths"])
    if line.render.engine:
        for width in line.spread_row["widths"]:
            # the tag printed is the read-back's for that key, character for
            # character (§0.1 item 53)
            assert width["tag"] == _read_back_tag(line.render.doc, width["key"]), width
            # whose figure it is: the read-back's class for a stated key, and
            # for a key the engine filled in, its `defaults applied` entry
            default = _defaulted(line.render.doc, width["key"])
            if width["source"] == "default":
                assert default is not None and _echo_class(line.render.doc,
                                                           width["key"]) is None
                assert (width["anchor"], width["formatted"]) == (
                    default["anchor"]["name"], default["formatted"]), width
            else:
                assert width["source"] == _echo_class(line.render.doc, width["key"]), width
            if width["note"] is not None:
                # "(pulled by KEY = rho; rho squared rho²)", figures from the config
                note = re.fullmatch(r"pulled by (?P<key>[\w.]+) = (?P<rho>[-\d.e]+); rho "
                                    r"squared (?P<sq>[-\d.e]+)", width["note"])
                assert note, width["note"]
                rho = float(note["rho"])
                option_key = note["key"].rsplit(".", 1)[-1]
                assert getattr(line.render.spec.simulation, option_key) == rho
                assert note["sq"] == f"{rho * rho:g}"


def _spread_sums(line):
    m, block = line.m, line.render.block
    interaction = block["spread"]["interaction"]
    assert m["sum"] == dt._share(interaction["first_order_sum"])
    assert m["sum_ci"] == dt._interval(_ci(interaction["first_order_sum_ci"]))
    # "summed before rounding": the unrounded points of every row, resolved or not
    rows = block["spread"]["rows"]
    if line.render.engine:
        assert math.isclose(interaction["first_order_sum"], sum(_point(r) for r in rows),
                            rel_tol=1e-9, abs_tol=1e-12)
    # the residual resolves exactly when the sum's interval lies below 1; it
    # is "not resolved" when the interval includes 1, and has no clause when
    # the interval lies above 1 (§4)
    low, high = (interaction["first_order_sum_ci"]["low"],
                 interaction["first_order_sum_ci"]["high"])
    resolved = high < 1.0
    assert interaction["resolved"] == resolved == (m["res"] is not None)
    assert (m["unresolved"] is not None) == (low <= 1.0 <= high)
    assert (m["res"] is None and m["unresolved"] is None) == (low > 1.0)
    if resolved:
        assert math.isclose(interaction["residual"], 1.0 - interaction["first_order_sum"],
                            abs_tol=1e-12)
        assert m["res"] == dt._share(interaction["residual"])
        assert m["res_ci"] == dt._interval(_ci(interaction["residual_ci"]))


_GAP_PART = re.compile(rf"(?P<label>{LABEL}) (?P<unresolved>not resolved: )?"
                       rf"(?P<gap>{SHARE}) (?P<ci>{CI})")


def _printed_spread_order(render):
    return [line.spread_row for line in _lines(render) if line.template == "SPREAD_ROW"]


def _spread_gaps(line):
    """Every row's gap, in the table's order, behind "not resolved:" exactly
    where its interval's low end does not lie above zero."""
    spread = line.render.block["spread"]
    rows = _printed_spread_order(line.render)
    parts = [_GAP_PART.fullmatch(p) for p in line.m["parts"].split("; ")]
    assert all(parts), line.m["parts"]
    assert [p["label"] for p in parts] == [r["label"] for r in rows]
    # the rule, both ways
    resolving = [r for r in rows if r["interaction_gap_ci"]["low"] > 0.0]
    assert sorted(spread["interaction_channel_ids"]) == sorted(
        r["channel_id"] for r in resolving)
    for part, row in zip(parts, rows):
        assert (part["unresolved"] is None) == (row in resolving)
        assert part["gap"] == dt._share(row["interaction_gap"])
        assert part["ci"] == dt._interval(_ci(row["interaction_gap_ci"]))
        # "with interaction minus alone, before rounding"
        assert math.isclose(row["interaction_gap"], _together(row) - _point(row),
                            rel_tol=1e-9, abs_tol=1e-12)


def _top(line, rows, leading, unresolved_top, size):
    """The engine's one top-row rule: the largest point estimate over every
    row, resolved or not — printed only when that row resolved and leads
    (`test_a_top_line_prints_exactly_where_the_top_row_leads` is the absence)."""
    row = _by_label(rows, line.m["label"])
    assert size(row) == max(size(r) for r in rows)
    assert row["resolved"] and leading == row["channel_id"] and unresolved_top is None


def _spread_top(line):
    spread = line.render.block["spread"]
    _top(line, spread["rows"], spread["leading_channel_id"],
         spread["unresolved_top_channel_id"], _point)


def _level_head(line):
    level, block = line.render.block["level"], line.render.block
    assert _whole(line.m["m"]) == level["paths"]
    if line.render.engine:
        assert level["paths"] == min(block["paths"], dc.LEVEL_PATHS)


def _level_base(line):
    m, level, verdict = line.m, line.render.block["level"], line.render.verdict
    assert m["futures"] == dt._money(level["futures_margin"])
    assert m["best"] == verdict["best"]
    assert m["p"] == dt._prob(level["prob_best_base"])
    # "the central case's margin minus that mean", on the printed dollars; the
    # all-frozen margin, printed, IS the central case's printed margin
    assert dt._money(level["all_frozen_margin"]) == dt._money(verdict["margin_pv"])
    assert _whole(m["gap"]) == (_whole(dt._money(level["all_frozen_margin"]))
                                - _whole(m["futures"]))


def _level_cols(line):
    assert line.m["best"] == line.render.verdict["best"]


def _dollars(text):
    """The figure a printed dollar amount names, with its sign."""
    return decimal.Decimal(text.replace("$", "").replace(",", "").replace("+", ""))


def _places(text):
    digits = text.replace("$", "").replace(",", "").lstrip("+-")
    return len(digits.split(".")[1]) if "." in digits else 0


# The precisions a level row may print at (§0.1 item 62): whole dollars, then
# cents, then one more decimal at a time.
_LEVEL_PLACES = (0, *range(2, 30))


def _shows(shift, se, resolved):
    """Whether a printed pair shows the row's judgment: the shift's size
    above twice the s.e. exactly when the row resolved."""
    return (abs(shift) > 2 * se) == resolved


def _level_row(line):
    """The row's figures are the JSON's, rounded to the nearest at the
    decimals printed; those decimals are the least of whole dollars, cents,
    then one more at a time at which the printed pair shows the judgment
    (§0.1 item 62)."""
    m = line.m
    row = _by_label(line.render.block["level"]["rows"], m["label"])
    assert (m["unresolved"] is None) == row["resolved"]
    # the resolution rule, both ways
    assert row["resolved"] == (abs(_shift(row)) > LEVEL_RESOLUTION_SIGMAS * row["se"])
    places = _places(m["se"])
    assert _places(m["delta"]) == places, m.group(0)
    shift, se = _dollars(m["delta"]), _dollars(m["se"])
    exact = decimal.Decimal(_shift(row))
    step = decimal.Decimal(1).scaleb(-places)
    assert abs(abs(shift) - abs(exact)) <= step / 2, (m["delta"], _shift(row))
    assert abs(se - decimal.Decimal(row["se"])) <= step / 2, (m["se"], row["se"])
    # a printed zero carries no sign, and any other shift carries its own
    assert (m["delta"][0] in "+-") == (shift != 0)
    if shift != 0:
        assert (m["delta"][0] == "-") == (_shift(row) < 0)
    assert _shows(shift, se, row["resolved"]), m.group(0)
    for fewer in _LEVEL_PLACES[:_LEVEL_PLACES.index(places)]:
        at = decimal.Decimal(f"{_shift(row):.{fewer}f}")
        at_se = decimal.Decimal(f"{row['se']:.{fewer}f}")
        assert not _shows(at, at_se, row["resolved"]), (m.group(0), fewer)
    assert m["p"] == dt._prob(row["prob_best_frozen"])


def _level_sum(line):
    """The sum of the printed shifts, at the most decimals a row prints."""
    level = line.render.block["level"]
    assert int(line.m["n"]) == len(level["rows"])
    rows = [l for l in _lines(line.render) if l.template == "LEVEL_ROW"]
    assert len(rows) == len(level["rows"])
    total = sum((_dollars(l.m["delta"]) for l in rows), decimal.Decimal(0))
    places = max(_places(l.m["delta"]) for l in rows)
    assert _places(line.m["sum"]) == places
    assert _dollars(line.m["sum"]) == total, (line.m["sum"], total)


def _level_top(line):
    level = line.render.block["level"]
    _top(line, level["rows"], level["leading_channel_id"],
         level["unresolved_top_channel_id"], lambda r: abs(_shift(r)))


def _zero_head(line):
    """The reversal register's rows with no place in the spread or the level:
    the stated paths, which no sample measured (§0.1 item 48)."""
    zeros = line.render.block["reversal"]["structural_zeros"]
    assert zeros and {z["kind"] for z in zeros} == {"stated_path"}


# Which register holds each kind of row, and the section of the text it
# prints in: a row measured on the block's futures is the spread register's
# (§0.1 item 48).
_ZERO_HOME = {"stated_path": ("reversal", "zero"), "dead_draw": ("spread", "spread")}


def _zero_row_of(line, kind):
    m, render = line.m, line.render
    register, section = _ZERO_HOME[kind]
    assert line.section == section, (m.group(0), line.section)
    held = render.block[register]["structural_zeros"]
    zeros = [z for z in held if z["kind"] == kind and z["label"] == m["label"]
             and ", ".join(z["keys"]) == (m["keys"] or "")]
    assert len(zeros) == 1, (m.group(0), held)
    return zeros[0]


def _zero_stated(line):
    """"no draw touches it": moving the stated key moves no generator's state."""
    render = line.render
    zero = _zero_row_of(line, "stated_path")
    assert set(zero) == {"kind", "label", "keys", "reversal_key"}
    assert list(zero["keys"]) == [zero["reversal_key"]]
    leaf = zero["reversal_key"].rsplit(".", 1)[-1]
    assert zero["label"] == {"mortgage_renewal_rates": "the renewal rate",
                             "mortgage_rate": "the contract rate"}[leaf]
    if not render.engine:
        return
    from hde.monte_carlo import run_monte_carlo
    spec = render.spec
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


def _zero_drawn(line):
    """Each claim at its own grain (§0.1 items 39 and 40). Of the STREAM: it
    drew on these N futures (its held generator advances), and re-drawing it
    moved no option's present value by more than the printed threshold (its
    re-seeding, on held generators and as many futures). Of the threshold: it
    is the identity's budget on this run. Of each key: it is a stated key that
    sizes that stream's draws — and nothing else is said of it."""
    m, render = line.m, line.render
    zero = _zero_row_of(line, "dead_draw")
    stream = zero["channel_id"]
    block = render.block
    assert stream not in block["live_channel_ids"]
    assert _whole(m["n"]) == zero["measured_paths"] == block["paths"]
    # the printed threshold is the field at three significant figures, taken
    # upward: the smallest such figure not below it, so no move under the
    # field is above the printed figure
    printed = decimal.Decimal(m["threshold"])
    exact = decimal.Decimal(zero["move_threshold"])
    assert len(printed.normalize().as_tuple().digits) <= 3, m["threshold"]
    assert printed >= exact
    assert printed - decimal.Decimal(1).scaleb(exact.adjusted() - 2) < exact
    expected_label = (dc.INCOME_STREAM_LABEL if stream == dc.INCOME_STREAM_ID
                      else dc.channel(stream).label)
    assert m["label"] == expected_label
    if not render.engine:
        return
    assert zero["move_threshold"] == _threshold(render)
    drawn, moves = _instruments(render, zero["measured_paths"])
    assert stream in drawn
    assert moves[stream] <= zero["move_threshold"], (stream, moves[stream])
    assert decimal.Decimal(moves[stream]) <= decimal.Decimal(m["threshold"])
    sizing = (("income.pay_drop_events",) if stream == dc.INCOME_STREAM_ID
              else dc.channel(stream).sizing_keys)
    for key in zero["keys"]:
        assert (_echo_class(render.doc, key) is not None
                or _defaulted(render.doc, key) is not None), key
        pulled = stream == 0 and key.endswith(("_vol", ".events"))
        assert key in sizing or pulled, key


def _exact_head(line):
    assert line.render.block["reversal"]["exact"]


def _estimated_head(line):
    assert line.render.block["reversal"]["estimated"]


def _no_distance(line):
    """A `refused` row's line, or the line of a register with no row."""
    reversal = line.render.block["reversal"]
    got = (line.m["code"], line.m["reason"])
    if reversal["refused"]:
        assert got in [(row["code"], row["reason"]) for row in reversal["refused"]]
        assert _REVERSAL_REFUSAL_REASON[got[0]].fullmatch(got[1])
        return
    assert reversal["exact"] == [] and reversal["estimated"] == []
    assert got == (reversal["no_distance_code"], reversal["no_distance_reason"])
    assert _NO_DISTANCE_REASON[got[0]].fullmatch(got[1])


def on_its_side(figure, value, row, render=None, axis=None):
    """A figure printed on a crossing's axis reads on its side of every
    printed crossing (§0.1 item 60): at or below the crossing's figure when it
    lies at or below the crossing's `value`, equal to it inside the bracket,
    above it at or above `upper_end`. With `render`, it is the key's one
    stated figure, and where it prints off that side it reads there what the
    crossing's field says in this run (§0.1 item 65). With `axis`, the config
    path of another figure, one inside a bracket prints above the crossing's
    figure where `--sweep` at it reads that crossing's `becomes`."""
    shown = decimal.Decimal(figure.rstrip("%"))
    for boundary in (b for b in row["boundaries"] if "formatted" in b):
        lower, upper = boundary["value"], boundary["upper_end"]
        crossing = decimal.Decimal(boundary["formatted"].rstrip("%"))
        if value <= lower:
            held = shown <= crossing
        elif value >= upper:
            held = shown > crossing
        else:
            held = shown == crossing
            if not held and axis is not None and shown > crossing:
                (there,) = _sweep_states(axis, row["key"], [value],
                                         futures="curve_paths" in boundary)
                held = there[boundary["verdict_field"]] == boundary["becomes"]
        if not held and render is not None:
            reads = boundary["was"] if shown <= crossing else boundary["becomes"]
            held = reads == _run_says(render, boundary["verdict_field"])
        assert held, (figure, value, boundary)


def _stated_figures(line, row):
    """The figures the config states for the row's key, and the figures the
    row prints for them."""
    option, leaf = row["key"].split(".", 1)
    stated = line.render.raw[option][leaf]
    values = stated if isinstance(stated, list) else [stated]
    figures = row["stated_formatted"].split(", ")
    assert len(figures) == len(values)
    return [float(v) for v in values], figures


def _row_head(line):
    m, row = line.m, line.reversal_row
    assert (m["key"], m["stated"], m["tag"]) == (row["key"], row["stated_formatted"],
                                                 row["stated_tag"])
    if line.render.engine:
        # whose figure it is: the read-back's own class for the same key, and
        # its own tag, character for character (§0.1 item 53)
        assert _echo_class(line.render.doc, row["key"]) == row["stated_source"]
        assert row["stated_tag"] == _read_back_tag(line.render.doc, row["key"])
        one = stated_path(line.render.raw, row["key"]) is None
        for value, figure in zip(*_stated_figures(line, row)):
            # each figure is the stated value at some number of decimals of a
            # percent, within one of its steps, and reads on its side
            places = len(figure.rstrip("%").split(".")[1])
            assert abs(decimal.Decimal(figure.rstrip("%"))
                       - decimal.Decimal(value) * 100) < decimal.Decimal(1).scaleb(-places)
            on_its_side(figure, value, row, line.render if one else None,
                        None if one else line.render.path)
        if one:
            reads_what_this_run_says(line.render, row)


def reads_what_this_run_says(render, row):
    """A figure the config states as the key's one figure reads, beside
    each field's printed crossings, what that field says in this run: the
    `was` of the nearest crossing printed at or above it, and the `becomes`
    of the nearest printed below it (§0.1 item 60)."""
    shown = decimal.Decimal(row["stated_formatted"].split(", ")[0].rstrip("%"))

    def at(boundary):
        return decimal.Decimal(boundary["formatted"].rstrip("%")), boundary["value"]

    for field in dict.fromkeys(b["verdict_field"] for b in row["boundaries"]):
        own = [b for b in row["boundaries"] if b["verdict_field"] == field]
        up = [b for b in own if shown <= at(b)[0]]
        down = [b for b in own if shown > at(b)[0]]
        says = _run_says(render, field)
        if up:
            assert min(up, key=at)["was"] == says, (field, row["stated_formatted"], up)
        if down:
            assert max(down, key=at)["becomes"] == says, (field, row["stated_formatted"], down)


def _bracket(line):
    m, row = line.m, line.reversal_row
    assert m["lo"] == dt._rate(row["bracket_low"]) and m["hi"] == dt._rate(row["bracket_high"])
    assert m["src"] == row["bracket_source"]
    if line.render.engine:
        assert (row["bracket_low"], row["bracket_high"]) == be.reversal_bracket(row["key"])
        # §0.1 item 43: a range the engine sets carries the budget ceiling's label
        assert row["bracket_source"] == "set in the engine" == be.BRACKET_SOURCE


def _solved(row):
    return [b for b in row["boundaries"] if b["verdict_field"] in ("best", "runner_up")
            and "curve_paths" not in b and "value_ci" not in b]


def _boundary(line, fmt):
    """The row's boundary the line prints: its field and words, and its
    figure as `fmt` reads it off the boundary."""
    m, row = line.m, line.reversal_row
    field = next(f for f, label in FIELD_WORDS.items() if label == m["field"])
    found = [b for b in row["boundaries"] if b["verdict_field"] == field
             and fmt(b) == m["value"].split(" ")[0] and b["was"] == m["was"]
             and b["becomes"] == m["becomes"]]
    assert len(found) == 1, (m.group(0), row["boundaries"])
    boundary = found[0]
    assert m["further"] == boundary["further_changes"]
    return boundary


def _printed(boundary):
    return boundary["formatted"]


def was_at_printed_becomes_above(path, key, boundary, printed, futures):
    """"as it rises past X": at the PRINTED X and at the bracket's lower end
    the field says `was`, and at its upper end it says `becomes` — read on
    `--sweep`, with the run's own futures for a sampled crossing (§0.1 items
    42, 54 and 60). The upper end is just above the unrounded value: a
    solved bracket's two ends have no float between them, and a sampled
    one's are less than 1e-12 apart."""
    at = float(decimal.Decimal(printed.rstrip("%")).scaleb(-2))
    values = [at, boundary["value"], boundary["upper_end"]]
    if boundary["verdict_field"] in ("best", "runner_up"):
        assert boundary["upper_end"] in (boundary["value"],
                                         math.nextafter(boundary["value"], 1.0))
    else:
        assert 0.0 < boundary["upper_end"] - boundary["value"] < 1e-12
    distinct = list(dict.fromkeys(values))
    states = dict(zip(distinct, _sweep_states(path, key, distinct, futures=futures)))
    field = boundary["verdict_field"]
    assert states[at][field] == boundary["was"], (printed, states[at])
    assert states[boundary["value"]][field] == boundary["was"], boundary
    assert states[boundary["upper_end"]][field] == boundary["becomes"], boundary


def _cross_solved(line):
    boundary = _boundary(line, _printed)
    # the prefix names the kind: a solved line carries a solved boundary
    assert boundary in _solved(line.reversal_row)
    if line.render.engine:
        was_at_printed_becomes_above(line.render.path, line.reversal_row["key"], boundary,
                                     line.m["value"], futures=False)


def _cross_sampled(line):
    boundary = _boundary(line, _printed)
    # the prefix names the kind: a sampled line carries a sampled boundary
    assert "curve_paths" in boundary
    assert _whole(line.m["paths"]) == boundary["curve_paths"]
    assert int(line.m["seed"]) == boundary["seed"]
    if line.render.engine:
        # the sample it was bisected on is this run's own
        assert boundary["seed"] == line.render.spec.simulation.random_seed
        assert boundary["curve_paths"] == line.render.spec.simulation.num_sims
        was_at_printed_becomes_above(line.render.path, line.reversal_row["key"], boundary,
                                     line.m["value"], futures=True)


def _cross_estimated(line):
    boundary = _boundary(line, lambda b: dt._rate(b["value"]))
    assert line.m["lo"] == dt._rate(boundary["value_ci"]["low"])
    assert line.m["hi"] == dt._rate(boundary["value_ci"]["high"])
    assert _whole(line.m["n"]) == boundary["resimulation_paths"]


def _path_note(line):
    """How the axis was built: the stated path, as the row's own
    `stated_formatted` prints it, replaced by one rate at every renewal —
    which is what the register's crossings price, since each is solved or
    bisected on `sweep.load_at`, one leaf set to one figure."""
    row = line.reversal_row
    assert line.m["note"] == row["path_note"]
    # the path's figures are the row's own ordered ones (§0.1 item 60)
    assert line.m["stated"] == row["stated_formatted"]
    if line.render.engine:
        option, leaf = row["key"].split(".", 1)
        stated = line.render.raw[option][leaf]
        # a path of more than one rate, which one rate at every renewal is not
        assert isinstance(stated, list) and len(set(stated)) > 1
        flat = be.load_at(line.render.raw, row["key"], 0.05)
        ladder = getattr(flat, option).mortgage_renewal_rates
        assert len(set(ladder)) == 1


def edge_codes_in_the_contract():
    """The codes the contract says refuse one boundary of a field, read off
    its own sentence, never off `decomposition.EDGE_REFUSAL_CODES`."""
    text = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    m = re.search(r"while another of that field's may be, the codes (?P<codes>.+?) "
                  r"\(`decomposition\.EDGE_REFUSAL_CODES`\)", text)
    assert m, "the contract's edge-code sentence"
    return set(re.findall(r"`(\w+)`", m["codes"]))


def _refused_boundary(line):
    m, row = line.m, line.reversal_row
    assert _BOUNDARY_REASON[m["code"]].fullmatch(m["reason"]), m.group(0)
    named = [r for r in row["refused_boundaries"]
             if (r["code"], r["reason"]) == (m["code"], m["reason"])]
    labels = [FIELD_WORDS[r["verdict_field"]] for r in named]
    expected = labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} or {labels[-1]}"
    assert m["fields"] == expected
    # the head is the contract's: "a boundary not printed" for a code that
    # refuses one boundary of a field, "no boundary printed" otherwise
    assert (m["head"] == "a boundary not printed") == (
        m["code"] in edge_codes_in_the_contract()), m.group(0)


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
        assert ref["label"] == ref["anchor"].rsplit(".", 1)[-1].replace("_", " ")
        if compounding == "effective_annual":
            # on this axis the semi-annual quote is converted by the loader's rule
            assert math.isclose(ref["value"], effective_mortgage_rate(published, "semi_annual"))
            assert ref["note"] == (f"published as {_fmt_value(row['key'], published)} "
                                   f"compounded semi-annually")
        else:
            assert ref["value"] == published and ref["note"] is None
        # on the axis, it reads on its side of every printed crossing
        on_its_side(ref["formatted"], ref["value"], row, axis=line.render.path)


LINE_CLAIMS: Dict[str, Callable[[Line], None]] = {
    "BLANK": lambda line: None,
    "HEADER": _header,
    "REFUSAL": _refusal,
    "MARGIN": _margin,
    "SPREAD_HEAD": lambda line: None,
    "SPREAD_REFUSED": _spread_refused,
    "SPREAD_COLS": _spread_cols,
    "SPREAD_ROW": _spread_row,
    "WIDTHS": _widths,
    "SPREAD_SUMS": _spread_sums,
    "SPREAD_GAPS": _spread_gaps,
    "SPREAD_TOP": _spread_top,
    "LEVEL_HEAD": _level_head,
    "LEVEL_BASE": _level_base,
    "LEVEL_COLS": _level_cols,
    "LEVEL_ROW": _level_row,
    "LEVEL_SUM": _level_sum,
    "LEVEL_TOP": _level_top,
    "ZERO_HEAD": _zero_head,
    "ZERO_STATED": _zero_stated,
    "ZERO_DRAWN": _zero_drawn,
    "EXACT_HEAD": _exact_head,
    "ESTIMATED_HEAD": _estimated_head,
    "NO_DISTANCE": _no_distance,
    "ROW_HEAD": _row_head,
    "BRACKET": _bracket,
    "CROSS_SOLVED": _cross_solved,
    "CROSS_SAMPLED": _cross_sampled,
    "CROSS_ESTIMATED": _cross_estimated,
    "PATH_NOTE": _path_note,
    "REFUSED_BOUNDARY": _refused_boundary,
    "REFERENCES": _references,
}

# Line templates only a hand-built outcome reaches, and why the engine cannot:
# a financing key always passes the exactness gate (`_financing_pv` shifts
# every path by one constant), so no engine row is estimated, and an estimated
# row carries no boundary.
HOUSEHOLD_ONLY = {"CROSS_ESTIMATED", "ESTIMATED_HEAD"}


# ---------------------------------------------------------------------------
# The inventory, closed both ways
# ---------------------------------------------------------------------------

def test_every_template_has_a_claim_check_and_a_kind():
    assert set(LINE_CLAIMS) == set(LINES) == set(KINDS)
    assert set(KINDS.values()) == SIX_KINDS | {"layout"}
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
# The reasons the engine writes: each the ONE measured fact that fired it
# ---------------------------------------------------------------------------

REASONS: Dict[str, "re.Pattern"] = {name: re.compile(pattern) for name, pattern in {
    # whole-block refusals
    "NO_FUTURES": r"^this run has no futures$",
    "TOO_FEW": (r"^(?P<n>[\d,]+) (?P<noun>future was|futures were) asked for, below the "
                r"minimum of (?P<min>\d+)$"),
    "SINGLE_OPTION": r"^this run prices one option$",
    "ONE_CHANNEL": rf"^one channel is live on these (?P<n>[\d,]+) futures: (?P<label>{LABEL})$",
    "NO_SPREAD_UNREACHED": r"^no channel is live on these (?P<n>[\d,]+) futures$",
    "NO_SPREAD_CONSTANT": (r"^the margin is identical on all (?P<n>[\d,]+) futures "
                           r"\((?P<value>-?\$[\d,]+\.\d\d)\)$"),
    "BUDGET": (r"^(?P<n>[\d,]+) futures with (?P<k>\d+) streams drawing on them price up "
               r"to (?P<work>[\d,]+) path evaluations, above the ceiling of "
               r"(?P<ceiling>[\d,]+) \[set in the engine\]; the largest path count within "
               r"it is (?P<largest>[\d,]+)$"),
    "BUDGET_N": (r"^(?P<n>[\d,]+) futures price (?P<work>[\d,]+) path evaluations before "
                 r"any re-draw, above the ceiling of (?P<ceiling>[\d,]+) \[set in the "
                 r"engine\]$"),
    "FREEZE_LEAK": (r"^with every channel frozen, the margins of the [\d,]+ paths differ by "
                    r"up to \$\S+$"),
    "IDENTITY_FAILED": (r"^with every channel frozen, the [\d,]+ paths price a margin of "
                        r"-?\$[\d,]+\.\d\d against the central case's -?\$[\d,]+\.\d\d, "
                        r"\$\S+ apart, above the \$\S+ this check allows$"),
    "INCOME_MOVED": (r"^re-drawing the income stream moved an option's present value on "
                     r"these (?P<n>[\d,]+) futures by up to \$(?P<move>\S+), above "
                     r"\$(?P<allowance>\S+)$"),
    "UNTAGGED_WIDTH": (rf"^(?P<key>[\w.]+), a width on the row of (?P<label>{LABEL}), has "
                       rf"no tag in the read-back$"),
    "DEGENERATE_RESAMPLE": (r"^the margin is identical on all (?P<n>[\d,]+) draws of "
                            r"bootstrap resample (?P<r>[\d,]+) of (?P<of>[\d,]+) "
                            r"\((?P<value>-?\$[\d,]+\.\d\d)\)$"),
    # the spread register's own refusal
    "NO_SIGN_VARIATION": (rf"^(?P<best>{OPTION}) is cheapest in (?:all (?P<n1>[\d,]+) of these "
                          rf"futures|none of these (?P<n2>[\d,]+) futures)$"),
    # a boundary field that prints no crossing
    "UNCHANGED": (rf"^(?P<field>best|runner_up|mc_best|decisive) says '(?P<value>[^']+)' "
                  rf"at every one of (?P<n>\d+) points across (?P<lo>{PCT})–(?P<hi>{PCT})$"),
    "SAYS_SO_NOWHERE": (rf"^(?P<field>best|runner_up|mc_best|decisive) says "
                        rf"'(?P<value>[^']+)' in this run and at none of (?P<n>\d+) points "
                        rf"across (?P<lo>{PCT})–(?P<hi>{PCT})$"),
    "SCAN_MISMATCH": (rf"^(?P<field>best|runner_up) says '(?P<value>[^']+)' in this run and "
                      rf"on (?:every|no) stretch between the solved crossings, read at its "
                      rf"middle, and at the (?P<n>\d+) points across (?P<lo>{PCT})–"
                      rf"(?P<hi>{PCT}) it reads '\w+'(?:, '\w+')*$"),
    "NOT_IDENTIFIED": (r"^across the bracket P\((?P<option>condo|house|rent) cheapest\) moves "
                       r"by \d\.\d{4}, not more than 2 s\.e\. of it at the boundary "
                       r"\(\d\.\d{4}\) on \d+ paths$"),
    "NO_PROBABILITY": r"^no probability is attached to this boundary$",
    "RESIMULATION_DISAGREES": (rf"^the re-simulation at (?P<rate>{PCT}) gives .+, and the "
                               rf"free curve gives .+$"),
    "NOT_PRINTABLE": (r"^the crossing of (?P<field>best|runner_up|mc_best|decisive) from "
                      r"'(?P<was>[^']+)' whose bracket starts at (?P<value>\S+), floored "
                      r"(?:at \d+ to \d+ decimals of a percent: .+|at no precision: its "
                      r"bracket is wider than one step at \d+ decimals of a percent)$"),
    "NOT_ORDERABLE": (r"^(?P<figure>\S+), a figure on this axis (?:at or below the lower end "
                      r"of|inside|at or above the upper end of) its bracket \[\S+, \S+\], prints "
                      r"(?:at or below|equal to|above) \d+\.\d+%(?:, (?:at or below|equal to|"
                      r"above) \d+\.\d+%)* rounded to the nearest at none of 2 to 12 decimals "
                      r"of a percent, nor as the figure of a crossing whose bracket holds it$"),
    "MISREAD": (r"^\S+, the stated figure, lies (?:at or below the lower end of|inside|at or "
                r"above the upper end of) its bracket \[\S+, \S+\] and reads '[^']+' beside "
                r"it, and (?:best|runner_up|mc_best|decisive) says '[^']+' in this run$"),
    "READS_NEITHER": (r"^\S+, a figure on this axis inside its bracket \[\S+, \S+\], reads "
                      r"'[^']+' there, and the crossing changes from '[^']+' to '[^']+'$"),
    "NOT_BRACKETED": (r"^(?P<field>best|runner_up) says '(?P<at>[^']+)' at (?P<value>\S+) and "
                      r"'(?P<up>[^']+)' at (?P<upper>\S+), the two ends of the bracket its "
                      r"crossing from '(?P<was>[^']+)' to '(?P<becomes>[^']+)' converged in$"),
    "GATE_NOT_FINITE": r"^a present value this gate compares is not a finite number: .+$",
    "GATE_MOVES_OTHERS": r"^moving \S+ moves .+, which it does not name$",
    "GATE_NOT_CONSTANT": (r"^moving \S+ shifts (?P<option>\w+) by a different amount on "
                          r"different paths \((?:worst \d\.\d\de[+-]\d\d of its own s\.d\., "
                          r"against 1e-09|(?P=option) is priced the same on every path as "
                          r"stated, and its shift differs across paths|its deviation over its "
                          r"own s\.d\. is not a number)\)$"),
    "WITHOUT_FUTURES": (r"^this run has no futures, and this solver reads "
                        r"(?P<field>mc_best|decisive) only off futures$"),
    # a stated key the reversal register refuses
    "NOT_ADMITTED": (r"^this config states (?P<key>[\w.]+), and (?P<fact>moving it to the far "
                     r"end of its bracket moves no option's present value|the loader refuses "
                     r"it at the far end of its bracket)$"),
    # the empty reversal register
    "NO_DISTANCE": r"^this config states no mortgage_renewal_rates or mortgage_rate$",
    "NO_DISTANCE_NO_MAPPING": r"^this block was handed no config mapping$",
    "NO_DISTANCE_ONE_OPTION": r"^fewer than two options are priced$",
    # the path note: how the axis was built (§0.1 item 41)
    "PATH_NOTE": (r"^each crossing on this key is priced with the stated path "
                  r"\((?P<stated>[^)]+)\) replaced by one rate at every renewal$"),
}.items()}

class _AnyOf:
    """Reason templates that share group names, matched one at a time."""

    def __init__(self, *patterns):
        self.patterns = patterns

    def fullmatch(self, text):
        return next((m for m in (p.fullmatch(text) for p in self.patterns) if m), None)


# Which reason each whole-block refusal code writes.
_REFUSAL_REASON = {
    "no_futures": REASONS["NO_FUTURES"],
    "too_few_futures": REASONS["TOO_FEW"],
    "single_option": REASONS["SINGLE_OPTION"],
    "one_channel": REASONS["ONE_CHANNEL"],
    "no_spread": _AnyOf(REASONS["NO_SPREAD_UNREACHED"], REASONS["NO_SPREAD_CONSTANT"]),
    "budget": _AnyOf(REASONS["BUDGET"], REASONS["BUDGET_N"]),
    "freeze_leak": REASONS["FREEZE_LEAK"],
    "identity_failed": REASONS["IDENTITY_FAILED"],
    "income_moved": REASONS["INCOME_MOVED"],
    "untagged_width": REASONS["UNTAGGED_WIDTH"],
    "degenerate_resample": REASONS["DEGENERATE_RESAMPLE"],
}

# Which reason each code of a refused boundary writes, and each code of an
# empty reversal register (§0.1 item 50: every refusal is a code and one fact).
_BOUNDARY_REASON = {
    "unchanged": REASONS["UNCHANGED"],
    "not_on_axis": REASONS["SAYS_SO_NOWHERE"],
    "scan_mismatch": REASONS["SCAN_MISMATCH"],
    "not_identified": _AnyOf(REASONS["NOT_IDENTIFIED"], REASONS["NO_PROBABILITY"]),
    "unconfirmed": REASONS["RESIMULATION_DISAGREES"],
    "not_printable": REASONS["NOT_PRINTABLE"],
    "not_orderable": _AnyOf(REASONS["NOT_ORDERABLE"], REASONS["MISREAD"],
                            REASONS["READS_NEITHER"]),
    "not_bracketed": REASONS["NOT_BRACKETED"],
    "not_exact": _AnyOf(REASONS["GATE_NOT_FINITE"], REASONS["GATE_MOVES_OTHERS"],
                        REASONS["GATE_NOT_CONSTANT"]),
    "no_futures": REASONS["WITHOUT_FUTURES"],
}
_NO_DISTANCE_REASON = {
    "no_candidate": REASONS["NO_DISTANCE"],
    "no_mapping": REASONS["NO_DISTANCE_NO_MAPPING"],
    "single_option": REASONS["NO_DISTANCE_ONE_OPTION"],
}
_REVERSAL_REFUSAL_REASON = {
    "not_admitted": REASONS["NOT_ADMITTED"],
}


def test_every_code_names_one_set_of_reasons():
    """The code maps are whole: every code the types allow has its reason
    templates, and no reason template is written under two codes.
    *Kills it:* a code with no template, or one template filed twice."""
    assert set(_REFUSAL_REASON) == set(dc.REFUSAL_CODES)
    assert set(_BOUNDARY_REASON) == set(dc.BOUNDARY_REFUSAL_CODES)
    assert set(_NO_DISTANCE_REASON) == set(dc.NO_DISTANCE_CODES)
    assert set(_REVERSAL_REFUSAL_REASON) == set(dc.REVERSAL_REFUSAL_CODES)
    filed = []
    for mapping in (_REFUSAL_REASON, _BOUNDARY_REASON, _NO_DISTANCE_REASON,
                    _REVERSAL_REFUSAL_REASON):
        for got in mapping.values():
            filed.extend(got.patterns if isinstance(got, _AnyOf) else (got,))
    names = [next(n for n, p in REASONS.items() if p is pattern) for pattern in filed]
    assert len(names) == len(set(names))
    assert set(REASONS) - set(names) == {"NO_SIGN_VARIATION", "PATH_NOTE"}


def _engine_reasons(render):
    """Every reason string the engine wrote into this run's JSON, with where."""
    block = render.block
    if "refusal" in block:
        return [("refusal", block["refusal"]["reason"], block["refusal"])]
    out = []
    spread = block["spread"]
    if "refusal" in spread:
        out.append(("spread", spread["refusal"]["reason"], None))
    reversal = block["reversal"]
    for kind in ("exact", "estimated"):
        for row in reversal[kind]:
            for refused in row["refused_boundaries"]:
                out.append(("refused", refused["reason"], (row, refused)))
            if row["path_note"] is not None:
                out.append(("path_note", row["path_note"], row))
    for row in reversal["refused"]:
        out.append(("refused_key", row["reason"], row))
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
    "INCOME_MOVED": "tests/test_decomposition_contract_doc.py::test_income_moved",
    "UNTAGGED_WIDTH": "tests/test_decomposition_contract_doc.py::test_untagged_width",
    "NOT_IDENTIFIED": "tests/test_reversal_register.py::TestTheConfirmingResimulation::"
                      "test_a_futures_boundary_inside_monte_carlo_noise_is_not_reported",
    "RESIMULATION_DISAGREES": "tests/test_reversal_register.py::TestTheConfirmingResimulation::"
                              "test_the_rate_a_disagreeing_re_simulation_names_prints_on_its_side",
    "SCAN_MISMATCH": "tests/test_reversal_register.py::TestTheStatePastAnEdgeIsReadAtTheEdge::"
                     "test_a_field_no_crossing_moves_is_read_at_the_nine_points",
    "GATE_NOT_FINITE": "tests/test_reversal_register.py::TestTheExactnessGate::"
                       "test_a_non_finite_present_value_in_the_named_option_refuses_by_name",
    "GATE_MOVES_OTHERS": "tests/test_reversal_register.py::TestTheExactnessGate::"
                         "test_a_key_that_moves_the_draw_stream_is_refused_by_clause_a",
    "GATE_NOT_CONSTANT": "tests/test_reversal_register.py::TestTheExactnessGate::"
                         "test_a_key_whose_shift_is_not_constant_is_refused",
    "WITHOUT_FUTURES": "tests/test_reversal_register.py::TestRefusals::"
                       "test_without_futures_the_register_still_carries_its_solved_half",
    "NO_PROBABILITY": "tests/test_reversal_register.py::"
                      "test_a_boundary_with_no_probability_is_not_identified",
    "MISREAD": "tests/test_reversal_register.py::"
               "test_the_stated_figure_prints_on_the_side_this_run_reads_it",
    "READS_NEITHER": "tests/test_reversal_register.py::"
                     "test_another_figure_inside_a_bracket_prints_on_the_side_it_reads",
    "NO_DISTANCE_NO_MAPPING": "tests/test_decomposition_sentences.py::"
                              "test_a_block_handed_no_config_mapping_searched_no_key",
    "NO_DISTANCE_ONE_OPTION": "tests/test_reversal_register.py::"
                              "test_a_register_on_one_option_has_no_verdict_to_reverse",
}


def _r_no_futures(render, m, node):
    # "this run has no futures": --no-monte-carlo, or every uncertainty input off
    assert "--no-monte-carlo" in render.extra or single_path_run(render.spec)
    assert render.doc["monte_carlo"] is None or single_path_run(render.spec)


def _r_too_few(render, m, node):
    n = _whole(m["n"])
    assert n == int(render.extra[0])
    assert int(m["min"]) == dr.MIN_INTERVALLED_FUTURES and n < dr.MIN_INTERVALLED_FUTURES
    assert (m["noun"] == "future was") == (n == 1)


def _r_single_option(render, m, node):
    assert len(_priced(render.raw)) == 1


def _r_one_channel(render, m, node):
    """"one channel is live on these N futures: X" — on the held-generator
    instruments, at that count of futures, X is the one drawing channel whose
    re-seeding moves a present value past the identity's budget."""
    n = _whole(m["n"])
    assert n == _requested(render)
    only = _live_by_instrument(render, n)
    assert len(only) == 1 and dc.channel(only[0]).label == m["label"]
    assert node["channel_id"] == only[0] and node["label"] == m["label"]


def _r_no_spread_unreached(render, m, node):
    """"no channel is live on these N futures", on a run whose margin is not
    one figure on every future — so something drew."""
    n = _whole(m["n"])
    assert n == _requested(render)
    assert _live_by_instrument(render, n) == ()
    assert _instruments(render, n)[0]
    margin = dr.margin_per_path(dr._run(dr._spec_at(render.spec, n), dr.MATRIX_A),
                                render.verdict["best"])
    assert np.ptp(margin) > 0.0


def _r_no_spread_constant(render, m, node):
    spec = render.spec
    n = _whole(m["n"])
    assert n == spec.simulation.num_sims
    margin = dr.margin_per_path(dr._run(dr._spec_at(spec, n), dr.MATRIX_A),
                                render.verdict["best"])
    assert np.ptp(margin) == 0.0
    assert m["value"] == _cents(float(margin[0]))


def _cents(value):
    """A dollar figure at two decimals, its sign before the dollar sign, and
    no sign on one that prints as zero."""
    text = f"{abs(value):,.2f}"
    return f"{'-' if value < 0 and float(text.replace(',', '')) else ''}${text}"


def _r_budget(render, m, node):
    """The count of drawing streams is the held-generator instrument's; the
    figures are the cost model's; the N it names is one the gate admits."""
    n = _whole(m["n"])
    assert n == int(render.extra[0])
    if m.re is REASONS["BUDGET_N"]:
        assert _whole(m["work"]) == n
        assert _whole(m["ceiling"]) == dr.EVALUATION_CEILING < n
        return
    k = len(oracle_drawn(render.spec))
    assert int(m["k"]) == k
    mm = min(n, dc.LEVEL_PATHS)
    assert _whole(m["work"]) == n * (k + 2) + mm * (k + 1) == dr.planned_evaluations(n, k, mm)
    assert _whole(m["ceiling"]) == dr.EVALUATION_CEILING < _whole(m["work"])
    largest = _whole(m["largest"])
    assert (dr.planned_evaluations(largest, k, dr._level_paths(largest))
            <= dr.EVALUATION_CEILING
            < dr.planned_evaluations(largest + 1, k, dr._level_paths(largest + 1)))
    # the N it names is one the gate admits, and one more is one it refuses
    assert dr._budget_refusal(largest, k) is None
    assert dr._budget_refusal(largest + 1, k).code == "budget"


def _r_degenerate_resample(render, m, node):
    """"the margin is identical on all N draws of bootstrap resample r of R
    (v)": N is the count asked for, and on the resample table the spread
    register's intervals are read off (`bootstrap_path_indices`, the run's own
    seed), resample r is the first whose futures carry one margin, v."""
    spec = render.spec
    n = _whole(m["n"])
    assert n == _requested(render)
    margin = dr.margin_per_path(dr._run(dr._spec_at(spec, n), dr.MATRIX_A),
                                render.verdict["best"])
    assert np.ptp(margin) > 0.0
    table = dm.bootstrap_path_indices(n, dm.DEFAULT_RESAMPLES,
                                      int(spec.simulation.random_seed))
    flat = [i for i, rows in enumerate(table) if np.ptp(margin[rows]) == 0.0]
    assert flat, "no resample holds one figure"
    assert _whole(m["r"]) == flat[0] + 1 and _whole(m["of"]) == dm.DEFAULT_RESAMPLES
    assert m["value"] == _cents(float(margin[table[flat[0]][0]]))


def _r_no_sign_variation(render, m, node):
    block = render.block
    f_a = render.source.f_a()
    share = float(np.mean(f_a > 0.0))
    assert m["best"] == render.verdict["best"]
    if m["n1"] is not None:
        assert share == 1.0 and _whole(m["n1"]) == block["paths"] == f_a.size
    else:
        assert share == 0.0 and _whole(m["n2"]) == block["paths"] == f_a.size


def _run_inputs_of(render):
    from hde.deterministic import compute_deterministic
    from hde.models import compute_verdict
    from hde.monte_carlo import run_monte_carlo
    spec = render.spec
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    return det, mc, verdict


def _scan_states(render, m, node):
    """What the refused field reads at each point of the scan its reason
    names (§0.1 item 47: the scan the refusal rests on, never "throughout").
    N is the solver's own scan: nine points per pair for a field solved on the
    central case, read here by a `--sweep` without futures at those nine
    points; 65 for a field bisected on the futures, read off the same free
    curve the register read."""
    row, refused = node
    field = m["field"]
    assert field == refused["verdict_field"]
    n = int(m["n"])
    lo, hi = row["bracket_low"], row["bracket_high"]
    assert (m["lo"], m["hi"]) == (dt._rate(lo), dt._rate(hi))
    xs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    if field in ("best", "runner_up"):
        assert n == be.CROSSING_SCAN_POINTS == 9
        return [s[field] for s in _sweep_states(render.path, row["key"], xs, futures=False)]
    assert n == be.REVERSAL_SCAN_POINTS == 65
    det, mc, _ = _run_inputs_of(render)
    free = be._free_curve(render.raw, row["key"], be._priced_options(render.raw), det,
                          mc, single_path=False)
    return [be.field_state(free(x)[0], field) for x in xs]


def _run_says(render, field):
    verdict = render.doc["verdict"]
    if field == "decisive":
        return f"decisive for {verdict['best']}" if verdict["decisive"] else "not decisive"
    return verdict[field]


def _r_unchanged(render, m, node):
    """"at every one of N points": each point of the scan reads the one value."""
    states = _scan_states(render, m, node)
    assert set(states) == {m["value"]}, (m["field"], states)


def _r_says_so_nowhere(render, m, node):
    """"in this run and at none of N points": the run's own verdict says it,
    and no point of the scan does."""
    assert _run_says(render, m["field"]) == m["value"]
    states = _scan_states(render, m, node)
    assert m["value"] not in states, (m["field"], states)


_NOT_PRINTABLE = re.compile(
    r"the crossing of (?P<field>\w+) from '(?P<was>[^']+)' whose bracket starts at "
    r"(?P<value>\S+), floored at (?P<start>\d+) to (?P<finest>\d+) decimals of a percent: "
    r"(?P<parts>.+)")


def _r_not_printable(render, m, node):
    """Each floored figure the reason names, one per precision from the
    kind's own to the finest tried, is what it says it was: a figure at which
    `--sweep` reads another state, one below the bracket searched, or one
    below a figure on the axis that lies below the crossing, at twelve
    decimals."""
    row, refused = node
    got = _NOT_PRINTABLE.fullmatch(m.group(0))
    field, value = got["field"], float(got["value"])
    assert field == refused["verdict_field"]
    futures = field not in ("best", "runner_up")
    start, finest = int(got["start"]), int(got["finest"])
    assert start == (2 if futures else 4) and start <= finest <= be.PRINTED_RATE_MAX_PLACES
    (at,) = _sweep_states(render.path, row["key"], [value], futures=futures)
    assert at[field] == got["was"]
    option, leaf = row["key"].split(".", 1)
    stated = render.raw[option][leaf]
    figures = [float(v) for v in (stated if isinstance(stated, list) else [stated])] + [
        r["value"] for r in row["references"]]
    parts = got["parts"].split("; ")
    assert len(parts) == finest - start + 1
    for places, part in zip(range(start, finest + 1), parts):
        text = be.floored_rate(value, places)
        shown = decimal.Decimal(text.rstrip("%"))
        if part == f"{text} is below the bracket searched":
            assert float(shown.scaleb(-2)) < row["bracket_low"]
            continue
        below = re.fullmatch(rf"{re.escape(text)} is below (?P<fig>\S+), a figure on this axis",
                             part)
        if below:
            assert below["fig"] in {f"{f:.12%}" for f in figures if f < value}, part
            assert shown < decimal.Decimal(below["fig"].rstrip("%"))
            continue
        reads = re.fullmatch(rf"{re.escape(text)} reads '(?P<says>[^']+)'", part)
        assert reads, part
        (there,) = _sweep_states(render.path, row["key"], [float(shown.scaleb(-2))],
                                 futures=futures)
        assert there[field] == reads["says"] != got["was"], part


def _r_not_bracketed(render, m, node):
    """A solved crossing's bracket, two adjacent floats, at which `--sweep`
    on the central case reads what the reason says, and not the crossing's
    `was` at the lower end and its `becomes` at the upper one."""
    row, refused = node
    field, value, upper = m["field"], float(m["value"]), float(m["upper"])
    assert field == refused["verdict_field"] and upper == math.nextafter(value, 1.0)
    at, above = _sweep_states(render.path, row["key"], [value, upper], futures=False)
    assert (at[field], above[field]) == (m["at"], m["up"])
    assert (m["at"], m["up"]) != (m["was"], m["becomes"]) and m["was"] != m["becomes"]


def _r_no_distance(render, m, node):
    assert be.reversal_candidates(render.raw) == []


def _r_not_admitted(render, m, node):
    """The row's own key, one the config states, moved to the far end of its
    bracket: no option's present value moves, or the loader refuses it."""
    key = m["key"]
    assert key == node["key"] and key in [k for k, _ in be.reversal_candidates(render.raw)]
    admitted, record = be.reversal_admission(render.raw, key, be.reversal_probe(render.raw, key))
    assert not admitted
    if m["fact"].startswith("moving it"):
        assert record["deltas"] and all(d == 0.0 for d in record["deltas"].values())
    else:
        assert record["why"].startswith("the loader refuses")


def _r_path_note(render, m, node):
    option, leaf = node["key"].split(".", 1)
    stated = render.raw[option][leaf]
    assert isinstance(stated, list) and len(set(stated)) > 1
    assert m["stated"] == node["stated_formatted"]


_NOT_ORDERABLE = re.compile(
    r"(?P<figure>\S+), a figure on this axis (?P<side>at or below the lower end of|inside|at "
    r"or above the upper end of) its bracket \[(?P<lower>\S+), (?P<upper>\S+)\], prints "
    r"(?P<tried>.+) rounded to the nearest at none of 2 to 12 decimals of a percent, nor as "
    r"the figure of a crossing whose bracket holds it")
_TRIED = re.compile(r"(at or below|equal to|above) (\d+\.\d+%)")
_PRINTS = {"at or below": -1, "equal to": 0, "above": 1}


def _r_not_orderable(render, m, node):
    """The figure is one the row prints on its axis; its side of the refused
    crossing's bracket is the one named; the crossings it was tried beside are
    the row's printed ones, in order, then the refused one at its own floored
    figure, each on the side named: the side the figure lies on, or, for the
    key's one stated figure beside a printed crossing, one on which it reads
    what that crossing's field says in this run, or, for another figure inside
    a crossing's bracket, above it where the field reads `becomes` there; and
    no rounding at 2 to 12
    decimals, nor any tried crossing's figure whose bracket holds it, prints
    on those sides of all of them."""
    row, refused = node
    got = _NOT_ORDERABLE.fullmatch(m.group(0))
    figure, lower, upper = float(got["figure"]), float(got["lower"]), float(got["upper"])
    option, leaf = row["key"].split(".", 1)
    stated = render.raw[option][leaf]
    values = [float(v) for v in (stated if isinstance(stated, list) else [stated])]
    assert figure in values + [r["value"] for r in row["references"]], figure
    one = stated_path(render.raw, row["key"]) is None and figure in values
    side = -1 if figure <= lower else (1 if figure >= upper else 0)
    assert got["side"] == {-1: "at or below the lower end of", 0: "inside",
                           1: "at or above the upper end of"}[side]
    tried = _TRIED.findall(got["tried"])
    assert ", ".join(f"{word} {text}" for word, text in tried) == got["tried"]
    printed = [(b["value"], b["upper_end"], b["formatted"], b) for b in row["boundaries"]]
    assert [p[2] for p in printed[:len(tried) - 1]] == [text for _, text in tried[:-1]]
    places = len(tried[-1][1].rstrip("%").split(".")[1])
    assert tried[-1][1] == be.floored_rate(lower, places)
    assert 0.0 < upper - lower < 1e-12 or upper == math.nextafter(lower, 1.0)
    brackets = [p[:3] for p in printed[:len(tried) - 1]] + [(lower, upper, tried[-1][1])]
    sides = [_PRINTS[word] for word, _ in tried]
    for at, ((low, high, _), named) in enumerate(zip(brackets, sides)):
        lies = -1 if figure <= low else (1 if figure >= high else 0)
        if named != lies and not one:
            # another figure inside a bracket, above the crossing's figure
            # where the field reads there what it reads at the upper end
            assert (lies, named) == (0, 1), (figure, low, high, named)
            field = (printed[at][3] if at < len(tried) - 1 else refused)["verdict_field"]
            there, end = _sweep_states(render.path, row["key"], [figure, high],
                                       futures=field not in ("best", "runner_up"))
            assert there[field] == end[field], (figure, field)
        elif named != lies:
            if at < len(tried) - 1:
                boundary = printed[at][3]
                assert boundary["was" if named < 1 else "becomes"] == _run_says(
                    render, boundary["verdict_field"])

    def placed(text):
        shown = decimal.Decimal(text.rstrip("%"))
        for (_, _, crossing), named in zip(brackets, sides):
            at = decimal.Decimal(crossing.rstrip("%"))
            if not {-1: shown <= at, 0: shown == at, 1: shown > at}[named]:
                return False
        return True

    assert not any(placed(f"{figure:.{k}%}") for k in range(2, 13))
    assert not any(placed(crossing) for low, high, crossing in brackets
                   if low <= figure <= high)


REASON_CLAIMS: Dict[str, Callable[..., None]] = {
    "NO_FUTURES": _r_no_futures,
    "TOO_FEW": _r_too_few,
    "SINGLE_OPTION": _r_single_option,
    "ONE_CHANNEL": _r_one_channel,
    "NO_SPREAD_UNREACHED": _r_no_spread_unreached,
    "NO_SPREAD_CONSTANT": _r_no_spread_constant,
    "BUDGET": _r_budget,
    "BUDGET_N": _r_budget,
    "DEGENERATE_RESAMPLE": _r_degenerate_resample,
    "NO_SIGN_VARIATION": _r_no_sign_variation,
    "UNCHANGED": _r_unchanged,
    "SAYS_SO_NOWHERE": _r_says_so_nowhere,
    "NOT_PRINTABLE": _r_not_printable,
    "NOT_ORDERABLE": _r_not_orderable,
    "NOT_BRACKETED": _r_not_bracketed,
    "NOT_ADMITTED": _r_not_admitted,
    "NO_DISTANCE": _r_no_distance,
    "PATH_NOTE": _r_path_note,
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


def test_no_reason_explains_or_routes():
    """A reason is the one measured fact that fired it (§0.1 items 35-37), and
    a path note the one construction fact of its axis (§0.1 item 41): no
    clause saying why it holds, predicting a run the block did not price, or
    naming another command, and no `--sweep` vocabulary with nothing in the
    block to refer to. Every reason and note the engine wrote on every render,
    and every template, is free of the words those clauses were built from.
    *Kills it:* any of the cut clauses — "so ...", "rather than", "which is
    why", a route to `--break-even`, `--sweep` or `--decompose`, "raise", a
    grid or a threshold reported — back in a reason or a note."""
    banned = re.compile(r"\bso\b|\brather than\b|\bwhich is why\b|\bbecause\b|"
                        r"--break-even|--sweep|--decompose|\braise\b|\bcould\b|\bwould\b|"
                        r"\binstead\b|\bgrid\b|\bthreshold reported\b")
    for render in renders():
        if render.engine:
            for where, text, node in _engine_reasons(render):
                assert not banned.search(text), (render.name, text)
    for name, pattern in REASONS.items():
        assert not banned.search(pattern.pattern), name


def test_a_block_handed_no_config_mapping_searched_no_key():
    got = run("fixture")
    det, mc, verdict = got.inputs()
    spec = dr._spec_at(got.spec, 40)
    outcome = dr.decompose(spec, det=det, mc=mc, verdict=verdict, raw=None, paths=40)
    reversal = outcome.reversal
    assert reversal.exact == () and reversal.estimated == ()
    assert reversal.no_distance_code == "no_mapping"
    assert REASONS["NO_DISTANCE_NO_MAPPING"].match(reversal.no_distance_reason)


def test_a_printed_crossing_is_a_rate_the_field_still_says_was():
    """§0.1 item 42's witness. The mortgage example's rate crossing lies at
    6.784887%; printed to the nearest it read 6.7849%, a rate at which
    `--sweep` already says `becomes`. Both kinds print through one floor of
    the bracket's lower end, starting at their own precision, and widen it
    only where the field does not say `was` there (§0.1 items 54 and 60).
    *Kills it:* rounding either kind to the nearest, flooring at a precision
    other than its own, or flooring any point but the lower end."""
    got = run("mortgage")
    (row,) = [r for r in got.block["reversal"]["exact"] if r["key"] == "house.mortgage_rate"]
    solved = [b for b in _solved(row)]
    assert solved
    for boundary in solved:
        printed = boundary["formatted"]
        assert printed == be.floored_rate(boundary["value"], 4)
        assert f"as it rises past {printed}, " in got.text
        nearest = f"{boundary['value'] * 100:.4f}%"
        field = boundary["verdict_field"]
        at, rounded = _sweep_states(got.path, row["key"],
                                    [float(printed.rstrip("%")) / 100.0,
                                     float(nearest.rstrip("%")) / 100.0], futures=False)
        assert at[field] == boundary["was"], (printed, at)
        if nearest != printed:
            assert rounded[field] == boundary["becomes"], (nearest, rounded)
    # the witness is live: this crossing is one the nearest figure mis-states
    assert any(f"{b['value'] * 100:.4f}%" != be.floored_rate(b["value"], 4) for b in solved)
    # the floor itself, at any precision: never above the value, and within
    # one step of it
    for value in (0.06784887, 0.0499999999, 0.05, 0.123456789):
        for places in (2, 3, 4, 7):
            printed = be.floored_rate(value, places)
            assert len(printed.split(".")[1]) == places + 1
            assert decimal.Decimal(printed.rstrip("%")) <= decimal.Decimal(value) * 100
            assert decimal.Decimal(printed.rstrip("%")) + decimal.Decimal(1).scaleb(-places) \
                > decimal.Decimal(value) * 100


# ---------------------------------------------------------------------------
# The guards the block's words turn on, pinned in BOTH directions on a run:
# one future (or a few thousandths) on each side of the line
# ---------------------------------------------------------------------------

def test_one_future_on_the_other_side_prints_the_table():
    """`_one_side_of_the_line` refuses at P(f > 0) of exactly 0 or 1. On
    `near_none` one future of 2,000 names rent, the central case's winner, and
    on `near_all` one future of 2,000 does not name the house: both print the
    spread table. `mortgage` and `all_other` sit exactly on the line and refuse.
    *Kills it:* widening the guard by any tolerance (the one-future runs
    refuse), or narrowing it to one side (a refusing run prints)."""
    for name, count in (("near_none", 1), ("near_all", 1999)):
        got = run(name)
        f_a = got.f_a()
        assert int(np.sum(f_a > 0.0)) == count and f_a.size == 2000, name
        assert "rows" in got.block["spread"], name
        assert "not split (no_sign_variation)" not in got.text
    for name, side in (("mortgage", 1.0), ("all_other", 0.0)):
        got = run(name)
        assert float(np.mean(got.f_a() > 0.0)) == side
        assert got.block["spread"]["refusal"]["code"] == "no_sign_variation"


def test_an_interaction_gap_a_few_thousandths_above_zero_resolves():
    """`interaction_is_resolved` is `low > 0`. On `advanced_4000` the economy's
    gap interval starts a few thousandths above zero, and the gap line names
    it with its figure; on `fixture` none resolves and the line says so.
    *Kills it:* any positive threshold above that low end (the economy moves
    behind "not resolved"), or `>= 0` / `low > -x` (a row whose interval
    reaches zero is named)."""
    got = run("advanced_4000")
    spread = got.block["spread"]
    economy = next(r for r in spread["rows"] if r["channel_id"] == 0)
    assert 0.0 < economy["interaction_gap_ci"]["low"] < 0.01
    assert 0 in spread["interaction_channel_ids"]
    gaps = next(line for line in got.text.splitlines()
                if line.startswith("  with interaction minus alone, before rounding: "))
    assert (f"the economy {dt._share(economy['interaction_gap'])} "
            f"{dt._interval(_ci(economy['interaction_gap_ci']))}") in gaps.split("; ")[0:]
    assert "the economy not resolved" not in gaps
    for row in spread["rows"]:
        assert (row["channel_id"] in spread["interaction_channel_ids"]) == (
            row["interaction_gap_ci"]["low"] > 0.0)
    assert any(r["interaction_gap_ci"]["low"] <= 0.0 < r["interaction_gap_ci"]["high"]
               for r in spread["rows"])


# The third-far config with the condo's fee drawing: 2,000 futures on which
# the tenancy's interaction gap has a bootstrap interval whose low end is
# exactly 0.0, the one value that tells `low > 0` from `low >= 0`.
THIRD_FAR_FEE = copy.deepcopy(THIRD_FAR)
THIRD_FAR_FEE["simulation"].update({"num_sims": 2000, "condo_fee_vol": 0.3})


def test_an_interaction_gap_whose_interval_starts_at_zero_does_not_resolve():
    """An interval that reaches zero cannot tell interaction from none, so a
    gap whose low end is exactly 0.0 prints behind "not resolved:". The
    witness is a run, not a constructed figure: the tenancy's gap on
    `THIRD_FAR_FEE`.
    *Kills it:* `low >= 0.0` in `interaction_is_resolved`, which names the
    tenancy's gap bare on this run."""
    assert dm.interaction_is_resolved(0.0) is False
    assert dm.interaction_is_resolved(-0.0) is False
    assert dm.interaction_is_resolved(math.ulp(0.0)) is True
    assert dm.interaction_is_resolved(-math.ulp(0.0)) is False
    got = _cli_render("third_far_fee", THIRD_FAR_FEE)
    spread = got.block["spread"]
    tenancy = next(r for r in spread["rows"]
                   if dc.channel(r["channel_id"]).label == "your tenancy")
    assert tenancy["interaction_gap_ci"]["low"] == 0.0
    assert tenancy["channel_id"] not in spread["interaction_channel_ids"]
    gaps = next(line for line in got.text.splitlines()
                if line.startswith("  with interaction minus alone, before rounding: "))
    assert (f"your tenancy not resolved: {dt._share(tenancy['interaction_gap'])} "
            f"{dt._interval(_ci(tenancy['interaction_gap_ci']))}") in gaps, gaps


def test_the_margin_line_s_mean_is_over_every_future_of_the_block():
    """"over this block's own N futures, mean …": the mean is re-derived here
    from the margin re-priced on all N futures, on a run whose N is above the
    level register's 2,000, where the first 2,000 have a different mean.
    *Kills it:* the mean taken over the level register's futures, or over any
    prefix of the block's."""
    got = run("advanced_4000")
    f_a = got.f_a()
    assert f_a.shape == (got.paths(),) and got.paths() > 2000
    mean = float(np.mean(f_a))
    assert got.block["mean_margin"] == mean
    assert dt._money(mean) != dt._money(float(np.mean(f_a[:2000])))
    assert f"over this block's own {got.paths():,} futures, mean {dt._money(mean)} " in got.text


def test_the_level_top_row_is_named_by_its_size_on_a_shipped_example():
    """advanced_config: the house's costs shift the margin by more, in size,
    than the economy's positive shift. The top row is the house's costs — by
    SIZE. Signed, the economy's positive shift would be "the largest".
    *Kills it:* dropping `abs` from `decomposition_run._level_point`."""
    got = run("advanced")
    level = got.block["level"]
    top = level["unresolved_top_channel_id"]
    assert top == 4, level
    row = next(r for r in level["rows"] if r["channel_id"] == 4)
    assert _shift(row) < 0 and any(_shift(r) > 0 for r in level["rows"])
    # an unresolved top row prints no "largest" line (§0.1 item 35)
    assert "largest shift in size" not in got.text


def test_a_top_line_prints_exactly_where_the_top_row_leads():
    """The absence the `SPREAD_TOP` and `LEVEL_TOP` claims cannot see: on
    every render, each register prints its "largest" line when its top row
    resolved and leads, and prints none when the top row did not resolve.
    *Kills it:* a top line for an unresolved top (a ranking of figures the
    block calls not resolved), or none for a resolved leader."""
    seen = set()
    for render in renders():
        block = render.block
        if "refusal" in block:
            continue
        templates = [line.template for line in _lines(render)]
        for register, template in (("spread", "SPREAD_TOP"), ("level", "LEVEL_TOP")):
            reg = block[register]
            if "rows" not in reg:
                assert template not in templates, render.name
                continue
            leads = reg["leading_channel_id"] is not None
            assert templates.count(template) == int(leads), (render.name, register)
            seen.add((register, leads))
    assert seen == {("spread", True), ("spread", False), ("level", True), ("level", False)}
