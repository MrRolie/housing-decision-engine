"""
Mortgage renewal risk, slice 1 — the deterministic ladder
(docs/specs/2026-09-03-mortgage-renewal-risk.md §10).

The engine priced one rate for a whole 25-year amortization; a Canadian
five-year fixed renews four times. The user states the renewal path (their own
figure — no anchor, no forecast) and the engine re-amortizes the remaining
balance over the remaining amortization at each renewal.

The two invariants that bind every other assertion here:
  * EQUAL-RATE IDENTITY — every renewal at the contract rate reproduces the
    single-rate numbers the engine already computed;
  * ABSENCE — with no renewal key, nothing about any result changes.
"""

import copy

import pytest

from hde.config import ConfigValidationError, coherence_warnings, load_config_dict
from hde.deterministic import _financing_pv, compute_deterministic
from hde.pv import mortgage_payment, outstanding_balance, pv_annuity, pv_single
from hde.pv import renewal_schedule
from hde.serialization import assumptions_to_dict, format_assumptions


# ---------------------------------------------------------------------------
# An independent oracle: year-by-year amortization with the payment solved by
# bisection, so nothing here shares a line of code with the engine's closed
# forms. A ladder the engine and this loop agree on is a ladder.
# ---------------------------------------------------------------------------

def _solve_payment(balance: float, rate: float, n_years: int) -> float:
    """The level payment that drives `balance` to zero in `n_years`, by
    bisection on a year-by-year loop (no annuity formula)."""
    lo, hi = 0.0, balance * (1 + rate) ** n_years + balance
    for _ in range(300):
        mid = (lo + hi) / 2
        b = balance
        for _ in range(n_years):
            b = b * (1 + rate) - mid
        if b > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _iterative_ladder(loan, rates, renewal_years, amortization_years):
    """(start_year, rate, payment, opening_balance) per segment, iteratively."""
    balance, k, year = loan, 0, 0
    out = []
    while year < amortization_years:
        rate = rates[min(k, len(rates) - 1)]
        remaining = amortization_years - year
        payment = _solve_payment(balance, rate, remaining)
        out.append((year + 1, rate, payment, balance))
        for _ in range(min(renewal_years, remaining)):
            balance = balance * (1 + rate) - payment
        year += min(renewal_years, remaining)
        k += 1
    return out


def _oracle_mortgage_pv(loan, rates, renewal_years, amortization_years, dr, n_years):
    """PV of a ladder's payments, one year at a time — no annuity formula and
    no segment arithmetic, so the horizon's truncation is checked against a
    loop that simply stops paying."""
    ladder = _iterative_ladder(loan, rates, renewal_years, amortization_years)
    starts = [start for start, _, _, _ in ladder] + [amortization_years + 1]
    total = 0.0
    for index, (start, _rate, payment, _opening) in enumerate(ladder):
        for year in range(start, min(starts[index + 1] - 1, n_years) + 1):
            total += payment / (1 + dr) ** year
    return total


