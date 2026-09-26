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
import inspect
import json
import math
import pathlib
import re
import sys
import types

import numpy as np
import pytest
import yaml

from hde import break_even as be
from hde import decomposition as dc
from hde import decomposition_math as dm
from hde import decomposition_run as dr
from hde import decomposition_text as dt
from hde import monte_carlo
from hde.break_even import REVERSAL_GATE_TOLERANCE, reversal_admission
from hde.config import load_config_dict, single_path_run
from hde.deterministic import renewal_segments_for
from hde.monte_carlo import run_monte_carlo
from hde.rates import effective_mortgage_rate
from hde.sweep import flattened_path_note

from tests import test_decomposition_sentences as sentences
from tests.decomposition_oracles import freeze_moves, oracle_drawn, oracle_moves, threshold
from tests.decomposition_runs import (
    CONDO_ONLY, CONTRACT, FIXTURE, INCOME, MIN_INTERACTION, MONTREAL, MORTGAGE, NEAR_ALL,
    NO_REACH, REPO, THIRD_FAR, Run, _block_text, _cli, _load, _strict, _sweep_states,
    corpus)
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

@claims("This section is the one prose home for the block",
        "checks each sentence here against a run",
        "Design record:")
def test_the_frame_points_at_files_that_exist():
    assert pathlib.Path(__file__).name == "test_decomposition_contract_doc.py"
    assert (REPO / "docs" / "specs" / "2026-09-22-which-risk-decides-it.md").is_file()
    assert "test_decomposition_contract_doc.py" in _section()


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
        "The level register prices the first `min(N, 2000)` of those futures",
        "The reversal register prices none of them.",
        "It reads the run's own Monte Carlo sample and re-simulates the config")
def test_the_assembler_says_whose_each_probability_is(runs):
    """`decomposition_run`'s docstring says which probabilities the assembler
    takes itself and on which futures, and which are `break_even`'s. Each
    clause is checked on runs whose N differs from `simulation.num_sims`.
    *Kills it:* a docstring that files the reversal register's probabilities
    under the assembler's, or under `f`'s sign, or on the block's N."""
    said = " ".join(dr.__doc__.split())
    for fragment in (
            "frequencies of `f`'s sign on futures it priced: over all N for whether "
            "the futures sit on both sides of the line, and over the level "
            "register's first paths for its `prob_best_*`",
            "The reversal register's probabilities are not this module's: "
            "`break_even` takes them per option, on the run's own Monte Carlo sample "
            "and on re-simulations, at the config's `simulation.num_sims`"):
        assert fragment in said, fragment
    fixture = runs["fixture"]
    f_a = fixture.f_a()
    level = fixture.block["level"]
    assert level["prob_best_base"] == float(np.mean(f_a[:level["paths"]] > 0.0))
    mortgage = runs["mortgage"]
    assert float(np.mean(mortgage.f_a() > 0.0)) == 1.0
    assert mortgage.block["spread"]["refusal"]["reason"] == (
        f"{mortgage.doc['verdict']['best']} is cheapest in all "
        f"{mortgage.paths():,} of these futures")
    num_sims = fixture.spec.simulation.num_sims
    priced = {o for o in ("condo", "house", "rent") if fixture.doc["deterministic"][o]}
    boundaries = [b for row in fixture.block["reversal"]["exact"] for b in row["boundaries"]]
    sampled = [b for b in boundaries if "curve_paths" in b]
    assert sampled and fixture.paths() != num_sims
    for b in sampled:
        assert b["curve_paths"] == num_sims
        assert {o for o, _ in b["curve_probabilities"]} == priced
    for b in boundaries:
        assert {o for o, _ in b["confirming_probabilities"]} == priced


