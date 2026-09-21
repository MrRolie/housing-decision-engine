"""Parts B and C of docs/specs/2026-09-21-one-world-simulation.md.

**Part B — dispersion on the value track.** Every cost in the model had a
volatility parameter and the home's value had none, so the largest single term
in an owned option's total (terminal equity, −$218,959 of $518,779 in the
shipped showcase) was the one term with no spread. `severity_vol` is the crash
channel's magnitude, not an everyday spread. `simulation.value_growth_vol`
supplies the everyday one, from a draw the condo and the house SHARE, because
a path has one housing market.

**Part C — a lease-reset hazard on the rent side.** The owned options have had
a discrete price-crash channel since S4b; rent could only ever drift smoothly.
So the model handed the owner a tail and the renter nothing, which is not
neutral between them. `rent.reset_hazard` plus `rent.reset_to_monthly_rent`
give the renter the mirror: a probability per year that the tenancy ends and
rent steps onto the market track.

Both are opt-in with no default and no anchor. The absence invariant therefore
binds: a spec that wires neither must be byte-identical, Monte Carlo included.
"""

import dataclasses
import pathlib

import numpy as np
import pytest

from hde.config import ConfigValidationError, load_config, load_config_dict
from hde.models import (
    ComparisonSpec,
    CondoParams,
    EconomicParams,
    HouseParams,
    RentParams,
    SimulationParams,
)
from hde.monte_carlo import _pv_reset_series, _sample_reset_year, run_monte_carlo

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = sorted((REPO_ROOT / "examples").glob("*.yaml"))


def _spec(*, value_growth_vol=0.0, reset_hazard=0.0, reset_to=None,
          num_sims=400, years=20, seed=7):
    """A condo, a house and a renter with every other volatility OFF, so a
    test that turns on one channel is measuring that channel alone."""
    return ComparisonSpec(
        simulation=SimulationParams(
            years=years, discount_rate=0.03, num_sims=num_sims, random_seed=seed,
            value_growth_vol=value_growth_vol,
        ),
        economic=EconomicParams(mode="real", inflation_rate=0.02, inflation_vol=0.0),
        condo=CondoParams(initial_value=450_000, monthly_fee=400, all_cash=True,
                          value_growth_rate=0.01),
        house=HouseParams(initial_value=650_000, all_cash=True,
                          value_growth_rate=0.01),
        rent=RentParams(monthly_rent=2_100, reset_hazard=reset_hazard,
                        reset_to_monthly_rent=reset_to),
    )


# ---------------------------------------------------------------------------
# Part B — the value track gets a spread, and it is the market's
# ---------------------------------------------------------------------------

class TestValueDispersion:
    def test_absent_key_is_a_single_path_run(self):
        """The whole absence invariant in one line: with no volatility wired
        anywhere, every path is identical. If value dispersion leaked a draw
        when its key is absent, this spread would be non-zero."""
        result = run_monte_carlo(_spec())
        for pvs in (result.condo.pvs, result.house.pvs, result.rent.pvs):
            assert len(set(np.asarray(pvs).tolist())) == 1

    def test_setting_the_key_spreads_both_owned_totals(self):
        result = run_monte_carlo(_spec(value_growth_vol=0.08))
        condo = np.asarray(result.condo.pvs)
        house = np.asarray(result.house.pvs)
        # Distinct VALUES, not a standard deviation: np.std of a constant
        # array of large floats returns ~1e-11 rather than 0, so a spread
        # assertion would pass on an engine that never applied the shock.
        assert len(set(condo.tolist())) == len(condo)
        assert len(set(house.tolist())) == len(house)
        # The renter holds no property, so their total must NOT move.
        assert len(set(np.asarray(result.rent.pvs).tolist())) == 1

    def test_one_market_moves_both_properties_together(self):
        """The shared draw, stated as a measurement: with value dispersion as
        the only live channel, the condo and the house are driven by the same
        year-by-year multiplier, so their totals are near-perfectly rank
        aligned. Independent draws would put this near zero."""
        result = run_monte_carlo(_spec(value_growth_vol=0.08, num_sims=500))
        condo = np.asarray(result.condo.pvs)
        house = np.asarray(result.house.pvs)
        corr = float(np.corrcoef(condo, house)[0, 1])
        assert corr > 0.95, f"one market must move both properties: corr={corr:.4f}"

    def test_dispersion_is_mean_preserving(self):
        """The lognormal multiplier has mean 1, so switching the channel on
        must not move the CENTRE of either distribution — only its width. A
        channel that shifted the mean would be a forecast change disguised as
        an uncertainty input."""
        flat = run_monte_carlo(_spec(num_sims=3_000, seed=11))
        wide = run_monte_carlo(_spec(value_growth_vol=0.08, num_sims=3_000, seed=11))
        for option in ("condo", "house"):
            base = float(np.mean(getattr(flat, option).pvs))
            shocked = float(np.mean(getattr(wide, option).pvs))
            # Within 2% of the flat mean: sampling error at 3,000 paths, not
            # a systematic drift. A one-sided bias shows up far larger.
            assert abs(shocked - base) < 0.02 * abs(base), (option, base, shocked)

    def test_key_is_reachable_from_yaml_and_declared_uncertainty(self):
        from hde.config import single_path_run
        from hde.sources import uncertainty_keys

        data = {
            "years": 15, "discount_rate": 0.03,
            "condo": {"initial_value": 400_000, "monthly_fee": 350, "all_cash": True},
            "simulation": {"value_growth_vol": 0.07},
        }
        spec = load_config_dict(data)
        assert spec.simulation.value_growth_vol == 0.07
        # It draws, so the run is not a single path and the echo must say so.
        assert single_path_run(spec) is False
        assert "simulation.value_growth_vol" in uncertainty_keys(data)


