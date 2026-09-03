"""
The mortgage-insurance premium, computed in the engine (round 7, 2026-09-03).

Five of five insured serves computed the CMHC premium by hand from recalled
tiers, applied the wrong provincial tax rate in two of them, and held the
premium fixed while a price scan walked the loan-to-value across a tier
boundary. The schedule is now anchored and the premium derived in the loader,
so every grid point re-derives its own tier.

Pinned here: tier selection at every band edge, the financing arithmetic, the
cash tax both ways (netted out of `cash_available`, else added to
`purchase_costs`), the refusals, the re-derivation across a price scan, and the
anchor records' url + date + figures.
"""

import pytest

from hde.anchors import ANCHORS
from hde.break_even import solve_break_even
from hde.config import ConfigValidationError, coherence_warnings, load_config_dict
from hde.mortgage_insurance import INSURED_LTV_THRESHOLD, anchored_schedule
from hde.serialization import format_assumptions
from hde.sweep import with_value


def _base(**over):
    """A 500k condo against rent; the round figures make every tier edge exact."""
    cfg = {
        "years": 10,
        "province": "QC",
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0},
        "condo": {
            "initial_value": 500_000, "monthly_fee": 400, "value_growth_rate": 0.0,
            "mortgage_rate": 0.05, "mortgage_term_years": 25,
            "down_payment": 75_000, "mortgage_insurance": "auto",
        },
    }
    cfg.update(over)
    return cfg


def _condo(**over):
    """The base config with condo keys overridden (None drops the key)."""
    cfg = _base()
    for key, value in over.items():
        if value is None:
            cfg["condo"].pop(key, None)
        else:
            cfg["condo"][key] = value
    return cfg


def _ins(cfg):
    return load_config_dict(cfg).condo.mortgage_insurance


def _financing_line(cfg):
    spec = load_config_dict(cfg)
    return next(line for line in format_assumptions(spec)
                if line.startswith("condo financing:"))


# ---------------------------------------------------------------------------
# The anchors themselves: fetched, with the figures as quoted
# ---------------------------------------------------------------------------

class TestScheduleAnchors:
    """The schedule is a fetched citation, never a recalled tier list."""

    BANDS = {
        "mortgage_insurance.premium_rate.ltv_65": 0.0060,
        "mortgage_insurance.premium_rate.ltv_65_75": 0.0170,
        "mortgage_insurance.premium_rate.ltv_75_80": 0.0240,
        "mortgage_insurance.premium_rate.ltv_80_85": 0.0280,
        "mortgage_insurance.premium_rate.ltv_85_90": 0.0310,
        "mortgage_insurance.premium_rate.ltv_90_95": 0.0400,
    }

    @pytest.mark.parametrize("name,rate", sorted(BANDS.items()))
    def test_each_band_is_registered_with_its_quoted_rate(self, name, rate):
        anchor = ANCHORS[name]
        assert anchor.value == pytest.approx(rate)
        assert anchor.url.startswith("https://")
        assert anchor.retrieved_on == "2026-09-03"
        assert "cmhc" in anchor.url.lower()

    def test_the_maximum_and_the_surcharge_are_registered(self):
        assert ANCHORS["mortgage_insurance.max_ltv"].value == pytest.approx(0.95)
        assert ANCHORS["mortgage_insurance.amortization_surcharge"].value == pytest.approx(0.0020)

    def test_the_premium_taxes_carry_url_and_retrieval_date(self):
        for name, rate in (("mortgage_insurance.premium_tax_rate.qc", 0.09),
                           ("mortgage_insurance.premium_tax_rate.on", 0.08)):
            anchor = ANCHORS[name]
            assert anchor.value == pytest.approx(rate)
            assert anchor.url.startswith("https://")
            assert anchor.retrieved_on == "2026-09-03"

    def test_the_quebec_rationale_states_the_2027_step(self):
        """9% is the rate to 2026-12-31; a closing after that pays 9.975%
        (Bill 99). An anchor that hid the step would go stale silently."""
        assert "9.975" in ANCHORS["mortgage_insurance.premium_tax_rate.qc"].rationale

    def test_the_anchored_schedule_reads_its_rates_from_the_registry(self):
        """The schedule is built FROM the registry — one edit, not two."""
        schedule = anchored_schedule("QC")
        assert schedule.max_ltv == pytest.approx(0.95)
        assert schedule.premium_tax_rate == pytest.approx(0.09)
        assert [band.rate for band in schedule.bands] == [
            pytest.approx(0.0060), pytest.approx(0.0170), pytest.approx(0.0240),
            pytest.approx(0.0280), pytest.approx(0.0310), pytest.approx(0.0400)]

    def test_the_bands_are_ordered_by_their_upper_edge(self):
        edges = [band.ltv_max for band in anchored_schedule("QC").bands]
        assert edges == sorted(edges)
        assert edges[-1] == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# Tier selection at the band edges — the hand-computation that went wrong
