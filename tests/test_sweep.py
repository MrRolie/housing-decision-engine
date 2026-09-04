"""--sweep (2026-09-02): flip points on any input, through the real loader and verdict."""

import json
import sys

import pytest

from hde.cli import main as cli_main
from hde.sweep import parse_sweep, run_sweep, with_value

RAW = {
    "years": 10,
    "condo": {"monthly_fee": 300, "initial_value": 400_000, "all_cash": True,
              "value_growth_rate": 0.01, "purchase_costs": 8_000,
              "other_recurring_costs": [{"name": "tax", "annual_amount": 3_000, "escalation_rate": 0.0}]},
    "rent": {"monthly_rent": 1_800, "invested_down_payment": 400_000},
}


class TestParse:
    def test_list_and_range_forms(self):
        assert parse_sweep("years=5,10,20") == ("years", [5, 10, 20])
        key, values = parse_sweep("condo.value_growth_rate=0:0.04:5")
        assert key == "condo.value_growth_rate" and values[0] == 0 and values[-1] == pytest.approx(0.04) and len(values) == 5

    @pytest.mark.parametrize("bad", ["years", "years=", "=5", "years=1:2", "years=1:2:1"])
    def test_malformed_refused(self, bad):
        with pytest.raises(ValueError):
            parse_sweep(bad)

    def test_with_value_sets_nested_and_top_level(self):
        assert with_value(RAW, "condo.initial_value", 1)["condo"]["initial_value"] == 1
        assert with_value(RAW, "simulation.years", 3)["years"] == 3
        assert RAW["condo"]["initial_value"] == 400_000  # untouched


class TestRun:
    def test_rows_carry_totals_and_verdict_and_flip(self):
        result = run_sweep(RAW, "rent.monthly_rent", [500, 6000], monte_carlo=False)
        rows = result["rows"]
        assert [r["best"] for r in rows] == ["rent", "condo"]
        assert set(rows[0]["totals"]) == {"condo", "rent"}
        assert result["flips"] == [{"from_value": 500, "from_best": "rent", "to_value": 6000, "to_best": "condo"}]

    def test_refused_point_is_reported_not_skipped(self):
        result = run_sweep(RAW, "years", [0, 10], monte_carlo=False)
        assert "error" in result["rows"][0] and "years" in result["rows"][0]["error"]
        assert "best" in result["rows"][1] and result["flips"] == []


