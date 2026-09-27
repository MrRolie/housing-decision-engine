"""One event, one world (docs/specs/2026-09-27-events-in-one-world.md).

The best guess charges an event once, in the year the config places it; the
futures time it by its model. These tests pin what the spec ruled: a config
whose event cannot happen, or whose window contradicts itself, is refused at
load (E2); a hazard fires only inside its window (E3); the single-path gate
asks whether the futures' timing can differ (E4); the futures' affordability
arrays place each event on each path (E5); and the read-back states, for every
hazard-timed event, the facts of its schedule (E1).
"""
from __future__ import annotations

import copy
import math
import sys

import numpy as np
import pytest
import yaml

from hde.config import ConfigValidationError, dispersion_sources, load_config_dict, single_path_run
from hde.deterministic import compute_deterministic
from hde.models import (
    ComparisonSpec, EconomicParams, EventConfig, HouseParams, RentParams, SimulationParams,
)
from hde.monte_carlo import run_monte_carlo
from hde.pv import pv_single
from hde.serialization import read_back_lines

YEARS = 20
RATE = 0.03


def _cfg(*events, option="house", years=YEARS, sims=200):
    """An all-cash house against a rent, every uncertainty input off, with
    `events` on `option`."""
    cfg = {"years": years, "discount_rate": RATE, "rates": "real",
           "house": {"initial_value": 300000, "all_cash": True,
                     "annual_maintenance_rate": 0.0, "value_growth_rate": 0.0},
           "rent": {"monthly_rent": 829, "rent_escalation_rate": 0.0},
           "simulation": {"num_sims": sims, "random_seed": 42}}
    if option == "condo":
        cfg["condo"] = {"monthly_fee": 300, "fee_escalation_rate": 0.0,
                        "initial_value": 300000, "all_cash": True}
    cfg[option]["events"] = [dict(e) for e in events]
    return cfg


def _roof(**fields):
    return {"name": "roof", "base_cost": 15000, "expected_year": 8, **fields}


def _refused(cfg) -> str:
    with pytest.raises(ConfigValidationError) as info:
        load_config_dict(cfg)
    return str(info.value)


# ---------------------------------------------------------------------------
# E2 — the loader refuses, naming the key and the fact; one step away loads
# ---------------------------------------------------------------------------

_PAY_DROP_BASE = {"annual_income": 90000, "income_growth_rate": 0.0}

