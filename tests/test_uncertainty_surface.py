"""The uncertainty machinery's regression surface (docs/BOARD.md item 12).

WHAT WAS WRONG. Six of the seven configs in `examples/` set no inflation
volatility. Only `showcase_demographic_prior.yaml` wires a prior and a crash, so
it was the only shipped config whose Monte Carlo block moved when the simulation
changed; every other example's uncertainty output was a constant, and a constant
cannot regress. Two real defects hid behind that in September 2026: with
inflation as the only volatility the renter's total was ONE value across 500
paths (the engine compared a distribution against a point), and the three
options were priced in three unrelated economies. Neither could be detected by
running any example. The regression surface had nothing on it.

WHAT THIS IS. `tests/fixtures/uncertainty_surface.yaml` is one config whose job
is to make every stochastic channel in the engine draw at once — a cash condo, a
leveraged house and a sitting tenant, in ONE world — and
`tests/fixtures/uncertainty_surface_mc_golden.json` is its Monte Carlo block,
committed. A change to the simulation now has to explain itself against a
committed figure.

WHY THE FIXTURE IS NOT IN `examples/`. Two reasons, and the second is decisive.
`examples/` is a reading-order walkthrough (`examples/README.md`) for a stranger
learning the tool, and this file's figures are chosen for mechanism coverage
rather than because a household has them. More importantly,
`tests/test_price_dispersion_and_lease_reset.py::test_no_shipped_example_wires_either_channel`
asserts that EVERY file in `examples/` reads `value_growth_vol` as 0 and wires no
lease reset — that is how the absence invariant is checked by RUNNING the shipped
configs rather than by reading the code. Putting a fully-stochastic config there
would have forced that assertion down to "every example that existed before",
which is a gate with no failure state. Here it stays exactly as strong as it was,
and the regression surface is built out of a file that gate never has to see.

HOW TO READ A FAILURE OF `test_monte_carlo_block_matches_the_pin`.
The failure prints every figure that moved, with its pinned value, its observed
value and the delta. Then:

  * Did you change anything under `src/hde/`? Then the move may well be INTENDED
    — regenerate with

        uv run --extra dev python tests/test_uncertainty_surface.py --regenerate

    and say in the commit message WHICH channel moved and WHY. A regenerated
    golden with no such sentence is the same thing as no golden at all.
    THE BOUNDARY IS THE WHOLE PACKAGE, not `monte_carlo.py`: these figures moved
    twice while this fixture was being written, once because `config.py` derived
    a tax line differently and once because `models.py` read a pay-drop event
    differently. Neither touched the simulation. A reader told to suspect only
    `monte_carlo.py` would have called both of those regressions.
  * Did you change nothing under `src/hde/`? Then the move is a REGRESSION, and
    the figures that moved name the channel: `rent.*` alone points at the rent
    side, `condo.*` and `house.*` together at the shared market draw, and the
    three `prob_*_cheapest` moving while every marginal stays put points at the
    COUPLING between the options rather than at any one of them.

WHY THE `prob_*_cheapest` FIGURES ARE THE PART THAT MATTERS. They are the only
JOINT-sensitive numbers on this surface: each option's `mean`, `std` and
percentiles describe that option alone, and a regression in how the three are
COMPARED does not have to move any of them. MEASURED, by reverting the shared
crash draw in `_apply_price_shock` in a scratch copy — each option crashing in
its own year again, the defect fixed on 2026-09-21 — and running this pin against
it: P(house cheapest) went 0.0905 -> 0.1720 (+90% of itself) and P(condo cheapest)
0.5705 -> 0.4915, while `condo.mean` moved 1.5% and `house.std` 0.8%, which is the
size of the reshuffled RNG stream rather than a distributional change. So a
reviewer who sees the marginals nudge and the probabilities lurch is looking at
the comparison breaking, not at the options breaking.

WHAT IS PINNED is `serialization.mc_to_dict`, which is exactly the `monte_carlo`
block of `uv run hde <config> --json` (`cli.py` serializes no second form). The
pin is therefore on the published surface, not on an internal one that could
agree with the engine while the output disagreed.
"""

