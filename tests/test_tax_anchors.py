"""The income-tax, FHSA, HBP and TFSA reference figures (2026-09-05).

Every figure here was fetched from its primary source on 2026-09-05 and is
registered as a REFERENCE entry: the engine applies none of them until a
config opts into a tax block. These pins hold the registry to the quoted
tables — a threshold typed from memory instead of the page is exactly the
defect the registry exists to make impossible.
"""

import pytest

from hde.anchors import (
    ANCHORS,
    ONTARIO_SURTAX_TIERS,
    REFERENCE_FAMILIES,
    TAX_BRACKET_SCHEDULES,
    is_reference,
)

FAMILIES = ("tax.", "fhsa.", "hbp.", "tfsa.")

SCALARS = {
    # CRA, indexation adjustment table, 2026 column
    "tax.federal.basic_personal_amount": 16_452.0,
    # Revenu Québec TP-1015.F-V (2026-01); Finances Québec parameters 2026
    "tax.qc.basic_personal_amount": 18_952.0,
    # CRA T4032-ON, effective January 1, 2026
    "tax.on.basic_personal_amount": 12_989.0,
    # Department of Finance, "Quebec Abatement": 16.5 percentage points
    "tax.federal.quebec_abatement": 0.165,
    "tax.on.surtax_1_threshold": 5_818.0,
    "tax.on.surtax_1_rate": 0.20,
    "tax.on.surtax_2_threshold": 7_446.0,
    "tax.on.surtax_2_rate": 0.36,
    # Income Tax Act s. 38(a): ½ — the proposed two-thirds was cancelled 2025-03-21
    "tax.capital_gains_inclusion_rate": 0.5,
    "tax.principal_residence_exempt_fraction": 1.0,
    "fhsa.annual_limit": 8_000.0,
    "fhsa.lifetime_limit": 40_000.0,
    "fhsa.carry_forward_max": 8_000.0,
    "fhsa.max_years_open": 15.0,
    "hbp.withdrawal_limit": 60_000.0,
    "hbp.repayment_years": 15.0,
    # first repayment year − withdrawal year: 2026 → 2031 under the 2026–2028 relief
    "hbp.repayment_grace_years": 5.0,
    "tfsa.annual_limit": 7_000.0,
    "tfsa.cumulative_room_since_2009": 109_000.0,
}

# (ceiling, rate) as the pages print them; None = no ceiling
FEDERAL = ((58_523.0, 0.14), (117_045.0, 0.205), (181_440.0, 0.26),
           (258_482.0, 0.29), (None, 0.33))
QUEBEC = ((54_345.0, 0.14), (108_680.0, 0.19), (132_245.0, 0.24), (None, 0.2575))
ONTARIO = ((53_891.0, 0.0505), (107_785.0, 0.0915), (150_000.0, 0.1116),
           (220_000.0, 0.1216), (None, 0.1316))


def _family_anchors():
    return {n: a for n, a in ANCHORS.items() if n.startswith(FAMILIES)}


class TestRegistry:
    def test_families_are_reference_tables(self):
        for family in FAMILIES:
            assert family in REFERENCE_FAMILIES
        assert is_reference("tax.federal.bracket_1_rate")
        assert is_reference("fhsa.annual_limit")
        assert is_reference("hbp.withdrawal_limit")
        assert is_reference("tfsa.annual_limit")

    def test_every_scalar_is_registered_with_its_fetched_value(self):
        for name, value in SCALARS.items():
            assert name in ANCHORS, name
            assert ANCHORS[name].value == value, (name, ANCHORS[name].value, value)

    def test_every_entry_was_fetched_on_2026_09_05_and_carries_the_quote(self):
        anchors = _family_anchors()
        # the scalars, plus a ceiling and a rate per bracket (5 federal, 4
        # Québec, 5 Ontario), less the three top brackets' absent ceilings
        assert len(anchors) == len(SCALARS) + 2 * (5 + 4 + 5) - 3
        for name, anchor in anchors.items():
            assert anchor.kind == "cited", name
            assert anchor.url.startswith("http"), name
            assert anchor.retrieved_on == "2026-09-05", name
            assert anchor.as_of == "2026", name
            assert anchor.quoted.strip(), name
            assert anchor.unit.strip(), name

    def test_every_rationale_says_the_figure_is_applied_only_on_opt_in(self):
        """The engine applies none of these today. A rationale that forgot to
        say so would let --print-anchors read as if a tax were being charged."""
        for name, anchor in _family_anchors().items():
            assert "opt" in anchor.rationale.lower(), name

    def test_provincial_entries_carry_their_province(self):
        for name, anchor in _family_anchors().items():
            if name.startswith("tax.qc."):
                assert anchor.province == "qc", name
            elif name.startswith("tax.on."):
                assert anchor.province == "on", name
            else:
                assert anchor.province == "", name


