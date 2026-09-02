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
the repo root (the directory with `pyproject.toml`); `scenarios/` is
git-ignored, so the user's numbers are never committed. The engine validates,
refuses unknown keys with did-you-mean, and renders the acts the config
supports — anything expressible as a command is the engine's job, not a
reasoning task. The repo's `CLAUDE.md` carries the honesty contract: every
number in an answer names its source class (the user's, an engine anchor, or
a labelled estimate with the direction it biases the verdict).

## Which reference to open (read it before the step it names)

| When | Read |
|---|---|
| The user is certain about one side and vague about the other — "what rent keeps renting the better deal?", "at my rent, what price is worth buying?", "how long would I have to stay?" | `references/threshold-lane.md`, before authoring the config |
| The user asks for a quick sense ("not a spreadsheet") | `references/quick-sense.md`, before the intake message |
| A user phrase you cannot place in the schema — a posted rate, "prices grow 3%", an insurance premium, "houses around $650k" | `references/translation.md` |
| Writing the answer | the checklist below, then `references/answer-template.md` |
| Why a gate exists, or the worked phrasing that satisfies it | `references/gates.md` |
| A worked example of intake → run → read-back | `references/examples.md` |
| Why the surface is CLI-only, and what each rule caught | `references/rationale.md` |

## Elicit first (before authoring anything)

The engine answers the question the config asks; get to know the person
first. Five things decide the shape of the run — ask them in the user's
language, folded into the ONE intake message, never as a quiz:

1. **How long do you expect to stay, and how sure are you?** → `years`;
   "not sure" is a range → bracket it (gate 5).
2. **How would you pay, and how much cash do you have for day one?** → all
   cash, or down payment + quoted rate + amortization; the down payment AND
   the purchase costs come out of that cash, so ask for the amount, not a
   percentage; under 20% down means a mortgage-insurance premium
   (`financed_purchase_costs`).
3. **What does "best" mean to you — lowest expected cost, smallest worst case,
   or most wealth at the end?** → which figure is the answer (gate 6).
4. **What is your income, and how stable is it?** → an `income` block turns on
   affordability ratios; a feared pay cut is a `pay_drop_events` entry.
5. **Which of your numbers are you least sure of?** → those get a `--sweep`.
   (Ask which numbers they would not bet on, never "which uncertainties
   matter".)

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
return, 1% real rent escalation — 0% for a Québec continuing lease — and
0.6% maintenance, unless you say otherwise").

1. **Which options the question implies** → which sections: "keep renting or
   buy a condo" = `rent` + `condo`; "house or condo" = `condo` + `house`; no
   dwelling named = ask which.
2. **The user's own numbers — always theirs, never yours:** rent; price;
   condo fees; how they'd pay and the cash they have for year 0 (down payment
   + purchase costs must fit in it); how long; income; **owner costs** — the
   property tax bill, home or unit insurance, purchase costs (welcome or
   land-transfer tax, notary, inspection, insurance premium) — "give me the
   number, a guess I'll label, or say skip and I'll report it as not
   modelled"; offer to bracket rather than pick. Exception — purchase costs
   when they named their cash: "no idea" must NOT become `purchase_costs: 0`;
   take the illustrative ≈ 1.5% of price (labelled), deduct it from their cash
   to get the real down payment, and recompute the loan-to-value band and the
   premium.
3. **Modelling parameters — may be proposed, always labelled:** discount rate
   (engine default 3% real, cited), growth and escalation rates, maintenance
   (NAHB routine ≈ 0.6% of value; the examples' 1.2% adds the 1%-rule
   budgeting family — name which), the uncertainty vols. "I don't know" here
   means take the default and name it; a RANGE is two configs (gate 5).
4. **Units and terms:** decimals in the YAML; quoted rates are usually sticker
   figures — settle real vs nominal (gate 3).

