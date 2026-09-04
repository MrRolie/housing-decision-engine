"""The land-transfer tax (Québec: droits sur les mutations immobilières).

Eight of eight real answers in the week to 2026-09-04 priced closing costs as a
1.5%-of-price guess labelled "no source". The transfer tax is the largest
one-time cost after the down payment and it is a PUBLISHED BRACKET SCHEDULE, so
the guess was never necessary. These tests are the contract:

1. Bracket arithmetic at every threshold edge, for all four fetched schedules,
   against the sources' own worked examples where they publish one.
2. A first-time-buyer rebate is capped at its maximum AND at the tax itself —
   a rebate never turns into a payment to the buyer.
3. `auto` without a province is refused; so is a municipality in the wrong
   province.
4. The tax is re-derived per grid point: a price sweep moves it.
5. Every anchor carries the fetched URL, the retrieval date and its bracket.
"""

import pytest

from hde.anchors import ANCHORS
from hde.config import ConfigValidationError, load_config_dict
from hde.land_transfer_tax import (
    LandTransferTaxError,
    anchored_schedules,
    resolve,
)
from hde.serialization import format_assumptions


# ---------------------------------------------------------------------------
# The published tables, transcribed from the fetched pages (2026-09-04).
# These literals are the ORACLE: the engine's schedules are built from the
# anchor registry, so a registry edit that drifts from the source fails here.
# ---------------------------------------------------------------------------

QC_BRACKETS = [(62_900.0, 0.005), (315_000.0, 0.010), (None, 0.015)]
MONTREAL_BRACKETS = [
    (62_900.0, 0.005), (315_000.0, 0.010), (552_300.0, 0.015),
    (1_104_700.0, 0.020), (2_136_500.0, 0.025), (3_113_000.0, 0.035),
    (None, 0.040),
]
ONTARIO_BRACKETS = [
    (55_000.0, 0.005), (250_000.0, 0.010), (400_000.0, 0.015),
    (2_000_000.0, 0.020), (None, 0.025),
]
TORONTO_BRACKETS = [
    (55_000.0, 0.005), (250_000.0, 0.010), (400_000.0, 0.015),
    (2_000_000.0, 0.020), (3_000_000.0, 0.025), (4_000_000.0, 0.0440),
    (5_000_000.0, 0.0545), (10_000_000.0, 0.0650), (20_000_000.0, 0.0755),
    (None, 0.0860),
]

PUBLISHED = {
    "land_transfer_tax.qc": QC_BRACKETS,
    "land_transfer_tax.montreal": MONTREAL_BRACKETS,
    "land_transfer_tax.ontario": ONTARIO_BRACKETS,
    "land_transfer_tax.toronto": TORONTO_BRACKETS,
}


def _reference_tax(brackets, base):
    """Independent bracket arithmetic — deliberately NOT the engine's loop."""
    total = 0.0
    lower = 0.0
    for up_to, rate in brackets:
        top = base if up_to is None else min(base, up_to)
        if top > lower:
            total += (top - lower) * rate
        lower = up_to if up_to is not None else base
        if up_to is not None and base <= up_to:
            break
    return total


def _schedule(province, municipality=None, first_time_buyer=False):
    return anchored_schedules(province, municipality)


def _tax(province, municipality, base):
    return sum(s.tax(base) for s in anchored_schedules(province, municipality))


# ---------------------------------------------------------------------------
# 1. Bracket arithmetic at every threshold edge
# ---------------------------------------------------------------------------

def _edges(brackets):
    """Every published threshold, a dollar under it and a dollar over it —
    a bracket schedule is a piecewise-linear function and its only interesting
    points are its knees."""
    out = [0.0, 1.0]
    for up_to, _rate in brackets:
        if up_to is None:
            continue
        out += [up_to - 1.0, up_to, up_to + 1.0, up_to + 0.01]
    out.append(max(e for e, _ in [(b, r) for b, r in brackets if b is not None]) * 2)
    return out


