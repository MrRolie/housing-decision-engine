"""Which streams draw and which channels are live, MEASURED on the run
(spec §0.1 item 39), held to instruments that are not that measurement.

A copy of the simulator's logic once answered both questions from the config.
It disagreed with the simulator on the tenancy, and the block printed what
followed: a header count, a `one_channel` refusal where the contract's own
table gave `no_spread`, a live spread row holding a measured zero, and "drawn"
over pay drops that draw nothing. The configs it got wrong are here, each run
through the CLI, with what the block now prints and what the instruments in
`tests/decomposition_oracles.py` say about every stream:

  - a stream the engine counts as drawing is one whose own held generator
    advances, and no other;
  - a channel the engine counts as live is one whose re-seeding, on held
    generators, moves some option's present value by more than the identity's
    budget, and whose FREEZE moves it too; a drawing stream it does not count
    is one whose re-seeding moves nothing by more than that.

Then the threshold and the measurement themselves, each mutated both ways by a
witness that fails on the printed block, and a generative sweep over random
configs.
"""
from __future__ import annotations

import copy
import pathlib
import random
import re
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from hde import decomposition_run as dr
from hde.config import load_config_dict
from hde.decomposition import INCOME_STREAM_ID
from hde.deterministic import compute_deterministic
from hde.models import compute_verdict

from tests.decomposition_oracles import freeze_moves, oracle_drawn, oracle_moves, threshold
from tests.decomposition_runs import _SCRATCH, _block_text, _cli, _strict

# ---------------------------------------------------------------------------
# The configs a config-read copy of the simulator got wrong
# ---------------------------------------------------------------------------

# Nominal mode, a deterministic inflation of 0 with a volatility on it, and a
# rent escalation of 0.0 as quoted (stored as the real rate that composes back
# to 0 at the base inflation). The inflation draw moves the composed
# escalation, so the tenancy's shock reaches rent: three channels are live.
NOMINAL_ZERO_ESCALATION = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "nominal", "inflation_rate": 0.0, "inflation_vol": 0.02},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200,
              "other_recurring_costs": [{"name": "property_tax", "annual_amount": 2600,
                                         "escalation_rate": 0.0}]},
    "rent": {"monthly_rent": 1400, "rent_escalation_rate": 0.0,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42, "condo_fee_vol": 0.05,
                   "rent_escalation_vol": 0.10},
}
# The same with no condo fee volatility: the economy and the tenancy are live,
# and the condo's fee draw moves nothing. It printed `one_channel` naming the
# economy.
NOMINAL_ZERO_ESCALATION_NO_FEE = copy.deepcopy(NOMINAL_ZERO_ESCALATION)
del NOMINAL_ZERO_ESCALATION_NO_FEE["simulation"]["condo_fee_vol"]
# Nominal mode with a deterministic inflation and no volatility on it, and a
# rent escalation of 0.0 as quoted: the composed escalation is exactly 0 in
# every year, so the tenancy's shock scales nothing. It printed `one_channel`
# naming the tenancy; every future prices one margin.
NOMINAL_FLAT_RENT = {
    "years": 20, "discount_rate": 0.052,
    "economic": {"mode": "nominal", "inflation_rate": 0.021},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.021, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200, "value_growth_rate": 0.031},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.0,
             "invested_down_payment": 355200, "investment_return_rate": 0.051},
    "simulation": {"num_sims": 400, "random_seed": 42, "rent_escalation_vol": 0.10},
}
# A lease reset to the tenant's own rent and escalation: the reset year is
# drawn and moves no present value beyond the last bits of a sum. It was
# counted live and printed a spread row of measured zeros; the condo's fees are
# the one live channel.
RESET_TO_OWN_RENT = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.01, "reset_hazard": 0.1,
             "reset_to_monthly_rent": 1500, "reset_market_escalation_rate": 0.01,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42, "condo_fee_vol": 0.05},
}
# The same reset with nothing else drawn: the margin differs across futures
# only in its last bits, and no channel is live.
RESET_TO_OWN_RENT_ALONE = copy.deepcopy(RESET_TO_OWN_RENT)
del RESET_TO_OWN_RENT_ALONE["simulation"]["condo_fee_vol"]
# Nominal mode with an inflation volatility and no other uncertainty input:
# the economy composes into every growth rate and is the one live channel.
INFLATION_ONLY = {
    "years": 20, "discount_rate": 0.05,
    "economic": {"mode": "nominal", "inflation_rate": 0.02, "inflation_vol": 0.02},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.02, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200, "value_growth_rate": 0.03},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.025,
             "invested_down_payment": 355200, "investment_return_rate": 0.05},
    "simulation": {"num_sims": 400, "random_seed": 42},
}
# A lease reset that is certain in the first year: its year is drawn on every
# future and lands on the same one, so re-drawing it moves nothing. It was
# counted live; the condo's fees are the one live channel.
RESET_CERTAIN = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200},
    "rent": {"monthly_rent": 1150, "rent_escalation_rate": 0.0, "reset_hazard": 1.0,
             "reset_to_monthly_rent": 2500, "invested_down_payment": 355200,
             "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42, "condo_fee_vol": 0.05},
}
# A price crash certain every year with a fixed severity: the crash draws are
# taken and every future takes the same loss. It was counted live.
CRASH_CERTAIN = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200,
              "price_shock": {"annual_hazard": 1.0, "severity_mean": 0.02,
                              "severity_vol": 0.0}},
    "rent": {"monthly_rent": 1150, "rent_escalation_rate": 0.0,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42, "condo_fee_vol": 0.05},
}
# A pay drop with no timing or size volatility, beside two live channels: the
# income stream draws nothing, and the block prints no row for it. A
# config-read copy printed "your income — income.pay_drop_events: drawn".
FIXED_PAY_DROP = yaml.safe_load(
    (pathlib.Path(__file__).resolve().parents[1] / "examples" / "income_shock.yaml")
    .read_text(encoding="utf-8"))