import dataclasses
import json
import math
import pathlib
import sys

import numpy as np
import pytest

from hde.config import coherence_warnings, dispersion_sources, load_config, single_path_run
from hde.monte_carlo import run_monte_carlo
from hde.serialization import mc_to_dict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"
GOLDEN = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface_mc_golden.json"
REGEN_COMMAND = (
    "uv run --extra dev python tests/test_uncertainty_surface.py --regenerate"
)

# The tolerance is NOT statistical. The engine is seeded and its draws are
# stability-guaranteed by NumPy's own policy, so a correct engine reproduces
# these figures exactly; the slack below exists only for last-bit differences
# from floating-point re-association across platforms. Any real change to the
# simulation moves these numbers by many orders of magnitude more than this:
# the September regressions moved P(cheapest) by tens of percentage points.
REL_TOL = 1e-9
ABS_TOL = 1e-6


@pytest.fixture(autouse=True)
def _at_repo_root(monkeypatch):
    """`market_scenario.path` in the fixture is resolved against the CURRENT
    WORKING DIRECTORY (`market_scenario.load_scenario_prior` takes the string as
    given), which is the same convention every other config in this repo uses.
    Pinning the directory here means these tests do not depend on where pytest
    was invoked from."""
    monkeypatch.chdir(REPO_ROOT)


# ---------------------------------------------------------------------------
# Flatten / compare — the readable failure is the whole point of the pin
# ---------------------------------------------------------------------------

def _flatten(doc, prefix=""):
    """`{'condo': {'mean': 1}}` -> `{'condo.mean': 1}`; lists index by position."""
    flat = {}
    if isinstance(doc, dict):
        for key, value in doc.items():
            flat.update(_flatten(value, f"{prefix}{key}."))
    elif isinstance(doc, list):
        for index, value in enumerate(doc):
            flat.update(_flatten(value, f"{prefix}{index}."))
    else:
        flat[prefix.rstrip(".")] = doc
    return flat


def _differences(pinned: dict, observed: dict):
    """Every leaf that moved, as (path, pinned, observed). Missing and added
    leaves are differences too — a figure that stopped being emitted is a
    regression the engine would otherwise report as silence."""
    left, right = _flatten(pinned), _flatten(observed)
    out = []
    for path in sorted(set(left) | set(right)):
        if path not in left:
            out.append((path, "<absent from the pin>", right[path]))
        elif path not in right:
            out.append((path, left[path], "<no longer emitted>"))
        elif isinstance(left[path], (int, float)) and isinstance(right[path], (int, float)) \
                and not isinstance(left[path], bool):
            if not math.isclose(float(left[path]), float(right[path]),
                                rel_tol=REL_TOL, abs_tol=ABS_TOL):
                out.append((path, left[path], right[path]))
        elif left[path] != right[path]:
            out.append((path, left[path], right[path]))
    return out


def _report(diffs) -> str:
    width = max(len(path) for path, _, _ in diffs)
    lines = [
        "",
        f"{len(diffs)} figure(s) moved against tests/fixtures/uncertainty_surface_mc_golden.json.",
        "",
        f"{'figure'.ljust(width)}  {'pinned':>20}  {'observed':>20}  delta",
    ]
    for path, pinned, observed in diffs:
        if isinstance(pinned, (int, float)) and isinstance(observed, (int, float)) \
                and not isinstance(pinned, bool):
            delta = f"{float(observed) - float(pinned):+,.6g}"
            lines.append(f"{path.ljust(width)}  {float(pinned):>20,.6f}  "
                         f"{float(observed):>20,.6f}  {delta}")
        else:
            lines.append(f"{path.ljust(width)}  {str(pinned):>20}  {str(observed):>20}  —")
    lines += [
        "",
        "INTENDED change to the simulation? Regenerate and say in the commit which",
        f"channel moved and why:  {REGEN_COMMAND}",
        "",
        "Touched none of src/hde/{monte_carlo,pv,market_scenario,deterministic}.py?",
        "Then this is a regression. See this module's docstring for how to read which",
        "channel the moved figures name — in particular, prob_*_cheapest moving while",
        "the marginals hold still is the COUPLING between the options breaking.",
    ]
    return "\n".join(lines)