@pytest.mark.parametrize("province,municipality,name", [
    ("QC", None, "land_transfer_tax.qc"),
    ("QC", "montreal", "land_transfer_tax.montreal"),
    ("ON", None, "land_transfer_tax.ontario"),
])
def test_bracket_arithmetic_at_every_threshold_edge(province, municipality, name):
    brackets = PUBLISHED[name]
    for base in _edges(brackets):
        assert _tax(province, municipality, base) == pytest.approx(
            _reference_tax(brackets, base), abs=1e-6), (name, base)


def test_toronto_adds_its_municipal_schedule_to_the_provincial_one():
    """Toronto: 'MLTT ... has been applied to purchases on all properties in the
    City of Toronto IN ADDITION TO the Provincial Land Transfer Tax'. Montréal
    REPLACES the provincial schedule; Toronto stacks on it. Getting this
    backwards halves or doubles the largest one-time cost in the answer."""
    for base in _edges(TORONTO_BRACKETS):
        expected = (_reference_tax(ONTARIO_BRACKETS, base)
                    + _reference_tax(TORONTO_BRACKETS, base))
        assert _tax("ON", "toronto", base) == pytest.approx(expected, abs=1e-6), base


def test_quebec_worked_example_from_the_source():
    """quebec.ca prints the arithmetic for a $350,000 base: 315 $ + 2 521 $ +
    525 $ = 3 361 $ (its first term rounded from 314.50)."""
    assert _tax("QC", None, 350_000) == pytest.approx(3_360.50, abs=0.005)


def test_montreal_worked_example_from_the_source():
    """montreal.ca prints its own 2026 example for a $700,000 base and totals
    9 349,00 $ — an exact figure, so the engine must hit it exactly."""
    assert _tax("QC", "montreal", 700_000) == pytest.approx(9_349.00, abs=0.005)


def test_montreal_650k_house():
    """The dogfood case: a $650,000 Montréal house. 314.50 + 2,521 + 3,559.50
    + 1,954 = 8,349.00 — against the 1.5%-of-price guess ($9,750) the answers
    had been using."""
    assert _tax("QC", "montreal", 650_000) == pytest.approx(8_349.00, abs=0.005)


def test_ontario_top_bracket_is_the_single_family_residence_rate():
    """ontario.ca: 'amounts exceeding $2,000,000, where the land contains one
    or two single family residences: 2.5%'. The engine models a home purchase,
    so 2.5% is the rate above $2M."""
    base = 3_000_000
    expected = (55_000 * 0.005 + 195_000 * 0.010 + 150_000 * 0.015
                + 1_600_000 * 0.020 + 1_000_000 * 0.025)
    assert _tax("ON", None, base) == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# 2. The first-time-buyer rebate
# ---------------------------------------------------------------------------

def test_ontario_first_time_buyer_refund_is_capped_at_its_maximum():
    assert ANCHORS["land_transfer_tax.ontario.first_time_buyer_refund_max"].value == 4_000.0
    record = resolve(
        {"land_transfer_tax": "auto", "province": "ON", "first_time_buyer": True},
        "house", top_province=None, initial_value=800_000)[1]
    gross = _reference_tax(ONTARIO_BRACKETS, 800_000)
    assert record.gross == pytest.approx(gross, abs=1e-6)
    assert record.rebate == pytest.approx(4_000.0, abs=1e-6)
    assert record.total == pytest.approx(gross - 4_000.0, abs=1e-6)


def test_a_rebate_never_exceeds_the_tax_it_refunds():
    """A $150,000 Ontario purchase owes $1,225 — less than the $4,000 maximum.
    The refund is the tax, not the maximum: a transfer tax cannot go negative."""
    record = resolve(
        {"land_transfer_tax": "auto", "province": "ON", "first_time_buyer": True},
        "house", top_province=None, initial_value=150_000)[1]
    assert record.gross == pytest.approx(1_225.0, abs=1e-6)
    assert record.rebate == pytest.approx(1_225.0, abs=1e-6)
    assert record.total == pytest.approx(0.0, abs=1e-6)