FIXED_PAY_DROP["simulation"].update({"num_sims": 400, "rent_escalation_vol": 0.02})
# A renewal-rate path file: stream 8 draws one row per path, and the block
# measures it like any other stream (docs/specs/2026-10-01-renewal-rate-path-file.md §4).
_REPO = pathlib.Path(__file__).resolve().parents[1]
RATE_PATHS = yaml.safe_load(
    (_REPO / "tests" / "fixtures" / "renewal_rate_paths.yaml").read_text(encoding="utf-8"))
RATE_PATHS["renewal_rates"]["path"] = str(
    _REPO / "tests" / "fixtures" / "renewal_rate_paths_synthetic.json")
RATE_PATHS["sources"] = {"renewal_rates.path": "user"}
RATE_PATHS["simulation"]["num_sims"] = 400

# What each prints, and which streams draw and are live on its futures.
EXPECTED = {
    "nominal_zero_escalation": (
        NOMINAL_ZERO_ESCALATION, "header", (0, 3, 5), (0, 3, 5)),
    "nominal_zero_escalation_no_fee": (
        NOMINAL_ZERO_ESCALATION_NO_FEE, "header", (0, 3, 5), (0, 5)),
    "nominal_flat_rent": (
        NOMINAL_FLAT_RENT, "no_spread:identical", (3, 5), ()),
    "reset_to_own_rent": (
        RESET_TO_OWN_RENT, "one_channel:the condo's costs", (3, 5), (3,)),
    "reset_to_own_rent_alone": (
        RESET_TO_OWN_RENT_ALONE, "no_spread:none live", (3, 5), ()),
    "inflation_only": (
        INFLATION_ONLY, "one_channel:the economy", (0, 3), (0,)),
    "reset_certain": (
        RESET_CERTAIN, "one_channel:the condo's costs", (3, 5), (3,)),
    "crash_certain": (
        CRASH_CERTAIN, "one_channel:the condo's costs", (1, 3), (3,)),
    "fixed_pay_drop": (
        FIXED_PAY_DROP, "header", (3, 5), (3, 5)),
    "renewal_rate_paths": (
        RATE_PATHS, "header", (4, 5, 8), (4, 5, 8)),
}


