"""Which risk decides it — the rendered block.

`decomposition_run.decompose` fills the types in `decomposition.py`; this
module turns one `DecompositionOutcome` into the text a household reads, and
`serialization.decomposition_to_dict` turns the same object into the `--json`
block. Nothing here computes a statistic: every figure printed is a field, a
count of a field's entries (the live channels, the level rows), or a
subtraction or sum of PRINTED figures performed where it is printed.

WHAT THE BLOCK PRINTS (spec §0.1 item 35): figures, not interpretation. Every
line is exactly one of five kinds —

  - a HEADING or a column heading;
  - a FIGURE ROW: a register's figures with their intervals, "not resolved"
    where a figure did not resolve, and the source tag of every width;
  - a CROSSING: the key, the value, what the field reads on each side of it
    read upward, whether it was solved or sampled, and a sampled crossing's
    paths and seed; a stated path's flattened-path note prints beside its
    crossings, because it says how to read them (§0.1 item 26);
  - a REFUSAL: its code and the one measured fact that fired it, written by
    the party that refused and printed verbatim;
  - a STRUCTURAL-ZERO row, stating its kind's drawn-or-not fact (§0.1 item 27).

No line says why a figure is what it is, which figure matters, or what to run
next. What a figure means is `docs/reference/API_CONTRACT.md`'s, and
interpreting the block is the assistant's, bound by the skill.

THE BINDING, and why this file has exactly one public function. The spread
table may never be emitted without the level register beside it: its top row
can be a channel whose shift the same run cannot tell from zero, and a reader
handed the spread table alone quotes it. `decomposition.py` encodes that as
far as a dataclass reaches; this file completes it STRUCTURALLY:

  - `__all__` names one function, and it is the only module-level callable
    that takes a `Decomposition`;
  - no function named for a register exists, and only that function reads a
    register's rows, so no callable in the process returns the spread table;
  - the helpers take one row, one width, one interval, one boundary — never a
    register.

TWO STATES THAT ARE NOT NONE AND NOT ZERO. Resolved and unresolved figures
share no attribute name for their point estimate, so this module dispatches
on the TYPE and never with `getattr` or a `try`: a figure that did not
resolve prints behind the words "not resolved" and cannot be printed in a
resolved cell.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

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

_LABEL_W = 23


# ---------------------------------------------------------------------------
# Figure formatting — one rule per kind of figure, applied once
# ---------------------------------------------------------------------------

def _money(value: float) -> str:
    """A dollar figure with its natural sign: `$N`, `-$N`."""
    return f"${value:,.0f}" if value >= 0 else f"-${-value:,.0f}"


def _shift(value: float) -> str:
    """A dollar SHIFT, sign always shown: a freeze's direction is the point."""
    return f"+${value:,.0f}" if value >= 0 else f"-${-value:,.0f}"


def _faithful(value: float, places: int, scale: float = 1.0) -> str:
    """`value × scale` at `places` decimals, or at as many more as it takes for
    the printed figure not to say something the value does not.

    Two things a rounding may never do, and they are one defect (no share is
    ever clamped into [0, 1], in either direction):

      - print a figure that is not zero AS zero — a small negative share at two
        or three places reads as a signed zero, a measured nothing, the cheap
        all-clear in the costume of a rounding;
      - print a figure outside [0, 1] inside it, or one inside it outside — an
        unresolved share a hair above one reads as "all of the spread" on the
        row that did not resolve BECAUSE it is above one.

    So the decimals grow until neither happens. One rule for every share, flip
    and probability, so one figure never prints at two roundings. An exact zero
    is a zero and prints as one, without a sign.
    """
    number = float(value)
    if number == 0.0:
        return f"{0.0:.{places}f}"
    inside = 0.0 <= number <= 1.0
    for extra in range(10):
        text = f"{number * scale:.{places + extra}f}"
        shown = float(text) / scale
        if shown != 0.0 and (0.0 <= shown <= 1.0) == inside:
            return text
    return repr(number * scale)


def _share(value: float) -> str:
    """A Sobol share: two decimals, or more where two would lie (`_faithful`)."""
    return _faithful(value, 2)


def _interval(interval: Interval) -> str:
    return f"[{_share(interval.low)}, {_share(interval.high)}]"


