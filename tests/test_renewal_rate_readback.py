"""What a renewal-rate path file run prints (docs/specs/2026-10-01-renewal-rate-path-file.md
§5 and §7; §9 rows 11, 15 and the sweep half of 16).

Every figure on the `renewal rate paths:` line is recomputed here from the
file's own bytes, by arithmetic written independently of the engine's: the
exact central row by `statistics.median` on Fractions, the band by hand-rolled
linear interpolation, the sha256 by `hashlib`. Every rendered-output pin reads
what a user is shown, stdout, stderr, `--json` and the read-back, and each is
paired with the same config's no-file twin, on which the phrase it forbids
does print: a pin whose forbidden text never prints anywhere checks nothing.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import statistics
import sys
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

import hde.cli as cli_mod
from hde.config import all_warnings, load_config_dict
from hde.serialization import format_assumptions
from hde.sweep import run_sweep

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
DATA = FIXTURES / "renewal_paths"
FIXTURE = FIXTURES / "renewal_rate_paths.yaml"

# §7's rendered-output configs, and the opt-in fixture (semi-annual, with a
# `sources:` block, so its stdout carries the `user-stated:` label).
RENDERED = [DATA / "hvr_opens_at.yaml", DATA / "condo5.yaml", DATA / "hvr_example.yaml", FIXTURE]
# What the ladder-warning loop and the ladder's source clause print, each
# naming a ladder the config cannot state beside the file.
FORBIDDEN = ("mortgage_renewal_rates", "opens at", "are inert", "the stated renewal path",
             "a stated scenario")


@pytest.fixture(autouse=True)
def _at_the_repo_root(monkeypatch):
    # The committed configs name their path files relative to the repo root.
    monkeypatch.chdir(ROOT)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _hde(monkeypatch, tmp_path, cfg, *flags):
    """`hde <cfg> <flags>` in-process: (exit code, stdout, stderr)."""
    if isinstance(cfg, dict):
        path = tmp_path / f"cfg{len(list(tmp_path.iterdir()))}.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        cfg = path
    monkeypatch.setattr(sys, "argv", ["hde", str(cfg), *flags])
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_mod.main()
    return code, out.getvalue(), err.getvalue()


def _laddered_twin(cfg: dict) -> dict:
    """The same config with no path file: each reading option types the
    central row's first n_o quoted rates as its ladder (the contract rate
    when it reads none, since a ladder is never empty). It is the no-file
    config one step away, not a pricing twin: the ladder is read in the
    contract's convention, the file in its own."""
    spec = load_config_dict(copy.deepcopy(cfg))
    twin = copy.deepcopy(cfg)
    del twin["renewal_rates"]
    for name in ("condo", "house"):
        opt = getattr(spec, name)
        if name in twin and opt is not None and opt.mortgage_renewal_rates_quoted is not None:
            twin[name]["mortgage_renewal_rates"] = (list(opt.mortgage_renewal_rates_quoted)
                                                    or [twin[name]["mortgage_rate"]])
    twin.pop("sources", None)
    return twin


# ---------------------------------------------------------------------------
# §9 row 11: the rendered output of a file run
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("config", RENDERED, ids=lambda p: p.stem)
def test_a_file_run_prints_no_sentence_about_a_ladder(config, monkeypatch, tmp_path):
    code, out, err = _hde(monkeypatch, tmp_path, config)
    assert code == 0, err[-400:]
    for stream, text in (("stdout", out), ("stderr", err)):
        hits = [phrase for phrase in FORBIDDEN if phrase in text]
        assert hits == [], (stream, hits)
        # The bare word cannot be the pin: the sources echo's `user-stated:`
        # label carries it on any run with a `sources:` block.
        loose = [line for line in text.splitlines() if re.search(r"(?<!user-)stated", line)]
        assert loose == [], (stream, loose)


def test_the_twins_print_what_the_file_run_does_not():
    """The positive control of the pin above: each phrase it forbids prints on
    the no-file twin of the config it was measured on (§7), so the pin's
    absence is the gate's work and not a phrase that never prints."""
    expected = {"hvr_opens_at": ("opens at", "a stated scenario", "mortgage_renewal_rates"),
                "condo5": ("are inert", "the stated renewal path", "a stated scenario"),
                "hvr_example": ("the stated renewal path", "a stated scenario")}
    for stem, phrases in expected.items():
        cfg = _yaml(DATA / f"{stem}.yaml")
        spec = load_config_dict(_laddered_twin(cfg))
        text = "\n".join(all_warnings(spec) + format_assumptions(spec))
        missing = [p for p in phrases if p not in text]
        assert missing == [], (stem, missing)


