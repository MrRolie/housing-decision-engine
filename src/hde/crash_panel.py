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

from .break_even import solve_crossings
from .config import single_path_run
from .deterministic import (_effective_growth_rate, compute_deterministic, owned_balance,
                            renewal_segments_for, renewals_priced_inside)
from .models import ComparisonSpec, EconomicParams, compute_verdict
from .monte_carlo import run_monte_carlo
from .rates import effective_mortgage_rate
from .sweep import affordability_of

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
BREAK_EVEN_KEY = "crash.drawdown"
BREAK_EVEN_BRACKET = (0.0, DROP_CEILING)

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


def check_panel(spec: ComparisonSpec, grid: CrashGrid) -> None:
    """The refusals the config decides (§7): X2 against the horizon, then
    X5, X4, X7 and X6. Each raises `CrashPanelRefusal`; X8 refuses only the
    break-even lines, `level` and `sd`, and is taken per block."""
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


def _break_even(spec: ComparisonSpec, options: Sequence[str], year: int,
                recovery: Recovery) -> Dict[str, Any]:
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

    def totals_at(d: float) -> Tuple[float, float]:
        det = compute_deterministic(spec, drop_path=drop_path(years, d, year, recovery))
        return getattr(det, options[0]).total_pv, getattr(det, options[1]).total_pv

    lo, hi = BREAK_EVEN_BRACKET
    out = solve_crossings(BREAK_EVEN_KEY, (options[0], options[1]), lo, hi, totals_at,
                          to_adjacent_floats=True)
    crossings = [{"value": be["value"], "cheaper_below": be["cheaper_below"],
                  "cheaper_above": be["cheaper_above"], "tie_band": list(be["tie_band"])}
                 for be in out["break_evens"]]
    no_crossing = None
    if not crossings:
        no_crossing = {"cheaper": out["cheaper_throughout"], "lo": lo, "hi": hi}
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
            break_evens.append(_break_even(row_spec, options, year, recovery))
    return {"grid": grid_to_dict(grid, reached), "source": "command line",
            "no_drop": no_drop, "rows": rows, "break_evens": break_evens, "refused": None}
