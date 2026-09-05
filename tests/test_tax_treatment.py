"""The tax treatment of the two sides' money (docs/specs/2026-09-05-tax-treatment.md).

Every figure here is hand-checked against the formulas in the note (§4) and
the merged registry: the renter's taxable share earns the after-tax return, the
sheltered shares are untouched, the FHSA share is haircut at the horizon for the
renter, the refunds enter both sides, and the HBP's own cost is its repayment
schedule — zero when the return equals the discount rate. Without a `tax:`
block nothing moves except one warning.
"""

import copy
import math

import pytest

from hde import tax_treatment as tt
from hde.anchors import ANCHORS
from hde.config import ConfigValidationError, coherence_warnings, load_config_dict
from hde.deterministic import compute_deterministic
from hde.input_schema import input_schema
from hde.models import CONDO_BREAKDOWN_KEYS, HOUSE_BREAKDOWN_KEYS
from hde.monte_carlo import run_monte_carlo
from hde.rates import deflate, is_convertible
from hde.reporting import format_text_report
from hde.serialization import assumptions_to_dict, format_assumptions, rates_line, read_back_lines
from hde.tax_rates import marginal_rate, marginal_rate_breakdown

PI = 0.021
R_QUOTED = 0.051
N = 10

BASE = {
    "years": N,
    "province": "QC",
    "economic": {"mode": "nominal", "inflation_rate": PI},
    "condo": {
        "initial_value": 450_000, "monthly_fee": 380, "cash_available": 60_000,
        "mortgage_rate": 0.0455, "mortgage_term_years": 25, "purchase_costs": 6_000,
        "first_time_buyer": True,
    },
    "rent": {"monthly_rent": 1_850, "invested_down_payment": 60_000,
             "investment_return_rate": R_QUOTED},
    "income": {"annual_income": 100_000},
    "simulation": {"num_sims": 150, "random_seed": 7},
}
SPLIT = {"tfsa": 25_000, "rrsp": 20_000, "fhsa": 0, "taxable": 15_000}


def cfg(tax=None, **top):
    doc = copy.deepcopy(BASE)
    doc.update(copy.deepcopy(top))
    if tax is not None:
        doc["tax"] = copy.deepcopy(tax)
    return doc


def real_mode(doc):
    doc["economic"] = {"mode": "real", "inflation_rate": PI}
    return doc


def r_eff(spec):
    """The renter's return as the engines hold it, in the run's own terms."""
    r = spec.rent.investment_return_rate
    if spec.economic.mode == "nominal":
        return (1 + r) * (1 + spec.economic.inflation_rate) - 1
    return r


def hand_terminal(spec, tfsa, rrsp, fhsa, taxable, refunds=0.0, t_ret=None):
    """V_N of §4.3 by hand: sheltered at r, the FHSA share haircut, the taxable
    share (plus the refunds) at the after-tax factor."""
    m = spec.tax.marginal_rate
    iota = spec.tax.inclusion_rate
    r = r_eff(spec)
    pi = spec.economic.inflation_rate
    if spec.economic.mode == "real":
        g_nom = (1 + r) * (1 + pi)
        a = (1 + (g_nom - 1) * (1 - m * iota)) / (1 + pi)
    else:
        a = 1 + r * (1 - m * iota)
    t_ret = spec.tax.retirement_marginal_rate if t_ret is None else t_ret
    return ((tfsa + rrsp) * (1 + r) ** N + fhsa * (1 + r) ** N * (1 - t_ret)
            + (taxable + refunds) * a ** N)


# ---------------------------------------------------------------------------
# The drag
# ---------------------------------------------------------------------------

class TestAfterTaxFactor:
    def test_nominal_mode_taxes_the_nominal_return(self):
        assert tt.after_tax_factor(1.051, "nominal", PI, 0.36, 0.5) == pytest.approx(1 + 0.051 * (1 - 0.18))

    def test_real_mode_composes_to_nominal_taxes_and_deflates(self):
        r_real = deflate(R_QUOTED, PI)
        g_nom = (1 + r_real) * (1 + PI)
        expected = (1 + (g_nom - 1) * (1 - 0.36 * 0.5)) / (1 + PI)
        assert tt.after_tax_factor(1 + r_real, "real", PI, 0.36, 0.5) == pytest.approx(expected)

    def test_interest_treatment_taxes_every_dollar(self):
        assert tt.after_tax_factor(1.05, "nominal", PI, 0.40, 1.0) == pytest.approx(1.03)

    def test_a_loss_year_is_a_negative_drag(self):
        assert tt.after_tax_factor(0.90, "nominal", PI, 0.40, 0.5) == pytest.approx(1 - 0.10 * 0.8)


