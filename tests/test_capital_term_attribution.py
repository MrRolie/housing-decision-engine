"""Which cause the renter's capital term HAS, said in the sentence itself.

The capital-term warning's guard is a disjunction — a spread between
`investment_return_rate` and `discount_rate`, OR the tax a `tax:` block charges
on the same money — and until 2026-09-21 one sentence served both branches: it
described the spread and prescribed the spread's remedy whichever cause had
fired. On a tax-only run it printed two equal rates and told the reader to make
them equal, on a term that reached 96% of a served verdict's margin. A reader
who followed it did something futile and watched the answer not move.

Every assertion here is on the RENDERED string, presence and absence both. The
components were always computable from `RenterTerminal`; what was wrong was the
sentence, so the sentence is what is pinned. The dollar split is asserted
against the ONE terminal-value computation every surface reads
(`renter_terminal_for`), never against a second arithmetic written here.
"""

import copy
from pathlib import Path

import pytest
import yaml

from hde.config import coherence_warnings, load_config_dict
from hde.deterministic import renter_terminal_for

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

PI = 0.021
BASE = {
    "years": 10,
    "province": "QC",
    "economic": {"mode": "nominal", "inflation_rate": PI},
    "rent": {"monthly_rent": 1_850, "invested_down_payment": 60_000,
             "investment_return_rate": 0.051},
    "income": {"annual_income": 95_000},
    "simulation": {"num_sims": 20, "random_seed": 7},
}
# No FHSA share: the haircut leg is absent and must not be named.
SPLIT = {"tfsa": 25_000, "rrsp": 20_000, "fhsa": 0, "taxable": 15_000}
# An FHSA share, derived from the plan below, so both tax legs are live.
FHSA_SPLIT = {"tfsa": 11_000, "rrsp": 20_000, "taxable": 15_000}
FHSA = {"balance": 8_000, "annual_contribution": 8_000, "years_until_purchase": 1}
CONDO = {"initial_value": 450_000, "monthly_fee": 380, "cash_available": 60_000,
         "mortgage_rate": 0.0455, "mortgage_term_years": 25, "purchase_costs": 6_000,
         "first_time_buyer": True}

# The remedy the one-sentence version prescribed on every branch.
RATE_REMEDY = "set investment_return_rate = discount_rate for a neutral comparison"


def cfg(**top):
    doc = copy.deepcopy(BASE)
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(doc.get(key), dict):
            doc[key] = {**doc[key], **copy.deepcopy(value)}
        else:
            doc[key] = copy.deepcopy(value)
    return doc


def capital_warning(doc):
    """The capital-term warning, and only it: the no-tax-block warning shares
    its `rent: invested capital` prefix."""
    spec = load_config_dict(doc)
    hits = [w for w in coherence_warnings(spec)
            if w.startswith("rent: invested capital") and "vs discount_rate" in w]
    assert len(hits) == 1, hits
    return hits[0]


# --- the fixtures, by which cause fires -------------------------------------

def spread_only():
    """A rate spread and no `tax:` block at all."""
    return cfg(discount_rate=0.05, rent={"investment_return_rate": 0.06})


def tax_only():
    """The two rates typed equal, a taxable share, no FHSA: drag alone."""
    return cfg(discount_rate=0.051, tax={"renter_capital": SPLIT})


def tax_only_with_fhsa():
    """The two rates typed equal, both tax legs live."""
    return cfg(discount_rate=0.051, condo=CONDO,
               rent={"invested_down_payment": 62_000},
               tax={"renter_capital": FHSA_SPLIT, "fhsa": FHSA})


def both_causes():
    """A spread AND a taxable share, no FHSA."""
    return cfg(discount_rate=0.055, tax={"renter_capital": SPLIT})


def both_causes_with_fhsa():
    """A spread AND both tax legs."""
    return cfg(discount_rate=0.055, condo=CONDO,
               rent={"invested_down_payment": 62_000},
               tax={"renter_capital": FHSA_SPLIT, "fhsa": FHSA})


