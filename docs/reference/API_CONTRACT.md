# API contract

The contract is emitted by the engine itself; this page only says where.
(Rewritten 2026-09-01 — the previous version documented the retired
four-argument engine and result classes that no longer exist.)

## Input

```bash
uv run hde --print-schema
```

One block per YAML section. Every key carries `required` (required when the
block is present), `note` (units, default, source), and — for the four
capital-structure keys — `required_if`, quoting the validator's own sentence:
an owned option declares `all_cash: true` OR the full mortgage block. The
`top_level` block lists every accepted top-level key and the rule that at
least one of `condo` / `house` / `rent` must be present. A key the parser does
not know is refused with a did-you-mean.

## Output

```bash
uv run hde <config.yaml> --json
```

| Key | What it is |
|---|---|
| `engine_version` | installed package version — the defaults registry changes verdicts across versions |
| `warnings` | coherence warnings + time-anchor violations, the same list the CLI prints to stderr |
| `assumptions` | `mode`, `years`, `discount_rate`, the text `lines` of the Assumptions block, `defaults_applied` (one entry per key the YAML omitted: `key`, `value`, `formatted`, `cite`, `kind`, `note` — how `value` relates to `anchor.value` when nominal mode composed it, else `null` — and the full `anchor` record), and `demographic_prior` (provenance block + `description` + cited `sources`) or `null` |
| `verdict` | `best`, `runner_up`, `margin_pv`, `margin_frac`, `monthly_equivalent`, `prob_best`, `decisive`, `rule`, `reason`, `mc_mean_best` — see the figure glossary |
| `deterministic` | per option `total_pv` + `breakdown` (keys in the glossary) + `cash_year1` / `principal_year1` / `appreciation_year1` (undiscounted year-1 cash, principal repaid and expected appreciation — the cash view beside the PV view), `affordability`, `market_scenario` |
| `monte_carlo` | per option `mean`/`std`/`p5`/`p50`/`p95`, `prob_<option>_cheapest`, `affordability_mc`, `market_scenario`; `null` under `--no-monte-carlo` |
| `sweeps` | only with `--sweep`: one entry per flag — `key`, `values`, per-point `rows` (`value`, `totals` per option, the verdict fields `best` / `runner_up` / `margin_pv` / `margin_frac` / `decisive` / `prob_best` / `mc_mean_best` / `reason`, `affordability` per option — `max_ratio` and `years_exceeding` — when an `income` block is present, or `error` when that point is refused) and `flips` (consecutive points whose cheapest option differs) plus `mc_mean_flips` (the same for `mc_mean_best`) |
| `break_evens` | only with `--break-even`: one entry per flag — `key`, the two `options`, the `bracket` asked for, `searched` (the accepted run(s) actually scanned), `refused` (only when the loader refused grid points: `count`, `values`, `reason`), `note` (only with a `market_scenario` prior: the prior does not move a deterministic threshold), `across` (only beside `--sweep`: per swept key, `rows` of `{value, break_evens, cheaper_throughout?, refused?}` — the threshold re-solved at every sweep point), `base_value`, `tie_band_fraction`, and `break_evens` (each: `sentence` — the threshold band-first in words, quote this shape; `value` where the deterministic totals cross, `cheaper_below` / `cheaper_above`, `tie_band` edges `[lo, hi]` — `null` when an edge lies outside the bracket); `cheaper_throughout` when there is no crossing |

Every figure's formula: `docs/reference/ARCHITECTURE.md` § Figure glossary.

## Provenance

```bash
uv run hde --print-anchors
```

The registry (`src/hde/anchors.py`): for every engine default its `value`,
`as_of`, `source`, `url`, `rationale`, `band`, `short_cite`, `retrieved_on`,
`kind` (`cited` / `reference` / `neutral` / `derivation`) and `replaces`.

## Library

Everything the CLI uses is exported from `hde`
(`src/hde/__init__.py`): `load_config` / `load_config_dict` → `ComparisonSpec`;
`compute_deterministic`, `run_monte_carlo`; `compute_verdict`;
`load_scenario_prior`; the serializers `det_to_dict`, `mc_to_dict`,
`verdict_to_dict`, `assumptions_to_dict`, `anchors_to_dict`; `all_warnings`.
(The MCP server that once wrapped these was removed 2026-09-01: the CLI plus
the repo-local skill is the only surface.)