def test_how_many_futures_each_register_prices(runs):
    """The fixture at `--decompose=300`: the spread and the level at 300, the
    reversal register at the config's 2,000 and seed 42, its gate at 200. At
    4,000 the level stops at 2,000; bare, `N` is the config's own count. That
    the reversal register is the same at another `N` is checked in
    `test_which_figures_move_with_the_seed_and_the_path_count`."""
    fixture = runs["fixture"]
    block = fixture.block
    assert block["paths"] == 300 == fixture.f_a().size
    assert block["level"]["paths"] == 300
    # which streams draw and which channels are live: on the same 300
    assert [z["measured_paths"] for z in block["reversal"]["structural_zeros"]
            if z["kind"] == "dead_draw"] == [300]
    sim = fixture.raw["simulation"]
    assert (sim["num_sims"], sim["random_seed"]) == (2000, 42)
    sampled = [b for row in block["reversal"]["exact"] for b in row["boundaries"]
               if "seed" in b]
    assert sampled and all((b["curve_paths"], b["seed"]) == (2000, 42) for b in sampled)
    assert [row["probe_paths"] for row in block["reversal"]["exact"]] == [200, 200]
    assert runs["advanced_4000"].block["level"]["paths"] == 2000
    assert runs["advanced_4000"].block["paths"] == 4000
    code, out, _ = _cli("--decompose", runs["mortgage"].path, "--json")
    bare = _strict(out)["decomposition"]
    assert bare["paths"] == runs["mortgage"].spec.simulation.num_sims != 200
    # the re-simulation behind a solved boundary is the config's own run
    row = block["reversal"]["exact"][0]
    solved = next(b for b in row["boundaries"] if "seed" not in b)
    again = run_monte_carlo(be.load_at(fixture.raw, row["key"], solved["value"]))
    assert [list(p) for p in solved["confirming_probabilities"]] == [
        [o, getattr(again, f"prob_{o}_cheapest")] for o in ("condo", "house", "rent")]


@claims("Every number in the block is finite, so a strict JSON parser",
        "The one figure that can be is",
        "A measured zero stays `0.0`.")
def test_numbers(runs):
    """Strict parsing is `Run`'s own; here the zero half — a real 0.0 is not
    turned into `null` by the guard that nulls a non-finite figure — and the
    one field that can be null. Its non-finite half is driven end to end in
    `test_decomposition_report.py::TestTheRealAssemblerThroughTheFlag::
    test_a_gate_that_cannot_measure_says_so_in_words_and_in_strict_json`."""
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
               "mean_margin", "sd_margin", "value", "max_path_deviation_over_sd",
               "low", "high", "first_order_sum", "residual"}
    assert not (set(nulls) & figures)


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
    for raw in (TWINS, THIRD_FAR, NO_REACH):
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
    doc, _, _, _ = _refusal(tmp_path, _load(MORTGAGE), "39")
    assert doc["refusal"] == {"code": "too_few_futures",
                              "reason": "39 futures were asked for, below the minimum of 40"}
    doc, _, _, _ = _refusal(tmp_path, _load(MORTGAGE), "40")
    assert "refusal" not in doc and doc["paths"] == 40


@claims("| `freeze_leak` |", "| `identity_failed` |")
def test_the_identity_refusals_forced_on_a_real_run(runs, monkeypatch):
    """Neither fires on a correct engine, so each is forced through the CLI on
    the fixture at 40 paths with the real engine and one run moved: a mask
    that lets one channel escape (the paths then differ), and the all-frozen
    run shifted by one constant (they agree, off the central case). Each
    reason is re-derived from that same run."""
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
    assert _strict(out)["decomposition"] == {"refusal": {"code": "freeze_leak", "reason": (
        f"with every channel frozen, the margins of the 40 paths differ by up to "
        f"${spread:,.6g}")}}
    with monkeypatch.context() as patched:
        TestTheIdentityIsGated._offset_all_frozen(patched, 0.01)
        code, out, _ = _cli(fixture.path, "--decompose=40", "--json")
        frozen = dr.margin_per_path(dr._run(spec, dr.MATRIX_A, freeze=dr.ALL_CHANNEL_IDS),
                                    verdict.best)
    budget = dr.identity_budget(det, verdict)
    assert float(np.ptp(frozen)) == 0.0
    apart = abs(float(frozen[0]) - verdict.margin_pv)
    assert apart > budget
    assert _strict(out)["decomposition"] == {"refusal": {"code": "identity_failed", "reason": (
        f"with every channel frozen, the 40 paths price a margin of ${frozen[0]:,.2f} "
        f"against the central case's ${verdict.margin_pv:,.2f}, ${apart:.3g} apart, "
        f"above the ${budget:.3g} this check allows")}}


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
        "A live channel can move only an option that never enters the margin")
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
    dead = [z for z in block["reversal"]["structural_zeros"] if z["kind"] == "dead_draw"]
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
    for run in runs.values():
        assert set(run.block) == {"paths", "max_paths", "live_channel_ids", "mean_margin",
                                  "sd_margin", "spread", "level", "reversal"}
        assert "verdict" not in json.dumps(list(run.block))


@claims("`paths` is `N`.",
        "`max_paths` is the largest `N` the budget admits")