def test_toronto_applies_both_rebates_each_capped_against_its_own_leg():
    assert ANCHORS["land_transfer_tax.toronto.first_time_buyer_rebate_max"].value == 4_475.0
    record = resolve(
        {"land_transfer_tax": "auto", "province": "ON", "municipality": "toronto",
         "first_time_buyer": True},
        "house", top_province=None, initial_value=900_000)[1]
    leg = _reference_tax(ONTARIO_BRACKETS, 900_000)
    assert record.gross == pytest.approx(leg * 2, abs=1e-6)
    assert record.rebate == pytest.approx(4_000.0 + 4_475.0, abs=1e-6)


def test_quebec_has_no_anchored_first_time_buyer_rebate_and_says_so():
    """No Québec transfer-duty first-time-buyer rebate was fetched, so the flag
    changes nothing and the record says the rebate is unanchored — never a
    silent zero that reads like 'there is none'."""
    record = resolve(
        {"land_transfer_tax": "auto", "province": "QC", "municipality": "montreal",
         "first_time_buyer": True},
        "house", top_province=None, initial_value=650_000)[1]
    assert record.rebate == 0.0
    assert record.total == pytest.approx(8_349.00, abs=0.005)
    assert not record.legs[0].rebate_anchored
    assert ANCHORS["land_transfer_tax.montreal.first_time_buyer_rebate"].value is None
    assert ANCHORS["land_transfer_tax.montreal.first_time_buyer_rebate"].kind == "unsourced"


# ---------------------------------------------------------------------------
# 3. Refusals
# ---------------------------------------------------------------------------

def test_auto_without_a_province_is_refused():
    with pytest.raises(LandTransferTaxError, match="needs a province"):
        resolve({"land_transfer_tax": "auto"}, "house",
                top_province=None, initial_value=650_000)


def test_auto_without_a_province_is_refused_through_the_loader():
    with pytest.raises(ConfigValidationError, match="needs a province"):
        load_config_dict({
            "years": 10,
            "house": {"initial_value": 650_000, "all_cash": True,
                      "land_transfer_tax": "auto"},
            "rent": {"monthly_rent": 2_000},
        })


def test_a_municipality_in_the_wrong_province_is_refused():
    with pytest.raises(LandTransferTaxError, match="toronto"):
        resolve({"land_transfer_tax": "auto", "province": "QC",
                 "municipality": "toronto"},
                "house", top_province=None, initial_value=650_000)
    with pytest.raises(LandTransferTaxError, match="montreal"):
        resolve({"land_transfer_tax": "auto", "province": "ON",
                 "municipality": "montreal"},
                "house", top_province=None, initial_value=650_000)


def test_a_province_with_no_anchored_schedule_is_refused_not_charged_zero():
    with pytest.raises(LandTransferTaxError, match="explicit"):
        resolve({"land_transfer_tax": "auto", "province": "other"},
                "house", top_province=None, initial_value=650_000)


def test_an_explicit_schedule_is_applied_verbatim():
    record = resolve(
        {"land_transfer_tax": {
            "brackets": [{"up_to": 100_000, "rate": 0.01}, {"rate": 0.02}],
            "first_time_buyer_rebate": 1_000},
         "first_time_buyer": True},
        "house", top_province=None, initial_value=300_000)[1]
    assert record.gross == pytest.approx(1_000 + 4_000, abs=1e-6)
    assert record.rebate == pytest.approx(1_000.0, abs=1e-6)


def test_an_explicit_schedule_needs_brackets():
    with pytest.raises(LandTransferTaxError, match="brackets"):
        resolve({"land_transfer_tax": {"first_time_buyer_rebate": 0}},
                "house", top_province=None, initial_value=300_000)


