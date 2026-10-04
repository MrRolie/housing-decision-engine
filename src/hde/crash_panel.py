"""Crash stress panel: stated one-time drops in the home's value, each priced
as a conditional row.

Contract: docs/specs/2026-10-03-crash-stress-panel.md — §3.1 the flag, §4 the
multiplier, §7 the refusals. A row says "if the value drops by `d` in year `c`
and comes back in the stated way"; nothing here says how likely a drop is.

`drop_path` is the ONE home of the multiplier m(t). The central line and the
Monte Carlo read its tuple; neither re-derives it.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .anchors import ANCHORS
from .break_even import solve_crossings
from .config import single_path_run
from .deterministic import (_effective_growth_rate, compute_deterministic, owned_balance,
                            renewal_segments_for, renewals_priced_inside)
from .models import ComparisonSpec, EconomicParams, compute_verdict
from .monte_carlo import run_monte_carlo
from .rates import effective_mortgage_rate
from .sweep import _breaches, affordability_of

# §7: the largest drop the panel accepts, and the most rows one grid may ask for.
DROP_CEILING = 0.99
MAX_ROWS = 48

REFUSAL_CODES = (
    "drop_out_of_range",      # X1
    "year_out_of_range",      # X2
    "recovery_malformed",     # X3
    "hazard_wired",           # X4
    "no_owned_option",        # X5
    "jump_without_ladder",    # X6
    "jump_beside_path_file",  # X7
    "not_two_options",        # X8
    "too_many_rows",          # X9
    "jump_floor",             # X10
)

_FIELDS = ("drop", "year", "recovery", "jump")
_REQUIRED = ("drop", "year", "recovery")


class CrashPanelRefusal(ValueError):
    """A §7 refusal: its code and the one measured fact it prints."""

    def __init__(self, code: str, fact: str) -> None:
        if code not in REFUSAL_CODES:
            raise ValueError(f"unknown crash panel refusal code {code!r}")
        super().__init__(f"{code}: {fact}")
        self.code = code
        self.fact = fact


@dataclass(frozen=True)
class Recovery:
    """How much of the log drop comes back, and over how many years.

    `share` R in [0, 1] of the log drop returns in equal log steps over the
    `years` K after the drop year. `permanent` is R = 0 with no K; `full:K` is
    R = 1. `form` is the form typed: "permanent", "full" or "share".
    """

    form: str
    share: float
    years: Optional[int]

    def __post_init__(self) -> None:
        if self.form == "permanent":
            if self.share != 0.0 or self.years is not None:
                raise ValueError("a permanent recovery has share 0 and no years")
        elif self.form in ("full", "share"):
            if not 0.0 < self.share <= 1.0 or self.years is None or self.years < 1:
                raise ValueError(
                    f"a {self.form} recovery needs a share in (0, 1] and years >= 1, "
                    f"got share {self.share!r}, years {self.years!r}")
            if self.form == "full" and self.share != 1.0:
                raise ValueError("a full recovery has share 1")
        else:
            raise ValueError(f"unknown recovery form {self.form!r}")


PERMANENT = Recovery("permanent", 0.0, None)


@dataclass(frozen=True)
class CrashGrid:
    """The parsed `--crash-panel` grid. Rows are drop × year × recovery."""

    drops: Tuple[float, ...]
    years: Tuple[int, ...]
    recoveries: Tuple[Recovery, ...]
    jump: Optional[float] = None

    @property
    def row_count(self) -> int:
        return len(self.drops) * len(self.years) * len(self.recoveries)

    def rows(self) -> List[Tuple[float, int, Recovery]]:
        """(drop, year, recovery) for every row, drop outermost."""
        return [(d, c, r) for d in self.drops for c in self.years for r in self.recoveries]


def drop_path(years: int, d: float, c: int, recovery: Recovery) -> Tuple[float, ...]:
    """The multiplier m(t) on the run's own no-crash value path, t = 1..years.

    Element `t - 1` is year t. m(t) = 1 before the drop year c; from c on,

        m(t) = exp(-L × (1 - R × min(1, (t - c) / K))),   L = -ln(1 - d)

    so the drop lands whole in year c and the share R of its log comes back in
    equal log steps over the K years after it. "Back" is back to the no-crash
    path, not to the pre-crash price (spec §5). A full recovery that completes
    gives exactly 1.0.

    A drop of 0 gives a path of ones: the break-even solver prices the
    bracket's low end, which the grid itself refuses (X1).
    """
    if not 1 <= c <= years:
        raise ValueError(f"drop year {c} is outside 1..{years}")
    if not 0.0 <= d <= DROP_CEILING:
        raise ValueError(f"drop {d!r} is outside [0, {DROP_CEILING}]")
    log_drop = -math.log1p(-d)
    path: List[float] = []
    for t in range(1, years + 1):
        if t < c:
            path.append(1.0)
            continue
        back = 0.0 if recovery.years is None else recovery.share * min(1.0, (t - c) / recovery.years)
        path.append(math.exp(-log_drop * (1.0 - back)))
    return tuple(path)


def _number(field: str, token: str) -> float:
    try:
        return float(token)
    except ValueError:
        raise ValueError(f"--crash-panel {field}: {token!r} is not a number") from None


def _parse_recovery(token: str) -> Recovery:
    parts = token.split(":")
    form = parts[0]
    if form == "permanent" and len(parts) == 1:
        return PERMANENT
    if form == "full" and len(parts) == 2:
        share_text, years_text = "1", parts[1]
    elif form == "share" and len(parts) == 3:
        share_text, years_text = parts[1], parts[2]
    else:
        raise CrashPanelRefusal(
            "recovery_malformed",
            f"recovery {token!r} is not permanent, full:K or share:R:K")
    try:
        share, k = float(share_text), float(years_text)
    except ValueError:
        raise CrashPanelRefusal(
            "recovery_malformed",
            f"recovery {token!r} is not permanent, full:K or share:R:K") from None
    if not 0.0 < share <= 1.0:
        raise CrashPanelRefusal("recovery_malformed", f"share {share!r} is outside (0, 1]")
    if k < 1:
        raise CrashPanelRefusal("recovery_malformed", f"years {years_text} is below 1")
    if k != int(k):
        raise CrashPanelRefusal("recovery_malformed", f"years {years_text} is not a whole number")
    return Recovery(form, share, int(k))


def parse_grid(arg: str) -> CrashGrid:
    """'drop=...;year=...;recovery=...[;jump=...]' -> CrashGrid.

    X1, X3 and X9 refuse here; X2 needs the horizon (`check_years`). A flag
    that does not have this shape (a missing, unknown or repeated field, a
    token that is not a number) raises a plain ValueError, as `--sweep` does.
    Drops are sorted and de-duplicated; years are too, and recoveries are
    de-duplicated in the order typed (`full:K` and `share:1:K` are one), so
    the row count X9 reads is the count of distinct rows.
    """
    fields = {}
    for part in arg.split(";"):
        name, sep, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name or not value:
            raise ValueError(
                "--crash-panel expects 'drop=d1,...;year=y1,...;recovery=r1,...[;jump=j]', "
                f"got {arg!r}")
        if name not in _FIELDS:
            raise ValueError(f"--crash-panel has no field {name!r}: the fields are "
                             f"{', '.join(_FIELDS)}")
        if name in fields:
            raise ValueError(f"--crash-panel field {name!r} is given twice")
        fields[name] = value
    missing = [name for name in _REQUIRED if name not in fields]
    if missing:
        raise ValueError(f"--crash-panel needs {', '.join(missing)}: nothing defaults")

    def tokens(name: str) -> List[str]:
        items = [t.strip() for t in fields[name].split(",")]
        if any(not t for t in items):
            raise ValueError(f"--crash-panel {name}: empty entry in {fields[name]!r}")
        return items

    drops = sorted({_number("drop", t) for t in tokens("drop")})
    for d in drops:
        if not 0.0 < d <= DROP_CEILING:
            raise CrashPanelRefusal("drop_out_of_range", f"drop {d!r} is outside (0, {DROP_CEILING}]")

    year_values = [_number("year", t) for t in tokens("year")]
    for y in year_values:
        if y != int(y):
            raise ValueError(f"--crash-panel year: {y!r} is not a whole year")
    years = sorted({int(y) for y in year_values})

    # `full:K` is `share:1:K`: one recovery, kept in the spelling typed first.
    recoveries: List[Recovery] = []
    for token in tokens("recovery"):
        recovery = _parse_recovery(token)
        if all((r.share, r.years) != (recovery.share, recovery.years) for r in recoveries):
            recoveries.append(recovery)

    jump = _number("jump", fields["jump"]) if "jump" in fields else None

    grid = CrashGrid(tuple(drops), tuple(years), tuple(recoveries), jump)
    if grid.row_count > MAX_ROWS:
        raise CrashPanelRefusal("too_many_rows", f"the grid has {grid.row_count} rows")
    return grid


def check_years(grid: CrashGrid, horizon: int) -> None:
    """X2: every drop year must be inside 1..horizon; the horizon is the sale year."""
    for c in grid.years:
        if c > horizon:
            raise CrashPanelRefusal("year_out_of_range", f"year {c} is past the {horizon}-year horizon")
        if c < 1:
            raise CrashPanelRefusal("year_out_of_range", f"year {c} is before year 1")



def underwater_years(params, econ: EconomicParams, years: int,
                     path: Optional[Sequence[float]] = None) -> List[int]:
    """The years t = 1..years in which one owned option's value net of selling
    cost, `initial_value × (1 + g)^t × m(t) × (1 − selling_cost_rate)`, is
    below the balance it owes at the end of t (`deterministic.owned_balance`,
    the split the PV leg prices at the sale). `path` None: no drop."""
    if path is not None and len(path) != years:
        raise ValueError(f"drop_path has {len(path)} entries for a {years}-year run")
    growth = _effective_growth_rate(params.value_growth_rate, econ)
    under: List[int] = []
    for t in range(1, years + 1):
        m = 1.0 if path is None else path[t - 1]
        net = params.initial_value * (1 + growth) ** t * m * (1 - params.selling_cost_rate)
        if net < owned_balance(params, t):
            under.append(t)
    return under


# ---------------------------------------------------------------------------
# The runner: one row per (drop, year, recovery), each with its central line
# and the conditional futures beside it (spec R1, §3.2, §3.3).
# ---------------------------------------------------------------------------

# The axis `solve_crossings` searches, and the bracket: the whole range X1
# accepts, so no wider bracket exists (spec §1.3).
BREAK_EVEN_KEY = "crash.drop"
BREAK_EVEN_BRACKET = (0.0, DROP_CEILING)
# Where no crossing exists, the drops at which the no-crossing line reads the
# margin rule, besides the grid's own drops (every row's drop is one of them,
# so the line cannot contradict a row's state).
TIE_SCAN_POINTS = 34

_OPTION_ORDER = ("condo", "house", "rent")
_OWNED = ("condo", "house")


def recovery_to_dict(recovery: Recovery) -> Dict[str, Any]:
    """A recovery as the JSON carries it: `full:K` is `share:1:K` (spec
    §3.1), so both serialise as the share form; `permanent` keeps its name,
    with share 0 and no years."""
    if recovery.years is None:
        return {"form": "permanent", "share": 0.0, "years": None}
    return {"form": "share", "share": recovery.share, "years": recovery.years}


def _priced(spec: ComparisonSpec) -> List[str]:
    return [name for name in _OPTION_ORDER if getattr(spec, name) is not None]


def _renewal_count(params) -> int:
    """The loader's count of renewals over the amortization:
    ⌈mortgage_term_years / mortgage_renewal_years⌉ − 1."""
    return -(-params.mortgage_term_years // params.mortgage_renewal_years) - 1


def jumped_params(params, jump: float):
    """Spec §6's four steps on one financed option's ladder: write the quoted
    ladder out in full (one entry per renewal, the last carried forward), add
    `jump` to the FIRST entry only, convert each entry once as the loader
    does, and give back a copy with both ladders replaced. None when the
    option states no ladder, so there is nothing to jump."""
    if renewal_segments_for(params) is None or not params.mortgage_renewal_rates_quoted:
        return None
    count = _renewal_count(params)
    if count < 1:
        return None
    quoted = list(params.mortgage_renewal_rates_quoted)
    full = [quoted[min(i, len(quoted) - 1)] for i in range(count)]
    full[0] += jump
    return dataclasses.replace(
        params,
        mortgage_renewal_rates=[effective_mortgage_rate(q, params.mortgage_rate_compounding)
                                for q in full],
        mortgage_renewal_rates_quoted=full,
    )


def apply_jump(spec: ComparisonSpec, jump: Optional[float]) -> Tuple[ComparisonSpec, List[str]]:
    """The spec every row of a jumped panel prices, and the options the jump
    reached: those whose first renewal the horizon prices. One market, so
    one jump for every laddered option."""
    if jump is None:
        return spec, []
    replaced: Dict[str, Any] = {}
    reached: List[str] = []
    for name in _OWNED:
        params = getattr(spec, name)
        if params is None:
            continue
        jumped = jumped_params(params, jump)
        if jumped is None:
            continue
        replaced[name] = jumped
        if renewals_priced_inside(jumped, spec.simulation.years) >= 1:
            reached.append(name)
    return dataclasses.replace(spec, **replaced), reached


def check_jump_floor(spec: ComparisonSpec, jump: float) -> None:
    """X10: the jump may not take any laddered option's first renewal below 0,
    the floor the loader holds every quoted renewal rate to. Checked on the
    quoted rate before any ladder is built, reached by the horizon or not."""
    for name in _OWNED:
        params = getattr(spec, name)
        if params is None or renewal_segments_for(params) is None:
            continue
        quoted = params.mortgage_renewal_rates_quoted
        if not quoted or _renewal_count(params) < 1:
            continue
        first = quoted[0] + jump
        if first < 0:
            raise CrashPanelRefusal(
                "jump_floor",
                (f"jump {jump:g} takes the first renewal to {first * 100:.2f}%, "
                 f"below 0").replace("-", MINUS))


def check_panel(spec: ComparisonSpec, grid: CrashGrid) -> None:
    """The refusals the config decides (§7): X2 against the horizon, then
    X5, X4, X7, X10 and X6. Each raises `CrashPanelRefusal`; X8 refuses only
    the break-even lines, `level` and `sd`, and is taken per block."""
    years = spec.simulation.years
    check_years(grid, years)
    owned = [name for name in _OWNED if getattr(spec, name) is not None]
    if not owned:
        raise CrashPanelRefusal("no_owned_option", "no owned option is priced")
    for name in owned:
        shock = getattr(spec, name).price_shock
        if shock is not None and shock.annual_hazard > 0:
            raise CrashPanelRefusal(
                "hazard_wired", f"{name}.price_shock.annual_hazard is {shock.annual_hazard!r}")
    if grid.jump is None:
        return
    if spec.renewal_rate_paths is not None:
        raise CrashPanelRefusal("jump_beside_path_file", "renewal_rates.path is set")
    check_jump_floor(spec, grid.jump)
    _, reached = apply_jump(spec, grid.jump)
    if not reached:
        raise CrashPanelRefusal(
            "jump_without_ladder", f"no financed option prices a renewal inside {years} years")


def _options_fact(count: int) -> str:
    return f"{count} option is priced" if count == 1 else f"{count} options are priced"


def _central(det, spec: ComparisonSpec, options: Sequence[str]) -> Dict[str, Any]:
    """The central line and the margin rule `--break-even` applies."""
    verdict = compute_verdict(det, None, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    return {
        "totals": {name: getattr(det, name).total_pv for name in options},
        "best": verdict.best, "runner_up": verdict.runner_up,
        "margin_pv": verdict.margin_pv, "margin_frac": verdict.margin_frac,
        "state": verdict.state, "rule": verdict.rule,
    }


def _futures(det, spec: ComparisonSpec, options: Sequence[str],
             path: Optional[Sequence[float]]) -> Dict[str, Any]:
    """The config's own Monte Carlo with the stated drop on every path, the
    same random numbers as the plain run, and the verdict's own rule."""
    mc = run_monte_carlo(spec, drop_path=path)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    gap_sd = None
    if len(options) == 2:
        a, b = options
        gap_sd = float(np.std(getattr(mc, b).pvs - getattr(mc, a).pvs))
    return {
        "best": verdict.best, "prob_best": verdict.prob_best,
        "mc_best": verdict.mc_best, "mc_prob_best": verdict.mc_prob_best,
        "state": verdict.state, "rule": verdict.rule, "gap_sd": gap_sd,
    }


