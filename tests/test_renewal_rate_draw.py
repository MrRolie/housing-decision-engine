"""Channel 8: a renewal-rate path file's row drawn once per path, and priced
by every financed option on that path
(docs/specs/2026-10-01-renewal-rate-path-file.md §4 and §5; §9 rows 1 to 8).

Each pin names the class it guards. The configs are the committed test data
under tests/fixtures/renewal_paths/ and the opt-in fixture
tests/fixtures/renewal_rate_paths.yaml; every figure below was measured on
them.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

import hde.monte_carlo as mc_mod
from hde import decomposition as dc
from hde import decomposition_run as dr
from hde.config import load_config_dict
from hde.deterministic import compute_deterministic
from hde.models import compute_verdict
from hde.monte_carlo import addressed_streams, channel_stream, run_monte_carlo
from hde.serialization import mc_to_dict
from tests import decomposition_oracles as oracles

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "fixtures" / "renewal_paths"
FIXTURE = ROOT / "tests" / "fixtures" / "renewal_rate_paths.yaml"


@pytest.fixture(autouse=True)
def _at_the_repo_root(monkeypatch):
    # The committed configs name their path files relative to the repo root.
    monkeypatch.chdir(ROOT)


def _raw(path: Path, paths: int = None) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if paths is not None:
        raw.setdefault("simulation", {})["num_sims"] = paths
    return raw


def _spec(path: Path, paths: int = None):
    return load_config_dict(_raw(path, paths))


def _typed(path: Path, paths: int = None):
    """The same config with no file and the central row typed as the ladder:
    its EFFECTIVE rates, which the effective-annual contracts of these configs
    take as typed."""
    spec = _spec(path, paths)
    raw = _raw(path, paths)
    raw.pop("renewal_rates")
    raw.get("sources", {}).pop("renewal_rates.path", None)
    if not raw.get("sources", True):
        raw.pop("sources")
    loaded = spec.renewal_rate_paths
    for name, n in loaded.columns.items():
        assert raw[name]["mortgage_rate_compounding"] == "effective_annual"
        raw[name]["mortgage_renewal_rates"] = loaded.central_effective(n)
    typed = load_config_dict(raw)
    for name, n in loaded.columns.items():
        assert getattr(typed, name).mortgage_renewal_rates == loaded.central_effective(n)
    return typed


def _verdict(spec, det):
    return compute_verdict(det, years=spec.simulation.years,
                           discount_rate=spec.simulation.discount_rate)


# ---------------------------------------------------------------------------
# §9 row 1: one world — the central case is one future's path
# ---------------------------------------------------------------------------

class TestOneWorld:
    def test_channel_8_frozen_prices_the_typed_central_row_on_every_path(self):
        """With channel 8 frozen, every path prices each option's own ladder,
        the central row: bit for bit the run of the same config with that row
        typed as its ladder and no file, on the same addressed streams."""
        filed = _spec(FIXTURE, 300)
        typed = _typed(FIXTURE, 300)
        seed = filed.simulation.random_seed
        frozen = run_monte_carlo(filed, addressed_streams(seed), freeze=(8,))
        plain = run_monte_carlo(typed, addressed_streams(seed))
        for name in ("house", "rent"):
            assert np.array_equal(getattr(frozen, name).pvs, getattr(plain, name).pvs), name
        central = filed.renewal_rate_paths.central_index
        assert central == 9
        assert np.all(frozen.renewal_rate_rows == central)

    def test_the_all_frozen_identity_holds_on_a_file_run(self):
        spec = _spec(DATA / "hvr_example.yaml", 2000)
        det = compute_deterministic(spec)
        verdict = _verdict(spec, det)
        level = dr._level_register(spec, verdict, verdict.best,
                                   dr.margin_per_path(dr._run(spec, dr.MATRIX_A),
                                                      verdict.best),
                                   (8,), spec.simulation.random_seed, 2000)
        assert level.all_frozen_path_spread == 0.0
        assert level.all_frozen_deviation == 5.820766091346741e-11
        assert level.all_frozen_deviation <= dr.identity_budget(det, verdict)

    def test_the_futures_never_price_the_mean_path(self):
        """§5: the 2,460 paths that draw row 0 and the 2,540 that draw row 1
        price the house in two ranges with nothing between them, and the mean
        path's $363,941.75 lies in the gap."""
        spec = _spec(DATA / "hvr_example.yaml")
        mc = run_monte_carlo(spec)
        rows, house = mc.renewal_rate_rows, mc.house.pvs
        assert np.bincount(rows).tolist() == [2460, 2540]
        low, high = house[rows == 0], house[rows == 1]
        assert (round(low.min(), 2), round(low.max(), 2)) == (277674.54, 318418.37)
        assert (round(high.min(), 2), round(high.max(), 2)) == (419293.02, 467443.65)
        assert low.max() < 363941.75 < high.min()


