"""demoflow CLI (spec §3) — two subcommands, `run` and `tripwires`, and nothing else.

`pyproject.toml` has declared `demoflow = "demoflow.cli:main"` since scaffold and this module
did not exist, so `uv run demoflow --help` raised `ModuleNotFoundError` for the whole arc while
the suite ran green. That is the shape this file is written against: the console script, the
package metadata and the entry point are ONE boundary, and a test that imports `main` and hands
it `argv` mocks exactly the leg that was broken.

THE TWO SUBCOMMANDS ARE NOT TWO VIEWS OF ONE COMPUTATION, and the plan's body treated them as
if they were — `main` called `run_pipeline` for BOTH, so asking for six tripwire statuses loaded
five workbooks, evaluated the excess-demand grid four times, and WROTE `rankings.json` into
whatever directory the operator was standing in. `run` emits; `tripwires` evaluates. They are
routed to different functions and only one of them can write anything.

THE EXIT CODES ANSWER DIFFERENT QUESTIONS, which is the one thing about this CLI a reader must
not have to guess, so it is stated here, in `--help`, and in the contract tests:

  * `demoflow run` exits on EMISSION success — both documents built, every contract validated,
    both files written. It deliberately does NOT adopt the tripwire verdict: on the committed
    tree all six indicators are honestly UNKNOWN, and a run that emitted a correct baseline
    saying so did its job. Conflating the two would make `run` unusable as an emitter and would
    give the operator one code for two different failures.
  * `demoflow tripwires` exits `run_exit_code` — spec §7c's "0 only when every code-required
    indicator is present exactly once, finite, fresh, well-banded, and OK". That is a property
    of the EVALUATION, not of the emission, and it is the code a cron or a shell `&&` should
    branch on.

Because those differ, `run` PRINTS the tripwire verdict beside its exit line: an operator who
reads `run`'s exit 0 as "the tripwires are green" has been misled by a gate that was never
claiming it. It prints the RUN LOG under that verdict for the same reason (ruling U, see
`_print_log`) — `run` is the path that emits the baseline, and the log carries the only line
that separates a gutted feed from a pre-era refusal. What stays `tripwires`-only is the
per-indicator LISTING.

NOTHING IS RE-DERIVED HERE. The status vocabulary, the source strings and the reason tokens are
the closed enums and the code-owned registry the artifacts use (spec §7's "no open string
anywhere" rule applies to the surface an operator reads, not only to the JSON); the exit code is
returned verbatim from the evaluation. The one thing this layer OWNS is the clock: `now` is
injected into the gate so an auditor can reproduce a verdict, and the CLI is the edge that reads
the real date — the library defaults (`now_month=12`) are a fail-safe floor for callers who do
not state one, never a verdict to ship.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from demoflow.errors import BasisError, CalibrationError, LoaderError
from demoflow.pipeline import evaluate_tripwires, run_pipeline

# The refusal classes this CLI turns into a named, nonzero exit rather than a traceback.
# `ValueError` is in the list because that is how `output/artifacts.py` refuses a document that
# violates its field allowlist or carries an open string — spec §7c requires such a run to exit
# nonzero WITH THE NAMED ERROR, and a traceback buries the name under a stack. The exception's
# type is printed alongside its message so a genuine programming ValueError is still
# distinguishable from a data refusal by anyone reading the line.
REFUSALS = (LoaderError, CalibrationError, BasisError, ValueError)

_EPILOG = """exit codes (they answer DIFFERENT questions):
  run        0 on EMISSION success -- both documents built, every contract validated, both
             files written. NOT the tripwire verdict: a run whose indicators are all UNKNOWN
             still emitted a correct baseline. The verdict is printed beside the exit line.
  tripwires  run_exit_code (spec 7c) -- 0 only when every code-required indicator is present
             exactly once, finite, fresh, well-banded, and OK; nonzero otherwise. This is the
             code to branch on.
