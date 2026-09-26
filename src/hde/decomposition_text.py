"""Which risk decides it — the rendered block (spec §7).

Design: `docs/specs/2026-09-22-which-risk-decides-it.md`. The types are
`decomposition.py`; `decomposition_run.decompose` fills them from one spec,
with the estimators in `decomposition_math` and the reversal solver in
`break_even`; this module turns one `DecompositionOutcome` into the text a
household reads, and
`serialization.decomposition_to_dict` turns the same object into the `--json`
block. Nothing here computes a statistic: every figure printed is a field, or
a subtraction/ratio OF fields performed where it is printed so that two
printings cannot disagree (§0.1 ruling 2).

THE BINDING, and why this file has exactly one public function (§5 mechanism 5,
operator ruling 2026-09-22; §7 formatter rule 1; test T7). The spread table may
never be emitted without the level register beside it. On this repo's own
flagship fixture the spread table's top row is the renter's portfolio at 0.88 of
the scatter, and freezing it moves the decision by -$2,200, while the tenancy at
0.10 of the scatter moves it by +$127,876 — 58x. A reader handed the spread
table alone quotes the channel that matters least. `decomposition.py` encodes
that as far as a dataclass reaches (no spread-only `Decomposition` can be
constructed); this file completes it, and the completion is STRUCTURAL rather
than a rule a later editor is trusted to remember:

  - `__all__` names one function, and it is the only module-level callable that
    takes a `Decomposition`;
  - no function named for a register exists. The spread rows, the level rows
    and the reversal rows are assembled in ONE function body, so there is no
    callable anywhere in the process that returns the spread table. The body is
    long for that reason and must stay that way: splitting out `_spread_block()`
    would create the caller-reachable path the ruling forbids;
  - the helpers below take one ROW, one `Width`, one interval — never a
    register.

CONDITIONALITY, not storage (operator instruction, 2026-09-22, measured on a
sibling line the same week: 834 characters, 98.3% of them identical between two
entirely different households). A clause that is true on every run which prints
this block is a property of the ENGINE: it belongs cited once and must not be
restated per run. So the column definitions — what "alone" means, why the flip
column does not sum, that a share is never clamped — live in
`docs/reference/ARCHITECTURE.md`'s figure glossary, which is already this
repo's answer to "what is this number?", and the block cites them in one
clause. What is printed per run is what turns on THIS household: its figures,
its channel names, its keys and their source classes.

TWO STATES THAT ARE NOT NONE AND NOT ZERO. `ResolvedShares`/`UnresolvedShares`
and `ResolvedLevel`/`IndistinguishableLevel` share no attribute name for their
point estimate, so this module dispatches on the TYPE (`isinstance`) and never
with `getattr` or a `try`: a figure that did not resolve renders as its own
sentence with its own figures, and cannot be printed in a resolved column.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from .decomposition import (
    BOUNDARY_FIELDS,
    Decomposition,
    DecompositionOutcome,
    DecompositionRefusal,
    EstimatedBoundary,
    ExactReversal,
    IndistinguishableLevel,
    Interval,
    LevelRow,
    RefusedBoundary,
    RefusedSpread,
    ResolvedInteraction,
    ResolvedLevel,
    ResolvedShares,
    SampledBoundary,
    SolvedBoundary,
    SpreadRegister,
    SpreadRow,
    StructuralZero,
    Width,
    channel,
)

__all__ = ["format_decomposition"]

# The one home for what the columns mean (see CONDITIONALITY above). Cited, not
# restated: `serialization.py`'s monthly-equivalent line already cites this doc
# the same way.
GLOSSARY = "docs/reference/ARCHITECTURE.md figure glossary"

# The source classes that are NOT somebody's guess (`sources.SourceEcho`'s own
# vocabulary: user | assistant | unattributed | sweep | anchor). §5 mechanism 3
# licenses the superlative only when every width of the leading row is one of
# these; `superlative_licensed` is carried on the register, and this tuple is
# used only to word §5 mechanism 4's clause about the table as a whole.
_SOURCED = ("user", "anchor")

_LABEL_W = 23


# ---------------------------------------------------------------------------
# Figure formatting — one rule per kind of figure, applied once
# ---------------------------------------------------------------------------

def _money(value: float) -> str:
    """A dollar figure with its natural sign: `$31,349`, `-$67,194`."""
    return f"${value:,.0f}" if value >= 0 else f"-${-value:,.0f}"


def _shift(value: float) -> str:
    """A dollar SHIFT, sign always shown: a freeze's direction is the point."""
    return f"+${value:,.0f}" if value >= 0 else f"-${-value:,.0f}"


