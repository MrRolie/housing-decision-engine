"""The engine-assembled READ-BACK block, and the two warning gaps beside it.

Eight reviewed answers in two days each dropped a line the engine had printed —
a `[warning]`, the `assistant-typed:` line, the decisiveness rule. The remedy is
mechanical: the engine assembles the lines an honest answer must carry, in one
order, as one block, so carrying them is a copy rather than a checklist.
"""

import sys

import pytest

from hde.break_even import prior_band_note, solve_break_even
from hde.cli import main as cli_main
from hde.config import all_warnings, affordability_warnings, coherence_warnings, load_config_dict
from hde.deterministic import compute_deterministic
from hde.market_scenario import load_scenario_prior
from hde.models import compute_verdict
from hde.serialization import read_back_lines
from hde.sweep import flip_lines, run_sweep

PRIOR_PATH = "tests/fixtures/scenario_prior_golden.json"


def _rich(**over):
    """A run that carries every read-back class at once: warnings (an insured
    mortgage under the 20% line), a `sources:` block, an income block, and two
    priced options so a threshold and a sweep both run."""
    cfg = {
        "years": 10,
        "discount_rate": 0.03,
        "province": "QC",
        "house": {
            "initial_value": 500_000, "value_growth_rate": 0.0,
            "down_payment": 75_000, "mortgage_rate": 0.04, "mortgage_term_years": 25,
            "mortgage_insurance": "auto", "purchase_costs": 6_000,
            "other_recurring_costs": [
                {"name": "property_tax", "annual_amount": 3_400, "escalation_rate": 0.0}],
        },
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                 "invested_down_payment": 75_000, "investment_return_rate": 0.03},
        "income": {"annual_income": 70_000},
        "simulation": {"num_sims": 200, "random_seed": 42, "investment_return_vol": 0.10},
        "sources": {"years": "user", "rent.monthly_rent": "user",
                    "house.initial_value": "assistant"},
    }
    cfg.update(over)
    return cfg


def _yaml(tmp_path, cfg) -> str:
    import yaml

    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return str(path)


