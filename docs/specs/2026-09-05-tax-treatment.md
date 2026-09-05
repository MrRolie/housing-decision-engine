# Tax treatment of the two sides' money — design

**Status:** accepted 2026-09-05 for build, both folds. Ruling (roadmap): tax asymmetry
first, the FHSA as its first-home slice. Review settled three points on the proposal: the
HBP leg is the like-for-like repayment schedule (§4.5), a config without the block gets an
engine warning (§7), and the intake asks where the savings sit (§7).

## 1. Why

Neither side is taxed today: the renter's capital compounds at `investment_return_rate`
untouched, the owner's gain is credited at sale untouched, and only the skill's
not-modelled line names the bias. The renter-side drag is the size of served verdict
margins ($1,600 in the first-time-buyer example); the FHSA refunds and the HBP are the two
first-home cash items a buyer plans around, and the intake cannot ask about them.

## 2. Today's contract, cited

- `deterministic._compute_rent_option`: `benefit = D (1 + r_inv)^N / (1 + dr)^N`, booked as
  `invested_capital_pv = +D`, `invested_dp_benefit_pv = −benefit`;
  `monte_carlo._simulate_rent_pv_once` compounds the same leg per year, `(1 + r) · shock_t`.
- `_financing_pv` credits `equity_N` with no tax — the principal-residence exemption, unnamed.
- `config._net_down_payment` nets `purchase_costs` out of `cash_available`, then
  `_apply_mortgage_insurance` picks the tier on the loan that remains.
- `rates.CONVERTIBLE_ORDER` omits `mortgage_rate`; a tax rate joins it — a fraction of
  income, never converted. `config.coherence_warnings` computes the capital-spread residual
  itself and would print a spread the engine did not use once a drag is in play.

## 3. Inputs — the `tax:` top-level block (opt-in; absent ⇒ every figure unchanged)

| Key | Rule |
|---|---|
| `marginal_rate` | fraction in [0, 1), as is. Omitted ⇒ `marginal_rate(income.annual_income, province)` through the anchored brackets, top-level `province` QC or ON. Neither ⇒ refused naming both paths. |
| `renter_capital: {tfsa, rrsp, fhsa, taxable}` | dollars; required when `rent.invested_down_payment > 0`, refused without `rent:`. Must sum to `rent.invested_down_payment` (±$1), else refused with both figures. `fhsa` is DERIVED when `tax.fhsa` is present (§4.4) and refused if also stated. |
| `taxable_return_treatment` | `capital_gains` (default) \| `interest`: `ι` = `tax.capital_gains_inclusion_rate` or 1. |
| `retirement_marginal_rate` | fraction; default = the current rate, printed "(= current, default)". |
| `fhsa: {balance, annual_contribution, years_until_purchase}` | today's balance; k ≥ 0 saving years before year 0 (default 0: the decision is now). Needs an owned option with `first_time_buyer: true`. |
| `hbp_withdrawal` | ≤ `hbp.withdrawal_limit`; ≤ `renter_capital.rrsp` when `rent:` is present; needs `first_time_buyer: true`. |

Intake identity, stated once so nothing is counted twice: `cash_available` (or
`down_payment`) keeps its meaning — the TFSA, FHSA and taxable dollars brought to closing.
RRSP dollars reach closing only through the HBP, so `hbp_withdrawal` is the one addition
from the pile and the refunds the one addition the user could not have counted.
Like-for-like is `cash_available + hbp_withdrawal = rent.invested_down_payment` — a
coherence warning when both piles are stated and differ (the engine already lets them).

Touch points: `config._TOP_LEVEL_KEYS` + `_TAX_KEYS` / `_RENTER_CAPITAL_KEYS` / `_FHSA_KEYS`
(nested, the `price_shock` pattern); `_SECTION_KEYS["tax"]` and `input_schema._NOTES["tax"]`
for `--print-schema`; `sweep.INT_KEYS` (`years_until_purchase`); `break_even._MONEY_KEYS`
(`hbp_withdrawal`, `renter_capital.*`, `fhsa.balance`). `models.TaxParams` on
`ComparisonSpec.tax` holds the resolved rate and its breakdown, the shares, `R`, `F_0` and
the HBP schedule — derived in the loader, so `--sweep` and `--break-even` re-derive per point.

## 4. Mechanics

`m` marginal rate, `ι` inclusion, `π` = `inflation_rate`, `r` the renter's return as the
engines hold it (real in real mode, composed in nominal mode), `t_ret` retirement rate,
`S` sheltered share (TFSA + RRSP + FHSA), `F` FHSA share, `T` taxable, `R` refunds, `H` HBP.

