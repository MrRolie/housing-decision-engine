"""
CLI tests (src/hde/cli.py): typed-refusal exit paths and stderr hygiene.
"""

import sys

import pytest

from hde.cli import main as cli_main


def _write_config(tmp_path, extra: str = "") -> str:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        f"""
years: 8
discount_rate: 0.03
economic:
  mode: real
{extra}house:
  initial_value: 400000
  all_cash: true
simulation:
  num_sims: 20
  random_seed: 42
""",
        encoding="utf-8",
    )
    return str(cfg)


class TestCliErrorPaths:
    def test_bad_prior_file_exits_1_without_traceback(self, tmp_path, monkeypatch, capsys):
        """F3: ScenarioPriorError from the engine → 'Error: <msg>' on stderr, exit 1."""
        config = _write_config(
            tmp_path,
            extra="market_scenario:\n  path: /nonexistent/prior.json\n  geography: MTL_RMR\n",
        )
        monkeypatch.setattr(sys, "argv", ["hde", config])
        assert cli_main() == 1
        err = capsys.readouterr().err
        assert err.startswith("Error:")
        assert "not found" in err
        assert "Traceback" not in err

    def test_config_typo_exits_1_with_did_you_mean(self, tmp_path, monkeypatch, capsys):
        """F1: a typo'd config key refuses CLI-side with a suggestion, no traceback."""
        cfg = tmp_path / "typo.yaml"
        cfg.write_text(
            """
years: 8
discount_rate: 0.03
house:
  initial_value: 400000
  all_cash: true
  value_growth_rat: 0.02
""",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg)])
        assert cli_main() == 1
        err = capsys.readouterr().err
        assert "unknown key 'house.value_growth_rat'" in err
        assert "did you mean 'value_growth_rate'?" in err
        assert "Traceback" not in err


