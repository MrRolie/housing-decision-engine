"""
STORY.md one-pager: the text companion to the six-act story plots.

`render_story_package` writes three things into a directory:
  1. the six-act plots (via ``render_decision_story`` — degradation rules
      identical: no MC -> no Act 3, no prior -> no Act 5, rent-vs-owned
      missing -> no Act 6, Act 4 falls back to the honest single-growth
      line; a zero-uncertainty MC run degrades like no-MC and is stamped
      'not a forecast');
  2. the text report (``report.txt``);
  3. ``STORY.md`` — a one-pager embedding the act images in order, one
     narrative sentence per act, every sentence derived from the same pure
     helpers the plots use (``verdict_sentence``, ``find_crossovers``, the
     prior's geography/vintage). No number is invented here.

The regeneration command is stamped at the top of STORY.md so the living
showcase in ``docs/story/`` stays regenerable.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import single_path_run
from .market_scenario import LoadedScenarioPrior
from .models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    ComparisonSpec,
)
from .reporting import format_assumptions, format_text_report
from .story_plots import (
    OPTION_DISPLAY,
    PRIOR_SOURCE_LINE,
    _cumulative_cost_curves,
    _verdict_subtitle,
    find_crossovers,
    market_line_sentence,
    render_decision_story,
    verdict_sentence,
)

REPORT_FILENAME = "report.txt"
STORY_FILENAME = "STORY.md"


def _act_sentences(
    spec: ComparisonSpec,
    det: ComparisonDeterministicResult,
    mc: Optional[ComparisonMonteCarloResult],
    prior: Optional[LoadedScenarioPrior],
) -> List[Tuple[str, str, str]]:
    """
    One (stem, act title, narrative sentence) per act that WILL render —
    the degradation conditions mirror ``render_decision_story`` exactly.
    """
    years = spec.simulation.years
    acts: List[Tuple[str, str, str]] = []

    acts.append((
        "act1_the_answer", "The answer",
        verdict_sentence(
            det, years, mc,
            num_sims=spec.simulation.num_sims, single_path=single_path_run(spec),
        ),
    ))

    paid_curves = {
        k: c["paid"] for k, c in _cumulative_cost_curves(spec).items()
    }
    crossovers = find_crossovers(paid_curves)
    if crossovers:
        year, _from, to = crossovers[0]
        race_sentence = (
            f"The lead changes hands in year {year}, when "
            f"{OPTION_DISPLAY[to].lower()} overtakes "
            f"{OPTION_DISPLAY[_from].lower()} — cheapest early is not "
            f"cheapest at the end."
        )
    else:
        leader = min(paid_curves, key=lambda k: paid_curves[k][-1])
        race_sentence = (
            f"{OPTION_DISPLAY[leader]} costs less out of pocket every single "
            f"year — the ranking never flips."
        )
    acts.append(("act2_the_race", "The race", race_sentence))

    mc_has_options = mc is not None and not single_path_run(spec) and any(
        getattr(mc, k) is not None for k in ("rent", "condo", "house")
    )
    if mc_has_options:
        probs = [
            (key, getattr(mc, f"prob_{key}_cheapest"))
            for key in ("rent", "condo", "house")
            if getattr(mc, f"prob_{key}_cheapest") is not None
        ]
        best_key, best_prob = max(probs, key=lambda kv: kv[1])
        acts.append((
            "act3_the_uncertainty", "The uncertainty",
            f"In {best_prob:.0%} of {spec.simulation.num_sims:,} simulations, "
            f"{OPTION_DISPLAY[best_key].lower()} came out cheapest.",
        ))

    if spec.house is not None or spec.condo is not None:
        dwelling_key = "house" if spec.house is not None else "condo"
        params = getattr(spec, dwelling_key)
        if prior is not None:
            futures_sentence = (
                f"Under {prior.geography} demographic demand scenarios, the "
                f"home's value fans out around your "
                f"{params.value_growth_rate:.1%} growth assumption."
            )
        else:
            futures_sentence = (
                "No demographic prior loaded — a single honest growth line, "
                "no false confidence."
            )
        acts.append(("act4_home_futures", "Your home's possible futures",
                     futures_sentence))

    if prior is not None:
        acts.append((
            "act5_demographic_signal", "Why",
            f"The demographic signal itself: projected price drift from "
            f"household demand in {prior.geography}{_vintage_clause(prior)}.",
        ))

    if spec.rent is not None and (spec.house is not None or spec.condo is not None):
        acts.append((
            "act6_the_market_line", "The market line",
            market_line_sentence(spec, det),
        ))

    return acts


def _vintage_clause(prior: LoadedScenarioPrior) -> str:
    vintage = prior.data_vintage
    parts = []
    if vintage.get("isq_edition"):
        parts.append(f"ISQ {vintage['isq_edition']} scenarios")
    if vintage.get("census_year"):
        parts.append(f"{vintage['census_year']} census")
    if not parts:
        return ""
    return " (" + ", ".join(parts) + ")"


def generate_story_markdown(
    acts: List[Tuple[str, str, str]],
    image_paths: Dict[str, Path],
    command: str,
    headline: str,
    subtitle: str,
    prior_line: Optional[str] = None,
    assumption_lines: Optional[List[str]] = None,
    single_path_note: bool = False,
) -> str:
    """Pure assembler: build STORY.md text from rendered act metadata."""
    lines: List[str] = []
    lines.append(f"<!-- Regenerate with: {command} (from the repo root) -->")
    lines.append("")
    lines.append("# The story of this housing decision")
    lines.append("")
    lines.append(f"**{headline}** — {subtitle}.")
    lines.append("")
    if single_path_note:
        # Audit U3: stamp zero-uncertainty runs so the single line is never
        # mistaken for a forecast.
        lines.append("> single-path run: all uncertainty inputs off — not a forecast.")
        lines.append("")
    if prior_line:
        lines.append(prior_line)
        lines.append("")
    for stem, title, sentence in acts:
        image = image_paths[stem]
        lines.append(f"## Act — {title}")
        lines.append("")
        lines.append(f"{sentence}")
        lines.append("")
        lines.append(f"![{title}]({image.name})")
        lines.append("")
    lines.append(f"Full text report: [{REPORT_FILENAME}]({REPORT_FILENAME})")
    lines.append("")
    if assumption_lines:
        # Audit U1: assumption echo footer, same lines the text report header
        # and the define_scenario MCP response carry.
        lines.append("---")
        lines.append("")
        lines.append("## Assumptions")
        lines.append("")
        lines.extend(f"- {line}" for line in assumption_lines)
        lines.append("")
    return "\n".join(lines)


def render_story_package(
    spec: ComparisonSpec,
    deterministic_result: ComparisonDeterministicResult,
    mc_result: Optional[ComparisonMonteCarloResult],
    prior: Optional[LoadedScenarioPrior] = None,
    out_dir: str | Path = "story",
    command: str = "uv run hde <config.yaml> --story <DIR>",
    fmt: str = "png",
) -> Dict[str, Path]:
    """
    Write the full story package into ``out_dir``: the six-act plots, the
    text report (``report.txt``), and the STORY.md one-pager.

    Returns a mapping {name: path} with keys "act images" (list), "report",
    and "story".
    """
    if deterministic_result is None:
        raise ValueError("render_story_package requires deterministic results")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    saved_images = render_decision_story(
        spec, deterministic_result, mc_result, prior=prior,
        out_dir=out_path, fmt=fmt,
    )
    image_by_stem = {p.stem: p for p in saved_images}

    acts = _act_sentences(spec, deterministic_result, mc_result, prior)
    missing = [stem for stem, _, _ in acts if stem not in image_by_stem]
    if missing:
        raise ValueError(f"acts without a rendered image: {missing}")

    prior_line = None
    if prior is not None:
        prior_line = (
            f"Demographic prior: {prior.geography} demand model"
            f"{_vintage_clause(prior)}. {PRIOR_SOURCE_LINE}."
        )

    report_path = out_path / REPORT_FILENAME
    report_path.write_text(
        format_text_report(
            deterministic_result, mc_result, spec.simulation, spec.economic,
            spec=spec,
        ),
        encoding="utf-8",
    )

    story_path = out_path / STORY_FILENAME
    story_path.write_text(
        generate_story_markdown(
            acts, image_by_stem, command,
            headline=verdict_sentence(
                deterministic_result, spec.simulation.years, mc_result,
                num_sims=spec.simulation.num_sims, single_path=single_path_run(spec),
            ),
            subtitle=_verdict_subtitle(spec),
            prior_line=prior_line,
            assumption_lines=format_assumptions(spec),
            single_path_note=mc_result is not None and single_path_run(spec),
        ),
        encoding="utf-8",
    )

    return {"act images": saved_images, "report": report_path, "story": story_path}
