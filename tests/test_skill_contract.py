"""
The hde skill (.claude/skills/hde/SKILL.md) is the agent-facing intake
contract; its concrete claims about the CLI are pinned here so a renamed flag
or a dropped JSON key makes the skill fail loudly instead of quietly lying
(readiness plan F.3, 2026-09-01).
"""

import json
import re
import sys
from pathlib import Path

import pytest

from hde.cli import main as cli_main

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "hde" / "SKILL.md"
TEXT = SKILL.read_text(encoding="utf-8")


def _help(monkeypatch, capsys) -> str:
    monkeypatch.setattr(sys, "argv", ["hde", "--help"])
    with pytest.raises(SystemExit):
        cli_main()
    return capsys.readouterr().out


def test_every_flag_the_skill_names_is_a_real_option(monkeypatch, capsys):
    flags = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", TEXT))
    assert flags >= {"--print-schema", "--print-anchors", "--json", "--story"}
    help_out = _help(monkeypatch, capsys)
    for flag in sorted(flags):
        assert flag in help_out, flag


def test_json_keys_the_skill_promises_are_the_document(tmp_path, monkeypatch, capsys):
    promised = {"engine_version", "warnings", "assumptions", "verdict", "deterministic", "monte_carlo"}
    for key in promised:
        assert f"`{key}`" in TEXT, key
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "years: 8\ndiscount_rate: 0.03\nhouse:\n  initial_value: 400000\n  all_cash: true\n"
        "rent:\n  monthly_rent: 1800\n  invested_down_payment: 400000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["hde", str(cfg), "--json", "--no-monte-carlo"])
    assert cli_main() == 0
    doc = json.loads(capsys.readouterr().out)
    assert set(doc) == promised
    assert all(e["anchor"]["source"] for e in doc["assumptions"]["defaults_applied"]
               if e["kind"] != "mode")


def test_skill_states_the_act_gating_the_renderer_implements():
    assert "acts 1–4 always" in TEXT
    assert "act 5" in TEXT and "market_scenario" in TEXT
    assert "act 6" in TEXT and "owned option" in TEXT


def test_skill_elicits_goals_and_reads_defaults_back():
    assert "## Elicit first" in TEXT
    for phrase in ("How long do you expect to stay", "What does \"best\" mean",
                   "Which uncertainties", "assumptions read-back", "defaults applied"):
        assert phrase in TEXT, phrase
    assert "Decisiveness is not the headline" in TEXT


def test_skill_points_at_the_docs_that_exist():
    root = SKILL.parents[3]
    for rel in ("examples/README.md", "docs/reference/ARCHITECTURE.md",
                "tests/fixtures/scenario_prior_golden.json",
                "examples/showcase_demographic_prior.yaml"):
        assert rel in TEXT, rel
        assert (root / rel).exists(), rel


def test_skill_has_no_machine_specific_paths():
    """A cloned repo runs anywhere: the skill may not name this machine's paths."""
    for needle in ("~/", "/home/", "ai_system"):
        assert needle not in TEXT, needle


def test_skill_gates_on_missing_information():
    assert "## Missing information" in TEXT
    for phrase in ("ONE message", "scenarios/", "Invent no values", "Run only once"):
        assert phrase in TEXT, phrase


def test_claude_md_routes_housing_questions_to_the_skill():
    root = SKILL.parents[3]
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert ".claude/skills/hde/SKILL.md" in text
    assert "Missing information" in text and "scenarios/" in text
    assert "scenarios/" in (root / ".gitignore").read_text(encoding="utf-8")


def test_project_settings_preapprove_the_user_flow():
    """A first-time user gets one trust dialog and no per-action prompts: the
    engine command and writing their scenario under scenarios/ are pre-approved."""
    root = SKILL.parents[3]
    allow = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
    assert "Bash(uv run hde *)" in allow
    assert "Edit(scenarios/**)" in allow  # Edit rules govern Write too
    # A Write(...) path rule is accepted but never consulted and warns at
    # startup (Claude Code permissions docs, "Read and Edit") — friction, not cover.
    assert not any(r.startswith("Write(") for r in allow)