class TestRenewalScheduleOracle:
    """pv.renewal_schedule against the independent loop and its own invariants."""

    LOAN, T, A = 400_000.0, 5, 25
    RATES = [0.05, 0.065, 0.07, 0.055, 0.06]

    def test_matches_the_iterative_oracle(self):
        segments = renewal_schedule(self.LOAN, self.RATES, self.T, self.A)
        oracle = _iterative_ladder(self.LOAN, self.RATES, self.T, self.A)
        assert len(segments) == len(oracle) == 5
        for seg, (start, rate, payment, opening) in zip(segments, oracle):
            assert seg.start_year == start
            assert seg.rate == rate
            assert seg.payment == pytest.approx(payment, rel=1e-9)
            assert seg.opening_balance == pytest.approx(opening, rel=1e-9)

    def test_one_segment_reproduces_mortgage_payment_to_the_cent(self):
        """A renewal term at the amortization is one segment: today's payment."""
        segments = renewal_schedule(self.LOAN, [0.05], self.A, self.A)
        assert len(segments) == 1
        assert segments[0].payment == pytest.approx(
            mortgage_payment(self.LOAN, 0.05, self.A), abs=0.01)

    def test_segment_count_is_ceil_of_amortization_over_term(self):
        """Segments exist only while kT < A strictly (§4): a 25-year
        amortization on a 5-year term is five segments, not six."""
        assert len(renewal_schedule(self.LOAN, [0.05], 5, 25)) == 5
        assert len(renewal_schedule(self.LOAN, [0.05], 25, 25)) == 1
        assert len(renewal_schedule(self.LOAN, [0.05], 30, 25)) == 1
        assert len(renewal_schedule(self.LOAN, [0.05], 7, 25)) == 4   # 7,14,21 < 25

    def test_last_segment_is_truncated_at_the_amortization(self):
        segments = renewal_schedule(self.LOAN, [0.05], 7, 25)
        assert [s.start_year for s in segments] == [1, 8, 15, 22]
        assert [s.end_year for s in segments] == [7, 14, 21, 25]

    def test_balance_is_monotone_and_zero_at_the_amortization(self):
        """The last payment must land the balance on zero.

        The closing balance is walked to the year BEFORE the amortization and
        then stepped once by hand: `outstanding_balance` returns 0.0 for any
        year at or past its term, so asking it for the final year would assert
        its own early return and stay green for any payment whatsoever
        (2026-09-21).
        """
        segments = renewal_schedule(self.LOAN, self.RATES, self.T, self.A)
        openings = [s.opening_balance for s in segments]
        assert openings[0] == pytest.approx(self.LOAN, rel=1e-12)
        assert all(openings[i] >= openings[i + 1] - 1e-6 for i in range(len(openings) - 1))
        last = segments[-1]
        elapsed = last.start_year - 1
        penultimate = outstanding_balance(
            last.opening_balance, last.rate,
            self.A - elapsed, last.end_year - elapsed - 1, last.payment)
        assert penultimate > 0.0
        closing = penultimate * (1 + last.rate) - last.payment
        assert closing == pytest.approx(0.0, abs=1e-6)

    def test_principal_repaid_over_every_segment_sums_to_the_loan(self):
        """Every segment's principal, summed, is the loan.

        The year-by-year balances come from an independent loop rather than
        from the same `outstanding_balance` call that produced the segments:
        re-calling it telescopes to `opening - closing` by construction and
        holds for any payment at all (2026-09-21).
        """
        segments = renewal_schedule(self.LOAN, self.RATES, self.T, self.A)
        repaid = 0.0
        for seg in segments:
            balance = seg.opening_balance
            for _ in range(seg.years):
                repaid += seg.payment - balance * seg.rate
                balance = balance * (1 + seg.rate) - seg.payment
        assert repaid == pytest.approx(self.LOAN, rel=1e-9)

    def test_a_short_rate_list_carries_its_last_rate_forward(self):
        short = renewal_schedule(self.LOAN, [0.05, 0.07], self.T, self.A)
        full = renewal_schedule(self.LOAN, [0.05, 0.07, 0.07, 0.07, 0.07], self.T, self.A)
        assert [s.rate for s in short] == [0.05, 0.07, 0.07, 0.07, 0.07]
        assert [s.payment for s in short] == [s.payment for s in full]

    def test_every_renewal_at_the_contract_rate_holds_one_payment(self):
        """The equal-rate identity at the helper: five segments, one payment."""
        segments = renewal_schedule(self.LOAN, [0.05], self.T, self.A)
        today = mortgage_payment(self.LOAN, 0.05, self.A)
        for seg in segments:
            assert seg.payment == pytest.approx(today, rel=1e-9)

    def test_zero_rate_ladder_amortizes_straight_line(self):
        segments = renewal_schedule(300_000.0, [0.0], 5, 30)
        assert [s.payment for s in segments] == pytest.approx([10_000.0] * 6, rel=1e-9)

    @pytest.mark.parametrize("kwargs, fragment", [
        (dict(rates=[], renewal_years=5, amortization_years=25), "at least one rate"),
        (dict(rates=[0.05], renewal_years=0, amortization_years=25), "renewal_years"),
        (dict(rates=[0.05], renewal_years=-5, amortization_years=25), "renewal_years"),
        (dict(rates=[0.05], renewal_years=5, amortization_years=0), "amortization_years"),
        (dict(rates=[0.05, -0.01], renewal_years=5, amortization_years=25), "must be >= 0"),
    ])
    def test_refuses_rather_than_computing_silent_garbage(self, kwargs, fragment):
        with pytest.raises(ValueError, match=fragment):
            renewal_schedule(400_000.0, **kwargs)


# ---------------------------------------------------------------------------
# Equal-rate identity at the financing leg: the invariant that proves the
# ladder is the same arithmetic the engine already trusted.
# ---------------------------------------------------------------------------

class TestEqualRateIdentity:

    ARGS = dict(initial_value=500_000.0, down_payment=100_000.0, mortgage_rate=0.05,
                mortgage_term_years=25, all_cash=False, selling_cost_rate=0.05,
                value_N=700_000.0, dr=0.04, n_years=20)

    def test_financing_pv_reproduces_the_single_rate_leg(self):
        single = _financing_pv(**self.ARGS)
        ladder = _financing_pv(**self.ARGS, renewal_years=5, renewal_rates=[0.05])
        assert ladder[0] == pytest.approx(single[0], rel=1e-12)   # down payment
        assert ladder[1] == pytest.approx(single[1], rel=1e-9)    # mortgage_pv
        assert ladder[2] == pytest.approx(single[2], rel=1e-9)    # terminal equity

    def test_balance_at_the_horizon_matches(self):
        loan = 400_000.0
        payment = mortgage_payment(loan, 0.05, 25)
        single = outstanding_balance(loan, 0.05, 25, 20, payment)
        segments = renewal_schedule(loan, [0.05], 5, 25)
        holding = next(s for s in segments if s.start_year <= 20 <= s.end_year)
        ladder = outstanding_balance(
            holding.opening_balance, holding.rate,
            25 - (holding.start_year - 1), 20 - (holding.start_year - 1), holding.payment)
        assert ladder == pytest.approx(single, rel=1e-9)

    def test_a_higher_renewal_rate_costs_more(self):
        base = _financing_pv(**self.ARGS, renewal_years=5, renewal_rates=[0.05])
        worse = _financing_pv(**self.ARGS, renewal_years=5, renewal_rates=[0.08])
        assert worse[1] > base[1]           # the payments cost more in PV
        assert worse[2] > base[2]           # less equity credited back

    def test_refuses_half_a_ladder(self):
        with pytest.raises(ValueError, match="renewal"):
            _financing_pv(**self.ARGS, renewal_years=5)
        with pytest.raises(ValueError, match="renewal"):
            _financing_pv(**self.ARGS, renewal_rates=[0.06])

    @pytest.mark.parametrize("n_years", [1, 3, 5, 6, 12, 18, 22, 24, 25, 26, 30])
    def test_the_identity_holds_at_a_horizon_inside_a_segment(self, n_years):
        """A 20-year horizon on a 5-year term lands exactly on a segment
        boundary, so `min(end_year, n_years)` is never the binding term and the
        truncation arm goes unexercised. These horizons land inside a segment
        (2026-09-21)."""
        args = dict(self.ARGS, n_years=n_years)
        single = _financing_pv(**args)
        ladder = _financing_pv(**args, renewal_years=5, renewal_rates=[0.05])
        assert ladder[1] == pytest.approx(single[1], rel=1e-9)    # mortgage_pv
        assert ladder[2] == pytest.approx(single[2], rel=1e-9)    # terminal equity

    @pytest.mark.parametrize("n_years", [12, 18, 22])
    def test_an_unequal_ladder_truncates_where_the_oracle_does(self, n_years):
        """An unequal ladder cut mid-segment, against the year-by-year loop
        discounting one payment at a time."""
        args = dict(self.ARGS, n_years=n_years)
        rates = [0.07, 0.09, 0.06]
        loan = args["initial_value"] - args["down_payment"]
        _, mortgage_pv, _ = _financing_pv(**args, renewal_years=5, renewal_rates=rates)
        expected = _oracle_mortgage_pv(
            loan, [args["mortgage_rate"], *rates], 5,
            args["mortgage_term_years"], args["dr"], n_years)
        assert mortgage_pv == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# The two option-level keys through the loader.