def _render(name, raw, *extra):
    directory = pathlib.Path(_SCRATCH.name) / "liveness" / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    code, out, _ = _cli(path, "--decompose", *extra, "--json")
    assert code == 0, out
    doc = _strict(out)
    code, out, _ = _cli(path, "--decompose", *extra, "-q")
    assert code == 0
    return doc["decomposition"], _block_text(out)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_the_block_prints_what_the_instruments_measure(name):
    """*Kills it:* any config-read rule that got these wrong, restored."""
    raw, outcome, drawn, live = EXPECTED[name]
    spec = load_config_dict(copy.deepcopy(raw))
    n = spec.simulation.num_sims
    block, text = _render(name, raw)
    first = text.splitlines()[0]
    if outcome == "header":
        assert first == f"which risk decides it — {n:,} futures, {len(live)} channels live on them"
        assert tuple(block["live_channel_ids"]) == live
        dead = [z for z in block["spread"]["structural_zeros"] if z["kind"] == "dead_draw"]
        assert tuple(sorted(z["channel_id"] for z in dead)) == tuple(
            sorted(set(drawn) - set(live)))
        assert all(z["measured_paths"] == n for z in dead)
    else:
        code, fact = outcome.split(":")
        assert block["refusal"]["code"] == code
        reason = block["refusal"]["reason"]
        if fact == "identical":
            assert re.fullmatch(rf"the margin is identical on all {n:,} futures "
                                r"\(-?\$[\d,]+\.\d\d\)", reason), reason
        elif fact == "none live":
            assert reason == f"no channel is live on these {n:,} futures"
        else:
            assert reason == f"one channel is live on these {n:,} futures: {fact}"
        assert first == f"which risk decides it — not split ({code}): {reason}"

    # What the instruments say about every stream, on the same count of futures.
    limit = threshold(spec)
    assert oracle_drawn(spec) == set(drawn)
    moves = oracle_moves(spec, n)
    frozen = freeze_moves(spec, n)
    for stream in drawn:
        if stream in live:
            assert moves[stream] > limit and frozen[stream] > limit, (stream, moves)
        else:
            assert moves[stream] <= limit, (stream, moves[stream], limit)
    for stream in set(dr.STREAM_IDS) - set(drawn):
        assert moves[stream] == 0.0, stream


def test_the_reset_to_own_rent_moves_something_only_the_threshold_calls_nothing():
    """The one config above where a drawing stream's re-draw moves a present
    value at all without being live: by a few units in the last place, below
    the identity's budget. It is what makes the threshold's own mutant in the
    exact direction fail (`test_the_threshold_is_the_identity_s_budget`)."""
    spec = load_config_dict(copy.deepcopy(RESET_TO_OWN_RENT))
    moves = oracle_moves(spec, spec.simulation.num_sims)
    assert 0.0 < moves[5] <= threshold(spec)


def test_the_income_stream_draws_only_with_a_volatility_on_it():
    """`year_jitter_std` and `magnitude_vol` default to 0, and then the pay
    drop is a fixed cut that draws nothing: no row. The corpus fixture's pay
    drop carries both, and its row says drawn — measured, on its futures.
    *Kills it:* a row for any income block, or none for a drawing one."""
    block, text = _render("fixed_pay_drop_row", FIXED_PAY_DROP)
    assert "your pay drops" not in text
    assert all(z["channel_id"] != INCOME_STREAM_ID
               for z in block["spread"]["structural_zeros"])
    spec = load_config_dict(copy.deepcopy(FIXED_PAY_DROP))
    assert INCOME_STREAM_ID not in oracle_drawn(spec)


# ---------------------------------------------------------------------------
# The threshold and the measurement, each able to fail both ways
# ---------------------------------------------------------------------------

def _priced(**pvs):
    return SimpleNamespace(**{o: (SimpleNamespace(pvs=np.asarray(pvs[o], dtype=float))
                                  if o in pvs else None)
                              for o in ("condo", "house", "rent")})


def test_the_threshold_is_the_identity_s_budget():
    """ONE threshold in one home: a move at the budget is inside it, a move
    past it is live, and a move of less than it is not.
    *Kills it:* exact equality (`> 0`: the half-budget move reads live), a
    widened budget (1000x: the twice-budget move reads dead), or `>=`."""
    t = 1e-9
    base = _priced(condo=[1.0, 1.0, 1.0], rent=[2.0, 2.0, 2.0])
    redraws = {
        3: _priced(condo=[1.0, 1.0 + 2 * t, 1.0], rent=[2.0, 2.0, 2.0]),
        6: _priced(condo=[1.0 + 0.5 * t, 1.0, 1.0], rent=[2.0, 2.0, 2.0]),
    }
    moves, live = dr._liveness(base, redraws, t, 3)
    assert moves[3] > t > moves[6] > 0.0
    assert live == (3,)
    # Exactly at the budget the move is inside it; one float below, past it.
    move = moves[3]
    assert dr._liveness(base, {3: redraws[3]}, move, 3)[1] == ()
    assert dr._liveness(base, {3: redraws[3]}, float(np.nextafter(move, 0.0)), 3)[1] == (3,)


def test_the_recorder_watches_every_generator_it_hands_out():
    """A stream draws when ANY of its generators advances, whichever future it
    belongs to. The simulator as written draws on every future or on none, so
    no config tells the first future from the rest; this is the constructed
    witness: one stream that draws on a later future only, one that draws on
    the first only, and one that never draws.
    *Kills it:* watching only the first generator of a stream, or only the
    last, or recording a stream that was handed out and never advanced."""
    def source(path_index):
        return np.random.default_rng(path_index)

    recorder = dr._DrawRecorder({3: source, 5: source, 6: source})
    later, first, never = recorder[3], recorder[5], recorder[6]
    for path_index in range(3):
        a, b, c = later(path_index), first(path_index), never(path_index)
        if path_index == 2:
            a.normal()
        if path_index == 0:
            b.normal()
    assert recorder.drawn() == (3, 5)


