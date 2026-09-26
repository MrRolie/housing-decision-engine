"""Hand-built `Decomposition` instances — the rendering's own test data.

WHY HAND-BUILT, and why that is a feature. These instances pin the RENDERING
independently of whether the estimators are right: a test that ran the
estimator would fail when the estimator changed and would say nothing about
what a household reads. Two households live here so the block's INVARIANT
FRACTION can be measured between them (`test_decomposition_report.py`), which
is the guard against this block becoming the sibling line that measured 834
characters, 98.3% of them identical between two different households.

PROVENANCE OF EVERY FIGURE. `uncertainty_surface()` carries the figures spec
§7 measured on `tests/fixtures/uncertainty_surface.yaml` at seed 42 and its own
2,000 paths, and every sizing key's value is read from that fixture file. Four
kinds of figure are NOT measured and are marked `# filled` at their line: the
`with_interaction` intervals (§7's draft prints one interval per row and calls
the one it shows for `economy` illustrative), the frozen probabilities of the
two indistinguishable rows (§7 prints no probability for them), the
per-boundary confirming probabilities other than the first (§6 measures one
triple, at the `best` boundary), and everything in `two_channel_option_state()`
— a second household invented to exercise the other branches. Nothing here is
evidence about a market; it is evidence about a formatter.
"""
from hde.decomposition import (
    Decomposition,
    EstimatedBoundary,
    EstimatedReversal,
    ExactReversal,
    IndistinguishableLevel,
    Interval,
    LevelRegister,
    LevelRow,
    RefusedBoundary,
    RefusedInteraction,
    ResolvedInteraction,
    ResolvedLevel,
    ResolvedShares,
    ReversalRegister,
    SampledBoundary,
    SolvedBoundary,
    SpreadRegister,
    SpreadRow,
    StructuralZero,
    UnresolvedShares,
    Width,
    AxisReference,
)
from hde.models import Verdict


def _w(key, formatted, source, anchor=None, note=None):
    return Width(key=key, formatted=formatted, source=source, anchor=anchor, note=note)


# The verdict of the fixture run, as `models.compute_verdict` produces it. The
# `reason` string is the shape `models.Verdict` documents and the block prints
# VERBATIM — one home for that sentence.
FIXTURE_VERDICT = Verdict(
    best="rent",
    runner_up="condo",
    margin_pv=31348.656075,
    margin_frac=0.078,
    monthly_equivalent=None,
    prob_best=0.3350,
    decisive=False,
    state="disagreement",
    rule="mc_floor",
    reason="best guess says rent by $31,349 (7.8% of rent PV); most futures say "
           "condo (57% cheapest) — the two disagree, not decisive [hde verdict rule]",
    mc_mean_best="condo",
    mc_best="condo",
    mc_prob_best=0.57,
)