# ---------------------------------------------------------------------------

def _base(**over):
    cfg = {
        "years": 20,
        "economic": {"mode": "nominal", "inflation_rate": 0.02},
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.02},
        "house": {
            "initial_value": 500_000, "down_payment": 100_000,
            "value_growth_rate": 0.02, "annual_maintenance_rate": 0.01,
            "mortgage_rate": 0.05, "mortgage_rate_compounding": "effective_annual",
            "mortgage_term_years": 25, "purchase_costs": 10_000,
            "other_recurring_costs": [
                {"name": "property_tax", "annual_amount": 4_000, "escalation_rate": 0.02}],
        },
    }
    cfg.update(over)
    return cfg


def _house(**over):
    cfg = _base()
    for key, value in over.items():
        if value is None:
            cfg["house"].pop(key, None)
        else:
            cfg["house"][key] = value
    return cfg


class TestLoader:

    def test_scalar_applies_to_every_renewal(self):
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.06))
        assert spec.house.mortgage_renewal_years == 5
        assert spec.house.mortgage_renewal_rates == [0.06]

    def test_a_list_is_kept_in_order(self):
        spec = load_config_dict(
            _house(mortgage_renewal_years=5, mortgage_renewal_rates=[0.06, 0.07, 0.055]))
        assert spec.house.mortgage_renewal_rates == [0.06, 0.07, 0.055]

    def test_renewal_rates_convert_by_the_same_compounding_as_mortgage_rate(self):
        """A renewal rate is a quoted contract rate of `mortgage_rate`'s class
        (spec §5): the same conversion, so the same typed figure means the same
        rate in both fields."""
        spec = load_config_dict(_house(
            mortgage_rate=0.0495, mortgage_rate_compounding="semi_annual",
            mortgage_renewal_years=5, mortgage_renewal_rates=0.0495))
        assert spec.house.mortgage_renewal_rates[0] == pytest.approx(spec.house.mortgage_rate)
        assert spec.house.mortgage_renewal_rates_quoted == [0.0495]

    def test_inflation_never_touches_a_renewal_rate(self):
        """Real mode deflates growth rates; a contract rate is used as entered."""
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.06)
        cfg["economic"] = {"mode": "real", "inflation_rate": 0.02}
        spec = load_config_dict(cfg)
        assert spec.house.mortgage_renewal_rates == [0.06]

    def test_the_condo_section_carries_the_same_keys(self):
        cfg = {
            "years": 20,
            "condo": {
                "initial_value": 400_000, "monthly_fee": 300, "down_payment": 80_000,
                "mortgage_rate": 0.05, "mortgage_rate_compounding": "effective_annual",
                "mortgage_term_years": 25, "purchase_costs": 8_000,
                "mortgage_renewal_years": 5, "mortgage_renewal_rates": [0.06, 0.07],
            },
        }
        spec = load_config_dict(cfg)
        assert spec.condo.mortgage_renewal_years == 5
        assert spec.condo.mortgage_renewal_rates == [0.06, 0.07]

    @pytest.mark.parametrize("over, fragment", [
        (dict(mortgage_renewal_years=5), "mortgage_renewal_rates"),
        (dict(mortgage_renewal_rates=0.06), "mortgage_renewal_years"),
        (dict(mortgage_renewal_years=0, mortgage_renewal_rates=0.06), "must be > 0"),
        (dict(mortgage_renewal_years=-5, mortgage_renewal_rates=0.06), "must be > 0"),
        (dict(mortgage_renewal_years=5, mortgage_renewal_rates=[]), "at least one rate"),
        (dict(mortgage_renewal_years=5, mortgage_renewal_rates=-0.01), "must be >= 0"),
        (dict(mortgage_renewal_years=5, mortgage_renewal_rates=[0.06, -0.01]), "must be >= 0"),
    ])
    def test_refusals(self, over, fragment):
        with pytest.raises(ConfigValidationError, match=fragment):
            load_config_dict(_house(**over))

    def test_more_rates_than_the_ladder_renews_is_refused(self):
        """A 25-year amortization on a 5-year term renews four times. A fifth
        rate reaches no payment, no balance and no PV; dropping it in silence
        is the honesty contract running backwards (2026-09-21)."""
        with pytest.raises(ConfigValidationError, match="priced nowhere"):
            load_config_dict(_house(
                mortgage_renewal_years=5,
                mortgage_renewal_rates=[0.03, 0.03, 0.03, 0.03, 0.12]))

    def test_the_surplus_refusal_names_both_counts_and_what_was_dropped(self):
        with pytest.raises(ConfigValidationError) as raised:
            load_config_dict(_house(
                mortgage_renewal_years=5,
                mortgage_renewal_rates=[0.06, 0.07, 0.055, 0.05, 0.12, 0.15]))
        message = str(raised.value)
        assert "6 rates" in message            # what the config typed
        assert "renews 4 times" in message     # what the ladder has
        assert "12.00%, 15.00%" in message     # the entries that would vanish
        assert "FIRST RENEWAL (year 6)" in message   # the off-by-one it invites

    def test_one_rate_per_renewal_is_accepted(self):
        spec = load_config_dict(_house(
            mortgage_renewal_years=5, mortgage_renewal_rates=[0.06, 0.07, 0.055, 0.05]))
        assert spec.house.mortgage_renewal_rates == [0.06, 0.07, 0.055, 0.05]

    def test_a_term_at_or_past_the_amortization_warns_rather_than_refusing(self):
        """Zero renewals is the inert case, which already has its own warning:
        refusing here would swallow the sentence that explains it."""
        spec = load_config_dict(_house(mortgage_renewal_years=25, mortgage_renewal_rates=0.08))
        assert spec.house.mortgage_renewal_years == 25

    def test_renewal_keys_without_a_mortgage_block_are_refused(self):
        cfg = _house(all_cash=True, down_payment=None, mortgage_rate=None,
                     mortgage_term_years=None, mortgage_rate_compounding=None,
                     mortgage_renewal_years=5, mortgage_renewal_rates=0.06)
        with pytest.raises(ConfigValidationError, match="renewal"):
            load_config_dict(cfg)

    def test_a_typo_still_gets_a_did_you_mean(self):
        with pytest.raises(ConfigValidationError, match="mortgage_renewal_rates"):
            load_config_dict(_house(mortgage_renewal_ratess=0.06))