def test_the_ladder_loop_is_gated_whole_and_nothing_past_it(monkeypatch, tmp_path):
    """The gate covers the ladder loop and stops there: the posted-rate
    warning right after it still fires on a file run whose contract rate is
    the posted one, on stdout and stderr both."""
    cfg = _yaml(DATA / "hvr_example.yaml")
    cfg["house"]["mortgage_rate"] = 0.0609
    code, out, err = _hde(monkeypatch, tmp_path, cfg)
    assert code == 0, err[-400:]
    posted = "house.mortgage_rate 6.09% is the POSTED 5-year rate"
    assert posted in err and posted in out
    assert [phrase for phrase in FORBIDDEN if phrase in out + err] == []


def test_the_renewals_line_names_the_central_row_and_reads_nothing_for_an_unread_option(
        monkeypatch, tmp_path):
    _, out, _ = _hde(monkeypatch, tmp_path, DATA / "condo5.yaml", "--read-back")
    lines = out.splitlines()
    house = [line for line in lines if line.startswith("house renewals:")]
    condo = [line for line in lines if line.startswith("condo renewals:")]
    assert len(house) == 1 and house[0].endswith(
        " · central row 0 of tests/fixtures/renewal_paths/two_paths.json")
    # The condo amortizes over its own term: it reads no column, so no row
    # prices anything for it and the line carries no source clause at all.
    assert condo == ["condo renewals: 5-year term, 0 renewals over the 5-year amortization · "
                     "year 1 4.400% $72,690/yr"]


def test_the_renewals_block_carries_the_files_convention(monkeypatch, tmp_path):
    """A semi-annual file beside an effective-annual contract: each renewal
    entry is labelled with the file's quote convention."""
    cfg = _yaml(FIXTURE)
    assert cfg["house"]["mortgage_rate_compounding"] == "effective_annual"
    _, out, _ = _hde(monkeypatch, tmp_path, FIXTURE, "--json")
    renewals = json.loads(out)["assumptions"]["mortgage_renewals"]
    assert [(r["option"], r["compounding"]) for r in renewals] == [("house", "semi_annual")]
    # The no-file twin keeps the contract's convention, as before.
    twin = _laddered_twin(cfg)
    _, out, _ = _hde(monkeypatch, tmp_path, twin, "--json")
    assert [r["compounding"] for r in json.loads(out)["assumptions"]["mortgage_renewals"]] == [
        "effective_annual"]


# ---------------------------------------------------------------------------
# §9 row 15: the read-back line, every figure recomputed
# ---------------------------------------------------------------------------

def _percentile(values, q):
    """numpy's default (linear) percentile, written out."""
    xs = sorted(values)
    h = (len(xs) - 1) * q / 100
    lo = int(h)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (h - lo) * (xs[hi] - xs[lo])