class TestMarginalRate:
    @pytest.mark.parametrize("province, income", [("QC", 100_000), ("ON", 100_000)])
    def test_resolved_from_income_and_province_through_the_registry(self, province, income):
        spec = load_config_dict(cfg({"renter_capital": SPLIT}, province=province))
        assert spec.tax.marginal_rate == pytest.approx(marginal_rate(income, province))
        assert spec.tax.marginal_rate_source == "resolved"

    def test_the_two_hand_checked_rates(self):
        assert marginal_rate(100_000, "qc") == pytest.approx(0.205 * 0.835 + 0.19)
        assert marginal_rate(100_000, "on") == pytest.approx(0.205 + 0.0915 * 1.20)
        assert load_config_dict(cfg({"renter_capital": SPLIT})).tax.marginal_rate == pytest.approx(0.361175)
        assert load_config_dict(cfg({"renter_capital": SPLIT}, province="ON")).tax.marginal_rate == pytest.approx(0.3148)

    def test_the_line_names_the_components(self):
        lines = format_assumptions(load_config_dict(cfg({"renter_capital": SPLIT})))
        tax = next(line for line in lines if line.startswith("tax:"))
        assert "marginal rate 36.12% resolved from income $100,000 in QC" in tax
        assert "federal 20.5% × (1 − 16.5% Québec abatement) + QC 19%" in tax
        assert "[tax.federal.*, tax.qc.* 2026]" in tax
        on = next(line for line in format_assumptions(load_config_dict(cfg({"renter_capital": SPLIT}, province="ON")))
                  if line.startswith("tax:"))
        assert "federal 20.5% + ON 9.15% × (1 + 20% surtax) [tax.federal.*, tax.on.* 2026]" in on

    def test_typed_rate_is_used_as_is_and_never_converted(self):
        spec = load_config_dict(cfg({"renter_capital": SPLIT, "marginal_rate": 0.30}))
        assert spec.tax.marginal_rate == 0.30
        assert spec.tax.marginal_rate_source == "typed"
        assert "tax" not in rates_line(spec)
        assert not is_convertible("tax.marginal_rate")
        assert not is_convertible("tax.retirement_marginal_rate")
        tax = next(line for line in format_assumptions(spec) if line.startswith("tax:"))
        assert "marginal rate 30.00% as typed" in tax

    def test_refused_when_neither_typed_nor_resolvable(self):
        doc = cfg({"renter_capital": SPLIT})
        del doc["income"]
        with pytest.raises(ConfigValidationError, match="marginal_rate"):
            load_config_dict(doc)
        with pytest.raises(ConfigValidationError, match="QC or ON"):
            load_config_dict(cfg({"renter_capital": SPLIT}, province="BC"))

    def test_refused_outside_the_unit_interval(self):
        with pytest.raises(ConfigValidationError, match=r"fraction of income"):
            load_config_dict(cfg({"renter_capital": SPLIT, "marginal_rate": 36.12}))


# ---------------------------------------------------------------------------
# Fold 1: the renter's capital under tax
# ---------------------------------------------------------------------------

