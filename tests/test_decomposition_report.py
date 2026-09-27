"""The `--decompose` block, asserted on the STRING a user sees.

Every test here reads the rendered output, not the code that produced it: a
mutation aimed at the rendered output catches what a test of the code that
produced it walks past. So the literals are spelled out, presence AND absence
are both asserted, and the mutations each test is meant to kill are named on
it.

The block prints figures, not interpretation (spec §0.1 item 35): headings,
figure rows, refusals and structural-zero rows. Which line is
which kind, and each template's claim against the run that printed it, is
`tests/test_decomposition_sentences.py`; this file pins the rendering rules.

The data is hand-built (`decomposition_households.py`): the rendering is pinned
independently of whether the estimators are right, because a test that ran them
would fail when an estimator changed and say nothing about what a household
reads. The few tests that DO run the real assembler, through the CLI, are the
ones whose subject is the sentence the assembler writes and this module prints.
"""
import ast
import dataclasses
import importlib.machinery
import inspect
import json
import pathlib
import re
import sys
import types

import pytest

from tests.decomposition_households import (
    resolved_interaction,
    seven_channel_other_household,
    two_channel_option_state,
    uncertainty_surface,
)
from hde import decomposition as dc
from hde import decomposition_text as dt
from hde.cli import main as cli_main
from hde.decomposition_text import format_decomposition
from hde.serialization import decomposition_to_dict

REPO = pathlib.Path(__file__).resolve().parents[1]


# The block, verbatim, on the flagship fixture's measured figures. Regenerated
# deliberately or not at all: this literal is what a household reads.
FIXTURE_BLOCK = """\
which risk decides it — 2,000 futures, 7 channels live on them
  margin, the cheapest other option's present value minus rent's: central case $31,349; over this block's own 2,000 futures, mean -$67,194 and s.d. $286,506

  THE SPREAD
  channel                 alone                                 with interaction                      flips whether rent is cheapest
  the renter's portfolio  0.88 [0.78, 0.999]                    0.84 [0.75, 0.95]                     40.6% [38.4, 42.8]
      sized by simulation.investment_return_vol=10% [assistant]
  the housing market      0.14 [0.11, 0.17]                     0.13 [0.10, 0.16]                     13.0% [11.5, 14.5]
      sized by simulation.value_growth_vol=7% [assistant]; condo.price_shock.annual_hazard=3% [assistant]; house.price_shock.annual_hazard=3% [assistant]; condo.price_shock.severity_vol=10% [price_shock.severity_vol]; house.price_shock.severity_vol=10% [price_shock.severity_vol]
  your tenancy            0.10 [0.08, 0.12]                     0.09 [0.07, 0.11]                     13.0% [11.5, 14.5]
      sized by rent.reset_hazard=7%/yr [assistant]; simulation.rent_escalation_vol=6% [assistant]; simulation.other_cost_vol=10% [assistant]; rent.events.moving_costs.cost_vol=20% [assistant]
  the population          0.03 [0.02, 0.05]                     0.03 [0.02, 0.05]                     6.0% [5.0, 7.0]
      sized by market_scenario.path [assistant] (the prior's own rows carry their citations); market_scenario.geography=MTL_RMR [user]
  the condo's costs       0.01 [0.01, 0.02]                     0.01 [0.01, 0.02]                     4.0% [3.1, 4.9]
      sized by simulation.condo_fee_vol=8% [assistant]; simulation.other_cost_vol=10% [assistant]; condo.events.special_assessment.cost_vol=25% [assistant]
  the economy             0.01 [-0.002, 0.01]                   0.01 [0.00, 0.01]                     4.0% [3.1, 4.9]
      sized by economic.inflation_vol=1.2% [assistant]; simulation.corr_inflation_condo=0.5 [assistant]; simulation.corr_inflation_house=0.5 [assistant]; simulation.corr_inflation_other=0.4 [assistant]; simulation.corr_inflation_event_cost=0.3 [assistant]; simulation.condo_fee_vol=8% [assistant] (pulled by simulation.corr_inflation_condo = 0.5; rho squared 0.25); simulation.house_maintenance_vol=20% [assistant] (pulled by simulation.corr_inflation_house = 0.5; rho squared 0.25); simulation.other_cost_vol=10% [assistant] (pulled by simulation.corr_inflation_other = 0.4; rho squared 0.16)
  the house's costs       not resolved: -0.001 [-0.002, 0.001]  not resolved: -0.002 [-0.003, 0.002]  0.4% [0.1, 0.7]
      sized by simulation.house_maintenance_vol=20% [assistant]; simulation.other_cost_vol=10% [assistant]; house.events.roof_replacement.cost_vol=20% [assistant]
  alone shares summed before rounding: 1.16 [1.04, 1.31]
  with interaction minus alone, before rounding: the renter's portfolio not resolved: -0.04 [-0.05, 0.01]; the housing market not resolved: -0.01 [-0.02, 0.01]; your tenancy not resolved: -0.01 [-0.02, 0.01]; the population not resolved: 0.00 [-0.01, 0.01]; the condo's costs not resolved: 0.00 [-0.01, 0.01]; the economy not resolved: 0.00 [-0.01, 0.01]; the house's costs not resolved: -0.001 [-0.01, 0.01]
  largest alone share: the renter's portfolio
  your pay drops: drawn on these 2,000 futures, and re-drawing it moved no option's present value by more than $1.87e-09; sized by income.pay_drop_events

  THE LEVEL — the first 2,000 of these futures
  as drawn: mean margin -$67,194, P(rent cheapest) 0.34; the central case's margin minus that mean: $98,543
  channel                 margin shift, channel frozen (± 1 s.e.)  P(rent cheapest), channel frozen
  your tenancy            +$125,074 (± $1,775)                     0.54
  the housing market      -$38,314 (± $2,252)                      0.28
  the population          +$11,064 (± $1,095)                      0.35
  the condo's costs       +$5,232 (± $786)                         0.35
  the house's costs       -$886 (± $179)                           0.35
  the renter's portfolio  not resolved: -$3,805 (± $5,383)         0.35
  the economy             not resolved: -$252 (± $642)             0.34
  the 7 shifts above, summed: $98,113
  largest shift in size: your tenancy"""


def _render(**kwargs) -> str:
    return format_decomposition(uncertainty_surface(**kwargs))


def _line(block: str, needle: str) -> str:
    """The one line containing `needle` — a failure names the whole line."""
    hits = [line for line in block.splitlines() if needle in line]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


def _zero_reading_figures(block: str) -> list:
    """Every printed figure that reads as zero and cannot BE an exact zero.

    An exact zero prints at the figure's own decimals and unsigned (`0.00`,
    `0.0`); a signed zero (`-0.00`, `-0.000`) or one carried to a third zero
    decimal (`0.000`) is a non-zero figure rounded into a zero. The old guard
    here was `"-0.00 " not in block`, which a `-0.000` walks straight past."""
    return re.findall(r"(?<![\d.])(?:-0\.0+|0\.000+)(?![\d])", block)


def _households():
    return (uncertainty_surface(), two_channel_option_state(),
            seven_channel_other_household(),
            uncertainty_surface(interaction=resolved_interaction()))


# ---------------------------------------------------------------------------
# The whole block
# ---------------------------------------------------------------------------

def test_the_block_is_this_text_and_nothing_else():
    """The strongest available assertion: every character a household reads.
    *Kills it:* any change to any figure, any column, any line."""
    assert format_decomposition(uncertainty_surface()) == FIXTURE_BLOCK


