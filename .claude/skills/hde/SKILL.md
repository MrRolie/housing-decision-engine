---
name: hde
description: Runs rent-vs-buy housing decision analyses with the housing-decision-engine (hde) CLI. Use when the user asks whether to rent or buy, whether buying a house or condo is worth it, compares renting vs buying costs, mentions a mortgage decision, wants a present-value comparison of housing options, asks about demographic or population-driven housing scenarios, or mentions hde. Also use for casual phrasings like "should I keep renting?", "is buying in Montréal/Gatineau worth it?", or any housing-cost-vs-alternatives question, even if hde is not named.
---

# HDE — housing decision engine (skill + CLI dispatch contract)

## Activation

Any housing-decision question: rent vs buy, condo vs house, "is it worth it",
demographic-informed price outlooks. The engine is the `hde` CLI in this repo
(the directory holding this skill's `.claude/`; standalone — the first
`uv run hde` installs its own dependencies, only `uv` is needed).

## Elicit first (before authoring anything)

The engine answers the question the config asks. Get to know the person before
you write a config. Five things decide the shape of the run — ask them in the
user's language, folded into the ONE intake message below, never as a quiz:

1. **How long do you expect to stay, and how sure are you?** → `years`. Under
   five years the selling cost dominates and the engine warns; if they are not
   sure, that is a range → bracket it (gate 5).
2. **How would you pay?** → all cash, or down payment + quoted rate + amortization
   (the mortgage block); a down payment under 20% means a mortgage-insurance
   premium (purchase_costs).
3. **What does "best" mean to you — lowest expected cost, smallest worst case,
   or most wealth at the end?** → which figure is the answer (gate 6).
4. **What is your income, and how stable is it?** → an `income` block turns on
   affordability ratios; a pay cut they fear is a `pay_drop_events` entry.
5. **Which of your numbers are you least sure of?** → those get a `--sweep`.
   (Never ask a member of the public "which uncertainties matter"; ask which
   numbers they would not bet on.)

Then gather the schema keys: consult `--print-schema` for exact keys, the
`required` flags, and `required_if` (an owned option must declare
`all_cash: true` OR the full mortgage block). Describe the schema only from
that output, never from memory. Invent no values: a plausible invented growth
rate produces a confident-looking wrong verdict, the exact failure this
engine exists to prevent. Every number you do not ask for becomes a default
the engine echoes back with its source.

## Missing information (ask before you run)

A question rarely carries everything the config needs. Before writing any
YAML, work out what is missing and ask for ALL of it in ONE message, in the
user's words, grouped so it reads as a short form — not a drip of one
question per turn, and never a run on guessed numbers.

1. **Which options the question implies** → which sections: "keep renting or
   buy a condo" = `rent` + `condo`; "house or condo" = `condo` + `house`;
   "is buying worth it" with no dwelling named = ask which.
2. **The user's own numbers — always theirs, never yours:** monthly rent;
   purchase price; condo fees; how they would pay (all cash, or down payment +
   quoted mortgage rate + amortization); how long they plan to stay; income if
   they care about affordability; **owner costs — the property tax bill, home
   or unit insurance, and purchase costs (welcome/land-transfer tax, notary,
   inspection, mortgage-insurance premium)** — "give me the number, a guess
   I'll label, or say skip and I'll report it as not modelled". If they
   cannot give one, offer to bracket it (two configs) rather than pick for
   them.
3. **Modelling parameters — may be proposed, always labelled:** discount rate
   (engine default 3% real, cited), growth and escalation rates, maintenance
   rate (NAHB ≈ 0.6% of value), the uncertainty vols. Say "I'll use X because
   <source or 'illustrative'>" and let the engine echo it back under
   `defaults applied`; a user's "I don't know" here means take the default
   and name it, not stop. A user's RANGE ("2–3%?") is not a midpoint — it is
   two configs (gate 5).
4. **Units and terms:** decimals not percents in the YAML; quoted mortgage
   and growth rates are usually nominal — settle real vs nominal (gate 3).

Run only once every item in (2) is known or explicitly waived. The engine
refuses a missing required key with the exact message — show it, never paper
over it.

## Translating the real world into the config