# ---------------------------------------------------------------------------
# The four consumers.
# ---------------------------------------------------------------------------

class TestConsumers:

    def test_equal_rate_identity_end_to_end(self):
        """Every renewal at the contract rate: the same total, the same
        breakdown — through the loader, at the typed figure."""
        plain = compute_deterministic(load_config_dict(_base()))
        ladder = compute_deterministic(load_config_dict(
            _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.05)))
        assert ladder.house.total_pv == pytest.approx(plain.house.total_pv, rel=1e-9)
        for key, value in plain.house.breakdown.items():
            assert ladder.house.breakdown[key] == pytest.approx(value, rel=1e-9), key

    def test_a_higher_renewal_path_makes_the_house_cost_more(self):
        plain = compute_deterministic(load_config_dict(_base()))
        ladder = compute_deterministic(load_config_dict(
            _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08)))
        assert ladder.house.total_pv > plain.house.total_pv

    def test_the_affordability_ratio_steps_at_renewal(self):
        """Owner costs escalate every year, so the ratio always drifts up; a
        renewal puts a STEP in it that no other year has."""
        income = {"annual_income": 150_000, "income_growth_rate": 0.0,
                  "affordability_threshold": 0.32}
        flat_cfg = _base()
        flat_cfg["income"] = income
        ladder_cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09)
        ladder_cfg["income"] = income

        flat = compute_deterministic(load_config_dict(flat_cfg)).income_report.house_ratios
        ladder = compute_deterministic(load_config_dict(ladder_cfg)).income_report.house_ratios

        # Before the first renewal the two runs are the same mortgage.
        assert ladder[:5] == pytest.approx(flat[:5], rel=1e-12)
        # The flat run never steps; the ladder does, in the renewal year only.
        flat_steps = [flat[y] - flat[y - 1] for y in range(1, len(flat))]
        ladder_steps = [ladder[y] - ladder[y - 1] for y in range(1, len(ladder))]
        assert ladder_steps[4] > 5 * max(flat_steps)      # index 4 = year 5 → year 6
        assert ladder_steps[5] == pytest.approx(flat_steps[5], rel=1e-9)

    def test_principal_repaid_in_year_one_is_untouched_by_a_renewal(self):
        plain = compute_deterministic(load_config_dict(_base()))
        ladder = compute_deterministic(load_config_dict(
            _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09)))
        assert ladder.house.principal_year1 == pytest.approx(plain.house.principal_year1)

    def test_the_story_curve_reconciles_to_the_total(self):
        from hde.story_plots import _cumulative_cost_curves
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08))
        result = compute_deterministic(spec)
        curves = _cumulative_cost_curves(spec)
        assert curves["house"]["net"][-1] == pytest.approx(result.house.total_pv, rel=1e-9)

    def test_the_paid_curve_kinks_at_the_first_renewal(self):
        from hde.story_plots import _cumulative_cost_curves
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09))
        paid = _cumulative_cost_curves(spec)["house"]["paid"]
        steps = [paid[y] - paid[y - 1] for y in range(1, len(paid))]
        assert steps[5] > steps[4]     # year 6 costs more than year 5

    def test_the_act_two_sentence_names_the_first_step(self):
        """The curve kinks; the sentence says where and what it costs."""
        from hde.story_page import _act_sentences
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09))
        det = compute_deterministic(spec)
        race = next(s for stem, _, s in _act_sentences(spec, det, None, None)
                    if stem == "act2_the_race")
        assert "steps in year 6, the first renewal: +$" in race

        plain_spec = load_config_dict(_base())
        plain = next(s for stem, _, s in _act_sentences(
            plain_spec, compute_deterministic(plain_spec), None, None)
            if stem == "act2_the_race")
        assert "first renewal" not in plain

    def test_the_act_two_sentence_stays_silent_past_the_horizon(self):
        """A step outside the horizon is outside every PV in the run and off
        the end of the plot the sentence sits under (2026-09-21)."""
        from hde.story_page import _act_sentences
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09)
        cfg["years"] = 5
        spec = load_config_dict(cfg)
        race = next(s for stem, _, s in _act_sentences(
            spec, compute_deterministic(spec), None, None) if stem == "act2_the_race")
        assert "first renewal" not in race

    def test_the_act_two_sentence_names_every_laddered_option(self):
        """Both paid curves kink; naming one leaves the other kink unexplained,
        and the earlier one is named first (2026-09-21)."""
        from hde.story_page import _act_sentences
        cfg = _base()
        cfg["house"].update(mortgage_renewal_years=10, mortgage_renewal_rates=0.09)
        cfg["condo"] = {
            "initial_value": 400_000, "monthly_fee": 300, "down_payment": 80_000,
            "mortgage_rate": 0.05, "mortgage_rate_compounding": "effective_annual",
            "mortgage_term_years": 25, "purchase_costs": 8_000,
            "mortgage_renewal_years": 5, "mortgage_renewal_rates": 0.08,
        }
        spec = load_config_dict(cfg)
        race = next(s for stem, _, s in _act_sentences(
            spec, compute_deterministic(spec), None, None) if stem == "act2_the_race")
        assert "The condo payment steps in year 6, the first renewal: +$" in race
        assert "The house payment steps in year 11, its own first renewal: +$" in race
        assert race.index("condo payment steps") < race.index("house payment steps")

    def test_the_monte_carlo_financing_leg_uses_the_same_ladder(self):
        """The financing leg is deterministic on every path (spec §2): a run
        with every volatility off must land on the deterministic total."""
        from hde.monte_carlo import run_monte_carlo
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09)
        cfg["simulation"] = {"num_sims": 8, "random_seed": 7}
        spec = load_config_dict(cfg)
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        assert mc.house.summary.mean == pytest.approx(det.house.total_pv, rel=1e-6)


