"""The unpriced channel, slice 1: the minimum qualifying rate on the
affordability line (docs/specs/2026-09-21-unpriced-dimensions.md §14, §16).

WHAT EACH CLASS BELOW IS GUARDING, so a later reader can tell a test that can
fail from one that cannot:

- `TestTheGuard` — spec §5, the reason this channel is honest at all: the same
  feature must be able to print NOTHING. Every silent case here is reached by a
  MINIMAL difference from a printing one, so "silent" can never be an artifact
  of an unrelated broken config.
- `TestTheAxis` — the spread lands on the AS-QUOTED axis and
  `mortgage_rate_compounding` converts the sum. The wrong axis is a 5.5bp error
  at a 4.5% quote, which ROUNDS AWAY at the line's `.1%` ratio formatting, so
  every assertion here is on floats against a HAND-COMPUTED oracle built from
  `pv.mortgage_payment` — never against a second call to the code under test.
- `TestBothLegs` — the greater-of has two legs and the crossover is arithmetic.
- `TestTheRegistry` — the stored rule and the printed rule are one rule.
- `TestWhatItMayNeverSay` — the line reports a ratio on the ENGINE's numerator
  and never rules on whether a lender would lend.
"""

import sys

import pytest

from hde.anchors import (
    ANCHORS,
    MQR_B20_STILL_APPLIES,
    MQR_INSURED_SWITCH_EFFECTIVE,
    MQR_RULE,
    MQR_STRAIGHT_SWITCH,
    MQR_STRAIGHT_SWITCH_EFFECTIVE,
    is_reference,
)
from hde.cli import main as cli_main
from hde.config import coherence_warnings, load_config_dict
from hde.deterministic import compute_deterministic
from hde.pv import mortgage_payment
from hde.rates import effective_mortgage_rate
from hde.serialization import read_back_lines
from hde.unpriced import (
    NEUTRAL,
    TOWARD_BUYING,
    TOWARD_RENTING,
    UNPRICED_LINE_CAP,
    qualifying_loads,
    qualifying_rate_quoted,
    unpriced_warnings,
)

BUFFER = ANCHORS["qualifying_rate.buffer"].value
FLOOR = ANCHORS["qualifying_rate.floor"].value

INCOME = 120_000.0


def cfg(
    *,
    income=True,
    all_cash=False,
    down_payment=120_000,
    mortgage_rate=0.045,
    compounding="semi_annual",
    initial_value=600_000,
    term=25,
    pay_drop_events=None,
):
    """A house-and-rent config whose year-1 affordability numerator is the
    mortgage payment ALONE: no condo fee, no events, no other recurring costs,
    and `house.annual_maintenance_rate` at its uncited 0.0 default. That is
    what makes the hand oracle in `TestTheAxis` exact rather than approximate.
    """
    house = {"initial_value": initial_value, "value_growth_rate": 0.0}
    if all_cash:
        house["all_cash"] = True
    else:
        house.update({"down_payment": down_payment, "mortgage_rate": mortgage_rate,
                      "mortgage_rate_compounding": compounding,
                      "mortgage_term_years": term})
    data = {
        "years": 10,
        "rates": "real",
        "house": house,
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                 "invested_down_payment": 120_000, "investment_return_rate": 0.03},
    }
    if income:
        block = {"annual_income": INCOME, "income_growth_rate": 0.0}
        if pay_drop_events:
            block["pay_drop_events"] = pay_drop_events
        data["income"] = block
    return data


def ladder_cfg(*, years=10, renewal_years=5, insured=False, rates=(0.06,), **kw):
    """The printing config with a renewal ladder stated on the house.

    `renewal_years` and `years` are what move the clause: a renewal inside the
    horizon is a transaction this run PRICES, and one past it is not.
    """
    data = insured_cfg(**kw) if insured else cfg(**kw)
    data["house"]["mortgage_renewal_years"] = renewal_years
    data["house"]["mortgage_renewal_rates"] = list(rates)
    data["years"] = years
    return data


def insured_cfg(down_payment=60_000):
    """A Québec purchase under 20% down, so the loader derives the CMHC tier
    and `mortgage_insurance.required` is True — the case OSFI's rule does NOT
    govern."""
    data = cfg(down_payment=down_payment, initial_value=600_000)
    data["province"] = "QC"
    data["house"]["mortgage_insurance"] = "auto"
    return data


def loads(data):
    spec = load_config_dict(data)
    return qualifying_loads(spec, compute_deterministic(spec), data)


def lines(data):
    spec = load_config_dict(data)
    return unpriced_warnings(spec, compute_deterministic(spec), data)


# ---------------------------------------------------------------------------
# Spec §5: the line prints a number solved from this run, and the same feature
# must be able to print NOTHING.
# ---------------------------------------------------------------------------

