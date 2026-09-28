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
from hde.sources import uncertainty_keys

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
        _cfg(_roof(expected_year=20, timing_model="hazard", hazard_base=0.1,
                   hazard_start_year=21)),
        "house.events['roof'].hazard_start_year (21) > years (20): no future fires it",
        _cfg(_roof(expected_year=20, timing_model="hazard", hazard_base=0.1,
                   hazard_start_year=20))),
    "hazard starts after max_year": (
        _cfg(_roof(expected_year=10, timing_model="hazard", hazard_base=0.1,
                   hazard_start_year=11, max_year=10)),
        "house.events['roof'].hazard_start_year (11) > max_year (10): no future fires it",
        _cfg(_roof(expected_year=10, timing_model="hazard", hazard_base=0.1,
                   hazard_start_year=10, max_year=10))),
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
    "expected_year past the horizon": (
        _cfg(_roof(expected_year=21)),
        "Event 'roof' has expected_year (21) > years (20)",
        _cfg(_roof(expected_year=20))),
    "expected_year before its hazard starts": (
        _cfg(_roof(expected_year=3, timing_model="hazard", hazard_base=0.2,
                   hazard_start_year=10)),
        "house.events['roof'].expected_year (3) is outside its window [10, 20]",
        _cfg(_roof(expected_year=10, timing_model="hazard", hazard_base=0.2,
                   hazard_start_year=10))),
    "hazard-timed min_year beyond the horizon": (
        _cfg(_roof(expected_year=20, min_year=21, timing_model="hazard", hazard_base=0.1)),
        "house.events['roof'].min_year (21) > years (20)",
        _cfg(_roof(expected_year=20, min_year=20, timing_model="hazard", hazard_base=0.1))),
    "hazard-timed min_year above max_year": (
        _cfg(_roof(expected_year=10, min_year=11, max_year=10, timing_model="hazard",
                   hazard_base=0.1)),
        "house.events['roof'].min_year (11) > max_year (10)",
        _cfg(_roof(expected_year=10, min_year=10, max_year=10, timing_model="hazard",
                   hazard_base=0.1))),
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
    """One defect, one line: a refusal that empties the window stops there, so
    no line follows it about a window that no longer exists."""
    refused, line, legal = REFUSALS[case]
    message = _refused(copy.deepcopy(refused))
    assert message.splitlines() == ["Configuration validation failed:", line], message
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


def test_the_glossary_states_the_hazard_s_window():
    from pathlib import Path
    glossary = " ".join((Path(__file__).parent.parent / "docs/reference/ARCHITECTURE.md")
                        .read_text().split())
    assert ("`hazard` → the first year of `[max(min_year, hazard_start_year), min(max_year, "
            "years)]` in which a uniform draw falls under") in glossary


def test_a_hazard_that_starts_inside_the_window_fires_from_its_start():
    """The window's first year is the later of min_year and hazard_start_year."""
    late_start = copy.deepcopy(C5)
    late_start["house"]["events"][0]["hazard_start_year"] = 16
    fired = {y for y in _fire_years(late_start) if y is not None}
    assert fired == {16, 17, 18}


# ---------------------------------------------------------------------------
# E4 — the gate asks whether the futures' timing can differ
# ---------------------------------------------------------------------------

GATE = {
    "hazard below certainty": (_roof(timing_model="hazard", hazard_base=0.1), False),
    "hazard certain in its first year": (_roof(timing_model="hazard", hazard_base=1.0,
                                               hazard_start_year=8), True),
    "hazard certain from year 1, charged there": (_roof(expected_year=1, timing_model="hazard",
                                                        hazard_base=1.0), True),
    "hazard certain in its first year, charged later": (
        _roof(expected_year=20, timing_model="hazard", hazard_base=1.0, hazard_start_year=2),
        False),
    "jitter across a window": (_roof(timing_std_years=2.0, min_year=7, max_year=8), False),
    "jitter inside a one-year window": (_roof(timing_std_years=2.0, min_year=8, max_year=8), True),
    "fixed": (_roof(), True),
    "fixed with a drawn cost": (_roof(cost_vol=0.2), False),
}


@pytest.mark.parametrize("case", sorted(GATE))
def test_the_gate_classes_an_event_by_whether_its_futures_can_differ(case):
    """A single-path run is one whose every future IS the best guess, and the
    uncertainty-inputs list names the events exactly when the gate reads them
    as drawn."""
    event, single = GATE[case]
    cfg = _cfg(event)
    spec = load_config_dict(copy.deepcopy(cfg))
    assert single_path_run(spec) is single
    owned, _, _ = dispersion_sources(spec)
    assert ("house.events" in owned) is not single
    assert ("house.events" in uncertainty_keys(cfg)) is not single
    gaps = run_monte_carlo(spec).house.pvs - compute_deterministic(spec).house.total_pv
    assert bool(np.all(np.abs(gaps) < 1e-6)) is single


