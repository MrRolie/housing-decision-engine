"""Which risk decides it — the rendered block.

`decomposition_run.decompose` fills the types in `decomposition.py`; this
module turns one `DecompositionOutcome` into the text a household reads, and
`serialization.decomposition_to_dict` turns the same object into the `--json`
block. Nothing here computes a statistic: every figure printed is a field, a
count of a field's entries (the live channels, the level rows), or a
subtraction or sum of PRINTED figures performed where it is printed.

WHAT THE BLOCK PRINTS (spec §0.1 items 35, 52 and 56): figures, not
interpretation. The kinds of line it may print, and what every field means,
are `docs/reference/API_CONTRACT.md`'s, under "The text block" and the
field bullets of its `decomposition` section. A refusal's reason and a
width's tag are written by the party that produced them and printed verbatim.

No line says why a figure is what it is, which figure matters, or what to run
next. Interpreting the block is the assistant's, bound by the skill.

THE BINDING, and why this file has exactly one public function. The spread
table may never be emitted without the level register beside it: its top row
can be a channel whose shift the same run cannot tell from zero, and a reader
handed the spread table alone quotes it. `decomposition.py` encodes that as
far as a dataclass reaches; this file completes it STRUCTURALLY:

  - `__all__` names one function, and it is the only module-level callable
    that takes a `Decomposition`;
  - no function named for a register exists, and only that function reads a
    register's rows, so no callable in the process returns the spread table;
  - the helpers take one row, one width, one interval — never a register.

TWO STATES THAT ARE NOT NONE AND NOT ZERO. Resolved and unresolved figures
share no attribute name for their point estimate, so this module tells them
apart by TYPE and never with `getattr` or a `try`: a figure that did not
resolve prints behind the words "not resolved" and cannot be printed in a
resolved cell.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import List, Optional, Sequence, Tuple

from .decomposition_math import sum_lies_above_one
from .decomposition_run import signed_dollars

from .decomposition import (
    Decomposition,
    DecompositionOutcome,
    DecompositionRefusal,
    Interval,
    LevelRow,
    RefusedSpread,
    ResolvedInteraction,
    ResolvedLevel,
    ResolvedShares,
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
    """A dollar figure with its natural sign, `$N` or `-$N`; one whose printed
    digits are all zero prints unsigned (`decomposition_run.signed_dollars`)."""
    return signed_dollars(value)


def _shift(value: float) -> str:
    """A dollar SHIFT, its sign shown, `+$N` or `-$N`: a freeze's direction is
    the point. A shift that prints as zero dollars shows no direction, and
    prints unsigned, as `_money` prints any zero."""
    text = signed_dollars(value)
    return text if text == "$0" or text.startswith("-") else f"+{text}"


def _faithful(value: float, places: int, scale: float = 1.0) -> str:
    """`value × scale` at `places` decimals, or at as many more as it takes for
    the printed figure not to say something the value does not.

    Three things a rounding may never do, and they are one defect (no share is
    ever clamped into [0, 1], in either direction):

      - print a figure that is not zero AS zero — a small negative share at two
        or three places reads as a signed zero, a measured nothing, the cheap
        all-clear in the costume of a rounding;
      - print a figure that is not one AS one — a probability over thousands of
        futures, all but one of them on one side, printed as though every one
        were (§0.1 item 51);
      - print a figure outside [0, 1] inside it, or one inside it outside — an
        unresolved share a hair above one reads as "all of the spread" on the
        row that did not resolve BECAUSE it is above one.

    So the decimals grow until none happens. One rule for every share, flip
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
        if (shown != 0.0 and (shown == 1.0) == (number == 1.0)
                and (0.0 <= shown <= 1.0) == inside):
            return text
    return repr(number * scale)


def _share(value: float) -> str:
    """A share: two decimals, or more where two would lie (`_faithful`)."""
    return _faithful(value, 2)


def _interval(interval: Interval) -> str:
    return f"[{_share(interval.low)}, {_share(interval.high)}]"


