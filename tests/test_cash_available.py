"""
`cash_available` on an owned option (2026-09-03, round-7 dogfood).

Every threshold serve so far hand-computed `down_payment = cash − purchase_costs`
on the user's behalf and typed the result in — unchecked arithmetic that landed
at 20.04% down by hand in three separate runs. The user states the cash pile;
the engine nets the CASH purchase costs out of it (financed_purchase_costs ride
the loan and are NOT netted), and every downstream figure — the financing line,
the under-20% warning, the break-even grid — reads the computed down payment.
"""

import copy

import pytest

from hde.break_even import solve_break_even
from hde.config import ConfigValidationError, coherence_warnings, load_config_dict
from hde.serialization import assumptions_to_dict
from hde.sweep import run_sweep, with_value


def _base(**over):
    cfg = {
        "years": 10,
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0},
        "condo": {
            "initial_value": 400_000, "monthly_fee": 300, "value_growth_rate": 0.0,
            "mortgage_rate": 0.04, "mortgage_term_years": 25,
            "purchase_costs": 12_000, "cash_available": 90_000,
            "other_recurring_costs": [
                {"name": "tax", "annual_amount": 3_000, "escalation_rate": 0.0}],
        },
    }
    cfg.update(over)
    return cfg


def _condo(**over):
    """The base config with condo keys overridden (None drops the key)."""
    cfg = _base()
    for k, v in over.items():
        if v is None:
            cfg["condo"].pop(k, None)
        else:
            cfg["condo"][k] = v
    return cfg


class TestNetting:
    """cash − purchase_costs = down payment; financed costs are not netted."""

    def test_down_payment_is_cash_less_purchase_costs(self):
        spec = load_config_dict(_base())
        assert spec.condo.down_payment == pytest.approx(78_000.0)
        assert spec.condo.cash_available == pytest.approx(90_000.0)

    def test_financed_purchase_costs_are_not_netted_out_of_the_cash(self):
        """A financed premium rides the loan — it never touches the cash pile."""
        spec = load_config_dict(_condo(financed_purchase_costs=9_000))
        assert spec.condo.down_payment == pytest.approx(78_000.0)

    def test_zero_purchase_costs_nets_to_the_whole_pile(self):
        spec = load_config_dict(_condo(purchase_costs=0.0))
        assert spec.condo.down_payment == pytest.approx(90_000.0)

    def test_the_computed_down_payment_drives_the_loan(self):
        """Same figures typed as down_payment must price identically."""
        cash = load_config_dict(_base())
        typed = load_config_dict(_condo(cash_available=None, down_payment=78_000))
        from hde.deterministic import compute_deterministic
        assert (compute_deterministic(cash).condo.total_pv
                == pytest.approx(compute_deterministic(typed).condo.total_pv))

    def test_cash_below_purchase_costs_is_refused(self):
        with pytest.raises(ConfigValidationError) as e:
            load_config_dict(_condo(cash_available=8_000))
        assert "cash_available" in str(e.value) and "purchase_costs" in str(e.value)

    def test_house_nets_the_same_way(self):
        cfg = {"years": 10, "rent": {"monthly_rent": 2_000},
               "house": {"initial_value": 500_000, "mortgage_rate": 0.04,
                         "mortgage_term_years": 25, "purchase_costs": 15_000,
                         "cash_available": 115_000}}
        assert load_config_dict(cfg).house.down_payment == pytest.approx(100_000.0)


class TestMutualExclusion:
    def test_both_given_is_refused_naming_both(self):
        with pytest.raises(ConfigValidationError) as e:
            load_config_dict(_condo(down_payment=80_000))
        msg = str(e.value)
        assert "down_payment" in msg and "cash_available" in msg

    def test_neither_given_is_refused_naming_both_as_the_choice(self):
        with pytest.raises(ConfigValidationError) as e:
            load_config_dict(_condo(cash_available=None))
        msg = str(e.value)
        assert "declare all_cash: true OR a mortgage block" in msg
        assert "cash_available" in msg

    def test_cash_available_with_all_cash_is_refused(self):
        with pytest.raises(ConfigValidationError) as e:
            load_config_dict(_condo(all_cash=True, mortgage_rate=None,
                                    mortgage_term_years=None))
        assert "cash_available" in str(e.value)

    def test_all_cash_alone_still_parses(self):
        """The regression guard: cash_available must not break all_cash configs."""
        spec = load_config_dict({"years": 10, "rent": {"monthly_rent": 2_000},
                                 "condo": {"initial_value": 400_000, "monthly_fee": 300,
                                           "all_cash": True}})
        assert spec.condo.cash_available is None

    def test_netted_down_payment_above_the_price_is_refused(self):
        with pytest.raises(ConfigValidationError) as e:
            load_config_dict(_condo(cash_available=500_000))
        assert "cash_available" in str(e.value)