# ---------------------------------------------------------------------------
# Assumptions and warnings.
# ---------------------------------------------------------------------------

class TestReadBack:

    def test_the_renewals_line_names_the_term_the_segments_and_the_first_step(self):
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08))
        line = next(l for l in format_assumptions(spec) if l.startswith("house renewals:"))
        assert "5-year term, 4 renewals over the 25-year amortization" in line
        assert "year 1 5.000%" in line              # the rate the payment uses
        assert "year 6 8.000%" in line              # a row per segment
        assert "first renewal at year 6: +$" in line
        assert "%)" in line                         # the step in dollars AND percent
        assert "not a forecast" in line             # the user's own scenario

    def test_no_renewals_line_without_the_keys(self):
        spec = load_config_dict(_base())
        assert not any(l.startswith("house renewals:") for l in format_assumptions(spec))

    def test_the_read_back_block_carries_the_renewals_line(self):
        """The block is what an answer pastes: a laddered verdict that never
        names the renewal path names nothing that produced it."""
        from hde.serialization import read_back_lines
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08))
        block = read_back_lines(spec)
        assert any(l.startswith("house renewals:") for l in block)
        plain = read_back_lines(load_config_dict(_base()))
        assert not any("renewals:" in l for l in plain)

    def test_the_conventions_line_stops_claiming_one_level_payment(self):
        """Beside a renewals line quoting five payments, "level annual payment"
        alone would contradict the line above it."""
        plain = next(l for l in format_assumptions(load_config_dict(_base()))
                     if l.startswith("conventions:"))
        assert "level annual payment at an effective annual rate ·" in plain
        assert "renewal" not in plain
        ladder = next(l for l in format_assumptions(load_config_dict(
            _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08)))
            if l.startswith("conventions:"))
        assert "re-solved over the remaining amortization at each renewal" in ladder

    def test_the_json_assumptions_carry_the_schedule(self):
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08))
        payload = assumptions_to_dict(spec)
        ladder = payload["mortgage_renewals"]
        assert ladder[0]["option"] == "house"
        assert ladder[0]["renewal_years"] == 5
        assert len(ladder[0]["segments"]) == 5
        assert ladder[0]["segments"][0]["start_year"] == 1

    def test_absent_keys_leave_the_json_list_empty(self):
        assert assumptions_to_dict(load_config_dict(_base()))["mortgage_renewals"] == []

    def test_a_segment_past_the_horizon_is_marked_not_priced(self):
        """A 20-year horizon on a 25-year amortization never reaches the year-21
        segment, so the line must not print its payment as a fact of this run
        (2026-09-21)."""
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08))
        line = next(l for l in format_assumptions(spec) if l.startswith("house renewals:"))
        assert "3 of 4 inside the 20-year horizon" in line
        assert "year 21 8.000%" in line
        assert "(not priced — past the horizon)" in line

    def test_a_ladder_the_horizon_never_reaches_quotes_no_step(self):
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08)
        cfg["years"] = 5
        line = next(l for l in format_assumptions(load_config_dict(cfg))
                    if l.startswith("house renewals:"))
        assert "first renewal at year" not in line
        assert "no renewal falls inside the 5-year horizon" in line
        assert "prices mortgage_rate 5.000% throughout" in line

    def test_the_json_segments_carry_the_priced_flag(self):
        spec = load_config_dict(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08))
        ladder = assumptions_to_dict(spec)["mortgage_renewals"][0]
        assert ladder["renewals_priced"] == 3
        assert [s["priced"] for s in ladder["segments"]] == [True, True, True, True, False]

    def test_the_conventions_line_is_silent_when_no_renewal_is_priced(self):
        """One level payment is exactly what a horizon short of the first
        renewal holds, so the clause would contradict the line above it."""
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08)
        cfg["years"] = 5
        line = next(l for l in format_assumptions(load_config_dict(cfg))
                    if l.startswith("conventions:"))
        assert "re-solved over the remaining amortization" not in line

    def test_the_renewals_line_says_whose_scenario_the_rates_are(self):
        """The engine anchors no renewal rate, so the closing clause reads the
        source echo rather than asserting the user's own class (2026-09-21)."""
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08)
        cfg["sources"] = {"house.mortgage_renewal_rates": "assistant",
                          "house.mortgage_renewal_years": "assistant"}
        line = next(l for l in format_assumptions(load_config_dict(cfg))
                    if l.startswith("house renewals:"))
        assert "the ASSISTANT's stated scenario and not yours" in line
        assert "your stated scenario" not in line

        cfg["sources"] = {"house.mortgage_renewal_rates": "user",
                          "house.mortgage_renewal_years": "user"}
        line = next(l for l in format_assumptions(load_config_dict(cfg))
                    if l.startswith("house renewals:"))
        assert "your stated scenario, not a forecast" in line

    def test_an_undeclared_renewal_path_is_not_called_the_users_own(self):
        line = next(l for l in format_assumptions(load_config_dict(
            _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.08)))
            if l.startswith("house renewals:"))
        assert "your stated scenario" not in line
        assert "the read-back cannot tell whose figure it is" in line