class TestRenterCapital:
    def test_shares_must_sum_to_the_renters_capital(self):
        bad = {**SPLIT, "taxable": 13_000}
        with pytest.raises(ConfigValidationError) as exc:
            load_config_dict(cfg({"renter_capital": bad}))
        assert "$58,000" in str(exc.value) and "$60,000" in str(exc.value)

    def test_required_when_the_renter_holds_capital(self):
        with pytest.raises(ConfigValidationError, match="renter_capital"):
            load_config_dict(cfg({"marginal_rate": 0.3}))

    def test_refused_without_a_rent_block(self):
        doc = cfg({"renter_capital": SPLIT, "marginal_rate": 0.3})
        del doc["rent"]
        with pytest.raises(ConfigValidationError, match="rent:"):
            load_config_dict(doc)

    def test_unknown_treatment_is_refused(self):
        with pytest.raises(ConfigValidationError, match="capital_gains | interest"):
            load_config_dict(cfg({"renter_capital": SPLIT, "taxable_return_treatment": "dividends"}))

    @pytest.mark.parametrize("mode", ["nominal", "real"])
    def test_hand_checked_terminal_value(self, mode):
        doc = cfg({"renter_capital": SPLIT})
        if mode == "real":
            real_mode(doc)
        spec = load_config_dict(doc)
        det = compute_deterministic(spec)
        dr = spec.simulation.discount_rate
        v_n = hand_terminal(spec, **SPLIT)
        assert det.rent.breakdown["invested_capital_pv"] == pytest.approx(60_000)
        assert det.rent.breakdown["invested_dp_benefit_pv"] == pytest.approx(-v_n / (1 + dr) ** N)
        # the drag is the taxable share's shortfall against the untaxed path
        r = r_eff(spec)
        untaxed = 60_000 * (1 + r) ** N
        assert untaxed - v_n > 0

    def test_interest_treatment_drags_harder_than_capital_gains(self):
        gains = compute_deterministic(load_config_dict(cfg({"renter_capital": SPLIT}))).rent.total_pv
        interest = compute_deterministic(load_config_dict(
            cfg({"renter_capital": SPLIT, "taxable_return_treatment": "interest"}))).rent.total_pv
        assert interest > gains

    def test_a_fully_sheltered_renter_is_untouched(self):
        sheltered = {"tfsa": 40_000, "rrsp": 20_000, "fhsa": 0, "taxable": 0}
        with_tax = compute_deterministic(load_config_dict(cfg({"renter_capital": sheltered}))).rent
        without = compute_deterministic(load_config_dict(cfg())).rent
        assert with_tax.total_pv == pytest.approx(without.total_pv)

    @pytest.mark.parametrize("mode", ["nominal", "real"])
    def test_zero_vol_monte_carlo_equals_deterministic(self, mode):
        doc = cfg({"renter_capital": SPLIT})
        if mode == "real":
            real_mode(doc)
        spec = load_config_dict(doc)
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        assert mc.rent.summary.mean == pytest.approx(det.rent.total_pv)
        assert mc.condo.summary.mean == pytest.approx(det.condo.total_pv)

    def test_shocked_years_compound_the_after_tax_factor_on_the_taxable_share(self):
        doc = cfg({"renter_capital": SPLIT}, simulation={"num_sims": 40, "random_seed": 3,
                                                          "investment_return_vol": 0.10})
        spec = load_config_dict(doc)
        mc = run_monte_carlo(spec)
        # a taxed renter never ends above the untaxed renter on the same draws
        untaxed = run_monte_carlo(load_config_dict(cfg(simulation=doc["simulation"])))
        assert mc.rent.summary.mean > untaxed.rent.summary.mean

    def test_the_tax_line_carries_the_split_the_drag_and_the_exemption(self):
        spec = load_config_dict(cfg({"renter_capital": SPLIT}))
        tax = next(line for line in format_assumptions(spec) if line.startswith("tax:"))
        assert ("renter capital $60,000 = sheltered $45,000 (TFSA $25,000 + RRSP $20,000 + FHSA $0) "
                "+ taxable $15,000 (+ FHSA refunds $0)") in tax
        assert "taxable share: 5.10% × (1 − 36.12% × 50% inclusion, capital gains — default) = 4.18% after tax [tax.capital_gains_inclusion_rate]" in tax
        assert "charged to rent" in tax
        assert "owner: principal-residence exemption — no tax on the equity gain at sale [tax.principal_residence_exempt_fraction]" in tax
        assert tax in read_back_lines(spec)

    def test_the_capital_spread_warning_quotes_the_blended_rate(self):
        spec = load_config_dict(cfg({"renter_capital": SPLIT}))
        warning = next(w for w in coherence_warnings(spec) if w.startswith("rent: invested capital"))
        assert "after tax on the taxable share: blended" in warning
        assert "untaxed" not in warning
        # with an FHSA share the blended figure carries the rollover haircut, and says so
        split = {"tfsa": 14_000, "rrsp": 20_000, "taxable": 15_000}
        spec = load_config_dict(cfg({"renter_capital": split, "fhsa": FHSA}))
        warning = next(w for w in coherence_warnings(spec) if w.startswith("rent: invested capital"))
        assert "after tax on the taxable share and the FHSA rollover: blended" in warning

    def test_real_mode_with_an_inert_deflator_warns(self):
        doc = real_mode(cfg({"renter_capital": SPLIT}))
        doc["rates"] = "real"
        doc["economic"] = {"mode": "real"}
        warnings = coherence_warnings(load_config_dict(doc))
        assert any("gains are taxed in nominal terms" in w and "toward renting" in w for w in warnings)

    def test_tfsa_share_above_the_cumulative_room_is_a_check_not_a_refusal(self):
        big = {"tfsa": 120_000, "rrsp": 0, "fhsa": 0, "taxable": 0}
        doc = cfg({"renter_capital": big}, rent={"monthly_rent": 1_850, "invested_down_payment": 120_000,
                                                 "investment_return_rate": R_QUOTED})
        warnings = coherence_warnings(load_config_dict(doc))
        room = ANCHORS["tfsa.cumulative_room_since_2009"].value
        assert any(f"${room:,.0f}" in w and "tfsa.cumulative_room_since_2009" in w for w in warnings)

    def test_sources_classes_reach_the_new_leaves(self):
        doc = cfg({"renter_capital": SPLIT})
        doc["sources"] = {"tax.renter_capital.tfsa": "user", "tax.renter_capital.taxable": "assistant"}
        spec = load_config_dict(doc)
        lines = format_assumptions(spec)
        assert any(line.startswith("user-stated:") and "tax.renter_capital.tfsa=$25,000" in line for line in lines)
        assert any(line.startswith("assistant-typed:") and "tax.renter_capital.taxable=$15,000" in line for line in lines)


