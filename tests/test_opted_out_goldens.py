"""The opted-out goldens: what a run without a renewal-rate path file prints
(docs/specs/2026-10-01-renewal-rate-path-file.md §8, commit 1).

A run with no `renewal_rates` file must be today's run byte for byte, so the
`--json` document of every shipped example and of the uncertainty-surface
fixture, and that fixture's `--decompose --json` document, are stored here as
documents and compared whole. A document, never a bare sha256 of one: a
version bump would move every hash and say nothing about which field moved,
so a failure names the first field that differs.

The run date is pinned, because the fixture's document depends on it (an
anchor's validity window), and the top-level `engine_version` is masked.

Regenerate, only for a change that is MEANT to move a figure:
    uv run python -m tests.test_opted_out_goldens
"""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pytest

import hde.cli as cli_mod

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = Path(__file__).parent / "fixtures" / "opted_out"
RUN_DATE = datetime.date(2026, 10, 1)
MASK = "<masked>"

# (golden file name, config path relative to the repo root, extra flags)
CASES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = tuple(
    [(f"{Path(p).stem}.json", p, ()) for p in sorted(
        str(c.relative_to(ROOT)) for c in (ROOT / "examples").glob("*.yaml"))]
    + [("uncertainty_surface.json", "tests/fixtures/uncertainty_surface.yaml", ()),
       ("uncertainty_surface.decompose.json", "tests/fixtures/uncertainty_surface.yaml",
        ("--decompose",))]
)


class _PinnedDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(RUN_DATE.year, RUN_DATE.month, RUN_DATE.day)


class _PinnedDatetime:
    """`cli`'s view of the `datetime` module with `date.today` pinned."""

    date = _PinnedDate

    def __getattr__(self, name: str) -> Any:
        return getattr(datetime, name)


def document(config: str, flags: Tuple[str, ...] = ()) -> str:
    """The `--json` document `hde <config> <flags> --json` prints, run
    in-process from the repo root at the pinned date, `engine_version` masked,
    re-serialized exactly as the CLI serializes it."""
    out = io.StringIO()
    saved = (os.getcwd(), sys.argv, cli_mod.datetime)
    try:
        os.chdir(ROOT)
        sys.argv = ["hde", config, *flags, "--json"]
        cli_mod.datetime = _PinnedDatetime()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli_mod.main()
    finally:
        os.chdir(saved[0])
        sys.argv = saved[1]
        cli_mod.datetime = saved[2]
    assert code == 0, (config, flags, code)
    doc = json.loads(out.getvalue())
    assert "engine_version" in doc
    doc["engine_version"] = MASK
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def first_difference(want: Any, got: Any, where: str = "$") -> Optional[str]:
    """The path of the first field at which two parsed documents differ."""
    if type(want) is not type(got):
        return f"{where}: {type(want).__name__} {want!r:.80} against {type(got).__name__} {got!r:.80}"
    if isinstance(want, dict):
        for key in list(want) + [k for k in got if k not in want]:
            if key not in want or key not in got:
                return f"{where}.{key}: present on one side only"
            found = first_difference(want[key], got[key], f"{where}.{key}")
            if found:
                return found
        if list(want) != list(got):
            return f"{where}: same keys in a different order"
        return None
    if isinstance(want, list):
        for i, (a, b) in enumerate(zip(want, got)):
            found = first_difference(a, b, f"{where}[{i}]")
            if found:
                return found
        if len(want) != len(got):
            return f"{where}: {len(want)} entries against {len(got)}"
        return None
    if json.dumps(want) != json.dumps(got):
        return f"{where}: {want!r:.80} against {got!r:.80}"
    return None


@pytest.mark.parametrize("name,config,flags", CASES, ids=[c[0] for c in CASES])
def test_a_run_with_no_path_file_is_the_stored_document(name, config, flags):
    stored = (GOLDEN_DIR / name).read_text(encoding="utf-8")
    got = document(config, flags)
    if got != stored:
        where = first_difference(json.loads(stored), json.loads(got))
        pytest.fail(f"{' '.join([config, *flags, '--json'])} moved from {name}: "
                    f"{where or 'same parsed document, different bytes'}")


def test_every_shipped_example_has_a_stored_document():
    """Seven examples and the fixture, twice for the fixture: a new example
    with no stored document would be an example nothing holds still."""
    assert len(CASES) == 9
    stored = sorted(p.name for p in GOLDEN_DIR.glob("*.json"))
    assert stored == sorted(c[0] for c in CASES)


def test_the_difference_names_the_field_that_moved():
    want = {"a": {"b": [1.0, 2.0]}, "c": 1}
    assert first_difference(want, {"a": {"b": [1.0, 2.5]}, "c": 1}) == "$.a.b[1]: 2.0 against 2.5"
    assert first_difference(want, {"a": {"b": [1.0, 2.0]}}) == "$.c: present on one side only"
    assert first_difference(want, json.loads(json.dumps(want))) is None


def _write_all() -> List[str]:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, config, flags in CASES:
        (GOLDEN_DIR / name).write_text(document(config, flags), encoding="utf-8")
        written.append(name)
    return written


if __name__ == "__main__":
    for written in _write_all():
        print(f"wrote {GOLDEN_DIR / written}")
