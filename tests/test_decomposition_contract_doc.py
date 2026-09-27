"""docs/reference/API_CONTRACT.md § The `decomposition` block, sentence by
sentence, against runs.

That section is the one prose home for the block. A sentence there is pinned
here by what it CLAIMS, on a run where the claim can fail: the test renders,
then checks the documented relation on that run's own `--json`, its text, a
re-run of the same matrices, or a `--sweep`. Asserting that a key name appears
is not such a test.

`CLAIMS` maps a fragment of each contract sentence to the test that checks it.
`test_every_sentence_is_claimed` fails on a sentence no fragment covers, and
`test_every_claim_is_still_in_the_contract` fails when a sentence a test was
written for has changed, so neither side can move alone.
"""
from __future__ import annotations

import copy
import dataclasses
import decimal
import json
import math
import pathlib
import re
import sys
import types

import numpy as np
import pytest
import yaml

import hde.break_even as be
from hde import decomposition as dc
from hde import decomposition_math as dm
from hde import decomposition_run as dr
from hde import decomposition_text as dt
from hde import monte_carlo
from hde.break_even import REVERSAL_GATE_TOLERANCE, reversal_admission
from hde.config import load_config_dict, single_path_run
from hde.deterministic import compute_deterministic, renewal_segments_for
from hde.monte_carlo import run_monte_carlo
from hde.sweep import flattened_path_note

from tests import decomposition_households as hh
from tests import test_decomposition_sentences as sentences
from tests.decomposition_oracles import freeze_moves, oracle_drawn, oracle_moves, threshold
from tests.decomposition_runs import (
    CONDO_ONLY, CONTRACT, CRASH_EVERY_YEAR, FIXTURE, INCOME, INCOME_ONLY, MONTREAL, MORTGAGE,
    INCOME_ONE_CHANNEL, NEAR_ALL, NO_REACH, PRIOR_NO_CONDO, PRIOR_NO_HOUSE,
    PRIOR_NO_RENT, RARE2, RARE_RESET_ONE, RARE_RESET_THREE, REPO,
    THIRD_FAR, Run, _block_text, _cli, _load, _strict, corpus, force_income_move, untag,
    HAZARD_ONLY, CORRELATION_UNPRICED_CONDO,
    CORRELATION_UNPRICED_HOUSE, CORRELATIONS_PULL_NOTHING, RENTER_LINE_DRAWN, OWNED_LINE,
    OWNED_EVENT, EV_LATE_START, LINES_CONDO_ONLY, LINES_CONDO_NO_HOUSE, HAZARD_ZERO,
    RESET_ZERO, VALUE_VOL_ZERO, BOTH_SHOCKS_DEFAULTED, UNPRICED_CONDO_ZERO_RHO,
    _sweep_states, not_printable_at_every_figure)
from tests.test_decomposition_liveness import RESET_TO_OWN_RENT_ALONE
from tests.test_decomposition_sentences import TWINS


@pytest.fixture(scope="module")
def runs():
    """Every run the claims below are checked on, shared with the sentence
    tests and priced once per session."""
    return corpus()


def _rows(block, register="spread"):
    return block[register]["rows"]


def _point(row):
    return row["alone"] if row["resolved"] else row["provisional_alone"]


def _together(row):
    return row["with_interaction"] if row["resolved"] else row["provisional_with_interaction"]


def _shift(row):
    return row["delta"] if row["resolved"] else row["provisional_delta"]


def _spread_tables(run):
    """`f(A)`, `f(B)` and the `f(A_B)` table of `run`, re-priced through the
    assembler's own seam — the matrices the block's figures are taken on."""
    best = run.doc["verdict"]["best"]
    spec = dr._spec_at(run.spec, run.paths())
    live = tuple(run.block["live_channel_ids"])
    f_a = dr.margin_per_path(dr._run(spec, dr.MATRIX_A), best)
    f_b = dr.margin_per_path(dr._run(spec, dr.MATRIX_B), best)
    f_ab = np.stack([dr.margin_per_path(dr._run(spec, dr.MATRIX_A, {c: dr.MATRIX_B}), best)
                     for c in live])
    return f_a, f_b, f_ab, live


# ---------------------------------------------------------------------------
# The claim map, and the two tests that keep it honest
# ---------------------------------------------------------------------------

CLAIMS = {}


def claims(*fragments):
    def mark(test):
        for fragment in fragments:
            assert fragment not in CLAIMS, fragment
            CLAIMS[fragment] = test.__name__
        return test
    return mark


def _section():
    text = CONTRACT.read_text(encoding="utf-8")
    start = text.index("## The `decomposition` block")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def _sentences():
    """The section's sentences: each table row is one, each bullet item and
    paragraph is split at its full stops."""
    out = []
    for block in re.split(r"\n\s*\n", _section()):
        for unit in re.split(r"\n(?=- |\|)", block):
            unit = " ".join(unit.split())
            if not unit or unit.startswith("#") or unit.startswith("|---") \
                    or unit == "| `code` | Fires when | `reason` states |":
                continue
            out.extend(s for s in re.split(r"(?<=\.)\s+(?=[A-Z`*])", unit) if s)
    return out


def test_every_sentence_is_claimed():
    """A sentence no test claims is a sentence nothing checks."""
    fragments = [" ".join(f.split()) for f in CLAIMS]
    unclaimed = [s for s in _sentences() if not any(f in s for f in fragments)]
    assert unclaimed == []


def test_every_claim_is_still_in_the_contract():
    """A claim whose sentence changed is a test of a sentence that is gone."""
    section = " ".join(_section().split())
    assert [f for f in CLAIMS if " ".join(f.split()) not in section] == []


def _refusal(tmp_path, raw, *extra):
    """A config's `--decompose` block and its text, with the config's path."""
    path = tmp_path / f"cfg{len(list(tmp_path.iterdir()))}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    code, out, _ = _cli(path, "--decompose", *extra, "--json")
    assert code == 0
    doc = _strict(out)
    code, text, _ = _cli(path, "--decompose", *extra, "-q")
    return doc["decomposition"], _block_text(text), path, doc


# ---------------------------------------------------------------------------
# The section's own frame
# ---------------------------------------------------------------------------

@claims("checks each sentence here against a run",
        "Design record:")
def test_the_frame_points_at_files_that_exist():
    assert pathlib.Path(__file__).name == "test_decomposition_contract_doc.py"
    assert (REPO / "docs" / "specs" / "2026-09-22-which-risk-decides-it.md").is_file()
    assert "test_decomposition_contract_doc.py" in _section()


# Where the contract says what each key of the block means, by where the key
# sits: the sentence (or the sentences) that says what it holds, never a list
# of keys alone. A key ending in `_ci` is defined by the one naming rule for
# intervals, and an interval's `low` and `high` by the sentence on intervals.
_STREAM = ("Where the block names a stream, `channel_id` is its id, `label` the name the "
           "text block prints for it (the channel's `label` in `decomposition.CHANNELS`, or "
           "`your pay drops` for the income stream), and `channel`, where it is carried, "
           "the channel's key: the word after its id above.")
_SPREAD_TOP = "The TOP ROW is the row with the largest `alone` point estimate"
_LEVEL_TOP = ("The TOP ROW is the row with the largest shift in size, resolved or not, "
              "named as in `spread`.")
_LEADING = "It is `leading_channel_id` when it resolved"
_UNRESOLVED_TOP = "`unresolved_top_channel_id` when it did not; the other is `null`"
_SPREAD_REFUSAL = ("it instead carries `refusal`, whose `code` is `no_sign_variation` and whose "
                   "`reason` states which")
_PROVISIONAL = ("OR the same four figures as `provisional_alone`, `provisional_alone_ci`, "
                "`provisional_with_interaction`")
_WIDTH_FIGURE = ("`key` names that input, and `formatted` is the input's value formatted "
                 "by the function the report's source lines use")
_SHIFT = ("and the shift, as `delta` (`resolved: true`) or `provisional_delta` "
          "(`resolved: false`).", "The shift is the mean over those futures")
_ROWS_SEARCHED = ("each is the key of exactly one row of `exact`, `estimated` or "
                  "`refused`")
_REFUSED_ROWS = "`refused[]` rows: `key` and `option`, as an `exact[]` row's, `code` and"
_NO_DISTANCE = ("`no_distance_reason` is the measured fact, and `no_distance_code` is "
                "`no_candidate` when")
_REFUSED = ("`refused_boundaries[]`: `verdict_field`, `code` and `reason`: one for a field on "
            "which no boundary is printed")
_REFUSED_CODE = "`reason` is the measured fact, and `code` is `unchanged` when"
_BRACKET_ENDS = ("`value` and `upper_end` are the lower and upper ends of the bracket the "
                 "boundary converged in")
_WAS_BECOMES = "`was` is what the field says at `value`, and `becomes` what it says at `upper_end`."
_SAMPLE_OF_A_BOUNDARY = ("`mc_best` and `decisive` are BISECTED on the run's own futures and "
                         "also carry `curve_probabilities`, `curve_paths` and `seed`.")
_MEANINGS = {
    ("", "paths"): ("`paths` is `N`.",),
    ("", "max_paths"): ("`max_paths` is the largest `N` the budget admits",),
    ("", "live_channel_ids"): ("`live_channel_ids` are the live channels, in id order.",),
    ("", "mean_margin"): ("`mean_margin` and `sd_margin` are the mean and population "
                          "standard deviation",),
    ("", "sd_margin"): ("`mean_margin` and `sd_margin` are the mean and population "
                        "standard deviation",),
    ("", "spread"): ("`spread` — how the variance of `f` splits across the live channels.",),
    ("", "level"): ("`level` — what the futures price that the central case does not.",),
    ("", "refusal"): ("**A whole-block refusal** is one key, `refusal`, holding `code` and "
                      "`reason`",),
    ("refusal", "code"): ("`code` is one of:",),
    ("refusal", "reason"): ("`reason` is the measured fact that fired the refusal",),
    ("refusal", "channel_id"): (_STREAM,),
    ("refusal", "channel"): (_STREAM,),
    ("refusal", "label"): (_STREAM,),
    ("spread", "rows"): ("`rows` holds one row per live channel, and each carries "
                         "`channel_id`, `channel`, `label`, `resolved`, `flip`",),
    ("spread", "interaction"): ("`interaction`, the alone shares' sum and what it leaves "
                                "that no single channel owns",),
    ("spread", "leading_channel_id"): (_SPREAD_TOP, _LEADING),
    ("spread", "unresolved_top_channel_id"): (_SPREAD_TOP, _UNRESOLVED_TOP),
    ("spread", "interaction_channel_ids"): ("`interaction_channel_ids` are the rows whose "
                                            "`interaction_gap_ci` lies entirely above 0.",),
    ("spread", "structural_zeros"): ("`structural_zeros[]`: `kind`, `label`, `keys`, "
                                     "`channel_id`, `measured_paths` and `move_threshold`, "
                                     "one row per stream",),
    ("spread", "refusal"): (_SPREAD_REFUSAL,),
    ("spread.refusal", "code"): (_SPREAD_REFUSAL,),
    ("spread.refusal", "reason"): (_SPREAD_REFUSAL,),
    ("spread.rows[]", "channel_id"): (_STREAM,),
    ("spread.rows[]", "channel"): (_STREAM,),
    ("spread.rows[]", "label"): (_STREAM,),
    ("spread.rows[]", "resolved"): ("A row is `resolved: false` when either share's point "
                                    "estimate lies outside [0, 1]",),
    ("spread.rows[]", "alone"): ("`alone` is the channel's first-order Sobol index",),
    ("spread.rows[]", "with_interaction"): ("`with_interaction` is its total index",),
    ("spread.rows[]", "provisional_alone"): (_PROVISIONAL,),
    ("spread.rows[]", "provisional_with_interaction"): (_PROVISIONAL,),
    ("spread.rows[]", "flip"): ("`flip` is a fraction of futures, not a share",),
    ("spread.rows[]", "interaction_gap"): ("`interaction_gap` is `with_interaction − alone` "
                                           "on that row",),
    ("spread.rows[]", "widths"): ("`widths[]`: `key`, `formatted`, `source`, `anchor`, "
                                  "`note` and `tag`. A width is a sizing input of the row's "
                                  "channel's draws",),
    ("spread.rows[].widths[]", "key"): (_WIDTH_FIGURE,),
    ("spread.rows[].widths[]", "formatted"): (_WIDTH_FIGURE,),
    ("spread.rows[].widths[]", "source"): ("One the config states carries its read-back "
                                           "class as `source`",),
    ("spread.rows[].widths[]", "anchor"): ("`anchor` names the registry entry the figure "
                                           "came from",),
    ("spread.rows[].widths[]", "note"): ("On the economy row a `note` names the correlation "
                                         "key that pulls an option's shock onto that row",),
    ("spread.rows[].widths[]", "tag"): ("`tag` is the read-back's tag for the key",),
    ("spread.interaction", "resolved"): ("`resolved` is true when that interval lies "
                                         "entirely below 1",),
    ("spread.interaction", "first_order_sum"): ("`first_order_sum` (the sum of every row's "
                                                "`alone` point estimate",),
    ("spread.interaction", "residual"): ("`residual` (`1 − first_order_sum`)",),
    ("spread.structural_zeros[]", "kind"): ("`kind` is `dead_draw` on every row.",),
    ("spread.structural_zeros[]", "label"): (_STREAM,),
    ("spread.structural_zeros[]", "channel_id"): (_STREAM, "(`channel_id`: a channel, or 7 "
                                                           "for the income stream)"),
    ("spread.structural_zeros[]", "keys"): ("`keys` are the keys of the stream's widths",),
    ("spread.structural_zeros[]", "measured_paths"): ("that drew on the block's "
                                                      "`measured_paths` futures",),
    ("spread.structural_zeros[]", "move_threshold"): ("whose re-draw moved no priced "
                                                      "option's present value on them by "
                                                      "more than `move_threshold`",),
    ("level", "rows"): ("`rows` holds one row per live channel, and each carries "
                        "`channel_id`, `channel`, `label`, `resolved`, `se`",),
    ("level", "paths"): ("The level register prices the first `min(N, 2000)` of those "
                         "futures (`level.paths`).",),
    ("level", "prob_best_base"): ("`prob_best_base` and `futures_margin` are the fraction "
                                  "of the level's futures with `f > 0` and the mean of `f` "
                                  "over them.",),
    ("level", "futures_margin"): ("`prob_best_base` and `futures_margin` are the fraction "
                                  "of the level's futures with `f > 0` and the mean of `f` "
                                  "over them.",),
    ("level", "all_frozen_margin"): ("`all_frozen_margin` is the margin every path prices "
                                     "with every channel frozen.",),
    ("level", "all_frozen_path_spread"): ("`all_frozen_path_spread` is how far those paths "
                                          "differ from each other",),
    ("level", "all_frozen_deviation"): ("`all_frozen_deviation` is `all_frozen_margin` "
                                        "against `verdict.margin_pv`.",),
    ("level", "accounted_for"): ("`accounted_for` is the sum of every row's shift",),
    ("level", "leading_channel_id"): (_LEVEL_TOP, _LEADING),
    ("level", "unresolved_top_channel_id"): (_LEVEL_TOP, _UNRESOLVED_TOP),
    ("level.rows[]", "channel_id"): (_STREAM,),
    ("level.rows[]", "channel"): (_STREAM,),
    ("level.rows[]", "label"): (_STREAM,),
    ("level.rows[]", "resolved"): ("`label`, `resolved`, `se`, `prob_best_frozen`, and the "
                                   "shift",
                                   "A row resolves when the size of its shift exceeds twice "
                                   "its `se`."),
    ("level.rows[]", "se"): ("`se` is the paired standard error of that difference",),
    ("level.rows[]", "prob_best_frozen"): ("`prob_best_frozen` the fraction with `f > 0` "
                                           "once frozen.",),
    ("level.rows[]", "delta"): _SHIFT,
    ("level.rows[]", "provisional_delta"): _SHIFT,
    ("", "reversal"): ("`reversal` — what would have to change for the verdict to change, "
                       "on inputs the config states that carry no distribution.",),
    ("reversal", "exact"): (_ROWS_SEARCHED, "and otherwise in `exact` when it passes the "
                                            "exactness test below"),
    ("reversal", "estimated"): (_ROWS_SEARCHED, "and in `estimated` when it does not."),
    ("reversal", "refused"): (_ROWS_SEARCHED, "A key is in `refused` when moving it to the "
                                              "far end of its bracket"),
    ("reversal.refused[]", "key"): (_REFUSED_ROWS, "`key` is the key searched and `option` "
                                                   "the option it belongs to."),
    ("reversal.refused[]", "option"): (_REFUSED_ROWS, "`key` is the key searched and "
                                                      "`option` the option it belongs to."),
    ("reversal.refused[]", "code"): ("`code` is `not_admitted`, and `reason` is the measured "
                                     "fact.",),
    ("reversal.refused[]", "reason"): ("`code` is `not_admitted`, and `reason` is the "
                                       "measured fact.",),
    ("reversal", "structural_zeros"): ("`structural_zeros[]`: `kind`, `label`, `keys` and "
                                       "`reversal_key`, one row per `exact` row",),
    ("reversal", "no_distance_code"): (_NO_DISTANCE,),
    ("reversal", "no_distance_reason"): (_NO_DISTANCE,),
    ("reversal.exact[]", "key"): ("`key` is the key searched and `option` the option it "
                                  "belongs to.",),
    ("reversal.exact[]", "option"): ("`key` is the key searched and `option` the option it "
                                     "belongs to.",),
    ("reversal.exact[]", "bracket_low"): ("`bracket_low` and `bracket_high` bound the search",),
    ("reversal.exact[]", "bracket_high"): ("`bracket_low` and `bracket_high` bound the "
                                           "search",),
    ("reversal.exact[]", "bracket_source"): ("and `bracket_source` is whose range that is",),
    ("reversal.exact[]", "probe_paths"): ("over `probe_paths` paths; "
                                          "`max_path_deviation_over_sd` is the largest "
                                          "departure measured.",),
    ("reversal.exact[]", "max_path_deviation_over_sd"): (
        "over `probe_paths` paths; `max_path_deviation_over_sd` is the largest departure "
        "measured.",),
    ("reversal.exact[]", "boundaries"): ("`boundaries[]`: `verdict_field`, `value`, "
                                         "`upper_end`, `formatted`, `was`,",
                                         "Boundaries are the edges of every stretch of the "
                                         "bracket"),
    ("reversal.exact[]", "refused_boundaries"): (_REFUSED,),
    ("reversal.exact[]", "path_note"): ("`path_note` is set when the config states the key "
                                        "as a path of two or more",),
    ("reversal.exact[].boundaries[]", "verdict_field"): ("`verdict_field` is the field of the "
                                                         "verdict that changes",),
    ("reversal.exact[].boundaries[]", "value"): (_BRACKET_ENDS,),
    ("reversal.exact[].boundaries[]", "upper_end"): (_BRACKET_ENDS,),
    ("reversal.exact[].boundaries[]", "formatted"): ("`formatted` is the boundary's figure as "
                                                     "the text block prints it.",),
    ("reversal.exact[].boundaries[]", "was"): (_WAS_BECOMES,),
    ("reversal.exact[].boundaries[]", "becomes"): (_WAS_BECOMES,),
    ("reversal.exact[].boundaries[]", "further_changes"): ("`further_changes` is `\"above\"` "
                                                           "when",),
    ("reversal.exact[].boundaries[]", "confirming_probabilities"): (
        "`confirming_probabilities` is each option's probability of being cheapest",),
    ("reversal.exact[].boundaries[]", "curve_probabilities"): (
        "`curve_probabilities` is the same read off the run's own futures shifted to",),
    ("reversal.exact[].boundaries[]", "curve_paths"): (_SAMPLE_OF_A_BOUNDARY,),
    ("reversal.exact[].boundaries[]", "seed"): (_SAMPLE_OF_A_BOUNDARY,),
    ("reversal.exact[].refused_boundaries[]", "verdict_field"): (_REFUSED,),
    ("reversal.exact[].refused_boundaries[]", "code"): (_REFUSED, _REFUSED_CODE),
    ("reversal.exact[].refused_boundaries[]", "reason"): (_REFUSED, _REFUSED_CODE),
    ("reversal.structural_zeros[]", "kind"): ("`kind` is `stated_path` on every row",),
    ("reversal.structural_zeros[]", "label"): ("and `label` is `the renewal rate` or `the "
                                               "contract rate`.",),
    ("reversal.structural_zeros[]", "keys"): ("`keys` holds that row's key",),
    ("reversal.structural_zeros[]", "reversal_key"): ("`reversal_key` names that row",),
    ("*", "*_ci"): ("A key ending in `_ci` is the interval on the figure its name begins "
                    "with.",),
    ("*_ci", "low"): ("Every interval is an object with `low` and `high`: a 95% percentile "
                      "interval",),
    ("*_ci", "high"): ("Every interval is an object with `low` and `high`: a 95% percentile "
                       "interval",),
}


def _emitted(node, parent="", out=None):
    """`(where it sits, key)` for every key of one `decomposition` object, a
    `*_ci` key filed under the naming rule and its bounds under intervals."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            if key.endswith("_ci"):
                assert key[:-3] in node, (parent, key)   # the figure it is the interval on
                out.add(("*", "*_ci"))
                _emitted(value, "*_ci", out)
            else:
                out.add((parent, key))
                _emitted(value, f"{parent}.{key}".lstrip("."), out)
    elif isinstance(node, list):
        for value in node:
            _emitted(value, f"{parent}[]", out)
    return out


def _named_streams(node):
    """Every object of the block that names a stream by `channel_id`."""
    if isinstance(node, dict):
        if "channel_id" in node:
            yield node
        for value in node.values():
            yield from _named_streams(value)
    elif isinstance(node, list):
        for value in node:
            yield from _named_streams(value)


@claims("This section is the one prose home for the block: what every key means",
        _STREAM)
def test_the_contract_says_what_every_key_the_block_emits_means(tmp_path, runs):
    """Enumerated: every key of `--json`'s `decomposition` across the corpus and
    two whole-block refusals, by where it sits, has a sentence of this section
    that says what it holds (`_MEANINGS`), and the section still carries each
    such sentence; and every meaning listed is a key some run emits. A stream's
    `channel` and `label` are the ones `decomposition.CHANNELS` holds for its
    id, or the income stream's own label.
    *Kills it:* a key the block emits that no sentence defines (a new key with
    no meaning written), a defining sentence cut from the contract, or a row
    naming its stream by another stream's key or label."""
    section = " ".join(_section().split())
    documents = [run.block for run in runs.values()]
    for raw in (_load(MONTREAL), _load(INCOME)):
        doc, _, _, _ = _refusal(tmp_path, raw)
        documents.append(doc)
    emitted = set()
    for document in documents:
        _emitted(document, out=emitted)
    assert emitted - set(_MEANINGS) == set()
    assert set(_MEANINGS) - emitted == set()
    for (parent, key), fragments in _MEANINGS.items():
        assert all(" ".join(f.split()) in section for f in fragments), (parent, key)
        pattern = r"`_ci`" if key == "*_ci" else rf"`(?:[\w.]+\.)?{re.escape(key)}(?:`|\[\]|:)"
        assert any(re.search(pattern, f) for f in fragments), (parent, key)
    # each stream named by its own key and label
    named = [node for document in documents for node in _named_streams(document)]
    assert {node["channel_id"] for node in named} >= {dc.INCOME_STREAM_ID} | set(range(7))
    assert documents[-1]["refusal"]["code"] == "one_channel" and \
        "channel" in documents[-1]["refusal"]
    for node in named:
        if node["channel_id"] == dc.INCOME_STREAM_ID:
            assert node["label"] == dc.INCOME_STREAM_LABEL and "channel" not in node
            continue
        entry = dc.channel(node["channel_id"])
        assert node["label"] == entry.label, node
        assert node.get("channel", entry.key) == entry.key, node
    # each register holds its own kind of row with no place in the other
    for register, kind in (("spread", "dead_draw"), ("reversal", "stated_path")):
        zeros = [zero for document in documents
                 for zero in document.get(register, {}).get("structural_zeros", ())]
        assert zeros and {zero["kind"] for zero in zeros} == {kind}