def _flip(value: float) -> str:
    """A fraction of futures, one decimal: a flip in a few futures out of
    thousands is not zero, and does not print as one (`_faithful`)."""
    return f"{_faithful(value, 1, 100.0)}%"


def _flip_cell(value: float, interval: Interval) -> str:
    """The flip column WITH its width (§3.3, §0.1 item 10): the one figure here
    stated in decision space, so a point estimate with no width, beside
    neighbours that all carry one, would read as the most certain number in
    the table. The bracket takes its unit from the point estimate it follows."""
    return (f"{_flip(value)} [{_faithful(interval.low, 1, 100.0)}, "
            f"{_faithful(interval.high, 1, 100.0)}]")


def _prob(value: float) -> str:
    """A probability, two decimals — the block's only rounding of one, and
    never `0.00` for a probability that is not zero (`_faithful`)."""
    return _faithful(value, 2)


def _rate(value: float) -> str:
    return f"{value:.2%}"


def _solved_rate(value: float) -> str:
    """A crossing solved on the DETERMINISTIC verdict, at four decimals: a
    property of the config as it stands, the same at any seed. A sampled
    crossing prints at two, so the two never share a typography."""
    return f"{value:.4%}"


def _sampled_rate(value: float) -> str:
    """A crossing bisected on the futures, at two decimals ROUNDED DOWN.

    Every crossing reads its key upward, so the figure printed is one at which
    the field still says `was`. Rounded to the nearest instead, a crossing in
    the upper half of a hundredth printed a rate at which `--sweep` already
    says `becomes`."""
    return f"{math.floor(value * 10_000 + 1e-9) / 10_000:.2%}"


def _dollars(value: float) -> float:
    """A dollar figure AS PRINTED — rounded the way `_money` and `_shift` print
    it. Any figure the block derives from printed dollars (the level gap, the
    sum of its shifts) is derived from these, so a reader adding up the printed
    figures lands on the printed result (§0.1 ruling 2)."""
    return float(f"{value:.0f}")


def _not_resolved(figure: str, resolved: bool) -> str:
    """ONE rule for every figure that may not have resolved: it prints behind
    the words, so a reader quoting the cell quotes them too."""
    return figure if resolved else f"not resolved: {figure}"


# ---------------------------------------------------------------------------
# Row-level helpers. Each takes ONE row (or one width, one boundary) — never a
# register, so none of them can return a table (see THE BINDING above).
# ---------------------------------------------------------------------------

def _width_cell(width: Width) -> str:
    """One sizing figure with whose figure it is, inline on its own row.
    `formatted` is None for a key whose value is not a figure
    (`market_scenario.path`), and then the key stands alone."""
    head = width.key if width.formatted is None else f"{width.key}={width.formatted}"
    tag = width.source if width.anchor is None else f"{width.source}: {width.anchor}"
    note = "" if width.note is None else f" ({width.note})"
    return f"{head} [{tag}]{note}"


def _widths_line(widths: Sequence[Width]) -> str:
    """Every width of one row, never a subset: the `economy` row's cell must
    carry the `corr_inflation_*` keys AND the option vols they pull from, or
    the cell is itself a wrong answer (§4, §0.1 ruling 6)."""
    return "      sized by " + "; ".join(_width_cell(w) for w in widths)


def _spread_cells(row: SpreadRow) -> Tuple[str, str, str]:
    """ONE row's three table cells — alone, with interaction, flip. A row that
    did not resolve prints both shares behind "not resolved"; the flip column
    survives it (§7 rule 4)."""
    shares = row.shares
    flip = _flip_cell(row.flip, row.flip_ci)
    if isinstance(shares, ResolvedShares):
        return (f"{_share(shares.alone)} {_interval(shares.alone_ci)}",
                f"{_share(shares.with_interaction)} "
                f"{_interval(shares.with_interaction_ci)}",
                flip)
    return (_not_resolved(f"{_share(shares.provisional_alone)} "
                          f"{_interval(shares.provisional_alone_ci)}", False),
            _not_resolved(f"{_share(shares.provisional_with_interaction)} "
                          f"{_interval(shares.provisional_with_interaction_ci)}", False),
            flip)