def _row(spec: ComparisonSpec, options: Sequence[str], drop: Optional[float],
         year: Optional[int], recovery: Optional[Recovery], *, futures: bool) -> Dict[str, Any]:
    years = spec.simulation.years
    path = None if drop is None else drop_path(years, drop, year, recovery)
    det = compute_deterministic(spec, drop_path=path)
    return {
        "drop": drop, "year": year,
        "recovery": None if recovery is None else recovery_to_dict(recovery),
        "sale_multiple": 1.0 if path is None else path[-1],
        "central": _central(det, spec, options),
        "level_pv": None,
        "futures": _futures(det, spec, options, path) if futures else None,
        "underwater_years": {
            name: underwater_years(getattr(spec, name), spec.economic, years, path)
            for name in _OWNED if getattr(spec, name) is not None
        },
        "affordability": affordability_of(det),
    }


def _gap(row: Dict[str, Any], options: Sequence[str]) -> float:
    a, b = options
    totals = row["central"]["totals"]
    return totals[b] - totals[a]


def _decisive(totals: Tuple[float, float]) -> bool:
    """The margin rule `compute_verdict` applies to a central line: the
    margin is at least the tie band of the cheaper option's total."""
    best, runner = sorted(totals)
    denom = abs(best) if best != 0 else abs(runner)
    frac = (runner - best) / denom if denom > 0 else 0.0
    return frac >= ANCHORS["verdict.tie_band"].value