def _assembled(cfg, *, break_even=None, sweep=None):
    """The read-back for one config, assembled the way the CLI assembles it."""
    spec = load_config_dict(cfg)
    det = compute_deterministic(spec)
    warnings = all_warnings(spec) + affordability_warnings(det)
    verdict = compute_verdict(det, None, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    break_evens = [solve_break_even(cfg, break_even)] if break_even else []
    sweeps = [run_sweep(cfg, *sweep, monte_carlo=False)] if sweep else []
    return read_back_lines(spec, warnings=warnings, verdict=verdict, det=det,
                           break_evens=break_evens, sweeps=sweeps), warnings


class TestReadBackContent:
    def test_every_class_appears_once_in_the_stated_order(self):
        lines, warnings = _assembled(
            _rich(), break_even="rent.monthly_rent", sweep=("years", [5, 10]))
        assert lines[:len(warnings)] == [f"[warning] {w}" for w in warnings]
        assert warnings, "the fixture is meant to carry warnings"

        def index_of(*prefixes: str) -> int:
            return next(i for i, line in enumerate(lines) if line.startswith(prefixes))

        order = [
            index_of("assistant-typed:"),
            index_of("unattributed:"),
            index_of("decisiveness:"),
            index_of("house financing:"),
            index_of("house other costs:"),
            index_of("Affordability (threshold:"),
            index_of("break-even rent.monthly_rent:"),
            index_of("flip:", "no flip:"),
        ]
        assert order == sorted(order), lines
        assert order[0] >= len(warnings)

    def test_user_stated_line_never_rides_the_read_back(self):
        lines, _ = _assembled(_rich())
        assert not any(line.startswith("user-stated:") for line in lines)
        assert any(line.startswith("assistant-typed:") for line in lines)

    def test_without_a_sources_block_the_read_back_says_so(self):
        cfg = _rich()
        cfg.pop("sources")
        lines, _ = _assembled(cfg)
        assert any(line.startswith("sources: none declared") for line in lines)
        assert not any(line.startswith(("assistant-typed:", "unattributed:")) for line in lines)

    def test_affordability_line_names_the_ratio_and_the_breach_years(self):
        lines, _ = _assembled(_rich())
        block = [line for line in lines if line.startswith(("Affordability", "House:", "Rent:"))]
        assert block and block[0].startswith("Affordability (threshold:")
        assert "CMHC caps GDS at 39%, TDS at 44%" in block[0]
        assert any("max ratio" in line and "years exceeding" in line for line in block)

    def test_break_even_carries_the_sentence_and_the_note(self):
        cfg = _rich()
        cfg["house"]["initial_value"] = 500_000
        lines, _ = _assembled(cfg, break_even="house.initial_value")
        assert any("too close to call between" in line for line in lines)
        # the price-scan coherence note (dollar-stated tax + purchase costs)
        assert any("held fixed in dollars while the price moves" in line for line in lines)

    def test_sweep_flip_lines_ride_the_block(self):
        lines, _ = _assembled(_rich(), sweep=("years", [5, 10]))
        assert any(line.startswith(("flip:", "no flip:")) for line in lines)


class TestReadBackCli:
    def test_text_block_is_headed_and_last(self, tmp_path, monkeypatch, capsys):
        config = _yaml(tmp_path, _rich())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--sweep", "years=5,10",
                                          "--break-even", "rent.monthly_rent"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        head = "READ-BACK — carry these lines into any answer, verbatim:"
        assert head in out
        block = out.split(head, 1)[1].strip().splitlines()
        assert block and block[0].startswith("[warning] ")
        # nothing else follows the block
        assert out.rstrip().endswith(block[-1])
        # and the report itself still printed
        assert "Assumptions" in out.split(head, 1)[0]

    def test_read_back_flag_prints_only_the_block(self, tmp_path, monkeypatch, capsys):
        config = _yaml(tmp_path, _rich())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--read-back"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert out.startswith("READ-BACK — carry these lines into any answer, verbatim:")
        assert "Assumptions" not in out and "total PV" not in out
        assert "[warning] " in out

    def test_read_back_flag_keeps_the_runs_exit_code(self, tmp_path, monkeypatch, capsys):
        cfg = _rich()
        cfg["house"]["value_growth_rat"] = 0.02  # typo → the loader refuses
        config = _yaml(tmp_path, cfg)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--read-back"])
        assert cli_main() == 1
        assert "READ-BACK" not in capsys.readouterr().out

    def test_json_carries_read_back_and_stdout_stays_one_document(
            self, tmp_path, monkeypatch, capsys):
        import json

        config = _yaml(tmp_path, _rich())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--json",
                                          "--break-even", "rent.monthly_rent"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        doc = json.loads(out)  # the document ALONE — no text block appended
        read_back = doc["assumptions"]["read_back"]
        assert isinstance(read_back, list) and read_back
        assert read_back[0].startswith("[warning] ")
        assert any(line.startswith("decisiveness:") for line in read_back)
        assert any("too close to call between" in line for line in read_back)


class TestOneSidedUncertaintyIsSymmetric:
    """Round-8 review: the one-sided warnings fired only when the RENTER was the
    point mass. A single-path owned side against a stochastic renter measured
    the renter's dispersion alone and said nothing."""

    def _cfg(self, **over):
        cfg = {
            "years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0, "all_cash": True},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 120_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 100, "random_seed": 42, "investment_return_vol": 0.10},
        }
        cfg.update(over)
        return cfg

    def test_renter_only_dispersion_warns_and_names_the_renter(self):
        warns = coherence_warnings(load_config_dict(self._cfg()))
        one_sided = [w for w in warns if w.startswith("one-sided uncertainty")]
        assert one_sided, warns
        assert "renter" in one_sided[0]
        assert "OVERconfident" in one_sided[0]
        assert "simulation.investment_return_vol" in one_sided[0]

    def test_owned_side_dispersion_alone_warns_the_other_way(self):
        cfg = self._cfg(simulation={"num_sims": 100, "random_seed": 42,
                                    "house_maintenance_vol": 0.20})
        cfg["house"]["annual_maintenance_rate"] = 0.01
        one_sided = [w for w in coherence_warnings(load_config_dict(cfg))
                     if w.startswith("one-sided uncertainty")]
        assert one_sided
        assert "house_maintenance_vol" in one_sided[0] and "OVERconfident" in one_sided[0]

    def test_both_sides_stochastic_is_quiet(self):
        cfg = self._cfg()
        cfg["house"]["price_shock"] = {"annual_hazard": 0.02}
        assert not [w for w in coherence_warnings(load_config_dict(cfg))
                    if w.startswith("one-sided uncertainty")]

    def test_a_specific_warning_is_not_repeated_by_the_general_one(self):
        """`asymmetric tails` and the prior warning each carry their own fix;
        the symmetric check stands down where one of them already fired, so the
        same diagnosis is never printed twice."""
        cfg = self._cfg(simulation={"num_sims": 100, "random_seed": 42})
        cfg["house"]["price_shock"] = {"annual_hazard": 0.02}
        warns = coherence_warnings(load_config_dict(cfg))
        family = [w for w in warns
                  if w.startswith(("asymmetric tails", "one-sided uncertainty"))]
        assert len(family) == 1 and family[0].startswith("asymmetric tails"), family

    def test_neither_side_stochastic_is_quiet(self):
        cfg = self._cfg(simulation={"num_sims": 100, "random_seed": 42})
        assert not [w for w in coherence_warnings(load_config_dict(cfg))
                    if w.startswith("one-sided uncertainty")]


class TestPriorAgainstTheTieBand:
    """`--break-even <owned>.value_growth_rate` on a config with a prior: three
    reviewed answers assembled this comparison by hand."""

    def _entry(self, band):
        return {"value": 0.0123, "tie_band": list(band),
                "cheaper_below": "rent", "cheaper_above": "house"}

    def test_inside_the_band_says_the_prior_does_not_settle_it(self):
        note = prior_band_note("house.value_growth_rate", {2030: 0.0136},
                               [self._entry((0.0097, 0.0149))])
        assert "+1.36%/yr (2030 band)" in note
        assert "INSIDE the tie band 0.97%–1.49%" in note
        assert "does not settle it" in note

    def test_below_the_band_points_at_the_cheaper_below_option(self):
        note = prior_band_note("house.value_growth_rate", {2030: 0.0026},
                               [self._entry((0.0097, 0.0149))])
        assert "BELOW the tie band" in note and "rent" in note

    def test_above_the_band_points_at_the_cheaper_above_option(self):
        note = prior_band_note("house.value_growth_rate", {2030: 0.02},
                               [self._entry((0.0097, 0.0149))])
        assert "ABOVE the tie band" in note and "house" in note

    def test_bands_on_the_same_side_collapse_to_one_sentence(self):
        note = prior_band_note("house.value_growth_rate",
                               {2030: 0.0026, 2035: 0.0025, 2040: 0.0009},
                               [self._entry((0.0097, 0.0149))])
        assert note.count("BELOW the tie band") == 1
        assert "+0.09%…+0.26%/yr (2030, 2035, 2040 bands)" in note

    def test_bands_on_different_sides_get_their_own_sentence(self):
        note = prior_band_note("house.value_growth_rate", {2030: 0.02, 2035: 0.0026},
                               [self._entry((0.0097, 0.0149))])
        assert "ABOVE the tie band" in note and "BELOW the tie band" in note
        assert "(2030 band)" in note and "(2035 band)" in note

    def test_an_edge_outside_the_bracket_is_said_not_guessed(self):
        note = prior_band_note("house.value_growth_rate", {2030: 0.02},
                               [self._entry((0.0097, None))])
        assert "outside the searched bracket" in note

    def test_the_note_reaches_a_real_break_even_run(self):
        raw = {
            "years": 10, "discount_rate": 0.03,
            "market_scenario": {"path": PRIOR_PATH, "geography": "MTL_RMR"},
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0, "all_cash": True},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 120_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }
        prior = load_scenario_prior(PRIOR_PATH, "MTL_RMR")
        result = solve_break_even(raw, "house.value_growth_rate", prior=prior)
        assert "tie band" in result["note"]
        # a 10-year run touches three bands, all on the same side of the band:
        # one sentence, not three
        assert "(2030, 2035, 2040 bands)" in result["note"]
        # and the drift is described as what the Monte Carlo does with it
        assert "added to value_growth_rate" in result["note"]