# ---------------------------------------------------------------------------
# §9 row 2: liveness is measured, and the draw is one integers(0, N) per path
# ---------------------------------------------------------------------------

class _Counting:
    """Stream 8's addressed generators, each wrapped to count its draws."""

    def __init__(self, inner):
        self.inner = inner
        self.handed = {}

    def __getitem__(self, stream_id):
        source = self.inner[stream_id]
        if stream_id != 8:
            return source

        def generator_for(path_index):
            got = source(path_index)
            self.handed[path_index] = got
            return got

        return generator_for


class TestTheDraw:
    def test_one_integers_draw_per_path_on_stream_8(self):
        spec = _spec(FIXTURE, 200)
        n_rows = spec.renewal_rate_paths.rows
        seed = spec.simulation.random_seed
        streams = _Counting(addressed_streams(seed))
        mc = run_monte_carlo(spec, streams)
        assert sorted(streams.handed) == list(range(200))
        for path, handed in streams.handed.items():
            fresh = channel_stream(seed, dr.MATRIX_A, 8, path)
            assert int(fresh.integers(0, n_rows)) == mc.renewal_rate_rows[path]
            # the whole state, `has_uint32` included: after a second draw of
            # a small range only that field tells the two apart
            assert handed.bit_generator.state == fresh.bit_generator.state, path

    def test_a_config_without_the_file_takes_no_draw_on_stream_8(self):
        typed = _typed(FIXTURE, 50)
        streams = _Counting(addressed_streams(typed.simulation.random_seed))
        mc = run_monte_carlo(typed, streams)
        assert streams.handed == {} and mc.renewal_rate_rows is None

    def test_stream_8_draws_and_is_live_exactly_when_the_simulator_draws_it(
            self, monkeypatch):
        spec = _spec(DATA / "hvr_example.yaml", 60)
        det = compute_deterministic(spec)
        verdict = _verdict(spec, det)
        got = dr.measure_channels(spec, det=det, verdict=verdict)
        assert 8 in got.drawn and 8 in got.live
        assert set(got.drawn) == oracles.oracle_drawn(spec, 60)
        # the file still on the spec, the draw switched off in the simulator:
        # channel 8 is neither drawn nor live, so neither is read off the spec
        real = mc_mod._world_draws
        monkeypatch.setattr(mc_mod, "_world_draws", lambda *a: mc_mod.WorldDraws(
            **{**real(*a).__dict__, "rate_rows": 0}))
        got = dr.measure_channels(spec, det=det, verdict=verdict)
        assert spec.renewal_rate_paths is not None
        assert 8 not in got.drawn and 8 not in got.live

    def test_the_rows_never_cross_a_surface(self):
        mc = run_monte_carlo(_spec(DATA / "hvr_example.yaml", 20))
        assert mc.renewal_rate_rows is not None
        assert "renewal_rate_rows" not in json.dumps(mc_to_dict(mc))


# ---------------------------------------------------------------------------
# §9 row 3: the draw is last, so the stream order holds
# ---------------------------------------------------------------------------

def _drawing_before_the_row(raw: dict) -> dict:
    """The config with a world that draws before the row: an inflation path, a
    house price shock and a value-growth vol, so the economy's and the
    market's draws all come first on the one generator of the legacy binding."""
    raw = copy.deepcopy(raw)
    raw["economic"]["inflation_vol"] = 0.01
    raw["simulation"]["value_growth_vol"] = 0.05
    raw["house"]["price_shock"] = {"annual_hazard": 0.03, "severity_mean": 0.2,
                                   "severity_vol": 0.1}
    return raw


