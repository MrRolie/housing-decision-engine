---
name: hde
description: Runs rent-vs-buy housing decision analyses with the housing-decision-engine (hde) CLI. Use when the user asks whether to rent or buy, whether buying a house or condo is worth it, compares renting vs buying costs, mentions a mortgage decision, wants a present-value comparison of housing options, asks about demographic or population-driven housing scenarios, or mentions hde. Also use for casual phrasings like "should I keep renting?", "is buying in Montréal/Gatineau worth it?", or any housing-cost-vs-alternatives question, even if hde is not named.
---

# HDE — housing decision engine (skill + CLI dispatch contract)

## Activation

Any housing-decision question: rent vs buy, condo vs house, "is it worth it",
demographic-informed price outlooks. The engine is the `hde` CLI at
`~/ai_system/projects/housing-decision-engine` (standalone; needs only `uv`).

## Elicit first (before authoring anything)

The engine answers the question the config asks. Get to know the person before
you write a config — five questions, in their language, each deciding something:

1. **How long do you expect to stay, and how sure are you?** → `years`. Under
   five years the selling cost dominates and the engine warns; if they are not
   sure, run a second config at the shorter horizon and show both verdicts.
2. **Might you need the money back, or move for work?** → horizon sensitivity
   again, and whether an all-cash purchase is even the right shape.
3. **What does "best" mean to you — lowest expected cost, smallest worst case,
   or most wealth at the end?** → which figure is the answer: the `verdict`
   margin (expected cost), the Monte Carlo p95 and `prob_*_cheapest` (worst
   case), or `terminal_equity_pv` (wealth at horizon). Say which one you used.
4. **What is your income, and how stable is it?** → an `income` block turns on
   affordability ratios; a pay cut they fear is a `pay_drop_events` entry.
5. **Which uncertainties actually matter to you?** → the `simulation` vols
   (maintenance, fees, rent escalation, investment return) and `price_shock`.
   With every vol at 0 the Monte Carlo is one repeated path: "P(x cheapest):
   100%" then means "nothing was modelled", not "certain".

Then gather the schema keys: consult `--print-schema` for exact keys, the
`required` flags, and `required_if` (an owned option must declare
`all_cash: true` OR the full mortgage block). Describe the schema only from
that output, never from memory. Invent no values: a plausible invented growth
rate produces a confident-looking wrong verdict, the exact failure this
engine exists to prevent. Every number you do not ask for becomes a default
the engine echoes back with its source.

## Cases → dispatch

Run everything from the repo root: `cd ~/ai_system/projects/housing-decision-engine`

| Case | Command |
|---|---|
| Contract question (what inputs exist / what's required) | `uv run hde --print-schema` |
| "Where did that number come from?" (any default's source, URL, band, what it replaced) | `uv run hde --print-anchors` |
| Quick estimate from a ready config | `uv run hde <config.yaml>` |
| Full answer with visuals (default for real questions) | `uv run hde <config.yaml> --story <dir>` |
| Agent-consumable result | append `--json` (typed doc: verdict + assumptions + warnings + deterministic + MC) |
| Demographic prior run | use `examples/showcase_demographic_prior.yaml` as template (prior committed at `tests/fixtures/scenario_prior_golden.json`) |

**Example 1:**
Input: "I pay 2400/mo rent, similar condos go for 480k — is buying worth it over 15 years?"
→ Ask the five questions above, author a config (schema first), set
`rent.invested_down_payment` to the buyer's equivalent down payment, run
`--story`, read back the verdict headline, the `decisiveness:` line, the
`defaults applied` list and every warning.

**Example 2:**
Input: "what does the model need from me?"
→ `uv run hde --print-schema`, then ask for the REQUIRED fields (and satisfy
every `required_if`), then ask which uncertainties matter — never stop at the
required fields alone.

**Example 3:**
Input: "why 3%? where does that come from?"
→ `uv run hde --print-anchors`, find the key (e.g. `rent.investment_return_rate`),
read back `source`, `rationale`, `band` and `replaces` in one paragraph.

## Judgment gates (reason HERE, not in the machinery)

1. **Decisiveness is not the headline.** Read `verdict.decisive` and
   `verdict.reason` (the text report's `decisiveness:` line). When it is not
   decisive, say the options are too close to call, quote the probability or
   the margin fraction, and name what would break the tie (a stated
   maintenance rate, a longer horizon, the renter's capital).
2. **Anything in `assumptions.defaults_applied` is a default, not the user's
   input.** Read the `defaults applied:` line back before the verdict; say the
   source for each; a `[neutral, uncited]` tag means the engine has NO evidence
   for that value and the user must supply a view (value growth, house
   maintenance).
3. **Real vs nominal coherence.** Defaults are REAL terms. Users quoting
   market mortgage/growth rates are usually thinking nominal. Resolve by
   converting or setting `economic.mode: nominal` — the engine's `[warning]`
   lines flag exactly this mismatch, so read them and settle it with the user.
   `mortgage_rate` is an effective annual rate with annual payments; a
   Canadian posted rate compounds semi-annually — convert it (schema note).
4. **Like-for-like renter capital.** If the buyer puts money down (all-cash
   means the whole price), the renter's equivalent capital belongs in
   `rent.invested_down_payment`; otherwise the comparison charges the buyer's
   capital while letting the renter's vanish — the engine warns precisely
   because this silently biases the verdict.

## Routine (deterministic — do not hand-reproduce)

Elicit → config authoring → engine run → **assumptions read-back** → warnings
review → verdict with its decisiveness → story rendering. The CLI validates,
refuses unknown keys with did-you-mean, and renders the acts the config
supports. Anything expressible as one of the commands above is the engine's
job, not a reasoning task.

## Verification

- Exit 0 AND every `[warning]` line addressed or surfaced to the user with the
  verdict (warnings are judgment gates in disguise, not noise).
- `--story`: the dir holds STORY.md whose headline states the verdict in words,
  plus the acts the config supports — acts 1–4 always; act 5 ("Why", the
  demographic signal) only with `market_scenario:`; act 6 ("The market line",
  break-even rent) only with `rent` plus an owned option.
- `--json`: `engine_version`, `warnings`, `assumptions`, `verdict`,
  `deterministic`, `monte_carlo` keys present; every entry in
  `assumptions.defaults_applied` carries an `anchor` with a `source`.

## Escalation

- Config errors: show the user the exact message; values are their decision.
- Prior/geography refusal lists valid geographies — choose with the user.
- Trade execution, money movement, market timing: out of scope; this engine
  computes present-value comparisons only.

## Why no MCP

Per the stack's TOOL-SURFACES doctrine: hde holds no session state, needs no
protocol gating, and its consumers have shells — MCP would be pure context tax.
The server code remains for non-shell consumers (claude.ai web) but the CLI is
the registered surface.

Deeper guidance: `examples/README.md` in the repo walks every config template;
`docs/reference/ARCHITECTURE.md` carries the figure glossary (what every
printed number is and how it is computed).
