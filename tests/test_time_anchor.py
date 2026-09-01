"""
Time-anchor provenance tests (parameter-provenance remediation Task C).

Two drift classes guard the START_CALENDAR_YEAR anchor that maps sim year t ->
calendar year -> demographic band:
- prior-vs-constant mismatch (constants_as_of far from the anchor) — hard fail
  inside load_scenario_prior (loader-level tests live in test_market_scenario);
- wall-clock staleness (current year past the anchor) — loud warning at the
  side-effecty edges (CLI stderr, MCP response warnings), never a refusal.

The pure helper takes the year as a parameter; the wiring keeps it injectable
so these tests never touch the wall clock.
"""

import datetime
import json
import sys
from pathlib import Path

import pytest

from hde.cli import main as cli_main
from hde.market_scenario import time_anchor_violations

GEO = "MTL_RMR"
GOLDEN = Path(__file__).parent / "fixtures" / "scenario_prior_golden.json"


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------

class TestTimeAnchorViolations:
    def test_current_year_matching_prior_is_clean(self):
        assert time_anchor_violations(2026, "2026-06-01") == []

    def test_no_prior_is_clean(self):
        assert time_anchor_violations(2026, None) == []

    def test_wall_clock_past_anchor_is_stale(self):
        violations = time_anchor_violations(2027, "2026")
        assert len(violations) == 1
        assert "stale" in violations[0]

    def test_prior_far_from_anchor_mismatches(self):
        violations = time_anchor_violations(2026, "2029")
        assert len(violations) == 1
        assert "misaligned" in violations[0]

    def test_staleness_and_mismatch_coexist(self):
        violations = time_anchor_violations(2027, "2020")
        assert len(violations) == 2

    def test_unparseable_constants_as_of_violates(self):
        violations = time_anchor_violations(2026, "FY26")
        assert len(violations) == 1
        assert "constants_as_of" in violations[0]


# ---------------------------------------------------------------------------
# MCP wiring (year injected, wall clock untouched)
# ---------------------------------------------------------------------------

def _mcp_config(prior_path):
    return {
        "years": 10,
        "discount_rate": 0.03,
        "house": {"initial_value": 400_000, "annual_maintenance_rate": 0.015,
                  "all_cash": True},
        "market_scenario": {"path": str(prior_path), "geography": GEO},
    }


class TestMCPTimeAnchorWarnings:
    def test_stale_year_appends_warning_to_run_response(self, tmp_path):
        from mcp_server import registry, tools
        assert "error" not in tools.define_scenario(
            "anchor-stale", _mcp_config(GOLDEN))
        try:
            resp = tools.run_comparison("anchor-stale", mode="deterministic",
                                        current_year=2027)
            assert "error" not in resp
            stale = [w for w in resp["warnings"] if "stale" in w]
            assert stale and "2027" in stale[0]
        finally:
            registry.remove("anchor-stale")

    def test_current_year_adds_no_anchor_warning(self, tmp_path):
        from mcp_server import registry, tools
        assert "error" not in tools.define_scenario(
            "anchor-clean", _mcp_config(GOLDEN))
        try:
            resp = tools.run_comparison("anchor-clean", mode="deterministic",
                                        current_year=2026)
            assert "error" not in resp
            assert not [w for w in resp["warnings"] if "stale" in w]
        finally:
            registry.remove("anchor-clean")

    def test_mismatched_prior_returns_error_dict(self, tmp_path):
        from mcp_server import registry, tools
        prior = json.loads(GOLDEN.read_text(encoding="utf-8"))
        prior["data_vintage"]["constants_as_of"] = "2029-01-01"
        path = tmp_path / "mismatched.json"
        path.write_text(json.dumps(prior), encoding="utf-8")
        assert "error" not in tools.define_scenario(
            "anchor-mismatch", _mcp_config(path))
        try:
            resp = tools.run_comparison("anchor-mismatch", mode="deterministic",
                                        current_year=2026)
            assert "error" in resp
            assert "misaligned" in resp["error"]
        finally:
            registry.remove("anchor-mismatch")


# ---------------------------------------------------------------------------
# CLI wiring (wall clock faked via the datetime module the CLI reads)
# ---------------------------------------------------------------------------

def _write_config(tmp_path, prior_path) -> str:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        f"""
years: 8
discount_rate: 0.03
economic:
  mode: real
house:
  initial_value: 400000
  all_cash: true
simulation:
  num_sims: 10
market_scenario:
  path: {prior_path}
  geography: {GEO}
""",
        encoding="utf-8",
    )
    return str(cfg)


def _fake_today(monkeypatch, year):
    import hde.cli as cli_mod

    class _FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(year, 6, 1)

    monkeypatch.setattr(cli_mod.datetime, "date", _FakeDate)


class TestCLITimeAnchorGuard:
    def test_stale_wall_clock_warns_on_stderr_and_continues(self, tmp_path, monkeypatch, capsys):
        _fake_today(monkeypatch, 2027)
        monkeypatch.setattr(sys, "argv", ["hde", _write_config(tmp_path, GOLDEN)])
        assert cli_main() == 0
        err = capsys.readouterr().err
        assert "[warning]" in err
        assert "stale" in err
        assert "Traceback" not in err

    def test_current_wall_clock_adds_no_warning(self, tmp_path, monkeypatch, capsys):
        _fake_today(monkeypatch, 2026)
        monkeypatch.setattr(sys, "argv", ["hde", _write_config(tmp_path, GOLDEN)])
        assert cli_main() == 0
        err = capsys.readouterr().err
        assert "stale" not in err

    def test_mismatched_prior_exits_1_with_clean_error(self, tmp_path, monkeypatch, capsys):
        prior = json.loads(GOLDEN.read_text(encoding="utf-8"))
        prior["data_vintage"]["constants_as_of"] = "2029-01-01"
        path = tmp_path / "mismatched.json"
        path.write_text(json.dumps(prior), encoding="utf-8")
        _fake_today(monkeypatch, 2026)
        monkeypatch.setattr(sys, "argv", ["hde", _write_config(tmp_path, path)])
        assert cli_main() == 1
        err = capsys.readouterr().err
        assert err.startswith("Error:")
        assert "misaligned" in err
        assert "Traceback" not in err

    def test_no_market_scenario_block_skips_guard(self, tmp_path, monkeypatch, capsys):
        _fake_today(monkeypatch, 2030)
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            """
years: 8
discount_rate: 0.03
economic:
  mode: real
house:
  initial_value: 400000
  all_cash: true
""",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg)])
        assert cli_main() == 0
        assert "stale" not in capsys.readouterr().err