def test_every_option_and_every_future_is_compared():
    """A channel that moves only the last option, or only a later future, is
    live all the same.
    *Kills it:* comparing the first priced option only, or the first future."""
    t = 1e-9
    base = _priced(condo=[1.0, 1.0, 1.0], house=[3.0, 3.0, 3.0], rent=[2.0, 2.0, 2.0])
    only_rent = _priced(condo=[1.0, 1.0, 1.0], house=[3.0, 3.0, 3.0], rent=[2.0, 2.0, 5.0])
    only_later = _priced(condo=[1.0, 7.0, 1.0], house=[3.0, 3.0, 3.0], rent=[2.0, 2.0, 2.0])
    assert dr._liveness(base, {5: only_rent, 3: only_later}, t, 3)[1] == (3, 5)


def test_a_moving_income_stream_is_refused_by_name():
    """The income stream is not a channel, so a re-draw of it that moved a
    present value has no row to go to: the check fails (`income_moved`),
    stating the move, rather than printing a partition with a mover left
    out; a re-draw that moves nothing passes."""
    base = _priced(condo=[1.0], rent=[2.0])
    with pytest.raises(dr.CheckFailed) as failed:
        dr._liveness(base, {INCOME_STREAM_ID: _priced(condo=[1.0], rent=[3.0])}, 1e-9, 1)
    assert (failed.value.code, failed.value.reason) == ("income_moved", (
        "re-drawing the income stream moved an option's present value on these 1 "
        "futures by up to $1, above $1e-09"))
    assert dr._liveness(base, {INCOME_STREAM_ID: _priced(condo=[1.0], rent=[2.0])},
                        1e-9, 1)[1] == ()


# A condo fee volatility so small that re-drawing it moves the condo's present
# value by a few ten-millionths of a dollar: more than the identity's budget,
# far less than a thousand times it. The renter's portfolio is the other live
# channel.
TINY_FEE_VOLATILITY = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.01,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 200, "random_seed": 42, "condo_fee_vol": 5e-13,
                   "investment_return_vol": 0.10},
}
# A lease reset with a low hazard: on the first of these futures neither `A`
# nor `B` resets, and on others they do.
LOW_HAZARD_RESET = {
    "years": 10, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.01, "reset_hazard": 0.02,
             "reset_to_monthly_rent": 2500, "invested_down_payment": 355200,
             "investment_return_rate": 0.03},
    "simulation": {"num_sims": 200, "random_seed": 42, "condo_fee_vol": 0.05},
}


def test_a_move_a_little_past_the_budget_is_live_in_the_printed_block():
    """*Kills it:* a threshold widened to 1000x the budget — the condo's
    costs drop out and the block refuses `one_channel` for the portfolio."""
    spec = load_config_dict(copy.deepcopy(TINY_FEE_VOLATILITY))
    limit = threshold(spec)
    moves = oracle_moves(spec, spec.simulation.num_sims)
    assert limit < moves[3] < 1000 * limit
    block, text = _render("tiny_fee_volatility", TINY_FEE_VOLATILITY)
    assert text.splitlines()[0] == "which risk decides it — 200 futures, 2 channels live on them"
    assert block["live_channel_ids"] == [3, 6]


def test_a_channel_that_moves_only_later_futures_is_live_in_the_printed_block():
    """*Kills it:* comparing the first future only — the tenancy drops out
    and the block refuses `one_channel` for the condo."""
    spec = load_config_dict(copy.deepcopy(LOW_HAZARD_RESET))
    small = dr._spec_at(spec, 200)
    base = dr._run(small, dr.MATRIX_A)
    redrawn = dr._run(small, dr.MATRIX_A, {5: dr.MATRIX_B})
    first = abs(float(np.asarray(base.rent.pvs)[0] - np.asarray(redrawn.rent.pvs)[0]))
    assert first == 0.0
    block, text = _render("low_hazard_reset", LOW_HAZARD_RESET)
    assert text.splitlines()[0] == "which risk decides it — 200 futures, 2 channels live on them"
    assert block["live_channel_ids"] == [3, 5]