# (refused config, the refusal line, the legal config one step away)
REFUSALS = {
    "hazard zero throughout": (
        _cfg(_roof(timing_model="hazard")),
        "house.events['roof']: timing_model hazard, but the hazard is 0 in every year it "
        "can fire [1, 20]: no future fires it",
        _cfg(_roof(timing_model="hazard", hazard_growth=0.01))),
    "hazard zero in a one-year window": (
        _cfg(_roof(timing_model="hazard", hazard_growth=0.01, hazard_start_year=8,
                   max_year=8, min_year=8)),
        "house.events['roof']: timing_model hazard, but the hazard is 0 in every year it "
        "can fire [8, 8]: no future fires it",
        _cfg(_roof(timing_model="hazard", hazard_growth=0.01, hazard_start_year=8,
                   max_year=9, min_year=8))),
    "hazard starts after the horizon": (
        _cfg(_roof(timing_model="hazard", hazard_base=0.1, hazard_start_year=21)),
        "house.events['roof'].hazard_start_year (21) > years (20): no future fires it",
        _cfg(_roof(timing_model="hazard", hazard_base=0.1, hazard_start_year=20))),
    "hazard starts after max_year": (
        _cfg(_roof(timing_model="hazard", hazard_base=0.1, hazard_start_year=11, max_year=10)),
        "house.events['roof'].hazard_start_year (11) > max_year (10): no future fires it",
        _cfg(_roof(timing_model="hazard", hazard_base=0.1, hazard_start_year=10, max_year=10))),
    "min_year beyond the horizon": (
        _cfg(_roof(expected_year=20, min_year=21)),
        "house.events['roof'].min_year (21) > years (20)",
        _cfg(_roof(expected_year=20, min_year=20))),
    "min_year above max_year": (
        _cfg(_roof(expected_year=10, min_year=11, max_year=10)),
        "house.events['roof'].min_year (11) > max_year (10)",
        _cfg(_roof(expected_year=10, min_year=10, max_year=10))),
    "expected_year below its window": (
        _cfg(_roof(expected_year=4, min_year=5)),
        "house.events['roof'].expected_year (4) is outside its window [5, 20]",
        _cfg(_roof(expected_year=5, min_year=5))),
    "expected_year above its window": (
        _cfg(_roof(expected_year=11, max_year=10)),
        "house.events['roof'].expected_year (11) is outside its window [1, 10]",
        _cfg(_roof(expected_year=10, max_year=10))),
    "two events with one name": (
        _cfg(_roof(), _roof(expected_year=15)),
        "house.events: 2 events are named 'roof'",
        _cfg(_roof(), {**_roof(expected_year=15), "name": "roof_2"})),
    "negative timing_std_years": (
        _cfg(_roof(timing_std_years=-1.0)),
        "house.events['roof'].timing_std_years should be >= 0, got -1.0",
        _cfg(_roof(timing_std_years=0.0))),
    "negative cost_vol": (
        _cfg(_roof(cost_vol=-0.1)),
        "house.events['roof'].cost_vol should be >= 0, got -0.1",
        _cfg(_roof(cost_vol=0.0))),
    "pay drop after the horizon": (
        {**_cfg(_roof()), "income": {**_PAY_DROP_BASE,
                                     "pay_drop_events": [{"year": 21, "magnitude": 0.5}]}},
        "income.pay_drop_events year (21) is outside the horizon [1, 20]",
        {**_cfg(_roof()), "income": {**_PAY_DROP_BASE,
                                     "pay_drop_events": [{"year": 20, "magnitude": 0.5}]}}),
    "pay drop before year 1": (
        {**_cfg(_roof()), "income": {**_PAY_DROP_BASE,
                                     "pay_drop_events": [{"year": 0, "magnitude": 0.5}]}},
        "income.pay_drop_events year (0) is outside the horizon [1, 20]",
        {**_cfg(_roof()), "income": {**_PAY_DROP_BASE,
                                     "pay_drop_events": [{"year": 1, "magnitude": 0.5}]}}),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_each_refusal_names_the_key_and_the_fact_and_one_step_away_loads(case):
    refused, line, legal = REFUSALS[case]
    message = _refused(copy.deepcopy(refused))
    assert line in message.splitlines(), message
    load_config_dict(copy.deepcopy(legal))


def test_the_refusals_reach_every_option():
    """The same refusal on the condo and the renter, by their own keys."""
    for option in ("condo", "rent"):
        message = _refused(_cfg(_roof(timing_model="hazard"), option=option))
        assert f"{option}.events['roof']: timing_model hazard" in message


# The rent futures indexed past the horizon on this config and crashed with a
# traceback (C8). The loader refuses it now, and the CLI says why.
C8_CRASH = {"years": 20, "discount_rate": 0.03, "rates": "real",
            "house": {"initial_value": 300000, "all_cash": True,
                      "annual_maintenance_rate": 0.0, "value_growth_rate": 0.0},
            "rent": {"monthly_rent": 784, "rent_escalation_rate": 0.0,
                     "events": [{"name": "move", "base_cost": 5000, "expected_year": 10,
                                 "min_year": 25}]},
            "simulation": {"num_sims": 2000}}


def test_the_config_that_crashed_the_rent_futures_is_refused(tmp_path, monkeypatch, capsys):
    assert "rent.events['move'].min_year (25) > years (20)" in _refused(copy.deepcopy(C8_CRASH))
    path = tmp_path / "c8.yaml"
    path.write_text(yaml.safe_dump(C8_CRASH))
    from hde.cli import main
    monkeypatch.setattr(sys, "argv", ["hde", str(path)])
    assert main() == 1
    err = capsys.readouterr().err
    assert "rent.events['move'].min_year (25) > years (20)" in err
    assert "Traceback" not in err and "IndexError" not in err


def _rent_spec(event: EventConfig) -> ComparisonSpec:
    return ComparisonSpec(
        simulation=SimulationParams(years=YEARS, discount_rate=RATE, num_sims=50),
        economic=EconomicParams(),
        house=HouseParams(initial_value=300000, all_cash=True, annual_maintenance_rate=0.0,
                          value_growth_rate=0.0),
        rent=RentParams(monthly_rent=784, rent_escalation_rate=0.0, events=[event]))


def test_the_rent_futures_never_index_past_the_horizon():
    """Built in code the loader never sees: the rent futures skip a year past
    the horizon, as the owned loops do, and still charge the horizon's last."""
    past = run_monte_carlo(_rent_spec(EventConfig("move", 5000, expected_year=10, min_year=25)))
    none = run_monte_carlo(_rent_spec(EventConfig("move", 0, expected_year=10)))
    assert past.rent.summary.mean == pytest.approx(none.rent.summary.mean)
    last = run_monte_carlo(_rent_spec(EventConfig("move", 5000, expected_year=YEARS)))
    assert last.rent.summary.mean - none.rent.summary.mean == pytest.approx(
        pv_single(5000, RATE, YEARS))


# ---------------------------------------------------------------------------
# Recovering each future's fire year from its present value
# ---------------------------------------------------------------------------

def _fire_years(cfg, option="house"):
    """The year each future fired the one event on `option` (None: never), read
    off the path's present value against the same config without the event.
    Every other input is off, so the event is the only difference."""
    spec = load_config_dict(copy.deepcopy(cfg))
    base_cost = spec.house.events[0].base_cost if option == "house" else None
    bare = copy.deepcopy(cfg)
    bare[option]["events"] = []
    with_event = getattr(run_monte_carlo(spec), option).pvs
    without = getattr(run_monte_carlo(load_config_dict(bare)), option).pvs
    assert np.ptp(without) < 1e-6
    years = []
    for gap in with_event - without:
        if abs(gap) < 1e-6:
            years.append(None)
            continue
        (year,) = [t for t in range(1, spec.simulation.years + 1)
                   if abs(pv_single(base_cost, spec.simulation.discount_rate, t) - gap) < 1e-6]
        years.append(year)
    return years


# ---------------------------------------------------------------------------
# E3 — a hazard fires only inside its window (C5)
# ---------------------------------------------------------------------------

C5 = _cfg(_roof(expected_year=16, timing_model="hazard", hazard_base=0.10,
                min_year=15, max_year=18), sims=4000)


def test_a_hazard_fires_only_inside_the_stated_window():
    """C5: before, the futures fired this event before min_year on 77% of paths
    and after max_year on 3%."""
    years = _fire_years(C5)
    fired = [y for y in years if y is not None]
    assert set(fired) == {15, 16, 17, 18}
    p = 1 - 0.9 ** 4
    se = math.sqrt(p * (1 - p) / len(years))
    assert abs(len(fired) / len(years) - p) < 4 * se


# ---------------------------------------------------------------------------
# E4 — the gate asks whether the futures' timing can differ
# ---------------------------------------------------------------------------

GATE = {
    "hazard below certainty": (_roof(timing_model="hazard", hazard_base=0.1), False),
    "hazard certain in its first year": (_roof(timing_model="hazard", hazard_base=1.0,
                                               hazard_start_year=8), True),
    "jitter across a window": (_roof(timing_std_years=2.0, min_year=7, max_year=8), False),
    "jitter inside a one-year window": (_roof(timing_std_years=2.0, min_year=8, max_year=8), True),
    "fixed": (_roof(), True),
    "fixed with a drawn cost": (_roof(cost_vol=0.2), False),
}


@pytest.mark.parametrize("case", sorted(GATE))
def test_the_gate_classes_an_event_by_whether_its_futures_can_differ(case):
    event, single = GATE[case]
    spec = load_config_dict(_cfg(event))
    assert single_path_run(spec) is single
    owned, _, _ = dispersion_sources(spec)
    assert ("house.events" in owned) is not single
    if single:
        # the gate's meaning: the futures would all be one path
        assert np.ptp(run_monte_carlo(spec).house.pvs) < 1e-6


# ---------------------------------------------------------------------------
# E5 — the futures' affordability arrays place each event on each path (C12)
# ---------------------------------------------------------------------------

def _c12(event, income):
    cfg = _cfg(event, option="condo", sims=4000)
    cfg["condo"]["events"][0]["name"] = "assessment"
    cfg["income"] = {"income_growth_rate": 0.0, "affordability_threshold": 0.32, **income}
    return cfg


def test_the_affordability_futures_charge_an_event_on_the_paths_that_fire_it():
    """C12: fees $3,600 are 9% of $40,000 and the $15,000 assessment lifts the
    year to 46.5%, so a path breaches exactly when it fires the event. Before,
    every path read the best guess's array and the answer was 1.0."""
    cfg = _c12(_roof(timing_model="hazard", hazard_base=0.03), {"annual_income": 40000})
    spec = load_config_dict(copy.deepcopy(cfg))
    pvs = run_monte_carlo(spec).condo.pvs
    fired = pvs - pvs.min() > 1.0
    mc = run_monte_carlo(spec)
    assert mc.affordability_mc.prob_condo_exceeds == pytest.approx(float(np.mean(fired)))
    p = 1 - 0.97 ** 20
    assert abs(float(np.mean(fired)) - p) < 4 * math.sqrt(p * (1 - p) / 4000)


def test_the_affordability_futures_place_an_event_in_the_path_s_own_year():
    """With the event at $15,000 and fees at $3,600, the year is 31% of $60,000
    and 38.75% after a 20% cut in year 10: a path breaches exactly when its
    event lands in year 10 or later. The best guess's year 10 on every path
    would say 1.0."""
    cfg = _c12(_roof(expected_year=10, timing_std_years=3.0),
               {"annual_income": 60000, "pay_drop_events": [{"year": 10, "magnitude": 0.8}]})
    spec = load_config_dict(copy.deepcopy(cfg))
    mc = run_monte_carlo(spec)
    bare = copy.deepcopy(cfg)
    bare["condo"]["events"] = []
    gaps = mc.condo.pvs - run_monte_carlo(load_config_dict(bare)).condo.pvs
    late = gaps < pv_single(15000, RATE, 10) + 1e-6
    assert 0.3 < float(np.mean(late)) < 0.8
    assert mc.affordability_mc.prob_condo_exceeds == pytest.approx(float(np.mean(late)))


# ---------------------------------------------------------------------------
# E1 — the read-back states the hazard schedule's facts, exactly
# ---------------------------------------------------------------------------

def _independent_facts(base, growth, start, first, last):
    """P(fires in [first, last]) and the first year by which half of ALL
    futures have fired it, from the survival product, written out here."""
    alive = 1.0
    half = None
    for t in range(first, last + 1):
        h = base + growth * (t - start) if t >= start else 0.0
        alive *= 1 - min(max(h, 0.0), 1.0)
        if half is None and alive <= 0.5:
            half = t
    return 1 - alive, half


def _best_guess(cfg):
    spec = load_config_dict(copy.deepcopy(cfg))
    return [line for line in read_back_lines(spec) if line.startswith("best guess:")]


# The advanced example's condo assessment, on a house with every other input off.
RISING = _cfg({"name": "exterior", "base_cost": 8000, "expected_year": 12,
               "timing_model": "hazard", "hazard_base": 0.05, "hazard_growth": 0.03,
               "hazard_start_year": 8, "min_year": 8, "max_year": 18},
              years=30, sims=4000)
# C3: a flat 3% over 20 years fires on fewer than half of the futures.
FLAT = _cfg(_roof(expected_year=10, timing_model="hazard", hazard_base=0.03), sims=4000)


def test_the_read_back_states_the_hazard_schedule_exactly():
    p, half = _independent_facts(0.05, 0.03, 8, 8, 18)
    assert half == 13 and p == pytest.approx(0.9206, abs=1e-4)
    assert _best_guess(RISING) == [
        f"best guess: house.events['exterior'] is charged in year 12; on its hazard "
        f"{p:.1%} of futures fire it within the 30 years, and half of all futures have "
        f"by year {half}"]
    p, half = _independent_facts(0.03, 0.0, 1, 1, 20)
    assert half is None
    assert _best_guess(FLAT) == [
        f"best guess: house.events['roof'] is charged in year 10; on its hazard {p:.1%} "
        f"of futures fire it within the 20 years, so fewer than half ever do"]


@pytest.mark.parametrize("cfg", [RISING, FLAT], ids=["rising", "flat"])
def test_the_read_back_facts_hold_on_the_futures_themselves(cfg):
    """The same figures, measured: the share of futures that fire the event is
    within four standard errors of the printed one, and on RISING, whose
    half-year sits about seven standard errors from either neighbour, half of
    the futures have fired it by the printed year and not the year before."""
    event = cfg["house"]["events"][0]
    years = _fire_years(cfg)
    n = len(years)
    p, half = _independent_facts(event["hazard_base"], event.get("hazard_growth", 0.0),
                                 event.get("hazard_start_year", 1),
                                 max(event.get("min_year", 1), event.get("hazard_start_year", 1)),
                                 min(event.get("max_year", cfg["years"]), cfg["years"]))
    fired = [y for y in years if y is not None]
    assert abs(len(fired) / n - p) < 4 * math.sqrt(p * (1 - p) / n)
    if half is not None:
        assert sum(y <= half for y in fired) / n >= 0.5
        assert sum(y <= half - 1 for y in fired) / n < 0.5
    else:
        assert len(fired) / n < 0.5


def test_a_jitter_event_prints_no_hazard_line():
    assert _best_guess(_cfg(_roof(timing_std_years=2.0))) == []


def test_the_reset_and_the_crash_are_named_only_when_the_futures_draw_them():
    cfg = _cfg(_roof())
    cfg["rent"].update({"reset_hazard": 0.07, "reset_to_monthly_rent": 1100})
    cfg["house"]["price_shock"] = {"annual_hazard": 0.03}
    assert _best_guess(cfg) == [
        "best guess: the rent is priced on a tenancy that never resets; the futures reset "
        "it at 7.0%/yr (rent.reset_hazard)",
        "best guess: the house is priced with no price crash; the futures draw one at "
        "3.0%/yr (house.price_shock.annual_hazard)"]
    cfg["house"]["price_shock"] = {"annual_hazard": 0.0}
    del cfg["rent"]["reset_hazard"], cfg["rent"]["reset_to_monthly_rent"]
    assert _best_guess(cfg) == []


def test_the_facts_ride_the_json_read_back(tmp_path, monkeypatch, capsys):
    import json
    path = tmp_path / "flat.yaml"
    path.write_text(yaml.safe_dump(FLAT))
    from hde.cli import main
    monkeypatch.setattr(sys, "argv", ["hde", str(path), "--json"])
    assert main() == 0
    doc = json.loads(capsys.readouterr().out)
    assert _best_guess(FLAT)[0] in doc["assumptions"]["read_back"]


def test_the_schema_states_every_refusal_and_the_hazard_window():
    from hde.input_schema import input_schema
    schema = input_schema()
    for option in ("condo", "house", "rent"):
        note = schema[option]["events"]["note"]
        assert ("A hazard (timing_model: hazard) fires only from max(min_year, "
                "hazard_start_year) to min(max_year, years)") in note
        for fact in ("two events with one name", "min_year past years or above max_year",
                     "expected_year outside [min_year, max_year]",
                     "a negative timing_std_years or cost_vol",
                     "a hazard whose hazard_start_year is past years or max_year, or that is 0 "
                     "in every year it can fire"):
            assert fact in note, (option, fact)
    assert "a year outside [1, years] is REFUSED" in schema["income"]["pay_drop_events"]["note"]


@pytest.mark.parametrize("hazard, share", [
    (1.0, "100.0%"),       # certain in year 1: exactly all
    (0.4, "over 99.9%"),   # 1 - 0.6**20 = 0.99996: not all
    (1e-6, "under 0.1%"),  # 1 - (1 - 1e-6)**20 = 0.00002: not none
])
def test_a_share_never_prints_as_certain_or_as_none_when_it_is_not(hazard, share):
    (line,) = _best_guess(_cfg(_roof(expected_year=1, timing_model="hazard",
                                     hazard_base=hazard)))
    assert f"on its hazard {share} of futures fire it" in line