def tie_bands(totals_at, lo: float, hi: float, drops: Sequence[float] = (),
              points: int = TIE_SCAN_POINTS, iterations: int = 60) -> List[List[Optional[float]]]:
    """Where no crossing exists: the stretches of [lo, hi] on which the
    central line is too close to call, each `[start, end]`, with None for an
    end at the bracket's own end. The margin rule is read at `points` evenly
    spaced drops and at every drop in `drops`, and each change of state is
    bisected. `[]` is decisive throughout; `[[None, None]]` too close to call
    throughout."""
    grid = sorted({lo + (hi - lo) * i / (points - 1) for i in range(points - 1)} | {hi}
                  | {d for d in drops if lo <= d <= hi})
    states = [_decisive(totals_at(d)) for d in grid]

    def edge(x0: float, x1: float, s0: bool) -> float:
        for _ in range(iterations):
            mid = 0.5 * (x0 + x1)
            if not x0 < mid < x1:
                break
            if _decisive(totals_at(mid)) == s0:
                x0 = mid
            else:
                x1 = mid
        return x1

    bands: List[List[Optional[float]]] = []
    start: Optional[float] = None
    in_tie = not states[0]
    for i in range(1, len(grid)):
        if states[i] == states[i - 1]:
            continue
        at = edge(grid[i - 1], grid[i], states[i - 1])
        if in_tie:
            bands.append([start, at])
        else:
            start = at
        in_tie = not in_tie
    if in_tie:
        bands.append([start, None])
    return bands