| The user says | Where it goes | Note |
|---|---|---|
| property tax, home/unit insurance, utilities the owner pays | `condo.other_recurring_costs` / `house.other_recurring_costs` `{name, annual_amount, escalation_rate}` | escalation is REAL (0 = tracks inflation); the engine warns when an owned option has none |
| welcome / land-transfer tax, notary, inspection, mortgage-insurance premium paid in cash | `purchase_costs` (owned option) | paid at year 0, outside the affordability ratio |
| mortgage-insurance premium rolled into the loan (<20% down) | not modelled as financing — put the premium in `purchase_costs` and SAY it is approximated as cash at purchase | engine gap: no CMHC schedule, no financed premium |
| roof, appliances, special assessment, moving costs | `events` `{name, base_cost, expected_year}` | one-offs during the horizon; they DO enter that year's affordability ratio |
| realtor commission + notary at sale | `selling_cost_rate` (default 5%, WOWA 2026) | dominates short horizons |
| the money the renter keeps instead of buying | `rent.invested_down_payment` + `investment_return_rate` | charged at year 0 and credited at its terminal value, exactly like the buyer's down payment; omitted = assume it earns the discount rate |
| a posted 5-year fixed rate | `mortgage_rate` = effective annual: `(1 + r/2)^2 − 1`, then real if `mode: real` | the rate is held for the whole amortization — say that renewal risk is not modelled |
| "prices here grow 3%", "rent goes up 3%" | `value_growth_rate`, `rent_escalation_rate` — REAL in real mode; in nominal mode the engine ADDS `inflation_rate` on top | gate 3 |
| "I might move for work" | run the shorter horizon as a second config | no probabilistic exit in the engine |

## Cases → dispatch

Run everything from the repo root (the directory with `pyproject.toml`).
Write the user's config to `scenarios/<slug>.yaml` and render into
`scenarios/<slug>/` — `scenarios/` is git-ignored, so their numbers are never
committed.