class TestTheGuard:
    def test_it_prints_on_a_financed_run_with_income(self):
        """The printing half of every pair below — if this ever goes silent,
        the silences stop meaning anything."""
        assert len(loads(cfg())) == 1
        assert lines(cfg())[0].startswith("house: unpriced — ")

    def test_two_configs_differing_only_in_the_income_block(self):
        """Spec §5's first pinning assertion, in this slice's terms: one
        prints, one is silent, and NOTHING else differs between them."""
        with_income, without = cfg(income=True), cfg(income=False)
        assert with_income.pop("income")
        assert with_income == without, "the pair must differ in the income block alone"
        assert lines(cfg(income=True)) != []
        assert lines(cfg(income=False)) == []

    def test_an_all_cash_purchase_is_silent(self):
        """No mortgage, so no rate a lender would test — and the engine says
        nothing rather than inventing a loan to stress."""
        assert lines(cfg(all_cash=True)) == []

    def test_a_spec_with_no_rate_on_the_quoted_axis_refuses(self):
        """A spec built in code carries no `mortgage_rate_quoted`: the run
        cannot establish which axis the rate is on, and the spread is defined
        on the quoted one. A surface that cannot verify REFUSES."""
        data = cfg()
        spec = load_config_dict(data)
        spec.house.mortgage_rate_quoted = None
        assert qualifying_loads(spec, compute_deterministic(spec), data) == []

    def test_without_the_raw_mapping_it_refuses(self):
        """The counterfactual is a reload of the user's own config; with no
        config to reload there is no measurement to print."""
        spec = load_config_dict(cfg())
        assert qualifying_loads(spec, compute_deterministic(spec), None) == []

    def test_two_configs_differing_only_in_loan_size_both_print_different_figures(self):
        """Spec §5's second pinning assertion, verbatim. If the line ever
        becomes text, these two are identical and this test says so."""
        small, big = cfg(down_payment=200_000), cfg(down_payment=120_000)
        assert {k: v for k, v in small["house"].items() if k != "down_payment"} == \
               {k: v for k, v in big["house"].items() if k != "down_payment"}
        [a], [b] = loads(small), loads(big)
        assert a.qualifying_ratio_year1 < b.qualifying_ratio_year1
        assert lines(small)[0] != lines(big)[0]

    def test_the_cap_bounds_the_channel(self):
        data = cfg()
        data["condo"] = {"initial_value": 400_000, "monthly_fee": 300,
                         "value_growth_rate": 0.0, "down_payment": 100_000,
                         "mortgage_rate": 0.045, "mortgage_term_years": 25}
        assert len(loads(data)) == 2 == UNPRICED_LINE_CAP

    def test_the_bigger_load_leads(self):
        """Spec §4, promotion: these lines' size is in points of income, so the
        verdict's PV margin cannot rank them and the size that exists does."""
        data = cfg()
        data["condo"] = {"initial_value": 200_000, "monthly_fee": 100,
                         "value_growth_rate": 0.0, "down_payment": 60_000,
                         "mortgage_rate": 0.045, "mortgage_term_years": 25}
        got = loads(data)
        assert [load.option for load in got] == ["house", "condo"]
        assert got[0].lift > got[1].lift


# ---------------------------------------------------------------------------
# §14: the spread lands on the AS-QUOTED axis, which `mortgage_rate_compounding`
# then converts — it must NEVER be added to an effective-annual figure.
# ---------------------------------------------------------------------------

class TestTheAxis:
    QUOTED = 0.045
    LOAN = 600_000 - 120_000

    def _oracle(self, effective_rate):
        """Year-1 housing cost over year-1 income, computed here from the
        mortgage formula — NOT from another call to the engine. The config has
        no fee, no maintenance, no event and no other recurring cost, so the
        year-1 numerator is the level payment and nothing else."""
        return mortgage_payment(self.LOAN, effective_rate, 25) / INCOME

    def test_the_sum_is_converted_not_the_contract_rate_alone(self):
        [load] = loads(cfg(mortgage_rate=self.QUOTED, compounding="semi_annual"))
        right = effective_mortgage_rate(self.QUOTED + BUFFER, "semi_annual")
        wrong = effective_mortgage_rate(self.QUOTED, "semi_annual") + BUFFER
        assert right != pytest.approx(wrong, abs=1e-6), "the two axes must be distinguishable"
        assert load.qualifying_quoted == pytest.approx(self.QUOTED + BUFFER, abs=1e-15)
        assert load.qualifying_effective == pytest.approx(right, abs=1e-15)
        # The RATIO — what the reader actually sees — is the one at the
        # correctly converted rate, and provably not the one at the wrong axis.
        assert load.qualifying_ratio_year1 == pytest.approx(self._oracle(right), abs=1e-12)
        assert load.qualifying_ratio_year1 != pytest.approx(self._oracle(wrong), abs=1e-9)

    def test_an_effective_annual_quote_is_loaded_as_typed(self):
        """`effective_annual` says the figure IS the rate the payment uses, so
        the qualifying rate is the sum with no conversion."""
        [load] = loads(cfg(mortgage_rate=self.QUOTED, compounding="effective_annual"))
        assert load.qualifying_effective == pytest.approx(self.QUOTED + BUFFER, abs=1e-15)
        assert load.qualifying_ratio_year1 == pytest.approx(
            self._oracle(self.QUOTED + BUFFER), abs=1e-12)

    def test_the_two_conventions_give_different_tested_ratios(self):
        """The same typed figure under the two conventions must not produce the
        same tested ratio — if it does, the conversion is not being applied."""
        [semi] = loads(cfg(mortgage_rate=self.QUOTED, compounding="semi_annual"))
        [eff] = loads(cfg(mortgage_rate=self.QUOTED, compounding="effective_annual"))
        assert semi.qualifying_ratio_year1 > eff.qualifying_ratio_year1

    def test_the_run_s_own_ratio_is_the_contract_rate_s(self):
        """The other half of the comparison is the engine's own figure, at the
        contract rate — not a second stressed number."""
        [load] = loads(cfg(mortgage_rate=self.QUOTED, compounding="semi_annual"))
        assert load.own_ratio_year1 == pytest.approx(
            self._oracle(effective_mortgage_rate(self.QUOTED, "semi_annual")), abs=1e-12)
        assert load.lift > 0

    def test_the_ratio_is_year_one_not_the_horizon_maximum(self):
        """The MQR is an ORIGINATION test. A pay drop in year 5 makes the
        horizon maximum a later year's; the line must still be year 1's, or it
        would attribute to the qualifying rate a peak an income shock put
        there."""
        data = cfg(mortgage_rate=self.QUOTED, pay_drop_events=[{"year": 5, "magnitude": 0.5}])
        [load] = loads(data)
        report = compute_deterministic(load_config_dict(data)).income_report
        assert max(report.house_ratios) > report.house_ratios[0], "the peak must not be year 1"
        assert load.own_ratio_year1 == pytest.approx(report.house_ratios[0], abs=1e-15)
        assert load.qualifying_ratio_year1 == pytest.approx(
            self._oracle(effective_mortgage_rate(self.QUOTED + BUFFER, "semi_annual")),
            abs=1e-12)


