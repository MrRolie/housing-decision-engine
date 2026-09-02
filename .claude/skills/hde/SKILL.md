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
about, keep the answer under 200 words, and offer the deeper pass. With a
mortgage, an income and a threshold question together the never-drop list
needs 250–300 words: exceed the cap before dropping an item, and cut in this
order — the story path, the SOURCE of every default other than
`selling_cost_rate` (5%, WOWA) and the discount rate (those two are named in
one clause and never cut), the years bracket to one clause ("barely moves at
8 or 10 years" — and say once which end of their range is the base, "over 8
years, the short end of your 8–10", so every PV figure has a horizon), the
prior to two sentences, every reassurance phrase. The cap ranks what stays,
it never drops a warning: every default the engine warned on, each with its
rerun figure or its bias (the 1% real rent escalation default was dropped
in every 2026-09-02 dogfood run — the Québec continuing lease is ≈ 0% real, so
put `--sweep rent.rent_escalation_rate=0,0.01` in the same command and quote
the threshold at 0%) · verdict with its decisiveness · the flip point in
their units — and if it rests on an estimate you chose, quoted at both ends
of that estimate in the same sentence · the cash line (down payment +
purchase costs against the cash named, and the distance to the 20% line when
it is within one price step of it) · the affordability line · not modelled
with its bias — renewal risk with any mortgage, early exit, the renter's
investment taxes: cut words, never items · one next step. A dropped warning
fails the answer at any length; if the cap binds, the story path goes first
— it is never the item you keep while a warning goes. Ask the six things
plus the labelled defaults you will take in the same message — amortization
when only the term was quoted, the 3% real return, the rent escalation (1%
real; 0% for a Québec continuing lease), the maintenance figure — each as
"unless you say otherwise".

**One side known.** Most people arrive certain about one side and vague about
the other: "I'm looking at houses in Duvernay around $650k — what rent would
keep renting the better deal?", or "I pay $1,900; at what price is buying
worth it?", or "how long would I have to stay?". That is a threshold
question, not a verdict question: author the config with their known side
and a placeholder for the other (the engine needs a `monthly_rent` / an
`initial_value` to run — use their current rent or the middle of the price
band, and say so), then run `--break-even` on the unknown input and lead
with the threshold in their units: "renting is cheaper below $X/month, too
close to call between $A and $B, buying is cheaper above $B". Everything
property-specific they cannot know yet (tax, fees, maintenance, purchase
costs) is an estimate you label and, for the least certain one, sweep — the
threshold moves with it, so quote the threshold at both ends of that sweep.
When the user has no price-growth view, `value_growth_rate` is the least
certain estimate by construction (the engine's default is neutral, uncited).
Put `--sweep house.value_growth_rate=0:0.02:3 --no-monte-carlo` beside the
`--break-even` on the same command (the threshold pass is deterministic; the
flag keeps it fast): the engine re-solves the threshold at every sweep point
(the `across` block) and both ends go into the threshold sentence —
"renting is cheaper below $2,715 if Laval prices only track inflation, below
$1,864 if they grow 2%/yr above it — at 2% your $1,900 is a toss-up". Then
the same on the largest labelled dollar estimate (maintenance 1.2% vs 0.6%)
and on the warned rent-escalation default — several `--sweep` flags ride one
command, each giving its own `across` block. The brackets interact: a bracket
end that flips the verdict is a claim about a combination (gate 5), so state
what else that end assumes and quote it under the other maintenance figure
too — "at 2% growth your $1,900 puts buying ahead with 0.6% maintenance; with
1.2% the band is $1,961–$2,162 and renting still wins". Never call a single
base rate "the point estimate". A `market_scenario`
prior does NOT move `--break-even`: its drift enters the Monte Carlo only,
so the prior run answers "does the verdict at their rent survive the
demographic view?", never "where is the threshold?" — it is not the growth
sweep and does not replace it. The threshold sentence reads "A is cheaper
below the band's low edge, too close to call inside it, B is cheaper above
the high edge". Write: "renting is cheaper below $2,715/month, too close to
call between $2,715 and $2,993, buying is cheaper above $2,993." Never: "the
crossing is $2,850 — below that renting is cheaper; between $2,715 and $2,993
it's too close" — the crossing sits inside the band and the reader cannot
tell which clause wins on $2,715–$2,850. The engine's `sentence` field on
every break-even entry and `across` row is already band-first: quote it in
the user's units, and never write "above that" after a band — name the edge. The break-even is the deterministic
crossing; with any uncertainty input on, the verdict's decisiveness is the
Monte Carlo floor, so quote BOTH bands: the deterministic tie band from
`--break-even`, and the verdict's band from a densified `--sweep` on the
same input (the points where `decisive` is false), saying at which value
each side becomes decisive ("the Monte Carlo calls rent decisive up to
$2,750 and buying from $2,900, neither between"). The command for that
second band is the uncertainty config (prior or vols on, Monte Carlo on)
with `--sweep rent.monthly_rent=<band low − 10%>:<band high + 10%>:11
--json`; read `decisive`, `prob_best` and `mc_mean_best` per row and quote
where `decisive` flips ("under the Laval prior the Monte Carlo calls rent
decisive up to $2,300 and buying from $2,800, neither between $2,400 and
$2,700"). When the user's rent sits outside both bands one clause suffices;
when it sits inside either, both bands lead. With only the owned side
stochastic (a prior and `investment_return_vol` 0) the verdict's band sits
INSIDE the deterministic band and the engine warns `one-sided uncertainty`:
that means the probabilities are OVERconfident and the true toss-up zone is
wider — never "the simulation overstates the uncertainty". Cross-check the
sweep's `mean flip:` line on the same input. A price
break-even holds `down_payment` fixed (a fixed cash pile), so
the loan-to-value and any insurance premium change along the scan — say so.
If the engine reports that the config refuses part of the bracket (a price
below the down payment), quote the searched range, not the bracket asked for.

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
   rate (NAHB routine ≈ 0.6% of value, narrow; the examples use 1.2% = routine
   + the 1%-rule budgeting family — either is illustrative: name the one you
   take and sweep between them when it moves the threshold), the uncertainty
   vols. Say "I'll use X because
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
| a posted 5-year fixed rate | `mortgage_rate` = effective annual: `(1 + r/2)^2 − 1`, used AS IS in `mode: nominal` (gate 3: a mortgage means nominal mode — never a real conversion of the mortgage); `mortgage_term_years` is the AMORTIZATION (usually 25), never the 5-year term; when only the term product is quoted ("4.5% on a 5-year fixed") assume 25, label it in the intake as a default they can overrule (30 is allowed on an uninsured mortgage), never spend a follow-up on it | the rate is held for the whole amortization — say that renewal risk is not modelled (biases toward buying when rates are rising) |
| "prices here grow 3%", "rent goes up 3%", "my portfolio makes 6%" | `value_growth_rate`, `rent_escalation_rate`, `investment_return_rate` — a colloquial GROWTH or RETURN rate is a STICKER (nominal) figure unless the user says "above inflation": convert each to real, (1 + quoted)/(1 + 2.1%) − 1, before typing it (nominal mode composes inflation back on). The mortgage is the exception: its only conversion is compounding, (1 + r/2)² − 1, used as entered in nominal mode — never an inflation conversion | gate 3 |
| "I might move for work" | run the shorter horizon as a second config | no probabilistic exit in the engine |
| browsing a market, no specific property ("houses in <area> around $650k") | the price band is THEIR number (`--sweep` or `--break-even` across it); everything property-specific is an estimate you label — tax from the municipality's rate or "≈ x% of value (illustrative)", maintenance NAHB routine ≈ 0.6% of value or the examples' 1.2% (name which), fees typical for the building type, purchase costs ≈ 1.5% of price — and the least certain one gets a `--sweep` | say which figures are estimates and that a real listing's tax bill and fees replace them |

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
| "What rent keeps renting the better deal?" / "at my rent, what price makes buying worth it?" / "how long before buying wins?" — the threshold on ONE input | `uv run hde <config.yaml> --break-even rent.monthly_rent` · `--break-even condo.initial_value` · `--break-even years=3:30` (solves the crossing and the tie-band edges; two priced options only; money inputs get a ¼×–4× bracket by default, anything else takes `=lo:hi`) |
| Agent-consumable result | append `--json` (typed doc: verdict + assumptions + warnings + deterministic + MC, plus `sweeps` / `break_evens` when asked) |
| Demographic prior run (Québec only — the shipped prior carries `MTL_RMR`, `MTL_ISLAND_RA06`, `LAVAL_RA13`, `QC_RMR`, `HORS_RMR`; use the finest geography that contains the user's area — Laval → `LAVAL_RA13`, the island → `MTL_ISLAND_RA06`, the rest of the metro → `MTL_RMR`, Québec City → `QC_RMR`, outside any CMA → `HORS_RMR` — and say which) | copy the `market_scenario` block from `examples/showcase_demographic_prior.yaml` (prior committed at `tests/fixtures/scenario_prior_golden.json`); Monte Carlo must be on — the prior ADDS its drift to `value_growth_rate` there only; the deterministic line uses the base alone. With no user view leave the base at the engine default (0, it warns) so the prior is the growth view; a non-zero base is a second view stacked on the prior — label it and sweep it. Runs in either mode (the drift is real; nominal mode composes it), so a financed buyer keeps `mode: nominal`. With a `rent` option set `simulation.investment_return_vol: 0.10` (≈ 60/40 portfolio) or the engine warns `one-sided uncertainty` — the prior makes the house stochastic while the renter's PV stays a point, and the probabilities read overconfident. On a threshold question the prior informs the verdict band only; the break-even does not move |

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
   back. On a threshold question the prior informs the verdict band only (a
   break-even is deterministic and does not move), so the growth sweep in
   "One side known" still runs. Say what growth the prior encodes — the run's
   `demographic prior:` assumptions line prints the reference drift for the
   bands the horizon touches (all bands and the scenario range are in
   `--json` under the prior's provenance `encoded_drift`) — so a flat prior is
   never introduced as "instead of flat prices". Quote only the bands inside
   the horizon: an 8-year run from 2026 touches 2030 and 2035, never a 2050
   figure for a 2034 exit.
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
   Every colloquial GROWTH or RETURN rate a member of the public quotes —
   price growth, rent growth, portfolio return — is a sticker rate unless they
   say "above inflation": convert each to real before typing it. The mortgage
   is the exception: its only conversion is compounding (posted → effective
   annual); in nominal mode it is used as entered, never inflation-converted.
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
   principal − appreciation + amortised purchase and selling costs. In
   nominal mode with 0% real growth that figure is inflation on the sticker
   value: say "$13,650 is inflation, not real gain" and keep the report's
   "not cash" label — never "$X goes to appreciation" beside "flat prices".
   Only when the breakdown's `terminal_equity_pv` does not explain the gap is
   there a discrepancy to report.
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
run when there is a mortgage — the engine's ratio is housing cost including
maintenance over income: GDS-shaped with a broader numerator and no other
debts, so compare it to CMHC's 39% GDS cap, never the 44% TDS cap unless
other debts were asked, and never soften an engine "exceeds" warning to "not
a breach" without saying which threshold each refers to · **every uncertainty input and every cost you
proposed** (a crash hazard, a vol, an illustrative insurance figure) named in
the user's text with its label ("illustrative, not cited") and what it sets
("this is what makes the p95") · **No source for:** every figure you had to
estimate because neither the user nor the anchor registry had it (a
property-tax rate, an insurance quote, a purchase-cost rate) — said plainly,
never filled silently; this line is what the engine anchors next · **Not modelled:** each item with its
direction of bias ("renewal risk — biases toward buying") · where the story
is (`scenarios/<slug>/STORY.md` and the act PNGs) · the one next step. Under
500 words (under 200 on the quick-sense lane, 300 when its never-drop list forces it); the report is on disk for
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