class TestCli:
    def _cfg(self, tmp_path):
        import yaml
        p = tmp_path / "c.yaml"; p.write_text(yaml.safe_dump(RAW)); return p

    def test_text_table_and_flip_line(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["hde", str(self._cfg(tmp_path)), "--no-monte-carlo",
                                          "--sweep", "rent.monthly_rent=500,6000"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert "Sweep rent.monthly_rent (2 points;" in out
        assert "flip rent.monthly_rent: cheapest changes from rent" in out

    def test_two_sweeps_print_two_named_no_flip_lines(self, tmp_path, monkeypatch, capsys):
        """Two --sweep flags used to print two unnamed `no flip:` lines; each
        names its key (2026-09-04)."""
        monkeypatch.setattr(sys, "argv", ["hde", str(self._cfg(tmp_path)), "--no-monte-carlo",
                                          "--sweep", "years=5,10", "--sweep", "rent.monthly_rent=1700,1900",
                                          "--read-back"])
        assert cli_main() == 0
        lines = capsys.readouterr().out.splitlines()
        assert "no flip along years: the same option is cheapest across the whole sweep" in lines
        assert "no flip along rent.monthly_rent: the same option is cheapest across the whole sweep" in lines
        assert not any(line.startswith("no flip:") for line in lines)

    def test_json_carries_sweeps_only_when_asked(self, tmp_path, monkeypatch, capsys):
        cfg = self._cfg(tmp_path)
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--json", "--no-monte-carlo", "--sweep", "years=5,10"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        assert [r["value"] for r in doc["sweeps"][0]["rows"]] == [5, 10]
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--json", "--no-monte-carlo"])
        assert cli_main() == 0
        assert "sweeps" not in json.loads(capsys.readouterr().out)

    def test_bad_sweep_is_a_clean_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["hde", str(self._cfg(tmp_path)), "--sweep", "years"])
        assert cli_main() == 1
        assert "--sweep expects" in capsys.readouterr().err


class TestFlipLinesNameTheirKey:
    def _result(self, **over):
        rows = [
            {"value": 5, "best": "rent", "mc_mean_best": "rent", "mc_best": "rent"},
            {"value": 10, "best": "house", "mc_mean_best": "house", "mc_best": "house"},
        ]
        flip = [{"from_value": 5, "from_best": "rent", "to_value": 10, "to_best": "house"}]
        # a majority turn that differs from the deterministic one, so it prints
        majority = [{"from_value": 5, "from_best": "rent", "to_value": 10, "to_best": "condo"}]
        result = {"key": "years", "rows": rows, "flips": flip,
                  "mc_mean_flips": flip, "mc_majority_flips": majority}
        result.update(over)
        return result

    def test_every_line_names_the_key(self):
        from hde.sweep import flip_lines
        lines = flip_lines(self._result())
        assert lines[0] == "flip years: cheapest changes from rent (years=5) to house (years=10)"
        assert lines[1] == "mean flip years: Monte Carlo mean favours rent (years=5) then house (years=10)"
        assert lines[2].startswith("majority flip years: Monte Carlo P(cheapest) majority favours")

    def test_no_flip_names_the_key(self):
        from hde.sweep import flip_lines
        lines = flip_lines(self._result(flips=[], mc_mean_flips=[], mc_majority_flips=[]))
        assert lines == ["no flip along years: the same option is cheapest across the whole sweep"]


class TestProbabilityExactlyAtTheFloor:
    """P(best) equal to the 65% floor is decisive by the rule (≥), and the row
    says it sits AT the floor rather than print a bare decisive flag
    (2026-09-04)."""

    def _row(self, prob):
        return {"value": 10, "totals": {"condo": 100_000.0, "rent": 110_000.0},
                "best": "condo", "runner_up": "rent", "margin_pv": 10_000.0,
                "margin_frac": 0.1, "decisive": prob >= 0.65, "rule": "mc_floor",
                "prob_best": prob, "mc_mean_best": "condo", "mc_best": "condo",
                "mc_prob_best": prob, "reason": "", "affordability": None, "monte_carlo": None}

    def _table(self, prob):
        from hde.sweep import format_sweep
        return format_sweep({"key": "years", "values": [10], "rows": [self._row(prob)],
                             "flips": [], "mc_mean_flips": [], "mc_majority_flips": []})

    def test_exactly_at_the_floor_is_marked(self):
        assert "True (mc_floor, at the floor)" in self._table(0.65)

    def test_clear_of_the_floor_is_a_plain_flag(self):
        assert "True (mc_floor) |" in self._table(0.80)
        assert "at the floor" not in self._table(0.80)
        assert "at the floor" not in self._table(0.6499)


class TestPointSentences:
    """One line per grid point in the read-back — the verdict, its margin, the
    Monte Carlo probability, the insured tier and the affordability, each
    clause only where the run has the data (2026-09-04)."""

    RICH = {
        "years": 10, "discount_rate": 0.03, "province": "QC",
        "house": {"initial_value": 500_000, "value_growth_rate": 0.0,
                  "down_payment": 75_000, "mortgage_rate": 0.04, "mortgage_term_years": 25,
                  "mortgage_insurance": "auto", "purchase_costs": 6_000},
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                 "invested_down_payment": 75_000, "investment_return_rate": 0.03},
        "income": {"annual_income": 70_000},
        "simulation": {"num_sims": 100, "random_seed": 42, "investment_return_vol": 0.10},
    }

    def test_rows_carry_the_sentence_in_the_stated_shape(self):
        result = run_sweep(self.RICH, "years", [5, 10], monte_carlo=False)
        row = result["rows"][0]
        assert row["sentence"].startswith("years=5: best ")
        assert " by $" in row["sentence"] and " of house PV)" in row["sentence"] or " of rent PV)" in row["sentence"]
        assert "P(best)" not in row["sentence"]  # no Monte Carlo ran
        assert "insured house 2.80%" in row["sentence"]
        assert "affordability house max " in row["sentence"] and "breaches years [" in row["sentence"]
        assert result["base_value"] == 10

    def test_the_probability_clause_rides_a_monte_carlo_run(self):
        result = run_sweep(self.RICH, "years", [5], monte_carlo=True)
        assert ", P(best) " in result["rows"][0]["sentence"]

    def test_at_the_floor_is_marked_in_the_sentence(self):
        from hde.sweep import point_sentence
        row = {"value": 5, "best": "house", "margin_pv": 1_000.0, "margin_frac": 0.01,
               "prob_best": 0.65, "insured": {}, "affordability": None}
        assert point_sentence("years", row) == (
            "years=5: best house by $1,000 (1.0% of house PV), P(best) 65% (at the floor)")

    def test_a_refused_point_is_one_line_too(self):
        from hde.sweep import point_sentence
        assert point_sentence("years", {"value": 0, "error": "years must be ≥ 1"}) == (
            "years=0: refused: years must be ≥ 1")

    def test_the_read_back_lines_state_an_invariant_option_once(self):
        """The renter's ratio does not move with the price: once, in the
        header, never per point."""
        from hde.sweep import sweep_lines
        result = run_sweep(self.RICH, "house.initial_value", [400_000, 450_000], monte_carlo=False)
        lines = sweep_lines(result)
        assert lines[0].startswith("sweep house.initial_value (2 points; ")
        assert "rent max 34.3% breaches years [1, 2, 3, 4, 5, 6, 7] at every point" in lines[0]
        per_point = [l for l in lines if l.startswith("house.initial_value=")]
        assert len(per_point) == 2
        assert not any("rent max" in l for l in per_point)
        assert all("affordability house max" in l for l in per_point)
        assert lines[-1].startswith("no flip along house.initial_value")

    def test_the_base_point_is_marked_and_carries_the_verdict_alone(self):
        """The base config's affordability and financing are in the block
        already; the row at the base value adds the verdict clauses only."""
        from hde.sweep import sweep_lines
        result = run_sweep(self.RICH, "years", [5, 10], monte_carlo=False)
        base = next(l for l in sweep_lines(result) if l.startswith("years=10"))
        assert base.startswith("years=10 (= base): best ")
        assert "affordability" not in base and "insured" not in base
        other = next(l for l in sweep_lines(result) if l.startswith("years=5"))
        assert "(= base)" not in other and "affordability" in other