```
4.1  m: typed, or marginal_rate(income.annual_income, province) — flat for the run: held
     across the horizon, not stepped down by the FHSA deduction. Breakdown printed as is.

4.2  drag, taxable share only (gains are taxed in NOMINAL terms):
     G_nom = (1 + r)(1 + π) real mode | 1 + r nominal mode
     A_nom = 1 + (G_nom − 1)(1 − m·ι);   A = A_nom / (1 + π) real mode | A_nom nominal
     one helper after_tax_factor(gross_factor, mode, π, m, ι) read by BOTH engines; the
     Monte Carlo passes the shocked (1 + r)·s_t per year, so zero vol reproduces the
     deterministic path exactly; linear on losses (losses assumed usable against gains).
     RRSP: sheltered for the drag; its pre-tax nature is not modelled (§8).

4.3  renter's terminal value — ONE helper renter_terminal_value(spec), read by the
     deterministic engine, the capital-spread warning and the tax: line:
     V_N = (S − F)(1 + r)^N + F (1 + r)^N (1 − t_ret) + (T + R) · A^N
     invested_capital_pv = D + R ;  invested_dp_benefit_pv = −V_N / (1 + dr)^N
     drag_N = (T + R)[(1 + r)^N − A^N] ;  haircut_N = t_ret · F (1 + r)^N   (both printed)
     The Monte Carlo applies t_ret to the FHSA share's SHOCKED terminal value.
     R joins the TAXABLE share (unsheltered cash; stated on the line — toward buying, small).

4.4  FHSA, saving years y = 1..k (no growth inside the saving years; stated):
     room_y = min(L_a + cf_y, L_life − paid_y);  paid_1 = balance (stands in for
     contributions to date);  cf_1 = 0 (unused room entering taken as zero; stated)
     c_y = min(annual_contribution, room_y);  cf_{y+1} = min(cf_max, cf_y + L_a − c_y)
     R = m · Σ c_y ;  F_0 = balance + Σ c_y
     (L_a fhsa.annual_limit, L_life fhsa.lifetime_limit, cf_max fhsa.carry_forward_max)
     R accrues to BOTH sides — the deduction does not depend on buying — so it enters the
     buyer's day-one cash AND the renter's capital. The buy-side differential is the tax
     the renter eventually pays on the FHSA→RRSP rollover (fhsa.max_years_open names the
     deadline): haircut_N, at t_ret, at the horizon end. The buyer's F_0 leaves tax-free.

4.5  HBP: H is already priced by the existing legs — the renter earns r on it, the
     buyer's down payment carries it — so the plan's own cost is the repayment schedule:
     tranche H/Y is an owner outlay at t_j = g + j − 1, j = 1..Y (g hbp.repayment_grace_years
     = first repayment year − withdrawal year; Y hbp.repayment_years), τ_j = min(t_j, N) —
     a tranche past N returns at N — and the rebuilt RRSP is credited at N, sheltered:
     out_j = H/Y nominal mode | (H/Y)/(1 + π)^τ_j real mode   (FIXED NOMINAL dollars)
     hbp_repayment_pv = Σ_j out_j (1 + dr)^(−τ_j) − [Σ_j out_j (1 + r)^(N − τ_j)] (1 + dr)^(−N)
     zero at r = dr; a new breakdown key on both owned options (0.0 without an HBP); the MC
     owned paths add the same constant (r unshocked). Outside the affordability ratio and
     the year-1 cash line — a transfer into the household's own RRSP, not a housing cost.
```

Where it enters: the loader derives `R + H` before the options are parsed and adds them
between `_net_down_payment` and `_apply_mortgage_insurance` on every owned option with
`first_time_buyer: true` — the insurance solver receives the augmented pile so the tier is
chosen on the loan that remains; `cash_available` stays as typed and the financing line
shows the addition. `_parse_rent` receives `R` for the taxable share.