class TestSourceEcho:
    """The `you said:` / `unattributed:` lines echo a renewal path in the units
    the config states it in — that surface exists to show the user their own
    figures back (2026-09-21)."""

    def test_a_scalar_renewal_rate_prints_as_a_percent(self):
        from hde.sources import format_source_value
        assert format_source_value("house.mortgage_renewal_rates", 0.065) == "6.5%"
        assert format_source_value("house.mortgage_renewal_rates", 0.08) == "8.0%"

    def test_a_rate_list_prints_its_rates_not_a_count(self):
        from hde.sources import format_source_value
        assert format_source_value(
            "house.mortgage_renewal_rates", [0.06, 0.07, 0.055]) == "6.0%, 7.0%, 5.5%"

    def test_a_list_of_records_still_prints_its_count(self):
        from hde.sources import format_source_value
        assert format_source_value(
            "house.events", [{"name": "roof"}, {"name": "furnace"}]) == "2 entries"
        assert format_source_value("house.other_recurring_costs", [{"name": "tax"}]) == "1 entry"

    def test_the_read_back_shows_the_path_the_verdict_turned_on(self):
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=[0.06, 0.07, 0.055])
        cfg["sources"] = {"house.mortgage_renewal_rates": "user",
                          "house.mortgage_renewal_years": "user"}
        line = next(l for l in format_assumptions(load_config_dict(cfg))
                    if "mortgage_renewal_rates=" in l)
        assert "mortgage_renewal_rates=6.0%, 7.0%, 5.5%" in line
        assert "entries" not in line


class TestSweepAndBreakEven:

    def _raw(self, **over):
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=[0.055, 0.065, 0.06])
        cfg.update(over)
        return cfg

    def test_a_grid_one_side_of_a_stated_path_still_warns(self):
        """`mortgage_renewal_rates` is the first sweepable key whose documented
        form is a list, and the guard returned None for any non-scalar base —
        silently absent on exactly the key the schema tells users to sweep
        (2026-09-21)."""
        from hde.sweep import one_sided_sweep_warning
        raw = self._raw()
        raw["sources"] = {"house.mortgage_renewal_rates": "assistant",
                          "house.mortgage_renewal_years": "assistant"}
        warning = one_sided_sweep_warning(
            raw, "house.mortgage_renewal_rates", [0.07, 0.08, 0.09])
        assert warning is not None
        assert "ABOVE" in warning and "5.50%, 6.50%, 6.00%" in warning   # as the grid prints

    def test_a_grid_straddling_the_stated_path_is_quiet(self):
        from hde.sweep import one_sided_sweep_warning
        raw = self._raw()
        raw["sources"] = {"house.mortgage_renewal_rates": "assistant",
                          "house.mortgage_renewal_years": "assistant"}
        assert one_sided_sweep_warning(
            raw, "house.mortgage_renewal_rates", [0.04, 0.06, 0.09]) is None

    def test_a_base_it_cannot_read_says_so_rather_than_going_quiet(self):
        from hde.sweep import one_sided_sweep_warning
        raw = self._raw()
        raw["house"]["mortgage_rate_compounding"] = "effective_annual"
        raw["sources"] = {"house.mortgage_rate_compounding": "assistant"}
        warning = one_sided_sweep_warning(
            raw, "house.mortgage_rate_compounding", [0.07, 0.08])
        assert warning is not None and "could not be evaluated" in warning

    def test_a_swept_path_is_named_as_flattened(self):
        from hde.sweep import flattened_path_note
        note = flattened_path_note(self._raw(), "house.mortgage_renewal_rates")
        assert note is not None
        assert "5.50%, 6.50%, 6.00%" in note   # as the grid prints
        assert "ONE figure applied at each renewal" in note
        assert "not a point on this grid" in note

    def test_a_scalar_base_gets_no_flattening_note(self):
        from hde.sweep import flattened_path_note
        raw = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.06)
        assert flattened_path_note(raw, "house.mortgage_renewal_rates") is None

    def test_the_bracket_refusal_names_the_real_reason(self):
        """The key IS in the YAML and IS a rate, so "only money and rate inputs
        get a default bracket" contradicted itself (2026-09-21)."""
        from hde.break_even import solve_break_even
        with pytest.raises(ValueError) as raised:
            solve_break_even(self._raw(), "house.mortgage_renewal_rates", None, None)
        message = str(raised.value)
        assert "only money and rate inputs" not in message
        assert "no range is anchored for mortgage_renewal_rates" in message
        assert "house.mortgage_renewal_rates=lo:hi" in message