def test_a_probability_prints_one_only_when_it_is_one(tmp_path):
    """§0.1 item 51: 1,999 futures of 2,000 printed as "1.00". A probability,
    a share and a flip print as one only when they are one, as they print as
    zero only when they are zero. The witness is a real run whose level
    register reads rent cheapest in 1,998 of 2,000 futures, and in 1,999 with
    the tenancy frozen, beside a frozen channel under which it is cheapest in
    all of them.
    *Kills it:* the one-side guard deleted (0.999 prints as 1.00), or widened
    so an exact one prints as something else."""
    from tests.decomposition_runs import NEAR_ONE, Run
    run = Run(NEAR_ONE, "2000").materialise(tmp_path / "near_one")
    level = run.block["level"]
    assert level["prob_best_base"] == 0.999
    assert _line(run.text, "  as drawn: mean margin").split("P(rent cheapest) ")[1].startswith(
        "0.999;")
    frozen = {row["label"]: row["prob_best_frozen"] for row in level["rows"]}
    assert frozen["your tenancy"] == 0.9995 and frozen["the condo's costs"] == 1.0
    level_text = run.text.split("\n  THE LEVEL", 1)[1]
    assert _line(level_text, "  your tenancy  ").endswith("  0.9995")
    assert _line(level_text, "  the condo's costs  ").endswith("  1.00")
    for value, printed in ((1.0, "1.00"), (0.9995, "0.9995"), (1999 / 2000, "0.9995"),
                           (0.99949, "0.999"), (0.999999, "0.999999"), (0.0, "0.00"),
                           (0.0005, "0.001")):
        assert dt._prob(value) == printed, value
        assert (float(dt._share(value)) == 1.0) == (value == 1.0)
        assert (float(dt._flip(value).rstrip("%")) == 100.0) == (value == 1.0)


def test_silence_is_the_empty_string_not_an_empty_block():
    """§8 case 1 — a run that did not pass the flag.
    *Kills it:* rendering a header, or a "nothing to report" line, for None."""
    assert format_decomposition(None) == ""


@pytest.mark.parametrize("cut", [
    "inputs sizing the channels", "check first", "decide the spread",
    "decides the spread", "either way", "different kinds of number",
    "name different winners", "raise the path count", "re-priced exactly:",
    "re-simulated there", "where the futures sit", "the exactness gate refused",
    "[hde verdict rule]", "docs/reference/API_CONTRACT.md", "not a risk",
    "averages", "above zero", "below zero", "--decompose", "--break-even",
    "--sweep", "no single channel owns", "estimator noise",
])
def test_no_cut_sentence_survives_on_any_household(cut):
    """§0.1 item 35: the verdict line, the provenance summary, the closings,
    the route advice, the licence line, the confirming probabilities and the
    glossary pointer are gone from the block, on every household shape.
    *Kills it:* any of them restored."""
    for dec in _households():
        assert cut not in format_decomposition(dec), cut
    assert uncertainty_surface().verdict.reason not in _render()


# ---------------------------------------------------------------------------
# THE BINDING — the spread table may never be emitted without the level
# register beside it (§5 mechanism 5, ruling 2026-09-22, test T7)
# ---------------------------------------------------------------------------

class TestTheBinding:
    def test_the_narrowest_public_entry_point_returns_both_registers(self):
        """Called the way any caller must call it, both registers come back —
        with their rows, not just their headings.
        *Kills it:* make the level block conditional on anything."""
        block = format_decomposition(uncertainty_surface())
        assert "  THE SPREAD" in block.splitlines()
        assert "  THE LEVEL — the first 2,000 of these futures" in block.splitlines()
        # the row a reader handed the spread table alone would never see
        assert ("  your tenancy            +$125,074 (± $1,775)                     0.54"
                in block.splitlines())

    def test_the_module_exposes_one_callable_and_it_is_that_entry_point(self):
        """*Kills it:* adding `format_spread_table()` — the mutation the ruling
        is about. A public helper that renders one register is the
        caller-reachable path to the spread rows alone."""
        assert dt.__all__ == ["format_decomposition"]
        public = [name for name, value in vars(dt).items()
                  if not name.startswith("_") and inspect.isfunction(value)
                  and value.__module__ == dt.__name__]
        assert public == ["format_decomposition"]

    def test_no_callable_anywhere_in_the_module_renders_the_spread_alone(self):
        """Private helpers included: every function in this module is called
        with every shape a spread renderer could take — the whole block, the
        spread register, its rows, each with and without a path count — and
        any output carrying the spread's table must carry the level register
        too. Two rows' width lines in one output are a table, however it is
        headed.
        *Kills it:* a private `_spread_block(dec)` or `_ranked(spread, paths)` —
        public or not, it exists in the process and a caller can reach it."""
        dec = uncertainty_surface()
        spread = dec.spread
        shapes = [(dec,), (dec, dec.paths), (spread,), (spread, dec.paths),
                  (spread.rows,), (spread.rows, dec.paths),
                  (list(spread.rows),), (list(spread.rows), dec.paths)]
        for name, value in vars(dt).items():
            if not inspect.isfunction(value) or value.__module__ != dt.__name__:
                continue
            for args in shapes:
                try:
                    out = value(*args)
                except (TypeError, AttributeError, AssertionError, KeyError,
                        ValueError):
                    continue      # does not take this shape: not a renderer of it
                text = (out if isinstance(out, str) else
                        "\n".join(map(str, out)) if isinstance(out, (list, tuple))
                        else "")
                if "THE SPREAD" in text or text.count("sized by ") >= 2:
                    assert "THE LEVEL" in text, (name, len(args))

    def test_only_the_entry_point_reads_a_registers_rows(self):
        """The binding checked on the SOURCE, where no argument shape can miss
        it: `.rows` is read only inside `format_decomposition`, so no helper can
        walk a register's rows and hand them back. The spread table then has
        exactly one renderer, and it is the one that renders the level
        register too (§5 mechanism 5).
        *Kills it:* any helper that takes a register and iterates its rows,
        whatever it is named and whatever arguments it takes."""
        tree = ast.parse(inspect.getsource(dt))
        entry = next(node for node in tree.body
                     if isinstance(node, ast.FunctionDef)
                     and node.name == "format_decomposition")
        inside = {id(node) for node in ast.walk(entry)}
        readers = [node.lineno for node in ast.walk(tree)
                   if isinstance(node, ast.Attribute) and node.attr == "rows"
                   and id(node) not in inside]
        assert readers == [], f"`.rows` read outside the entry point at {readers}"
        by_name = [node.lineno for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and node.value == "rows"]
        assert by_name == [], f"`rows` reached by name at {by_name}"

    def test_no_name_in_the_module_promises_one_register(self):
        """A function named for one register is the shape of the defect, so the
        name is refused before it can be written."""
        for name, value in vars(dt).items():
            if not inspect.isfunction(value) or value.__module__ != dt.__name__:
                continue
            assert not any(word in name for word in ("spread_block", "spread_table",
                                                     "level_block", "spread_register",
                                                     "level_register")), name


# ---------------------------------------------------------------------------
# §0.1's rulings on §7's draft, in the figures that carry them
# ---------------------------------------------------------------------------