# ---------------------------------------------------------------------------
# Part C — the renter gets a tail
# ---------------------------------------------------------------------------

class TestLeaseReset:
    def test_certain_hazard_resets_in_year_one_on_every_path(self):
        rng = np.random.default_rng(0)
        assert [_sample_reset_year(1.0, 20, rng) for _ in range(50)] == [1] * 50

    def test_zero_hazard_never_fires_and_consumes_no_draw(self):
        rng = np.random.default_rng(0)
        assert _sample_reset_year(0.0, 20, rng) is None
        # The generator must be untouched: the first draw after a zero-hazard
        # call is the first draw of a fresh generator.
        assert float(rng.random()) == float(np.random.default_rng(0).random())

    def test_resetting_to_your_own_rent_costs_nothing(self):
        """The cleanest statement of what the channel means. A tenant who
        already pays market rent has no exposure, so the reset must be a
        no-op for any reset year."""
        rates = [0.01] * 12
        plain = _pv_reset_series(24_000, 24_000, rates, 0.03, 12, 12)
        for reset_year in (1, 5, 12):
            assert _pv_reset_series(24_000, 24_000, rates, 0.03, 12, reset_year) == \
                pytest.approx(plain)

    def test_the_market_track_escalates_so_a_later_reset_costs_more_per_year(self):
        """A reset in year 8 must land on year 8's market rent, not today's.
        Comparing the year the reset lands in: an engine that stepped to the
        un-escalated figure would show the same annual rent whenever it fired.
        """
        rates = [0.03] * 10
        # One-year horizon ending exactly at the reset year isolates the
        # amount the tenant pays in that first reset year.
        year_1 = _pv_reset_series(24_000, 30_000, rates, 0.0, 1, 1)
        year_5_pv = _pv_reset_series(24_000, 30_000, rates, 0.0, 5, 5)
        year_4_pv = _pv_reset_series(24_000, 30_000, rates, 0.0, 4, 5)
        year_5_amount = year_5_pv - year_4_pv
        assert year_1 == pytest.approx(30_000 * 1.03)
        assert year_5_amount == pytest.approx(30_000 * 1.03 ** 5)
        assert year_5_amount > year_1

    def test_a_reset_upward_raises_the_renter_total(self):
        below = _spec(reset_hazard=0.0)
        exposed = _spec(reset_hazard=0.10, reset_to=3_200)
        assert float(np.mean(run_monte_carlo(exposed).rent.pvs)) > \
            float(np.mean(run_monte_carlo(below).rent.pvs))

    def test_the_hazard_gives_the_renter_a_spread_they_did_not_have(self):
        """The asymmetry this closes. With every other volatility off, the
        owned options have a tail and the renter's total is a single number;
        wiring the reset gives the renter distinct outcomes across paths."""
        flat = run_monte_carlo(_spec())
        assert len(set(np.asarray(flat.rent.pvs).tolist())) == 1
        exposed = run_monte_carlo(_spec(reset_hazard=0.08, reset_to=3_000))
        distinct = len(set(np.asarray(exposed.rent.pvs).tolist()))
        assert distinct > 5, f"only {distinct} distinct renter totals"

    def test_hazard_without_a_market_rent_refuses(self):
        with pytest.raises(ConfigValidationError, match="will not guess"):
            load_config_dict({
                "years": 10, "discount_rate": 0.03,
                "rent": {"monthly_rent": 2_000, "reset_hazard": 0.1},
            })

    def test_a_market_rent_that_can_never_be_used_refuses(self):
        """A figure the user supplied that the engine would silently ignore is
        the worse of the two failures under the honesty contract."""
        with pytest.raises(ConfigValidationError, match="would be ignored"):
            load_config_dict({
                "years": 10, "discount_rate": 0.03,
                "rent": {"monthly_rent": 2_000, "reset_to_monthly_rent": 3_000},
            })

    @pytest.mark.parametrize("hazard", [-0.1, 1.5, float("nan"), float("inf")])
    def test_a_hazard_outside_zero_to_one_refuses(self, hazard):
        """NaN is in the list deliberately. Every comparison against NaN is
        False, so `h < 0 or h > 1` ACCEPTS it, and a NaN hazard then never
        fires — `rng.random() < nan` is always False — which would silently
        price no reset for a user who stated one."""
        with pytest.raises(ConfigValidationError, match="annual probability"):
            load_config_dict({
                "years": 10, "discount_rate": 0.03,
                "rent": {"monthly_rent": 2_000, "reset_hazard": hazard,
                         "reset_to_monthly_rent": 3_000},
            })

    @pytest.mark.parametrize("market", [0, -100, float("nan"), float("inf")])
    def test_a_market_rent_that_is_not_a_positive_number_refuses(self, market):
        with pytest.raises(ConfigValidationError, match="positive number"):
            load_config_dict({
                "years": 10, "discount_rate": 0.03,
                "rent": {"monthly_rent": 2_000, "reset_hazard": 0.05,
                         "reset_to_monthly_rent": market},
            })

    def test_the_pair_is_declared_uncertainty(self):
        from hde.config import single_path_run
        from hde.sources import uncertainty_keys

        data = {
            "years": 10, "discount_rate": 0.03,
            "rent": {"monthly_rent": 2_000, "reset_hazard": 0.08,
                     "reset_to_monthly_rent": 3_000},
        }
        assert single_path_run(load_config_dict(data)) is False
        keys = uncertainty_keys(data)
        assert "rent.reset_hazard" in keys
        assert "rent.reset_to_monthly_rent" in keys


