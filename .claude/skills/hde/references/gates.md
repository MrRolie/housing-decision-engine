# Judgment gates — the why and the worked phrasing

The hot path states each gate as one rule. This file carries what the rule
protects against and the sentences that satisfy it.

## 1. Decisiveness is not the headline

The engine's `verdict.decisive` is a rule, not a vibe: with Monte Carlo on,
decisive ⇔ P(best cheapest) ≥ 65%; otherwise ⇔ margin ≥ 5% of the winner's
PV (both anchored in `--print-anchors` under `verdict.*`). When it is not
decisive, say the options are too close to call, quote the probability or the
margin fraction, and name what would break the tie. A sweep read-back obeys
the same rule at every point — "condo wins at every point" is false when a
point is inside the tie band. The verdict has three states (`verdict.state`):
`option`, `tie`, or `disagreement` — the deterministic central case and the
Monte Carlo majority favour different options. A disagreement is never
decisive and is said with both figures, in the engine's own line — "best
guess says rent by $6,517 (1.9% of rent PV); most futures say house (60%
cheapest) — the two disagree" — never softened into "rent, not decisive" or
"house wins in most futures"; name what would move each side (a sweep point
carries the same line: `best guess rent by …, most futures house (60%) —
disagree`).

## 2. A default is not the user's input

Read the `defaults applied:` line back before the verdict; say the source for
each. `[neutral, uncited]` means the engine has NO evidence for that value
(value growth, house maintenance). Zero growth warns whether defaulted or
typed: the verdict is sensitive to it, so state a view or bracket it. When the
user has no view on price growth and their area has a shipped prior
(`references/translation.md` lists the five geographies), do not hand the
question back: run a second config with the prior and lead with whether the
verdict survives it; only an area with no prior gets the question back. On a
threshold question the prior informs the verdict band only (a break-even is
deterministic and does not move), so the growth sweep in the threshold lane
still runs. Say what growth the prior encodes — the run's `demographic prior:`
assumptions line prints the reference drift for the bands the horizon touches
(all bands and the scenario range are in `--json` under the prior's
provenance `encoded_drift`); quote only the bands inside the horizon — an
8-year run from 2026 touches 2030 and 2035, never a 2050 figure for a 2034
exit.

## 3. Real vs nominal — the contract, not a vibe

Defaults are REAL terms. With a mortgage, run `mode: nominal`: `economic:
{mode: nominal, inflation_rate: 0.021}`, `mortgage_rate` = the quoted rate's
effective annual (no real conversion — a quoted contract rate is the one
input used as typed). `discount_rate` is a REAL opportunity cost like every
other rate: omit it for the anchor — the engine composes its 3% real default
with inflation (5.2%) and echoes it — or state the user's own REAL figure and
the engine composes it the same way; the read-back's `mode:` line shows both
(`discount_rate 3.5% real → 5.7% nominal (incl. 2.1% inflation)`). Never type
a nominal discount rate — it is inflated twice. Growth, escalation and return
inputs stay REAL in nominal mode and the engine composes `inflation_rate` on
top (that includes `investment_return_rate`); never type a sticker growth
rate into nominal mode — inflated twice the same way. Why nominal: the lender collects the NOMINAL payment;
a real-rate level payment understates year-1 cash by about a fifth and hides
GDS/TDS breaches (the engine warns when a mortgage runs in real mode with an
income). `mode: real` is for all-cash and rent-only comparisons, where every
rate you enter is real. `mortgage_rate` is an effective annual rate with
annual payments; a Canadian posted rate compounds semi-annually — convert it
(the schema note carries the formula). Every colloquial GROWTH or RETURN rate
a member of the public quotes is a sticker rate unless they say "above
inflation": convert each to real before typing it; the mortgage is the
exception — compounding only.

## 4. Like-for-like renter capital

Put the buyer's total year-0 cash — down payment + purchase costs (all cash =
the whole price + purchase costs) — in `rent.invested_down_payment`; the
engine charges it at year 0 and credits its terminal value, mirroring the
buyer. Omitting it assumes the renter earns exactly the discount rate — say so
if you do. When the return equals the discount rate the capital term nets to
zero in PV (the breakdown shows +D and −D): never describe the renter's
capital as a drag or an advantage; a spread is the engine's capital-spread
warning, and only that warning says which way it cuts.

## 5. A range is two configs