class TestTheRulingsOnTheDraft:
    def test_the_gap_is_the_subtraction_of_the_two_figures_it_names(self):
        """§0.1 ruling 2. The two figures are the LEVEL register's own
        (§0.1 ruling 1), and the header's mean is a different sample's — so a
        gap taken from the header would print $100,876, the draft's own error.
        *Kills it:* store the gap, or take it from `mean_margin`."""
        block = _render(mean_margin=-69527.0)
        assert _line(block, "as drawn:") == (
            "  as drawn: mean margin -$67,194, P(rent cheapest) 0.34; the central "
            "case's margin minus that mean: $98,543")
        assert "$100,876" not in block          # 31,349 − (−69,527): the draft's gap
        assert "mean -$69,527" in block         # the header's own sample
        assert block.count("$98,543") == 1

    def test_the_level_sum_is_taken_over_the_printed_shifts(self):
        """The sum line adds the dollars the rows PRINT, so a reader adding the
        column lands on it.
        *Kills it:* summing the unrounded deltas (off by the rounding)."""
        dec = two_channel_option_state()
        first, second = dec.level.rows
        rows = (dataclasses.replace(first, level=dataclasses.replace(
                    first.level, delta=8940.4)),
                dataclasses.replace(second, level=dataclasses.replace(
                    second.level, delta=-2110.6)))
        block = format_decomposition(dataclasses.replace(
            dec, level=dataclasses.replace(dec.level, rows=rows)))
        assert _line(block, "the condo's costs       +$8,940").startswith(
            "  the condo's costs       +$8,940 (")
        assert _line(block, "the house's costs       -$2,111").startswith(
            "  the house's costs       -$2,111 (")
        # 8,940 - 2,111 as printed; the unrounded sum, 6,829.8, prints $6,830
        assert "  the 2 shifts above, summed: $6,829" in block.splitlines()

    def test_one_stored_probability_at_one_rounding(self):
        """§0.1 ruling 2's second half: the level baseline is printed ONCE, at
        one rounding, instead of leading every row as `0.34 ->`.
        *Kills it:* restate the baseline per row, or print it at 4 decimals
        somewhere as well."""
        block = _render()
        assert block.count("P(rent cheapest) 0.34") == 1
        assert "0.34 ->" not in block and "->" not in block
        assert "0.3350" not in block            # verdict.prob_best's own rounding
        assert "0.341" not in block             # prob_best_base unrounded

    def test_the_ten_thousand_path_parenthetical_is_gone(self):
        """§0.1 ruling 3: no section licenses computing the decomposition twice.
        *Kills it:* re-adding "(at 10,000 they add to 1.02)"."""
        block = _render()
        assert "10,000" not in block
        assert "they add to" not in block
        assert block.count("alone shares summed before rounding") == 1

    def test_the_economy_row_names_the_option_vols_its_correlations_pull_from(self):
        """§0.1 ruling 6: §7's draft cell listed only the `corr_inflation_*`
        keys and is in breach of §4, because which vols are pulled depends on
        which rho is non-zero.
        *Kills it:* drop the pulled vols, or cap the width cell."""
        row = _line(_render(), "corr_inflation_condo")
        for key in ("economic.inflation_vol=1.2%",
                    "simulation.corr_inflation_condo=0.5",
                    "simulation.corr_inflation_house=0.5",
                    "simulation.corr_inflation_other=0.4",
                    "simulation.corr_inflation_event_cost=0.3",
                    "simulation.condo_fee_vol=8%",
                    "simulation.house_maintenance_vol=20%",
                    "simulation.other_cost_vol=10%"):
            assert key in row, key
        assert ("simulation.condo_fee_vol=8% [assistant] (pulled by "
                "simulation.corr_inflation_condo = 0.5; rho squared 0.25)") in row


# ---------------------------------------------------------------------------
# The three §7-draft defects (§0.1 item 18)
# ---------------------------------------------------------------------------

class TestTheDraftDefectsOfItem18:
    def test_the_house_row_is_resolved_because_its_shift_is_five_se(self):
        """-$886 ± $179 is 4.95 SE and §3.4's rule is |Δ| > 2·SE, so it prints
        as a resolved figure. §7's draft filed it under "indistinguishable from
        zero" — the draft printing a real effect as noise, which is the error
        this feature exists to prevent.
        *Kills it:* printing it behind "not resolved"."""
        lines = _render().splitlines()
        assert ("  the house's costs       -$886 (± $179)                           0.35"
                in lines)
        assert ("  the renter's portfolio  not resolved: -$3,805 (± $5,383)         0.35"
                in lines)
        assert ("  the economy             not resolved: -$252 (± $642)             0.34"
                in lines)

# ---------------------------------------------------------------------------
# §7's formatter rules
# ---------------------------------------------------------------------------