# ---------------------------------------------------------------------------
# Presence, path counts and numbers
# ---------------------------------------------------------------------------

@claims("The key is present only when `--decompose` is passed",
        "The flag goes before or after the config.",
        "`--decompose` with `--read-back` refuses before anything is priced")
def test_presence(runs, monkeypatch):
    run = runs["mortgage"]
    code, out, _ = _cli(run.path, "--json")
    assert code == 0 and "decomposition" not in _strict(out)
    code, out, _ = _cli("--decompose=200", run.path, "--json")
    assert code == 0 and _strict(out)["decomposition"] == run.block
    code, out, _ = _cli(run.path, "--decompose", "200", "--json")
    assert code == 0 and _strict(out)["decomposition"] == run.block

    def no_pricing(*args, **kwargs):
        raise AssertionError("priced before refusing")
    monkeypatch.setattr("hde.cli.run_monte_carlo", no_pricing, raising=False)
    monkeypatch.setattr("hde.cli.compute_deterministic", no_pricing, raising=False)
    code, out, err = _cli(run.path, "--decompose", "--read-back")
    assert code == 1 and out == "" and "--read-back" in err


@claims("sets `N`; bare, `N` is `simulation.num_sims`.",
        "are taken on `N` futures the block draws for itself (`paths`).",
        "The level register prices the first `min(N, 2000)` of those futures")
def test_the_assembler_says_whose_each_probability_is(runs):
    """`decomposition_run`'s docstring says which probabilities the assembler
    takes and on which futures. Each clause is checked on runs whose N
    differs from `simulation.num_sims`.
    *Kills it:* a docstring that files a probability on other futures than
    these — in place of its one sentence or beside it: every sentence of the
    docstring that speaks of a probability is this one."""
    said = " ".join(dr.__doc__.split())
    whose = [
        "The probabilities this module takes itself are frequencies of `f`'s sign on "
        "futures it priced: over all N for whether the futures sit on both sides of the "
        "line, and over the level register's first paths for its `prob_best_*`."]

    def about_probabilities(text):
        return [s for s in re.split(r"(?<=\.)\s+(?=[A-Z`])", text)
                if "probabilit" in s.lower()]

    assert about_probabilities(said) == whose
    appended = said.replace(whose[0], whose[0] + " Every probability here is taken on "
                            "the run's own Monte Carlo sample.")
    assert about_probabilities(appended) != whose
    fixture = runs["fixture"]
    f_a = fixture.f_a()
    level = fixture.block["level"]
    assert level["prob_best_base"] == float(np.mean(f_a[:level["paths"]] > 0.0))
    mortgage = runs["mortgage"]
    assert float(np.mean(mortgage.f_a() > 0.0)) == 1.0
    assert mortgage.block["spread"]["refusal"]["reason"] == (
        f"{mortgage.doc['verdict']['best']} is cheapest in all "
        f"{mortgage.paths():,} of these futures")
    assert fixture.paths() != fixture.spec.simulation.num_sims


def test_how_many_futures_each_register_prices(runs):
    """The fixture at `--decompose=300`: the spread and the level at 300. At
    4,000 the level stops at 2,000; bare, `N` is the config's own count."""
    fixture = runs["fixture"]
    block = fixture.block
    assert block["paths"] == 300 == fixture.f_a().size
    assert block["level"]["paths"] == 300
    # which streams draw and which channels are live: on the same 300, and
    # the rows that measure it are the spread register's (§0.1 item 48)
    assert [z["measured_paths"] for z in block["spread"]["structural_zeros"]
            if z["kind"] == "dead_draw"] == [300]
    assert runs["advanced_4000"].block["level"]["paths"] == 2000
    assert runs["advanced_4000"].block["paths"] == 4000
    code, out, _ = _cli("--decompose", runs["mortgage"].path, "--json")
    bare = _strict(out)["decomposition"]
    assert bare["paths"] == runs["mortgage"].spec.simulation.num_sims != 200


@claims("Every number in the block is finite, so a strict JSON parser",
        "A measured zero stays `0.0`.")
def test_numbers(runs):
    """Strict parsing is `Run`'s own; here no figure of any corpus run is
    `null`, a real 0.0 is not turned into `null` by the guard that nulls a
    non-finite figure, and a figure that is not finite — constructed, since
    no run emits one — is emitted as `null` and the document stays strict.
    *Kills it:* deleting the guard (a bare `NaN` token fails the strict
    parser) or widening it to take in a zero."""
    for name in ("fixture", "mortgage", "advanced", "three", "min"):
        level = runs[name].block["level"]
        assert level["all_frozen_path_spread"] == 0.0, name
        assert level["all_frozen_path_spread"] is not None
    nulls = []

    def walk(node, where):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, where + (key,))
        elif isinstance(node, list):
            for value in node:
                walk(value, where)
        elif node is None:
            nulls.append(where[-1])
    for run in runs.values():
        walk(run.block, ())
    figures = {"alone", "with_interaction", "flip", "delta", "provisional_delta", "se",
               "mean_margin", "sd_margin", "low", "high", "first_order_sum", "residual",
               "move_threshold", "futures_margin", "all_frozen_margin",
               "all_frozen_deviation", "accounted_for", "prob_best_base",
               "prob_best_frozen", "interaction_gap"}
    assert not (set(nulls) & figures)
    from hde.serialization import decomposition_to_dict
    from tests.decomposition_households import uncertainty_surface
    dec = uncertainty_surface()
    first = dec.level.rows[0]
    rows = (dataclasses.replace(first, level=dataclasses.replace(first.level,
                                                                se=float("nan"))),
            ) + dec.level.rows[1:]
    doc = decomposition_to_dict(dataclasses.replace(
        dec, level=dataclasses.replace(dec.level, rows=rows, accounted_for=0.0)))
    text = json.dumps(doc)
    assert _strict(text)["level"]["rows"][0]["se"] is None
    assert _strict(text)["level"]["accounted_for"] == 0.0


# ---------------------------------------------------------------------------
# Whole-block refusals
# ---------------------------------------------------------------------------

@claims("**A whole-block refusal** is one key",
        "`one_channel` also carries `channel_id`, `channel` and `label`.",
        "`reason` is the measured fact that fired the refusal, and the text block prints",
        "`code` is one of:")
def test_a_refusal_is_one_key_and_prints_its_code_and_reason(tmp_path):
    doc, text, _, _ = _refusal(tmp_path, _load(MONTREAL))
    assert list(doc) == ["refusal"] and set(doc["refusal"]) == {"code", "reason"}
    assert text == f"which risk decides it — not split (no_futures): {doc['refusal']['reason']}"
    doc, text, _, _ = _refusal(tmp_path, _load(INCOME))
    refusal = doc["refusal"]
    assert refusal["code"] == "one_channel"
    assert refusal["channel_id"] == dc.channel_by_key(refusal["channel"]).id
    assert refusal["label"] == dc.channel(refusal["channel_id"]).label
    assert text == f"which risk decides it — not split (one_channel): {refusal['reason']}"


@claims("| `no_futures` | the run has no futures")
def test_no_futures(tmp_path):
    """A single-path run and a `--no-monte-carlo` run, two options or three."""
    assert single_path_run(load_config_dict(_load(MONTREAL)))
    for raw, extra in ((_load(MONTREAL), ()), (_load(FIXTURE), ("--no-monte-carlo",))):
        doc, _, _, _ = _refusal(tmp_path, raw, *extra)
        assert doc["refusal"] == {"code": "no_futures", "reason": "this run has no futures"}


@claims("| `single_option` |")
def test_single_option(tmp_path):
    doc, _, _, _ = _refusal(tmp_path, CONDO_ONLY)
    assert doc["refusal"] == {"code": "single_option",
                              "reason": "this run prices one option"}
    assert [o for o in ("condo", "house", "rent") if o in CONDO_ONLY] == ["condo"]


@claims("| `one_channel` |")
def test_one_channel(tmp_path):
    """The count of futures and the one channel whose re-seeding, on held
    generators and as many futures, moves a present value past the budget."""
    doc, _, _, _ = _refusal(tmp_path, _load(INCOME))
    refusal = doc["refusal"]
    assert refusal["code"] == "one_channel"
    spec = load_config_dict(_load(INCOME))
    n = spec.simulation.num_sims
    moves = oracle_moves(spec, n)
    assert [c for c in range(7) if moves[c] > threshold(spec)] == [refusal["channel_id"]]
    assert refusal["reason"] == (f"one channel is live on these {n:,} futures: "
                                 f"{refusal['label']}")


@claims("| `no_spread` |")
def test_no_spread(tmp_path):
    """Both forms, each reason the fact that fired it: no live channel on a
    margin that is not one figure (it differs across futures in its last bits,
    and every drawing stream's re-seeding moves nothing past the budget), and
    a margin identical on every future — re-priced here to that figure."""
    doc, _, _, full = _refusal(tmp_path, RESET_TO_OWN_RENT_ALONE)
    spec = load_config_dict(RESET_TO_OWN_RENT_ALONE)
    n = spec.simulation.num_sims
    assert doc["refusal"] == {"code": "no_spread",
                              "reason": f"no channel is live on these {n:,} futures"}
    drawn = oracle_drawn(spec)
    moves = oracle_moves(spec, n)
    assert drawn and all(moves[c] <= threshold(spec) for c in drawn)
    f = dr.margin_per_path(dr._run(dr._spec_at(spec, n), dr.MATRIX_A),
                           full["verdict"]["best"])
    assert float(np.ptp(f)) > 0.0
    below_zero = set()
    for raw in (TWINS, THIRD_FAR, NO_REACH, CRASH_EVERY_YEAR):
        doc, _, _, full = _refusal(tmp_path, raw)
        spec = load_config_dict(raw)
        n = int(spec.simulation.num_sims)
        f = dr.margin_per_path(dr._run(dr._spec_at(spec, n), dr.MATRIX_A),
                               full["verdict"]["best"])
        assert float(np.ptp(f)) == 0.0
        value = float(f[0])
        assert doc["refusal"] == {"code": "no_spread", "reason": (
            f"the margin is identical on all {n:,} futures "
            f"({'-' if value < 0 else ''}${abs(value):,.2f})")}
        assert ("(-$" in doc["refusal"]["reason"]) == (value < 0)
        below_zero.add(value < 0)
    # Both signs are witnessed, so the sign cannot be dropped or forced
    # (§0.1 item 44).
    assert below_zero == {True, False}


@claims("| `budget` |")
def test_budget(tmp_path, runs):
    """Both forms. Above the ceiling, `N` alone refuses. Below it, on the
    fixture, the count is the streams the held-generator instrument sees
    drawing — eight, the income stream's included — and the largest `N` is the
    one the formula at that count admits."""
    doc, _, _, _ = _refusal(tmp_path, _load(FIXTURE), "250001")
    assert doc["refusal"] == {"code": "budget", "reason": (
        "250,001 futures price 250,001 path evaluations before any re-draw, above "
        "the ceiling of 250,000 [set in the engine]")}
    k = len(oracle_drawn(runs["fixture"].spec))
    assert k == 8
    largest = dr.largest_affordable_paths(k)
    n = largest + 1
    doc, _, _, _ = _refusal(tmp_path, _load(FIXTURE), str(n))
    work = n * (k + 2) + 2000 * (k + 1)
    assert doc["refusal"] == {"code": "budget", "reason": (
        f"{n:,} futures with {k} streams drawing on them price up to {work:,} path "
        f"evaluations, above the ceiling of 250,000 [set in the engine]; the largest "
        f"path count within it is {largest:,}")}
    assert dr.EVALUATION_CEILING == 250_000
    assert largest * (k + 2) + 2000 * (k + 1) <= 250_000 < work


@claims("| `too_few_futures` |")
def test_too_few_futures(tmp_path):
    doc, text, _, _ = _refusal(tmp_path, _load(MORTGAGE), "39")
    assert doc["refusal"] == {"code": "too_few_futures",
                              "reason": "39 futures were asked for, below the minimum of 40"}
    assert text == ("which risk decides it — not split (too_few_futures): 39 futures were "
                    "asked for, below the minimum of 40")
    doc, text, _, _ = _refusal(tmp_path, _load(MORTGAGE), "1")
    assert doc["refusal"] == {"code": "too_few_futures",
                              "reason": "1 future was asked for, below the minimum of 40"}
    assert text == ("which risk decides it — not split (too_few_futures): 1 future was "
                    "asked for, below the minimum of 40")
    doc, _, _, _ = _refusal(tmp_path, _load(MORTGAGE), "40")
    assert "refusal" not in doc and doc["paths"] == 40


@claims("| `freeze_leak` |", "| `identity_failed` |",
        "how far apart a `freeze_leak` reason says the paths are at six",
        "how far apart an `identity_failed` reason says the margins are")
def test_the_identity_refusals_forced_on_a_real_run(runs, monkeypatch):
    """Neither fires on a correct engine, so each is forced through the CLI on
    the fixture at 40 paths with the real engine and one run moved: a mask
    that lets one channel escape (the paths then differ), and the all-frozen
    run shifted by one constant (they agree, off the central case). Each
    reason is re-derived from that same run; the leak's spread prints at six
    significant figures, taken upward, with its thousands separator; how far
    apart the margins are prints at three, taken upward, and the allowance at
    three, taken downward.
    *Kills it:* that spread printed to nearest, which lands below it here, or
    a step above its ceiling, or with no separator; either figure of the
    identity's reason printed the other way."""
    from tests.test_decomposition_run import TestTheFreezeIdentity, TestTheIdentityIsGated
    fixture = runs["fixture"]
    det, _, verdict = fixture.inputs()
    spec = dr._spec_at(fixture.spec, 40)
    with monkeypatch.context() as patched:
        TestTheFreezeIdentity._leaky_mask(patched, escaped=dc.channel_by_key("shelter").id)
        code, out, _ = _cli(fixture.path, "--decompose=40", "--json")
        frozen = dr.margin_per_path(dr._run(spec, dr.MATRIX_A, freeze=dr.ALL_CHANNEL_IDS),
                                    verdict.best)
    spread = float(np.max(np.abs(frozen - frozen[0])))
    assert spread > 0.0
    reason = _strict(out)["decomposition"]["refusal"]["reason"]
    assert _strict(out)["decomposition"] == {"refusal": {"code": "freeze_leak",
                                                         "reason": reason}}
    printed = re.fullmatch(r"with every channel frozen, the margins of the 40 paths differ "
                           r"by up to \$(?P<spread>[\d,.]+(?:e[+-]\d+)?)", reason)["spread"]
    _taken_upward(printed, spread, 6)
    assert spread >= 1000.0 and printed == f"{float(printed.replace(',', '')):,.6g}"
    # a spread whose nearest figure at six places lies below it
    assert decimal.Decimal(f"{spread:.6g}") < decimal.Decimal(spread)
    with monkeypatch.context() as patched:
        TestTheIdentityIsGated._offset_all_frozen(patched, 0.01)
        code, out, _ = _cli(fixture.path, "--decompose=40", "--json")
        frozen = dr.margin_per_path(dr._run(spec, dr.MATRIX_A, freeze=dr.ALL_CHANNEL_IDS),
                                    verdict.best)
    budget = dr.identity_budget(det, verdict)
    assert float(np.ptp(frozen)) == 0.0
    apart = abs(float(frozen[0]) - verdict.margin_pv)
    assert apart > budget
    refusal = _strict(out)["decomposition"]["refusal"]
    assert refusal["code"] == "identity_failed"
    got = re.fullmatch(
        rf"with every channel frozen, the 40 paths price a margin of "
        rf"{re.escape(f'${frozen[0]:,.2f}')} against the central case's "
        rf"{re.escape(f'${verdict.margin_pv:,.2f}')}, \$(?P<apart>\S+) apart, "
        rf"above the \$(?P<budget>\S+) this check allows", refusal["reason"])
    _taken_upward(got["apart"], apart, 3)
    _taken_downward(got["budget"], budget, 3)


def _taken_upward(printed, value, digits):
    """`printed` is `value` at `digits` significant figures, taken upward: no
    more digits, never below it, and less than one printed step above it."""
    figure = decimal.Decimal(printed.replace(",", ""))
    assert len(figure.normalize().as_tuple().digits) <= digits, printed
    assert figure >= decimal.Decimal(value), (printed, value)
    assert figure - decimal.Decimal(1).scaleb(figure.adjusted() - (digits - 1)) \
        < decimal.Decimal(value), (printed, value)


def _taken_downward(printed, value, digits):
    """`printed` is `value` at `digits` significant figures, taken downward:
    no more digits, never above it, and less than one printed step below it."""
    figure = decimal.Decimal(printed.replace(",", ""))
    assert len(figure.normalize().as_tuple().digits) <= digits, printed
    assert figure <= decimal.Decimal(value), (printed, value)
    assert figure + decimal.Decimal(1).scaleb(figure.adjusted() - (digits - 1)) \
        > decimal.Decimal(value), (printed, value)


@claims("the allowance an `income_moved` or `identity_failed` reason states prints at")
def test_each_reason_says_above_of_a_larger_printed_figure():
    """An allowance of 2^-28, which prints 3.73e-09 to nearest, and a move and
    a deviation of 3.7314e-09 above it, which print 3.73e-09 to nearest too:
    each reason, written by the engine's own check from these figures, prints
    the allowance taken downward (3.72e-09) and the figure above it taken
    upward (3.74e-09), so its "above" holds at the printed figures.
    *Kills it:* the allowance printed to nearest, or the move or the deviation
    printed to nearest; either leaves a figure said to be above one it equals."""
    allowance, above = 2.0 ** -28, 3.7314e-09
    assert above > allowance
    assert f"{allowance:.3g}" == f"{above:.3g}" == "3.73e-09"
    _taken_downward("3.72e-09", allowance, 3)
    _taken_upward("3.74e-09", above, 3)

    def priced(pvs):
        return types.SimpleNamespace(condo=None, house=None,
                                     rent=types.SimpleNamespace(pvs=np.full(40, pvs)))

    with pytest.raises(dr.CheckFailed) as failed:
        dr._liveness(priced(0.0), {dc.INCOME_STREAM_ID: priced(above)}, allowance, 40)
    assert (failed.value.code, failed.value.reason) == ("income_moved", (
        "re-drawing the income stream moved an option's present value on these 40 "
        "futures by up to $3.74e-09, above $3.72e-09"))
    level = types.SimpleNamespace(paths=40, all_frozen_margin=1000.0,
                                  all_frozen_deviation=above)
    got = dr._identity_failed(level, types.SimpleNamespace(margin_pv=1000.0), allowance)
    assert (got.code, got.reason) == ("identity_failed", (
        "with every channel frozen, the 40 paths price a margin of $1,000.00 against the "
        "central case's $1,000.00, $3.74e-09 apart, above the $3.72e-09 this check "
        "allows"))


def test_a_move_that_is_not_finite_still_refuses_the_block(tmp_path, monkeypatch):
    """The income stream's re-draw forced to move a present value by an
    infinite amount, and by one that is not a number: the block refuses with
    `income_moved`, its reason stating the figure as measured, and the rest
    of the run's output is what the run prints without `--decompose`, exit 0.
    *Kills it:* a figure that is not finite raising while the reason is
    written, which loses the report."""
    path = tmp_path / "fixture.yaml"
    path.write_text(yaml.safe_dump(_load(FIXTURE), sort_keys=False), encoding="utf-8")
    plain = _cli(path, "-q")
    for forced, printed in ((math.inf, "inf"), (math.nan, "nan")):
        with monkeypatch.context() as patched:
            force_income_move(patched, forced)
            status, text, err = _cli(path, "--decompose=40", "-q")
        assert status == 0 and err == plain[2]
        allowance = re.search(r"above \$(\S+)$", text.rstrip("\n"))[1]
        assert _inserted(plain[1], text)[1] == ["", (
            f"which risk decides it — not split (income_moved): re-drawing the income "
            f"stream moved an option's present value on these 40 futures by up to "
            f"${printed}, above ${allowance}")]
    assert dr.ceiled_figure(math.inf, 3) == "inf" and dr.floored_figure(math.inf, 3) == "inf"
    assert dr.ceiled_figure(160831.2, 6, ",") == "160,832"
    assert dr.ceiled_figure(160831.2, 6) == "160832"


@claims("| `income_moved` |", "the largest move an `income_moved` reason states")
def test_income_moved(tmp_path, monkeypatch):
    """Forced, as no correct engine moves a present value by re-drawing the
    income stream: its re-draw handed back as `A`'s own present values moved
    by one figure (`force_income_move`). Past the allowance the block refuses,
    stating the count of futures, that move taken upward at three significant
    figures, and the allowance taken downward; at half the allowance it does
    not, and the
    block is the one the run prints unforced. The move forced is one whose
    nearest figure at three places lies below it.
    *Kills it:* the check deleted, or widened to a move inside the allowance,
    or the largest move printed to nearest or a step above its ceiling."""
    raw = _load(FIXTURE)
    spec = load_config_dict(raw)
    det, mc = compute_deterministic_and_mc(spec)
    allowance = dr.identity_budget(det, _verdict(spec, det, mc))
    unforced, _, _, _ = _refusal(tmp_path, raw, "40")
    assert "refusal" not in unforced
    assert dc.INCOME_STREAM_ID in [z["channel_id"] for z in
                                   unforced["spread"]["structural_zeros"]]
    base = dr._run(dr._spec_at(spec, 40), dr.MATRIX_A)
    # 1,234.5 prints as 1.23e+03 to nearest, below the move; 1,000 is exact
    for forced, printed in ((1234.5, "1.24e+03"), (1000.0, "1e+03")):
        with monkeypatch.context() as patched:
            force_income_move(patched, forced)
            doc, text, _, _ = _refusal(tmp_path, raw, "40")
        printed_allowance = re.fullmatch(r".*, above \$(\S+)", doc["refusal"]["reason"])[1]
        _taken_downward(printed_allowance, allowance, 3)
        reason = (f"re-drawing the income stream moved an option's present value on these "
                  f"40 futures by up to ${printed}, above ${printed_allowance}")
        assert doc == {"refusal": {"code": "income_moved", "reason": reason}}
        assert text == f"which risk decides it — not split (income_moved): {reason}"
        moved = max(float(np.max(np.abs((np.asarray(getattr(base, o).pvs) + forced)
                                        - np.asarray(getattr(base, o).pvs))))
                    for o in ("condo", "house", "rent"))
        _taken_upward(printed, moved, 3)
    with monkeypatch.context() as patched:
        force_income_move(patched, allowance / 2)
        doc, _, _, _ = _refusal(tmp_path, raw, "40")
    assert doc == unforced


@claims("| `untagged_width` |")
def test_untagged_width(tmp_path, monkeypatch):
    """Forced, as every width a correct engine names has a read-back tag: the
    tag withheld from one key (`untag`). The block refuses, naming that key and
    the row it is on, on `--json` too, where no formatter reads a tag.
    *Kills it:* the check deleted, so the width is emitted with no tag."""
    with monkeypatch.context() as patched:
        untag(patched, "simulation.investment_return_vol")
        doc, text, _, _ = _refusal(tmp_path, _load(FIXTURE), "40")
    reason = (f"simulation.investment_return_vol, a width on the row of "
              f"{dc.channel_by_key('portfolio').label}, has no tag in the read-back")
    assert doc == {"refusal": {"code": "untagged_width", "reason": reason}}
    assert text == f"which risk decides it — not split (untagged_width): {reason}"


@claims("| `degenerate_resample` |")
def test_degenerate_resample(tmp_path, runs):
    """Two rare hazards on 400 futures: the margin differs across them, and a
    resample of the table the spread register's intervals are read off (the
    run's seed, `bootstrap_path_indices`) holds one margin. The reason names
    the first such resample, the 400 draws it holds, which repeat futures, of
    how many resamples, and that margin. On 2,000 futures of the same config
    no resample does, and the block prints.
    *Kills it:* the check deleted, or a reason naming another resample or
    another figure."""
    doc, _, _, full = _refusal(tmp_path, RARE2, "400")
    spec = load_config_dict(RARE2)
    f = dr.margin_per_path(dr._run(dr._spec_at(spec, 400), dr.MATRIX_A),
                           full["verdict"]["best"])
    assert float(np.ptp(f)) > 0.0
    table = dm.bootstrap_path_indices(400, dm.DEFAULT_RESAMPLES,
                                      int(spec.simulation.random_seed))
    flat = [i for i, rows in enumerate(table) if float(np.ptp(f[rows])) == 0.0]
    assert len(table[flat[0]]) == 400 > len(set(table[flat[0]].tolist()))
    value = float(f[table[flat[0]][0]])
    assert value > 0.0 and dm.DEFAULT_RESAMPLES == 300
    assert doc == {"refusal": {"code": "degenerate_resample", "reason": (
        f"the margin is identical on all 400 draws of bootstrap resample {flat[0] + 1} "
        f"of 300 (${value:,.2f})")}}
    assert "refusal" not in runs["rare2"].block and runs["rare2"].block["paths"] == 2000


