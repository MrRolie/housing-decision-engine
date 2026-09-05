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

An `other_recurring_costs` line is declared by NAME:
`<option>.other_recurring_costs.<line name>.annual_amount` (and
`.escalation_rate`) — `house.other_recurring_costs.home_insurance.annual_amount:
anchor:home_insurance.qc` on an $813 line, or `anchor:property_tax.laval` on a
dollar tax line, which is compared as amount ÷ `initial_value` (the read-back's
own probe, so a line the `<option> other costs:` line cites is a line `sources:`
accepts, and a line it does not cite is refused). The named form echoes under
the same dotted name; once a line of a list is named, that list is echoed per
leaf — the declared leaves with their class, the rest `unattributed` — and the
bare list key only when it too was declared. The bare key
`house.other_recurring_costs` stays `user` | `assistant` only (the anchor form
is refused with a pointer to the named form); an unknown line name is refused
naming the lines that exist, and a name two lines share cannot be declared.

## Output

```bash
uv run hde <config.yaml> --json
```

| Key | What it is |
|---|---|
| `engine_version` | installed package version — the defaults registry changes verdicts across versions |
| `warnings` | coherence warnings + time-anchor violations + affordability breaches + the decisiveness-provenance warning (`decisiveness rests on uncertainty inputs the user did not state: …` — fires only under the `mc_floor` verdict rule, names every uncertainty input that is `assistant` or unattributed with its value, and closes with what the deterministic line alone says and whether that margin clears the tie band), the same list the CLI prints to stderr; also (2026-09-04) the prior-without-Monte-Carlo warning — `market_scenario prior acts only in Monte Carlo — this run shows the deterministic line alone (the prior's drift is not in it)`, on `--no-monte-carlo` with a `market_scenario` block, with or without sweeps — and the one-sided sweep warning — `sweep of <key> covers only values ABOVE\|BELOW the placeholder <base>; the other direction is untested`, when a `--sweep` over a key declared `assistant` in `sources:` lies entirely on one side of the config's value |
| `assumptions` | `mode`, `years`, `discount_rate` (the rate in use: in nominal mode the REAL figure stated — typed or the anchored default — composed with `inflation_rate`, `(1 + real)(1 + π) − 1`, like every other rate; `discount_rate_note` says so in one line, `composed at parse: (1 + 3.5% real)(1 + 2.5% inflation_rate) − 1 = 6.09% nominal`, `null` in real mode), the text `lines` of the Assumptions block (the `mode:` line names both figures in nominal mode — `discount_rate 3.5% real → 6.1% nominal (incl. 2.5% inflation)`, `default` inserted when the anchor was used; the `<option> financing:` line carries the down payment, its share of price, the distance to the 20% mortgage-insurance line and the loan-to-value; with `cash_available` it leads with the netting `cash − purchase_costs = down payment` and closes with the price at which that pile stops covering 20% down — `(cash − purchase_costs) ÷ 20%`, with the `purchase_costs` figure it holds fixed; with `mortgage_insurance` active it adds an `insured:` clause — the tier, the financed premium, the provincial tax paid in cash and the resulting loan and loan-to-value — and the loan-to-value it quotes is the tier basis, before the premium; an owned option that priced a transfer tax gets its own `<option> purchase costs:` line — the duty, the schedule or schedules that charged it, the first-time-buyer rebate applied (or the maximum NOT applied, or the fact that none is anchored), and the decomposition of the `purchase_costs` figure the financing line quotes, so the two lines reconcile; it is a separate line because an all-cash purchase has no financing line and pays the tax all the same), `defaults_applied` (one entry per key the YAML omitted: `key`, `value`, `formatted`, `cite`, `kind`, `note` — how `value` relates to `anchor.value` when nominal mode composed it, else `null` — and the full `anchor` record), `reference_matches` (one entry per owned-option `other_recurring_costs` line naming a property tax or home-insurance premium: `option`, `cost_name`, `annual_amount`, `family`, `implied_rate` — the amount as a fraction of `initial_value`, `null` for insurance — `matches`, the full anchor record of every anchor cited for the line, and `citations`, how they combine: one `{kind, anchors, total}` record per claim, `kind` either `single` (one published figure equals the line) or `sum` (a municipal rate plus its province's school rate — the bill a Québec owner actually pays), `anchors` the registry names in citation order and `total` the published figure the line was matched against. Both lists empty means no source agrees, which is reported rather than hidden), and `demographic_prior` (provenance block + `description` + cited `sources`) or `null`, and `sources` — the source-class echo: `declared` (false when the config carries no `sources:` block, and then the lines say so in one sentence), `user` / `assistant` / `unattributed` / `sweep` (each a list of `{key, value, formatted}`, `formatted` in the config's own units; `sweep` is non-empty only in the document of a grid point whose key a `--sweep` or `--break-even` moved, and its line reads `swept: <key>=<value>`) and `anchor` (a `{key: anchor name}` mapping) — and `read_back`, the block below (also `anchor-sourced:` lines, so a cited figure travels with its citation). On the CLI's surfaces — the text report, `--json` and the read-back — the financing line's 20%-down price is solved through the loader (2026-09-04), so a `purchase_costs_rate`, a `land_transfer_tax: auto` schedule and the premium tax are re-derived along the price and the clause reads `(purchase_costs $Y at that price; above it the mortgage is insured)`; a surface holding the spec alone keeps the seed figure and says `purchase_costs held at $Y`. Beside `read_back` rides `read_back_short` (2026-09-05, the gist shape): the `[warning]` lines, the source lines and the `decisiveness:` line of `read_back` — a strict subsequence of it, in its order — closed by one engine line counting the lines the full block adds and naming their sections, `full read-back: <n> more lines (defaults applied, financing, year-1 cash, …) — rerun with --read-back full` (absent when nothing was left out); `--read-back short` prints it alone |
| `verdict` | `best`, `runner_up`, `margin_pv`, `margin_frac`, `monthly_equivalent`, `prob_best`, `decisive`, `state`, `rule`, `reason`, `mc_mean_best`, `mc_best`, `mc_prob_best` — see the figure glossary. `state` (2026-09-04) is one of `option` (`best` wins, decisive), `tie` (not decisive; the Monte Carlo majority, when there is one, is `best` itself) or `disagreement` (the deterministic central case and the Monte Carlo majority favour different options: `decisive` is false and `reason` carries both figures — `best guess says rent by $6,517 (1.9% of rent PV); most futures say house (60% cheapest) — the two disagree, not decisive [hde verdict rule]`). `best` is the deterministic winner in every state; `mc_best` / `mc_prob_best` are the majority's option and how often it is cheapest, `null` without Monte Carlo or on a single-path run. The text report's verdict line and the `-q` summary line print the same three states (`Cheapest: …` / `Too close to call: …` / `Best guess says Rent by $6,517 (1.9%) vs House; most futures say House (60% cheapest) — the two disagree, not decisive`) |
| `deterministic` | per option `total_pv` + `breakdown` (keys in the glossary) + `cash_year1` / `principal_year1` / `appreciation_year1` (undiscounted year-1 cash, principal repaid and expected appreciation — the cash view beside the PV view), `affordability`, `market_scenario` |
| `monte_carlo` | per option `mean`/`std`/`p5`/`p50`/`p95`, `prob_<option>_cheapest`, `affordability_mc`, `market_scenario`; `null` under `--no-monte-carlo` |
| `sweeps` | only with `--sweep`: one entry per flag — `key`, `values` (the DISTINCT points actually run), per-point `rows` (`value`, `totals` per option, the verdict fields `best` / `runner_up` / `margin_pv` / `margin_frac` / `decisive` / `state` / `prob_best` / `mc_mean_best` / `reason`, the Monte Carlo majority `mc_best` and its `mc_prob_best` (the verdict's own) — `best` is the DETERMINISTIC winner and `prob_best` that winner's probability, so a row can read `best: rent` / `prob_best: 0.34` while the majority favours the house: that row's `state` is `disagreement` and its `decisive` is false, `affordability` per option — `max_ratio` and `years_exceeding` — when an `income` block is present, or `error` when that point is refused), `flips` (consecutive points whose cheapest option differs) plus `mc_mean_flips` (the same for `mc_mean_best`) and `mc_majority_flips` (the same for `mc_best`; the text block prints a `majority flip:` line only where it differs from the deterministic `flip:`), and `note` (present when either applies, `; `-joined: duplicate grid points collapsed — an integer key rounds `7:8:5` to five points and two values; or the price-scan coherence note below). Each row also carries (2026-09-04) `sentence` — the read-back's one line for that point, `<key>=<v>: best <opt> by <margin$> (<pct>% of <opt> PV)[, P(best) <p>%[ (at the floor)]][, insured <opt> <tier>%][, affordability <opt> max <r>% breaches years […]]`, only the clauses whose data the run has (`at the floor` marks a probability EQUAL to the 65% floor: decisive by ≥, with nothing to spare; the text table's decisive column prints `True (mc_floor, at the floor)` there; on a `disagreement` point the verdict clause reads `best guess <opt> by <margin$> (<pct>% of <opt> PV), most futures <other> (<p>%) — disagree` instead, the other clauses unchanged, and the table's decisive column prints `False (mc_floor, disagree: house 60%)`) — and `insured` (`{option: premium rate}` for every owned option whose derived mortgage insurance is required at that point); the sweep carries `base_value` (the key's value in the YAML, or `null`). A `sources:` declaration on the swept key is lifted at every grid point — its echo class there is `sweep` — rather than re-validated against an anchor's figure; the base run still validates it |
| `break_evens` | only with `--break-even`: one entry per flag — `key`, the two `options`, the `bracket` asked for, `searched` (the accepted run(s) actually scanned), `refused` (only when the loader refused grid points: `count`, `values`, `reason`), `note` (`; `-joined, present when any applies: a `market_scenario` prior does not move a deterministic threshold; where that prior's own reference drift sits against the tie band on a `<owned>.value_growth_rate` threshold — INSIDE / BELOW / ABOVE, with the reminder that the drift is added to `value_growth_rate` in the Monte Carlo rather than substituted for it; a crossing OR EITHER BAND EDGE that is a mortgage-insurance cliff (the 20%-down line crossed or a premium tier changed between the two sides of that point — a step, whose "tie band" is the step's width; the clause names which point jumped, and a point that is both the crossing and an edge is said once) or that borders a refused value; or the price-scan coherence note below), `across` (only beside `--sweep`: per swept key, `rows` of `{value, break_evens, cheaper_throughout?, refused?}` — the threshold re-solved at every sweep point; each row prints as ONE line carrying its sentence(s), what the config refused, and — with an `income` block — the `affordability` its `break_evens` hold, at the crossing and both band edges), `base_value`, `tie_band_fraction`, and `break_evens` (each: `sentence` — the threshold band-first in words, quote this shape; `value` where the deterministic totals cross, `cheaper_below` / `cheaper_above`, `tie_band` edges `[lo, hi]` — `null` when an edge lies outside the bracket; `affordability` — `threshold`, `value` and `tie_band` mirroring those keys, each holding per-option `{max_ratio, years_exceeding}` — or `null` without an `income` block); `cheaper_throughout` when there is no crossing, beside `no_crossing` (2026-09-04): `lo` / `hi` (the searched bounds), `cheaper`, `narrows_toward` (`low` or `high` — the end where the gap is smaller) and `widen` (the bracket to try next, one width further out on that side, or `null` when that end is one the config refuses beyond); the line reads `no crossing between <lo> and <hi>: <opt> is cheaper at both ends — widen with --break-even <key>=<lo'>:<hi'>`, on the base solve and on every `across` row (an `across` block also carries the sweep key's `base_value`). The `sentence` closes with `(crossing <v>)` alone: the band rule is stated once, in the block's header line, and `tie_band_fraction` carries the figure. The `note` also names a mortgage-insurance step strictly INSIDE the tie band — neither the crossing nor an edge — as `… lies inside the tie band, at <v> — the gap steps there; the band is not one smooth range of near-ties` |

**The read-back block (`assumptions.read_back`, `--read-back`).** The lines an
answer must carry, assembled by the engine in one fixed order: every
`[warning]`; the source classes the user did not state (`assistant-typed:`,
`unattributed:`, or the one `sources: none declared …` line) — never
`user-stated:`, since the user knows their own numbers; the `defaults applied:`
line, so the numbers the ENGINE chose are named with their citations; in
nominal mode the `mode:` line — the REAL discount rate stated (typed or the
default) and the nominal rate composed from it, since the rate in use is then
the engine's composition; the `decisiveness:` line; each `<option> financing:` line and each `<option>
purchase costs:` line; the `Year-1 cash` block (both sides in $/yr and $/mo,
the principal repaid, the appreciation that is not cash) beside the PV view;
each `<option> other costs:` line with its citation or `no anchor match`; the
affordability summary when an `income` block is present; each break-even's
`sentence`, then — beside `--sweep` — the same threshold re-solved at every
sweep point, one line each as `break-even <key> at <sweep key>=<value>: …`
carrying the affordability at the crossing and the band edges where an `income`
block is present, then the block's `note`; each sweep's `flip:` / `mean flip:`
/ `majority flip:` lines; and, on a verdict Monte Carlo left undecided with a
`market_scenario` prior loaded, one `next:` line naming the run that resolves
it (`--break-even <cheapest owned option>.value_growth_rate`), omitted when
that break-even is already in the run. Every line is built by the same function
that prints it elsewhere, so the block repeats rather than paraphrases.

**One fact once (2026-09-04).** Within the block each derived fact is said
once; every `[warning]` and source line stays verbatim. The break-even lines
open with a header — `break-even <key> (bracket <lo>–<hi>; band = 5% of the
cheaper option's PV[; config refuses N point(s) (…)][; affordability =
highest cost/income ratio; years above the <t>% threshold[; <opt> <r>% (<k>
yr(s) over) at every quoted point]])` — so the band rule, a refused clause
every solve shares and an option whose ratio is the same at every quoted
point of every solve are stated there and nowhere else; the base line carries
its own affordability clause (`; affordability <opt> <r>% (<k> yr(s) over) at
every quoted point · at the crossing <v>: … · at the band's low edge …`), and
the `across` row that re-solves the base config prints `break-even <key> at
<sweep key>=<v>: (= base)`. Each sweep prints `sweep <key> (<n> points[;
affordability <opt> max <r>% breaches … at every point][; insured <opt>
<tier>% at every point])`, then one line per grid point (the row's
`sentence`; the point equal to the base value is marked `(= base)` and keeps
its verdict clauses alone), then the flip lines, each naming its key (`flip
<key>: …`, `no flip along <key>: …`, `mean flip <key>: …`, `majority flip
<key>: …`); a sweep's price-scan note prints as `sweep <key> note: …` unless a
break-even already carried the same note. Where an option's affordability
breach is already a `[warning]` line, the Affordability section keeps its
header and the max-ratio line of every option no warning names.

```bash
uv run hde <config.yaml> --read-back         # the block alone on stdout, exit code as the run
uv run hde <config.yaml> --read-back full    # the same, byte for byte
uv run hde <config.yaml> --read-back short   # the gist shape: [warning] lines, source lines,
                                             #   decisiveness:, and one closing line counting the rest
```

In text output the block prints LAST under `READ-BACK — carry these lines into
any answer, verbatim:`; under `--json` it rides `assumptions.read_back` and the
text block is suppressed, so stdout stays one document. `--quiet` prints its one
line unless `--read-back` is passed too. The flag takes an optional value —
bare or `full` for the whole block, `short` for the gist shape's block
(`assumptions.read_back_short` under `--json`); the config goes before the
flag, since a path after it would be read as the value. A run that prints
the block LAST (no flag) always prints the full one.

**Jurisdiction lines (2026-09-04).** Where an owned option sits is read once —
its `province`, else the province its `municipality` belongs to (`montreal` →
QC, `toronto` → ON) — and three lines follow from it. A Québec option with a
line named for property tax (or a `property_tax_rate`) and no line named for
the school tax gets the `[warning]` `<option>: no school-tax line — Québec levies
school_tax.qc (0.07899% of assessed value) on top of the municipal rate; add it
or list it as not modelled (toward buying)`, the rate read from the registry;
it stays silent when the property-tax figure already carries the school tax (a
cited or declared municipal + school sum). An Ontario property-tax line no
anchor matches has its `<option> other costs:` line end `[no anchor match — hde
--print-anchors; a rate on the purchase price overstates an Ontario bill:
assessments are on a 2016 base]`, and each `reference_matches` entry carries
`province` (`"QC"`, `"ON"`, or `null`). Independently of jurisdiction, a
`mortgage_rate` equal to `mortgage_rate.posted_5y` — in either stated
convention, within the matcher's window — gets the `[warning]`
`<option>.mortgage_rate <x>% is the POSTED 5-year rate (mortgage_rate.posted_5y);
its source says contracted rates run lower — see
mortgage_rate.contracted_5y_uninsured / mortgage_rate.contracted_5y_insured in
--print-anchors; the verdict's margin moves with the rate`. At load, a
`province` or `municipality` YAML parsed as a boolean (an unquoted `ON`, `NO`,
`YES`, `OFF`) is refused before any schedule lookup: `province: True is not a
province code — YAML reads an unquoted ON as a boolean; quote it: province:
"ON"` (an option-level key is prefixed `<option>.`; `municipality` gets the
same shape with `"montreal" | "toronto"` as the example).

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
`verdict_to_dict`, `assumptions_to_dict`, `anchors_to_dict`, `read_back_lines`
(`short=True` for the gist shape's block);
`all_warnings`.
(The MCP server that once wrapped these was removed 2026-09-01: the CLI plus
the repo-local skill is the only surface.)

## Reference entries added 2026-09-04

`mortgage_rate.contracted_5y_uninsured` (4.35%) and
`mortgage_rate.contracted_5y_insured` (4.01%) — Bank of Canada Valet series
V122667786 / V122667780, the average rate on funds advanced in the 2026-06
reference month, each with the effective-annual `restatement` — sit beside
`mortgage_rate.posted_5y`, whose rationale now points at them by name.
`maintenance.nahb_routine` (0.6% of home value a year — NAHB, *Operating Costs
of Owning a Home*, 2019 AHS, Table 2) is the reference sibling of the uncited
`house.annual_maintenance_rate` default; `maintenance.` is a reference family:
never applied, cited when a `sources:` line declares it. `--print-anchors`
carries every record.

## Near-miss hint on an unmatched cost line (2026-09-04)

Each `reference_matches` entry carries one more key, `nearest`: `null` when the
line matched (`citations` non-empty), when nothing published in the option's
own province lies within 2% of the user's figure, or when the option states no
`province` (its own or the top-level one) — a hint is never offered across
provinces. Otherwise `{name, value, delta, short_cite, unit}`: the registry
name, its published figure, the signed gap `user − published` in the family's
own unit (a rate fraction for property tax, dollars for insurance), and the
anchor's tag and unit. The text line appends it to the `no anchor match`
clause, the gap in percentage points for a rate:

```
property tax $3,340/yr = 0.557% of price [no anchor match — hde --print-anchors;
nearest: property_tax.montreal 0.5556% (Δ +0.0011 pt) — not a match]
home insurance $825/yr [no anchor match — hde --print-anchors;
nearest: home_insurance.qc $813 (Δ +$12) — not a match]
```

It is a hint, not a citation: the match rule is unchanged and a `sources:`
declaration on the near-miss figure is still refused.
