"""The engine-assembled READ-BACK block, and the two warning gaps beside it.

Eight reviewed answers in two days each dropped a line the engine had printed —
a `[warning]`, the `assistant-typed:` line, the decisiveness rule. The remedy is
mechanical: the engine assembles the lines an honest answer must carry, in one
order, as one block, so carrying them is a copy rather than a checklist.
"""

import sys

import pytest

from hde.break_even import prior_band_note, solve_break_even, solve_break_even_across
from hde.cli import main as cli_main
from hde.config import all_warnings, affordability_warnings, coherence_warnings, load_config_dict
from hde.deterministic import compute_deterministic
from hde.market_scenario import load_scenario_prior
from hde.models import Verdict, compute_verdict
from hde.reporting import format_text_report
from hde.serialization import READ_BACK_HEADER, format_assumptions, read_back_lines
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
    # Beside --sweep the CLI re-solves the threshold at every sweep point of a
    # DIFFERENT key; the read-back has to carry those re-solutions too.
    if break_evens and sweeps and sweep[0] != break_even:
        break_evens[0]["across"] = [
            solve_break_even_across(cfg, break_even, None, None, sweep[0], sweeps[0]["values"])
        ]
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
            index_of("defaults applied:"),
            index_of("decisiveness:"),
            index_of("house financing:"),
            index_of("Year-1 cash"),
            index_of("house other costs:"),
            index_of("Affordability (threshold:"),
            index_of("break-even rent.monthly_rent:"),
            index_of("break-even rent.monthly_rent at years="),
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
        block = [line for line in lines
                 if line.startswith(("Affordability", "House: max", "Rent: max"))]
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


class TestTheThreeLinesTheAnswerDropped:
    """Round-9 review of a real answer: the block named neither of the two
    largest engine-set numbers, said nothing about year-1 cash, and carried the
    base threshold sentence alone beside a sweep — so the answer reduced a
    years bracket to "near $300k"."""

    def test_the_defaults_line_names_the_engine_set_numbers_with_their_citations(self):
        cfg = _rich()
        cfg.pop("discount_rate")  # the engine's own 3% real default applies
        lines, _ = _assembled(cfg)
        line = next(l for l in lines if l.startswith("defaults applied:"))
        # the echo's OWN line, verbatim — one builder, not a second formatter
        assert line in format_assumptions(load_config_dict(cfg))
        assert "simulation.discount_rate=3.0%" in line
        assert "house.selling_cost_rate=5.0% [WOWA 2026]" in line

    def test_year_1_cash_rides_the_block_in_dollars_per_month(self):
        lines, _ = _assembled(_rich())
        assert "Year-1 cash (undiscounted; PV totals above credit equity at sale)" in lines
        house = next(l for l in lines if l.startswith("House: $"))
        assert "/yr (" in house and "/mo)" in house
        assert "principal repaid" in house and "unrecoverable" in house
        assert any(l.startswith("Rent: $") for l in lines)

    def test_the_cash_lines_are_the_reports_own_lines(self):
        """One builder: the text report prints these lines indented under the
        same header, so the two surfaces cannot drift."""
        cfg = _rich()
        spec = load_config_dict(cfg)
        det = compute_deterministic(spec)
        report = format_text_report(det, None, spec.simulation, spec.economic, spec)
        lines, _ = _assembled(cfg)
        cash = [l for l in lines if l.startswith(("Year-1 cash", "House: $", "Rent: $"))]
        assert len(cash) == 3
        assert cash[0] in report
        for line in cash[1:]:
            assert f"  {line}" in report

    def test_the_across_re_solutions_ride_the_block_one_line_each(self):
        lines, _ = _assembled(_rich(), break_even="rent.monthly_rent",
                              sweep=("years", [5, 10]))
        across = [l for l in lines if l.startswith("break-even rent.monthly_rent at years=")]
        assert len(across) == 2, lines
        assert across[0].startswith("break-even rent.monthly_rent at years=5: ")
        assert across[1].startswith("break-even rent.monthly_rent at years=10: ")
        assert all("cheaper" in line for line in across)

    def test_an_across_line_carries_the_affordability_it_implies(self):
        """A reviewed answer called a price a "safe-buy ceiling" while the
        across row it came from sat above the 39% GDS cap."""
        lines, _ = _assembled(_rich(), break_even="house.initial_value",
                              sweep=("years", [5, 10]))
        across = [l for l in lines if l.startswith("break-even house.initial_value at years=")]
        assert across
        assert all("affordability (highest cost/income ratio" in line for line in across), across
        assert all("at the crossing" in line and "at the band's high edge" in line
                   for line in across)
        assert all("yr(s) over" in line for line in across)

    def test_the_purchase_costs_line_rides_the_block(self):
        cfg = _rich()
        cfg["house"]["land_transfer_tax"] = "auto"
        lines, _ = _assembled(cfg)
        line = next(l for l in lines if l.startswith("house purchase costs:"))
        assert line in format_assumptions(load_config_dict(cfg))
        assert "transfer tax" in line or "welcome tax" in line
        # it sits with the financing line it reconciles against
        assert lines.index(line) > next(
            i for i, l in enumerate(lines) if l.startswith("house financing:"))


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

    def test_the_block_is_byte_identical_with_and_without_the_flag(
            self, tmp_path, monkeypatch, capsys):
        """`--read-back` is the same block the run already prints — an answer
        assembled from either surface says the same thing."""
        config = _yaml(tmp_path, _rich())
        argv = ["hde", config, "--no-monte-carlo", "--sweep", "years=5,10",
                "--break-even", "rent.monthly_rent"]
        monkeypatch.setattr(sys, "argv", argv)
        assert cli_main() == 0
        tail = capsys.readouterr().out.split(READ_BACK_HEADER, 1)[1]
        monkeypatch.setattr(sys, "argv", argv + ["--read-back"])
        assert cli_main() == 0
        alone = capsys.readouterr().out.split(READ_BACK_HEADER, 1)[1]
        assert tail.strip("\n") == alone.strip("\n")

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