def test_under_the_legacy_binding_every_earlier_draw_is_the_no_file_run_s():
    """The draw is LAST in the path's world: with one generator for every
    channel, path 0's inflation, crash and value draws on a file run are those
    of the same config without the file, and the file run's path 0 then takes
    exactly one more draw, one integers(0, N). The world draws its inflation,
    crash and value draws before the row, so a row drawn ahead of any of the
    three moves them and fails here."""
    raw = _drawing_before_the_row(_raw(FIXTURE, 1))
    filed = load_config_dict(raw)
    twin = copy.deepcopy(raw)
    twin.pop("renewal_rates")
    twin["sources"].pop("renewal_rates.path")
    if not twin["sources"]:
        twin.pop("sources")
    twin["house"]["mortgage_renewal_rates"] = filed.renewal_rate_paths.central_effective(4)
    plain_spec = load_config_dict(twin)
    assert plain_spec.renewal_rate_paths is None
    g_file = np.random.default_rng(1)
    g_plain = np.random.default_rng(1)
    world = mc_mod._draw_path_world(g_file, filed.economic, filed.simulation.years,
                                    mc_mod._world_draws(filed, (None, None)))
    plain = mc_mod._draw_path_world(g_plain, plain_spec.economic, plain_spec.simulation.years,
                                    mc_mod._world_draws(plain_spec, (None, None)))
    assert world.rate_row is not None and plain.rate_row is None
    # every channel the world draws before the row drew, on both runs
    assert len(plain.z_inflation) == len(plain.crash_uniforms) == len(plain.z_value) == 20
    assert any(z != 0.0 for z in plain.z_inflation)
    assert world.inflation_factors == plain.inflation_factors
    assert world.z_inflation == plain.z_inflation
    assert world.crash_uniforms == plain.crash_uniforms
    assert world.crash_zs == plain.crash_zs
    assert world.z_value == plain.z_value
    # and the file run's generator sits exactly one integers(0, N) further on,
    # `has_uint32` included
    g_plain.integers(0, filed.renewal_rate_paths.rows)
    assert g_file.bit_generator.state == g_plain.bit_generator.state


# ---------------------------------------------------------------------------
# §9 row 4: the channel count is read off the table
# ---------------------------------------------------------------------------

class TestTheChannelCount:
    def test_channel_8_resolves_and_7_and_9_do_not(self):
        assert dc.channel(8).key == "rates"
        assert dc.channel(8).sizing_keys == ("renewal_rates.path",)
        for bad in (7, 9):
            with pytest.raises(KeyError):
                dc.channel(bad)
        assert dr.ALL_CHANNEL_IDS == (0, 1, 2, 3, 4, 5, 6, 8)
        assert dr.STREAM_IDS == (0, 1, 2, 3, 4, 5, 6, 7, 8)

    def test_the_legacy_binding_takes_every_channel_and_refuses_the_old_seven(self):
        spec = _spec(FIXTURE, 4)
        run_monte_carlo(spec, freeze=dr.ALL_CHANNEL_IDS)
        with pytest.raises(ValueError, match="partial freeze"):
            run_monte_carlo(spec, freeze=range(7))
        with pytest.raises(ValueError, match="which is no channel"):
            run_monte_carlo(spec, addressed_streams(1), freeze=(7,))

    def test_the_refusals_name_channel_8(self):
        spec = _spec(FIXTURE, 4)
        with pytest.raises(ValueError) as caught:
            run_monte_carlo(spec, addressed_streams(1), freeze=(9,))
        assert "6 portfolio, 8 rates. Id 7 is" in str(caught.value)
        with pytest.raises(ValueError) as caught:
            run_monte_carlo(spec, freeze=(8,))
        assert "a freeze of every channel, [0, 1, 2, 3, 4, 5, 6, 8]," in str(caught.value)
        streams = {c: np.random.default_rng(c) for c in range(8)}
        with pytest.raises(ValueError) as caught:
            run_monte_carlo(spec, streams)
        assert str(caught.value).startswith("streams binds no stream for channel 8")
        assert "6 portfolio, 7 income, 8 rates)" in str(caught.value)

    def test_the_test_helpers_bind_every_stream(self):
        """The held-stream helpers bind stream 8, so a file run can use them."""
        from tests.test_decomposition_contract_doc import _held as held_doc
        from tests.test_decomposition_sentences import _held as held_sentences
        spec = _spec(DATA / "hvr_example.yaml", 3)
        for streams in (oracles.held_streams(), held_doc(), held_sentences()):
            assert run_monte_carlo(spec, streams).renewal_rate_rows is not None


# ---------------------------------------------------------------------------
# §9 rows 5 and 6: one market, and each option's own columns
# ---------------------------------------------------------------------------

def _record_rates(monkeypatch):
    seen = {"condo": [], "house": []}
    for name in seen:
        attr = f"_simulate_{name}_pv_once"
        real = getattr(mc_mod, attr)

        def wrapped(*args, _real=real, _name=name, **kwargs):
            seen[_name].append(kwargs.get("renewal_rates"))
            return _real(*args, **kwargs)

        monkeypatch.setattr(mc_mod, attr, wrapped)
    return seen


