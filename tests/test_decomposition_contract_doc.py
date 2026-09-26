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
import inspect
import json
import math
import pathlib
import re
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
from hde.monte_carlo import run_monte_carlo
from hde.rates import effective_mortgage_rate
from hde.sweep import flattened_path_note

from tests import test_decomposition_sentences as sentences
from tests.decomposition_runs import (
    CONDO_ONLY, CONTRACT, FIXTURE, INCOME, MIN_INTERACTION, MONTREAL, MORTGAGE, NEAR_ALL,
    NO_REACH, REPO, THIRD_FAR, Run, _block_text, _cli, _load, _strict, _sweep_states,
    corpus)
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
    doc, _, _, _ = _refusal(tmp_path, _load(INCOME))
    refusal = doc["refusal"]
    assert refusal["code"] == "one_channel"
    assert dr.live_channels(load_config_dict(_load(INCOME))) == (refusal["channel_id"],)
    assert refusal["reason"] == f"one channel is live on this run: {refusal['label']}"


@claims("| `no_spread` |")
def test_no_spread(tmp_path):
    """Both forms, each reason the fact that fired it: no live channel (with
    channels that draw), and a margin identical on every future — re-priced
    here to that figure."""
    doc, _, _, _ = _refusal(tmp_path, NO_REACH)
    assert doc["refusal"] == {"code": "no_spread", "reason": "no channel is live on this run"}
    spec = load_config_dict(NO_REACH)
    assert dr.live_channels(spec) == () and dr.channels_that_draw(spec)
    for raw in (TWINS, THIRD_FAR):
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
    doc, _, _, _ = _refusal(tmp_path, _load(FIXTURE), "1000000")
    k = len(dr.live_channels(runs["fixture"].spec))
    work = 1_000_000 * (k + 2) + 2000 * (k + 1)
    largest = dr.largest_affordable_paths(k)
    assert doc["refusal"] == {"code": "budget", "reason": (
        f"1,000,000 futures at {k} live channels price up to {work:,} path "
        f"evaluations, above the ceiling of 250,000 [set in the engine]; the largest "
        f"path count within it is {largest:,}")}
    assert dr.EVALUATION_CEILING == 250_000
    assert largest * (k + 2) + 2000 * (k + 1) <= 250_000
    assert (largest + 1) * (k + 2) + 2000 * (k + 1) > 250_000


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


@claims("The first refusal in this order that fires is the one returned")
def test_the_refusal_order(tmp_path):
    """Each pair: a config on which BOTH conditions hold, and the earlier
    code wins — except the identical-margin `no_spread`, which yields to
    `too_few_futures` and to `budget`, because it is measured on priced
    futures."""
    pairs = [
        (CONDO_ONLY, ("--no-monte-carlo",), "no_futures"),   # and one option
        (CONDO_ONLY, (), "single_option"),                   # and one live channel
        (_load(INCOME), ("39",), "one_channel"),             # and too few
        (NO_REACH, ("39",), "no_spread"),                    # no live channel, too few
        (TWINS, ("1000000",), "budget"),                     # and an identical margin
        (TWINS, ("39",), "too_few_futures"),                 # and an identical margin
    ]
    assert dr.live_channels(load_config_dict(CONDO_ONLY)) == (3,)
    for raw, extra, code in pairs:
        doc, _, _, _ = _refusal(tmp_path, raw, *extra)
        assert doc["refusal"]["code"] == code, (code, extra)
    doc, _, _, _ = _refusal(tmp_path, TWINS)
    assert doc["refusal"]["code"] == "no_spread"


# ---------------------------------------------------------------------------
# Live channels and the block's own keys
# ---------------------------------------------------------------------------

def _option_pvs(spec, swap=None):
    mc = dr._run(spec, dr.MATRIX_A, swap or {})
    return {o: np.asarray(getattr(mc, o).pvs) for o in ("condo", "house", "rent")
            if getattr(mc, o) is not None}


@claims("`live_channel_ids` are the channels whose draws reach a cash flow",
        "Ids: 0 economy, 1 market",
        "A live channel may move only an option that never enters the margin")
def test_live_channels_are_the_ones_that_move_a_present_value(runs, tmp_path):
    """Swapping a live channel's stream moves some option's present values and
    swapping a drawn, dead one moves none. On THIRD_FAR two channels are live,
    each moves only the option that is never the cheapest other, and the
    margin is identical on every future."""
    assert [c.key for c in dc.CHANNELS] == ["economy", "market", "population", "condo",
                                            "house", "shelter", "portfolio"]
    run = runs["three"]
    live = run.block["live_channel_ids"]
    spec = dr._spec_at(run.spec, 200)
    base = _option_pvs(spec)
    for channel in dr.channels_that_draw(run.spec):
        swapped = _option_pvs(spec, {channel: dr.MATRIX_B})
        moved = any(not np.array_equal(base[o], swapped[o]) for o in base)
        assert moved == (channel in live), channel
    assert set(dr.channels_that_draw(run.spec)) - set(live)
    far = load_config_dict(THIRD_FAR)
    assert dr.live_channels(far) == (5, 6)
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
    for name, run in runs.items():
        k = len(run.block["live_channel_ids"])
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
            assert row["bracket_source"] == "assistant"


