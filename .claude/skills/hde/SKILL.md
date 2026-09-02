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
2. **How would you pay, and how much cash do you have for day one?** → all
   cash, or down payment + quoted rate + amortization (the mortgage block);
   the down payment AND the purchase costs come out of that cash, so ask for
   the amount, not a percentage; a down payment under 20% means a
   mortgage-insurance premium (financed_purchase_costs).
3. **What does "best" mean to you — lowest expected cost, smallest worst case,
   or most wealth at the end?** → which figure is the answer (gate 6).
4. **What is your income, and how stable is it?** → an `income` block turns on
   affordability ratios; a pay cut they fear is a `pay_drop_events` entry.
5. **Which of your numbers are you least sure of?** → those get a `--sweep`.
   (Never ask a member of the public "which uncertainties matter"; ask which
   numbers they would not bet on.)

**Quick-sense lane.** If the user asks for a quick sense ("not a spreadsheet"),
ask only six things in one message — dwelling, rent, price, how they'd pay,
horizon, income — decide the sweep yourself from whatever they were vague
about, keep the answer under 200 words, and offer the deeper pass. The cap
ranks what stays, it never drops a warning: verdict with its decisiveness ·
the flip point in their units · the affordability line · not modelled with
its bias (renewal risk with any mortgage; every defaulted escalation the
engine warned on) · one next step. Defaults' provenance beyond the two
largest and the story path can go; a warning cannot.

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
question per turn, and never a run on guessed numbers. Group it into four
lines they can answer in one reply — (1) how long, how they'd pay and the
cash they have for day one; (2) fees, tax, insurance, closing costs; (3)
income; (4) what "best" means and any view on prices — and put every
modelling default you will take in the same message as a labelled default
they can overrule ("I'll take 25 years and the engine's 3% real return unless
you say otherwise"). Six asks on the quick-sense lane. When their answers open a
new question — the arithmetic does not close (down payment + purchase costs
above the cash they named), or one number contradicts another — ONE follow-up
is right; a config built on a contradiction is worse than a second message.
One exception needs no follow-up: when the shortfall is smaller than the
mortgage-insurance premium it would trigger, run BOTH branches — "you find
the cash" and "insured mortgage at the lower down payment" — as two configs
and read back both verdicts; the user chooses between outcomes, not
between questions.

1. **Which options the question implies** → which sections: "keep renting or
   buy a condo" = `rent` + `condo`; "house or condo" = `condo` + `house`;
   "is buying worth it" with no dwelling named = ask which.
2. **The user's own numbers — always theirs, never yours:** monthly rent;
   purchase price; condo fees; how they would pay (all cash, or down payment +
   quoted mortgage rate + amortization) and the cash they actually have for
   year 0 (down payment + purchase costs must fit in it); how long they plan
   to stay; income if they care about affordability; **owner costs — the property tax bill, home
   or unit insurance, and purchase costs (welcome/land-transfer tax, notary,
   inspection, mortgage-insurance premium)** — "give me the number, a guess
   I'll label, or say skip and I'll report it as not modelled". If they
   cannot give one, offer to bracket it (two configs) rather than pick for
   them. Exception — purchase costs when they named the cash they have: "no
   idea" must NOT become `purchase_costs: 0`; take the examples' illustrative
   figure (welcome/land-transfer tax + notary ≈ 1.5% of price, labelled
   illustrative), deduct it from their cash to get the real down payment,
   and recompute the loan-to-value band and the insurance premium from that
   — closing costs come out of the same pile as the down payment.
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
| mortgage-insurance premium rolled into the loan (<20% down) | `financed_purchase_costs` (owned option) — added to the loan principal, so it raises the payment and the balance; the provincial tax on the premium is cash → `purchase_costs` | the premium schedule is not in the engine yet: compute it, say so, label it |
| roof, appliances, special assessment, moving costs | `events` `{name, base_cost, expected_year}` | one-offs during the horizon; they DO enter that year's affordability ratio |
| realtor commission + notary at sale | `selling_cost_rate` (default 5%, WOWA 2026) | dominates short horizons |
| the money the renter keeps instead of buying | `rent.invested_down_payment` + `investment_return_rate` | charged at year 0 and credited at its terminal value, exactly like the buyer's down payment; omitted = assume it earns the discount rate |
| a posted 5-year fixed rate | `mortgage_rate` = effective annual: `(1 + r/2)^2 − 1`, used AS IS in `mode: nominal` (gate 3: a mortgage means nominal mode — never a real conversion of the mortgage); `mortgage_term_years` is the AMORTIZATION (usually 25), never the 5-year term | the rate is held for the whole amortization — say that renewal risk is not modelled (biases toward buying when rates are rising) |
| "prices here grow 3%", "rent goes up 3%", "my portfolio makes 6%" | `value_growth_rate`, `rent_escalation_rate`, `investment_return_rate` — a colloquial rate is a STICKER (nominal) figure unless the user says "above inflation": convert every one of them the same way, real ≈ (1 + quoted)/(1 + 2.1%) − 1 — never just the mortgage | gate 3 |
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
| Demographic prior run (Montréal only — `MTL_RMR` is the one geography shipped) | copy the `market_scenario` block from `examples/showcase_demographic_prior.yaml` (prior committed at `tests/fixtures/scenario_prior_golden.json`); Monte Carlo must be on — the prior adds drift there only; it runs in either mode (the drift is real; nominal mode composes it), so a financed buyer keeps `mode: nominal` |

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
   a view or bracket it. When the user has no view on price growth and the
   market is Montréal, do not hand the question back: run a second config
   with the shipped demographic prior (dispatch table) and lead with whether
   the verdict survives it; only a market with no prior gets the question
   back.
3. **Real vs nominal — the contract, not a vibe.** Defaults are REAL terms.
   **With a mortgage, run `mode: nominal`:** `economic: {mode: nominal,
   inflation_rate: 0.021}`, `mortgage_rate` = the quoted rate's effective
   annual (no real conversion), `discount_rate` omitted — the engine composes
   its 3% real default with inflation (5.2%) and echoes it — or typed as
   (1 + real)(1 + 2.1%) − 1. Growth, escalation and return inputs stay REAL
   in nominal mode and the engine composes `inflation_rate` on top (that
   includes `investment_return_rate`); never type a sticker growth rate into
   nominal mode — it is inflated twice. Why nominal: the lender collects the
   NOMINAL payment; a real-rate level payment understates year-1 cash by about
   a fifth and hides GDS/TDS breaches (the engine warns when a mortgage runs
   in real mode with an income). `mode: real` is for all-cash and rent-only
   comparisons, where every rate you enter is real (real ≈ (1 + nominal)/
   (1 + 2.1%) − 1). `mortgage_rate` is an effective annual rate with annual
   payments; a Canadian posted rate compounds semi-annually — convert it
   (schema note).
   Every colloquial rate a member of the public quotes — mortgage, price
   growth, rent growth, portfolio return — is a sticker rate unless they say
   "above inflation"; convert them ALL with the same formula, never just the
   mortgage.
4. **Like-for-like renter capital.** Put the buyer's total year-0 cash —
   down payment + purchase costs (all cash = the whole price + purchase costs)
   — in `rent.invested_down_payment`; the engine charges it at
   year 0 and credits its terminal value, mirroring the buyer. Omitting it
   assumes the renter earns exactly the discount rate — say so if you do.
   When the return equals the discount rate the capital term nets to zero in
   PV (the breakdown shows +D and −D): never describe the renter's capital as
   a drag or an advantage; a spread is the engine's capital-spread warning,
   and only that warning says which way it cuts.
5. **A range is two configs.** When the user gives a range on a decision-
   relevant input (growth, horizon, price), bracket it — `--sweep` — and lead
   with whether the verdict survives the bracket; never quietly take the
   midpoint. Author brackets in the USER's units and include their stated
   value, zero in their units (flat sticker prices = −2.1% real) and one step
   below; read the flip point back in their units. The flip point is the
   engine's `flip:` line — the bracket between two run points; if that
   bracket is too coarse to act on, densify with the range form
   (`--sweep key=lo:hi:n`) and rerun — never interpolate a flip from two
   points. The tie band is a range too: quote the points where `decisive` is
   false ("too close to call between X and Y"). Every flip point in the
   answer is stated under the user's criterion: with uncertainty on and
   "lowest expected cost" as the criterion, the flip is the sweep's `mean
   flip:` line (`mc_mean_flips` in JSON), not the deterministic `flip:` —
   never mix the two in one answer, and say when the mean never changes
   sides across the bracket. "It would not flip" about an input you did not
   sweep is a guess — sweep it, or write "not run"; the same for any claim
   about a combination of inputs (edit the config and sweep the second key).
6. **Match the figure to their criterion.** Lowest expected cost → the
   verdict margin — but with any uncertainty input on, "expected cost" is the
   Monte Carlo MEAN: read `verdict.mc_mean_best` (the report's `mean` per
   option) and when it disagrees with `best` say so with both means (the
   `reason` line carries the clause); "too close to call" survives, the sign
   does not go unmentioned. When the mean disagrees only because of an
   uncertainty input YOU chose (a crash hazard, a vol), say that the input is
   yours and sweep it (`--sweep condo.price_shock.annual_hazard=…`) so the
   user sees where their fear starts to matter. Smallest worst case → turn the uncertainty inputs ON
   (`simulation.*_vol`, `price_shock`), label them illustrative, and read the
   p95 and `prob_*_cheapest`. `investment_return_vol` is the ANNUAL volatility
   of the renter's return (0.10 ≈ a 60/40 portfolio, 0.16 ≈ equities); with a
   `price_shock` on the owned side and 0 here the renter's capital cannot lose
   — the engine warns, so set both or neither; with every vol at 0 the Monte Carlo is one
   repeated path and "P(x cheapest): 100%" means nothing was modelled. Most
   wealth at the end → compare `total_pv` (net cost including the terminal
   assets of both sides); `terminal_equity_pv` is a component, not the answer.
7. **Cash line — cash is not PV.** Beside the $/month PV equivalent, quote
   the report's `Year-1 cash` line: each side's year-1 outlay, the principal
   repaid, and the owner's unrecoverable cash (cash − principal, plus the
   purchase and selling costs amortised over the horizon). The owner usually
   pays MORE cash per month while the PV verdict favours buying — that is
   equity at sale being credited, not a defect: say "you pay $X/month more
   in cash; buying still wins by $Y in present value because you leave with
   equity". The line's `expected appreciation` figure is the term a
   cash-only comparison omits (in nominal mode the levered asset grows with
   inflation while the debt does not): owner economic cost ≈ cash −
   principal − appreciation + amortised purchase and selling costs. Only when
   the breakdown's `terminal_equity_pv` does not explain the gap is there a
   discrepancy to report.
8. **"Not modelled" is mandatory.** Every answer names what was left out
   (renewal risk, a financed insurance premium, rent control, taxes on the
   investment return, a probabilistic exit) with the direction of bias. With
   a mortgage, renewal risk is always on the list (the quoted rate is held
   for the whole amortization — biases toward buying when rates are rising),
   and so is any default the engine warned on (a 1% real rent escalation
   defaulted for a Québec continuing lease biases toward buying); "no chance
   you move early" biases toward buying too (an early exit pays the selling
   cost sooner) — every item gets a direction, none gets none.

## The answer (what the user actually reads)

The verdict in words with its decisiveness · the two or three things it rests
on (from the breakdown and `defaults applied`; the owner's driver is always
"equity at sale = value after growth × (1 − selling cost) − remaining
mortgage; purchase and selling costs are sunk; the renter's capital is
credited at its terminal value too" — never "closing costs come back as
equity" or "renting has no equity") · the cash line (gate 7) and the year-0
cash total the config commits · the two largest engine-set
numbers whenever an owned option is present — `selling_cost_rate` (5%, WOWA)
and the discount rate — named with their source · the flip point from the
sweep, in the user's units · the sanity line · the affordability line (max
ratio and breach years) whenever an income was given, from the nominal-mode
run when there is a mortgage · **every uncertainty input and every cost you
proposed** (a crash hazard, a vol, an illustrative insurance figure) named in
the user's text with its label ("illustrative, not cited") and what it sets
("this is what makes the p95") · **Not modelled:** each item with its
direction of bias ("renewal risk — biases toward buying") · where the story
is (`scenarios/<slug>/STORY.md` and the act PNGs) · the one next step. Under
500 words (under 200 on the quick-sense lane); the report is on disk for
anyone who wants it.

## Routine (deterministic — do not hand-reproduce)

Elicit → **Missing information** gate → config authoring → engine run (+ sweep)
→ **assumptions read-back** → warnings review → verdict with its decisiveness
→ story rendering → the answer. The CLI validates, refuses unknown keys with
did-you-mean, and renders the acts the config supports. Anything expressible
as one of the commands above is the engine's job, not a reasoning task.

## Verification

- Exit 0 AND every `[warning]` line addressed or surfaced to the user with the
  verdict (warnings are judgment gates in disguise, not noise): owner costs
  not modelled, zero appreciation, affordability breaches, a mortgage run in
  real mode (the cash ratio is higher — rerun nominal), real/nominal
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
