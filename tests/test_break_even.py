"""
--break-even KEY[=lo:hi] (2026-09-02, operator product direction): most users
arrive certain about one side ("houses in Laval around $650k") and want the
threshold on the other ("what rent keeps renting the better deal?", or "what
price makes buying worth it at my rent?"). A sweep grid brackets that; this
solves it: the value of ONE input where the two priced options' deterministic
total PVs cross, plus the tie-band edges around it (the same 5% band the
verdict uses), so the answer reads "renting is cheaper below $X, too close to
call between $A and $B, buying is cheaper above $B".
"""

import pytest

from hde.anchors import ANCHORS
from hde.break_even import (format_break_even, parse_break_even, solve_break_even,
                            solve_break_even_across)
from hde.config import load_config_dict
from hde.deterministic import compute_deterministic
from hde.sweep import with_value

BAND = ANCHORS["verdict.tie_band"].value


def _base(**over):
    cfg = {
        "years": 10, "rates": "real",
        "rent": {"monthly_rent": 2000, "rent_escalation_rate": 0.0, "invested_down_payment": 85_000},
        "condo": {
            "initial_value": 400_000, "monthly_fee": 300, "value_growth_rate": 0.0,
            "down_payment": 80_000, "mortgage_rate": 0.04, "mortgage_term_years": 25,
            "purchase_costs": 5_000,
            "other_recurring_costs": [{"name": "tax", "annual_amount": 3_000, "escalation_rate": 0.0}],
        },
    }
    cfg.update(over)
    return cfg


def _gap(raw, key, v):
    det = compute_deterministic(load_config_dict(with_value(raw, key, v)))
    return det.rent.total_pv - det.condo.total_pv


class TestParse:
    def test_bare_key_and_bracket_forms(self):
        assert parse_break_even("rent.monthly_rent") == ("rent.monthly_rent", None, None)
        assert parse_break_even("condo.initial_value=300000:900000") == ("condo.initial_value", 300000.0, 900000.0)

    def test_rejects_malformed(self):
        with pytest.raises(ValueError):
            parse_break_even("rent.monthly_rent=1000")
        with pytest.raises(ValueError):
            parse_break_even("=1:2")


class TestSolve:
    def test_rent_break_even_is_where_the_totals_cross(self):
        raw = _base()
        out = solve_break_even(raw, "rent.monthly_rent")
        assert out["options"] == ["condo", "rent"]
        assert len(out["break_evens"]) == 1
        be = out["break_evens"][0]
        assert abs(_gap(raw, "rent.monthly_rent", be["value"])) < 1.0  # dollars of PV
        # Renting is cheaper below the break-even rent, the condo above it.
        assert be["cheaper_below"] == "rent" and be["cheaper_above"] == "condo"
        lo, hi = be["tie_band"]
        assert lo < be["value"] < hi
        # At the band edges the margin is exactly the tie band of the winner's PV.
        for edge in (lo, hi):
            det = compute_deterministic(load_config_dict(with_value(raw, "rent.monthly_rent", edge)))
            a, b = det.rent.total_pv, det.condo.total_pv
            assert abs(abs(a - b) / abs(min(a, b)) - BAND) < 1e-4

    def test_price_break_even_from_the_rent_side(self):
        raw = _base()
        out = solve_break_even(raw, "condo.initial_value")
        assert len(out["break_evens"]) == 1
        be = out["break_evens"][0]
        assert be["cheaper_below"] == "condo" and be["cheaper_above"] == "rent"
        assert abs(_gap(raw, "condo.initial_value", be["value"])) < 1.0

    def test_default_bracket_is_a_quarter_to_four_times_the_base_value(self):
        out = solve_break_even(_base(), "rent.monthly_rent")
        assert out["bracket"] == [500.0, 8000.0] and out["base_value"] == 2000

    def test_no_crossing_in_bracket_is_said_not_invented(self):
        out = solve_break_even(_base(), "rent.monthly_rent", lo=100.0, hi=200.0)
        assert out["break_evens"] == [] and out["cheaper_throughout"] == "rent"


class TestNoCrossingNamesTheBracketAndTheWidening:
    """A bracket with no crossing used to print `<opt> is cheaper throughout`
    and nothing else — not the bounds it held for, nor what to run next. The
    line names both ends, which option is cheaper at each, and the widened
    bracket on the side where the gap narrows (2026-09-04)."""

    def test_the_gap_narrowing_upward_widens_the_high_end(self):
        from hde.break_even import threshold_sentences
        out = solve_break_even(_base(), "rent.monthly_rent", lo=100.0, hi=200.0)
        assert out["no_crossing"]["widen"] == [100.0, 300.0]
        [line] = threshold_sentences("rent.monthly_rent", out, BAND)
        assert line == ("no crossing between 100 and 200: rent is cheaper at both ends — "
                        "widen with --break-even rent.monthly_rent=100:300")
        assert line in format_break_even(out)

    def test_the_gap_narrowing_downward_widens_the_low_end_never_below_half(self):
        from hde.break_even import threshold_sentences
        out = solve_break_even(_base(), "rent.monthly_rent", lo=5_000.0, hi=6_000.0)
        assert out["cheaper_throughout"] == "condo"
        [line] = threshold_sentences("rent.monthly_rent", out, BAND)
        assert line.startswith("no crossing between 5,000 and 6,000: condo is cheaper at both ends")
        assert line.endswith("widen with --break-even rent.monthly_rent=4000:6000")

    def test_an_integer_key_widens_in_whole_values(self):
        from hde.break_even import threshold_sentences
        out = solve_break_even(_base(), "years", lo=2, hi=4)
        if out["break_evens"]:
            pytest.skip("this config crosses inside 2–4 years")
        [line] = threshold_sentences("years", out, BAND)
        assert "--break-even years=" in line
        lo, hi = line.rsplit("=", 1)[1].split(":")
        assert int(lo) >= 1 and int(hi) > int(lo)

    def test_an_across_row_carries_the_same_line(self):
        across = solve_break_even_across(_base(), "rent.monthly_rent", 100.0, 200.0,
                                         "condo.value_growth_rate", [0.0, 0.02])
        from hde.break_even import across_row_sentence
        for row in across["rows"]:
            text = across_row_sentence("rent.monthly_rent", "condo.value_growth_rate", row, BAND)
            assert "no crossing between 100 and 200" in text and "widen with" in text

    def test_three_options_refused(self):
        raw = _base(house={"initial_value": 500_000, "all_cash": True, "value_growth_rate": 0.0})
        with pytest.raises(ValueError, match="exactly two"):
            solve_break_even(raw, "rent.monthly_rent")

    def test_defaulted_key_needs_an_explicit_bracket(self):
        raw = _base()
        del raw["rent"]["invested_down_payment"]
        with pytest.raises(ValueError, match="lo:hi"):
            solve_break_even(raw, "rent.invested_down_payment")


