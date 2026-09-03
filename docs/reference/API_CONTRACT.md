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
| `assumptions` | `mode`, `years`, `discount_rate`, the text `lines` of the Assumptions block (the `<option> financing:` line carries the down payment, its share of price, the distance to the 20% mortgage-insurance line and the loan-to-value; with `cash_available` it leads with the netting `cash − purchase_costs = down payment`), `defaults_applied` (one entry per key the YAML omitted: `key`, `value`, `formatted`, `cite`, `kind`, `note` — how `value` relates to `anchor.value` when nominal mode composed it, else `null` — and the full `anchor` record), `reference_matches` (one entry per owned-option `other_recurring_costs` line naming a property tax or home-insurance premium: `option`, `cost_name`, `annual_amount`, `family`, `implied_rate` — the amount as a fraction of `initial_value`, `null` for insurance — and `matches`, the full anchor record of every jurisdiction whose published figure equals it; an empty `matches` means no source agrees, which is reported rather than hidden), and `demographic_prior` (provenance block + `description` + cited `sources`) or `null` |
| `verdict` | `best`, `runner_up`, `margin_pv`, `margin_frac`, `monthly_equivalent`, `prob_best`, `decisive`, `rule`, `reason`, `mc_mean_best` — see the figure glossary |
| `deterministic` | per option `total_pv` + `breakdown` (keys in the glossary) + `cash_year1` / `principal_year1` / `appreciation_year1` (undiscounted year-1 cash, principal repaid and expected appreciation — the cash view beside the PV view), `affordability`, `market_scenario` |
| `monte_carlo` | per option `mean`/`std`/`p5`/`p50`/`p95`, `prob_<option>_cheapest`, `affordability_mc`, `market_scenario`; `null` under `--no-monte-carlo` |
| `sweeps` | only with `--sweep`: one entry per flag — `key`, `values` (the DISTINCT points actually run), per-point `rows` (`value`, `totals` per option, the verdict fields `best` / `runner_up` / `margin_pv` / `margin_frac` / `decisive` / `prob_best` / `mc_mean_best` / `reason`, `affordability` per option — `max_ratio` and `years_exceeding` — when an `income` block is present, or `error` when that point is refused), `flips` (consecutive points whose cheapest option differs) plus `mc_mean_flips` (the same for `mc_mean_best`), and `note` (present when either applies, `; `-joined: duplicate grid points collapsed — an integer key rounds `7:8:5` to five points and two values; or the price-scan coherence note below) |
| `break_evens` | only with `--break-even`: one entry per flag — `key`, the two `options`, the `bracket` asked for, `searched` (the accepted run(s) actually scanned), `refused` (only when the loader refused grid points: `count`, `values`, `reason`), `note` (present when either applies, `; `-joined: a `market_scenario` prior does not move a deterministic threshold; or the price-scan coherence note below), `across` (only beside `--sweep`: per swept key, `rows` of `{value, break_evens, cheaper_throughout?, refused?}` — the threshold re-solved at every sweep point; each row's `break_evens` carry `affordability` too, though the text output prints only their one-line sentences), `base_value`, `tie_band_fraction`, and `break_evens` (each: `sentence` — the threshold band-first in words, quote this shape; `value` where the deterministic totals cross, `cheaper_below` / `cheaper_above`, `tie_band` edges `[lo, hi]` — `null` when an edge lies outside the bracket; `affordability` — `threshold`, `value` and `tie_band` mirroring those keys, each holding per-option `{max_ratio, years_exceeding}` — or `null` without an `income` block); `cheaper_throughout` when there is no crossing |

**The price-scan coherence note.** A `--break-even` or `--sweep` that moves an
owned option's `initial_value` re-derives everything the loader derives from
the price and nothing that is typed in dollars. When a price-proportional
input is stated in dollars (`purchase_costs`, `financed_purchase_costs`, an
`other_recurring_costs` line named for tax or insurance) the block's `note`
names each one with its value, the seed price it was sized for, and the
direction of the bias — the band moves once they scale. `property_tax_rate`
and `purchase_costs_rate` are the rate alternatives that scale
(`--print-schema`).

Every figure's formula: `docs/reference/ARCHITECTURE.md` § Figure glossary.

## Provenance

```bash
uv run hde --print-anchors
```

The registry (`src/hde/anchors.py`): for every engine default its `value`,
`as_of`, `source`, `url`, `rationale`, `band`, `short_cite`, `quoted`, `unit`,
`retrieved_on`, `kind` (`cited` / `reference` / `neutral` / `derivation` /
`unsourced`) and `replaces`.

The registry also carries **jurisdiction reference tables** — keys
`property_tax.<municipality>` and `home_insurance.<province>` — which are *not*
engine defaults: nothing falls back to them and the engine never applies one.
Each carries two fields the defaults do not need:

| field | meaning |
|---|---|
| `quoted` | the figure exactly as the source prints it, in the source's own notation |
| `unit` | the base the figure is stated on — for a municipal rate, always **assessed** value, which is not market value |

`kind: "unsourced"` is the `source: none` state: `value` is `null`, `url`
records what was tried, and `short_cite` reads `source: none`. It is the only
kind permitted to carry no figure, and no other kind may serialize a null
`value`.

## Library

Everything the CLI uses is exported from `hde`
(`src/hde/__init__.py`): `load_config` / `load_config_dict` → `ComparisonSpec`;
`compute_deterministic`, `run_monte_carlo`; `compute_verdict`;
`load_scenario_prior`; the serializers `det_to_dict`, `mc_to_dict`,
`verdict_to_dict`, `assumptions_to_dict`, `anchors_to_dict`; `all_warnings`.
(The MCP server that once wrapped these was removed 2026-09-01: the CLI plus
the repo-local skill is the only surface.)