def _break_even(spec: ComparisonSpec, options: Sequence[str], year: int,
                recovery: Recovery, drops: Sequence[float] = ()) -> Dict[str, Any]:
    """The drop at which the central case's cheapest option changes, solved
    by `solve_crossings` over the whole accepted range. Only its figures are
    kept (`value`, `cheaper_below`, `cheaper_above`, `tie_band`); its
    `sentence` is `threshold_sentences`' wording, which this axis does not
    use (spec §1.3)."""
    head = {"year": year, "recovery": recovery_to_dict(recovery)}
    if len(options) != 2:
        return {**head, "refused": {"code": "not_two_options",
                                    "fact": _options_fact(len(options))}}
    years = spec.simulation.years

    memo: Dict[float, Tuple[float, float]] = {}

    def totals_at(d: float) -> Tuple[float, float]:
        if d not in memo:
            det = compute_deterministic(spec, drop_path=drop_path(years, d, year, recovery))
            memo[d] = (getattr(det, options[0]).total_pv, getattr(det, options[1]).total_pv)
        return memo[d]

    lo, hi = BREAK_EVEN_BRACKET
    out = solve_crossings(BREAK_EVEN_KEY, (options[0], options[1]), lo, hi, totals_at,
                          to_adjacent_floats=True)
    crossings = [{"value": be["value"], "cheaper_below": be["cheaper_below"],
                  "cheaper_above": be["cheaper_above"], "tie_band": list(be["tie_band"])}
                 for be in out["break_evens"]]
    no_crossing = None
    if not crossings:
        no_crossing = {"cheaper": out["cheaper_throughout"], "lo": lo, "hi": hi,
                       "tie_bands": tie_bands(totals_at, lo, hi, drops)}
    return {**head, "key": BREAK_EVEN_KEY, "options": list(options), "bracket": [lo, hi],
            "break_evens": crossings, "no_crossing": no_crossing}