# ---------------------------------------------------------------------------
# The greater-of has two legs, and which one binds is arithmetic.
# ---------------------------------------------------------------------------

class TestBothLegs:
    def test_the_buffer_binds_above_the_crossover(self):
        assert qualifying_rate_quoted(0.05) == pytest.approx(0.07, abs=1e-15)
        [load] = loads(cfg(mortgage_rate=0.05))
        assert load.qualifying_quoted == pytest.approx(0.07, abs=1e-15)

    def test_the_floor_binds_below_the_crossover(self):
        assert qualifying_rate_quoted(0.03) == pytest.approx(FLOOR, abs=1e-15)
        [load] = loads(cfg(mortgage_rate=0.03))
        assert load.qualifying_quoted == pytest.approx(FLOOR, abs=1e-15)
        # and it is strictly above what the buffer leg alone would give
        assert load.qualifying_quoted > 0.03 + BUFFER

    def test_the_crossover_is_the_floor_minus_the_buffer(self):
        crossover = FLOOR - BUFFER
        assert crossover == pytest.approx(0.0325, abs=1e-15)
        assert qualifying_rate_quoted(crossover) == pytest.approx(FLOOR, abs=1e-15)
        # a hair either side picks the other leg
        assert qualifying_rate_quoted(crossover - 0.001) == pytest.approx(FLOOR, abs=1e-15)
        assert qualifying_rate_quoted(crossover + 0.001) == pytest.approx(
            crossover + 0.001 + BUFFER, abs=1e-15)

    def test_a_zero_rate_still_tests_at_the_floor(self):
        assert qualifying_rate_quoted(0.0) == pytest.approx(FLOOR, abs=1e-15)


# ---------------------------------------------------------------------------
# The stored rule and the printed rule are ONE rule.
# ---------------------------------------------------------------------------

class TestTheRegistry:
    def test_both_legs_quote_the_whole_greater_of_rule(self):
        for name in ("qualifying_rate.buffer", "qualifying_rate.floor"):
            anchor = ANCHORS[name]
            assert MQR_RULE in anchor.quoted, name
            assert MQR_RULE in anchor.rationale, name
            assert anchor.url.startswith("https://www.osfi-bsif.gc.ca/"), name
            assert anchor.retrieved_on == "2026-09-21", name

    def test_the_stored_figures_are_the_ones_the_printed_rule_states(self):
        """The alarm on the two homes: the line prints `MQR_RULE` verbatim while
        the engine computes from the anchor values, so a value edited without
        the sentence (or the reverse) would have the run state one rule and
        apply another. This is what turns that into a failure."""
        assert f"{BUFFER:.0%}" in MQR_RULE
        assert f"{FLOOR:.2%}" in MQR_RULE

    def test_the_floor_rationale_records_where_its_leg_stops_binding(self):
        """Derived from the two stored figures, not typed here: an edit to
        either leg that leaves the rationale's crossover stale lands on this
        assertion, which is the only thing that keeps the prose true."""
        crossover = FLOOR - BUFFER
        assert f"{crossover:.2%}" in ANCHORS["qualifying_rate.floor"].rationale
        assert qualifying_rate_quoted(crossover) == pytest.approx(FLOOR, abs=1e-15)
        assert qualifying_rate_quoted(crossover + 1e-6) > FLOOR

    def test_neither_leg_carries_a_validity_date(self):
        """`valid_until` is set only where the SOURCE states when the figure
        changes; OSFI states no such date for the MQR."""
        for name in ("qualifying_rate.buffer", "qualifying_rate.floor"):
            assert ANCHORS[name].valid_until == "", name

    def test_it_is_not_in_the_family_of_rates_a_borrower_can_be_charged(self):
        """Spec §14: a TEST threshold in a row of prices gets read as a price
        whatever the label says."""
        for name in ("qualifying_rate.buffer", "qualifying_rate.floor"):
            assert not is_reference(name), name
            assert not name.startswith("mortgage_rate."), name

    def test_neither_leg_is_ever_an_engine_default(self):
        """The read-back's `defaults applied:` line is a list of figures the
        ENGINE chose for the run's own numbers, and every one of them is a
        price or a rate the present value moves with. A test threshold landing
        there would be read as one — §14's failure in the other surface. The
        assertion is on the rendered line, not only on the list, because the
        line is where a reader would meet it."""
        data = cfg()
        spec = load_config_dict(data)
        det = compute_deterministic(spec)
        # The feature must have RUN against THIS spec first. Asserting on a spec
        # the channel never touched would pass however the channel behaves —
        # the absence would be an artifact of the test, not a property of the
        # code (found by mutation M32, which this line is what catches).
        assert qualifying_loads(spec, det, data), "the channel did not run"
        assert not [k for k in spec.defaults_applied if "qualifying" in k]
        block = read_back_lines(spec, warnings=[], det=det, raw=data)
        [defaults] = [l for l in block if l.startswith("defaults applied:")]
        assert "qualifying" not in defaults, defaults

    def test_the_load_moves_no_present_value(self):
        """The counterfactual is read for its income report and its present
        value is DISCARDED (spec §14). The run's own numbers are untouched."""
        data = cfg()
        spec = load_config_dict(data)
        det = compute_deterministic(spec)
        before = det.house.total_pv
        assert qualifying_loads(spec, det, data)
        assert compute_deterministic(load_config_dict(data)).house.total_pv == before