class TestIntegerCollapse:
    """A range on an integer key produces duplicate grid points (2026-09-03
    review: `years=7:8:5` ran [7, 7, 8, 8, 8] and printed five rows, three of
    them the same answer). Dedupe after the cast, keep order, say so."""

    def test_duplicates_dropped_order_kept_and_noted(self):
        key, values = parse_sweep("years=7:8:5")
        assert values == [7, 7, 8, 8, 8]
        result = run_sweep(RAW, key, values, monte_carlo=False)
        assert result["values"] == [7, 8]
        assert [r["value"] for r in result["rows"]] == [7, 8]
        assert "5 requested points collapse to 2" in result["note"]

    def test_no_note_when_nothing_collapses(self):
        assert run_sweep(RAW, "years", [5, 10], monte_carlo=False).get("note") is None

    def test_the_note_reaches_the_text_output(self, tmp_path, monkeypatch, capsys):
        import yaml
        cfg = tmp_path / "c.yaml"; cfg.write_text(yaml.safe_dump(RAW))
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo",
                                          "--sweep", "years=7:8:5"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert "Sweep years (2 points;" in out and "collapse to 2" in out


class TestDeclaredSourcesAtGridPoints:
    """A key declared `anchor:<name>` in `sources:` is validated against the
    anchor's figure at load time — so a sweep or break-even that moves that key
    used to be refused at every off-anchor point (the copied YAML still carried
    the declaration). The grid point's value is the sweep's, not the anchor's:
    the declaration is lifted and the echo says `sweep` (2026-09-04)."""

    def _raw(self):
        return {**RAW, "discount_rate": 0.03,
                "sources": {"discount_rate": "anchor:simulation.discount_rate",
                            "years": "user"}}

    def test_the_base_config_still_validates_the_declaration(self):
        from hde.config import ConfigValidationError, load_config_dict
        bad = self._raw()
        bad["discount_rate"] = 0.04
        with pytest.raises(ConfigValidationError, match="anchor's figure"):
            load_config_dict(bad)

    def test_a_sweep_over_the_declared_key_runs_every_point(self):
        result = run_sweep(self._raw(), "discount_rate", [0.02, 0.04], monte_carlo=False)
        assert all("best" in row for row in result["rows"]), result["rows"]

    def test_the_overridden_key_is_classed_sweep_in_the_echo(self):
        from hde.sweep import load_at
        spec = load_at(self._raw(), "discount_rate", 0.04)
        assert spec.sources.classify("discount_rate") == "sweep"
        assert spec.sources.anchor_name("discount_rate") is None
        # the other declarations are untouched
        assert spec.sources.classify("years") == "user"
        assert spec.sources.declared

    def test_the_alias_form_lifts_the_top_level_declaration(self):
        from hde.sweep import load_at
        spec = load_at(self._raw(), "simulation.discount_rate", 0.04)
        assert spec.sources.classify("discount_rate") == "sweep"

    def test_an_undeclared_key_is_left_alone(self):
        from hde.sweep import load_at
        spec = load_at(self._raw(), "rent.monthly_rent", 2_500)
        assert spec.sources.classify("rent.monthly_rent") == "unattributed"
        assert spec.sources.classify("discount_rate") == "anchor"


