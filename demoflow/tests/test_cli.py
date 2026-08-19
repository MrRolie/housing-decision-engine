"""Contract tests for `cli.py` — spec §3's two subcommands, and the console script.

WHY THIS FILE EXISTS AT ALL, stated once. `pyproject.toml` has declared
`demoflow = "demoflow.cli:main"` since scaffold and `src/demoflow/cli.py` never existed, so
`uv run demoflow --help` died with `ModuleNotFoundError` for the whole arc while every test in
this suite passed. THE PACKAGE METADATA IS THE BOUNDARY, and a test that imports `main`
directly mocks exactly the leg that was broken — so `test_the_declared_console_script_target_resolves`
below resolves the entry point THROUGH the declaration in `pyproject.toml` rather than through
an import statement a reader wrote by hand. The live `uv run demoflow` legs are run at
acceptance; this file pins what a live run cannot re-check on every commit.

THE EXIT-CODE CONTRACT IS AN INTERFACE PROMISE (seat ruling, run-30 carry C4), so it is tested
in both directions and its `--help` text is tested too:

  * `demoflow run`       exits on EMISSION success — artifacts written and every contract
                         validated. It does NOT adopt the tripwire verdict: a run whose
                         indicators are all UNKNOWN still emitted a correct baseline, and a
                         gate that conflated the two would make `run` unusable as an emitter.
  * `demoflow tripwires` exits `run_exit_code` — spec §7c's "0 only when every code-required
                         indicator is present exactly once, finite, fresh, well-banded, and
                         OK", which is a property of the EVALUATION, not of the emission.

An exit code no operator can look up is a gate nobody can rely on, so both meanings ride
`demoflow --help` and a test asserts they are there.
"""
import inspect
import tomllib
from datetime import datetime
from pathlib import Path

import pytest

import demoflow.cli as cli
import demoflow.pipeline as pipeline
from demoflow.output.tripwires import (
    REQUIRED_INDICATORS,
    SOURCE_REGISTRY,
    Reason,
    Status,
    TripwireResult,
)

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _fake_result(exit_code: int = 1, out_dir: Path | None = None) -> dict:
    """What `run_pipeline` hands back, minus the ten seconds of real I/O."""
    trips = [TripwireResult(i, None, SOURCE_REGISTRY[i], None, 0.0, 0.0, Status.UNKNOWN,
                            Reason.SOURCE_UNAVAILABLE) for i in sorted(REQUIRED_INDICATORS)]
    return {"rankings": [], "tripwires": trips, "tripwire_log": ["fake: nothing wired"],
            "exclusions": [], "exit_code": exit_code, "out_dir": out_dir,
            "artifacts": ["rankings.json", "tripwire_baseline.json"],
            "assumptions_hash": "0" * 12, "data_vintage": {}}


# ------------------------------------------------------------------ the boundary that was broken

def test_the_declared_console_script_target_resolves():
    """Carry C1. Resolved through `[project.scripts]` itself, so a rename on EITHER side reds —
    an `import demoflow.cli` written by hand cannot see the declaration drift away from it."""
    import importlib
    declared = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["scripts"]
    assert declared == {"demoflow": "demoflow.cli:main"}, declared
    module_path, _, attr = declared["demoflow"].partition(":")
    entry = getattr(importlib.import_module(module_path), attr)
    assert callable(entry) and entry is cli.main


def test_no_subcommand_refuses_rather_than_defaulting_to_one():
    """`run` and `tripwires` do different things and write different amounts; guessing which
    one a bare `demoflow` meant is the kind of default that emits an artifact nobody asked for."""
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


# ------------------------------------------------------------------ C4: the exit-code contract

@pytest.mark.parametrize("phrase", [
    "emission",          # what `run` exits on
    "run_exit_code",     # what `tripwires` exits
])
def test_help_states_both_exit_code_meanings(phrase):
    """Both meanings must be reachable from `demoflow --help` ALONE — an operator who has to
    know which subcommand to ask before they can learn what its exit code means cannot script
    against it (carry C4)."""
    assert phrase in cli.build_parser().format_help()


def test_run_exits_on_emission_success_not_on_the_tripwire_verdict(monkeypatch, tmp_path):
    """The ruled contract, in the direction that a naive `return result["exit_code"]` breaks:
    the committed tree's six honest UNKNOWNs make the tripwire verdict 1, and `run` still
    emitted both documents correctly, so it exits 0."""
    monkeypatch.setattr(cli, "run_pipeline",
                        lambda **kw: _fake_result(exit_code=1, out_dir=kw["out_dir"]))
    assert cli.main(["run", "--out", str(tmp_path)]) == 0