def _inserted(plain, text):
    """`(at, lines)`: `text` is the output `plain` with `lines` put in before
    its line `at` and nothing else changed. They start with a blank line and
    the block's first line."""
    base, lines = plain.split("\n"), text.split("\n")
    head = next(i for i, line in enumerate(lines) if line.startswith("which risk decides it"))
    at, size = head - 1, len(lines) - len(base)
    assert size >= 2 and lines[at] == "", lines[at:head + 1]
    assert lines[:at] + lines[at + size:] == base
    return at, lines[at:at + size]


def _above_the_read_back(plain, at):
    """Where the run prints a `READ-BACK` block, `at` is above it, so the
    block still prints last."""
    from hde.serialization import READ_BACK_HEADER
    base = plain.split("\n")
    return READ_BACK_HEADER not in base or at <= base.index(READ_BACK_HEADER)


@claims("Nothing else the run prints or returns changes")
def test_a_whole_block_refusal_leaves_every_other_line_as_the_run_prints_it(tmp_path):
    """Diffed against the run without `--decompose`, on a shipped example,
    bare and beside every flag that prints lines of its own (`-q`, `--sweep`,
    `--break-even`, `--story`, `--plots`): at one future the block refuses,
    and the output is the run's own, stdout and stderr, with a blank line and
    the refusal line put in, exit 0; at 40 futures the block prints, put in at
    the same line; and both sit above the `READ-BACK` block where one prints.
    Under `--json`, bare and beside `--sweep`, the document is the run's own
    with `decomposition` added. The same holds of a refusal decided by the
    re-draws and of one a check that cannot pass returns. Beside a `--sweep`
    the run cannot parse, the run prints nothing on stdout and exits 1 with or
    without the flag.
    *Kills it:* a refusal that stops the report, exits non-zero or drops a
    key of the document; a refusal line printed anywhere the block is not
    (below the sweep's table, the break-even's line or the story's lines, or
    below the `READ-BACK` block); or any other line moved or changed."""
    story, plots = tmp_path / "story", tmp_path / "plots"
    sweep = ("--sweep", "house.mortgage_rate=0.05,0.06")
    too_few = ("which risk decides it — not split (too_few_futures): 1 future was asked "
               "for, below the minimum of 40")
    for flags in ((), ("-q",), sweep, ("-q", *sweep), ("--break-even", "house.mortgage_rate"),
                  ("--story", story), ("--plots", plots)):
        plain = _cli(MORTGAGE, *flags)
        refused = _cli(MORTGAGE, "--decompose=1", *flags)
        printed = _cli(MORTGAGE, "--decompose=40", *flags)
        assert plain[0] == refused[0] == printed[0] == 0, flags
        assert plain[2] == refused[2] == printed[2], flags
        at, lines = _inserted(plain[1], refused[1])
        assert lines == ["", too_few], flags
        block_at, block = _inserted(plain[1], printed[1])
        assert block[1].startswith("which risk decides it — 40 futures, "), flags
        assert block_at == at and _above_the_read_back(plain[1], at), flags
    for flags in ((), sweep):
        bare = _strict(_cli(MORTGAGE, "--json", *flags)[1])
        status, out, _ = _cli(MORTGAGE, "--decompose=1", "--json", *flags)
        doc = _strict(out)
        assert status == 0 and doc.pop("decomposition") == {"refusal": {
            "code": "too_few_futures", "reason": too_few.split(": ", 1)[1]}}
        assert doc == bare, flags
    broken = ("--sweep", "house.mortgage_rate")
    plain, refused = _cli(MORTGAGE, *broken), _cli(MORTGAGE, "--decompose=1", *broken)
    assert refused == plain and plain[0] == 1 and plain[1] == ""
    path = tmp_path / "rare2.yaml"
    path.write_text(yaml.safe_dump(RARE2, sort_keys=False), encoding="utf-8")
    for source, extra, code in ((MONTREAL, (), "no_futures"), (INCOME, (), "one_channel"),
                                (path, ("400",), "degenerate_resample")):
        status, out, _ = _cli(source, "--decompose", *extra, "--json")
        doc = _strict(out)
        refusal = doc.pop("decomposition")["refusal"]
        assert status == 0 and refusal["code"] == code
        assert doc == _strict(_cli(source, "--json")[1])
        for flags in ((), ("-q",)):
            plain = _cli(source, *flags)
            refused = _cli(source, "--decompose", *extra, *flags)
            assert plain[0] == refused[0] == 0 and plain[2] == refused[2], (code, flags)
            at, lines = _inserted(plain[1], refused[1])
            assert lines == ["", f"which risk decides it — not split ({code}): "
                                 f"{refusal['reason']}"], (code, flags)
            assert _above_the_read_back(plain[1], at), (code, flags)


def test_an_exception_that_is_no_check_reaches_the_caller(monkeypatch):
    """Only a check that cannot pass is a refusal (§0.1 item 58). An engine
    defect inside the block — a KeyError, or a ValueError or a TypeError no
    check raised — reaches the caller as itself, never as a refusal and never
    as a message that a check failed.
    *Kills it:* the CLI or the assembler catching more than the check's own
    exception, or the reversal register catching more than a crossing
    check's."""
    for error in (KeyError("a defect"), ValueError("a defect"), TypeError("a defect")):
        def broken(*args, **kwargs):
            raise error
        with monkeypatch.context() as patched:
            patched.setattr(dr, "_top_row", broken)
            with pytest.raises(type(error)):
                _cli(FIXTURE, "--decompose=40", "--json")
        with monkeypatch.context() as patched:
            patched.setattr(be, "_percent_value", broken)
            with pytest.raises(type(error)):
                _cli(MORTGAGE, "--decompose=200", "--json")


@claims("They are checked in this order, and the first that fires is the one returned")
def test_the_refusal_order(tmp_path, monkeypatch):
    """Each pair: a config on which BOTH conditions hold, and the earlier code
    wins. The ones decided before pricing come first; an identical margin is
    known once the futures are priced, before the count of drawing streams is
    gated; the channel refusals once the re-draws are priced.
    *Kills it:* reordering any two checks."""
    pairs = [
        (CONDO_ONLY, ("--no-monte-carlo",), "no_futures"),   # and one option
        (CONDO_ONLY, (), "single_option"),                   # and one live channel
        (_load(INCOME), ("39",), "too_few_futures"),         # and one live channel
        (TWINS, ("39",), "too_few_futures"),                 # and an identical margin
        (TWINS, ("250001",), "budget"),                      # and an identical margin
    ]
    for raw, extra, code in pairs:
        doc, _, _, _ = _refusal(tmp_path, raw, *extra)
        assert doc["refusal"]["code"] == code, (code, extra)
    doc, _, _, _ = _refusal(tmp_path, TWINS)
    assert doc["refusal"]["code"] == "no_spread"
    # With the ceiling lowered under their work, an identical margin still
    # refuses as `no_spread`, and one live channel as `budget` — the gate on
    # the count comes between them.
    monkeypatch.setattr(dr, "EVALUATION_CEILING", 100)
    spec = load_config_dict(TWINS)
    det, mc = compute_deterministic_and_mc(spec)
    verdict = _verdict(spec, det, mc)
    got = dr.decompose(spec, det=det, mc=mc, verdict=verdict, raw=TWINS, paths=64)
    assert got.code == "no_spread"
    spec = load_config_dict(_load(INCOME))
    det, mc = compute_deterministic_and_mc(spec)
    got = dr.decompose(spec, det=det, mc=mc, verdict=_verdict(spec, det, mc),
                       raw=_load(INCOME), paths=40)
    assert got.code == "budget"
    monkeypatch.undo()
    got = dr.decompose(spec, det=det, mc=mc, verdict=_verdict(spec, det, mc),
                       raw=_load(INCOME), paths=40)
    assert got.code == "one_channel"
    # The checks on the way, each forced beside a code that holds too: an
    # identical margin before the income stream's move, that move before one
    # live channel, one live channel before the widths are read, the widths
    # before the bootstrap, and the bootstrap before the level's identity.
    from tests.test_decomposition_run import TestTheFreezeIdentity
    assert _refusal(tmp_path, INCOME_ONE_CHANNEL, "400")[0]["refusal"]["code"] == \
        "one_channel"
    with monkeypatch.context() as patched:
        force_income_move(patched, 1000.0)
        doc, _, _, _ = _refusal(tmp_path, INCOME_ONLY)
        assert doc["refusal"]["code"] == "no_spread"
        doc, _, _, _ = _refusal(tmp_path, INCOME_ONE_CHANNEL, "400")
        assert doc["refusal"]["code"] == "income_moved"
    with monkeypatch.context() as patched:
        untag(patched)
        doc, _, _, _ = _refusal(tmp_path, _load(INCOME))
        assert doc["refusal"]["code"] == "one_channel"
        doc, _, _, _ = _refusal(tmp_path, RARE2, "400")
        assert doc["refusal"]["code"] == "untagged_width"
    with monkeypatch.context() as patched:
        TestTheFreezeIdentity._leaky_mask(patched, escaped=dc.channel_by_key("shelter").id)
        doc, _, _, _ = _refusal(tmp_path, RARE2, "400")
        assert doc["refusal"]["code"] == "degenerate_resample"


def compute_deterministic_and_mc(spec):
    from hde.deterministic import compute_deterministic
    return compute_deterministic(spec), run_monte_carlo(spec)


def _verdict(spec, det, mc):
    from hde.models import compute_verdict
    return compute_verdict(det, mc, years=spec.simulation.years,
                           discount_rate=spec.simulation.discount_rate,
                           single_path=single_path_run(spec))


# ---------------------------------------------------------------------------
# Live channels and the block's own keys
# ---------------------------------------------------------------------------

def _option_pvs(spec, swap=None):
    mc = dr._run(spec, dr.MATRIX_A, swap or {})
    return {o: np.asarray(getattr(mc, o).pvs) for o in ("condo", "house", "rent")
            if getattr(mc, o) is not None}


# A lease reset so rare that forty futures can hold none of it, in `A` or in
# `B`, while two thousand hold some: the tenancy is live on the larger sample
# and not on the smaller.
RARE_RESET = {
    "years": 10, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.01, "reset_hazard": 0.0005,
             "reset_to_monthly_rent": 2500, "invested_down_payment": 355200,
             "investment_return_rate": 0.03},
    "simulation": {"num_sims": 2000, "random_seed": 42, "condo_fee_vol": 0.05},
}


@claims("**Draws and live channels, measured on the block's own futures.**",
        "A stream draws when its generator advances",
        "Every stream that draws is re-drawn alone on the same futures",
        "`live_channel_ids` are the live channels, in id order.",
        "Both facts are measured on these futures and on no others",
        "A channel can be live while every option it moves stays out of")
def test_draws_and_live_channels_are_measured(runs, tmp_path):
    """On `three`, against instruments that are not the engine's measurement:
    the streams that draw are the ones whose held generators advance (the live
    channels and the `dead_draw` rows' streams); a live channel's re-seeding
    and its freeze each move a present value past the identity's budget, and
    the one drawing stream that is not live moves nothing past it. On a rare
    reset the tenancy is live on 2,000 futures and not on 40. On THIRD_FAR two
    channels move rent, never the cheapest other option, and the margin is one
    figure on every future."""
    assert [c.key for c in dc.CHANNELS] == ["economy", "market", "population", "condo",
                                            "house", "shelter", "portfolio"]
    assert dc.INCOME_STREAM_ID == 7
    run = runs["three"]
    block = run.block
    live = block["live_channel_ids"]
    assert live == sorted(live)
    dead = [z for z in block["spread"]["structural_zeros"] if z["kind"] == "dead_draw"]
    assert set(live) | {z["channel_id"] for z in dead} == oracle_drawn(run.spec)
    limit = threshold(run.spec)
    assert all(z["move_threshold"] == limit for z in dead)
    det, _, verdict = run.inputs()
    assert limit == dr.identity_budget(det, verdict)
    moves = oracle_moves(run.spec, block["paths"])
    frozen = freeze_moves(run.spec, block["paths"])
    for channel in live:
        assert moves[channel] > limit and frozen[channel] > limit, channel
    for zero in dead:
        assert moves[zero["channel_id"]] <= limit, zero
    small, large = (dr.measure_channels(load_config_dict(RARE_RESET), det=d, verdict=v,
                                        paths=n)
                    for d, v, n in [(*_det_verdict(RARE_RESET), 40),
                                    (*_det_verdict(RARE_RESET), 2000)])
    assert 5 in small.drawn and 5 in large.drawn
    assert small.live == (3,) and large.live == (3, 5)
    far = load_config_dict(THIRD_FAR)
    doc, _, _, full = _refusal(tmp_path, THIRD_FAR)
    assert doc["refusal"]["code"] == "no_spread"
    spec = dr._spec_at(far, 200)
    base = _option_pvs(spec)
    best = full["verdict"]["best"]
    for channel in (5, 6):
        swapped = _option_pvs(spec, {channel: dr.MATRIX_B})
        assert not np.array_equal(base["rent"], swapped["rent"])
        assert np.array_equal(dr.margin_per_path(dr._run(spec, dr.MATRIX_A), best),
                              dr.margin_per_path(dr._run(spec, dr.MATRIX_A,
                                                         {channel: dr.MATRIX_B}), best))


def _det_verdict(raw):
    from hde.deterministic import compute_deterministic
    from hde.models import compute_verdict
    spec = load_config_dict(copy.deepcopy(raw))
    det = compute_deterministic(spec)
    return det, compute_verdict(det, years=spec.simulation.years,
                                discount_rate=spec.simulation.discount_rate)


@claims("**The block** carries",
        "The verdict is not copied in")
def test_the_block_keys(runs):
    """The block's keys on every run, and the output table's row for the key,
    which names the same three registers."""
    for run in runs.values():
        assert set(run.block) == {"paths", "max_paths", "live_channel_ids", "mean_margin",
                                  "sd_margin", "spread", "level", "reversal"}
        assert "verdict" not in json.dumps(list(run.block))
    (row,) = [line for line in CONTRACT.read_text(encoding="utf-8").splitlines()
              if line.startswith("| `decomposition` |")]
    assert "the spread, level and reversal registers together, or a named refusal" in row


@claims("`paths` is `N`.",
        "`max_paths` is the largest `N` the budget admits")
def test_paths_and_max_paths(runs):
    """`max_paths` at the count of streams that drew: the live channels and the
    `dead_draw` rows' streams, which is the held-generator instrument's count."""
    for name, run in runs.items():
        dead = [z for z in run.block["spread"]["structural_zeros"]
                if z["kind"] == "dead_draw"]
        k = len(run.block["live_channel_ids"]) + len(dead)
        assert k == len(oracle_drawn(run.spec)), name
        assert run.block["max_paths"] == dr.largest_affordable_paths(k)
        assert run.block["paths"] <= run.block["max_paths"]
        assert run.f_a().size == run.block["paths"]
        if run.extra:
            assert run.block["paths"] == int(run.extra[0]), name


@claims("`f` is the decision margin on each future:",
        "`f > 0` on a future is `verdict.best` cheapest there.",
        "`mean_margin` and `sd_margin` are the mean and population standard deviation",
        "Those futures are drawn from the run's seed but are not the run's Monte Carlo")
def test_the_margin_and_its_sample(runs):
    run = runs["fixture"]
    f = run.f_a()
    assert run.block["mean_margin"] == pytest.approx(float(np.mean(f)), abs=1e-6)
    assert run.block["sd_margin"] == pytest.approx(float(np.std(f)), abs=1e-6)
    # f is the cheapest other option's PV minus the winner's, per future
    spec = dr._spec_at(run.spec, run.paths())
    pvs = _option_pvs(spec)
    best = run.doc["verdict"]["best"]
    others = [pvs[o] for o in pvs if o != best]
    assert np.array_equal(f, np.min(others, axis=0) - pvs[best])
    # f > 0 exactly where the winner is the cheapest option
    names = list(pvs)
    cheapest = np.array(names)[np.argmin(np.stack([pvs[o] for o in names]), axis=0)]
    assert np.array_equal(f > 0, cheapest == best)
    assert 0 < np.mean(f > 0) < 1
    # ...and the run's own Monte Carlo sample is another sample
    legacy = dr.margin_per_path(run_monte_carlo(dr._spec_at(run.spec, run.paths())), best)
    assert not np.array_equal(legacy, f)


# ---------------------------------------------------------------------------
# spread
# ---------------------------------------------------------------------------

SPREAD_KEYS = {"rows", "interaction", "leading_channel_id", "unresolved_top_channel_id",
               "interaction_channel_ids", "structural_zeros"}


@claims("`spread` — how the variance of `f` splits across the live channels.",
        "It carries `rows`, `interaction`, `leading_channel_id`",
        "When `f > 0` on every one of the block's futures, or")
def test_the_spread_keys_and_its_refusal(runs):
    for name in ("fixture", "showcase", "min", "advanced", "three"):
        assert set(runs[name].block["spread"]) == SPREAD_KEYS, name
    for name, side in (("mortgage", 1.0), ("all_other", 0.0)):
        run = runs[name]
        f = run.f_a()
        assert float(np.mean(f > 0.0)) == side, name
        assert run.block["level"]["rows"]
        assert set(run.block["reversal"]) == {"exact", "estimated", "refused",
                                              "structural_zeros", "no_distance_code",
                                              "no_distance_reason"}
        best = run.doc["verdict"]["best"]
        reason = (f"{best} is cheapest in all {run.paths():,} of these futures" if side
                  else f"{best} is cheapest in none of these {run.paths():,} futures")
        assert run.block["spread"] == {
            "refusal": {"code": "no_sign_variation", "reason": reason},
            "structural_zeros": run.block["spread"]["structural_zeros"]}
        assert all(z["kind"] == "dead_draw" and z["measured_paths"] == run.paths()
                   for z in run.block["spread"]["structural_zeros"])


@claims("`label`, `resolved`, `flip`, `flip_ci`, `widths`",
        "(`resolved: false`), never both.")
def test_a_row_carries_one_set_of_share_keys(runs):
    for run in runs.values():
        rows = run.block["spread"].get("rows")
        if rows is not None:
            assert sorted(row["channel_id"] for row in rows) == run.block["live_channel_ids"]
    for name in ("fixture", "showcase", "three", "min"):
        for row in _rows(runs[name].block):
            base = {"channel_id", "channel", "label", "resolved", "flip", "flip_ci",
                    "widths", "interaction_gap", "interaction_gap_ci"}
            shares = {"alone", "alone_ci", "with_interaction", "with_interaction_ci"}
            if row["resolved"]:
                assert set(row) == base | shares
            else:
                assert set(row) == base | {f"provisional_{k}" for k in shares}


@claims("`alone` is the channel's first-order Sobol index",
        "`with_interaction` is its total index",
        "Neither is how often the channel changes the answer.",
        "`flip` is a fraction of futures, not a share",
        "`interaction_gap` is `with_interaction − alone` on that row, before rounding.",
        "A key ending in `_ci` is the interval on the figure its name begins with.",
        "Every interval is an object with `low` and `high`: a 95% percentile")
def test_the_row_figures_are_the_named_estimators_on_the_blocks_own_matrices(runs):
    run = runs["fixture"]
    f_a, f_b, f_ab, live = _spread_tables(run)
    seed = int(run.spec.simulation.random_seed)
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total = dm.total_order_indices(f_a, f_ab)
    flip = np.mean(np.sign(f_ab) != np.sign(f_a), axis=1)
    first_ci, total_ci, flip_ci, _ = dm.bootstrap_spread_intervals(f_a, f_b, f_ab, seed=seed)
    gap_ci = dm.bootstrap_interaction_gap_intervals(f_a, f_b, f_ab, seed=seed)
    rows = {row["channel_id"]: row for row in _rows(run.block)}
    assert list(rows) == list(live)
    for position, channel in enumerate(live):
        row = rows[channel]
        prefix = "" if row["resolved"] else "provisional_"
        assert row[f"{prefix}alone"] == first[position]
        assert row[f"{prefix}with_interaction"] == total[position]
        assert row["flip"] == flip[position]
        assert row["interaction_gap"] == pytest.approx(
            row[f"{prefix}with_interaction"] - row[f"{prefix}alone"], abs=1e-12)
        for key, ci in ((f"{prefix}alone_ci", first_ci), (f"{prefix}with_interaction_ci", total_ci),
                        ("flip_ci", flip_ci), ("interaction_gap_ci", gap_ci)):
            assert (row[key]["low"], row[key]["high"]) == tuple(ci[position]), key
    # the share and the flip are different quantities on the same row
    assert any(abs(_point(r) - r["flip"]) > 0.1 for r in rows.values())
    # 300 resamples, 95%: the bounds are the 2.5th and 97.5th percentiles
    table = dm.bootstrap_path_indices(f_a.size, 300, seed)
    assert table.shape == (300, f_a.size)


@claims("never clamped into [0, 1].",
        "A row is `resolved: false` when either share's point estimate lies outside",
        "its interval does not decide it, so a resolved share's interval may")
def test_the_resolution_rule_is_the_point_rule(runs):
    """Either share outside [0, 1] leaves the row unresolved. The
    with-interaction half is witnessed on its own: the condo's alone share
    inside [0, 1] beside a share with interaction above 1, where the row
    prints both figures behind the words and, being the top row, names no
    largest share.
    *Kills it:* a row resolved on its alone share only, or on either share."""
    seen_negative_resolved = False
    for name in ("fixture", "showcase", "three", "min", "advanced", "together_above_one"):
        for row in _rows(runs[name].block):
            inside = 0.0 <= _point(row) <= 1.0 and 0.0 <= _together(row) <= 1.0
            assert row["resolved"] == inside, (name, row["channel"])
            ci = row["alone_ci"] if row["resolved"] else row["provisional_alone_ci"]
            seen_negative_resolved |= row["resolved"] and ci["low"] < 0
    assert seen_negative_resolved      # an unclamped interval below 0 on a resolved row
    run = runs["together_above_one"]
    (condo,) = [row for row in _rows(run.block) if row["channel"] == "condo"]
    assert 0.0 <= _point(condo) <= 1.0 < _together(condo)
    assert any(row["resolved"] for row in _rows(run.block))
    assert run.block["spread"]["unresolved_top_channel_id"] == condo["channel_id"]
    line = _table_line(run.text, "  THE SPREAD", condo["channel_id"])
    assert re.fullmatch(rf"  {re.escape(condo['label'])} +not resolved: 0\.99 \[[^]]+\] +"
                        r"not resolved: 1\.02 \[[^]]+\] +[\d.]+% \[[^]]+\]", line), line
    assert "largest alone share" not in run.text


@claims("The TOP ROW is the row with the largest `alone` point estimate",
        "It is `leading_channel_id` when it resolved")
def test_the_spread_top_row(runs):
    for name in ("fixture", "showcase", "three", "min", "advanced"):
        spread = runs[name].block["spread"]
        top = max(spread["rows"], key=_point)
        want = (top["channel_id"], None) if top["resolved"] else (None, top["channel_id"])
        assert (spread["leading_channel_id"], spread["unresolved_top_channel_id"]) == want


_NOTE = re.compile(r"pulled by (?P<key>simulation\.corr_inflation_\w+) = (?P<rho>[\d.]+); "
                   r"rho squared (?P<sq>[\d.]+)")


@claims("`widths[]`: `key`, `formatted`, `source`",
        "On the economy row a `note` names the correlation key")
