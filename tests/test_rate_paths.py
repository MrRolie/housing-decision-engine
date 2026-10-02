"""The renewal-rate path file: its loader, its refusals and the central row
(docs/specs/2026-10-01-renewal-rate-path-file.md §2, §3, §5; §9 rows 1, 2,
12, 13 and 14).

Every refusal is pinned beside the legal config one step away, so a refusal
deleted fails the first test of its pair and a refusal widened onto its
neighbour fails the second.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import statistics
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
import yaml

import hde.cli as cli_mod
import hde.config as config_mod
from hde import rate_paths
from hde.config import (
    ConfigValidationError, dispersion_sources, load_config, load_config_dict, single_path_run,
)
from hde.deterministic import compute_deterministic
from hde.input_schema import input_schema
from hde.rates import effective_mortgage_rate
from hde.sources import uncertainty_keys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
DATA = FIXTURES / "renewal_paths"
TWO_PATHS = "tests/fixtures/renewal_paths/two_paths.json"
FIXTURE = FIXTURES / "renewal_rate_paths.yaml"
DROP = object()


@pytest.fixture(autouse=True)
def _at_the_repo_root(monkeypatch):
    # A path file is read relative to the working directory, as
    # market_scenario.path is; the committed configs name repo-root paths.
    monkeypatch.chdir(ROOT)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _file(**changes) -> dict:
    """two_paths.json with top-level fields replaced (DROP removes one)."""
    doc = json.loads((DATA / "two_paths.json").read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is DROP:
            doc.pop(key)
        else:
            doc[key] = value
    return doc


_WRITTEN = iter(range(10 ** 6))


def _write(tmp_path: Path, doc, name: str = "") -> str:
    """A path file under a fresh name unless one is given: rewriting a path
    already read in this test would be R19's change, not the case at hand."""
    target = tmp_path / (name or f"paths{next(_WRITTEN)}.json")
    text = doc if isinstance(doc, str) else json.dumps(doc, indent=2, ensure_ascii=False)
    target.write_text(text, encoding="utf-8")
    return str(target)


def _config(path: str, base: str = "hvr_example.yaml") -> dict:
    cfg = copy.deepcopy(_yaml(DATA / base))
    cfg["renewal_rates"] = {"path": path}
    return cfg


def _refused(cfg: dict) -> str:
    with pytest.raises(ConfigValidationError) as caught:
        load_config_dict(cfg)
    return str(caught.value)


def _why(tmp_path: Path, doc, base: str = "hvr_example.yaml") -> str:
    """The refusal of a config reading `doc`, its path written as P."""
    path = _write(tmp_path, doc)
    return _refused(_config(path, base)).replace(path, "P")


def _loads(cfg: dict):
    spec = load_config_dict(cfg)
    assert spec.renewal_rate_paths is not None
    return spec


# ---------------------------------------------------------------------------
# §9 row 13: every R-row against its neighbour
# ---------------------------------------------------------------------------