class TestTheFormatterRules:
    def test_no_column_is_called_importance_or_contribution(self):
        """§7 rule 3."""
        block = _render().lower()
        assert "importance" not in block
        assert "contribution" not in block

    def test_the_flip_column_prints_on_every_row_with_its_own_width(self):
        """§7 rule 4 — it is the only column that speaks in decision space —
        and §3.3 plus §0.1 item 10: it carries its interval. A point estimate
        with no width, beside neighbours that all carry one, reads as the most
        certain number in the table.
        *Kills it:* dropping the column, dropping it only where the shares did
        not resolve, or printing the point estimate bare."""
        block = _render()
        assert _line(block, "flips whether").endswith("flips whether rent is cheapest")
        for cell in ("40.6% [38.4, 42.8]", "13.0% [11.5, 14.5]", "6.0% [5.0, 7.0]",
                     "4.0% [3.1, 4.9]", "0.4% [0.1, 0.7]"):
            assert cell in block, cell
        assert _line(block, "  the house's costs       not resolved").endswith(
            "0.4% [0.1, 0.7]")

    def test_the_flip_column_names_the_winner_whose_side_it_counts(self):
        """The flip is `sign(f)` against the CENTRAL CASE's winner: a future
        that moves from the condo to the house while rent stays beaten is not
        counted. "changes sides" named no side. The heading names this run's
        `verdict.best`.
        *Kills it:* a fixed header, or one naming the runner-up."""
        block = _render()
        assert "changes sides" not in block and "changing sides" not in block
        assert block.count("flips whether rent is cheapest") == 1
        other = format_decomposition(two_channel_option_state())
        assert "flips whether condo is cheapest" in other
        assert "flips whether rent is cheapest" not in other

    def test_an_unresolved_share_prints_only_behind_the_words(self):
        """§7 rule 6 and §4's no-clamp rule: the estimates are kept, printed
        behind "not resolved", and never rounded into `-0.00`.
        *Kills it:* rendering `provisional_alone` in the `alone` column bare,
        or clamping it to 0.00."""
        block = _render()
        assert ("  the house's costs       not resolved: -0.001 [-0.002, 0.001]  not "
                "resolved: -0.002 [-0.003, 0.002]  0.4% [0.1, 0.7]") in block.splitlines()
        bare = re.sub(r"not resolved: -0\.00[12] \[[^]]*\]", "", block)
        assert "-0.001 [" not in bare and "-0.002 [-0.003" not in bare
        assert _zero_reading_figures(block) == []

    def test_a_small_share_flip_or_probability_never_reads_as_zero(self):
        """§4 and this module's own rule: a figure that is not zero never
        prints as zero. Measured on examples/showcase_demographic_prior.yaml
        before this was fixed: "0.001 [-0.000, 0.002]" and "-0.000 [-0.001,
        0.001]" — the shares' own rule said three decimals would do, and the
        test beside it looked for "-0.00 " and so never saw "-0.000". Each
        figure here is small enough that its base decimals would round it to
        zero, and each prints at the first decimal that shows it.
        *Kills it:* reverting `_faithful` to a fixed three decimals (the
        shares), one decimal (the flip), or two (the probability)."""
        dec = two_channel_option_state()
        condo, house = dec.spread.rows
        tiny = dataclasses.replace(house, shares=dc.ResolvedShares(
            alone=0.0004, alone_ci=dc.Interval(-0.0003, 0.0021),
            with_interaction=0.0012, with_interaction_ci=dc.Interval(0.0004, 0.0019)),
            flip=0.0002, flip_ci=dc.Interval(0.0001, 0.0004))
        noise = dataclasses.replace(condo, shares=dc.UnresolvedShares(
            provisional_alone=-0.0004,
            provisional_alone_ci=dc.Interval(-0.0011, 0.0006),
            provisional_with_interaction=0.0009,
            provisional_with_interaction_ci=dc.Interval(0.00049, 0.0013)))
        rare = dc.LevelRow(channel_id=4, level=dc.ResolvedLevel(
            delta=-2110.0, se=505.0, prob_best_frozen=0.003))
        block = format_decomposition(dataclasses.replace(
            dec,
            spread=dataclasses.replace(dec.spread, rows=(noise, tiny),
                                       leading_channel_id=4),
            level=dataclasses.replace(dec.level,
                                      rows=(dec.level.rows[0], rare))))
        lines = block.splitlines()
        assert ("  the house's costs       0.0004 [-0.0003, 0.002]                0.001 "
                "[0.0004, 0.002]                0.02% [0.01, 0.04]") in lines
        assert ("  the condo's costs       not resolved: -0.0004 [-0.001, 0.001]  not "
                "resolved: 0.001 [0.0005, 0.001]  8.2% [7.3, 9.1]") in lines
        assert ("  the house's costs       -$2,110 (± $505)                         0.003"
                in lines)
        assert _zero_reading_figures(block) == []
        # ...and an exact zero is still a zero, unsigned, at its own decimals
        zero = dataclasses.replace(tiny, shares=dataclasses.replace(
            tiny.shares, alone_ci=dc.Interval(-0.0, 0.0021)))
        exact = format_decomposition(dataclasses.replace(
            dec, spread=dataclasses.replace(dec.spread, rows=(condo, zero))))
        assert "0.0004 [0.00, 0.002]" in exact

    def test_a_share_outside_zero_to_one_never_reads_inside_it(self):
        """The same rule's other half: an unresolved share of 1.004 at two
        decimals reads "1.00" — all of the spread, and inside [0, 1] — on the
        row that did not resolve BECAUSE it is above one. That is the clamp §4
        refuses, done by a rounding.
        *Kills it:* dropping the [0, 1] half of `_faithful`."""
        block = format_decomposition(seven_channel_other_household())
        assert ("  the economy             not resolved: 1.004 [0.998, 1.01]  not "
                "resolved: 1.01 [1.001, 1.01]  0.2% [0.1, 0.3]") in block.splitlines()
        assert "1.00 [1.00, 1.01]" not in block

    def test_the_residual_prints_only_on_its_resolved_branch(self):
        """§7 rule 5 / §4, the three states: on this fixture at its committed
        2,000 paths the interval on the shares' sum lies above 1, and no
        residual clause prints; where the interval includes 1, its low end
        exactly 1 included, the residual is not resolved; below 1 it prints.
        *Kills it:* clamping ΣS to 1 (the refusal becomes unreachable),
        printing a residual on the refused branch, "not resolved" beside an
        interval above 1, or no clause beside one whose low end is 1."""
        assert _line(_render(), "summed before rounding") == (
            "  alone shares summed before rounding: 1.16 [1.04, 1.31]")
        assert _line(_render(interaction=resolved_interaction()),
                     "summed before rounding") == (
            "  alone shares summed before rounding: 0.95 [0.92, 0.98]; 1 minus that "
            "sum: 0.05 [0.02, 0.08]")
        for low, printed in ((0.73, "0.73"), (1.0, "1.00")):
            refused = dc.RefusedInteraction(first_order_sum=1.1,
                                            first_order_sum_ci=dc.Interval(low, 1.22))
            assert _line(_render(interaction=refused), "summed before rounding") == (
                f"  alone shares summed before rounding: 1.10 [{printed}, 1.22]; 1 minus "
                f"that sum: not resolved")

    def test_the_gap_line_names_every_row_once_resolved_or_not(self):
        """Every row's gap prints with its interval, in the table's order, and
        a gap that did not resolve prints behind "not resolved:" (§0.1 item 46:
        a figure that did not resolve prints behind the words, never in place
        of them).
        *Kills it:* dropping an unresolved row's figure, or printing a gap that
        did not resolve without the words before it."""
        dec = two_channel_option_state()
        condo, house = dec.spread.rows
        cells = {row.channel_id: f"{dt._share(row.interaction_gap)} "
                                 f"{dt._interval(row.interaction_gap_ci)}"
                 for row in (condo, house)}
        both = format_decomposition(dec)
        assert _line(both, "with interaction minus alone") == (
            f"  with interaction minus alone, before rounding: the condo's costs not "
            f"resolved: {cells[3]}; the house's costs not resolved: {cells[4]}")
        one = format_decomposition(dataclasses.replace(
            dec, spread=dataclasses.replace(dec.spread, interaction_channel_ids=(3,))))
        assert _line(one, "with interaction minus alone") == (
            f"  with interaction minus alone, before rounding: the condo's costs "
            f"{cells[3]}; the house's costs not resolved: {cells[4]}")

    def test_every_row_carries_its_widths_inline_on_that_row(self):
        """§7 rule 7 / §5 mechanism 1: a reader cannot see the ranking without
        seeing whose numbers produced it.
        *Kills it:* moving the widths to a trailing footnote, or dropping one."""
        block = _render()
        lines = block.splitlines()
        for row in uncertainty_surface().spread.rows:
            label = dc.channel(row.channel_id).label
            start = next(i for i, line in enumerate(lines)
                         if line.startswith(f"  {label} ") and "%" in line
                         and "[" in line and "$" not in line)
            assert lines[start + 1].startswith("      sized by "), label
            for width in row.widths:
                assert width.key in lines[start + 1], (label, width.key)
                assert f"[{width.tag}]" in lines[start + 1]

    def test_an_anchored_width_names_its_anchor(self):
        """§0.1 item 53: a width's tag is the read-back's for that key, and the
        read-back's `anchor-sourced:` line brackets the anchor's name alone.
        *Kills it:* a class prefix before the name, or the class in its place."""
        assert ("condo.price_shock.severity_vol=10% [price_shock.severity_vol]"
                in _render())

    def test_a_width_prints_the_tag_it_carries(self):
        """The formatter prints the producer's tag as it is; a width with none
        never reaches it, as the assembler refuses the block
        (`untagged_width`).
        *Kills it:* rebuilding the tag from `source` and `anchor` (the cite
        below then vanishes)."""
        cite = dc.Width(key="condo.price_shock.severity_mean", formatted="25.0%",
                        source="default", anchor="price_shock.severity_mean",
                        tag="TREB 1989–96")
        assert dt._width_cell(cite) == "condo.price_shock.severity_mean=25.0% [TREB 1989–96]"

    def test_a_shift_that_prints_as_zero_prints_unsigned(self):
        """A printed zero has no direction: an exact zero, a negative zero and
        a shift that prints as zero dollars from either side all print `$0`,
        where `+$0` read as a shift upward and `-$0` as one downward. A shift
        that prints as a dollar keeps its sign.
        *Kills it:* the zero branch deleted (`+$0` and `-$0` again), or
        widened to a shift that prints as a dollar."""
        assert (dt._shift(0.0), dt._shift(-0.0)) == ("$0", "$0")
        assert (dt._shift(0.3), dt._shift(-0.3)) == ("$0", "$0")
        assert (dt._shift(0.6), dt._shift(-0.6)) == ("+$1", "-$1")
        assert (dt._shift(1234.4), dt._shift(-1234.6)) == ("+$1,234", "-$1,235")
        dec = uncertainty_surface()
        rows = tuple(
            dataclasses.replace(row, level=dc.IndistinguishableLevel(
                provisional_delta=delta, se=0.0, prob_best_frozen=0.5))
            if row.channel_id in (3, 4) else row
            for row, delta in zip(dec.level.rows, [0.0 if r.channel_id == 3 else 0.3
                                                   for r in dec.level.rows]))
        lines = format_decomposition(dataclasses.replace(
            dec, level=dataclasses.replace(dec.level, rows=rows))).splitlines()
        condo = next(line for line in lines if line.startswith("  the condo's costs ")
                     and "± $" in line)
        house = next(line for line in lines if line.startswith("  the house's costs ")
                     and "± $" in line)
        assert "not resolved: $0 (± $0)" in condo
        assert "not resolved: $0 (± $0)" in house

    def test_a_width_with_no_figure_prints_its_key_alone(self):
        assert "market_scenario.path [assistant]" in _render()


# ---------------------------------------------------------------------------
# The top row of each register: the engine's rule, read and never re-derived
# ---------------------------------------------------------------------------