# ---------------------------------------------------------------------------
# §14's one guard, from the registry itself.
# ---------------------------------------------------------------------------

class TestWhatItMayNeverSay:
    FORBIDDEN = ("would not qualify", "will not qualify", "does not qualify",
                 "do not qualify", "fail to qualify", "would fail", "you fail",
                 "cannot qualify", "denied", "rejected", "you qualify",
                 "would qualify")

    def _every_line(self):
        out = []
        for rate in (0.03, 0.045, 0.05, 0.08):
            for down in (120_000, 200_000):
                out += lines(cfg(mortgage_rate=rate, down_payment=down))
        # The corpus MUST reach the straight-switch clause, or every scan in
        # this class stops at the sentence that shipped and the longest, most
        # dangerous half of the line is guarded by nothing (2026-09-21).
        out += lines(ladder_cfg(mortgage_rate=0.045))
        out += lines(ladder_cfg(mortgage_rate=0.045, renewal_years=3))
        out += lines(ladder_cfg(insured=True))
        assert len(out) == 11
        assert sum("straight switch" in l or "low-ratio" in l for l in out) == 3, \
            "the corpus must exercise BOTH clause branches and the silent case"
        return out

    def test_no_line_ever_rules_on_whether_a_lender_would_lend(self):
        for line in self._every_line():
            low = line.lower()
            for phrase in self.FORBIDDEN:
                assert phrase not in low, (phrase, line)

    def test_every_line_names_the_numerator_gap_and_cites_the_anchor(self):
        for line in self._every_line():
            assert "broader than the gross debt service a lender uses" in line, line
            assert "[income.affordability_threshold]" in line, line

    def test_every_line_cites_both_legs_and_states_its_direction(self):
        for line in self._every_line():
            assert "[qualifying_rate.buffer, qualifying_rate.floor]" in line, line
            assert TOWARD_BUYING in line, line

    def test_an_insured_loan_is_told_the_citation_is_not_its_own_test(self):
        """OSFI's minimum qualifying rate governs UNINSURED mortgages. The
        first-time-buyer case — under 20% down — is exactly the one it does
        NOT govern, and the two published formulas matching today is what
        makes passing one citation off as the other so easy. The line names
        the other authority and says no source for it is registered here."""
        [load] = loads(insured_cfg())
        assert load.insured is True
        line = lines(insured_cfg())[0]
        assert "Your loan is insured, so that rate is the federal government's, not OSFI's" \
            in line, line

    def test_an_uninsured_loan_is_told_the_citation_IS_its_own_test(self):
        [load] = loads(cfg(down_payment=200_000))
        assert load.insured is False
        line = lines(cfg(down_payment=200_000))[0]
        assert "Your loan is uninsured, so that rate is OSFI's, which governs uninsured " \
               "mortgages like yours" in line, line
        assert "federal government" not in line, line

    def test_the_registry_carries_the_insured_side_citation(self):
        """The line tells an insured household the figures are the federal
        government's. That is a claim about the world, so it is sourced on both
        anchors — with the statement's own words and its date — rather than
        asserted in prose the registry cannot back."""
        for name in ("qualifying_rate.buffer", "qualifying_rate.floor"):
            anchor = ANCHORS[name]
            assert "Department of Finance Canada" in anchor.source, name
            assert "2021-05-20" in anchor.source, name
            assert "align with OSFI" in anchor.source, name
            assert "June 1, 2021" in anchor.source, name
            assert "UNINSURED" in anchor.rationale, name
            assert "TWO AUTHORITIES, ONE FORMULA" in anchor.rationale, name

    def test_every_line_refuses_the_lender_verdict_IN_WORDS(self):
        """`test_no_line_ever_rules_on_whether_a_lender_would_lend` pins the
        NEGATIVE — the line must not say the household would fail. This pins
        the POSITIVE, and they are different claims: the line must SAY it
        cannot rule. Strip this clause and what is left is a 42.2%-of-income
        figure computed at a lender's own test rate with nothing anywhere
        saying the engine is not a lender, which is the single reading that
        would do real harm. Asserted on the RENDERED line, so a rewrite that
        keeps a variable named for the refusal while dropping it from the
        output fails here (found surviving 38 tests, 2026-09-21).
        """
        for line in self._every_line() + [lines(insured_cfg())[0]]:
            assert "so this run cannot say how a lender would rule on you" in line, line

    def test_every_line_names_the_authority_whose_test_it_applied(self):
        """Both branches, on the RENDERED line, over a corpus rather than one
        config each — and each asserts the OTHER branch's words are ABSENT.
        The two published formulas agree today, so a line naming the wrong
        authority still prints a correct-looking number: this clause is the
        only thing that says whose rule the figure came from."""
        for data in (cfg(mortgage_rate=0.03), cfg(mortgage_rate=0.05),
                     cfg(down_payment=200_000),
                     insured_cfg(), insured_cfg(down_payment=50_000)):
            [load] = loads(data)
            line = lines(data)[0]
            if load.insured:
                assert ("Your loan is insured, so that rate is the federal government's, "
                        "not OSFI's") in line, line
                assert "governs uninsured mortgages like yours" not in line, line
            else:
                assert ("Your loan is uninsured, so that rate is OSFI's, which governs "
                        "uninsured mortgages like yours") in line, line
                assert "federal government" not in line, line

    def test_the_line_carries_this_run_s_own_figures(self):
        """Spec §4's admission rule: at least one quantity FROM THIS RUN."""
        [load] = loads(cfg())
        line = lines(cfg())[0]
        assert f"{100 * load.qualifying_ratio_year1:.1f}%" in line
        assert f"{100 * load.own_ratio_year1:.1f}%" in line

    def test_the_line_names_the_rate_but_never_restates_the_rule(self):
        """The rule's sentence has ONE home, the registry, and the line cites
        the legs instead of quoting it — which is what keeps the line short
        enough to be read. Its own test pins the values against that sentence,
        so shortening here costs no provenance."""
        [load] = loads(cfg())
        line = lines(cfg())[0]
        assert f"{load.qualifying_quoted:.2%} as quoted" in line, line
        # and the figure it is a load ON: a tested rate with no contract rate
        # beside it is a number the reader cannot place.
        assert f"against your contract {load.contract_quoted:.2%}" in line, line
        assert MQR_RULE not in line, line
        assert "[qualifying_rate.buffer, qualifying_rate.floor]" in line, line

    def test_the_points_shown_are_the_difference_of_the_figures_shown(self):
        """A reader who subtracts the two percentages in the line must get the
        line's own third number."""
        for line in self._every_line():
            shown = line.split("runs ", 1)[1]
            loaded = float(shown.split("%", 1)[0])
            own = float(shown.split("this run's own ", 1)[1].split("%", 1)[0])
            points = float(shown.split("— ", 1)[1].split(" points", 1)[0])
            assert round(loaded - own, 1) == points, line