Why the repayment leg and not "sheltered growth lost": that figure — `H(1 + r)^N` less the
rebuilt RRSP — charges the buyer `r` on `H` a second time (≈ $6,500 PV on a $20,000 HBP
over 10 years at 5.1%, four times the example's margin) when the capital legs already deny
the buyer `r` on `H`. `--sweep tax.hbp_withdrawal` shows HBP-versus-bigger-loan through
those legs.

## 5. The owner's side

Nothing in the numbers changes. The `tax:` line names the principal-residence exemption
with `tax.principal_residence_exempt_fraction` (consumed there, as
`economic.inflation_rate.nominal_planning` is by its warning). A non-exempt fraction at
sale (the partly-rented duplex) is the follow-up, not this fold.

## 6. Read-back — verbatim shapes (figures illustrative: QC, $100,000, 60/40 at 5.1%, 10 years)

Each row illustrates its own shape; the rows do not compose into one config.

| Line | Shape |
|---|---|
| `tax:` — a new read-back section after `purchase costs` | `tax: marginal rate 36.12% resolved from income $100,000 in QC — federal 20.5% × (1 − 16.5% Québec abatement) + QC 19% [tax.federal.*, tax.qc.* 2026] · renter capital $60,000 = sheltered $45,000 (TFSA $25,000 + RRSP $20,000 + FHSA $0) + taxable $15,000 (+ FHSA refunds $0) · taxable share: 5.1% × (1 − 36.12% × 50% inclusion, capital gains — default) = 4.18% after tax [tax.capital_gains_inclusion_rate]; blended 4.88%; drag $2,078 at year 10 (PV $1,256) charged to rent · owner: principal-residence exemption — no tax on the equity gain at sale [tax.principal_residence_exempt_fraction]`. Typed: `marginal rate 36.1% as typed`. With `F > 0`, appended: ` · FHSA share $31,000 rolls to an RRSP for the renter (within 15 years of opening [fhsa.max_years_open]) — haircut 36.12% retirement marginal rate (= current, default) on $50,979 at year 10 = $18,412 (PV $11,130) charged to rent [tax.retirement_marginal_rate]` |
| `fhsa:` clause on the financing line | head: `cash available $60,000 + FHSA refunds $5,779 + HBP $20,000 − purchase_costs $6,860 − premium tax $1,110 = down payment $77,809`; clause: `fhsa: balance $15,000 + $16,000 contributed over 2 saving years (room $8,000/yr + carry-forward ≤ $8,000, lifetime $40,000, $25,000 remaining [fhsa.annual_limit, fhsa.carry_forward_max, fhsa.lifetime_limit]) → refunds $5,779 at 36.12%, added to both sides' capital`; k = 0: `fhsa: balance $15,000, no saving years — no refunds to add` |
| `hbp:` — per owned option, same section | `condo hbp: $20,000 withdrawn from the RRSP into the down payment (≤ $60,000 [hbp.withdrawal_limit]) · repaid $1,333/yr over 15 years from year 5 [hbp.repayment_years, hbp.repayment_grace_years]; 10 tranches fall at or past year 10 and return at the horizon · the RRSP is rebuilt to $21,092 by year 10 (repayments PV $12,758 against the rebuilt RRSP's PV $12,749) — net PV $9 charged to condo (hbp_repayment_pv)` |
| `[warning]` with no `tax:` block | `rent: invested capital $60,000 earns 5.1% untaxed — no tax: block, so tax on the taxable share is not modelled (toward renting); state where the savings sit (tax.renter_capital)` |

`--json`: `assumptions.tax` carries the same facts structured; `breakdown.hbp_repayment_pv`
is always present. The text report prints `hbp_repayment_pv` only when non-zero (the one
special case, stated in `reporting.py`).

## 7. Interactions

- **Capital-spread warning** reads `renter_terminal_value` and gains "after tax on the
  taxable share: blended 4.87%" — it can never quote a spread the engine did not use.
- **Like-for-like** (§3 identity) and **TFSA room** (`renter_capital.tfsa` above
  `tfsa.cumulative_room_since_2009` — a check, not a refusal: growth can outrun
  contributions; `tfsa.annual_limit` in the schema note).
- **Real-mode drag:** warn when `rates: real` leaves `inflation_rate` at the inert zero —
  the drag is applied to the real return while gains are taxed nominally (understated,
  toward renting).
- **`sources:` classes:** every `tax.*` leaf is attributable through `attributable_keys`
  as it stands; a resolved `marginal_rate` has no key — the `tax:` line carries its
  derivation; a derived `renter_capital.fhsa` is attributed through the `fhsa` leaves.
- **As-quoted rule:** `marginal_rate` and `retirement_marginal_rate` are never in
  `CONVERTIBLE_KEYS`, never on the `rates:` line — pinned by a test.
- **No block ⇒ the engine warns** (§6, last row) when `rent.invested_down_payment > 0`
  and no `tax:` block. STORY.md carries warnings, so the showcase is regenerated in the
  same commit; the seven examples' totals and verdicts are unchanged and only that line is
  new in their read-backs. Skill gate 8 quotes the engine's warning instead of carrying
  its own not-modelled text.
- **Refusals** (`ConfigValidationError`, each naming the fix): no rate typed and none
  resolvable; `marginal_rate` outside [0, 1); shares not summing (both figures);
  `renter_capital.fhsa` beside `tax.fhsa`; `renter_capital` without `rent:`; `fhsa` /
  `hbp_withdrawal` without a `first_time_buyer: true` owned option; `hbp_withdrawal` above
  the limit or the RRSP share; an unknown `taxable_return_treatment`.
- `single_path_run` / `dispersion_sources` unchanged — the drag adds no randomness. Docs:
  `CONFIG_SCHEMAS.md`, `API_CONTRACT.md`, the `ARCHITECTURE.md` glossary, `AGENTS.md`
  (the "no geographic tax rules" line and the package layout).
- **Skill and prompts:** the intake's money ask (SKILL.md elicit item 2) gains "and
  where does it sit — TFSA, RRSP, FHSA, or a taxable account?"; `references/translation.md`
  gains a `tax:` row and a first-home row (FHSA balance and contributions, HBP withdrawal →
  the keys); `PROMPTS.md` "How to ask" gains one bullet and "What it does not do" drops
  "taxes on the renter's return" for the §8 list in one sentence; the hot path stays under
  300 lines / 2,600 words.

## 8. Not modelled after this lands

RRSP pre-tax nature (both sides hold it pre-tax — symmetric, unpriced); the dividend tax
credit and foreign withholding; provinces beyond QC and ON (type `marginal_rate`); the
FHSA→RRSP rollover's effect on RRSP room; FHSA growth during the saving years; deferral of
capital-gains realisation (the drag assumes annual realisation — toward buying); a marginal
rate that moves with income; a missed HBP repayment (taxed as income); US or non-resident
cases; the AMT.

## 9. Test plan (failing tests first)

- `tests/test_tax_treatment.py` reads the merged registry (the anchors lane landed first);
  a stand-in is registered only for a name the registry lacks — none today. Every engine
  lookup is lazy (inside the function; no dataclass default reads a new anchor).
- One hand-checked example per province at $100,000: QC 36.12% (20.5% × 0.835 + 19%), ON
  31.48% (20.5% + 9.15% × 1.20) against `tax_rates.marginal_rate_breakdown`; `V_N`,
  `drag_N`, `haircut_N`, `R`, `F_0`, `hbp_repayment_pv` to the dollar against §4, nominal and
  real mode; `hbp_repayment_pv = 0` at `r = dr`.
- Zero-vol Monte Carlo equals the deterministic rent AND owned PVs with a `tax:` block
  (both modes).
- Absence invariant: the seven examples' totals, verdicts and breakdowns unchanged; text,
  `--read-back` and `--json` byte-identical apart from the one `[warning]` line and
  `hbp_repayment_pv: 0.0`; `docs/story/` regenerated once and byte-stable after.
- Every refusal in §7 names its fix; every line in §6 matches its shape; the capital-spread
  warning's blended rate equals the helper's; the `rates:` line never lists a tax key;
  `--sweep tax.hbp_withdrawal=0:20000:3` re-derives through the loader.
- `tests/test_anchors.py`: `tax.`, `fhsa.`, `hbp.`, `tfsa.` join `CONSUMED_FAMILIES` naming
  `tax_treatment.py` (they are reference families, so the Defaults Summary test already
  excludes them).

## 10. What the anchors lane supplies (merged first)

Read by name from `ANCHORS`, lazily: `tax.capital_gains_inclusion_rate`,
`tax.principal_residence_exempt_fraction`, `fhsa.annual_limit`, `fhsa.lifetime_limit`,
`fhsa.carry_forward_max`, `fhsa.max_years_open`, `hbp.withdrawal_limit`,
`hbp.repayment_years`, `hbp.repayment_grace_years`, `tfsa.annual_limit`,
`tfsa.cumulative_room_since_2009`; the brackets, abatement and surtax through
`hde.tax_rates.marginal_rate(taxable_income, province)` and `marginal_rate_breakdown`
(federal, abatement, provincial and surtax components), imported inside the resolver so
`import hde` never depends on it. Nothing here writes an anchor.

## 11. The two folds

Fold 1 — the asymmetry: `marginal_rate`, `renter_capital`, `taxable_return_treatment`, the
drag (§4.2–4.3 without `F`), the owner's line, the warnings, the docs. Fold 2 — the
first-home slice: `fhsa`, `hbp_withdrawal`, `retirement_marginal_rate`, the day-one cash,
the haircut, `hbp_repayment_pv`, the financing clause and the `hbp:` line.
