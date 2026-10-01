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
TEXT = SKILL.read_text(encoding="utf-8")                     # the hot path, loaded on every trigger
REFERENCES = sorted((SKILL.parent / "references").glob("*.md"))
ALL_TEXT = TEXT + "".join(r.read_text(encoding="utf-8") for r in REFERENCES)  # hot path + references


def test_every_reference_file_is_pointed_at_and_every_pointer_resolves():
    """Progressive disclosure (skill restructure 2026-09-02): SKILL.md is the hot
    path and names each reference file with when to read it; a file nobody
    points at is dead weight, a pointer to a missing file is a broken step."""
    assert REFERENCES, "references/ is empty"
    for ref in REFERENCES:
        assert f"references/{ref.name}" in TEXT, ref.name
    for name in set(re.findall(r"references/([a-z-]+\.md)", ALL_TEXT)):
        assert (SKILL.parent / "references" / name).exists(), name


def test_hot_path_stays_under_the_documented_body_budget():
    """Claude Code's skill guidance: keep SKILL.md under 500 lines and move
    reference material out; the evaluation rounds grew it to 436 lines / 5,400
    words before the restructure. Pin the hot path well under both."""
    assert TEXT.count("\n") < 300, TEXT.count("\n")
    assert len(TEXT.split()) < 2600, len(TEXT.split())


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
    assert "acts 1 and 2 always" in TEXT
    assert "act 3" in TEXT and "uncertainty input is on" in TEXT   # single-path runs skip act 3
    assert "act 5" in TEXT and "market_scenario" in TEXT
    assert "act 6" in TEXT and "owned option" in TEXT


def test_skill_elicits_goals_and_reads_defaults_back():
    assert "## Elicit first" in TEXT
    for phrase in ("How long do you expect to stay", "What does \"best\" mean",
                   "Which of your numbers are you least sure of", "assumptions read-back",
                   "defaults applied"):
        assert phrase in TEXT, phrase
    assert "Decisiveness is not the headline" in TEXT


def test_skill_points_at_the_docs_that_exist():
    root = SKILL.parents[3]
    for rel in ("examples/README.md", "docs/reference/ARCHITECTURE.md",
                "tests/fixtures/scenario_prior_golden.json",
                "examples/showcase_demographic_prior.yaml"):
        assert rel in ALL_TEXT, rel
        assert (root / rel).exists(), rel


def test_skill_has_no_machine_specific_paths():
    """A cloned repo runs anywhere: the skill may not name this machine's paths."""
    for needle in ("~/", "/home/", "/Users/"):
        assert needle not in ALL_TEXT, needle


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


def test_skill_translates_real_world_items_and_dispatches_sweeps():
    """The evaluation's top friction: owner costs silently zero, flip points hand-rolled.
    Hot-path pins are the rules applied on every run; the rest live in references/."""
    for phrase in ("property tax", "purchase_costs", "--sweep", "Not modelled",
                   "A range is two configs", "Cash line", "sticker",
                   "financed_purchase_costs", '"not run"', "down payment + purchase costs",
                   "ANNUAL volatility"):
        assert phrase in TEXT, phrase
    for phrase in ("other_recurring_costs", "Quick-sense lane", "One side known"):
        assert phrase in ALL_TEXT, phrase


def test_answer_checklist_reads_the_engine_lines_back():
    """Adherence fix (three threshold serves dropped a warned default that the
    prose required at several sites): the answer step is a checklist naming the
    engine line to read, placed before the prose."""
    assert "checklist first" in TEXT
    for item in ("every `[warning]` line", "`defaults applied:`", "`decisiveness:`",
                 "`Year-1 cash`", "`Affordability`", "No source for", "Not modelled"):
        assert item in TEXT, item
    assert TEXT.index("checklist first") < TEXT.index("## Verification")
    # The gist shape (2026-09-05): the checklist keeps the full block as the
    # rule, names the short block for the gist, and the reference that
    # pastes it names the flag that prints it.
    assert "the gist shape pastes the short block" in " ".join(TEXT.split())
    assert "--read-back short" in ALL_TEXT


LANES = ("quick-sense.md", "threshold-lane.md")


def _lane(name: str) -> str:
    return " ".join((SKILL.parent / "references" / name).read_text(encoding="utf-8").split())


@pytest.mark.parametrize("name", LANES)
def test_the_price_threshold_seeds_above_the_20_percent_line(name):
    """Operator ruling 2026-09-22 (docs/specs/2026-10-01-threshold-seed-above-the-line.md
    §3): a seed a step BELOW the 20%-down price printed `none required` and an
    OSFI qualifying rate for a household whose crossing was insured. Both lanes
    now seed at the first round figure above it, with the engine's refusal past
    the maximum insurable loan-to-value as the reason to take a finer step."""
    text = _lane(name)
    assert "first round figure ABOVE" in text
    assert "maximum insurable loan-to-value" in text
    assert "step BELOW" not in text
    assert "still covers 20%" not in text


@pytest.mark.parametrize("name", LANES)
def test_the_lanes_quote_the_no_crossing_affordability_the_engine_prints(name):
    """Board round 12 item 3: a no-crossing break-even now prints affordability
    at both ends it searched. Each lane names that line by the header the
    engine prints, so the assistant quotes it instead of going without."""
    from hde.break_even import format_break_even, solve_break_even
    header = "affordability at both searched ends"
    assert header in _lane(name)
    raw = {"years": 10, "rates": "real",
           "rent": {"monthly_rent": 2000, "rent_escalation_rate": 0.0, "invested_down_payment": 85_000},
           "condo": {"initial_value": 400_000, "monthly_fee": 300, "value_growth_rate": 0.0,
                     "down_payment": 80_000, "mortgage_rate": 0.04, "mortgage_term_years": 25,
                     "purchase_costs": 5_000},
           "income": {"annual_income": 80_000, "income_growth_rate": 0.0}}
    out = solve_break_even(raw, "condo.initial_value", lo=250_000.0, hi=300_000.0)
    assert out["break_evens"] == []
    assert f"  {header} (highest cost/income ratio" in format_break_even(out)