# ---------------------------------------------------------------------------

class TestTierSelectionAtBandEdges:
    """The upper edge of each band belongs to that band; a dollar past it is
    the next tier up. 80% itself is conventional: no premium at all."""

    @pytest.mark.parametrize("down,expected_rate", [
        (100_000, None),    # 80.00% — conventional, no insurance
        (99_000, 0.0280),   # 80.20%
        (75_000, 0.0280),   # 85.00% — upper edge of 80.01–85
        (74_900, 0.0310),   # 85.02%
        (50_000, 0.0310),   # 90.00% — upper edge of 85.01–90
        (49_900, 0.0400),   # 90.02%
        (25_000, 0.0400),   # 95.00% — the maximum, still insurable
    ])
    def test_the_band_is_chosen_on_the_pre_premium_loan_to_value(self, down, expected_rate):
        record = _ins(_condo(down_payment=down))
        if expected_rate is None:
            assert record is not None and not record.required
            assert record.premium == 0.0 and record.premium_tax == 0.0
        else:
            assert record.required
            assert record.band_rate == pytest.approx(expected_rate)

    def test_eighty_percent_exactly_is_conventional(self):
        record = _ins(_condo(down_payment=100_000))
        assert record.ltv == pytest.approx(INSURED_LTV_THRESHOLD)
        assert not record.required

    def test_the_tier_reads_the_loan_before_the_premium_is_added(self):
        """95% down is insurable; the financed premium pushes the loan past 95%
        of price and that must NOT retro-refuse the config."""
        record = _ins(_condo(down_payment=25_000))
        assert record.ltv == pytest.approx(0.95)
        assert record.ltv_after > 0.95
        assert record.premium == pytest.approx(0.0400 * 475_000)


# ---------------------------------------------------------------------------
# The arithmetic: premium rides the loan, the tax is cash
# ---------------------------------------------------------------------------

class TestFinancingArithmetic:

    def test_the_premium_is_the_band_rate_on_the_loan_and_is_financed(self):
        spec = load_config_dict(_base())
        record = spec.condo.mortgage_insurance
        assert record.premium == pytest.approx(0.0280 * 425_000)   # $11,900
        # financed like financed_purchase_costs: it rides the loan, never year-0 cash
        assert spec.condo.financed_purchase_costs == pytest.approx(11_900.0)
        assert record.loan == pytest.approx(436_900.0)
        assert record.ltv_after == pytest.approx(436_900.0 / 500_000)

    def test_the_engine_finances_the_premium_in_the_deterministic_loan(self):
        """The loan the rest of the engine uses already carries the premium."""
        spec = load_config_dict(_base())
        loan = (spec.condo.initial_value - spec.condo.down_payment
                + spec.condo.financed_purchase_costs)
        assert loan == pytest.approx(436_900.0)

    def test_an_amortization_beyond_25_years_adds_the_surcharge(self):
        record = _ins(_condo(mortgage_term_years=30))
        assert record.surcharge_rate == pytest.approx(0.0020)
        assert record.rate == pytest.approx(0.0300)
        assert record.premium == pytest.approx(0.0300 * 425_000)   # $12,750

    def test_twenty_five_years_carries_no_surcharge(self):
        assert _ins(_base()).surcharge_rate == 0.0

    def test_mortgage_insurance_none_is_the_default_and_changes_nothing(self):
        spec = load_config_dict(_condo(mortgage_insurance=None))
        assert spec.condo.mortgage_insurance is None
        assert spec.condo.financed_purchase_costs == 0.0
        assert spec.condo.purchase_costs == 0.0