def _share(value: float) -> str:
    """A Sobol share: two decimals, or three when two would round it to zero.

    One rule, so one figure never prints at two roundings (§0.1 ruling 2), and
    a share that is small but not zero never renders AS zero — the measured
    `-0.001` reading `-0.00` would be the clamp this feature refuses (§4). An
    exact zero is a zero and prints as one.
    """
    return f"{value:.2f}" if value == 0 or abs(value) >= 0.005 else f"{value:.3f}"


def _interval(interval: Interval) -> str:
    return f"[{_share(interval.low)}, {_share(interval.high)}]"


def _flip(value: float) -> str:
    """A fraction of futures, one decimal: the measured 0.4% is not 0%."""
    return f"{value:.1%}"


def _flip_cell(value: float, interval: Interval) -> str:
    """The flip column WITH its width (§3.3, §0.1 item 10; §7's draft prints
    none and the draft loses).

    The reason this column in particular may not stand bare is the reason it
    exists: it is the one figure here stated in decision space, so a point
    estimate with no width, beside neighbours that all carry one, reads as the
    most certain number in the table. The bracket takes its unit from the
    point estimate it follows rather than repeating it twice more.
    """
    return (f"{_flip(value)} [{interval.low * 100:.1f}, "
            f"{interval.high * 100:.1f}]")


def _prob(value: float) -> str:
    """A probability, two decimals — the block's only rounding of one."""
    return f"{value:.2f}"


def _rate(value: float) -> str:
    return f"{value:.2%}"


def _solved_rate(value: float) -> str:
    """A crossing solved on the DETERMINISTIC verdict, at four decimals.

    The precision is the point, not decoration: the reversal solver measured
    these identical to seven digits across five seeds, because they are
    properties of the config the user stated. A sampled crossing prints at two
    decimals and says whose sample it is, so the two never share a typography
    (§0.1 item 24; see `_sampled_boundary_line`).
    """
    return f"{value:.4%}"


def _deviation(value: float) -> str:
    return f"{value:.1e}"


# ---------------------------------------------------------------------------
# Row-level helpers. Each takes ONE row (or one width, one boundary) — never a
# register, so none of them can return a table (see THE BINDING above).
# ---------------------------------------------------------------------------

def _width_cell(width: Width) -> str:
    """One sizing figure with whose figure it is, inline on its own row (§7
    rule 7, §5 mechanism 1). `formatted` is None for a key whose value is not a
    figure (`market_scenario.path`), and then the key stands alone."""
    head = width.key if width.formatted is None else f"{width.key}={width.formatted}"
    tag = width.source if width.anchor is None else f"{width.source}: {width.anchor}"
    note = "" if width.note is None else f" ({width.note})"
    return f"{head} [{tag}]{note}"


def _widths_line(widths: Sequence[Width]) -> str:
    """Every width of one row, never a subset: the `economy` row's cell must
    carry the `corr_inflation_*` keys AND the option vols they pull from, or
    the cell is itself a wrong answer (§4, §0.1 ruling 6). A cap or a "…and 3
    more" here would be that wrong answer."""
    return "      sized by " + "; ".join(_width_cell(w) for w in widths)


def _spread_row_lines(row: SpreadRow, paths: int) -> List[str]:
    label = channel(row.channel_id).label
    shares = row.shares
    lines: List[str] = []
    if isinstance(shares, ResolvedShares):
        alone = f"{_share(shares.alone)} {_interval(shares.alone_ci)}"
        both = (f"{_share(shares.with_interaction)} "
                f"{_interval(shares.with_interaction_ci)}")
        lines.append(f"  {label:<{_LABEL_W}} {alone:<19} {both:<19} "
                     f"{_flip_cell(row.flip, row.flip_ci):>19}")
    else:
        # Not resolved at this sample size: the estimates are KEPT and printed,
        # in their own words and on their own line, and there is no attribute
        # on this object that could put them in a resolved column (§4, §7 rule
        # 6). The flip column survives an unresolved row (§7 rule 4).
        lines.append(f"  {label:<{_LABEL_W}} {'not resolved':<19} "
                     f"{'not resolved':<19} "
                     f"{_flip_cell(row.flip, row.flip_ci):>19}")
        lines.append(
            f"      {_share(shares.provisional_alone)} "
            f"{_interval(shares.provisional_alone_ci)} alone and "
            f"{_share(shares.provisional_with_interaction)} "
            f"{_interval(shares.provisional_with_interaction_ci)} with interaction, "
            f"at {paths:,} futures"
        )
    lines.append(_widths_line(row.widths))
    return lines