def _flip(value: float) -> str:
    """The flip column as a percentage at one decimal, or more where one would
    lie (`_faithful`)."""
    return f"{_faithful(value, 1, 100.0)}%"


def _flip_cell(value: float, interval: Interval) -> str:
    """The flip column WITH its interval (§3.3, §0.1 item 10): a point
    estimate with no width, beside neighbours that all carry one, would read
    as the most certain number in the table. The bracket takes its unit from
    the point estimate it follows."""
    return (f"{_flip(value)} [{_faithful(interval.low, 1, 100.0)}, "
            f"{_faithful(interval.high, 1, 100.0)}]")


def _prob(value: float) -> str:
    """A probability at two decimals, or more where two would lie
    (`_faithful`)."""
    return _faithful(value, 2)


def _ceiled_threshold(value: float) -> str:
    """A move threshold at three significant figures, CEILED. A row says no
    move was above it, so the printed figure is never below the value it
    stands for, and the sentence holds at the figure printed. Taken on the
    float's exact decimal value. The threshold is the identity's budget, which
    a row reaches only where `decomposition_math.identity_holds` held against
    it, so it is finite; it is a positive multiple of a float spacing."""
    exact = Decimal(value)
    step = Decimal(1).scaleb(exact.adjusted() - 2)
    return f"{float(exact.quantize(step, rounding=ROUND_CEILING)):.3g}"


def _dollars(value: float) -> float:
    """A dollar figure AS PRINTED — rounded the way `_money` and `_shift` print
    its magnitude. Any figure the block derives from printed dollars (the level gap, the
    sum of its shifts) is derived from these, so a reader adding up the printed
    figures lands on the printed result (§0.1 ruling 2)."""
    return float(f"{value:.0f}")


def _not_resolved(figure: str, resolved: bool) -> str:
    """ONE rule for every figure that may not have resolved: it prints behind
    the words, so a reader quoting the cell quotes them too."""
    return figure if resolved else f"not resolved: {figure}"


# ---------------------------------------------------------------------------
# Row-level helpers. Each takes ONE row (or one width) — never a register, so
# none of them can return a table (see THE BINDING above).
# ---------------------------------------------------------------------------

def _width_cell(width: Width) -> str:
    """One width with its tag, inline on its own row; a width with no
    `formatted` prints its key alone. The tag is the one the producer took
    from the read-back, printed as it is (the producer refuses a width with
    none: `untagged_width`)."""
    head = width.key if width.formatted is None else f"{width.key}={width.formatted}"
    note = "" if width.note is None else f" ({width.note})"
    return f"{head} [{width.tag}]{note}"