class TestPremiumTaxNetting:
    """The tax is paid in cash at closing — CMHC: 'The sales tax can't be added
    to the loan amount.' It is netted out of a stated cash pile, else added to
    purchase_costs."""

    def test_quebec_rate_is_applied_and_added_to_purchase_costs(self):
        spec = load_config_dict(_condo(purchase_costs=9_000))
        record = spec.condo.mortgage_insurance
        assert record.premium_tax_rate == pytest.approx(0.09)
        assert record.premium_tax == pytest.approx(0.09 * 11_900)   # $1,071
        assert spec.condo.purchase_costs == pytest.approx(9_000 + 1_071.0)

    def test_ontario_rate_is_applied(self):
        spec = load_config_dict(_base(province="ON"))
        record = spec.condo.mortgage_insurance
        assert record.premium_tax_rate == pytest.approx(0.08)
        assert record.premium_tax == pytest.approx(0.08 * 11_900)   # $952

    def test_a_province_without_a_premium_tax_pays_none(self):
        record = _ins(_base(province="other"))
        assert record.premium_tax_rate == 0.0
        assert record.premium_tax == 0.0
        assert record.premium > 0

    def test_the_option_province_overrides_the_top_level_one(self):
        """An Ottawa-vs-Gatineau config compares two provinces in one file."""
        record = _ins(_condo(province="ON"))          # top level says QC
        assert record.premium_tax_rate == pytest.approx(0.08)

    def test_cash_available_has_the_tax_netted_out_of_the_pile(self):
        cfg = _condo(down_payment=None, cash_available=90_000, purchase_costs=10_000)
        spec = load_config_dict(cfg)
        opt, record = spec.condo, spec.condo.mortgage_insurance
        # the pile pays the cash costs, the tax, and what is left is the down payment
        assert (opt.cash_available - opt.purchase_costs - record.premium_tax
                == pytest.approx(opt.down_payment, abs=1e-6))
        # ... and the tax is self-consistently the tax on the resulting loan
        loan = opt.initial_value - opt.down_payment
        assert record.premium_tax == pytest.approx(
            record.premium_tax_rate * record.rate * loan, abs=1e-6)
        # purchase_costs stays the CASH closing costs the user typed: the tax
        # came out of the pile, so adding it there too would double count
        assert opt.purchase_costs == pytest.approx(10_000.0)

    def test_the_tax_feedback_can_move_the_tier(self):
        """Paying the tax out of the pile shrinks the down payment, which
        raises the loan-to-value — close to an edge that changes the tier.
        Base LTV 84.95% (2.80%); after the tax it settles in 85.01–90 at 3.10%."""
        cfg = _condo(down_payment=None, cash_available=85_250, purchase_costs=10_000)
        spec = load_config_dict(cfg)
        opt, record = spec.condo, spec.condo.mortgage_insurance
        assert record.band_rate == pytest.approx(0.0310)
        assert record.ltv > 0.85
        # the down payment moved by more than a dollar against the naive netting
        assert opt.down_payment < 85_250 - 10_000 - 1.0
        assert (opt.cash_available - opt.purchase_costs - record.premium_tax
                == pytest.approx(opt.down_payment, abs=1e-6))


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