def test_the_widths_whose_they_are_and_what_rho_squared_is(runs):
    """Each width's class is the read-back's; the economy row's notes carry
    the config's own rho and its square; and rho squared IS the fraction of
    the shock's variance the economy's draw supplies, measured on the engine's
    own correlated draw (`monte_carlo._correlated_z`)."""
    notes = 0
    for name in ("fixture", "advanced", "showcase"):
        run = runs[name]
        for row in run.block["spread"]["rows"]:
            for width in row["widths"]:
                assert set(width) == {"key", "formatted", "source", "anchor", "note", "tag"}
                assert width["source"] in ("user", "assistant", "anchor", "unattributed")
                assert run.spec.sources.classify(width["key"]) == width["source"]
                assert width["key"] not in run.spec.defaults_applied
                if row["channel"] == "economy" and width["note"]:
                    match = _NOTE.fullmatch(width["note"])
                    assert match, width["note"]
                    rho = float(match["rho"])
                    assert getattr(run.spec.simulation,
                                   match["key"].split(".", 1)[1]) == rho
                    assert match["sq"] == f"{rho * rho:g}"
                    notes += 1
    assert notes
    rng = np.random.default_rng(11)
    for rho in (0.5, 0.3):
        base = rng.normal(size=100_000)
        z = np.array([monte_carlo._correlated_z(b, rho, rng) for b in base])
        explained = np.corrcoef(base, z)[0, 1] ** 2
        assert explained == pytest.approx(rho * rho, abs=0.01)
        assert np.var(z) == pytest.approx(1.0, abs=0.02)


def _sized_by(run, label):
    """The printed `sized by` cells under the spread row of `label`."""
    lines = run.text.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith(f"  {label} "))
    assert lines[at + 1].startswith("      sized by "), lines[at + 1]
    return lines[at + 1][len("      sized by "):].split("; ")


def _width_keys(run, channel_key):
    (row,) = [r for r in run.block["spread"]["rows"] if r["channel"] == channel_key]
    return [w["key"] for w in row["widths"]]


# The oracle's own account of which options a sizing key's draws belong to,
# written from the simulator's draw sites (`monte_carlo`), never read off the
# engine: a cost or return channel's keys are its option's, and the population
# prior's rows are handed to the condo's and the house's simulations only; on
# the economy's and the market's rows an option's own section is that
# option's, and these `simulation.*` keys are the options named. Any other key
# sizes a draw every option's simulation reads.
_ORACLE_CHANNEL_OPTIONS = {2: {"condo", "house"}, 3: {"condo"}, 4: {"house"},
                           5: {"rent"}, 6: {"rent"}}
_ORACLE_KEY_OPTIONS = {
    "simulation.corr_inflation_condo": {"condo"},
    "simulation.corr_inflation_house": {"house"},
    "simulation.condo_fee_vol": {"condo"},
    "simulation.house_maintenance_vol": {"house"},
    "simulation.value_growth_vol": {"condo", "house"},
}
# Each economy correlation and the keys of the shocks `_correlated_z` composes
# it into, at the draw sites.
_ORACLE_PULLS = {
    "simulation.corr_inflation_condo": ("simulation.condo_fee_vol",),
    "simulation.corr_inflation_house": ("simulation.house_maintenance_vol",),
    "simulation.corr_inflation_other": ("simulation.other_cost_vol",),
    "simulation.corr_inflation_event_cost": ("condo.events", "house.events", "rent.events"),
}


def _oracle_options(channel_id, key):
    if channel_id in _ORACLE_CHANNEL_OPTIONS:
        return _ORACLE_CHANNEL_OPTIONS[channel_id]
    section = key.split(".", 1)[0]
    if section in ("condo", "house", "rent"):
        return {section}
    return _ORACLE_KEY_OPTIONS.get(key)


def _given_by_the_read_back(doc):
    """Every key given on the run: each key the source echo lists, and each
    key the run defaulted."""
    echo = doc["assumptions"]["sources"]
    given = {e["key"] for source in ("user", "assistant", "unattributed", "sweep")
             for e in echo.get(source) or ()}
    given |= set(echo.get("anchor") or {})
    given |= {e["key"] for e in doc["assumptions"]["defaults_applied"]}
    return given


def _expected_widths(doc, raw, channel_id):
    """`[(key, pulled by)]` a row names, by §0.1 item 53's rule, from the
    read-back and `CHANNELS` alone."""
    priced = {o for o in ("condo", "house", "rent") if o in raw}
    given = _given_by_the_read_back(doc)

    def member(key):
        options = _oracle_options(channel_id, key)
        return key in given and (options is None or bool(options & priced))

    out = [(key, None) for key in dc.channel(channel_id).sizing_keys if member(key)]
    for key, _ in list(out):
        out.extend((pulled, key) for pulled in _ORACLE_PULLS.get(key, ()) if member(pulled))
    return out


def _pulled_by(width):
    match = re.match(r"pulled by (?P<key>[\w.]+) = ", width["note"] or "")
    return None if match is None else match["key"]


def _read_back_figure(doc, key):
    """The figure the source lines print for `key` (`assumptions.lines`):
    `key=<figure>` on the source or defaults line that lists it, or the echo's
    own figure where no `sources:` block lets a line list it."""
    for line in doc["assumptions"]["lines"]:
        line = line.strip()
        label, _, rest = line.partition(": ")
        if label in ("user-stated", "assistant-typed", "unattributed", "anchor-sourced",
                     "defaults applied", "swept"):
            m = re.search(rf"(?:^|, ){re.escape(key)}=(?P<figure>.+?)(?: \[[^\]]+\])?"
                          rf"(?=, [\w.]+=|$)", rest)
            if m:
                return m["figure"]
    echo = doc["assumptions"]["sources"]
    for entry in echo.get("unattributed") or ():
        if entry["key"] == key and not echo["declared"]:
            return entry["formatted"]
    return None


def _read_back_anchor(doc, width):
    """The registry entry the read-back says a width's figure came from: the
    one an `anchor` source names, the one a default was read from, or none."""
    if width["source"] == "anchor":
        return doc["assumptions"]["sources"]["anchor"][width["key"]]
    if width["source"] == "default":
        (entry,) = [e for e in doc["assumptions"]["defaults_applied"]
                    if e["key"] == width["key"]]
        return entry["anchor"]["name"] if entry["anchor"] else None
    return None


def _printed_widths(text, label):
    """The `sized by` line printed under the spread row of `label`, whole."""
    lines = text.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith(f"  {label} "))
    assert lines[at + 1].startswith("      sized by "), lines[at + 1]
    return lines[at + 1][len("      sized by "):]


def _assert_widths_enumerated(name, doc, raw, text):
    """Every width on every row of one run, and every dead row's keys,
    against `CHANNELS`, the read-back and the oracle's option map: the same
    keys in the same order, set equality both ways, and for each the
    read-back's own tag and figure, character for character; `note` only
    where a correlation pulls the width; and the line the text prints under
    the row is each width's `<key>=<formatted> [<tag>]`, its note after it."""
    block = doc["decomposition"]
    if "refusal" in block:
        return 0
    seen = 0
    for row in block["spread"].get("rows", ()):
        want = _expected_widths(doc, raw, row["channel_id"])
        got = [(w["key"], _pulled_by(w)) for w in row["widths"]]
        assert got == want, (name, row["channel"], got, want)
        assert [w["note"] is None for w in row["widths"]] == \
            [pulled is None for _, pulled in want], (name, row["channel"])
        assert _printed_widths(text, row["label"]) == "; ".join(
            f"{w['key']}={w['formatted']} [{w['tag']}]"
            + ("" if w["note"] is None else f" ({w['note']})")
            for w in row["widths"]), (name, row["channel"])
        for width in row["widths"]:
            tag = sentences._read_back_tag(doc, width["key"])
            # a key in the set with no read-back tag fails here, never silently
            assert tag is not None, (name, width["key"])
            assert width["tag"] == tag, (name, width)
            assert width["formatted"] == _read_back_figure(doc, width["key"]), (name, width)
            assert width["anchor"] == _read_back_anchor(doc, width), (name, width)
            seen += 1
    for zero in block["spread"]["structural_zeros"]:
        if zero["channel_id"] == dc.INCOME_STREAM_ID:
            want = [k for k in ("income.pay_drop_events",) if k in _given_by_the_read_back(doc)]
        else:
            want = [key for key, _ in _expected_widths(doc, raw, zero["channel_id"])]
        assert list(zero["keys"]) == want, (name, zero)
    return seen


# Configs whose widths are pinned as the block prints them (§0.1 item 53's
# witnesses): each input sizes a draw that never fires on its run, or sizes one
# only for an option the run does not price.
_WIDTH_WITNESSES = {
    "ev_late_start": (EV_LATE_START, {
        "the condo's costs": "simulation.condo_fee_vol=10.0% [unattributed]; condo.events=1 "
                             "entry [unattributed]",
        "the economy": "economic.inflation_vol=2.0% [unattributed]; "
                       "simulation.corr_inflation_event_cost=0.5 [unattributed]; "
                       "condo.events=1 entry [unattributed] (pulled by "
                       "simulation.corr_inflation_event_cost = 0.5; rho squared 0.25)"}),
    "lines_condo_only": (LINES_CONDO_ONLY, {
        "the condo's costs": "simulation.condo_fee_vol=10.0% [unattributed]; "
                             "simulation.other_cost_vol=10.0% [unattributed]",
        "the house's costs": "simulation.house_maintenance_vol=30.0% [unattributed]; "
                             "simulation.other_cost_vol=10.0% [unattributed]"}),
    "lines_condo_no_house": (LINES_CONDO_NO_HOUSE, {
        "the condo's costs": "simulation.condo_fee_vol=10.0% [unattributed]; "
                             "simulation.other_cost_vol=10.0% [unattributed]; "
                             "condo.events=0 entries [unattributed]",
        "the renter's portfolio": "simulation.investment_return_vol=5.0% [unattributed]"}),
    "hazard_zero": (HAZARD_ZERO, {
        "the housing market": "simulation.value_growth_vol=5.0% [assistant]; "
                              "condo.price_shock.annual_hazard=0.0% [assistant]; "
                              "condo.price_shock.severity_mean=25.0% [TREB 1989–96]; "
                              "condo.price_shock.severity_vol=10.0% [TREB 1989–96 "
                              "(calibrated)]"}),
    "reset_zero": (RESET_ZERO, {
        "your tenancy": "simulation.rent_escalation_vol=3.0% [unattributed]; rent.events=1 "
                        "entry [assistant]; rent.reset_hazard=0.0% [unattributed]"}),
    "value_vol_zero": (VALUE_VOL_ZERO, {
        "the housing market": "simulation.value_growth_vol=0.0% [unattributed]; "
                              "condo.price_shock.annual_hazard=5.0% [assistant]; "
                              "condo.price_shock.severity_mean=25.0% [TREB 1989–96]; "
                              "condo.price_shock.severity_vol=10.0% [TREB 1989–96 "
                              "(calibrated)]"}),
    "m28": (CORRELATION_UNPRICED_CONDO, {
        "the economy": "economic.inflation_vol=2.0% [unattributed]; "
                       "simulation.corr_inflation_house=0.5 [unattributed]; "
                       "simulation.house_maintenance_vol=20.0% [unattributed] (pulled by "
                       "simulation.corr_inflation_house = 0.5; rho squared 0.25)"}),
    "hazard_only": (HAZARD_ONLY, {
        "the housing market": "condo.price_shock.annual_hazard=5.0% [assistant]; "
                              "condo.price_shock.severity_mean=25.0% [TREB 1989–96]; "
                              "condo.price_shock.severity_vol=10.0% [TREB 1989–96 "
                              "(calibrated)]"}),
    "both_shocks_defaulted": (BOTH_SHOCKS_DEFAULTED, {}),
    "unpriced_condo_zero_rho": (UNPRICED_CONDO_ZERO_RHO, {
        "the housing market": "simulation.value_growth_vol=5.0% [unattributed]"}),
    "unpriced_house": (CORRELATION_UNPRICED_HOUSE, {}),
    "pull_nothing": (CORRELATIONS_PULL_NOTHING, {}),
    "renter_line": (RENTER_LINE_DRAWN, {}),
    "owned_line": (OWNED_LINE, {}),
    "owned_event": (OWNED_EVENT, {}),
    "prior_no_rent": (PRIOR_NO_RENT, {
        "the population": "market_scenario.path='tests/fixtures/scenario_prior_golden.json' "
                          "[assistant]; market_scenario.geography='MTL_RMR' [user]"}),
    "prior_no_condo": (PRIOR_NO_CONDO, {
        "the population": "market_scenario.path='tests/fixtures/scenario_prior_golden.json' "
                          "[assistant]; market_scenario.geography='MTL_RMR' [user]"}),
    "prior_no_house": (PRIOR_NO_HOUSE, {
        "the population": "market_scenario.path='tests/fixtures/scenario_prior_golden.json' "
                          "[assistant]; market_scenario.geography='MTL_RMR' [user]"}),
}


@claims("A width is a sizing input of the row's channel's draws",
        "Whether its draw fires on the run is not asked",
        "On the economy row the row's own widths come first, then the widths of the",
        "One the config states carries its read-back class as `source`",
        "A width no correlation pulls carries `note` `null`.",
        "`tag` is the read-back's tag for the key (`serialization.read_back_tag`)")
def test_every_width_on_every_witness_row_is_a_sizing_input_the_read_back_carries(tmp_path,
                                                                                 runs):
    """§0.1 item 53, enumerated: on every row of every corpus run and every
    witness, the widths are exactly the channel's sizing keys the read-back
    carries (stated or defaulted) for an option the run prices, each
    correlation followed by the shocks it pulls; each carries the read-back's
    own tag and figure; and each dead row names the same keys. On the
    witnesses the printed line is pinned too: a hazard of zero, an event no
    future fires, and a cost volatility on an option holding no
    line print their figures, and a correlation onto an unpriced option does
    not print.
    *Kills it:* a predicate that asks whether a draw fires (the witnesses'
    lines lose a width), dropping the priced-option filter (M28 prints the
    condo's correlation), an option map that files a channel under another
    option (the condo row without a house loses its widths, the population's
    under the renter loses them with no renter priced, and the population's
    under one owned option loses them beside the other alone), a tag rebuilt from the
    class (the defaults' cites vanish), or a width left out. The order is
    pinned literally on the advanced example's economy row, where each
    correlation followed by the shocks it pulls would read otherwise, and the
    tag with no `sources:` block on the basic example, where no source line
    lists a stated key."""
    seen = 0
    for name, (raw, lines) in _WIDTH_WITNESSES.items():
        got = Run(raw, "400").materialise(tmp_path / name)
        seen += _assert_widths_enumerated(name, got.doc, got.raw, got.text)
        for label, cells in lines.items():
            assert _sized_by(got, label) == cells.split("; "), (name, label)
    assert seen
    # the witnesses are live: each prints the width a prediction dropped
    m28 = Run(CORRELATION_UNPRICED_CONDO, "400").materialise(tmp_path / "m28_again")
    assert "corr_inflation_condo" not in m28.text and "condo_fee_vol" not in m28.text
    zero = Run(UNPRICED_CONDO_ZERO_RHO, "400").materialise(tmp_path / "zero_again")
    (economy,) = [z for z in zero.block["spread"]["structural_zeros"] if z["channel_id"] == 0]
    assert economy["keys"] == ["economic.inflation_vol", "simulation.corr_inflation_house",
                               "simulation.house_maintenance_vol"]
    both = Run(BOTH_SHOCKS_DEFAULTED, "400").materialise(tmp_path / "both_again")
    defaulted = {e["key"] for e in both.doc["assumptions"]["defaults_applied"]}
    assert {f"{o}.price_shock.{s}" for o in ("condo", "house")
            for s in ("severity_mean", "severity_vol")} <= defaulted
    # the row's own widths first, then the pulled ones in their correlations' order
    assert _width_keys(runs["advanced"], "economy") == [
        "economic.inflation_vol", "simulation.corr_inflation_condo",
        "simulation.corr_inflation_house", "simulation.corr_inflation_other",
        "simulation.corr_inflation_event_cost", "simulation.condo_fee_vol",
        "simulation.house_maintenance_vol", "simulation.other_cost_vol",
        "condo.events", "house.events"]
    # with no `sources:` block every stated key is filed under `unattributed`,
    # and that is its tag, though no source line lists it
    basic = runs["basic"]
    assert "sources" not in basic.raw
    assert basic.doc["assumptions"]["sources"]["declared"] is False
    stated = [w for row in basic.block["spread"]["rows"] for w in row["widths"]
              if w["source"] != "default"]
    assert stated and {(w["source"], w["tag"]) for w in stated} == {
        ("unattributed", "unattributed")}
    assert not any(line.strip().startswith("unattributed:")
                   for line in basic.doc["assumptions"]["lines"])


@claims(_WIDTH_FIGURE)
def test_a_width_s_figure_is_its_value_as_the_source_lines_format_it(runs):
    """`formatted`, re-derived by calling the function the contract names on
    the input's value: `sources.format_source_value` on the value the config
    states, `serialization.echo_value` on the run's spec for a default.
    *Kills it:* a width's figure formatted by any other function."""
    from hde.serialization import echo_value
    from hde.sources import format_source_value, raw_value
    seen = set()
    for name, run in runs.items():
        for row in run.block["spread"].get("rows", ()):
            for width in row["widths"]:
                if width["source"] == "default":
                    want = echo_value(run.spec, width["key"])
                else:
                    want = format_source_value(width["key"], raw_value(run.raw, width["key"]))
                assert width["formatted"] == want, (name, width)
                seen.add(width["source"] == "default")
    assert seen == {True, False}


def test_the_oracle_s_option_map_is_the_simulator_s(runs):
    """`_ORACLE_CHANNEL_OPTIONS`, measured: on the fixture, which prices all
    three options and draws every channel, re-drawing each channel the map
    names, alone, moves the present values of exactly the options it names
    and leaves the others' bit for bit.
    *Kills it:* an oracle that files a channel's draws under another option,
    as the population's under the renter, which reads none of them."""
    spec = dr._spec_at(runs["fixture"].spec, 40)
    base = dr._run(spec, dr.MATRIX_A)
    for channel_id, options in _ORACLE_CHANNEL_OPTIONS.items():
        redrawn = dr._run(spec, dr.MATRIX_A, {channel_id: dr.MATRIX_B})
        moved = {name for name in ("condo", "house", "rent")
                 if np.asarray(getattr(redrawn, name).pvs).tobytes()
                 != np.asarray(getattr(base, name).pvs).tobytes()}
        assert moved == options, (channel_id, moved)


def test_every_width_on_every_corpus_row_is_a_sizing_input_the_read_back_carries(runs):
    """The same enumeration over every row of every run of the shared corpus,
    the dead rows' keys included."""
    seen = 0
    for name, run in runs.items():
        seen += _assert_widths_enumerated(name, run.doc, run.raw, run.text)
    assert seen


@claims("`interaction_channel_ids` are the rows whose `interaction_gap_ci` lies")
def test_the_interacting_rows(runs):
    seen = False
    for name in ("fixture", "showcase", "three", "min", "advanced", "advanced_4000"):
        spread = runs[name].block["spread"]
        assert spread["interaction_channel_ids"] == [
            r["channel_id"] for r in spread["rows"] if r["interaction_gap_ci"]["low"] > 0]
        seen |= bool(spread["interaction_channel_ids"])
    assert seen and not runs["fixture"].block["spread"]["interaction_channel_ids"]


@claims("`interaction`, the alone shares' sum and what it leaves",
        "`resolved` is true when that interval lies entirely below 1")
def test_the_interaction_branches(runs):
    for name in ("fixture", "showcase", "min", "advanced"):
        spread = runs[name].block["spread"]
        inter = spread["interaction"]
        assert inter["first_order_sum"] == pytest.approx(
            sum(_point(r) for r in spread["rows"]), abs=1e-12)
        resolved = inter["first_order_sum_ci"]["high"] < 1.0
        assert inter["resolved"] is resolved
        if not resolved:
            assert set(inter) == {"resolved", "first_order_sum", "first_order_sum_ci"}
            continue
        assert set(inter) == {"resolved", "first_order_sum", "first_order_sum_ci",
                              "residual", "residual_ci"}
        assert inter["residual"] == pytest.approx(1.0 - inter["first_order_sum"])
        assert inter["residual_ci"] == pytest.approx({
            "low": 1.0 - inter["first_order_sum_ci"]["high"],
            "high": 1.0 - inter["first_order_sum_ci"]["low"]})
    assert runs["min"].block["spread"]["interaction"]["resolved"] is True


# ---------------------------------------------------------------------------
# level
# ---------------------------------------------------------------------------

@claims("`level` — what the futures price that the central case does not",
        "It carries `rows`, `paths`, `prob_best_base`",
        "`prob_best_base` and `futures_margin` are the fraction",
        "`label`, `resolved`, `se`, `prob_best_frozen`, and the shift",
        "The shift is the mean over those futures",
        "A row resolves when the size of its shift exceeds twice its `se`.")
def test_the_level_register_re_derived(runs):
    run = runs["fixture"]
    level = run.block["level"]
    m = level["paths"]
    base = run.f_a()[:m]
    assert level["prob_best_base"] == float(np.mean(base > 0.0))
    assert level["futures_margin"] == pytest.approx(float(np.mean(base)), abs=1e-6)
    spec = dr._spec_at(run.spec, m)
    best = run.doc["verdict"]["best"]
    signs = set()
    for each in runs.values():
        assert sorted(row["channel_id"] for row in each.block["level"]["rows"]) == \
            each.block["live_channel_ids"]
    for row in level["rows"]:
        assert set(row) == {"channel_id", "channel", "label", "resolved", "se",
                            "prob_best_frozen", "delta" if row["resolved"] else
                            "provisional_delta"}
        frozen = dr.margin_per_path(dr._run(spec, dr.MATRIX_A, freeze=(row["channel_id"],)), best)
        diff = frozen - base
        assert _shift(row) == pytest.approx(float(np.mean(diff)), abs=1e-6)
        assert row["se"] == pytest.approx(float(np.std(diff, ddof=1) / math.sqrt(m)))
        assert row["prob_best_frozen"] == float(np.mean(frozen > 0.0))
        assert row["resolved"] == (abs(_shift(row)) > 2 * row["se"])
        signs.add(_shift(row) > 0)
    assert signs == {True, False}         # the size, not the signed shift, decides
    assert set(level) == {"rows", "paths", "prob_best_base", "futures_margin",
                          "all_frozen_margin", "all_frozen_path_spread",
                          "all_frozen_deviation", "accounted_for", "leading_channel_id",
                          "unresolved_top_channel_id"}


@claims("`all_frozen_margin` is the margin every path prices",
        "`all_frozen_path_spread` is how far those paths differ",
        "`all_frozen_deviation` is",
        "`accounted_for` is the sum of every row's shift",
        "The gap is not stored",
        "The TOP ROW is the row with the largest shift in size")
def test_the_all_frozen_identity_the_sum_and_the_top_row(runs):
    """advanced at 4,000 paths is the witness for "in size": its largest shift
    is a resolved NEGATIVE one, which a signed rule would pass over for a
    smaller positive shift."""
    for name in ("fixture", "min", "mortgage", "advanced_4000"):
        run = runs[name]
        level = run.block["level"]
        spec = dr._spec_at(run.spec, level["paths"])
        best = run.doc["verdict"]["best"]
        frozen = dr.margin_per_path(dr._run(spec, dr.MATRIX_A, freeze=dr.ALL_CHANNEL_IDS), best)
        assert level["all_frozen_margin"] == frozen[0]
        assert level["all_frozen_path_spread"] == float(np.max(np.abs(frozen - frozen[0])))
        assert level["all_frozen_deviation"] == abs(
            frozen[0] - run.doc["verdict"]["margin_pv"])
        assert level["accounted_for"] == pytest.approx(
            sum(_shift(r) for r in level["rows"]), abs=1e-6)
        assert "gap" not in json.dumps(list(level))
        top = max(level["rows"], key=lambda r: abs(_shift(r)))
        want = (top["channel_id"], None) if top["resolved"] else (None, top["channel_id"])
        assert (level["leading_channel_id"], level["unresolved_top_channel_id"]) == want
    # the witness stays one: the leader's shift is negative, and a positive
    # shift in the same register is smaller in size
    level = runs["advanced_4000"].block["level"]
    leader = next(r for r in level["rows"] if r["channel_id"] == level["leading_channel_id"])
    assert leader["resolved"] and _shift(leader) < 0 < max(_shift(r) for r in level["rows"])


