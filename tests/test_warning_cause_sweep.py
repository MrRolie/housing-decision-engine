"""The sweep record: warnings whose guard is a disjunction, or whose message
names a cause, checked for a branch that makes the message FALSE.

Run 2026-09-21 over every warning this engine emits, after the capital-term
warning was found describing one cause on both of its branches
(`test_capital_term_attribution.py`). This file holds the three siblings the
sweep found, asserted on the rendered string, and — as much the point — the
NON-FINDINGS, so the next sweep does not re-derive them:

* `discount_rate outside [-15%, 15%]` — a two-sided guard, and the message
  names the interval rather than a side. True on both branches.
* `mortgage_rate is the POSTED 5-year rate` — matches the anchor's value OR any
  declared restatement, so the figure shown can be the semi-annual quote or its
  effective-annual form. Both ARE the posted rate as its source states it; the
  message names the figure, never the axis, so it holds on every branch. Axis
  note: a run typing 6.09% as `effective_annual` pays slightly less than the
  posted rate, and the sentence still holds because it is about the figure.
* `mortgage_renewal_rates are inert` (renewal years at or past the
  amortization) — names a key the config might not have set, except that
  `_mortgage_renewal` REFUSES `mortgage_renewal_years` without
  `mortgage_renewal_rates`. Unreachable with the key unstated.
* `down payment under the 20% line with no financed_purchase_costs` — the
  `elif` branch behind it needs `mortgage_insurance` to be present but not
  required, and `band_for` returns None only at or under 80% loan-to-value,
  which a down payment under 20% cannot reach. The branch is reachable only
  with no schedule stated, which is what the message addresses.
* `not modelled — purchase_costs / other_recurring_costs` — a joined list of
  whichever causes fired, and the closing "owner costs are understated, which
  biases the verdict toward buying" is true of each.
* `one-sided uncertainty` (whichever side is alone stochastic) and the renewal
  `not modelled` warning at a term of five years or less — both already fork
  their message on the branch, and their tests pin both forks.
* `asymmetric tails` — `any(price_shock)` over the two owned options, and the
  message says "an owned option carries a price_shock channel", true whichever
  one has it; its remedy binds either way.
* The per-option loops — the real-mode mortgage/affordability line (which forks
  the payment it quotes), the `tax: like-for-like` ask (which forks on whether
  the config typed `cash_available` or `down_payment`), the school-tax line, the
  four renewal-ladder warnings and the under-20% insured line — each fires once
  per option and names that option, so no branch speaks for another.
* `unpriced.qualifying_rate_line` and `straight_switch_clause` — both fork on
  `insured`, and their own comments record that the unforked sentence would be
  false. The `time_anchor_violations` pair, `validity_warnings`,
  `tfsa_room_warning` and the units tripwires each have one cause and one
  message.
* `sweep.one_sided_sweep_warning` — three branches (ABOVE, BELOW, and a
  placeholder it cannot compare at all), each with its own sentence.
"""

from hde.config import (affordability_warnings, coherence_warnings,
                        load_config_dict)
from hde.deterministic import compute_deterministic

CONDO = {"initial_value": 400_000, "monthly_fee": 300, "down_payment": 50_000,
         "mortgage_rate": 0.04, "mortgage_term_years": 25, "purchase_costs": 5_000,
         "value_growth_rate": 0.01,
         "other_recurring_costs": [{"name": "property_tax", "annual_amount": 3_000}]}
HOUSE = {"initial_value": 600_000, "down_payment": 100_000,
         "mortgage_rate": 0.04, "mortgage_term_years": 25, "purchase_costs": 8_000,
         "value_growth_rate": 0.01, "annual_maintenance_rate": 0.006,
         "other_recurring_costs": [{"name": "property_tax", "annual_amount": 4_000}]}


def warnings_for(doc):
    return coherence_warnings(load_config_dict(doc))


def one(doc, needle):
    hits = [w for w in warnings_for(doc) if needle in w]
    assert len(hits) == 1, hits
    return hits[0]