class TestRefusals:

    def test_financed_purchase_costs_beside_auto_is_refused_as_double_counting(self):
        with pytest.raises(ConfigValidationError, match="double"):
            load_config_dict(_condo(financed_purchase_costs=11_900))

    def test_financed_purchase_costs_alone_still_works_as_the_manual_path(self):
        spec = load_config_dict(_condo(mortgage_insurance=None,
                                       financed_purchase_costs=11_900))
        assert spec.condo.financed_purchase_costs == pytest.approx(11_900.0)
        assert spec.condo.mortgage_insurance is None

    def test_a_loan_to_value_above_the_maximum_is_refused_with_the_figure(self):
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config_dict(_condo(down_payment=20_000))   # 96.00%
        message = str(excinfo.value)
        assert "96.00%" in message and "95.00%" in message

    def test_all_cash_with_insurance_is_refused(self):
        with pytest.raises(ConfigValidationError, match="all_cash"):
            load_config_dict(_condo(all_cash=True, down_payment=None,
                                    mortgage_rate=None, mortgage_term_years=None))

    def test_auto_without_a_province_is_refused(self):
        cfg = _base()
        cfg.pop("province")
        with pytest.raises(ConfigValidationError, match="province"):
            load_config_dict(cfg)

    def test_saskatchewan_is_refused_because_its_rate_is_not_anchored(self):
        """CMHC names Ontario, Québec and Saskatchewan as taxing provinces; only
        two are anchored, so SK must state its own rate rather than get 0%."""
        with pytest.raises(ConfigValidationError, match="premium_tax_rate"):
            load_config_dict(_base(province="SK"))

    def test_an_unknown_province_is_refused_with_the_accepted_values(self):
        with pytest.raises(ConfigValidationError, match="QC"):
            load_config_dict(_base(province="Ontario"))

    def test_an_explicit_schedule_without_a_premium_tax_rate_is_refused(self):
        with pytest.raises(ConfigValidationError, match="premium_tax_rate"):
            load_config_dict(_condo(mortgage_insurance={
                "bands": [{"ltv_max": 0.95, "rate": 0.035}]}))

    def test_an_explicit_schedule_without_bands_is_refused(self):
        with pytest.raises(ConfigValidationError, match="bands"):
            load_config_dict(_condo(mortgage_insurance={"premium_tax_rate": 0.09}))

    def test_an_unknown_mortgage_insurance_word_is_refused(self):
        with pytest.raises(ConfigValidationError, match="auto"):
            load_config_dict(_condo(mortgage_insurance="cmhc"))


class TestExplicitSchedule:
    """The escape hatch: the user quotes their own bands (a lender's sheet, or a
    schedule the engine has no anchor for)."""

    SCHEDULE = {"bands": [{"ltv_max": 0.90, "rate": 0.025},
                          {"ltv_max": 0.95, "rate": 0.035}],
                "premium_tax_rate": 0.05}

    def test_the_users_own_bands_and_tax_rate_are_used(self):
        record = _ins(_condo(mortgage_insurance=self.SCHEDULE))
        assert record.band_rate == pytest.approx(0.025)      # 85% falls in <=90
        assert record.premium == pytest.approx(0.025 * 425_000)
        assert record.premium_tax == pytest.approx(0.05 * 0.025 * 425_000)

    def test_an_explicit_schedule_needs_no_province(self):
        cfg = _condo(mortgage_insurance=self.SCHEDULE)
        cfg.pop("province")
        assert _ins(cfg).premium_tax_rate == pytest.approx(0.05)

    def test_the_explicit_maximum_is_its_last_band(self):
        with pytest.raises(ConfigValidationError, match="95.00%"):
            load_config_dict(_condo(down_payment=20_000,
                                    mortgage_insurance=self.SCHEDULE))


# ---------------------------------------------------------------------------
# Re-derivation across a scan — the failure this feature exists to remove
# ---------------------------------------------------------------------------

