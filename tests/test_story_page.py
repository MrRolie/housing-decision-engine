"""
Story-page tests: the STORY.md one-pager (src/hde/story_page.py).

Covers:
  - acts listed in order, one section per rendered act
  - the verdict sentence appears in the page
  - every image referenced by STORY.md exists on disk
  - prior geography/vintage cited when a prior is loaded
  - degradation mirrors render_decision_story (no MC -> no Act 3; no prior
    -> no Act 5, Act 4 falls back to the honest single-growth sentence)
  - CLI --story wiring
"""

import re
import sys
from pathlib import Path

import pytest

from hde.cli import main as cli_main
from hde.deterministic import compute_deterministic
from hde.market_scenario import load_scenario_prior
from hde.monte_carlo import run_monte_carlo
from hde.story_page import (
    REPORT_FILENAME,
    _act_sentences,
    STORY_FILENAME,
    generate_story_markdown,
    render_story_package,
)
from hde.config import single_path_run
from hde.story_plots import verdict_sentence

from tests.test_story_plots import GOLDEN_PRIOR, _spec

ACT_IMAGE_RE = re.compile(r"^!\[.*\]\((.+)\)$", re.MULTILINE)


def _render(tmp_path, with_prior=True, with_mc=True):
    spec = _spec(with_prior=with_prior)
    prior = (
        load_scenario_prior(GOLDEN_PRIOR, "MTL_RMR") if with_prior else None
    )
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec) if with_mc else None
    package = render_story_package(
        spec, det, mc, prior=prior, out_dir=tmp_path,
        command="uv run hde examples/x.yaml --story out",
    )
    story = package["story"].read_text(encoding="utf-8")
    return spec, det, mc, prior, package, story


class TestStoryMarkdown:
    def test_acts_listed_in_order(self, tmp_path):
        *_, story = _render(tmp_path)
        positions = [
            story.find(f"## Act — {title}") for title in (
                "The answer", "The race", "The uncertainty",
                "Your home's possible futures", "Why", "The market line",
            )
        ]
        assert all(p >= 0 for p in positions), "every act must be sectioned"
        assert positions == sorted(positions), "acts must appear in order"

    def test_verdict_sentence_present(self, tmp_path):
        spec, det, mc, _, _, story = _render(tmp_path)
        # the headline is the SAME sentence verdict_sentence builds from the
        # same inputs (det + mc + single-path flag) — one verdict, every surface
        assert verdict_sentence(
            det, spec.simulation.years, mc,
            num_sims=spec.simulation.num_sims, single_path=single_path_run(spec),
        ) in story

    def test_referenced_images_exist(self, tmp_path):
        *_, package, story = _render(tmp_path)
        refs = ACT_IMAGE_RE.findall(story)
        assert refs, "STORY.md must embed act images"
        for ref in refs:
            assert (tmp_path / ref).exists()
            assert (tmp_path / ref).stat().st_size > 0
        # one image per rendered act, in act order
        stems = [Path(r).stem for r in refs]
        assert stems == [
            "act1_the_answer", "act2_the_race", "act3_the_uncertainty",
            "act4_home_futures", "act5_demographic_signal", "act6_the_market_line",
        ]

    def test_regeneration_command_stamped_at_top(self, tmp_path):
        *_, story = _render(tmp_path)
        assert story.startswith("<!-- Regenerate with: uv run hde examples/x.yaml --story out")

    def test_prior_geography_and_vintage_cited(self, tmp_path):
        """Discriminating on the FILE's vintage — no literal can supply these tokens."""
        *_, story = _render(tmp_path)
        assert "MTL_RMR" in story
        assert "ISQ 2026 scenarios" in story          # isq_edition
        assert "2021 census" in story                 # census_year
        assert "constants as of 2026-07-21" in story  # constants_as_of
        assert "simulation year 1 = calendar 2026" in story
        assert "StatCan 98-10-0231-01" in story       # a pinned source, cited
        assert "UN WPP" not in story                  # the retired uncorroborated literal

    def test_report_written_and_nonempty(self, tmp_path):
        *_, package, _ = _render(tmp_path)
        report = package["report"]
        assert report.name == REPORT_FILENAME
        assert report.exists()
        assert "Total PV" in report.read_text(encoding="utf-8") or \
            report.stat().st_size > 0


class TestDegradation:
    def test_no_mc_skips_act3(self, tmp_path):
        *_, package, story = _render(tmp_path, with_mc=False)
        assert "act3_the_uncertainty" not in story
        assert "The uncertainty" not in story
        assert len(package["act images"]) == 5

    def test_no_prior_skips_act5_and_act4_is_honest(self, tmp_path):
        *_, package, story = _render(tmp_path, with_prior=False)
        assert "act5_demographic_signal" not in story
        assert "Why" not in story
        assert "No demographic prior loaded" in story
        assert len(package["act images"]) == 5

    def test_requires_deterministic_result(self, tmp_path):
        spec = _spec()
        with pytest.raises(ValueError):
            render_story_package(spec, None, None, out_dir=tmp_path)


class TestGenerateStoryMarkdownPure:
    def test_pure_assembler_takes_act_metadata(self, tmp_path):
        acts = [
            ("act1_the_answer", "The answer", "Sentence one."),
            ("act2_the_race", "The race", "Sentence two."),
        ]
        image_paths = {
            "act1_the_answer": tmp_path / "act1_the_answer.png",
            "act2_the_race": tmp_path / "act2_the_race.png",
        }
        md = generate_story_markdown(
            acts, image_paths, "cmd",
            headline="Renting wins by $1,000 over 8 years",
            subtitle="under your stated assumptions · 8-year horizon",
        )
        assert "## Act — The answer" in md
        assert "Sentence one." in md
        assert "![The answer](act1_the_answer.png)" in md


