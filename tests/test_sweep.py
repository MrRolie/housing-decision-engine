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
