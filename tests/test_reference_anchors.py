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
                   short_cite="s", retrieved_on="2026-09-03", quoted="1.0%")

    def test_construction_refuses_a_reference_entry_without_the_quoted_figure(self):
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=0.01, as_of="2026", source="s",
                   url="https://example.org", rationale="r", band=(0.0, 0.02),
                   short_cite="s", retrieved_on="2026-09-03",
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
            kind="unsourced",
        )

    def test_an_unsourced_entry_holds_no_value(self):
        assert self._unsourced().value is None

    def test_unsourced_entries_must_say_what_was_tried(self):
        with pytest.raises(AnchorError):
            Anchor(name="property_tax.nowhere", value=None, as_of="2026",
                   source="none", url="none", rationale="r", band=(0.0, 0.0),
                   short_cite="source: none", kind="unsourced")

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