def test_two_options_price_one_row_each_with_its_own_columns(monkeypatch):
    spec = _spec(DATA / "two_opts.yaml", 300)
    loaded = spec.renewal_rate_paths
    assert loaded.columns == {"condo": 1, "house": 4}
    seen = _record_rates(monkeypatch)
    mc = run_monte_carlo(spec)
    rows = mc.renewal_rate_rows
    assert len(set(rows.tolist())) == loaded.rows
    for path, row in enumerate(rows.tolist()):
        assert seen["condo"][path] == list(loaded.effective[row][:1])
        assert seen["house"][path] == list(loaded.effective[row][:4])


def test_the_renewals_lines_carry_each_option_s_own_rates():
    out = subprocess.run([sys.executable, "-m", "hde.cli", str(DATA / "two_opts.yaml"),
                          "--no-monte-carlo"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    lines = {name: [line for line in out.splitlines()
                    if line.strip().startswith(f"{name} renewals:")]
             for name in ("condo", "house")}
    quoted = {name: re.search(r"rates as quoted \(semi-annual\) ([^=]*?) =", found[0]).group(1)
              for name, found in lines.items()}
    assert quoted == {"condo": "4.00%", "house": "4.00%, 5.00%, 6.00%, 7.00%"}


def test_an_option_that_reads_no_column_prices_the_empty_ladder_on_every_path():
    spec = _spec(DATA / "condo5.yaml", 200)
    mc = run_monte_carlo(spec)
    assert len(set(mc.renewal_rate_rows.tolist())) == 2
    # the condo reads no column, so its present value ignores the row
    frozen = run_monte_carlo(spec, addressed_streams(spec.simulation.random_seed),
                             freeze=(8,))
    drawn = run_monte_carlo(spec, addressed_streams(spec.simulation.random_seed))
    assert np.array_equal(frozen.condo.pvs, drawn.condo.pvs)
    assert not np.array_equal(frozen.house.pvs, drawn.house.pvs)


# ---------------------------------------------------------------------------
# §9 row 7: affordability per path
# ---------------------------------------------------------------------------

def test_a_path_s_affordability_reads_its_own_row():
    """On §4's config, whose income block holds income_growth_rate 0.0, the
    central row's peak ratio is 28.10% and row 1's is 38.55% against a 32%
    threshold, so the house breaches on exactly the paths that drew row 1."""
    raw = _raw(DATA / "hvr_example.yaml")
    raw["income"] = {"annual_income": 150000, "income_growth_rate": 0.0,
                     "affordability_threshold": 0.32}
    spec = load_config_dict(raw)
    mc = run_monte_carlo(spec)
    share = float(np.mean(mc.renewal_rate_rows == 1))
    assert share == 0.508
    assert mc.affordability_mc.prob_house_exceeds == share


def test_each_row_s_affordability_is_its_own_on_twelve_rows():
    """The fixture's twelve rows peak at different ratios against a fixed
    income; at a 35% threshold six of them breach (rows 1, 2, 5, 6, 7 and
    11), and P(house exceeds) is the share of paths that drew one of those
    six. With two rows a cost array cached for one row and read for another
    could not be told apart; with twelve it can."""
    raw = _raw(FIXTURE)
    raw["income"] = {"annual_income": 140000, "income_growth_rate": 0.0,
                     "affordability_threshold": 0.35}
    spec = load_config_dict(raw)
    loaded = spec.renewal_rate_paths
    from hde.deterministic import _annual_costs_for_option, _compute_income_trajectory
    income = _compute_income_trajectory(spec.income, spec.simulation.years, spec.economic)
    breach = [row for row in range(loaded.rows)
              if max(c / i for c, i in zip(_annual_costs_for_option(
                  "house", spec.house, spec.simulation, spec.economic,
                  renewal_rates=loaded.effective[row][:4]), income)) > 0.35]
    assert breach == [1, 2, 5, 6, 7, 11]
    mc = run_monte_carlo(spec)
    share = float(np.mean(np.isin(mc.renewal_rate_rows, breach)))
    assert share == 0.507
    assert mc.affordability_mc.prob_house_exceeds == share


# ---------------------------------------------------------------------------
# §9 row 8: freezing another channel keeps the rows
# ---------------------------------------------------------------------------

def test_freezing_any_other_channel_records_the_unfrozen_run_s_rows():
    spec = _spec(FIXTURE, 400)
    base = dr._run(spec, dr.MATRIX_A).renewal_rate_rows
    assert len(set(base.tolist())) == spec.renewal_rate_paths.rows
    for channel_id in (0, 1, 2, 3, 4, 5, 6):
        frozen = dr._run(spec, dr.MATRIX_A, freeze=(channel_id,))
        assert np.array_equal(frozen.renewal_rate_rows, base), channel_id
    frozen = dr._run(spec, dr.MATRIX_A, freeze=(8,))
    assert np.all(frozen.renewal_rate_rows == spec.renewal_rate_paths.central_index)