class TestTheThreeStates:
    def test_a_rate_spread_alone_keeps_the_sentence_it_always_had(self):
        assert capital_warning(spread_only()) == (
            "rent: invested capital $60,000 earns 6.0% vs discount_rate 5.0% — net capital "
            "term $5,966 credited to the renter over 10 years; set investment_return_rate = "
            "discount_rate for a neutral comparison or keep the spread deliberately")

    def test_tax_alone_says_the_rate_remedy_changes_nothing(self):
        warning = capital_warning(tax_only())
        assert warning == (
            "rent: invested capital $60,000 earns 5.1% (after tax on the taxable share: "
            "blended 4.88%) vs discount_rate 5.1% — net capital term $1,264 charged to the "
            "renter over 10 years; the rate spread carries none of it, so setting "
            "investment_return_rate = discount_rate changes nothing here — the whole term is "
            "the tax the engine charged: $1,264 of drag on the taxable share "
            "(lever: tax.renter_capital)")
        # the remedy that cannot work is gone, and so is the claim of a spread
        assert RATE_REMEDY not in warning
        assert "keep the spread deliberately" not in warning

    def test_tax_alone_names_only_the_legs_that_move_a_dollar(self):
        # no FHSA share ⇒ no haircut ⇒ the haircut leg is not named at $0
        assert "FHSA rollover haircut" not in capital_warning(tax_only())
        assert "FHSA rollover haircut" in capital_warning(tax_only_with_fhsa())

    def test_tax_alone_splits_the_two_legs_and_their_levers(self):
        assert capital_warning(tax_only_with_fhsa()) == (
            "rent: invested capital $64,889 earns 5.1% (after tax on the taxable share and "
            "the FHSA rollover: blended 3.86%) vs discount_rate 5.1% — net capital term "
            "$7,286 charged to the renter over 10 years; the rate spread carries none of it, "
            "so setting investment_return_rate = discount_rate changes nothing here — the "
            "whole term is the tax the engine charged: $1,507 of drag on the taxable share "
            "(lever: tax.renter_capital) and $5,779 of FHSA rollover haircut "
            "(lever: tax.retirement_marginal_rate)")

    def test_both_causes_are_split_in_dollars_with_a_remedy_each(self):
        warning = capital_warning(both_causes())
        assert warning == (
            "rent: invested capital $60,000 earns 5.1% (after tax on the taxable share: "
            "blended 4.88%) vs discount_rate 5.5% — net capital term $3,453 charged to the "
            "renter over 10 years; two causes, and fixing one moves only its own share: "
            "$2,236 charged by the spread between the two rates, which investment_return_rate "
            "= discount_rate removes, and $1,217 charged by the tax the engine applied — "
            "$1,217 of drag on the taxable share (lever: tax.renter_capital)")

    def test_both_causes_with_an_fhsa_name_three_dollar_figures(self):
        assert capital_warning(both_causes_with_fhsa()) == (
            "rent: invested capital $64,889 earns 5.1% (after tax on the taxable share and "
            "the FHSA rollover: blended 3.86%) vs discount_rate 5.5% — net capital term "
            "$9,433 charged to the renter over 10 years; two causes, and fixing one moves "
            "only its own share: $2,419 charged by the spread between the two rates, which "
            "investment_return_rate = discount_rate removes, and $7,014 charged by the tax "
            "the engine applied — $1,451 of drag on the taxable share "
            "(lever: tax.renter_capital) and $5,563 of FHSA rollover haircut "
            "(lever: tax.retirement_marginal_rate)")

    @pytest.mark.parametrize("doc_of", [tax_only, tax_only_with_fhsa])
    def test_a_tax_only_run_never_prescribes_the_rate_change(self, doc_of):
        assert RATE_REMEDY not in capital_warning(doc_of())

    @pytest.mark.parametrize("doc_of", [both_causes, both_causes_with_fhsa])
    def test_a_both_run_names_the_tax_as_well_as_the_spread(self, doc_of):
        warning = capital_warning(doc_of())
        assert "the spread between the two rates" in warning
        assert "tax.renter_capital" in warning


class TestTheSplitComesFromTheOneComputation:
    """The two components must sum to the net the sentence prints, and the tax
    component must BE the drag and the haircut the engine already computed —
    otherwise the split is a second home for the renter's capital."""

    @pytest.mark.parametrize(
        "doc_of", [spread_only, tax_only, tax_only_with_fhsa, both_causes, both_causes_with_fhsa])
    def test_spread_plus_tax_is_the_net_and_the_tax_part_is_drag_plus_haircut(self, doc_of):
        spec = load_config_dict(doc_of())
        terminal = renter_terminal_for(spec)
        dr, n = spec.simulation.discount_rate, spec.simulation.years
        disc = (1 + dr) ** n
        net = terminal.capital - terminal.value / disc
        spread = terminal.capital - terminal.untaxed_value / disc
        assert net - spread == pytest.approx((terminal.drag + terminal.haircut) / disc, abs=1e-6)

    def test_an_untaxed_run_has_no_tax_component_at_all(self):
        spec = load_config_dict(spread_only())
        terminal = renter_terminal_for(spec)
        assert terminal.untaxed_value == pytest.approx(terminal.value)
        assert terminal.drag == 0.0 and terminal.haircut == 0.0