def test_paths_and_max_paths(runs):
    """`max_paths` at the count of streams that drew: the live channels and the
    `dead_draw` rows' streams, which is the held-generator instrument's count."""
    for name, run in runs.items():
        dead = [z for z in run.block["reversal"]["structural_zeros"]
                if z["kind"] == "dead_draw"]
        k = len(run.block["live_channel_ids"]) + len(dead)
        assert k == len(oracle_drawn(run.spec)), name
        assert run.block["max_paths"] == dr.largest_affordable_paths(k)
        assert run.block["paths"] <= run.block["max_paths"]
        assert run.f_a().size == run.block["paths"]
        if run.extra:
            assert run.block["paths"] == int(run.extra[0]), name


@claims("The block's figures are taken on `f`",
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
               "interaction_channel_ids"}


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
        assert run.block["level"]["rows"] and "reversal" in run.block
        best = run.doc["verdict"]["best"]
        reason = (f"{best} is cheapest in all {run.paths():,} of these futures" if side
                  else f"{best} is cheapest in none of these {run.paths():,} futures")
        assert run.block["spread"] == {"refusal": {"code": "no_sign_variation",
                                                   "reason": reason}}


@claims("Each row carries `channel_id`, `channel`, `label`, `resolved`, `flip`",
        "(`resolved: false`), never both.")
def test_a_row_carries_one_set_of_share_keys(runs):
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
    seen_negative_resolved = False
    for name in ("fixture", "showcase", "three", "min", "advanced"):
        for row in _rows(runs[name].block):
            inside = 0.0 <= _point(row) <= 1.0 and 0.0 <= _together(row) <= 1.0
            assert row["resolved"] == inside, (name, row["channel"])
            ci = row["alone_ci"] if row["resolved"] else row["provisional_alone_ci"]
            seen_negative_resolved |= row["resolved"] and ci["low"] < 0
    assert seen_negative_resolved      # an unclamped interval below 0 on a resolved row


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
        "A width is a stated input that sizes the row's draws.",
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
                assert set(width) == {"key", "formatted", "source", "anchor", "note"}
                assert width["source"] in ("user", "assistant", "anchor", "unattributed")
                assert run.spec.sources.classify(width["key"]) == width["source"]
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


@claims("`interaction_channel_ids` are the rows whose `interaction_gap_ci` lies")
def test_the_interacting_rows(runs):
    seen = False
    for name in ("fixture", "showcase", "three", "min", "advanced", "advanced_4000"):
        spread = runs[name].block["spread"]
        assert spread["interaction_channel_ids"] == [
            r["channel_id"] for r in spread["rows"] if r["interaction_gap_ci"]["low"] > 0]
        seen |= bool(spread["interaction_channel_ids"])
    assert seen and not runs["fixture"].block["spread"]["interaction_channel_ids"]


@claims("`interaction`: `resolved`, `first_order_sum`",
        "When that interval lies entirely below 1 it is")
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
        "Each row carries `channel_id`, `channel`, `label`, `resolved`, `se`",
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

@claims("`reversal` — what would have to change for the verdict to change",
        "It carries `exact`, `estimated`, `structural_zeros` and",
        "The search covers a financed option's `mortgage_rate` and")
def test_what_the_reversal_register_searches(runs):
    fixture = runs["fixture"].block["reversal"]
    assert set(fixture) == {"exact", "estimated", "structural_zeros", "no_distance_reason"}
    assert [r["key"] for r in fixture["exact"]] == ["house.mortgage_renewal_rates",
                                                    "house.mortgage_rate"]
    assert [r["key"] for r in runs["mortgage"].block["reversal"]["exact"]] == [
        "house.mortgage_rate"]
    for name in ("fixture", "mortgage"):
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            admitted, _ = reversal_admission(run.raw, row["key"], row["bracket_high"])
            assert admitted
    for name in ("advanced", "showcase", "three", "min"):
        block = runs[name].block["reversal"]
        assert block["exact"] == [] and block["estimated"] == []
        raw = runs[name].raw
        assert not any(isinstance(raw.get(o), dict) and (
            "mortgage_rate" in raw[o] or "mortgage_renewal_rates" in raw[o])
            for o in ("condo", "house"))


@claims("`no_distance_reason` is set exactly when `exact` and `estimated` are both",
        "It is `null` otherwise.")
def test_the_empty_register_states_what_the_config_states(runs):
    seen = 0
    for run in runs.values():
        reversal = run.block["reversal"]
        empty = not (reversal["exact"] or reversal["estimated"])
        assert (reversal["no_distance_reason"] is not None) == empty
        if not empty:
            continue
        seen += 1
        stated = be.reversal_candidates(run.raw)
        if not stated:
            assert reversal["no_distance_reason"] == (
                "this config states no mortgage_renewal_rates or mortgage_rate")
        else:
            for key, _ in stated:
                assert f"this config states {key}, and " in reversal["no_distance_reason"]
    assert seen


