"""
Price-scan coherence (2026-09-03, answer reviews).

A `--break-even` or `--sweep` on an owned option's `initial_value` re-runs the
whole loader per grid point, so anything the loader DERIVES from the price
moves with it — and anything typed in dollars does not. The property-tax bill,
`purchase_costs`, `financed_purchase_costs` and insurance are all
price-proportional in reality and dollar-denominated in the config, so a
price scan silently holds them at the seed price's size: one no-listing answer
handed a user a "buying wins above $346k" band that moves ~$50k once those
inputs scale, another moved a clear-win edge $35k.

Three things close it: rate alternatives the loader re-derives every load
(`property_tax_rate`, `purchase_costs_rate`), a coherence note whenever a price
scan leaves a dollar form in place, and the affordability ratios at the
crossing and both band edges — a reviewer found an answer calling a range
"cheaper on average" while the engine's own sweep showed 40.9% of income there,
above the 39% cap the answer itself cited.
"""

import json
import sys

import pytest

from hde.break_even import solve_break_even
from hde.cli import main as cli_main
from hde.config import ConfigValidationError, load_config_dict
from hde.sweep import run_sweep, with_value

PRICE_RAW = {
    "years": 25,
    "house": {
        "initial_value": 650_000,
        "value_growth_rate": 0.01,
        "down_payment": 130_000,
        "mortgage_rate": 0.04,
        "mortgage_term_years": 25,
        "purchase_costs": 18_000,
        "annual_maintenance_rate": 0.006,
        "other_recurring_costs": [
            {"name": "property tax", "annual_amount": 4_200, "escalation_rate": 0.0},
            {"name": "home insurance", "annual_amount": 1_800, "escalation_rate": 0.0},
        ],
    },
    "rent": {"monthly_rent": 2_100, "invested_down_payment": 148_000},
    "income": {"annual_income": 120_000},
}

NOTE = (
    "held fixed in dollars while the price moves: house.purchase_costs=$18,000, "
    "house.other_recurring_costs[property tax]=$4,200/yr, "
    "house.other_recurring_costs[home insurance]=$1,800/yr — sized for $650,000, "
    "this understates owner costs above it (favours buying) and overstates them below "
    "(favours renting); use property_tax_rate / purchase_costs_rate to scale them"
)


def _rates_raw():
    """The same config with both dollar forms replaced by their rate alternatives."""
    raw = {k: (dict(v) if isinstance(v, dict) else v) for k, v in PRICE_RAW.items()}
    house = dict(raw["house"])
    house.pop("purchase_costs")
    house["purchase_costs_rate"] = 18_000 / 650_000
    house["property_tax_rate"] = 4_200 / 650_000
    house["other_recurring_costs"] = [
        {"name": "home insurance", "annual_amount": 1_800, "escalation_rate": 0.0},
    ]
    raw["house"] = house
    return raw


