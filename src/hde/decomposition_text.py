"""Which risk decides it — the rendered block.

`decomposition_run.decompose` fills the types in `decomposition.py`; this
module turns one `DecompositionOutcome` into the text a household reads, and
`serialization.decomposition_to_dict` turns the same object into the `--json`
block. Nothing here computes a statistic: every figure printed is a field, or
a subtraction or sum of PRINTED figures performed where it is printed, so a
reader adding up what the block shows lands on what it says.

THE BINDING, and why this file has exactly one public function. The spread
table may never be emitted without the level register beside it: its top row
can be a channel whose shift the same run cannot tell from zero, and a reader
handed the spread table alone quotes it. `decomposition.py` encodes that as
far as a dataclass reaches; this file completes it STRUCTURALLY:

  - `__all__` names one function, and it is the only module-level callable
    that takes a `Decomposition`;
  - no function named for a register exists, and only that function reads a
    register's rows, so no callable in the process returns the spread table;
  - the helpers take one row, one width, one interval, one list of widths —
    never a register.

ONE HOME FOR EACH CONDITION. A clause whose truth turns on the run is
rendered from a field the assembler decided (who leads, which gaps resolve,
why a register is empty), or from ONE helper here that every site calls
(`_route` for "a larger run", `_provenance_lines` for whose inputs sized the
table), so no second site can print a condition the first one fixed. What
the columns MEAN is cited once per block (`GLOSSARY`), never restated per run.

TWO STATES THAT ARE NOT NONE AND NOT ZERO. Resolved and unresolved figures
share no attribute name for their point estimate, so this module dispatches
on the TYPE and never with `getattr` or a `try`: a figure that did not
resolve renders as its own sentence and cannot be printed in a resolved
column.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .decomposition import (
    BOUNDARY_FIELDS,
    Decomposition,
    DecompositionOutcome,
    DecompositionRefusal,
    EstimatedBoundary,
    EstimatedReversal,
    ExactReversal,
    IndistinguishableLevel,
    Interval,
    LEVEL_PATHS,
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
    UnresolvedShares,
    Width,
    channel,
)
from .decomposition_math import LEVEL_RESOLUTION_SIGMAS

__all__ = ["format_decomposition"]

# The one home for what the columns mean (see CONDITIONALITY above). Cited, not
# restated: `serialization.py`'s monthly-equivalent line already cites this doc
# the same way.
GLOSSARY = "docs/reference/API_CONTRACT.md, the decomposition block"

# The source classes a figure can carry (`sources.SourceEcho`'s own vocabulary:
# user | assistant | unattributed | sweep | anchor), worded as the read-back of
# the same run words them. `unattributed` is NOT "the assistant chose": it is a
# figure no `sources:` entry claims, typed with nobody's name on it, and
# reading that silence as the assistant's answer is the one inference the
# source echo exists to refuse (`config`'s decisiveness warning says the same).
# So the two are never counted, or worded, as one class here. §5 mechanism
# 3's gate itself is `superlative_licensed`, carried on the register.
_STATED_BY = {
    "user": "you stated this {what}",
    "assistant": "the assistant typed this {what}, not you",
    "anchor": "this {what} is anchor-sourced",
    "unattributed": "no sources: entry says who typed this {what}",
}

_LABEL_W = 23


def _route(paths: int, cap: int) -> str:
    """The ONE route clause, for every figure that did not resolve: what a
    larger run would do for a register that priced `paths` futures and can
    price at most `cap` on this run.

    Two caps bound a register, and `cap` is whichever binds: the evaluation
    ceiling (`Decomposition.max_paths`, above which the block refuses) for the
    spread register, and that or `LEVEL_PATHS` for the level register, which
    prices `min(N, LEVEL_PATHS)`. Below the cap a larger run prices more of
    them, named by both ways in (`--decompose=N` when that was passed,
    `simulation.num_sims` otherwise — raising the one that was not used changes
    nothing). AT the cap no larger run does: the budget refuses it, or the
    level register prices the same count again — and at the N the budget
    refusal itself recommends, "raise N" was an instruction this engine would
    refuse."""
    if paths < cap:
        return (f"raise the path count (simulation.num_sims, or N in --decompose=N) — "
                f"this register prices at most {cap:,} futures on this run")
    return (f"this register prices at most {cap:,} futures on this run and is at that "
            f"count, so no larger run resolves it here")


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
        unresolved share a hair above one reads as "all of the spread" on the row
        that says it did not resolve BECAUSE it is above one.

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
    thousands is not zero, and does not print as one (`_faithful`).
    """
    return f"{_faithful(value, 1, 100.0)}%"