@claims("`exact[]` rows:", "A key is exact when moving it to `bracket_high` leaves")
def test_the_exact_rows_and_their_licence(runs):
    from hde.break_even import reversal_gate
    run = runs["mortgage"]
    for row in run.block["reversal"]["exact"]:
        assert set(row) == {"key", "option", "stated_formatted", "stated_source",
                            "bracket_low", "bracket_high", "bracket_source", "probe_paths",
                            "max_path_deviation_over_sd", "boundaries",
                            "refused_boundaries", "references", "path_note"}
        assert row["stated_source"] == run.spec.sources.classify(row["key"])
        gate = reversal_gate(run.raw, row["key"], row["bracket_high"],
                             paths=row["probe_paths"])
        assert gate["licensed"] and gate["others_bit_identical"]
        assert gate["paths"] == row["probe_paths"]
        assert gate["worst_deviation_over_sd"] == row["max_path_deviation_over_sd"]
        assert row["max_path_deviation_over_sd"] <= REVERSAL_GATE_TOLERANCE


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
    ladder is re-priced at its value with one rate at every renewal (the
    solved ones on the deterministic verdict, through the loader the
    register's own sweep reads), and that is the note's whole content."""
    run = runs["fixture"]
    rows = {r["key"]: r for r in run.block["reversal"]["exact"]}
    ladder = rows["house.mortgage_renewal_rates"]
    stated = run.raw["house"]["mortgage_renewal_rates"]
    assert len(set(stated)) > 1
    assert ladder["path_note"] == (
        "each crossing on this key is priced with the stated path "
        f"({', '.join(f'{v:.2%}' for v in stated)}) replaced by one rate at every renewal")
    assert ladder["path_note"] == be.reversal_path_note(run.raw, ladder["key"])
    base = renewal_segments_for(load_config_dict(copy.deepcopy(run.raw)).house)
    assert len({s.rate for s in base[1:]}) > 1
    for boundary in ladder["boundaries"]:
        at = be.load_at(run.raw, ladder["key"], boundary["value"])
        renewals = renewal_segments_for(at.house)[1:]
        assert len(renewals) == len(base) - 1
        assert len({s.rate for s in renewals}) == 1
    assert rows["house.mortgage_rate"]["path_note"] is None
    flat = copy.deepcopy(run.raw)
    flat["house"]["mortgage_renewal_rates"] = [0.05, 0.05, 0.05]
    assert be.reversal_path_note(flat, "house.mortgage_renewal_rates") is None
    flat["house"]["mortgage_renewal_rates"] = [0.05, 0.06]
    assert be.reversal_path_note(flat, "house.mortgage_renewal_rates") is not None
    # the sweep's own note reads the same test of "a path", and is unchanged
    assert flattened_path_note(flat, "house.mortgage_renewal_rates") is not None


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


def test_the_help_says_how_many_futures_each_register_reads(runs):
    """`hde --help` is read before the contract is: every count it gives for
    `--decompose` is checked against runs. N is the block's `paths` (bare, the
    config's `simulation.num_sims`), the level reads `min(N, cap)` of them at
    an N under the cap and one over it, and the reversal register's curves
    are bisected on the config's `simulation.num_sims` at an N that differs
    from it.
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
    assert [f.name for f in dataclasses.fields(dc.EstimatedBoundary)] == [
        "verdict_field", "value", "value_ci", "was", "becomes", "further_changes",
        "resimulation_paths"]
    for path in (REPO / "src" / "hde").glob("*.py"):
        if path.name in ("decomposition.py", "decomposition_text.py"):
            continue
        assert "EstimatedBoundary(" not in path.read_text(encoding="utf-8"), path.name


@claims("A boundary carries `verdict_field`, `value`, `was`, `becomes`,",
        "`best` and `runner_up` are SOLVED on the central case;",
        "`was` is what the field says just below `value` and `becomes` what it says",
        "For `decisive` they read")
def test_every_boundary_reads_upward_against_a_sweep(runs):
    for name in ("fixture", "mortgage"):
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            for boundary in row["boundaries"]:
                field = boundary["verdict_field"]
                solved = field in ("best", "runner_up")
                keys = {"verdict_field", "value", "was", "becomes", "further_changes",
                        "confirming_probabilities"}
                if not solved:
                    keys |= {"curve_probabilities", "curve_paths", "seed"}
                assert set(boundary) == keys
                below, above = _sweep_states(run.path, row["key"],
                                             [boundary["value"] - 1e-4,
                                              boundary["value"] + 1e-4], not solved)
                assert below[field] == boundary["was"], (name, row["key"], field)
                assert above[field] == boundary["becomes"], (name, row["key"], field)
                if field == "decisive":
                    assert re.fullmatch(r"decisive for \w+|not decisive", boundary["was"])


@claims("`confirming_probabilities` is each option's probability of being cheapest",
        "A boundary is reported only where the two are equal.",
        "Each is a list of `[option, probability]` pairs.")
def test_the_confirming_and_the_curve_probabilities(runs):
    """A sampled boundary's two lists are equal pair for pair; the confirming
    one is a full re-simulation at the boundary's value (checked on one
    sampled boundary here, and on a solved one in
    `test_how_many_futures_each_register_prices`)."""
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
                             gap(lambda v: v > 0.05))
    assert [b["value"] for b in one["break_evens"]] == pytest.approx([0.05], abs=1e-8)

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
    assert found == [] and why.startswith("mc_best says 'condo' at every one of 65 points")
    assert xs == pytest.approx([0.01 + 0.09 * i / 64 for i in range(65)])
    found, why = be._futures_field_boundaries(
        {}, "house.mortgage_rate", "mc_best", curve(lambda x: 0.0205 < x < 0.03),
        stated, 0.01, 0.10, scan_points=be.REVERSAL_SCAN_POINTS)
    assert why is None
    assert [b["value"] for b in found] == pytest.approx([0.0205, 0.03], abs=1e-9)
    assert inspect.signature(be.reversal_register).parameters[
        "scan_points"].default == 65

    # the register's own solver call: each pair of the fixture's three options,
    # each scanned at the same nine points before it bisects
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