# ---------------------------------------------------------------------------
# reversal
# ---------------------------------------------------------------------------

@claims("- The reversal register prices none of them.",
        "It reads the run's own Monte Carlo sample and re-simulates the config")
def test_the_reversal_register_is_break_even_s_and_nothing_added(monkeypatch, runs):
    """What makes "the reversal register prices none of them" true by
    construction: the block's `reversal` IS the object
    `break_even.reversal_register` returns, and that function is handed the
    config, the central case and the run's own Monte Carlo result — nothing
    the block's `N` sizes. Its curves carry the config's own path count and
    seed at an `N` that differs from it, and its gate probes
    `min(200, simulation.num_sims)` paths.
    *Kills it:* the assembler adding a row to the register, or handing it
    anything of the block's own futures."""
    from hde.deterministic import compute_deterministic
    from hde.models import compute_verdict
    raw = _load(FIXTURE)
    spec = load_config_dict(copy.deepcopy(raw))
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    seen = []
    real = be.reversal_register

    def spy(*args, **kwargs):
        seen.append((args, kwargs))
        seen.append(real(*args, **kwargs))
        return seen[-1]

    monkeypatch.setattr(be, "reversal_register", spy)
    got = dr.decompose(spec, det=det, mc=mc, verdict=verdict, raw=raw, paths=300)
    (args, kwargs), returned = seen
    assert got.reversal is returned
    assert kwargs == {} and len(args) == 3
    assert args[0] is raw and args[1] is det and args[2] is mc
    for name in ("fixture", "mortgage"):
        run = runs[name]
        sim = run.spec.simulation
        assert run.block["paths"] != sim.num_sims
        for row in run.block["reversal"]["exact"]:
            assert row["probe_paths"] == min(200, sim.num_sims)
            for boundary in row["boundaries"]:
                if "seed" in boundary:
                    assert (boundary["curve_paths"], boundary["seed"]) == (
                        sim.num_sims, sim.random_seed)


def _stated_reversal_keys(raw):
    """The keys the contract says are searched, read off the config: each
    option's `mortgage_rate` and `mortgage_renewal_rates` it states."""
    return [f"{option}.{leaf}" for option in ("condo", "house")
            if isinstance(raw.get(option), dict)
            for leaf in ("mortgage_renewal_rates", "mortgage_rate") if leaf in raw[option]]


def _far_end_moves(raw, key):
    """Each priced option's present value with `key` at the far end of its
    bracket minus its value as stated, priced here and not by the register;
    None where the loader refuses the far end."""
    try:
        far = compute_deterministic(be.load_at(raw, key, be.reversal_probe(raw, key)))
    except (be.ConfigValidationError, be.RateConventionError, ValueError):
        return None
    base = compute_deterministic(load_config_dict(raw))
    return {option: getattr(far, option).total_pv - getattr(base, option).total_pv
            for option in ("condo", "house", "rent") if getattr(base, option) is not None}


@claims("`reversal` — what would have to change for the verdict to change",
        "It carries `exact`, `estimated`, `refused`, `structural_zeros`,",
        "The keys searched are a financed option's `mortgage_rate` and",
        "each is the key of exactly one row of `exact`, `estimated` or `refused`",
        "A key is in `refused` when moving it to the far end of its bracket moves no",
        "The far end is `bracket_high`, or `bracket_low` where every figure the config")
def test_what_the_reversal_register_searches(runs):
    """§0.1 item 64, enumerated: on every run of the corpus that prints the
    block, each reversal key the config states is the key of exactly one
    row, in `refused` where moving it to the far end of its bracket moves no
    present value and in `exact` where it does, by less than a dollar
    included; each refused row prints its own line, in the order of
    `refused`, the inert ladder beside an admitted contract rate included.
    *Kills it:* a stated key that no crossing moves dropped from the block,
    a key filed twice, a refused row filed where the key moves a value, or
    a refused row whose line does not print."""
    fixture = runs["fixture"].block["reversal"]
    assert set(fixture) == {"exact", "estimated", "refused", "structural_zeros",
                            "no_distance_code", "no_distance_reason"}
    assert [r["key"] for r in fixture["exact"]] == ["house.mortgage_renewal_rates",
                                                    "house.mortgage_rate"]
    assert [r["key"] for r in runs["mortgage"].block["reversal"]["exact"]] == [
        "house.mortgage_rate"]
    seen = set()
    for name, run in runs.items():
        if "refusal" in run.block:
            continue
        reversal = run.block["reversal"]
        filed = [(kind, row["key"]) for kind in ("exact", "estimated", "refused")
                 for row in reversal[kind]]
        stated = _stated_reversal_keys(run.raw)
        assert sorted(key for _, key in filed) == sorted(stated), name
        for kind, key in filed:
            moves = _far_end_moves(run.raw, key)
            refused = moves is None or all(delta == 0.0 for delta in moves.values())
            assert refused == (kind == "refused"), (name, key, moves)
            seen.add(kind)
        rows = reversal["refused"] or ([] if reversal["exact"] or reversal["estimated"] else [
            {"code": reversal["no_distance_code"], "reason": reversal["no_distance_reason"]}])
        assert [line for line in run.text.splitlines()
                if line.startswith("  WHAT WOULD HAVE TO CHANGE — not solved")] == [
            f"  WHAT WOULD HAVE TO CHANGE — not solved ({row['code']}): {row['reason']}"
            for row in rows], name
    assert seen == {"exact", "refused"}
    run = runs["inert_ladder"]
    reversal = run.block["reversal"]
    assert [r["key"] for r in reversal["exact"]] == ["house.mortgage_rate"]
    (row,) = reversal["refused"]
    assert row["key"] == "house.mortgage_renewal_rates"
    assert [line for line in run.text.splitlines() if row["key"] in line] == [
        f"  WHAT WOULD HAVE TO CHANGE — not solved (not_admitted): {row['reason']}"]
    # a house bought outright: both of its keys are refused, and each prints
    run = runs["two_refused"]
    reversal = run.block["reversal"]
    assert reversal["exact"] == [] and reversal["estimated"] == []
    assert [r["key"] for r in reversal["refused"]] == ["house.mortgage_renewal_rates",
                                                       "house.mortgage_rate"]
    for row in reversal["refused"]:
        assert [line for line in run.text.splitlines() if row["key"] in line] == [
            f"  WHAT WOULD HAVE TO CHANGE — not solved (not_admitted): {row['reason']}"]
    # a loan of one dollar: the contract rate moves the house by under a dollar
    run = runs["one_dollar_loan"]
    (row,) = run.block["reversal"]["exact"]
    assert row["key"] == "house.mortgage_rate" and run.block["reversal"]["refused"] == []
    moves = _far_end_moves(run.raw, row["key"])
    assert 0.0 < abs(moves["house"]) < 1.0 and moves["rent"] == 0.0
    # stated at the high end, the key is moved to the low end, where it moves
    # the house's present value; at the high end it prices the config itself
    run = runs["stated_at_the_bracket_high_end"]
    (row,) = run.block["reversal"]["exact"]
    assert run.raw["house"]["mortgage_rate"] == row["bracket_high"]
    assert be.reversal_probe(run.raw, row["key"]) == row["bracket_low"]
    assert not reversal_admission(run.raw, row["key"], row["bracket_high"])[0]
    assert row["boundaries"]
    for name in ("advanced", "showcase", "three", "min"):
        block = runs[name].block["reversal"]
        assert block["exact"] == [] and block["estimated"] == []
        raw = runs[name].raw
        assert not any(isinstance(raw.get(o), dict) and (
            "mortgage_rate" in raw[o] or "mortgage_renewal_rates" in raw[o])
            for o in ("condo", "house"))


@claims("`refused[]` rows: `key` and `option`, as an `exact[]` row's, `code` and",
        "`code` is `not_admitted`, and `reason` is the measured fact.")
def test_a_refused_row_states_what_was_measured(runs):
    """Every refused row of the corpus: its option is its key's, its code
    `not_admitted`, and its reason the far end's measurement, re-run.
    *Kills it:* a reason naming another key or another measurement."""
    checked = 0
    for run in runs.values():
        if "refusal" in run.block:
            continue
        for row in run.block["reversal"]["refused"]:
            assert set(row) == {"key", "option", "code", "reason"}
            assert row["option"] == row["key"].split(".", 1)[0]
            assert row["code"] == "not_admitted"
            admitted, record = be.reversal_admission(run.raw, row["key"],
                                                     be.reversal_probe(run.raw, row["key"]))
            assert not admitted and record["deltas"]
            assert all(delta == 0.0 for delta in record["deltas"].values())
            assert row["reason"] == (f"this config states {row['key']}, and moving it to the "
                                     f"far end of its bracket moves no option's present value")
            checked += 1
    assert checked >= 2


@claims("`no_distance_code` and `no_distance_reason` are set exactly when `exact`,",
        "`no_distance_reason` is the measured fact, and `no_distance_code` is")
def test_the_empty_register_states_what_the_config_states(runs):
    """Every run of the corpus, both ways, and the two codes only a library
    call reaches: a block handed no config mapping, and a register on one
    option. Each code writes its own reason (§0.1 item 50).
    *Kills it:* a code on a register with rows, or one naming the other case."""
    seen = set()
    for run in runs.values():
        if "refusal" in run.block:
            continue
        reversal = run.block["reversal"]
        empty = not (reversal["exact"] or reversal["estimated"] or reversal["refused"])
        assert (reversal["no_distance_reason"] is not None) == empty
        assert (reversal["no_distance_code"] is not None) == empty
        if not empty:
            continue
        seen.add(reversal["no_distance_code"])
        assert be.reversal_candidates(run.raw) == []
        assert reversal["no_distance_code"] == "no_candidate"
        assert reversal["no_distance_reason"] == (
            "this config states no mortgage_renewal_rates or mortgage_rate")
        assert sentences._NO_DISTANCE_REASON[reversal["no_distance_code"]].fullmatch(
            reversal["no_distance_reason"])
    assert seen == {"no_candidate"}
    fixture = runs["fixture"]
    det, mc, verdict = fixture.inputs()
    bare = dr.decompose(dr._spec_at(fixture.spec, 40), det=det, mc=mc, verdict=verdict,
                        raw=None, paths=40)
    assert (bare.reversal.no_distance_code, bare.reversal.exact) == ("no_mapping", ())
    from hde.deterministic import compute_deterministic
    one = load_config_dict(CONDO_ONLY)
    lone = be.reversal_register(copy.deepcopy(CONDO_ONLY), compute_deterministic(one),
                                run_monte_carlo(one))
    assert (lone.no_distance_code, lone.no_distance_reason) == (
        "single_option", "fewer than two options are priced")


@claims("`exact[]` rows:", "`key` is the key searched and `option` the option it belongs to.",
        "A key is exact when moving it to the far end of its bracket leaves")
def test_the_exact_rows_and_their_licence(runs):
    """The row's keys, and no figure the config states for its key (§0.1 item
    67); and the exactness gate re-run.
    *Kills it:* a stated figure or a reference back on the row, or a row
    licensed by a gate that does not re-run to the same figure."""
    from hde.break_even import reversal_gate
    checked = 0
    for name, run in runs.items():
        if "refusal" in run.block:
            continue
        for row in run.block["reversal"]["exact"]:
            assert set(row) == {"key", "option", "bracket_low", "bracket_high",
                                "bracket_source", "probe_paths",
                                "max_path_deviation_over_sd", "boundaries",
                                "refused_boundaries", "path_note"}, name
            assert row["option"] == row["key"].split(".", 1)[0]
            checked += 1
    for name in ("mortgage", "stated_at_the_bracket_high_end"):
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            gate = reversal_gate(run.raw, row["key"], be.reversal_probe(run.raw, row["key"]),
                                 paths=row["probe_paths"])
            assert gate["licensed"] and gate["others_bit_identical"]
            assert gate["paths"] == row["probe_paths"]
            assert gate["worst_deviation_over_sd"] == row["max_path_deviation_over_sd"]
            assert row["max_path_deviation_over_sd"] <= REVERSAL_GATE_TOLERANCE
    assert checked


@claims("`bracket_low` and `bracket_high` bound the search")
def test_the_bracket_is_the_engines_own(runs):
    for name in ("fixture", "mortgage"):
        for row in runs[name].block["reversal"]["exact"]:
            leaf = row["key"].split(".", 1)[1]
            assert (row["bracket_low"], row["bracket_high"]) == be.RATE_BRACKETS[leaf]
            assert row["bracket_source"] == "set in the engine"


@claims("`path_note` is set when the config states the key as a path of two or more",
        "a path of one repeated rate included.")
def test_the_path_note(runs):
    """How the axis was built, checked against the axis: every crossing on the
    ladder is re-priced at its value with one rate at every renewal, and the
    note says so and names none of the path's figures (§0.1 item 67).
    *Kills it:* a figure of the path back in the note, or a note on a path
    of one repeated rate."""
    for name in ("fixture",):
        run = runs[name]
        rows = {r["key"]: r for r in run.block["reversal"]["exact"]}
        ladder = rows["house.mortgage_renewal_rates"]
        stated = run.raw["house"]["mortgage_renewal_rates"]
        assert len(set(stated)) > 1
        assert ladder["path_note"] == (
            "each crossing on this key is priced with the stated path replaced by one "
            "rate at every renewal")
        base = renewal_segments_for(load_config_dict(copy.deepcopy(run.raw)).house)
        assert len({s.rate for s in base[1:]}) > 1
        for boundary in ladder["boundaries"]:
            at = be.load_at(run.raw, ladder["key"], boundary["value"])
            renewals = renewal_segments_for(at.house)[1:]
            assert len(renewals) == len(base) - 1
            assert len({s.rate for s in renewals}) == 1
        assert rows["house.mortgage_rate"]["path_note"] is None
    flat = copy.deepcopy(runs["fixture"].raw)
    flat["house"]["mortgage_renewal_rates"] = [0.05, 0.05, 0.05]
    assert be.reversal_path_note(flat, "house.mortgage_renewal_rates") is None
    flat["house"]["mortgage_renewal_rates"] = [0.05, 0.06]
    assert be.reversal_path_note(flat, "house.mortgage_renewal_rates") is not None
    # the sweep's own note reads the same test of "a path"
    assert flattened_path_note(flat, "house.mortgage_renewal_rates") is not None


@claims("`estimated[]` rows carry the same keys without `probe_paths`.",
        "A key there failed that test, and this engine locates no boundary on it",
        "The boundary such a row is typed for")
def test_an_estimated_row_carries_no_boundary(monkeypatch):
    """Forced on a real run: with the gate's deviation held above its
    tolerance the key lands in `estimated[]` with every field refused. And no
    module outside the types and the text constructs the boundary type an
    estimated row is typed for."""
    monkeypatch.setattr(be, "_shift_deviation_over_sd", lambda before, after: 1.0)
    code, out, _ = _cli(MORTGAGE, "--decompose", "200", "--json")
    assert code == 0
    reversal = _strict(out)["decomposition"]["reversal"]
    assert reversal["exact"] == []
    (row,) = reversal["estimated"]
    exact_fields = {f.name for f in dataclasses.fields(dc.ExactReversal)}
    assert set(row) == exact_fields - {"probe_paths"}
    assert row["boundaries"] == []
    assert {r["verdict_field"] for r in row["refused_boundaries"]} == set(dc.BOUNDARY_FIELDS)
    assert {r["code"] for r in row["refused_boundaries"]} == {"not_exact"}
    assert [f.name for f in dataclasses.fields(dc.EstimatedBoundary)] == [
        "verdict_field", "value", "value_ci", "was", "becomes", "further_changes",
        "resimulation_paths"]
    for path in (REPO / "src" / "hde").glob("*.py"):
        if path.name in ("decomposition.py", "decomposition_text.py"):
            continue
        assert "EstimatedBoundary(" not in path.read_text(encoding="utf-8"), path.name


# The runs whose crossings are read against `--sweep` here: the shipped
# examples, each witness of a crossing's own figure (§0.1 items 54 and 60),
# and one whose solved brackets' ends read other states.
_CROSSING_RUNS = ("fixture", "mortgage", "decisive_step", "decisive_step_lower",
                  "crossing_below_a_step", "not_decisive_off_the_scan", "sliver_low",
                  "sliver_high", "three_way_tie")


@claims("`boundaries[]`: `verdict_field`, `value`, `upper_end`, `formatted`, `was`,",
        "`verdict_field` is the field of the verdict that changes:",
        "`value` and `upper_end` are the lower and upper ends of the bracket the boundary",
        "`was` is what the field says at `value`, and `becomes` what it says at `upper_end`.",
        "For `decisive` they read",
        "`formatted` is the boundary's figure as the text block prints it.")
def test_every_boundary_reads_upward_against_a_sweep(runs):
    """`was` at `value` and `becomes` at `upper_end`, read by `--sweep` (with
    the run's own futures for a bisected boundary), and the two ends as close
    as the contract says: adjacent floats for a solved boundary, less than
    1e-12 apart for a bisected one. No run but the tie's refuses a solved
    boundary with `not_bracketed`.
    *Kills it:* a boundary reported at a bracket's midpoint or at a solver's
    stopping tolerance, a tie counted on the wrong side of it, or the state
    past an edge read on another stretch than the next."""
    solved = sampled = 0
    for name in _CROSSING_RUNS:
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            for boundary in row["boundaries"]:
                field = boundary["verdict_field"]
                futures = field not in ("best", "runner_up")
                keys = {"verdict_field", "value", "upper_end", "formatted", "was", "becomes",
                        "further_changes", "confirming_probabilities"}
                if futures:
                    keys |= {"curve_probabilities", "curve_paths", "seed"}
                    assert 0.0 < boundary["upper_end"] - boundary["value"] < 1e-12
                    sampled += 1
                else:
                    assert boundary["upper_end"] == math.nextafter(boundary["value"], 1.0)
                    solved += 1
                assert set(boundary) == keys
                at, above = _sweep_states(run.path, row["key"],
                                          [boundary["value"], boundary["upper_end"]], futures)
                assert at[field] == boundary["was"], (name, row["key"], field)
                assert above[field] == boundary["becomes"], (name, row["key"], field)
                if field == "decisive":
                    assert re.fullmatch(r"decisive for \w+|not decisive", boundary["was"])
                assert f"as it rises past {boundary['formatted']}, " in run.text
    assert solved and sampled
    # a solved boundary whose bracket's ends read other states is refused on
    # the one run where three present values tie within a few floats, and on
    # no other run of the corpus
    assert {name for name, run in runs.items() if "refusal" not in run.block
            for row in run.block["reversal"]["exact"] for refused in row["refused_boundaries"]
            if refused["code"] == "not_bracketed"} == {"three_way_tie"}


@claims("`confirming_probabilities` is each option's probability of being cheapest",
        "A boundary is reported only where the two are equal.",
        "Each is a list of `[option, probability]` pairs.")
def test_the_confirming_and_the_curve_probabilities(runs):
    """A sampled boundary's two lists are equal pair for pair; the confirming
    one is a full re-simulation at the boundary's value."""
    sampled = []
    for name in ("fixture", "mortgage"):
        for row in runs[name].block["reversal"]["exact"]:
            for boundary in row["boundaries"]:
                for pair in boundary["confirming_probabilities"]:
                    assert isinstance(pair[0], str) and 0.0 <= pair[1] <= 1.0
                    assert len(pair) == 2
                if "seed" in boundary:
                    assert boundary["curve_probabilities"] == boundary[
                        "confirming_probabilities"]
                    sampled.append((runs[name], row, boundary))
    run, row, boundary = sampled[0]
    again = run_monte_carlo(be.load_at(run.raw, row["key"], boundary["value"]))
    assert [list(p) for p in boundary["confirming_probabilities"]] == [
        [o, getattr(again, f"prob_{o}_cheapest")] for o in ("condo", "house", "rent")
        if getattr(again, f"prob_{o}_cheapest") is not None]


@claims("Boundaries are the edges of every stretch of the bracket",
        "`best` and `runner_up` are found by scanning each",
        "A change and its reversal inside one scan step are")
def test_the_two_scans(runs, monkeypatch):
    """The solver on synthetic curves, and on the register's own call: 9
    points per pair, bisected where the gap changes sign; 65 points for the
    futures fields, each edge of a stretch bisected; a flip that starts and
    ends inside one step is not seen by either."""
    asked = []

    def gap(inside):
        def totals(v):
            asked.append(v)
            return (-1.0 if inside(v) else 1.0, 0.0)
        return totals

    none = be.solve_crossings("house.mortgage_rate", ("condo", "house"), 0.01, 0.10,
                              gap(lambda v: 0.0205 < v < 0.0206))
    assert none["break_evens"] == []
    assert asked == pytest.approx([0.01 + 0.09 * i / 8 for i in range(9)])
    asked.clear()
    one = be.solve_crossings("house.mortgage_rate", ("condo", "house"), 0.01, 0.10,
                             gap(lambda v: v > 0.05), to_adjacent_floats=True)
    assert [b["value"] for b in one["break_evens"]] == pytest.approx([0.05], abs=1e-15)

    xs = []

    def curve(inside):
        def free(x):
            xs.append(x)
            return types.SimpleNamespace(mc_best="house" if inside(x) else "condo"), {}
        return free

    stated = types.SimpleNamespace(mc_best="condo")
    found, why = be._futures_field_boundaries(
        {}, "house.mortgage_rate", "mc_best", curve(lambda x: 0.0205 < x < 0.0206),
        stated, 0.01, 0.10, scan_points=be.REVERSAL_SCAN_POINTS)
    assert found == [] and why[0] == "unchanged"
    assert why[1].startswith("mc_best says 'condo' at every one of 65 points")
    assert xs == pytest.approx([0.01 + 0.09 * i / 64 for i in range(65)])
    found, why = be._futures_field_boundaries(
        {}, "house.mortgage_rate", "mc_best", curve(lambda x: 0.0205 < x < 0.03),
        stated, 0.01, 0.10, scan_points=be.REVERSAL_SCAN_POINTS)
    assert why is None
    assert [b["value"] for b in found] == pytest.approx([0.0205, 0.03], abs=1e-9)
    import inspect
    assert inspect.signature(be.reversal_register).parameters[
        "scan_points"].default == 65

    calls = []
    real = be.solve_crossings

    def recorded(key, options, lo, hi, totals_at, **kwargs):
        seen = []
        calls.append((options, seen))

        def spy(v):
            seen.append(v)
            return totals_at(v)
        return real(key, options, lo, hi, spy, **kwargs)

    monkeypatch.setattr(be, "solve_crossings", recorded)
    raw = runs["fixture"].raw
    be.deterministic_boundaries(raw, "house.mortgage_rate", 0.01, 0.10)
    assert sorted(o for o, _ in calls) == [("condo", "house"), ("condo", "rent"),
                                           ("house", "rent")]
    for _, seen in calls:
        assert seen[:9] == pytest.approx([0.01 + 0.09 * i / 8 for i in range(9)])


def _run_says(run, row, field):
    """What `field` says at the config's own value of the row's key."""
    doc = run.doc["verdict"]
    if field == "decisive":
        return f"decisive for {doc['best']}" if doc["decisive"] else "not decisive"
    return doc[field]


@claims("`further_changes` is `\"above\"` when")
def test_further_changes_against_a_sweep_past_the_edge(runs):
    """For each boundary, sweep from the edge to where the field says what the
    run says again, or to the bracket's end, on the flagged side: more than
    one state there exactly when `further_changes` names that side."""
    checked = set()
    for name in ("fixture", "mortgage", "decisive_step", "decisive_step_lower"):
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            for boundary in row["boundaries"]:
                field = boundary["verdict_field"]
                futures = field not in ("best", "runner_up")
                upward = boundary["was"] == _run_says(run, row, field)
                side = "above" if upward else "below"
                edge = boundary["upper_end"] if upward else boundary["value"]
                end = row["bracket_high"] if upward else row["bracket_low"]
                step = 1.0 if upward else -1.0
                fine = [edge + step * d for d in (2e-4, 5e-4, 1e-3, 2e-3, 4e-3)]
                grid = [x for x in fine if min(edge, end) < x < max(edge, end)]
                grid += list(np.linspace(edge, end, 13)[1:])
                states = [s[field] for s in _sweep_states(run.path, row["key"], grid, futures)]
                says = boundary["was"] if upward else boundary["becomes"]
                stretch = []
                for state in states:
                    if state == says:
                        break
                    stretch.append(state)
                changes = len(set(stretch)) > 1
                assert (boundary["further_changes"] == side) == changes, (
                    name, row["key"], field, stretch)
                if boundary["further_changes"] is not None:
                    checked.add(boundary["further_changes"])
    assert checked == {"above", "below"}


