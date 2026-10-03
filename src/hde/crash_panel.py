"""Crash stress panel: stated one-time drops in the home's value, each priced
as a conditional row.

Contract: docs/specs/2026-10-03-crash-stress-panel.md — §3.1 the flag, §4 the
multiplier, §7 the refusals. A row says "if the value drops by `d` in year `c`
and comes back in the stated way"; nothing here says how likely a drop is.

`drop_path` is the ONE home of the multiplier m(t). The central line and the
Monte Carlo read its tuple; neither re-derives it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .deterministic import _effective_growth_rate, owned_balance
from .models import EconomicParams

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
