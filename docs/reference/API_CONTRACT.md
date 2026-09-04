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

The optional top-level `sources:` block records WHO stated each value: a
mapping from a dotted key the config sets (`rent.monthly_rent`,
`simulation.investment_return_vol`, `house.events` for a whole list) to `user`,
`assistant` (a value typed on the user's behalf) or `anchor:<name>` from
`--print-anchors` — and `anchor:<name>+<name>` when the value is the SUM of two
published figures (`anchor:property_tax.laval+school_tax.qc`: a Québec owner's
rate is the municipal rate plus the province's school rate), which echoes both.
It affects no computation — it splits the assumption echo by source class and
arms one warning. A key the config does not set, a value outside those forms, an
unknown anchor name, a `source: none` anchor (it holds no figure), and an anchor
whose figure is not the number the config states all refuse at load: the value
must equal the anchor's — or the sum, or a declared `restatement` of it — within
the same equality window the read-back matcher uses.

## Output

```bash
uv run hde <config.yaml> --json
```

| Key | What it is |
|---|---|
| `engine_version` | installed package version — the defaults registry changes verdicts across versions |
| `warnings` | coherence warnings + time-anchor violations + affordability breaches + the decisiveness-provenance warning (`decisiveness rests on uncertainty inputs the user did not state: …` — fires only under the `mc_floor` verdict rule, names every uncertainty input that is `assistant` or unattributed with its value, and closes with what the deterministic line alone says and whether that margin clears the tie band), the same list the CLI prints to stderr |
| `assumptions` | `mode`, `years`, `discount_rate`, the text `lines` of the Assumptions block (the `<option> financing:` line carries the down payment, its share of price, the distance to the 20% mortgage-insurance line and the loan-to-value; with `cash_available` it leads with the netting `cash − purchase_costs = down payment`; with `mortgage_insurance` active it adds an `insured:` clause — the tier, the financed premium, the provincial tax paid in cash and the resulting loan and loan-to-value — and the loan-to-value it quotes is the tier basis, before the premium; an owned option that priced a transfer tax gets its own `<option> purchase costs:` line — the duty, the schedule or schedules that charged it, the first-time-buyer rebate applied (or the maximum NOT applied, or the fact that none is anchored), and the decomposition of the `purchase_costs` figure the financing line quotes, so the two lines reconcile; it is a separate line because an all-cash purchase has no financing line and pays the tax all the same), `defaults_applied` (one entry per key the YAML omitted: `key`, `value`, `formatted`, `cite`, `kind`, `note` — how `value` relates to `anchor.value` when nominal mode composed it, else `null` — and the full `anchor` record), `reference_matches` (one entry per owned-option `other_recurring_costs` line naming a property tax or home-insurance premium: `option`, `cost_name`, `annual_amount`, `family`, `implied_rate` — the amount as a fraction of `initial_value`, `null` for insurance — `matches`, the full anchor record of every anchor cited for the line, and `citations`, how they combine: one `{kind, anchors, total}` record per claim, `kind` either `single` (one published figure equals the line) or `sum` (a municipal rate plus its province's school rate — the bill a Québec owner actually pays), `anchors` the registry names in citation order and `total` the published figure the line was matched against. Both lists empty means no source agrees, which is reported rather than hidden), and `demographic_prior` (provenance block + `description` + cited `sources`) or `null`, and `sources` — the source-class echo: `declared` (false when the config carries no `sources:` block, and then the lines say so in one sentence), `user` / `assistant` / `unattributed` (each a list of `{key, value, formatted}`, `formatted` in the config's own units) and `anchor` (a `{key: anchor name}` mapping) — and `read_back`, the block below (also `anchor-sourced:` lines, so a cited figure travels with its citation) |
| `verdict` | `best`, `runner_up`, `margin_pv`, `margin_frac`, `monthly_equivalent`, `prob_best`, `decisive`, `rule`, `reason`, `mc_mean_best` — see the figure glossary |
| `deterministic` | per option `total_pv` + `breakdown` (keys in the glossary) + `cash_year1` / `principal_year1` / `appreciation_year1` (undiscounted year-1 cash, principal repaid and expected appreciation — the cash view beside the PV view), `affordability`, `market_scenario` |
| `monte_carlo` | per option `mean`/`std`/`p5`/`p50`/`p95`, `prob_<option>_cheapest`, `affordability_mc`, `market_scenario`; `null` under `--no-monte-carlo` |
| `sweeps` | only with `--sweep`: one entry per flag — `key`, `values` (the DISTINCT points actually run), per-point `rows` (`value`, `totals` per option, the verdict fields `best` / `runner_up` / `margin_pv` / `margin_frac` / `decisive` / `prob_best` / `mc_mean_best` / `reason`, the Monte Carlo majority `mc_best` and its `mc_prob_best` — `decisive` keys to the DETERMINISTIC winner and `prob_best` is that winner's probability, so a row can read `best: rent` / `decisive: false` / `prob_best: 0.34` while the majority and the mean favour the house, `affordability` per option — `max_ratio` and `years_exceeding` — when an `income` block is present, or `error` when that point is refused), `flips` (consecutive points whose cheapest option differs) plus `mc_mean_flips` (the same for `mc_mean_best`) and `mc_majority_flips` (the same for `mc_best`; the text block prints a `majority flip:` line only where it differs from the deterministic `flip:`), and `note` (present when either applies, `; `-joined: duplicate grid points collapsed — an integer key rounds `7:8:5` to five points and two values; or the price-scan coherence note below) |
| `break_evens` | only with `--break-even`: one entry per flag — `key`, the two `options`, the `bracket` asked for, `searched` (the accepted run(s) actually scanned), `refused` (only when the loader refused grid points: `count`, `values`, `reason`), `note` (`; `-joined, present when any applies: a `market_scenario` prior does not move a deterministic threshold; where that prior's own reference drift sits against the tie band on a `<owned>.value_growth_rate` threshold — INSIDE / BELOW / ABOVE, with the reminder that the drift is added to `value_growth_rate` in the Monte Carlo rather than substituted for it; a crossing that is a mortgage-insurance cliff (the 20%-down line crossed or a premium tier changed between the two sides of it — a step, whose "tie band" is the step's width) or that borders a refused value; or the price-scan coherence note below), `across` (only beside `--sweep`: per swept key, `rows` of `{value, break_evens, cheaper_throughout?, refused?}` — the threshold re-solved at every sweep point; each row's `break_evens` carry `affordability` too, though the text output prints only their one-line sentences), `base_value`, `tie_band_fraction`, and `break_evens` (each: `sentence` — the threshold band-first in words, quote this shape; `value` where the deterministic totals cross, `cheaper_below` / `cheaper_above`, `tie_band` edges `[lo, hi]` — `null` when an edge lies outside the bracket; `affordability` — `threshold`, `value` and `tie_band` mirroring those keys, each holding per-option `{max_ratio, years_exceeding}` — or `null` without an `income` block); `cheaper_throughout` when there is no crossing |

**The read-back block (`assumptions.read_back`, `--read-back`).** The lines an
answer must carry, assembled by the engine in one fixed order: every
`[warning]`; the source classes the user did not state (`assistant-typed:`,
`unattributed:`, or the one `sources: none declared …` line) — never
`user-stated:`, since the user knows their own numbers; the `decisiveness:`
line; each `<option> financing:` line; each `<option> other costs:` line with
its citation or `no anchor match`; the affordability summary when an `income`
block is present; each break-even's `sentence` and the block's `note`; each
sweep's `flip:` / `mean flip:` / `majority flip:` lines. Every line is built by
the same function that prints it elsewhere, so the block repeats rather than
paraphrases.

```bash
uv run hde <config.yaml> --read-back     # the block alone on stdout, exit code as the run
```

In text output the block prints LAST under `READ-BACK — carry these lines into
any answer, verbatim:`; under `--json` it rides `assumptions.read_back` and the
text block is suppressed, so stdout stays one document. `--quiet` prints its one
line unless `--read-back` is passed too.

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
`province`, `retrieved_on`, `kind` (`cited` / `reference` / `neutral` /
`derivation` / `unsourced`), `restatements` and `replaces`.

The registry also carries **reference tables** — keys
`property_tax.<municipality>`, `school_tax.<province>`,
`home_insurance.<province>` and `mortgage_rate.posted_5y` — which are *not*
engine defaults: nothing falls back to them and the engine never applies one.
They are published figures a user picks from, cited when the user's own number
IS one. Each carries fields the defaults do not need:

| field | meaning |
|---|---|
| `quoted` | the figure exactly as the source prints it, in the source's own notation |
| `unit` | the base the figure is stated on — for a municipal rate, always **assessed** value, which is not market value; for `mortgage_rate.posted_5y`, a POSTED rate (a list price: contracted rates run lower, so it is a ceiling) quoted semi-annually compounded |
| `province` | which province the entry is in — required for `property_tax.*` and `school_tax.*`, because a municipal rate is summed only with its OWN province's school rate |
| `restatements` | the same published figure in another convention, each `{value, why}` — 6.09% posted and 6.1827% effective annual are one figure, so a config stating either may cite the anchor |

`kind: "unsourced"` is the `source: none` state: `value` is `null`, `url`
records what was tried, and `short_cite` reads `source: none`. It is the only
kind permitted to carry no figure, and no other kind may serialize a null
`value`.

The `land_transfer_tax.*` entries are the transfer-tax schedules the engine
applies: one entry per bracket, whose NAME carries the threshold
(`land_transfer_tax.montreal.to_552300` = 1.5%, `…over_3113000` = 4% for the
uncapped top band), plus the first-time-buyer maximums
(`ontario.first_time_buyer_refund_max` $4,000, `toronto.first_time_buyer_rebate_max`
$4,475). Neither Québec schedule has an anchored first-time-buyer rebate, so both
carry a `source: none` entry naming what was tried. `quoted` holds each bracket
exactly as the source prints it and `unit` names the base it is levied on.

The `mortgage_insurance.*` entries are the premium schedule the engine applies:
one entry per CMHC loan-to-value band (`premium_rate.ltv_80_85` = 2.80% and so
on), `max_ltv` (95%), `amortization_surcharge` (0.20% beyond 25 years) and the
provincial taxes on the premium (`premium_tax_rate.qc` 9%, `premium_tax_rate.on`
8%). Saskatchewan taxes the premium too but its rate is NOT anchored, so a
`province: SK` config is refused with a pointer to an explicit schedule rather
than charged 0%.

## Library

Everything the CLI uses is exported from `hde`
(`src/hde/__init__.py`): `load_config` / `load_config_dict` → `ComparisonSpec`;
`compute_deterministic`, `run_monte_carlo`; `compute_verdict`;
`load_scenario_prior`; the serializers `det_to_dict`, `mc_to_dict`,
`verdict_to_dict`, `assumptions_to_dict`, `anchors_to_dict`, `read_back_lines`;
`all_warnings`.
(The MCP server that once wrapped these was removed 2026-09-01: the CLI plus
the repo-local skill is the only surface.)