def grid_to_dict(grid: CrashGrid, reached: Sequence[str]) -> Dict[str, Any]:
    return {
        "drop": list(grid.drops), "year": list(grid.years),
        "recovery": [recovery_to_dict(r) for r in grid.recoveries],
        "jump": None if grid.jump is None else {"value": grid.jump, "options": list(reached)},
    }


def refused_panel(refusal: CrashPanelRefusal, grid: Optional[CrashGrid] = None,
                  reached: Sequence[str] = ()) -> Dict[str, Any]:
    """A panel refused whole: the refusal in place of the rows (§7)."""
    return {"grid": None if grid is None else grid_to_dict(grid, reached),
            "source": "command line", "no_drop": None, "rows": [], "break_evens": [],
            "refused": {"code": refusal.code, "fact": refusal.fact}}


def run_crash_panel(spec: ComparisonSpec, grid: CrashGrid, *,
                    monte_carlo: bool = True) -> Dict[str, Any]:
    """The panel (§3.3's `crash_panel` object). A whole-panel refusal comes
    back as `refused` with no rows; it is never raised.

    Every row prices the jumped spec when the grid carries a jump, the
    `none` row included, so `level` is the drop's move with the jump in
    place. The futures run only when the run itself has futures: not under
    `--no-monte-carlo` (`monte_carlo=False`) and not on a single-path run.
    """
    try:
        check_panel(spec, grid)
    except CrashPanelRefusal as refusal:
        return refused_panel(refusal, grid)
    row_spec, reached = apply_jump(spec, grid.jump)
    options = _priced(row_spec)
    futures = monte_carlo and not single_path_run(spec)

    no_drop = _row(row_spec, options, None, None, None, futures=futures)
    if len(options) == 2:
        no_drop["level_pv"] = 0.0
    rows: List[Dict[str, Any]] = []
    break_evens: List[Dict[str, Any]] = []
    for year in grid.years:
        for recovery in grid.recoveries:
            for drop in grid.drops:
                row = _row(row_spec, options, drop, year, recovery, futures=futures)
                if len(options) == 2:
                    row["level_pv"] = _gap(row, options) - _gap(no_drop, options)
                rows.append(row)
            break_evens.append(_break_even(row_spec, options, year, recovery, grid.drops))
    return {"grid": grid_to_dict(grid, reached), "source": "command line",
            "no_drop": no_drop, "rows": rows, "break_evens": break_evens, "refused": None}