@claims("`further_changes` is `\"above\"` when")
def test_further_changes_against_a_sweep_past_the_edge(runs):
    """For each boundary, sweep from the edge to where the field says what the
    run says again, or to the bracket's end, on the flagged side: more than
    one state there exactly when `further_changes` names that side."""
    checked = set()
    for name in ("fixture", "mortgage"):
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            for boundary in row["boundaries"]:
                field = boundary["verdict_field"]
                futures = field not in ("best", "runner_up")
                upward = boundary["was"] == _run_says(run, row, field, futures)
                side = "above" if upward else "below"
                end = row["bracket_high"] if upward else row["bracket_low"]
                # fine steps off the edge first, where a short stretch lives,
                # then the rest of the way to the bracket's end
                step = 1.0 if upward else -1.0
                fine = [boundary["value"] + step * d for d in (2e-4, 5e-4, 1e-3, 2e-3, 4e-3)]
                grid = [x for x in fine if min(boundary["value"], end) < x
                        < max(boundary["value"], end)]
                grid += list(np.linspace(boundary["value"], end, 13)[1:])
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


def _run_says(run, row, field, futures):
    """What `field` says at the config's own value of the row's key."""
    doc = run.doc["verdict"]
    if field == "decisive":
        return f"decisive for {doc['best']}" if doc["decisive"] else "not decisive"
    return doc[field]


@claims("`refused_boundaries[]`: `verdict_field` and `reason`",
        "`references[]`: `label`, `value`, `formatted`, `anchor` and `note`",
        "On an `effective_annual` config the semi-annual anchor passes through")
def test_the_refused_fields_and_the_references(runs):
    from hde.anchors import ANCHORS
    refused = 0
    for name, converted in (("fixture", False), ("mortgage", True)):
        run = runs[name]
        for row in run.block["reversal"]["exact"]:
            for item in row["refused_boundaries"]:
                assert set(item) == {"verdict_field", "reason"}
                # the measured fact: one of the reason templates the sentence
                # tests check against the run
                assert sentences._reason_hits(item["reason"]), item["reason"]
                refused += 1
            for ref in row["references"]:
                assert set(ref) == {"label", "value", "formatted", "anchor", "note"}
                published = ANCHORS[ref["anchor"]].value
                want = (effective_mortgage_rate(published, "semi_annual") if converted
                        else published)
                assert ref["value"] == want
                assert ref["note"] == (f"published as {published:.2%} compounded "
                                       f"semi-annually" if converted else None)
    assert refused
    assert runs["mortgage"].raw["house"]["mortgage_rate_compounding"] == "effective_annual"
    # the stated rate, typed on that axis, sits where the converted contracted
    # figure does: 4.40% typed against 4.35% published
    row = runs["mortgage"].block["reversal"]["exact"][0]
    refs = {r["anchor"]: r["value"] for r in row["references"]}
    assert abs(refs["mortgage_rate.contracted_5y_uninsured"] - 0.044) < 0.0003


