"""
Command-line interface for the housing decision engine.

Usage:
    hde <config.yaml> [options]
"""

import argparse
import sys
from pathlib import Path

from .config import load_config, coherence_warnings, ConfigValidationError
from .deterministic import compute_deterministic
from .market_scenario import ScenarioPriorError
from .models import InputError
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
        help="Render the five-act decision story into DIR after the run",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full result document as JSON (agent-native; same "
             "serializers the MCP layer uses)",
    )

    parser.add_argument(
        "--print-schema",
        action="store_true",
        help="Print the input contract (sections, keys, required, notes) and exit",
    )

    parser.add_argument(
        "--story",
        type=str,
        default=None,
        metavar="DIR",
        help="Write the full story package into DIR: five-act plots, "
             "text report, and a STORY.md one-pager",
    )

    args = parser.parse_args()

    if args.print_schema:
        import json as _json
        from .input_schema import input_schema
        print(_json.dumps(input_schema(), indent=2))
        return 0

    if args.config is None:
        print("Error: config path required (or use --print-schema)", file=sys.stderr)
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

    # Coherence warnings (audit U2): surface, never refuse. stderr so --quiet
    # and piped stdout stay clean.
    for warning in coherence_warnings(spec):
        print(f"[warning] {warning}", file=sys.stderr)

    # Run analysis — typed refusals (bad prior file, mode composition, direct-
    # construction violations) exit cleanly with "Error: <msg>", no traceback.
    det_result = None
    mc_result = None

    try:
        if not args.no_deterministic:
            det_result = compute_deterministic(spec)

        if not args.no_monte_carlo:
            mc_result = run_monte_carlo(spec)
    except (ConfigValidationError, InputError, ScenarioPriorError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Output results
    if args.json:
        import json as _json
        from .serialization import det_to_dict, mc_to_dict
        doc = {
            "warnings": coherence_warnings(spec),
            "deterministic": det_to_dict(det_result) if det_result is not None else None,
            "monte_carlo": mc_to_dict(mc_result) if mc_result is not None else None,
        }
        print(_json.dumps(doc, indent=2))
        # plots/story still render below when requested
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
            report = format_text_report(det_result, mc_result, spec.simulation, spec.economic, spec=spec)
            print(report)
        elif mc_result is not None:
            # MC-only mode: build a minimal det result placeholder to satisfy signature
            from .models import ComparisonDeterministicResult
            empty_det = ComparisonDeterministicResult()
            report = format_text_report(empty_det, mc_result, spec.simulation, spec.economic, spec=spec)
            print(report)

    if args.plots:
        if det_result is None:
            print(
                "Note: --plots needs the deterministic run; re-run without "
                "--no-deterministic to render the story plots.",
                file=sys.stderr,
            )
        else:
            from .monte_carlo import _load_prior_if_any
            from .story_plots import render_decision_story

            prior = _load_prior_if_any(spec)
            try:
                saved = render_decision_story(
                    spec, det_result, mc_result, prior=prior, out_dir=args.plots,
                )
            except Exception as e:
                print(f"Error rendering story plots: {e}", file=sys.stderr)
                return 1
            for path in saved:
                print(f"Saved plot: {path}")

    if args.story:
        if det_result is None:
            print(
                "Note: --story needs the deterministic run; re-run without "
                "--no-deterministic to render the story package.",
                file=sys.stderr,
            )
        else:
            from .monte_carlo import _load_prior_if_any
            from .story_page import render_story_package

            prior = _load_prior_if_any(spec)
            try:
                package = render_story_package(
                    spec, det_result, mc_result, prior=prior,
                    out_dir=args.story,
                    command=f"uv run hde {args.config} --story {args.story}",
                )
            except Exception as e:
                print(f"Error rendering story package: {e}", file=sys.stderr)
                return 1
            for path in package["act images"]:
                print(f"Saved plot: {path}")
            print(f"Story written: {package['report']}")
            print(f"Story written: {package['story']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