# ---------------------------------------------------------------------------
# The direction vocabulary has one home (spec §13).
# ---------------------------------------------------------------------------

class TestDirectionVocabulary:
    def test_every_direction_a_coherence_warning_states_is_one_of_the_two(self):
        """A fourth direction written by hand would land here. Scanned over a
        config that fires the owner-cost, appreciation, renter-tax and renewal
        warnings at once."""
        data = cfg(mortgage_rate=0.045)
        data["house"]["value_growth_rate"] = 0.0
        warns = coherence_warnings(load_config_dict(data), data)
        assert warns, "the corpus must not be empty"
        found = set()
        for warn in warns:
            for chunk in warn.split("toward ")[1:]:
                found.add(chunk.split()[0].rstrip(".,;)"))
        # EQUALITY, not containment: `<=` would pass on a corpus that fires
        # only one direction and would then guard neither the other's sites.
        assert found == {TOWARD_BUYING.split()[1], TOWARD_RENTING.split()[1]}, found
        assert any(f"({NEUTRAL})" in w for w in warns), "the third direction is unexercised"


# ---------------------------------------------------------------------------
# The line reaches every surface the channel owns.
# ---------------------------------------------------------------------------

class TestItReachesTheSurfaces:
    def _yaml(self, tmp_path, data):
        import yaml
        path = tmp_path / "c.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return str(path)

    def test_stderr_and_the_read_back_both_carry_it(self, tmp_path, monkeypatch, capsys):
        config = self._yaml(tmp_path, cfg())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--no-monte-carlo"])
        assert cli_main() == 0
        out = capsys.readouterr()
        assert any("unpriced —" in line for line in out.err.splitlines()), out.err
        assert any("unpriced —" in line for line in out.out.splitlines()), out.out

    def test_the_json_warnings_list_carries_it(self, tmp_path, monkeypatch, capsys):
        import json
        config = self._yaml(tmp_path, cfg())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--no-monte-carlo", "--json"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        assert [w for w in doc["warnings"] if "unpriced —" in w]
        assert [w for w in doc["assumptions"]["read_back"] if "unpriced —" in w]
        assert [w for w in doc["assumptions"]["read_back_short"] if "unpriced —" in w]

    def test_a_stated_renewal_ladder_cannot_leak_into_the_reported_figure(
            self, tmp_path, monkeypatch, capsys):
        """The counterfactual is a RELOAD of the user's config, so a renewal
        ladder survives it. Year 1 falls in the opening term, so the figure is
        still the oracle at the qualifying rate — and the reload must not be
        refused by the ladder's own validation."""
        data = cfg(mortgage_rate=0.045)
        data["house"]["mortgage_renewal_years"] = 5
        data["house"]["mortgage_renewal_rates"] = [0.06, 0.07, 0.08, 0.09]
        [load] = loads(data)
        assert load.qualifying_ratio_year1 == pytest.approx(
            mortgage_payment(600_000 - 120_000,
                             effective_mortgage_rate(0.045 + BUFFER, "semi_annual"), 25)
            / INCOME, abs=1e-12)

    def test_an_all_cash_run_leaves_every_surface_silent(self, tmp_path, monkeypatch, capsys):
        """The silence is not a formatting accident of one surface."""
        import json
        config = self._yaml(tmp_path, cfg(all_cash=True))
        monkeypatch.setattr(sys, "argv", ["hde", config, "--no-monte-carlo", "--json"])
        assert cli_main() == 0
        out = capsys.readouterr()
        assert "unpriced" not in out.err
        doc = json.loads(out.out)
        assert not [w for w in doc["warnings"] if "unpriced" in w]
        assert not [w for w in doc["assumptions"]["read_back"] if "unpriced" in w]