class TestFormat:
    def test_text_reads_as_a_threshold_sentence(self):
        out = solve_break_even(_base(), "rent.monthly_rent")
        text = format_break_even(out)
        assert "Break-even rent.monthly_rent" in text and "a market_scenario prior does not move it" in text
        assert "rent is cheaper below" in text and "condo is cheaper above" in text
        assert "too close to call between" in text
        # Band-first, and the JSON entry leads with the same sentence (three evaluation
        # serves copied a crossing-first shape into the user's text).
        be = out["break_evens"][0]
        assert list(be)[0] == "sentence"
        lo, hi = be["tie_band"]
        assert be["sentence"].startswith(f"rent is cheaper below {lo:,.0f}; too close to call between {lo:,.0f} and {hi:,.0f}; condo is cheaper above {hi:,.0f}")
        assert be["sentence"] in text

    def test_the_band_rule_is_stated_once_in_the_header(self):
        """The rule `band = 5% of the cheaper option's PV` used to close every
        sentence; it is one fact, stated in the block's header (2026-09-04)."""
        out = solve_break_even(_base(), "rent.monthly_rent")
        be = out["break_evens"][0]
        assert be["sentence"].endswith(f"(crossing {be['value']:,.0f})")
        text = format_break_even(out)
        assert text.count("band = 5% of the cheaper option's PV") == 1
        assert "band = 5% of the cheaper option's PV" in text.splitlines()[1]

    def test_the_story_keeps_the_band_clause_on_its_own_caption(self):
        from hde.break_even import band_sentence
        out = solve_break_even(_base(), "rent.monthly_rent")
        be = out["break_evens"][0]
        assert band_sentence("rent.monthly_rent", be, BAND).endswith(
            "band = 5% of the cheaper option's PV)")


class TestCliffNoteIsOneSentence:
    def _cfg(self):
        return {
            "years": 10, "discount_rate": 0.03, "province": "QC", "rates": "real", "rates": "real",
            "house": {"initial_value": 600_000, "value_growth_rate": 0.0,
                      "cash_available": 130_000, "purchase_costs": 5_000,
                      "mortgage_rate": 0.04, "mortgage_term_years": 25,
                      "mortgage_insurance": "auto"},
            "rent": {"monthly_rent": 2_300, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 125_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }

    def test_the_cliff_clause_is_one_sentence(self):
        note = solve_break_even(self._cfg(), "house.initial_value")["note"]
        clause = next(c for c in note.split("; ") if "mortgage-insurance cliff" in c)
        assert clause == (
            "the crossing at 625,000 is the mortgage-insurance cliff — house uninsured just "
            "below it, insured (2.80% premium on the loan) just above — not a smooth cost "
            "crossing: the tie band around it is the step's width, not a range of near-ties")


class TestIntegerInputs:
    def test_years_reports_the_first_year_the_other_side_wins(self):
        raw = _base()
        out = solve_break_even(raw, "years", lo=2, hi=30)
        assert len(out["break_evens"]) == 1
        be = out["break_evens"][0]
        assert isinstance(be["value"], int) and be["last_value_below"] == be["value"] - 1
        # The sign really changes between those two integers.
        g_below = _gap(raw, "years", be["last_value_below"])
        g_above = _gap(raw, "years", be["value"])
        assert (g_below > 0) != (g_above > 0)
        assert all(e is None or isinstance(e, int) for e in be["tie_band"])
        assert "is cheaper up to years=" in format_break_even(out)


class TestRefusedPoints:
    """A bracket end the loader refuses (price below the fixed down payment) must
    shrink the search and say so — never surface as a traceback (review, 2026-09-02)."""

    def test_refused_tail_shrinks_the_search_and_is_reported(self):
        raw = _base()
        raw["condo"]["down_payment"] = 120_000
        raw["rent"]["invested_down_payment"] = 125_000
        out = solve_break_even(raw, "condo.initial_value")  # default bracket 100k–1.6M; 100k < down payment
        assert out["bracket"] == [100_000.0, 1_600_000.0]
        assert out["refused"]["count"] == 1 and "down_payment" in out["refused"]["reason"]
        assert out["searched"] == [[287_500.0, 1_600_000.0]]
        text = format_break_even(out)
        assert "refuses 1 point(s)" in text and "searched 287,500–1,600,000" in text

    def test_every_point_refused_is_a_clear_error(self):
        raw = _base()
        raw["condo"]["down_payment"] = 120_000
        raw["rent"]["invested_down_payment"] = 125_000
        with pytest.raises(ValueError, match="refused every point"):
            solve_break_even(raw, "condo.initial_value", lo=10_000, hi=50_000)

    def test_cli_reports_a_refused_bracket_without_a_traceback(self, tmp_path, monkeypatch, capsys):
        import sys
        from hde.cli import main as cli_main
        cfg = tmp_path / "refused.yaml"
        cfg.write_text(
            "years: 10\nrent:\n  monthly_rent: 2000\n  invested_down_payment: 125000\n"
            "condo:\n  initial_value: 400000\n  monthly_fee: 300\n  down_payment: 120000\n"
            "  mortgage_rate: 0.04\n  mortgage_term_years: 25\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo",
                                          "--break-even", "condo.initial_value=10000:50000"])
        assert cli_main() == 1
        err = capsys.readouterr().err
        assert "refused every point" in err and "Traceback" not in err