def test_run_names_the_files_the_run_ACTUALLY_emitted(monkeypatch, tmp_path, capsys):
    """"wrote X" is a claim about a side effect, so it is read off the run's own emission list
    and never from a pair typed into the CLI. Measured: a mutant restoring the plan's literal
    (`wrote {out}/rankings.json and {out}/tripwire_baseline.json`) survived every other test in
    this file — it prints the right two names today and would keep printing exactly those two
    the day a third document is emitted, which is a completion claim about a file that was
    never written."""
    monkeypatch.setattr(cli, "run_pipeline", lambda **kw: dict(
        _fake_result(exit_code=0, out_dir=kw["out_dir"]),
        artifacts=["rankings.json", "tripwire_baseline.json", "scenario_prior.json"]))
    cli.main(["run", "--out", str(tmp_path)])
    printed = capsys.readouterr().out
    for name in ("rankings.json", "tripwire_baseline.json", "scenario_prior.json"):
        assert str(tmp_path / name) in printed


def test_a_refused_emission_exits_nonzero(monkeypatch, tmp_path):
    """The other half of "exits on EMISSION success". `artifacts.py` refuses a document by
    raising; spec §7c requires the run to exit nonzero WITH THE NAMED ERROR, so the message
    must survive to stderr rather than being swallowed into a bare code."""
    def refuse(**kw):
        raise ValueError("rankings.json carries an open string at rows[0].flags[0]")
    monkeypatch.setattr(cli, "run_pipeline", refuse)
    assert cli.main(["run", "--out", str(tmp_path)]) != 0


def test_the_named_error_reaches_stderr(monkeypatch, tmp_path, capsys):
    from demoflow.errors import LoaderError

    def refuse(**kw):
        raise LoaderError("compo-rmr-base.xlsx: sha256 drift, expected abc got def")
    monkeypatch.setattr(cli, "run_pipeline", refuse)
    cli.main(["run", "--out", str(tmp_path)])
    assert "sha256 drift" in capsys.readouterr().err


def test_tripwires_exits_the_run_level_gate_verbatim(monkeypatch):
    """`tripwires` returns what the evaluation ruled — never a re-derivation in the CLI, which
    would be a second copy of spec §7c's exit rule for a reader to reconcile."""
    monkeypatch.setattr(cli, "evaluate_tripwires", lambda **kw: _fake_result(exit_code=7))
    assert cli.main(["tripwires"]) == 7


# --------------------------------------------------- C2/C3: the status listing builds nothing

def test_tripwires_never_calls_the_full_pipeline(monkeypatch):
    """Carry C2 at the CLI boundary. The plan's `main` called `run_pipeline` for BOTH
    subcommands; here it is poisoned, so a body that reaches it dies."""
    def poison(**kw):
        raise AssertionError("`demoflow tripwires` ran the full pipeline")
    monkeypatch.setattr(cli, "run_pipeline", poison)
    now = datetime.now()
    expected = pipeline.evaluate_tripwires(now_year=now.year, now_month=now.month)["exit_code"]
    assert cli.main(["tripwires"]) == expected


def test_tripwires_writes_nothing_into_the_working_directory(monkeypatch, tmp_path):
    """Carry C3. `run_pipeline` defaults `out_dir` to `Path.cwd() / "artifacts"`, so the plan's
    `main` emitted `rankings.json` into whatever directory the operator happened to be in when
    they asked for six statuses."""
    monkeypatch.chdir(tmp_path)
    cli.main(["tripwires"])
    assert list(tmp_path.iterdir()) == []


