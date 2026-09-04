"""Jurisdiction reference anchors: property tax by municipality, home insurance
by province.

These are NOT engine defaults — the engine never applies them. They are a
published reference table the user (or an assistant writing the YAML) picks
from, and the assumption read-back cites one by name when the user's own figure
equals the published figure. The pins here are the honesty contract in test
form:

1. Every reference entry carries a fetched URL, the retrieval date, the figure
   AS QUOTED by the source, and the unit that figure is stated in.
2. `--print-anchors` lists them, quoted figure and unit included.
3. The read-back cites a matching anchor and carries its unit — a municipal
   rate is a rate on ASSESSED value and the echo must never let it read as a
   rate on market value.
4. A jurisdiction with no fetchable source is registered as `source: none` and
   prints as such: an absent source is reported, never inferred.
"""

import pytest

from hde.anchors import (
    ANCHORS,
    REFERENCE_FAMILIES,
    Anchor,
    AnchorError,
    is_reference,
    match_reference,
    match_reference_sum,
    short_cite,
)
from hde.config import load_config_dict
from hde.serialization import (
    anchors_to_dict,
    assumptions_to_dict,
    format_assumptions,
    reference_matches,
)

PROPERTY_TAX = "property_tax."
HOME_INSURANCE = "home_insurance."

# The jurisdictions the registry is required to speak to. A jurisdiction with
# no fetchable primary source is still REQUIRED to appear — as `source: none`.
REQUIRED_JURISDICTIONS = [
    "property_tax.laval",
    "property_tax.montreal",
    "property_tax.quebec_city",
    "property_tax.gatineau",
    "property_tax.ottawa",
    "property_tax.toronto",
    "home_insurance.qc",
    "home_insurance.on",
]


def _reference_anchors():
    return {n: a for n, a in ANCHORS.items() if is_reference(n)}


def _sourced():
    return {n: a for n, a in _reference_anchors().items() if a.kind != "unsourced"}


class TestReferenceRegistry:
    def test_every_required_jurisdiction_is_registered(self):
        missing = [n for n in REQUIRED_JURISDICTIONS if n not in ANCHORS]
        assert not missing, f"unregistered jurisdictions: {missing}"

    def test_sourced_entries_carry_url_date_figure_and_unit(self):
        for name, anchor in _sourced().items():
            assert anchor.url.startswith("http"), f"{name}: no fetched URL"
            assert anchor.retrieved_on.strip(), f"{name}: no retrieval date"
            assert anchor.quoted.strip(), f"{name}: no figure as quoted"
            assert anchor.unit.strip(), f"{name}: no unit for the quoted figure"
            assert anchor.value is not None, f"{name}: sourced entry with no value"

    def test_property_tax_units_say_assessed_not_market(self):
        """The one thing this feature must never do is let a rate on assessed
        value read as a rate on market value."""
        for name, anchor in _sourced().items():
            if not name.startswith(PROPERTY_TAX):
                continue
            assert "assess" in anchor.unit.lower(), (
                f"{name}: unit must state the base the rate applies to, got {anchor.unit!r}"
            )

    def test_construction_refuses_a_reference_entry_without_a_unit(self):
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=0.01, as_of="2026", source="s",
                   url="https://example.org", rationale="r", band=(0.0, 0.02),
                   short_cite="s", province="qc", retrieved_on="2026-09-03", quoted="1.0%")

    def test_construction_refuses_a_reference_entry_without_the_quoted_figure(self):
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=0.01, as_of="2026", source="s",
                   url="https://example.org", rationale="r", band=(0.0, 0.02),
                   short_cite="s", province="qc", retrieved_on="2026-09-03",
                   unit="rate on assessed value")


