"""
Command-line interface for the housing decision engine.

Usage:
    hde <config.yaml> [options]
"""

import argparse
import datetime
import re
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
from .reporting import format_text_report, verdict_line
from .unpriced import unpriced_warnings

# A demographic prior enters the Monte Carlo only: a run that skips it shows
# the deterministic line alone, and says so rather than let the prior's
# presence in the echo read as its presence in the numbers (2026-09-04).
# `--decompose` bare vs `--decompose N`: a sentinel rather than a number, so
# "asked for it" and "asked for it at N paths" are never the same value. A bool
# would not do — `isinstance(True, int)` is True, which is exactly how a
# sentinel silently becomes a sample size.
_DECOMPOSE_AT_NUM_SIMS = object()

PRIOR_WITHOUT_MONTE_CARLO = (
    "market_scenario prior acts only in Monte Carlo — this run shows the "
    "deterministic line alone (the prior's drift is not in it)"
)


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
        nargs="?",
        const="full",
        default=None,
        choices=("full", "short"),
        metavar="{full,short}",
        help="Print ONLY the read-back block — the lines an answer must carry "
             "verbatim (exit code as the run). Bare or 'full': every [warning], "
             "the source classes the user did not state, the defaults applied, "
             "the decisiveness rule, the financing, purchase-cost, year-1 cash and "
             "other-cost lines, affordability, and any threshold or sweep lines. "
             "'short' (the gist): the [warning] lines, the source lines and the "
             "decisiveness rule alone, closed by one line counting what the full "
             "block adds. Give the config before this flag",
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
        "--refresh-plan",
        action="store_true",
        help="Print the refresh work order for every anchor whose source says "
             "when its figure changes: grouped by the release that publishes it, "
             "ranked by how soon it lapses, with the figure as quoted, the "
             "publisher and edition to look for, where to look, when the source "
             "was last checked and what was found — plus the steps of a correct "
             "refresh. Exits 3 if any figure has already lapsed",
    )

    parser.add_argument(
        "--refresh-plan-as-of",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Date --refresh-plan measures against (default: today). The only "
             "clock that surface reads",
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
             "--sweep years=5,10,20 or --sweep condo.value_growth_rate=0:0.04:5; a cost line "
             "by its name, --sweep 'house.other_recurring_costs.property_tax.annual_amount=3000,6000'; "
             "prints per-point verdicts and where the cheapest option flips; rides --json as 'sweeps'",
    )
    parser.add_argument(
        "--decompose",
        nargs="?",
        const=_DECOMPOSE_AT_NUM_SIMS,
        default=None,
        metavar="N",
        help="Which risk decides it. The spread register prices N futures of the "
             "block's own (N defaults to simulation.num_sims), and the level register "
             "the first min(N, 2000) of them. What each figure means: "
             "docs/reference/API_CONTRACT.md, the decomposition block",
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

    # `hde --decompose config.yaml`: an optional value takes the next token
    # whatever it is, so the config path arrives HERE and the positional is
    # left empty. A whole number is the path count; anything else, with no
    # config given, is the config and the flag was bare. With a config given
    # as well, it can only be a malformed count, and argparse's own error for
    # one is the answer.
    if isinstance(args.decompose, str):
        token = args.decompose
        if re.fullmatch(r"[+-]?[0-9]+", token):
            args.decompose = int(token)
        elif args.config is None:
            args.config, args.decompose = token, _DECOMPOSE_AT_NUM_SIMS
        elif re.fullmatch(r"[+-]?[0-9]+", str(args.config)):
            # `--decompose config.yaml 300`: the count landed where the config
            # goes. Naming the config as a bad count misdiagnoses it.
            parser.error(f"argument --decompose: the path count goes right after the "
                         f"flag — --decompose {args.config} {token}, or {token} "
                         f"--decompose {args.config} — and {token!r} is in its place")
        else:
            parser.error(f"argument --decompose: invalid int value: {token!r}")

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

    if args.refresh_plan:
        import datetime as _dt
        import json as _json
        from .serialization import refresh_plan
        if args.refresh_plan_as_of is None:
            as_of = _dt.date.today()
        else:
            try:
                as_of = _dt.date.fromisoformat(args.refresh_plan_as_of)
            except ValueError:
                print(f"Error: --refresh-plan-as-of must be an ISO date "
                      f"(YYYY-MM-DD), got {args.refresh_plan_as_of!r}", file=sys.stderr)
                return 1
        plan = refresh_plan(as_of)
        print(_json.dumps(plan, indent=2, ensure_ascii=False))
        # A figure that has lapsed is a registry the engine can no longer stand
        # behind, so the surface REFUSES rather than reporting success. A figure
        # still in force is information: a gate that went red for the three
        # months before an edition is published, with nothing to fetch, would be
        # a red that means nothing.
        if plan["lapsed_anchors"]:
            print(f"REFUSING: {plan['lapsed_anchors']} anchored figure(s) are past "
                  f"their validity date as of {plan['as_of']} — the registry states "
                  f"figures their own sources say have changed.", file=sys.stderr)
            return 3
        return 0

    if args.config is None:
        print("Error: config path required (or use --print-schema / --print-anchors "
              "/ --refresh-plan)", file=sys.stderr)
        return 1

    # --decompose's refusals that the FLAGS alone decide, taken before anything
    # is priced: each would otherwise run the whole Monte Carlo first and then
    # refuse, or — with --read-back — compute the decomposition and print none
    # of it, since stdout is then the read-back block alone.
    decompose_paths = None
    if args.decompose is not None:
        # The sample-size override is the ASSEMBLER's figure (it is consumed at
        # compute time); this surface only parses it, and refuses a value that
        # cannot be a path count rather than passing it on.
        decompose_paths = (None if args.decompose is _DECOMPOSE_AT_NUM_SIMS
                           else args.decompose)
        if decompose_paths is not None and decompose_paths < 1:
            print(f"Error: --decompose takes a path count of 1 or more, got "
                  f"{decompose_paths}", file=sys.stderr)
            return 1
        if args.no_deterministic:
            print("Error: --decompose needs the deterministic run — the block is "
                  "priced against the central case; re-run without "
                  "--no-deterministic", file=sys.stderr)
            return 1
        if args.read_back:
            print("Error: --decompose is not part of the read-back — --read-back "
                  "prints the read-back lines alone, so this run would price the "
                  "decomposition and show none of it. Run --decompose without "
                  "--read-back: the block prints in the text, or rides --json "
                  "as 'decomposition'", file=sys.stderr)
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
    # The raw mapping the spec came from: the sweeps and thresholds re-run the
    # loader on copies of it, and the financing line solves the 20%-down price
    # through the same loader (2026-09-04).
    import yaml as _yaml
    raw = _yaml.safe_load(config_path.read_text(encoding="utf-8"))

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

    # Warnings (audit U2 coherence + the time-anchor staleness guard + anchors
    # used past their validity date): surface, never refuse. stderr so --quiet
    # and piped stdout stay clean; the same list rides the --json document. The
    # wall clock is read here, at the edge; `raw` reaches the price ceiling.
    today = datetime.date.today()
    warnings = all_warnings(spec, prior, current_year=today.year, run_date=today, raw=raw)
    if args.no_monte_carlo and spec.market_scenario is not None:
        warnings.append(PRIOR_WITHOUT_MONTE_CARLO)
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

        # The dimensions this RUN does not price, measured on its own numbers
        # (docs/specs/2026-09-21-unpriced-dimensions.md §6: this channel, this
        # position — after the verdict, beside the decisiveness provenance).
        # Silent whenever nothing qualifies, which is the design's own guard
        # (§5): a line that cannot come out silent is a disclaimer, not a
        # measurement.
        for warning in unpriced_warnings(spec, det_result, raw):
            warnings.append(warning)
            print(f"[warning] {warning}", file=sys.stderr)

    # Which risk decides it (docs/specs/2026-09-22-which-risk-decides-it.md).
    # Silent unless asked: no flag, no stream built, no draw consumed (§8
    # case 1). The ESTIMATORS live behind one seam, `hde.decomposition_run`
    # (spec §0.1 item 17); this surface renders what that seam returns and
    # decides none of §8's refusals, which are judgments about data the
    # assembler is the only thing that sees.
    decomposition = None
    if args.decompose is not None:
        # The flag-only refusals (a path count below one, --no-deterministic,
        # --read-back) were taken before anything was priced, above.
        # A build that carries the surface without the estimators REFUSES here
        # rather than printing an empty block: a flag that comes out silent
        # because half the feature is missing is the cheap all-clear this repo
        # treats as the cardinal failure.
        try:
            from .decomposition_run import decompose
        except ImportError as e:
            # ONLY the seam's own absence is a refusal. An ImportError raised
            # from inside a landed `decomposition_run` is a real defect, and
            # reporting it as "not in this build" would be a wrong diagnosis
            # of someone else's bug.
            if getattr(e, "name", None) != "hde.decomposition_run":
                raise
            print("Error: --decompose needs the decomposition estimators "
                  "(hde.decomposition_run), which this build does not carry — the "
                  "surface is here, the registers are not", file=sys.stderr)
            return 1
        # `paths` is passed ONLY when the user gave one (§0.1 item 16).
        extra = {} if decompose_paths is None else {"paths": decompose_paths}
        try:
            decomposition = decompose(spec, det=det_result, mc=mc_result,
                                      verdict=verdict, raw=raw, **extra)
        except (ConfigValidationError, InputError, ScenarioPriorError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        # A check inside the block that cannot pass comes back as the block's
        # refusal (§0.1 item 58); nothing else is caught here, so an engine
        # defect is never printed as a failed check.

    # Parameter sweeps (flip points) — through the same loader and verdict rule.
    sweeps = []
    sweep_specs = []  # (key, values) pairs; --break-even re-solves at each
    if args.sweep:
        from .sweep import one_sided_sweep_warning, parse_sweep, run_sweep
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
            # A placeholder swept in one direction only tests half the guess.
            one_sided = one_sided_sweep_warning(raw, key, sweeps[-1]["values"])
            if one_sided is not None:
                warnings.append(one_sided)
                print(f"[warning] {one_sided}", file=sys.stderr)

    # Break-evens (threshold questions) — same loader, deterministic line.
    break_evens = []
    if args.break_even:
        from .break_even import parse_break_even, solve_break_even, solve_break_even_across
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
    read_back_kw = dict(warnings=warnings, verdict=verdict, det=det_result, prior=prior,
                        break_evens=break_evens, sweeps=sweeps, raw=raw)
    read_back = read_back_lines(spec, **read_back_kw)
    # The short block (2026-09-05): the gist shape's paste — warnings, source
    # lines, decisiveness, and one closing line counting what the full block
    # adds. Both ride --json; --read-back short prints this one alone.
    read_back_short = read_back_lines(spec, short=True, **read_back_kw)

    # Output results. --read-back keeps stdout to the block alone, so a caller
    # that wants only the lines to carry does not have to parse them out.
    if args.json and not args.read_back:
        import json as _json
        from .serialization import (
            assumptions_to_dict, det_to_dict, engine_version, mc_to_dict,
            verdict_to_dict,
        )
        assumptions = assumptions_to_dict(spec, prior, raw)
        assumptions["read_back"] = read_back
        assumptions["read_back_short"] = read_back_short
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
        if args.decompose is not None:
            from .serialization import decomposition_to_dict
            doc["decomposition"] = decomposition_to_dict(decomposition)
        print(_json.dumps(doc, indent=2, ensure_ascii=False))
        # plots/story still render below when requested
    elif args.read_back:
        pass  # the block below is the whole of stdout
    elif args.quiet:
        # Print summary line only: the totals, then the report's own verdict
        # sentence (three states; a disagreement names both figures).
        if det_result is not None:
            parts = []
            if det_result.condo is not None:
                parts.append(f"Condo: ${det_result.condo.total_pv:,.0f}")
            if det_result.house is not None:
                parts.append(f"House: ${det_result.house.total_pv:,.0f}")
            if det_result.rent is not None:
                parts.append(f"Rent: ${det_result.rent.total_pv:,.0f}")
            sentence = verdict_line(verdict)
            print("  ".join(parts) + (f" | {sentence}" if sentence else ""))
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
                                        spec=spec, prior=prior, raw=raw)
            print(report)
        elif mc_result is not None:
            # MC-only mode: build a minimal det result placeholder to satisfy signature
            from .models import ComparisonDeterministicResult
            empty_det = ComparisonDeterministicResult()
            report = format_text_report(empty_det, mc_result, spec.simulation, spec.economic,
                                        spec=spec, prior=prior, raw=raw)
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
            # (round-6 evaluation: a saved `--story --json` output did not parse).
            status_out = sys.stderr if (args.json or args.read_back) else sys.stdout
            for path in saved:
                print(f"Saved plot: {path}", file=status_out)

    # The block goes under the verdict the report just printed, and before the
    # threshold lines, in the same channel the other opt-in surfaces use (a
    # flag the user asked for is not suppressed by -q, exactly as --sweep is
    # not). Silence is the empty string, so a refusal is the only thing that
    # can print here besides the block.
    if decomposition is not None and not args.json and not args.read_back:
        from .decomposition_text import format_decomposition
        rendered = format_decomposition(decomposition)
        if rendered:
            print(f"\n{rendered}")

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
        for line in (read_back_short if args.read_back == "short" else read_back):
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
