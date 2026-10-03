"""The crash stress panel (docs/specs/2026-10-03-crash-stress-panel.md; §10's
rows, each named where it is pinned).

Every refusal is pinned beside the legal grid one step away, so a refusal
deleted fails the first test of its pair and a refusal widened onto its
neighbour fails the second.
"""
from __future__ import annotations

import copy
import math
import re
import tokenize
from pathlib import Path

import numpy as np
import pytest
import yaml

from hde.break_even import solve_crossings
from hde.config import load_config_dict
from hde.crash_panel import (
    MAX_ROWS, PERMANENT, CrashPanelRefusal, Recovery, check_years, drop_path, parse_grid,
    underwater_years,
)
from hde.deterministic import _annual_costs_for_option, compute_deterministic
from hde.models import compute_verdict
from hde.monte_carlo import run_monte_carlo
from hde.pv import pv_single

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "hde"
FTB = ROOT / "examples" / "first_time_buyer_montreal.yaml"
HOUSE = ROOT / "examples" / "mortgage_house_vs_rent.yaml"


@pytest.fixture(autouse=True)
def _at_the_repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)


def _raw(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _ftb_laddered(years: int) -> dict:
    """FTB-10L / FTB-25L (spec, top): FTB with a 5-year renewal at the opening
    rate, both keys declared the assistant's."""
    raw = _raw(FTB)
    raw["years"] = years
    raw["condo"]["mortgage_renewal_years"] = 5
    raw["condo"]["mortgage_renewal_rates"] = 0.0455
    raw["sources"]["condo.mortgage_renewal_years"] = "assistant"
    raw["sources"]["condo.mortgage_renewal_rates"] = "assistant"
    return raw


def _spec(raw: dict):
    return load_config_dict(copy.deepcopy(raw))


FULL_5 = Recovery("full", 1.0, 5)
FULL_7 = Recovery("full", 1.0, 7)


def _refused(arg: str, horizon: int = 10) -> CrashPanelRefusal:
    with pytest.raises(CrashPanelRefusal) as caught:
        check_years(parse_grid(arg), horizon)
    return caught.value


def _loads(arg: str, horizon: int = 10):
    grid = parse_grid(arg)
    check_years(grid, horizon)
    return grid


# --- row 2: one home for m(t) ---------------------------------------------------

# A log drop and its inverse, in code (comments and strings removed; the
# tokens are rejoined with spaces, so the pattern allows them).
_LOG_DROP = re.compile(r"\blog1p\s*\(\s*-|\blog\s*\(\s*1(\.0)?\s*-|\bexp\s*\(\s*-")


def _code_only(path: Path) -> str:
    kept = []
    with path.open("rb") as handle:
        for tok in tokenize.tokenize(handle.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.ENCODING):
                continue
            kept.append(tok.string)
    return " ".join(kept)


def test_drop_path_is_the_only_code_computing_a_log_drop():
    """Row 2. The pattern must match in crash_panel.py, so the pin cannot pass
    on a pattern that matches nothing, and nowhere else in the engine."""
    hits = sorted(p.name for p in SRC.glob("*.py") if _LOG_DROP.search(_code_only(p)))
    assert hits == ["crash_panel.py"]


# --- drop_path: the multiplier ------------------------------------------------------

def test_a_permanent_drop_holds_from_its_year_to_the_sale():
    m = drop_path(10, 0.20, 4, PERMANENT)
    assert m[:3] == (1.0, 1.0, 1.0)
    assert all(v == pytest.approx(0.8, rel=1e-15) for v in m[3:])


def test_a_full_recovery_returns_exactly_to_the_path():
    m = drop_path(10, 0.40, 1, Recovery("full", 1.0, 7))
    assert m[0] == pytest.approx(0.6, rel=1e-15)
    assert m[7:] == (1.0, 1.0, 1.0)  # years 8..10: c + K = 8
    assert m[6] < 1.0                # year 7 is still one step short


def test_a_partial_recovery_steps_in_logs():
    """Row 5's multiple: share:0.5:5 from year 1 at 10% leaves m(10) = 0.9^0.5,
    not the level step's 0.95."""
    m = drop_path(10, 0.10, 1, Recovery("share", 0.5, 5))
    assert m[9] == pytest.approx(math.sqrt(0.9), rel=1e-14)
    assert round(m[9], 4) == 0.9487
    assert m[2] == pytest.approx(0.9 ** (1 - 0.5 * 2 / 5), rel=1e-14)


def test_a_drop_of_zero_is_a_path_of_ones():
    """The break-even solver prices the bracket's low end, which X1 refuses on
    the grid."""
    assert drop_path(10, 0.0, 1, PERMANENT) == (1.0,) * 10


def test_a_drop_in_the_sale_year_reaches_only_the_sale():
    m = drop_path(10, 0.30, 10, Recovery("full", 1.0, 5))
    assert m[:9] == (1.0,) * 9
    assert m[9] == pytest.approx(0.7, rel=1e-15)


# --- the grid parser ----------------------------------------------------------------

def test_the_grid_parses_sorted_and_deduplicated():
    grid = _loads("drop=0.30,0.10,0.20,0.10;year=9,1;recovery=permanent,full:5,share:1:5,full:15;"
                  "jump=0.0237")
    assert grid.drops == (0.10, 0.20, 0.30)
    assert grid.years == (1, 9)
    assert grid.recoveries == (PERMANENT, Recovery("full", 1.0, 5), Recovery("full", 1.0, 15))
    assert grid.jump == 0.0237
    assert grid.row_count == 3 * 2 * 3


def test_full_k_and_share_1_k_are_one_recovery_and_other_shares_are_not():
    grid = _loads("drop=0.1;year=1;recovery=share:1:7,full:7,share:0.5:7,full:5")
    assert grid.recoveries == (Recovery("share", 1.0, 7), Recovery("share", 0.5, 7),
                               Recovery("full", 1.0, 5))


def test_jump_is_optional():
    assert _loads("drop=0.1;year=1;recovery=permanent").jump is None


@pytest.mark.parametrize("arg", [
    "drop=0.1;year=1",                                  # recovery missing: nothing defaults
    "drop=0.1;year=1;recovery=permanent;sale=3",        # no such field
    "drop=0.1;drop=0.2;year=1;recovery=permanent",      # a field twice
    "drop=ten;year=1;recovery=permanent",               # not a number
    "drop=0.1;year=1.5;recovery=permanent",             # not a whole year
])
def test_a_flag_without_the_grid_shape_is_a_usage_error_not_a_refusal(arg):
    with pytest.raises(ValueError) as caught:
        parse_grid(arg)
    assert not isinstance(caught.value, CrashPanelRefusal)


# --- row 9 (in part): X1, X2, X3 and X9 each beside the neighbour that loads -----------

def test_x1_refuses_a_drop_past_the_ceiling():
    refusal = _refused("drop=1.0;year=1;recovery=permanent")
    assert (refusal.code, refusal.fact) == ("drop_out_of_range", "drop 1.0 is outside (0, 0.99]")


def test_x1_refuses_no_drop():
    refusal = _refused("drop=0;year=1;recovery=permanent")
    assert (refusal.code, refusal.fact) == ("drop_out_of_range", "drop 0.0 is outside (0, 0.99]")


def test_x1_neighbour_loads():
    assert _loads("drop=0.99;year=1;recovery=permanent").drops == (0.99,)


def test_x2_refuses_a_year_past_the_horizon():
    refusal = _refused("drop=0.1;year=11;recovery=permanent", horizon=10)
    assert (refusal.code, refusal.fact) == ("year_out_of_range",
                                            "year 11 is past the 10-year horizon")


def test_x2_refuses_a_year_before_the_first():
    refusal = _refused("drop=0.1;year=0;recovery=permanent", horizon=10)
    assert (refusal.code, refusal.fact) == ("year_out_of_range", "year 0 is before year 1")


def test_x2_neighbour_loads():
    """`years` itself is the sale year, and loads."""
    assert _loads("drop=0.1;year=1,10;recovery=permanent", horizon=10).years == (1, 10)


def test_x3_refuses_a_share_above_one():
    refusal = _refused("drop=0.1;year=1;recovery=share:1.2:7")
    assert (refusal.code, refusal.fact) == ("recovery_malformed", "share 1.2 is outside (0, 1]")


@pytest.mark.parametrize("token, fact", [
    ("share:0:5", "share 0.0 is outside (0, 1]"),
    ("full:0", "years 0 is below 1"),
    ("full:2.5", "years 2.5 is not a whole number"),
    ("linear:5", "recovery 'linear:5' is not permanent, full:K or share:R:K"),
    ("full", "recovery 'full' is not permanent, full:K or share:R:K"),
    ("share:a:5", "recovery 'share:a:5' is not permanent, full:K or share:R:K"),
])
def test_x3_refuses_every_malformed_recovery(token, fact):
    refusal = _refused(f"drop=0.1;year=1;recovery={token}")
    assert (refusal.code, refusal.fact) == ("recovery_malformed", fact)


def test_x3_neighbour_loads():
    grid = _loads("drop=0.1;year=1;recovery=share:1:7,full:1,share:0.5:1")
    assert grid.recoveries == (Recovery("share", 1.0, 7), Recovery("full", 1.0, 1),
                               Recovery("share", 0.5, 1))


def test_x9_refuses_more_than_48_rows():
    drops = ",".join(f"0.{k}" for k in range(1, 10))  # 9 drops x 3 years x 2 recoveries
    refusal = _refused(f"drop={drops};year=1,2,3;recovery=permanent,full:5")
    assert (refusal.code, refusal.fact) == ("too_many_rows", "the grid has 54 rows")


def test_x9_neighbour_loads():
    drops = ",".join(f"0.{k}" for k in range(1, 9))  # 8 x 3 x 2 = 48
    grid = _loads(f"drop={drops};year=1,2,3;recovery=permanent,full:5")
    assert grid.row_count == MAX_ROWS == 48
    assert len(grid.rows()) == 48


# --- the central line (§4; rows 3 to 6 and row 11's first pin) ------------------------

def _central(spec, d, c, recovery):
    return compute_deterministic(spec, drop_path=drop_path(spec.simulation.years, d, c, recovery))


def test_row3_the_permanent_break_even_is_the_selling_cost_oracle():
    """Row 3. A permanent drop raises the condo's total by d × value_N × (1 − s)
    discounted, so the crossing is gap / pv_single(value_N × (1 − s), r, years).
    Solved to adjacent floats: the default bisection stops at a width of 1e-9,
    which is 5.9e-9 relative at this crossing."""
    spec = _spec(_raw(FTB))
    base = compute_deterministic(spec)
    gap = base.rent.total_pv - base.condo.total_pv
    growth = (1 + spec.condo.value_growth_rate) * (1 + spec.economic.inflation_rate) - 1
    value_n = spec.condo.initial_value * (1 + growth) ** spec.simulation.years
    unit = pv_single(value_n * (1 - spec.condo.selling_cost_rate),
                     spec.simulation.discount_rate, spec.simulation.years)
    assert (round(gap, 2), round(unit, 2)) == (6525.78, 318100.15)

    def totals_at(d):
        det = _central(spec, d, 1, PERMANENT)
        return det.condo.total_pv, det.rent.total_pv

    out = solve_crossings("crash.drawdown", ("condo", "rent"), 0.0, 0.99, totals_at,
                          to_adjacent_floats=True)
    (crossing,) = out["break_evens"]
    assert crossing["value"] == pytest.approx(gap / unit, rel=1e-9)
    assert round(crossing["value"], 6) == 0.020515
    assert (crossing["cheaper_below"], crossing["cheaper_above"]) == ("condo", "rent")
    assert crossing["tie_band"][0] is None
    assert round(crossing["tie_band"][1], 4) == 0.0531


def test_row4_a_condo_permanent_row_is_the_same_in_every_drop_year():
    """Row 4. Only m(years) reaches a condo's total, and a permanent drop
    carries it to the sale from any year."""
    spec = _spec(_raw(FTB))
    base = compute_deterministic(spec).condo.total_pv
    totals = {c: _central(spec, 0.20, c, PERMANENT).condo.total_pv for c in (1, 9, 10)}
    assert totals[1] == totals[9] == totals[10]
    assert round(totals[1]) == 264122
    assert totals[1] != base


def test_row5_a_completed_recovery_leaves_the_condo_total_bit_for_bit():
    """Row 5. full:7 from year 1 on FTB-25L brings m(25) back to exactly 1."""
    spec = _spec(_ftb_laddered(25))
    base = compute_deterministic(spec).condo.total_pv
    assert round(base, 2) == 377856.33
    for d in (0.10, 0.20, 0.40):
        assert _central(spec, d, 1, FULL_7).condo.total_pv == base


def test_row5_a_half_recovery_steps_in_logs_on_the_central_line():
    """Row 5. share:0.5:5 from year 1 at 10%: m(10) = 0.9487 and FTB's condo
    $216,825 (the level step's m = 0.95 gives another total)."""
    spec = _spec(_raw(FTB))
    assert round(_central(spec, 0.10, 1, Recovery("share", 0.5, 5)).condo.total_pv) == 216825


def test_row5_a_recovery_still_under_way_at_the_sale_is_priced_in_part():
    """FTB-25L, 20% from year 24, full:5: condo cheaper by $32,272 (spec §1.2)."""
    det = _central(_spec(_ftb_laddered(25)), 0.20, 24, FULL_5)
    assert round(det.rent.total_pv - det.condo.total_pv) == 32272


def test_row6_a_drop_moves_the_house_maintenance():
    """Row 6 (R3). House example, year 1, full:7, 40%: $341,252, below the
    no-drop $349,866, because maintenance is priced on the lower value."""
    spec = _spec(_raw(HOUSE))
    assert round(compute_deterministic(spec).house.total_pv) == 349866
    assert round(_central(spec, 0.40, 1, FULL_7).house.total_pv) == 341252


def test_row6_a_permanent_drop_on_the_house_reaches_its_sale_and_its_maintenance():
    spec = _spec(_raw(HOUSE))
    rows = {(c, d): _central(spec, d, c, PERMANENT) for c, d in
            ((1, 0.30), (1, 0.40), (19, 0.30), (19, 0.40))}
    gaps = {k: round(v.rent.total_pv - v.house.total_pv) for k, v in rows.items()}
    assert gaps == {(1, 0.30): 23400, (1, 0.40): -3034, (19, 0.30): -591, (19, 0.40): -35022}


def test_a_drop_reaches_the_house_affordability_cost_and_no_other():
    spec = _spec(_raw(HOUSE))
    path = drop_path(20, 0.40, 1, FULL_7)
    plain = _annual_costs_for_option("house", spec.house, spec.simulation, spec.economic)
    dropped = _annual_costs_for_option("house", spec.house, spec.simulation, spec.economic,
                                       drop_path=path)
    maintenance = spec.house.initial_value * spec.house.annual_maintenance_rate
    assert plain[0] - dropped[0] == pytest.approx(maintenance * 0.40, rel=1e-12)
    assert dropped[7:] == plain[7:]
    ftb = _spec(_raw(FTB))
    with_drop = compute_deterministic(ftb, drop_path=drop_path(10, 0.40, 1, PERMANENT))
    assert with_drop.income_report.condo_ratios == compute_deterministic(ftb).income_report.condo_ratios


def test_row11_the_first_underwater_year_turns_on_between_12_and_13_percent():
    """Row 11, first pin. FTB year 1: $459,450 × 0.95 = $436,477 against a
    $381,862 balance, so the boundary is 12.51%."""
    spec = _spec(_raw(FTB))

    def under(d, c=1, recovery=PERMANENT):
        return underwater_years(spec.condo, spec.economic, 10, drop_path(10, d, c, recovery))

    assert under(0.12) == []
    assert under(0.13) == [1]
    assert under(0.20) == [1, 2]
    assert under(0.30) == [1, 2, 3, 4, 5]
    assert under(0.40) == list(range(1, 9))
    assert under(0.40, recovery=FULL_7) == [1, 2, 3, 4]
    assert under(0.40, c=9) == []
    assert underwater_years(spec.condo, spec.economic, 10) == []


def test_a_drop_path_of_the_wrong_length_is_refused():
    spec = _spec(_raw(FTB))
    with pytest.raises(ValueError, match="drop_path has 9 entries for a 10-year run"):
        compute_deterministic(spec, drop_path=(1.0,) * 9)


# --- the Monte Carlo (§4; rows 7 and 8) -------------------------------------------

def _household(base_years: int, value_vol: float, rent_vol: float, seed: int = 42):
    """The worked households (spec, top): P1 is FTB-10L at 0.04 / 0.23, P2b
    FTB-25L at 0.068 / 0.23, 5,000 paths."""
    raw = _ftb_laddered(base_years)
    raw["economic"]["inflation_vol"] = 0.01
    raw["simulation"].update(investment_return_vol=0.10, other_cost_vol=0.01,
                             value_growth_vol=value_vol, rent_escalation_vol=rent_vol,
                             random_seed=seed)
    for key in ("economic.inflation_vol", "simulation.investment_return_vol",
                "simulation.other_cost_vol", "simulation.value_growth_vol",
                "simulation.rent_escalation_vol"):
        raw["sources"][key] = "assistant"
    return _spec(raw)


def _verdict(spec, path):
    det = compute_deterministic(spec, drop_path=path)
    mc = run_monte_carlo(spec, drop_path=path)
    return mc, compute_verdict(det, mc, years=spec.simulation.years,
                               discount_rate=spec.simulation.discount_rate)


def _one_stream(seed: int):
    gen = np.random.default_rng(seed)
    return gen, {channel: gen for channel in range(9)}


def test_row7_a_stated_drop_takes_no_draw():
    """Row 7. Every row and the plain run read the same random numbers: the
    renter's PVs are byte-identical and the generator ends in the same state,
    while the condo's PVs do move."""
    spec = _household(10, 0.04, 0.23)
    gen, streams = _one_stream(42)
    plain = run_monte_carlo(spec, streams)
    end_state = gen.bit_generator.state
    for path in (drop_path(10, 0.20, 1, PERMANENT), drop_path(10, 0.40, 9, FULL_7),
                 drop_path(10, 0.10, 3, Recovery("share", 0.5, 4))):
        gen, streams = _one_stream(42)
        row = run_monte_carlo(spec, streams, drop_path=path)
        assert gen.bit_generator.state == end_state
        assert row.rent.pvs.tobytes() == plain.rent.pvs.tobytes()
        assert not np.array_equal(row.condo.pvs, plain.condo.pvs)


def test_row7_the_house_takes_no_draw_either():
    spec = _spec(_raw(HOUSE))
    gen, streams = _one_stream(42)
    plain = run_monte_carlo(spec, streams)
    end_state = gen.bit_generator.state
    gen, streams = _one_stream(42)
    row = run_monte_carlo(spec, streams, drop_path=drop_path(20, 0.30, 2, FULL_7))
    assert gen.bit_generator.state == end_state
    assert row.rent.pvs.tobytes() == plain.rent.pvs.tobytes()
    assert np.all(row.house.pvs < plain.house.pvs)  # R3: a recovered drop lowers maintenance


def test_row8_a_path_of_ones_is_the_plain_run():
    """Row 8. Built directly, since X1 refuses a 0 drop on the grid: the
    conditional run on a path of ones is the plain run bit for bit, P1 0.5450."""
    spec = _household(10, 0.04, 0.23)
    plain_mc, plain = _verdict(spec, None)
    ones_mc, ones = _verdict(spec, (1.0,) * 10)
    assert ones_mc.condo.pvs.tobytes() == plain_mc.condo.pvs.tobytes()
    assert ones.prob_best == plain.prob_best
    assert (ones.best, ones.state, round(ones.prob_best, 4)) == ("condo", "tie", 0.5450)


def test_a_conditional_run_moves_the_verdict_by_the_stated_drop():
    """P1, 10% permanent from year 1, seed 42: rent option at 0.7192 (§1.4)."""
    _, verdict = _verdict(_household(10, 0.04, 0.23), drop_path(10, 0.10, 1, PERMANENT))
    assert (verdict.best, verdict.state, round(verdict.prob_best, 4)) == ("rent", "option", 0.7192)


def test_a_run_with_no_value_dispersion_takes_the_drop_too():
    """FTB draws nothing, so every path is its central line: with a stated drop
    the paths price the dropped central total, condo and house alike."""
    for raw, option, years, c in ((_raw(FTB), "condo", 10, 4), (_raw(HOUSE), "house", 20, 3)):
        raw["simulation"]["num_sims"] = 3
        if option == "house":
            raw["simulation"]["house_maintenance_vol"] = 0.0
            raw["simulation"]["rent_escalation_vol"] = 0.0
        spec = _spec(raw)
        path = drop_path(years, 0.30, c, Recovery("share", 0.6, 5))
        central = getattr(compute_deterministic(spec, drop_path=path), option).total_pv
        plain = getattr(compute_deterministic(spec), option).total_pv
        pvs = getattr(run_monte_carlo(spec, drop_path=path), option).pvs
        assert central != pytest.approx(plain, rel=1e-6)
        assert pvs == pytest.approx([central] * 3, rel=1e-12)


def test_a_monte_carlo_drop_path_of_the_wrong_length_is_refused():
    with pytest.raises(ValueError, match="drop_path has 9 entries for a 10-year run"):
        run_monte_carlo(_spec(_raw(FTB)), drop_path=(1.0,) * 9)