# ---------------------------------------------------------------------------
# §15: WHICH TRANSACTION the qualifying rate tests, and the exemption the run
# names without ever claiming it.
#
# The minimum qualifying rate is an ORIGINATION test. The line stated it as
# "the minimum qualifying rate a lender would test you at" on runs that also
# price a renewal, which since 2024-11-21 is false for an uninsured straight
# switch — and the reader it misleads is the household already facing a
# payment jump (README, docs/BOARD.md item 5).
#
# EVERY ASSERTION BELOW IS ON THE RENDERED LINE AGAINST A LITERAL SPELLED OUT
# HERE, never against a module constant: a rewrite that keeps the constant and
# drops the words from the output must fail. And every one checks BOTH what
# must be there and what must NOT — because the way to get this wrong is the
# generous direction, where a household told they are exempt walks into a
# refusal at the branch.
# ---------------------------------------------------------------------------

class TestWhichTransactionItPrices:

    # What no line may say, however the clause is rewritten: a claim that THIS
    # household is out of the test. The run cannot see the two facts that
    # decide it — the amount carried over and the amortization kept.
    NEVER = (
        "you are exempt", "you're exempt", "you would be exempt", "are exempt",
        "you qualify at your contract", "no stress test", "will not be tested",
        "you will not be tested", "no test applies", "do not need to requalify",
        "don't need to requalify", "no longer tested", "you are not tested",
        "this test does not apply to you", "so you are fine",
    )

    def test_a_run_that_prices_a_renewal_says_which_transaction_the_figure_tests(self):
        """The defect, in one assertion. The figures are the ORIGINATION test;
        the run also prices a renewal at year 6, and the line must say so and
        name the year THIS config produced."""
        line = lines(ladder_cfg())[0]
        assert ("The figure tests the year-0 purchase, not the renewal this run prices "
                "at year 6:") in line, line

    def test_the_uninsured_clause_names_the_transaction_the_rule_stops_at(self):
        """THE LINE CITES, THE ANCHORS RECITE (operator ruling 2026-09-21). The
        effective date, the three conditions of a straight switch and the B-20
        mechanism are stored verbatim on the two legs the clause cites, and
        `TestTheStraightSwitchRegistry` is what keeps them there. What the LINE
        owes is the name of the transaction the rule stops at — without it the
        reader has no term to look up and no way to tell their own case."""
        line = lines(ladder_cfg())[0]
        assert "a straight switch is outside OSFI's prescribed rate" in line, line
        # and the clause stays a clause: the rule is not recited back
        assert "2024-11-21" not in line, line
        assert "Guideline B-20" not in line, line
        assert "amortization" not in line, line

    def test_the_uninsured_clause_refuses_to_claim_the_exemption_for_the_user(self):
        """THE CLAUSE THIS FEATURE EXISTS FOR. Strip it and what is left is a
        published exemption printed in the engine's own voice at a household
        whose transaction the engine cannot see — the generous failure, which
        is worse than the sentence it replaced."""
        line = lines(ladder_cfg())[0]
        assert "and this run cannot see whether yours is one" in line, line

    def test_the_uninsured_clause_says_the_relief_is_not_relief_from_underwriting(self):
        """OSFI stopped PRESCRIBING the rate; it still expects the loan
        assessed « like any other new origination » under B-20, with the lender
        setting its own qualifying rate. Drop this and a scope limit reads as a
        promise that nobody will test them."""
        line = lines(ladder_cfg())[0]
        assert "outside OSFI's prescribed rate, not outside a lender's test" in line, line

    def test_an_insured_run_is_not_handed_the_uninsured_exemption(self):
        """`insured` here means the loader derived mortgage insurance, which
        happens only above the 80% line — so this engine's insured loan is
        HIGH-RATIO, and the federal removal (2024-12-16) is written for the
        renewal of a prior LOW-RATIO loan. The branch reports the absent source
        rather than borrowing OSFI's exemption, which governs a loan this one
        is not."""
        [load] = loads(ladder_cfg(insured=True))
        assert load.insured is True
        line = lines(ladder_cfg(insured=True))[0]
        assert "the insured straight-switch removal is written for low-ratio loans and " \
               "this one starts above that line, so no source here says it reaches you" \
               in line, line
        # and NOT the other branch's words, whose exemption is a claim about a
        # loan class this one is not in
        assert "outside OSFI's prescribed rate" not in line, line
        assert "a straight switch is outside" not in line, line

    def test_an_uninsured_run_is_not_handed_the_insured_measure(self):
        line = lines(ladder_cfg())[0]
        assert "low-ratio" not in line, line
        assert "insured straight-switch removal" not in line, line
        assert "federal government" not in line, line

    def test_no_line_ever_tells_the_household_it_is_out_of_the_test(self):
        """Over the whole corpus, both branches and the silent case."""
        corpus = (lines(ladder_cfg()) + lines(ladder_cfg(insured=True))
                  + lines(ladder_cfg(renewal_years=3)) + lines(cfg())
                  + lines(insured_cfg()))
        assert len(corpus) == 5
        for line in corpus:
            low = line.lower()
            for phrase in self.NEVER:
                assert phrase not in low, (phrase, line)

    def test_a_run_with_no_renewal_says_nothing_about_switches(self):
        """The guard, spec §5: the same feature must be able to print NOTHING.
        A clause that cannot come out silent is a disclaimer riding on a
        measurement, and every shipped example is in that silent state."""
        for line in (lines(cfg())[0], lines(insured_cfg())[0]):
            assert "straight switch" not in line, line
            assert "straight-switch" not in line, line
            assert "low-ratio" not in line, line
            assert "The figure tests the year-0 purchase" not in line, line
            assert "cannot see whether yours is one" not in line, line
            assert "no source here says it reaches you" not in line, line

    def test_two_configs_differing_only_in_the_ladder_one_speaks_one_is_silent(self):
        """The minimal pair: identical but for the two renewal keys."""
        plain, laddered = cfg(), ladder_cfg()
        assert {k: v for k, v in laddered["house"].items()
                if k not in ("mortgage_renewal_years", "mortgage_renewal_rates")} \
            == plain["house"], "the pair must differ in the ladder alone"
        assert "straight switch" not in lines(plain)[0]
        assert "straight switch" in lines(laddered)[0]

    def test_a_renewal_past_the_horizon_is_not_a_transaction_this_run_prices(self):
        """`renewals_priced_inside` is the one answer to "did the ladder reach
        this run". A first renewal at year 6 in a 4-year run reaches no payment
        and no PV, so naming it here would report a step the verdict never saw
        — and the clause would become text, since a stated ladder alone would
        print it."""
        [load] = loads(ladder_cfg(years=4, renewal_years=5))
        assert load.first_renewal_year is None
        line = lines(ladder_cfg(years=4, renewal_years=5))[0]
        assert "straight switch" not in line, line
        assert "year 6" not in line, line
        # the printing half of the pair, one key apart: the same ladder inside
        # a 10-year horizon does speak
        assert "at year 6" in lines(ladder_cfg(years=10, renewal_years=5))[0]

    def test_the_year_named_is_this_config_s_own(self):
        """Spec §4's admission rule, applied to the clause: two configs
        differing ONLY in the renewal term print different years. If the clause
        ever hardcodes one, these two are identical and this says so."""
        three, five = ladder_cfg(renewal_years=3), ladder_cfg(renewal_years=5)
        assert {k: v for k, v in three["house"].items() if k != "mortgage_renewal_years"} \
            == {k: v for k, v in five["house"].items() if k != "mortgage_renewal_years"}
        [a], [b] = loads(three), loads(five)
        assert (a.first_renewal_year, b.first_renewal_year) == (4, 6)
        assert "at year 4:" in lines(three)[0], lines(three)[0]
        assert "at year 6:" in lines(five)[0], lines(five)[0]
        assert lines(three)[0] != lines(five)[0]

    def test_the_clause_does_not_disturb_the_sentence_it_rides_on(self):
        """The line's own contract still holds with the clause in: the closing
        refusal, the numerator gap, the direction, and the year-1 figures are
        the ones a laddered run computed."""
        [load] = loads(ladder_cfg())
        line = lines(ladder_cfg())[0]
        assert "so this run cannot say how a lender would rule on you" in line, line
        assert "broader than the gross debt service a lender uses" in line, line
        assert "[income.affordability_threshold]" in line, line
        assert TOWARD_BUYING in line, line
        assert f"{100 * load.qualifying_ratio_year1:.1f}%" in line, line
        assert f"{100 * load.own_ratio_year1:.1f}%" in line, line

    def test_the_clause_cites_the_anchors_that_hold_its_source(self):
        """The exemption is a claim about the world, so the clause carries the
        pair a reader can look up with `--print-anchors` — where the sentence,
        the two dates and the B-20 caveat are stored verbatim. Asserted on the
        clause's own half of the line, so the citation that was already there
        before the clause cannot stand in for it."""
        for line in (lines(ladder_cfg())[0], lines(ladder_cfg(insured=True))[0]):
            _head, marker, tail = line.partition("The figure tests the year-0 purchase")
            assert marker, line
            assert "[qualifying_rate.buffer, qualifying_rate.floor]" in tail, line

    def test_the_clause_reaches_every_surface_the_channel_owns(self, tmp_path, monkeypatch,
                                                               capsys):
        """A clause that lands only on stderr is not in the answer the
        assistant reads back."""
        import json

        import yaml
        path = tmp_path / "c.yaml"
        path.write_text(yaml.safe_dump(ladder_cfg()), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["hde", str(path), "--no-monte-carlo", "--json"])
        assert cli_main() == 0
        out = capsys.readouterr()
        needle = "a straight switch is outside OSFI's prescribed rate"
        assert needle in out.err, out.err
        doc = json.loads(out.out)
        for key in ("read_back", "read_back_short"):
            assert [w for w in doc["assumptions"][key] if needle in w], key
        assert [w for w in doc["warnings"] if needle in w]