def _monte_carlo_block() -> dict:
    return mc_to_dict(run_monte_carlo(load_config(str(CONFIG))))


# ---------------------------------------------------------------------------
# The pin
# ---------------------------------------------------------------------------

def test_monte_carlo_block_matches_the_pin():
    pinned = json.loads(GOLDEN.read_text(encoding="utf-8"))["monte_carlo"]
    observed = _monte_carlo_block()
    diffs = _differences(pinned, observed)
    assert not diffs, _report(diffs)


def test_the_golden_carries_the_regeneration_command_this_module_names():
    """The golden's `_about` block prints the regeneration command for whoever
    opens the file rather than the test, so the command is written down twice.
    This is the alarm on the pair: when they disagree, the reader of the file is
    being told to run something that is not the command."""
    about = "\n".join(json.loads(GOLDEN.read_text(encoding="utf-8"))["_about"])
    assert REGEN_COMMAND in about, (
        "tests/fixtures/uncertainty_surface_mc_golden.json prints a different "
        "regeneration command from the one this module defines"
    )


def test_the_pin_covers_every_figure_the_block_emits():
    """A pin that silently stopped covering a figure would go on passing while
    that figure drifted. Compares the SHAPE of the committed block against the
    shape the engine emits, so a new Monte Carlo output has to be pinned rather
    than quietly escape."""
    pinned = json.loads(GOLDEN.read_text(encoding="utf-8"))["monte_carlo"]
    observed = _monte_carlo_block()
    missing = sorted(set(_flatten(observed)) - set(_flatten(pinned)))
    assert not missing, (
        f"the engine emits figures the pin does not cover: {missing} — regenerate "
        f"with `{REGEN_COMMAND}` and state in the commit what the new figures are"
    )


# ---------------------------------------------------------------------------
# The fixture has to keep being what it claims to be
# ---------------------------------------------------------------------------

# Every stochastic channel the engine has, with the base it multiplies. A
# channel whose base is zero draws and then multiplies nothing, which is a
# pinned constant wearing a volatility's name — the exact failure this item
# exists to end, one level down.
CHANNELS = {
    "economic.inflation_vol": lambda s: s.economic.inflation_vol,
    "simulation.condo_fee_vol": lambda s: s.simulation.condo_fee_vol,
    "simulation.house_maintenance_vol": lambda s: s.simulation.house_maintenance_vol,
    "simulation.other_cost_vol": lambda s: s.simulation.other_cost_vol,
    "simulation.rent_escalation_vol": lambda s: s.simulation.rent_escalation_vol,
    "simulation.investment_return_vol": lambda s: s.simulation.investment_return_vol,
    "simulation.value_growth_vol": lambda s: s.simulation.value_growth_vol,
    "condo.price_shock.annual_hazard": lambda s: s.condo.price_shock.annual_hazard,
    "house.price_shock.annual_hazard": lambda s: s.house.price_shock.annual_hazard,
    "rent.reset_hazard": lambda s: s.rent.reset_hazard,
}

BASES = {
    "condo.monthly_fee": lambda s: s.condo.monthly_fee,
    "house.annual_maintenance_rate": lambda s: s.house.annual_maintenance_rate,
    "condo.other_recurring_costs": lambda s: len(s.condo.other_recurring_costs),
    "house.other_recurring_costs": lambda s: len(s.house.other_recurring_costs),
    "rent.other_recurring_costs": lambda s: len(s.rent.other_recurring_costs),
    "rent.invested_down_payment": lambda s: s.rent.invested_down_payment,
    "rent.reset_to_monthly_rent": lambda s: s.rent.reset_to_monthly_rent,
    "condo.events": lambda s: len(s.condo.events),
    "house.events": lambda s: len(s.house.events),
    "rent.events": lambda s: len(s.rent.events),
    "income.pay_drop_events": lambda s: len(s.income.pay_drop_events),
}