class TestTheRenterIsNotHeldToALendersRule:
    """`affordability_warnings` loops over rent, condo and house with ONE
    message, and that message was written about an owned option: it called the
    ratio GDS-shaped, said the numerator includes maintenance, and named CMHC's
    39% cap. A tenant has no mortgage, so no GDS exists for them, the rent
    numerator carries no maintenance (`_annual_costs_for_option` reads neither
    a maintenance rate nor a payment for it), and no lender tests them at all.
    """

    BASE = {
        "years": 10, "discount_rate": 0.05, "rates": "real",
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0},
        "income": {"annual_income": 60_000, "income_growth_rate": 0.0},
        "simulation": {"num_sims": 5, "random_seed": 1},
    }

    def rows(self, doc):
        return affordability_warnings(compute_deterministic(load_config_dict(doc)))

    def test_the_rent_row_names_its_own_numerator_and_no_lender_rule(self):
        rows = self.rows(self.BASE)
        assert len(rows) == 1
        assert rows[0] == (
            "affordability: rent housing cost exceeds 32% of income in years "
            "[1, 2, 3, 4, 5, 6, 7, 8, 9, 10] (max 40.0%) — rent plus the renter's own "
            "recurring costs over income, with no mortgage and no maintenance in it: a "
            "tenant faces no lender test, so this threshold is a budget line and not a "
            "qualifying rule [income.affordability_threshold]")
        assert "GDS" not in rows[0] and "CMHC" not in rows[0] and "TDS" not in rows[0]

    def test_an_owned_row_keeps_the_gds_cap_it_is_measured_against(self):
        doc = {**self.BASE, "condo": {**CONDO, "down_payment": 200_000}}
        owned = [w for w in self.rows(doc) if w.startswith("affordability: condo")]
        assert owned
        assert ("GDS-shaped ratio (housing cost incl. maintenance over income, no other "
                "debts): CMHC's cap for that shape is 39% GDS, not the 44% TDS "
                "[income.affordability_threshold]") in owned[0]


class TestTheNeutralGrowthWarningNamesTheTypedFigure:
    """`value_growth_rate == 0` is reached two ways: the key omitted (the
    engine's neutral 0% real default) and a quote equal to `inflation_rate`,
    which deflates to EXACTLY zero. The sentence printed "=0.0%" on both, so
    the second told a household that typed 2.1% a figure it never entered and
    asked it to state a view it had stated."""

    def doc(self, growth=None):
        condo = {"initial_value": 400_000, "monthly_fee": 300, "all_cash": True,
                 "purchase_costs": 5_000,
                 "other_recurring_costs": [{"name": "property_tax", "annual_amount": 3_000}]}
        if growth is not None:
            condo["value_growth_rate"] = growth
        return {
            "years": 10,
            "economic": {"mode": "nominal", "inflation_rate": 0.021},
            "condo": condo,
            "rent": {"monthly_rent": 1_800},
            "simulation": {"num_sims": 5, "random_seed": 1},
        }

    def test_a_quote_equal_to_inflation_is_shown_as_the_user_typed_it(self):
        assert one(self.doc(0.021), "no appreciation modelled") == (
            "condo.value_growth_rate=0.0% real (2.1% as quoted) — no appreciation modelled "
            "(neutral); the verdict is sensitive to it: state a view or bracket it "
            "(a market_scenario prior adds drift in the Monte Carlo only)")

    def test_an_omitted_key_has_no_quote_to_show(self):
        warning = one(self.doc(), "no appreciation modelled")
        assert warning.startswith("condo.value_growth_rate=0.0% — no appreciation modelled")
        assert "as quoted" not in warning


class TestTheRenterCapitalAskNamesEachOptionsOwnFigure:
    """The guard sums the down payments of BOTH owned options, and the message
    printed the sum. On a 3-way run that is a figure no option puts down and no
    renter should invest — the like-for-like capital is one option's. The
    repo's own uncertainty fixture records the same tension from the other
    side: "a single scalar cannot match both owned options"."""

    BASE = {
        "years": 10, "discount_rate": 0.05, "rates": "real",
        "rent": {"monthly_rent": 2_000, "invested_down_payment": 0},
        "simulation": {"num_sims": 5, "random_seed": 1},
    }
    TAIL = ("but rent.invested_down_payment=0 — the renter's equivalent capital is assumed "
            "to earn exactly the discount rate (net present value 0); set "
            "invested_down_payment + investment_return_rate to model a different return")

    def test_two_owned_options_are_named_separately_and_the_sum_is_gone(self):
        warning = one({**self.BASE, "condo": CONDO, "house": HOUSE},
                      "rent.invested_down_payment=0")
        assert warning == (
            f"owned options put $50,000 (condo) and $100,000 (house) down {self.TAIL} — a "
            f"single figure cannot match both, so the option you are weighing sets it")
        assert "$150,000" not in warning

    def test_one_owned_option_carries_no_choice_clause(self):
        warning = one({**self.BASE, "condo": CONDO}, "rent.invested_down_payment=0")
        assert warning == f"owned options put $50,000 (condo) down {self.TAIL}"

    def test_an_all_cash_option_still_puts_the_whole_price_down(self):
        house = {"initial_value": 600_000, "all_cash": True, "purchase_costs": 8_000,
                 "value_growth_rate": 0.01, "annual_maintenance_rate": 0.006,
                 "other_recurring_costs": [{"name": "property_tax", "annual_amount": 4_000}]}
        warning = one({**self.BASE, "house": house}, "rent.invested_down_payment=0")
        assert warning == f"owned options put $600,000 (house) down {self.TAIL}"