class TestNoBlock:
    def test_the_engine_warns_when_the_renter_holds_untaxed_capital(self):
        warnings = coherence_warnings(load_config_dict(cfg()))
        assert ("rent: invested capital $60,000 earns 5.1% untaxed — no tax: block, so tax on the "
                "taxable share is not modelled (toward renting); state where the savings sit "
                "(tax.renter_capital)") in warnings

    def test_silent_without_renter_capital(self):
        doc = cfg(rent={"monthly_rent": 1_850})
        assert not any("no tax: block" in w for w in coherence_warnings(load_config_dict(doc)))

    def test_silent_with_a_block(self):
        warnings = coherence_warnings(load_config_dict(cfg({"renter_capital": SPLIT})))
        assert not any("no tax: block" in w for w in warnings)

    def test_nothing_else_moves(self):
        spec = load_config_dict(cfg())
        det = compute_deterministic(spec)
        r = r_eff(spec)
        dr = spec.simulation.discount_rate
        assert det.rent.breakdown["invested_dp_benefit_pv"] == pytest.approx(-60_000 * (1 + r) ** N / (1 + dr) ** N)
        assert det.condo.breakdown["hbp_repayment_pv"] == 0.0
        assert "hbp_repayment_pv" in CONDO_BREAKDOWN_KEYS and "hbp_repayment_pv" in HOUSE_BREAKDOWN_KEYS
        assert not any(line.startswith("tax:") for line in format_assumptions(spec))
        report = format_text_report(det, None, spec.simulation, spec.economic, spec=spec)
        assert "hbp_repayment_pv" not in report


# ---------------------------------------------------------------------------
# Fold 2: the first home — the FHSA and the HBP
# ---------------------------------------------------------------------------

FHSA_SPLIT = {"tfsa": 14_000, "rrsp": 20_000, "taxable": 15_000}  # + derived FHSA $11,000 = $60,000
FHSA = {"balance": 11_000, "annual_contribution": 0, "years_until_purchase": 0}