@pytest.mark.parametrize("name", sorted(CHANNELS))
def test_every_channel_is_wired(name):
    assert CHANNELS[name](load_config(str(CONFIG))) > 0, (
        f"{name} is off in the fixture — the surface this file exists to provide "
        f"has a hole in it"
    )


@pytest.mark.parametrize("name", sorted(BASES))
def test_every_channel_has_a_live_base(name):
    assert BASES[name](load_config(str(CONFIG))) > 0, (
        f"{name} is zero, so the volatility that multiplies it is inert and its "
        f"pinned figures are constants"
    )


def test_the_channel_list_names_every_volatility_the_engine_has():
    """The roster is only a roster if it is complete. Pins it against
    `SimulationParams` itself, so a `*_vol` added later fails here instead of
    quietly staying off this surface for a year."""
    from hde.models import SimulationParams
    engine = {f for f in SimulationParams.__dataclass_fields__ if f.endswith("_vol")}
    covered = {n.split(".", 1)[1] for n in CHANNELS if n.startswith("simulation.")}
    assert engine == covered, engine.symmetric_difference(covered)


def test_the_three_options_and_the_prior_are_all_present():
    spec = load_config(str(CONFIG))
    assert spec.condo is not None and spec.house is not None and spec.rent is not None
    assert spec.market_scenario is not None, "no prior: the scenario draw is not exercised"
    assert spec.income is not None, "no income block: affordability_mc would be null"
    assert spec.economic.mode == "nominal", (
        "inflation_vol is inert on escalation in real mode — a real-mode fixture "
        "wires the channel that caught the biggest defect of the month and leaves "
        "it half dead"
    )


def test_both_sides_carry_dispersion_so_the_probabilities_mean_something():
    """P(cheapest) is only a comparison if BOTH sides have a spread. The engine's
    own one-sided-uncertainty gate is the judge, so this asserts against the
    warning the engine would print rather than against a restatement of it."""
    spec = load_config(str(CONFIG))
    owned, renter, shared = dispersion_sources(spec)
    assert owned and renter and shared, (owned, renter, shared)
    warns = " ".join(coherence_warnings(spec))
    assert "one-sided uncertainty" not in warns, warns
    assert single_path_run(spec) is False


def test_all_three_totals_really_have_a_spread():
    """The guard under the guard: `dispersion_sources` reads the CONFIG, so it
    would still say "both sides" on an engine that had stopped drawing. This
    reads the paths. Distinct VALUES, not a standard deviation: np.std of a
    constant array of numbers this large returns ~1e-11 rather than 0."""
    mc = run_monte_carlo(load_config(str(CONFIG)))
    for option in ("condo", "house", "rent"):
        pvs = np.asarray(getattr(mc, option).pvs)
        assert len(set(pvs.tolist())) > len(pvs) // 2, (
            f"{option}: only {len(set(pvs.tolist()))} distinct totals across "
            f"{len(pvs)} paths"
        )


# ---------------------------------------------------------------------------
# Each channel reaches the output, and reaches the options it belongs to
# ---------------------------------------------------------------------------
#
# Perturb one channel and require the totals to move. Most perturbations here
# SCALE a channel rather than switching it off, which keeps the number of draws
# consumed identical — so the comparison is exact and noise-free, and an option
# that must NOT move is bit-for-bit unchanged. Switching a channel off instead
# would shift every later draw and move all three totals for a reason that has
# nothing to do with the channel, which is a test that cannot fail.

def _totals(spec):
    mc = run_monte_carlo(spec)
    return {name: np.asarray(getattr(mc, name).pvs) for name in ("condo", "house", "rent")}


def _fast(spec, paths: int = 200):
    """Movement is detected by exact inequality, so a short run is enough and
    keeps this file cheap to run."""
    return dataclasses.replace(
        spec, simulation=dataclasses.replace(spec.simulation, num_sims=paths))


def _scale_simulation(spec, field, factor):
    sim = spec.simulation
    return dataclasses.replace(
        spec, simulation=dataclasses.replace(sim, **{field: getattr(sim, field) * factor}))