def _widths_line(widths: Sequence[Width]) -> str:
    """Every width of one row, never a subset, in the row's own order
    (`decomposition_run.width_keys`)."""
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
    figure the row prints. Which kind a row is has been checked where the
    register was built (`decomposition_run._level_point`)."""
    return level.delta if isinstance(level, ResolvedLevel) else level.provisional_delta


def _level_cells(row: LevelRow) -> Tuple[str, str]:
    """ONE level row's two cells: the shift with its one standard error, and
    the probability with that channel frozen."""
    level = row.level
    shift = f"{_shift(_level_point_signed(level))} (± ${level.se:,.0f})"
    return (_not_resolved(shift, isinstance(level, ResolvedLevel)),
            _prob(level.prob_best_frozen))


def _level_sort_key(row: LevelRow) -> Tuple[int, float]:
    """Resolved rows first, each group by the size of its shift before
    rounding."""
    return (0 if isinstance(row.level, ResolvedLevel) else 1,
            -abs(_level_point_signed(row.level)))


def _top_line(what: str, leading: Optional[int]) -> Optional[str]:
    """The register's top row, printed as a figure only where the engine's one
    top-row rule resolved it (§0.1 item 35): a LEADING row. Where the top row
    did not resolve there is no line — "largest" over a figure the same block
    prints as not resolved would rank noise — and `--json` names that row.
    Read from the register (`decomposition_run._top_row` decides it), never
    re-derived here."""
    if leading is None:
        return None
    return f"  largest {what}: {channel(leading).label}"


def _structural_zero_line(zero: StructuralZero) -> str:
    """One `dead_draw` row of the spread register's `structural_zeros` (the
    only kind `SpreadRegister` and `RefusedSpread` hold). Its words are said
    of its stream by name, and its keys follow as the keys that size that
    stream's draws; nothing is said of their cash flows (§0.1 items 39 and
    40)."""
    sized = f"; sized by {', '.join(zero.keys)}" if zero.keys else ""
    return (f"  {zero.label}: drawn on these {zero.measured_paths:,} futures, and "
            f"re-drawing it moved no option's present value by more than "
            f"${_ceiled_threshold(zero.move_threshold)}{sized}")


def _refusal(code: str, reason: str) -> str:
    """A refusal as printed: its code, then the reason its producer wrote,
    verbatim. The formatter appends nothing — the party that declines owns
    the sentence."""
    return f"({code}): {reason}"


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
        return f"which risk decides it — not split {_refusal(outcome.code, outcome.reason)}"

    dec: Decomposition = outcome
    verdict = dec.verdict
    best = verdict.best
    spread, level = dec.spread, dec.level
    lines: List[str] = [
        f"which risk decides it — {dec.paths:,} futures, "
        f"{len(dec.live_channel_ids)} channels live on them",
        f"  margin, the cheapest other option's present value minus {best}'s: "
        f"central case {_money(verdict.margin_pv)}; over this block's own "
        f"{dec.paths:,} futures, mean {_money(dec.mean_margin)} and s.d. "
        f"{_money(dec.sd_margin)}",
    ]

    # --- THE SPREAD
    lines.append("")
    lines.append("  THE SPREAD")
    if isinstance(spread, RefusedSpread):
        # The level register still prints below: the binding runs one way.
        lines.append(f"  not split {_refusal(spread.code, spread.reason)}")
    elif isinstance(spread, SpreadRegister):
        if not spread.rows:
            raise ValueError(
                "a SpreadRegister with no rows reached the formatter; a spread "
                "register that declines to print arrives as RefusedSpread with "
                "its reason, so this is a producer defect, not an empty table")
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
        # column is told why the last digit can differ. The residual prints
        # with its interval where it resolved, "not resolved" where the sum's
        # interval includes 1, and not at all where it lies above 1 (§4).
        interaction = spread.interaction
        summed = (f"  alone shares summed before rounding: "
                  f"{_share(interaction.first_order_sum)} "
                  f"{_interval(interaction.first_order_sum_ci)}")
        if isinstance(interaction, ResolvedInteraction):
            summed += (f"; 1 minus that sum: {_share(interaction.residual)} "
                       f"{_interval(interaction.residual_ci)}")
        elif not sum_lies_above_one(interaction.first_order_sum_ci.low):
            summed += "; 1 minus that sum: not resolved"
        lines.append(summed)
        # Every row's gap, in the table's order, each behind "not resolved:"
        # where it did not resolve: the one rule for such a figure.
        interacting = set(spread.interaction_channel_ids)
        parts = [f"{channel(row.channel_id).label} "
                 + _not_resolved(f"{_share(row.interaction_gap)} "
                                 f"{_interval(row.interaction_gap_ci)}",
                                 row.channel_id in interacting)
                 for row in ordered]
        lines.append("  with interaction minus alone, before rounding: " + "; ".join(parts))
        top = _top_line("alone share", spread.leading_channel_id)
        if top is not None:
            lines.append(top)
    else:
        raise TypeError(
            f"the spread register is a {type(spread).__name__}, which is neither "
            f"a SpreadRegister nor a RefusedSpread")
    # The rows measured on these same futures, under this register's heading
    # whether or not it refused (§0.1 item 48).
    lines.extend(_structural_zero_line(zero) for zero in spread.structural_zeros)

    # --- THE LEVEL. Emitted by these same lines, unconditionally: there is no
    # branch above that can skip it, which is the binding.
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
    top = _top_line("shift in size", level.leading_channel_id)
    if top is not None:
        lines.append(top)

    return "\n".join(lines)