ONE follow-up is right when their answers open a new question (the arithmetic
does not close, one number contradicts another); a config built on a
contradiction is worse than a second message. Exception: a cash shortfall
smaller than the insurance premium it would trigger → run BOTH branches ("you
find the cash" / "insured mortgage at the lower down payment") and read back
both verdicts. Run only once every item in (2) is known or explicitly waived;
the engine refuses a missing required key with the exact message — show it.

## Cases → dispatch

| Case | Command |
|---|---|
| Contract question (what inputs exist, what is required) | `uv run hde --print-schema` |
| "Where did that number come from?" (source, URL, band, what it replaced) | `uv run hde --print-anchors` |
| Quick estimate from a ready config | `uv run hde <config.yaml>` |
| Full answer with visuals (default for real questions) | `uv run hde <config.yaml> --story scenarios/<slug>` |
| "What if I stayed N years / prices grew X / the price were Y?" — the flip point | `--sweep years=5,10,15,20` · `--sweep condo.value_growth_rate=0:0.04:5` · `--sweep condo.initial_value=380000,400000,420000` (repeatable; `--no-monte-carlo` for speed) |
| The threshold on ONE input — rent, price, years | `--break-even rent.monthly_rent` · `--break-even condo.initial_value` · `--break-even years=3:30`; beside `--sweep` it is re-solved at every sweep point (`across`); two priced options only; the lane is `references/threshold-lane.md` |
| Agent-consumable result | append `--json` |
| Demographic prior (Québec only: `MTL_RMR`, `MTL_ISLAND_RA06`, `LAVAL_RA13`, `QC_RMR`, `HORS_RMR` — the finest geography containing the user's area, and say which) | copy the `market_scenario` block from `examples/showcase_demographic_prior.yaml` (prior at `tests/fixtures/scenario_prior_golden.json`); Monte Carlo on; with a `rent` option set `simulation.investment_return_vol: 0.10` or the engine warns; a financed buyer keeps `mode: nominal` |

## Judgment gates (one rule each; the why and the worked phrasing are in `references/gates.md`)

1. **Decisiveness is not the headline.** Read `verdict.decisive` and
   `verdict.reason`; not decisive = "too close to call", with the probability
   or the margin and what breaks the tie — at every sweep point too.
2. **A default is not the user's input.** Read the `defaults applied:` line
   back before the verdict, each with its source; `[neutral, uncited]` means
   no evidence. No price-growth view in a shipped-prior geography → run the
   prior as a second config (it is the growth view), leave the base growth at
   0, and quote the drift the assumptions line prints for the horizon's bands.
3. **A mortgage means `mode: nominal`** (`inflation_rate: 0.021`,
   `mortgage_rate` = the quote's effective annual, `discount_rate` omitted);
   growth, escalation and return inputs stay REAL and the engine composes
   inflation. `mode: real` for all-cash and rent-only. Colloquial growth and
   return rates are sticker figures — convert to real, (1 + quoted)/(1 + 2.1%)
   − 1; the mortgage's only conversion is compounding.
4. **Like-for-like renter capital.** `rent.invested_down_payment` = the
   buyer's total year-0 cash (down payment + purchase costs; all cash = price
   + purchase costs). Never call that capital a drag or an advantage — only
   the engine's capital-spread warning says which way it cuts.
5. **A range is two configs.** Bracket with `--sweep` in the user's units
   (their value, zero in their units, one step below); the flip is the
   engine's `flip:` line — densify, never interpolate; the tie band is the
   points where `decisive` is false; under "expected cost" with uncertainty
   on, the flip is the `mean flip:` line, never mixed with the deterministic
   one; an unswept claim is written "not run".
6. **Match the figure to their criterion.** Expected cost → the margin, and
   with uncertainty on the Monte Carlo MEAN (`verdict.mc_mean_best`; say so
   when it disagrees); worst case → vols and `price_shock` on, labelled, read
   p95 and `prob_*_cheapest`; `investment_return_vol` is the ANNUAL volatility
   of the renter's return (0.10 ≈ 60/40) — both sides carry uncertainty or
   neither; every vol at 0 means nothing was modelled; most wealth →
   `total_pv`.
7. **Cash line — cash is not PV.** Quote the report's `Year-1 cash` line
   beside the $/month PV equivalent: outlay, principal, unrecoverable cash,
   and the `expected appreciation` term with the engine's label (at 0% real
   growth it is inflation, not real gain).
8. **"Not modelled" is mandatory,** every item with its direction of bias:
   renewal risk with any mortgage (toward buying), early exit (toward buying),
   taxes on the renter's return (toward renting), every default the engine
   warned on (with its rerun figure or its bias).

## The answer — checklist first, then prose

Before writing, read these off the run in this order and carry each into the
answer; the cap of any lane ranks what stays and never drops an item:

- [ ] every `[warning]` line — each with its rerun figure or its direction of
      bias (a dropped warning fails the answer at any length)
- [ ] `defaults applied:` — with an owned option, the two largest engine-set
      numbers, `selling_cost_rate` (5%, WOWA) and the discount rate, named
      with their source; every other figure you proposed, with its label
- [ ] `decisiveness:` — the verdict's rule, its margin or probability, and
      `mc_mean_best` when it disagrees
- [ ] the flip point or threshold, in the user's units, quoted at both ends
      of any estimate it rests on
- [ ] `Year-1 cash` — both sides, principal, unrecoverable; the year-0 cash
      total the config commits and the distance to the 20% line
- [ ] `Affordability` — max ratio and breach years, quoting the affordability
      `[warning]` line verbatim (it names the 32% guideline, the 39% GDS cap
      and the 44% TDS cap)
- [ ] **No source for:** every figure you estimated because neither the user
      nor the anchor registry had it
- [ ] **Not modelled:** every item with a direction
- [ ] where the story is (`scenarios/<slug>/STORY.md`), and the one next step

Then the prose per `references/answer-template.md`, under 500 words; the
quick-sense cap and its cut order are in `references/quick-sense.md`.

## Verification

- Exit 0 AND every `[warning]` line surfaced with the verdict (warnings are
  judgment gates in disguise): owner costs not modelled, zero appreciation,
  affordability breaches, a mortgage run in real mode, one-sided uncertainty.
- `--story`: STORY.md's headline states the verdict in words; the acts the
  config supports — acts 1 and 2 always; act 4 ("Home-value futures") with an
  owned option; act 3 ("The uncertainty") only when at least one
  uncertainty input is on (a single-path run skips it); act 5 ("Why", the demographic
  signal) only with `market_scenario:`; act 6 ("The market line", break-even
  rent) only with `rent` plus an owned option.
- `--json`: `engine_version`, `warnings`, `assumptions`, `verdict`,
  `deterministic`, `monte_carlo` present (`sweeps` / `break_evens` when
  asked); every `assumptions.defaults_applied` entry carries an `anchor` with
  a `source`.

## Escalation

Config errors: show the exact message; values are the user's decision. A
prior or geography refusal lists the valid geographies — choose with the
user. Trade execution, money movement, market timing: out of scope; the engine
computes present-value comparisons only. Deeper guidance: `examples/README.md`
walks every config template; `docs/reference/ARCHITECTURE.md` carries the
figure glossary (what every printed number is and how it is computed).