class TestTheTopRow:
    def test_a_resolved_top_row_prints_as_a_figure(self):
        block = _render()
        assert "  largest alone share: the renter's portfolio" in block.splitlines()
        assert "  largest shift in size: your tenancy" in block.splitlines()

    def test_an_unresolved_top_share_prints_no_largest_line(self):
        """examples/rent_vs_condo_vs_house.yaml: the condo's costs carry a
        provisional 1.07 that did not resolve, and the resolved leader was the
        house's costs at 0.01 — so the block named a hundredth of the spread
        as the leading channel. Nothing smaller is promoted, and no line calls
        a figure the block prints as not resolved the largest (§0.1 item 35);
        the JSON names the unresolved top.
        *Kills it:* a formatter that promotes the resolved row, prints the
        unresolved top as largest, or a serializer that drops it."""
        dec = two_channel_option_state()
        condo, house = dec.spread.rows
        big = dataclasses.replace(condo, shares=dc.UnresolvedShares(
            provisional_alone=1.07, provisional_alone_ci=dc.Interval(0.9996, 1.16),
            provisional_with_interaction=1.04,
            provisional_with_interaction_ci=dc.Interval(0.9998, 1.10)))
        small = dataclasses.replace(house, shares=dc.ResolvedShares(
            alone=0.01, alone_ci=dc.Interval(0.006, 0.02),
            with_interaction=0.02, with_interaction_ci=dc.Interval(0.015, 0.025)))
        outcome = dataclasses.replace(
            dec, spread=dataclasses.replace(
                dec.spread, rows=(small, big), leading_channel_id=None,
                unresolved_top_channel_id=3))
        block = format_decomposition(outcome)
        assert "largest alone share" not in block
        assert "not resolved: 1.07 [0.9996, 1.16]" in block
        doc = decomposition_to_dict(outcome)["spread"]
        assert (doc["leading_channel_id"], doc["unresolved_top_channel_id"]) == (None, 3)

    def test_an_unresolved_top_shift_is_named_and_no_smaller_row_is_called_largest(self):
        """examples/basic_config.yaml: the house's costs resolve at +$252 and
        the condo's costs move the margin by +$390 ± $273. The closing called
        the house's costs the largest single shift. No row is called largest,
        the larger shift prints behind "not resolved", and the smaller
        resolved row keeps its figure.
        *Kills it:* promoting the resolved row."""
        dec = two_channel_option_state()
        rows = (
            dc.LevelRow(channel_id=3, level=dc.IndistinguishableLevel(
                provisional_delta=390.0, se=273.0, prob_best_frozen=0.87)),
            dc.LevelRow(channel_id=4, level=dc.ResolvedLevel(
                delta=252.0, se=122.0, prob_best_frozen=0.68)),
        )
        block = format_decomposition(dataclasses.replace(dec, level=dataclasses.replace(
            dec.level, rows=rows, paths=2000, leading_channel_id=None,
            unresolved_top_channel_id=3)))
        lines = block.splitlines()
        assert "largest shift in size" not in block
        assert ("  the house's costs       +$252 (± $122)                           0.68"
                in lines)
        assert ("  the condo's costs       not resolved: +$390 (± $273)             0.87"
                in lines)

    def test_every_legal_pairing_of_the_top_row_renders(self):
        """Which row is on top, and whether it leads, is the assembler's
        judgment (`decomposition_run._top_row`); the formatter names the
        leader it is handed. A resolved leader and an unresolved top that is an
        unresolved row both render.
        *Kills it:* a formatter that refuses an unresolved top."""
        seven = format_decomposition(seven_channel_other_household())
        assert "largest alone share" not in seven          # an unresolved top
        assert "  largest shift in size: the housing market" in seven.splitlines()
        assert "largest alone share: the renter's portfolio" in _render()


# ---------------------------------------------------------------------------
# Refusals — RENDERED here as code and reason, decided by the assembler
# ---------------------------------------------------------------------------

class TestRefusalsAreRenderedWithTheirReason:
    @pytest.mark.parametrize("code", dc.REFUSAL_CODES)
    def test_every_refusal_code_prints_its_code_and_reason_and_nothing_else(self, code):
        """*Kills it:* letting any refusal fall through to silence, printing an
        empty register beside it, or appending a sentence of the formatter's
        own to the refusing party's."""
        out = format_decomposition(dc.DecompositionRefusal(
            code=code, reason=f"the {code} condition fired on this run",
            channel_id=3 if code == "one_channel" else None))
        assert out == (f"which risk decides it — not split ({code}): the {code} "
                       f"condition fired on this run")

    def test_a_refused_spread_prints_code_and_reason_and_the_level_still_prints(self):
        """§0.1 item 7: `P(f > 0) == 1` refuses the SPREAD register by name
        while the level register still prints — the binding runs one way, so
        a refused spread beside a printed level is the honest shape. The reason is the ASSEMBLER's and prints verbatim, directly
        under the spread's heading.
        *Kills it:* printing an empty table with a column header and no rows,
        a sums line over no rows, a top line naming a row that did not print,
        or dropping the level register along with the shares."""
        dec = uncertainty_surface()
        reason = "rent is cheapest in all 2,000 of these futures"
        block = format_decomposition(dataclasses.replace(
            dec, spread=dc.RefusedSpread(code="no_sign_variation", reason=reason,
                                         structural_zeros=dec.spread.structural_zeros)))
        lines = block.splitlines()
        heading = lines.index("  THE SPREAD")
        assert lines[heading + 1] == f"  not split (no_sign_variation): {reason}"
        # §0.1 item 48: the rows measured on these futures stay under the
        # register whose sample they are, refused or not
        assert lines[heading + 2] == (
            "  your pay drops: drawn on these 2,000 futures, and re-drawing it moved no "
            "option's present value by more than $1.87e-09; sized by "
            "income.pay_drop_events")
        assert lines[heading + 3] == ""
        assert lines[heading + 4] == "  THE LEVEL — the first 2,000 of these futures"
        assert block.count(reason) == 1
        for absent in ("with interaction", "summed before rounding", "largest alone",
                       "      sized by", "not resolved: -0.001"):
            assert absent not in block, absent
        assert "  your tenancy            +$125,074 (± $1,775)                     0.54" \
            in lines
        assert lines[-1] == "  largest shift in size: your tenancy"

    def test_an_empty_spread_register_raises_rather_than_printing_over_nothing(self):
        """A `SpreadRegister` with no rows is a state no producer emits: a spread
        with nothing to show arrives as `RefusedSpread`, carrying its reason. A
        heading over no rows would leave the reader to infer why, so the
        formatter refuses the object rather than guess at a sentence.
        *Kills it:* rendering the heading over nothing."""
        dec = uncertainty_surface()
        empty = dataclasses.replace(
            dec, spread=dataclasses.replace(dec.spread, rows=(),
                                            leading_channel_id=None,
                                            unresolved_top_channel_id=0))
        with pytest.raises(ValueError, match="RefusedSpread"):
            format_decomposition(empty)

    def test_a_spread_register_of_neither_type_raises(self):
        dec = uncertainty_surface()
        with pytest.raises(TypeError, match="neither a SpreadRegister nor a RefusedSpread"):
            format_decomposition(dataclasses.replace(dec, spread=dec.level))

    def test_a_dead_draw_row_says_its_facts_of_the_stream_and_never_of_a_key(self):
        """A stream that drew and moves nothing prints as its own row, never as
        a measured `0.00` row, and its two facts are said of the STREAM by
        name, scoped to the futures and the threshold they were measured on
        (§0.1 items 39 and 40). The key follows as what sizes the stream, and
        no fact is said of it: `rent.events` carries a deterministic cost that
        reaches rent's present value.
        *Kills it:* the key as the row's subject, or a fact with no scope."""
        block = format_decomposition(two_channel_option_state())
        assert ("  your tenancy: drawn on these 4,000 futures, and re-drawing it moved no "
                "option's present value by more than $1.87e-09; sized by rent.events"
                in block.splitlines())
        assert "your tenancy            0.00" not in block
        assert "rent.events:" not in block and "cash flow" not in block

    def test_a_row_of_each_kind_carries_exactly_what_its_kind_rests_on(self):
        """A stated-path row names its exact row and no measurement; a measured
        row names its stream, its futures and its threshold, and no exact row.
        *Kills it:* a measured row with no scope, or a stated path carrying one."""
        with pytest.raises(ValueError, match="stated_path"):
            dc.StructuralZero(kind="stated_path", label="x", keys=("a.b",),
                              reversal_key="a.b", measured_paths=10)
        with pytest.raises(ValueError, match="stated_path"):
            dc.StructuralZero(kind="stated_path", label="x", keys=("a.b",))
        with pytest.raises(ValueError, match="dead_draw"):
            dc.StructuralZero(kind="dead_draw", label="x", keys=(), channel_id=5,
                              measured_paths=10)
        with pytest.raises(ValueError, match="dead_draw"):
            dc.StructuralZero(kind="dead_draw", label="x", keys=(), channel_id=5,
                              measured_paths=10, move_threshold=1e-9,
                              reversal_key="rent.events")
        with pytest.raises(ValueError, match="not one of"):
            dc.StructuralZero(kind="no_pv_reach", label="x", keys=())
        dc.StructuralZero(kind="dead_draw", label="x", keys=(), channel_id=5,
                          measured_paths=10, move_threshold=1e-9)