When the user gives a range on a decision-relevant input (growth, horizon,
price), bracket it with `--sweep` and lead with whether the verdict survives
the bracket; never quietly take the midpoint. Author brackets in the USER's
units and include their stated value, zero in their units (flat sticker
prices = −2.1% real) and one step below; read the flip point back in their
units. The flip point is the engine's `flip <key>:` line — the bracket between two
run points; if it is too coarse to act on, densify with the range form
(`--sweep key=lo:hi:n`) and rerun — never interpolate a flip from two points.
The tie band is a range too: quote the points where `decisive` is false ("too
close to call between X and Y"). Every flip point is stated under the user's
criterion: with uncertainty on and "lowest expected cost" as the criterion,
the flip is the sweep's `mean flip <key>:` line (`mc_mean_flips` in JSON), not the
deterministic `flip <key>:` — never mix the two in one answer, and say when the mean
never changes sides. (A break-even's tie band is a deterministic band and the
verdict's band from a densified sweep is the Monte Carlo one; quoting both,
labelled, is the threshold lane's rule and does not breach this one.) "It
would not flip" about an input you did not sweep is a guess — sweep it, or
write "not run"; the same for any claim about a combination of inputs (the
sweep header says so: edit the config and sweep the second key).

## 6. Match the figure to their criterion

Lowest expected cost → the verdict margin — but with any uncertainty input
on, "expected cost" is the Monte Carlo MEAN: read `verdict.mc_mean_best` (the
report's `mean` per option) and when it disagrees with `best` say so with
both means (the `reason` line carries the clause); "too close to call"
survives, the sign does not go unmentioned. When the mean disagrees only
because of an uncertainty input YOU chose (a crash hazard, a vol), say that
the input is yours and sweep it (`--sweep condo.price_shock.annual_hazard=…`)
so the user sees where their fear starts to matter. Smallest worst case →
turn the uncertainty inputs ON (`simulation.*_vol`, `price_shock`), label
them illustrative, and read the p95 and `prob_*_cheapest`.
`investment_return_vol` is the ANNUAL volatility of the renter's return (0.10
≈ a 60/40 portfolio, 0.16 ≈ equities); with a `price_shock` or a prior on the
owned side and 0 here the renter's capital cannot lose — the engine warns
(`asymmetric tails`, `one-sided uncertainty`), so set both or neither; with
every vol at 0 the Monte Carlo is one repeated path and "P(x cheapest): 100%"
means nothing was modelled. A "no nasty surprise" criterion gets ONE clause
carrying both sides' p95, labelled as resting on the vols you typed ("the
worst 5% of futures: buying $412k, renting $388k — both on my illustrative
30% maintenance and 10% return vols, not evidence"); never a p95 for one side
alone. Most wealth at the end → compare `total_pv` (net cost including the
terminal assets of both sides); `terminal_equity_pv` is a component, not the
answer.

## 7. Cash line — cash is not PV

Beside the $/month PV equivalent, quote the report's `Year-1 cash` line: each
side's year-1 outlay, the principal repaid, and the owner's unrecoverable cash
(cash − principal, plus the purchase and selling costs amortised over the
horizon). The owner usually pays MORE cash per month while the PV verdict
favours buying — that is equity at sale being credited, not a defect: say
"you pay $X/month more in cash; buying still wins by $Y in present value
because you leave with equity". The line's `expected appreciation` figure is
the term a cash-only comparison omits (in nominal mode the levered asset
grows with inflation while the debt does not): owner economic cost ≈ cash −
principal − appreciation + amortised purchase and selling costs. In nominal
mode with 0% real growth that figure is inflation on the sticker value — the
engine labels it so; say "$13,650 is inflation, not real gain", never "$X
goes to appreciation" beside "flat prices". Only when the breakdown's
`terminal_equity_pv` does not explain the gap is there a discrepancy to
report.

## 8. "Not modelled" is mandatory

Every answer names what was left out (renewal risk, a financed insurance
premium, rent control, taxes on the investment return, a probabilistic exit)
with the direction of bias. With a mortgage, renewal risk is always on the
list (the quoted rate is held for the whole amortization — biases toward
buying when rates are rising), and so is any default the engine warned on (a
1% real rent escalation defaulted for a Québec continuing lease biases toward
buying); "no chance you move early" biases toward buying too (an early exit
pays the selling cost sooner); the renter's investment return is shown
pre-tax (biases toward renting); every dollar input the engine's coherence
note held fixed along a price scan (a `purchase_costs` figure, a dollar tax or
insurance line sized for the seed) goes here with the note's direction — it
favours buying above the seed price and renting below it — every item gets a
direction, none gets none.