def uncertainty_surface(*, interaction=None, mean_margin=-67194.0) -> Decomposition:
    """The flagship fixture's block: seven live channels, a disagreement, the
    renter's portfolio carrying the spread and the tenancy moving the answer.

    `interaction` overrides the ΣS branch (§4 has both branches reachable on
    this one fixture); `mean_margin` is E[f] on the SPREAD register's own A
    matrix, which is not the level register's `futures_margin` (§0.1 ruling 1).
    """
    economy_widths = (
        _w("economic.inflation_vol", "1.2%", "assistant"),
        # §0.1 ruling 6: the cell must name the corr keys AND the option vols
        # they pull from, because which vols are pulled depends on which rho is
        # non-zero. §7's draft listed only the corr keys and is in breach of §4.
        _w("simulation.corr_inflation_condo", "0.5", "assistant",
           note="rho²=0.25 of the condo fee shock"),
        _w("simulation.condo_fee_vol", "8%", "assistant"),
        _w("simulation.corr_inflation_house", "0.5", "assistant",
           note="rho²=0.25 of the house maintenance shock"),
        _w("simulation.house_maintenance_vol", "20%", "assistant"),
        _w("simulation.corr_inflation_other", "0.4", "assistant",
           note="rho²=0.16 of each other-cost shock"),
        _w("simulation.other_cost_vol", "10%", "assistant"),
        _w("simulation.corr_inflation_event_cost", "0.3", "assistant",
           note="rho²=0.09 of each event-cost shock"),
    )
    rows = (
        SpreadRow(
            channel_id=6,
            shares=ResolvedShares(
                alone=0.877, alone_ci=Interval(0.775, 0.999),
                with_interaction=0.84,
                with_interaction_ci=Interval(0.75, 0.95),      # filled
            ),
            flip=0.406,
            flip_ci=Interval(0.384, 0.428),   # filled
            widths=(_w("simulation.investment_return_vol", "10%", "assistant"),),
        ),
        SpreadRow(
            channel_id=1,
            shares=ResolvedShares(
                alone=0.14, alone_ci=Interval(0.11, 0.17),
                with_interaction=0.13,
                with_interaction_ci=Interval(0.10, 0.16),      # filled
            ),
            flip=0.13,
            flip_ci=Interval(0.115, 0.145),   # filled
            widths=(
                _w("simulation.value_growth_vol", "7%", "assistant"),
                _w("condo.price_shock.annual_hazard", "3%", "assistant"),
                _w("house.price_shock.annual_hazard", "3%", "assistant"),
                _w("condo.price_shock.severity_vol", "10%", "anchor",
                   anchor="price_shock.severity_vol"),
                _w("house.price_shock.severity_vol", "10%", "anchor",
                   anchor="price_shock.severity_vol"),
            ),
        ),
        SpreadRow(
            channel_id=5,
            shares=ResolvedShares(
                alone=0.100, alone_ci=Interval(0.081, 0.122),
                with_interaction=0.09,
                with_interaction_ci=Interval(0.07, 0.11),      # filled
            ),
            flip=0.13,
            flip_ci=Interval(0.115, 0.145),   # filled
            widths=(
                _w("rent.reset_hazard", "7%/yr", "assistant"),
                _w("simulation.rent_escalation_vol", "6%", "assistant"),
                _w("simulation.other_cost_vol", "10%", "assistant"),
                _w("rent.events.moving_costs.cost_vol", "20%", "assistant"),
            ),
        ),
        SpreadRow(
            channel_id=2,
            shares=ResolvedShares(
                alone=0.03, alone_ci=Interval(0.02, 0.05),
                with_interaction=0.03,
                with_interaction_ci=Interval(0.02, 0.05),      # filled
            ),
            flip=0.06,
            flip_ci=Interval(0.05, 0.07),   # filled
            widths=(
                _w("market_scenario.path", None, "assistant",
                   note="the prior's own rows carry their citations"),
                _w("market_scenario.geography", "MTL_RMR", "user"),
            ),
        ),
        SpreadRow(
            channel_id=3,
            shares=ResolvedShares(
                alone=0.01, alone_ci=Interval(0.01, 0.02),
                with_interaction=0.01,
                with_interaction_ci=Interval(0.01, 0.02),      # filled
            ),
            flip=0.04,
            flip_ci=Interval(0.031, 0.049),   # filled
            widths=(
                _w("simulation.condo_fee_vol", "8%", "assistant"),
                _w("simulation.other_cost_vol", "10%", "assistant"),
                _w("condo.events.special_assessment.cost_vol", "25%", "assistant"),
            ),
        ),
        SpreadRow(
            channel_id=0,
            shares=ResolvedShares(
                alone=0.01, alone_ci=Interval(-0.002, 0.01),
                with_interaction=0.01,
                with_interaction_ci=Interval(0.00, 0.01),      # filled
            ),
            flip=0.04,
            flip_ci=Interval(0.031, 0.049),   # filled
            widths=economy_widths,
        ),
        # The house's share does not resolve at 2,000 futures and is KEPT as a
        # provisional figure, never clamped to 0.00 (§4, §7 rule 6).
        SpreadRow(
            channel_id=4,
            shares=UnresolvedShares(
                provisional_alone=-0.001,
                provisional_alone_ci=Interval(-0.002, 0.001),
                provisional_with_interaction=-0.002,
                provisional_with_interaction_ci=Interval(-0.003, 0.002),  # filled
            ),
            flip=0.004,
            flip_ci=Interval(0.001, 0.007),   # filled
            widths=(
                _w("simulation.house_maintenance_vol", "20%", "assistant"),
                _w("simulation.other_cost_vol", "10%", "assistant"),
                _w("house.events.roof_replacement.cost_vol", "20%", "assistant"),
            ),
        ),
    )
    spread = SpreadRegister(
        rows=rows,
        interaction=interaction or RefusedInteraction(
            first_order_sum=1.164, first_order_sum_ci=Interval(1.042, 1.310),
        ),
        leading_channel_id=6,
        superlative_licensed=False,
        check_first=_w("simulation.investment_return_vol", "10%", "assistant"),
    )
    # §3.4's rule is |Δ| > 2·SE. The house's costs at -$886 ± $179 is 4.95 SE,
    # so it is a RESOLVED row — §7's draft filed it under "indistinguishable
    # from zero", which is the draft making the error this feature exists to
    # prevent (§0.1 item 18(a)).
    level = LevelRegister(
        rows=(
            LevelRow(channel_id=5, level=ResolvedLevel(
                delta=125074.0, se=1775.0, prob_best_frozen=0.5355)),
            LevelRow(channel_id=1, level=ResolvedLevel(
                delta=-38314.0, se=2252.0, prob_best_frozen=0.28)),
            LevelRow(channel_id=2, level=ResolvedLevel(
                delta=11064.0, se=1095.0, prob_best_frozen=0.35)),
            LevelRow(channel_id=3, level=ResolvedLevel(
                delta=5232.0, se=786.0, prob_best_frozen=0.35)),
            LevelRow(channel_id=4, level=ResolvedLevel(
                delta=-886.0, se=179.0, prob_best_frozen=0.35)),
            LevelRow(channel_id=6, level=IndistinguishableLevel(
                provisional_delta=-3805.0, se=5383.0,
                prob_best_frozen=0.35)),                        # filled
            LevelRow(channel_id=0, level=IndistinguishableLevel(
                provisional_delta=-252.0, se=642.0,
                prob_best_frozen=0.34)),                        # filled
        ),
        paths=2000,
        prob_best_base=0.341,
        futures_margin=-67194.0,
        all_frozen_margin=31348.656075,
        all_frozen_path_spread=0.0, all_frozen_deviation=5.8e-11,
        accounted_for=98113.0,
        leading_channel_id=5,
    )
    renewal = ExactReversal(
        key="house.mortgage_renewal_rates",
        option="house",
        stated_formatted="4.60%, 5.00%, 4.80%, 4.40%",
        bracket_low=0.01,
        bracket_high=0.10,
        bracket_source="assistant",
        probe_paths=200,
        max_path_deviation_over_sd=2.0e-15,
        # `best` and `runner_up` are solved on the DETERMINISTIC verdict and
        # came out identical to seven digits across five seeds — properties of
        # the stated config. `mc_best` is bisected on the Monte Carlo curve and
        # moved 2.698%–2.805% over the same five seeds, so it is a property of
        # a sample and carries the sample that produced it.
        boundaries=(
            SolvedBoundary(verdict_field="best", value=0.0160522601, was="rent",
                           becomes="house",
                           confirming_probabilities=(("condo", 0.1915),
                                                     ("house", 0.5185),
                                                     ("rent", 0.2900))),
            SampledBoundary(verdict_field="mc_best", value=0.0271640308, was="condo",
                            becomes="house", curve_paths=2000, seed=42,
                            curve_probabilities=(("condo", 0.3405),   # filled
                                                 ("house", 0.3410),
                                                 ("rent", 0.3185)),
                            confirming_probabilities=(("condo", 0.3405),
                                                      ("house", 0.3410),
                                                      ("rent", 0.3185))),
            SolvedBoundary(verdict_field="runner_up", value=0.0295494356, was="condo",
                           becomes="house",
                           confirming_probabilities=(("condo", 0.3210),  # filled
                                                     ("house", 0.3650),
                                                     ("rent", 0.3140))),
        ),
        refused_boundaries=(
            RefusedBoundary(verdict_field="decisive",
                            reason="no value in the bracket clears the 65% floor, so "
                                   "there is nothing to cross"),
        ),
        references=(
            AxisReference(label="your contract", value=0.0435, formatted="4.35%",
                          anchor="mortgage_rate.contracted_5y_uninsured"),
            AxisReference(label="today's posted 5-year", value=0.0609,
                          formatted="6.09%", anchor="mortgage_rate.posted_5y",
                          note="a list price to bracket a guess from above, never a "
                               "ceiling on a 2031 renewal"),
        ),
        path_note="every grid point replaces the whole stated path with ONE figure "
                  "applied at each renewal, so your stated path is not a point on "
                  "that line",
    )
    # §6 licenses `<opt>.mortgage_rate` for slice 1 and measures it at the same
    # 2.0e-15; §7's draft renders no row for it (found 2026-09-21).
    contract_rate = ExactReversal(
        key="house.mortgage_rate",
        option="house",
        stated_formatted="4.35%",
        bracket_low=0.01,
        bracket_high=0.10,
        bracket_source="assistant",
        probe_paths=200,
        max_path_deviation_over_sd=2.0e-15,
        boundaries=(
            SolvedBoundary(verdict_field="best", value=0.02251804, was="rent",
                           becomes="house",
                           confirming_probabilities=(("condo", 0.2440),   # filled
                                                     ("house", 0.4380),
                                                     ("rent", 0.3180))),
        ),
        refused_boundaries=(),
        references=(
            AxisReference(label="today's posted 5-year", value=0.0609,
                          formatted="6.09%", anchor="mortgage_rate.posted_5y"),
        ),
    )
    reversal = ReversalRegister(
        exact=(renewal, contract_rate),
        estimated=(),
        structural_zeros=(
            StructuralZero(
                kind="stated_path",
                label="your renewal rate",
                keys=("house.mortgage_renewal_rates",),
                reason="a path you stated, not a distribution — the engine anchors no "
                       "forward rate and draws none, so renewal carries no spread here "
                       "at all",
                stated_formatted="4.60%, 5.00%, 4.80%, 4.40%",
                reversal_key="house.mortgage_renewal_rates",
            ),
            StructuralZero(
                kind="no_pv_reach",
                label="your income",
                keys=("income.pay_drop_events",),
                reason="it moves the affordability report, not either option's present "
                       "value, so it cannot move this margin",
            ),
        ),
    )
    return Decomposition(
        paths=2000,
        live_channel_ids=(0, 1, 2, 3, 4, 5, 6),
        verdict=FIXTURE_VERDICT,
        mean_margin=mean_margin,
        sd_margin=286506.0,
        spread=spread,
        level=level,
        reversal=reversal,
    )