class TestUnsourcedEntries:
    """`source: none` is a first-class registry state, not an omission."""

    def _unsourced(self):
        return Anchor(
            name="property_tax.nowhere",
            value=None,
            as_of="2026",
            source="none — no primary source found",
            url="none — tried the municipality's budget page and its tax-rate PDF",
            rationale="Tried the city's own budget page and rate PDF; neither carried a "
                      "2026 residential rate in fetchable form. No figure is registered.",
            band=(0.0, 0.0),
            short_cite="source: none",
            province="qc",
            kind="unsourced",
        )

    def test_an_unsourced_entry_holds_no_value(self):
        assert self._unsourced().value is None

    def test_construction_refuses_a_tax_entry_without_a_province(self):
        """The municipal + school sum is only a real bill within one province,
        so an entry that cannot say which one it is in cannot be paired."""
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=0.01, as_of="2026", source="s",
                   url="https://example.org", rationale="r", band=(0.0, 0.02),
                   short_cite="s", retrieved_on="2026-09-03", quoted="1.0%",
                   unit="rate on assessed value")

    def test_unsourced_entries_must_say_what_was_tried(self):
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=None, as_of="2026",
                   source="none", url="none", rationale="r", band=(0.0, 0.0),
                   short_cite="source: none", province="qc", kind="unsourced")

    def test_unsourced_entries_refuse_a_value(self):
        """A `source: none` entry carrying a number is the exact failure this
        state exists to prevent — a figure with no source."""
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=0.01, as_of="2026",
                   source="none — nothing fetchable",
                   url="none — tried the budget page", rationale="r",
                   band=(0.0, 0.02), short_cite="source: none", kind="unsourced")

    def test_unsourced_entries_refuse_a_live_url(self):
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=None, as_of="2026",
                   source="none", url="https://example.org", rationale="r",
                   band=(0.0, 0.0), short_cite="source: none", kind="unsourced")

    def test_an_unsourced_entry_prints_as_source_none(self):
        printed = anchors_to_dict()
        for name, anchor in _reference_anchors().items():
            if anchor.kind != "unsourced":
                continue
            entry = printed[name]
            assert entry["value"] is None, f"{name}: printed a value with no source"
            assert entry["kind"] == "unsourced"
            assert "none" in entry["url"].lower()
            assert entry["short_cite"] == "source: none"

    def test_an_unsourced_entry_never_matches(self):
        assert match_reference(PROPERTY_TAX, 0.0) == []


class TestPrintAnchors:
    def test_print_anchors_lists_every_reference_entry(self):
        printed = anchors_to_dict()
        for name in REQUIRED_JURISDICTIONS:
            assert name in printed, f"--print-anchors omits {name}"

    def test_printed_reference_entries_carry_quoted_and_unit(self):
        printed = anchors_to_dict()
        for name in _sourced():
            assert printed[name]["quoted"], f"{name}: quoted figure not printed"
            assert printed[name]["unit"], f"{name}: unit not printed"
            assert printed[name]["retrieved_on"], f"{name}: retrieval date not printed"


class TestMatcher:
    def test_matches_its_own_published_figure(self):
        laval = ANCHORS["property_tax.laval"]
        assert laval.value is not None
        assert [a.name for a in match_reference(PROPERTY_TAX, laval.value)] == ["property_tax.laval"]

    def test_a_figure_matching_nothing_returns_nothing(self):
        assert match_reference(PROPERTY_TAX, 0.0999) == []

    def test_rounding_the_dollar_amount_still_matches(self):
        """The tolerance exists for this and nothing else: a user who types the
        annual amount to the nearest dollar still typed the published rate."""
        laval = ANCHORS["property_tax.laval"]
        rounded = round(laval.value * 600_000) / 600_000
        assert [a.name for a in match_reference(PROPERTY_TAX, rounded)] == ["property_tax.laval"]

    def test_a_near_miss_is_not_a_match(self):
        """2026-09-03: a 0.750%-of-price line in a MONTRÉAL scenario matched
        Québec City's 0.7464% under a looser window. True, and misleading."""
        assert match_reference(PROPERTY_TAX, 0.0075) == []

    def test_match_is_confined_to_its_own_family(self):
        laval = ANCHORS["property_tax.laval"]
        assert match_reference(HOME_INSURANCE, laval.value) == []

    def test_reference_families_are_declared(self):
        assert PROPERTY_TAX in REFERENCE_FAMILIES
        assert HOME_INSURANCE in REFERENCE_FAMILIES
        assert is_reference("property_tax.laval")
        assert not is_reference("condo.house.selling_cost_rate")

    def test_reference_anchors_are_not_engine_defaults(self):
        """Nothing in the registry's default-citation path may resolve to a
        jurisdiction table: these are never applied, only cited."""
        for name in _reference_anchors():
            assert short_cite(name) in ("", ANCHORS[name].short_cite)