# ---------------------------------------------------------------------------
# The `--json` block (serialization.decomposition_to_dict)
# ---------------------------------------------------------------------------

class TestTheJsonBlock:
    def test_the_two_registers_are_emitted_together(self):
        """The binding in this surface's own terms: a consumer cannot get the
        spread rows without the level rows beside them, and the block carries
        no third register (§0.1 item 56).
        *Kills it:* a register emitted alone, or a `reversal` key back."""
        doc = decomposition_to_dict(uncertainty_surface())
        assert set(doc) == {"paths", "max_paths", "live_channel_ids", "mean_margin",
                            "sd_margin", "spread", "level"}
        assert doc["spread"]["rows"] and doc["level"]["rows"]

    def test_silence_is_no_block_at_all(self):
        assert decomposition_to_dict(None) is None

    def test_a_refusal_carries_no_register_keys(self):
        """*Kills it:* emitting empty registers beside a refusal, which reads as
        "nothing to report" rather than "this did not run"."""
        doc = decomposition_to_dict(dc.DecompositionRefusal(
            code="one_channel", reason="nothing to split", channel_id=3))
        assert doc == {"refusal": {"code": "one_channel", "reason": "nothing to split",
                                   "channel_id": 3, "channel": "condo",
                                   "label": "the condo's costs"}}
        assert "spread" not in doc and "level" not in doc

    def test_an_unresolved_row_has_no_resolved_key_to_read(self):
        """The typed contract's device, carried into JSON: a consumer reading
        `row["alone"]` on an unresolved row gets a KeyError, not a number.
        *Kills it:* emitting `alone` on both branches, or a `null` for it."""
        doc = decomposition_to_dict(uncertainty_surface())
        house = next(r for r in doc["spread"]["rows"] if r["channel"] == "house")
        assert house["resolved"] is False
        assert "alone" not in house and "with_interaction" not in house
        assert house["provisional_alone"] == -0.001
        portfolio = next(r for r in doc["level"]["rows"] if r["channel"] == "portfolio")
        assert portfolio["resolved"] is False
        assert "delta" not in portfolio and portfolio["provisional_delta"] == -3805.0

    def test_the_refused_interaction_branch_carries_no_residual(self):
        doc = decomposition_to_dict(uncertainty_surface())
        assert doc["spread"]["interaction"]["resolved"] is False
        assert "residual" not in doc["spread"]["interaction"]
        resolved = decomposition_to_dict(
            uncertainty_surface(interaction=resolved_interaction()))
        assert resolved["spread"]["interaction"]["residual"] == 0.05

    def test_neither_the_verdict_nor_the_gap_is_stored_here(self):
        """One home per truth: the document's top-level `verdict` key is that
        object's home, and the gap is a subtraction of two figures in this
        block (§0.1 ruling 2)."""
        doc = decomposition_to_dict(uncertainty_surface())
        assert "verdict" not in doc
        assert "gap" not in doc["level"]
        assert (doc["level"]["all_frozen_margin"] - doc["level"]["futures_margin"]
                == pytest.approx(98542.656075))

    def test_the_block_is_json_serialisable(self):
        json.dumps(decomposition_to_dict(uncertainty_surface()), allow_nan=False)
        json.dumps(decomposition_to_dict(seven_channel_other_household()),
                   allow_nan=False)

    def test_a_refused_spread_is_a_refusal_in_the_spread_slot_with_no_rows(self):
        """§0.1 item 7 in this surface's terms: the refusal sits where the
        register would, with its code and reason, and there is no `rows` key
        for a consumer to read as "nothing to report". The level register
        still travels beside it.
        *Kills it:* serializing the refusal as an empty register."""
        dec = uncertainty_surface()
        doc = decomposition_to_dict(dataclasses.replace(
            dec, spread=dc.RefusedSpread(code="no_sign_variation",
                                         reason="nothing to split",
                                         structural_zeros=dec.spread.structural_zeros)))
        (zero,) = dec.spread.structural_zeros
        assert doc["spread"] == {
            "refusal": {"code": "no_sign_variation", "reason": "nothing to split"},
            # §0.1 item 48: measured on these futures, refused or not
            "structural_zeros": [{
                "kind": "dead_draw", "label": zero.label, "keys": list(zero.keys),
                "channel_id": zero.channel_id, "measured_paths": zero.measured_paths,
                "move_threshold": zero.move_threshold}]}
        assert doc["level"]["rows"]
        json.dumps(doc)

    def test_the_flip_figure_travels_with_its_interval(self):
        """§0.1 item 10 holds on this surface too: the one figure in decision
        space never arrives bare while its neighbours carry an interval."""
        doc = decomposition_to_dict(uncertainty_surface())
        for row in doc["spread"]["rows"]:
            assert set(row["flip_ci"]) == {"low", "high"}
            assert row["flip_ci"]["low"] <= row["flip"] <= row["flip_ci"]["high"]

    def test_every_key_the_block_emits_is_in_the_documented_contract(self):
        """AGENTS.md's artifact boundary: the agent-facing contract lives in
        `docs/reference/`. Every key `decomposition_to_dict` emits — on a block,
        on a whole-block refusal, on a refused spread — and every refusal code
        is named in API_CONTRACT.md's `decomposition`
        section, so a consumer never meets a key the contract does not define.
        *Kills it:* adding a key, or a refusal code, without documenting it."""
        text = (REPO / "docs" / "reference" / "API_CONTRACT.md").read_text(
            encoding="utf-8")
        start = text.index("## The `decomposition` block")
        end = text.find("\n## ", start + 1)
        section = text[start:] if end == -1 else text[start:end]
        keys = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    keys.add(key)
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        agreed = dataclasses.replace(
            uncertainty_surface(),
            spread=dc.RefusedSpread(code="no_sign_variation", reason="r",
                                    structural_zeros=uncertainty_surface().spread.structural_zeros))
        for outcome in (uncertainty_surface(), seven_channel_other_household(),
                        two_channel_option_state(), agreed,
                        uncertainty_surface(interaction=resolved_interaction()),
                        dc.DecompositionRefusal(code="one_channel", reason="r",
                                                channel_id=3)):
            # Walked as a consumer reads it, after JSON: the serializer's
            # tuples (a row's widths, a dead row's keys) are lists there, and a
            # walk of the dict alone skipped every key inside them.
            walk(json.loads(json.dumps(decomposition_to_dict(outcome))))
        assert {"anchor", "move_threshold", "tag", "note"} <= keys
        assert "reversal" not in keys and "reversal_key" not in keys
        assert sorted(k for k in keys if f"`{k}`" not in section) == []
        for code in dc.REFUSAL_CODES + dc.SPREAD_REFUSAL_CODES:
            assert f"`{code}`" in section, code
        # A whole-block code is documented by its own ROW of the refusal table,
        # which says what its reason states; a mention in passing elsewhere in
        # the section is not that.
        for code in dc.REFUSAL_CODES:
            assert f"\n| `{code}` | " in section, code

    def test_the_contract_states_the_resolution_rule_the_code_applies(self):
        """The contract said "a row is unresolved when either share's interval
        leaves [0, 1]"; the code (`decomposition_math.share_is_resolved`)
        tests the POINT estimate, and the code's rule stands — a point outside
        [0, 1] is a meaningless share, a small share whose interval touches
        zero is a real one. Both documents state the point rule, and the row
        that proves the difference is pinned beside them: its interval crosses
        zero, the code resolves it, and the JSON says `resolved: true`.
        *Kills it:* either document reverting to the interval rule, or the
        code changing rule while the documents keep this one."""
        from hde import decomposition_math as dm
        row = next(r for r in uncertainty_surface().spread.rows if r.channel_id == 0)
        assert row.shares.alone_ci.low < 0 < row.shares.alone
        assert dm.share_is_resolved(row.shares.alone)
        assert not dm.share_is_resolved(row.shares.alone_ci.low)
        doc = decomposition_to_dict(uncertainty_surface())
        economy = next(r for r in doc["spread"]["rows"] if r["channel"] == "economy")
        assert economy["resolved"] is True and economy["alone_ci"]["low"] < 0
        # One home for the rule: the contract states it, and the glossary
        # points there instead of restating it (§0.1 item 32).
        contract = " ".join((REPO / "docs" / "reference" / "API_CONTRACT.md"
                             ).read_text(encoding="utf-8").split())
        assert ("A row is `resolved: false` when either share's point estimate lies "
                "outside [0, 1]; its interval does not decide it") in contract
        assert "interval leaves [0, 1]" not in contract
        glossary = (REPO / "docs" / "reference" / "ARCHITECTURE.md").read_text(
            encoding="utf-8")
        section = glossary.split("### Which risk decides it", 1)[1].split("\n### ", 1)[0]
        assert "API_CONTRACT.md" in section
        assert "POINT estimate" not in section and "resolved" not in section