def _spread_sort_key(row: SpreadRow) -> Tuple[int, float]:
    """Largest share first, unresolved rows last. Presentation, so it lives
    here rather than in the estimator that has no reader to serve."""
    shares = row.shares
    if isinstance(shares, ResolvedShares):
        return (0, -shares.alone)
    return (1, -shares.provisional_alone)


def _level_row_line(row: LevelRow) -> str:
    """A RESOLVED level row: `|Δ| > 2·SE` (§3.4). Read as a cost the central
    case leaves out, which is what the register's own heading says."""
    level = row.level
    assert isinstance(level, ResolvedLevel)   # the caller filed it by type
    label = channel(row.channel_id).label
    se = f"(± ${level.se:,.0f})"
    return (f"  {label:<{_LABEL_W}} {_shift(level.delta):>10} {se:<12} "
            f"-> {_prob(level.prob_best_frozen)}")


def _indistinguishable_cell(row: LevelRow) -> str:
    """A channel whose freeze moves the margin by no more than 2·SE — a row a
    reader must SEE rather than an absence: on this repo's fixture it is the
    channel carrying 88% of the spread, and that is the whole finding."""
    level = row.level
    assert isinstance(level, IndistinguishableLevel)
    return (f"{channel(row.channel_id).label} ({_shift(level.provisional_delta)} "
            f"± ${level.se:,.0f}, P -> {_prob(level.prob_best_frozen)})")


def _level_sort_key(row: LevelRow) -> Tuple[int, float]:
    level = row.level
    if isinstance(level, ResolvedLevel):
        return (0, -abs(level.delta))
    return (1, -abs(level.provisional_delta))


# The four boundary kinds in words (§0.1 ruling 4 fixes the enumeration at
# four). One home for this vocabulary; an unknown kind renders as its own field
# name rather than being dropped, because a solved boundary nobody prints is
# the absence this register exists to refuse.
_BOUNDARY_LABEL = {
    "best": "the central case's winner",
    "runner_up": "the runner-up",
    "mc_best": "the option most futures call cheapest",
    "decisive": "the decisiveness verdict",
}

# The order the rows print in, which is `BOUNDARY_FIELDS`' own order. Fixed
# here rather than taken from the tuple the assembler happened to build, so the
# block is stable across runs and across assemblers.
_BOUNDARY_ORDER = {field: index for index, field in enumerate(BOUNDARY_FIELDS)}


def _probabilities(pairs: Sequence[Tuple[str, float]]) -> str:
    return ", ".join(f"{option} {_prob(value)}" for option, value in pairs)


def _confirmed_clause(pairs: Sequence[Tuple[str, float]], lead: str) -> str:
    """Where the confirming re-simulation puts the futures — and NOTHING when
    that tuple is empty, which it is on a run with no futures to re-simulate.
    An empty tuple is data; this surface is not told why it is empty and does
    not invent a reason (§8's absence discipline).

    The confirming probabilities print and the free curve's do not: a boundary
    that is printed at all is one whose two agreed (§6, test T11), so printing
    both would be two statements of one number.
    """
    return "" if not pairs else f"{lead}{_probabilities(pairs)}"


def _solved_boundary_line(boundary: "SolvedBoundary") -> str:
    """A crossing solved on the DETERMINISTIC verdict: a property of the config
    the user stated, which is why it prints at four decimals."""
    label = _BOUNDARY_LABEL.get(boundary.verdict_field, boundary.verdict_field)
    return (f"        {label} changes from {boundary.was} to {boundary.becomes} at "
            f"{_solved_rate(boundary.value)}"
            f"{_confirmed_clause(boundary.confirming_probabilities, ' — re-simulated there: ')}")