class TestBandEdges:
    def test_edges_sit_where_the_gap_equals_the_tie_band(self):
        raw = _base()
        out = solve_break_even(raw, "rent.monthly_rent")
        be = out["break_evens"][0]
        left, right = be["tie_band"]
        assert left is not None and right is not None and left < be["value"] < right
        for edge_v in (left, right):
            det = compute_deterministic(load_config_dict(with_value(raw, "rent.monthly_rent", edge_v)))
            cheaper = min(det.rent.total_pv, det.condo.total_pv)
            assert abs(det.rent.total_pv - det.condo.total_pv) / cheaper == pytest.approx(BAND, rel=1e-6)


class TestPriorDoesNotMoveTheThreshold:
    """Round 5b: the trial run ran a demographic-prior variant to test the threshold's
    growth sensitivity; the prior's drift enters the Monte Carlo only, so the
    deterministic crossing is identical and the output must say so."""

    def test_identical_crossing_and_a_note(self):
        raw = _base()
        raw["house"] = {**raw.pop("condo"), "annual_maintenance_rate": 0.01}
        del raw["house"]["monthly_fee"]
        base = solve_break_even(raw, "rent.monthly_rent")
        with_prior = solve_break_even(
            {**raw, "market_scenario": {"path": "tests/fixtures/scenario_prior_golden.json",
                                        "geography": "LAVAL_RA13"}},
            "rent.monthly_rent")
        assert with_prior["break_evens"][0]["value"] == pytest.approx(base["break_evens"][0]["value"])
        assert "note" not in base and "does not move this threshold" in with_prior["note"]
        assert "does not move this threshold" in format_break_even(with_prior)


class TestAcrossASweep:
    """Round 5b: 'the threshold at 0% and at 2% growth' must be one command —
    --break-even re-solved at every --sweep point."""

    def test_threshold_re_solved_at_each_growth_point(self):
        raw = _base()
        across = solve_break_even_across(raw, "rent.monthly_rent", None, None,
                                         "condo.value_growth_rate", [0.0, 0.02])
        assert across["key"] == "condo.value_growth_rate" and len(across["rows"]) == 2
        t0 = across["rows"][0]["break_evens"][0]["value"]
        t2 = across["rows"][1]["break_evens"][0]["value"]
        assert t2 < t0  # faster appreciation: renting needs a lower rent to stay ahead
        assert t0 == pytest.approx(solve_break_even(raw, "rent.monthly_rent")["break_evens"][0]["value"])

    def test_cli_prints_and_rides_json(self, tmp_path, monkeypatch, capsys):
        import json, sys
        from hde.cli import main as cli_main
        import yaml
        cfg = tmp_path / "two.yaml"
        cfg.write_text(yaml.safe_dump(_base()), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo", "--json",
                                          "--break-even", "rent.monthly_rent",
                                          "--sweep", "condo.value_growth_rate=0:0.02:3"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        rows = doc["break_evens"][0]["across"][0]["rows"]
        assert [r["value"] for r in rows] == [0.0, 0.01, 0.02]
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo",
                                          "--break-even", "rent.monthly_rent",
                                          "--sweep", "condo.value_growth_rate=0:0.02:3"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert "across condo.value_growth_rate (the threshold re-solved at each value):" in out
        assert out.count("condo.value_growth_rate=") >= 3

    def test_sweeping_the_break_even_key_itself_adds_no_across_block(self, tmp_path, monkeypatch, capsys):
        import json, sys
        from hde.cli import main as cli_main
        import yaml
        cfg = tmp_path / "two.yaml"
        cfg.write_text(yaml.safe_dump(_base()), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo", "--json",
                                          "--break-even", "rent.monthly_rent",
                                          "--sweep", "rent.monthly_rent=1500:3000:4"])
        assert cli_main() == 0
        assert "across" not in json.loads(capsys.readouterr().out)["break_evens"][0]