# (label, how to perturb, which options must move, which must be bit-identical)
PERTURBATIONS = [
    ("economic.inflation_vol",
     lambda s: dataclasses.replace(
         s, economic=dataclasses.replace(s.economic, inflation_vol=s.economic.inflation_vol * 2)),
     ("condo", "house", "rent"), ()),
    ("simulation.condo_fee_vol",
     lambda s: _scale_simulation(s, "condo_fee_vol", 2.0), ("condo",), ("house", "rent")),
    ("simulation.house_maintenance_vol",
     lambda s: _scale_simulation(s, "house_maintenance_vol", 2.0), ("house",), ("condo", "rent")),
    ("simulation.other_cost_vol",
     lambda s: _scale_simulation(s, "other_cost_vol", 2.0), ("condo", "house", "rent"), ()),
    ("simulation.rent_escalation_vol",
     lambda s: _scale_simulation(s, "rent_escalation_vol", 2.0), ("rent",), ("condo", "house")),
    ("simulation.investment_return_vol",
     lambda s: _scale_simulation(s, "investment_return_vol", 2.0), ("rent",), ("condo", "house")),
    # One housing market: the shared value draw must move BOTH properties and
    # leave the renter, who owns none, untouched.
    ("simulation.value_growth_vol",
     lambda s: _scale_simulation(s, "value_growth_vol", 2.0), ("condo", "house"), ("rent",)),
    ("simulation.corr_inflation_condo",
     lambda s: _scale_simulation(s, "corr_inflation_condo", -1.0), ("condo",), ("house", "rent")),
    ("simulation.corr_inflation_house",
     lambda s: _scale_simulation(s, "corr_inflation_house", -1.0), ("house",), ("condo", "rent")),
    # Updated 2026-09-21 when board item 14 landed. This row previously
    # expected the renter to be bit-identical, because the renter's other-cost
    # shock kept an independent draw. That WAS the defect: the key names a cost
    # category, not a tenure, and it now reaches all three options. The row is
    # a good record of how the pin earns its place — it was written by one
    # builder and caught the other's semantic change on the next merge.
    ("simulation.corr_inflation_other",
     lambda s: _scale_simulation(s, "corr_inflation_other", -1.0),
     ("condo", "house", "rent"), ()),
    ("simulation.corr_inflation_event_cost",
     lambda s: _scale_simulation(s, "corr_inflation_event_cost", -1.0),
     ("condo", "house", "rent"), ()),
    ("condo.price_shock.annual_hazard",
     lambda s: dataclasses.replace(s, condo=dataclasses.replace(
         s.condo, price_shock=dataclasses.replace(
             s.condo.price_shock, annual_hazard=s.condo.price_shock.annual_hazard * 2))),
     ("condo",), ("house", "rent")),
    ("house.price_shock.severity_mean",
     lambda s: dataclasses.replace(s, house=dataclasses.replace(
         s.house, price_shock=dataclasses.replace(
             s.house.price_shock, severity_mean=s.house.price_shock.severity_mean * 2))),
     ("house",), ("condo", "rent")),
    ("condo.events[].cost_vol",
     lambda s: dataclasses.replace(s, condo=dataclasses.replace(
         s.condo, events=[dataclasses.replace(e, cost_vol=e.cost_vol * 2)
                          for e in s.condo.events])),
     ("condo",), ("house", "rent")),
    ("house.events[].cost_vol",
     lambda s: dataclasses.replace(s, house=dataclasses.replace(
         s.house, events=[dataclasses.replace(e, cost_vol=e.cost_vol * 2)
                          for e in s.house.events])),
     ("house",), ("condo", "rent")),
    ("rent.events[].cost_vol",
     lambda s: dataclasses.replace(s, rent=dataclasses.replace(
         s.rent, events=[dataclasses.replace(e, cost_vol=e.cost_vol * 2)
                         for e in s.rent.events])),
     ("rent",), ("condo", "house")),
    ("rent.reset_to_monthly_rent",
     lambda s: dataclasses.replace(s, rent=dataclasses.replace(
         s.rent, reset_to_monthly_rent=s.rent.reset_to_monthly_rent * 2)),
     ("rent",), ("condo", "house")),
    # NOT stream-preserving: `_sample_reset_year` draws once per year until the
    # tenancy ends, so changing the hazard changes how many draws the path
    # consumes and every later draw shifts. Only the "must move" half is
    # asserted for it.
    ("rent.reset_hazard",
     lambda s: dataclasses.replace(s, rent=dataclasses.replace(
         s.rent, reset_hazard=s.rent.reset_hazard * 2)),
     ("rent",), ()),
    # Likewise: dropping the prior removes the scenario and band draws.
    ("market_scenario",
     lambda s: dataclasses.replace(s, market_scenario=None), ("condo", "house"), ()),
]