def _expected(config: Path):
    """Every figure of the line, from the config and the file's bytes."""
    cfg = _yaml(config)
    path = cfg["renewal_rates"]["path"]
    raw = (ROOT / path).read_bytes()
    doc = json.loads(raw)
    term, horizon = doc["term_years"], cfg["years"]
    # P: the largest count of renewals any reading option prices inside the
    # horizon. Every config here reads the file with a house amortized past
    # the horizon, so P is the horizon's own count, capped by the grid.
    priced = min(len(doc["renewal_years"]), (horizon - 1) // term)
    rows = doc["paths"]
    exact = [[Fraction(v) for v in row[:priced]] for row in rows]
    median = [statistics.median(column) for column in zip(*exact)]
    distances = [sum((x - m) ** 2 for x, m in zip(row, median)) for row in exact]
    central = distances.index(min(distances))
    tied = distances.count(min(distances)) - 1
    years = doc["renewal_years"][:priced]
    band = {year: (_percentile([row[k] for row in rows], 5),
                   _percentile([row[k] for row in rows], 95))
            for k, year in enumerate(years)}
    return dict(path=path, sha=hashlib.sha256(raw).hexdigest(), doc=doc, rows=rows,
                priced=priced, central=central, tied=tied, years=years, band=band)


def _line(e) -> str:
    """§7's template, filled."""
    tie = (f", tied with {e['tied']} other row{'' if e['tied'] == 1 else 's'}, lowest index"
           if e["tied"] else "")
    words = {"semi_annual": "semi-annual", "effective_annual": "effective annual"}
    provenance = e["doc"]["provenance"]
    return (
        f"renewal rate paths: {e['path']} · sha256 {e['sha'][:12]}… · central row {e['central']} "
        f"of {len(e['rows']):,} (nearest the per-renewal median{tie}): "
        + ", ".join(f"{r:.2%}" for r in e["rows"][e["central"]][:e["priced"]])
        + f" as quoted ({words[e['doc']['compounding']]}) · 5–95% by renewal: "
        + ", ".join(f"year {y} {lo:.2%}–{hi:.2%}" for y, (lo, hi) in e["band"].items())
        + f" · method: {provenance['method']} · data window: {provenance['data_window']} · "
          f"validation: {provenance['validation']['text']} · drawn independently of every "
          f"other draw (the discount rate is fixed)")


def test_the_example_line_is_the_specs_own():
    """§7 prints this line filled with the example's figures; the expected
    builder above reproduces it, so it is the template and not a paraphrase."""
    e = _expected(DATA / "hvr_example.yaml")
    assert (e["central"], e["tied"]) == (0, 1)
    assert _line(e) == (
        "renewal rate paths: tests/fixtures/renewal_paths/two_paths.json · sha256 b3827bb92169… "
        "· central row 0 of 2 (nearest the per-renewal median, tied with 1 other row, lowest "
        "index): 2.00%, 2.00%, 2.00% as quoted (effective annual) · 5–95% by renewal: year 6 "
        "2.30%–7.70%, year 11 2.30%–7.70%, year 16 2.30%–7.70% · method: synthetic, not a "
        "calibration: two hand-set paths · data window: none · validation: none: an example, "
        "not a model · drawn independently of every other draw (the discount rate is fixed)")


@pytest.mark.parametrize("config", [DATA / "hvr_example.yaml", DATA / "hvr_opens_at.yaml",
                                    FIXTURE], ids=lambda p: p.stem)
def test_every_figure_on_the_line_is_recomputed(config, monkeypatch, tmp_path):
    e = _expected(config)
    _, out, _ = _hde(monkeypatch, tmp_path, config, "--read-back")
    block = out.splitlines()
    assert [line for line in block if line.startswith("renewal rate paths:")] == [_line(e)]
    # Right after the renewals: lines, and once.
    at = block.index(_line(e))
    assert block[at - 1].startswith("house renewals:")
    assert sum("renewal rate paths:" in line for line in block) == 1


def test_the_fixtures_tell_rows_apart():
    """The opt-in fixture's central row is not row 0 and is not tied, and the
    example's is a tie: a line that printed row 0 always, or never said tie,
    or always said one, fails one of the two."""
    fixture, example = _expected(FIXTURE), _expected(DATA / "hvr_example.yaml")
    assert fixture["central"] != 0 and fixture["tied"] == 0
    assert example["tied"] == 1


def test_the_json_block_carries_the_lines_figures(monkeypatch, tmp_path):
    e = _expected(FIXTURE)
    _, out, _ = _hde(monkeypatch, tmp_path, FIXTURE, "--json")
    assumptions = json.loads(out)["assumptions"]
    block = assumptions["renewal_rate_paths"]
    assert set(block) == {
        "path", "file_sha256", "schema_version", "term_years", "renewal_years", "priced_years",
        "compounding", "as_of", "rows", "central_index", "central_rates_quoted", "tied_rows",
        "band", "provenance", "independent_of_channels"}
    assert block["path"] == e["path"] and block["file_sha256"] == e["sha"]
    assert block["schema_version"] == "1" and block["term_years"] == 5
    assert block["renewal_years"] == [6, 11, 16, 21] and block["priced_years"] == [6, 11, 16]
    assert block["compounding"] == "semi_annual" and block["as_of"] == "2026-10-01"
    assert block["rows"] == 12
    assert (block["central_index"], block["tied_rows"]) == (e["central"], e["tied"])
    assert block["central_rates_quoted"] == e["rows"][e["central"]][:3]
    assert set(block["band"]) == {"6", "11", "16"}
    for year, (lo, hi) in e["band"].items():
        assert block["band"][str(year)] == pytest.approx([lo, hi], rel=1e-12, abs=0)
    assert block["provenance"] == e["doc"]["provenance"]
    # Every channel but the renewal rates' own (8); income (7) is no channel.
    assert block["independent_of_channels"] == [0, 1, 2, 3, 4, 5, 6]
    # The same line rides `assumptions.read_back`, once, right after renewals:.
    read_back = assumptions["read_back"]
    assert [line for line in read_back if line.startswith("renewal rate paths:")] == [_line(e)]
    assert read_back[read_back.index(_line(e)) - 1].startswith("house renewals:")


def test_an_absent_as_of_is_null(monkeypatch, tmp_path):
    doc = json.loads((DATA / "two_paths.json").read_text(encoding="utf-8"))
    del doc["as_of"]
    path = tmp_path / "no_as_of.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    cfg = _yaml(DATA / "hvr_example.yaml")
    cfg["renewal_rates"]["path"] = str(path)
    _, out, _ = _hde(monkeypatch, tmp_path, cfg, "--json")
    assert json.loads(out)["assumptions"]["renewal_rate_paths"]["as_of"] is None


def test_the_short_block_names_the_section_it_left_out(monkeypatch, tmp_path):
    _, out, _ = _hde(monkeypatch, tmp_path, FIXTURE, "--read-back", "short")
    lines = out.splitlines()
    assert not any(line.startswith("renewal rate paths:") for line in lines)
    closing = lines[-1]
    assert closing.startswith("full read-back: ")
    named = closing.split("(", 1)[1].split(")", 1)[0].split(", ")
    assert named[named.index("renewals") + 1] == "renewal rate paths"


def test_a_no_file_run_has_no_line_no_block_and_no_section(monkeypatch, tmp_path):
    twin = _laddered_twin(_yaml(FIXTURE))
    _, out, _ = _hde(monkeypatch, tmp_path, twin, "--json")
    assumptions = json.loads(out)["assumptions"]
    assert "renewal_rate_paths" not in assumptions
    assert not any("renewal rate paths" in line
                   for line in assumptions["lines"] + assumptions["read_back"]
                   + [assumptions["read_back_short"][-1]])


# ---------------------------------------------------------------------------
# §9 row 16, the sweep half: each point names its own central row
# ---------------------------------------------------------------------------

def _central_at(cfg: dict, horizon: int) -> int:
    e = _expected(FIXTURE)
    priced = min(4, (horizon - 1) // 5)
    exact = [[Fraction(v) for v in row[:priced]] for row in e["rows"]]
    median = [statistics.median(column) for column in zip(*exact)]
    distances = [sum((x - m) ** 2 for x, m in zip(row, median)) for row in exact]
    return distances.index(min(distances))


def test_each_sweep_point_names_the_central_row_its_own_load_chose():
    cfg = _yaml(FIXTURE)
    result = run_sweep(cfg, "years", [5, 10, 15, 20], monte_carlo=False)
    first, *ran = result["rows"]
    # A horizon inside the first term prices no renewal: R15 refuses it.
    assert first["error"] == ("no reading option renews inside the 5-year horizon "
                              "(first renewal: year 6)")
    assert "central_row" not in first
    expected = [_central_at(cfg, h) for h in (10, 15, 20)]
    assert expected == [2, 2, 9]
    assert [row["central_row"] for row in ran] == expected
    for row, index in zip(ran, expected):
        assert row["sentence"].endswith(f", central row {index}"), row["sentence"]


def test_the_central_row_reaches_the_rendered_sweep_lines(monkeypatch, tmp_path):
    cfg = _yaml(FIXTURE)
    cfg["simulation"]["num_sims"] = 200
    _, out, _ = _hde(monkeypatch, tmp_path, cfg, "--sweep", "years=10,15,20", "--read-back")
    points = [line for line in out.splitlines() if line.startswith("years=")]
    assert [line.rsplit(", central row ", 1)[1] for line in points] == ["2", "2", "9"]
    assert points[-1].startswith("years=20 (= base): ")


def test_a_no_file_sweep_names_no_central_row():
    twin = _laddered_twin(_yaml(FIXTURE))
    result = run_sweep(twin, "years", [10, 20], monte_carlo=False)
    assert all("central_row" not in row for row in result["rows"])
    assert all("central row" not in row["sentence"] for row in result["rows"])
