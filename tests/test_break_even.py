"""
--break-even KEY[=lo:hi] (2026-09-02, operator product direction): most users
arrive certain about one side ("houses in Laval around $650k") and want the
threshold on the other ("what rent keeps renting the better deal?", or "what
price makes buying worth it at my rent?"). A sweep grid brackets that; this
solves it: the value of ONE input where the two priced options' deterministic
total PVs cross, plus the tie-band edges around it (the same 5% band the
verdict uses), so the answer reads "renting is cheaper below $X, too close to
call between $A and $B, buying is cheaper above $B".
"""

import pytest

from hde.anchors import ANCHORS
from hde.break_even import format_break_even, parse_break_even, solve_break_even
from hde.config import load_config_dict
from hde.deterministic import compute_deterministic
from hde.sweep import with_value

BAND = ANCHORS["verdict.tie_band"].value


def _base(**over):
    cfg = {
        "years": 10,
        "rent": {"monthly_rent": 2000, "rent_escalation_rate": 0.0, "invested_down_payment": 85_000},
        "condo": {
            "initial_value": 400_000, "monthly_fee": 300, "value_growth_rate": 0.0,
            "down_payment": 80_000, "mortgage_rate": 0.04, "mortgage_term_years": 25,
            "purchase_costs": 5_000,
            "other_recurring_costs": [{"name": "tax", "annual_amount": 3_000, "escalation_rate": 0.0}],
        },
    }
    cfg.update(over)
    return cfg


def _gap(raw, key, v):
    det = compute_deterministic(load_config_dict(with_value(raw, key, v)))
    return det.rent.total_pv - det.condo.total_pv


class TestParse:
    def test_bare_key_and_bracket_forms(self):
        assert parse_break_even("rent.monthly_rent") == ("rent.monthly_rent", None, None)
        assert parse_break_even("condo.initial_value=300000:900000") == ("condo.initial_value", 300000.0, 900000.0)

    def test_rejects_malformed(self):
        with pytest.raises(ValueError):
            parse_break_even("rent.monthly_rent=1000")
        with pytest.raises(ValueError):
            parse_break_even("=1:2")


class TestSolve:
    def test_rent_break_even_is_where_the_totals_cross(self):
        raw = _base()
        out = solve_break_even(raw, "rent.monthly_rent")
        assert out["options"] == ["condo", "rent"]
        assert len(out["break_evens"]) == 1
        be = out["break_evens"][0]
        assert abs(_gap(raw, "rent.monthly_rent", be["value"])) < 1.0  # dollars of PV
        # Renting is cheaper below the break-even rent, the condo above it.
        assert be["cheaper_below"] == "rent" and be["cheaper_above"] == "condo"
        lo, hi = be["tie_band"]
        assert lo < be["value"] < hi
        # At the band edges the margin is exactly the tie band of the winner's PV.
        for edge in (lo, hi):
            det = compute_deterministic(load_config_dict(with_value(raw, "rent.monthly_rent", edge)))
            a, b = det.rent.total_pv, det.condo.total_pv
            assert abs(abs(a - b) / abs(min(a, b)) - BAND) < 1e-4

    def test_price_break_even_from_the_rent_side(self):
        raw = _base()
        out = solve_break_even(raw, "condo.initial_value")
        assert len(out["break_evens"]) == 1
        be = out["break_evens"][0]
        assert be["cheaper_below"] == "condo" and be["cheaper_above"] == "rent"
        assert abs(_gap(raw, "condo.initial_value", be["value"])) < 1.0

    def test_default_bracket_is_a_quarter_to_four_times_the_base_value(self):
        out = solve_break_even(_base(), "rent.monthly_rent")
        assert out["bracket"] == [500.0, 8000.0] and out["base_value"] == 2000

    def test_no_crossing_in_bracket_is_said_not_invented(self):
        out = solve_break_even(_base(), "rent.monthly_rent", lo=100.0, hi=200.0)
        assert out["break_evens"] == [] and out["cheaper_throughout"] == "rent"

    def test_three_options_refused(self):
        raw = _base(house={"initial_value": 500_000, "all_cash": True, "value_growth_rate": 0.0})
        with pytest.raises(ValueError, match="exactly two"):
            solve_break_even(raw, "rent.monthly_rent")

    def test_defaulted_key_needs_an_explicit_bracket(self):
        raw = _base()
        del raw["rent"]["invested_down_payment"]
        with pytest.raises(ValueError, match="lo:hi"):
            solve_break_even(raw, "rent.invested_down_payment")


class TestFormat:
    def test_text_reads_as_a_threshold_sentence(self):
        out = solve_break_even(_base(), "rent.monthly_rent")
        text = format_break_even(out)
        assert "Break-even rent.monthly_rent" in text
        assert "rent is cheaper below" in text and "condo is cheaper above" in text
        assert "too close to call between" in text


class TestIntegerInputs:
    def test_years_reports_the_first_year_the_other_side_wins(self):
        raw = _base()
        out = solve_break_even(raw, "years", lo=2, hi=30)
        assert len(out["break_evens"]) == 1
        be = out["break_evens"][0]
        assert isinstance(be["value"], int) and be["last_value_below"] == be["value"] - 1
        # The sign really changes between those two integers.
        g_below = _gap(raw, "years", be["last_value_below"])
        g_above = _gap(raw, "years", be["value"])
        assert (g_below > 0) != (g_above > 0)
        assert all(e is None or isinstance(e, int) for e in be["tie_band"])
        assert "is cheaper up to years=" in format_break_even(out)