def _spec(other_costs, initial_value=600_000):
    return load_config_dict({
        "years": 10,
        "house": {
            "initial_value": initial_value,
            "all_cash": True,
            "other_recurring_costs": other_costs,
        },
        "rent": {"monthly_rent": 2_000},
    })


class TestReadBack:
    def test_a_matching_property_tax_line_is_cited_by_name(self):
        laval = ANCHORS["property_tax.laval"]
        amount = round(laval.value * 600_000, 2)
        spec = _spec([{"name": "property tax", "annual_amount": amount}])
        text = " ".join(format_assumptions(spec))
        assert laval.short_cite in text

    def test_the_citation_carries_the_unit_so_assessed_is_never_read_as_market(self):
        laval = ANCHORS["property_tax.laval"]
        amount = round(laval.value * 600_000, 2)
        spec = _spec([{"name": "property tax", "annual_amount": amount}])
        text = " ".join(format_assumptions(spec))
        assert "assess" in text.lower(), (
            "the read-back cited a rate on assessed value without saying so"
        )

    def test_an_unmatched_property_tax_line_says_it_is_unmatched(self):
        spec = _spec([{"name": "property tax", "annual_amount": 9_999}])
        text = " ".join(format_assumptions(spec))
        assert f"{9_999 / 600_000:.3%}" in text  # the implied rate is still shown
        assert "no anchor" in text.lower()

    def test_the_implied_rate_is_shown_whether_or_not_it_matches(self):
        laval = ANCHORS["property_tax.laval"]
        amount = round(laval.value * 600_000, 2)
        spec = _spec([{"name": "property tax", "annual_amount": amount}])
        text = " ".join(format_assumptions(spec))
        assert f"{laval.value:.3%}" in text

    def test_a_tenant_insurance_line_is_never_matched_to_a_homeowner_premium(self):
        """`home_insurance.*` is a HOMEOWNER premium; a renter's policy is a
        different product and must not borrow the citation."""
        qc = ANCHORS.get("home_insurance.qc")
        if qc is None or qc.value is None:
            pytest.skip("no sourced QC home-insurance anchor")
        spec = load_config_dict({
            "years": 10,
            "rent": {
                "monthly_rent": 2_000,
                "other_recurring_costs": [
                    {"name": "tenant insurance", "annual_amount": qc.value},
                ],
            },
        })
        assert reference_matches(spec) == []

    def test_a_config_with_no_other_costs_adds_no_line(self):
        spec = _spec([])
        assert reference_matches(spec) == []
        assert not any(line.startswith("house other costs:")
                       for line in format_assumptions(spec))

    def test_the_structured_form_carries_the_matched_anchor(self):
        laval = ANCHORS["property_tax.laval"]
        amount = round(laval.value * 600_000, 2)
        spec = _spec([{"name": "property tax", "annual_amount": amount}])
        doc = assumptions_to_dict(spec)
        entries = doc["reference_matches"]
        assert entries, "no reference_matches in the structured assumptions"
        entry = entries[0]
        assert entry["option"] == "house"
        assert entry["cost_name"] == "property tax"
        assert entry["annual_amount"] == pytest.approx(amount)
        assert entry["implied_rate"] == pytest.approx(laval.value, abs=1e-6)
        assert entry["matches"][0]["name"] == "property_tax.laval"
        assert entry["matches"][0]["unit"] == laval.unit
        assert entry["matches"][0]["url"] == laval.url

    def test_an_unmatched_line_is_reported_with_an_empty_match_list(self):
        spec = _spec([{"name": "property tax", "annual_amount": 9_999}])
        entry = assumptions_to_dict(spec)["reference_matches"][0]
        assert entry["matches"] == []

    def test_underscored_names_are_matched(self):
        """`property_tax` / `home_insurance` is how the shipped examples name
        these lines; a matcher blind to it would skip the repo's own configs."""
        spec = _spec([
            {"name": "property_tax", "annual_amount": 4_700},
            {"name": "home_insurance", "annual_amount": 1_200},
        ])
        families = [e["family"] for e in reference_matches(spec)]
        assert families == ["property_tax.", "home_insurance."]

    def test_a_non_tax_non_insurance_line_is_not_annotated(self):
        """Landscaping is neither; the read-back must not invent a rate for it."""
        spec = _spec([{"name": "landscaping", "annual_amount": 1_200}])
        assert reference_matches(spec) == []