class TestMortgageInsuranceCliff:
    """A reviewed answer read a $651,163 'crossing' as a cost crossing; it was
    the 20%-down line — the premium switching on, not costs meeting."""

    def _cfg(self, monthly_rent=2_300):
        return {
            "years": 10, "discount_rate": 0.03, "province": "QC",
            "house": {"initial_value": 600_000, "value_growth_rate": 0.0,
                      "cash_available": 130_000, "purchase_costs": 5_000,
                      "mortgage_rate": 0.04, "mortgage_term_years": 25,
                      "mortgage_insurance": "auto"},
            "rent": {"monthly_rent": monthly_rent, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 125_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }

    def test_a_crossing_on_the_cliff_is_named_as_one(self):
        result = solve_break_even(self._cfg(), "house.initial_value")
        crossing = result["break_evens"][0]["value"]
        assert crossing == pytest.approx(625_000, abs=50)
        assert "mortgage-insurance cliff" in result["note"]
        assert "not a smooth cost crossing" in result["note"]

    def test_an_insured_mortgage_on_both_sides_is_not_a_step(self):
        """The loan-to-value moves with every price, so a regime comparison that
        read it would report a step at every crossing — a false claim of exactly
        the kind this note exists to prevent. Only the TIER counts."""
        raw = {
            "years": 10, "discount_rate": 0.03, "province": "QC",
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0,
                      "down_payment": 75_000, "mortgage_rate": 0.04,
                      "mortgage_term_years": 25, "mortgage_insurance": "auto",
                      "purchase_costs": 6_000},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 75_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }
        note = solve_break_even(raw, "house.initial_value").get("note") or ""
        assert "cliff" not in note and "tier change" not in note

    def test_a_smooth_crossing_carries_no_cliff_note(self):
        raw = {
            "years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0, "all_cash": True},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 120_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }
        result = solve_break_even(raw, "rent.monthly_rent")
        assert "cliff" not in (result.get("note") or "")


class TestSweepCarriesTheMonteCarloMajority:
    """A row's `decisive` flag keys to the DETERMINISTIC best by design, so a
    row can read best=rent / decisive=false / prob_best=0.34 while the Monte
    Carlo majority favours house. The fields make that machine-visible."""

    def _raw(self):
        return {
            "years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0, "all_cash": True,
                      "price_shock": {"annual_hazard": 0.05, "severity_mean": 0.2,
                                      "severity_vol": 0.1}},
            "rent": {"monthly_rent": 2_100, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 120_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 400, "random_seed": 42, "investment_return_vol": 0.10},
        }

    def test_rows_carry_the_monte_carlo_majority_and_its_probability(self):
        result = run_sweep(self._raw(), "years", [5, 10])
        for row in result["rows"]:
            assert row["mc_best"] in ("condo", "house", "rent")
            assert 0.0 <= row["mc_prob_best"] <= 1.0
            assert row["mc_prob_best"] >= (row["prob_best"] or 0.0)

    def test_majority_flips_are_tracked_and_only_shown_when_they_differ(self):
        rows = [
            {"value": 5, "best": "rent", "mc_mean_best": "rent", "mc_best": "rent"},
            {"value": 10, "best": "rent", "mc_mean_best": "house", "mc_best": "house"},
        ]
        result = {"key": "years", "rows": rows, "flips": [],
                  "mc_mean_flips": [{"from_value": 5, "from_best": "rent",
                                     "to_value": 10, "to_best": "house"}],
                  "mc_majority_flips": [{"from_value": 5, "from_best": "rent",
                                         "to_value": 10, "to_best": "house"}]}
        lines = flip_lines(result)
        assert any(line.startswith("no flip:") for line in lines)
        assert any(line.startswith("mean flip:") for line in lines)
        assert any(line.startswith("majority flip:") for line in lines)
        # identical to the deterministic flips → nothing new to say
        same = dict(result, flips=result["mc_majority_flips"])
        assert not any(line.startswith("majority flip:") for line in flip_lines(same))