# ---------------------------------------------------------------------------
# (1) rate alternatives the loader derives per load
# ---------------------------------------------------------------------------
class TestRateAlternatives:
    def test_purchase_costs_rate_is_a_fraction_of_the_price(self):
        raw = _rates_raw()
        spec = load_config_dict(raw)
        assert spec.house.purchase_costs == pytest.approx(18_000)

    def test_every_grid_point_re_derives_the_purchase_costs(self):
        raw = _rates_raw()
        for price in (400_000, 900_000):
            spec = load_config_dict(with_value(raw, "house.initial_value", price))
            assert spec.house.purchase_costs == pytest.approx(price * 18_000 / 650_000)

    def test_purchase_costs_rate_and_purchase_costs_are_exclusive(self):
        raw = _rates_raw()
        raw["house"]["purchase_costs"] = 18_000
        with pytest.raises(ConfigValidationError) as e:
            load_config_dict(raw)
        assert "purchase_costs_rate" in str(e.value) and "purchase_costs" in str(e.value)

    def test_cash_available_nets_the_derived_purchase_costs(self):
        raw = _rates_raw()
        house = raw["house"]
        house.pop("down_payment")
        house["cash_available"] = 150_000
        spec = load_config_dict(raw)
        assert spec.house.down_payment == pytest.approx(150_000 - 18_000)
        # and the netting follows the price, grid point by grid point
        spec2 = load_config_dict(with_value(raw, "house.initial_value", 900_000))
        assert spec2.house.down_payment == pytest.approx(150_000 - 900_000 * 18_000 / 650_000)

    def test_property_tax_rate_derives_a_value_proportional_bill(self):
        raw = _rates_raw()
        spec = load_config_dict(with_value(raw, "house.initial_value", 800_000))
        taxes = [c for c in spec.house.other_recurring_costs if "property tax" in c.name]
        assert len(taxes) == 1
        assert taxes[0].annual_amount == pytest.approx(800_000 * 4_200 / 650_000)
        # "fraction of value per year": the bill tracks the value's growth
        assert taxes[0].escalation_rate == pytest.approx(spec.house.value_growth_rate)

    def test_property_tax_rate_and_a_dollar_tax_line_are_exclusive(self):
        raw = _rates_raw()
        raw["house"]["other_recurring_costs"] = [
            {"name": "property tax", "annual_amount": 4_200},
        ]
        with pytest.raises(ConfigValidationError) as e:
            load_config_dict(raw)
        assert "property_tax_rate" in str(e.value) and "property tax" in str(e.value)

    def test_both_rate_keys_work_on_the_condo_side_too(self):
        raw = {
            "years": 10,
            "condo": {"initial_value": 500_000, "monthly_fee": 350, "all_cash": True,
                      "purchase_costs_rate": 0.02, "property_tax_rate": 0.008},
            "rent": {"monthly_rent": 1_900, "invested_down_payment": 510_000},
        }
        spec = load_config_dict(with_value(raw, "condo.initial_value", 700_000))
        assert spec.condo.purchase_costs == pytest.approx(14_000)
        taxes = [c for c in spec.condo.other_recurring_costs if "property tax" in c.name]
        assert taxes[0].annual_amount == pytest.approx(5_600)

    @pytest.mark.parametrize("key", ["purchase_costs_rate", "property_tax_rate"])
    def test_negative_rates_refused(self, key):
        raw = _rates_raw()
        raw["house"][key] = -0.01
        with pytest.raises(ConfigValidationError):
            load_config_dict(raw)

    def test_the_rate_form_moves_the_threshold(self):
        """The whole point. A no-listing user seeds a price and asks where
        buying starts to win; the crossing lands far from the seed, and the
        dollar forms are still sized for the seed. Scaling them moves the
        threshold by tens of thousands — the reviewed answer's ~$50k."""
        fixed = {
            "years": 25,
            "house": {
                "initial_value": 450_000, "value_growth_rate": 0.01,
                "down_payment": 90_000, "mortgage_rate": 0.04, "mortgage_term_years": 25,
                "purchase_costs": 12_500, "annual_maintenance_rate": 0.006,
                "other_recurring_costs": [
                    {"name": "property tax", "annual_amount": 3_800, "escalation_rate": 0.0},
                    {"name": "home insurance", "annual_amount": 1_500, "escalation_rate": 0.0},
                ],
            },
            "rent": {"monthly_rent": 2_600, "invested_down_payment": 102_500},
        }
        scaled = {**fixed, "house": {**fixed["house"]}}
        scaled["house"].pop("purchase_costs")
        scaled["house"]["purchase_costs_rate"] = 12_500 / 450_000
        scaled["house"]["property_tax_rate"] = 3_800 / 450_000
        scaled["house"]["other_recurring_costs"] = [
            {"name": "home insurance", "annual_amount": 1_500, "escalation_rate": 0.0},
        ]
        a = solve_break_even(fixed, "house.initial_value")["break_evens"][0]["value"]
        b = solve_break_even(scaled, "house.initial_value")["break_evens"][0]["value"]
        # the crossing sits well above the seed, where the dollar forms understate
        # owner costs: scaling them pulls the "buying wins below" threshold down
        assert a > 700_000 and b < a - 50_000