def _sampled_boundary_line(boundary: "SampledBoundary") -> str:
    """A crossing BISECTED ON THE MONTE CARLO CURVE, which is a property of a
    sample and not of the config.

    Measured on this repo's fixture: the two solved crossings came out
    identical to seven digits across five seeds, and this one moved 2.698% to
    2.805% over the same five. A reader handed both in one typography is being
    told a sample property is a config property — this feature's own cardinal
    error, committed by its own output. Three things separate them here, so the
    distinction survives losing any one: two decimals against four, this
    clause, and the grouping the caller prints them under.
    """
    label = _BOUNDARY_LABEL.get(boundary.verdict_field, boundary.verdict_field)
    return (f"        {label} changes from {boundary.was} to {boundary.becomes} at "
            f"{_rate(boundary.value)}"
            f"{_confirmed_clause(boundary.confirming_probabilities, ', where the futures sit at ')}"
            f" — bisected on {boundary.curve_paths:,} paths at seed {boundary.seed}, "
            f"so it moves with the seed")


def _estimated_boundary_line(boundary: EstimatedBoundary) -> str:
    label = _BOUNDARY_LABEL.get(boundary.verdict_field, boundary.verdict_field)
    return (f"        {label} changes from {boundary.was} to {boundary.becomes} at "
            f"{_rate(boundary.value)}, inside "
            f"{_rate(boundary.value_ci.low)}–{_rate(boundary.value_ci.high)} on "
            f"{boundary.resimulation_paths:,} re-simulated paths")


def _refused_boundary_line(refused: RefusedBoundary) -> str:
    """A boundary that exists on the curve and is not printed (§8 refusal 7),
    recorded rather than dropped: a boundary that vanishes with no row is an
    absence a reader reads as "nothing here"."""
    label = _BOUNDARY_LABEL.get(refused.verdict_field, refused.verdict_field)
    return f"      no boundary printed for {label} — {refused.reason}"


def _reference_clause(reference) -> str:
    note = "" if reference.note is None else f" — {reference.note}"
    anchor = "" if reference.anchor is None else f" [{reference.anchor}]"
    return f"{reference.label} {reference.formatted}{anchor}{note}"


def _bracket_clause(low: float, high: float, source: str) -> str:
    """The bracket the curve was solved inside, with WHOSE width it is. §6's
    2026-09-21 correction: a `RATE_BRACKETS` entry converts an honest refusal
    into an answer, so the bracket must be printed rather than assumed — a
    bracket figure on a row with no source class is the honesty contract's own
    breach (`ExactReversal.bracket_source`)."""
    return f"inside a {_rate(low)}–{_rate(high)} bracket [{source}]"


def _require_types(items: Sequence[object], allowed: Tuple[type, ...],
                   where: str) -> None:
    """Raise on any item that is none of `allowed`, naming it and where it was.

    Every register here is rendered by dispatching on TYPE, and a dispatch
    that filters by `isinstance` drops whatever it did not foresee without a
    word — the row is simply absent, and an absent row is the thing a reader
    takes for "nothing here". So a type outside the contract is a defect to
    surface, never a row to skip.
    """
    for item in items:
        if not isinstance(item, allowed):
            names = " or ".join(t.__name__ for t in allowed)
            raise TypeError(
                f"{where} carries a {type(item).__name__}, which is not a {names}: "
                f"this block cannot say what that figure is, so it does not print "
                f"it as one of them or drop it as though it were absent")