class TestTheFile:
    def test_r1_no_file(self, tmp_path):
        missing = str(tmp_path / "absent.json")
        assert _refused(_config(missing)) == f"renewal_rates.path: no file at '{missing}'"
        # the neighbour: a file that is there, named relative to the working directory
        _loads(_config(TWO_PATHS))

    def test_r2_not_json(self, tmp_path):
        path = _write(tmp_path, json.dumps(_file()).replace("0.08, 0.08, 0.08, 0.08]",
                                                            "0.08, NaN, 0.08, 0.08]"))
        message = _refused(_config(path))
        assert message.startswith(f"'{path}' is not valid JSON: ") and "NaN" in message
        broken = _write(tmp_path, "{", "broken.json")
        assert _refused(_config(broken)).startswith(f"'{broken}' is not valid JSON: ")
        # the neighbour: UTF-8 that is not ASCII is valid
        method = "synthétique, not a calibration: two hand-set paths"
        doc = _file(provenance=dict(_file()["provenance"], method=method))
        assert _loads(_config(_write(tmp_path, doc, "utf8.json"))).renewal_rate_paths \
            .provenance["method"] == method

    def test_r3_exact_allowlist_at_every_level(self, tmp_path):
        assert _why(tmp_path, _file(weights=[1, 1])) == \
            "'P': unknown field(s) ['weights'] (exact allowlist)"
        provenance = dict(_file()["provenance"], notes="x")
        assert _why(tmp_path, _file(provenance=provenance)) == \
            "'P': unknown field(s) ['provenance.notes'] (exact allowlist)"
        provenance = dict(_file()["provenance"], validation={"text": "none", "notes": "x"})
        assert _why(tmp_path, _file(provenance=provenance)) == \
            "'P': unknown field(s) ['provenance.validation.notes'] (exact allowlist)"
        provenance = {k: v for k, v in _file()["provenance"].items() if k != "method"}
        assert _why(tmp_path, _file(provenance=provenance)) == \
            "'P': missing field(s) ['provenance.method']"
        assert _why(tmp_path, _file(paths=DROP)) == "'P': missing field(s) ['paths']"
        # the neighbours: the two optional fields, absent and present
        _loads(_config(_write(tmp_path, _file(as_of=DROP), "no_as_of.json")))
        validation = {"text": "none", "metrics": {"rmse": 0.004}}
        provenance = dict(_file()["provenance"], validation=validation)
        _loads(_config(_write(tmp_path, _file(provenance=provenance), "metrics.json")))

    def test_r3_every_violation_is_collected_before_one_refusal(self, tmp_path):
        path = _write(tmp_path, _file(weights=[1], compounding="monthly", schema_version="2"))
        lines = _refused(_config(path)).splitlines()
        assert len(lines) == 3, lines

    def test_r4_schema_and_version(self, tmp_path):
        path = _write(tmp_path, _file(schema_version="2"))
        assert _refused(_config(path)) == (
            f"'{path}' is hde.renewal_rate_paths version 2; this engine reads "
            f"hde.renewal_rate_paths version 1")
        other = _write(tmp_path, _file(schema="hde.scenario_prior"), "other.json")
        assert _refused(_config(other)).startswith(f"'{other}' is hde.scenario_prior version 1;")
        _loads(_config(_write(tmp_path, _file(), "good.json")))

    def test_r5_provenance_is_the_file_s_own_words(self, tmp_path):
        for field in ("method", "data_window", "source", "producer"):
            for empty in ("", "   ", 3):
                provenance = dict(_file()["provenance"], **{field: empty})
                path = _write(tmp_path, _file(provenance=provenance))
                assert _refused(_config(path)) == (
                    f"'{path}': provenance.{field} must be a non-empty string — the "
                    f"read-back prints it as the file's own words")
        provenance = dict(_file()["provenance"], validation={"text": ""})
        path = _write(tmp_path, _file(provenance=provenance))
        assert _refused(_config(path)) == (
            f"'{path}': provenance.validation.text must be a non-empty string — the "
            f"read-back prints it as the file's own words")
        provenance = dict(_file()["provenance"],
                          validation={"text": "none", "metrics": {"rmse": "small"}})
        path = _write(tmp_path, _file(provenance=provenance))
        assert _refused(_config(path)) == (
            f"'{path}': provenance.validation.metrics.rmse = 'small': a metric is a "
            f"finite number")
        # the neighbour: any finite number is a metric, a negative bias included
        provenance = dict(_file()["provenance"],
                          validation={"text": "none", "metrics": {"rmse": 0.004, "bias": -0.001}})
        _loads(_config(_write(tmp_path, _file(provenance=provenance), "good.json")))

    def test_r6_compounding(self, tmp_path):
        path = _write(tmp_path, _file(compounding="monthly"))
        assert _refused(_config(path)) == (
            f"'{path}': compounding 'monthly' — must be semi_annual or effective_annual")
        _loads(_config(_write(tmp_path, _file(compounding="semi_annual"), "semi.json")))

    def test_r7_the_grid(self, tmp_path):
        path = _write(tmp_path, _file(renewal_years=[1, 6, 11, 16]))
        assert _refused(_config(path)) == (
            f"'{path}': renewal_years [1, 6, 11, 16] for term_years 5 must be [6, 11, 16, 21] "
            f"— column k is the rate at the k-th renewal, simulation year k·5+1; the opening "
            f"term is the option's own mortgage_rate")
        path = _write(tmp_path, _file(term_years=0))
        assert _refused(_config(path)).startswith(f"'{path}': term_years 0 must be an integer >= 1")
        # the neighbour: the grid exactly
        _loads(_config(_write(tmp_path, _file(renewal_years=[6, 11, 16, 21]), "good.json")))

    def test_r8_as_of(self, tmp_path):
        for value in ("2026-13-01", "2026-1-1", 20261001, "2026-10-01T00:00"):
            path = _write(tmp_path, _file(as_of=value))
            assert _refused(_config(path)) == (
                f"'{path}': as_of {value!r} is not an ISO date (YYYY-MM-DD)")
        _loads(_config(_write(tmp_path, _file(as_of="2026-10-01"), "good.json")))
        _loads(_config(_write(tmp_path, _file(as_of=DROP), "none.json")))

    def test_r9_row_shape_and_value(self, tmp_path):
        path = _write(tmp_path, _file(paths=[[0.02] * 4, [0.08] * 3]))
        assert _refused(_config(path)) == (
            f"'{path}': paths[1] has 3 rates and renewal_years has 4")
        for bad in (-0.01, True, "0.05", None):
            path = _write(tmp_path, _file(paths=[[0.02] * 4, [0.08, 0.08, bad, 0.08]]))
            assert _refused(_config(path)) == (
                f"'{path}': paths[1][2] = {bad!r}: a rate is a finite number >= 0")
        # the neighbour: a zero rate is a rate
        _loads(_config(_write(tmp_path, _file(paths=[[0.0] * 4, [0.08] * 4]), "good.json")))

    def test_r10_one_row_is_no_distribution(self, tmp_path):
        path = _write(tmp_path, _file(paths=[[0.02] * 4]))
        assert _refused(_config(path)) == (
            f"'{path}' has 1 row: a distribution needs two or more")
        path = _write(tmp_path, _file(paths=[]))
        assert _refused(_config(path)) == (
            f"'{path}' has 0 rows: a distribution needs two or more")
        # the neighbour: two rows load
        assert _loads(_config(_write(tmp_path, _file(), "two.json"))).renewal_rate_paths.rows == 2


