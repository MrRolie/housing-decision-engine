"""
Reference docs that restate registry facts are pinned to the registry
(readiness plan G.3, 2026-09-01): the CONFIG_SCHEMAS.md defaults table must
quote each anchored default's value and citation tag exactly, and must not
attribute a source to a structural default.
"""

import re

import pytest
from pathlib import Path

from hde.anchors import ANCHORS, _ECHO_ALIASES, is_reference, short_cite

DOC = Path(__file__).resolve().parents[1] / "docs" / "reference" / "CONFIG_SCHEMAS.md"
ROW = re.compile(r"^\| `([\w.]+)` \| ([^|]+?) \| ([^|]+?) \|$", re.MULTILINE)


def _rows():
    section = DOC.read_text(encoding="utf-8").split("### Defaults Summary", 1)[1]
    section = section.split("## Validation Rules", 1)[0]
    return [(f, d.strip(), s.strip()) for f, d, s in ROW.findall(section)]


def test_defaults_table_matches_the_registry():
    rows = _rows()
    assert len(rows) > 30
    seen = set()
    for field, default, source in rows:
        name = _ECHO_ALIASES.get(field, field)
        anchor = ANCHORS.get(name)
        if anchor is None:
            assert source == "—", f"{field}: cites {source!r} but has no anchor"
            continue
        seen.add(name)
        assert float(default) == anchor.value, (field, default, anchor.value)
        assert source == short_cite(field), (field, source, short_cite(field))
    # every dataclass-default anchor appears in the table (consumed-elsewhere ones
    # need not). Jurisdiction reference tables are excluded because they are not
    # defaults at all — the engine never applies one, so a "Defaults Summary" row
    # for them would claim the opposite of the truth. Their own doc surface is
    # `hde --print-anchors`, pinned in test_reference_anchors. The mortgage-insurance
    # premium and the land-transfer-tax schedules are tables of bands, not per-field
    # defaults, documented under their own headings in CONFIG_SCHEMAS.md.
    expected = {n for n in ANCHORS
                if not n.startswith(("verdict.", "market_scenario.",
                                     "mortgage_insurance.", "land_transfer_tax."))
                and not is_reference(n)
                and n != "economic.inflation_rate.nominal_planning"}
    assert expected <= seen, sorted(expected - seen)


# ---------------------------------------------------------------------------
# Figure glossary completeness (readiness plan D.2): every key the engine
# prints or emits has a glossary row, so "what is this number?" always has an
# answer without opening src/.
# ---------------------------------------------------------------------------

from hde.config import load_config
from hde.deterministic import compute_deterministic
from hde.models import (
    CONDO_BREAKDOWN_KEYS,
    HOUSE_BREAKDOWN_KEYS,
    RENT_BREAKDOWN_KEYS,
    compute_verdict,
)
from hde.monte_carlo import run_monte_carlo
from hde.serialization import det_to_dict, mc_to_dict, verdict_to_dict

ARCH = Path(__file__).resolve().parents[1] / "docs" / "reference" / "ARCHITECTURE.md"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
# Containers, not figures; the prior's provenance block is identity, not a figure.
STRUCTURAL = {"condo", "house", "rent", "breakdown", "affordability", "affordability_mc"}
SKIP_SUBTREES = {"market_scenario"}


def _glossary_keys():
    text = ARCH.read_text(encoding="utf-8")
    section = text.split("## Figure glossary", 1)[1]
    return set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", section))


def _leaf_keys(doc, out):
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k in SKIP_SUBTREES:
                continue
            if isinstance(v, dict):
                if k not in STRUCTURAL:
                    out.add(k)
                _leaf_keys(v, out)
            else:
                out.add(k)
    return out


def _emitted_keys():
    keys = set()
    for name in ("advanced_config.yaml", "income_shock.yaml", "rent_vs_condo_vs_house.yaml"):
        spec = load_config(EXAMPLES / name)
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        _leaf_keys(det_to_dict(det), keys)
        _leaf_keys(mc_to_dict(mc), keys)
        _leaf_keys(verdict_to_dict(compute_verdict(
            det, mc, years=spec.simulation.years, discount_rate=spec.simulation.discount_rate)), keys)
    return keys - STRUCTURAL


def test_glossary_covers_every_emitted_figure():
    glossary = _glossary_keys()
    required = set(CONDO_BREAKDOWN_KEYS | HOUSE_BREAKDOWN_KEYS | RENT_BREAKDOWN_KEYS) | _emitted_keys()
    assert {"total_pv", "prob_house_cheapest", "margin_frac", "years_exceeding"} <= required
    missing = required - glossary
    assert not missing, f"figures without a glossary row: {sorted(missing)}"


def test_no_tracked_text_file_carries_a_merge_conflict_marker():
    """2026-09-04: a three-way patch merge left `<<<<<<<` markers in API_CONTRACT.md
    and the commit went through because nothing read the file. Tracked text is
    what the public repo serves; a marker in it is a broken document."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    files = subprocess.run(["git", "ls-files", "*.md", "*.py", "*.yaml", "*.txt", "*.toml"],
                           cwd=root, capture_output=True, text=True, check=True).stdout.split()
    offenders = []
    for rel in files:
        path = root / rel
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.startswith(("<<<<<<< ", ">>>>>>> ")):
                offenders.append(f"{rel}:{n}")
    assert not offenders, offenders


def test_prompts_doc_is_linked_and_every_command_it_shows_runs(monkeypatch, capsys):
    """PROMPTS.md sits beside the README for the person who just cloned the repo: every
    flag it names must be a real option and every config path it runs must exist."""
    import re
    from hde.cli import main

    root = Path(__file__).resolve().parents[1]
    text = (root / "PROMPTS.md").read_text(encoding="utf-8")
    assert "PROMPTS.md" in (root / "README.md").read_text(encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["hde", "--help"])
    with pytest.raises(SystemExit):
        main()
    help_out = capsys.readouterr().out
    flags = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", text))
    assert flags >= {"--print-schema", "--print-anchors", "--read-back", "--json", "--break-even"}
    for flag in sorted(flags):
        assert flag in help_out, flag
    for rel in re.findall(r"uv run hde (examples/[\w./-]+\.yaml)", text):
        assert (root / rel).exists(), rel
    for rel in re.findall(r"\]\(([\w./-]+\.md)\)", text):
        assert (root / rel).exists(), rel


def test_every_example_config_runs_and_is_walked_through():
    """Every shipped example is a template someone will copy: it must load and
    run, be named in the walkthrough (examples/README.md — a file the README
    does not name is one nobody is led to), and quote any province code it
    sets (an unquoted ON is a YAML boolean, which the loader refuses)."""
    import yaml

    readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    configs = sorted(EXAMPLES.glob("*.yaml"))
    assert "first_time_buyer_montreal.yaml" in {c.name for c in configs}
    for cfg in configs:
        assert cfg.name in readme, cfg.name
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        for block in (data, data.get("condo") or {}, data.get("house") or {}):
            if "province" in block:
                assert isinstance(block["province"], str), (cfg.name, block["province"])
        assert compute_deterministic(load_config(cfg)) is not None, cfg.name