class TestRatesThatRoundAlike:
    """Two rates 3.7 basis points apart both render "5.2%" at one decimal. The
    sentence then showed equal rates and named a spread between them — and the
    reviewer's four households all landed here, because the DEFAULT discount
    rate composes to 5.163% while a typed 5.2% quote stays 5.200%."""

    def reviewers_household(self):
        doc = yaml.safe_load((EXAMPLES / "first_time_buyer_montreal.yaml").read_text(
            encoding="utf-8"))
        doc["rent"]["investment_return_rate"] = 0.052
        # the anchor declaration is about the 5.1% figure, not this one
        doc["sources"]["rent.investment_return_rate"] = "user"
        return doc

    def test_the_exact_figures_are_named_when_the_labels_collide(self):
        warning = capital_warning(self.reviewers_household())
        assert "vs discount_rate 5.2% (the two round alike: 5.200% against 5.163%)" in warning

    def test_the_reviewers_household_reads_as_a_both_run(self):
        assert capital_warning(self.reviewers_household()) == (
            "rent: invested capital $77,889 earns 5.2% (after tax on the taxable share and "
            "the FHSA rollover: blended 4.18%) vs discount_rate 5.2% (the two round alike: "
            "5.200% against 5.163%) — net capital term $6,978 charged to the renter over 10 "
            "years; two causes, and fixing one moves only its own share: $274 credited by the "
            "spread between the two rates, which investment_return_rate = discount_rate "
            "removes, and $7,253 charged by the tax the engine applied — $1,454 of drag on "
            "the taxable share (lever: tax.renter_capital) and $5,799 of FHSA rollover "
            "haircut (lever: tax.retirement_marginal_rate)")

    def test_labels_that_differ_carry_no_disambiguation(self):
        assert "round alike" not in capital_warning(spread_only())
        assert "round alike" not in capital_warning(both_causes())

    def test_the_shipped_example_itself_names_both_causes(self):
        doc = yaml.safe_load((EXAMPLES / "first_time_buyer_montreal.yaml").read_text(
            encoding="utf-8"))
        warning = capital_warning(doc)
        assert "two causes, and fixing one moves only its own share" in warning
        assert "of FHSA rollover haircut (lever: tax.retirement_marginal_rate)" in warning


class TestSilence:
    def test_a_sub_dollar_term_says_nothing_at_all(self):
        """The old guard fired on any non-zero rate difference, so a spread
        worth fractions of a cent rendered "net capital term $0". The gate is
        the dollars the sentence claims, not the rates behind them."""
        doc = cfg(discount_rate=0.051, rent={"investment_return_rate": 0.051})
        spec = load_config_dict(doc)
        assert not [w for w in coherence_warnings(spec)
                    if w.startswith("rent: invested capital") and "vs discount_rate" in w]

    def test_a_rate_difference_too_small_to_be_a_dollar_says_nothing(self):
        """The fixture that separates the two gates. A tenth of a nanopoint
        clears the old 1e-12 test on the RATES and is worth $0.00006 on
        $60,000 over ten years, so the old guard fired and printed "net
        capital term $0 credited to the renter" with a remedy attached. The
        gate is the dollars, so this is silent."""
        doc = cfg(discount_rate=0.051, rent={"investment_return_rate": 0.0510000001})
        spec = load_config_dict(doc)
        r_inv = (1 + spec.rent.investment_return_rate) * (1 + PI) - 1
        # the rates DO differ by more than the tolerance the old guard used
        assert abs(r_inv - spec.simulation.discount_rate) > 1e-12
        terminal = renter_terminal_for(spec)
        disc = (1 + spec.simulation.discount_rate) ** spec.simulation.years
        assert abs(terminal.capital - terminal.value / disc) < 0.5
        assert not [w for w in coherence_warnings(spec)
                    if w.startswith("rent: invested capital") and "vs discount_rate" in w]

    def test_no_renter_capital_no_sentence(self):
        doc = cfg(rent={"invested_down_payment": 0})
        spec = load_config_dict(doc)
        assert not [w for w in coherence_warnings(spec) if "vs discount_rate" in w]