class TestTheFileAgainstTheConfig:
    def test_r11_one_term(self):
        cfg = _config(TWO_PATHS)
        cfg["house"]["mortgage_renewal_years"] = 3
        assert _refused(cfg) == (
            f"house.mortgage_renewal_years is 3; '{TWO_PATHS}' quotes 5-year rates")
        cfg = _config(TWO_PATHS, "two_opts.yaml")
        cfg["renewal_rates"]["path"] = TWO_PATHS
        cfg["condo"]["mortgage_renewal_years"] = 2
        assert _refused(cfg) == (
            f"condo.mortgage_renewal_years is 2; '{TWO_PATHS}' quotes 5-year rates")
        # the neighbour: both options on the file's term
        cfg["condo"]["mortgage_renewal_years"] = 5
        _loads(cfg)

    def test_r12_zero_spread_on_the_priced_renewals(self, tmp_path):
        # rows that differ only in year 21, which the 20-year horizon never prices
        path = _write(tmp_path, _file(paths=[[0.04, 0.04, 0.04, 0.02], [0.04, 0.04, 0.04, 0.08]]))
        assert _refused(_config(path)) == (
            f"every row of '{path}' prices house's renewals in years [6, 11, 16] at the same "
            f"rates: no future differs")
        # the neighbour: one varying priced column is a distribution
        good = _write(tmp_path, _file(paths=[[0.04, 0.04, 0.03, 0.04], [0.04, 0.04, 0.05, 0.04]]),
                      "good.json")
        _loads(_config(good))

    def test_r12_is_evaluated_per_reading_option(self, tmp_path):
        # the condo reads year 6 alone, and every row prices it at 4%
        doc = _file(paths=[[0.04, 0.03, 0.05, 0.06], [0.04, 0.07, 0.06, 0.05]])
        path = _write(tmp_path, doc)
        cfg = _config(path, "two_opts.yaml")
        assert _refused(cfg) == (
            f"every row of '{path}' prices condo's renewals in years [6] at the same rates: "
            f"no future differs")
        doc = _file(paths=[[0.04, 0.03, 0.05, 0.06], [0.05, 0.07, 0.06, 0.05]])
        _loads(_config(_write(tmp_path, doc, "good.json"), "two_opts.yaml"))

    def test_r13_no_ladder_beside_the_file(self):
        cfg = _config(TWO_PATHS)
        cfg["house"]["mortgage_renewal_rates"] = [0.05]
        assert _refused(cfg) == (
            "house.mortgage_renewal_rates is set beside renewal_rates.path — one market, two "
            "sources for its renewal rate")
        cfg.pop("renewal_rates")
        load_config_dict(cfg)          # the same ladder without the file is today's run
        _loads(_config(TWO_PATHS))

    def test_r14_a_financed_option_states_its_term(self):
        cfg = _config(TWO_PATHS)
        cfg["house"].pop("mortgage_renewal_years")
        assert _refused(cfg) == (
            "house has a mortgage and no mortgage_renewal_years; renewal_rates.path quotes "
            "5-year rates")
        # the neighbour: an all-cash option has no rate to renew and reads nothing
        cfg = _config(TWO_PATHS)
        cfg["condo"] = {"initial_value": 300_000, "monthly_fee": 350, "all_cash": True}
        assert _loads(cfg).renewal_rate_paths.columns == {"house": 4}

    def test_r14_lifts_the_ladder_refusal_only_beside_a_file(self):
        cfg = _config(TWO_PATHS)
        cfg.pop("renewal_rates")
        assert _refused(cfg).startswith(
            "house.mortgage_renewal_years=5 is set without house.mortgage_renewal_rates — ")

    def test_r15_nothing_priced_inside_the_horizon(self):
        cfg = _config(TWO_PATHS)
        cfg["years"] = 5
        assert _refused(cfg) == (
            "no reading option renews inside the 5-year horizon (first renewal: year 6)")
        cfg["years"] = 6
        assert _loads(cfg).renewal_rate_paths.priced_years == (6,)

    def test_r15_with_no_reading_option(self):
        cfg = _config(TWO_PATHS)
        cfg["house"] = {"initial_value": 400_000, "all_cash": True}
        assert _refused(cfg) == (
            "no reading option renews inside the 20-year horizon (first renewal: year 6)")

    def test_r16_every_renewal_inside_the_amortization_needs_a_column(self, tmp_path):
        # 25-year amortization, 5-year term, 20-year horizon: year 21 is priced by
        # nothing, and still needs its column
        short = _file(renewal_years=[6, 11, 16], paths=[[0.02] * 3, [0.08] * 3])
        path = _write(tmp_path, short)
        assert _refused(_config(path)) == (
            f"'{path}' ends at year 16; house renews in year 21 inside its 25-year "
            f"amortization — every renewal needs a column, and the engine carries no rate "
            f"forward")
        _loads(_config(_write(tmp_path, _file(), "good.json")))

    def test_r17_no_column_past_every_amortization(self, tmp_path):
        long = _file(renewal_years=[6, 11, 16, 21, 26], paths=[[0.02] * 5, [0.08] * 5])
        path = _write(tmp_path, long)
        assert _refused(_config(path)) == (
            f"'{path}' renewal_years [26]: past every reading option's last renewal "
            f"(house: year 21)")
        # the neighbour: a condo whose amortization ends before a column the house reads
        spec = _loads(_config("tests/fixtures/renewal_paths/semi.json", "two_opts.yaml"))
        assert spec.renewal_rate_paths.columns == {"condo": 1, "house": 4}