class TestCliStory:
    def _write_config(self, tmp_path: Path, with_prior: bool) -> str:
        market_block = (
            f"market_scenario:\n  path: {GOLDEN_PRIOR}\n  geography: MTL_RMR\n"
            if with_prior else ""
        )
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            f"""
years: 8
discount_rate: 0.03
economic:
  mode: real
{market_block}condo:
  monthly_fee: 450
  initial_value: 350000
  all_cash: true
house:
  initial_value: 400000
  value_growth_rate: 0.01
  annual_maintenance_rate: 0.012
  all_cash: true
rent:
  monthly_rent: 1900
  rent_escalation_rate: 0.03
simulation:
  num_sims: 50
  random_seed: 42
""",
            encoding="utf-8",
        )
        return str(cfg)

    def test_cli_story_flag_writes_package(self, tmp_path, monkeypatch, capsys):
        config = self._write_config(tmp_path, with_prior=True)
        story_dir = tmp_path / "story"
        monkeypatch.setattr(
            sys, "argv", ["hde", config, "--story", str(story_dir)],
        )
        assert cli_main() == 0
        out = capsys.readouterr().out
        story = (story_dir / STORY_FILENAME).read_text(encoding="utf-8")
        # all six acts, in order, images on disk, report present
        assert story.find("The answer") < story.find("The race") \
            < story.find("The uncertainty") \
            < story.find("Your home's possible futures") < story.find("Why") \
            < story.find("The market line")
        for ref in ACT_IMAGE_RE.findall(story):
            assert (story_dir / ref).exists()
        assert (story_dir / REPORT_FILENAME).exists()
        assert f"Story written: {story_dir / STORY_FILENAME}" in out

    def test_cli_story_without_prior_omits_act5(self, tmp_path, monkeypatch):
        config = self._write_config(tmp_path, with_prior=False)
        story_dir = tmp_path / "story"
        monkeypatch.setattr(
            sys, "argv", ["hde", config, "--story", str(story_dir)],
        )
        assert cli_main() == 0
        story = (story_dir / STORY_FILENAME).read_text(encoding="utf-8")
        assert "act5_demographic_signal" not in story

    def test_cli_story_with_no_deterministic_warns(
            self, tmp_path, monkeypatch, capsys):
        config = self._write_config(tmp_path, with_prior=False)
        monkeypatch.setattr(
            sys, "argv",
            ["hde", config, "--no-deterministic", "--story", str(tmp_path / "s")],
        )
        assert cli_main() == 0
        err = capsys.readouterr().err
        assert "--no-deterministic" in err


# --- Audit U1/U3: single-path stamp + assumptions footer ---

def _zero_vol_spec():
    from hde.models import (
        ComparisonSpec,
        CondoParams, EconomicParams, HouseParams, RentParams, SimulationParams,
    )
    return ComparisonSpec(
        simulation=SimulationParams(years=10, discount_rate=0.03, num_sims=25),
        economic=EconomicParams(mode="real"),
        condo=CondoParams(monthly_fee=450, initial_value=350_000, all_cash=True),
        house=HouseParams(initial_value=400_000, value_growth_rate=0.01,
                          annual_maintenance_rate=0.012, all_cash=True),
        rent=RentParams(monthly_rent=1_900, invested_down_payment=60_000),
    )


class TestSinglePathStampAndFooter:
    def test_zero_vol_story_is_stamped_and_skips_act3(self, tmp_path):
        spec = _zero_vol_spec()
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)  # MC ran, but every path is identical
        package = render_story_package(spec, det, mc, prior=None, out_dir=tmp_path)
        story = package["story"].read_text(encoding="utf-8")
        assert "single-path run: all uncertainty inputs off — not a forecast" in story
        assert "The uncertainty" not in story
        assert not (tmp_path / "act3_the_uncertainty.png").exists()

    def test_voled_story_not_stamped(self, tmp_path):
        *_, story = _render(tmp_path, with_prior=False)
        assert "single-path run" not in story
        assert "The uncertainty" in story

    def test_assumptions_footer_present(self, tmp_path):
        """U1: config-loaded spec (defaults_applied populated) → footer lists them."""
        from hde.config import load_config_dict

        spec = load_config_dict({
            "years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "all_cash": True},
            "rent": {"monthly_rent": 1_900},
        })
        det = compute_deterministic(spec)
        package = render_story_package(spec, det, None, prior=None, out_dir=tmp_path)
        story = package["story"].read_text(encoding="utf-8")
        assert "## Assumptions" in story
        assert "mode: real terms" in story
        assert "defaults applied:" in story

    def test_report_carries_assumption_header(self, tmp_path):
        *_, package, _ = _render(tmp_path, with_prior=False)
        report = package["report"].read_text(encoding="utf-8")
        assert report.startswith("Assumptions")


class TestActSentencesPinned:
    """G.5: act-2 and act-3 sentences are pinned (they carried no test)."""

    def test_no_crossover_race_sentence_names_the_equity_credit(self, tmp_path):
        import re
        spec, det, mc, prior, _, _ = _render(tmp_path)
        sentences = {stem: s for stem, _, s in _act_sentences(spec, det, mc, prior)}
        race = sentences["act2_the_race"]
        assert ("never flips" in race and "equity credit" in race) or "lead changes hands" in race
        assert re.search(r"In \d+% of [\d,]+ simulations, .* came out cheapest\.",
                         sentences["act3_the_uncertainty"])