def _flip_cell(value: float, interval: Interval) -> str:
    """The flip column WITH its width (§3.3, §0.1 item 10; §7's draft prints
    none and the draft loses).

    The reason this column in particular may not stand bare is the reason it
    exists: it is the one figure here stated in decision space, so a point
    estimate with no width, beside neighbours that all carry one, reads as the
    most certain number in the table. The bracket takes its unit from the
    point estimate it follows rather than repeating it twice more.
    """
    return (f"{_flip(value)} [{_faithful(interval.low, 1, 100.0)}, "
            f"{_faithful(interval.high, 1, 100.0)}]")


def _prob(value: float) -> str:
    """A probability, two decimals — the block's only rounding of one, and
    never `0.00` for a probability that is not zero (`_faithful`)."""
    return _faithful(value, 2)


def _ratio(value: float) -> str:
    """The scatter against the margin: one decimal at or above one, and below one
    at two or more (`_faithful`), because one decimal prints a ratio under a
    tenth as a tenth.
    """
    return f"{value:.1f}" if value >= 1.0 else _faithful(value, 2)


def _rate(value: float) -> str:
    return f"{value:.2%}"


def _solved_rate(value: float) -> str:
    """A crossing solved on the DETERMINISTIC verdict, at four decimals.

    The precision is the point, not decoration: a solved crossing is a
    property of the config as it stands, the same at any seed (pinned in
    `tests/test_decomposition_contract_doc.py`, which figures move with the
    sample). A sampled crossing prints at two decimals and says whose sample
    it is, so the two never share a typography (see `_sampled_boundary_line`).
    """
    return f"{value:.4%}"


def _sampled_rate(value: float) -> str:
    """A crossing bisected on the futures, at two decimals ROUNDED DOWN.

    Every crossing reads its key upward, so the figure printed is one at which
    the field still says `was`, and the next figure up is past the crossing.
    Rounded to the nearest instead, a crossing in the upper half of a
    hundredth printed a rate at which `--sweep` already says `becomes`, under
    a sentence saying the change happens as the key rises past it."""
    return f"{math.floor(value * 10_000 + 1e-9) / 10_000:.2%}"


def _deviation(value: float) -> str:
    """A measured deviation, for the two lines that print a PASSING gate's
    figure. Both gates fail closed on a figure that is not a finite number,
    so one reaching this line is a producer defect, and it raises rather than
    printing `nan` or `inf` as though that had been measured."""
    if value is None or not math.isfinite(value):
        raise ValueError(
            f"a deviation of {value!r} reached a line that prints a gate's passing "
            f"figure; a gate that meets a figure that is not a finite number "
            f"refuses, so this is a producer defect, not a measurement")
    return f"{value:.1e}"


def _verb(label: str, singular: str, plural: str) -> str:
    """The verb a channel's printed label takes: "the condo's costs carry",
    "the economy carries". Every label in `decomposition.CHANNELS` that ends
    in `s` is a plural noun phrase ("… costs"), and none of the others is."""
    return plural if label.endswith("s") else singular


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


def _spread_cells(row: SpreadRow) -> Tuple[str, str, str]:
    """ONE row's three table cells — alone, with interaction, flip — so the
    caller can size the columns to the widest cell rather than let a figure
    printed at more decimals push its row out of line."""
    shares = row.shares
    flip = _flip_cell(row.flip, row.flip_ci)
    if isinstance(shares, ResolvedShares):
        return (f"{_share(shares.alone)} {_interval(shares.alone_ci)}",
                f"{_share(shares.with_interaction)} "
                f"{_interval(shares.with_interaction_ci)}",
                flip)
    return ("not resolved", "not resolved", flip)


def _spread_row_lines(row: SpreadRow, paths: int,
                      columns: Tuple[int, int, int]) -> List[str]:
    label = channel(row.channel_id).label
    shares = row.shares
    alone, both, flip = _spread_cells(row)
    alone_w, both_w, flip_w = columns
    # Not resolved at this sample size: the estimates are KEPT and printed, in
    # their own words and on their own line, and there is no attribute on
    # that object that could put them in a resolved column (§4, §7 rule 6).
    # The flip column survives an unresolved row (§7 rule 4).
    lines: List[str] = [f"  {label:<{_LABEL_W}} {alone:<{alone_w}} {both:<{both_w}} "
                        f"{flip:>{flip_w}}"]
    if not isinstance(shares, ResolvedShares):
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


def _dollars(value: float) -> float:
    """A dollar figure AS PRINTED — rounded the way `_money` and `_shift` print
    it. Any figure the block derives from printed dollars (the level gap, the
    sum its shifts account for) is derived from these, so a reader adding up
    the printed figures lands on the printed result (§0.1 ruling 2)."""
    return float(f"{value:.0f}")