# ---------------------------------------------------------------------------
# The text block and the read-back line (spec §3.2, §3.4): figures, not prose.
# ---------------------------------------------------------------------------

HEADER = ("crash panel — stated drops, each conditional on happening "
          "[drop, year, recovery: command line]")
TAG = "[solved, central case]"
MINUS = "−"


def _pct(value: float) -> str:
    """A grid figure as a percentage, as typed: 0.1 → 10%, 0.125 → 12.5%."""
    return f"{value * 100:g}%"


def _edge(value: float) -> str:
    """A solved drop: a break-even crossing or a tie-band edge."""
    return f"{value * 100:.2f}%"


def recovery_words(recovery: Dict[str, Any]) -> str:
    """`permanent`, `full over K years` or `share R over K years`."""
    if recovery["years"] is None:
        return "permanent"
    span = f"{recovery['years']} year{'s' if recovery['years'] != 1 else ''}"
    if recovery["share"] == 1.0:
        return f"full over {span}"
    return f"share {recovery['share']:g} over {span}"


def jump_words(jump: Dict[str, Any]) -> str:
    """`jump +2.37 pp at the first renewal: condo`."""
    return (f"jump {jump['value'] * 100:+g} pp at the first renewal: "
            f"{', '.join(jump['options'])}").replace("-", MINUS)


def read_back_line(grid: Dict[str, Any]) -> str:
    """The one read-back line (§3.4): the grid as stated, and what it is not."""
    parts = [
        "drops " + ", ".join(_pct(d) for d in grid["drop"]),
        "years " + ", ".join(str(y) for y in grid["year"]),
        "recovery " + ", ".join(recovery_words(r) for r in grid["recovery"]),
    ]
    if grid["jump"] is not None:
        parts.append(jump_words(grid["jump"]))
    return ("crash panel: " + "; ".join(parts)
            + "; stated on the command line, not a forecast and not a probability")


def _money(value: float) -> str:
    return f"{round(value):,}".replace("-", MINUS)


def _signed(value: int) -> str:
    """A printed gap or level: `+6,526`, `−25,284`, `0`."""
    if value == 0:
        return "0"
    return (f"+{value:,}" if value > 0 else f"{MINUS}{-value:,}")


