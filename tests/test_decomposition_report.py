"""The `--decompose` block, asserted on the STRING a user sees.

Every test here reads the rendered output, not the code that produced it: this
repo's own calibration record says one mutation aimed at the rendered output
beat thirty-four aimed inside the code. So the literals are spelled out,
presence AND absence are both asserted, and the mutations each test is meant to
kill are named on it.

The data is hand-built (`decomposition_households.py`): the rendering is pinned
independently of whether the estimators are right, because a test that ran them
would fail when an estimator changed and say nothing about what a household
reads. The few tests that DO run the real assembler, through the CLI, are the
ones whose subject is the sentence the assembler writes and this module prints.
"""
import ast
import dataclasses
import difflib
import importlib.machinery
import inspect
import json
import pathlib
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
which risk decides it — 2,000 futures, 7 channels live
  best guess says rent by $31,349 (7.8% of rent PV); most futures say condo (57% cheapest) — the two disagree, not decisive [hde verdict rule]
  that margin averages -$67,194 across those 2,000 futures and scatters by $286,506 (1 s.d.) — 9.1x the margin itself

  THE SPREAD — where the $286,506 comes from
  channel                 alone               with interaction          changes sides
  the renter's portfolio  0.88 [0.78, 1.00]   0.84 [0.75, 0.95]    40.6% [38.4, 42.8]
      sized by simulation.investment_return_vol=10% [assistant]
  the housing market      0.14 [0.11, 0.17]   0.13 [0.10, 0.16]    13.0% [11.5, 14.5]
      sized by simulation.value_growth_vol=7% [assistant]; condo.price_shock.annual_hazard=3% [assistant]; house.price_shock.annual_hazard=3% [assistant]; condo.price_shock.severity_vol=10% [anchor: price_shock.severity_vol]; house.price_shock.severity_vol=10% [anchor: price_shock.severity_vol]
  your tenancy            0.10 [0.08, 0.12]   0.09 [0.07, 0.11]    13.0% [11.5, 14.5]
      sized by rent.reset_hazard=7%/yr [assistant]; simulation.rent_escalation_vol=6% [assistant]; simulation.other_cost_vol=10% [assistant]; rent.events.moving_costs.cost_vol=20% [assistant]
  the population          0.03 [0.02, 0.05]   0.03 [0.02, 0.05]       6.0% [5.0, 7.0]
      sized by market_scenario.path [assistant] (the prior's own rows carry their citations); market_scenario.geography=MTL_RMR [user]
  the condo's costs       0.01 [0.01, 0.02]   0.01 [0.01, 0.02]       4.0% [3.1, 4.9]
      sized by simulation.condo_fee_vol=8% [assistant]; simulation.other_cost_vol=10% [assistant]; condo.events.special_assessment.cost_vol=25% [assistant]
  the economy             0.01 [-0.002, 0.01] 0.01 [0.00, 0.01]       4.0% [3.1, 4.9]
      sized by economic.inflation_vol=1.2% [assistant]; simulation.corr_inflation_condo=0.5 [assistant] (rho²=0.25 of the condo fee shock); simulation.condo_fee_vol=8% [assistant]; simulation.corr_inflation_house=0.5 [assistant] (rho²=0.25 of the house maintenance shock); simulation.house_maintenance_vol=20% [assistant]; simulation.corr_inflation_other=0.4 [assistant] (rho²=0.16 of each other-cost shock); simulation.other_cost_vol=10% [assistant]; simulation.corr_inflation_event_cost=0.3 [assistant] (rho²=0.09 of each event-cost shock)
  the house's costs       not resolved        not resolved            0.4% [0.1, 0.7]
      -0.001 [-0.002, 0.001] alone and -0.002 [-0.003, 0.002] with interaction, at 2,000 futures
      sized by simulation.house_maintenance_vol=20% [assistant]; simulation.other_cost_vol=10% [assistant]; house.events.roof_replacement.cost_vol=20% [assistant]
  the first-order shares add to 1.16 [1.04, 1.31] — above the whole, so interaction is not measurable at 2,000 futures: estimator noise, not a finding; raise simulation.num_sims
  the renter's portfolio's two figures are different kinds of number: 0.88 of the spread's variance, 40.6% of the futures changing sides [docs/reference/ARCHITECTURE.md figure glossary]

  THE LEVEL — what 2,000 futures price that the central case does not: a cost it leaves out, not a risk
  channel                 the margin moves by     P(rent cheapest), from 0.34
  your tenancy             +$125,074 (± $1,775)   -> 0.54
  the housing market        -$38,314 (± $2,252)   -> 0.28
  the population            +$11,064 (± $1,095)   -> 0.35
  the condo's costs          +$5,232 (± $786)     -> 0.35
  the house's costs            -$886 (± $179)     -> 0.35
  indistinguishable from zero at 2,000 futures: the renter's portfolio (-$3,805 ± $5,383, P -> 0.35), the economy (-$252 ± $642, P -> 0.34)
  on its own 2,000 paths: the central case rent by $31,349, the futures -$67,194, a $98,543 gap of which these 7 shifts account for $98,113; all 7 frozen reproduces the central case to 5.8e-11
  your tenancy (0.10 of the spread) moves the margin by +$125,074, and pricing it the central case's way takes P(rent cheapest) to 0.54 — that channel is why the central case and the futures name different winners
  the renter's portfolio is 0.88 of that spread and moves the margin by nothing that resolves (-$3,805 ± $5,383) — pure risk, and not a cost the central case left out

  NOT DRAWN IN THIS RUN — zero spread by construction, not by measurement
  your renewal rate — house.mortgage_renewal_rates (4.60%, 5.00%, 4.80%, 4.40%): a path you stated, not a distribution — the engine anchors no forward rate and draws none, so renewal carries no spread here at all
      replacing that path with one flat rate, inside a 1.00%–10.00% bracket [assistant] — solved on your own figures:
        the central case's winner changes from rent to house at 1.6052% — re-simulated there: condo 0.19, house 0.52, rent 0.29
        the runner-up changes from condo to house at 2.9549% — re-simulated there: condo 0.32, house 0.36, rent 0.31
      on the same axis, bisected on the futures rather than solved:
        the option most futures call cheapest changes from condo to house at 2.72%, where the futures sit at condo 0.34, house 0.34, rent 0.32 — bisected on 2,000 paths at seed 42, so it moves with the seed
      exact to 2.0e-15 of the option's own s.d. over 200 probe paths
      every grid point replaces the whole stated path with ONE figure applied at each renewal, so your stated path is not a point on that line
      no boundary printed for the decisiveness verdict — no value in the bracket clears the 65% floor, so there is nothing to cross
      on the same axis: your contract 4.35% [mortgage_rate.contracted_5y_uninsured]; today's posted 5-year 6.09% [mortgage_rate.posted_5y] — a list price to bracket a guess from above, never a ceiling on a 2031 renewal
  your income — income.pay_drop_events: it moves the affordability report, not either option's present value, so it cannot move this margin

  WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly
  house.mortgage_rate (house), stated 4.35%
      moving it inside a 1.00%–10.00% bracket [assistant] — solved on your own figures:
        the central case's winner changes from rent to house at 2.2518% — re-simulated there: condo 0.24, house 0.44, rent 0.32
      exact to 2.0e-15 of the option's own s.d. over 200 probe paths
      on the same axis: today's posted 5-year 6.09% [mortgage_rate.posted_5y]

  every channel above is sized by a figure the assistant chose, not by you, so this ranking is a property of widths you did not state — the figure to check first is simulation.investment_return_vol=10% [assistant]"""


def _render(**kwargs) -> str:
    return format_decomposition(uncertainty_surface(**kwargs))


def _line(block: str, needle: str) -> str:
    """The one line containing `needle` — a failure names the whole line."""
    hits = [line for line in block.splitlines() if needle in line]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


# ---------------------------------------------------------------------------
# The whole block
# ---------------------------------------------------------------------------

def test_the_block_is_this_text_and_nothing_else():
    """The strongest available assertion: every character a household reads.
    *Kills it:* any change to any figure, any column, any sentence."""
    assert format_decomposition(uncertainty_surface()) == FIXTURE_BLOCK


def test_silence_is_the_empty_string_not_an_empty_block():
    """§8 case 1 — the flag not passed, which is every run shipped today.
    *Kills it:* rendering a header, or a "nothing to report" line, for None."""
    assert format_decomposition(None) == ""


# ---------------------------------------------------------------------------
# THE BINDING — the spread table may never be emitted without the level
# register beside it (§5 mechanism 5, operator ruling 2026-09-22, test T7)
# ---------------------------------------------------------------------------

class TestTheBinding:
    def test_the_narrowest_public_entry_point_returns_both_registers(self):
        """Called the way any caller must call it, both registers come back —
        with their rows, not just their headings.
        *Kills it:* make the level block conditional on anything."""
        block = format_decomposition(uncertainty_surface())
        assert "  THE SPREAD — where the $286,506 comes from" in block
        assert ("  THE LEVEL — what 2,000 futures price that the central case does "
                "not: a cost it leaves out, not a risk") in block
        # the row a reader handed the spread table alone would never see
        assert "  your tenancy             +$125,074 (± $1,775)   -> 0.54" in block

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
# §0.1's four rulings on §7's draft
# ---------------------------------------------------------------------------

class TestTheRulingsOnTheDraft:
    def test_the_gap_is_the_subtraction_of_the_two_figures_printed_beside_it(self):
        """§0.1 ruling 2. The two figures are the LEVEL register's own
        (§0.1 ruling 1), and the header's E[f] is a different sample's — so a
        gap taken from the header would print $100,876, the draft's own error.
        *Kills it:* store the gap, or take it from `mean_margin`."""
        block = _render(mean_margin=-69527.0)
        assert ("  on its own 2,000 paths: the central case rent by $31,349, the "
                "futures -$67,194, a $98,543 gap of which these 7 shifts account for "
                "$98,113") in block
        assert "$100,876" not in block          # 31,349 − (−69,527): the draft's gap
        assert "-$69,527" in block              # the header's own sample, labelled
        assert "$98,543" in block and block.count("$98,543") == 1

    def test_one_stored_probability_at_one_rounding(self):
        """§0.1 ruling 2's second half: the level baseline is printed ONCE, at
        one rounding, instead of leading every row as `0.34 ->`.
        *Kills it:* restate the baseline per row, or print it at 4 decimals
        somewhere as well."""
        block = _render()
        assert "P(rent cheapest), from 0.34" in block
        assert block.count(", from 0.34") == 1
        assert "0.34 ->" not in block           # the draft's per-row restatement
        assert "0.3350" not in block            # verdict.prob_best's own rounding
        assert "0.341" not in block             # prob_best_base unrounded

    def test_the_ten_thousand_path_parenthetical_is_gone(self):
        """§0.1 ruling 3: no section licenses computing the decomposition twice.
        *Kills it:* re-adding "(at 10,000 they add to 1.02)"."""
        block = _render()
        assert "10,000" not in block
        assert "they add to" not in block
        assert block.count("the first-order shares add to") == 1

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
        assert "rho²=0.25 of the condo fee shock" in row


# ---------------------------------------------------------------------------
# The three §7-draft defects (§0.1 item 18)
# ---------------------------------------------------------------------------

class TestTheDraftDefectsOfItem18:
    def test_the_house_row_is_resolved_because_its_shift_is_five_se(self):
        """-$886 ± $179 is 4.95 SE and §3.4's rule is |Δ| > 2·SE, so it belongs
        in the table. §7's draft filed it under "indistinguishable from zero" —
        the draft printing a real effect as noise, which is the error this
        feature exists to prevent.
        *Kills it:* filing it back under the indistinguishable line."""
        block = _render()
        assert "  the house's costs            -$886 (± $179)     -> 0.35" in block
        assert _line(block, "indistinguishable from zero") == (
            "  indistinguishable from zero at 2,000 futures: the renter's portfolio "
            "(-$3,805 ± $5,383, P -> 0.35), the economy (-$252 ± $642, P -> 0.34)")

    def test_the_renewal_row_prints_its_bracket_and_whose_width_it_is(self):
        """`ExactReversal.bracket_source`: a bracket figure on a row with no
        source class is the honesty contract's own breach, and the bracket is
        what converts an honest refusal into an answer (§6, 2026-09-21).
        *Kills it:* printing the solved rates without the bracket."""
        block = _render()
        assert ("      replacing that path with one flat rate, inside a 1.00%–10.00% "
                "bracket [assistant] — solved on your own figures:") in block

    def test_the_contract_rate_gets_its_own_row(self):
        """§6 licenses `<opt>.mortgage_rate` for slice 1 and measures it at the
        same 2.0e-15; §7's draft renders nothing for it.
        *Kills it:* rendering only the reversals a structural zero joins."""
        block = _render()
        assert "  house.mortgage_rate (house), stated 4.35%" in block
        assert ("        the central case's winner changes from rent to house at "
                "2.2518% — re-simulated there: condo 0.24, house 0.44, rent 0.32"
                ) in block


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
        and §3.3 plus §0.1 item 10: it carries its interval, which
        §7's draft omits. A point estimate with no width, beside neighbours
        that all carry one, reads as the most certain number in the table.
        *Kills it:* dropping the column, dropping it only where the shares did
        not resolve, or printing the point estimate bare."""
        block = _render()
        assert ("  channel                 alone               with interaction     "
                "     changes sides") in block
        for cell in ("40.6% [38.4, 42.8]", "13.0% [11.5, 14.5]", "6.0% [5.0, 7.0]",
                     "4.0% [3.1, 4.9]", "0.4% [0.1, 0.7]"):
            assert cell in block, cell
        assert _line(block, "the house's costs       not resolved").endswith(
            "0.4% [0.1, 0.7]")

    def test_an_unresolved_share_never_appears_as_a_number_in_a_column(self):
        """§7 rule 6 and §4's no-clamp rule: the estimates are kept, printed in
        their own words, and never rounded into `-0.00`.
        *Kills it:* rendering `provisional_alone` in the `alone` column, or
        clamping it to 0.00."""
        block = _render()
        assert ("  the house's costs       not resolved        not resolved       "
                "     0.4% [0.1, 0.7]") in block
        assert ("      -0.001 [-0.002, 0.001] alone and -0.002 [-0.003, 0.002] with "
                "interaction, at 2,000 futures") in block
        assert "-0.00 " not in block and "-0.00]" not in block

    def test_the_residual_line_is_printed_and_takes_its_refusal_branch(self):
        """§7 rule 5 / §4: on this fixture at its committed 2,000 paths the
        shares sum above 1 and no residual may print.
        *Kills it:* clamping ΣS to 1 (the refusal becomes unreachable), or
        printing a residual on the refused branch."""
        refused = _render()
        assert ("  the first-order shares add to 1.16 [1.04, 1.31] — above the whole, "
                "so interaction is not measurable at 2,000 futures: estimator noise, "
                "not a finding; raise simulation.num_sims") in refused
        assert "no single channel owns" not in refused
        assert "residual" not in refused

        resolved = _render(interaction=resolved_interaction())
        assert ("  the first-order shares add to 0.95 [0.92, 0.98], leaving 0.05 "
                "[0.02, 0.08] that no single channel owns; 0.94 of the shares above is "
                "a sum over channels sized entirely by figures the assistant chose"
                ) in resolved
        assert "estimator noise" not in resolved

    def test_the_assistant_typed_sum_cannot_print_on_the_refused_branch(self):
        """§5 mechanism 4: on the refused branch that figure is noise, and the
        type carries no field for it there."""
        assert "0.94" not in _render()

    def test_every_row_carries_its_widths_inline_on_that_row(self):
        """§7 rule 7 / §5 mechanism 1: a reader cannot see the ranking without
        seeing whose numbers produced it.
        *Kills it:* moving the widths to a trailing footnote, or dropping one."""
        block = _render()
        lines = block.splitlines()
        for row in uncertainty_surface().spread.rows:
            label = dc.channel(row.channel_id).label
            start = next(i for i, line in enumerate(lines)
                         if line.startswith(f"  {label} "))
            body = "\n".join(lines[start:start + 4])
            for width in row.widths:
                assert width.key in body, (label, width.key)
                assert f"[{width.source}" in body or f"[{width.source}:" in body

    def test_an_anchored_width_names_its_anchor(self):
        assert ("condo.price_shock.severity_vol=10% [anchor: price_shock.severity_vol]"
                in _render())

    def test_a_width_with_no_figure_prints_its_key_alone(self):
        assert "market_scenario.path [assistant]" in _render()


# ---------------------------------------------------------------------------
# §7 rule 2 — one closing branch per verdict STATE, chosen by `verdict.state`
# ---------------------------------------------------------------------------

class TestTheClosingSentenceBranchesOnTheVerdictState:
    def test_a_disagreement_names_the_channel_that_split_the_two(self):
        block = _render()
        assert ("  your tenancy (0.10 of the spread) moves the margin by +$125,074, "
                "and pricing it the central case's way takes P(rent cheapest) to 0.54 "
                "— that channel is why the central case and the futures name different "
                "winners") in block
        assert ("  the renter's portfolio is 0.88 of that spread and moves the margin "
                "by nothing that resolves (-$3,805 ± $5,383) — pure risk, and not a "
                "cost the central case left out") in block

    def test_the_causal_clause_is_licensed_by_the_frozen_probability(self):
        """The one comparison this module makes: the clause may be written only
        when pricing that channel the central case's way puts `best` back in
        front of most futures.
        *Kills it:* writing the clause unconditionally."""
        dec = uncertainty_surface()
        rows = tuple(
            dc.LevelRow(channel_id=r.channel_id,
                        level=dc.ResolvedLevel(delta=r.level.delta, se=r.level.se,
                                               prob_best_frozen=0.44))
            if r.channel_id == 5 else r
            for r in dec.level.rows
        )
        weaker = dataclasses.replace(
            dec, level=dataclasses.replace(dec.level, rows=rows))
        block = format_decomposition(weaker)
        assert "takes P(rent cheapest) to 0.44" in block
        assert "name different winners" not in block

    def test_an_option_state_says_the_decisiveness_survives(self):
        """A sentence written for the disagreement mechanism would be false
        here, which is §1's failure in miniature.
        *Kills it:* one branch for all three states."""
        block = format_decomposition(two_channel_option_state())
        assert ("  condo is cheapest either way, and the largest shift is the condo's "
                "costs (0.62 of the spread), +$8,940: with it priced the central "
                "case's way P(condo cheapest) is 0.93 against 0.81 as drawn") in block
        assert "disagree" not in block
        assert "name different winners" not in block

    def test_a_tie_names_the_channel_that_would_move_it_out(self):
        dec = two_channel_option_state()
        tied = dataclasses.replace(
            dec, verdict=dataclasses.replace(dec.verdict, state="tie", decisive=False))
        block = format_decomposition(tied)
        assert ("  this run is too close to call as drawn, and the largest single "
                "shift is the condo's costs (0.62 of the spread), +$8,940, taking "
                "P(condo cheapest) to 0.93 — the channel to check before trusting the "
                "tie") in block

    def test_no_resolved_shift_says_so_rather_than_naming_a_channel(self):
        dec = two_channel_option_state()
        flat = dataclasses.replace(dec, level=dataclasses.replace(
            dec.level,
            rows=tuple(dc.LevelRow(channel_id=r.channel_id,
                                   level=dc.IndistinguishableLevel(
                                       provisional_delta=r.level.delta,
                                       se=r.level.se,
                                       prob_best_frozen=r.level.prob_best_frozen))
                       for r in dec.level.rows),
            leading_channel_id=None,
        ))
        block = format_decomposition(flat)
        assert ("  no channel's shift resolves at 1,500 futures, so this run cannot "
                "say which one the futures price and the central case does not") in block
        assert "either way" not in block


# ---------------------------------------------------------------------------
# §5 mechanism 3 — the superlative is gated on provenance (test T14)
# ---------------------------------------------------------------------------

class TestTheProvenanceGate:
    def test_assistant_typed_widths_forbid_the_superlative_and_name_the_figure(self):
        block = _render()
        assert ("  every channel above is sized by a figure the assistant chose, not "
                "by you, so this ranking is a property of widths you did not state — "
                "the figure to check first is simulation.investment_return_vol=10% "
                "[assistant]") in block
        assert "decides the spread of this answer" not in block

    def test_user_stated_widths_license_it_and_the_sentence_changes(self):
        """T14: change one `sources:` entry and the sentence changes, while the
        table is otherwise identical.
        *Kills it:* hardcoding either sentence, or inferring the class from the
        key's name."""
        block = format_decomposition(two_channel_option_state())
        assert ("  the condo's costs decides the spread of this answer, and every "
                "width behind that row is yours or an anchor's") in block
        assert "the figure to check first" not in block

    def test_a_partly_guessed_table_counts_the_rows_rather_than_saying_every(self):
        dec = two_channel_option_state()
        rows = (dec.spread.rows[0],
                dataclasses.replace(
                    dec.spread.rows[1],
                    widths=(dc.Width(key="simulation.house_maintenance_vol",
                                     formatted="9%", source="assistant"),)))
        partly = dataclasses.replace(dec, spread=dataclasses.replace(
            dec.spread, rows=rows, superlative_licensed=False, check_first=None))
        assert ("  1 of the 2 channels above are sized by a figure the assistant "
                "chose, not by you, so this ranking is a property of widths you did "
                "not state") in format_decomposition(partly)


# ---------------------------------------------------------------------------
# §8's refusals — RENDERED here, decided by the assembler
# ---------------------------------------------------------------------------

class TestRefusalsAreRenderedWithTheirReason:
    @pytest.mark.parametrize("code", dc.REFUSAL_CODES)
    def test_every_refusal_code_prints_its_own_reason_and_no_table(self, code):
        """*Kills it:* letting any refusal fall through to silence, or printing
        an empty register beside it."""
        out = format_decomposition(dc.DecompositionRefusal(
            code=code, reason=f"the {code} condition fired on this run"))
        assert f"the {code} condition fired on this run" in out
        assert "THE SPREAD" not in out and "THE LEVEL" not in out

    def test_the_one_channel_refusal_names_the_channel_carrying_the_spread(self):
        """§8 refusal 4: the channel is NAMED and no numbers print."""
        out = format_decomposition(dc.DecompositionRefusal(
            code="one_channel", channel_id=3,
            reason="one channel carries all of it, so there is nothing to split"))
        assert out == ("the condo's costs carries all of this run's spread — not "
                       "split: one channel carries all of it, so there is nothing to "
                       "split")

    def test_a_refused_boundary_is_named_rather_than_dropped(self):
        """§8 refusal 7: a boundary that vanishes with no row is an absence a
        reader reads as "nothing here".
        *Kills it:* dropping `refused_boundaries` from the render."""
        assert ("      no boundary printed for the decisiveness verdict — no value in "
                "the bracket clears the 65% floor, so there is nothing to cross"
                ) in _render()

    def test_a_refused_spread_prints_its_reason_verbatim_and_the_level_still_prints(
            self):
        """§0.1 item 7: `P(f > 0) == 1` refuses the SPREAD register by name
        while the level and reversal registers still print — the binding runs
        one way, so a refused spread beside a printed level is the honest
        shape. The reason is the ASSEMBLER's and prints verbatim, directly
        under the spread's heading; the verdict's own `prob_best` (0.335 here,
        another sample) is not consulted, because the refusal already says
        what its data showed.
        *Kills it:* printing an empty table with a column header and no rows,
        writing a sentence of the formatter's own, printing the provenance
        sentence about a ranking that did not print, or dropping the level
        register along with the shares."""
        dec = uncertainty_surface()
        reason = ("no share is apportioned: rent is cheapest in all 2,000 of these "
                  "futures, and this sentence is the assembler's")
        refused = dataclasses.replace(
            dec, spread=dc.RefusedSpread(code="no_sign_variation", reason=reason))
        block = format_decomposition(refused)
        lines = block.splitlines()
        heading = lines.index("  THE SPREAD — where the $286,506 comes from")
        assert lines[heading + 1] == f"  {reason}"
        assert lines[heading + 2] == ""
        assert lines[heading + 3].startswith("  THE LEVEL — what 2,000 futures price")
        assert block.count(reason) == 1
        assert "with interaction" not in block      # no header over no rows
        assert "the first-order shares add to" not in block
        assert "different kinds of number" not in block
        assert "not resolved" not in block
        assert "  your tenancy             +$125,074 (± $1,775)   -> 0.54" in block
        # the closing level sentence names the mover without a share it no
        # longer has, and the leader of a table that did not print is not named
        assert ("  your tenancy moves the margin by +$125,074, and pricing it the "
                "central case's way takes P(rent cheapest) to 0.54") in block
        assert "pure risk" not in block
        # a ranking that did not print has no provenance sentence to carry
        assert "this ranking is a property of widths" not in block
        assert "decides the spread of this answer" not in block
        # the reversal register still prints
        assert "  NOT DRAWN IN THIS RUN" in block

    def test_an_empty_spread_register_raises_rather_than_printing_over_nothing(self):
        """A `SpreadRegister` with no rows is a state no producer emits: a spread
        with nothing to show arrives as `RefusedSpread`, carrying its reason. A
        heading over no rows would leave the reader to infer why, so the
        formatter refuses the object rather than guess at a sentence.
        *Kills it:* rendering the heading over nothing, or reviving a sentence
        of the formatter's own for the empty case."""
        dec = uncertainty_surface()
        empty = dataclasses.replace(
            dec, spread=dataclasses.replace(dec.spread, rows=(),
                                            leading_channel_id=None, check_first=None))
        with pytest.raises(ValueError, match="RefusedSpread"):
            format_decomposition(empty)

    def test_a_spread_register_of_neither_type_raises(self):
        dec = uncertainty_surface()
        with pytest.raises(TypeError, match="neither a SpreadRegister nor a RefusedSpread"):
            format_decomposition(dataclasses.replace(dec, spread=dec.level))

    def test_a_structural_zero_renders_without_the_reversal_it_would_join(self):
        """A zero with `reversal_key=None` — a stated path with no solved row
        behind it — must render from what is present.
        *Kills it:* assuming the join, which raises rather than prints."""
        dec = uncertainty_surface()
        zeros = tuple(dataclasses.replace(z, reversal_key=None)
                      for z in dec.reversal.structural_zeros)
        block = format_decomposition(dataclasses.replace(
            dec, reversal=dc.ReversalRegister(exact=(), estimated=(),
                                              structural_zeros=zeros)))
        assert ("  your renewal rate — house.mortgage_renewal_rates (4.60%, 5.00%, "
                "4.80%, 4.40%): a path you stated, not a distribution") in block
        assert "replacing that path with one flat rate" not in block
        assert "1.61%" not in block

    def test_an_empty_reversal_register_says_it_found_no_candidate(self):
        block = format_decomposition(two_channel_option_state())
        assert ("  NOTHING STATED IN THIS RUN CARRIES A REVERSAL DISTANCE the engine "
                "can solve — no candidate was found, which is not a finding that "
                "nothing would reverse the verdict") in block


class TestTheTwoReversalKindsAreNeverOneTable:
    """§0's ruling: the rows GROUP by exactness and are never ranked across the
    split, because ordering a rate against a rent would need a plausibility
    magnitude the registry has none of."""

    def test_each_kind_prints_under_its_own_heading_with_its_own_evidence(self):
        block = format_decomposition(seven_channel_other_household())
        exact_at = block.index("  WHAT WOULD HAVE TO CHANGE — keys the engine "
                               "re-prices exactly")
        estimated_at = block.index("  WHAT WOULD HAVE TO CHANGE — keys the engine can "
                                   "only re-price by re-simulating, each distance "
                                   "inside an interval")
        assert exact_at < estimated_at        # no interleaving, no shared ordering
        assert ("      exact to 3.1e-15 of the option's own s.d. over 200 probe paths"
                in block)
        assert ("      the exactness gate refused this key at 1.8e+00 of the option's "
                "own s.d., so the distance is estimated") in block

    def test_a_sampled_crossing_never_reads_as_a_solved_one(self):
        """§0.1 item 24, one level down: `best` and `runner_up`
        are solved on the deterministic verdict and came out identical to seven
        digits across five seeds, while `mc_best` is bisected on the Monte
        Carlo curve and moved 2.698%–2.805% over the same five. A reader given
        both in one typography is told a sample property is a config property —
        this feature's cardinal error committed by its own output.

        THREE distinctions, so it survives losing any one: four decimals
        against two, an explicit clause naming the sample, and the grouping.
        *Kills it:* one shape for both, or dropping any of the three."""
        block = _render()
        assert ("        the central case's winner changes from rent to house at "
                "1.6052% — re-simulated there: condo 0.19, house 0.52, rent 0.29"
                ) in block
        assert ("        the runner-up changes from condo to house at 2.9549% — "
                "re-simulated there: condo 0.32, house 0.36, rent 0.31") in block
        assert ("      on the same axis, bisected on the futures rather than solved:"
                ) in block
        assert ("        the option most futures call cheapest changes from condo to "
                "house at 2.72%, where the futures sit at condo 0.34, house 0.34, "
                "rent 0.32 — bisected on 2,000 paths at seed 42, so it moves with "
                "the seed") in block
        # the sampled figure never appears at the solved precision, and the
        # solved ones never carry the sampled clause
        assert "2.7164%" not in block
        assert "1.6052% — bisected" not in block
        assert block.index("1.6052%") < block.index("bisected on the futures")
        # and no hedge was invented for the seed-to-seed spread, which is not
        # a field of this type
        assert "2.698" not in block and "2.805" not in block

    def test_one_key_carries_both_kinds_and_decisive_is_a_sampled_one(self):
        """A licensed key carries both at once (contract, 2026-09-22), so the
        two group headings belong to ONE row. `decisive` is SAMPLED — it turns
        on `prob_best` against the anchored floor, which is a figure of the
        sample — so printing it at four decimals would be a solved typography
        on a sample property.
        *Kills it:* filing `decisive` with the solved kinds, or emitting one
        group heading per reversal row instead of per kind."""
        block = format_decomposition(seven_channel_other_household())
        row = block.index("  condo.mortgage_renewal_rates (condo), stated 5.20%, 5.40%")
        tail = block[row:block.index("      exact to 3.1e-15", row)]
        assert tail.count("WHAT WOULD HAVE TO CHANGE") == 0      # one row, two groups
        assert "— solved on your own figures:" in tail
        assert "bisected on the futures rather than solved:" in tail
        assert ("        the runner-up changes from house to rent at 5.0042% — "
                "re-simulated there: condo 0.59, rent 0.30") in tail
        assert ("        the decisiveness verdict changes from no to yes at 6.12%, "
                "where the futures sit at condo 0.65, rent 0.26 — bisected on 6,000 "
                "paths at seed 42, so it moves with the seed") in tail
        # the kinds keep BOUNDARY_FIELDS' order inside each group
        assert tail.index("the option most futures call cheapest") < tail.index(
            "the decisiveness verdict")

    def test_a_row_with_only_sampled_crossings_still_prints_its_bracket(self):
        """A bracket that does not appear is the same breach as one appearing
        with no source class, so the bracket prints on whichever group leads.
        *Kills it:* attaching the bracket to the solved group alone — the
        bracket then vanishes on every key whose crossings are all sampled."""
        dec = seven_channel_other_household()
        row = dec.reversal.exact[0]
        sampled_only = dataclasses.replace(row, boundaries=tuple(
            b for b in row.boundaries if isinstance(b, dc.SampledBoundary)))
        block = format_decomposition(dataclasses.replace(
            dec, reversal=dataclasses.replace(dec.reversal, exact=(sampled_only,))))
        assert ("      replacing that path with one flat rate, inside a 2.00%–12.00% "
                "bracket [assistant], bisected on the futures rather than solved:"
                ) in block
        assert "solved on your own figures" not in block

    def test_a_crossing_with_no_confirming_run_prints_alone(self):
        """A crossing whose `confirming_probabilities` is EMPTY prints alone.

        The library emits exactly this: `break_even.reversal_register` on a
        run with no futures (`mc=None`, or a single-path run) still answers
        with its solved half — `best` and `runner_up` read no path, so they
        come back as `SolvedBoundary` rows with nothing to confirm them
        against, and the register is NOT empty there. `--decompose` never
        hands the formatter that register: it refuses the whole block with
        `no_futures` before any register is built (§0.1 item 25). So this
        defends the library shape, which the deterministic renewal-flip line
        reaches without futures, rather than a state the flag produces today.
        *Kills it:* rendering "re-simulated there:" with nothing after it, or
        dropping the crossing because it has no probabilities."""
        dec = uncertainty_surface()
        renewal = dec.reversal.exact[0]
        bare = dataclasses.replace(renewal, boundaries=tuple(
            dataclasses.replace(b, confirming_probabilities=())
            for b in renewal.boundaries if isinstance(b, dc.SolvedBoundary)))
        block = format_decomposition(dataclasses.replace(
            dec, reversal=dataclasses.replace(dec.reversal, exact=(bare,))))
        assert ("        the central case's winner changes from rent to house at "
                "1.6052%\n") in block
        assert "re-simulated there" not in block
        assert "no futures" not in block        # no invented explanation

    def test_a_crossing_of_neither_kind_raises_rather_than_vanishing(self):
        """An `isinstance` filter drops whatever it did not foresee, and every
        crossing of that type then vanishes with no row saying so — on a key
        whose crossings were ALL of it, the row reads as if nothing were solved
        there. So a boundary that is neither `SolvedBoundary` nor
        `SampledBoundary` raises, naming its type and its row.
        *Kills it:* removing the raise, which drops the crossing silently."""
        dec = uncertainty_surface()
        renewal = dec.reversal.exact[0]
        stray = dc.EstimatedBoundary(
            verdict_field="best", value=0.016,
            value_ci=dc.Interval(low=0.015, high=0.017),
            was="rent", becomes="house", resimulation_paths=500)
        odd = dataclasses.replace(renewal, boundaries=renewal.boundaries + (stray,))
        with pytest.raises(TypeError) as raised:
            format_decomposition(dataclasses.replace(
                dec, reversal=dataclasses.replace(dec.reversal, exact=(odd,))))
        assert "house.mortgage_renewal_rates's exact reversal row" in str(raised.value)
        assert "EstimatedBoundary" in str(raised.value)
        # ...and only the stray: the same row without it renders in full
        assert "at 1.6052%" in format_decomposition(dec)

    def test_an_estimated_row_carrying_a_solved_crossing_raises(self):
        """The sibling of the case above, one tuple over: an estimated row's
        crossings are `EstimatedBoundary`, and anything else raises rather
        than printing in the estimated row's vocabulary."""
        dec = seven_channel_other_household()
        row = dec.reversal.estimated[0]
        solved = dc.SolvedBoundary(verdict_field="best", value=0.014, was="condo",
                                   becomes="house", confirming_probabilities=())
        odd = dataclasses.replace(row, boundaries=row.boundaries + (solved,))
        with pytest.raises(TypeError, match="estimated reversal row carries a "
                                            "SolvedBoundary"):
            format_decomposition(dataclasses.replace(
                dec, reversal=dataclasses.replace(dec.reversal, estimated=(odd,))))

    def test_a_level_row_of_neither_kind_raises_rather_than_vanishing(self):
        """The level rows are filed by type into two groups; a row of a third
        type would fall through both and never print."""
        dec = uncertainty_surface()
        stray = dc.LevelRow(channel_id=0, level=dc.Interval(low=0.0, high=1.0))
        odd = dataclasses.replace(dec, level=dataclasses.replace(
            dec.level, rows=dec.level.rows + (stray,)))
        with pytest.raises(TypeError, match="not a ResolvedLevel or "
                                            "IndistinguishableLevel"):
            format_decomposition(odd)

    def test_an_estimated_boundary_prints_its_interval_and_its_sample(self):
        assert ("        the central case's winner changes from condo to house at "
                "1.42%, inside 1.19%–1.68% on 3,000 re-simulated paths"
                ) in format_decomposition(seven_channel_other_household())

    def test_a_dead_draw_zero_prints_its_reason_and_not_a_measured_zero(self):
        """§3.5's third kind: a channel that draws every year and reaches no
        cash flow. A measured `0.00` in that row would read as "inflation does
        not matter", which is not what is true."""
        block = format_decomposition(seven_channel_other_household())
        assert ("  the economy — economic.inflation_vol, "
                "simulation.corr_inflation_condo: this run is in real terms and every "
                "inflation correlation is zero, so the draw happens every year and "
                "reaches no cash flow") in block

    def test_a_share_above_one_is_unresolved_and_is_not_clamped(self):
        """§4: no share is ever clamped into [0, 1] — in either direction."""
        block = format_decomposition(seven_channel_other_household())
        assert ("  the economy             not resolved        not resolved       "
                "     0.2% [0.1, 0.3]") in block
        assert ("      1.00 [1.00, 1.01] alone and 1.01 [1.00, 1.01] with interaction, "
                "at 6,000 futures") in block


# ---------------------------------------------------------------------------
# One home per truth
# ---------------------------------------------------------------------------

def test_the_verdict_sentence_is_the_verdicts_own_reason_verbatim():
    """`models.Verdict.reason` is that sentence's one home; rebuilding it here
    would be a second statement of one truth.
    *Kills it:* composing the header sentence from the verdict's scalars."""
    dec = uncertainty_surface()
    assert f"  {dec.verdict.reason}" in format_decomposition(dec)


def test_the_column_definitions_are_cited_once_rather_than_restated():
    """CONDITIONALITY: a clause true on every run that prints the block belongs
    cited once. The citation names a file that exists and a section in it."""
    from pathlib import Path
    block = _render()
    assert block.count(dt.GLOSSARY) == 1
    doc = Path(__file__).resolve().parents[1] / "docs" / "reference" / "ARCHITECTURE.md"
    assert "## Figure glossary" in doc.read_text(encoding="utf-8")
    assert "### Which risk decides it" in doc.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The `--json` block (serialization.decomposition_to_dict)
# ---------------------------------------------------------------------------

class TestTheJsonBlock:
    def test_the_three_registers_are_emitted_together(self):
        """The binding in this surface's own terms: a consumer cannot get the
        spread rows without the level rows beside them."""
        doc = decomposition_to_dict(uncertainty_surface())
        assert set(doc) == {"paths", "live_channel_ids", "mean_margin", "sd_margin",
                            "spread", "level", "reversal"}
        assert doc["spread"]["rows"] and doc["level"]["rows"]
        assert set(doc["reversal"]) == {"exact", "estimated", "structural_zeros"}

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
        assert "unstated_first_order_sum" not in doc["spread"]["interaction"]
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

    def test_the_two_reversal_kinds_stay_two_lists(self):
        doc = decomposition_to_dict(seven_channel_other_household())
        assert [row["key"] for row in doc["reversal"]["exact"]] == [
            "condo.mortgage_renewal_rates"]
        assert [row["key"] for row in doc["reversal"]["estimated"]] == [
            "house.value_growth_rate"]
        assert doc["reversal"]["exact"][0]["bracket_source"] == "assistant"
        assert doc["reversal"]["exact"][0]["refused_boundaries"][0]["verdict_field"] \
            == "best"

    def test_the_block_is_json_serialisable(self):
        json.dumps(decomposition_to_dict(uncertainty_surface()))
        json.dumps(decomposition_to_dict(seven_channel_other_household()))

    def test_a_refused_spread_is_a_refusal_in_the_spread_slot_with_no_rows(self):
        """§0.1 item 7 in this surface's terms: the refusal sits where the
        register would, with its code and reason, and there is no `rows` key
        for a consumer to read as "nothing to report". The level register
        still travels beside it.
        *Kills it:* serializing the refusal as an empty register."""
        dec = uncertainty_surface()
        doc = decomposition_to_dict(dataclasses.replace(
            dec, spread=dc.RefusedSpread(code="no_sign_variation",
                                         reason="nothing to split")))
        assert doc["spread"] == {"refusal": {"code": "no_sign_variation",
                                             "reason": "nothing to split"}}
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
        on a whole-block refusal, on a refused spread, on both reversal kinds —
        and every refusal code is named in API_CONTRACT.md's `decomposition`
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
            spread=dc.RefusedSpread(code="no_sign_variation", reason="r"))
        for outcome in (uncertainty_surface(), seven_channel_other_household(),
                        two_channel_option_state(), agreed,
                        uncertainty_surface(interaction=resolved_interaction()),
                        dc.DecompositionRefusal(code="one_channel", reason="r",
                                                channel_id=3)):
            walk(decomposition_to_dict(outcome))
        assert sorted(k for k in keys if f"`{k}`" not in section) == []
        for code in dc.REFUSAL_CODES + dc.SPREAD_REFUSAL_CODES:
            assert f"`{code}`" in section, code


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
            code="no_futures", reason="this run has no futures to split")
        config = _config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["hde", config, "--decompose"])
        assert cli_main() == 0
        assert ("which risk decides it — not split: this run has no futures to split"
                in capsys.readouterr().out)
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

    def test_the_flag_is_in_the_help_the_docs_are_checked_against(
            self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["hde", "--help"])
        with pytest.raises(SystemExit):
            cli_main()
        assert "--decompose" in capsys.readouterr().out