# ---------------------------------------------------------------------------
# Sums of anchors (2026-09-04)
#
# A Québec owner's tax bill IS the municipal rate plus the province's school
# rate: three answers this week set `property_tax_rate` to that sum — both
# halves anchored — and the read-back printed "no anchor match" on a number
# built entirely from anchors. The citation degraded on the most careful
# configs, which is the wrong way round.
# ---------------------------------------------------------------------------

class TestSumMatcher:
    def _pair(self):
        muni = ANCHORS["property_tax.laval"]
        school = ANCHORS["school_tax.qc"]
        return muni, school, muni.value + school.value

    def test_a_municipal_plus_school_rate_matches_both_anchors(self):
        muni, school, total = self._pair()
        pairs = match_reference_sum(PROPERTY_TAX, total)
        assert [[a.name for a in p] for p in pairs] == [[muni.name, school.name]]

    def test_a_sum_of_two_municipal_rates_never_matches(self):
        """The pairing is municipal + school BY CONSTRUCTION. Two cities'
        rates summed is not a bill anyone pays, and citing both for it would
        be an invented total."""
        laval = ANCHORS["property_tax.laval"].value
        montreal = ANCHORS["property_tax.montreal"].value
        assert match_reference_sum(PROPERTY_TAX, laval + montreal) == []

    def test_a_school_tax_is_only_summed_within_its_own_province(self):
        """Toronto + the Québec school rate is not an Ontario owner's bill —
        Ontario's education rate is already inside the Toronto total."""
        toronto = ANCHORS["property_tax.toronto"].value
        school = ANCHORS["school_tax.qc"].value
        assert match_reference_sum(PROPERTY_TAX, toronto + school) == []

    def test_the_sum_window_is_the_same_half_basis_point(self):
        muni, school, total = self._pair()
        assert match_reference_sum(PROPERTY_TAX, total + 4e-6)
        assert match_reference_sum(PROPERTY_TAX, total + 5e-5) == []

    def test_rounding_the_dollar_amount_still_matches_a_sum(self):
        _, _, total = self._pair()
        rounded = round(total * 600_000) / 600_000
        assert [a.name for a in match_reference_sum(PROPERTY_TAX, rounded)[0]] == [
            "property_tax.laval", "school_tax.qc"]

    def test_an_unsourced_municipality_never_sums(self):
        """Gatineau holds no figure, so no sum containing it can exist."""
        school = ANCHORS["school_tax.qc"].value
        assert all("gatineau" not in a.name
                   for pair in match_reference_sum(PROPERTY_TAX, 0.006 + school)
                   for a in pair)

    def test_single_anchor_matching_is_unchanged_by_the_sum_rule(self):
        muni, _, _ = self._pair()
        assert [a.name for a in match_reference(PROPERTY_TAX, muni.value)] == [muni.name]
        assert match_reference_sum(PROPERTY_TAX, muni.value) == []

    def test_home_insurance_amounts_are_never_summed(self):
        qc = ANCHORS["home_insurance.qc"]
        assert match_reference_sum(HOME_INSURANCE, qc.value * 2) == []

    def test_every_pairable_anchor_declares_its_province(self):
        """The pairing is by province; an entry that does not say which one it
        is in cannot be paired, so the registry refuses it at import."""
        for name, anchor in ANCHORS.items():
            if name.startswith((PROPERTY_TAX, "school_tax.")):
                assert anchor.province.strip(), f"{name}: no province"


