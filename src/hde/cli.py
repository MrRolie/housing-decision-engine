"""
Command-line interface for the housing decision engine.

Usage:
    hde <config.yaml> [options]
"""

import argparse
import datetime
import sys
from pathlib import Path

from .config import (
    load_config, all_warnings, affordability_warnings, single_path_run,
    uncertainty_source_warnings, ConfigValidationError,
)
from .deterministic import compute_deterministic
from .market_scenario import ScenarioPriorError
from .models import InputError, compute_verdict
from .monte_carlo import run_monte_carlo
from .reporting import format_text_report


def main() -> int:
    """
    Main entry point for the CLI.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = argparse.ArgumentParser(
        prog="hde",
        description="Rent vs condo vs house present-value comparison, "
                    "deterministic and Monte Carlo",
    )

    parser.add_argument(
        "config",
        type=str,
        nargs="?",
        help="Path to YAML configuration file (omit with --print-schema)",
    )

    parser.add_argument(
        "--no-monte-carlo",
        action="store_true",
        help="Skip Monte Carlo simulation (deterministic only)",
    )

    parser.add_argument(
        "--no-deterministic",
        action="store_true",
        help="Skip deterministic calculation (Monte Carlo only)",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress detailed output, print only summary line",
    )

    parser.add_argument(
        "--plots",
        type=str,
        default=None,
        metavar="DIR",
        help="Render the six-act decision story into DIR after the run",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full result document as JSON (agent-native; the "
             "serialization core every surface uses)",
    )

    parser.add_argument(
        "--read-back",
        action="store_true",
        help="Print ONLY the read-back block — every [warning], the source classes "
             "the user did not state, the decisiveness rule, the financing and "
             "other-cost lines, affordability, and any threshold or sweep lines — "
             "the lines an answer must carry verbatim (exit code as the run)",
    )

    parser.add_argument(
        "--print-schema",
        action="store_true",
        help="Print the input contract (sections, keys, required, notes) and exit",
    )

    parser.add_argument(
        "--print-anchors",
        action="store_true",
        help="Print the provenance registry — every engine default with its "
             "value, source, URL, rationale, band, retrieved_on — and exit",
    )

    parser.add_argument(
        "--story",
        type=str,
        default=None,
        metavar="DIR",
        help="Write the full story package into DIR: six-act plots, "
             "text report, and a STORY.md one-pager",
    )

    parser.add_argument(
        "--sweep",
        action="append",
        default=[],
        metavar="KEY=v1,v2,...|KEY=start:stop:n",
        help="Re-run the comparison across values of one input (repeatable), e.g. "
             "--sweep years=5,10,20 or --sweep condo.value_growth_rate=0:0.04:5; prints "
             "per-point verdicts and where the cheapest option flips; rides --json as 'sweeps'",
    )
    parser.add_argument(
        "--break-even",
        action="append",
        default=[],
        metavar="KEY|KEY=lo:hi",
        help="Solve one input for the value where the two priced options' total PVs cross, "
             "with the tie-band edges around it (repeatable), e.g. --break-even rent.monthly_rent "
             "or --break-even condo.initial_value=300000:900000; needs exactly two options; "
             "beside --sweep the threshold is re-solved at every sweep point ('across'); "
             "rides --json as 'break_evens'",
    )
    args = parser.parse_args()

    if args.print_schema:
        import json as _json
        from .input_schema import input_schema
        print(_json.dumps(input_schema(), indent=2))
        return 0

    if args.print_anchors:
        import json as _json
        from .serialization import anchors_to_dict
        print(_json.dumps(anchors_to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.config is None:
        print("Error: config path required (or use --print-schema / --print-anchors)",
              file=sys.stderr)
        return 1

    # Validate config path
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file not found: {args.config}", file=sys.stderr)
        return 1

    # Load configuration
    try:
        spec = load_config(str(config_path))
    except ConfigValidationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 1

    # The demographic prior is loaded ONCE at this edge (the prior-vs-constant
    # mismatch hard-fails inside load_scenario_prior and surfaces as a clean
    # Error line, no traceback) and reused by the run, the plots and the story.
    prior = None
    if spec.market_scenario is not None:
        from .monte_carlo import _load_prior_if_any
        try:
            prior = _load_prior_if_any(spec)
        except ScenarioPriorError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Warnings (audit U2 coherence + the time-anchor staleness guard): surface,
    # never refuse. stderr so --quiet and piped stdout stay clean; the same list
    # rides the --json document. The wall clock is read here, at the edge.
    warnings = all_warnings(spec, prior, current_year=datetime.date.today().year)
    for warning in warnings:
        print(f"[warning] {warning}", file=sys.stderr)

    # Run analysis — typed refusals (bad prior file, mode composition, direct-
    # construction violations) exit cleanly with "Error: <msg>", no traceback.
    det_result = None
    mc_result = None

    try:
        if not args.no_deterministic:
            det_result = compute_deterministic(spec)
            # Warnings that need the result (affordability breaches) join the
            # same channel — stderr now, the --json `warnings` list below.
            for warning in affordability_warnings(det_result):
                warnings.append(warning)
                print(f"[warning] {warning}", file=sys.stderr)

        if not args.no_monte_carlo:
            mc_result = run_monte_carlo(spec)
    except (ConfigValidationError, InputError, ScenarioPriorError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # The decision, computed ONCE here: the source echo's warning needs it (a
    # Monte-Carlo verdict resting on uncertainty inputs the user never stated),
    # and --json serializes this same object. Before the sweeps, so the story
    # package's `warnings=` list carries the warning too.
    verdict = None
    if det_result is not None:
        verdict = compute_verdict(
            det_result, mc_result,
            years=spec.simulation.years,
            discount_rate=spec.simulation.discount_rate,
            single_path=single_path_run(spec),
        )
        for warning in uncertainty_source_warnings(spec, det_result, verdict):
            warnings.append(warning)
            print(f"[warning] {warning}", file=sys.stderr)

    # Parameter sweeps (flip points) — through the same loader and verdict rule.
    sweeps = []
    sweep_specs = []  # (key, values) pairs; --break-even re-solves at each
    if args.sweep:
        import yaml as _yaml
        from .sweep import parse_sweep, run_sweep
        raw = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
        for sweep_arg in args.sweep:
            try:
                key, values = parse_sweep(sweep_arg)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
            sweeps.append(run_sweep(raw, key, values, monte_carlo=not args.no_monte_carlo))
            # the sweep's own (deduped) grid, so a break-even re-solved "across"
            # it does not repeat itself at a collapsed integer point
            sweep_specs.append((key, sweeps[-1]["values"]))

    # Break-evens (threshold questions) — same loader, deterministic line.
    break_evens = []
    if args.break_even:
        import yaml as _yaml
        from .break_even import parse_break_even, solve_break_even, solve_break_even_across
        raw = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
        for be_arg in args.break_even:
            try:
                key, lo, hi = parse_break_even(be_arg)
                result = solve_break_even(raw, key, lo, hi, prior=prior)
                # Beside --sweep, the threshold is re-solved at every sweep point
                # ("the rent threshold at 0% and at 2% growth" in one call).
                across = [solve_break_even_across(raw, key, lo, hi, skey, vals)
                          for skey, vals in sweep_specs if skey != key]
                if across:
                    result["across"] = across
                break_evens.append(result)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1

    # The read-back block (2026-09-04): the lines an honest answer must carry,
    # assembled by the engine in one order rather than gathered by hand from
    # four surfaces. Built here, after the sweeps and thresholds, so the same
    # list rides --json and the text block below.
    from .serialization import read_back_lines
    read_back = read_back_lines(
        spec, warnings=warnings, verdict=verdict, det=det_result, prior=prior,
        break_evens=break_evens, sweeps=sweeps,
    )

    # Output results. --read-back keeps stdout to the block alone, so a caller
    # that wants only the lines to carry does not have to parse them out.
    if args.json and not args.read_back:
        import json as _json
        from .serialization import (
            assumptions_to_dict, det_to_dict, engine_version, mc_to_dict,
            verdict_to_dict,
        )
        assumptions = assumptions_to_dict(spec, prior)
        assumptions["read_back"] = read_back
        doc = {
            "engine_version": engine_version(),
            "warnings": warnings,
            "assumptions": assumptions,
            "verdict": verdict_to_dict(verdict),
            "deterministic": det_to_dict(det_result) if det_result is not None else None,
            "monte_carlo": mc_to_dict(mc_result) if mc_result is not None else None,
        }
        if args.sweep:
            doc["sweeps"] = sweeps
        if args.break_even:
            doc["break_evens"] = break_evens
        print(_json.dumps(doc, indent=2, ensure_ascii=False))
        # plots/story still render below when requested
    elif args.read_back:
        pass  # the block below is the whole of stdout
    elif args.quiet:
        # Print summary line only
        if det_result is not None:
            parts = []
            if det_result.condo is not None:
                parts.append(f"Condo: ${det_result.condo.total_pv:,.0f}")
            if det_result.house is not None:
                parts.append(f"House: ${det_result.house.total_pv:,.0f}")
            if det_result.rent is not None:
                parts.append(f"Rent: ${det_result.rent.total_pv:,.0f}")
            print("  ".join(parts))
        elif mc_result is not None:
            parts = []
            if mc_result.condo is not None:
                parts.append(f"Condo MC mean: ${mc_result.condo.summary.mean:,.0f}")
            if mc_result.house is not None:
                parts.append(f"House MC mean: ${mc_result.house.summary.mean:,.0f}")
            if mc_result.rent is not None:
                parts.append(f"Rent MC mean: ${mc_result.rent.summary.mean:,.0f}")
            print("  ".join(parts))
    else:
        # Print full report — requires deterministic results
        if det_result is not None:
            report = format_text_report(det_result, mc_result, spec.simulation, spec.economic,
                                        spec=spec, prior=prior)
            print(report)
        elif mc_result is not None:
            # MC-only mode: build a minimal det result placeholder to satisfy signature
            from .models import ComparisonDeterministicResult
            empty_det = ComparisonDeterministicResult()
            report = format_text_report(empty_det, mc_result, spec.simulation, spec.economic,
                                        spec=spec, prior=prior)
            print(report)

    if args.plots:
        if det_result is None:
            print(
                "Note: --plots needs the deterministic run; re-run without "
                "--no-deterministic to render the story plots.",
                file=sys.stderr,
            )
        else:
            from .story_plots import render_decision_story

            try:
                saved = render_decision_story(
                    spec, det_result, mc_result, prior=prior, out_dir=args.plots,
                )
            except Exception as e:
                print(f"Error rendering story plots: {e}", file=sys.stderr)
                return 1
            # Under --json stdout is the document; status lines go to stderr
            # (round-6 dogfood: a saved `--story --json` output did not parse).
            status_out = sys.stderr if (args.json or args.read_back) else sys.stdout
            for path in saved:
                print(f"Saved plot: {path}", file=status_out)

    if sweeps and not args.json and not args.read_back:
        from .sweep import format_sweep
        for sweep_result in sweeps:
            print(format_sweep(sweep_result))
    if break_evens and not args.json and not args.read_back:
        from .break_even import format_break_even
        for be_result in break_evens:
            print(format_break_even(be_result))

    if args.story:
        if det_result is None:
            print(
                "Note: --story needs the deterministic run; re-run without "
                "--no-deterministic to render the story package.",
                file=sys.stderr,
            )
        else:
            from .story_page import render_story_package

            try:
                package = render_story_package(
                    spec, det_result, mc_result, prior=prior,
                    out_dir=args.story,
                    command=f"uv run hde {args.config} --story {args.story}",
                    warnings=warnings,
                )
            except Exception as e:
                print(f"Error rendering story package: {e}", file=sys.stderr)
                return 1
            status_out = sys.stderr if (args.json or args.read_back) else sys.stdout
            for path in package["act_images"]:
                print(f"Saved plot: {path}", file=status_out)
            print(f"Story written: {package['report']}", file=status_out)
            print(f"Story written: {package['story']}", file=status_out)

    # LAST, so the lines to carry are the last thing on the screen. Under --json
    # stdout stays the document alone and `assumptions.read_back` carries them;
    # --quiet asked for one line and gets one, unless --read-back overrides.
    if read_back and (args.read_back or not (args.json or args.quiet)):
        from .serialization import READ_BACK_HEADER
        print(READ_BACK_HEADER if args.read_back else f"\n{READ_BACK_HEADER}")
        for line in read_back:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
