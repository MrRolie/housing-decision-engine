"""Every sentence the `--decompose` block prints, and a test of what it claims.

The block is built from sentence TEMPLATES: the lines `hde.decomposition_text`
writes, and the reason strings the assembler (`hde.decomposition_run`) writes
for it. Every template is one of the six KINDS of spec §0.1 items 35 and 41
(`SIX_KINDS`), and `KINDS` records which, so a template that is none of them
has nowhere to go. Since item 56 the block prints four of them — a heading, a
figure row, a refusal (its code and the one measured fact that fired it) or a
structural-zero row.

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
of a threshold, which row is on top, what a draw reaches — against the
JSON's own fields, the read-back's source echo, or the instruments in
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
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pytest
import yaml

import hde.decomposition as dc
import hde.decomposition_math as dm
import hde.decomposition_run as dr
import hde.decomposition_text as dt
from hde.config import load_config_dict, single_path_run
from hde.decomposition_math import LEVEL_RESOLUTION_SIGMAS
from hde.serialization import decomposition_to_dict

from tests import decomposition_households as hh
from tests.decomposition_oracles import oracle_drawn, oracle_moves
from tests.decomposition_runs import (
    _SCRATCH, CONDO_ONLY, CRASH_EVERY_YEAR, FIXTURE, INCOME, INCOME_ONLY, MONTREAL,
    MORTGAGE, NO_REACH, RARE2, THIRD_FAR, THIRD_FAR_ONE, _block_text, _cli, _load,
    _strict, corpus, run)
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

LABEL = "(?:" + "|".join(re.escape(c.label) for c in dc.CHANNELS) + ")"
OPTION = r"(?:condo|house|rent)"
SHARE = r"-?\d+\.\d+"
CI = rf"\[{SHARE}, {SHARE}\]"
MONEY = r"-?\$[\d,]+"
SHIFT = r"(?:[+-]\$[\d,]+|\$0)"
PROB = r"\d+\.\d+"
PCT = r"\d+\.\d+%"
N = r"[\d,]+"

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
                  rf"\(± (?P<se>\$[\d,]+)\) +(?P<p>{PROB})$"),
    "LEVEL_SUM": rf"^  the (?P<n>\d+) shifts above, summed: (?P<sum>{MONEY})$",
    "LEVEL_TOP": rf"^  largest shift in size: (?P<label>{LABEL})$",
    "ZERO_DRAWN": (rf"^  (?P<label>[^—:]+?): drawn on these (?P<n>{N}) futures, and "
                   rf"re-drawing it moved no option's present value by more than "
                   rf"\$(?P<threshold>[\d.e+-]+)(?:; sized by (?P<keys>[\w.]+(?:, "
                   rf"[\w.]+)*))?$"),
}.items()}

# The six kinds a line may be (spec §0.1 items 35 and 41). A line that is none
# of them is interpretation, and interpretation is the assistant's. The
# crossing and the path note left the block with the reversal register (§0.1
# item 56): no template below is of either kind.
SIX_KINDS = {"header", "figure row", "crossing", "path note", "refusal", "structural zero"}

# What each template IS.
KINDS = {
    "BLANK": "layout",
    "HEADER": "header", "SPREAD_HEAD": "header", "SPREAD_COLS": "header",
    "LEVEL_HEAD": "header", "LEVEL_COLS": "header",
    "MARGIN": "figure row", "SPREAD_ROW": "figure row", "WIDTHS": "figure row",
    "SPREAD_SUMS": "figure row", "SPREAD_GAPS": "figure row", "SPREAD_TOP": "figure row",
    "LEVEL_BASE": "figure row", "LEVEL_ROW": "figure row", "LEVEL_SUM": "figure row",
    "LEVEL_TOP": "figure row",
    "REFUSAL": "refusal", "SPREAD_REFUSED": "refusal",
    "ZERO_DRAWN": "structural zero",
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


def _hits(text):
    return [(name, pattern.match(text)) for name, pattern in LINES.items()
            if pattern.match(text)]


def _by_label(rows, label):
    return next(r for r in rows if r["label"] == label)


@functools.lru_cache(maxsize=None)
def _lines(render: Render) -> Tuple[Line, ...]:
    out: List[Line] = []
    section, spread_row = "head", None
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
        out.append(Line(render, name, m, section, spread_row))
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
    for character. None when the read-back carries the key nowhere."""
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


def _level_row(line):
    m = line.m
    row = _by_label(line.render.block["level"]["rows"], m["label"])
    assert (m["unresolved"] is None) == row["resolved"]
    # the resolution rule, both ways
    assert row["resolved"] == (abs(_shift(row)) > LEVEL_RESOLUTION_SIGMAS * row["se"])
    assert m["delta"] == dt._shift(_shift(row))
    assert m["se"] == f"${row['se']:,.0f}"
    assert m["p"] == dt._prob(row["prob_best_frozen"])


def _level_sum(line):
    level = line.render.block["level"]
    assert int(line.m["n"]) == len(level["rows"])
    printed = [_whole(dt._shift(_shift(r))) for r in level["rows"]]
    assert _whole(line.m["sum"]) == sum(printed)