# ---------------------------------------------------------------------------
# §9 row 14: sources and anchors
# ---------------------------------------------------------------------------

class TestSources:
    def _declared(self, value):
        cfg = _config(TWO_PATHS)
        cfg["sources"] = {"renewal_rates.path": value}
        return cfg

    def test_r20_the_file_is_the_user_s(self):
        assert _refused(self._declared("assistant")) == (
            "sources: 'renewal_rates.path' declared assistant — the path file is the user's "
            "own work and an assistant never proposes, invents or builds one; declare it user "
            "when the user supplied it")
        assert _loads(self._declared("user")).sources.classify("renewal_rates.path") == "user"
        assert _loads(_config(TWO_PATHS)).sources.classify("renewal_rates.path") == "unattributed"

    def test_assistant_stays_declarable_on_every_other_key(self):
        cfg = self._declared("user")
        cfg["sources"]["house.mortgage_rate"] = "assistant"
        assert _loads(cfg).sources.classify("house.mortgage_rate") == "assistant"

    def test_r18_an_anchor_sources_a_number(self):
        message = _refused(self._declared("anchor:mortgage_rate.contracted_5y_uninsured"))
        assert message == (
            "sources: 'renewal_rates.path' declared anchor:mortgage_rate.contracted_5y_uninsured "
            f"but the config states '{TWO_PATHS}' — an anchor sources a number, not str")

    def test_the_uncertainty_mirror_names_the_file(self):
        cfg = _yaml(FIXTURE)
        for key in ("house_maintenance_vol", "rent_escalation_vol"):
            cfg["simulation"][key] = 0.0
        assert uncertainty_keys(cfg) == ["renewal_rates.path"]
        spec = load_config_dict(copy.deepcopy(cfg))
        assert not single_path_run(spec)
        assert dispersion_sources(spec)[0] == ["renewal_rates.path (renewal rates per path)"]
        # off by absence: the block and the term it needs
        cfg.pop("renewal_rates")
        cfg["sources"].pop("renewal_rates.path")
        cfg["house"].pop("mortgage_renewal_years")
        assert uncertainty_keys(cfg) == []
        spec = load_config_dict(cfg)
        assert single_path_run(spec) and dispersion_sources(spec) == ([], [], [])