class TestWarnings:

    def _warns(self, cfg):
        return coherence_warnings(load_config_dict(cfg))

    def test_a_mortgage_without_a_renewal_term_says_the_risk_is_not_modelled(self):
        warns = self._warns(_base())
        assert any("renewal risk" in w and "house" in w for w in warns)

    def test_the_warning_is_silent_once_the_term_is_stated(self):
        warns = self._warns(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.06))
        assert not any("renewal risk is not modelled" in w for w in warns)

    def test_an_all_cash_option_is_not_asked_for_a_renewal_term(self):
        cfg = _house(all_cash=True, down_payment=None, mortgage_rate=None,
                     mortgage_term_years=None, mortgage_rate_compounding=None)
        assert not any("renewal risk" in w for w in self._warns(cfg))

    def test_renewal_rates_below_the_contract_rate_name_the_bias(self):
        warns = self._warns(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.03))
        assert any("below" in w and "toward buying" in w for w in warns)

    def test_a_renewal_term_at_or_past_the_amortization_is_inert(self):
        warns = self._warns(_house(mortgage_renewal_years=25, mortgage_renewal_rates=0.08))
        assert any("never renews" in w or "inert" in w for w in warns)

    def _real_income_cfg(self, years):
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09)
        cfg["economic"] = {"mode": "real", "inflation_rate": 0.02}
        cfg["income"] = {"annual_income": 150_000, "income_growth_rate": 0.0,
                         "affordability_threshold": 0.32}
        cfg["years"] = years
        return cfg

    def test_the_affordability_clause_names_the_payment_the_run_holds(self):
        """The ratios quote the year-1 payment only where a renewal actually
        steps it. A horizon short of the first renewal holds ONE payment, like
        any single-rate mortgage, and calling it the year-1 payment implies a
        step this run never took (2026-09-21)."""
        stepping = next(w for w in self._warns(self._real_income_cfg(20))
                        if w.startswith("affordability: house ratios use"))
        assert "the year-1 payment" in stepping
        level = next(w for w in self._warns(self._real_income_cfg(5))
                     if w.startswith("affordability: house ratios use"))
        assert "the level payment" in level

    def test_a_short_amortization_is_not_told_its_rate_resets(self):
        """A 5-year amortization never reaches a renewal on a 5-year term, so
        "the rate resets at every renewal" names a reset it cannot have — and
        the remedy it prescribes would be refused as inert (2026-09-21)."""
        line = next(w for w in self._warns(_house(mortgage_term_years=5))
                    if "renewal risk is not modelled" in w)
        assert "the rate resets at every renewal" not in line
        assert "covers it with no renewal at all" in line
        assert "any shorter term resets the rate" in line
        assert "set mortgage_renewal_years (under 5)" in line

    def test_a_one_year_amortization_prescribes_no_term_it_would_refuse(self):
        """Under 1 is not a term the loader accepts, so the remedy must not
        name one (2026-09-21)."""
        line = next(w for w in self._warns(_house(mortgage_term_years=1))
                    if "renewal risk is not modelled" in w)
        assert "set mortgage_renewal_years" not in line
        assert "this mortgage cannot renew at all" in line

    def test_a_ladder_starting_past_the_horizon_says_it_prices_nothing(self):
        """A 5-year run on a 5-year term reaches its first renewal at year 6:
        the ladder is arithmetically inert, and declaring the keys must not buy
        silence from the not-modelled warning (2026-09-21)."""
        cfg = _house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09)
        cfg["years"] = 5
        line = next(w for w in self._warns(cfg) if "prices nothing in this run" in w)
        assert "first renewal falls at year 6" in line       # when it would land
        assert "past the 5-year horizon" in line             # what the run covers
        assert "still not modelled" in line

    def test_a_ladder_inside_the_horizon_is_not_called_inert(self):
        warns = self._warns(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09))
        assert not any("prices nothing in this run" in w for w in warns)

    def test_a_carry_forward_path_that_prices_cheaper_still_names_the_bias(self):
        """`[0.08, 0.03]` prices 8% at the first renewal and 3% at every later
        one, so the mortgage costs less than its contract rate overall while
        NOT every typed entry sits below it. Reading the typed list stayed
        silent here; the engine now measures what it priced (2026-09-21)."""
        cfg = _house(mortgage_rate=0.06, mortgage_renewal_years=5,
                     mortgage_renewal_rates=[0.08, 0.03])
        cfg["years"] = 25
        line = next(w for w in self._warns(cfg) if "below its contract rate" in w)
        assert "toward buying" in line
        assert "25-year horizon" in line

    def test_a_first_entry_repeating_the_contract_rate_names_both_readings(self):
        """One rate per RENEWAL against one rate per BLOCK.

        Counted over the amortization the block reading always types exactly
        one figure too many and the loader refuses it. Counted over a HORIZON
        that is a whole number of terms the counts coincide, nothing refuses,
        and the whole path is priced one term later than it was meant. The tell
        is entry 1 repeating mortgage_rate, so the first renewal steps by
        nothing (2026-09-21)."""
        cfg = _house(mortgage_renewal_years=5,
                     mortgage_renewal_rates=[0.05, 0.06, 0.07, 0.055])
        line = next(w for w in self._warns(cfg) if "ONE RATE PER RENEWAL" in w)
        assert "opens at 5.00%, the same figure as mortgage_rate" in line
        assert "prices year 6" in line              # where the engine puts it
        assert "put that figure on year 1" in line  # where the other reading does
        assert "cannot tell them apart" in line     # disclosed, never resolved

    def test_a_renewal_path_that_differs_from_the_contract_rate_is_quiet(self):
        """The warning must not fire on every ladder — only where the two
        readings are genuinely indistinguishable."""
        warns = self._warns(_house(mortgage_renewal_years=5,
                                   mortgage_renewal_rates=[0.06, 0.07, 0.055, 0.05]))
        assert not any("ONE RATE PER RENEWAL" in w for w in warns)
        assert not any("ONE RATE PER RENEWAL" in w
                       for w in self._warns(_base()))

    def test_holding_the_contract_rate_through_the_first_renewal_is_not_refused(self):
        """"My rate holds through the first renewal, then rises" is a real
        thing to model and a correct input: it is disclosed, never refused, and
        the run prices exactly what was typed."""
        cfg = _house(mortgage_renewal_years=5,
                     mortgage_renewal_rates=[0.05, 0.08, 0.09, 0.09])
        spec = load_config_dict(cfg)            # loads, no ConfigValidationError
        from hde.deterministic import renewal_segments_for
        assert [s.rate for s in renewal_segments_for(spec.house)] == [
            0.05, 0.05, 0.08, 0.09, 0.09]

    def test_a_stressed_renewal_path_gets_no_bias_warning(self):
        warns = self._warns(_house(mortgage_renewal_years=5, mortgage_renewal_rates=0.09))
        assert not any("below its contract rate" in w for w in warns)


