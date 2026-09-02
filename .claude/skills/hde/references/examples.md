# Worked examples

**Example 1:**
Input: "I pay 2400/mo rent, similar condos go for 480k — is buying worth it over 15 years?"
→ One intake message (how they'd pay and the cash for day one, fees, tax bill,
purchase costs, income, which numbers they're unsure of), author a config
(schema first), set `rent.invested_down_payment` to the buyer's total year-0
cash (down payment + purchase costs — gate 4), run `--story` plus a `--sweep`
on the number they were least sure of, then the answer checklist: every
warning, `defaults applied`, the `decisiveness:` line, the flip point.

**Example 2:**
Input: "what does the model need from me?"
→ `uv run hde --print-schema`, then ask for the REQUIRED fields (and satisfy
every `required_if`), then the owner costs, then which numbers they would not
bet on — never stop at the required fields alone.

**Example 3:**
Input: "why 3%? where does that come from?"
→ `uv run hde --print-anchors`, find the key (e.g. `rent.investment_return_rate`),
read back `source`, `rationale`, `band` and `replaces` in one paragraph.

**Example 4 (threshold):**
Input: "I'm looking at houses in Duvernay, Laval for around 650k — what would
my rent have to be for renting to stay the better deal?"
→ `references/threshold-lane.md`: the price is their number, `monthly_rent`
is a placeholder (their current rent, said so), one command with
`--break-even rent.monthly_rent` and the growth, maintenance and
rent-escalation sweeps beside it; a second config with the `LAVAL_RA13` prior
and `investment_return_vol: 0.10` for the verdict band at their rent; the
answer leads with the band-first threshold at both ends of the growth
bracket, then the checklist.