class TestFhsa:
    def test_saving_years_room_lifetime_and_refunds(self):
        # two saving years at $8,000: both fit the annual limit; F_0 = balance + $16,000
        plan = tt.fhsa_plan(balance=15_000, annual_contribution=8_000, years_until_purchase=2,
                            marginal_rate=0.361175)
        assert plan.contributions == (8_000.0, 8_000.0)
        assert plan.refunds == pytest.approx(0.361175 * 16_000)
        assert plan.share_at_year0 == 31_000
        assert plan.lifetime_remaining == 40_000 - 31_000

    def test_the_lifetime_limit_caps_the_second_year(self):
        plan = tt.fhsa_plan(balance=30_000, annual_contribution=20_000, years_until_purchase=2,
                            marginal_rate=0.3)
        assert plan.contributions == (8_000.0, 2_000.0)
        assert plan.lifetime_remaining == 0

    def test_carry_forward_accrues_from_an_unused_year(self):
        plan = tt.fhsa_plan(balance=0, annual_contribution=[0, 16_000, 16_000], years_until_purchase=3,
                            marginal_rate=0.3)
        # year 2 has $8,000 + $8,000 carried forward; year 3 has the annual limit alone
        assert plan.contributions == (0.0, 16_000.0, 8_000.0)

    def test_the_share_is_derived_and_a_stated_one_is_refused(self):
        spec = load_config_dict(cfg({"renter_capital": FHSA_SPLIT, "fhsa": FHSA}))
        assert spec.tax.renter_capital.fhsa == 11_000
        assert spec.tax.renter_capital.fhsa_derived
        with pytest.raises(ConfigValidationError, match="derived"):
            load_config_dict(cfg({"renter_capital": {**FHSA_SPLIT, "fhsa": 11_000}, "fhsa": FHSA}))

    def test_needs_a_first_time_buyer(self):
        doc = cfg({"renter_capital": FHSA_SPLIT, "fhsa": FHSA})
        doc["condo"]["first_time_buyer"] = False
        with pytest.raises(ConfigValidationError, match="first_time_buyer: true"):
            load_config_dict(doc)

    def test_needs_a_rent_block(self):
        doc = cfg({"fhsa": FHSA, "marginal_rate": 0.3})
        del doc["rent"]
        with pytest.raises(ConfigValidationError, match="rent:"):
            load_config_dict(doc)

    def test_refused_on_an_all_cash_purchase(self):
        doc = cfg({"renter_capital": FHSA_SPLIT, "fhsa": FHSA})
        doc["condo"] = {"initial_value": 450_000, "monthly_fee": 380, "all_cash": True, "first_time_buyer": True}
        with pytest.raises(ConfigValidationError, match="all_cash"):
            load_config_dict(doc)

    def test_refunds_enter_both_sides_and_the_haircut_hits_the_renter(self):
        saving = {"balance": 15_000, "annual_contribution": 8_000, "years_until_purchase": 2}
        split = {"tfsa": 14_000, "rrsp": 0, "taxable": 15_000}  # + derived $31,000 = $60,000
        spec = load_config_dict(cfg({"renter_capital": split, "fhsa": saving}))
        m = spec.tax.marginal_rate
        refunds = m * 16_000
        assert spec.tax.fhsa.refunds == pytest.approx(refunds)
        # buyer: the refunds join the down payment
        assert spec.condo.down_payment == pytest.approx(60_000 + refunds - 6_000)
        # renter: the refunds join the taxable share and the FHSA share is haircut at N
        det = compute_deterministic(spec)
        dr = spec.simulation.discount_rate
        v_n = hand_terminal(spec, tfsa=14_000, rrsp=0, fhsa=31_000, taxable=15_000, refunds=refunds)
        assert det.rent.breakdown["invested_capital_pv"] == pytest.approx(60_000 + refunds)
        assert det.rent.breakdown["invested_dp_benefit_pv"] == pytest.approx(-v_n / (1 + dr) ** N)
        assert spec.tax.retirement_marginal_rate == m and spec.tax.retirement_rate_source == "default"

    def test_a_typed_retirement_rate_sets_the_haircut(self):
        split = {"tfsa": 14_000, "rrsp": 20_000, "taxable": 15_000}
        spec = load_config_dict(cfg({"renter_capital": split, "fhsa": FHSA, "retirement_marginal_rate": 0.25}))
        det = compute_deterministic(spec)
        dr = spec.simulation.discount_rate
        v_n = hand_terminal(spec, tfsa=14_000, rrsp=20_000, fhsa=11_000, taxable=15_000, t_ret=0.25)
        assert det.rent.breakdown["invested_dp_benefit_pv"] == pytest.approx(-v_n / (1 + dr) ** N)

    def test_the_clause_and_the_haircut_are_printed(self):
        saving = {"balance": 15_000, "annual_contribution": 8_000, "years_until_purchase": 2}
        split = {"tfsa": 14_000, "rrsp": 0, "taxable": 15_000}
        spec = load_config_dict(cfg({"renter_capital": split, "fhsa": saving}))
        lines = format_assumptions(spec)
        financing = next(line for line in lines if line.startswith("condo financing:"))
        assert "cash available $60,000 + FHSA refunds $5,779 − purchase_costs $6,000 = down payment $59,779" in financing
        assert ("fhsa: balance $15,000 + $16,000 contributed over 2 saving years (room $8,000/yr + "
                "carry-forward ≤ $8,000, lifetime $40,000, $9,000 remaining [fhsa.annual_limit, "
                "fhsa.carry_forward_max, fhsa.lifetime_limit]) → refunds $5,779 at 36.12%, added to "
                "both sides' capital") in financing
        tax = next(line for line in lines if line.startswith("tax:"))
        assert "FHSA share $31,000 rolls to an RRSP for the renter (within 15 years of opening [fhsa.max_years_open])" in tax
        assert "haircut 36.12% retirement marginal rate (= current, default) on $50,979 at year 10 = $18,412" in tax
        assert "[tax.retirement_marginal_rate]" in tax

    def test_no_saving_years_says_so(self):
        spec = load_config_dict(cfg({"renter_capital": FHSA_SPLIT, "fhsa": FHSA}))
        financing = next(line for line in format_assumptions(spec) if line.startswith("condo financing:"))
        assert "fhsa: balance $11,000, no saving years — no refunds to add" in financing
        assert spec.condo.down_payment == pytest.approx(60_000 - 6_000)