class TestRateKeyBrackets:
    """2026-09-03 review: `--break-even condo.value_growth_rate` refused with
    "only money inputs get a default bracket" — the threshold question users
    actually ask about growth needed a bracket they had no way to guess. Rate
    keys get sensible defaults, and the output says which bracket was used."""

    def test_defaults_cover_the_rate_keys(self):
        from hde.break_even import RATE_BRACKETS
        assert RATE_BRACKETS["value_growth_rate"] == (-0.02, 0.05)
        assert RATE_BRACKETS["rent_escalation_rate"] == (-0.01, 0.05)
        assert RATE_BRACKETS["annual_maintenance_rate"] == (0.0, 0.03)
        assert RATE_BRACKETS["mortgage_rate"] == (0.01, 0.10)
        assert RATE_BRACKETS["discount_rate"] == (0.0, 0.08)

    def test_growth_solves_without_a_manual_bracket(self):
        out = solve_break_even(_base(), "condo.value_growth_rate")
        assert out["bracket"] == [-0.02, 0.05]
        assert out["break_evens"] or "cheaper_throughout" in out

    def test_a_rate_key_absent_from_the_yaml_still_gets_its_bracket(self):
        raw = _base()
        raw["condo"].pop("value_growth_rate")
        out = solve_break_even(raw, "condo.value_growth_rate")
        assert out["bracket"] == [-0.02, 0.05] and out["base_value"] is None

    def test_a_manual_bracket_still_wins(self):
        out = solve_break_even(_base(), "condo.value_growth_rate", -0.01, 0.03)
        assert out["bracket"] == [-0.01, 0.03]

    def test_the_output_says_the_bracket_used(self):
        out = solve_break_even(_base(), "condo.value_growth_rate")
        assert "bracket -2.00%–5.00%" in format_break_even(out)

    def test_a_key_that_is_neither_money_nor_rate_still_asks_for_one(self):
        with pytest.raises(ValueError, match="lo:hi"):
            solve_break_even(_base(), "condo.mortgage_term_years")


class TestDeclaredSourcesAtGridPoints:
    """The threshold on a key declared `anchor:<name>` must solve: every grid
    point used to be refused because the copied YAML re-validated the
    declaration against the anchor's figure (2026-09-04)."""

    def _raw(self):
        raw = _base(discount_rate=0.03)
        raw["sources"] = {"discount_rate": "anchor:simulation.discount_rate"}
        return raw

    def test_the_break_even_solves_instead_of_refusing_every_point(self):
        out = solve_break_even(self._raw(), "discount_rate", 0.0, 0.08)
        assert "refused" not in out, out
        assert out["searched"] == [[0.0, 0.08]]

    def test_the_across_rows_lift_the_swept_keys_declaration_too(self):
        raw = self._raw()
        across = solve_break_even_across(raw, "rent.monthly_rent", None, None,
                                         "discount_rate", [0.02, 0.04])
        assert all(row["break_evens"] for row in across["rows"]), across


class TestValuesPrintByTheKeysKind:
    """`--break-even condo.purchase_costs=0:6000` printed "0.00%–6,000" and
    "no crossing between 0.00% and 6,000": the low bound was formatted by its
    size, not by the key's kind (2026-09-08). A dollar key prints as money at
    every magnitude; a rate key keeps the percent form."""

    def test_bracket_bounds_and_the_no_crossing_line_print_as_money(self):
        from hde.break_even import read_back_block
        out = solve_break_even(_base(), "condo.purchase_costs", lo=0.0, hi=6_000.0)
        text = format_break_even(out)
        assert "bracket 0–6,000" in text
        assert "no crossing between 0 and 6,000: condo is cheaper at both ends" in text
        assert "0.00%" not in text
        assert read_back_block(out)[0].startswith("break-even condo.purchase_costs (bracket 0–6,000;")

    def test_the_formatter_goes_by_kind_not_magnitude(self):
        from hde.sweep import _fmt_value
        assert _fmt_value("condo.purchase_costs", 0.0) == "0"
        assert _fmt_value("condo.purchase_costs", 6_000) == "6,000"
        assert _fmt_value("condo.other_recurring_costs.tax.annual_amount", 0.5) == "0"
        assert _fmt_value("condo.value_growth_rate", 0.0) == "0.00%"
        assert _fmt_value("condo.value_growth_rate", 1.5) == "150.00%"
        assert _fmt_value("years", 7) == "7"


class TestTheWidenHintRespectsAZeroFloor:
    """A property-tax rate widened to 0% was then offered "widen with
    … = -0.005:…" (2026-09-08): the hint walked one bracket width below a
    floor the input cannot cross. A dollar figure, a tax or cost rate, a
    mortgage rate or a volatility stops at 0 — the hint stops there too, and
    at 0 the only direction left is up. A growth, escalation, return or
    discount rate may be negative and keeps the open floor."""

    def _rent_cheaper(self):
        raw = _base()
        raw["rent"]["monthly_rent"] = 1_200
        return raw

    def test_a_money_key_at_zero_says_so_and_widens_upward(self):
        from hde.break_even import read_back_block, threshold_sentences
        out = solve_break_even(self._rent_cheaper(), "condo.purchase_costs", lo=0.0, hi=6_000.0)
        record = out["no_crossing"]
        assert record["narrows_toward"] == "low" and record["at_floor"] is True
        assert record["widen"] == [0.0, 12_000.0]
        [line] = threshold_sentences("condo.purchase_costs", out, BAND)
        assert line == ("no crossing down to 0 on condo.purchase_costs: rent is cheaper throughout "
                        "that range — widen upward with --break-even condo.purchase_costs=0:12000")
        assert line in format_break_even(out) and line in read_back_block(out)[1]

    def test_a_tax_rate_never_goes_negative(self):
        from hde.break_even import threshold_sentences
        raw = self._rent_cheaper()
        raw["condo"]["property_tax_rate"] = 0.01
        del raw["condo"]["other_recurring_costs"]
        out = solve_break_even(raw, "condo.property_tax_rate", lo=0.0, hi=0.005)
        assert out["no_crossing"]["widen"] == [0.0, 0.01]
        [line] = threshold_sentences("condo.property_tax_rate", out, BAND)
        assert line.endswith("widen upward with --break-even condo.property_tax_rate=0:0.01")
        assert "-0.005" not in line

    def test_a_growth_rate_keeps_the_open_floor(self):
        from hde.break_even import threshold_sentences
        out = solve_break_even(_base(), "condo.value_growth_rate", lo=0.0, hi=0.01)
        assert out["no_crossing"]["narrows_toward"] == "low"
        assert out["no_crossing"]["at_floor"] is False
        assert out["no_crossing"]["widen"] == [-0.01, 0.01]
        [line] = threshold_sentences("condo.value_growth_rate", out, BAND)
        assert line.endswith("widen with --break-even condo.value_growth_rate=-0.01:0.01")

    def test_the_floor_is_by_key_kind(self):
        from hde.break_even import floor_at_zero
        assert floor_at_zero("condo.purchase_costs") and floor_at_zero("rent.monthly_rent")
        assert floor_at_zero("house.property_tax_rate") and floor_at_zero("condo.mortgage_rate")
        assert floor_at_zero("condo.other_recurring_costs.tax.annual_amount")
        assert floor_at_zero("simulation.investment_return_vol")
        assert not floor_at_zero("condo.value_growth_rate")
        assert not floor_at_zero("rent.rent_escalation_rate")
        assert not floor_at_zero("discount_rate")