@claims("`structural_zeros[]`: `kind`, `label`, `keys`, `channel_id`,",
        "Decided by the model's structure;",
        "Both facts are measured, on those futures, and both are facts about the stream.",
        "`keys` are the stated keys that size its draws, and nothing is said of them",
        "`reversal_key` is `null`.")
def test_the_structural_zeros_say_what_is_drawn(runs):
    """Checked at the generators: a stated path moves no stream's state; the
    income stream and a dead channel do move theirs, and re-seeding them, on
    held generators and as many futures as the row names, moves no present
    value past the row's threshold. And at the grain of a key (§0.1 item 40):
    `rent.events` on `three` names a stated moving cost whose deterministic
    present value is in rent's, and the row names it only as what sizes the
    tenancy's draws."""
    fixture = runs["fixture"]
    zeros = fixture.block["reversal"]["structural_zeros"]
    for zero in zeros:
        assert set(zero) == {"kind", "label", "keys", "channel_id", "reversal_key",
                             "measured_paths", "move_threshold"}
    exact_keys = {r["key"] for r in fixture.block["reversal"]["exact"]}
    spec = dr._spec_at(fixture.spec, 40)
    for zero in (z for z in zeros if z["kind"] == "stated_path"):
        assert zero["reversal_key"] in exact_keys and zero["channel_id"] is None
        moved = copy.deepcopy(fixture.raw)
        moved["sources"].pop(zero["reversal_key"], None)
        key = zero["reversal_key"].split(".", 1)[1]
        value = moved["house"][key]
        moved["house"][key] = ([v + 0.01 for v in value] if isinstance(value, list)
                               else value + 0.01)
        assert _stream_states(spec) == _stream_states(
            dr._spec_at(load_config_dict(moved), 40)), zero["label"]
    for zero in (z for z in zeros if z["kind"] == "stated_path"):
        assert (zero["measured_paths"], zero["move_threshold"]) == (None, None)
    income = next(z for z in zeros if z["kind"] == "dead_draw")
    assert income["channel_id"] == dc.INCOME_STREAM_ID and income["reversal_key"] is None
    assert income["keys"] == ["income.pay_drop_events"]
    assert income["measured_paths"] == fixture.block["paths"]
    assert 7 in _moved_streams(spec)
    assert oracle_moves(fixture.spec, income["measured_paths"])[7] <= income["move_threshold"]
    three = runs["three"]
    dead = [z for z in three.block["reversal"]["structural_zeros"] if z["kind"] == "dead_draw"]
    assert [z["channel_id"] for z in dead] == [5]
    spec3 = dr._spec_at(three.spec, 40)
    for zero in dead:
        assert zero["channel_id"] in _moved_streams(spec3)
        moves = oracle_moves(three.spec, zero["measured_paths"])
        assert moves[zero["channel_id"]] <= zero["move_threshold"]
        assert zero["reversal_key"] is None
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


def _pvs(spec, overrides):
    mc = run_monte_carlo(spec, _held(overrides))
    return {o: np.asarray(getattr(mc, o).pvs).tobytes()
            for o in ("condo", "house", "rent") if getattr(mc, o) is not None}


# ---------------------------------------------------------------------------
# The text block
# ---------------------------------------------------------------------------

@claims("**The text block** prints these figures and no sentence about them.",
        "Every line is one of six kinds: a heading; a figure row",
        "A crossing line names whether it was solved or sampled",
        "A path note is a row's `path_note`, printed after its bracket.",
        "A `stated_path` row prints its label, its keys and that no draw touches them")