class TestBracketSchedules:
    @pytest.mark.parametrize("jur, rows", [
        ("tax.federal", FEDERAL), ("tax.qc", QUEBEC), ("tax.on", ONTARIO),
    ])
    def test_schedule_rows_match_the_quoted_tables(self, jur, rows):
        _label, url, _source, _unit, schedule, _cite = TAX_BRACKET_SCHEDULES[jur]
        assert url.startswith("http")
        assert [(c, r) for c, r, _q in schedule] == list(rows)

    @pytest.mark.parametrize("jur, rows", [
        ("tax.federal", FEDERAL), ("tax.qc", QUEBEC), ("tax.on", ONTARIO),
    ])
    def test_one_anchor_per_bracket_ceiling_and_rate(self, jur, rows):
        """`<jur>.bracket_<k>_ceiling` and `_rate`, 1-based; the top bracket has
        no ceiling and therefore no ceiling anchor — an Anchor holds a figure
        or is `source: none`, and 'no ceiling' is neither."""
        for k, (ceiling, rate) in enumerate(rows, start=1):
            assert ANCHORS[f"{jur}.bracket_{k}_rate"].value == rate
            if ceiling is None:
                assert f"{jur}.bracket_{k}_ceiling" not in ANCHORS
                assert "no ceiling" in ANCHORS[f"{jur}.bracket_{k}_rate"].rationale
            else:
                assert ANCHORS[f"{jur}.bracket_{k}_ceiling"].value == ceiling
        assert f"{jur}.bracket_{len(rows) + 1}_rate" not in ANCHORS

    def test_ceilings_and_rates_rise_monotonically(self):
        for jur, (_l, _u, _s, _un, schedule, _c) in TAX_BRACKET_SCHEDULES.items():
            ceilings = [c for c, _r, _q in schedule[:-1]]
            rates = [r for _c, r, _q in schedule]
            assert schedule[-1][0] is None, jur
            assert all(c is not None for c in ceilings), jur
            assert ceilings == sorted(ceilings) and len(set(ceilings)) == len(ceilings), jur
            assert rates == sorted(rates) and len(set(rates)) == len(rates), jur

    def test_each_bracket_quote_names_its_own_rate(self):
        """The `quoted` string is the row as the page prints it; it must carry
        the rate the anchor registers, so a reader can reconcile the two."""
        for jur, (_l, _u, _s, _un, schedule, _c) in TAX_BRACKET_SCHEDULES.items():
            for _c, rate, quoted in schedule:
                printed = f"{rate * 100:g}%"
                assert printed in quoted.replace(" %", "%"), (jur, rate, quoted)


class TestScalars:
    def test_ontario_surtax_tiers_are_the_registry(self):
        assert ONTARIO_SURTAX_TIERS == ((5_818.0, 0.20), (7_446.0, 0.36))
        assert "5,818" in ANCHORS["tax.on.surtax_1_threshold"].quoted
        assert "7,446" in ANCHORS["tax.on.surtax_2_threshold"].quoted

    def test_federal_basic_personal_amount_carries_its_phase_out(self):
        a = ANCHORS["tax.federal.basic_personal_amount"]
        assert a.band == (14_829.0, 16_452.0)
        assert "14,829" in a.rationale and "181,440" in a.rationale and "258,482" in a.rationale

    def test_capital_gains_rate_names_the_cancelled_increase(self):
        a = ANCHORS["tax.capital_gains_inclusion_rate"]
        assert "½" in a.quoted
        assert "cancel" in a.source.lower()
        assert "laws-lois.justice.gc.ca" in a.url

    def test_tfsa_cumulative_room_is_the_sum_of_the_quoted_table(self):
        table = {2009: 5_000, 2010: 5_000, 2011: 5_000, 2012: 5_000,
                 2013: 5_500, 2014: 5_500, 2015: 10_000,
                 2016: 5_500, 2017: 5_500, 2018: 5_500,
                 2019: 6_000, 2020: 6_000, 2021: 6_000, 2022: 6_000,
                 2023: 6_500, 2024: 7_000, 2025: 7_000, 2026: 7_000}
        assert sum(table.values()) == ANCHORS["tfsa.cumulative_room_since_2009"].value
        assert "sum" in ANCHORS["tfsa.cumulative_room_since_2009"].rationale.lower()

    def test_hbp_grace_names_both_rules(self):
        a = ANCHORS["hbp.repayment_grace_years"]
        assert a.band == (2.0, 5.0)
        assert "2031" in a.quoted
        assert "second" in a.rationale.lower() and "2028" in a.rationale

    def test_principal_residence_exemption_is_whole(self):
        a = ANCHORS["tax.principal_residence_exempt_fraction"]
        assert a.value == 1.0 and a.band == (1.0, 1.0)
        assert "every year you owned it" in a.quoted