class TestSumReadBack:
    def _spec_at_the_sum(self):
        muni = ANCHORS["property_tax.laval"]
        school = ANCHORS["school_tax.qc"]
        total = muni.value + school.value
        return _spec([{"name": "property tax",
                       "annual_amount": round(total * 600_000, 2)}]), muni, school

    def test_the_read_back_cites_both_anchors_by_name(self):
        spec, muni, school = self._spec_at_the_sum()
        text = " ".join(format_assumptions(spec))
        assert muni.short_cite in text
        assert school.short_cite in text
        assert "no anchor match" not in text

    def test_the_citation_carries_both_units(self):
        spec, muni, school = self._spec_at_the_sum()
        text = " ".join(format_assumptions(spec))
        assert muni.unit in text
        assert school.unit in text

    def test_the_structured_form_lists_both_anchors_for_the_line(self):
        spec, muni, school = self._spec_at_the_sum()
        entry = assumptions_to_dict(spec)["reference_matches"][0]
        assert [m["name"] for m in entry["matches"]] == [muni.name, school.name]
        assert entry["citations"] == [{
            "kind": "sum",
            "anchors": [muni.name, school.name],
            "total": pytest.approx(muni.value + school.value),
        }]

    def test_a_single_match_still_reports_one_citation(self):
        laval = ANCHORS["property_tax.laval"]
        spec = _spec([{"name": "property tax",
                       "annual_amount": round(laval.value * 600_000, 2)}])
        entry = assumptions_to_dict(spec)["reference_matches"][0]
        assert entry["citations"] == [{
            "kind": "single",
            "anchors": [laval.name],
            "total": pytest.approx(laval.value),
        }]

    def test_a_rate_form_config_is_cited_the_same_way(self):
        """`property_tax_rate` is the price-proportional form the threshold
        lane uses; the line it synthesizes must cite the sum too."""
        muni = ANCHORS["property_tax.laval"]
        school = ANCHORS["school_tax.qc"]
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "all_cash": True,
                      "property_tax_rate": muni.value + school.value},
            "rent": {"monthly_rent": 2_000},
        })
        text = " ".join(format_assumptions(spec))
        assert muni.short_cite in text and school.short_cite in text

    def test_an_unmatched_sum_still_says_no_anchor_match(self):
        spec = _spec([{"name": "property tax", "annual_amount": 9_999}])
        entry = assumptions_to_dict(spec)["reference_matches"][0]
        assert entry["matches"] == [] and entry["citations"] == []
        assert "no anchor" in " ".join(format_assumptions(spec)).lower()


# ---------------------------------------------------------------------------
# The posted mortgage rate (2026-09-04)
#
# No anchor existed for a mortgage rate, so a user with no quote got an
# assistant's guess with nothing to bracket it.
# ---------------------------------------------------------------------------

class TestPostedMortgageRate:
    NAME = "mortgage_rate.posted_5y"

    def test_it_is_registered(self):
        assert self.NAME in ANCHORS

    def test_it_carries_url_date_value_and_unit_or_says_source_none(self):
        anchor = ANCHORS[self.NAME]
        if anchor.kind == "unsourced":
            assert anchor.value is None
            assert anchor.short_cite.startswith("source: none")
            assert "tried" in anchor.url.lower()
            return
        assert anchor.url.startswith("http")
        assert anchor.retrieved_on.strip()
        assert anchor.value is not None
        assert anchor.quoted.strip()
        assert anchor.unit.strip()
        assert anchor.band[0] <= anchor.value <= anchor.band[1]

    def test_the_unit_says_posted_and_that_contracted_rates_run_lower(self):
        anchor = ANCHORS[self.NAME]
        if anchor.kind == "unsourced":
            pytest.skip("no posted rate fetched")
        low = anchor.unit.lower()
        assert "posted" in low
        assert "lower" in low or "discount" in low

    def test_it_is_never_applied_as_an_engine_default(self):
        """Like the jurisdiction tables: cited when the user's figure comes
        from it, never silently supplied."""
        assert is_reference(self.NAME)
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "all_cash": True},
            "rent": {"monthly_rent": 2_000},
        })
        assert not any("mortgage_rate" in k for k in spec.defaults_applied)

    def test_print_anchors_lists_it_with_its_quoted_figure(self):
        printed = anchors_to_dict()[self.NAME]
        assert printed["source"]
        if printed["kind"] != "unsourced":
            assert printed["quoted"] and printed["unit"] and printed["retrieved_on"]

    def test_the_schema_note_points_at_it(self):
        from hde.input_schema import input_schema
        text = str(input_schema())
        assert self.NAME in text


