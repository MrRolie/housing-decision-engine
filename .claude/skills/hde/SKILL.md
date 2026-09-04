---
name: hde
description: Runs rent-vs-buy housing decision analyses with the housing-decision-engine (hde) CLI. Use when the user asks whether to rent or buy, whether buying a house or condo is worth it, compares renting vs buying costs, mentions a mortgage decision, wants a present-value comparison of housing options, asks about demographic or population-driven housing scenarios, or mentions hde. Also use for casual phrasings like "should I keep renting?", "is buying in Montréal/Gatineau worth it?", or any housing-cost-vs-alternatives question, even if hde is not named.
---

# HDE — housing decision engine (skill + CLI dispatch contract)

## Order of operations

Elicit → **Missing information** gate (ONE message) → config in
`scenarios/<slug>.yaml` → run (+ `--sweep` / `--break-even`) →
**assumptions read-back** → warnings → verdict with its decisiveness → story →
the answer, via the checklist below. Everything runs as `uv run hde …` from
the repo root; `scenarios/` is git-ignored (the user's numbers are never
committed). Anything expressible as a command is the engine's job, not a
reasoning task. The repo's `CLAUDE.md` carries the honesty contract: every
number names its source class (the user's, an anchor, or a labelled estimate
with the direction it biases the verdict).

## Which reference to open (read it before the step it names)

Reference files live beside this file under `.claude/skills/hde/references/`;
`examples/`, `docs/` and `tests/fixtures/` paths are repo-root paths.

| When | Read |
|---|---|
| The user is certain about one side and vague about the other — "what rent keeps renting the better deal?", "at what price is buying worth it?", "how long would I have to stay?" — always the full run with a threshold, never the short shape | `references/threshold-lane.md`, before authoring the config |
| The user asks for brevity in their own words ("just roughly", "the gist") — OR the question names no listing, no price, no date and asks for no threshold ("is it dumb to rent forever?") | `references/quick-sense.md`, before the intake message: brevity words set the cap, the no-listing test sets the asks |
| A user phrase you cannot place in the schema (a posted rate, "houses around $650k", "$X down plus $Y for closing") | `references/translation.md` |
| Writing the answer | the checklist below, then `references/answer-template.md` |
| Why a gate exists, or the worked phrasing that satisfies it | `references/gates.md` |
| A worked example of intake → run → read-back | `references/examples.md` |
| Why the surface is CLI-only, and what each rule caught | `references/rationale.md` |

## Elicit first (before authoring anything)

Five things decide the shape of the run — asked in the user's language,
folded into the ONE intake message:

1. **How long do you expect to stay, and how sure are you?** → `years`;
   "not sure" is a range → bracket it (gate 5).
2. **How would you pay, how much cash do you have for day one, and where
   does that money sit today if you do not buy?** → all cash, or
   `cash_available` (the AMOUNT, never a percentage — the engine nets the
   purchase costs and prints the loan-to-value) + quoted rate + amortization;
   first home → `first_time_buyer: true`; under 20% down →
   `mortgage_insurance: auto` with the province, never a hand-computed premium
   (`financed_purchase_costs` only carries one the user was quoted); the
   renter's alternative sets `rent.investment_return_rate`.
3. **What does "best" mean to you — lowest expected cost, smallest worst case,
   or most wealth at the end?** → which figure is the answer (gate 6).
4. **What is your income, and how stable is it?** → an `income` block turns on
   affordability ratios; a feared pay cut is a `pay_drop_events` entry.
5. **Which of your numbers are you least sure of?** → those get a `--sweep`.

Then the schema: `uv run hde --print-schema` for the exact keys, the
`required` flags and `required_if` (an owned option declares `all_cash: true`
OR the full mortgage block). Describe the schema only from that output, never
from memory. Invent no values: every number you do not ask for becomes a
default the engine echoes back with its source.

## Missing information (ask before you run)

Work out everything the config needs and ask for ALL of it in ONE message,
grouped as a short form the user answers in one reply — (1) how long, how
they'd pay, the cash for day one; (2) fees, tax, insurance, closing costs;
(3) income; (4) what "best" means and any view on prices — with every
modelling default you will take stated in the same message as a labelled
default they can overrule ("25-year amortization, the engine's 3% real
return, 1% real rent escalation, 0.6% maintenance — unless you say
otherwise").

1. **Which options the question implies** → which sections: "keep renting or
   buy a condo" = `rent` + `condo`; "house or condo" = `condo` + `house`; no
   dwelling named = ask which; "not sure if it has a fee" = two configs, both
   quoted.
2. **The user's own numbers — always theirs, never yours:** rent; price;
   condo fees; how they'd pay and the cash for year 0 (`cash_available` — and
   whether it includes closing costs); how long; income; **owner costs** — the
   property tax bill, home or unit insurance, purchase costs (notary,
   inspection) — "give me the number, a guess I'll label, or say skip and I'll
   report it as not modelled"; offer to bracket rather than pick. Before
   guessing an owner cost run `uv run hde --print-anchors` (what it covers:
   `references/translation.md`). "No idea" on closing costs must NOT become
   `purchase_costs: 0` — set `land_transfer_tax: auto` with a QUOTED
   `province: "QC"` / `"ON"` (plus `municipality: montreal|toronto`) so the
   engine prices the duty, then add notary and inspection.
