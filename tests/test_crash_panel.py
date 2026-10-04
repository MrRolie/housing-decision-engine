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

    out = solve_crossings("crash.drop", ("condo", "rent"), 0.0, 0.99, totals_at,
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


# --- the runner (§3.3; rows 11 second pin, 12, 14 and 15; X4 to X8) -------------------

from hde.crash_panel import apply_jump, run_crash_panel  # noqa: E402

THREE = ROOT / "examples" / "rent_vs_condo_vs_house.yaml"
SURFACE = ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"
PATH_FILE = ROOT / "tests" / "fixtures" / "renewal_paths" / "hvr_example.yaml"


def _panel(spec, arg: str, **kw):
    return run_crash_panel(spec, parse_grid(arg), **kw)


def _ftb_jumped(years: int, jump: float = 0.0237):
    spec, reached = apply_jump(_spec(_ftb_laddered(years)), jump)
    return spec, reached


def test_row11_the_underwater_balance_reads_the_jumped_ladder():
    """Row 11, second pin. FTB-10L with jump=0.0237, 45% permanent from year 1:
    underwater years 1–10, through the panel row. The unladdered balance
    (`outstanding_balance`) under the jump gives 1–9."""
    panel = _panel(_spec(_ftb_laddered(10)),
                   "drop=0.45;year=1;recovery=permanent;jump=0.0237", monte_carlo=False)
    (row,) = panel["rows"]
    assert row["underwater_years"] == {"condo": list(range(1, 11))}
    assert panel["grid"]["jump"] == {"value": 0.0237, "options": ["condo"]}


def test_row12_the_jump_lands_on_the_first_renewal_only():
    """Row 12. FTB-25L (four priced renewals), jump=0.0237: condo $403,362.00
    and years above 32% 1–10 at no drop; with a 20% permanent drop, rent by a
    `margin_pv` of $689 (the printed `rent − condo` gap reads −688), `tie`.
    The jump on every renewal gives $432,244.22, years 1–11, and rent by a
    `margin_pv` of $29,571, `option`."""
    panel = _panel(_spec(_ftb_laddered(25)),
                   "drop=0.20;year=1;recovery=permanent;jump=0.0237", monte_carlo=False)
    none, (row,) = panel["no_drop"], panel["rows"]
    assert round(none["central"]["totals"]["condo"], 2) == 403362.00
    assert none["affordability"]["condo"]["years_exceeding"] == list(range(1, 11))
    central = row["central"]
    assert (central["best"], round(central["margin_pv"]), central["state"]) == ("rent", 689, "tie")


def test_a_jump_of_zero_leaves_the_ladder_as_loaded():
    """§6's write-out and conversion reproduce the loader's ladder exactly."""
    base = _spec(_ftb_laddered(25))
    jumped, reached = apply_jump(base, 0.0)
    assert reached == ["condo"]
    assert compute_deterministic(jumped).condo.total_pv == compute_deterministic(base).condo.total_pv
    assert jumped.condo.mortgage_renewal_rates_quoted == [0.0455] * 4


def _p2b():
    return _household(25, 0.068, 0.23)


def test_row14_level_is_the_central_move_and_sd_the_row_own_spread():
    """Row 14. P2b at seed 42, 20% permanent from year 1: `level_pv` −40,835
    (the printed `level` column, the difference of printed gaps, reads
    −40,836), `sd` 77,718 (the plain run's is 88,671), futures `condo` 0.6080
    `tie`, central `condo` `option`."""
    panel = _panel(_p2b(), "drop=0.20;year=1;recovery=permanent")
    (row,) = panel["rows"]
    assert round(row["level_pv"]) == -40835
    assert round(row["futures"]["gap_sd"]) == 77718
    assert round(panel["no_drop"]["futures"]["gap_sd"]) == 88671
    futures = row["futures"]
    assert (futures["best"], round(futures["prob_best"], 4), futures["state"]) == ("condo", 0.6080, "tie")
    assert (row["central"]["best"], row["central"]["state"]) == ("condo", "option")


def _p2():
    return _household(25, 0.04, 0.23)


def test_row15_a_disagreement_row_carries_both_options():
    """Row 15. P2 at seed 42, 32% permanent from year 1: the verdict is
    `condo` `disagreement` at 0.4968 and the majority is rent at 0.5032."""
    (row,) = _panel(_p2(), "drop=0.32;year=1;recovery=permanent")["rows"]
    futures = row["futures"]
    assert (futures["best"], round(futures["prob_best"], 4), futures["state"]) == (
        "condo", 0.4968, "disagreement")
    assert (futures["mc_best"], round(futures["mc_prob_best"], 4)) == ("rent", 0.5032)


def test_the_no_drop_row_is_the_plain_run():
    """Row 8 through the runner: the `none` row is the run's own verdict."""
    spec = _household(10, 0.04, 0.23)
    panel = _panel(spec, "drop=0.10;year=1;recovery=permanent")
    _, plain = _verdict(spec, None)
    none = panel["no_drop"]
    assert none["futures"]["prob_best"] == plain.prob_best
    assert (none["drop"], none["sale_multiple"], none["level_pv"]) == (None, 1.0, 0.0)
    (row,) = panel["rows"]
    assert (row["futures"]["best"], round(row["futures"]["prob_best"], 4)) == ("rent", 0.7192)


def test_futures_are_absent_without_a_monte_carlo_and_on_a_single_path_run():
    spec = _household(10, 0.04, 0.23)
    assert _panel(spec, "drop=0.1;year=1;recovery=permanent",
                  monte_carlo=False)["rows"][0]["futures"] is None
    assert _panel(_spec(_raw(FTB)), "drop=0.1;year=1;recovery=permanent")["rows"][0]["futures"] is None


def test_the_rows_group_by_year_then_recovery_with_one_break_even_each():
    panel = _panel(_spec(_raw(FTB)), "drop=0.2,0.1;year=9,1;recovery=permanent,full:7",
                   monte_carlo=False)
    keys = [(r["year"], r["recovery"]["years"], r["drop"]) for r in panel["rows"]]
    assert keys == [(1, None, 0.1), (1, None, 0.2), (1, 7, 0.1), (1, 7, 0.2),
                    (9, None, 0.1), (9, None, 0.2), (9, 7, 0.1), (9, 7, 0.2)]
    assert [(b["year"], b["recovery"]["years"]) for b in panel["break_evens"]] == [
        (1, None), (1, 7), (9, None), (9, 7)]
    first = panel["break_evens"][0]
    assert set(first["break_evens"][0]) == {"value", "cheaper_below", "cheaper_above", "tie_band"}
    assert round(first["break_evens"][0]["value"], 6) == 0.020515


def test_row3_the_runner_solves_the_break_even_to_adjacent_floats():
    """Row 3 through the runner: the JSON crossing is the adjacent-floats
    solve exactly. The default bisection stops at a width of 1e-9 and lands on
    another float."""
    spec = _spec(_raw(FTB))
    panel = _panel(spec, "drop=0.1;year=1;recovery=permanent", monte_carlo=False)
    (crossing,) = panel["break_evens"][0]["break_evens"]

    def totals_at(d):
        det = _central(spec, d, 1, PERMANENT)
        return det.condo.total_pv, det.rent.total_pv

    exact = solve_crossings("crash.drop", ("condo", "rent"), 0.0, 0.99, totals_at,
                            to_adjacent_floats=True)["break_evens"][0]["value"]
    assert crossing["value"] == exact


def test_level_is_the_gap_move_when_the_best_option_changes():
    """FTB, 10% permanent from year 1: condo is cheapest with no drop and rent
    with the drop, so `level_pv` is the signed move of `rent − condo`,
    −31,810.01; the difference of the two margins would read +18,758."""
    panel = _panel(_spec(_raw(FTB)), "drop=0.1;year=1;recovery=permanent", monte_carlo=False)
    (row,) = panel["rows"]
    assert (panel["no_drop"]["central"]["best"], row["central"]["best"]) == ("condo", "rent")
    assert round(row["level_pv"], 2) == -31810.01


# --- row 9: X4 to X8, each beside the neighbour that loads -----------------------------

def _surface(hazard: float):
    raw = _raw(SURFACE)
    for name in ("condo", "house"):
        raw[name]["price_shock"]["annual_hazard"] = hazard
    raw["simulation"]["num_sims"] = 50
    return _spec(raw)


def test_x4_refuses_a_wired_hazard():
    panel = _panel(_surface(0.03), "drop=0.1;year=1;recovery=permanent", monte_carlo=False)
    assert panel["refused"] == {"code": "hazard_wired",
                                "fact": "condo.price_shock.annual_hazard is 0.03"}
    assert panel["rows"] == [] and panel["no_drop"] is None


def test_x4_neighbour_a_hazard_of_zero_loads():
    panel = _panel(_surface(0.0), "drop=0.1;year=1;recovery=permanent", monte_carlo=False)
    assert panel["refused"] is None
    assert len(panel["rows"]) == 1


def test_x4_refuses_a_hazard_wired_on_the_house_alone():
    """X4 reads every owned option: the condo at hazard 0 and the house at
    0.03 refuse on the house."""
    raw = _raw(SURFACE)
    raw["condo"]["price_shock"]["annual_hazard"] = 0.0
    raw["house"]["price_shock"]["annual_hazard"] = 0.03
    raw["simulation"]["num_sims"] = 50
    panel = _panel(_spec(raw), "drop=0.1;year=1;recovery=permanent", monte_carlo=False)
    assert panel["refused"] == {"code": "hazard_wired",
                                "fact": "house.price_shock.annual_hazard is 0.03"}


def _without(path: Path, option: str) -> dict:
    raw = _raw(path)
    del raw[option]
    raw["sources"] = {k: v for k, v in (raw.get("sources") or {}).items()
                      if not k.startswith(f"{option}.")}
    return raw


def test_x5_refuses_a_config_with_no_owned_option():
    raw = _without(HOUSE, "house")
    panel = _panel(_spec(raw), "drop=0.1;year=1;recovery=permanent", monte_carlo=False)
    assert panel["refused"] == {"code": "no_owned_option", "fact": "no owned option is priced"}


def test_x5_neighbour_one_owned_option_loads():
    raw = _without(HOUSE, "rent")
    panel = _panel(_spec(raw), "drop=0.1;year=1;recovery=permanent", monte_carlo=False)
    assert panel["refused"] is None
    assert panel["rows"][0]["central"]["totals"].keys() == {"house"}
    assert panel["break_evens"][0]["refused"] == {"code": "not_two_options",
                                                  "fact": "1 option is priced"}


def _ftb_laddered_at(years: int):
    return _spec(_ftb_laddered(years))


def test_x6_refuses_a_jump_no_renewal_reaches():
    """FTB-10L at 4 years: the first renewal is year 6."""
    panel = _panel(_ftb_laddered_at(4), "drop=0.1;year=1;recovery=permanent;jump=0.0237",
                   monte_carlo=False)
    assert panel["refused"] == {"code": "jump_without_ladder",
                                "fact": "no financed option prices a renewal inside 4 years"}


def test_x6_refuses_a_jump_on_a_config_with_no_ladder():
    panel = _panel(_spec(_raw(FTB)), "drop=0.1;year=1;recovery=permanent;jump=0.0237",
                   monte_carlo=False)
    assert panel["refused"]["code"] == "jump_without_ladder"


def test_x6_neighbour_a_renewal_inside_the_horizon_loads():
    """FTB-10L at 6 years prices its one renewal, in year 6."""
    panel = _panel(_ftb_laddered_at(6), "drop=0.1;year=1;recovery=permanent;jump=0.0237",
                   monte_carlo=False)
    assert panel["refused"] is None
    assert panel["grid"]["jump"]["options"] == ["condo"]


def test_x7_refuses_a_jump_beside_a_path_file():
    panel = _panel(_spec(_raw(PATH_FILE)), "drop=0.1;year=1;recovery=permanent;jump=0.01",
                   monte_carlo=False)
    assert panel["refused"] == {"code": "jump_beside_path_file", "fact": "renewal_rates.path is set"}


def test_x7_neighbour_the_flag_without_jump_loads():
    panel = _panel(_spec(_raw(PATH_FILE)), "drop=0.1;year=1;recovery=permanent",
                   monte_carlo=False)
    assert panel["refused"] is None


def test_x10_refuses_a_jump_that_takes_the_first_renewal_below_zero():
    """X10. FTB-10L's first renewal is quoted at 4.55%: a jump of −0.06 takes
    it to −1.45%, which the loader's floor refuses, so the panel refuses
    before any ladder is built; −0.0456 is one step past the floor."""
    for jump, fact in (("-0.06", "jump −0.06 takes the first renewal to −1.45%, below 0"),
                       ("-0.0456", "jump −0.0456 takes the first renewal to −0.01%, below 0")):
        panel = _panel(_ftb_laddered_at(10), f"drop=0.2;year=1;recovery=permanent;jump={jump}",
                       monte_carlo=False)
        assert panel["refused"] == {"code": "jump_floor", "fact": fact}
        assert panel["rows"] == [] and panel["no_drop"] is None


def test_x10_neighbour_a_jump_to_a_zero_renewal_loads():
    """A jump of −0.0455 takes the first renewal to exactly 0, which the
    loader's floor admits: the panel prices it."""
    panel = _panel(_ftb_laddered_at(10), "drop=0.2;year=1;recovery=permanent;jump=-0.0455",
                   monte_carlo=False)
    assert panel["refused"] is None
    assert panel["grid"]["jump"] == {"value": -0.0455, "options": ["condo"]}
    assert len(panel["rows"]) == 1


def test_x8_three_options_refuse_the_break_even_level_and_sd_and_keep_the_rows():
    raw = _raw(THREE)
    raw["simulation"]["num_sims"] = 200
    panel = _panel(_spec(raw), "drop=0.1;year=1;recovery=permanent")
    assert panel["refused"] is None
    (row,) = panel["rows"]
    assert row["central"]["totals"].keys() == {"condo", "house", "rent"}
    assert row["level_pv"] is None and row["futures"]["gap_sd"] is None
    assert panel["no_drop"]["level_pv"] is None
    assert panel["break_evens"] == [{"year": 1, "recovery": {"form": "permanent", "share": 0.0,
                                                             "years": None},
                                     "refused": {"code": "not_two_options",
                                                 "fact": "3 options are priced"}}]


def test_x8_neighbour_two_options_solve():
    panel = _panel(_spec(_raw(HOUSE)), "drop=0.3;year=1;recovery=permanent", monte_carlo=False)
    (be,) = panel["break_evens"]
    assert "refused" not in be
    assert round(be["break_evens"][0]["value"], 4) == 0.3885
    assert panel["rows"][0]["level_pv"] is not None


# --- the surface: the text block, --json and the read-back (rows 10 and 13) -------------

import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402

import hde.cli as cli_mod  # noqa: E402
from hde.crash_panel import HEADER, format_crash_panel  # noqa: E402

_NUM = r"−?[\d,]+"
_SIGNED = r"(?:0|[+−][\d,]+)"
_PCT = r"\d+\.\d\d%"
_EDGE = rf"(?:{_PCT}|the next crossing)"
_O = r"(?:condo|house|rent)"
_TAG = r" \[solved, central case\]"
# §3.2's break-even templates, and no others.
_BREAK_EVEN = [
    rf"break-even: {_O} is cheaper below {_EDGE}; too close to call from {_EDGE} to {_EDGE}; "
    rf"{_O} is cheaper above {_EDGE} \(crossing {_PCT}\){_TAG}",
    rf"break-even: too close to call from no drop to {_EDGE}; {_O} is cheaper above {_EDGE} "
    rf"\(crossing {_PCT}\){_TAG}",
    rf"break-even: {_O} is cheaper below {_EDGE}; too close to call from {_EDGE} to a 99% drop "
    rf"\(crossing {_PCT}\){_TAG}",
    rf"break-even: too close to call from no drop to a 99% drop \(crossing {_PCT}\){_TAG}",
    rf"break-even: no crossing from no drop to a 99% drop: {_O} is cheaper throughout{_TAG}",
    rf"break-even: no crossing from no drop to a 99% drop: too close to call throughout{_TAG}",
    rf"break-even: no crossing from no drop to a 99% drop: too close to call from no drop to "
    rf"{_PCT}; {_O} is cheaper above {_PCT}{_TAG}",
    rf"break-even: no crossing from no drop to a 99% drop: {_O} is cheaper below {_PCT}; "
    rf"too close to call from {_PCT} to a 99% drop{_TAG}",
    r"break-even: refused \(not_two_options\): \d+ options? (is|are) priced",
]
_LINE = [
    re.escape(HEADER),
    r"jump [+−][\d.]+ pp at the first renewal: [a-z, ]+",
    r"  central line( +futures \([\d,]+\))?",
    r"  drop  sale value  .*",
    r"year \d+ · (permanent|full over \d+ years?|share [\d.]+ over \d+ years?)",
    rf"  (none|\d+(\.\d+)?%) +×(1|\d\.\d\d\d) +{_NUM}( +{_NUM})+ .*",
    *(rf"  {t}" for t in _BREAK_EVEN),
]


def _parse_block(text: str):
    """Every line against the fixed shapes; the rows' printed columns."""
    lines = text.split("\n")
    for line in lines:
        assert any(re.fullmatch(p, line) for p in _LINE), f"untemplated line: {line!r}"
    assert not any("widen" in line for line in lines)
    header = next(l for l in lines if l.startswith("  drop  sale value"))
    cols = re.split(r"  +", header.strip())
    rows = [dict(zip(cols, re.split(r"  +", l.strip()))) for l in lines
            if re.fullmatch(rf"  (none|\d+(\.\d+)?%) +×.*", l)]
    return lines, cols, rows


def _int(text: str) -> int:
    return int(text.replace(",", "").replace("−", "-").replace("+", ""))


def _check_arithmetic(cols, rows):
    """Row 10: each gap is the difference of its row's printed totals, and
    each level the difference of two printed gaps."""
    gap_col = next(c for c in cols if " − " in c)
    b, a = gap_col.split(" − ")
    none_gap = None
    for row in rows:
        gap = _int(row[gap_col])
        assert gap == _int(row[b]) - _int(row[a])
        if row["drop"] == "none":
            none_gap = gap
            assert row["level"] == "0"
        assert _int(row["level"]) == gap - none_gap


def test_row10_every_line_of_the_block_is_a_fixed_template():
    """Row 10 on P1 at seed 42 (FTB's central line): the band-from-no-drop
    template for a permanent drop, the no-crossing one for full:7 from year 1,
    and every gap and level recomputed from the printed figures."""
    spec = _household(10, 0.04, 0.23)
    panel = _panel(spec, "drop=0.10,0.20;year=1;recovery=permanent,full:7")
    lines, cols, rows = _parse_block(format_crash_panel(panel, paths=5000))
    _check_arithmetic(cols, rows)
    assert lines[1] == "  central line" + lines[1][len("  central line"):]
    assert lines[1].endswith("futures (5,000)")
    assert ("  break-even: too close to call from no drop to 5.31%; rent is cheaper above 5.31% "
            "(crossing 2.05%) [solved, central case]") in lines
    assert ("  break-even: no crossing from no drop to a 99% drop: too close to call throughout "
            "[solved, central case]") in lines
    none = rows[0]
    assert (none["drop"], none["sale value"], none["condo"], none["rent"], none["rent − condo"]) == (
        "none", "×1", "200,502", "207,027", "+6,525")
    ten = rows[1]
    assert (ten["drop"], ten["sale value"], ten["level"], ten["best"]) == ("10%", "×0.900", "−31,810", "rent")
    assert lines[3].split() == ["none", "×1", "200,502", "207,027", "+6,525", "0", "condo", "tie",
                                "condo", "0.5450", "tie", "48,104", "none", "condo", "max", "36.2%",
                                "breaches", "years", "[1,", "2,", "3,", "4,", "5];", "rent", "max",
                                "23.4%", "breaches", "none"]
    twenty = next(l for l in lines if l.startswith("  20%"))
    assert "condo 1–2" in twenty


def test_row10_the_house_rows_and_their_crossings_are_templates():
    panel = _panel(_spec(_raw(HOUSE)), "drop=0.3,0.4;year=1,19;recovery=permanent,share:0.5:3",
                   monte_carlo=False)
    lines, cols, rows = _parse_block(format_crash_panel(panel))
    _check_arithmetic(cols, rows)
    assert lines[1] == "  central line"
    assert ("  break-even: house is cheaper below 30.70%; too close to call from 30.70% to 47.41%; "
            "rent is cheaper above 47.41% (crossing 38.85%) [solved, central case]") in lines
    assert "year 1 · share 0.5 over 3 years" in lines


def test_row10_a_recovery_under_way_at_the_sale_moves_the_futures_by_its_sale_multiple():
    """P1 at seed 42, year 9, full:7: the sale is one year into the
    seven-year recovery, so every future takes m(10), not m(9). The futures' cells, as
    printed (a condo path that took m(9) prints other futures cells)."""
    panel = _panel(_household(10, 0.04, 0.23), "drop=0.1,0.2,0.4;year=9;recovery=full:7")
    lines, cols, rows = _parse_block(format_crash_panel(panel, paths=5000))
    _check_arithmetic(cols, rows)
    printed = [l.split()[:12] for l in lines if re.match(r"  \d+% ", l)]
    assert printed == [
        ["10%", "×0.914", "227,970", "207,027", "−20,943", "−27,468", "rent", "option",
         "rent", "0.6838", "option", "45,016"],
        ["20%", "×0.826", "255,879", "207,027", "−48,852", "−55,377", "rent", "option",
         "rent", "0.8812", "option", "41,958"],
        ["40%", "×0.645", "313,293", "207,027", "−106,266", "−112,791", "rent", "option",
         "rent", "0.9984", "option", "36,003"],
    ]


def test_row15_the_disagreement_cell_names_both_options():
    """Row 15, rendered: `condo 0.4968 disagreement · rent 0.5032 of the futures`."""
    panel = _panel(_p2(), "drop=0.32;year=1;recovery=permanent")
    lines, _, _ = _parse_block(format_crash_panel(panel, paths=5000))
    row = next(l for l in lines if l.startswith("  32%"))
    assert "condo 0.4968 disagreement · rent 0.5032 of the futures" in row


def test_x8_three_options_print_the_rows_and_the_refusal_line():
    raw = _raw(THREE)
    raw["simulation"]["num_sims"] = 200
    panel = _panel(_spec(raw), "drop=0.1;year=1;recovery=permanent")
    lines, cols, _ = _parse_block(format_crash_panel(panel, paths=200))
    assert "level" not in cols and "sd" not in cols and "gap" in cols
    assert lines[-1] == "  break-even: refused (not_two_options): 3 options are priced"


def _cli(*argv: str, tmp_cwd=None):
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    try:
        sys.argv = ["hde", *argv]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_mod.main()
    finally:
        sys.argv = saved
    return code, out.getvalue(), err.getvalue()


def _ftb10l_file(tmp_path) -> str:
    path = tmp_path / "ftb10l.yaml"
    path.write_text(yaml.safe_dump(_ftb_laddered(10)), encoding="utf-8")
    return str(path)


def test_row13_the_read_back_line_follows_the_renewals_line(tmp_path):
    """Row 13. Once in --read-back and in assumptions.read_back, right after
    the `renewals:` line."""
    config = _ftb10l_file(tmp_path)
    flag = ("--crash-panel", "drop=0.10,0.20;year=1,9;recovery=permanent,full:5;jump=0.0237")
    want = ("crash panel: drops 10%, 20%; years 1, 9; recovery permanent, full over 5 years; "
            "jump +2.37 pp at the first renewal: condo; stated on the command line, not a "
            "forecast and not a probability")
    code, out, _ = _cli(config, *flag, "--read-back")
    assert code == 0
    lines = out.splitlines()
    assert lines.count(want) == 1
    assert lines[lines.index(want) - 1].startswith("condo renewals:")
    code, out, _ = _cli(config, *flag, "--json", "--no-monte-carlo")
    doc = json.loads(out)
    read_back = doc["assumptions"]["read_back"]
    assert read_back.count(want) == 1
    assert read_back[read_back.index(want) - 1].startswith("condo renewals:")
    assert doc["crash_panel"]["grid"]["jump"] == {"value": 0.0237, "options": ["condo"]}
    assert len(doc["crash_panel"]["rows"]) == 8


def test_row13_no_line_and_no_key_without_the_flag(tmp_path):
    config = _ftb10l_file(tmp_path)
    code, out, _ = _cli(config, "--read-back")
    assert code == 0 and "crash panel" not in out
    code, out, _ = _cli(config, "--json", "--no-monte-carlo")
    doc = json.loads(out)
    assert "crash_panel" not in doc
    assert not any("crash panel" in line for line in doc["assumptions"]["read_back"])


def test_the_short_read_back_counts_the_line(tmp_path):
    code, out, _ = _cli(_ftb10l_file(tmp_path), "--crash-panel",
                        "drop=0.1;year=1;recovery=permanent", "--read-back", "short")
    assert code == 0
    closing = out.splitlines()[-1]
    assert closing.startswith("full read-back:") and "crash panel" in closing
    assert not any(l.startswith("crash panel:") for l in out.splitlines())


def test_the_text_block_prints_after_the_report_and_q_keeps_it():
    code, out, _ = _cli(str(FTB), "--crash-panel", "drop=0.1;year=1;recovery=permanent", "-q")
    assert code == 0
    assert HEADER in out.splitlines()


def test_a_refused_grid_prints_its_refusal_in_place_and_the_run_goes_on():
    code, out, _ = _cli(str(FTB), "--crash-panel", "drop=1.5;year=1;recovery=permanent", "-q")
    assert code == 0
    assert "crash panel — refused (drop_out_of_range): drop 1.5 is outside (0, 0.99]" in out
    assert out.startswith("Condo: $200,502")
    code, out, _ = _cli(str(FTB), "--crash-panel", "drop=0.1;year=11;recovery=permanent", "--json")
    panel = json.loads(out)["crash_panel"]
    assert panel["refused"] == {"code": "year_out_of_range",
                                "fact": "year 11 is past the 10-year horizon"}
    assert panel["rows"] == [] and panel["no_drop"] is None


def test_a_jump_below_the_floor_prints_its_refusal_in_place(tmp_path):
    """X10 through the command line: the run that used to end in a traceback
    prints the refusal where the block goes and exits as the run does."""
    code, out, _ = _cli(_ftb10l_file(tmp_path), "--crash-panel",
                        "drop=0.2;year=1;recovery=permanent;jump=-0.06", "-q")
    assert code == 0
    assert ("crash panel — refused (jump_floor): jump −0.06 takes the first renewal to −1.45%, "
            "below 0") in out.splitlines()


def test_a_flag_without_the_grid_shape_exits_1():
    code, _, err = _cli(str(FTB), "--crash-panel", "drop=x;year=1;recovery=permanent")
    assert code == 1
    assert "Error: --crash-panel drop: 'x' is not a number" in err


def test_the_json_block_is_the_runner_document():
    code, out, _ = _cli(str(FTB), "--crash-panel", "drop=0.1;year=1;recovery=full:7", "--json")
    panel = json.loads(out)["crash_panel"]
    assert set(panel) == {"grid", "source", "no_drop", "rows", "break_evens", "refused"}
    assert panel["source"] == "command line"
    (row,) = panel["rows"]
    assert set(row) == {"drop", "year", "recovery", "sale_multiple", "central", "level_pv",
                        "futures", "underwater_years", "affordability"}
    assert row["recovery"] == {"form": "share", "share": 1.0, "years": 7}
    (be,) = panel["break_evens"]
    # One input, one name: the flag's `drop=` is the break-even's `crash.drop`.
    assert (be["key"], be["bracket"]) == ("crash.drop", [0.0, 0.99])
    assert be["no_crossing"] == {"cheaper": "condo", "lo": 0.0, "hi": 0.99,
                                 "tie_bands": [[None, None]]}
    assert "widen" not in json.dumps(panel)


# --- the no-crossing line reads the margin rule as the rows do ------------------------------

from hde.crash_panel import _no_crossing_text, tie_bands  # noqa: E402


def _no_crossing_case(spec, arg: str):
    panel = _panel(spec, arg, monte_carlo=False)
    lines, _, _ = _parse_block(format_crash_panel(panel))
    states = {row["drop"]: row["central"]["state"] for row in panel["rows"]}
    (line,) = [l for l in lines if l.startswith("  break-even:")]
    return line, states, panel["break_evens"][0]["no_crossing"]


def test_no_crossing_tie_throughout_where_every_row_is_a_tie():
    """FTB, full:7 from year 1: m(10) = 1, so every row is the base's 3.25%
    tie, and the line says so instead of "condo is cheaper throughout"."""
    line, states, record = _no_crossing_case(_spec(_raw(FTB)),
                                             "drop=0.1,0.4,0.99;year=1;recovery=full:7")
    assert set(states.values()) == {"tie"}
    assert line == ("  break-even: no crossing from no drop to a 99% drop: too close to call "
                    "throughout [solved, central case]")
    assert record["tie_bands"] == [[None, None]]


def test_no_crossing_decisive_throughout_where_every_row_is_decisive():
    """House example, full:7 from year 1: the house only gets cheaper (R3)."""
    line, states, record = _no_crossing_case(_spec(_raw(HOUSE)),
                                             "drop=0.1,0.4,0.99;year=1;recovery=full:7")
    assert set(states.values()) == {"option"}
    assert line == ("  break-even: no crossing from no drop to a 99% drop: house is cheaper "
                    "throughout [solved, central case]")
    assert record["tie_bands"] == []


def test_no_crossing_tie_then_decisive():
    """The house example at 80% of its rent starts inside the band (3.6%) and a
    recovered drop's lower maintenance carries the house out of it."""
    raw = _raw(HOUSE)
    raw["rent"]["monthly_rent"] = round(raw["rent"]["monthly_rent"] * 0.8)
    line, states, record = _no_crossing_case(_spec(raw), "drop=0.1,0.4,0.9;year=1;recovery=full:7")
    assert states == {0.1: "tie", 0.4: "option", 0.9: "option"}
    assert line == ("  break-even: no crossing from no drop to a 99% drop: too close to call "
                    "from no drop to 23.04%; house is cheaper above 23.04% [solved, central case]")
    (band,) = record["tie_bands"]
    assert band[0] is None and 0.1 < band[1] < 0.4


def test_no_crossing_decisive_then_tie():
    """FTB-25L, full:15 from year 11: four of the fifteen recovery years fall
    after the sale, so the sale meets part of the drop and a deep enough one
    brings the condo's lead inside the band without crossing."""
    line, states, record = _no_crossing_case(_spec(_ftb_laddered(25)),
                                             "drop=0.4,0.9,0.98;year=11;recovery=full:15")
    assert states == {0.4: "option", 0.9: "option", 0.98: "tie"}
    assert line == ("  break-even: no crossing from no drop to a 99% drop: condo is cheaper "
                    "below 97.50%; too close to call from 97.50% to a 99% drop "
                    "[solved, central case]")
    (band,) = record["tie_bands"]
    assert 0.9 < band[0] < 0.98 and band[1] is None


def _synthetic(fracs):
    """totals_at for a made-up margin: A cheaper by `frac(d)` of A's total."""
    return lambda d: (100.0, 100.0 * (1 + fracs(d)))


def test_tie_bands_find_every_stretch_and_include_the_grid_drops():
    """A margin that dips into the band and out again, and one that leaves it
    and comes back: each stretch is found, and a stretch narrower than the
    scan spacing is found at a grid drop."""
    dip = _synthetic(lambda d: 0.03 if 0.3 <= d <= 0.6 else 0.08)
    bands = tie_bands(dip, 0.0, 0.99)
    assert len(bands) == 1 and abs(bands[0][0] - 0.3) < 1e-9 and abs(bands[0][1] - 0.6) < 1e-6
    narrow = _synthetic(lambda d: 0.03 if 0.501 <= d <= 0.502 else 0.08)
    assert tie_bands(narrow, 0.0, 0.99) == []
    assert len(tie_bands(narrow, 0.0, 0.99, drops=(0.5015,))) == 1
    hump = _synthetic(lambda d: 0.08 if 0.2 <= d <= 0.7 else 0.03)
    assert [[b is None for b in band] for band in tie_bands(hump, 0.0, 0.99)] == [
        [True, False], [False, True]]


def test_the_no_crossing_clauses_for_every_shape():
    def text(bands):
        return _no_crossing_text({"cheaper": "condo", "tie_bands": bands})
    assert text([]) == "condo is cheaper throughout"
    assert text([[None, None]]) == "too close to call throughout"
    assert text([[None, 0.2]]) == "too close to call from no drop to 20.00%; condo is cheaper above 20.00%"
    assert text([[0.3, None]]) == "condo is cheaper below 30.00%; too close to call from 30.00% to a 99% drop"
    assert text([[0.3, 0.6]]) == ("condo is cheaper below 30.00%; too close to call from 30.00% to "
                                  "60.00%; condo is cheaper above 60.00%")
    assert text([[None, 0.2], [0.7, None]]) == (
        "too close to call from no drop to 20.00%; condo is cheaper from 20.00% to 70.00%; "
        "too close to call from 70.00% to a 99% drop")