def test_tripwires_takes_no_out_flag():
    """It does not write, so a `--out` on it would be an interface that lies. Structural: the
    parser REFUSES the flag rather than accepting and ignoring it (the plan built both
    subparsers in one loop and gave `--out` to both)."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["tripwires", "--out", "somewhere"])
    assert exc.value.code == 2


# ------------------------------------------------------------------ C5: closed vocabularies out

def test_every_printed_token_comes_from_a_closed_vocabulary(monkeypatch, capsys):
    """Carry C5. `source` is the DECLARED registry string and `reason` is the closed enum's
    token — the same "no open string anywhere" rule the artifacts obey, applied to the surface
    an operator actually reads."""
    monkeypatch.setattr(cli, "evaluate_tripwires", lambda **kw: _fake_result(exit_code=1))
    cli.main(["tripwires"])
    printed = capsys.readouterr().out
    for indicator in REQUIRED_INDICATORS:
        assert SOURCE_REGISTRY[indicator] in printed
    assert Reason.SOURCE_UNAVAILABLE.value in printed
    assert Status.UNKNOWN.value in printed


def test_the_run_log_reaches_the_operator(monkeypatch, capsys):
    """Spec §6 amendment #15 / ruling U: the truncation state surfaces as `source_unavailable`
    like every other empty-closed-years cause, so THE RUN LOG must name member-set truncation
    or a reader cannot tell a pre-era refusal from a gutted feed. Both subcommands carry the
    log; only the STATUS LISTING is tripwires-only."""
    monkeypatch.setattr(cli, "evaluate_tripwires", lambda **kw: _fake_result(exit_code=1))
    cli.main(["tripwires"])
    assert "  log: fake: nothing wired" in capsys.readouterr().out


def test_the_run_log_reaches_the_operator_on_the_EMITTING_path_TOO(monkeypatch, tmp_path, capsys):
    """Review finding: `run` is the ONLY subcommand that emits `tripwire_baseline.json`, and it
    was dropping the very log ruling U exists to create.

    The dropped discriminator is not cosmetic. A feed truncated to the two modeled CMAs and a
    plan era that has not closed a year yet produce a BYTE-IDENTICAL tripwire record —
    `pr_landings_annual`, status UNKNOWN, reason `source_unavailable`, `current_value` null,
    `as_of` null — because the reason enum is spec-closed and correctly stays closed. The only
    thing that separates them is `_member_set_note`'s "MEMBER-SET TRUNCATION SUSPECTED" line,
    which rides the run log. So a cron'd `demoflow run` emitted a baseline that could not be
    told apart from a healthy one, printed `NOT all OK`, exited 0, and threw the discriminator
    away. "Just run `demoflow tripwires` afterwards" is not the recovery: that is a SECOND read
    of a deliberately unpinned, monthly-refreshing feed. `test_the_cheap_tripwire_path_returns_
    the_SAME_verdict_as_the_full_run` (test_pipeline.py) guarantees the two paths agree ON THE
    SAME BYTES, and `test_the_ircc_feed_is_read_once_inside_the_identity_bracket` exists because
    a second read of those bytes is exactly what nothing downstream can see — so a log recovered
    by a later invocation is a statement about a different read than the one that emitted. Nor
    does the envelope catch it: the IRCC digest is RECORDED, not pinned, so a changed hash is
    indistinguishable from a normal monthly refresh.

    THE `  log: ` PREFIX IS PART OF THE ASSERTION. `test_run_emits_both_documents_through_the_cli`
    reads `run`'s side-effect claim off the `wrote ` lines, so the two line shapes must stay
    disjoint; asserting the bare message would leave that disjointness an accident of
    formatting rather than a pinned property."""
    monkeypatch.setattr(cli, "run_pipeline",
                        lambda **kw: _fake_result(exit_code=1, out_dir=kw["out_dir"]))
    assert cli.main(["run", "--out", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "  log: fake: nothing wired" in printed
    # ...and it did not arrive by turning `run` into the status listing, which stays the other
    # subcommand's job (carries C2/C3: `run` points at `tripwires` for the listing).
    assert "UNKNOWN" not in printed


# ------------------------------------------------------------------ the clock is the CLI's job

def test_the_cli_supplies_the_real_month_to_both_subcommands(monkeypatch, tmp_path):
    """`run_pipeline` defaults `now_month` to 12 — the FAIL-SAFE end of the freshness axis, so
    an under-specified call refuses rather than certifies. That default is a floor for library
    callers, not a verdict: leaving it in place would freeze the freshness gate at the hardcoded
    2026-12 and read every future feed as fresher than it is. The gate takes `now` injected;
    the CLI is the edge that reads the clock."""
    seen = {}
    monkeypatch.setattr(cli, "run_pipeline",
                        lambda **kw: (seen.update(run=kw), _fake_result(1, kw["out_dir"]))[1])
    monkeypatch.setattr(cli, "evaluate_tripwires",
                        lambda **kw: (seen.update(trip=kw), _fake_result(1))[1])
    before = datetime.now()
    cli.main(["run", "--out", str(tmp_path)])
    cli.main(["tripwires"])
    after = datetime.now()

    clock = {(d.year, d.month) for d in (before, after)}   # tolerate a month boundary mid-test
    for kw in (seen["run"], seen["trip"]):
        assert (kw["now_year"], kw["now_month"]) in clock
    # Bind the call shape to the callee's REAL signature — a fake cannot vouch for kwargs the
    # production function does not accept, which is how a mocked CLI passes while `uv run` dies.
    inspect.signature(pipeline.run_pipeline).bind(**seen["run"])
    inspect.signature(pipeline.evaluate_tripwires).bind(**seen["trip"])


# ------------------------------------------------------------------ the real thing, end to end

def test_run_emits_both_documents_through_the_cli(tmp_path, monkeypatch, capsys):
    """One unmocked pass. Everything above swaps `run_pipeline` for a fake, which is exactly
    the substitution that let a missing `cli.py` sit green for an arc.

    THE SPY IS HOW THE FAKE STAYS HONEST. `_fake_result` is a hand-written stand-in for
    `run_pipeline`'s return, and a fake that drifts from the real shape turns every test above
    into a test of the fake — measured, not hypothesised: this suite passed with an
    `artifacts` key the real run had and the fake did not. The spy wraps the REAL function on
    the one pass that runs it anyway, so the shapes are compared at zero extra cost."""
    real, seen = cli.run_pipeline, {}
    monkeypatch.setattr(cli, "run_pipeline",
                        lambda **kw: seen.setdefault("r", real(**kw)))
    assert cli.main(["run", "--out", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "rankings.json", "tripwire_baseline.json"]
    assert set(seen["r"]) == set(_fake_result()), "the CLI suite's fake drifted from run_pipeline"
    wrote = {line.removeprefix("wrote ") for line in capsys.readouterr().out.splitlines()
             if line.startswith("wrote ")}
    assert wrote == {str(p) for p in tmp_path.iterdir()}, "the `wrote` lines are not the files"
