"""The reversal register and the break-even on a renewal-rate path file
(docs/specs/2026-10-01-renewal-rate-path-file.md §5 and §6; §9 rows 9, 10
and 16).

On a file run each future's financing leg reads the row it drew, so moving a
contract rate shifts different futures by different amounts and clause (b)
of the exactness gate refuses. Clause (b') subtracts the per-row term
G_i = Fin(rho_i) - Fin(c) first. Every figure below was measured on the
committed test data.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

import hde.break_even as be
from hde.break_even import (REVERSAL_GATE_TOLERANCE, _shift_deviation_over_sd,
                            reversal_gate, reversal_register, row_financing_gaps,
                            solve_break_even)
from hde.config import load_config_dict
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo
from hde.sweep import load_at, with_value

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "fixtures" / "renewal_paths"
FIXTURE = ROOT / "tests" / "fixtures" / "renewal_rate_paths.yaml"
NO_FILE = ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"


@pytest.fixture(autouse=True)
def _at_the_repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)


def _raw(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "hde.cli", *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True)


def _plain_b(raw: dict, key: str, probe: float, paths: int = 200) -> float:
    """Clause (b) as it was: the named option's shift measured raw."""
    option = key.split(".", 1)[0]
    m = min(paths, load_config_dict(raw).simulation.num_sims)
    base = run_monte_carlo(load_at(raw, "simulation.num_sims", m))
    at = run_monte_carlo(load_at(with_value(raw, "simulation.num_sims", m), key, probe))
    return _shift_deviation_over_sd(getattr(base, option).pvs, getattr(at, option).pvs)


def _block(text: str, head: str) -> list:
    """The lines of one register section of the `--decompose` text, from its
    head to the blank line that ends it."""
    lines = text.splitlines()
    start = lines.index(head)
    end = lines.index("", start)
    return lines[start:end]


# ---------------------------------------------------------------------------
# §9 row 9: (b'), end to end
# ---------------------------------------------------------------------------

def test_the_register_under_b_prime_on_the_fixture():
    """The register's own output under (b'), on the opt-in fixture: the
    contract rate is re-priced exactly, each printed boundary was confirmed by
    a full re-simulation (`_confirmed_boundaries` prints no other), and its
    row says no draw touches it. Under clause (b) the same key printed no
    boundary at all: not_exact, worst 1.02e-01 of its own s.d."""
    run = _cli(FIXTURE, "--decompose")
    assert run.returncode == 0, run.stderr
    assert _block(run.stdout, "  NO ROW IN THE SPREAD OR THE LEVEL") == [
        "  NO ROW IN THE SPREAD OR THE LEVEL",
        "  the contract rate — house.mortgage_rate: no draw touches it",
    ]
    assert _block(run.stdout, "  WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly") == [
        "  WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly",
        "  house.mortgage_rate",
        "      bracket searched: 1.00%–10.00% [set in the engine]",
        "      solved on the central case: as it rises past 5.4212%, the central case's "
        "winner changes from house to rent",
        "      solved on the central case: as it rises past 5.4212%, the runner-up changes "
        "from rent to house",
        "      sampled on 2,000 paths at seed 42: as it rises past 5.34%, the option most "
        "futures call cheapest changes from house to rent",
        "      sampled on 2,000 paths at seed 42: as it rises past 4.92%, the decisiveness "
        "verdict changes from decisive for house to not decisive (and changes again above "
        "it, inside the bracket)",
    ]
    assert "cannot re-price exactly" not in run.stdout


@pytest.mark.parametrize("path, plain", [
    (FIXTURE, 0.10183891936869417),
    (DATA / "hvr_example.yaml", 0.07001188597291098),
])
def test_b_prime_licenses_the_contract_rate_on_a_file_run(path, plain):
    raw = _raw(path)
    assert _plain_b(raw, "house.mortgage_rate", 0.10) == plain      # (b) refuses it
    gate = reversal_gate(raw, "house.mortgage_rate", 0.10)
    assert gate["licensed"], gate["why"]
    assert gate["worst_deviation_over_sd"] <= 1e-14