def _level_row_line(row: LevelRow) -> str:
    """A RESOLVED level row: its shift exceeds the resolution multiple of its
    standard error. The `±` figure is ONE standard error, as the column header
    says."""
    level = row.level
    assert isinstance(level, ResolvedLevel)   # the caller filed it by type
    label = channel(row.channel_id).label
    se = f"(± ${level.se:,.0f})"
    return (f"  {label:<{_LABEL_W}} {_shift(level.delta):>10} {se:<19} "
            f"-> {_prob(level.prob_best_frozen)}")


def _indistinguishable_cell(row: LevelRow) -> str:
    """A channel whose freeze moves the margin by no more than the resolution
    multiple of its standard error — a row a reader must SEE rather than an
    absence: it can be the channel carrying most of the spread, and that is the
    finding.
    """
    level = row.level
    assert isinstance(level, IndistinguishableLevel)
    return (f"{channel(row.channel_id).label} ({_shift(level.provisional_delta)} "
            f"± ${level.se:,.0f}, P -> {_prob(level.prob_best_frozen)})")


def _level_point_signed(level) -> float:
    """ONE level row's point shift, with its sign, resolved or not — the
    figure the row prints."""
    if isinstance(level, ResolvedLevel):
        return level.delta
    if isinstance(level, IndistinguishableLevel):
        return level.provisional_delta
    raise TypeError(f"a level row carries a {type(level).__name__}, which is "
                    f"neither ResolvedLevel nor IndistinguishableLevel")


# The words each source class is counted under in the provenance sentence, in
# the order they are listed. The tag after each is the class exactly as every
# width cell prints it, so a count can be checked against the tags above it.
_CLASS_WORDS = (
    ("assistant", "the assistant chose"),
    ("unattributed", "that no sources: entry claims"),
    ("user", "you stated"),
    ("anchor", "anchor-sourced"),
)


def _provenance_lines(widths_by_row: Sequence[Sequence[Width]], licensed: bool,
                      leader_label, check_first: Sequence[Width]) -> List[str]:
    """The sentence under the tables about WHOSE inputs sized them, built from
    the very widths the rows print (§0.1 item 34), so it cannot contradict a
    tag printed above it: it counts the distinct inputs by the class each one's
    tag names, says "entirely" only when none is the user's or an anchor's,
    and names the leading row's own unstated inputs to check first — all of
    them, since nothing measured an order among them.

    A licensed superlative (§5 mechanism 3) replaces it: every width on the
    leading row is the user's or an anchor's."""
    if licensed:
        return ["", f"  {leader_label} {_verb(leader_label, 'decides', 'decide')} the "
                    f"spread of this answer, and every width behind that row is yours "
                    f"or an anchor's"]
    distinct = {}
    for widths in widths_by_row:
        for width in widths:
            distinct.setdefault(width.key, width.source)
    counts = {}
    for source in distinct.values():
        counts[source] = counts.get(source, 0) + 1
    unstated = sum(n for source, n in counts.items() if source not in ("user", "anchor"))
    if not unstated:
        return []
    named = [source for source, _ in _CLASS_WORDS]
    words = dict(_CLASS_WORDS)
    order = named + sorted(set(counts) - set(named))
    parts = ", ".join(
        f"{counts[source]} {words.get(source, 'of source class ' + source)} [{source}]"
        for source in order if counts.get(source))
    extent = "entirely" if unstated == len(distinct) else "partly"
    check = ""
    if check_first:
        check = (f" — check first what sizes {leader_label}, the table's leading row: "
                 + "; ".join(_width_cell(w) for w in check_first))
    noun = "input" if len(distinct) == 1 else "inputs"
    return ["", f"  the {len(distinct)} {noun} sizing the channels above: {parts} — so "
                f"this ranking rests {extent} on inputs not marked as yours or an "
                f"anchor's{check}"]


def _level_sort_key(row: LevelRow) -> Tuple[int, float]:
    """Resolved rows first, each group by the size of its printed shift."""
    return (0 if isinstance(row.level, ResolvedLevel) else 1,
            -abs(_level_point_signed(row.level)))


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