def _years(years: Sequence[int]) -> str:
    """[1, 2, 3, 5] → `1–3, 5`."""
    runs: List[List[int]] = []
    for y in years:
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    return ", ".join(f"{r[0]}–{r[-1]}" if len(r) > 1 else f"{r[0]}" for r in runs)


def _underwater(row: Dict[str, Any]) -> str:
    named = [f"{name} {_years(years)}" for name, years in row["underwater_years"].items() if years]
    return " · ".join(named) if named else "none"


def _affordability(row: Dict[str, Any]) -> str:
    aff = row["affordability"] or {}
    return "; ".join(f"{name} max {aff[name]['max_ratio']:.1%} {_breaches(aff[name])}"
                     for name in _OPTION_ORDER if name in aff)


def _printed_gap(row: Dict[str, Any], options: Sequence[str]) -> int:
    """`B − A` as the difference of the two PRINTED totals (which-risk §0.1
    item 2), so the gap a reader recomputes is the gap printed."""
    totals = row["central"]["totals"]
    a, b = options
    return round(totals[b]) - round(totals[a])


def _futures_cells(futures: Dict[str, Any]) -> Tuple[str, ...]:
    if futures["state"] == "disagreement":
        return (f"{futures['best']} {futures['prob_best']:.4f} disagreement · "
                f"{futures['mc_best']} {futures['mc_prob_best']:.4f} of the futures",)
    return (futures["best"], f"{futures['prob_best']:.4f}", futures["state"])


def _no_crossing_text(record: Dict[str, Any]) -> str:
    """The stretches of a no-crossing axis, in order, each read by the margin
    rule as the rows are: `A is cheaper throughout`, `too close to call
    throughout`, or clauses of `A is cheaper below lo`, `too close to call
    from lo to hi`, `A is cheaper from lo to hi` and `A is cheaper above hi`."""
    cheaper, bands = record["cheaper"], record["tie_bands"]
    if not bands:
        return f"{cheaper} is cheaper throughout"
    if bands == [[None, None]]:
        return "too close to call throughout"
    clauses: List[str] = []
    after: Optional[float] = None  # where the last tie stretch ended
    for k, (start, end) in enumerate(bands):
        if start is not None:
            clauses.append(f"{cheaper} is cheaper below {_edge(start)}" if k == 0
                           else f"{cheaper} is cheaper from {_edge(after)} to {_edge(start)}")
        lo_text = "no drop" if start is None else _edge(start)
        hi_text = "a 99% drop" if end is None else _edge(end)
        clauses.append(f"too close to call from {lo_text} to {hi_text}")
        after = end
    if after is not None:
        clauses.append(f"{cheaper} is cheaper above {_edge(after)}")
    return "; ".join(clauses)


def _break_even_line(entry: Dict[str, Any]) -> List[str]:
    """One line per crossing, from §3.2's fixed templates and no others."""
    if "refused" in entry:
        refused = entry["refused"]
        return [f"break-even: refused ({refused['code']}): {refused['fact']}"]
    crossings = entry["break_evens"]
    if not crossings:
        record = entry["no_crossing"]
        return [f"break-even: no crossing from no drop to a 99% drop: "
                f"{_no_crossing_text(record)} {TAG}"]
    lines = []
    last = len(crossings) - 1
    for k, be in enumerate(crossings):
        left, right = be["tie_band"]
        below, above = be["cheaper_below"], be["cheaper_above"]
        at_low = left is None and k == 0
        at_high = right is None and k == last
        lo = "the next crossing" if left is None else _edge(left)
        hi = "the next crossing" if right is None else _edge(right)
        crossing = f"(crossing {_edge(be['value'])})"
        if at_low and at_high:
            text = f"too close to call from no drop to a 99% drop {crossing}"
        elif at_low:
            text = f"too close to call from no drop to {hi}; {above} is cheaper above {hi} {crossing}"
        elif at_high:
            text = f"{below} is cheaper below {lo}; too close to call from {lo} to a 99% drop {crossing}"
        else:
            text = (f"{below} is cheaper below {lo}; too close to call from {lo} to {hi}; "
                    f"{above} is cheaper above {hi} {crossing}")
        lines.append(f"break-even: {text} {TAG}")
    return lines