def _reversal_detail_lines(reversal) -> List[str]:
    """The solved numbers of ONE reversal row — exact or estimated, each in its
    own vocabulary (§0: the two kinds share no field set and cannot be
    concatenated into one ordered table)."""
    lines: List[str] = []
    exact = isinstance(reversal, ExactReversal)
    bracket = _bracket_clause(reversal.bracket_low, reversal.bracket_high,
                              reversal.bracket_source)
    if reversal.boundaries:
        # A stated PATH is replaced by one flat figure; a stated scalar is
        # simply moved. `path_note` is what tells them apart (§6: the row may
        # never claim the user stated a flat rate they did not).
        head = ("replacing that path with one flat rate, "
                if reversal.path_note is not None else "moving it ")
        ordered = sorted(
            reversal.boundaries,
            key=lambda b: (_BOUNDARY_ORDER.get(b.verdict_field, len(_BOUNDARY_ORDER)),
                           b.verdict_field),
        )
        if not exact:
            _require_types(ordered, (EstimatedBoundary,),
                           f"{reversal.key}'s estimated reversal row")
            lines.append(f"      {head}{bracket}:")
            lines.extend(_estimated_boundary_line(b) for b in ordered)
        else:
            # The crossings GROUP by what produced them, the same way the rows
            # one level up group by exactness — so a reader who has learned
            # that rule once applies it twice (§0.1 item 24). A boundary of
            # any OTHER type raises rather than falling through both filters:
            # a crossing dropped by an isinstance filter vanishes with no row,
            # and on a key whose every crossing is of an unforeseen type the
            # row reads as if nothing were solved on it at all.
            _require_types(ordered, (SolvedBoundary, SampledBoundary),
                           f"{reversal.key}'s exact reversal row")
            solved = [b for b in ordered if isinstance(b, SolvedBoundary)]
            sampled = [b for b in ordered if isinstance(b, SampledBoundary)]
            if solved:
                lines.append(f"      {head}{bracket} — solved on your own figures:")
                lines.extend(_solved_boundary_line(b) for b in solved)
            if sampled:
                # The bracket prints on whichever group comes first, never on
                # neither: a bracket figure that does not appear is the same
                # breach as one appearing without its source class.
                lines.append("      on the same axis, bisected on the futures rather "
                             "than solved:" if solved else
                             f"      {head}{bracket}, bisected on the futures rather "
                             f"than solved:")
                lines.extend(_sampled_boundary_line(b) for b in sampled)
    else:
        lines.append(f"      no boundary solved {bracket}")
    if exact:
        lines.append(f"      exact to "
                     f"{_deviation(reversal.max_path_deviation_over_sd)} of the "
                     f"option's own s.d. over {reversal.probe_paths:,} probe paths")
    else:
        lines.append(f"      the exactness gate refused this key at "
                     f"{_deviation(reversal.max_path_deviation_over_sd)} of the "
                     f"option's own s.d., so the distance is estimated")
    if reversal.path_note is not None:
        lines.append(f"      {reversal.path_note}")
    lines.extend(_refused_boundary_line(r) for r in reversal.refused_boundaries)
    if reversal.references:
        lines.append("      on the same axis: "
                     + "; ".join(_reference_clause(r) for r in reversal.references))
    return lines


def _structural_zero_head(zero: StructuralZero) -> str:
    stated = "" if zero.stated_formatted is None else f" ({zero.stated_formatted})"
    return f"  {zero.label} — {', '.join(zero.keys)}{stated}: {zero.reason}"


def _reversal_head(reversal) -> str:
    """The row's subject: the key, whose option it names, and what the user
    stated for it. Which KIND of distance this is belongs to the group heading
    above it, so it is not restated per row."""
    return (f"  {reversal.key} ({reversal.option}), stated "
            f"{reversal.stated_formatted}")


# ---------------------------------------------------------------------------
# The block. ONE function, for the reason in THE BINDING above.
# ---------------------------------------------------------------------------