class TestTheOneSidedGateSeesBothNewChannels:
    """`dispersion_sources` names what gives each SIDE a distribution, and the
    one-sided-uncertainty warning reads it. A channel it does not know about
    makes that warning lie.

    Measured on the engine before this fix: a config with an owned
    `price_shock` and a renter `reset_hazard` was told "the renter's PV is a
    single path" while the renter's PV ran from $291,579 to $534,562 across
    2,000 paths. Asserting the opposite of the truth is the failure the honesty
    contract weighs heaviest, so all four cases below are pinned.
    """

    @staticmethod
    def _spec(*, value_vol=0.0, hazard=0.0, reset_to=None, shock=False):
        cfg = {
            "years": 20, "discount_rate": 0.03,
            "condo": {"initial_value": 450_000, "monthly_fee": 400, "all_cash": True},
            "rent": {"monthly_rent": 1_200},
            "simulation": {"num_sims": 200, "value_growth_vol": value_vol},
        }
        if shock:
            cfg["condo"]["price_shock"] = {"annual_hazard": 0.03, "severity_mean": 0.2}
        if hazard:
            cfg["rent"]["reset_hazard"] = hazard
            cfg["rent"]["reset_to_monthly_rent"] = reset_to
        return load_config_dict(cfg)

    def test_value_growth_vol_counts_for_the_owned_side(self):
        from hde.config import dispersion_sources
        owned, renter, _ = dispersion_sources(self._spec(value_vol=0.07))
        assert "simulation.value_growth_vol" in owned
        assert renter == []

    def test_the_lease_reset_counts_for_the_renter(self):
        from hde.config import dispersion_sources
        owned, renter, _ = dispersion_sources(self._spec(hazard=0.08, reset_to=2_200))
        assert "rent.reset_hazard" in renter
        assert owned == []

    def test_owner_only_dispersion_warns(self):
        from hde.config import coherence_warnings
        warns = " ".join(coherence_warnings(self._spec(value_vol=0.07)))
        assert "one-sided uncertainty" in warns
        assert "simulation.value_growth_vol" in warns

    def test_renter_only_dispersion_warns(self):
        from hde.config import coherence_warnings
        warns = " ".join(coherence_warnings(self._spec(hazard=0.08, reset_to=2_200)))
        assert "one-sided uncertainty" in warns
        assert "rent.reset_hazard" in warns

    def test_both_sides_stochastic_makes_no_one_sided_claim(self):
        """The case that used to LIE. The renter's side must also genuinely
        have a spread, or this would pass on an engine that had simply stopped
        warning about anything."""
        from hde.config import coherence_warnings
        spec = self._spec(shock=True, hazard=0.08, reset_to=2_200)
        warns = " ".join(coherence_warnings(spec))
        assert "one-sided uncertainty" not in warns
        rent_pvs = np.asarray(run_monte_carlo(spec).rent.pvs)
        assert len(set(rent_pvs.tolist())) > 1, "the renter really must have a spread"

    def test_the_remedy_names_the_channel_that_would_fix_it(self):
        """A warning that says what is wrong and not what to do sends the user
        back to the schema. Both remedies name the new knobs."""
        from hde.config import coherence_warnings
        owner = " ".join(coherence_warnings(self._spec(value_vol=0.07)))
        assert "rent.reset_hazard" in owner
        renter = " ".join(coherence_warnings(self._spec(hazard=0.08, reset_to=2_200)))
        assert "simulation.value_growth_vol" in renter