# ---------------------------------------------------------------------------
# R19 and §9 row 12: bytes that change within one process
# ---------------------------------------------------------------------------

class TestFileIntegrity:
    def test_r19_changed_bytes_raise(self, tmp_path):
        path = _write(tmp_path, _file(), "fixed.json")
        first = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert _loads(_config(path)).renewal_rate_paths.file_sha256 == first
        _write(tmp_path, _file(paths=[[0.02] * 4, [0.09] * 4]), "fixed.json")
        now = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        with pytest.raises(rate_paths.RatePathsChanged) as caught:
            load_config_dict(_config(path))
        assert str(caught.value) == (
            f"'{path}' changed since this process first read it: sha256 {first[:12]}… first, "
            f"{now[:12]}… now")
        rate_paths.reset_pins()
        assert _loads(_config(path)).renewal_rate_paths.file_sha256 == now

    def test_r19_the_same_bytes_rewritten_load(self, tmp_path):
        path = _write(tmp_path, _file(), "fixed.json")
        _loads(_config(path))
        _write(tmp_path, _file(), "fixed.json")
        _loads(_config(path))

    def test_r19_is_no_exception_a_per_point_capture_catches(self):
        assert not issubclass(rate_paths.RatePathsChanged, (ConfigValidationError, ValueError))

    def test_the_sha_is_the_sha_of_the_bytes_priced(self):
        spec = _loads(_config(TWO_PATHS))
        loaded = spec.renewal_rate_paths
        assert loaded.file_sha256 == hashlib.sha256((ROOT / TWO_PATHS).read_bytes()).hexdigest()
        assert loaded.file_sha256.startswith("b3827bb92169")


def _cli(argv, rewrite_after_first_load, monkeypatch, tmp_path):
    """`hde` in-process on the fixture with an income block, at 200 paths.
    With `rewrite_after_first_load` the path file's bytes are rewritten right
    after the first load reads them, so every later load sees other bytes."""
    doc = json.loads((FIXTURES / "renewal_rate_paths_synthetic.json").read_text(encoding="utf-8"))
    path = _write(tmp_path, doc, "rates.json")
    cfg = _yaml(FIXTURE)
    cfg["renewal_rates"]["path"] = path
    cfg["simulation"]["num_sims"] = 200
    cfg["income"] = {"annual_income": 150_000, "income_growth_rate": 0.0,
                     "affordability_threshold": 0.32}
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    real = config_mod.read_path_file
    calls = {"n": 0}

    def read(p):
        calls["n"] += 1
        got = real(p)
        if rewrite_after_first_load and calls["n"] == 1:
            doc["paths"][0][0] += 0.001
            _write(tmp_path, doc, "rates.json")
        return got

    monkeypatch.setattr(config_mod, "read_path_file", read)
    monkeypatch.setattr(sys, "argv", ["hde", str(config_path), *argv])
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_mod.main()
    return code, out.getvalue(), err.getvalue(), calls["n"]