3. **Modelling parameters — may be proposed, always labelled:** discount rate
   (engine default 3% real, cited), growth and escalation rates, maintenance
   (0.6% `maintenance.nahb_routine` or the examples' 1.2% — name which), the
   uncertainty vols. "I don't know" here means take the default and name it; a
   RANGE is two configs (gate 5).
4. **Units and terms:** decimals in the YAML; quoted rates are usually sticker
   figures — settle real vs nominal (gate 3).

ONE follow-up is right when their answers open a new question (the arithmetic
does not close, one number contradicts another); a config built on a
contradiction is worse than a second message — and it never asks the user to
pick a method or a dwelling they said they do not care about. Exception: cash
within one premium of the 20% line, either side (the `financing:` line prints
the distance) → run BOTH tiers and quote both (checklist). Run only once every
item in (2) is known or explicitly waived; the engine refuses a missing
required key with the exact message — show it.

## Cases → dispatch

| Case | Command |
|---|---|
| Contract question (what inputs exist, what is required) | `uv run hde --print-schema` |
| "Where did that number come from?" (source, URL, band, what it replaced) | `uv run hde --print-anchors` |
| Quick estimate from a ready config | `uv run hde <config.yaml>` |
| Full answer with visuals (default for real questions) | `uv run hde <config.yaml> --story scenarios/<slug>` — on the config the answer leads with (a rent threshold: at the user's actual rent, uncertainty on; a price threshold: at the shop-under edge, never the placeholder seed — `references/threshold-lane.md`; say which price the story is at) |
| "What if I stayed N years / prices grew X / the price were Y?" — the flip point | `--sweep years=5,10,15,20` · `--sweep condo.value_growth_rate=0:0.04:5` · `--sweep condo.initial_value=380000,400000,420000` (repeatable; `--no-monte-carlo` for speed) |
| The threshold on ONE input — rent, price, years, growth, a placeholder in rate form | `--break-even rent.monthly_rent` · `--break-even condo.initial_value` · `--break-even years=3:30` · `--break-even condo.value_growth_rate=-0.02:0.05` · `--break-even house.property_tax_rate=0.004:0.016`; beside `--sweep` it is re-solved at every sweep point (`across`, one axis at a time — a combination is a second config); two priced options only; the lane is `references/threshold-lane.md` |
| Agent-consumable result | append `--json` |
| Demographic prior (Québec only: `MTL_RMR`, `MTL_ISLAND_RA06`, `LAVAL_RA13`, `QC_RMR`, `HORS_RMR` — the finest geography containing the user's area, and say which) | copy the `market_scenario` block from `examples/showcase_demographic_prior.yaml`; Monte Carlo on; with a `rent` option set `simulation.investment_return_vol: 0.10` or the engine warns; a financed buyer keeps `mode: nominal` |

## Judgment gates (one rule each; the why and the worked phrasing are in `references/gates.md`)

1. **Decisiveness is not the headline.** Read `verdict.decisive` and
   `verdict.reason`; not decisive = "too close to call", with the probability
   or the margin and what breaks the tie — at every sweep point too.
2. **A default is not the user's input.** Read the `defaults applied:` line
   back before the verdict, each with its source; `[neutral, uncited]` means
   no evidence. No price-growth view in a shipped-prior geography → run the
   prior as a second config (it is the growth view), leave the base growth at
   0, and quote the drift the assumptions line prints for the horizon's bands
   — in ADDITION to the growth sweep, never instead of it.
3. **A mortgage means `mode: nominal`** (`inflation_rate: 0.021`, declared
   `anchor:economic.inflation_rate.nominal_planning`; `mortgage_rate` = the
   quote's effective annual; `discount_rate` NEVER typed — omit it and the
   engine composes 5.2%); growth, escalation and return inputs stay REAL and the engine composes
   inflation. `mode: real` for all-cash and rent-only. Quoted growth and
   return rates are sticker figures — convert to real (`references/translation.md`).
4. **Like-for-like renter capital.** `rent.invested_down_payment` = the
   buyer's total year-0 cash (down payment + purchase costs; all cash = price
   + purchase costs). Never call that capital a drag or an advantage — only
   the engine's capital-spread warning says which way it cuts.
5. **A range is two configs.** Bracket with `--sweep` in the user's units;
   the flip is the engine's `flip <key>:` line — densify, never interpolate; the tie
   band is the points where `decisive` is false; under "expected cost" with
   uncertainty on, the flip is the `mean flip <key>:` line, never mixed with the
   deterministic one; an unswept claim is written "not run".
6. **Match the figure to their criterion.** Expected cost → the margin, and
   with uncertainty on the Monte Carlo MEAN (`verdict.mc_mean_best`; say so
   when it disagrees); worst case → vols and `price_shock` on, labelled, read
   p95 and `prob_*_cheapest`; `investment_return_vol` is the ANNUAL volatility
   of the renter's return — both sides carry uncertainty or neither; most
   wealth → `total_pv`.
7. **Cash line — cash is not PV.** Quote the report's `Year-1 cash` line
   beside the $/month PV equivalent: outlay, principal, unrecoverable cash,
   and the `expected appreciation` term with the engine's label (at 0% real
   growth it is inflation, not real gain).
8. **"Not modelled" is mandatory,** every item with its direction of bias:
   renewal risk with any mortgage (toward buying), early exit (toward buying),
   taxes on the renter's return (toward renting), every default the engine
   warned on (with its rerun figure or its bias), every dollar input a
   coherence note held fixed along a scan (with the note's direction).

## The answer — checklist first, then prose

Before writing, read these off the run and carry each into the answer; the
cap of any lane ranks what stays and never drops an item:

- [ ] the engine's **READ-BACK block** (`--read-back`, or the last section
      of any run) pasted verbatim at the END of the answer,
      outside every cap — every `[warning]` line, the `assistant-typed:` /
      `unattributed:` lines (every config key declared in `sources:` as `user`
      / `assistant` / `anchor:<name>`), the `decisiveness:` rule with its
      threshold, each `financing:` and `other costs:` line, `Affordability`,
      every sweep point's line and every break-even `sentence` with its
      coherence `note` (in `--json`: `assumptions.read_back`). The block is
      ONE command's output: run the sweeps and break-evens together with
      `--read-back`; never merge two blocks or write a line in the engine's
      voice. It is the config the verdict leads with — the other config's
      `decisiveness:` line and any warning only it raised are quoted in the
      prose; the prose never contradicts it
- [ ] `defaults applied:` — the two largest engine-set numbers,
      `selling_cost_rate` (5%, WOWA) and the discount rate, named with their
      source in the prose
- [ ] `decisiveness:` in the prose — the threshold it rests on (the 65% floor
      with Monte Carlo on, else the 5% tie band), its margin or probability,
      `mc_mean_best` when it disagrees, and the typed uncertainty input it
      rests on when the block's warning names one; every figure names its
      config (flat-price or prior), never a flat-price line under a prior
      headline; a prior that leaves the verdict undecided means the growth
      break-even ran and its note (where the drift sits against the band) is
      quoted
- [ ] the flip point or threshold in the prose — the block's `sentence`
      restated in the user's units, at both ends of any estimate it rests on;
      every bracket that ran gets its clause (a run you drop is a claim you
      hide; unrun = "not run"); brackets ride the config the headline comes
      from, Monte Carlo on — a bracket run on a flat config is quoted as the
      flat line's; an insured branch quotes both thresholds; on a price scan
      the coherence `note`'s direction
- [ ] `Year-1 cash` — both sides in $/month, principal, unrecoverable, beside
      the verdict's `≈ $/month equivalent` (PV, not cash); a second cash tier
      that ran is told — its loan-to-value, tier, premium and 20%-down ceiling
      from its `financing:` line — with its verdict beside this one
- [ ] `Affordability` — in the prose too when income was given, at the
      threshold's crossing and band edges as well as the base run; a range you
      call cheaper is checked against the 32% and 39% lines and never softened
- [ ] **No source for:** every figure you estimated because neither the user
      nor the anchor registry had it; outside the anchored jurisdictions say so
      (an Ottawa or Gatineau property-tax rate has no anchor); every assistant-typed
      placeholder the verdict could turn on (a tax bill, insurance, the seed
      price) is typed in a form `--break-even` can solve (`property_tax_rate`,
      `purchase_costs`) and solved on a bracket spanning BOTH sides of your
      figure (`KEY=lo:hi`) — never a one-sided `--sweep`; an Ontario tax
      placeholder is checked downward first (bills rest on a 2016 assessment
      base, so a rate on price overstates them)
- [ ] **Not modelled:** every item with a direction (gate 8)
- [ ] where the story is (`scenarios/<slug>/STORY.md`), and the one next step

Then the prose per `references/answer-template.md`. One cap applies to the
prose: under 500 words, or the quick-sense cap and its cut order in
`references/quick-sense.md` when the user asked for a quick sense — the
lane's cap overrides the template's; the READ-BACK block is outside both.

## Verification

- Exit 0 AND every `[warning]` line surfaced with the verdict.
- `--story`: STORY.md's headline states the verdict in words; the acts the
  config supports — acts 1 and 2 always; act 4 ("Home-value futures") with an
  owned option; act 3 ("The uncertainty") only when at least one
  uncertainty input is on (a single-path run skips it); act 5 ("Why", the demographic
  signal) only with `market_scenario:`; act 6 ("The market line", break-even
  rent) only with `rent` plus an owned option.
- `--json`: `engine_version`, `warnings`, `assumptions`, `verdict`,
  `deterministic`, `monte_carlo` present; every `assumptions.defaults_applied`
  entry carries an `anchor` with a `source`.

## Escalation

Config errors: show the exact message; values are the user's decision. Trade
execution, money movement, market timing: out of scope. Deeper guidance: `examples/README.md`
(every config template); `docs/reference/ARCHITECTURE.md` (the figure glossary).