def _stdout(tmp_path, monkeypatch, capsys, cfg, *flags):
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(cfg))
    from hde.cli import main
    monkeypatch.setattr(sys, "argv", ["hde", str(path), *flags])
    assert main() == 0
    return capsys.readouterr().out


@pytest.mark.parametrize("cost, rent", [(60000, 1080), (15000, 850)], ids=["decisive", "tie"])
def test_a_certain_hazard_in_another_year_is_named_a_disagreement(
        tmp_path, monkeypatch, capsys, cost, rent):
    """Every future fires the roof in year 2 and the best guess charges it in
    year 20, so every future says rent where the best guess says house."""
    cfg = _cfg({**_roof(expected_year=20, timing_model="hazard", hazard_base=1.0,
                        hazard_start_year=2), "base_cost": cost}, sims=1000)
    cfg["rent"]["monthly_rent"] = rent
    out = _stdout(tmp_path, monkeypatch, capsys, cfg)
    assert "most futures say Rent (100% cheapest) — the two disagree, not decisive" in out
    assert "single-path run" not in out


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


def test_each_option_reads_its_own_affordability_array(tmp_path, monkeypatch, capsys):
    """The condo's $15,000 assessment lifts its year to 44% of $42,000 and the
    house's $1,000 repair to 2.4%. On the paths where both fire in the same
    year, each still reads its own array: the house never breaches."""
    cfg = _c12(_roof(timing_model="hazard", hazard_base=0.2), {"annual_income": 42000})
    cfg["house"]["events"] = [{**_roof(timing_model="hazard", hazard_base=0.2),
                               "name": "repair", "base_cost": 1000}]
    import json
    out = _stdout(tmp_path, monkeypatch, capsys, cfg, "--json")
    afford = json.loads(out)["monte_carlo"]["affordability_mc"]
    pvs = run_monte_carlo(load_config_dict(copy.deepcopy(cfg))).condo.pvs
    assert afford["prob_condo_exceeds"] == pytest.approx(float(np.mean(pvs - pvs.min() > 1.0)))
    assert afford["prob_condo_exceeds"] > 0.9
    assert afford["prob_house_exceeds"] == 0.0


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
# A hazard that grows from year 5 in a window that opens in year 10.
GROWS_BEFORE_WINDOW = _cfg(_roof(expected_year=12, timing_model="hazard", hazard_base=0.01,
                                 hazard_growth=0.02, hazard_start_year=5, min_year=10))


def _event_line(name, charged, share, half, years=YEARS, option="house"):
    when = (f"and that chance reaches one half by year {half}" if half is not None
            else "and that chance never reaches one half")
    return (f"best guess: {option}.events['{name}'] is charged in year {charged}; on its "
            f"hazard schedule the chance it fires within the {years} years is {share}, {when}")


def test_the_read_back_states_the_hazard_schedule_exactly():
    p, half = _independent_facts(0.05, 0.03, 8, 8, 18)
    assert half == 13 and p == pytest.approx(0.9206, abs=1e-4)
    assert _best_guess(RISING) == [_event_line("exterior", 12, f"{p:.1%}", half, years=30)]
    p, half = _independent_facts(0.03, 0.0, 1, 1, 20)
    assert half is None
    assert _best_guess(FLAT) == [_event_line("roof", 10, f"{p:.1%}", None)]
    # growth counts from hazard_start_year, not from the window's first year
    p, half = _independent_facts(0.01, 0.02, 5, 10, 20)
    assert half == 14 and p == pytest.approx(0.928, abs=1e-3)
    assert _best_guess(GROWS_BEFORE_WINDOW) == [_event_line("roof", 12, f"{p:.1%}", half)]


@pytest.mark.parametrize("fields, share, half", [
    # 0.5, then 1.1 clamped to 1: certain by year 2, half by year 1
    ({"hazard_base": 0.5, "hazard_growth": 0.6}, "100.0%", 1),
    # a flat 0.5: exactly one half by year 1
    ({"hazard_base": 0.5}, "over 99.9%", 1),
])
def test_the_schedule_is_clamped_and_reaches_one_half_at_exactly_one_half(fields, share, half):
    cfg = _cfg(_roof(expected_year=1, timing_model="hazard", **fields))
    assert _best_guess(cfg) == [_event_line("roof", 1, share, half)]


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