class TestReDerivationAcrossAScan:
    """--sweep / --break-even re-run the loader per grid point, so the tier is
    re-chosen at each price instead of being frozen at the base config."""

    def test_a_price_scan_moves_the_tier_between_two_grid_points(self):
        raw = _condo(down_payment=75_000)
        cheap = load_config_dict(with_value(raw, "condo.initial_value", 500_000))
        dear = load_config_dict(with_value(raw, "condo.initial_value", 520_000))
        assert cheap.condo.mortgage_insurance.band_rate == pytest.approx(0.0280)  # 85.00%
        assert dear.condo.mortgage_insurance.band_rate == pytest.approx(0.0310)   # 85.58%
        assert (dear.condo.financed_purchase_costs
                > cheap.condo.financed_purchase_costs)

    def test_a_cash_scan_re_derives_the_premium_per_point(self):
        raw = _condo(down_payment=None, cash_available=90_000, purchase_costs=10_000)
        lean = load_config_dict(with_value(raw, "condo.cash_available", 60_000))
        rich = load_config_dict(with_value(raw, "condo.cash_available", 110_000))
        assert lean.condo.mortgage_insurance.band_rate > rich.condo.mortgage_insurance.band_rate

    def test_grid_points_above_the_maximum_shrink_the_search(self):
        """A refused point is data, not a crash: break-even reports it."""
        raw = _condo(down_payment=75_000)
        result = solve_break_even(raw, "condo.initial_value", 400_000, 2_000_000)
        assert result.get("refused"), result
        assert result["refused"]["count"] > 0


# ---------------------------------------------------------------------------
# Read-back: what the user is actually told
# ---------------------------------------------------------------------------

class TestReadBack:

    def test_the_financing_line_states_tier_premium_tax_and_the_result(self):
        line = _financing_line(_base())
        assert "insured: 85.00% LTV" in line
        assert "2.80% tier" in line
        assert "$11,900 financed" in line
        assert "premium tax 9% (QC) = $1,071 cash" in line
        assert "loan $436,900" in line
        assert "87.38% LTV" in line

    def test_the_line_names_the_surcharge_only_when_it_fires(self):
        assert "+0.20%" in _financing_line(_condo(mortgage_term_years=30))
        assert "+0.20%" not in _financing_line(_base())

    def test_auto_below_the_line_says_none_was_required(self):
        line = _financing_line(_condo(down_payment=100_000))
        assert "none required" in line
        assert "80.00%" in line

    def test_the_premium_is_not_echoed_as_a_typed_financed_purchase_cost(self):
        """The user never typed financed_purchase_costs — saying they did would
        credit them with a number the engine chose."""
        assert "financed_purchase_costs $" not in _financing_line(_base())

    def test_the_cash_equation_balances_with_the_premium_tax_in_it(self):
        """The tax is paid out of the pile, so the sentence that shows the
        netting must carry it: cash − purchase_costs − premium tax = down
        payment. Without the term the printed equation is simply false."""
        line = _financing_line(_condo(down_payment=None, cash_available=90_000,
                                      purchase_costs=10_000))
        assert ("cash available $90,000 − purchase_costs $10,000 − premium tax $1,061 "
                "= down payment $78,939") in line
        assert line.count("$78,939") == 1

    def test_the_year_zero_cash_names_the_premium_tax_it_includes(self):
        """A stated down payment pays the tax on top: the parenthetical must
        list every term of the figure it explains."""
        line = _financing_line(_base())
        assert "year-0 cash $76,071 (down payment + purchase_costs + premium tax)" in line

    def test_an_uninsured_cash_equation_is_unchanged(self):
        line = _financing_line(_condo(mortgage_insurance=None, down_payment=None,
                                      cash_available=90_000, purchase_costs=10_000))
        assert "cash available $90,000 − purchase_costs $10,000 = down payment $80,000" in line
        assert "premium tax" not in line

    def test_the_under_twenty_warning_states_what_was_computed(self):
        warns = coherence_warnings(load_config_dict(_base()))
        under = [w for w in warns if "under the 20%" in w]
        assert under, warns
        assert "2.80%" in under[0] and "$11,900" in under[0]
        assert "put it in financed_purchase_costs" not in under[0]

    def test_without_insurance_the_warning_still_asks_for_the_manual_path(self):
        """The default path is untouched: no schedule, so the old ask stands."""
        warns = coherence_warnings(load_config_dict(_condo(mortgage_insurance=None)))
        under = [w for w in warns if "under the 20%" in w]
        assert under and "financed_purchase_costs" in under[0]