def test_none_is_the_default_and_prices_nothing():
    costs, record = resolve({}, "house", top_province=None, initial_value=650_000)
    assert record is None and costs == 0.0


# ---------------------------------------------------------------------------
# 4. Derived in the loader: it moves with the price, and it is cash
# ---------------------------------------------------------------------------

def _montreal_config(price, **house):
    block = {"initial_value": price, "down_payment": 200_000,
             "mortgage_rate": 0.045, "mortgage_term_years": 25,
             "land_transfer_tax": "auto", "municipality": "montreal"}
    block.update(house)
    return {"years": 10, "province": "QC",
            "house": block, "rent": {"monthly_rent": 2_500}}


def test_the_tax_is_added_to_purchase_costs():
    spec = load_config_dict(_montreal_config(650_000, purchase_costs=2_000))
    assert spec.house.purchase_costs == pytest.approx(2_000 + 8_349.00, abs=0.005)
    assert spec.house.land_transfer_tax.total == pytest.approx(8_349.00, abs=0.005)


def test_the_tax_is_added_on_top_of_a_purchase_costs_rate():
    spec = load_config_dict(_montreal_config(650_000, purchase_costs_rate=0.01))
    assert spec.house.purchase_costs == pytest.approx(6_500 + 8_349.00, abs=0.005)


def test_the_tax_is_netted_out_of_cash_available():
    cfg = _montreal_config(650_000, purchase_costs=2_000)
    cfg["house"].pop("down_payment")
    cfg["house"]["cash_available"] = 150_000
    spec = load_config_dict(cfg)
    assert spec.house.down_payment == pytest.approx(150_000 - 2_000 - 8_349.00, abs=0.005)


def test_it_is_re_derived_at_every_price_a_scan_tries():
    """A price scan re-runs the loader per grid point. Two prices that straddle
    Montréal's $552,300 knee must not share one tax: 540,000 sits in the 1.5%
    band and 650,000 reaches the 2% band."""
    low = load_config_dict(_montreal_config(540_000)).house
    high = load_config_dict(_montreal_config(650_000)).house
    assert low.land_transfer_tax.total == pytest.approx(
        _reference_tax(MONTREAL_BRACKETS, 540_000), abs=1e-6)
    assert high.land_transfer_tax.total == pytest.approx(
        _reference_tax(MONTREAL_BRACKETS, 650_000), abs=1e-6)
    assert high.land_transfer_tax.total > low.land_transfer_tax.total
    # and the derived cash cost moved with it, not with the seed price
    assert high.purchase_costs - low.purchase_costs == pytest.approx(
        high.land_transfer_tax.total - low.land_transfer_tax.total, abs=1e-6)


def test_an_all_cash_purchase_still_pays_the_welcome_tax():
    cfg = _montreal_config(650_000)
    cfg["house"].pop("down_payment")
    cfg["house"].pop("mortgage_rate")
    cfg["house"].pop("mortgage_term_years")
    cfg["house"]["all_cash"] = True
    spec = load_config_dict(cfg)
    assert spec.house.land_transfer_tax.total == pytest.approx(8_349.00, abs=0.005)


# ---------------------------------------------------------------------------
# 5. The read-back
# ---------------------------------------------------------------------------

def _purchase_costs_line(spec):
    return next(line for line in format_assumptions(spec)
                if line.startswith("house purchase costs:"))


def test_the_read_back_names_the_schedule_and_the_tax():
    spec = load_config_dict(_montreal_config(650_000))
    line = _purchase_costs_line(spec)
    assert "$8,349" in line
    assert "Montréal" in line
    assert "first-time" in line


def test_the_read_back_shows_the_rebate_it_applied():
    cfg = {"years": 10, "province": "ON",
           "house": {"initial_value": 900_000, "all_cash": True,
                     "land_transfer_tax": "auto", "municipality": "toronto",
                     "first_time_buyer": True},
           "rent": {"monthly_rent": 2_500}}
    line = _purchase_costs_line(load_config_dict(cfg))
    assert "Ontario" in line and "Toronto" in line
    assert "$4,000" in line and "$4,475" in line