def _spread_sort_key(row: SpreadRow) -> Tuple[int, float]:
    """Largest share first, unresolved rows last. Presentation only: which row
    is on top is the register's field, printed on a line of its own."""
    shares = row.shares
    if isinstance(shares, ResolvedShares):
        return (0, -shares.alone)
    return (1, -shares.provisional_alone)


def _level_point_signed(level) -> float:
    """ONE level row's point shift, with its sign, resolved or not — the
    figure the row prints."""
    if isinstance(level, ResolvedLevel):
        return level.delta
    if isinstance(level, IndistinguishableLevel):
        return level.provisional_delta
    raise TypeError(f"a level row carries a {type(level).__name__}, which is "
                    f"neither ResolvedLevel nor IndistinguishableLevel")


def _level_cells(row: LevelRow) -> Tuple[str, str]:
    """ONE level row's two cells: the shift with its one standard error, and
    the probability with that channel frozen."""
    level = row.level
    shift = f"{_shift(_level_point_signed(level))} (± ${level.se:,.0f})"
    return (_not_resolved(shift, isinstance(level, ResolvedLevel)),
            _prob(level.prob_best_frozen))


def _level_sort_key(row: LevelRow) -> Tuple[int, float]:
    """Resolved rows first, each group by the size of its printed shift."""
    return (0 if isinstance(row.level, ResolvedLevel) else 1,
            -abs(_level_point_signed(row.level)))


def _top_line(what: str, leading, unresolved_top, resolved: dict) -> Optional[str]:
    """The register's top row, printed as a figure only where the engine's one
    top-row rule resolved it (§0.1 item 35): a LEADING row. Where the top row
    did not resolve there is no line — "largest" over a figure the same block
    prints as not resolved would rank noise — and `--json` names that row.

    Read from the register and never re-derived here. `resolved` maps each
    row's channel to whether that row resolved, and a leader that is not a
    resolved row of the register is a producer defect, not a line to print."""
    if leading is None and unresolved_top is None:
        raise ValueError(
            f"a register with rows names no top row for its {what}: a register "
            f"with rows has one, so this is a producer defect")
    if leading is None:
        return None
    if resolved.get(leading) is not True:
        state = {False: "an unresolved row", None: "no row"}[resolved.get(leading)]
        raise TypeError(
            f"the register names {channel(leading).label} as its leading row for its "
            f"{what}, and that channel is {state} of the register: a producer defect")
    return f"  largest {what}: {channel(leading).label}"


# The four boundary kinds in words (§0.1 ruling 4). An unknown kind renders as
# its own field name rather than being dropped.
_BOUNDARY_LABEL = {
    "best": "the central case's winner",
    "runner_up": "the runner-up",
    "mc_best": "the option most futures call cheapest",
    "decisive": "the decisiveness verdict",
}

# The order the crossings print in, which is `BOUNDARY_FIELDS`' own order.
_BOUNDARY_ORDER = {field: index for index, field in enumerate(BOUNDARY_FIELDS)}


def _crossing(boundary, where: str) -> str:
    """"as it rises past <where>, <field> changes from <was> to <becomes>", and,
    when the searched range changes that field AGAIN on one side, a clause
    saying so (`further_changes`): without it a reader takes the state past the
    crossing to hold to the end of the bracket.

    EVERY boundary reads its key UPWARD: `was` is what the field says just below
    the value and `becomes` just above it. `was` and `becomes` are WORDS; this
    line refuses anything else where it is printed, because a boolean that
    reached a household once read "changes from True to False"."""
    label = _BOUNDARY_LABEL.get(boundary.verdict_field, boundary.verdict_field)
    for name in ("was", "becomes"):
        words = getattr(boundary, name)
        if not isinstance(words, str) or not words.strip():
            raise TypeError(
                f"{type(boundary).__name__}.{name} for {boundary.verdict_field!r} is "
                f"{words!r} ({type(words).__name__}), not words: this block prints "
                f"what the verdict reads on each side of a crossing, never a raw value")
    side = boundary.further_changes
    further = "" if side is None else f" (and changes again {side} it, inside the bracket)"
    return (f"as it rises past {where}, {label} changes from {boundary.was} "
            f"to {boundary.becomes}{further}")


def _solved_boundary_line(boundary: SolvedBoundary) -> str:
    return f"      solved on the central case: {_crossing(boundary, _solved_rate(boundary.value))}"