# ---------------------------------------------------------------------------
# ABSENCE: with no renewal key, nothing moves.
# ---------------------------------------------------------------------------

class TestAbsenceInvariant:

    # Every total and breakdown value `_base()` produced on the engine BEFORE
    # the renewal ladder landed, captured by running that engine and printing
    # `repr()` of each float, so the literals round-trip exactly. Comparing the
    # new engine against a second run of itself would only prove determinism —
    # it would stay green if this change had moved every no-renewal number
    # (2026-09-21). These are the pre-change figures, not a target: a change
    # that moves one has broken the absence invariant, and the fix is the
    # change, never the literal.
    PRE_CHANGE = {
        "house": (
            377124.15407597553,
            {
                "purchase_costs_pv": 10000.0,
                "maintenance_pv": 72928.79833556621,
                "events_pv": 0.0,
                "other_pv": 59509.899441822046,
                "downpayment_pv": 100000.0,
                "mortgage_pv": 351897.3157858274,
                "terminal_equity_pv": -217211.8594872402,
                "hbp_repayment_pv": 0.0,
            },
        ),
        "rent": (
            357059.3966509325,
            {
                "rent_pv": 357059.3966509325,
                "events_pv": 0.0,
                "other_pv": 0.0,
                "invested_capital_pv": 0.0,
                "invested_dp_benefit_pv": -0.0,
            },
        ),
    }

    def test_every_total_and_breakdown_is_bit_identical(self):
        """Not approx: the no-renewal path must run the same lines it always
        did, so every float is the same float as the PRE-CHANGE engine's."""
        result = compute_deterministic(load_config_dict(copy.deepcopy(_base())))
        for option, (total, breakdown) in self.PRE_CHANGE.items():
            got = getattr(result, option)
            assert got.total_pv == total, option
            assert got.breakdown == breakdown, option

    def test_the_financing_leg_takes_the_original_code_path(self):
        """`_financing_pv` with no ladder returns exactly the single-rate
        arithmetic, to the last bit — the ladder is a branch, not a rewrite."""
        loan = 400_000.0
        payment = mortgage_payment(loan, 0.05, 25)
        expected_mortgage_pv = pv_annuity(payment, 0.04, 20)
        expected_balance = outstanding_balance(loan, 0.05, 25, 20, payment)
        _, mortgage_pv, terminal = _financing_pv(
            500_000.0, 100_000.0, 0.05, 25, False, 0.05, 700_000.0, 0.04, 20)
        assert mortgage_pv == expected_mortgage_pv
        equity = 700_000.0 * 0.95 - expected_balance
        assert terminal == -pv_single(equity, 0.04, 20)
