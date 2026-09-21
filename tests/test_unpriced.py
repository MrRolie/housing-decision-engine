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

from hde.anchors import ANCHORS, MQR_RULE, is_reference
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
        assert len(out) == 8
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