class TestFinancingLine:
    """The assumptions line shows the netting, not just its result."""

    def _line(self, cfg):
        return next(l for l in assumptions_to_dict(load_config_dict(cfg), None)["lines"]
                    if l.startswith("condo financing:"))

    def test_the_line_shows_the_pile_the_costs_and_the_result(self):
        line = self._line(_base())
        assert "cash available $90,000" in line
        assert "purchase_costs $12,000" in line
        assert "down payment $78,000" in line

    def test_the_line_shows_loan_to_value_and_the_distance_to_the_line(self):
        line = self._line(_base())
        assert "19.50% of price" in line
        assert "$2,000 below the 20% mortgage-insurance line ($80,000)" in line
        assert "loan-to-value 80.50%" in line

    def test_the_down_payment_dollar_figure_appears_once(self):
        """Extended, not duplicated: one line, one statement of each figure."""
        line = self._line(_base())
        assert line.count("$78,000") == 1
        assert line.count("$90,000") == 1

    def test_loan_to_value_counts_the_financed_costs(self):
        """LTV is the loan the engine actually finances, premium included."""
        line = self._line(_condo(financed_purchase_costs=8_000))
        assert "loan-to-value 82.50%" in line

    def test_the_line_says_the_price_at_which_the_cash_stops_covering_20(self):
        """Round-9 review: the answer hand-solved "your $140,000 covers 20%
        down up to $642,893" — the engine's own fixed point, (cash − costs) /
        20%, and the price above which the mortgage is insured."""
        line = self._line(_condo(cash_available=130_000, purchase_costs=5_000))
        assert "covers 20% down up to a price of $625,000" in line
        assert "above it the mortgage is insured" in line

    def test_the_fixed_point_says_what_it_holds_fixed(self):
        line = self._line(_condo(cash_available=130_000, purchase_costs=5_000))
        assert "purchase_costs held at $5,000" in line

    def test_a_typed_down_payment_gets_no_fixed_point(self):
        line = self._line(_condo(cash_available=None, down_payment=80_000))
        assert "covers 20% down up to" not in line

    def test_a_typed_down_payment_keeps_the_plain_head(self):
        line = self._line(_condo(cash_available=None, down_payment=80_000))
        assert line.startswith("condo financing: down payment $80,000")
        assert "cash available" not in line


class TestUnderTwentyWarningFiresOnTheComputedFigure:
    """The warning must read the NETTED down payment, not the cash pile."""

    def test_cash_that_nets_below_the_line_warns_at_the_computed_percent(self):
        warns = coherence_warnings(load_config_dict(_base()))
        under = [w for w in warns if "under the 20%" in w]
        assert under, warns
        assert "19.50% of price" in under[0]

    def test_the_same_pile_typed_as_down_payment_does_not_warn(self):
        """90,000 typed straight in is 22.5% — the hand-computation error the
        netting removes; it must not silently clear the insurance line."""
        warns = coherence_warnings(load_config_dict(
            _condo(cash_available=None, down_payment=90_000)))
        assert not [w for w in warns if "under the 20%" in w]

    def test_cash_clearing_the_line_after_netting_does_not_warn(self):
        warns = coherence_warnings(load_config_dict(_condo(cash_available=92_000)))
        assert not [w for w in warns if "under the 20%" in w]


class TestGridPathsReNet:
    """--break-even and --sweep re-run the loader per point, so the netting is
    re-derived at every grid value instead of being frozen at the base config."""

    def test_break_even_on_price_differs_between_fixed_cash_and_fixed_down_payment(self):
        """The same 90,000: as a cash pile it buys a 78,000 down payment, as a
        typed down_payment it buys 90,000 — different loans, different crossing."""
        cash_cfg = _base()
        typed_cfg = _condo(cash_available=None, down_payment=90_000)
        cash = solve_break_even(cash_cfg, "condo.initial_value")
        typed = solve_break_even(typed_cfg, "condo.initial_value")
        assert cash["break_evens"] and typed["break_evens"]
        assert cash["break_evens"][0]["value"] != pytest.approx(
            typed["break_evens"][0]["value"], rel=1e-6)

    def test_sweeping_purchase_costs_moves_the_netted_down_payment_per_point(self):
        """The discriminating case: with the cash pile fixed, each grid point's
        purchase_costs nets a DIFFERENT down payment. A netting frozen at the
        base config would hold it at 78,000 across the sweep."""
        raw = _base()
        dps = [load_config_dict(with_value(raw, "condo.purchase_costs", v)).condo.down_payment
               for v in (6_000.0, 12_000.0, 18_000.0)]
        assert dps == [pytest.approx(84_000.0), pytest.approx(78_000.0),
                       pytest.approx(72_000.0)]

    def test_sweep_rows_move_with_the_re_netted_down_payment(self):
        rows = run_sweep(_base(), "condo.purchase_costs", [6_000.0, 18_000.0],
                         monte_carlo=False)["rows"]
        assert all("error" not in r for r in rows), rows
        totals = [r["totals"]["condo"] for r in rows]
        # A bigger closing bill both costs more AND shrinks the down payment,
        # so the two rows cannot differ by the $12,000 cost delta alone.
        assert abs((totals[1] - totals[0]) - 12_000.0) > 1.0

    def test_a_price_below_the_netted_down_payment_is_refused_not_crashed(self):
        """Refused grid points shrink the search; they never raise."""
        result = solve_break_even(_base(), "condo.initial_value", 50_000, 600_000)
        assert result["refused"]["count"] >= 1
        assert "cash_available" in result["refused"]["reason"]


class TestSchemaAndContract:
    def test_cash_available_is_published_in_the_schema(self):
        from hde.input_schema import input_schema
        for section in ("condo", "house"):
            entry = input_schema()[section]["cash_available"]
            assert entry["required"] is False
            assert "purchase_costs" in entry["note"]
            assert entry["required_if"]

    def test_the_capital_structure_sentence_names_cash_available(self):
        from hde.input_schema import input_schema
        note = input_schema()["condo"]["down_payment"]["required_if"]
        assert "cash_available" in note

    def test_break_even_gives_cash_available_a_default_bracket(self):
        from hde.break_even import _MONEY_KEYS
        assert "cash_available" in _MONEY_KEYS


class TestUnchangedConfigsAreUntouched:
    def test_a_config_without_cash_available_is_byte_identical_in_its_line(self):
        cfg = _condo(cash_available=None, down_payment=80_000)
        before = copy.deepcopy(cfg)
        load_config_dict(cfg)
        assert cfg == before, "the loader must not mutate the caller's mapping"