def format_decomposition(outcome: DecompositionOutcome) -> str:
    """The `--decompose` block, or "" for silence (the flag not passed).

    THE ONLY public entry point of this module, and the only place the spread
    rows are assembled: there is no caller-reachable path to them without the
    level register, because the level register is rendered by these same lines
    (§5 mechanism 5, §7 formatter rule 1, test T7).

    §8's refusals are the assembler's judgments, not this module's: a
    `DecompositionRefusal` is RENDERED here with the reason it carries, never
    decided here.
    """
    if outcome is None:
        return ""

    if isinstance(outcome, DecompositionRefusal):
        # Subject first (the repo's own line doctrine), then the reason the
        # assembler recorded. `channel_id` is set by `one_channel`, which names
        # the channel carrying all of the run's spread and prints no numbers.
        subject = ("which risk decides it" if outcome.channel_id is None
                   else f"{channel(outcome.channel_id).label} carries all of this "
                        f"run's spread")
        return f"{subject} — not split: {outcome.reason}"

    dec: Decomposition = outcome
    verdict = dec.verdict
    spread, level, reversal = dec.spread, dec.level, dec.reversal
    lines: List[str] = []

    # --- the header: the verdict's own sentence, then how wide the scatter is
    # against the answer. `verdict.reason` is printed VERBATIM: it is one home
    # for that sentence (models.Verdict.reason), already state-aware, and a
    # second rendering of it here would be a second statement of one truth.
    live = len(dec.live_channel_ids)
    lines.append(f"which risk decides it — {dec.paths:,} futures, "
                 f"{live} channels live")
    lines.append(f"  {verdict.reason}")
    ratio = ("" if verdict.margin_pv == 0 else
             f" — {dec.sd_margin / abs(verdict.margin_pv):.1f}x the margin itself")
    lines.append(f"  that margin averages {_money(dec.mean_margin)} across those "
                 f"{dec.paths:,} futures and scatters by {_money(dec.sd_margin)} "
                 f"(1 s.d.){ratio}")

    # --- THE SPREAD
    lines.append("")
    lines.append(f"  THE SPREAD — where the {_money(dec.sd_margin)} comes from")
    # `ranked` is the register when it printed rows and None when it refused:
    # every later sentence that speaks of a leading row or of the table as a
    # whole reads it, so none of them can speak about a table that is not
    # there.
    ranked = None
    if isinstance(spread, RefusedSpread):
        # §0.1 item 7: the spread register refused by name (`P(f > 0) == 1`)
        # and the level and reversal registers still print below — the
        # binding runs one way. The sentence is the assembler's, printed
        # verbatim: it saw the data, and this module appends nothing to it.
        lines.append(f"  {spread.reason}")
    elif isinstance(spread, SpreadRegister):
        if not spread.rows:
            # A register with no rows is not a state the assembler produces:
            # a spread with nothing to show arrives as `RefusedSpread`, which
            # carries its reason. Printing a heading over no rows would leave
            # the reader to infer why.
            raise ValueError(
                "a SpreadRegister with no rows reached the formatter; a spread "
                "register that declines to print arrives as RefusedSpread with "
                "its reason, so this is a producer defect, not an empty table")
        ranked = spread
        lines.append(f"  {'channel':<{_LABEL_W}} {'alone':<19} "
                     f"{'with interaction':<19} {'changes sides':>19}")
        for row in sorted(spread.rows, key=_spread_sort_key):
            lines.extend(_spread_row_lines(row, dec.paths))

        # The residual line is printed, never inferred, and takes the refusal
        # branch when the CI permits (§4, §7 rule 5). `ResolvedInteraction` is
        # the only branch carrying a residual at all, so the refusal cannot
        # print one.
        interaction = spread.interaction
        total = (f"{_share(interaction.first_order_sum)} "
                 f"{_interval(interaction.first_order_sum_ci)}")
        if isinstance(interaction, ResolvedInteraction):
            clause = (f"  the first-order shares add to {total}, leaving "
                      f"{_share(interaction.residual)} "
                      f"{_interval(interaction.residual_ci)} that no single channel "
                      f"owns")
            if interaction.unstated_first_order_sum is not None:
                clause += (f"; {_share(interaction.unstated_first_order_sum)} "
                           f"of the shares above is a sum over channels sized "
                           f"entirely by figures the assistant chose")
            lines.append(clause)
        else:
            where = ("above the whole" if interaction.first_order_sum > 1
                     else "reaching the whole inside its own interval")
            lines.append(f"  the first-order shares add to {total} — {where}, so "
                         f"interaction is not measurable at {dec.paths:,} futures: "
                         f"estimator noise, not a finding; raise simulation.num_sims")

        # The two columns a reader will otherwise conflate, printed with THIS
        # household's two figures and nothing else; what the columns MEAN is
        # cited once (see CONDITIONALITY above) rather than restated on every
        # run.
        if spread.leading_channel_id is not None:
            leader = channel(spread.leading_channel_id)
            lead_row = next(r for r in spread.rows
                            if r.channel_id == spread.leading_channel_id)
            lead_shares = lead_row.shares
            if isinstance(lead_shares, ResolvedShares):
                lines.append(
                    f"  {leader.label}'s two figures are different kinds of number: "
                    f"{_share(lead_shares.alone)} of the spread's variance, "
                    f"{_flip(lead_row.flip)} of the futures changing sides [{GLOSSARY}]"
                )
    else:
        raise TypeError(
            f"the spread register is a {type(spread).__name__}, which is neither "
            f"a SpreadRegister nor a RefusedSpread")

    # --- THE LEVEL. Emitted by these same lines, unconditionally: there is no
    # branch above that can skip it, which is the binding (§5 mechanism 5).
    # Its baseline probability is printed ONCE, here, at one rounding of one
    # stored figure (§0.1 ruling 2), and its own sample is named because
    # `futures_margin`/`prob_best_base` are measured on THAT sample and are not
    # the header's figures (§0.1 ruling 1).
    lines.append("")
    lines.append(f"  THE LEVEL — what {level.paths:,} futures price that the central "
                 f"case does not: a cost it leaves out, not a risk")
    lines.append(f"  {'channel':<{_LABEL_W}} {'the margin moves by':<23}"
                 f" P({verdict.best} cheapest), from "
                 f"{_prob(level.prob_best_base)}")
    # The level rows are filed by TYPE into two groups; a row of any other type
    # would fall through both filters and vanish, so it raises instead.
    _require_types([r.level for r in level.rows],
                   (ResolvedLevel, IndistinguishableLevel), "the level register")
    ordered = sorted(level.rows, key=_level_sort_key)
    resolved_rows = [r for r in ordered if isinstance(r.level, ResolvedLevel)]
    flat_rows = [r for r in ordered if isinstance(r.level, IndistinguishableLevel)]
    for row in resolved_rows:
        lines.append(_level_row_line(row))
    if flat_rows:
        lines.append(f"  indistinguishable from zero at {level.paths:,} futures: "
                     + ", ".join(_indistinguishable_cell(r) for r in flat_rows))

    # The gap is the SUBTRACTION of the two figures printed beside it, never a
    # stored third number (§0.1 ruling 2): the draft this replaces printed a
    # gap that disagreed with them by $2,333, which implied a second estimate
    # of E[f] inside one block.
    gap = level.all_frozen_margin - level.futures_margin
    lines.append(
        f"  on its own {level.paths:,} paths: the central case {verdict.best} by "
        f"{_money(level.all_frozen_margin)}, the futures "
        f"{_money(level.futures_margin)}, a {_money(gap)} gap of which these "
        f"{len(level.rows)} shifts account for {_money(level.accounted_for)}; all "
        f"{len(level.rows)} frozen reproduces the central case to "
        f"{_deviation(level.all_frozen_deviation)}"
    )

    # The closing sentence has one branch per verdict STATE, chosen by
    # `verdict.state` and never by the sign of anything (§7 rule 2): a
    # formatter with one branch prints a disagreement explanation on an
    # agreement, which is §1's failure in miniature.
    if level.leading_channel_id is None:
        lines.append(f"  no channel's shift resolves at {level.paths:,} futures, so "
                     f"this run cannot say which one the futures price and the "
                     f"central case does not")
    else:
        mover = channel(level.leading_channel_id)
        mover_row = next(r for r in level.rows
                         if r.channel_id == level.leading_channel_id)
        mover_level = mover_row.level
        assert isinstance(mover_level, ResolvedLevel)   # leading_channel_id's contract
        mover_share = None if ranked is None else next(
            (r.shares for r in ranked.rows if r.channel_id == level.leading_channel_id),
            None,
        )
        # The mover's own share, as a parenthetical, so one phrase composes in
        # all three state branches. Absent when that channel's share did not
        # resolve — there is no attribute on an `UnresolvedShares` that could
        # supply it.
        mover_phrase = mover.label
        if isinstance(mover_share, ResolvedShares):
            mover_phrase += f" ({_share(mover_share.alone)} of the spread)"
        if verdict.state == "disagreement":
            # The causal clause is licensed only when pricing that channel the
            # central case's way puts `best` back in front of most futures —
            # the one probability comparison this module makes, and it is a
            # comparison against 0.5, not against another estimate.
            because = (f" — that channel is why the central case and the futures name "
                       f"different winners"
                       if mover_level.prob_best_frozen > 0.5 else "")
            lines.append(
                f"  {mover_phrase} moves the margin by "
                f"{_shift(mover_level.delta)}, and pricing it the central case's way "
                f"takes P({verdict.best} cheapest) to "
                f"{_prob(mover_level.prob_best_frozen)}{because}"
            )
        elif verdict.state == "tie":
            lines.append(
                f"  this run is too close to call as drawn, and the largest single "
                f"shift is {mover_phrase}, {_shift(mover_level.delta)}, taking "
                f"P({verdict.best} cheapest) to "
                f"{_prob(mover_level.prob_best_frozen)} — the channel to check before "
                f"trusting the tie"
            )
        else:
            lines.append(
                f"  {verdict.best} is cheapest either way, and the largest shift is "
                f"{mover_phrase}, {_shift(mover_level.delta)}: with it priced the "
                f"central case's way P({verdict.best} cheapest) is "
                f"{_prob(mover_level.prob_best_frozen)} against "
                f"{_prob(level.prob_best_base)} as drawn"
            )
        # The other half of §1's finding, when the spread's leader is not the
        # level's: a channel can carry the scatter and move the answer by
        # nothing that resolves. Typed, not inferred — an `IndistinguishableLevel`.
        if (ranked is not None and ranked.leading_channel_id is not None
                and ranked.leading_channel_id != level.leading_channel_id):
            top = channel(ranked.leading_channel_id)
            top_level = next((r.level for r in level.rows
                              if r.channel_id == ranked.leading_channel_id), None)
            top_shares = next((r.shares for r in ranked.rows
                               if r.channel_id == ranked.leading_channel_id), None)
            if (isinstance(top_level, IndistinguishableLevel)
                    and isinstance(top_shares, ResolvedShares)):
                lines.append(
                    f"  {top.label} is {_share(top_shares.alone)} of that spread and "
                    f"moves the margin by nothing that resolves "
                    f"({_shift(top_level.provisional_delta)} ± ${top_level.se:,.0f}) "
                    f"— pure risk, and not a cost the central case left out"
                )

    # --- THE REVERSAL REGISTER: structural zeros with the numbers they carry
    # (§0.1 ruling 5), then the rows grouped BY EXACTNESS — never ranked across
    # that split (§0, operator ruling).
    zero_keys = {z.reversal_key for z in reversal.structural_zeros
                 if z.reversal_key is not None}
    if reversal.structural_zeros:
        lines.append("")
        lines.append("  NOT DRAWN IN THIS RUN — zero spread by construction, not by "
                     "measurement")
        for zero in reversal.structural_zeros:
            lines.append(_structural_zero_head(zero))
            joined = next((r for r in reversal.exact if r.key == zero.reversal_key), None)
            if joined is not None:
                lines.extend(_reversal_detail_lines(joined))
    standalone = [r for r in reversal.exact if r.key not in zero_keys]
    if standalone:
        lines.append("")
        # The heading is about the KEY, not about each crossing on it: the
        # exactness gate licenses the engine to re-price this key by shifting
        # every path by one constant, which is a fact about the key. Whether a
        # given crossing on it is a property of the config or of a sample is
        # the grouping below, and conflating the two would over-claim for a
        # bisected crossing inside an exactly re-priced row.
        lines.append("  WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly")
        for row in standalone:
            lines.append(_reversal_head(row))
            lines.extend(_reversal_detail_lines(row))
    if reversal.estimated:
        lines.append("")
        lines.append("  WHAT WOULD HAVE TO CHANGE — keys the engine can only re-price "
                     "by re-simulating, each distance inside an interval")
        for row in reversal.estimated:
            lines.append(_reversal_head(row))
            lines.extend(_reversal_detail_lines(row))
    if not (reversal.exact or reversal.estimated or reversal.structural_zeros):
        # An empty register is DATA: it says the engine found no candidate
        # (§8's absence discipline), and rendering nothing at all would let a
        # reader take the absence for the finding. WHY there is no candidate is
        # the assembler's knowledge and the register carries no field for it,
        # so this line does not guess at one.
        lines.append("")
        lines.append("  NOTHING STATED IN THIS RUN CARRIES A REVERSAL DISTANCE the "
                     "engine can solve — no candidate was found, which is not a "
                     "finding that nothing would reverse the verdict")

    # --- §5 mechanism 3: the one sentence allowed to sit below the tables,
    # because it is about the table as a whole rather than about any row in it
    # (§7 rule 7). The superlative is GATED on provenance: when any width of
    # the leading row is somebody's guess, the block may not write "X decides
    # the spread of this answer" — it writes the share and names the figure to
    # check. Flipping one `sources:` entry changes this sentence (test T14).
    # A refused spread printed no ranking, so there is none to qualify.
    if ranked is not None:
        guessed = [r for r in ranked.rows
                   if any(w.source not in _SOURCED for w in r.widths)]
        if ranked.superlative_licensed and ranked.leading_channel_id is not None:
            leader = channel(ranked.leading_channel_id)
            lines.append("")
            lines.append(f"  {leader.label} decides the spread of this answer, and "
                         f"every width behind that row is yours or an anchor's")
        elif guessed:
            scope = ("every channel above is" if len(guessed) == len(ranked.rows)
                     else f"{len(guessed)} of the {len(ranked.rows)} channels above are")
            check = ("" if ranked.check_first is None else
                     f" — the figure to check first is {_width_cell(ranked.check_first)}")
            lines.append("")
            lines.append(f"  {scope} sized by a figure the assistant chose, not by you, "
                         f"so this ranking is a property of widths you did not "
                         f"state{check}")

    return "\n".join(lines)