# ---------------------------------------------------------------------------
# The exemption's source, stored verbatim, and the line's paraphrase pinned
# against it — the same alarm `test_the_stored_figures_are_the_ones_the_printed
# _rule_states` puts on the rule's two values.
# ---------------------------------------------------------------------------

class TestTheStraightSwitchRegistry:
    LEGS = ("qualifying_rate.buffer", "qualifying_rate.floor")

    def test_both_legs_store_osfi_s_own_definition_of_a_straight_switch(self):
        """Spelled out here, not imported, so an edit to the stored sentence
        lands on this assertion and the editor has to go back to the source."""
        assert MQR_STRAIGHT_SWITCH == (
            "when a borrower switches their uninsured mortgage from one federally "
            "regulated lender to another with no increase to: the amortization period, "
            "nor the loan amount.")
        for name in self.LEGS:
            assert MQR_STRAIGHT_SWITCH in ANCHORS[name].source, name

    def test_both_legs_store_what_the_exemption_does_not_relieve(self):
        assert MQR_B20_STILL_APPLIES == (
            "When considering an uninsured straight switch application, an institution "
            "should assess the loan like any other new origination and should continue "
            "to apply principles of sound residential mortgage underwriting set out in "
            "Guideline B-20.")
        for name in self.LEGS:
            assert MQR_B20_STILL_APPLIES in ANCHORS[name].source, name
            assert ("Lenders should continue to consider current and future conditions "
                    "as they determine qualifying rates") in ANCHORS[name].source, name

    def test_the_stored_rule_carries_the_three_facts_the_line_sends_readers_to(self):
        """The line names the transaction and cites the legs; the conditions
        that DEFINE that transaction live here, and this is what keeps them.
        If OSFI ever allowed a longer amortization or a bigger loan, the stored
        sentence changes and this assertion is where that surfaces — the line
        would then be sending readers to a rule it no longer describes."""
        for phrase in ("the amortization period", "the loan amount",
                       "from one federally regulated lender to another"):
            assert phrase in MQR_STRAIGHT_SWITCH, phrase
        # the one word the line and the registry must share, or the citation
        # leads nowhere a reader can follow
        assert "straight switch" in lines(ladder_cfg())[0]
        for name in self.LEGS:
            assert "straight switch" in ANCHORS[name].source, name

    def test_both_legs_carry_the_two_effective_dates_in_the_sources_own_words(self):
        """One home for each date: the ISO constant the line prints and the
        spelling the source uses must be the same day."""
        import datetime
        assert MQR_STRAIGHT_SWITCH_EFFECTIVE == "2024-11-21"
        assert MQR_INSURED_SWITCH_EFFECTIVE == "2024-12-16"
        for iso, spelled in ((MQR_STRAIGHT_SWITCH_EFFECTIVE, "November 21, 2024"),
                             (MQR_INSURED_SWITCH_EFFECTIVE, "December 16, 2024")):
            date = datetime.date.fromisoformat(iso)
            assert date.strftime("%B %-d, %Y") == spelled, (iso, spelled)
            for name in self.LEGS:
                assert spelled in ANCHORS[name].source, (name, spelled)

    def test_both_legs_carry_the_announcement_and_the_insured_measure_by_url(self):
        for name in self.LEGS:
            source = ANCHORS[name].source
            assert ("osfi-bsif.gc.ca/en/guidance/guidance-library/osfi-exempts-uninsured-"
                    "mortgage-straight-switches-prescribed-mqr-implements-portfolio-lti-"
                    "limits") in source, name
            assert ("canada.ca/en/department-finance/news/2024/12/straight-switches-and-"
                    "portfolio-insurance.html") in source, name
            assert "SOR/2025-55" in source, name

    def test_the_insured_measure_is_stored_with_its_own_narrower_scope(self):
        """The failure this guards is passing the low-ratio measure off as an
        insured borrower's exemption — the same mistake the two-authorities
        rationale already guards for the formula."""
        for name in self.LEGS:
            source = ANCHORS[name].source
            assert ("This measure will remove the minimum qualifying rate requirement for "
                    "low-ratio (i.e., loan-to-value up to 80 per cent) renewals") \
                in source, name
            assert ("the loan is for the discharge of the outstanding balance of a prior "
                    "low ratio loan") in source, name
            assert "Equity take out is not permitted" in source, name
            rationale = ANCHORS[name].rationale
            assert "HIGH-RATIO" in rationale, name
            assert "no primary source was found either way" in rationale, name

    def test_the_rationale_records_what_the_engine_may_never_say_off_the_rule(self):
        for name in self.LEGS:
            rationale = ANCHORS[name].rationale
            assert "never claims it for the user" in rationale, name
            assert "not from being assessed" in rationale, name

    def test_the_exemption_moved_no_value_and_added_no_default(self):
        """A scope limit on a test threshold, applied to ONE DISCLOSURE. If it
        ever reached a present value or a default, the line would be pricing
        the thing it says it does not price."""
        assert ANCHORS["qualifying_rate.buffer"].value == 0.02
        assert ANCHORS["qualifying_rate.floor"].value == 0.0525
        data = ladder_cfg()
        spec = load_config_dict(data)
        det = compute_deterministic(spec)
        before = det.house.total_pv
        assert qualifying_loads(spec, det, data), "the channel did not run"
        assert not [k for k in spec.defaults_applied if "qualifying" in k]
        assert compute_deterministic(load_config_dict(data)).house.total_pv == before