def _level_top(line):
    level = line.render.block["level"]
    _top(line, level["rows"], level["leading_channel_id"],
         level["unresolved_top_channel_id"], lambda r: abs(_shift(r)))


def _zero_row_of(line):
    """The spread register's row the line prints: a row measured on the
    block's futures is the spread register's, and prints in its section
    (§0.1 item 48)."""
    m, render = line.m, line.render
    assert line.section == "spread", (m.group(0), line.section)
    held = render.block["spread"]["structural_zeros"]
    zeros = [z for z in held if z["kind"] == "dead_draw" and z["label"] == m["label"]
             and ", ".join(z["keys"]) == (m["keys"] or "")]
    assert len(zeros) == 1, (m.group(0), held)
    return zeros[0]


def _zero_drawn(line):
    """Each claim at its own grain (§0.1 items 39 and 40). Of the STREAM: it
    drew on these N futures (its held generator advances), and re-drawing it
    moved no option's present value by more than the printed threshold (its
    re-seeding, on held generators and as many futures). Of the threshold: it
    is the identity's budget on this run. Of each key: it is a stated key that
    sizes that stream's draws — and nothing else is said of it."""
    m, render = line.m, line.render
    zero = _zero_row_of(line)
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
    "ZERO_DRAWN": _zero_drawn,
}

# Line templates only a hand-built outcome reaches: none.
HOUSEHOLD_ONLY: set = set()


# ---------------------------------------------------------------------------
# The inventory, closed both ways
# ---------------------------------------------------------------------------

def test_every_template_has_a_claim_check_and_a_kind():
    assert set(LINE_CLAIMS) == set(LINES) == set(KINDS)
    assert set(KINDS.values()) <= SIX_KINDS | {"layout"}
    assert set(KINDS.values()) == {"layout", "header", "figure row", "refusal",
                                   "structural zero"}
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
    "TOO_FEW": r"^(?P<n>[\d,]+) futures were asked for, below the minimum of (?P<min>\d+)$",
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
    "DEGENERATE_RESAMPLE": (r"^the margin is identical on all (?P<n>[\d,]+) futures of "
                            r"bootstrap resample (?P<r>[\d,]+) of (?P<of>[\d,]+) "
                            r"\((?P<value>-?\$[\d,]+\.\d\d)\)$"),
    # the spread register's own refusal
    "NO_SIGN_VARIATION": (rf"^(?P<best>{OPTION}) is cheapest in (?:all (?P<n1>[\d,]+) of these "
                          rf"futures|none of these (?P<n2>[\d,]+) futures)$"),
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



def test_every_code_names_one_set_of_reasons():
    """The code map is whole: every whole-block code the types allow has its
    reason templates, and no reason template is written under two codes.
    *Kills it:* a code with no template, or one template filed twice."""
    assert set(_REFUSAL_REASON) == set(dc.REFUSAL_CODES)
    filed = []
    for got in _REFUSAL_REASON.values():
        filed.extend(got.patterns if isinstance(got, _AnyOf) else (got,))
    names = [next(n for n, p in REASONS.items() if p is pattern) for pattern in filed]
    assert len(names) == len(set(names))
    assert set(REASONS) - set(names) == {"NO_SIGN_VARIATION"}


def _engine_reasons(render):
    """Every reason string the engine wrote into this run's JSON, with where."""
    block = render.block
    if "refusal" in block:
        return [("refusal", block["refusal"]["reason"], block["refusal"])]
    out = []
    spread = block["spread"]
    if "refusal" in spread:
        out.append(("spread", spread["refusal"]["reason"], None))
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
}


def _r_no_futures(render, m, node):
    # "this run has no futures": --no-monte-carlo, or every uncertainty input off
    assert "--no-monte-carlo" in render.extra or single_path_run(render.spec)
    assert render.doc["monte_carlo"] is None or single_path_run(render.spec)


def _r_too_few(render, m, node):
    n = _whole(m["n"])
    assert n == int(render.extra[0])
    assert int(m["min"]) == dr.MIN_INTERVALLED_FUTURES and n < dr.MIN_INTERVALLED_FUTURES


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
    """"the margin is identical on all N futures of bootstrap resample r of R
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
    """A reason is the one measured fact that fired it (§0.1 items 35-37): no
    clause saying why it holds, predicting a run the block did not price, or
    naming another command, and no `--sweep` vocabulary with nothing in the
    block to refer to. Every reason the engine wrote on every render, and
    every template, is free of the words those clauses were built from.
    *Kills it:* any of the cut clauses — "so ...", "rather than", "which is
    why", a route to `--break-even`, `--sweep` or `--decompose`, "raise", a
    grid or a threshold reported — back in a reason."""
    banned = re.compile(r"\bso\b|\brather than\b|\bwhich is why\b|\bbecause\b|"
                        r"--break-even|--sweep|--decompose|\braise\b|\bcould\b|\bwould\b|"
                        r"\binstead\b|\bgrid\b|\bthreshold reported\b")
    for render in renders():
        if render.engine:
            for where, text, node in _engine_reasons(render):
                assert not banned.search(text), (render.name, text)
    for name, pattern in REASONS.items():
        assert not banned.search(pattern.pattern), name


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
