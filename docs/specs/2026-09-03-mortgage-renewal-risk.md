# Mortgage renewal risk — design

**Status:** proposed. Design only — no engine code.

## 1. Why

The engine prices a 25-year amortization at one rate for its whole life. A Canadian
five-year fixed renews four times, and the renewal rate is the biggest buy-side risk a
buyer carries; today it cannot reach the answer at all. Not the refinancing/variable-rate
*optimization* `AGENTS.md` excludes: a renewal is a contractual reset at term end.

## 2. Today's contract, cited

- `pv.mortgage_payment(principal, rate, term_years)` returns ONE level annual payment `M`
  over the whole `mortgage_term_years` `A` — the schema's *amortization* term
  (`input_schema._NOTES["condo"]["mortgage_term_years"]`), not the Canadian rate contract.
- `deterministic._financing_pv` prices `mortgage_pv = pv_annuity(M, dr, min(N, A))` and
  `balance_N = pv.outstanding_balance(loan, rate, A, N, M)`.
- `deterministic._annual_costs_for_option` holds that `M` while `year <= mort_term`: the
  affordability ratio never steps.
- `monte_carlo._simulate_condo_pv_once` and `_simulate_house_pv_once` import that same
  `_financing_pv`: the financing leg is identical on every path; only `terminal_value` varies.
- `deterministic._effective_growth_rate` composes `econ.inflation_rate` onto
  growth/escalation/return inputs ONLY; `mortgage_rate` and `discount_rate` are used as
  entered (`input_schema._NOTES["economic"]["mode"]`, echoed by
  `serialization.format_assumptions`).

## 3. Inputs

| Key | Section | Note |
|---|---|---|
| `mortgage_renewal_years` | condo, house | int: the RATE contract's length — the Canadian "term", not `mortgage_term_years` (the amortization). Absent ⇒ today's numbers plus a warning. |
| `mortgage_renewal_rates` | condo, house | float **or** list of effective-annual rates in order; a scalar applies to every renewal, a short list carries its last forward. `required_if` `mortgage_renewal_years` is present. |
| `simulation.renewal_rate_vol` | simulation | float: rate-points σ per renewal (slice 2). |

No default, **no `ANCHORS` entry**: no defensible forward path exists, and inventing one
breaches the honesty markings of `docs/specs/2026-09-01-provenance-remediation-design.md` §2.
The scalar form matters: `sweep.with_value` sets one dict leaf.

Touch points: `config._CONDO_KEYS` / `_HOUSE_KEYS` / `_SIMULATION_KEYS`
(`_reject_unknown_keys` refuses unlisted keys); `input_schema._NOTES`;
`config.single_path_run`, which must count `renewal_rate_vol` or a renewal-only run is
stamped single-path, losing Act 3 and `mc_floor`.

## 4. Re-amortization

One pure helper: `pv.renewal_schedule(loan, rates, renewal_years, amortization_years)` →
segments `(start_year, rate, payment, opening_balance)`.

- Segment `k` spans years `kT+1 … min((k+1)T, A)` over remaining amortization `A − kT`.
- `M_k = mortgage_payment(B_k, r_k, A − kT)` — re-solved over the REMAINING amortization,
  Canadian convention.
- `B_{k+1} = outstanding_balance(B_k, r_k, A − kT, T, M_k)` — pass remaining amortization and
  years-into-segment, or the `year >= term_years → 0` branch zeroes the balance early.
- Segments exist only for `kT < A` strictly: `mortgage_payment` raises on `term_years <= 0`.

Four consumers, re-deriving nothing: `_financing_pv`
(`mortgage_pv = Σ_k pv_single(pv_annuity(M_k, dr, len_k), dr, kT)` over segments starting
before `N`, `len_k` truncated at `N` — today's `min(N, A)` cap; `balance_N` from the segment
holding `N`); `_annual_costs_for_option` (per-year `M_k`, so the affordability ratio steps at
renewal); `story_plots._cumulative_cost_curves`, whose docstring forbids re-deriving the
math; `OptionResult.principal_year1` unchanged.

## 5. Real vs nominal

Renewal rates are quoted, contractual, nominal — `mortgage_rate`'s class — so they are used
as entered in both modes and `_effective_growth_rate` never touches them; real mode prices
the schedule at nominal rates against a real discount rate, as today's single rate is. The
real-mode warning must name the payment it quotes (now "the year-1 payment").

## 6. Assumptions, provenance, warnings

- **Assumptions** (`serialization.format_assumptions`): a `{name} renewals:` line — term
  length, a row per segment (start year, rate, payment), and the first renewal's payment
  change in dollars and percent.
- **Provenance:** `--print-anchors` unchanged. Every renewal rate is the user's own figure —
  a scenario, not a forecast; where the assistant supplies one, the honesty contract's
  "no source for" line carries it.
- **Warnings** (`config.coherence_warnings`): no `mortgage_renewal_years` on a mortgage block
  — renewal risk not modelled, the rate held for the whole amortization though a Canadian
  fixed term is at most five years; renewal rates below `mortgage_rate` — biases the verdict
  toward buying; a renewal term at or past the amortization — inert.
  `config.affordability_warnings` already reports post-renewal breaches.

## 7. `--sweep` and `--break-even`

`--sweep house.mortgage_renewal_rates=0.03:0.08:6` gives the flip point on the renewal rate,
through the same loader and verdict rule; add `mortgage_renewal_years` to `sweep.INT_KEYS`.
`--break-even house.mortgage_renewal_rates=0.02:0.12` solves the rate at which the buy side
stops winning; a rate key is not in `break_even._MONEY_KEYS`, so the `lo:hi` bracket is
required; `solve_break_even_across` re-solves it at every sweep point.

## 8. Story

Act 2 — `story_plots.plot_act2_the_race`: the paid curve kinks at each renewal, and the
sentence in `story_page._act_sentences` gains the year and size of the first step. Act 3
widens when the channel lands; no new act.

## 9. Test plan

- `tests/test_financing_oracle.py`: a pinned schedule against an external calculator;
  invariants — segment principal sums to the loan, balance monotone non-increasing and zero
  at `A`, one segment reproducing `mortgage_payment` to the cent.
- Equal-rate identity: every renewal at `mortgage_rate` reproduces today's `mortgage_pv` and
  `balance_N` exactly.
- Absence invariant: with no renewal key, totals, breakdowns and plot bytes are unchanged
  (`tests/test_deterministic.py`, `tests/test_story_plots.py`; byte-stability, `CLAUDE.md`).
- Refusals: renewal keys without a mortgage block, `mortgage_renewal_years <= 0`, a negative
  rate.

## 10. Smallest shippable slice

Deterministic only: the two option-level keys, `pv.renewal_schedule`, its four consumers, the
assumptions line, the warnings, Act 2. `--sweep` and `--break-even` arrive free, re-entering
through `load_config_dict`.

Deliberately left out: the Monte Carlo channel (`simulation.renewal_rate_vol`: one draw per
renewal, cumulative, clamped at zero since `_financing_pv` refuses a negative rate); any
renewal-rate anchor or forward curve; mean reversion and `_correlated_z`-style coupling to
the inflation shock; variable- and trigger-rate products; prepayment penalties and break
costs; the qualifying-rate stress test; the Fisher split in real mode.
