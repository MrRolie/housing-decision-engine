"""The combined marginal rate helper (tax anchors, 2026-09-05).

`tax_rates.marginal_rate` reads the 2026 bracket schedules FROM the registry
and returns the statutory federal + provincial marginal rate at a taxable
income, with the Québec abatement (16.5% of federal tax) and the Ontario surtax
(20% / 36% of basic Ontario tax) applied. Every expected figure below is
hand-checked from the quoted tables — no fetched page prints a combined
marginal-rate example, so there is none to quote.

Two definitions the tests pin, because they are choices:

* the Ontario surtax is levied on basic Ontario tax AFTER non-refundable
  credits, and the registry knows only the basic personal amount — so the
  helper nets exactly 5.05% × $12,989 and nothing else. Other credits push the
  crossover income higher; a run with them would surtax later than this says;
* the federal basic personal amount's phase-out between $181,440 and $258,482
  (an implicit ~0.3-point marginal) is NOT in the rate — the helper reports
  the statutory bracket rate, as the CRA table does.
"""

import pytest

from hde.tax_rates import (
    MarginalRateBreakdown,
    bracket_schedule,
    marginal_rate,
    marginal_rate_breakdown,
    ontario_basic_tax,
    ontario_surtax_tiers,
    progressive_tax,
)

ABATED = 1 - 0.165  # federal tax net of the Québec abatement


class TestQuebec:
    # federal 14% × 0.835 + Québec 14%
    def test_first_bracket(self):
        assert marginal_rate(40_000, "qc") == pytest.approx(0.14 * ABATED + 0.14)
        assert marginal_rate(40_000, "qc") == pytest.approx(0.2569)

    # federal 20.5% ($58,523.01–$117,045) × 0.835 + Québec 19% ($54,345.01–$108,680)
    def test_middle(self):
        assert marginal_rate(100_000, "qc") == pytest.approx(0.205 * ABATED + 0.19)
        assert marginal_rate(100_000, "qc") == pytest.approx(0.361175)

    # federal 26% ($117,045.01–$181,440) × 0.835 + Québec 25.75% (over $132,245)
    def test_upper(self):
        assert marginal_rate(150_000, "qc") == pytest.approx(0.26 * ABATED + 0.2575)
        assert marginal_rate(150_000, "qc") == pytest.approx(0.4746)

    # the top combined rate: federal 33% × 0.835 + 25.75%
    def test_top(self):
        assert marginal_rate(300_000, "qc") == pytest.approx(0.53305)

    def test_breakdown_components(self):
        b = marginal_rate_breakdown(100_000, "qc")
        assert isinstance(b, MarginalRateBreakdown)
        assert b.federal_rate == 0.205
        assert b.quebec_abatement == 0.165
        assert b.federal_net_rate == pytest.approx(0.205 * ABATED)
        assert b.provincial_rate == 0.19
        assert b.surtax_rate == 0.0
        assert b.provincial_net_rate == 0.19
        assert b.combined_rate == pytest.approx(0.361175)
        assert b.combined_rate == marginal_rate(100_000, "qc")


class TestOntario:
    # federal 14% + Ontario 5.05%; basic Ontario tax $2,020 − $655.94 credit is
    # far under the $5,818 surtax threshold
    def test_first_bracket_no_surtax(self):
        b = marginal_rate_breakdown(40_000, "on")
        assert b.surtax_rate == 0.0
        assert b.combined_rate == pytest.approx(0.1905)

    # federal 20.5% + Ontario 9.15% × 1.20: basic Ontario tax at $100,000 is
    # 2,721.50 + 46,109 × 9.15% − 655.94 = 6,284.53, inside the 20% tier
    def test_middle_first_surtax_tier(self):
        b = marginal_rate_breakdown(100_000, "on")
        assert b.surtax_rate == 0.20
        assert b.provincial_net_rate == pytest.approx(0.0915 * 1.20)
        assert b.combined_rate == pytest.approx(0.3148)

    # federal 29% + Ontario 13.16% × 1.56 (both surtax tiers)
    def test_upper_both_tiers(self):
        b = marginal_rate_breakdown(250_000, "on")
        assert b.surtax_rate == pytest.approx(0.56)
        assert b.combined_rate == pytest.approx(0.495296)

    # the top combined rate: federal 33% + 13.16% × 1.56
    def test_top(self):
        assert marginal_rate(300_000, "on") == pytest.approx(0.535296)

    def test_no_abatement_outside_quebec(self):
        b = marginal_rate_breakdown(100_000, "on")
        assert b.quebec_abatement == 0.0
        assert b.federal_net_rate == b.federal_rate == 0.205

    def test_first_surtax_crossover_nets_only_the_basic_personal_credit(self):
        """basic tax = bracket tax − 5.05% × 12,989 = 5,818 at 53,891 × 5.05% +
        (Y − 53,891) × 9.15% − 655.94 ⇒ Y = 94,901.37."""
        assert marginal_rate_breakdown(94_900, "on").surtax_rate == 0.0
        assert marginal_rate_breakdown(94_905, "on").surtax_rate == 0.20

    def test_second_surtax_crossover(self):
        """basic tax = 7,446 ⇒ bracket tax 8,101.94; tax to 107,785 is 7,652.80,
        the rest at 11.16% ⇒ Y = 111,809.6."""
        assert marginal_rate_breakdown(111_805, "on").surtax_rate == 0.20
        b = marginal_rate_breakdown(111_815, "on")
        assert b.surtax_rate == pytest.approx(0.56)
        # federal 20.5% (still under $117,045) + 11.16% × 1.56
        assert b.combined_rate == pytest.approx(0.205 + 0.1116 * 1.56)