def test_the_text_block_holds_six_kinds_of_line(runs):
    """Every line of every render is one template of the sentence tests, and
    every template is one of the six kinds or a blank — the path note under its
    own kind, not filed as a crossing (§0.1 item 41); the crossing lines of the
    fixture carry their type, and the sampled ones their paths and seed, with
    the path note after the bracket; each structural-zero row prints its kind's
    fields."""
    kinds = set(sentences.KINDS.values())
    assert kinds == {"layout", "header", "figure row", "crossing", "path note", "refusal",
                     "structural zero"}
    assert sentences.KINDS["PATH_NOTE"] == "path note"
    for render in sentences.renders():
        for line in sentences._lines(render):
            assert sentences.KINDS[line.template] in kinds
    run = runs["fixture"]
    lines = run.text.splitlines()
    for row in run.block["reversal"]["exact"]:
        for boundary in row["boundaries"]:
            if "seed" in boundary:
                head = (f"      sampled on {boundary['curve_paths']:,} paths at seed "
                        f"{boundary['seed']}: as it rises past "
                        f"{dt._sampled_rate(boundary['value'])}, ")
            else:
                head = (f"      solved on the central case: as it rises past "
                        f"{dt._solved_rate(boundary['value'])}, ")
            assert sum(line.startswith(head) for line in lines) == 1, head
    ladder = run.block["reversal"]["exact"][0]
    at = lines.index(f"      bracket searched: {dt._rate(ladder['bracket_low'])}–"
                     f"{dt._rate(ladder['bracket_high'])} [{ladder['bracket_source']}]")
    assert lines[at + 1] == f"      {ladder['path_note']}"
    assert lines[at + 2].startswith("      solved on the central case:")
    for zero in run.block["reversal"]["structural_zeros"]:
        if zero["kind"] == "stated_path":
            want = f"  {zero['label']} — {', '.join(zero['keys'])}: no draw touches it"
        else:
            want = (f"  {zero['label']}: drawn on these {zero['measured_paths']:,} futures, "
                    f"and re-drawing it moved no option's present value by more than "
                    f"${dt._ceiled_threshold(zero['move_threshold'])}; sized by "
                    f"{', '.join(zero['keys'])}")
            # three significant figures, taken upward
            printed = decimal.Decimal(dt._ceiled_threshold(zero["move_threshold"]))
            assert len(printed.normalize().as_tuple().digits) <= 3
            assert printed >= decimal.Decimal(zero["move_threshold"])
            assert printed - decimal.Decimal(1).scaleb(printed.adjusted() - 2) \
                < decimal.Decimal(zero["move_threshold"])
        assert want in lines, want


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
        "`not resolved` with no colon and no figure after it stands where the residual",
        "`largest alone share:` and `largest shift in size:` name a",
        "when the top row did not resolve, neither line prints.",
        "Each printed figure is rounded on its own from the unrounded field")
def test_the_text_block_prints_the_registers_own_judgments(runs):
    """On the fixture: each unresolved spread and level row behind the words,
    each resolved one bare; each top line as the JSON names it; the sums and
    the level's difference over the printed figures. And the partition of
    "not resolved" pinned whole (§0.1 item 46): over every line of every
    render, each occurrence is either followed by ": " and a figure, or is
    the residual's own place on a block whose interaction did not resolve."""
    residual_seen = 0
    for render in sentences.renders():
        for line in render.text.splitlines():
            for hit in re.finditer(r"not resolved(?P<after>.{0,3})", line):
                if hit["after"].startswith(": "):
                    assert re.match(r"not resolved: [+-]?\$?-?\d", line[hit.start():]), line
                    continue
                assert line.endswith("; 1 minus that sum: not resolved"), line
                assert render.block["spread"]["interaction"]["resolved"] is False
                residual_seen += 1
    assert residual_seen
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


# ---------------------------------------------------------------------------
# Which figures move with the sample
# ---------------------------------------------------------------------------