@claims("`refused_boundaries[]`: `verdict_field`, `code` and `reason`: one for a field",
        "`reason` is the measured fact, and `code` is `unchanged` when")
def test_the_refused_fields(runs):
    """The refused entries on real rows; each code by its own witness in
    `tests/test_decomposition_refusal_codes.py`, which also checks the head
    each code prints behind. A field with one boundary printed and another
    refused says so: its refusal never says no boundary was printed for
    it."""
    renewal = hh.uncertainty_surface()
    row = renewal.reversal.exact[0]
    edge = dc.RefusedBoundary(verdict_field="mc_best", code="not_identified",
                              reason="across the bracket P(condo cheapest) moves by 0.0100, "
                                     "not more than 2 s.e. of it at the boundary (0.0400) on "
                                     "2000 paths")
    both = dataclasses.replace(row, refused_boundaries=row.refused_boundaries + (edge,))
    text = dt.format_decomposition(dataclasses.replace(
        renewal, reversal=dataclasses.replace(renewal.reversal,
                                              exact=(both,) + renewal.reversal.exact[1:])))
    lines = text.splitlines()
    assert any(line.startswith("      sampled on 2,000 paths at seed 42: as it rises past "
                               "2.71%, the option most futures call cheapest") for line in lines)
    assert ("      a boundary not printed for the option most futures call cheapest "
            f"(not_identified): {edge.reason}") in lines
    assert not any(line.startswith("      no boundary printed for the option most futures")
                   for line in lines)
    assert set(dc.EDGE_REFUSAL_CODES) < set(dc.BOUNDARY_REFUSAL_CODES)
    refused = 0
    for name in ("fixture", "mortgage"):
        for row in runs[name].block["reversal"]["exact"]:
            for item in row["refused_boundaries"]:
                assert set(item) == {"verdict_field", "code", "reason"}
                assert sentences._BOUNDARY_REASON[item["code"]].fullmatch(
                    item["reason"]), item
                refused += 1
    assert refused


@claims("`structural_zeros[]`: `kind`, `label`, `keys` and `reversal_key`, one row per")
def test_the_reversal_register_s_zeros_are_its_stated_paths(runs):
    """One row per `exact` row, each naming that row's key, which no draw
    touches: moving it moves no stream's generator state."""
    for name in ("fixture", "mortgage"):
        run = runs[name]
        exact = run.block["reversal"]["exact"]
        zeros = run.block["reversal"]["structural_zeros"]
        assert [z["reversal_key"] for z in zeros] == [r["key"] for r in exact]
        spec = dr._spec_at(run.spec, 40)
        for zero in zeros:
            assert set(zero) == {"kind", "label", "keys", "reversal_key"}
            assert zero["kind"] == "stated_path"
            assert zero["keys"] == [zero["reversal_key"]]
            option, leaf = zero["reversal_key"].split(".", 1)
            assert zero["label"] == {"mortgage_renewal_rates": "the renewal rate",
                                     "mortgage_rate": "the contract rate"}[leaf]
            moved = copy.deepcopy(run.raw)
            moved.get("sources", {}).pop(zero["reversal_key"], None)
            value = moved[option][leaf]
            moved[option][leaf] = ([v + 0.01 for v in value] if isinstance(value, list)
                                   else value + 0.01)
            assert _stream_states(spec) == _stream_states(
                dr._spec_at(load_config_dict(moved), 40)), zero["label"]


# What `hde --help` says of `--decompose`, as a template: each claim it makes
# about a path count is a group, and the test below checks every group
# against runs. A help text that says anything else fails the match.
HELP_DECOMPOSE = re.compile(
    r"--decompose \[N\] Which risk decides it\. The spread register prices N futures "
    r"of the block's own \(N defaults to (?P<default>simulation\.num_sims)\), the level "
    r"register the first min\(N, (?P<cap>[\d,]+)\) of them, and the reversal register "
    r"reads the run's own (?P<reversal>simulation\.num_sims) paths whatever N is\. "
    r"What each figure means: (?P<doc>docs/reference/API_CONTRACT\.md), the "
    r"(?P<section>decomposition) block$")


def _help_entry():
    import contextlib
    import io
    from hde.cli import main
    out = io.StringIO()
    saved = sys.argv
    sys.argv = ["hde", "--help"]
    try:
        with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
            main()
    finally:
        sys.argv = saved
    lines = out.getvalue().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("  --decompose"))
    entry = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("  -"):
            break
        entry.append(line)
    return " ".join(" ".join(entry).split())


def test_a_row_measured_on_the_futures_is_the_spread_register_s(tmp_path):
    """§0.1 item 48's witness. A lease reset so rare that the tenancy draws
    and moves nothing on 40 futures, and is live on 5,000: its `dead_draw` row
    appears with `N` and goes with it, and it is the spread register's, in the
    JSON and under THE SPREAD in the text. The reversal register is the same
    object at both counts, whole.
    *Kills it:* a measured row printed outside the spread register, or a
    reversal register that changes with `N`."""
    few = Run(RARE_RESET_THREE, "40").materialise(tmp_path / "few")
    many = Run(RARE_RESET_THREE, "5000").materialise(tmp_path / "many")
    assert few.block["reversal"] == many.block["reversal"]
    assert [(z["kind"], z["channel_id"], z["measured_paths"])
            for z in few.block["spread"]["structural_zeros"]] == [("dead_draw", 5, 40)]
    assert many.block["spread"]["structural_zeros"] == []
    assert 5 not in few.block["live_channel_ids"] and 5 in many.block["live_channel_ids"]
    lines = few.text.splitlines()
    row = next(i for i, line in enumerate(lines) if line.startswith("  your tenancy: drawn"))
    assert lines.index("  THE SPREAD") < row < next(
        i for i, line in enumerate(lines) if line.startswith("  THE LEVEL"))
    assert "NO ROW IN THE SPREAD OR THE LEVEL" not in few.text


def test_the_help_says_how_many_futures_each_register_reads(runs):
    """`hde --help` is read before the contract is: every count it gives for
    `--decompose` is checked against runs. N is the block's `paths` (bare, the
    config's `simulation.num_sims`), the level reads `min(N, cap)` of them at
    an N under the cap and one over it, and the reversal register's curves are
    bisected on the config's `simulation.num_sims` at an N that differs from it.
    *Kills it:* a help text that names another count for any register, or a
    cap other than the engine's."""
    m = HELP_DECOMPOSE.fullmatch(_help_entry())
    assert m, _help_entry()
    cap = int(m["cap"].replace(",", ""))
    assert cap == dr.LEVEL_PATHS
    fixture = runs["fixture"]
    num_sims = fixture.spec.simulation.num_sims
    assert fixture.block["paths"] == 300 != num_sims
    assert fixture.block["level"]["paths"] == min(300, cap)
    big = runs["advanced_4000"]
    assert big.block["paths"] == 4000 > cap
    assert big.block["level"]["paths"] == min(4000, cap)
    curves = [b["curve_paths"] for row in fixture.block["reversal"]["exact"]
              for b in row["boundaries"] if "curve_paths" in b]
    assert curves and set(curves) == {num_sims}
    code, out, _ = _cli("--decompose", runs["mortgage"].path, "--json")
    assert code == 0
    assert _strict(out)["decomposition"]["paths"] == runs["mortgage"].spec.simulation.num_sims
    assert (REPO / m["doc"]).is_file()
    assert "## The `decomposition` block" in (REPO / m["doc"]).read_text(encoding="utf-8")


@claims("`structural_zeros[]`: `kind`, `label`, `keys`, `channel_id`,",
        "Both facts are measured, on those futures, and both are facts about the stream.",
        "`keys` are the keys of the stream's widths (the income stream's")
def test_the_structural_zeros_say_what_is_drawn(runs):
    """Checked at the generators: the income stream and a dead channel move
    their state, and re-seeding them, on held generators and as many futures
    as the row names, moves no present value past the row's threshold. And at
    the grain of a key (§0.1 item 40): `rent.events` on `three` names a stated
    moving cost whose deterministic present value is in rent's, and the row
    names it only as what sizes the tenancy's draws."""
    fixture = runs["fixture"]
    zeros = fixture.block["spread"]["structural_zeros"]
    for zero in zeros:
        assert set(zero) == {"kind", "label", "keys", "channel_id", "measured_paths",
                             "move_threshold"}
    # every row of every run of the corpus is a dead_draw row
    for name, run in runs.items():
        assert {z["kind"] for z in run.block["spread"]["structural_zeros"]} <= {
            "dead_draw"}, name
    spec = dr._spec_at(fixture.spec, 40)
    income = next(z for z in zeros if z["kind"] == "dead_draw")
    assert income["channel_id"] == dc.INCOME_STREAM_ID
    assert income["keys"] == ["income.pay_drop_events"]
    assert income["measured_paths"] == fixture.block["paths"]
    assert 7 in _moved_streams(spec)
    assert oracle_moves(fixture.spec, income["measured_paths"])[7] <= income["move_threshold"]
    three = runs["three"]
    dead = [z for z in three.block["spread"]["structural_zeros"] if z["kind"] == "dead_draw"]
    assert [z["channel_id"] for z in dead] == [5]
    spec3 = dr._spec_at(three.spec, 40)
    for zero in dead:
        assert zero["channel_id"] in _moved_streams(spec3)
        moves = oracle_moves(three.spec, zero["measured_paths"])
        assert moves[zero["channel_id"]] <= zero["move_threshold"]
    # the key the tenancy's row names carries a cash flow of its own
    tenancy = dead[0]
    assert tenancy["keys"] == ["rent.events"]
    event = three.raw["rent"]["events"][0]
    breakdown = three.doc["deterministic"]["rent"]["breakdown"]
    discount = three.spec.simulation.discount_rate
    assert breakdown["events_pv"] == pytest.approx(
        event["base_cost"] / (1 + discount) ** event["expected_year"], rel=1e-9)
    assert breakdown["events_pv"] > 0.0
    line = next(l for l in three.text.splitlines() if l.startswith("  your tenancy:"))
    assert line.endswith("; sized by rent.events")
    assert "rent.events:" not in three.text and "cash flow" not in three.text


def _held(overrides=None):
    seeds = {c: 1000 + c for c in range(8)}
    seeds.update(overrides or {})
    return {c: np.random.default_rng(s) for c, s in seeds.items()}


def _stream_states(spec):
    streams = _held()
    run_monte_carlo(spec, streams)
    return {c: g.bit_generator.state["state"]["state"] for c, g in streams.items()}


def _moved_streams(spec):
    before = {c: g.bit_generator.state["state"]["state"] for c, g in _held().items()}
    after = _stream_states(spec)
    return {c for c in before if before[c] != after[c]}


# ---------------------------------------------------------------------------
# The text block
# ---------------------------------------------------------------------------

@claims("**The text block** prints these figures and no sentence about them.",
        "Every line is one of six kinds: a heading; a figure row",
        "`move_threshold`, the largest move an")
def test_the_text_block_holds_six_kinds_of_line(runs):
    """Every line of every render is one template of the sentence tests, and
    every template is a blank or one of the six kinds (§0.1 items 35 and 41),
    the path note under its own kind, not filed as a crossing. Each
    structural-zero row prints its fields, after the spread register's
    figures."""
    kinds = set(sentences.KINDS.values())
    assert kinds == sentences.SIX_KINDS | {"layout"}
    assert sentences.KINDS["PATH_NOTE"] == "path note"
    # §0.1 item 50: a refusal is its code and one fact, every one of them
    refusals = [name for name, kind in sentences.KINDS.items() if kind == "refusal"]
    assert set(refusals) == {"REFUSAL", "SPREAD_REFUSED", "REFUSED_BOUNDARY", "NO_DISTANCE"}
    for name in refusals:
        assert {"code", "reason"} <= set(sentences.LINES[name].groupindex), name
    for render in sentences.renders():
        for line in sentences._lines(render):
            assert sentences.KINDS[line.template] in kinds
    run = runs["fixture"]
    lines = run.text.splitlines()
    level_head = next(i for i, line in enumerate(lines) if line.startswith("  THE LEVEL"))
    dead = run.block["spread"]["structural_zeros"]
    # under the spread register's heading, after its figures: the last lines
    # before the blank line that opens the level register
    assert dead and lines[level_head - 1] == ""
    assert lines[level_head - 1 - len(dead):level_head - 1] == [
        f"  {zero['label']}: drawn on these {zero['measured_paths']:,} futures, and "
        f"re-drawing it moved no option's present value by more than "
        f"${dt._ceiled_threshold(zero['move_threshold'])}; sized by "
        f"{', '.join(zero['keys'])}" for zero in dead]
    assert lines[level_head - 2 - len(dead)].startswith("  largest alone share:")
    for zero in dead:
        # three significant figures, taken upward
        printed = decimal.Decimal(dt._ceiled_threshold(zero["move_threshold"]))
        assert len(printed.normalize().as_tuple().digits) <= 3
        assert printed >= decimal.Decimal(zero["move_threshold"])
        assert printed - decimal.Decimal(1).scaleb(printed.adjusted() - 2) \
            < decimal.Decimal(zero["move_threshold"])