# ---------------------------------------------------------------------------
# An unmatched Ontario tax line says WHY the rate-on-price reading overstates
# (2026-09-04). Served answers showed an Ottawa run applying a rate to the
# purchase price with nothing beside the `no anchor match` telling the reader
# that Ontario assesses the 2026 tax year on January 1, 2016 values.
# ---------------------------------------------------------------------------

ONTARIO_SUFFIX = ("[no anchor match — hde --print-anchors; a rate on the purchase price "
                  "overstates an Ontario bill: assessments are on a 2016 base]")


def _spec_in(other_costs, **house_extra):
    house = {"initial_value": 600_000, "all_cash": True, "other_recurring_costs": other_costs}
    house.update(house_extra)
    return load_config_dict({"years": 10, "house": house, "rent": {"monthly_rent": 2_000}})


def _other_costs_line(spec):
    hits = [ln for ln in format_assumptions(spec) if ln.startswith("house other costs:")]
    assert len(hits) == 1, hits
    return hits[0]


class TestOntarioNoMatchSuffix:
    def test_an_unmatched_ontario_tax_line_carries_the_assessment_base(self):
        spec = _spec_in([{"name": "property tax", "annual_amount": 6_000}], province="ON")
        assert ONTARIO_SUFFIX in _other_costs_line(spec)

    def test_toronto_as_municipality_places_the_option_in_ontario(self):
        spec = _spec_in([{"name": "property tax", "annual_amount": 6_000}], municipality="toronto")
        assert ONTARIO_SUFFIX in _other_costs_line(spec)

    def test_a_quebec_line_keeps_the_plain_no_match(self):
        spec = _spec_in([{"name": "property tax", "annual_amount": 6_000}], province="QC")
        line = _other_costs_line(spec)
        assert "[no anchor match — hde --print-anchors]" in line
        assert "2016" not in line

    def test_no_province_keeps_the_plain_no_match(self):
        spec = _spec_in([{"name": "property tax", "annual_amount": 6_000}])
        assert "2016" not in _other_costs_line(spec)

    def test_a_matched_ontario_line_is_cited_not_suffixed(self):
        toronto = ANCHORS["property_tax.toronto"]
        spec = _spec_in([{"name": "property tax", "annual_amount": round(toronto.value * 600_000, 2)}],
                        province="ON")
        line = _other_costs_line(spec)
        assert toronto.short_cite in line and "no anchor match" not in line

    def test_an_unmatched_ontario_insurance_line_is_not_about_assessments(self):
        spec = _spec_in([{"name": "home insurance", "annual_amount": 1_500}], province="ON")
        line = _other_costs_line(spec)
        assert "no anchor match" in line and "2016" not in line

    def test_the_structured_entry_carries_the_province(self):
        spec = _spec_in([{"name": "property tax", "annual_amount": 6_000}], municipality="toronto")
        [entry] = reference_matches(spec)
        assert entry["province"] == "ON"
        spec = _spec_in([{"name": "property tax", "annual_amount": 6_000}])
        [entry] = reference_matches(spec)
        assert entry["province"] is None

# ---------------------------------------------------------------------------
# Contracted mortgage rates (2026-09-04)
#
# The posted rate is a list price; what borrowers actually paid is its own pair
# of anchors, so a typed rate has the market's realised figure beside it and
# the posted rationale points at them by name instead of repeating figures.
# ---------------------------------------------------------------------------