def format_crash_panel(panel: Dict[str, Any], *, paths: Optional[int] = None) -> str:
    """The `--crash-panel` text block. `paths` is the run's path count, printed
    over the futures columns; the futures columns are absent when no row
    carries futures."""
    if panel["refused"] is not None:
        refused = panel["refused"]
        return f"crash panel — refused ({refused['code']}): {refused['fact']}"
    none = panel["no_drop"]
    options = list(none["central"]["totals"])
    two = len(options) == 2
    with_futures = none["futures"] is not None
    with_aff = none["affordability"] is not None

    head_central = ["drop", "sale value", *options]
    if two:
        head_central += [f"{options[1]} {MINUS} {options[0]}", "level"]
    elif len(options) > 2:
        head_central += ["gap"]
    head_central += ["best", "state"]
    head_futures = (["best", "P(best)", "state"] + (["sd"] if two else [])) if with_futures else []
    head_tail = ["underwater"] + (["affordability"] if with_aff else [])

    none_gap = _printed_gap(none, options) if two else None

    def cells(row: Dict[str, Any]) -> List[Any]:
        central = row["central"]
        drop = "none" if row["drop"] is None else _pct(row["drop"])
        sale = "×1" if row["drop"] is None else f"×{row['sale_multiple']:.3f}"
        out: List[Any] = [drop, sale, *(_money(central["totals"][o]) for o in options)]
        if two:
            gap = _printed_gap(row, options)
            out += [_signed(gap), _signed(gap - none_gap)]
        elif len(options) > 2:
            margin = round(central["totals"][central["runner_up"]]) - round(central["totals"][central["best"]])
            out += [f"{central['runner_up']} {MINUS} {central['best']} {_signed(margin)}"]
        out += [central["best"], central["state"]]
        if with_futures:
            futures = row["futures"]
            verdict_cells = _futures_cells(futures)
            out.append(verdict_cells)  # one span: three cells, or the disagreement cell
            if two:
                out.append(_money(futures["gap_sd"]))
        out.append(_underwater(row))
        if with_aff:
            out.append(_affordability(row))
        return out

    body = [("row", cells(none))]
    by_group: Dict[Tuple[int, Any], List[Dict[str, Any]]] = {}
    for row in panel["rows"]:
        by_group.setdefault((row["year"], tuple(sorted(row["recovery"].items()))), []).append(row)
    for entry in panel["break_evens"]:
        key = (entry["year"], tuple(sorted(entry["recovery"].items())))
        body.append(("group", f"year {entry['year']} · {recovery_words(entry['recovery'])}"))
        for row in by_group[key]:
            body.append(("row", cells(row)))
        for line in _break_even_line(entry):
            body.append(("text", f"  {line}"))

    # The futures verdict is one span of three sub-cells, aligned within it.
    span_widths = [len(h) for h in head_futures[:3]]
    for kind, item in body:
        if kind == "row" and with_futures:
            span = next(c for c in item if isinstance(c, tuple))
            if len(span) == 3:
                span_widths = [max(w, len(s)) for w, s in zip(span_widths, span)]

    def span_text(span: Sequence[str]) -> str:
        if len(span) == 1:
            return span[0]
        return "  ".join(s.ljust(w) for s, w in zip(span, span_widths)).rstrip()

    header = list(head_central)
    if with_futures:
        header.append(span_text(head_futures[:3]))
        header += head_futures[3:]
    header += head_tail
    rendered_rows = [[span_text(c) if isinstance(c, tuple) else c for c in item]
                     for kind, item in body if kind == "row"]
    widths = [max(len(header[i]), *(len(r[i]) for r in rendered_rows)) for i in range(len(header))]

    def line(cols: Sequence[str]) -> str:
        return ("  " + "  ".join(c.ljust(w) for c, w in zip(cols, widths))).rstrip()

    lines = [HEADER]
    if panel["grid"]["jump"] is not None:
        lines.append(jump_words(panel["grid"]["jump"]))
    # The two column groups, each label over its first column.
    starts, pos = [], 2
    for w in widths:
        starts.append(pos)
        pos += w + 2
    over = " " * starts[0] + "central line"
    if with_futures:
        label = f"futures ({paths:,})" if paths is not None else "futures"
        over = over.ljust(starts[len(head_central)]) + label
    lines.append(over)
    lines.append(line(header))
    rows_iter = iter(rendered_rows)
    for kind, item in body:
        lines.append(line(next(rows_iter)) if kind == "row" else item)
    return "\n".join(lines)