def _reset_line(rate):
    return ("best guess: the rent is priced on a tenancy that never resets; on the model's "
            f"schedule it resets with a chance of {rate} a year (rent.reset_hazard)")


def _crash_line(option, rate, key=None):
    key = key or f"{option}.price_shock.annual_hazard"
    return (f"best guess: the {option} is priced with no price crash; on the model's "
            f"schedule a crash comes with a chance of {rate} a year ({key})")


def test_the_reset_and_the_crash_are_named_only_when_the_model_draws_them():
    cfg = _cfg(_roof())
    cfg["rent"].update({"reset_hazard": 0.07, "reset_to_monthly_rent": 1100})
    cfg["house"]["price_shock"] = {"annual_hazard": 0.03}
    assert _best_guess(cfg) == [_reset_line("7.0%"), _crash_line("house", "3.0%")]
    cfg["house"]["price_shock"] = {"annual_hazard": 0.0}
    del cfg["rent"]["reset_hazard"], cfg["rent"]["reset_to_monthly_rent"]
    assert _best_guess(cfg) == []


# A hazard-timed event on each option, the lease reset and a crash on each owned one.
EVERY_OPTION = _cfg(_roof(timing_model="hazard", hazard_base=0.1), option="condo")
EVERY_OPTION["condo"]["events"][0]["name"] = "assessment"
EVERY_OPTION["house"]["events"] = [_roof(timing_model="hazard", hazard_base=0.1)]
EVERY_OPTION["rent"]["events"] = [{**_roof(timing_model="hazard", hazard_base=0.1),
                                   "name": "move"}]
EVERY_OPTION["rent"].update({"reset_hazard": 0.07, "reset_to_monthly_rent": 1100})
EVERY_OPTION["condo"]["price_shock"] = {"annual_hazard": 0.02}
EVERY_OPTION["house"]["price_shock"] = {"annual_hazard": 0.03}


def test_every_option_s_lines_in_order_and_the_short_block_counts_them():
    p, half = _independent_facts(0.1, 0.0, 1, 1, 20)
    assert _best_guess(EVERY_OPTION) == [
        _event_line("assessment", 8, f"{p:.1%}", half, option="condo"),
        _event_line("roof", 8, f"{p:.1%}", half, option="house"),
        _event_line("move", 8, f"{p:.1%}", half, option="rent"),
        _reset_line("7.0%"),
        _crash_line("condo", "2.0%"),
        _crash_line("house", "3.0%")]
    spec = load_config_dict(copy.deepcopy(EVERY_OPTION))
    full = read_back_lines(spec)
    *body, closing = read_back_lines(spec, short=True)
    assert not any(line.startswith("best guess:") for line in body)
    assert closing.startswith(f"full read-back: {len(full) - len(body)} more lines (")
    assert "best guess" in closing


def test_the_lines_state_the_schedule_on_a_run_with_no_futures(tmp_path, monkeypatch, capsys):
    """The facts are the model's schedule, not a count of paths, so a run with
    no futures prints the same lines and none of them speaks of futures."""
    lines = _best_guess(EVERY_OPTION)
    for flags in ((), ("--no-monte-carlo",)):
        out = _stdout(tmp_path, monkeypatch, capsys, EVERY_OPTION, *flags)
        assert [x for x in out.splitlines() if x.startswith("best guess:")] == lines
    assert not any("futures" in line for line in lines)


@pytest.mark.parametrize("rate, text", [
    (0.0004, "under 0.1%"),  # 0.0% at one decimal: not none
    (0.9996, "over 99.9%"),  # 100.0% at one decimal: not certain
    (1.0, "100.0%"),
])
def test_a_rate_prints_as_none_or_certain_only_when_it_is(rate, text):
    cfg = _cfg(_roof())
    cfg["rent"].update({"reset_hazard": rate, "reset_to_monthly_rent": 1100})
    cfg["house"]["price_shock"] = {"annual_hazard": rate}
    assert _best_guess(cfg) == [_reset_line(text), _crash_line("house", text)]


def _with_prior(tmp_path, tilt_by_horizon):
    """A house with a crash hazard of 3%, read against the golden prior with
    each band's drawdown_weight_tilt replaced."""
    import json
    from pathlib import Path
    golden = Path(__file__).parent / "fixtures" / "scenario_prior_golden.json"
    prior = json.loads(golden.read_text())
    for row in prior["scenario_priors"]:
        row["drawdown_weight_tilt"] = tilt_by_horizon[row["horizon_year"]]
    path = tmp_path / "prior.json"
    path.write_text(json.dumps(prior))
    cfg = _cfg(_roof(), years=25)
    cfg["house"]["price_shock"] = {"annual_hazard": 0.03}
    cfg["market_scenario"] = {"path": str(path), "geography": "MTL_RMR"}
    return cfg