def _crossing(boundary, where: str) -> str:
    """"as it rises past <where>, <field> changes from <was> to <becomes>", and,
    when the searched range changes that field AGAIN on one side, a clause
    saying so (`further_changes`): without it a reader takes the state past the
    crossing to hold to the end of the bracket, which `--sweep` contradicted on
    examples/mortgage_house_vs_rent.yaml.

    EVERY boundary reads its key UPWARD: `was` is what the field says just below
    the value and `becomes` just above it, whichever side this run's own value
    sits on — so the sentence names the direction, and `--sweep` at a point
    either side reads the same.

    `was` and `becomes` are the WORDS a household is shown. The contract's types
    refuse anything else when a boundary is built; this line refuses it again
    where it is printed, because what it guards is the printing: a boolean that
    reached a household once read "changes from True to False".
    """
    label = _BOUNDARY_LABEL.get(boundary.verdict_field, boundary.verdict_field)
    for name in ("was", "becomes"):
        words = getattr(boundary, name)
        if not isinstance(words, str) or not words.strip():
            raise TypeError(
                f"{type(boundary).__name__}.{name} for {boundary.verdict_field!r} is "
                f"{words!r} ({type(words).__name__}), not words: this block prints "
                f"what the verdict reads on each side of a crossing, never a raw value")
    side = boundary.further_changes
    further = ("" if side is None else
               f" (further changes lie {side} it inside the searched range; this row "
               f"reports the nearest)")
    return (f"        as it rises past {where}, {label} changes from {boundary.was} "
            f"to {boundary.becomes}{further}")


def _solved_boundary_line(boundary: "SolvedBoundary") -> str:
    """A crossing solved on the DETERMINISTIC verdict: a property of the config
    as it stands, which is why it prints at four decimals."""
    return (_crossing(boundary, _solved_rate(boundary.value))
            + _confirmed_clause(boundary.confirming_probabilities,
                                " — re-simulated there: "))


def _sampled_boundary_line(boundary: "SampledBoundary") -> str:
    """A crossing BISECTED ON THE MONTE CARLO CURVE, which is a property of a
    sample and not of the config.

    A solved crossing is the same figure at any seed and a sampled one moves
    with it (both pinned in `tests/test_reversal_register.py`). A reader handed
    both in one typography is being told a sample property is a config property
    — this feature's own cardinal error, committed by its own output. Three
    things separate them here, so the distinction survives losing any one: two
    decimals against four, this clause, and the grouping the caller prints them
    under.
    """
    return (_crossing(boundary, _sampled_rate(boundary.value))
            + _confirmed_clause(boundary.confirming_probabilities,
                                ", where the futures sit at ")
            + f" — bisected on {boundary.curve_paths:,} paths at seed {boundary.seed}, "
              f"so the crossing moves with the seed")


def _estimated_boundary_line(boundary: EstimatedBoundary) -> str:
    where = (f"{_rate(boundary.value)} (inside {_rate(boundary.value_ci.low)}–"
             f"{_rate(boundary.value_ci.high)} on {boundary.resimulation_paths:,} "
             f"re-simulated paths)")
    return _crossing(boundary, where)


def _refused_boundary_lines(refused: Sequence[RefusedBoundary]) -> List[str]:
    """Boundaries that exist on the curve and are not printed (§8 refusal 7),
    recorded rather than dropped: a boundary that vanishes with no row is an
    absence a reader reads as "nothing here".

    One line per REASON, naming every field it refuses: a key the exactness
    gate refused carries the gate's one sentence on all four fields, and
    printing it four times reads as four findings where there is one."""
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


def _stated_by_line(reversal) -> str:
    """WHOSE figure the stated value is, from `stated_source` — the class the
    read-back of the same run prints for that key (`sources.SourceEcho`), in
    that read-back's words. "You stated" only when the class is `user`: the
    fixture's renewal ladder is the assistant's and its contract rate an
    anchor's, and a row saying "your own figures" there contradicts the
    read-back two screens down. Every crossing below is solved on the config
    as it stands, WHOEVER typed it, so the row says whose it is instead."""
    what = "path" if reversal.path_note is not None else "value"
    source = reversal.stated_source
    words = _STATED_BY.get(source, "this {what}'s source class is " + str(source))
    return f"      {words.format(what=what)} [{source}]"


def _licence_line(reversal: ExactReversal) -> str:
    """The exactness gate's evidence, as a property of the KEY's shift — the
    licence for reading this axis off the run's own futures shifted rather than
    re-drawn (§6). It prints BEFORE the crossings: printed after a sampled one
    it read as a precision claim about that crossing, which is a property of a
    sample and carries its own clause saying so."""
    return (f"      re-priced exactly: moving this key shifts {reversal.option}'s present "
            f"value by the same amount on every path (to within "
            f"{_deviation(reversal.max_path_deviation_over_sd)} of its s.d., over "
            f"{reversal.probe_paths:,} probe paths) and leaves every other option's "
            f"untouched")