class TestQuotedRateThresholdsCarryTheRealEquivalent:
    """`--break-even <opt>.value_growth_rate` in nominal mode solves on quoted
    rates; each band edge and the crossing state their real equivalent once,
    and an `across` row over such a key labels its point the same way
    (2026-09-08). Real mode is unchanged."""

    PI = 0.021

    def _nominal(self):
        raw = _base()
        del raw["rates"]
        raw["economic"] = {"mode": "nominal", "inflation_rate": self.PI}
        raw["condo"]["all_cash"] = True
        del raw["condo"]["down_payment"], raw["condo"]["mortgage_rate"], raw["condo"]["mortgage_term_years"]
        raw["rent"]["monthly_rent"] = 1_800
        raw["rent"]["invested_down_payment"] = 400_000
        return raw

    def test_each_edge_and_the_crossing_say_the_real_figure_once(self):
        from hde.rates import deflate
        out = solve_break_even(self._nominal(), "condo.value_growth_rate")
        assert out["real_equivalent_inflation"] == self.PI
        [be] = out["break_evens"]
        lo, hi = be["tie_band"]
        v = be["value"]
        assert be["sentence"] == (
            f"{be['cheaper_below']} is cheaper below {lo:.2%} ({deflate(lo, self.PI):.2%} real); "
            f"too close to call between {lo:.2%} and {hi:.2%} ({deflate(hi, self.PI):.2%} real); "
            f"{be['cheaper_above']} is cheaper above {hi:.2%} "
            f"(crossing {v:.2%}, {deflate(v, self.PI):.2%} real)")
        assert be["sentence"] in format_break_even(out)

    def test_real_mode_is_unchanged(self):
        out = solve_break_even(_base(), "condo.value_growth_rate", lo=-0.02, hi=0.05)
        assert out["real_equivalent_inflation"] is None
        for be in out["break_evens"]:
            assert "real" not in be["sentence"]

    def test_an_across_row_over_a_quoted_rate_labels_its_point(self):
        from hde.break_even import across_row_sentence, read_back_block
        raw = self._nominal()
        base = solve_break_even(raw, "rent.monthly_rent")
        across = solve_break_even_across(raw, "rent.monthly_rent", None, None,
                                         "condo.value_growth_rate", [0.0, 0.02])
        assert across["real_equivalent_inflation"] == self.PI
        text = across_row_sentence("rent.monthly_rent", "condo.value_growth_rate",
                                   across["rows"][0], BAND, pi=self.PI)
        assert text.startswith("condo.value_growth_rate=0.00% (-2.06% real): ")
        base["across"] = [across]
        assert any(line.startswith("break-even rent.monthly_rent at condo.value_growth_rate=0.00% (-2.06% real): ")
                   for line in read_back_block(base))
        assert any("at condo.value_growth_rate=2.00% (-0.10% real): " in line
                   for line in format_break_even(base).splitlines() + read_back_block(base))


def _with_income(raw=None):
    """`_base()` with an income block: rent $2,000/mo is 30.0% of $80,000, and
    the condo's ratio climbs with the price: 31.95% at $375,000, and 32.03%,
    past the 32% default, at $376,000 (2026-10-01)."""
    raw = _base() if raw is None else raw
    raw["income"] = {"annual_income": 80_000, "income_growth_rate": 0.0}
    return raw


def _affordability_at(raw, key, value):
    """The per-option affordability a single run at `value` prints, computed
    here without the break-even code, so a test can tell which point the
    solver priced."""
    from hde.sweep import affordability_of
    return affordability_of(compute_deterministic(load_config_dict(with_value(raw, key, value))))