# Every numeric leaf of the block, by the list the contract files it under.
# The key is the leaf's path with list positions dropped, and a boundary's
# `value` is filed by its kind. `test_the_partition_of_the_numbers_is_whole`
# enumerates every leaf of two runs against this map, and checks each name
# against the contract's own list.
PARTITION = {
    "config": {
        "reversal.exact[].bracket_low": "`bracket_low`",
        "reversal.exact[].bracket_high": "`bracket_high`",
        "reversal.exact[].references[].value": "each reference's `value`",
        "reversal.exact[].probe_paths": "`probe_paths`",
        "reversal.exact[].boundaries[].curve_paths": "`curve_paths`",
        "reversal.exact[].boundaries[].value#solved": "a solved boundary's `value`",
        "level.all_frozen_margin": "`all_frozen_margin`",
        "level.all_frozen_deviation": "`all_frozen_deviation`",
        "reversal.structural_zeros[].move_threshold": "`move_threshold`",
    },
    "fixed": {
        "level.all_frozen_path_spread": "`all_frozen_path_spread`, which is `0.0`",
    },
    "sample": {
        "paths": "`paths`",
        "level.paths": "`level.paths`",
        "reversal.structural_zeros[].measured_paths": "`measured_paths`",
        "reversal.exact[].boundaries[].seed": "`seed`, which is the seed",
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
        "reversal.exact[].boundaries[].value#sampled": "a sampled boundary's `value`",
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
        "reversal.structural_zeros[].channel_id":
            "every row's and every `structural_zeros` row's `channel_id`",
        "spread.leading_channel_id": "`leading_channel_id`",
        "level.leading_channel_id": "`leading_channel_id`",
        "spread.unresolved_top_channel_id": "`unresolved_top_channel_id`",
        "level.unresolved_top_channel_id": "`unresolved_top_channel_id`",
        "spread.interaction_channel_ids[]": "`interaction_channel_ids`",
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
        kind = ""
        if "verdict_field" in node and "value" in node:
            kind = "#sampled" if "seed" in node else "#solved"
        for key, value in node.items():
            filed = f"{path}.{key}" if path else key
            if key == "value" and kind:
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
        "Every number in the block is in exactly one of these four lists:",
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
    list, or a config figure that moves."""
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
    # the words the contract files with the config
    for key in ("stated_formatted", "stated_source", "bracket_source", "path_note"):
        assert ([r[key] for r in a_run.block["reversal"]["exact"]]
                == [r[key] for r in b_run.block["reversal"]["exact"]]), key
    assert [r["widths"] for r in a_run.block["spread"]["rows"]] == [
        r["widths"] for r in b_run.block["spread"]["rows"]]
    for x, y in zip(a_run.block["reversal"]["exact"], b_run.block["reversal"]["exact"]):
        assert ([(b["verdict_field"], b["was"], b["becomes"], b["further_changes"])
                 for b in x["boundaries"] if "seed" not in b]
                == [(b["verdict_field"], b["was"], b["becomes"], b["further_changes"])
                    for b in y["boundaries"] if "seed" not in b])


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
        assert _without_counts(a["reversal"]["structural_zeros"]) == _without_counts(
            b["reversal"]["structural_zeros"])
        assert a["reversal"]["no_distance_reason"] == b["reversal"]["no_distance_reason"]
        assert a["level"]["all_frozen_margin"] == b["level"]["all_frozen_margin"]
        assert a["level"]["all_frozen_deviation"] == b["level"]["all_frozen_deviation"]
        assert a["mean_margin"] != b["mean_margin"] and a["sd_margin"] != b["sd_margin"]
        assert _rows(a)[0]["flip"] != _rows(b)[0]["flip"]
        assert a["level"]["futures_margin"] != b["level"]["futures_margin"]
    for x, y in zip(a["reversal"]["exact"], other_seed.block["reversal"]["exact"]):
        assert (x["bracket_low"], x["bracket_high"], x["references"]) == (
            y["bracket_low"], y["bracket_high"], y["references"])
        solved_x = [(b["verdict_field"], b["value"], b["further_changes"])
                    for b in x["boundaries"] if "seed" not in b]
        solved_y = [(b["verdict_field"], b["value"], b["further_changes"])
                    for b in y["boundaries"] if "seed" not in b]
        assert solved_x == solved_y
        sampled_x = [b["value"] for b in x["boundaries"] if "seed" in b]
        sampled_y = [b["value"] for b in y["boundaries"] if "seed" in b]
        assert sampled_x != sampled_y
    # the reversal register reads no future of the block's own: at another N
    # it is the same register, every sampled figure included, but for the
    # count a measured row states it was measured on
    assert other_count.block["paths"] == 400
    assert {**other_count.block["reversal"], "structural_zeros": None} == {
        **a["reversal"], "structural_zeros": None}
    assert [z["measured_paths"] for z in other_count.block["reversal"]["structural_zeros"]
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


def test_the_skill_is_behavioural_and_restates_nothing():
    """gates.md §10 is what an assistant loads before it quotes the block. It
    once carried the fixture's figures, which went stale when the engine's
    changed, and then the block's own rules. It carries instructions on how
    to quote and a pointer here: every instruction present, and no figure,
    rule or field meaning (§0.1 item 32).
    *Kills it:* restoring a figure, a resolution rule, a path count or a
    field's meaning to §10, or dropping one of its instructions."""
    section = _between(_GATES.read_text(encoding="utf-8"),
                       "## 10. `--decompose`", "\n## ")
    assert "`docs/reference/API_CONTRACT.md` § The `decomposition` block" in section
    for instruction in (
        "Quote the block's lines verbatim, with their figures and their `[...]` tags.",
        "Never quote a row from THE SPREAD without the same channel's row from THE",
        "Where the block prints `not resolved`, say it is not resolved",
        "Read what a figure, a refusal code or a path count means in",
        "never explain it from memory",
    ):
        assert instruction in " ".join(section.split()), instruction
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
    assert "\n|" not in architecture and "mean(" not in architecture
    assert not _FIGURE.search(architecture)
    prompts = (REPO / "PROMPTS.md").read_text(encoding="utf-8")
    bullet = _between(prompts, "- *\"Which of these risks actually decides it?\"*", "\n- ")
    assert "`docs/reference/API_CONTRACT.md` § The `decomposition` block" in bullet
    assert "refusals included" in bullet
    assert not _FIGURE.search(bullet)


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
