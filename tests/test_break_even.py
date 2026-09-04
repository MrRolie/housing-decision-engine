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
        "years": 10,
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
        # Band-first, and the JSON entry leads with the same sentence (three dogfood
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
            "years": 10, "discount_rate": 0.03, "province": "QC",
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
    """Round 5b: the persona ran a demographic-prior variant to test the threshold's
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
