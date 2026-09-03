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
git-ignored, so the user's numbers are never committed. Anything expressible
as a command is the engine's job, not a reasoning task. The repo's `CLAUDE.md` carries the honesty contract: every
number names its source class (the user's, an anchor, or a labelled estimate
with the direction it biases the verdict).

## Which reference to open (read it before the step it names)

Reference files live beside this file under `.claude/skills/hde/references/`;
`examples/`, `docs/` and `tests/fixtures/` paths are repo-root paths.

| When | Read |
|---|---|
| The user is certain about one side and vague about the other — "what rent keeps renting the better deal?", "at my rent, what price is worth buying?", "how long would I have to stay?" | `references/threshold-lane.md`, before authoring the config |
| The user asks, in their own words, for a quick sense ("not a spreadsheet", "just roughly") — never on anticipation | `references/quick-sense.md`, before the intake message |
| A user phrase you cannot place in the schema (a posted rate, "houses around $650k") | `references/translation.md` |
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
2. **How would you pay, how much cash do you have for day one, and where
   does that money sit today if you do not buy?** → all cash, or the cash pile
   + quoted rate + amortization: ask for the AMOUNT, never a percentage — it
   goes in as `cash_available` and the engine nets the purchase costs and
   prints the loan-to-value; under 20% down means a mortgage-insurance premium
   (`financed_purchase_costs`); the renter's alternative sets
   `rent.investment_return_rate` (an index fund is not a savings account).
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
   dwelling named = ask which.
2. **The user's own numbers — always theirs, never yours:** rent; price;
   condo fees; how they'd pay and the cash they have for year 0
   (`cash_available`); how long; income; **owner costs** — the property tax
   bill, home or unit insurance, purchase costs (welcome or land-transfer tax,
   notary, inspection, insurance premium) — "give me the number, a guess I'll
   label, or say skip and I'll report it as not modelled"; offer to bracket
   rather than pick. Before guessing an owner cost run `uv run hde
   --print-anchors`: property-tax rates on ASSESSED value for Laval, Montréal,
   Québec City and Toronto (the read-back cites a match), explicit no-source
   entries for Gatineau and Ottawa, household-average insurance floors for QC
   and ON. Purchase costs when they named their cash: "no idea" must NOT
   become `purchase_costs: 0` — take the illustrative ≈ 1.5% of price
   (labelled) and let the engine net it from `cash_available`; never type a
   hand-computed `down_payment`.