def test_b_prime_widened_to_a_value_key_refuses():
    """A value key's shift varies by path on its own: (b') subtracts nothing
    from it, because the financing leg at a zero value does not move with it."""
    raw = _raw(FIXTURE)
    gate = reversal_gate(raw, "house.value_growth_rate", 0.05)
    assert not gate["licensed"]
    assert gate["worst_deviation_over_sd"] == _plain_b(raw, "house.value_growth_rate", 0.05)
    assert gate["worst_deviation_over_sd"] == 0.15580041947006154


@pytest.mark.parametrize("key, probe, figure, licensed", [
    ("house.mortgage_rate", 0.10, 9.524697909411047e-16, True),
    ("house.mortgage_renewal_rates", 0.10, 9.524697909411047e-16, True),
    ("house.value_growth_rate", 0.05, 2.744209111776317, False),
])
def test_without_a_file_b_prime_is_b_bit_for_bit(key, probe, figure, licensed):
    raw = _raw(NO_FILE)
    gate = reversal_gate(raw, key, probe)
    assert gate["worst_deviation_over_sd"] == _plain_b(raw, key, probe) == figure
    assert gate["licensed"] is licensed


def test_without_a_file_the_per_row_term_is_zero_exactly():
    spec = load_config_dict(_raw(NO_FILE))
    gaps = row_financing_gaps(spec, "house", None, 7)
    assert gaps.tolist() == [0.0] * 7


def _rows_shifted_on_the_probe(calls):
    """A simulator whose second run (the gate's probe) records rows one
    position over: the premise of (b') no longer holds."""
    import dataclasses

    def simulate(spec):
        result = run_monte_carlo(spec)
        calls.append(spec)
        if len(calls) == 2 and result.renewal_rate_rows is not None:
            rows = np.roll(result.renewal_rate_rows, 1)
            return dataclasses.replace(result, renewal_rate_rows=rows)
        return result

    return simulate


def test_a_probe_whose_recorded_rows_differ_is_refused():
    raw = _raw(FIXTURE)
    calls = []
    gate = reversal_gate(raw, "house.mortgage_rate", 0.10,
                         simulate=_rows_shifted_on_the_probe(calls))
    assert not gate["licensed"]
    assert gate["why"].startswith("moving house.mortgage_rate changes the renewal-rate row ")
    # the neighbour: the same rows on both runs license it
    assert reversal_gate(raw, "house.mortgage_rate", 0.10)["licensed"]


def _one_middle_row_changed_on_the_probe(calls):
    """A simulator whose second run (the gate's probe) records one path in the
    middle on another row and leaves every other path, path 0 included, as
    it drew: a premise check that compared only path 0 would pass it."""
    import dataclasses

    def simulate(spec):
        result = run_monte_carlo(spec)
        calls.append(spec)
        if len(calls) == 2 and result.renewal_rate_rows is not None:
            rows = result.renewal_rate_rows.copy()
            middle = rows.size // 2
            rows[middle] = (rows[middle] + 1) % spec.renewal_rate_paths.rows
            return dataclasses.replace(result, renewal_rate_rows=rows)
        return result

    return simulate


def test_a_probe_with_one_middle_row_changed_is_refused():
    raw = _raw(FIXTURE)
    calls = []
    gate = reversal_gate(raw, "house.mortgage_rate", 0.10,
                         simulate=_one_middle_row_changed_on_the_probe(calls))
    assert not gate["licensed"]
    # the premise refused it, not the tolerance: one path of the 200 moved
    assert gate["why"] == ("moving house.mortgage_rate changes the renewal-rate row 1 of "
                           "the 200 paths price, so no per-row term can be subtracted")


def test_the_free_curve_is_a_full_re_simulation():
    """At 3% the curve and a full re-simulation both give P(house cheapest)
    0.966; shifting every path by the central case's delta alone gives
    0.9575."""
    raw = _raw(FIXTURE)
    spec = load_config_dict(raw)
    det, mc = compute_deterministic(spec), run_monte_carlo(spec)
    free = be._free_curve(raw, "house.mortgage_rate", ["house", "rent"], det, mc,
                          single_path=False)
    full = run_monte_carlo(load_at(raw, "house.mortgage_rate", 0.03))
    at = compute_deterministic(load_at(raw, "house.mortgage_rate", 0.03))
    constant = {o: getattr(mc, o).pvs + (getattr(at, o).total_pv - getattr(det, o).total_pv)
                for o in ("house", "rent")}
    assert free(0.03)[1]["house"] == full.prob_house_cheapest == 0.966
    assert be._cheapest_probabilities(constant, ["house", "rent"])["house"] == 0.9575