class TestContractedMortgageRates:
    UNINSURED = "mortgage_rate.contracted_5y_uninsured"
    INSURED = "mortgage_rate.contracted_5y_insured"

    @pytest.mark.parametrize("name, series", [(UNINSURED, "V122667786"),
                                              (INSURED, "V122667780")])
    def test_registered_fetched_and_quoted(self, name, series):
        anchor = ANCHORS[name]
        assert is_reference(name)
        assert anchor.url.startswith("https://www.bankofcanada.ca/valet/observations/" + series)
        assert anchor.retrieved_on == "2026-09-04"
        assert series in anchor.quoted and '"d": "2026-06-01"' in anchor.quoted
        assert "advanced" in anchor.unit.lower() and "effective" in anchor.unit.lower()
        assert anchor.band[0] <= anchor.value <= anchor.band[1]
        assert "applies this to nothing" in anchor.rationale.lower()

    def test_insured_sits_below_uninsured_below_posted(self):
        insured = ANCHORS[self.INSURED].value
        uninsured = ANCHORS[self.UNINSURED].value
        assert insured < uninsured < ANCHORS["mortgage_rate.posted_5y"].value

    @pytest.mark.parametrize("name", [UNINSURED, INSURED])
    def test_the_restatement_is_the_effective_annual_rate(self, name):
        anchor = ANCHORS[name]
        (effective, why), = anchor.restatements
        assert effective == pytest.approx((1 + anchor.value / 2) ** 2 - 1, abs=1e-12)
        assert "semi-annually" in why.lower()

    def test_the_posted_rationale_names_them_and_repeats_no_figure(self):
        rationale = ANCHORS["mortgage_rate.posted_5y"].rationale
        assert self.UNINSURED in rationale and self.INSURED in rationale
        assert "4.35" not in rationale and "4.01" not in rationale

    @pytest.mark.parametrize("name", [UNINSURED, INSURED])
    def test_never_applied_as_an_engine_default(self, name):
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "down_payment": 120_000,
                      "mortgage_rate": 0.05, "mortgage_term_years": 25},
            "rent": {"monthly_rent": 2_000},
        })
        assert not any("mortgage_rate" in k for k in spec.defaults_applied)

    def test_a_sources_declaration_validates_the_published_or_effective_figure(self):
        anchor = ANCHORS[self.UNINSURED]
        for stated in anchor.stated_values():
            spec = load_config_dict({
                "years": 10,
                "house": {"initial_value": 600_000, "down_payment": 120_000,
                          "mortgage_rate": stated, "mortgage_term_years": 25},
                "rent": {"monthly_rent": 2_000},
                "sources": {"house.mortgage_rate": f"anchor:{self.UNINSURED}"},
            })
            assert spec.sources.anchor_name("house.mortgage_rate") == self.UNINSURED


# ---------------------------------------------------------------------------
# Routine maintenance (2026-09-04)
#
# `house.annual_maintenance_rate` is a deliberately uncited 0.0 whose rationale
# has always pointed at the NAHB figure. The figure is now its own reference
# entry, so a user who takes it has it cited by name.
# ---------------------------------------------------------------------------

class TestMaintenanceReference:
    NAME = "maintenance.nahb_routine"

    def test_registered_as_a_reference_with_the_fetched_table(self):
        anchor = ANCHORS[self.NAME]
        assert is_reference(self.NAME)
        assert anchor.value == 0.006
        assert anchor.url.startswith("https://www.nahb.org/")
        assert anchor.retrieved_on == "2026-09-04"
        assert "Table 2" in anchor.quoted and "All Homes 0.6" in anchor.quoted
        assert "routine" in anchor.unit.lower() and "excluding" in anchor.unit.lower()
        assert anchor.band == (0.002, 0.008)
        assert "applies this to nothing" in anchor.rationale.lower()

    def test_the_engine_default_stays_an_uncited_zero(self):
        default = ANCHORS["house.annual_maintenance_rate"]
        assert default.value == 0.0 and default.kind == "neutral"
        assert "NAHB" in default.rationale
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "all_cash": True},
            "rent": {"monthly_rent": 2_000},
        })
        assert spec.house.annual_maintenance_rate == 0.0
        assert not any(k.startswith("maintenance.") for k in spec.defaults_applied)

    def test_a_sources_declaration_validates_for_the_published_figure(self):
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "all_cash": True,
                      "annual_maintenance_rate": 0.006},
            "rent": {"monthly_rent": 2_000},
            "sources": {"house.annual_maintenance_rate": f"anchor:{self.NAME}"},
        })
        assert spec.sources.anchor_name("house.annual_maintenance_rate") == self.NAME
        assert any(self.NAME in line for line in format_assumptions(spec))

    def test_a_sources_declaration_is_refused_for_another_figure(self):
        from hde.config import ConfigValidationError
        with pytest.raises(ConfigValidationError, match=self.NAME):
            load_config_dict({
                "years": 10,
                "house": {"initial_value": 600_000, "all_cash": True,
                          "annual_maintenance_rate": 0.01},
                "rent": {"monthly_rent": 2_000},
                "sources": {"house.annual_maintenance_rate": f"anchor:{self.NAME}"},
            })