def test_a_channel_that_moves_only_a_later_option_is_live_in_the_printed_block():
    """*Kills it:* comparing the first priced option only — the tenancy moves
    rent alone, drops out, and the block refuses `one_channel` for the
    economy. The config is `nominal_zero_escalation_no_fee`."""
    block, text = _render("later_option", NOMINAL_ZERO_ESCALATION_NO_FEE)
    assert block["live_channel_ids"] == [0, 5]
    assert text.splitlines()[0].endswith("2 channels live on them")


# ---------------------------------------------------------------------------
# A generative sweep
# ---------------------------------------------------------------------------

def _random_config(rng):
    pick = rng.choice

    def event():
        e = {"name": "ev", "base_cost": pick([0, 5000]), "cost_vol": pick([0.0, 0.2]),
             "expected_year": pick([3, 8])}
        if pick([True, False]):
            e.update({"timing_model": "hazard", "hazard_base": pick([0.0, 0.05, 1.0]),
                      "hazard_growth": pick([0.0, 0.01])})
        else:
            e["timing_std_years"] = pick([0.0, 2.0])
        return e

    mode = pick(["real", "nominal"])
    raw = {"years": pick([10, 20]), "discount_rate": 0.03,
           "economic": {"mode": mode, "inflation_rate": pick([0.0, 0.02]),
                        "inflation_vol": pick([0.0, 0.02])}}
    options = pick([("condo", "rent"), ("house", "rent"), ("condo", "house"),
                    ("condo", "house", "rent")])
    if "condo" in options:
        raw["condo"] = {"monthly_fee": pick([0, 450]), "fee_escalation_rate": pick([0.0, 0.02]),
                        "initial_value": 350000, "all_cash": True, "purchase_costs": 5200,
                        "value_growth_rate": pick([0.0, 0.02])}
        if pick([True, False]):
            raw["condo"]["events"] = [event()]
        if pick([True, False, False]):
            raw["condo"]["price_shock"] = {"annual_hazard": pick([0.0, 0.03]),
                                           "severity_mean": pick([0.0, 0.2])}
    if "house" in options:
        raw["house"] = {"initial_value": 450000, "all_cash": True, "purchase_costs": 5000,
                        "annual_maintenance_rate": pick([0.0, 0.01]),
                        "value_growth_rate": pick([0.0, 0.02])}
        if pick([True, False]):
            raw["house"]["other_recurring_costs"] = [
                {"name": "property_tax", "annual_amount": pick([0, 3000]),
                 "escalation_rate": pick([0.0, 0.02])}]
    if "rent" in options:
        raw["rent"] = {"monthly_rent": pick([1150, 1500]),
                       "rent_escalation_rate": pick([0.0, 0.01]),
                       "invested_down_payment": pick([0, 355200]),
                       "investment_return_rate": 0.03}
        if pick([True, False, False]):
            raw["rent"].update({"reset_hazard": 0.1, "reset_to_monthly_rent": pick([1500, 2500]),
                                "reset_market_escalation_rate": pick([0.0, 0.01])})
        if pick([True, False]):
            raw["rent"]["events"] = [event()]
    sim = {"num_sims": 40, "random_seed": 3}
    for key in ("condo_fee_vol", "house_maintenance_vol", "other_cost_vol",
                "rent_escalation_vol", "investment_return_vol", "value_growth_vol"):
        sim[key] = pick([0.0, 0.0, 0.1])
    if mode == "real" and pick([True, False]):
        sim[pick(["corr_inflation_condo", "corr_inflation_house", "corr_inflation_other",
                  "corr_inflation_event_cost"])] = 0.5
    raw["simulation"] = sim
    return raw


def test_the_measurement_agrees_with_the_instruments_on_random_configs():
    """Thirty random loadable configs, at 40 futures: the streams the engine
    counts as drawing are the ones whose held generators advance, and the
    channels it counts as live are the ones whose re-seeding moves a present
    value past the identity's budget. The sweep that found the config-read
    copy's 19 disagreements ran this comparison on 800 configs.
    *Kills it:* any rule that answers either question another way."""
    rng = random.Random(20260926)
    checked = 0
    while checked < 30:
        raw = _random_config(rng)
        try:
            spec = load_config_dict(raw)
        except Exception:  # the loader refuses it: not a config a user can run
            continue
        checked += 1
        det = compute_deterministic(spec)
        verdict = compute_verdict(det, years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate)
        got = dr.measure_channels(spec, det=det, verdict=verdict, paths=40)
        assert set(got.drawn) == oracle_drawn(spec), raw
        moves = oracle_moves(spec, 40)
        assert set(got.live) == {c for c in range(7) if moves[c] > got.threshold}, raw
        assert moves[INCOME_STREAM_ID] <= got.threshold, raw
