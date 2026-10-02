"""Renewal-rate path file: load a fitted model's sampled renewal-rate paths
and price them against a config.

Contract: docs/specs/2026-10-01-renewal-rate-path-file.md — §2 the file, §3 the
config surface and the refusals R1 to R20, §5 the central row. The engine holds
no rate model and ships no file: the paths are the user's, written by a model
fitted outside the engine, and this module only validates them and says which
row the deterministic case prices.

Import-light on purpose (`rates` only): `config` and `models` import this
module, so nothing here may import either. A refusal raises `RatePathsError`,
which the loader re-raises as its `ConfigValidationError`; `RatePathsChanged`
is deliberately neither, so no per-point capture can fold it into one row.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .rates import MORTGAGE_COMPOUNDING, effective_mortgage_rate

SCHEMA = "hde.renewal_rate_paths"
SCHEMA_VERSION = "1"

# Exact allowlists, per object. `as_of` and `validation.metrics` are the two
# optional fields; every other field is required.
_TOP_REQUIRED = ("schema", "schema_version", "term_years", "renewal_years",
                 "compounding", "provenance", "paths")
_TOP_OPTIONAL = ("as_of",)
_PROVENANCE_TEXT = ("method", "data_window", "source", "producer")
_PROVENANCE_REQUIRED = _PROVENANCE_TEXT + ("validation",)
_VALIDATION_REQUIRED = ("text",)
_VALIDATION_OPTIONAL = ("metrics",)


class RatePathsError(Exception):
    """A path file, or a config read against one, that the engine refuses."""


class RatePathsChanged(Exception):
    """The bytes of a path file changed within one process (R19).

    Subclasses neither `ConfigValidationError` nor `ValueError`: every sweep
    point, break-even probe and reversal probe re-enters the loader and
    catches those two, and a changed file is not one point's problem — it
    makes every figure already priced a figure of other bytes.
    """


# R19: the first sha256 seen per resolved path, for the life of the process.
_FIRST_SHA: Dict[str, str] = {}
# The file-level parse, cached by sha256. Only what the bytes alone decide is
# cached here: the priced columns and the central row depend on the config's
# horizon and options, and are computed on every load.
_PARSED: Dict[str, "RatePathFile"] = {}


def reset_pins() -> None:
    """Forget every pinned sha256 and every cached parse (tests)."""
    _FIRST_SHA.clear()
    _PARSED.clear()


@dataclass(frozen=True)
class RatePathFile:
    """A validated path file, independent of any config."""
    sha256: str
    schema_version: str
    term_years: int
    renewal_years: Tuple[int, ...]
    compounding: str
    as_of: Optional[str]
    provenance: Dict[str, Any]
    quoted: Tuple[Tuple[float, ...], ...]


@dataclass(frozen=True)
class LoadedRatePaths:
    """A path file priced against one config (§3).

    `quoted` and `effective` hold every row, as the file quotes it and as the
    payment uses it (converted once by the file's own `compounding`).
    `columns` is each reading option's n_o, the number of columns it reads;
    `priced_columns` is P, the most renewals any reading option prices inside
    the horizon, and `priced_years` their years. `central_index` is the row the
    deterministic case prices (§5) and `tied_rows` the number of OTHER rows at
    the same exact distance from the per-renewal median.
    """
    path: str
    file_sha256: str
    schema_version: str
    term_years: int
    renewal_years: Tuple[int, ...]
    compounding: str
    as_of: Optional[str]
    provenance: Dict[str, Any]
    quoted: Tuple[Tuple[float, ...], ...]
    effective: Tuple[Tuple[float, ...], ...]
    columns: Dict[str, int]
    priced_columns: int
    priced_years: Tuple[int, ...]
    central_index: int
    tied_rows: int

    @property
    def rows(self) -> int:
        return len(self.quoted)

    def central_quoted(self, n: int) -> List[float]:
        """The central row's first n quoted rates."""
        return list(self.quoted[self.central_index][:n])

    def central_effective(self, n: int) -> List[float]:
        """The central row's first n effective rates."""
        return list(self.effective[self.central_index][:n])


# ---------------------------------------------------------------------------
# The file (§2): R1 to R10, and R19
# ---------------------------------------------------------------------------

class _NonFinite(ValueError):
    pass


def _reject_constant(token: str):
    raise _NonFinite(f"non-finite literal {token!r} (NaN and Infinity are refused)")


def _is_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _fields(obj: Any, where: str, required: Sequence[str], optional: Sequence[str],
            errors: List[str], tag: str) -> bool:
    """R3 for one object; True when it is an object at all."""
    prefix = f"{where}." if where else ""
    if not isinstance(obj, dict):
        errors.append(f"'{tag}': missing field(s) {[prefix + k for k in required]}")
        return False
    unknown = sorted(prefix + str(k) for k in obj if k not in required and k not in optional)
    missing = [prefix + k for k in required if k not in obj]
    if unknown:
        errors.append(f"'{tag}': unknown field(s) {unknown} (exact allowlist)")
    if missing:
        errors.append(f"'{tag}': missing field(s) {missing}")
    return True


def _parse(raw: bytes, path: str, sha: str) -> RatePathFile:
    """Validate the bytes; every violation is collected, then refused once."""
    try:
        data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:                      # R2
        raise RatePathsError(f"'{path}' is not valid JSON: {exc}") from exc

    errors: List[str] = []
    if not _fields(data, "", _TOP_REQUIRED, _TOP_OPTIONAL, errors, path):  # R3
        raise RatePathsError("\n".join(errors))

    schema, version = data.get("schema"), data.get("schema_version")
    if ("schema" in data and "schema_version" in data
            and (schema != SCHEMA or version != SCHEMA_VERSION)):         # R4
        errors.append(f"'{path}' is {schema} version {version}; this engine reads "
                      f"{SCHEMA} version {SCHEMA_VERSION}")

    provenance = data.get("provenance")
    if "provenance" in data and _fields(provenance, "provenance", _PROVENANCE_REQUIRED,
                                        (), errors, path):
        for name in _PROVENANCE_TEXT:                                      # R5
            value = provenance.get(name)
            if name in provenance and not (isinstance(value, str) and value.strip()):
                errors.append(f"'{path}': provenance.{name} must be a non-empty string — "
                              f"the read-back prints it as the file's own words")
        validation = provenance.get("validation")
        if "validation" in provenance and _fields(
                validation, "provenance.validation", _VALIDATION_REQUIRED,
                _VALIDATION_OPTIONAL, errors, path):
            text = validation.get("text")
            if "text" in validation and not (isinstance(text, str) and text.strip()):
                errors.append(f"'{path}': provenance.validation.text must be a non-empty "
                              f"string — the read-back prints it as the file's own words")
            if "metrics" in validation:
                metrics = validation["metrics"]
                if not isinstance(metrics, dict):
                    errors.append(f"'{path}': provenance.validation.metrics must map "
                                  f"names to finite numbers")
                else:
                    for name, value in metrics.items():
                        if not _is_number(value):
                            errors.append(f"'{path}': provenance.validation.metrics.{name} "
                                          f"= {value!r}: a metric is a finite number")

    compounding = data.get("compounding")
    if "compounding" in data and compounding not in MORTGAGE_COMPOUNDING:   # R6
        errors.append(f"'{path}': compounding {compounding!r} — must be semi_annual or "
                      f"effective_annual")

    term = data.get("term_years")
    grid = data.get("renewal_years")
    term_ok = _is_int(term) and term >= 1
    if "term_years" in data and not term_ok:                              # R7
        errors.append(f"'{path}': term_years {term!r} must be an integer >= 1 — the fixed "
                      f"term every rate in the file is quoted for")
    grid_ok = (isinstance(grid, list) and len(grid) >= 1
               and all(_is_int(year) for year in grid))
    if term_ok and "renewal_years" in data:
        k = len(grid) if isinstance(grid, list) and grid else 1
        expected = [i * term + 1 for i in range(1, k + 1)]
        if not grid_ok or list(grid) != expected:
            grid_ok = False
            errors.append(f"'{path}': renewal_years {grid!r} for term_years {term} must be "
                          f"{expected} — column k is the rate at the k-th renewal, simulation "
                          f"year k·{term}+1; the opening term is the option's own "
                          f"mortgage_rate")

    as_of = data.get("as_of")
    if "as_of" in data:                                                    # R8
        valid = False
        if isinstance(as_of, str) and len(as_of) == 10:
            try:
                valid = datetime.date.fromisoformat(as_of).isoformat() == as_of
            except ValueError:
                valid = False
        if not valid:
            errors.append(f"'{path}': as_of {as_of!r} is not an ISO date (YYYY-MM-DD)")

    paths = data.get("paths")
    rows: List[Tuple[float, ...]] = []
    if "paths" in data:
        if not isinstance(paths, list):
            errors.append(f"'{path}': paths must be a list of rows, got "
                          f"{type(paths).__name__}")
        else:
            width = len(grid) if isinstance(grid, list) else None
            for i, row in enumerate(paths):                                # R9
                if not isinstance(row, list):
                    errors.append(f"'{path}': paths[{i}] is not a list of rates")
                    continue
                if width is not None and len(row) != width:
                    errors.append(f"'{path}': paths[{i}] has {len(row)} rates and "
                                  f"renewal_years has {width}")
                bad = False
                for k, value in enumerate(row):
                    if not (_is_number(value) and value >= 0):
                        errors.append(f"'{path}': paths[{i}][{k}] = {value!r}: a rate is a "
                                      f"finite number >= 0")
                        bad = True
                if not bad:
                    rows.append(tuple(float(v) for v in row))
            if len(paths) < 2:                                             # R10
                errors.append(f"'{path}' has {len(paths)} row{'' if len(paths) == 1 else 's'}: "
                              f"a distribution needs two or more")

    if errors:
        raise RatePathsError("\n".join(errors))
    return RatePathFile(
        sha256=sha, schema_version=version, term_years=term,
        renewal_years=tuple(grid), compounding=compounding,
        as_of=as_of, provenance=provenance, quoted=tuple(rows),
    )


def read_path_file(path: str) -> RatePathFile:
    """Read, pin (R19) and validate one path file.

    Every call re-reads the bytes: the sha256 they hash to is pinned on the
    first read of a resolved path in this process, and any later read that
    hashes differently raises `RatePathsChanged`. Parsing is cached by sha256.
    """
    file = Path(path)
    if not file.is_file():                                                 # R1
        raise RatePathsError(f"renewal_rates.path: no file at '{path}'")
    raw = file.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    key = str(file.resolve())
    first = _FIRST_SHA.setdefault(key, sha)
    if first != sha:                                                       # R19
        raise RatePathsChanged(
            f"'{path}' changed since this process first read it: sha256 "
            f"{first[:12]}… first, {sha[:12]}… now")
    parsed = _PARSED.get(sha)
    if parsed is None:
        parsed = _parse(raw, path, sha)
        _PARSED[sha] = parsed
    return parsed


# ---------------------------------------------------------------------------
# The central row (§5)
# ---------------------------------------------------------------------------

def central_row(quoted: Sequence[Sequence[float]], priced: int) -> Tuple[int, int]:
    """(the central row's index, how many OTHER rows tie it).

    The median of each priced column (the mean of the two middle values when
    the row count is even), then each row's squared Euclidean distance to that
    median path over the priced columns, and the FIRST row at the minimum —
    all in exact rational arithmetic on the parsed floats, because float
    evaluation breaks a true tie by rounding (§0.1 item 1).
    """
    exact = [[Fraction(v) for v in row[:priced]] for row in quoted]
    n = len(exact)
    median: List[Fraction] = []
    for k in range(priced):
        column = sorted(row[k] for row in exact)
        mid = n // 2
        median.append(column[mid] if n % 2 else (column[mid - 1] + column[mid]) / 2)
    distances = [sum((x - m) ** 2 for x, m in zip(row, median)) for row in exact]
    best = min(distances)
    return distances.index(best), distances.count(best) - 1


# ---------------------------------------------------------------------------
# The file against the config (§2 "Grid against the config", §3): R11 to R17
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReadingOption:
    """What the file is checked against, for one condo or house that is not
    all-cash and has a full mortgage block."""
    name: str
    renewal_years: Optional[int]
    amortization: int


def renewals_in(amortization: int, term: int) -> int:
    """n_o: how many renewals an amortization has on a term — the segment
    count `pv.renewal_schedule` builds, less the opening one."""
    return -(-amortization // term) - 1


def price_against(file: RatePathFile, path: str, options: Sequence[ReadingOption],
                  horizon: int) -> LoadedRatePaths:
    """Check the file against the config's reading options and horizon, and
    choose the central row. Raises `RatePathsError` naming the option."""
    term = file.term_years
    errors: List[str] = []
    for opt in options:
        if opt.renewal_years is None:                                      # R14
            errors.append(f"{opt.name} has a mortgage and no mortgage_renewal_years; "
                          f"renewal_rates.path quotes {term}-year rates")
        elif opt.renewal_years != term:                                    # R11
            errors.append(f"{opt.name}.mortgage_renewal_years is {opt.renewal_years}; "
                          f"'{path}' quotes {term}-year rates")
    if errors:
        raise RatePathsError("\n".join(errors))

    columns = {opt.name: renewals_in(opt.amortization, term) for opt in options}
    inside = max(0, (horizon - 1) // term)
    priced_by = {name: min(n, inside) for name, n in columns.items()}
    priced = max(priced_by.values(), default=0)
    if not options:                                                        # R15
        raise RatePathsError(f"'{path}': no option carries a mortgage, so nothing reads a "
                             f"renewal rate")
    if priced == 0:                                                        # R15
        raise RatePathsError(f"no reading option renews inside the {horizon}-year horizon "
                             f"(first renewal: year {term + 1})")

    k = len(file.renewal_years)
    for opt in options:                                                    # R16
        if columns[opt.name] > k:
            errors.append(
                f"'{path}' ends at year {file.renewal_years[-1]}; {opt.name} renews in year "
                f"{(k + 1) * term + 1} inside its {opt.amortization}-year amortization — every "
                f"renewal needs a column, and the engine carries no rate forward")
    deepest = max(options, key=lambda opt: columns[opt.name])
    reach = columns[deepest.name]
    if k > reach:                                                          # R17
        surplus = list(file.renewal_years[reach:])
        errors.append(f"'{path}' renewal_years {surplus}: past every reading option's last "
                      f"renewal ({deepest.name}: year {reach * term + 1})")
    if errors:
        raise RatePathsError("\n".join(errors))

    for opt in options:                                                    # R12
        n = priced_by[opt.name]
        if n == 0:
            continue
        if len({row[:n] for row in file.quoted}) == 1:
            years = list(file.renewal_years[:n])
            errors.append(f"every row of '{path}' prices {opt.name}'s renewals in years "
                          f"{years} at the same rates: no future differs")
    if errors:
        raise RatePathsError("\n".join(errors))

    index, tied = central_row(file.quoted, priced)
    effective = tuple(tuple(effective_mortgage_rate(r, file.compounding) for r in row)
                      for row in file.quoted)
    return LoadedRatePaths(
        path=path, file_sha256=file.sha256, schema_version=file.schema_version,
        term_years=term, renewal_years=file.renewal_years, compounding=file.compounding,
        as_of=file.as_of, provenance=file.provenance, quoted=file.quoted,
        effective=effective, columns=columns, priced_columns=priced,
        priced_years=file.renewal_years[:priced], central_index=index, tied_rows=tied,
    )
