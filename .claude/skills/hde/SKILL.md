---
name: hde
description: Runs rent-vs-buy housing decision analyses with the housing-decision-engine (hde) CLI. Use when the user asks whether to rent or buy, whether buying a house or condo is worth it, compares renting vs buying costs, mentions a mortgage decision, wants a present-value comparison of housing options, asks about demographic or population-driven housing scenarios, or mentions hde. Also use for casual phrasings like "should I keep renting?", "is buying in Montréal/Gatineau worth it?", or any housing-cost-vs-alternatives question, even if hde is not named.
---

# HDE — housing decision engine (skill + CLI dispatch contract)

## Activation

Any housing-decision question: rent vs buy, condo vs house, "is it worth it",
demographic-informed price outlooks. The engine is the `hde` CLI at
`~/ai_system/projects/housing-decision-engine` (standalone; needs only `uv`).

## Cases → dispatch

Run everything from the repo root: `cd ~/ai_system/projects/housing-decision-engine`

| Case | Command |
|---|---|
| Contract question (what inputs exist / what's required) | `uv run hde --print-schema` |
| Quick estimate from a ready config | `uv run hde <config.yaml>` |
| Full answer with visuals (default for real questions) | `uv run hde <config.yaml> --story <dir>` |
| Agent-consumable result | append `--json` (typed doc: deterministic + MC + warnings) |
| Demographic prior run | use `examples/showcase_demographic_prior.yaml` as template (prior committed at `tests/fixtures/scenario_prior_golden.json`) |

**Example 1:**
Input: "I pay 2400/mo rent, similar condos go for 480k — is buying worth it over 15 years?"
→ Author a config (schema first), set `rent.invested_down_payment` to the buyer's
equivalent down payment, run `--story`, read the verdict headline + warnings back.

**Example 2:**
Input: "what does the model need from me?"
→ `uv run hde --print-schema`, then ask the user for the REQUIRED fields only.

## Judgment gates (reason HERE, not in the machinery)

1. **Gathering inputs is the model's job.** Users give partial facts (salary,
   rent, target price, down payment). Ask for what's missing; consult
   `--print-schema` for exact keys and REQUIRED flags. Describe the schema only
   from that output, never from memory — docs rot and keys drift, and a
   guessed key is refused anyway (better to check than to fail the run).
   Invent no values: a plausible invented growth rate produces a
   confident-looking wrong verdict, the exact failure this engine exists to
   prevent.
2. **Real vs nominal coherence.** Defaults are REAL terms. Users quoting
   market mortgage/growth rates are usually thinking nominal. Resolve by
   converting or setting `economic.mode: nominal` — the engine's `[warning]`
   lines flag exactly this mismatch, so read them and settle it with the user.
3. **Like-for-like renter capital.** If the buyer puts money down, the renter's
   equivalent capital belongs in `rent.invested_down_payment`; otherwise the
   comparison charges the buyer's capital while letting the renter's vanish —
   the engine warns precisely because this silently biases the verdict.

## Routine (deterministic — do not hand-reproduce)

Config authoring → engine run → warnings review → story rendering. The CLI
validates, refuses unknown keys with did-you-mean, and renders all five acts.
Anything expressible as one of the commands above is the engine's job, not a
reasoning task.

## Verification

- Exit 0 AND every `[warning]` line addressed or surfaced to the user with the
  verdict (warnings are judgment gates in disguise, not noise).
- `--story`: the dir holds act1..act5 PNGs + STORY.md whose headline states the
  verdict in words.
- `--json`: `warnings` + `deterministic` + `monte_carlo` keys present.

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

Deeper guidance: `examples/README.md` in the repo walks every config template.