def _table_line(text, heading, channel_id):
    """The one line of the table under `heading` that opens with the channel's
    label: a row's own cells, and no other line's figures."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    label = f"  {dc.channel(channel_id).label} "
    found = []
    for line in lines[start + 2:]:
        if not line.startswith("  ") or line.startswith("  alone shares summed") \
                or line.startswith("  the ") and "shifts above" in line:
            break
        if line.startswith(label):
            found.append(line)
    assert len(found) == 1, (heading, label, found)
    return found[0]


def _assert_top_line(text, what, leading):
    lines = [line for line in text.splitlines() if line.startswith(f"  largest {what}:")]
    want = [] if leading is None else [f"  largest {what}: {dc.channel(leading).label}"]
    assert lines == want, (what, lines)


@claims("A figure that did not resolve prints behind",
        "by `; 1 minus that sum: not resolved` when the sum's interval includes 1,",
        "`largest alone share:` and `largest shift in size:` name a",
        "when a register's top row did not resolve, that register's line does not print.",
        "Each printed figure is rounded on its own from the unrounded field")
def test_the_text_block_prints_the_registers_own_judgments(runs):
    """On the fixture: each unresolved spread and level row behind the words,
    each resolved one bare; each top line as the JSON names it; the sums and
    the level's difference over the printed figures. And the partition of
    "not resolved" pinned whole (§0.1 item 46): over every line of every
    render, each occurrence is either followed by ": " and a figure, or is
    the residual's own place on a block whose sum's interval includes 1. Where
    that interval lies above 1, the line ends at the interval (§4), on the
    fixture at its own count of futures."""
    residual_seen = 0
    for render in sentences.renders():
        for line in render.text.splitlines():
            for hit in re.finditer(r"not resolved(?P<after>.{0,3})", line):
                if hit["after"].startswith(": "):
                    assert re.match(r"not resolved: [+-]?\$?-?\d", line[hit.start():]), line
                    continue
                assert line.endswith("; 1 minus that sum: not resolved"), line
                interaction = render.block["spread"]["interaction"]
                assert interaction["resolved"] is False
                low, high = (interaction["first_order_sum_ci"]["low"],
                             interaction["first_order_sum_ci"]["high"])
                assert low <= 1.0 <= high, line
                residual_seen += 1
    assert residual_seen
    above = 0
    for render in sentences.renders():
        interaction = render.block.get("spread", {}).get("interaction")
        if interaction is None or interaction["first_order_sum_ci"]["low"] <= 1.0:
            continue
        (line,) = [line for line in render.text.splitlines()
                   if line.startswith("  alone shares summed")]
        assert line == (f"  alone shares summed before rounding: "
                        f"{dt._share(interaction['first_order_sum'])} "
                        f"{dt._interval(dc.Interval(**interaction['first_order_sum_ci']))}")
        above += render.engine
    assert above
    seen_unresolved = 0
    tops = set()
    for name in ("fixture", "showcase", "three", "advanced", "basic"):
        run = runs[name]
        text = run.text
        spread = run.block["spread"]
        level = run.block["level"]
        if "rows" in spread:
            for row in spread["rows"]:
                cell = f"{dt._share(_point(row))} {dt._interval(dc.Interval(**(row['alone_ci'] if row['resolved'] else row['provisional_alone_ci'])))}"
                line = _table_line(text, "  THE SPREAD", row["channel_id"])
                assert cell in line, (name, cell, line)
                assert (f"not resolved: {cell}" in line) == (not row["resolved"]), (name, cell)
                seen_unresolved += not row["resolved"]
            _assert_top_line(text, "alone share", spread["leading_channel_id"])
            tops.add(spread["leading_channel_id"] is not None)
        for row in level["rows"]:
            cell = f"{dt._shift(_shift(row))} (± ${row['se']:,.0f})"
            line = _table_line(text, "  THE LEVEL", row["channel_id"])
            assert cell in line, (name, cell, line)
            assert (f"not resolved: {cell}" in line) == (not row["resolved"]), (name, cell)
            seen_unresolved += not row["resolved"]
        _assert_top_line(text, "shift in size", level["leading_channel_id"])
        tops.add(level["leading_channel_id"] is not None)
    assert seen_unresolved and tops == {True, False}
    run = runs["fixture"]
    level = run.block["level"]
    printed = [float(f"{_shift(r):.0f}") for r in level["rows"]]
    frozen, futures = (float(f"{level['all_frozen_margin']:.0f}"),
                       float(f"{level['futures_margin']:.0f}"))
    lines = run.text.splitlines()
    assert any(line.endswith(f"the central case's margin minus that mean: "
                             f"{dt._money(frozen - futures)}") for line in lines)
    assert f"  the {len(printed)} shifts above, summed: {dt._money(sum(printed))}" in lines
    inter = run.block["spread"]["interaction"]
    assert any(line.startswith(f"  alone shares summed before rounding: "
                               f"{dt._share(inter['first_order_sum'])} ") for line in lines)


# The contract's skeleton of every line the text block prints, as its spans:
# each is a backticked span of the section, and a line is its spans in order.
_SUMS = "alone shares summed before rounding: <first_order_sum> [<low>, <high>]"
_SOLVED = ("solved on the central case: as it rises past <formatted>, <field> changes from "
           "<was> to <becomes>")
_SAMPLED = ("sampled on <curve_paths> paths at seed <seed>: as it rises past <formatted>, "
            "<field> changes from <was> to <becomes>")
_FURTHER = " (and changes again <further_changes> it, inside the bracket)"
_ZERO = ("<label>: drawn on these <measured_paths> futures, and re-drawing it moved no "
         "option's present value by more than $<move_threshold>")
_SKELETONS = {
    "HEADER": ("which risk decides it — <paths> futures, <k> channels live on them",),
    "REFUSAL": ("which risk decides it — not split (<code>): <reason>",),
    "MARGIN": ("margin, the cheapest other option's present value minus <best>'s: central "
               "case <margin>; over this block's own <paths> futures, mean <mean_margin> "
               "and s.d. <sd_margin>",),
    "SPREAD_HEAD": ("THE SPREAD",),
    "SPREAD_REFUSED": ("not split (<code>): <reason>",),
    "SPREAD_COLS": ("channel alone with interaction flips whether <best> is cheapest",),
    "SPREAD_ROW": ("<label> <alone> [<low>, <high>] <with_interaction> [<low>, <high>] "
                   "<flip>% [<low>, <high>]",),
    "WIDTHS": ("sized by <widths>",),
    "SUMS": (_SUMS,),
    "SUMS_RESIDUAL": (_SUMS, "; 1 minus that sum: <residual> [<low>, <high>]"),
    "SUMS_UNRESOLVED": (_SUMS, "; 1 minus that sum: not resolved"),
    "GAPS": ("with interaction minus alone, before rounding: <label> <interaction_gap> "
             "[<low>, <high>]",),
    "SPREAD_TOP": ("largest alone share: <label>",),
    "ZERO": (_ZERO,),
    "ZERO_KEYS": (_ZERO, "; sized by <keys>"),
    "LEVEL_HEAD": ("THE LEVEL — the first <level.paths> of these futures",),
    "LEVEL_BASE": ("as drawn: mean margin <futures_margin>, P(<best> cheapest) "
                   "<prob_best_base>; the central case's margin minus that mean: <gap>",),
    "LEVEL_COLS": ("channel margin shift, channel frozen (± 1 s.e.) P(<best> cheapest), "
                   "channel frozen",),
    "LEVEL_ROW": ("<label> <shift> (± $<se>) <prob_best_frozen>",),
    "LEVEL_SUM": ("the <n> shifts above, summed: <sum>",),
    "LEVEL_TOP": ("largest shift in size: <label>",),
    "ZERO_HEAD": ("NO ROW IN THE SPREAD OR THE LEVEL",),
    "ZERO_STATED": ("<label> — <keys>: no draw touches it",),
    "EXACT_HEAD": ("WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly",),
    "ESTIMATED_HEAD": ("WHAT WOULD HAVE TO CHANGE — keys the engine cannot re-price exactly",),
    "NOT_SOLVED": ("WHAT WOULD HAVE TO CHANGE — not solved (<code>): <reason>",),
    "ROW_HEAD": ("<key>",),
    "BRACKET": ("bracket searched: <bracket_low>–<bracket_high> [<bracket_source>]",),
    "CROSS_SOLVED": (_SOLVED,),
    "CROSS_SOLVED_FURTHER": (_SOLVED, _FURTHER),
    "CROSS_SAMPLED": (_SAMPLED,),
    "CROSS_SAMPLED_FURTHER": (_SAMPLED, _FURTHER),
    "REFUSED_NONE": ("no boundary printed for <fields> (<code>): <reason>",),
    "REFUSED_EDGE": ("a boundary not printed for <fields> (<code>): <reason>",),
}
# The order the contract gives the lines in, over the skeletons' names.
_ROWS = (r"(?: ROW_HEAD BRACKET(?: PATH_NOTE)?(?: CROSS_SOLVED\w*)*(?: CROSS_SAMPLED\w*)*"
         r"(?: REFUSED_\w+)*)+")
_ORDER = re.compile(
    r"REFUSAL|HEADER MARGIN BLANK SPREAD_HEAD (?:SPREAD_REFUSED|SPREAD_COLS"
    r"(?: SPREAD_ROW WIDTHS)+ SUMS\w* GAPS(?: SPREAD_TOP)?)(?: ZERO(?:_KEYS)?)* BLANK LEVEL_HEAD "
    r"LEVEL_BASE LEVEL_COLS(?: LEVEL_ROW)+ LEVEL_SUM(?: LEVEL_TOP)?"
    r"(?: BLANK ZERO_HEAD(?: ZERO_STATED)+)?"
    rf"(?: BLANK EXACT_HEAD{_ROWS}(?: BLANK ESTIMATED_HEAD{_ROWS})?(?: BLANK(?: NOT_SOLVED)+)?"
    rf"| BLANK ESTIMATED_HEAD{_ROWS}(?: BLANK(?: NOT_SOLVED)+)?| BLANK(?: NOT_SOLVED)+)")
# A placeholder that may hold any text; every other one is a figure or a label,
# which holds no bracket, no parenthesis and no `; `.
_FREE = {"<reason>", "<widths>", "<keys>"}
# The path note prints a row's `path_note` whole, which the contract gives in
# words rather than as a skeleton.
_PATH_NOTE = re.compile(r"each crossing on this key is priced with the stated path "
                        r"replaced by one rate at every renewal")


def _span_pattern(span):
    return "".join(
        (".+" if part in _FREE else r"[^\[\];()]+?") if re.fullmatch(r"<[^<>]+>", part)
        else re.escape(part)
        for part in re.split(r"(<[^<>]+>)", span) if part)


def _skeleton_pattern(name, spans):
    if name == "GAPS":
        # one part per row, `; `-joined
        head, part = spans[0].split(": ", 1)
        one = _span_pattern(part)
        return re.compile(f"{re.escape(head)}: {one}(?:; {one})*")
    if name == "ROW_HEAD":
        # a key, which is dotted
        return re.compile(r"[a-z_]+(?:\.[a-z_]+)+")
    return re.compile("".join(_span_pattern(span) for span in spans))


@claims("The lines it prints are these, in this order, and no others",
        "- `which risk decides it — <paths> futures, <k> channels live on them`",
        "- `margin, the cheapest other option's present value minus <best>'s:",
        "- A blank line, and `THE SPREAD`.",
        "- For a refused spread, `not split (<code>): <reason>`; otherwise its table:",
        "- Each row of `structural_zeros`, refused spread or not:",
        "- A blank line, and `THE LEVEL — the first <level.paths> of these futures`.",
        "- `as drawn: mean margin <futures_margin>,",
        "- `channel margin shift, channel frozen (± 1 s.e.) P(<best> cheapest), channel",
        "- When `reversal.structural_zeros` has rows, a blank line, `NO ROW IN THE",
        "- When `exact` has rows, a blank line and `WHAT WOULD HAVE TO CHANGE — keys the",
        "A `<field>` is `the central case's winner` (`best`), `the runner-up`",
        "- When `estimated` has rows, the same under a blank line and `WHAT WOULD HAVE",
        "- When `refused` has rows, a blank line and, for each row, `WHAT WOULD HAVE",
        "- When none of the three has rows, a blank line and that line, its `<code>`")
def test_the_text_block_prints_the_contract_s_lines_in_its_order_and_no_others(monkeypatch):
    """§0.1 item 46's rule for a list that says it is whole: every span of
    every skeleton is the contract's own text, character for character; every
    line of every render, its runs of spaces collapsed, is exactly one
    skeleton; the lines of each render come in the contract's order; and every
    skeleton, each ending of the sums line and of a `structural_zeros` row
    included, is printed by a run of the engine. What each figure in a line is
    checked against is the sentence tests' (`LINE_CLAIMS`).
    *Kills it:* a line the contract does not list, a listed line no run
    prints, an ending of a line the contract gives wrong (the sums line's with
    its interval above 1, a `structural_zeros` row's with no keys), or two
    lines printed out of the contract's order."""
    section = " ".join(_section().split())
    for spans in _SKELETONS.values():
        for span in spans:
            assert f"`{span}`" in section, span
    assert "its `path_note` when it is set" in section
    for field, words in sentences.FIELD_WORDS.items():
        assert f"`{words}` (`{field}`)" in section, field
    patterns = {name: _skeleton_pattern(name, spans) for name, spans in _SKELETONS.items()}
    patterns["PATH_NOTE"] = _PATH_NOTE
    # an estimated row, forced on a real run (see the test of `estimated[]`)
    monkeypatch.setattr(be, "_shift_deviation_over_sd", lambda before, after: 1.0)
    code, forced, _ = _cli(MORTGAGE, "--decompose", "200", "-q")
    monkeypatch.undo()
    assert code == 0
    texts = [(render.name, render.engine, render.text) for render in sentences.renders()]
    texts.append(("estimated", True, _block_text(forced)))
    printed = set()
    for name, engine, text in texts:
        names = []
        for line in text.splitlines():
            if not line.strip():
                names.append("BLANK")
                continue
            if not engine and sentences.LINES["CROSS_ESTIMATED"].match(line):
                # the boundary type an estimated row is typed for, which no run
                # emits: a household's alone prints it
                continue
            flat = " ".join(line.split())
            hits = [key for key, pattern in patterns.items() if pattern.fullmatch(flat)]
            assert len(hits) == 1, (name, line, hits)
            names.append(hits[0])
            if engine:
                printed.add(hits[0])
        assert _ORDER.fullmatch(" ".join(names)), (name, names)
    assert printed == set(patterns), set(patterns) - printed


def _printed_labels(render, template):
    return [line.m["label"] for line in sentences._lines(render) if line.template == template]


@claims("A level row prints its shift and `se` in whole dollars, or at cents and then one",
        "The sum of the shifts prints at the most decimals a row prints.")
def test_a_level_row_prints_the_decimals_its_judgment_needs(runs):
    """§0.1 item 62's witnesses as printed: a resolved row whose shift is not
    above twice its s.e. at whole dollars prints at cents, as do rows a
    fraction of a dollar each, and the sum prints at the most decimals a row
    prints; a constructed unresolved row whose whole dollars would read as
    resolved prints at cents too. Every level row of every render is checked
    both ways by the sentence tests (`_level_row`): its printed pair shows its
    judgment, and no fewer decimals would.
    *Kills it:* whole dollars on every row (the witnesses' lines revert), or
    the decimals chosen on anything but the judgment."""
    run = runs["pull_nothing"]
    (economy,) = [r for r in run.block["level"]["rows"] if r["channel_id"] == 0]
    assert economy["resolved"]
    # at whole dollars the pair does not show the judgment
    assert abs(float(f"{economy['delta']:.0f}")) <= 2 * float(f"{economy['se']:.0f}")
    lines = run.text.splitlines()
    level = run.text.split("THE LEVEL", 1)[1].splitlines()
    (line,) = [line for line in level if line.startswith("  the economy ")]
    assert f"{dr.signed_dollars(economy['delta'], 2)} (± ${economy['se']:,.2f})" in line
    assert "not resolved" not in line
    assert "  the 3 shifts above, summed: -$329.00" in lines
    small = runs["level_under_a_dollar"].text.splitlines()
    for want in ("+$0.03 (± $0.01)", "not resolved: $0 (± $0)"):
        assert any(want in line for line in small), want
    assert "  the 3 shifts above, summed: $1.03" in small
    outcome = hh.uncertainty_surface()
    rows = tuple(dataclasses.replace(row, level=dc.IndistinguishableLevel(
        provisional_delta=2.6, se=1.4, prob_best_frozen=0.34)) if row.channel_id == 0
        else row for row in outcome.level.rows)
    text = dt.format_decomposition(dataclasses.replace(
        outcome, level=dataclasses.replace(outcome.level, rows=rows)))
    assert "not resolved: +$2.60 (± $1.40)" in text


def _percent(text):
    return float(decimal.Decimal(text.rstrip("%")).scaleb(-2))


@claims("A crossing's rate is `formatted`: `value` floored,",
        "It never widens past twelve decimals, nor past the precision at which one printed",
        "Where no precision passes, the boundary refuses with `not_printable`")
def test_a_crossing_s_figure_is_its_value_floored_where_the_field_says_was(runs, monkeypatch):
    """§0.1 items 54, 60 and 61, on their witnesses. Every crossing's figure
    is its value floored at its kind's precision or more; `--sweep` at the
    printed figure says `was`; one printed step is no narrower than the
    bracket; and at each fewer decimal the field said another state there or
    the figure lay below the bracket searched, so it widened no further than
    it had to. A crossing no precision prints refuses by name with each
    figure tried, and the row's other crossings print.
    *Kills it:* a fixed precision (the witnesses' lines revert), a figure
    floored from anything but `value`, a check at the unrounded value instead
    of the printed figure, or widening past need or past the bracket."""
    widened = 0
    for name in _CROSSING_RUNS + ("level_under_a_dollar", "crossing_near_the_low_end",
                                  "stated_at_the_bracket_high_end", "decisive_for_another",
                                  "decisive_without_noise", "decisive_for_the_house",
                                  "sampled_just_above_its_figure",
                                  "solved_just_above_its_figure",
                                  "sampled_was_just_under_its_figure",
                                  "solved_was_just_under_its_figure"):
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            for boundary in row["boundaries"]:
                field, sampled = boundary["verdict_field"], "curve_paths" in boundary
                start = 2 if sampled else 4
                places = len(boundary["formatted"].rstrip("%").split(".")[1])
                assert start <= places <= be.PRINTED_RATE_MAX_PLACES == 12, boundary
                width = decimal.Decimal(boundary["upper_end"]) - decimal.Decimal(boundary["value"])
                assert decimal.Decimal(1).scaleb(-(places + 2)) >= width, boundary
                assert boundary["formatted"] == be.floored_rate(boundary["value"], places)
                (at,) = _sweep_states(run.path, row["key"], [_percent(boundary["formatted"])],
                                      sampled)
                assert at[field] == boundary["was"], (name, boundary)
                for fewer in range(start, places):
                    text = be.floored_rate(boundary["value"], fewer)
                    if _percent(text) >= row["bracket_low"]:
                        (there,) = _sweep_states(run.path, row["key"], [_percent(text)],
                                                 sampled)
                        assert there[field] != boundary["was"], (name, text)
                    widened += 1
    assert widened
    # crossings a few hundredths of a percent inside the bracket's low end
    # print, at their kind's own precision: a floored figure is passed over
    # only below it
    (row,) = runs["crossing_near_the_low_end"].block["reversal"]["exact"]
    assert [(b["verdict_field"], len(b["formatted"].split(".")[1]) - 1)
            for b in row["boundaries"]] == [("best", 4), ("runner_up", 4), ("mc_best", 2),
                                            ("decisive", 2)]
    assert all(row["bracket_low"] < _percent(b["formatted"]) < row["bracket_low"] + 0.0005
               for b in row["boundaries"][:3])
    # floored from the bracket's lower end, never its middle: the mortgage
    # example's central-case crossings moved onto a bracket whose middle float
    # is the first four-decimal figure above the crossing, where the field no
    # longer says `was`, and whose lower end floors one step below it; the
    # central case at the moved lower end reads what it reads at the
    # crossing's own
    real = be.solve_crossings
    real_ranking = be._ranking_at
    moved = {}

    def onto_a_figure(*args, **kwargs):
        solved = real(*args, **kwargs)
        for entry in solved["break_evens"]:
            grid = decimal.Decimal(entry["value"]).scaleb(2).quantize(
                decimal.Decimal("0.0001"), rounding=decimal.ROUND_CEILING).scaleb(-2)
            middle = float(grid)
            if decimal.Decimal(middle) < grid:
                middle = math.nextafter(middle, 1.0)
            lower = math.nextafter(middle, 0.0)
            moved[lower] = entry["value"]
            entry["value"], entry["bracket"] = lower, [lower, math.nextafter(middle, 1.0)]
        return solved

    monkeypatch.setattr(be, "solve_crossings", onto_a_figure)
    monkeypatch.setattr(be, "_ranking_at", lambda raw, key, value: real_ranking(
        raw, key, moved.get(value, value)))
    code, out, _ = _cli(MORTGAGE, "--decompose", "200", "--json")
    assert code == 0
    (row,) = _strict(out)["decomposition"]["reversal"]["exact"]
    solved = [b for b in row["boundaries"] if "curve_paths" not in b]
    assert solved and not [r for r in row["refused_boundaries"]
                           if r["verdict_field"] in ("best", "runner_up")]
    code, text, _ = _cli(MORTGAGE, "--decompose", "200")
    assert code == 0
    for boundary in solved:
        middle = 0.5 * (boundary["value"] + boundary["upper_end"])
        step = (decimal.Decimal(be.floored_rate(middle, 4).rstrip("%"))
                - decimal.Decimal(be.floored_rate(boundary["value"], 4).rstrip("%")))
        assert step == decimal.Decimal("0.0001")
        assert (f"solved on the central case: as it rises past "
                f"{be.floored_rate(boundary['value'], 4)}, ") in text
    monkeypatch.undo()
    for boundary in solved:
        middle = 0.5 * (boundary["value"] + boundary["upper_end"])
        (there,) = _sweep_states(runs["mortgage"].path, row["key"],
                                 [_percent(be.floored_rate(middle, 4))], False)
        assert there[boundary["verdict_field"]] != boundary["was"]
    # a crossing no precision prints: forced, the central case read at every
    # floored figure of the mortgage example's crossing names its `becomes`
    boundary = not_printable_at_every_figure(monkeypatch, "best")
    code, out, _ = _cli(MORTGAGE, "--decompose", "200", "--json")
    monkeypatch.undo()
    assert code == 0
    (row,) = _strict(out)["decomposition"]["reversal"]["exact"]
    (refused,) = [r for r in row["refused_boundaries"] if r["verdict_field"] == "best"]
    assert refused["code"] == "not_printable"
    assert refused["reason"] == (
        f"the crossing of best from {boundary['was']!r} whose bracket starts at "
        f"{boundary['value']!r}, floored at 4 to 12 decimals of a percent: "
        + "; ".join(f"{be.floored_rate(boundary['value'], places)} reads "
                    f"{boundary['becomes']!r}" for places in range(4, 13)))
    (printed,) = runs["mortgage"].block["reversal"]["exact"]
    assert row["boundaries"] == [b for b in printed["boundaries"]
                                 if b["verdict_field"] != "best"]


def test_a_crossing_s_figure_is_checked_at_that_figure(runs):
    """§0.1 items 54 and 60, a billionth of the figure either side of it.
    Where the field reads the crossing's `becomes` a billionth of the figure
    above the printed figure, the crossing still prints, at its kind's own
    precision; where it reads a state other than `was` a billionth below, the
    crossing prints no finer than there. A sampled and a solved crossing each
    way.
    *Kills it:* the printed-rate check reading the field anywhere but at the
    printed figure."""
    for name, field, formatted, line in (
            ("sampled_just_above_its_figure", "decisive", "6.23%",
             "sampled on 400 paths at seed 42: as it rises past 6.23%, the decisiveness "
             "verdict changes from decisive for house to not decisive (and changes again "
             "above it, inside the bracket)"),
            ("solved_just_above_its_figure", "best", "6.2700%",
             "solved on the central case: as it rises past 6.2700%, the central case's "
             "winner changes from house to rent"),
            ("sampled_was_just_under_its_figure", "decisive", "6.28%",
             "sampled on 400 paths at seed 42: as it rises past 6.28%, the decisiveness "
             "verdict changes from not decisive to decisive for rent (and changes again "
             "below it, inside the bracket)"),
            ("solved_was_just_under_its_figure", "runner_up", "6.2700%",
             "solved on the central case: as it rises past 6.2700%, the runner-up changes "
             "from house to rent (and changes again below it, inside the bracket)")):
        run = runs[name]
        (row,) = run.block["reversal"]["exact"]
        assert f"      {line}" in run.text.splitlines(), name
        (boundary,) = [b for b in row["boundaries"]
                       if b["verdict_field"] == field and b["formatted"] == formatted]
        figure = _percent(formatted)
        at, above, below = _sweep_states(run.path, row["key"],
                                         [figure, figure * (1 + 1e-9), figure * (1 - 1e-9)],
                                         "curve_paths" in boundary)
        assert at[field] == boundary["was"], name
        if "above" in name:
            assert above[field] == boundary["becomes"], name
        else:
            assert below[field] != boundary["was"], name


@claims("The sides of an `mc_best` boundary are computed from P(cheapest) of")
def test_a_decisive_boundary_is_identified_on_the_option_its_sides_are_computed_from(runs):
    """§0.1 item 63, on two three-option witnesses whose decisiveness
    crossing is decisive for the house while this run's winner is another
    option: the crossing prints; `--sweep` names the house the central case's
    winner at each end of its bracket; and the house's P(cheapest),
    re-simulated at the two ends of the bracket searched, moves by more than
    two of its standard errors at the boundary, where the run's winner's does
    not.
    *Kills it:* the check watching the run's own winner, which refuses the
    crossing as `not_identified`, or watching any option but the ones its
    sides are computed from."""
    for name, key in (("decisive_for_another", "house.mortgage_rate"),
                      ("decisive_for_the_house", "house.mortgage_renewal_rates")):
        run = runs[name]
        (row,) = [r for r in run.block["reversal"]["exact"] if r["key"] == key]
        (boundary,) = [b for b in row["boundaries"] if b["verdict_field"] == "decisive"]
        assert (boundary["was"], boundary["becomes"]) == ("decisive for house", "not decisive")
        best = run.doc["verdict"]["best"]
        assert best != "house"
        ends = _sweep_states(run.path, key, [boundary["value"], boundary["upper_end"]], False)
        assert [end["best"] for end in ends] == ["house", "house"]
        at = dict(boundary["curve_probabilities"])
        low, high = (run_monte_carlo(be.load_at(run.raw, key, v))
                     for v in (row["bracket_low"], row["bracket_high"]))

        def moves_past_its_noise(option):
            move = abs(getattr(high, f"prob_{option}_cheapest")
                       - getattr(low, f"prob_{option}_cheapest"))
            return move > 2.0 * math.sqrt(at[option] * (1.0 - at[option])
                                          / boundary["curve_paths"])

        assert moves_past_its_noise("house") and not moves_past_its_noise(best), name


def _decisive_crossing(run, key, seed):
    """The run's one `decisive` boundary on `key`, checked to print as its
    line, and the options `--sweep` names the central case's winner at its
    two ends."""
    (row,) = [r for r in run.block["reversal"]["exact"] if r["key"] == key]
    (boundary,) = [b for b in row["boundaries"] if b["verdict_field"] == "decisive"]
    assert (boundary["was"], boundary["becomes"]) == ("decisive for condo", "not decisive")
    assert (f"      sampled on 400 paths at seed {seed}: as it rises past "
            f"{boundary['formatted']}, the decisiveness verdict changes from decisive for "
            "condo to not decisive") in run.text.splitlines()
    sides = [end["best"] for end in _sweep_states(
        run.path, key, [boundary["value"], boundary["upper_end"]], True)]
    return row, boundary, sides


def _moves_across_the_bracket(run, row, option):
    """How far `option`'s P(cheapest), re-simulated at the two ends of the
    bracket searched, moves between them."""
    low, high = (run_monte_carlo(be.load_at(run.raw, row["key"], v))
                 for v in (row["bracket_low"], row["bracket_high"]))
    return abs(getattr(high, f"prob_{option}_cheapest") - getattr(low, f"prob_{option}_cheapest"))


@claims("or at which every such standard error is 0")
def test_a_decisive_step_with_no_noise_is_identified(runs):
    """§0.1 item 67, on two witnesses: the condo's decisiveness crossing
    prints, though the probabilities its two sides are computed from,
    P(cheapest) of the central case's winner at each end of its bracket, are
    each 0 or 1 at the boundary, so their standard error there is 0. On one
    neither moves between the two ends of the bracket searched; on the other
    the condo's moves and rent's does not. Both are computed from two
    options, so item 68 identifies them too.
    *Kills it:* the check held to the noise rule there, which refuses the
    crossing as `not_identified`, or held to it wherever one of those
    probabilities does not move."""
    for name, moving in (("decisive_without_noise", set()),
                         ("one_moves_one_flat", {"condo"})):
        run = runs[name]
        row, boundary, sides = _decisive_crossing(run, "condo.mortgage_rate", 42)
        assert sides == ["condo", "rent"], name
        at = dict(boundary["curve_probabilities"])
        assert [at[option] for option in sides] == [1.0, 0.0], name
        assert {option for option in sides
                if _moves_across_the_bracket(run, row, option) > 0.0} == moving, name


@claims("whose two sides are computed from different options")
def test_a_decisive_step_where_the_winner_changes_is_identified(runs):
    """§0.1 item 68, on its witness: the condo's decisiveness crossing lies
    where the central case's winner changes from the condo to the house, at
    the solved crossing inside its bracket, so its two sides are computed
    from those two options, and it prints. Neither's P(cheapest) moves
    between the two ends of the bracket searched, and each has a standard
    error above 0 at the boundary, so the noise rule alone would refuse it.
    *Kills it:* the check held to the noise rule wherever the two sides are
    computed from different options, which refuses the crossing as
    `not_identified`."""
    run = runs["decisive_at_the_winners_step"]
    row, boundary, sides = _decisive_crossing(run, "condo.mortgage_rate", 4)
    assert sides == ["condo", "house"]
    (best,) = [b for b in row["boundaries"] if b["verdict_field"] == "best"]
    assert (best["was"], best["becomes"]) == ("condo", "house")
    assert boundary["value"] <= best["value"] < boundary["upper_end"]
    at = dict(boundary["curve_probabilities"])
    for option in sides:
        assert 0.0 < at[option] < 1.0, option
        assert _moves_across_the_bracket(run, row, option) == 0.0, option
    assert not any(r["verdict_field"] == "decisive" for r in row["refused_boundaries"])


def test_every_decisiveness_step_at_a_winner_change_prints(runs):
    """§0.1 item 68 on a rendered run: each of the four decisiveness
    crossings on the two-ladder config lies where the central case's winner
    changes, so each prints, two of them running out of decisiveness and two
    into it, and no decisiveness boundary on it is refused.
    *Kills it:* item 68's rule narrowed to probabilities that do not move, to
    probabilities inside their noise, or to steps out of decisiveness; each
    refuses one of these lines as `not_identified`."""
    run = runs["winners_steps_on_two_ladders"]
    lines = run.text.splitlines()
    for key, figure, was, becomes in [
        ("condo.mortgage_renewal_rates", "3.19%", "decisive for condo", "not decisive"),
        ("condo.mortgage_rate", "3.80%", "decisive for condo", "not decisive"),
        ("house.mortgage_renewal_rates", "5.77%", "not decisive", "decisive for condo"),
        ("house.mortgage_rate", "8.82%", "not decisive", "decisive for condo"),
    ]:
        (row,) = [r for r in run.block["reversal"]["exact"] if r["key"] == key]
        (boundary,) = [b for b in row["boundaries"] if b["verdict_field"] == "decisive"]
        assert (boundary["formatted"], boundary["was"], boundary["becomes"]) == (figure, was, becomes)
        assert (f"      sampled on 400 paths at seed 7: as it rises past {figure}, the "
                f"decisiveness verdict changes from {was} to {becomes}") in lines, key
        sides = [end["best"] for end in _sweep_states(
            run.path, key, [boundary["value"], boundary["upper_end"]], True)]
        assert sides[0] != sides[1], key
        assert not any(r["verdict_field"] == "decisive" for r in row["refused_boundaries"]), key


@claims("A table's rows print resolved rows first, each group largest first")
def test_the_rows_print_resolved_first_each_group_largest_first():
    """Over every render: the spread table's rows are the JSON's sorted
    resolved first, each group by its `alone` point, largest first; the level
    table's resolved first, each group by the size of its shift before
    rounding. Some table on the engine's runs prints in an order other than
    the JSON's, and some holds both groups, so neither rule holds by accident.
    *Kills it:* a table printed in the JSON's order, a group sorted smallest
    first, or the unresolved rows first."""
    reordered = mixed = 0
    for render in sentences.renders():
        block = render.block
        if "refusal" in block:
            continue
        tables = [(block["level"]["rows"], "LEVEL_ROW", lambda r: abs(_shift(r)))]
        if "rows" in block["spread"]:
            tables.append((block["spread"]["rows"], "SPREAD_ROW", _point))
        for rows, template, size in tables:
            want = sorted(rows, key=lambda r: (not r["resolved"], -size(r)))
            labels = [dc.channel(r["channel_id"]).label for r in want]
            assert _printed_labels(render, template) == labels, (render.name, template)
            if render.engine:
                reordered += want != rows
                mixed += len({r["resolved"] for r in rows}) == 2
    assert reordered and mixed


@claims("A dollar figure prints its sign before the dollar sign")
def test_a_dollar_figure_carries_its_sign_before_the_dollar_and_a_zero_none():
    """Over every line of every render, no sign after a dollar sign and no
    signed zero; and on figures a fraction of a dollar either side of zero,
    in the lines and in a reason's figures at two decimals, the zero prints
    unsigned, a shift's included: a zero has no side.
    *Kills it:* the sign put after the dollar sign, or a zero printed with
    the sign of what rounded to it."""
    for render in sentences.renders():
        for line in render.text.splitlines():
            assert "$-" not in line, (render.name, line)
            for token in re.findall(r"[+-]\$[\d,.]+", line):
                assert re.search(r"[1-9]", token), (render.name, line)
    assert [dt._money(v) for v in (-0.4, 0.4, -0.6, -1234.6, 1234.6)] == [
        "$0", "$0", "-$1", "-$1,235", "$1,235"]
    assert [dt._shift(v) for v in (-0.3, 0.3, -0.0, -2.5, 2.5)] == [
        "$0", "$0", "$0", "-$2", "+$2"]
    assert [dt._shift(v, 2) for v in (-0.004, 0.004, 0.006)] == ["$0.00", "$0.00", "+$0.01"]
    assert [dr.signed_dollars(v, 2) for v in (-0.004, 0.004, -0.005001, -8002.31)] == [
        "$0.00", "$0.00", "-$0.01", "-$8,002.31"]
    outcome = hh.uncertainty_surface(mean_margin=-0.4)
    text = dt.format_decomposition(outcome)
    assert ", mean $0 and s.d." in text


# ---------------------------------------------------------------------------
# Which figures move with the sample
# ---------------------------------------------------------------------------

# Every numeric leaf of the block, by the list the contract files it under.
# The key is the leaf's path with list positions dropped.
# `test_the_partition_of_the_numbers_is_whole` enumerates every leaf of two
# runs against this map, and checks each name against the contract's own list.
PARTITION = {
    "config": {
        "reversal.exact[].bracket_low": "`bracket_low`",
        "reversal.exact[].bracket_high": "`bracket_high`",
        "reversal.exact[].probe_paths": "`probe_paths`",
        "reversal.exact[].boundaries[].curve_paths": "`curve_paths`",
        "reversal.exact[].boundaries[].value#solved": "a solved boundary's `value` and "
                                                      "`upper_end`",
        "reversal.exact[].boundaries[].upper_end#solved": "a solved boundary's `value` and "
                                                          "`upper_end`",
        "level.all_frozen_margin": "`all_frozen_margin`",
        "level.all_frozen_deviation": "`all_frozen_deviation`",
        "spread.structural_zeros[].move_threshold": "`move_threshold`",
    },
    "fixed": {
        "level.all_frozen_path_spread": "`all_frozen_path_spread`, which is `0.0`",
    },
    "sample": {
        "paths": "`paths`",
        "level.paths": "`level.paths`",
        "spread.structural_zeros[].measured_paths": "`measured_paths`",
        "mean_margin": "`mean_margin`",
        "sd_margin": "`sd_margin`",
        **{f"spread.rows[].{name}{bound}": "every share, flip, gap, sum and residual in"
           for name in ("alone", "with_interaction", "provisional_alone",
                        "provisional_with_interaction", "flip", "interaction_gap")
           for bound in ("", "_ci.low", "_ci.high")},
        **{f"spread.interaction.{name}{bound}": "every share, flip, gap, sum and residual in"
           for name in ("first_order_sum", "residual")
           for bound in ("", "_ci.low", "_ci.high")},
        "level.futures_margin": "`futures_margin`",
        "level.prob_best_base": "`prob_best_base`",
        "level.accounted_for": "`accounted_for`",
        "level.rows[].delta": "every level row's shift",
        "level.rows[].provisional_delta": "every level row's shift",
        "level.rows[].se": "`se`",
        "level.rows[].prob_best_frozen": "`prob_best_frozen`",
        "reversal.exact[].boundaries[].seed": "`seed`, which is the seed",
        "reversal.exact[].boundaries[].value#sampled": "a sampled boundary's `value` and "
                                                       "`upper_end`",
        "reversal.exact[].boundaries[].upper_end#sampled": "a sampled boundary's `value` and "
                                                           "`upper_end`",
        "reversal.exact[].boundaries[].confirming_probabilities[][]":
            "every probability in a `*_probabilities` pair",
        "reversal.exact[].boundaries[].curve_probabilities[][]":
            "every probability in a `*_probabilities` pair",
        "reversal.exact[].max_path_deviation_over_sd": "`max_path_deviation_over_sd`",
    },
    "ids": {
        "live_channel_ids[]": "`live_channel_ids`",
        "max_paths": "`max_paths`",
        "spread.rows[].channel_id": "every row's and every `structural_zeros` row's `channel_id`",
        "level.rows[].channel_id": "every row's and every `structural_zeros` row's `channel_id`",
        "spread.structural_zeros[].channel_id":
            "every row's and every `structural_zeros` row's `channel_id`",
        "spread.leading_channel_id": "`leading_channel_id`",
        "level.leading_channel_id": "`leading_channel_id`",
        "spread.unresolved_top_channel_id": "`unresolved_top_channel_id`",
        "level.unresolved_top_channel_id": "`unresolved_top_channel_id`",
        "spread.interaction_channel_ids[]": "`interaction_channel_ids`",
        "refusal.channel_id": "a whole-block refusal's `channel_id`",
    },
}
_LIST_OPENERS = {
    "config": "- The same at any seed and any `N`, properties of the config:",
    "fixed": "- The same on every block emitted:",
    "sample": "- Figures that change with the seed or with `N`:",
    "ids": "- Ids and counts measured on these futures, which two samples can share:",
}


def _numeric_leaves(node, path="", stable=""):
    """`(filed path, stable path, value)` for every number in the block. The
    stable path names list items by what they are (a channel, a key, a field)
    so that two runs' leaves meet even where a list's length differs."""
    if isinstance(node, bool) or node is None or isinstance(node, str):
        return
    if isinstance(node, (int, float)):
        yield path, stable, node
        return
    if isinstance(node, dict):
        # a boundary's two ends are filed by the kind of boundary they bound
        kind = ""
        if "verdict_field" in node and "value" in node:
            kind = "#sampled" if "seed" in node else "#solved"
        for key, value in node.items():
            filed = f"{path}.{key}" if path else key
            if key in ("value", "upper_end") and kind:
                filed += kind
            yield from _numeric_leaves(value, filed, f"{stable}.{key}")
        return
    seen: dict = {}
    for position, item in enumerate(node):
        name = position
        if isinstance(item, dict):
            base = (item.get("channel_id"), item.get("key"), item.get("label"),
                    item.get("verdict_field"), item.get("kind"))
            seen[base] = seen.get(base, -1) + 1
            name = (*base, seen[base])
        yield from _numeric_leaves(item, f"{path}[]", f"{stable}[{name}]")


@claims("**Which figures move with the sample.**",
        "Every number in the block, and in a whole-block refusal, is in exactly one",
        "- The same at any seed and any `N`, properties of the config:",
        "- The same on every block emitted:",
        "- Figures that change with the seed or with `N`:",
        "- Ids and counts measured on these futures, which two samples can share:",
        "Of the fields that are words,")
def test_the_partition_of_the_numbers_is_whole(runs, tmp_path):
    """§0.1 item 46: a universal sentence is pinned by enumerating every case.
    Two runs of the fixture that differ in seed AND in `N` (42 at 300, 7 at
    400): every numeric leaf of both is filed in exactly one list, every name
    the map files it under is in that list's sentence of the contract, and the
    lists hold: config leaves equal between the runs, fixed leaves at their
    one value, and every field of the sample list moving on at least one of its
    leaves. Ids and counts may coincide, and the contract says so.
    *Kills it:* a leaf the contract does not file, a name filed in the wrong
    list, or a config figure that moves.

    The refusal forms are enumerated too (§0.1 item 48): every numeric leaf
    of every whole-block refusal the sentence tests render, and of the
    `one_channel` refusal a rare lease reset gives on 40 futures and not on
    5,000, whose `channel_id` is a fact about those 40."""
    section = " ".join(_section().split())
    for group, names in PARTITION.items():
        opener = " ".join(_LIST_OPENERS[group].split())
        start = section.index(opener)
        end = section.index(" - ", start + len(opener)) if group != "ids" else \
            section.index("Of the fields that are words", start)
        sentence = section[start:end]
        for name in names.values():
            assert " ".join(name.split()) in sentence, (group, name)
    filed = {path: group for group, names in PARTITION.items() for path in names}
    a_run = runs["fixture"]
    reseeded = copy.deepcopy(a_run.raw)
    reseeded["simulation"]["random_seed"] = 7
    b_run = Run(reseeded, "400").materialise(tmp_path / "seed_and_count")
    a = {stable: (path, value) for path, stable, value in _numeric_leaves(a_run.block)}
    b = {stable: (path, value) for path, stable, value in _numeric_leaves(b_run.block)}
    paths = {path for path, _ in a.values()} | {path for path, _ in b.values()}
    assert sorted(paths - set(filed)) == []
    config = {stable for stable, (path, _) in {**a, **b}.items() if filed[path] == "config"}
    assert config <= set(a) & set(b)
    for stable in config:
        assert a[stable] == b[stable], (stable, a[stable], b[stable])
    for stable, (path, value) in {**a, **b}.items():
        if filed[path] == "fixed":
            assert value == 0.0, path

    def values(leaves, field):
        return sorted(value for path, value in leaves.values() if path == field)

    still = [field for field in paths if filed[field] == "sample"
             and values(a, field) == values(b, field)]
    assert still == []
    # the refusal forms: every leaf filed, and the one id there a sample fact
    one = Run(RARE_RESET_ONE, "40").materialise(tmp_path / "rare_one_40")
    many = Run(RARE_RESET_ONE, "5000").materialise(tmp_path / "rare_one_5000")
    refusals = [r.block for r in sentences.renders() if "refusal" in r.block]
    refusals.append(one.block)
    assert {r["refusal"]["code"] for r in refusals} >= {
        "no_futures", "single_option", "too_few_futures", "budget", "no_spread",
        "one_channel", "degenerate_resample"}
    # the refusals filed with the sample: every code but the three decided
    # before anything is priced
    words = section[section.index("Of the fields that are words"):]
    start = words.index("once the block's futures are priced (")
    priced = words[start:words.index(")", start)]
    assert set(re.findall(r"`(\w+)`", priced)) - {"k"} == set(dc.REFUSAL_CODES) - {
        "no_futures", "single_option", "too_few_futures"}
    leaves = sorted({path for block in refusals for path, _, _ in _numeric_leaves(block)})
    assert leaves == ["refusal.channel_id"]
    assert sorted(set(leaves) - set(filed)) == []
    assert one.block["refusal"]["code"] == "one_channel"
    assert "refusal" not in many.block
    assert one.block["refusal"]["channel_id"] in many.block["live_channel_ids"]
    assert len(many.block["live_channel_ids"]) > 1
    # the words the contract files with the config
    assert [r["widths"] for r in a_run.block["spread"]["rows"]] == [
        r["widths"] for r in b_run.block["spread"]["rows"]]

    # a refused boundary's words: the config's on the two solved fields under
    # the codes the contract names, and the sample's otherwise
    named = re.search(r"a refused boundary's `code` and `reason` are the config's where its "
                      r"field is `best` or `runner_up` and its code (?P<codes>.+?), and the "
                      r"sample's otherwise;", words)
    config_codes = set(re.findall(r"`(\w+)`", named["codes"]))
    # the codes decided on the central case alone, with no path read
    assert config_codes == {"unchanged", "not_on_axis", "scan_mismatch", "not_bracketed"}

    def config_refusal(f):
        return f["verdict_field"] in ("best", "runner_up") and f["code"] in config_codes

    def config_words(block):
        reversal = block["reversal"]
        return ([(r["key"], r["bracket_source"], r["path_note"],
                  [(b["verdict_field"], b["was"], b["becomes"], b["further_changes"],
                    b["formatted"]) for b in r["boundaries"] if "seed" not in b],
                  [(f["verdict_field"], f["code"], f["reason"]) for f in r["refused_boundaries"]
                   if config_refusal(f)])
                 for r in reversal["exact"]],
                reversal["no_distance_code"], reversal["no_distance_reason"])

    assert config_words(a_run.block) == config_words(b_run.block)
    assert any(words[-1] for words in config_words(a_run.block)[0])
    assert any(words[2] for words in config_words(a_run.block)[0])
    # the refused boundaries filed with the sample: on 150 futures, one
    # refused at one seed is not refused at another
    few = copy.deepcopy(a_run.raw)
    few["simulation"]["num_sims"] = 150
    one = Run(few, "100").materialise(tmp_path / "seed_42")
    few["simulation"]["random_seed"] = 10
    other = Run(few, "100").materialise(tmp_path / "seed_10")

    def sample_words(block):
        return [(r["key"], f["verdict_field"], f["code"], f["reason"])
                for r in block["reversal"]["exact"] for f in r["refused_boundaries"]
                if not config_refusal(f)]

    assert config_words(one.block) == config_words(other.block)
    assert sample_words(one.block) != sample_words(other.block)
    # and a boundary whose bracket's ends read other states, at a second seed
    tie = runs["three_way_tie"]
    reseeded_tie = copy.deepcopy(tie.raw)
    reseeded_tie["simulation"]["random_seed"] = 42
    tie_again = Run(reseeded_tie, "100").materialise(tmp_path / "tie_at_42")
    assert config_words(tie.block) == config_words(tie_again.block)
    assert {f[1] for words in config_words(tie.block)[0] for f in words[-1]} >= {"not_bracketed"}


@claims("A figure that changes with `simulation.random_seed` or with `N` is a property")
def test_which_figures_move_with_the_seed_and_the_path_count(runs, tmp_path):
    run = runs["fixture"]
    reseeded = copy.deepcopy(run.raw)
    reseeded["simulation"]["random_seed"] = 7
    other_seed = Run(reseeded, "300").materialise(tmp_path / "seed")
    other_count = Run(run.raw, "400").materialise(tmp_path / "count")
    a = run.block
    for b in (other_seed.block, other_count.block):
        assert (a["max_paths"], a["live_channel_ids"]) == (b["max_paths"], b["live_channel_ids"])
        assert [r["widths"] for r in a["spread"]["rows"]] == [
            r["widths"] for r in b["spread"]["rows"]]
        assert _without_counts(a["spread"]["structural_zeros"]) == _without_counts(
            b["spread"]["structural_zeros"])
        assert a["level"]["all_frozen_margin"] == b["level"]["all_frozen_margin"]
        assert a["level"]["all_frozen_deviation"] == b["level"]["all_frozen_deviation"]
        assert a["mean_margin"] != b["mean_margin"] and a["sd_margin"] != b["sd_margin"]
        assert _rows(a)[0]["flip"] != _rows(b)[0]["flip"]
        assert a["level"]["futures_margin"] != b["level"]["futures_margin"]
    # the rows measured on the block's own futures are the spread register's,
    # stating the count they were measured on (§0.1 item 48)
    assert other_count.block["paths"] == 400
    assert [z["measured_paths"] for z in other_count.block["spread"]["structural_zeros"]
            if z["kind"] == "dead_draw"] == [400]
    # one config, two path counts: the spread refuses at 200 and prints at 2,000
    fewer = Run(NEAR_ALL, "200").materialise(tmp_path / "near")
    assert fewer.block["spread"]["refusal"]["code"] == "no_sign_variation"
    assert "rows" in runs["near_all"].block["spread"]


def _without_counts(zeros):
    return [{k: v for k, v in z.items() if k != "measured_paths"} for z in zeros]


# ---------------------------------------------------------------------------
# The other homes point here, and restate nothing
# ---------------------------------------------------------------------------

# A measured figure written as text: a dollar amount, a percentage, a figure
# with a thousands separator, one in scientific notation, one at two or more
# decimals (a rendered `0.00` is a format, not a figure), or a multiple.
_FIGURE = re.compile(r"\$\s?\d|\d%|\d,\d{3}|\d(?:\.\d+)?e-?\d|\b\d+\.(?!0+\b)\d{2,}\b"
                     r"|\b\d+(?:\.\d+)?x\b")
_GATES = REPO / ".claude" / "skills" / "hde" / "references" / "gates.md"


def _between(text, start, stop):
    begin = text.index(start)
    end = text.find(stop, begin + len(start))
    return text[begin:] if end == -1 else text[begin:end]


# gates.md §10, whole: its heading, its opening paragraph and every one of its
# bullets (§0.1 item 52). Text appended after a pinned fragment was invisible
# to a fragment test, so the section is enumerated, its heading included.
_GATES_10_HEADING = "## 10. `--decompose`: quote the block, and read its meaning in the contract"
_GATES_10_OPENING = (
    "What the block prints, line by line, is written in "
    "`docs/reference/API_CONTRACT.md` § The `decomposition` block, under \"The text "
    "block\". Explaining the lines is your job, and that section is what you explain "
    "them from. So:")
_GATES_10_BULLETS = (
    "Quote the block's lines verbatim, with their figures and their `[...]` tags.",
    "Never quote a row of THE SPREAD's table without the same channel's row from THE "
    "LEVEL beside it.",
    "Where the block prints `not resolved`, say it is not resolved, and quote what the "
    "block prints after the words.",
    "Read what a figure, a refusal code or a path count means in the contract section "
    "above before you explain it; never explain it from memory or from this file.",
    "Name a share by the column it is printed under, never \"importance\" or a "
    "\"contribution to the answer\".",
    "A refusal, of the whole block, of the spread, of a boundary or of the search for "
    "one, is that run's finding: quote its line as printed.",
)


def _gates_10(text):
    """`(heading, opening, bullets)` of gates.md §10, each
    whitespace-normalised, and anything else the section holds."""
    section = _between(text, "## 10. `--decompose`", "\n## ")
    heading, body = section.split("\n", 1)
    blocks = [block for block in re.split(r"\n\s*\n", body) if block.strip()]
    opening = " ".join(blocks[0].split())
    bullets, rest = [], []
    for block in blocks[1:]:
        for item in re.split(r"\n(?=- )", block.strip()):
            if item.startswith("- "):
                bullets.append(" ".join(item[2:].split()))
            else:
                rest.append(" ".join(item.split()))
    return " ".join(heading.split()), opening, tuple(bullets), rest


def test_the_skill_is_behavioural_and_restates_nothing():
    """gates.md §10 is what an assistant loads before it quotes the block. It
    once carried the fixture's figures, which went stale when the engine's
    changed, and then the block's own rules. It carries instructions on how
    to quote and a pointer here, and no figure, rule or field meaning (§0.1
    item 32). It is pinned whole (§0.1 item 52): its opening and its bullets
    are these and no others, so a bullet appended or a qualifier added to one
    fails here.
    *Kills it:* restoring a figure, a resolution rule, a path count or a
    field's meaning to §10, dropping one of its instructions, or appending a
    bullet or a clause — both appended below fail it."""
    text = _GATES.read_text(encoding="utf-8")
    section = _between(text, "## 10. `--decompose`", "\n## ")
    assert _gates_10(text) == (_GATES_10_HEADING, _GATES_10_OPENING, _GATES_10_BULLETS, [])
    appended_bullet = text.replace(
        "quote its line as printed.\n",
        "quote its line as printed.\n"
        "- When every future names the same winner, only the spread table refuses.\n")
    qualified = text.replace("  THE LEVEL beside it.\n",
                             "  THE LEVEL beside it, unless the share resolved.\n")
    headed = text.replace(_GATES_10_HEADING, _GATES_10_HEADING + ", unless a share resolved")
    for mutant in (appended_bullet, qualified, headed):
        assert mutant != text and _gates_10(mutant) != _gates_10(text)
    assert not _FIGURE.search(section), _FIGURE.search(section)
    for restated in ("Sobol", "variance", "s.e.", "standard error", "bootstrap",
                     "num_sims", "2000", "2,000", "min(", "percentile", "point estimate",
                     "resolves when", "twice", "first-order", "cheapest in"):
        assert restated not in section, restated


def test_the_glossary_and_the_prompts_point_here():
    """ARCHITECTURE.md's decomposition glossary gave the uncentred Saltelli
    numerator the engine does not compute, and PROMPTS.md said a refusal meant
    "one source of spread, or none" beside a refusal with two channels live.
    Each now points at this section and restates none of it.
    *Kills it:* a table row, a formula or a figure back in either."""
    architecture = _between(
        (REPO / "docs" / "reference" / "ARCHITECTURE.md").read_text(encoding="utf-8"),
        "### Which risk decides it — `decomposition`", "\n### ")
    assert "`docs/reference/API_CONTRACT.md`" in architecture
    assert "`tests/test_decomposition_contract_doc.py`" in architecture
    assert ("The block's three registers are the spread, the level and the reversal "
            "register.") in " ".join(architecture.split())
    assert "\n|" not in architecture and "mean(" not in architecture
    assert not _FIGURE.search(architecture)
    prompts = (REPO / "PROMPTS.md").read_text(encoding="utf-8")
    bullet = _between(prompts, "- *\"Which of these risks actually decides it?\"*", "\n- ")
    assert "`docs/reference/API_CONTRACT.md` § The `decomposition` block" in bullet
    assert "refusals included" in bullet
    assert "its spread, its level and its reversal register, as printed" in " ".join(
        bullet.split())
    assert not _FIGURE.search(bullet)


def _docstrings_and_comments(path):
    """`(where, text)` for every docstring and every comment of one module."""
    import ast
    import io
    import tokenize
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    out = []
    for node in [tree] + [n for n in ast.walk(tree) if isinstance(
            n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]:
        doc = ast.get_docstring(node, clean=True)
        if doc is not None:
            out.append((getattr(node, "name", "<module>"), " ".join(doc.split())))
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            out.append((f"line {token.start[0]}", token.string))
    return out


# The six kinds, as the contract names them, and a field's meaning written
# out: the two restatements §0.1 item 52 found in the implementing modules.
_SIX_KINDS = ("a heading", "a figure row", "a crossing", "a path note", "a refusal",
              "a row with no place", "a row of `structural_zeros`")
_DEFINES = re.compile(r"`(?P<field>\w+)` (?:is|are|means|reads) (?:what|how|whether|the "
                      r"fraction|the mean|the largest|a fraction|one of|the share)\b"
                      r"|\bjust (?:below|above) (?:the |`)?value")


def _restatements(prose, fields):
    found = []
    for where, text in prose:
        if sum(kind in text for kind in _SIX_KINDS) >= 3:
            found.append((where, "the six kinds"))
        for m in _DEFINES.finditer(text):
            if m["field"] is None or m["field"] in fields:
                found.append((where, m.group(0)))
    return found


def test_the_implementing_modules_point_at_the_contract_for_kinds_and_meanings():
    """§0.1 item 52: `decomposition_text` and `decomposition_run` point at the
    contract for the six kinds of line and for what a field means. Their
    module docstrings name the contract, and no docstring or comment of theirs
    lists the kinds or writes out a field of the block as what it is — the
    formatter's module docstring once listed the six kinds, and a helper's
    once said what a field read.
    *Kills it:* either restatement put back, as the two below are."""
    fields = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                fields.add(key)
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    from hde.serialization import decomposition_to_dict
    for build in (hh.uncertainty_surface, hh.seven_channel_other_household,
                  hh.two_channel_option_state):
        walk(decomposition_to_dict(build()))
    assert {"flip", "move_threshold", "alone", "tag", "accounted_for"} <= fields
    for module in (dt, dr):
        path = pathlib.Path(module.__file__)
        assert "`docs/reference/API_CONTRACT.md`" in module.__doc__, path.name
        assert _restatements(_docstrings_and_comments(path), fields) == [], path.name
    listed = [("<module>", "Every line is exactly one of the six kinds the contract lists: "
               "a heading, a figure row, a crossing, a path note, a refusal, or a row "
               "with no place in either register.")]
    assert _restatements(listed, fields) == [("<module>", "the six kinds")]
    defined = [("_spread_cells", "`flip` is the fraction of futures in which re-drawing "
                "the channel changes the sign of the margin.")]
    assert [text for _, text in _restatements(defined, fields)] == ["`flip` is the fraction"]


def test_the_decomposition_modules_docstrings_carry_no_measured_figure():
    """A figure in a docstring is a second statement of what a run prints, with
    nothing to keep it true: `± $5,383` sat in one beside an engine printing
    `± $5,385`. The modules' docstrings name the test that pins a figure
    instead.
    *Kills it:* a measured figure back in any module, class or function
    docstring of `hde/decomposition*.py`."""
    import ast
    found = []
    for path in sorted((REPO / "src" / "hde").glob("decomposition*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes = [tree] + [n for n in ast.walk(tree) if isinstance(
            n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        for node in nodes:
            doc = ast.get_docstring(node, clean=False) or ""
            for hit in _FIGURE.finditer(doc):
                found.append((path.name, getattr(node, "name", "<module>"), hit.group(0)))
    assert not found, found