class TestSchedules:
    def test_ceilings_are_inclusive(self):
        """CRA prints '$0 to $58,523' then '$58,523.01 to …': the edge belongs
        to the lower bracket."""
        assert marginal_rate_breakdown(58_523, "on").federal_rate == 0.14
        assert marginal_rate_breakdown(58_523.01, "on").federal_rate == 0.205
        assert marginal_rate_breakdown(54_345, "qc").provincial_rate == 0.14
        assert marginal_rate_breakdown(54_345.01, "qc").provincial_rate == 0.19

    def test_bracket_schedule_is_read_from_the_registry(self):
        fed = bracket_schedule("federal")
        assert fed == ((58_523.0, 0.14), (117_045.0, 0.205), (181_440.0, 0.26),
                       (258_482.0, 0.29), (None, 0.33))
        assert bracket_schedule("qc") == ((54_345.0, 0.14), (108_680.0, 0.19),
                                          (132_245.0, 0.24), (None, 0.2575))
        assert bracket_schedule("on") == ((53_891.0, 0.0505), (107_785.0, 0.0915),
                                          (150_000.0, 0.1116), (220_000.0, 0.1216),
                                          (None, 0.1316))

    def test_surtax_tiers(self):
        assert ontario_surtax_tiers() == ((5_818.0, 0.20), (7_446.0, 0.36))

    def test_progressive_tax_matches_the_source_constants(self):
        """TP-1015.F-V prints a constant K per bracket such that tax = T × income
        − K, rounded to the dollar (the exact K for 19% is 54,345 × 5% =
        2,717.25); the registry's brackets must reproduce it within that
        rounding: at $108,680, 108,680 × 19% − 2,717.25 = 17,931.95."""
        assert progressive_tax("qc", 108_680) == pytest.approx(108_680 * 0.19 - 2_717, abs=1.0)
        assert progressive_tax("qc", 132_245) == pytest.approx(132_245 * 0.24 - 8_151, abs=1.0)
        # T4032-ON prints the same constants for Ontario: 107,785 × 9.15% − 2,210
        assert progressive_tax("on", 107_785) == pytest.approx(107_785 * 0.0915 - 2_210, abs=1.0)
        assert progressive_tax("on", 150_000) == pytest.approx(150_000 * 0.1116 - 4_376, abs=1.0)
        assert progressive_tax("federal", 0) == 0.0

    def test_ontario_basic_tax_nets_the_basic_personal_credit(self):
        assert ontario_basic_tax(40_000) == pytest.approx(40_000 * 0.0505 - 0.0505 * 12_989)
        assert ontario_basic_tax(10_000) == 0.0  # never negative

    def test_province_codes_are_case_insensitive(self):
        assert marginal_rate(100_000, "QC") == marginal_rate(100_000, "qc")
        assert marginal_rate(100_000, "ON") == marginal_rate(100_000, "on")

    def test_unknown_province_is_refused_naming_the_registered_ones(self):
        with pytest.raises(ValueError, match="qc.*on|on.*qc"):
            marginal_rate(100_000, "bc")
        with pytest.raises(ValueError):
            marginal_rate(100_000, "")

    def test_negative_income_is_refused(self):
        with pytest.raises(ValueError):
            marginal_rate(-1, "qc")