def resolved_interaction() -> ResolvedInteraction:
    """§4's numeric branch, measured on the same fixture at 10,000 paths, with
    §5 mechanism 4's assistant-typed sum — which exists ONLY here."""
    return ResolvedInteraction(
        first_order_sum=0.95, first_order_sum_ci=Interval(0.92, 0.98),
        residual=0.05, residual_ci=Interval(0.02, 0.08),
        unstated_first_order_sum=0.94,
        unstated_first_order_sum_ci=Interval(0.90, 0.97),
    )


def seven_channel_other_household() -> Decomposition:
    """A DIFFERENT household of the same shape: seven live channels, a
    disagreement, and nothing else in common — a financed condo rather than a
    financed house, its own keys and source classes, its own stated renewal
    path, an ESTIMATED reversal row and a `dead_draw` structural zero.

    It exists for the harsher invariant-fraction measurement (same shape is
    where restated prose hides) and because it is the only fixture that
    exercises the estimated-reversal and dead-draw branches. Every figure is
    invented.
    """
    verdict = Verdict(
        best="condo", runner_up="house", margin_pv=88114.0, margin_frac=0.142,
        monthly_equivalent=None, prob_best=0.4180, decisive=False,
        state="disagreement", rule="mc_floor",
        reason="best guess says condo by $88,114 (14.2% of condo PV); most futures "
               "say rent (46% cheapest) — the two disagree, not decisive "
               "[hde verdict rule]",
        mc_mean_best="rent", mc_best="rent", mc_prob_best=0.46,
    )
    spread = SpreadRegister(
        rows=(
            SpreadRow(channel_id=1, shares=ResolvedShares(
                alone=0.51, alone_ci=Interval(0.44, 0.58),
                with_interaction=0.57, with_interaction_ci=Interval(0.50, 0.64)),
                flip=0.221,
                flip_ci=Interval(0.211, 0.231),   # filled
                widths=(_w("simulation.value_growth_vol", "12%", "user"),
                        _w("condo.price_shock.annual_hazard", "5%", "user"))),
            SpreadRow(channel_id=3, shares=ResolvedShares(
                alone=0.24, alone_ci=Interval(0.19, 0.29),
                with_interaction=0.27, with_interaction_ci=Interval(0.21, 0.33)),
                flip=0.104,
                flip_ci=Interval(0.096, 0.112),   # filled
                widths=(_w("simulation.condo_fee_vol", "15%", "user"),)),
            SpreadRow(channel_id=6, shares=ResolvedShares(
                alone=0.12, alone_ci=Interval(0.08, 0.16),
                with_interaction=0.13, with_interaction_ci=Interval(0.09, 0.17)),
                flip=0.061,
                flip_ci=Interval(0.055, 0.067),   # filled
                widths=(_w("simulation.investment_return_vol", "4%", "user"),)),
            SpreadRow(channel_id=4, shares=ResolvedShares(
                alone=0.07, alone_ci=Interval(0.04, 0.10),
                with_interaction=0.08, with_interaction_ci=Interval(0.05, 0.11)),
                flip=0.033,
                flip_ci=Interval(0.028, 0.038),   # filled
                widths=(_w("simulation.house_maintenance_vol", "11%", "user"),)),
            SpreadRow(channel_id=5, shares=ResolvedShares(
                alone=0.04, alone_ci=Interval(0.02, 0.06),
                with_interaction=0.05, with_interaction_ci=Interval(0.03, 0.07)),
                flip=0.019,
                flip_ci=Interval(0.016, 0.022),   # filled
                widths=(_w("rent.reset_hazard", "2%/yr", "user"),)),
            SpreadRow(channel_id=2, shares=ResolvedShares(
                alone=0.02, alone_ci=Interval(0.01, 0.03),
                with_interaction=0.02, with_interaction_ci=Interval(0.01, 0.03)),
                flip=0.008,
                flip_ci=Interval(0.006, 0.01),   # filled
                widths=(_w("market_scenario.geography", "TOR_CMA", "user"),)),
            SpreadRow(channel_id=0, shares=UnresolvedShares(
                provisional_alone=1.004, provisional_alone_ci=Interval(0.998, 1.011),
                provisional_with_interaction=1.007,
                provisional_with_interaction_ci=Interval(1.001, 1.014)),
                flip=0.002,
                flip_ci=Interval(0.001, 0.003),   # filled
                widths=(_w("economic.inflation_vol", "0.9%", "anchor",
                           anchor="economic.inflation_rate"),)),
        ),
        interaction=ResolvedInteraction(
            first_order_sum=0.88, first_order_sum_ci=Interval(0.81, 0.95),
            residual=0.12, residual_ci=Interval(0.05, 0.19),
        ),
        leading_channel_id=1,
        superlative_licensed=True,
        check_first=None,
    )
    level = LevelRegister(
        rows=(
            LevelRow(channel_id=1, level=ResolvedLevel(
                delta=-52880.0, se=3140.0, prob_best_frozen=0.61)),
            LevelRow(channel_id=5, level=ResolvedLevel(
                delta=9905.0, se=880.0, prob_best_frozen=0.44)),
            LevelRow(channel_id=3, level=ResolvedLevel(
                delta=2410.0, se=410.0, prob_best_frozen=0.43)),
            LevelRow(channel_id=6, level=IndistinguishableLevel(
                provisional_delta=1180.0, se=2900.0, prob_best_frozen=0.42)),
            LevelRow(channel_id=4, level=IndistinguishableLevel(
                provisional_delta=-140.0, se=390.0, prob_best_frozen=0.42)),
            LevelRow(channel_id=2, level=IndistinguishableLevel(
                provisional_delta=60.0, se=220.0, prob_best_frozen=0.42)),
            LevelRow(channel_id=0, level=IndistinguishableLevel(
                provisional_delta=-15.0, se=95.0, prob_best_frozen=0.42)),
        ),
        paths=3000,
        prob_best_base=0.424,
        # The rows above sum to -$39,480, so this register's own gap
        # (`all_frozen_margin − futures_margin`) is that figure: the fixture is
        # internally coherent, as the block's arithmetic assumes.
        futures_margin=127594.0,
        all_frozen_margin=88114.0,
        all_frozen_path_spread=0.0, all_frozen_deviation=7.3e-11,
        accounted_for=-39480.0,
        leading_channel_id=1,
    )
    reversal = ReversalRegister(
        exact=(
            ExactReversal(
                key="condo.mortgage_renewal_rates",
                option="condo",
                stated_formatted="5.20%, 5.40%",
                bracket_low=0.02, bracket_high=0.12, bracket_source="assistant",
                probe_paths=200, max_path_deviation_over_sd=3.1e-15,
                # A licensed key carries BOTH kinds at once, so both group
                # headings belong to ONE row. `decisive` is SAMPLED, not
                # solved: it turns on `prob_best` against the anchored floor,
                # which is a figure of the sample (contract, 2026-09-22).
                boundaries=(
                    SampledBoundary(verdict_field="mc_best", value=0.03841262,
                                    was="rent", becomes="condo",
                                    curve_paths=6000, seed=42,
                                    curve_probabilities=(("condo", 0.4510),
                                                         ("rent", 0.4505)),
                                    confirming_probabilities=(("condo", 0.4510),
                                                              ("rent", 0.4505))),
                    SampledBoundary(verdict_field="decisive", value=0.06120411,
                                    was="no", becomes="yes",
                                    curve_paths=6000, seed=42,
                                    curve_probabilities=(("condo", 0.6520),
                                                         ("rent", 0.2610)),
                                    confirming_probabilities=(("condo", 0.6520),
                                                              ("rent", 0.2610))),
                    SolvedBoundary(verdict_field="runner_up", value=0.05004182,
                                   was="house", becomes="rent",
                                   confirming_probabilities=(("condo", 0.5910),
                                                             ("rent", 0.3020))),
                ),
                refused_boundaries=(
                    RefusedBoundary(verdict_field="best",
                                    reason="it does not change anywhere in the "
                                           "bracket"),
                ),
                references=(
                    AxisReference(label="your contract", value=0.0401,
                                  formatted="4.01%",
                                  anchor="mortgage_rate.contracted_5y_insured"),
                ),
                path_note="every grid point replaces the whole stated path with ONE "
                          "figure applied at each renewal, so your stated path is not "
                          "a point on that line",
            ),
        ),
        # RATE-SHAPED ON PURPOSE. The contract carries `bracket_low`,
        # `bracket_high` and `Boundary.value` as bare floats with no unit, and
        # the formatter renders them as rates — which is right for every
        # slice-1 candidate (§6 restricts them to the financing leg) and wrong
        # for a dollar level or a multiplier. §14's deferred candidates include
        # both, so this is a reported contract gap, not a rendering choice: a
        # `rent.monthly_rent` bracket of ¼×–4× would print as "25.00%–400.00%".
        estimated=(
            EstimatedReversal(
                key="house.value_growth_rate",
                option="house",
                stated_formatted="3.10%",
                bracket_low=0.0, bracket_high=0.06, bracket_source="assistant",
                max_path_deviation_over_sd=1.8e00,
                boundaries=(
                    EstimatedBoundary(verdict_field="best", value=0.0142,
                                      value_ci=Interval(0.0119, 0.0168), was="condo",
                                      becomes="house", resimulation_paths=3000),
                ),
                refused_boundaries=(),
                references=(),
            ),
        ),
        structural_zeros=(
            StructuralZero(
                kind="dead_draw",
                label="the economy",
                keys=("economic.inflation_vol", "simulation.corr_inflation_condo"),
                reason="this run is in real terms and every inflation correlation is "
                       "zero, so the draw happens every year and reaches no cash flow",
                channel_id=0,
            ),
        ),
    )
    return Decomposition(
        paths=6000,
        live_channel_ids=(0, 1, 2, 3, 4, 5, 6),
        verdict=verdict,
        mean_margin=129050.0,
        sd_margin=402115.0,
        spread=spread,
        level=level,
        reversal=reversal,
    )