"""


def build_parser() -> argparse.ArgumentParser:
    """Exposed so the exit-code contract can be tested against the help text an operator reads.

    Both meanings ride the TOP-LEVEL help. An operator who has to already know which subcommand
    to ask before they can learn what its exit code means cannot script against it, and an exit
    code nobody can look up is a gate nobody can rely on.
    """
    parser = argparse.ArgumentParser(
        prog="demoflow",
        description="Demographic housing-flow scenario module (Quebec RMR), Tranche 1.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser(
        "run", help="emit rankings + tripwire artifacts (exits 0 on emission success)",
        description="Run the Tranche-1 pipeline and emit rankings.json + "
                    "tripwire_baseline.json. Exits 0 on EMISSION success -- not on the "
                    "tripwire verdict, which is printed and available from "
                    "`demoflow tripwires`.")
    run.add_argument("--out", type=Path, default=Path("artifacts"),
                     help="directory to write both artifacts into (default: ./artifacts)")

    # NO `--out` HERE, and that is the interface, not an omission. This subcommand writes
    # nothing, so a `--out` it accepted and ignored would be a flag that lies; the plan built
    # both subparsers in one loop and gave the option to both.
    sub.add_parser(
        "tripwires", help="evaluate the spec 7c indicators (exits run_exit_code)",
        description="Evaluate the six code-required tripwire indicators and print their "
                    "status. Writes nothing and does not build the demographic model. Exits "
                    "run_exit_code: 0 only when every required indicator is present exactly "
                    "once, finite, fresh, well-banded, and OK.")
    return parser


def _print_log(log) -> None:
    """The run log, on EVERY path that has one — one formatter, so the two cannot drift apart.

    THE LOG IS NOT OPTIONAL OUTPUT (spec §6 amendment #15 / ruling U). A feed truncated to the
    two modeled CMAs surfaces as `source_unavailable` — the same token as "the plan era has not
    closed a year yet" — so a record ALONE cannot tell a pre-era refusal from a gutted feed, and
    the ruling puts that distinction in the run log.

    THAT MAKES IT LOAD-BEARING ON `run` IN PARTICULAR, which is the finding this function exists
    to answer: `run` is the ONLY subcommand that emits `tripwire_baseline.json`, and it was
    computing the log, returning it, and dropping it. The two states produce a byte-identical
    record — UNKNOWN / `source_unavailable`, `current_value` and `as_of` null — so a cron'd
    emitter left nothing behind that could separate them. "Run `demoflow tripwires` afterwards"
    is not the recovery: that is a SECOND read of a deliberately unpinned, monthly-refreshing
    feed, and the whole point of one-read-per-run is that two reads can disagree. Nor does the
    envelope catch it — the IRCC digest is RECORDED, not pinned, so a changed hash and a normal
    monthly refresh look the same.

    The `  log: ` prefix keeps these lines disjoint from `run`'s `wrote ` lines, which are a
    machine-readable claim about a side effect.
    """
    for line in log:
        print(f"  log: {line}")


def _print_tripwires(results, log) -> None:
    """One line per indicator, then the run log. The LISTING is this subcommand's alone (`run`
    prints a verdict and points here); the log is not.

    Every token on these lines comes from a closed vocabulary: `status` and `reason` from their
    enums, `source` from the code-owned registry the emitted record is bound to.
    """
    for t in results:
        reason = f" — {t.reason.value}" if t.reason is not None else ""
        print(f"{t.status.value:8} {t.indicator} ({t.source}){reason}")
    _print_log(log)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # THE CLOCK IS READ HERE AND NOWHERE DEEPER. `now` is a parameter of the verification gate
    # so an auditor can reproduce a freshness verdict; the edge is the only layer entitled to
    # decide what it currently is.
    now = datetime.now()
    try:
        if args.cmd == "run":
            result = run_pipeline(out_dir=args.out, now_year=now.year, now_month=now.month)
        else:
            result = evaluate_tripwires(now_year=now.year, now_month=now.month)
    except REFUSALS as exc:
        # The `try` covers the WORK and not the reporting: a refusal raised while printing a
        # result would otherwise be reported as a refusal of the run itself.
        print(f"demoflow {args.cmd}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.cmd == "run":
        # The emitted names come from the run, never from a pair typed here that would drift
        # the day a third document is added.
        for name in result["artifacts"]:
            print(f"wrote {result['out_dir'] / name}")
        verdict = result["exit_code"]
        print(f"tripwire verdict: {verdict} "
              f"({'all required indicators OK' if verdict == 0 else 'NOT all OK'}) — "
              f"`demoflow tripwires` for the listing and that exit code")
        # Ruling U's discriminator, on the path that EMITS the baseline (see `_print_log`).
        # Indexed, not `.get`: the key is part of `run_pipeline`'s return contract and a
        # missing one is a shape break that should be loud rather than silently logless.
        _print_log(result["tripwire_log"])
        return 0

    _print_tripwires(result["tripwires"], result["tripwire_log"])
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