def _sampled_boundary_line(boundary: SampledBoundary) -> str:
    """A crossing bisected on the futures names its sample on its own line, so
    a quote of the line carries it."""
    return (f"      sampled on {boundary.curve_paths:,} paths at seed {boundary.seed}: "
            f"{_crossing(boundary, _sampled_rate(boundary.value))}")


def _estimated_boundary_line(boundary: EstimatedBoundary) -> str:
    where = (f"{_rate(boundary.value)} (inside {_rate(boundary.value_ci.low)}–"
             f"{_rate(boundary.value_ci.high)})")
    return (f"      estimated on {boundary.resimulation_paths:,} re-simulated paths: "
            f"{_crossing(boundary, where)}")


def _refused_boundary_lines(refused: Sequence[RefusedBoundary]) -> List[str]:
    """Boundaries that are not printed, recorded rather than dropped: a boundary
    that vanishes with no row is an absence a reader reads as "nothing here".
    One line per REASON, naming every field it refuses."""
    reasons: List[str] = []
    fields: dict = {}
    for item in refused:
        if item.reason not in fields:
            reasons.append(item.reason)
            fields[item.reason] = []
        fields[item.reason].append(
            _BOUNDARY_LABEL.get(item.verdict_field, item.verdict_field))
    lines: List[str] = []
    for reason in reasons:
        labels = fields[reason]
        named = (labels[0] if len(labels) == 1
                 else f"{', '.join(labels[:-1])} or {labels[-1]}")
        lines.append(f"      no boundary printed for {named} — {reason}")
    return lines


def _reference_clause(reference) -> str:
    anchor = "" if reference.anchor is None else f" [{reference.anchor}]"
    note = "" if reference.note is None else f" — {reference.note}"
    return f"{reference.label} {reference.formatted}{anchor}{note}"


def _bracket_line(low: float, high: float, source: str) -> str:
    """The bracket the key was searched inside, with WHOSE width it is (§6's
    correction: a bracket that turns an honest refusal into an answer shows
    the range it chose and whose figure it is)."""
    return f"      bracket searched: {_rate(low)}–{_rate(high)} [{source}]"


def _require_types(items: Sequence[object], allowed: Tuple[type, ...],
                   where: str) -> None:
    """Raise on any item that is none of `allowed`: a dispatch that filters by
    `isinstance` drops what it did not foresee without a word, and an absent
    row is what a reader takes for "nothing here"."""
    for item in items:
        if not isinstance(item, allowed):
            names = " or ".join(t.__name__ for t in allowed)
            raise TypeError(
                f"{where} carries a {type(item).__name__}, which is not a {names}: "
                f"this block cannot say what that figure is, so it does not print "
                f"it as one of them or drop it as though it were absent")


def _reversal_head(reversal) -> str:
    """The row's subject: the key, what the config states for it, and whose
    figure that is — the class the read-back of the same run prints."""
    return f"  {reversal.key}, stated {reversal.stated_formatted} [{reversal.stated_source}]"


def _reversal_detail_lines(reversal) -> List[str]:
    """ONE reversal row's figures: its bracket, its path note, its crossings —
    solved ones first, each typed on its own line — the fields it refused, and
    the cited figures on its axis."""
    lines: List[str] = [_bracket_line(reversal.bracket_low, reversal.bracket_high,
                                      reversal.bracket_source)]
    if reversal.path_note is not None:
        lines.append(f"      {reversal.path_note}")
    ordered = sorted(
        reversal.boundaries,
        key=lambda b: (_BOUNDARY_ORDER.get(b.verdict_field, len(_BOUNDARY_ORDER)),
                       b.verdict_field),
    )
    if isinstance(reversal, ExactReversal):
        _require_types(ordered, (SolvedBoundary, SampledBoundary),
                       f"{reversal.key}'s exact reversal row")
        lines.extend(_solved_boundary_line(b) for b in ordered
                     if isinstance(b, SolvedBoundary))
        lines.extend(_sampled_boundary_line(b) for b in ordered
                     if isinstance(b, SampledBoundary))
    else:
        _require_types(ordered, (EstimatedBoundary,),
                       f"{reversal.key}'s estimated reversal row")
        lines.extend(_estimated_boundary_line(b) for b in ordered)
    lines.extend(_refused_boundary_lines(reversal.refused_boundaries))
    if reversal.references:
        lines.append("      on the same axis: "
                     + "; ".join(_reference_clause(r) for r in reversal.references))
    return lines


