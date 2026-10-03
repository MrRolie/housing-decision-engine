"""The crash stress panel (docs/specs/2026-10-03-crash-stress-panel.md; §10's
rows, each named where it is pinned).

Every refusal is pinned beside the legal grid one step away, so a refusal
deleted fails the first test of its pair and a refusal widened onto its
neighbour fails the second.
"""
from __future__ import annotations

import io
import math
import re
import tokenize
from pathlib import Path

import pytest

from hde.crash_panel import (
    MAX_ROWS, PERMANENT, CrashPanelRefusal, Recovery, check_years, drop_path, parse_grid,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "hde"


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
    assert grid.recoveries == (PERMANENT, Recovery("full", 1.0, 5), Recovery("share", 1.0, 5),
                               Recovery("full", 1.0, 15))
    assert grid.jump == 0.0237
    assert grid.row_count == 3 * 2 * 4


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