def test_prog_is_hde(monkeypatch, capsys):
    """F4: argparse prog is 'hde' (the shipped entry point), not the legacy name."""
    monkeypatch.setattr(sys, "argv", ["hde", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 0
    assert "usage: hde" in capsys.readouterr().out


class TestCoherenceWarnings:
    def test_warnings_printed_to_stderr(self, tmp_path, monkeypatch, capsys):
        """U2: experiment A config — real mode + 5% growth DECLARED real + mortgage 6%
        (under the default as-quoted convention a typed 5% is a quote and is deflated,
        so the tripwire has nothing to catch there — 2026-09-05)."""
        cfg = tmp_path / "exp_a.yaml"
        cfg.write_text(
            """
years: 25
discount_rate: 0.05
rates: real
economic:
  mode: real
house:
  initial_value: 500000
  value_growth_rate: 0.05
  down_payment: 100000
  mortgage_rate: 0.06
  mortgage_term_years: 25
rent:
  monthly_rent: 2200
simulation:
  num_sims: 20
""",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--no-monte-carlo"])
        assert cli_main() == 0
        err = capsys.readouterr().err
        assert "[warning] house.value_growth_rate=5.0%" in err
        assert "nominal quote" in err
        assert "[warning]" in err.split("\n")[0] or err.startswith("[warning]")


class TestJsonContract:
    """A.5: the --json document is the agent-native contract; pin its shape and
    its provenance half (readiness plan 2026-09-01)."""

    def _doc(self, tmp_path, monkeypatch, capsys, extra_args=()):
        import json
        config = _write_config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--json", *extra_args])
        assert cli_main() == 0
        return json.loads(capsys.readouterr().out)

    def test_top_level_keys(self, tmp_path, monkeypatch, capsys):
        doc = self._doc(tmp_path, monkeypatch, capsys)
        assert set(doc) == {"engine_version", "warnings", "assumptions", "verdict",
                            "deterministic", "monte_carlo"}
        assert doc["engine_version"]
        assert doc["monte_carlo"] is not None
        assert set(doc["verdict"]) == {"best", "runner_up", "margin_pv", "margin_frac",
                                       "monthly_equivalent", "prob_best", "decisive", "state",
                                       "rule", "reason", "mc_mean_best", "mc_best", "mc_prob_best"}
        assert doc["verdict"]["state"] in {"option", "tie", "disagreement"}

    def test_break_even_rides_json(self, tmp_path, monkeypatch, capsys):
        import json
        cfg = tmp_path / "two.yaml"
        cfg.write_text(
            "years: 10\n"
            "rent:\n  monthly_rent: 2000\n  rent_escalation_rate: 0.0\n  invested_down_payment: 85000\n"
            "condo:\n  initial_value: 400000\n  monthly_fee: 300\n  value_growth_rate: 0.0\n"
            "  down_payment: 80000\n  mortgage_rate: 0.04\n  mortgage_term_years: 25\n  purchase_costs: 5000\n"
            "  other_recurring_costs:\n    - {name: tax, annual_amount: 3000, escalation_rate: 0.0}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--json", "--no-monte-carlo",
                                          "--break-even", "rent.monthly_rent"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        assert "break_evens" in doc and doc["break_evens"][0]["key"] == "rent.monthly_rent"
        assert set(doc["break_evens"][0]) >= {"options", "bracket", "base_value", "tie_band_fraction", "break_evens"}
        assert doc["break_evens"][0]["break_evens"][0]["cheaper_below"] == "rent"

    def test_no_monte_carlo_yields_null_not_missing(self, tmp_path, monkeypatch, capsys):
        doc = self._doc(tmp_path, monkeypatch, capsys, ["--no-monte-carlo"])
        assert "monte_carlo" in doc and doc["monte_carlo"] is None

    def test_every_defaulted_key_carries_a_source(self, tmp_path, monkeypatch, capsys):
        doc = self._doc(tmp_path, monkeypatch, capsys, ["--no-monte-carlo"])
        entries = doc["assumptions"]["defaults_applied"]
        assert entries
        for entry in entries:
            if entry["kind"] == "mode":
                continue
            assert entry["anchor"]["source"], entry["key"]
            assert entry["kind"] != "uncited", entry["key"]


def test_print_anchors_dumps_the_registry(monkeypatch, capsys):
    import json
    from hde.anchors import ANCHORS
    monkeypatch.setattr(sys, "argv", ["hde", "--print-anchors"])
    assert cli_main() == 0
    dump = json.loads(capsys.readouterr().out)
    assert set(dump) == set(ANCHORS)
    assert all(v["source"] for v in dump.values())


def test_story_status_lines_never_pollute_json_stdout(tmp_path, monkeypatch, capsys):
    """Round-6 dogfood: `--story DIR --json` printed 'Saved plot:' lines after the
    document and the saved output did not parse. Under --json, stdout is the
    document alone; status goes to stderr."""
    import json
    cfg = _write_config(tmp_path)
    out_dir = tmp_path / "story"
    monkeypatch.setattr(sys, "argv", ["hde", cfg, "--json", "--no-monte-carlo", "--story", str(out_dir)])
    assert cli_main() == 0
    captured = capsys.readouterr()
    doc = json.loads(captured.out)  # the whole of stdout parses
    assert "engine_version" in doc
    assert "Story written:" in captured.err and "Saved plot:" in captured.err
    assert (out_dir / "STORY.md").exists()


class TestQuietLine:
    """-q prints one line: the totals, then the same three-state verdict
    sentence the report prints (2026-09-04) — a summary that names the
    totals but not which one wins, or whether the futures agree, is not a
    summary of the verdict."""

    def test_the_summary_line_carries_the_verdict_sentence(self, tmp_path, monkeypatch, capsys):
        cfg = _write_config(tmp_path, extra="rent:\n  monthly_rent: 1500\n")
        monkeypatch.setattr(sys, "argv", ["hde", cfg, "-q"])
        assert cli_main() == 0
        out = capsys.readouterr().out.strip()
        assert "\n" not in out
        totals, verdict = out.split(" | ")
        assert totals.startswith("House: $") and "Rent: $" in totals
        assert verdict.startswith(("Cheapest:", "Too close to call:", "Best guess says"))

    def test_one_option_keeps_the_bare_totals(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["hde", _write_config(tmp_path), "-q"])
        assert cli_main() == 0
        out = capsys.readouterr().out.strip()
        assert out.startswith("House: $") and " | " not in out