# What each structural-zero KIND says about drawing (§0.1 item 27): the
# heading claims only what all three share, and each row states its own fact.
_DRAWN_FACT = {
    "stated_path": "no draw touches it",
    "no_pv_reach": "drawn, and reaching no option's present value",
    "dead_draw": "drawn, and reaching no cash flow",
}


def _structural_zero_line(zero: StructuralZero) -> str:
    if zero.kind not in _DRAWN_FACT:
        raise ValueError(
            f"a structural zero of kind {zero.kind!r} reached the formatter, which "
            f"can say whether {sorted(_DRAWN_FACT)} are drawn and not this one")
    return f"  {zero.label} — {', '.join(zero.keys)}: {_DRAWN_FACT[zero.kind]}"


def _refusal(code: str, reason: str) -> str:
    """A refusal as printed: its code, then the reason its producer wrote,
    verbatim. The formatter appends nothing — the party that declines owns
    the sentence."""
    return f"not split ({code}): {reason}"


# ---------------------------------------------------------------------------
# The block. ONE function, for the reason in THE BINDING above.
# ---------------------------------------------------------------------------

def format_decomposition(outcome: DecompositionOutcome) -> str:
    """The `--decompose` block, or "" for silence (the flag not passed).

    THE ONLY public entry point of this module, and the only place the spread
    rows are assembled: there is no caller-reachable path to them without the
    level register, because the level register is rendered by these same lines
    (§5 mechanism 5, §7 formatter rule 1, test T7).
    """
    if outcome is None:
        return ""

    if isinstance(outcome, DecompositionRefusal):
        return f"which risk decides it — {_refusal(outcome.code, outcome.reason)}"

    dec: Decomposition = outcome
    verdict = dec.verdict
    best = verdict.best
    spread, level, reversal = dec.spread, dec.level, dec.reversal
    lines: List[str] = [
        f"which risk decides it — {dec.paths:,} futures, "
        f"{len(dec.live_channel_ids)} channels live",
        f"  margin, the cheapest other option's present value minus {best}'s: "
        f"central case {_money(verdict.margin_pv)}; over this block's own "
        f"{dec.paths:,} futures, mean {_money(dec.mean_margin)} and s.d. "
        f"{_money(dec.sd_margin)}",
    ]

    # --- THE SPREAD
    lines.append("")
    lines.append("  THE SPREAD")
    if isinstance(spread, RefusedSpread):
        # The level and reversal registers still print below: the binding
        # runs one way.
        lines.append(f"  {_refusal(spread.code, spread.reason)}")
    elif isinstance(spread, SpreadRegister):
        if not spread.rows:
            raise ValueError(
                "a SpreadRegister with no rows reached the formatter; a spread "
                "register that declines to print arrives as RefusedSpread with "
                "its reason, so this is a producer defect, not an empty table")
        # The flip column counts futures in which re-drawing one channel moves
        # the sign of f — whether the CENTRAL CASE's winner is cheapest there —
        # so the heading names that winner.
        flip_head = f"flips whether {best} is cheapest"
        ordered = sorted(spread.rows, key=_spread_sort_key)
        cells = [_spread_cells(row) for row in ordered]
        widths = (max([len("alone")] + [len(c[0]) for c in cells]),
                  max([len("with interaction")] + [len(c[1]) for c in cells]))
        lines.append(f"  {'channel':<{_LABEL_W}} {'alone':<{widths[0]}}  "
                     f"{'with interaction':<{widths[1]}}  {flip_head}")
        for row, (alone, both, flip) in zip(ordered, cells):
            lines.append(f"  {channel(row.channel_id).label:<{_LABEL_W}} "
                         f"{alone:<{widths[0]}}  {both:<{widths[1]}}  {flip}")
            lines.append(_widths_line(row.widths))

        # The register's own sums, each labelled with what it is a sum of:
        # the shares are summed before rounding, so a reader adding the printed
        # column is told why the last digit can differ.
        interaction = spread.interaction
        residual = (f"{_share(interaction.residual)} {_interval(interaction.residual_ci)}"
                    if isinstance(interaction, ResolvedInteraction) else "not resolved")
        lines.append(f"  alone shares summed before rounding: "
                     f"{_share(interaction.first_order_sum)} "
                     f"{_interval(interaction.first_order_sum_ci)}; 1 minus that sum: "
                     f"{residual}")
        interacting = set(spread.interaction_channel_ids)
        parts = [f"{channel(row.channel_id).label} {_share(row.interaction_gap)} "
                 f"{_interval(row.interaction_gap_ci)}"
                 for row in ordered if row.channel_id in interacting]
        flat = [channel(row.channel_id).label for row in ordered
                if row.channel_id not in interacting]
        if flat:
            parts.append("not resolved: " + ", ".join(flat))
        lines.append("  with interaction minus alone, before rounding: " + "; ".join(parts))
        top = _top_line(
            "alone share", spread.leading_channel_id, spread.unresolved_top_channel_id,
            {row.channel_id: isinstance(row.shares, ResolvedShares) for row in ordered})
        if top is not None:
            lines.append(top)
    else:
        raise TypeError(
            f"the spread register is a {type(spread).__name__}, which is neither "
            f"a SpreadRegister nor a RefusedSpread")

    # --- THE LEVEL. Emitted by these same lines, unconditionally: there is no
    # branch above that can skip it, which is the binding.
    _require_types([r.level for r in level.rows],
                   (ResolvedLevel, IndistinguishableLevel), "the level register")
    # The gap and the sum are taken over the PRINTED dollars, never over a
    # stored third number (§0.1 ruling 2).
    frozen_printed = _dollars(level.all_frozen_margin)
    futures_printed = _dollars(level.futures_margin)
    shifts_printed = sum(_dollars(_level_point_signed(r.level)) for r in level.rows)
    lines.append("")
    lines.append(f"  THE LEVEL — the first {level.paths:,} of these futures")
    lines.append(f"  as drawn: mean margin {_money(futures_printed)}, P({best} cheapest) "
                 f"{_prob(level.prob_best_base)}; the central case's margin minus that "
                 f"mean: {_money(frozen_printed - futures_printed)}")
    ordered_level = sorted(level.rows, key=_level_sort_key)
    level_cells = [_level_cells(row) for row in ordered_level]
    shift_head = "margin shift, channel frozen (± 1 s.e.)"
    shift_w = max([len(shift_head)] + [len(c[0]) for c in level_cells])
    lines.append(f"  {'channel':<{_LABEL_W}} {shift_head:<{shift_w}}  "
                 f"P({best} cheapest), channel frozen")
    for row, (shift, prob) in zip(ordered_level, level_cells):
        lines.append(f"  {channel(row.channel_id).label:<{_LABEL_W}} "
                     f"{shift:<{shift_w}}  {prob}")
    lines.append(f"  the {len(level.rows)} shifts above, summed: {_money(shifts_printed)}")
    top = _top_line(
        "shift in size", level.leading_channel_id, level.unresolved_top_channel_id,
        {row.channel_id: isinstance(row.level, ResolvedLevel) for row in ordered_level})
    if top is not None:
        lines.append(top)

    # --- THE REVERSAL REGISTER: the structural zeros, then the rows grouped BY
    # EXACTNESS — never ranked across that split.
    if reversal.structural_zeros:
        lines.append("")
        lines.append("  ZERO SPREAD BY CONSTRUCTION, NOT BY MEASUREMENT")
        lines.extend(_structural_zero_line(zero) for zero in reversal.structural_zeros)
    if reversal.exact:
        lines.append("")
        lines.append("  WHAT WOULD HAVE TO CHANGE — keys the engine re-prices exactly")
        for row in reversal.exact:
            lines.append(_reversal_head(row))
            lines.extend(_reversal_detail_lines(row))
    if reversal.estimated:
        lines.append("")
        lines.append("  WHAT WOULD HAVE TO CHANGE — keys the engine cannot re-price "
                     "exactly")
        for row in reversal.estimated:
            lines.append(_reversal_head(row))
            lines.extend(_reversal_detail_lines(row))
    if not (reversal.exact or reversal.estimated):
        lines.append("")
        lines.append(f"  WHAT WOULD HAVE TO CHANGE — not solved: "
                     f"{reversal.no_distance_reason}")

    return "\n".join(lines)