class TestEveryVolatilityRefusesANegative:
    """A volatility is a standard deviation, so a negative one is not a value —
    it is a typo. Until 2026-09-21 only `other_cost_vol` and `inflation_vol`
    said so; the other four accepted a negative and treated it as OFF, which
    means the engine silently ignored a figure the user had typed. That is the
    failure the honesty contract weighs heaviest, so there is now one rule.
    """

    VOLS = ["house_maintenance_vol", "condo_fee_vol", "other_cost_vol",
            "rent_escalation_vol", "investment_return_vol", "value_growth_vol"]

    @pytest.mark.parametrize("key", VOLS)
    def test_a_negative_volatility_refuses(self, key):
        with pytest.raises(ConfigValidationError, match=f"{key} should be >= 0"):
            load_config_dict({
                "years": 10, "discount_rate": 0.03,
                "condo": {"initial_value": 400_000, "monthly_fee": 350, "all_cash": True},
                "simulation": {key: -0.2},
            })

    @pytest.mark.parametrize("key", VOLS)
    def test_zero_and_positive_still_load(self, key):
        for value in (0.0, 0.15):
            spec = load_config_dict({
                "years": 10, "discount_rate": 0.03,
                "condo": {"initial_value": 400_000, "monthly_fee": 350, "all_cash": True},
                "simulation": {key: value},
            })
            assert getattr(spec.simulation, key) == value

    def test_the_list_covers_every_volatility_the_engine_has(self):
        """The rule is only one rule if it names every key. Pins the list
        against `SimulationParams` itself, so a new `*_vol` field added later
        fails here instead of quietly escaping validation."""
        fields = {f for f in SimulationParams.__dataclass_fields__ if f.endswith("_vol")}
        assert fields == set(self.VOLS), fields.symmetric_difference(set(self.VOLS))


# ---------------------------------------------------------------------------
# Neither channel touches a spec that does not wire it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("config", EXAMPLES, ids=lambda p: p.stem)
def test_no_shipped_example_wires_either_channel(config):
    """Both channels are opt-in with no default, so every shipped example must
    read them as off. This is what makes the absence invariant checkable by
    running the examples rather than by reading the code."""
    spec = load_config(str(config))
    assert spec.simulation.value_growth_vol == 0.0
    if spec.rent is not None:
        assert spec.rent.reset_hazard == 0.0
        assert spec.rent.reset_to_monthly_rent is None