# ---------------------------------------------------------------------------
# The flag (cli.py) — including the refusal that is the CLI's own to make
# ---------------------------------------------------------------------------

SEAM = "hde.decomposition_run"


def _config(tmp_path) -> str:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "years: 8\ndiscount_rate: 0.03\nhouse:\n  initial_value: 400000\n"
        "  all_cash: true\nrent:\n  monthly_rent: 1800\n"
        "  invested_down_payment: 400000\n",
        encoding="utf-8",
    )
    return str(cfg)


@pytest.fixture
def seam(monkeypatch):
    """The assembler's seam, `hde/decomposition_run.py :: decompose(spec, *,
    det, mc, verdict, raw, prior)`, stood in for: this fixture drives the CLI's
    own path — flag, render, JSON — over a hand-built block, so the surface is
    tested independently of the estimators behind the seam."""
    module = types.ModuleType(SEAM)
    module.__spec__ = importlib.machinery.ModuleSpec(SEAM, None)
    calls = {}

    def decompose(spec, **kwargs):
        calls.update(kwargs)
        calls["spec"] = spec
        return calls.get("outcome", uncertainty_surface())

    module.decompose = decompose
    monkeypatch.setitem(sys.modules, SEAM, module)
    return calls


class TestTheFlag:
    def test_without_the_flag_nothing_is_computed_and_nothing_is_printed(
            self, tmp_path, monkeypatch, capsys):
        """§8 case 1, and the absence invariant: the seam is never even
        imported on a run that does not ask."""
        monkeypatch.setitem(sys.modules, SEAM, None)   # importing it would fail
        monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path)])
        assert cli_main() == 0
        assert "which risk decides it" not in capsys.readouterr().out

    def test_the_flag_prints_the_block_under_the_verdict(
            self, tmp_path, monkeypatch, capsys, seam):
        monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path), "--decompose"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert FIXTURE_BLOCK in out
        # under the verdict the report printed, and above the lines to carry
        assert out.index("decisiveness:") < out.index("which risk decides it")
        assert out.index("which risk decides it") < out.index("READ-BACK")
        # the seam is called with the run's own objects, not re-derived ones
        assert seam["verdict"] is not None and seam["raw"]["years"] == 8

    def test_the_flag_adds_the_json_key_and_only_then(
            self, tmp_path, monkeypatch, capsys, seam):
        config = _config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--decompose", "--json"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["decomposition"]["spread"]["leading_channel_id"] == 6
        assert "which risk decides it" not in json.dumps(doc)   # text stays out of JSON

        monkeypatch.setattr(sys, "argv", ["hde", config, "--json"])
        assert cli_main() == 0
        assert "decomposition" not in json.loads(capsys.readouterr().out)

    def test_a_missing_seam_refuses_by_name_rather_than_printing_nothing(
            self, tmp_path, monkeypatch, capsys):
        """The one refusal that is the CLI's own: §8's refusals are judgments
        about data and belong to the assembler, but a build with no assembler
        at all is this surface's own problem to name.
        *Kills it:* swallowing the ImportError and printing an empty block."""
        monkeypatch.setitem(sys.modules, SEAM, None)
        monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path), "--decompose"])
        assert cli_main() == 1
        captured = capsys.readouterr()
        assert ("Error: --decompose needs the decomposition estimators "
                "(hde.decomposition_run), which this build does not carry"
                in captured.err)
        assert "Traceback" not in captured.err
        assert "which risk decides it" not in captured.out

    def test_a_broken_seam_is_not_reported_as_a_missing_one(
            self, tmp_path, monkeypatch):
        """A `decomposition_run` that fails to import its own dependency is a
        defect, not an absence, and must not be diagnosed as "not in this
        build"."""
        module = types.ModuleType(SEAM)
        module.__spec__ = importlib.machinery.ModuleSpec(SEAM, None)

        def explode(*a, **k):
            raise ImportError("no module named numpyy", name="numpyy")

        module.__getattr__ = explode
        monkeypatch.setitem(sys.modules, SEAM, module)
        monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path), "--decompose"])
        with pytest.raises(ImportError):
            cli_main()

    def test_the_flag_refuses_a_run_with_no_central_case(
            self, tmp_path, monkeypatch, capsys, seam):
        monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path), "--decompose",
                                          "--no-deterministic"])
        assert cli_main() == 1
        assert ("Error: --decompose needs the deterministic run" in
                capsys.readouterr().err)

    def test_an_assemblers_refusal_reaches_both_surfaces(
            self, tmp_path, monkeypatch, capsys, seam):
        seam["outcome"] = dc.DecompositionRefusal(
            code="no_futures", reason="this run has no futures")
        config = _config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--decompose"])
        assert cli_main() == 0
        assert ("which risk decides it — not split (no_futures): this run has no "
                "futures" in capsys.readouterr().out)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--decompose", "--json"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["decomposition"]["refusal"]["code"] == "no_futures"

    def test_a_path_count_reaches_the_assembler_and_only_when_given(
            self, tmp_path, monkeypatch, capsys, seam):
        """`--decompose N` is the assembler's sample-size override (its own
        keyword, with a default), so the bare flag must keep the six-argument
        call intact — passing `paths=None` to a seam that has no such keyword
        would break a build that is otherwise fine.
        *Kills it:* always passing `paths`, or reading the bare flag's sentinel
        as a path count (`isinstance(True, int)` is True — hence a sentinel)."""
        config = _config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--decompose"])
        assert cli_main() == 0
        assert "paths" not in seam

        monkeypatch.setattr(sys, "argv", ["hde", config, "--decompose", "500"])
        assert cli_main() == 0
        assert seam["paths"] == 500

    def test_a_path_count_below_one_refuses_instead_of_being_passed_on(
            self, tmp_path, monkeypatch, capsys, seam):
        monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path), "--decompose=0"])
        assert cli_main() == 1
        assert ("Error: --decompose takes a path count of 1 or more, got 0"
                in capsys.readouterr().err)
        assert "paths" not in seam

    @pytest.mark.parametrize("argv, paths", [
        (["--decompose", "{config}"], None),
        (["--decompose", "{config}", "--json"], None),
        (["--decompose=300", "{config}"], 300),
        (["--decompose", "300", "{config}"], 300),
        (["{config}", "--decompose", "300"], 300),
        (["{config}", "--decompose=300"], 300),
        (["{config}", "--decompose"], None),
    ])
    def test_the_flag_goes_before_or_after_the_config(
            self, tmp_path, monkeypatch, capsys, seam, argv, paths):
        """`hde --decompose examples/x.yaml` exited 2 with an argparse error:
        the flag's optional count swallowed the config path and refused it as
        a number. The natural order works, and a count still reaches the
        assembler in every position it can be written.
        *Kills it:* typing the flag's value as an int again (the first case
        exits 2), or reading a config path as a count."""
        config = _config(tmp_path)
        monkeypatch.setattr(sys, "argv",
                            ["hde"] + [a.format(config=config) for a in argv])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert seam["spec"] is not None
        assert seam.get("paths") == paths
        if "--json" in argv:
            assert json.loads(out)["decomposition"]["spread"]["leading_channel_id"] == 6
        else:
            assert "which risk decides it — 2,000 futures" in out

    def test_a_count_that_is_not_a_number_is_still_refused_as_one(
            self, tmp_path, monkeypatch, capsys, seam):
        """The widening of the fix above: with the config already given, the
        token after the flag can only be a malformed count, and it refuses as
        one — it is never taken for a second config.
        *Kills it:* accepting any non-numeric token as the config."""
        monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path), "--decompose",
                                          "abc"])
        with pytest.raises(SystemExit) as raised:
            cli_main()
        assert raised.value.code == 2
        assert "argument --decompose: invalid int value: 'abc'" in (
            capsys.readouterr().err)
        assert "spec" not in seam

    def test_read_back_refuses_the_flag_before_anything_is_priced(
            self, tmp_path, monkeypatch, capsys, seam):
        """`--decompose --read-back` priced the whole decomposition and then
        printed only the read-back, which does not carry the block — a run
        that paid for an answer and showed none of it. It refuses up front,
        says why, and names the two routes that do print the block.
        *Kills it:* deleting the refusal (the seam is called and nothing
        prints), or moving it after the Monte Carlo run."""
        import hde.cli as cli_module

        def priced(*a, **k):
            raise AssertionError("the run was priced before the refusal")

        monkeypatch.setattr(cli_module, "run_monte_carlo", priced)
        monkeypatch.setattr(cli_module, "compute_deterministic", priced)
        for flags in (["--decompose", "--read-back"], ["--decompose=500", "--read-back",
                                                       "short"]):
            monkeypatch.setattr(sys, "argv", ["hde", _config(tmp_path)] + flags)
            assert cli_main() == 1
            captured = capsys.readouterr()
            assert ("Error: --decompose is not part of the read-back — --read-back "
                    "prints the read-back lines alone, so this run would price the "
                    "decomposition and show none of it. Run --decompose without "
                    "--read-back: the block prints under the report, or rides --json "
                    "as 'decomposition'") in captured.err
            assert captured.out == ""
            assert "spec" not in seam

    def test_read_back_alone_and_decompose_alone_are_both_still_legal(
            self, tmp_path, monkeypatch, capsys, seam):
        """The refusal above both ways: widened to any read-back-shaped flag,
        or to --json, it would refuse calls that were always legal.
        *Kills it:* refusing --read-back without --decompose, or --decompose
        with --json."""
        config = _config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--read-back"])
        assert cli_main() == 0
        assert capsys.readouterr().out.startswith("READ-BACK")
        assert "spec" not in seam
        monkeypatch.setattr(sys, "argv", ["hde", config, "--decompose", "--json"])
        assert cli_main() == 0
        assert "decomposition" in json.loads(capsys.readouterr().out)

    def test_the_help_points_at_the_one_prose_home(self, monkeypatch, capsys):
        """What each figure means lives in API_CONTRACT.md's decomposition
        section; the block prints no pointer, so the flag's help carries it,
        and the section it names exists.
        *Kills it:* dropping the pointer, or a pointer to a section that is
        not there."""
        monkeypatch.setattr(sys, "argv", ["hde", "--help"])
        with pytest.raises(SystemExit):
            cli_main()
        text = " ".join(capsys.readouterr().out.split())
        assert "--decompose" in text
        assert ("docs/reference/API_CONTRACT.md, the decomposition block") in text
        doc = (REPO / "docs" / "reference" / "API_CONTRACT.md").read_text(
            encoding="utf-8")
        assert "## The `decomposition` block" in doc