class TestNoCrossingPricesAffordabilityAtBothSearchedEnds:
    """Board round 12 item 3 (2026-10-01, docs/specs/2026-10-01-threshold-seed-above-the-line.md
    §4): a break-even with no crossing printed no affordability at all, in the
    text or the JSON, while a sweep over the same range found the top of it
    past the household's threshold. The no-crossing line now carries the
    crossing branch's affordability figures at the two ends it searched.

    The bracket 250,000–390,000 on `_with_income()` has no crossing (condo is
    cheaper throughout). The seed, 400,000, lies outside it, and its condo
    ratio, 34.0%, differs from both ends: 21.9% at 250,000 and 33.2% at 390,000."""

    KEY = "condo.initial_value"
    LO, HI = 250_000.0, 390_000.0
    LINE = ("no crossing between 250,000 and 390,000: condo is cheaper at both ends — "
            "widen with --break-even condo.initial_value=250000:530000")
    BLOCK = [
        f"  {LINE}",
        "  affordability at both searched ends (highest cost/income ratio; years above the 32% threshold):",
        "    rent 30.0% (0 yr(s) over) at every quoted point",
        "    at the low end 250,000: condo 21.9% (0 yr(s) over)",
        "    at the high end 390,000: condo 33.2% (10 yr(s) over)",
    ]

    def _solve(self, raw=None):
        return solve_break_even(_with_income() if raw is None else raw, self.KEY, lo=self.LO, hi=self.HI)

    def test_the_text_block_prints_the_ratio_at_both_ends(self):
        out = self._solve()
        assert out["break_evens"] == []
        lines = format_break_even(out).splitlines()
        start = lines.index(self.BLOCK[0])
        assert lines[start:start + len(self.BLOCK)] == self.BLOCK

    def test_the_figures_are_the_searched_ends_and_not_the_seed(self):
        raw = _with_income()
        out = self._solve(raw)
        record = out["no_crossing"]["affordability"]
        lo, hi = _affordability_at(raw, self.KEY, self.LO), _affordability_at(raw, self.KEY, self.HI)
        seed = _affordability_at(raw, self.KEY, raw["condo"]["initial_value"])
        assert record == {"threshold": 0.32, "lo": lo, "hi": hi}
        assert seed["condo"] != lo["condo"] and seed["condo"] != hi["condo"]
        text = format_break_even(out)
        assert f"condo {seed['condo']['max_ratio']:.1%}" not in text
        assert f"at the low end 250,000: condo {lo['condo']['max_ratio']:.1%}" in text
        assert f"at the high end 390,000: condo {hi['condo']['max_ratio']:.1%}" in text

    def test_the_read_back_carries_both_ends_on_the_line_it_pastes(self):
        from hde.break_even import read_back_block
        header, line = read_back_block(self._solve())[:2]
        assert header == ("break-even condo.initial_value (bracket 250,000–390,000; band = 5% of the "
                          "cheaper option's PV; affordability = highest cost/income ratio; years above "
                          "the 32% threshold; rent 30.0% (0 yr(s) over) at every quoted point)")
        assert line == (f"break-even condo.initial_value: {self.LINE}; affordability at the low end "
                        f"250,000: condo 21.9% (0 yr(s) over) · at the high end 390,000: condo 33.2% "
                        f"(10 yr(s) over)")

    def test_an_across_row_with_no_crossing_carries_it_too(self):
        from hde.break_even import across_row_sentence, read_back_block
        raw = _with_income()
        out = self._solve(raw)
        out["across"] = [solve_break_even_across(raw, self.KEY, self.LO, self.HI,
                                                 "rent.monthly_rent", [1_500, 2_200])]
        crossed, flat = out["across"][0]["rows"]
        assert crossed["break_evens"] and not flat["break_evens"]
        at = with_value(raw, "rent.monthly_rent", 2_200)
        assert flat["no_crossing"]["affordability"] == {
            "threshold": 0.32, "lo": _affordability_at(at, self.KEY, self.LO),
            "hi": _affordability_at(at, self.KEY, self.HI)}
        row = ("rent.monthly_rent=2,200: " + self.LINE + "; affordability (highest cost/income ratio; "
               "years above the 32% threshold): rent 33.0% (10 yr(s) over) at every quoted point · "
               "at the low end 250,000: condo 21.9% (0 yr(s) over) · at the high end 390,000: "
               "condo 33.2% (10 yr(s) over)")
        assert across_row_sentence(self.KEY, "rent.monthly_rent", flat, BAND) == row
        assert f"    {row}" in format_break_even(out).splitlines()
        assert ("break-even condo.initial_value at rent.monthly_rent=2,200: " + self.LINE
                + "; affordability rent 33.0% (10 yr(s) over) at every quoted point · at the low end "
                "250,000: condo 21.9% (0 yr(s) over) · at the high end 390,000: condo 33.2% "
                "(10 yr(s) over)") in read_back_block(out)

    def test_the_at_floor_branch_prints_both_ends_it_priced(self):
        """`no crossing down to 0`: the fee of 0 is a point the loader accepts
        and the scan priced, so it is an end like any other."""
        raw = _with_income()
        raw["rent"]["monthly_rent"] = 1_200
        out = solve_break_even(raw, "condo.monthly_fee", lo=0.0, hi=200.0)
        assert out["no_crossing"]["at_floor"] is True
        assert out["no_crossing"]["affordability"]["lo"] == _affordability_at(raw, "condo.monthly_fee", 0.0)
        lines = format_break_even(out).splitlines()
        start = lines.index("  no crossing down to 0 on condo.monthly_fee: rent is cheaper throughout "
                            "that range — widen upward with --break-even condo.monthly_fee=0:400")
        assert lines[start + 1:start + 5] == [
            "  affordability at both searched ends (highest cost/income ratio; years above the 32% threshold):",
            "    rent 18.0% (0 yr(s) over) at every quoted point",
            "    at the low end 0: condo 29.5% (0 yr(s) over)",
            "    at the high end 200: condo 32.5% (10 yr(s) over)",
        ]

    def test_without_an_income_block_nothing_new_prints(self):
        from hde.break_even import across_row_sentence, read_back_block
        raw = _base()
        out = self._solve(raw)
        assert out["break_evens"] == [] and out["no_crossing"]["affordability"] is None
        out["across"] = [solve_break_even_across(raw, self.KEY, self.LO, self.HI,
                                                 "rent.monthly_rent", [2_200])]
        [row] = out["across"][0]["rows"]
        assert not row["break_evens"] and row["no_crossing"]["affordability"] is None
        assert "affordability" not in format_break_even(out)
        assert not any("affordability" in line for line in read_back_block(out))
        assert across_row_sentence(self.KEY, "rent.monthly_rent", row, BAND) == (
            "rent.monthly_rent=2,200: " + self.LINE)

    def test_the_cli_prints_and_serializes_it(self, tmp_path, monkeypatch, capsys):
        import json, sys
        import yaml
        from hde.cli import main as cli_main
        for raw, priced in ((_with_income(), True), (_base(), False)):
            cfg = tmp_path / "two.yaml"
            cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
            args = ["hde", str(cfg), "--no-monte-carlo", "--break-even", f"{self.KEY}=250000:390000"]
            monkeypatch.setattr(sys, "argv", args + ["--json"])
            assert cli_main() == 0
            record = json.loads(capsys.readouterr().out)["break_evens"][0]["no_crossing"]
            monkeypatch.setattr(sys, "argv", args)
            assert cli_main() == 0
            lines = capsys.readouterr().out.splitlines()
            start = lines.index(self.BLOCK[0])
            if priced:
                assert set(record["affordability"]) == {"threshold", "lo", "hi"}
                assert record["affordability"]["hi"]["condo"]["years_exceeding"] == list(range(1, 11))
                assert lines[start:start + len(self.BLOCK)] == self.BLOCK
                assert ("break-even condo.initial_value: " + self.LINE + "; affordability at the low end "
                        "250,000: condo 21.9% (0 yr(s) over) · at the high end 390,000: condo 33.2% "
                        "(10 yr(s) over)") in lines
            else:
                assert record["affordability"] is None
                assert not any("affordability at both searched ends" in line for line in lines)
                assert f"break-even condo.initial_value: {self.LINE}" in lines