class TestHbp:
    H = 20_000

    def test_within_the_limit_and_the_rrsp_share(self):
        with pytest.raises(ConfigValidationError, match=r"\$60,000"):
            load_config_dict(cfg({"renter_capital": SPLIT, "hbp_withdrawal": 70_000}))
        with pytest.raises(ConfigValidationError, match="RRSP share"):
            load_config_dict(cfg({"renter_capital": SPLIT, "hbp_withdrawal": 25_000}))
        doc = cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H})
        doc["condo"]["first_time_buyer"] = False
        with pytest.raises(ConfigValidationError, match="first_time_buyer: true"):
            load_config_dict(doc)

    def test_the_withdrawal_joins_the_down_payment(self):
        spec = load_config_dict(cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H}))
        assert spec.condo.down_payment == pytest.approx(60_000 + self.H - 6_000)
        assert spec.condo.cash_available == 60_000  # as typed

    def test_the_insurance_tier_is_chosen_on_the_augmented_pile(self):
        doc = cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H})
        doc["condo"]["mortgage_insurance"] = "auto"
        spec = load_config_dict(doc)
        record = spec.condo.mortgage_insurance
        assert record is not None and record.required
        assert spec.condo.down_payment + spec.condo.purchase_costs + record.premium_tax == pytest.approx(60_000 + self.H)

    @pytest.mark.parametrize("mode", ["nominal", "real"])
    def test_hand_checked_repayment_leg(self, mode):
        doc = cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H})
        if mode == "real":
            real_mode(doc)
        spec = load_config_dict(doc)
        det = compute_deterministic(spec)
        r, dr, pi = r_eff(spec), spec.simulation.discount_rate, spec.economic.inflation_rate
        years, grace = int(ANCHORS["hbp.repayment_years"].value), int(ANCHORS["hbp.repayment_grace_years"].value)
        tranche = self.H / years
        taus = [min(grace + j - 1, N) for j in range(1, years + 1)]
        outs = [tranche / (1 + pi) ** t if mode == "real" else tranche for t in taus]
        outlays_pv = sum(o / (1 + dr) ** t for o, t in zip(outs, taus))
        rebuilt = sum(o * (1 + r) ** (N - t) for o, t in zip(outs, taus))
        expected = outlays_pv - rebuilt / (1 + dr) ** N
        assert det.condo.breakdown["hbp_repayment_pv"] == pytest.approx(expected)
        assert det.condo.total_pv == pytest.approx(
            sum(v for k, v in det.condo.breakdown.items()))

    def test_zero_when_the_return_equals_the_discount_rate(self):
        doc = cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H})
        dr_nominal = (1.03) * (1 + PI) - 1  # the anchored real default composed
        doc["rent"]["investment_return_rate"] = dr_nominal  # as quoted = used as typed in nominal mode
        det = compute_deterministic(load_config_dict(doc))
        assert det.condo.breakdown["hbp_repayment_pv"] == pytest.approx(0.0, abs=1e-6)

    def test_zero_vol_monte_carlo_carries_the_same_constant(self):
        spec = load_config_dict(cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H}))
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        assert mc.condo.summary.mean == pytest.approx(det.condo.total_pv)

    def test_the_hbp_line(self):
        spec = load_config_dict(cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H}))
        lines = format_assumptions(spec)
        hbp = next(line for line in lines if line.startswith("condo hbp:"))
        assert "$20,000 withdrawn from the RRSP into the down payment (≤ $60,000 [hbp.withdrawal_limit])" in hbp
        assert "repaid $1,333/yr over 15 years from year 5 [hbp.repayment_years, hbp.repayment_grace_years]" in hbp
        assert "10 tranches fall at or past year 10 and return at the horizon" in hbp
        assert "the RRSP is rebuilt to $21,092 by year 10" in hbp
        assert "net PV $9 charged to condo (hbp_repayment_pv)" in hbp
        assert hbp in read_back_lines(spec)
        financing = next(line for line in lines if line.startswith("condo financing:"))
        assert "cash available $60,000 + HBP $20,000 − purchase_costs $6,000 = down payment $74,000" in financing
        report = format_text_report(compute_deterministic(spec), None, spec.simulation, spec.economic, spec=spec)
        assert "hbp_repayment_pv" in report

    def test_like_for_like_warning_when_the_piles_differ(self):
        doc = cfg({"renter_capital": SPLIT, "hbp_withdrawal": self.H})
        warnings = coherence_warnings(load_config_dict(doc))
        assert any("$60,000 + HBP $20,000 = $80,000" in w and "$60,000" in w for w in warnings)
        doc["condo"]["cash_available"] = 40_000
        assert not any("like-for-like" in w for w in coherence_warnings(load_config_dict(doc)))

    def test_sweeping_the_withdrawal_re_derives_through_the_loader(self):
        from hde.sweep import run_sweep
        result = run_sweep(cfg({"renter_capital": SPLIT, "hbp_withdrawal": 0}), "tax.hbp_withdrawal",
                           [0.0, 20_000.0], monte_carlo=False)
        totals = [row["totals"]["condo"] for row in result["rows"]]
        assert totals[0] != totals[1]