def _gate_refusal_line(reversal: EstimatedReversal) -> str:
    """The exactness gate's refusal, and what follows from it on THIS row.

    The measured figure prints only when it is a finite number: the gate
    refuses a present value that is not one (the figure is then NaN), and a
    shift that varies over paths with no spread of their own measures `inf`,
    and neither is a figure to print as a multiple of an s.d. The refusal's
    own sentence says which — it is every refused field's `reason`, printed
    once below. Nor is the figure worded as the cause: the gate also refuses
    a key that moves another option, whatever this one measured.

    Slice 1 estimates NOTHING (§6, §14): a refused key carries no boundary,
    so "the distance is estimated" would be false on every row the engine
    produces today, and the line says what is true of the row in hand. A
    figure that is not a finite number (or None) is WORDS — "could not be
    measured" — never `nan`, `inf` or `None` printed as a measurement."""
    option = reversal.option
    deviation = reversal.max_path_deviation_over_sd
    measured = (f"; how far moving it shifts {option}'s present value differently "
                f"across paths could not be measured"
                if deviation is None or not math.isfinite(deviation) else
                f"; moving it shifts {option}'s present value by amounts that differ "
                f"across paths by up to {deviation:.1e} of its s.d.")
    then = ("each distance below is located by re-simulating, inside an interval"
            if reversal.boundaries else
            "no distance on it is solved or estimated in this run")
    return f"      the exactness gate refused this key{measured} — so {then}"


def _reversal_detail_lines(reversal) -> List[str]:
    """The solved numbers of ONE reversal row — exact or estimated, each in its
    own vocabulary (§0: the two kinds share no field set and cannot be
    concatenated into one ordered table)."""
    exact = isinstance(reversal, ExactReversal)
    lines: List[str] = [_stated_by_line(reversal),
                        _licence_line(reversal) if exact
                        else _gate_refusal_line(reversal)]
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
                # "Solved on the central case" is true whoever typed the
                # figures; whose they are is `_stated_by_line`'s, above.
                lines.append(f"      {head}{bracket} — solved on the central case:")
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
    if reversal.path_note is not None:
        lines.append(f"      {reversal.path_note}")
    lines.extend(_refused_boundary_lines(reversal.refused_boundaries))
    if reversal.references:
        lines.append("      on the same axis: "
                     + "; ".join(_reference_clause(r) for r in reversal.references))
    return lines


# What each structural-zero KIND says about drawing (§0.1 item 27, the second).
# The section heading claims only what all three share — zero spread by
# construction — because two of the three ARE drawn: a heading reading "not
# drawn" sat over income, whose pay-drop events advance their own stream, and
# over dead-draw rows that say in their own words that they draw. So each row
# states its own fact, and an unknown kind raises rather than borrowing one.
_DRAWN_FACT = {
    "stated_path": "no draw touches it",
    "no_pv_reach": "drawn, and reaching no option's present value",
    "dead_draw": "drawn, and reaching no cash flow",
}


def _structural_zero_head(zero: StructuralZero) -> str:
    if zero.kind not in _DRAWN_FACT:
        raise ValueError(
            f"a structural zero of kind {zero.kind!r} reached the formatter, which "
            f"can say whether {sorted(_DRAWN_FACT)} are drawn and not this one")
    stated = "" if zero.stated_formatted is None else f" ({zero.stated_formatted})"
    return (f"  {zero.label} — {', '.join(zero.keys)}{stated}, "
            f"{_DRAWN_FACT[zero.kind]}: {zero.reason}")