def _montreal(**condo):
    """The shipped first-time buyer, Montréal, seeded at $380,000, a step above
    the $361,762 its cash covers at 20% down, with any `condo` key overridden."""
    import yaml
    from pathlib import Path
    doc = yaml.safe_load((Path(__file__).resolve().parents[1] / "examples"
                          / "first_time_buyer_montreal.yaml").read_text(encoding="utf-8"))
    doc["condo"].update({"initial_value": 380_000, **condo})
    return doc


def _priced_at(raw, key, value):
    """`_affordability_at` for a config with a `sources:` block: `load_at`
    lifts the declaration on the scanned key, as every scan path does."""
    from hde.sweep import affordability_of, load_at
    return affordability_of(compute_deterministic(load_at(raw, key, value)))


class TestTheNoCrossingGuardsPriceWhatTheSolverSearched:
    """Three guards a fresh verifier found unpinned on 2026-10-01: each one
    survived a mutant that drops or misplaces a figure the user reads. Every
    test reads the rendered lines, not only the record behind them."""

    KEY = "condo.initial_value"
    RENT = "    rent 23.4% (0 yr(s) over) at every quoted point"

    def test_a_refused_bracket_is_priced_at_the_ends_it_searched_not_the_ends_asked(self):
        """`=0:300000` refuses 0, 37,500 and 75,000 (the cash nets a down
        payment above the price), so the search runs 112,500–300,000. The
        asked low end of 0 is a price the loader refuses: priced there, the
        whole record would read as no income block and nothing would print."""
        raw = _montreal()
        out = solve_break_even(raw, self.KEY, lo=0.0, hi=300_000.0)
        assert out["break_evens"] == [] and out["refused"]["count"] == 3
        record = out["no_crossing"]
        assert (record["lo"], record["hi"]) == (112_500.0, 300_000.0)
        assert record["affordability"] == {
            "threshold": 0.32, "lo": _priced_at(raw, self.KEY, 112_500.0),
            "hi": _priced_at(raw, self.KEY, 300_000.0)}
        lines = format_break_even(out).splitlines()
        start = lines.index("  no crossing between 112,500 and 300,000: condo is cheaper at both ends — "
                            "widen with --break-even condo.initial_value=112500:487500")
        assert lines[start - 1].endswith("; searched 112,500–300,000")
        assert lines[start + 1:start + 5] == [
            "  affordability at both searched ends (highest cost/income ratio; years above the 32% threshold):",
            self.RENT,
            "    at the low end 112,500: condo 11.0% (0 yr(s) over)",
            "    at the high end 300,000: condo 24.5% (0 yr(s) over)",
        ]

    def test_an_end_the_config_refuses_beyond_still_carries_both_ends(self):
        """`widen` is None when the gap narrows toward an end the config
        refuses beyond (95% loan-to-value past 1,075,000 here): the record
        still carries the affordability, on the base line and on an `across`
        row alike."""
        from hde.break_even import read_back_block
        refused_beyond = ("no crossing between 200,000 and 1,075,000: condo is cheaper at both ends — "
                          "the gap narrows toward the high end, which the config refuses beyond; "
                          "no wider bracket reaches a crossing")
        ends = ("at the low end 200,000: condo 17.3% (0 yr(s) over) · "
                "at the high end 1,075,000: condo 84.0% (10 yr(s) over)")
        raw = _montreal()
        out = solve_break_even(raw, self.KEY, lo=200_000.0, hi=1_600_000.0)
        out["across"] = [solve_break_even_across(raw, self.KEY, 200_000.0, 1_600_000.0,
                                                 "condo.value_growth_rate", [0.021, 0.051])]
        crossed, flat = out["across"][0]["rows"]
        assert crossed["break_evens"] and flat["no_crossing"]["widen"] is None
        hot = with_value(raw, "condo.value_growth_rate", 0.051)
        assert flat["no_crossing"]["affordability"] == {
            "threshold": 0.32, "lo": _priced_at(hot, self.KEY, 200_000.0),
            "hi": _priced_at(hot, self.KEY, 1_075_000.0)}
        row = next(line for line in format_break_even(out).splitlines()
                   if line.startswith("    condo.value_growth_rate=5.10% (2.94% real): "))
        assert refused_beyond in row and row.endswith(" · " + ends)
        assert (f"break-even condo.initial_value at condo.value_growth_rate=5.10% (2.94% real): "
                f"{refused_beyond}; affordability {ends}") in read_back_block(out)

        base = solve_break_even(hot, self.KEY, lo=200_000.0, hi=1_600_000.0)
        assert base["break_evens"] == [] and base["no_crossing"]["widen"] is None
        lines = format_break_even(base).splitlines()
        start = lines.index(f"  {refused_beyond}")
        assert lines[start + 1:start + 5] == [
            "  affordability at both searched ends (highest cost/income ratio; years above the 32% threshold):",
            self.RENT,
            "    at the low end 200,000: condo 17.3% (0 yr(s) over)",
            "    at the high end 1,075,000: condo 84.0% (10 yr(s) over)",
        ]
        assert read_back_block(base)[1] == (
            f"break-even condo.initial_value: {refused_beyond}; affordability {ends}")

    def test_a_band_edge_outside_the_bracket_leaves_the_crossing_and_the_other_edge_priced(self):
        """The band's low edge, 438,607, lies below a bracket that starts at
        440,000, so it is None. The crossing and the high edge are still
        priced: one missing point does not withhold the two that exist."""
        from hde.break_even import read_back_block
        raw = _montreal()
        out = solve_break_even(raw, self.KEY, lo=440_000.0, hi=900_000.0)
        [be] = out["break_evens"]
        assert be["tie_band"][0] is None and be["tie_band"][1] is not None
        aff = be["affordability"]
        assert aff["tie_band"][0] is None
        assert aff["value"] == _priced_at(raw, self.KEY, be["value"])
        assert aff["tie_band"][1] == _priced_at(raw, self.KEY, be["tie_band"][1])
        lines = format_break_even(out).splitlines()
        start = lines.index("  affordability at the crossing and the band edges (highest cost/income "
                            "ratio; years above the 32% threshold):")
        assert lines[start + 1:start + 4] == [
            self.RENT,
            "    at the crossing 468,398: condo 37.7% (7 yr(s) over)",
            "    at the band's high edge 503,436: condo 40.3% (9 yr(s) over)",
        ]
        assert read_back_block(out)[1].endswith(
            "; affordability at the crossing 468,398: condo 37.7% (7 yr(s) over) · "
            "at the band's high edge 503,436: condo 40.3% (9 yr(s) over)")