class TestTheRealAssemblerThroughTheFlag:
    """The reasons the assembler writes and this module prints, on the real
    engine, read off what the CLI prints. A refusal's reason is ONE author's
    sentence (§0.1 item 25): the assembler writes it and the formatter
    prefixes only its code."""

    FIXTURE = str(REPO / "tests" / "fixtures" / "uncertainty_surface.yaml")
    AGREED = str(REPO / "examples" / "mortgage_house_vs_rent.yaml")

    def test_a_path_free_run_prints_the_refusal_verbatim_and_no_route(
            self, monkeypatch, capsys):
        """*Kills it:* a route sentence appended by the formatter or restored
        in the assembler, or the two surfaces disagreeing."""
        monkeypatch.setattr(sys, "argv", ["hde", self.FIXTURE, "--decompose",
                                          "--no-monte-carlo"])
        assert cli_main() == 0
        line = _line(capsys.readouterr().out, "which risk decides it")
        assert line == "which risk decides it — not split (no_futures): this run has no futures"

        monkeypatch.setattr(sys, "argv", ["hde", self.FIXTURE, "--decompose",
                                          "--no-monte-carlo", "--json"])
        assert cli_main() == 0
        refusal = json.loads(capsys.readouterr().out)["decomposition"]["refusal"]
        assert refusal["code"] == "no_futures"
        assert line == f"which risk decides it — not split (no_futures): {refusal['reason']}"

    def test_an_identity_that_fails_prints_the_assemblers_refusal_verbatim(
            self, monkeypatch, capsys):
        """`identity_failed` (the all-frozen paths agree with each other and
        not with the central case) refuses the whole block, and its reason is
        the assembler's sentence, printed after its code with nothing added —
        on both surfaces. Forced on a real run by holding the identity to a
        budget of zero, which the all-frozen margin's measured rounding
        (compounding year by year against `(1 + g) ** years`) always exceeds.
        *Kills it:* a formatter that renders only the codes it knows, or one
        that appends to the reason."""
        import hde.decomposition_run as dr
        monkeypatch.setattr(dr, "identity_budget", lambda det, verdict: 0.0)
        basic = str(REPO / "examples" / "basic_config.yaml")
        monkeypatch.setattr(sys, "argv", ["hde", basic, "--decompose", "50", "--json"])
        assert cli_main() == 0
        refusal = json.loads(capsys.readouterr().out)["decomposition"]["refusal"]
        assert refusal["code"] == "identity_failed"
        assert refusal["reason"].startswith("with every channel frozen, the 50 paths "
                                            "price a margin of $")
        monkeypatch.setattr(sys, "argv", ["hde", basic, "--decompose", "50"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        assert _line(out, "which risk decides it") == (
            f"which risk decides it — not split (identity_failed): {refusal['reason']}")
        assert "THE SPREAD" not in out and "THE LEVEL" not in out

    def test_every_future_agreeing_prints_the_named_refusal_and_the_level(
            self, monkeypatch, capsys):
        """`mortgage_house_vs_rent.yaml` names the house cheapest in every
        future, so the spread register refuses by name and the level register
        prints under it — on stdout and in the JSON.
        *Kills it:* dropping the refusal (a table of shares over a margin that
        never changes sides), or dropping the level register with it."""
        monkeypatch.setattr(sys, "argv", ["hde", self.AGREED, "--decompose", "200"])
        assert cli_main() == 0
        lines = capsys.readouterr().out.splitlines()
        heading = lines.index("  THE SPREAD")
        reason = "house is cheapest in all 200 of these futures"
        assert lines[heading + 1] == f"  not split (no_sign_variation): {reason}"
        assert lines[heading + 3] == "  THE LEVEL — the first 200 of these futures"
        assert not any("with interaction" in line for line in lines)

        monkeypatch.setattr(sys, "argv", ["hde", self.AGREED, "--decompose", "200",
                                          "--json"])
        assert cli_main() == 0
        block = json.loads(capsys.readouterr().out)["decomposition"]
        assert block["spread"] == {"refusal": {"code": "no_sign_variation",
                                               "reason": reason},
                                   "structural_zeros": []}
        assert block["level"]["rows"] and block["level"]["paths"] == 200