@claims("`path_note` is set when the config states the key as a path of two or more",
        "a path of one repeated rate included.")
def test_the_path_note(runs):
    run = runs["fixture"]
    rows = {r["key"]: r for r in run.block["reversal"]["exact"]}
    ladder = rows["house.mortgage_renewal_rates"]
    assert len(set(run.raw["house"]["mortgage_renewal_rates"])) > 1
    assert ladder["path_note"] == flattened_path_note(run.raw, ladder["key"]) is not None
    assert rows["house.mortgage_rate"]["path_note"] is None
    flat = copy.deepcopy(run.raw)
    flat["house"]["mortgage_renewal_rates"] = [0.05, 0.05, 0.05]
    assert flattened_path_note(flat, "house.mortgage_renewal_rates") is None
    flat["house"]["mortgage_renewal_rates"] = [0.05, 0.06]
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


@claims("`structural_zeros[]`: `kind`, `label`, `keys`, `channel_id` and",
        "`stated_path` is an input no draw touches")
def test_the_structural_zeros_say_what_is_drawn(runs):
    """Checked at the generators: a stated path moves no stream's state; the
    income block and a dead channel do move theirs, and re-drawing them moves
    no present value."""
    fixture = runs["fixture"]
    zeros = fixture.block["reversal"]["structural_zeros"]
    for zero in zeros:
        assert set(zero) == {"kind", "label", "keys", "channel_id", "reversal_key"}
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
    income = next(z for z in zeros if z["kind"] == "no_pv_reach")
    assert 7 in _moved_streams(spec)
    assert _pvs(spec, {7: 101}) == _pvs(spec, {7: 202})
    three = runs["three"]
    dead = [z for z in three.block["reversal"]["structural_zeros"] if z["kind"] == "dead_draw"]
    assert dead and income["channel_id"] is None
    spec3 = dr._spec_at(three.spec, 40)
    for zero in dead:
        assert zero["channel_id"] in _moved_streams(spec3)
        assert _pvs(spec3, {zero["channel_id"]: 101}) == _pvs(spec3, {zero["channel_id"]: 202})


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
        "Every line is a heading, a figure row with its intervals and source tags",
        "A crossing line names whether it was solved or sampled")
def test_the_text_block_holds_five_kinds_of_line(runs):
    """Every line of every render is one template of the sentence tests, and
    every template is one of the five kinds or a blank; the crossing lines of
    the fixture carry their type, and the sampled ones their paths and seed,
    with the path note beside them."""
    kinds = set(sentences.KINDS.values())
    assert kinds == {"layout", "header", "figure row", "crossing", "refusal",
                     "structural zero"}
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


def _assert_top_line(text, what, leading):
    lines = [line for line in text.splitlines() if line.startswith(f"  largest {what}:")]
    want = [] if leading is None else [f"  largest {what}: {dc.channel(leading).label}"]
    assert lines == want, (what, lines)


@claims("A figure that did not resolve prints behind",
        "`largest alone share:` and `largest shift in size:` name a",
        "when the top row did not resolve, neither line prints.",
        "Each printed figure is rounded on its own from the unrounded field")
def test_the_text_block_prints_the_registers_own_judgments(runs):
    """On the fixture: each unresolved spread and level row behind the words,
    each resolved one bare; each top line as the JSON names it; the sums and
    the level's difference over the printed figures."""
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
                assert (f"not resolved: {cell}" in text) == (not row["resolved"]), (name, cell)
                seen_unresolved += not row["resolved"]
            _assert_top_line(text, "alone share", spread["leading_channel_id"])
            tops.add(spread["leading_channel_id"] is not None)
        for row in level["rows"]:
            cell = f"{dt._shift(_shift(row))} (± ${row['se']:,.0f})"
            assert (f"not resolved: {cell}" in text) == (not row["resolved"]), (name, cell)
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

@claims("**Which figures move with the sample.**",
        "Properties of the config, the same at any seed and any path count",
        "Everything else in the block that is a figure moves with the seed",
        "So does whether `spread` refuses with")
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
        assert a["reversal"]["structural_zeros"] == b["reversal"]["structural_zeros"]
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
    # it is the same register, every sampled figure included
    assert other_count.block["paths"] == 400
    assert other_count.block["reversal"] == a["reversal"]
    # one config, two path counts: the spread refuses at 200 and prints at 2,000
    fewer = Run(NEAR_ALL, "200").materialise(tmp_path / "near")
    assert fewer.block["spread"]["refusal"]["code"] == "no_sign_variation"
    assert "rows" in runs["near_all"].block["spread"]


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