| Case | Command |
|---|---|
| Contract question (what inputs exist / what's required) | `uv run hde --print-schema` |
| "Where did that number come from?" (any default's source, URL, band, what it replaced) | `uv run hde --print-anchors` |
| Quick estimate from a ready config | `uv run hde <config.yaml>` |
| Full answer with visuals (default for real questions) | `uv run hde <config.yaml> --story <dir>` |
| "What if I stayed N years / prices grew X / the price were Y?" — the flip point on any input | `uv run hde <config.yaml> --sweep years=5,10,15,20` · `--sweep condo.value_growth_rate=0:0.04:5` · `--sweep condo.initial_value=380000,400000,420000` (repeatable; `--no-monte-carlo` for speed) |
| Agent-consumable result | append `--json` (typed doc: verdict + assumptions + warnings + deterministic + MC, plus `sweeps` when asked) |
| Demographic prior run | use `examples/showcase_demographic_prior.yaml` as template (prior committed at `tests/fixtures/scenario_prior_golden.json`) |

**Example 1:**
Input: "I pay 2400/mo rent, similar condos go for 480k — is buying worth it over 15 years?"
→ One intake message (how they'd pay, fees, tax bill, purchase costs, income,
which numbers they're unsure of), author a config (schema first), set
`rent.invested_down_payment` to the buyer's down payment, run `--story` plus
a `--sweep` on the number they were least sure of, read back the verdict
headline, the `decisiveness:` line, the `defaults applied` list and every
warning, then the flip point.

**Example 2:**
Input: "what does the model need from me?"
→ `uv run hde --print-schema`, then ask for the REQUIRED fields (and satisfy
every `required_if`), then the owner costs, then which numbers they would not
bet on — never stop at the required fields alone.

**Example 3:**
Input: "why 3%? where does that come from?"
→ `uv run hde --print-anchors`, find the key (e.g. `rent.investment_return_rate`),
read back `source`, `rationale`, `band` and `replaces` in one paragraph.

## Judgment gates (reason HERE, not in the machinery)

1. **Decisiveness is not the headline.** Read `verdict.decisive` and
   `verdict.reason` (the text report's `decisiveness:` line). When it is not
   decisive, say the options are too close to call, quote the probability or
   the margin fraction, and name what would break the tie. A sweep read-back
   obeys the same rule at every point — "condo wins at every point" is false
   when a point is inside the tie band.
2. **Anything in `assumptions.defaults_applied` is a default, not the user's
   input.** Read the `defaults applied:` line back before the verdict; say
   the source for each. A `[neutral, uncited]` tag means the engine has NO
   evidence for that value (value growth, house maintenance). Zero growth
   warns whether defaulted or typed: the verdict is sensitive to it, so state
   a view or bracket it.
3. **Real vs nominal — the contract, not a vibe.** Defaults are REAL terms.
   In `mode: real` every rate you enter is real: convert a quoted nominal
   mortgage or growth rate first (real ≈ (1 + nominal)/(1 + 2.1%) − 1). In
   `mode: nominal` the engine keeps growth/escalation inputs as REAL and
   composes `inflation_rate` on top (that includes `investment_return_rate`);
   `discount_rate` and `mortgage_rate` are used as entered. Never type a sticker growth rate
   into nominal mode — it is inflated twice. `mortgage_rate` is an effective
   annual rate with annual payments; a Canadian posted rate compounds
   semi-annually — convert it (schema note).
4. **Like-for-like renter capital.** Put the buyer's down payment (all cash =
   the whole price) in `rent.invested_down_payment`; the engine charges it at
   year 0 and credits its terminal value, mirroring the buyer. Omitting it
   assumes the renter earns exactly the discount rate — say so if you do.
5. **A range is two configs.** When the user gives a range on a decision-
   relevant input (growth, horizon, price), bracket it — `--sweep` — and lead
   with whether the verdict survives the bracket; never quietly take the
   midpoint.
6. **Match the figure to their criterion.** Lowest expected cost → the
   verdict margin. Smallest worst case → turn the uncertainty inputs ON
   (`simulation.*_vol`, `price_shock`), label them illustrative, and read the
   p95 and `prob_*_cheapest`; with every vol at 0 the Monte Carlo is one
   repeated path and "P(x cheapest): 100%" means nothing was modelled. Most
   wealth at the end → compare `total_pv` (net cost including the terminal
   assets of both sides); `terminal_equity_pv` is a component, not the answer.
7. **Sanity line.** Beside the margin, state each side's annual unrecoverable
   cost (owner: interest + fees + tax + maintenance + amortised purchase and
   selling costs; renter: rent) from the breakdown. If the engine margin and
   that arithmetic disagree in sign, do not call the result decisive — report
   the discrepancy and the breakdown line that carries it.
8. **"Not modelled" is mandatory.** Every answer names what was left out
   (renewal risk, a financed insurance premium, rent control, taxes on the
   investment return, a probabilistic exit) with the direction of bias.

## The answer (what the user actually reads)

The verdict in words with its decisiveness · the two or three things it rests
on (from the breakdown and `defaults applied`) · the flip point from the sweep
· the sanity line · **Not modelled:** … · where the story is
(`scenarios/<slug>/STORY.md` and the act PNGs) · the one next step. No wall of
engine output; the report is on disk for anyone who wants it.

## Routine (deterministic — do not hand-reproduce)

Elicit → **Missing information** gate → config authoring → engine run (+ sweep)
→ **assumptions read-back** → warnings review → verdict with its decisiveness
→ story rendering → the answer. The CLI validates, refuses unknown keys with
did-you-mean, and renders the acts the config supports. Anything expressible
as one of the commands above is the engine's job, not a reasoning task.

## Verification

- Exit 0 AND every `[warning]` line addressed or surfaced to the user with the
  verdict (warnings are judgment gates in disguise, not noise): owner costs
  not modelled, zero appreciation, affordability breaches, real/nominal
  tripwires.
- `--story`: the dir holds STORY.md whose headline states the verdict in words,
  plus the acts the config supports — acts 1 and 2 always; act 4 ("Home-value
  futures") with an owned option; act 3 ("The uncertainty") only when at
  least one uncertainty input is on (a single-path run skips it); act 5
  ("Why", the demographic signal) only with `market_scenario:`; act 6 ("The
  market line", break-even rent) only with `rent` plus an owned option.
- `--json`: `engine_version`, `warnings`, `assumptions`, `verdict`,
  `deterministic`, `monte_carlo` keys present (`sweeps` when `--sweep` was
  given); every entry in `assumptions.defaults_applied` carries an `anchor`
  with a `source`.

## Escalation

- Config errors: show the user the exact message; values are their decision.
- Prior/geography refusal lists valid geographies — choose with the user.
- Trade execution, money movement, market timing: out of scope; this engine
  computes present-value comparisons only.

## Why only the CLI

hde holds no session state, needs no protocol gating, and every consumer has a
shell — an MCP layer would be pure context tax. The MCP server that existed
until 2026-09-01 was removed as superseded; this skill plus the CLI is the
whole surface.

Deeper guidance: `examples/README.md` in the repo walks every config template;
`docs/reference/ARCHITECTURE.md` carries the figure glossary (what every
printed number is and how it is computed).