SURFACES = [
    ["--sweep", "house.mortgage_rate=0.03:0.06:3"],
    ["--break-even", "house.mortgage_rate=0.01:0.12"],
    ["--decompose", "200"],
    [],                      # a plain run: the income block re-enters the loader
    ["--read-back"],
]


@pytest.mark.parametrize("argv", SURFACES, ids=lambda a: " ".join(a) or "plain")
def test_r19_every_surface_exits_once_with_one_error_line(argv, monkeypatch, tmp_path):
    code, out, err, loads = _cli(argv, True, monkeypatch, tmp_path)
    assert loads >= 2, "the surface never re-entered the loader, so this pins nothing"
    errors = [line for line in err.splitlines() if line.startswith("Error:")]
    assert code == 1, (code, err[-400:])
    assert len(errors) == 1 and "changed since this process first read it" in errors[0], errors
    assert errors[0].startswith(f"Error: '{tmp_path / 'rates.json'}' changed")
    assert "Traceback" not in err + out


@pytest.mark.parametrize("argv", SURFACES, ids=lambda a: " ".join(a) or "plain")
def test_r19_the_same_surfaces_run_when_the_bytes_hold(argv, monkeypatch, tmp_path):
    code, _, err, loads = _cli(argv, False, monkeypatch, tmp_path)
    assert code == 0, err[-400:]
    assert loads >= 2


def test_no_monte_carlo_says_the_run_prices_the_central_row_alone(monkeypatch, capsys):
    def warnings(*flags):
        monkeypatch.setattr(sys, "argv", ["hde", str(FIXTURE), "--json", *flags])
        assert cli_mod.main() == 0
        return json.loads(capsys.readouterr().out)["warnings"]

    assert cli_mod.RATES_WITHOUT_MONTE_CARLO in warnings("--no-monte-carlo")
    assert cli_mod.RATES_WITHOUT_MONTE_CARLO == (
        "renewal_rates draws only in Monte Carlo — this run prices the central row alone")
    rate_paths.reset_pins()
    assert cli_mod.RATES_WITHOUT_MONTE_CARLO not in warnings()


# ---------------------------------------------------------------------------
# The central row (§5; the deterministic half of §9 row 1)
# ---------------------------------------------------------------------------

def _central_by_hand(rows, priced):
    """An independent statement of §5: statistics.median on Fractions."""
    exact = [[Fraction(v) for v in row[:priced]] for row in rows]
    median = [statistics.median(column) for column in zip(*exact)]
    distances = [sum((x - m) ** 2 for x, m in zip(row, median)) for row in exact]
    return distances.index(min(distances)), distances.count(min(distances)) - 1