class TestPriorWithoutMonteCarlo:
    """A config carrying a `market_scenario` prior run with `--no-monte-carlo`
    shows the deterministic line alone: the prior's drift enters the Monte
    Carlo only, so the run says so rather than let the prior's presence in the
    echo read as its presence in the numbers (2026-09-04)."""

    LINE = ("market_scenario prior acts only in Monte Carlo — this run shows the "
            "deterministic line alone (the prior's drift is not in it)")

    def _raw(self, prior=True):
        raw = {
            "years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0, "all_cash": True},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 120_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }
        if prior:
            raw["market_scenario"] = {"path": PRIOR_PATH, "geography": "MTL_RMR"}
        return raw

    def test_it_warns_on_stderr_and_reaches_the_read_back(self, tmp_path, monkeypatch, capsys):
        config = _yaml(tmp_path, self._raw())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--no-monte-carlo", "--read-back"])
        assert cli_main() == 0
        captured = capsys.readouterr()
        assert f"[warning] {self.LINE}" in captured.err.splitlines()
        assert f"[warning] {self.LINE}" in captured.out.splitlines()

    def test_it_rides_json_warnings_beside_a_sweep(self, tmp_path, monkeypatch, capsys):
        import json

        config = _yaml(tmp_path, self._raw())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--no-monte-carlo", "--json",
                                          "--sweep", "years=5,10"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["warnings"].count(self.LINE) == 1

    def test_a_monte_carlo_run_is_quiet(self, tmp_path, monkeypatch, capsys):
        config = _yaml(tmp_path, self._raw())
        monkeypatch.setattr(sys, "argv", ["hde", config, "--json"])
        assert cli_main() == 0
        assert self.LINE not in capsys.readouterr().err

    def test_without_a_prior_it_is_quiet(self, tmp_path, monkeypatch, capsys):
        config = _yaml(tmp_path, self._raw(prior=False))
        monkeypatch.setattr(sys, "argv", ["hde", config, "--no-monte-carlo"])
        assert cli_main() == 0
        assert self.LINE not in capsys.readouterr().err


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

    def test_a_band_edge_on_the_cliff_is_named_as_one(self):
        """Round-9 review: the crossing was smooth but the tie band's UPPER
        edge landed exactly on the 20%-down line — the house PV jumped across
        it, so "band = 5% of the cheaper option's PV" was false at that edge
        and nothing fired. Both edges are probed, and the note says which."""
        result = solve_break_even(self._cfg(monthly_rent=2_200), "house.initial_value")
        entry = result["break_evens"][0]
        assert entry["value"] == pytest.approx(622_820, abs=2_000)
        assert entry["tie_band"][1] == pytest.approx(625_000, abs=1)
        note = result["note"]
        assert "tie band's upper edge at 625,000" in note, note
        assert "mortgage-insurance cliff" in note
        assert "not a range of near-ties" in note

    def test_a_band_edge_clear_of_the_line_stays_quiet(self):
        result = solve_break_even(self._cfg(monthly_rent=2_050), "house.initial_value")
        assert "cliff" not in (result.get("note") or "")

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


class TestARealRateTypedIntoNominalMode:
    """Round-9 review: a config typed `discount_rate: 0.03` under
    `mode: nominal`, so nominal cash flows were discounted at a real rate.
    Every PV on both sides was overstated and the 10-year verdict's sign
    reversed once corrected."""

    def _cfg(self, discount_rate=None, mode="nominal"):
        cfg = {
            "years": 10,
            "economic": {"mode": mode, "inflation_rate": 0.021},
            "house": {"initial_value": 500_000, "value_growth_rate": 0.01,
                      "all_cash": True},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.01,
                     "invested_down_payment": 500_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }
        if discount_rate is not None:
            cfg["discount_rate"] = discount_rate
        return cfg

    def _fired(self, cfg):
        return [w for w in coherence_warnings(load_config_dict(cfg))
                if "in nominal mode is below" in w]

    def test_a_real_looking_rate_names_both_rates_and_the_direction(self):
        fired = self._fired(self._cfg(0.03))
        assert len(fired) == 1, fired
        warning = fired[0]
        assert "discount_rate=3.0%" in warning          # what was typed
        assert "5.2%" in warning                        # what the engine composes
        assert "3.0% real" in warning and "2.1%" in warning
        assert "overstates every PV" in warning
        assert "omit discount_rate or state the nominal rate you mean" in warning

    def test_a_nominal_rate_is_quiet(self):
        assert not self._fired(self._cfg(0.052))

    def test_an_omitted_discount_rate_is_quiet(self):
        """Omitting it is the skill's default: the engine composes it itself."""
        assert not self._fired(self._cfg())

    def test_real_mode_is_quiet(self):
        assert not self._fired(self._cfg(0.03, mode="real"))

    def test_it_reaches_the_read_back_block(self, tmp_path, monkeypatch, capsys):
        config = _yaml(tmp_path, self._cfg(0.03))
        monkeypatch.setattr(sys, "argv", ["hde", config, "--no-monte-carlo", "--read-back"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert any(line.startswith("[warning] discount_rate=3.0% typed in nominal mode")
                   for line in out.splitlines()), out


class TestNextStepUnderAPrior:
    """A coin flip under a demographic prior has one answer that resolves it:
    `--break-even <owned>.value_growth_rate`, whose note places the prior's
    drift against the tie band. One round ran it; the next shipped the coin
    flip without it — so the block says what to run."""

    LINE = ("next: not decisive under the prior — run --break-even "
            "house.value_growth_rate to see where the prior's drift sits "
            "against the tie band")

    def _raw(self, prior=True):
        raw = {
            "years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0, "all_cash": True},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 120_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }
        if prior:
            raw["market_scenario"] = {"path": PRIOR_PATH, "geography": "MTL_RMR"}
        return raw

    def _verdict(self, *, rule="mc_floor", decisive=False):
        return Verdict(best="rent", runner_up="house", margin_pv=1_000.0,
                       margin_frac=0.002, monthly_equivalent=8.0, prob_best=0.42,
                       decisive=decisive, rule=rule,
                       reason="P(rent cheapest) = 42% < 65% floor [hde verdict rule]")

    def _lines(self, *, prior=True, verdict_kw=None, break_evens=()):
        raw = self._raw(prior)
        spec = load_config_dict(raw)
        det = compute_deterministic(spec)
        loaded = load_scenario_prior(PRIOR_PATH, "MTL_RMR") if prior else None
        return read_back_lines(spec, verdict=self._verdict(**(verdict_kw or {})),
                               det=det, prior=loaded, break_evens=break_evens)

    def test_a_coin_flip_under_the_prior_names_the_run_that_resolves_it(self):
        lines = self._lines()
        assert [l for l in lines if l.startswith("next:")] == [self.LINE]
        assert lines[-1] == self.LINE  # last: it is what to do after reading

    def test_a_decisive_verdict_says_nothing(self):
        assert not [l for l in self._lines(verdict_kw={"decisive": True})
                    if l.startswith("next:")]

    def test_without_a_prior_it_says_nothing(self):
        assert not [l for l in self._lines(prior=False) if l.startswith("next:")]

    def test_the_deterministic_rule_says_nothing(self):
        """`--no-monte-carlo` falls back to the margin band; there is no Monte
        Carlo verdict to resolve."""
        assert not [l for l in self._lines(verdict_kw={"rule": "margin_band"})
                    if l.startswith("next:")]

    def test_the_run_that_is_that_break_even_says_nothing(self):
        prior = load_scenario_prior(PRIOR_PATH, "MTL_RMR")
        solved = solve_break_even(self._raw(), "house.value_growth_rate", prior=prior)
        assert not [l for l in self._lines(break_evens=[solved]) if l.startswith("next:")]