def _reversal_head(reversal) -> str:
    """The row's subject: the key, whose option it names, and what the config
    states for it — whoever typed it, which `_stated_by_line` says next. Which
    KIND of distance this is belongs to the group heading above it, so it is
    not restated per row."""
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
        if outcome.channel_id is None:
            subject = "which risk decides it"
        else:
            label = channel(outcome.channel_id).label
            subject = (f"{label} {_verb(label, 'carries', 'carry')} all of this "
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
    # The margin is STATED here, not referred to: on a decisive run
    # `verdict.reason` prints a probability against the floor and no margin
    # at all, so "that margin" had nothing to point back to.
    ratio = ("" if verdict.margin_pv == 0 else
             f" — {_ratio(dec.sd_margin / abs(verdict.margin_pv))}x the margin itself")
    # The margin is the cheapest OTHER option's PV minus the winner's, so its
    # sign says who is ahead — stated in words, because "averages -$69,527"
    # left the reader to know the convention to know which side it favours.
    if dec.mean_margin > 0:
        side = (f" (above zero: on average {verdict.best} costs less than the "
                f"cheapest other option)")
    elif dec.mean_margin < 0:
        side = (f" (below zero: on average {verdict.best} costs more than the "
                f"cheapest other option)")
    else:
        side = ""
    # WHICH futures: the block draws its own sample (§0.1 item 1), and a
    # reader who subtracts the run's Monte Carlo means above will not land on
    # these figures, so the sentence says whose they are.
    lines.append(f"  the central case says {verdict.best} by "
                 f"{_money(verdict.margin_pv)}; across this block's own {dec.paths:,} "
                 f"futures, not the run's Monte Carlo sample, that margin averages "
                 f"{_money(dec.mean_margin)}{side} and scatters by "
                 f"{_money(dec.sd_margin)} (1 s.d.){ratio}")

    # --- THE SPREAD
    lines.append("")
    lines.append(f"  THE SPREAD — where the {_money(dec.sd_margin)} comes from")
    # `ranked` is the register when it printed rows and None when it refused:
    # every later sentence that speaks of a leading row or of the table as a
    # whole reads it, so none of them can speak about a table that is not
    # there. `leader_id` is the channel the block may name as leading the
    # table, None when it names none (see WHO LEADS below).
    ranked = None
    leader_id = None
    if isinstance(spread, RefusedSpread):
        # The spread register refused by name and the level and reversal
        # registers still print below — the binding runs one way. The
        # sentence is the assembler's, printed verbatim: it saw the data, and
        # this module appends nothing to it.
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
        by_id = {row.channel_id: row for row in spread.rows}
        # The flip column counts futures in which re-drawing one channel moves
        # the sign of f — whether the CENTRAL CASE's winner is cheapest there
        # — not futures whose cheapest option changes: a future that goes from
        # the condo to the house while rent stays beaten is not counted. So
        # the header names the winner it is about.
        flip_head = f"flips whether {verdict.best} is cheapest"
        cells = [_spread_cells(row) for row in spread.rows]
        columns = (max([19] + [len(c[0]) for c in cells]),
                   max([19] + [len(c[1]) for c in cells]),
                   max([19, len(flip_head)] + [len(c[2]) for c in cells]))
        lines.append(f"  {'channel':<{_LABEL_W}} {'alone':<{columns[0]}} "
                     f"{'with interaction':<{columns[1]}} {flip_head:>{columns[2]}}")
        for row in sorted(spread.rows, key=_spread_sort_key):
            lines.extend(_spread_row_lines(row, dec.paths, columns))

        # The residual line is printed, never inferred, and takes the refusal
        # branch when the CI permits. `ResolvedInteraction` is the only branch
        # carrying a residual at all, so the refusal cannot print one.
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
            # Two claims, each keyed on its own measurement (§0.1 item 28):
            # the RESIDUAL is refused on the sum's interval, and interaction
            # itself is "not measurable" only when no channel's own gap
            # between its two columns resolves — the column headed "with
            # interaction" measures it per channel, and a sentence keyed on
            # the residual alone contradicted that column when a gap resolved.
            where = ("above 1 across its whole interval, which is estimator noise: "
                     "first-order shares cannot add to more than the whole"
                     if interaction.first_order_sum_ci.low > 1 else
                     "an interval that reaches 1")
            head = (f"  the first-order shares add to {total} — {where}, so no "
                    f"residual is printed")
            interacting = [by_id[channel_id]
                           for channel_id in spread.interaction_channel_ids]
            if not interacting:
                lines.append(
                    f"{head}; no channel's with-interaction figure resolves above "
                    f"its alone figure either, so interaction is not measurable at "
                    f"{dec.paths:,} futures; {_route(dec.paths, dec.max_paths)}")
            else:
                named = "; ".join(
                    f"{channel(row.channel_id).label} by "
                    f"{_share(row.interaction_gap)} {_interval(row.interaction_gap_ci)}"
                    for row in interacting)
                lines.append(
                    f"{head}; interaction does resolve, as a with-interaction figure "
                    f"above its alone figure: {named}")

        # WHO LEADS is the register's, decided once in the assembler over the
        # point estimates of every row (`SpreadRegister`): the top row either
        # leads (`leading_channel_id`) or did not resolve
        # (`unresolved_top_channel_id`), and then THAT row is named with its
        # provisional figure and nothing leads — here, in the provenance
        # sentence below, and in the JSON, which reads the same fields.
        leader_id = spread.leading_channel_id
        if spread.unresolved_top_channel_id is not None:
            top_row = by_id[spread.unresolved_top_channel_id]
            top = top_row.shares
            if not isinstance(top, UnresolvedShares):
                raise TypeError(
                    f"the spread register names channel {top_row.channel_id} as its "
                    f"unresolved top row, and that row's shares are a "
                    f"{type(top).__name__}: a producer defect, not a sentence to print")
            lines.append(
                f"  the largest share is on {channel(top_row.channel_id).label}: "
                f"{_share(top.provisional_alone)} {_interval(top.provisional_alone_ci)} "
                f"alone, not resolved at {dec.paths:,} futures — so no channel leads "
                f"this table; {_route(dec.paths, dec.max_paths)}")
        # The two columns a reader will otherwise conflate, printed with THIS
        # household's two figures and nothing else; what the columns MEAN is
        # cited once (see CONDITIONALITY above) rather than restated on every
        # run.
        if leader_id is not None:
            leader = channel(leader_id)
            lead_row = by_id[leader_id]
            lead_shares = lead_row.shares
            if isinstance(lead_shares, ResolvedShares):
                lines.append(
                    f"  on {leader.label} the two figures are different kinds of "
                    f"number: {_share(lead_shares.alone)} of the spread's variance, "
                    f"{_flip(lead_row.flip)} of the futures flipping whether "
                    f"{verdict.best} is cheapest [{GLOSSARY}]"
                )
    else:
        raise TypeError(
            f"the spread register is a {type(spread).__name__}, which is neither "
            f"a SpreadRegister nor a RefusedSpread")

    # --- THE LEVEL. Emitted by these same lines, unconditionally: there is no
    # branch above that can skip it, which is the binding. Its baseline
    # probability is printed ONCE, here, at one rounding of one stored figure,
    # and its own sample is named because `futures_margin`/`prob_best_base`
    # are measured on THAT sample and are not the header's figures.
    level_cap = min(LEVEL_PATHS, dec.max_paths)
    lines.append("")
    lines.append(f"  THE LEVEL — what {level.paths:,} of these futures price that the "
                 f"central case does not: a cost or saving it leaves out, not a risk")
    lines.append(f"  {'channel':<{_LABEL_W}} {'the margin moves by (± 1 s.e.)':<30}"
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
        lines.append(f"  within {LEVEL_RESOLUTION_SIGMAS:g} s.e. of zero, so "
                     f"indistinguishable from it at {level.paths:,} futures: "
                     + ", ".join(_indistinguishable_cell(r) for r in flat_rows))

    # The gap and the sum are taken over the PRINTED dollars, never over a
    # stored third number and never over figures the reader cannot see:
    # adding up what the block prints lands on what it says (§0.1 ruling 2).
    frozen_printed = _dollars(level.all_frozen_margin)
    futures_printed = _dollars(level.futures_margin)
    shifts_printed = sum(_dollars(_level_point_signed(r.level)) for r in level.rows)
    lines.append(
        f"  on its own {level.paths:,} paths: the central case {verdict.best} by "
        f"{_money(frozen_printed)}, the futures {_money(futures_printed)}, a "
        f"{_money(frozen_printed - futures_printed)} gap of which these "
        f"{len(level.rows)} shifts account for {_money(shifts_printed)}; every "
        f"channel frozen reproduces the central case to within "
        f"{_deviation(level.all_frozen_deviation)} dollars"
    )

    # The closing sentence has one branch per verdict STATE, chosen by
    # `verdict.state` and never by the sign of anything: a formatter with one
    # branch prints a disagreement explanation on an agreement.
    #
    # WHICH channel it names is the register's (`LevelRegister`): the top row
    # by |point shift| either leads or did not resolve. When it did not, THAT
    # row is named with its provisional figure and the sentence says it did
    # not resolve — never a smaller resolved row promoted as "the largest".
    if level.unresolved_top_channel_id is not None:
        top_id = level.unresolved_top_channel_id
        top_level = next(r.level for r in level.rows if r.channel_id == top_id)
        if not isinstance(top_level, IndistinguishableLevel):
            raise TypeError(
                f"the level register names channel {top_id} as its unresolved top "
                f"row, and that row is a {type(top_level).__name__}: a producer "
                f"defect, not a sentence to print")
        figure = (f"{channel(top_id).label} at {_shift(top_level.provisional_delta)} ± "
                  f"${top_level.se:,.0f} (P({verdict.best} cheapest) -> "
                  f"{_prob(top_level.prob_best_frozen)} priced the central case's way)")
        if any(isinstance(r.level, ResolvedLevel) for r in level.rows):
            head = (f"the largest shift by point estimate, {figure}, does not resolve "
                    f"at {level.paths:,} futures")
        else:
            head = (f"no channel's shift resolves at {level.paths:,} futures, the "
                    f"largest by point estimate included: {figure}")
        if verdict.state == "tie":
            text = (f"this run is too close to call as drawn, and {head} — so this "
                    f"register cannot name a channel to check before trusting the tie")
        elif verdict.state == "disagreement":
            text = (f"{head} — so this run cannot say which channel puts the central "
                    f"case and the futures on different winners")
        else:
            text = (f"{head} — so this run cannot say which one the futures price and "
                    f"the central case does not")
        lines.append(f"  {text}; {_route(level.paths, level_cap)}")
    elif level.leading_channel_id is None:
        raise ValueError(
            "the level register names neither a leading row nor an unresolved top "
            "row; a register with rows has a top row, so this is a producer defect")
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
                f"  {mover_phrase} {_verb(mover.label, 'moves', 'move')} the margin by "
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
            # "Cheapest either way" is the same claim the disagreement branch
            # licenses its causal clause with — `best` in front of most futures
            # — made twice, as drawn and priced the central case's way, so it
            # is gated the same way on both figures it names. Below 0.5 on
            # either, the sentence says which one fell, and no more.
            fell = [where for where, p in (("as drawn", level.prob_best_base),
                                           ("priced that way",
                                            mover_level.prob_best_frozen))
                    if not p > 0.5]
            tail = ("" if not fell else
                    f" — {' and '.join(fell)}, {verdict.best} is cheapest in no more "
                    f"than half of these futures")
            lead = (f"{verdict.best} is cheapest either way, and the largest shift is"
                    if not fell else "the largest shift is")
            lines.append(
                f"  {lead} {mover_phrase}, {_shift(mover_level.delta)}: with it priced "
                f"the central case's way P({verdict.best} cheapest) is "
                f"{_prob(mover_level.prob_best_frozen)} against "
                f"{_prob(level.prob_best_base)} as drawn{tail}"
            )
        # The other half of §1's finding, when the spread's leader is not the
        # level's: a channel can carry the scatter and move the answer by
        # nothing that resolves. Typed, not inferred — an `IndistinguishableLevel`.
        # Only a channel the block names as leading (`leader_id`) can be "the
        # spread's" here: a resolved row smaller than an unresolved one is not.
        # It says what an unresolved shift licenses and no more: that this run
        # cannot tell the shift from zero — never "pure risk, and not a cost the
        # central case left out", which is a claim the shift is zero.
        if (ranked is not None and leader_id is not None
                and leader_id != level.leading_channel_id):
            top = channel(leader_id)
            top_level = next((r.level for r in level.rows
                              if r.channel_id == leader_id), None)
            top_shares = next((r.shares for r in ranked.rows
                               if r.channel_id == leader_id), None)
            if (isinstance(top_level, IndistinguishableLevel)
                    and isinstance(top_shares, ResolvedShares)):
                lines.append(
                    f"  {top.label} {_verb(top.label, 'is', 'are')} "
                    f"{_share(top_shares.alone)} of that spread and "
                    f"{_verb(top.label, 'moves', 'move')} the margin by nothing that "
                    f"resolves at {level.paths:,} futures "
                    f"({_shift(top_level.provisional_delta)} ± ${top_level.se:,.0f}): "
                    f"{_verb(top.label, 'it widens', 'they widen')} the futures, and this "
                    f"run cannot tell {_verb(top.label, 'its', 'their')} shift from zero"
                )

    # --- THE REVERSAL REGISTER: structural zeros with the numbers they carry,
    # then the rows grouped BY EXACTNESS — never ranked across that split.
    zero_keys = {z.reversal_key for z in reversal.structural_zeros
                 if z.reversal_key is not None}
    if reversal.structural_zeros:
        lines.append("")
        lines.append("  ZERO SPREAD BY CONSTRUCTION, NOT BY MEASUREMENT")
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
        # What follows the gate's refusal is each row's to say: slice 1
        # estimates nothing, so a heading promising a distance inside an
        # interval would be false over every row the engine produces today.
        lines.append("  WHAT WOULD HAVE TO CHANGE — keys the engine cannot re-price "
                     "exactly")
        for row in reversal.estimated:
            lines.append(_reversal_head(row))
            lines.extend(_reversal_detail_lines(row))
    if not (reversal.exact or reversal.estimated):
        # No row carries a distance. WHAT was searched, and the route to what
        # was not, is the producer's sentence (`no_distance_reason`), printed
        # verbatim: it knows the candidate set and this module does not, and
        # an empty section would let a reader take the absence for a finding.
        lines.append("")
        lines.append(f"  WHAT WOULD HAVE TO CHANGE — {reversal.no_distance_reason}")

    # --- The one sentence allowed to sit below the tables, because it is
    # about the table as a whole rather than about any row in it. The
    # superlative is GATED on provenance: when any width of the leading row is
    # not the user's or an anchor's, the block may not write "X decides the
    # spread of this answer" — it says whose figures sized the table and names
    # the leading row's figures to check. A refused spread printed no ranking,
    # so there is none to qualify.
    if ranked is not None:
        lines.extend(_provenance_lines(
            [row.widths for row in ranked.rows], ranked.superlative_licensed,
            None if leader_id is None else channel(leader_id).label,
            ranked.check_first))

    return "\n".join(lines)