3. **Modelling parameters — may be proposed, always labelled:** discount rate
   (engine default 3% real, cited), growth and escalation rates, maintenance
   (0.6% NAHB routine or the examples' 1.2% — name which), the uncertainty
   vols. "I don't know" here
   means take the default and name it; a RANGE is two configs (gate 5).
4. **Units and terms:** decimals in the YAML; quoted rates are usually sticker
   figures — settle real vs nominal (gate 3).

ONE follow-up is right when their answers open a new question (the arithmetic
does not close, one number contradicts another); a config built on a
contradiction is worse than a second message — and it never asks the user to
pick a method or a dwelling they said they do not care about. Exception: a
cash shortfall smaller than the premium it would trigger, OR a 20% clearance
smaller than the purchase-cost estimate it rests on (the `financing:` line
prints the distance) → run BOTH branches (uninsured at 20% / insured with the
premium in `financed_purchase_costs`) and quote both verdicts and thresholds;
a pro-buying clause that holds only uninsured says so. Run only once every
item in (2) is known or explicitly waived; the engine refuses a missing
required key with the exact message — show it.

## Cases → dispatch

| Case | Command |
|---|---|
| Contract question (what inputs exist, what is required) | `uv run hde --print-schema` |
| "Where did that number come from?" (source, URL, band, what it replaced) | `uv run hde --print-anchors` |
| Quick estimate from a ready config | `uv run hde <config.yaml>` |
| Full answer with visuals (default for real questions) | `uv run hde <config.yaml> --story scenarios/<slug>` — on the config whose verdict the answer leads with (a rent threshold: the one at the user's actual rent with uncertainty on; a price threshold: at the shop-under edge, never the placeholder seed — say which price the story is at) |
| "What if I stayed N years / prices grew X / the price were Y?" — the flip point | `--sweep years=5,10,15,20` · `--sweep condo.value_growth_rate=0:0.04:5` · `--sweep condo.initial_value=380000,400000,420000` (repeatable; `--no-monte-carlo` for speed) |
| The threshold on ONE input — rent, price, years, growth | `--break-even rent.monthly_rent` · `--break-even condo.initial_value` · `--break-even years=3:30` · `--break-even condo.value_growth_rate=-0.02:0.05` (a comparison with a prior on quotes the prior's drift against this band — it is what settles a coin flip); beside `--sweep` it is re-solved at every sweep point (`across`, one axis at a time — a combination needs a second config with the other value typed, then the same command); two priced options only; the lane is `references/threshold-lane.md` |
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
3. **A mortgage means `mode: nominal`** (`inflation_rate: 0.021`,
   `mortgage_rate` = the quote's effective annual, `discount_rate` omitted);
   growth, escalation and return inputs stay REAL and the engine composes
   inflation. `mode: real` for all-cash and rent-only. Quoted growth and
   return rates are sticker figures — convert to real (`references/translation.md`).
4. **Like-for-like renter capital.** `rent.invested_down_payment` = the
   buyer's total year-0 cash (down payment + purchase costs; all cash = price
   + purchase costs). Never call that capital a drag or an advantage — only
   the engine's capital-spread warning says which way it cuts.
5. **A range is two configs.** Bracket with `--sweep` in the user's units;
   the flip is the
   engine's `flip:` line — densify, never interpolate; the tie band is the
   points where `decisive` is false; under "expected cost" with uncertainty
   on, the flip is the `mean flip:` line, never mixed with the deterministic
   one; an unswept claim is written "not run".
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
   warned on (with its rerun figure or its bias).

## The answer — checklist first, then prose

Before writing, read these off the run in this order and carry each into the
answer; the cap of any lane ranks what stays and never drops an item:

- [ ] every `[warning]` line — each with its rerun figure or its direction of
      bias (a dropped warning fails the answer at any length)
- [ ] `defaults applied:` — with an owned option, the two largest engine-set
      numbers, `selling_cost_rate` (5%, WOWA) and the discount rate, named
      with their source; then every value you TYPED on the user's behalf (a 0%
      rent escalation, the 25-year amortization, a maintenance rate, every
      vol): declare each config key in a `sources:` block as `user`,
      `assistant` or `anchor:<name>` and quote the read-back's
      `assistant-typed:` line — a typed value leaves `defaults applied` and its
      warning never fires, so that line is the user's only record; never under
      "Not modelled" (it was modelled, at your number)
- [ ] `decisiveness:` — the verdict's rule with its threshold (the 5% tie
      band or the 65% floor), its margin or probability, and `mc_mean_best`
      when it disagrees; when Monte Carlo decides, every uncertainty input
      with its source class and what the deterministic line says without them
      (the engine's warning carries both)
- [ ] the flip point or threshold — the engine's band-first `sentence` copied
      verbatim (the `--break-even` entry or the act-6 caption), never a bare
      crossing; at both ends of any estimate it rests on; every bracket that
      ran gets its clause (growth, maintenance, escalation, years) — a run you
      drop is a claim you hide; on an insured branch both thresholds side by
      side; on a price scan the engine's coherence `note` (dollar inputs held
      fixed while the price moves) with its direction
- [ ] `Year-1 cash` — both sides in $/month, principal, unrecoverable, beside
      the verdict's `≈ $/month equivalent` (PV, not cash); the assumptions
      line's `financing:` entry (the netting `cash − purchase_costs = down
      payment`, loan-to-value, the distance to the 20% line) — a clearance smaller than the estimate it
      rests on is the same cliff as a shortfall: the insured branch was run
      (Missing information) and its verdict is quoted beside this one
- [ ] `Affordability` — max ratio and breach years, quoting the affordability
      `[warning]` line verbatim (it names the 32% guideline, the 39% GDS cap
      and the 44% TDS cap) — and at the threshold: the break-even's
      affordability at the crossing and band edges, or the sweep rows'
      `affordability`; a range you call cheaper is checked against the same
      lines
- [ ] **No source for:** every figure you estimated because neither the user
      nor the anchor registry had it; outside the anchored jurisdictions say so
      (the registry is Québec-shaped plus Toronto — an Ontario land-transfer
      tax or an Ottawa rate has no anchor); a placeholder above ~10% of year-1
      cash (a tax bill, insurance) gets a two-point `--sweep`, both points
      quoted with the direction
- [ ] **Not modelled:** every item with a direction
- [ ] where the story is (`scenarios/<slug>/STORY.md`), and the one next step

Then the prose per `references/answer-template.md`. One cap applies: under
500 words, or the quick-sense cap and its cut order in
`references/quick-sense.md` when the user asked for a quick sense — the
lane's cap overrides the template's.

## Verification

- Exit 0 AND every `[warning]` line surfaced with the verdict (warnings are
  judgment gates in disguise).
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
(every config template); `docs/reference/ARCHITECTURE.md` (the figure glossary).