# ---------------------------------------------------------------------------
# §9 row 10: no draw touches it, on both branches of the gate
# ---------------------------------------------------------------------------

def test_the_contract_rate_s_row_prints_on_both_branches():
    raw = _raw(FIXTURE)
    spec = load_config_dict(raw)
    det, mc = compute_deterministic(spec), run_monte_carlo(spec)
    licensed = reversal_register(raw, det, mc)
    assert [r.key for r in licensed.exact] == ["house.mortgage_rate"]
    refused = reversal_register(raw, det, mc, simulate=_rows_shifted_on_the_probe([]))
    assert [r.key for r in refused.estimated] == ["house.mortgage_rate"]
    assert {b.code for b in refused.estimated[0].refused_boundaries} == {"not_exact"}
    for register in (licensed, refused):
        assert [(z.kind, z.keys) for z in register.structural_zeros] == [
            ("stated_path", ("house.mortgage_rate",))]


# ---------------------------------------------------------------------------
# §9 row 16: the central row at each end of a break-even
# ---------------------------------------------------------------------------

def _at_rent(monthly_rent: float) -> dict:
    raw = _raw(FIXTURE)
    raw["rent"]["monthly_rent"] = monthly_rent
    return raw


def test_a_break_even_across_a_row_switch_says_so():
    """At $1,840 a month the house first wins at a 16-year horizon: the
    15-year horizon prices two renewals and central row 2, the 16-year one
    three and central row 9."""
    result = solve_break_even(_at_rent(1840), "years", 6, 20)
    (entry,) = result["break_evens"]
    assert (entry["last_value_below"], entry["value"]) == (15, 16)
    assert entry["sentence"].endswith(
        "; the central row switches here: row 2 at years=15, row 9 at years=16")


def test_a_break_even_inside_one_central_row_says_nothing():
    """At $1,900 the crossing lies between 10 and 11 years: one renewal priced
    and then two, and central row 2 at both."""
    result = solve_break_even(_at_rent(1900), "years", 6, 20)
    (entry,) = result["break_evens"]
    assert (entry["last_value_below"], entry["value"]) == (10, 11)
    assert "central row" not in entry["sentence"]


def _one_end_raising(monkeypatch, error):
    """`load_at` in break_even raising `error` at years=16 and loading every
    other value as it does."""
    real = be.load_at

    def load_at(raw, key, value):
        if key == "years" and value == 16:
            raise error
        return real(raw, key, value)

    monkeypatch.setattr(be, "load_at", load_at)


def test_a_bug_in_one_end_s_load_is_never_reported_as_no_switch(monkeypatch):
    """Only the loader's refusals mean an end switches nothing it could name:
    any other exception from one end's load propagates."""
    entry = {"last_value_below": 15, "value": 16}
    assert be.central_row_switch(_at_rent(1840), "years", entry) == (
        "the central row switches here: row 2 at years=15, row 9 at years=16")
    _one_end_raising(monkeypatch, RuntimeError("a bug in the load"))
    with pytest.raises(RuntimeError, match="a bug in the load"):
        be.central_row_switch(_at_rent(1840), "years", entry)


def test_an_end_the_loader_refuses_switches_nothing(monkeypatch):
    from hde.config import ConfigValidationError
    _one_end_raising(monkeypatch, ConfigValidationError("refused"))
    entry = {"last_value_below": 15, "value": 16}
    assert be.central_row_switch(_at_rent(1840), "years", entry) is None


def test_the_row_switch_reaches_the_rendered_break_even(tmp_path):
    raw = _at_rent(1840)
    raw["renewal_rates"]["path"] = str(ROOT / raw["renewal_rates"]["path"])
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    run = _cli(config, "--break-even", "years=6:20", "--no-monte-carlo")
    assert run.returncode == 0, run.stderr
    note = "the central row switches here: row 2 at years=15, row 9 at years=16"
    lines = [line for line in run.stdout.splitlines() if note in line]
    assert len(lines) == 2          # the text block and its read-back line
    run = _cli(config, "--break-even", "years=6:20", "--no-monte-carlo", "--json")
    ((entry,),) = [solve["break_evens"] for solve in json.loads(run.stdout)["break_evens"]]
    assert entry["sentence"].endswith(note)