def test_an_all_cash_option_still_gets_a_purchase_costs_line():
    """The financing line is skipped for an all-cash buyer, who pays the
    welcome tax all the same — which is why the tax has its own line."""
    cfg = _montreal_config(650_000)
    cfg["house"].pop("down_payment")
    cfg["house"].pop("mortgage_rate")
    cfg["house"].pop("mortgage_term_years")
    cfg["house"]["all_cash"] = True
    lines = format_assumptions(load_config_dict(cfg))
    assert not any(line.startswith("house financing:") for line in lines)
    assert any(line.startswith("house purchase costs:") for line in lines)


def test_the_source_echo_calls_an_auto_tax_anchor_sourced():
    cfg = _montreal_config(650_000)
    cfg["sources"] = {"house.initial_value": "user"}
    spec = load_config_dict(cfg)
    entry = spec.sources.get("house.land_transfer_tax")
    assert entry.source == "anchor"
    assert "land_transfer_tax.montreal" in entry.anchor
    line = next(line for line in format_assumptions(spec)
                if line.startswith("anchor-sourced:"))
    assert "house.land_transfer_tax" in line


def test_a_user_declared_source_still_wins_over_the_derived_one():
    cfg = _montreal_config(650_000)
    cfg["sources"] = {"house.land_transfer_tax": "assistant"}
    spec = load_config_dict(cfg)
    assert spec.sources.classify("house.land_transfer_tax") == "assistant"


def test_the_missing_purchase_costs_warning_is_not_silenced_by_the_tax():
    """The transfer tax is priced; notary and inspection are still nobody's
    number. A derived tax must not read as 'purchase costs are modelled'."""
    from hde.config import coherence_warnings
    spec = load_config_dict(_montreal_config(650_000))
    warns = coherence_warnings(spec)
    assert any("notary" in w for w in warns), warns


# ---------------------------------------------------------------------------
# 6. The anchors themselves
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("family,brackets", sorted(PUBLISHED.items()))
def test_every_bracket_is_an_anchor_carrying_url_date_and_threshold(family, brackets):
    entries = {name: a for name, a in ANCHORS.items()
               if name.startswith(f"{family}.") and a.kind != "unsourced"
               and "rebate" not in name and "refund" not in name}
    assert len(entries) == len(brackets), (family, sorted(entries))
    for name, anchor in entries.items():
        assert anchor.url.startswith("http"), name
        assert anchor.retrieved_on == "2026-09-04", name
        assert anchor.quoted.strip(), name
        assert anchor.unit.strip(), name
        assert anchor.band == (anchor.value, anchor.value), name
    # the thresholds live in the anchor NAMES, so --print-anchors alone shows
    # the whole schedule: every edge, and one uncapped top band.
    named = [(None if n.rsplit(".", 1)[-1].startswith("over_")
              else float(n.rsplit("_", 1)[-1]))
             for n in entries]
    named.sort(key=lambda v: (v is None, v))
    assert named == [b for b, _ in brackets]


def test_the_rebate_anchors_carry_their_maximum_and_a_source():
    for name in ("land_transfer_tax.ontario.first_time_buyer_refund_max",
                 "land_transfer_tax.toronto.first_time_buyer_rebate_max"):
        anchor = ANCHORS[name]
        assert anchor.url.startswith("http"), name
        assert anchor.retrieved_on == "2026-09-04", name
        assert anchor.value > 0


def test_unsourced_rebates_report_the_absence_rather_than_a_zero():
    for name in ("land_transfer_tax.qc.first_time_buyer_rebate",
                 "land_transfer_tax.montreal.first_time_buyer_rebate"):
        anchor = ANCHORS[name]
        assert anchor.kind == "unsourced" and anchor.value is None, name
        assert anchor.short_cite.startswith("source: none"), name