class TestTheCentralRow:
    def test_the_tie_is_decided_in_exact_arithmetic(self):
        loaded = _loads(_config(TWO_PATHS)).renewal_rate_paths
        assert (loaded.central_index, loaded.tied_rows) == (0, 1)
        # float evaluation breaks the same tie by rounding, toward row 1
        rows = np.array([[0.02] * 3, [0.08] * 3])
        floats = ((rows - np.median(rows, axis=0)) ** 2).sum(axis=1)
        assert int(np.argmin(floats)) == 1

    def test_the_central_case_is_one_future_s_path(self):
        filed = compute_deterministic(_loads(_config(TWO_PATHS))).house.total_pv
        typed = _yaml(DATA / "hvr_example.yaml")
        typed.pop("renewal_rates")
        typed["house"]["mortgage_renewal_rates"] = [0.02] * 4
        assert filed == compute_deterministic(load_config_dict(typed)).house.total_pv
        assert filed == 296909.29108796926
        # never the per-year mean: that path prices a house no future reaches
        typed["house"]["mortgage_renewal_rates"] = [0.05] * 4
        assert round(compute_deterministic(load_config_dict(typed)).house.total_pv, 2) == 363941.75

    def test_the_fixture_s_central_row_is_not_row_zero(self):
        loaded = load_config(str(FIXTURE)).renewal_rate_paths
        assert loaded.central_index == 9 and loaded.tied_rows == 0
        assert (loaded.central_index, loaded.tied_rows) == _central_by_hand(loaded.quoted, 3)

    def test_the_central_row_depends_on_the_priced_renewals(self):
        cfg = _yaml(FIXTURE)
        found = {}
        for years in (6, 10, 11, 15, 16, 20):
            cfg["years"] = years
            loaded = load_config_dict(copy.deepcopy(cfg)).renewal_rate_paths
            found[years] = (loaded.priced_columns, loaded.central_index)
            assert loaded.central_index == _central_by_hand(loaded.quoted,
                                                            loaded.priced_columns)[0]
        assert found == {6: (1, 2), 10: (1, 2), 11: (2, 2), 15: (2, 2), 16: (3, 9), 20: (3, 9)}

    def test_each_reading_option_takes_its_own_columns_of_the_central_row(self):
        spec = _loads(_config("tests/fixtures/renewal_paths/semi.json", "two_opts.yaml"))
        row = spec.renewal_rate_paths.quoted[spec.renewal_rate_paths.central_index]
        assert spec.condo.mortgage_renewal_rates_quoted == list(row[:1])
        assert spec.house.mortgage_renewal_rates_quoted == list(row[:4])
        # converted once, by the FILE's compounding, not the contract's
        assert spec.house.mortgage_rate_compounding == "effective_annual"
        assert spec.house.mortgage_renewal_rates == [
            effective_mortgage_rate(r, "semi_annual") for r in row[:4]]
        assert spec.house.mortgage_renewal_rates != list(row[:4])

    def test_an_option_that_reads_no_column_takes_the_empty_ladder(self):
        spec = _loads(_config(TWO_PATHS, "condo5.yaml"))
        assert spec.renewal_rate_paths.columns == {"condo": 0, "house": 4}
        assert spec.condo.mortgage_renewal_rates == []
        assert spec.condo.mortgage_renewal_rates_quoted == []


# ---------------------------------------------------------------------------
# The config surface (§3, §8 commit 3)
# ---------------------------------------------------------------------------

def test_a_top_level_typo_names_the_section():
    cfg = _yaml(ROOT / "examples" / "mortgage_house_vs_rent.yaml")
    cfg["renewal_rate"] = {"path": "x.json"}
    assert "unknown key 'renewal_rate' — did you mean 'renewal_rates'?" in _refused(cfg)


def test_the_section_takes_one_key():
    cfg = _config(TWO_PATHS)
    cfg["renewal_rates"]["rate_shift"] = 0.01
    assert "unknown key 'renewal_rates.rate_shift'" in _refused(cfg)


def test_the_schema_says_whose_file_it_is():
    schema = input_schema()
    assert schema["top_level"]["renewal_rates"]["note"] == (
        "a renewal-rate path file the USER supplies (schema hde.renewal_rate_paths), written "
        "by a model fitted outside the engine; an assistant never proposes, invents or builds one")
    assert schema["renewal_rates"]["path"]["required"]
    assert "sources: declares it user" in schema["renewal_rates"]["path"]["note"]
    for option in ("condo", "house"):
        assert schema[option]["mortgage_renewal_years"]["required_if"] == (
            "requires mortgage_renewal_rates — the two renewal keys travel together — or a "
            "renewal_rates.path file, which supplies the rates and refuses "
            "mortgage_renewal_rates")


def test_the_fixture_file_says_it_is_synthetic():
    doc = json.loads((FIXTURES / "renewal_rate_paths_synthetic.json").read_text(encoding="utf-8"))
    assert doc["provenance"]["method"].startswith("synthetic, not a calibration")
    assert doc["compounding"] == "semi_annual"