class TestOneSidedSweepOfAPlaceholder:
    """A sweep over a key the ASSISTANT typed whose grid lies entirely on one
    side of the placeholder tests one direction of the guess and none of the
    other (2026-09-04: an Ontario tax placeholder was swept upward only, and
    the answer read the sweep as a sensitivity test)."""

    def _raw(self, source="assistant"):
        raw = {**RAW, "sources": {"rent.monthly_rent": source}}
        return raw

    def test_all_above_names_the_untested_direction(self):
        from hde.sweep import one_sided_sweep_warning
        assert one_sided_sweep_warning(self._raw(), "rent.monthly_rent", [1_900, 2_200]) == (
            "sweep of rent.monthly_rent covers only values ABOVE the placeholder 1,800; "
            "the other direction is untested")

    def test_all_below_says_below(self):
        from hde.sweep import one_sided_sweep_warning
        warning = one_sided_sweep_warning(self._raw(), "rent.monthly_rent", [1_200, 1_500])
        assert warning is not None and "BELOW the placeholder 1,800" in warning

    def test_a_grid_that_straddles_or_touches_the_base_is_quiet(self):
        from hde.sweep import one_sided_sweep_warning
        assert one_sided_sweep_warning(self._raw(), "rent.monthly_rent", [1_500, 2_200]) is None
        assert one_sided_sweep_warning(self._raw(), "rent.monthly_rent", [1_800, 2_200]) is None

    def test_a_user_stated_or_undeclared_key_is_quiet(self):
        from hde.sweep import one_sided_sweep_warning
        assert one_sided_sweep_warning(self._raw("user"), "rent.monthly_rent", [1_900, 2_200]) is None
        assert one_sided_sweep_warning(RAW, "rent.monthly_rent", [1_900, 2_200]) is None

    def test_the_alias_form_reads_the_top_level_declaration(self):
        from hde.sweep import one_sided_sweep_warning
        raw = {**RAW, "sources": {"years": "assistant"}}
        warning = one_sided_sweep_warning(raw, "simulation.years", [15, 20])
        assert warning is not None and "ABOVE the placeholder 10" in warning

    def test_it_reaches_stderr_and_the_read_back(self, tmp_path, monkeypatch, capsys):
        import yaml
        cfg = tmp_path / "c.yaml"; cfg.write_text(yaml.safe_dump(self._raw()))
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo",
                                          "--sweep", "rent.monthly_rent=1900,2200"])
        assert cli_main() == 0
        captured = capsys.readouterr()
        line = ("[warning] sweep of rent.monthly_rent covers only values ABOVE the "
                "placeholder 1,800; the other direction is untested")
        assert line in captured.err.splitlines()
        assert captured.out.splitlines().count(line) == 1