class TestAnIntegerEndIsPricedAndLabelledAtTheWholeNumberTheSolverPriced:
    """Seat ruling 2026-10-01 (F4): the solver prices an integer key at
    `int(round(v))`, so the grid point 3.75 of `mortgage_term_years=0:30` is a
    4-year term to the solver. The no-crossing record printed `3.75` and priced
    affordability at a 3.75-year term, 130.0%, a point no solve priced; at 4 the
    figure is 101.6%. The record now carries the whole number at both ends, and
    the sentence, the affordability lines and the JSON all name it. The refusal
    line's `searched` span and the widen hint are not the record's and do not
    move."""

    KEY = "condo.mortgage_term_years"
    LINE = ("no crossing between 4 and 30: condo is cheaper at both ends — the gap narrows toward "
            "the low end, which the config refuses beyond; no wider bracket reaches a crossing")

    def test_the_low_end_is_the_four_year_term_the_solver_priced(self):
        raw = _montreal()
        out = solve_break_even(raw, self.KEY, lo=0.0, hi=30.0)
        assert out["break_evens"] == [] and out["searched"] == [[3.75, 30.0]]
        record = out["no_crossing"]
        assert (record["lo"], record["hi"]) == (4, 30)
        assert all(type(record[end]) is int for end in ("lo", "hi"))
        four = _priced_at(raw, self.KEY, 4)
        assert four["condo"]["years_exceeding"] == [1, 2, 3, 4]
        assert four != _priced_at(raw, self.KEY, 3.75)
        assert record["affordability"] == {"threshold": 0.32, "lo": four,
                                           "hi": _priced_at(raw, self.KEY, 30)}
        lines = format_break_even(out).splitlines()
        start = lines.index(f"  {self.LINE}")
        assert lines[start - 1].endswith("; searched 3.75–30.0")
        assert lines[start + 1:start + 5] == [
            "  affordability at both searched ends (highest cost/income ratio; years above the 32% threshold):",
            "    rent 23.4% (0 yr(s) over) at every quoted point",
            "    at the low end 4: condo 101.6% (4 yr(s) over)",
            "    at the high end 30: condo 29.0% (0 yr(s) over)",
        ]

    def test_an_across_row_names_the_whole_numbers_and_keeps_its_widen_hint(self):
        from hde.break_even import read_back_block
        raw = _montreal()
        out = solve_break_even(raw, self.KEY, lo=0.0, hi=30.0)
        out["across"] = [solve_break_even_across(raw, self.KEY, 0.0, 30.0,
                                                 "rent.monthly_rent", [1_500, 1_850])]
        cheap = out["across"][0]["rows"][0]
        assert (cheap["no_crossing"]["lo"], cheap["no_crossing"]["hi"]) == (4, 30)
        assert ("break-even condo.mortgage_term_years at rent.monthly_rent=1,500: no crossing "
                "between 4 and 30: rent is cheaper at both ends — widen with --break-even "
                "condo.mortgage_term_years=4:56; affordability rent 18.9% (0 yr(s) over) at every "
                "quoted point · at the low end 4: condo 101.6% (4 yr(s) over) · at the high end 30: "
                "condo 29.0% (0 yr(s) over)") in read_back_block(out)
