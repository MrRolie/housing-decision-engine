"""Shared loader validation contracts (spec §4). Fail-loud, never impute."""
import math

import pandas as pd

from demoflow.errors import LoaderError


def assert_finite(name: str, value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise LoaderError(f"{name}: non-numeric value {value!r}") from exc
    if not math.isfinite(f):
        raise LoaderError(f"{name}: non-finite value {value!r}")
    return f


def assert_fraction(name: str, value) -> float:
    f = assert_finite(name, value)
    if not 0.0 <= f <= 1.0:
        raise LoaderError(f"{name}: fraction outside [0,1]: {f}")
    return f


def assert_nonneg_finite(name: str, value) -> float:
    """Nonnegative-finite (codex r7-F8 ratio carve-out): the immigrant/non-immigrant
    ownership RATIO is NOT a fraction — it can validly exceed 1 (immigrants CAN out-own
    non-immigrants in a cell); only the PRODUCT p_imm binds [0,1]. Also used for stocks."""
    f = assert_finite(name, value)
    if f < 0.0:
        raise LoaderError(f"{name}: negative value {f}")
    return f


# Signed-flow carve-out (codex r9-F2): natural increase / net-migration components are
# legitimately signed — validate them with assert_finite ONLY (never nonneg/fraction); the
# natural-increase tripwire's job is to EVALUATE a negative value, not raise on it.


def _as_year(value, ctx: str) -> int:
    """Coerce one year cell to int under THIS module's error taxonomy. A bare `int(y)` leaks
    ValueError/TypeError — a class no `except LoaderError` catches — on exactly the malformation
    the year gates exist to catch (a blank `Année` cell arrives as NaN); spec §4 rules these
    causes data/environment state → explicit named error."""
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise LoaderError(f"{ctx}: non-numeric year {value!r}") from exc
    if not math.isfinite(f):
        raise LoaderError(f"{ctx}: non-finite year {value!r}")
    if f != int(f):
        raise LoaderError(f"{ctx}: non-integer year {value!r}")
    return int(f)


def assert_unique_primary_key(df: pd.DataFrame, keys: list[str], ctx: str) -> None:
    dups = df.duplicated(subset=keys, keep=False)
    if dups.any():
        raise LoaderError(f"{ctx}: duplicate primary key {keys} on {int(dups.sum())} rows")


def assert_year_lattice(years, ctx: str, expected_span: tuple[int, int] | None = None) -> None:
    ys = sorted({_as_year(y, ctx) for y in years})
    if not ys:
        raise LoaderError(f"{ctx}: empty year index")
    if ys != list(range(ys[0], ys[-1] + 1)):
        raise LoaderError(f"{ctx}: year lattice not contiguous (consecutive diffs must be 1): {ys}")
    if expected_span is not None and (ys[0], ys[-1]) != expected_span:
        raise LoaderError(f"{ctx}: year span {(ys[0], ys[-1])} != expected endpoints {expected_span}")


def assert_uniform_year_domain(df: pd.DataFrame, group_keys: list[str], year_col: str, ctx: str) -> None:
    """Every geography×scenario×sex series must carry the IDENTICAL year set (codex r6-F3);
    a missing terminal year for one series raises (never a silently shortened mean)."""
    # dropna=False is LOAD-BEARING: pandas' default excises null-keyed rows before the gate sees
    # them, so the property above fails OPEN for that class — frame non-empty, gate runs, returns
    # clean. Reachable: pop-as-rmr-base.xlsx "Années d'âge" header=6 → 2 of 2513 rows carry NaN in
    # every label column. Same flag on the assert_statut_sublattice loop below.
    domains = df.groupby(group_keys, dropna=False)[year_col].apply(
        lambda s: frozenset(_as_year(y, ctx) for y in s))
    uniq = set(domains)
    if len(uniq) > 1:
        ref = max(uniq, key=len)
        deficient = [k for k, d in domains.items() if d != ref]
        raise LoaderError(f"{ctx}: non-uniform year domain across series (missing terminal year?); "
                          f"deficient groups: {deficient[:5]}")


def assert_statut_sublattice(df: pd.DataFrame, group_keys: list[str], year_col: str,
                             status_col: str, allowed: set[str], ctx: str) -> None:
    """Statut SUB-lattice (codex r10): status values in the metadata's allowed set; exactly ONE
    est→proj transition per series (monotone, no proj→est reversal); and an IDENTICAL PROJECTED-year
    domain across every series — so a proj→est relabel of one geography's terminal year raises even
    though the RAW year lattice is intact (it would silently shorten that geography's ranking mean)."""
    bad = set(df[status_col].astype(str)) - set(allowed)
    if bad:
        raise LoaderError(f"{ctx}: Statut values outside allowed set {sorted(allowed)}: {sorted(bad)}")
    proj_domains = set()
    for key, grp in df.groupby(group_keys, dropna=False):  # dropna=False load-bearing (see above)
        g = grp.sort_values(year_col)
        # The projected marker is a "proj" PREFIX, measured against pop-as-rmr-base.xlsx and
        # pop-as-ra-base.xlsx (the qc + compo workbooks were NOT read):
        # Statut ∈ {'r' réel, 'p' provisoire, 'proj'} — only 'proj' is projected, and the observed
        # per-series order r…r,p,proj…proj is monotone with exactly one switch.
        is_proj = [str(s).lower().startswith("proj") for s in g[status_col]]
        if any(is_proj[i] < is_proj[i - 1] for i in range(1, len(is_proj))):
            raise LoaderError(f"{ctx}: series {key} has a proj→est reversal (relabel?) — not a sub-lattice")
        switches = sum(1 for i in range(1, len(is_proj)) if is_proj[i] and not is_proj[i - 1])
        if switches != 1:
            raise LoaderError(f"{ctx}: series {key} has {switches} est→proj transitions (expected exactly 1)")
        proj_domains.add(frozenset(_as_year(y, ctx) for y, p in zip(g[year_col], is_proj) if p))
    if len(proj_domains) > 1:
        raise LoaderError(f"{ctx}: non-uniform PROJECTED-year domain across series (a proj→est relabel "
                          f"shortens one geography's ranking mean)")