# ---------------------------------------------------------------------------
# (2) the coherence note
# ---------------------------------------------------------------------------
class TestCoherenceNote:
    def test_break_even_on_price_names_the_fixed_dollar_inputs(self):
        result = solve_break_even(PRICE_RAW, "house.initial_value")
        assert NOTE in result["note"]

    def test_sweep_on_price_names_them_too(self):
        result = run_sweep(PRICE_RAW, "house.initial_value", [500_000, 800_000],
                           monte_carlo=False)
        assert NOTE in result["note"]

    def test_financed_purchase_costs_are_named(self):
        raw = {**PRICE_RAW, "house": {**PRICE_RAW["house"], "financed_purchase_costs": 12_000}}
        result = run_sweep(raw, "house.initial_value", [500_000, 800_000], monte_carlo=False)
        assert "house.financed_purchase_costs=$12,000" in result["note"]

    def test_no_note_when_the_rate_forms_are_used(self):
        raw = _rates_raw()
        raw["house"]["other_recurring_costs"] = []
        assert run_sweep(raw, "house.initial_value", [500_000, 800_000],
                         monte_carlo=False).get("note") is None
        assert "held fixed in dollars" not in (
            solve_break_even(raw, "house.initial_value").get("note") or "")

    def test_no_note_when_the_scan_is_not_on_a_price(self):
        result = run_sweep(PRICE_RAW, "rent.monthly_rent", [1_800, 2_400], monte_carlo=False)
        assert "held fixed in dollars" not in (result.get("note") or "")

    def test_the_note_reaches_the_text_output(self, tmp_path, monkeypatch, capsys):
        import yaml
        cfg = tmp_path / "c.yaml"
        cfg.write_text(yaml.safe_dump(PRICE_RAW))
        monkeypatch.setattr(sys, "argv", [
            "hde", str(cfg), "--no-monte-carlo",
            "--sweep", "house.initial_value=500000,800000",
            "--break-even", "house.initial_value",
        ])
        assert cli_main() == 0
        out = capsys.readouterr().out
        # once on the sweep block, once on the break-even, and once more in the
        # read-back block — which repeats by design: it is the paste-ready copy
        # of every line an answer has to carry (2026-09-04).
        assert out.count(NOTE) == 3

    def test_the_prior_note_and_the_coherence_note_coexist(self):
        raw = {**PRICE_RAW, "market_scenario": {
            "path": "tests/fixtures/scenario_prior_golden.json", "geography": "MTL_RMR"}}
        note = solve_break_even(raw, "house.initial_value")["note"]
        assert "deterministic line" in note and NOTE in note


# ---------------------------------------------------------------------------
# (3) affordability at the crossing and both band edges
# ---------------------------------------------------------------------------
class TestBreakEvenAffordability:
    def test_carried_at_the_crossing_and_both_edges(self):
        result = solve_break_even(PRICE_RAW, "house.initial_value")
        be = result["break_evens"][0]
        aff = be["affordability"]
        assert aff["threshold"] == pytest.approx(0.32)
        for point in [aff["value"]] + [e for e in aff["tie_band"] if e is not None]:
            assert set(point) == {"house", "rent"}
            for per_option in point.values():
                assert per_option["max_ratio"] > 0
                assert isinstance(per_option["years_exceeding"], list)
        # the house is bought at the crossing price: a dearer band edge is dearer
        lo, hi = aff["tie_band"]
        assert lo is not None and hi is not None
        assert lo["house"]["max_ratio"] < hi["house"]["max_ratio"]

    def test_null_without_an_income_block(self):
        raw = {k: v for k, v in PRICE_RAW.items() if k != "income"}
        assert solve_break_even(raw, "house.initial_value")["break_evens"][0]["affordability"] is None

    def test_printed_in_the_text_output(self, tmp_path, monkeypatch, capsys):
        import yaml
        cfg = tmp_path / "c.yaml"
        cfg.write_text(yaml.safe_dump(PRICE_RAW))
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo",
                                          "--break-even", "house.initial_value"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert "affordability" in out and "32% threshold" in out
        assert "at the crossing" in out and "band edge" in out

    def test_rides_json(self, tmp_path, monkeypatch, capsys):
        import yaml
        cfg = tmp_path / "c.yaml"
        cfg.write_text(yaml.safe_dump(PRICE_RAW))
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--json", "--no-monte-carlo",
                                          "--break-even", "house.initial_value"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        aff = doc["break_evens"][0]["break_evens"][0]["affordability"]
        assert set(aff) == {"threshold", "value", "tie_band"}
