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
        assert "Sweep rent.monthly_rent (2 points;" in out and "flip: cheapest changes from rent" in out

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