TILTED = "house.price_shock.annual_hazard × the prior's drawdown_weight_tilt"


def test_the_crash_rate_is_the_one_the_model_applies_after_the_prior_s_tilt(tmp_path):
    uniform = _with_prior(tmp_path, {h: 2.0 for h in (2030, 2035, 2040, 2045, 2050)})
    assert _best_guess(uniform) == [_crash_line("house", "6.0%", TILTED)]


def test_the_read_back_reads_the_prior_only_for_a_crash_line(tmp_path):
    """Called without the prior, the read-back loads it only to compose a crash
    rate, and refuses rather than print a rate it cannot compose."""
    from hde.market_scenario import ScenarioPriorError
    spec = load_config_dict(_with_prior(tmp_path, {h: 2.0 for h in (2030, 2035, 2040, 2045,
                                                                     2050)}))
    spec.market_scenario.path = str(tmp_path / "missing.json")
    with pytest.raises(ScenarioPriorError):
        read_back_lines(spec)
    spec.house.price_shock.annual_hazard = 0.0
    assert [x for x in read_back_lines(spec) if x.startswith("best guess:")] == []


def test_a_crash_rate_that_varies_by_year_prints_as_its_range(tmp_path):
    """Year t of the run is calendar year 2026 + t, read in the first band at
    or after it: 25 years reach every band, the last holding past 2050."""
    tilts = {2030: 1.0, 2035: 2.0, 2040: 1.5, 2045: 1.0, 2050: 40.0}
    rates = [min(0.03 * tilts[next(h for h in (2030, 2035, 2040, 2045, 2050)
                                   if h >= min(2026 + t, 2050))], 1.0)
             for t in range(1, 26)]
    assert (min(rates), max(rates)) == (0.03, 1.0)
    cfg = _with_prior(tmp_path, tilts)
    assert _best_guess(cfg) == [_crash_line("house", "3.0% to 100.0%", TILTED)]


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
                     "expected_year outside [min_year, max_year], or for a hazard outside "
                     "the years it can fire",
                     "a negative timing_std_years or cost_vol",
                     "a hazard whose hazard_start_year is past years or max_year, or that is 0 "
                     "in every year it can fire"):
            assert fact in note, (option, fact)
    assert "a year outside [1, years] is REFUSED" in schema["income"]["pay_drop_events"]["note"]


@pytest.mark.parametrize("hazard, share", [
    (1.0, "100.0%"),       # certain in year 1: exactly all
    (0.4, "over 99.9%"),   # 1 - 0.6**20 = 0.99996: not all
    (0.9, "over 99.9%"),   # 1 - 0.1**20 is 1.0 in floating point: not all
    (1e-6, "under 0.1%"),  # 1 - (1 - 1e-6)**20 = 0.00002: not none
    (1e-17, "under 0.1%"),  # 1 - 1e-17 is 1.0 in floating point: not none
])
def test_a_share_never_prints_as_certain_or_as_none_when_it_is_not(hazard, share):
    (line,) = _best_guess(_cfg(_roof(expected_year=1, timing_model="hazard",
                                     hazard_base=hazard)))
    assert f"the chance it fires within the 20 years is {share}," in line


def test_a_share_of_exactly_none_prints_as_none():
    """Only a spec built in code reaches a hazard of 0: the loader refuses it."""
    spec = load_config_dict(_cfg(_roof(timing_model="hazard", hazard_base=0.1)))
    spec.house.events[0].hazard_base = 0.0
    (line,) = [x for x in read_back_lines(spec) if x.startswith("best guess:")]
    assert line == _event_line("roof", 8, "0.0%", None)


def test_the_contract_lists_the_best_guess_lines_after_decisiveness():
    from pathlib import Path
    contract = " ".join((Path(__file__).parent.parent / "docs/reference/API_CONTRACT.md")
                        .read_text().split())
    assert ("the `decisiveness:` line; the `best guess:` lines — for each hazard-timed event "
            "the year the best guess charges it and, on its hazard schedule, the chance it "
            "fires within the horizon and the year that chance reaches one half (or that it "
            "never does); when `rent.reset_hazard` or a `price_shock.annual_hazard` is above "
            "0, that the best guess prices a tenancy that never resets or no price crash, "
            "with the annual chance the model applies (after a prior's "
            "`drawdown_weight_tilt`, as a range when it varies); each "
            "`<option> financing:` line") in contract