class TestTheRealAssemblerThroughTheFlag:
    """The sentences the assembler writes and this module prints, on the real
    engine, read off what the CLI prints. The refusal's reason is ONE author's
    sentence (§0.1 item 25): the assembler writes it and the formatter
    appends nothing."""

    FIXTURE = str(REPO / "tests" / "fixtures" / "uncertainty_surface.yaml")
    AGREED = str(REPO / "examples" / "mortgage_house_vs_rent.yaml")

    def test_a_path_free_run_prints_the_refusal_verbatim_and_names_the_route(
            self, monkeypatch, capsys):
        """*Kills it:* a route sentence appended by the formatter (the line
        would then carry `--break-even` twice, or read past the reason), or a
        route dropped by the assembler."""
        monkeypatch.setattr(sys, "argv", ["hde", self.FIXTURE, "--decompose",
                                          "--no-monte-carlo"])
        assert cli_main() == 0
        line = _line(capsys.readouterr().out, "which risk decides it")
        assert line == (
            "which risk decides it — not split: there are no futures to decompose: "
            "this run priced the central case only (--no-monte-carlo, or every "
            "uncertainty input is off). The deterministic line is the whole answer "
            "here. What would have to change for that answer to change needs no "
            "futures: --sweep <key>=<values> prints the verdict at each point of a "
            "grid and says where the cheapest option flips, and --break-even <key> "
            "solves the crossing exactly with the solver this block's reversal "
            "register uses — one pair of options at a time, so on this three-option "
            "config it needs one option's section dropped first.")
        assert line.count("--break-even") == 1 and line.count("--sweep") == 1

        monkeypatch.setattr(sys, "argv", ["hde", self.FIXTURE, "--decompose",
                                          "--no-monte-carlo", "--json"])
        assert cli_main() == 0
        refusal = json.loads(capsys.readouterr().out)["decomposition"]["refusal"]
        assert refusal["code"] == "no_futures"
        assert line == f"which risk decides it — not split: {refusal['reason']}"

    def test_every_future_agreeing_prints_the_named_refusal_and_the_level(
            self, monkeypatch, capsys):
        """`mortgage_house_vs_rent.yaml` names the house cheapest in every
        future, so the spread register refuses by name and the level register
        prints under it — on stdout and in the JSON.
        *Kills it:* dropping the refusal (a table of shares over a margin that
        never changes sides), or dropping the level register with it."""
        monkeypatch.setattr(sys, "argv", ["hde", self.AGREED, "--decompose", "200"])
        assert cli_main() == 0
        out = capsys.readouterr().out
        lines = out.splitlines()
        heading = next(i for i, line in enumerate(lines)
                       if line.startswith("  THE SPREAD — where the "))
        reason = ("no share is apportioned: house is cheapest in all 200 of these "
                  "futures, so none sits across the line for a channel to have "
                  "moved it there — there is nothing to split in decision space. "
                  "The shares themselves are defined; they would rank the scatter "
                  "of a margin that never changes the answer.")
        assert lines[heading + 1] == f"  {reason}"
        assert lines[heading + 3].startswith(
            "  THE LEVEL — what 200 futures price that the central case does not")
        assert "with interaction" not in out and "changes sides" not in out

        monkeypatch.setattr(sys, "argv", ["hde", self.AGREED, "--decompose", "200",
                                          "--json"])
        assert cli_main() == 0
        block = json.loads(capsys.readouterr().out)["decomposition"]
        assert block["spread"] == {"refusal": {"code": "no_sign_variation",
                                               "reason": reason}}
        assert block["level"]["rows"] and block["level"]["paths"] == 200


