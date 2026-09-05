# Asking the engine — example prompts

Open Claude Code in this folder (`claude`) and ask a housing question in plain words. A run
takes seconds; the first one also fetches the engine's dependencies, which depends on your
connection.
Claude runs the engine for you: it asks once for whatever your question is missing,
writes your scenario to `scenarios/` (git-ignored, so your numbers stay yours), runs it,
and gives the verdict with the lines that back it. This page shows what you can ask and
what to put in your first message so the first answer is the good one.

## What you can ask

| You want to know | Ask it like this |
|---|---|
| Should I buy this place? | *"Thinking of buying a condo in Griffintown listed at $485k, fees $410/month. I rent for $1,850 right now. Is buying it a good idea?"* |
| At what price does buying win? | *"We rent a 5½ in Rosemont for $2,150 and it's fine. At what house price would buying actually make sense for us?"* |
| What rent keeps renting ahead? | *"I'm looking at houses in Duvernay, Laval for around $650k. What would my rent have to be for renting to stay the better deal?"* |
| Is renting forever a mistake? | *"Honestly, is it dumb to just rent forever? Everyone says I'm throwing money away. Just give me the gist."* |
| Condo or house? | *"A condo at $520k with $450 fees, or a house at $680k — which costs us less over the next ten years?"* |
| Can we afford it? | *"We're looking at a townhouse in Barrhaven, Ottawa for $720k. We rent for $2,700 and have $144k saved. Is it worth buying?"* |

A question with a listing, a price or a date gets a full run with the threshold that
matters to it (the price or rent where the answer flips). So does any question that asks
*at what price* or *what rent*: that is a threshold question even with no listing in view,
and it gets the full run with its threshold, not the short shape. A question with none of
those gets a short answer built around one conditional, and the offer to go deeper.

## How to ask — what to put in the first message

Claude will ask for anything missing in one message, so you can also just start and
answer the form. Front-loading these saves that round trip:

- **How long you expect to stay**, as a range if you are not sure ("6 to 8 years"). The
  answer is checked at both ends. Selling at the end of that horizon is priced, including a
  default selling cost (commission and notary) that you can replace with your own figure.
- **How you would pay: the cash you have for day one, as a dollar amount**, not a
  percentage. Closing costs, the welcome or land-transfer tax and any mortgage-insurance
  premium tax come out of that same pile; the engine nets them and prints the down payment
  that is left and the share of the price the mortgage covers. Say whether that amount
  already includes the closing costs, or give the two amounts ("$60k all in", or "$52k for
  the down payment plus $8k for closing"). If you have a mortgage quote, give the rate and
  the amortization ("4.65% five-year fixed, 25 years").
- **Province and city**, and whether this is your first home. Québec and Ontario transfer
  taxes (Montréal and Toronto municipal) and the insurance-premium tax are priced from the
  published schedules; the first-time-buyer rebate is applied where one is sourced.
- **Your rent today** and roughly how it has been rising.
- **Owner costs if you have them**: the property-tax bill, home or unit insurance, condo
  fees. "No idea" is fine: the engine takes a labelled default or a placeholder and the
  answer names it as such, so you can replace it later.
- **Whether the place carries a monthly fee.** A condo does; a townhouse may or may not
  (a freehold has none, one under a syndicate or condo corporation does). Say which, or say
  you don't know and both get run, each with its own verdict.
- **Your income**, if you want the affordability check (housing cost against income).
- **What "best" means to you**: lowest expected cost, smallest worst case, or most
  wealth at the end. Different figures answer different questions.
- **Which of your numbers you trust least.** Those get swept, so the answer says whether
  they change the verdict.

Two phrases do specific things. *"No idea"* on any item makes it a labelled default you
can overrule. *"Just the gist"* shortens the prose and the read-back block to its short
form; the block still comes, because it is what lets you check the short answer.

## What comes back

1. **The verdict with its decisiveness.** With uncertainty inputs on, "decisive" means the
   winning option is cheapest in at least 65% of the simulated futures; on a single-path run
   (no uncertainty inputs) it means the winner's margin is at least 5% of the cheaper
   option's cost. Below either line it is "too close to call", and the answer says which
   rule it rests on and what would tip it: a price, a rent, a horizon, or a view on price
   growth.
2. **A threshold sentence** when your question has one: the price (or rent) where the two
   options tie, with the band around it where the difference is inside the noise.
3. **Every estimate labelled.** Each number carries who supplied it: you, a published
   figure the engine cites by name, or an estimate Claude typed for you, with the direction
   it biases the verdict. What could not be sourced is said plainly ("no source for an
   Ottawa property-tax rate; 1.0% of value is a placeholder").
4. **The READ-BACK block, pasted verbatim at the end.** The engine assembles it: every
   warning, which inputs you stated and which were typed for you, the defaults applied,
   the financing line, affordability, and any threshold or sweep lines. It is there so you
   can check the answer against the run instead of trusting the prose. A gist answer ends
   with the short block — every warning, which inputs were typed for you, the decisiveness
   rule — and one line offering the full one (ask, or run `--read-back full` yourself).

## Follow-ups you can ask

- *"What if rates are 6% when we renew?"*
- *"What if we stay 15 years instead?"*
- *"At what price would this flip?"* or *"What rent would flip it?"*
- *"Use my actual property-tax bill: $3,400."*
- *"What did you assume for price growth, and what if it's zero?"*
- *"Show me the story"* — six plots: the verdict, the cost race, uncertainty, home-value
  futures, the demographic signal, the break-even line.
- *"Give me the run as JSON"* — the full result document, for your own tooling.

## Without Claude

The engine is a command-line tool and everything above is available directly:

```bash
uv run hde examples/basic_config.yaml                 # a worked scenario
uv run hde --print-schema                             # every input, what is required, every note
uv run hde --print-anchors                            # where every default comes from, with dates
uv run hde examples/mortgage_house_vs_rent.yaml --break-even rent.monthly_rent
uv run hde examples/basic_config.yaml --read-back     # only the lines an honest answer must carry
uv run hde examples/basic_config.yaml --read-back short   # the gist: warnings, sources, decisiveness
uv run hde examples/basic_config.yaml --json          # the full result document
```

[examples/README.md](examples/README.md) walks through the scenario files in reading order.

## What it does not do (yet)

- **Mortgage renewal risk.** The quoted rate is held for the whole horizon; a design
  exists but is not built. When rates rise, this biases the answer toward buying. Ask the
  "what if rates are 6%" follow-up to see the exposure.
- **Property tax outside Laval, Montréal, Québec City and Toronto.** Gatineau and Ottawa
  have no registered source; any figure used there is a labelled placeholder until you
  supply your bill.
- **Transfer tax and insurance-premium tax outside Québec and Ontario.** Elsewhere you
  supply the closing-cost number.
- **Rental income.** A duplex you partly rent out is priced as a home you occupy entirely.
- **Tax, legal or mortgage advice.** The engine compares present-value costs under stated
  assumptions. Every published figure it uses carries its source and date
  (`uv run hde --print-anchors`); where a source has a scheduled change (Québec's
  insurance-premium tax rises after 2026-12-31), the entry says so.