@pytest.mark.parametrize("label,perturb,must_move,must_hold",
                         PERTURBATIONS, ids=[p[0] for p in PERTURBATIONS])
def test_each_channel_reaches_the_options_it_belongs_to(label, perturb, must_move, must_hold):
    base_spec = _fast(load_config(str(CONFIG)))
    base = _totals(base_spec)
    moved = _totals(perturb(base_spec))
    for option in must_move:
        assert not np.array_equal(base[option], moved[option]), (
            f"perturbing {label} left the {option} totals bit-identical — the "
            f"channel is inert in this fixture, so its pinned figures are constants"
        )
    for option in must_hold:
        assert np.array_equal(base[option], moved[option]), (
            f"perturbing {label} moved the {option} totals, which it should not "
            f"reach — either the channel leaked across options or it changed how "
            f"many draws a path consumes (see the note above PERTURBATIONS)"
        )


def test_the_affordability_channel_reaches_the_affordability_block():
    """`income.pay_drop_events` is the only channel whose output lives in
    `affordability_mc` rather than in the totals, so it gets its own case."""
    base_spec = _fast(load_config(str(CONFIG)))
    shocked = dataclasses.replace(base_spec, income=dataclasses.replace(
        base_spec.income,
        pay_drop_events=[dataclasses.replace(e, magnitude_vol=e.magnitude_vol * 2)
                         for e in base_spec.income.pay_drop_events]))
    before = mc_to_dict(run_monte_carlo(base_spec))["affordability_mc"]
    after = mc_to_dict(run_monte_carlo(shocked))["affordability_mc"]
    assert before != after, (before, after)


def test_no_affordability_probability_is_pinned_at_zero_or_one():
    """A probability pinned at exactly 0 or 1 is a figure that can only regress
    in one direction — half a pin. The fixture's pay-drop severity is sized to
    keep all three strictly inside the interval."""
    block = json.loads(GOLDEN.read_text(encoding="utf-8"))["monte_carlo"]
    for key in ("prob_condo_cheapest", "prob_house_cheapest", "prob_rent_cheapest"):
        assert 0.0 < block[key] < 1.0, (key, block[key])
    for key in ("prob_condo_exceeds", "prob_house_exceeds", "prob_rent_exceeds"):
        assert 0.0 < block["affordability_mc"][key] < 1.0, (key, block["affordability_mc"][key])


# ---------------------------------------------------------------------------
# Regeneration — deliberately a command someone has to type
# ---------------------------------------------------------------------------

def _regenerate() -> None:
    import os
    os.chdir(REPO_ROOT)
    document = {
        "_about": [
            "The Monte Carlo block of tests/fixtures/uncertainty_surface.yaml, pinned.",
            "Board item 12: the shipped examples barely exercise uncertainty, so a",
            "change to the simulation could not be caught by running one. This is the",
            "surface it is caught on. Figures are ILLUSTRATIVE — they are what this",
            "fixture's invented inputs produce, and they are evidence about the engine,",
            "never about any housing market.",
            "",
            "Regenerate with:",
            f"  {REGEN_COMMAND}",
            "and state in the commit message WHICH channel moved and WHY. A golden",
            "regenerated without that sentence is the same thing as no golden.",
        ],
        "config": "tests/fixtures/uncertainty_surface.yaml",
        "monte_carlo": _monte_carlo_block(),
    }
    GOLDEN.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"wrote {GOLDEN.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    if "--regenerate" not in sys.argv[1:]:
        print(f"usage: {REGEN_COMMAND}", file=sys.stderr)
        raise SystemExit(2)
    _regenerate()