# ---------------------------------------------------------------------------
# The measurement the block is judged on
# ---------------------------------------------------------------------------

def _invariant_fraction(first: str, second: str, *, run: int = 20) -> float:
    """The fraction of the SHORTER block that also appears in the other as a
    run of at least `run` identical characters.

    The run floor is the whole method's honesty: `SequenceMatcher`'s raw
    matching total counts every coincidental " the " and reports 0.79 between
    two blocks that share no sentence, which would measure the alphabet rather
    than the restatement. At 20 characters a match is a PHRASE. The sibling line
    this guard exists for — 834 characters, 98.3% identical between two
    households, 14 characters apart — scores the same either way, because there
    the whole line was one run.
    """
    matcher = difflib.SequenceMatcher(None, first, second, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks()
                  if block.size >= run)
    return matched / min(len(first), len(second))


@pytest.mark.parametrize("first, second", [
    (uncertainty_surface, two_channel_option_state),
    (uncertainty_surface, seven_channel_other_household),
    # The worst pair, and it is here because it is the worst: the shortest
    # block has the least conditional content to dilute a fixed vocabulary
    # that costs the same on every run, so the FRACTION rises as the block
    # shortens. Leaving it out would be a guard that passes where it matters
    # most.
    (two_channel_option_state, seven_channel_other_household),
])
def test_two_different_households_do_not_share_most_of_their_block(first, second):
    """The guard against this block becoming the sibling line. The lever is
    CONDITIONALITY — only what turns on THIS household earns its characters —
    and the ceiling is pinned here so a later edit that adds standing prose
    fails a test rather than waiting to be measured.

    Every pair of the three households runs: different SHAPE (two channels, a
    decisive verdict, no reversal row), SAME shape with different figures, keys
    and rows, and the two of those against each other. Measured 0.49 / 0.52 /
    0.57, against the sibling line's 0.983 on the same kind of comparison.
    *Kills it:* restoring §7's two definitional paragraphs, or its "READ THIS
    COLUMN AS" sentence, or any per-run clause that carries no figure."""
    fraction = _invariant_fraction(format_decomposition(first()),
                                   format_decomposition(second()))
    assert fraction < 0.60, fraction