def two_channel_option_state() -> Decomposition:
    """A second household, sharing nothing with the first: two live channels, a
    decisive `option` verdict, the condo winning, widths the USER stated, the
    superlative licensed, no structural zero and no reversal row.

    Every figure here is invented for the formatter's other branches — it is
    the control in the invariant-fraction measurement, not a measurement.
    """
    verdict = Verdict(
        best="condo", runner_up="rent", margin_pv=54120.0, margin_frac=0.121,
        monthly_equivalent=311.0, prob_best=0.81, decisive=True, state="option",
        rule="mc_floor",
        reason="P(condo cheapest) = 81% ≥ 65% floor [hde verdict rule]",
        mc_mean_best="condo", mc_best="condo", mc_prob_best=0.81,
    )
    spread = SpreadRegister(
        rows=(
            SpreadRow(channel_id=3, shares=ResolvedShares(
                alone=0.62, alone_ci=Interval(0.55, 0.69),
                with_interaction=0.66, with_interaction_ci=Interval(0.59, 0.73)),
                flip=0.082,
                flip_ci=Interval(0.073, 0.091),   # filled
                widths=(_w("simulation.condo_fee_vol", "6%", "user"),)),
            SpreadRow(channel_id=4, shares=ResolvedShares(
                alone=0.35, alone_ci=Interval(0.28, 0.42),
                with_interaction=0.39, with_interaction_ci=Interval(0.32, 0.46)),
                flip=0.051,
                flip_ci=Interval(0.044, 0.058),   # filled
                widths=(_w("simulation.house_maintenance_vol", "9%", "user"),)),
        ),
        interaction=ResolvedInteraction(
            first_order_sum=0.97, first_order_sum_ci=Interval(0.94, 0.99),
            residual=0.03, residual_ci=Interval(0.01, 0.06),
        ),
        leading_channel_id=3,
        superlative_licensed=True,
        check_first=None,
    )
    level = LevelRegister(
        rows=(
            LevelRow(channel_id=3, level=ResolvedLevel(
                delta=8940.0, se=610.0, prob_best_frozen=0.93)),
            LevelRow(channel_id=4, level=ResolvedLevel(
                delta=-2110.0, se=505.0, prob_best_frozen=0.76)),
        ),
        paths=1500,
        prob_best_base=0.812,
        futures_margin=47290.0,
        all_frozen_margin=54120.0,
        all_frozen_path_spread=0.0, all_frozen_deviation=3.1e-11,
        accounted_for=6830.0,
        leading_channel_id=3,
    )
    return Decomposition(
        paths=4000,
        live_channel_ids=(3, 4),
        verdict=verdict,
        mean_margin=47290.0,
        sd_margin=96420.0,
        spread=spread,
        level=level,
        reversal=ReversalRegister(exact=(), estimated=(), structural_zeros=()),
    )