# ---------------------------------------------------------------------------
# Surfaces
# ---------------------------------------------------------------------------

class TestSurfaces:
    def test_the_schema_carries_every_new_key_with_a_note(self):
        schema = input_schema()
        block = schema["tax"]
        for key in ("marginal_rate", "renter_capital", "taxable_return_treatment",
                    "retirement_marginal_rate", "fhsa", "hbp_withdrawal"):
            assert block[key]["note"].strip(), key
        assert "tax" in schema["top_level"]
        assert "required_if" in block["marginal_rate"]

    def test_unknown_nested_keys_are_refused_with_a_hint(self):
        with pytest.raises(ConfigValidationError, match="tax.renter_capital.tfsaa"):
            load_config_dict(cfg({"renter_capital": {**SPLIT, "tfsaa": 1}}))
        with pytest.raises(ConfigValidationError, match="tax.fhsa.balanse"):
            load_config_dict(cfg({"renter_capital": FHSA_SPLIT, "fhsa": {**FHSA, "balanse": 1}}))

    def test_json_assumptions_carry_the_structured_block(self):
        saving = {"balance": 15_000, "annual_contribution": 8_000, "years_until_purchase": 2}
        split = {"tfsa": 14_000, "rrsp": 0, "taxable": 15_000}
        spec = load_config_dict(cfg({"renter_capital": split, "fhsa": saving}))
        block = assumptions_to_dict(spec)["tax"]
        assert block["marginal_rate"] == pytest.approx(0.361175)
        assert block["marginal_rate_source"] == "resolved"
        assert block["renter_capital"]["fhsa"] == 31_000
        assert block["fhsa"]["refunds"] == pytest.approx(0.361175 * 16_000)
        assert block["drag_at_horizon"] > 0 and block["haircut_at_horizon"] > 0
        assert block["principal_residence_exempt_fraction"] == 1.0
        assert assumptions_to_dict(load_config_dict(cfg()))["tax"] is None

    def test_the_read_back_has_a_tax_section_after_purchase_costs(self):
        spec = load_config_dict(cfg({"renter_capital": SPLIT, "hbp_withdrawal": 20_000}))
        lines = read_back_lines(spec)
        tax_at = next(i for i, line in enumerate(lines) if line.startswith("tax:"))
        hbp_at = next(i for i, line in enumerate(lines) if line.startswith("condo hbp:"))
        financing_at = next(i for i, line in enumerate(lines) if line.startswith("condo financing:"))
        assert financing_at < tax_at < hbp_at
