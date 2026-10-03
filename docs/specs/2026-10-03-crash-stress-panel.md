# Crash stress panel — design (2026-10-03)

**Status:** R1–R7 ruled 2026-10-03 (§2). Design only; no engine code is written by this document.
Revision 2: every figure re-measured against main at 3b7306a (§13).
**Lineage:** `docs/specs/2026-09-21-one-world-simulation.md` §2 (one housing market per path);
`docs/specs/2026-09-22-which-risk-decides-it.md` §0.1 item 35 (the block prints figures, not
interpretation); `docs/specs/2026-10-01-renewal-rate-path-file.md` (the ladder, the path file and
its ruling 2, `rate_shift` out of scope).

Every figure below was measured, and §13 gives each one's command. "Prototype" means
exploratory scripts that wrap three engine functions in-process and restore them (§13 says how);
they are not committed, and the engine was not edited.

**The configs.** Every figure comes from a file in this repo or from one built from it by the keys
named here, so anyone can rebuild it:

- **FTB** is `examples/first_time_buyer_montreal.yaml` as it stands (10 years, no renewal ladder).
- **FTB-10L** and **FTB-25L** are FTB plus `condo.mortgage_renewal_years: 5` and
  `condo.mortgage_renewal_rates: 0.0455` (the condo's own `mortgage_rate`, quoted
  `effective_annual`), at `years: 10` and `years: 25`, with both keys declared `assistant` in
  `sources:`. A ladder at the opening rate leaves the central line unchanged: FTB-10L's totals equal
  FTB's to the cent.
- **The worked households** add to FTB-10L or FTB-25L `economic.inflation_vol: 0.01`,
  `simulation.investment_return_vol: 0.10`, `simulation.other_cost_vol: 0.01`, and:

  | household | base | `value_growth_vol` | `rent_escalation_vol` |
  |---|---|---|---|
  | P1 | FTB-10L | 0.04 | 0.23 |
  | P1b | FTB-10L | 0.068 | 0.23 |
  | P2 | FTB-25L | 0.04 | 0.23 |
  | P2b | FTB-25L | 0.068 | 0.23 |
  | P2m | FTB-25L | 0.031 | 0.14 |

  each declared `assistant`, 5,000 paths, `random_seed` 42 or 4242. The volatilities are
  illustrative sizes, not estimates this spec defends; P1 and P1b share FTB's central line, and P2,
  P2b and P2m share FTB-25L's.

---

## 0. What is asked, and the shape this spec gives it

The question: "a panel to help the decision in the case of a real estate market crash: simulate
multiple market crashes of different magnitude that happen once."

The answer this spec builds is a CONDITIONAL panel. Each row says: if the home's value drops by
`d` in year `c` and comes back in the stated way, here are the central line's totals, the gap,
how far the gap moved against no drop, and the verdict over the config's futures with its
decisiveness. It never says how likely a drop is. The probability of a crash stays where it is
today, in `price_shock`, and the panel refuses to run beside one (§7, R2).

One row per (drop, year, recovery). One solved break-even drop per (year, recovery): the drop at
which the central case's cheapest option changes.

## 1. What was measured

### 1.1 The engine's crash today, read from the code at 3b7306a

- `_apply_price_shock` (`monte_carlo.py:665`) fires when `u < annual_hazard × tilt` and
  multiplies every value track by `1 − min(severity_mean × lognormal(severity_vol), 1)`. It is a
  one-year step applied after that year's ordinary dispersion, and a permanent level drop: no
  later year undoes it.
- It is Monte Carlo only. `compute_deterministic` never reads `price_shock`: on
  `tests/fixtures/uncertainty_surface.yaml` the central totals with and without both
  `price_shock` blocks are identical to the cent (condo $430,855.19, house $476,086.89, rent
  $399,506.53). A hazard therefore cannot move the central line, and a panel built on it alone
  could not reach the central case.
- The central line has no value path. The condo's sale value is the closed form
  `initial_value × (1 + g)^years` (`deterministic.py:417`); the house tracks a yearly value only
  to price maintenance (`deterministic.py:482`, `maintenance_rate × house_value`).
- The sale value enters a total in exactly one place: `equity_N = value_N × (1 − selling_cost_rate)
  − balance_N` (`deterministic.py:191`). The mortgage balance, the payment and every renewal
  re-solve depend on the loan and the rates, never on the value. On a laddered mortgage `balance_N`
  is `pv.balance_at` on the renewal schedule; without a ladder it is `pv.outstanding_balance`
  (`deterministic.py:169–190`).
- The house's maintenance follows the crashed value in the Monte Carlo (`monte_carlo.py:1075`,
  then `:1079`), but the affordability channel prices the house's maintenance on the central
  value path on every path (`deterministic.py:683`, called from `monte_carlo.py:1627`).
- The engine sells only at the horizon. There is no early exit; unpriced-dimensions §9 lists it
  as "solve `years` over the user's own range".

### 1.2 The panel on the central line (prototype)

The prototype multiplies `value_N` by `m(years)` and each house maintenance year by `m(year)`
(§4), and leaves everything else alone.

**FTB** (condo against rent, 10 years, nominal, 0% real growth). No drop: condo $200,502, rent
$207,027; condo cheaper by $6,526 (3.25%), `tie`.

| year | recovery | drop | sale value | condo | rent − condo | best | state (margin rule) |
|---|---|---|---|---|---|---|---|
| 1 | permanent | 10% | ×0.900 | 232,312 | −25,284 | rent | option |
| 1 | permanent | 20% | ×0.800 | 264,122 | −57,094 | rent | option |
| 1 | permanent | 30% | ×0.700 | 295,932 | −88,904 | rent | option |
| 1 | permanent | 40% | ×0.600 | 327,742 | −120,714 | rent | option |
| 1 | half over 5 | 10% | ×0.949 | 216,825 | −9,798 | rent | tie |
| 1 | half over 5 | 20% | ×0.894 | 234,084 | −27,057 | rent | option |
| 1 | full over 5 or 7 | 10% to 40% | ×1 | 200,502 | +6,526 | condo | tie |
| 1 | full over 15 | 20% | ×0.915 | 227,664 | −20,637 | rent | option |
| 1 | full over 15 | 40% | ×0.815 | 259,289 | −52,261 | rent | option |
| 9 | full over 5 | 20% | ×0.837 | 252,507 | −45,480 | rent | option |
| 9 | full over 7 | 10% | | 227,970 | −20,943 | rent | option |
| 9 | full over 7 | 40% | | 313,293 | −106,265 | rent | option |
| 9 | full over 15 | 20% | ×0.812 | 260,308 | −53,280 | rent | option |
| 9 or 10 | permanent | 10% to 40% | as year 1, permanent | | | | |

**FTB-25L** (P2's central line). No drop: condo $377,856, rent $443,509; condo cheaper by $65,652
(17.37%), `option`. A drop in year 1 that recovers fully over 5, 7 or 15 years leaves it unchanged.
From year 24: full over 5 at 20% gives condo cheaper by $32,272 (`option`), at 40% rent cheaper by
$2,841 (`tie`); full over 15 at 20% condo by $27,265 (`option`), at 40% rent by $11,774 (`tie`).

**`examples/mortgage_house_vs_rent.yaml`** (house against rent, 20 years). No drop: house
$349,866, rent $452,568; house cheaper by $102,702 (29.35%), `option`.

| year | recovery | drop | house | rent − house | best | state |
|---|---|---|---|---|---|---|
| 1 | permanent | 30% | 429,168 | +23,400 | house | option |
| 1 | permanent | 40% | 455,602 | −3,034 | rent | tie |
| 1 | full over 7 | 10% / 20% / 30% / 40% | 347,825 / 345,718 / 343,533 / 341,252 | +104,743 to +111,316 | house | option |
| 19 | permanent | 30% | 453,159 | −591 | rent | tie |
| 19 | permanent | 40% | 487,590 | −35,022 | rent | option |

The house rows show the one non-terminal channel: a drop the house recovers from before the sale
makes it CHEAPER than no drop (−$8,614 at 40%), because its maintenance is priced on the value
it has meanwhile. A permanent drop in year 1 costs less than the same drop in year 19, for the
same reason.

### 1.3 The break-even drop: `solve_crossings` finds it; the panel words it

`break_even.solve_crossings(key, options, lo, hi, totals_at)` takes any callable. With
`key = "crash.drawdown"`, bracket [0, 0.99] (the whole range X1 accepts, §7) and `totals_at(d)`
returning the prototype's crashed totals, it returns the crossing and the tie-band edges. The
rest of the break-even machinery (`solve_break_even`, `_affordability_at`,
`deterministic_boundaries`, `_ranking_at`) reaches values only through `load_at(raw, key, v)` on
a YAML key, so it cannot be reused for an axis that is not in the YAML.

`solve_crossings`'s FIGURES are reused; `threshold_sentences`'s WORDING is not. Where there is no
crossing it prints, on FTB with full recovery over 7 years from year 1, on FTB-25L likewise, and on
the house example likewise: "no crossing between 0.00% and 99.00%: condo is cheaper at both ends —
widen with --break-even crash.drawdown=-0.99:0.99". That command does not exist (`crash.drawdown`
is no YAML key and `--crash-panel` takes no bracket), and its low end is a negative drop, which X1
refuses: `floor_at_zero("crash.drawdown")` is False. The bracket is the whole accepted range, so
no wider bracket exists. Where the band reaches the bracket's low end it prints "condo is cheaper
below the bracket's low end", which on this axis would assert something about a price RISE, which
the panel cannot price. The panel therefore has its own break-even templates (§3.2), and no hint
to widen.

An exact oracle exists for a condo against rent with a permanent drop: the condo's total rises by
`d × value_N × (1 − selling_cost_rate) / (1 + r)^years`, linear in `d`, so the crossing is
`d* = gap / (value_N × (1 − selling_cost_rate) / (1 + r)^years)`. The solver matches it to six
digits on both central lines:

| central line | year | recovery | crossing | tie band | oracle |
|---|---|---|---|---|---|
| FTB (= P1, P1b) | 1, 9 or 10 | permanent | 2.0515% | no drop to 5.31% | 6,525.78 / 318,100.15 = 0.020515 |
| | 1 | half over 5 | 4.0609% | no drop to 10.33% | |
| | 1 | full over 5 or 7 | none: condo cheaper throughout | | |
| | 1 | full over 15 | 5.0501% | no drop to 12.74% | |
| | 9 | half over 5 / full over 5 / full over 7 / full over 15 | 2.2768% / 2.5577% / 2.3893% / 2.1964% | no drop to 5.88% / 6.59% / 6.16% / 5.67% | |
| FTB-25L (= P2, P2b, P2m) | 1, 24 or 25 | permanent | 32.1548% | 21.81% to 43.02% | 65,652.41 / 204,176.38 = 0.321548 |
| | 1 | half over 5 | 53.97% | 38.86% to 67.53% | |
| | 1 | full over 5, 7 or 15 | none: condo cheaper throughout | | |
| | 24 | half over 5 / full over 5 / full over 7 / full over 15 | 35.02% / 38.43% / 36.40% / 34.01% | 23.92%–46.47% / 26.48%–50.49% / 24.95%–48.11% / 23.17%–45.26% | |
| house against rent | 1 / 19 / 20 | permanent | 38.85% / 29.83% / 29.51% | 30.70%–47.41% / 23.57%–36.40% / 23.32%–36.02% | 29.21% if maintenance ignored |
| | 1 | full over 5, 7 or 15 | none: house cheaper throughout | | |
| | 19 | full over 5 / full over 15 | 35.85% / 31.60% | 28.60%–43.28% / 25.04%–38.45% | |

FTB's no-drop case is already inside the tie band, so the band starts at no drop. Every crossing
above is the same with the bracket's high end at 0.95 or 0.99.

### 1.4 Does a stated crash change a decision? (conditional Monte Carlo, worked households)

The measurement multiplies every value track by `m(t) / m(t − 1)` after the year's ordinary
dispersion, as the build will (§4), and consumes no draw. Every row is therefore
common-random-number paired with the plain run: the renter's 5,000 PVs are byte-identical across
every row of a household at a seed. The plain runs give P1 0.5450/0.5476, P1b 0.5056/0.5044, P2
0.8582/0.8558, P2b 0.7774/0.7808, P2m 0.9060/0.8978 (seed 42 / 4242). "Changes a decision" means
`verdict.best` or `verdict.state` differs from the plain run at BOTH seeds 42 and 4242. A run with
|P − 0.65| < 0.02 is flagged near the floor; a change of `best` with |P − 0.5| < 0.02 at either
seed is flagged near the boundary and is not counted as a change. No change below carries the
second flag.

| households | drop, year 1 or year T−1, permanent | full recovery over 7 years from year 1 | full recovery over 7 years from year T−1 |
|---|---|---|---|
| P1 (base `tie`, P 0.545) | every drop from 10%: rent `option`, P 0.72 at 10%, 0.92 at 20% | no change at any size | every drop from 10%: rent `option` |
| P1b (base `tie`, P 0.506) | every drop: rent `option`; at 10% P 0.669/0.675, near the floor | no change | every drop: rent; 10% is `tie`/`option` (0.647/0.651), near the floor |
| P2 (base `option`, P 0.858) | 10%, 20%: no change (P 0.77; 0.660/0.667 at 20%, near the floor); 30%: `tie` (0.52); 40%: rent `tie` (0.62) | no change | 30%: `tie` (0.58); 40%: rent `tie` (0.56) |
| P2b (base `option`, P 0.777) | 10%: no change; 20%: `tie` (0.61/0.62); 30%: `tie`; 40%: rent `tie` | no change | 10%: no change (0.71/0.72); 20%: `tie`, near the floor (0.63/0.64); 30%, 40% as permanent |
| P2m (base `option`, P 0.906) | 10%, 20%: no change; 30%: `tie` (0.55); 40%: rent `tie` (0.63) | no change | 30%: `tie` (0.62); 40%: rent `tie` (0.55) |

Two P2b rows are seed-unstable, not changes: half recovery over 5 years from year 1 at 30%, and
full recovery over 5 years from year 24 at 20%, are each `tie` at seed 42 (0.6426) and `option` at
seed 4242 (0.6550). The two rows' sale multiples agree to within 0.0002, and a condo's total sees
nothing else.

**A row can be `disagreement`.** P2 with a 32% permanent drop in year 1: the central line has the
condo cheaper by $316, while 50.32% / 50.42% of the futures have rent cheaper, so the verdict is
`condo`/`disagreement` with `prob_best` 0.4968 / 0.4958 and `mc_best` rent at 0.5032 / 0.5042,
at both seeds. At 31% it is `condo`/`tie` (0.5104), at 32.5% `rent`/`tie` (0.5104).

**The ordinary value dispersion decides one row.** Holding the stated drop and setting
`value_growth_vol` to 1e-6 instead of the household's figure: P2b at a 20% permanent drop in
year 1 is `option` (0.7086/0.7004) instead of `tie` (0.6080/0.6172), at both seeds. P1, P2 and
P2b's other rows keep their states.

### 1.5 Level and spread

A stated drop moves the central line (the LEVEL) and leaves the futures spread around it. The two
are reported apart (§3.2): `level` is the central gap's change against no drop, and `sd` is the
standard deviation over the futures of the same two options' difference. Measured with the
two-option gap `rent − condo`, permanent drop in year 1, seed 42 (seed 4242 within $1,000 on each
`sd`):

| household | drop | central gap | level | futures' mean gap − no drop's | sd |
|---|---|---|---|---|---|
| P1 | none | +6,526 | 0 | 0 | 48,104 |
| P1 | 10% / 20% / 40% | −25,284 / −57,094 / −120,714 | −31,810 / −63,620 / −127,240 | −31,824 / −63,648 / −127,295 | 44,535 / 41,073 / 34,597 |
| P2b | none | +65,652 | 0 | 0 | 88,671 |
| P2b | 10% / 20% / 40% | +45,235 / +24,817 / −16,018 | −20,418 / −40,835 / −81,671 | −20,334 / −40,668 / −81,335 | 83,069 / 77,718 / 67,995 |

Across 36 measured rows (P1, P2, P2b; permanent at 10% to 40%, full over 5 from year T−1 and full
over 15 from year 1, at 20%; both seeds) the futures' mean gap moves by the level to within $620.
So the panel's decision changes are, to that precision, the level. The spread is not flat: `sd`
falls as the drop deepens, because the ordinary dispersion multiplies a smaller value. A drop that
leaves the sale value unchanged (full over 15 from year 1 on P2) leaves `prob_best` identical to
the plain run's, with every condo PV within $4.7e-10 of it (the yearly steps `m(t) / m(t − 1)`
multiply back to 1 only to rounding), so a recovered row is never pinned byte for byte.

### 1.6 The "2022-like" variant: a renewal jump with the drop

The first renewal's rate is raised by `j`, every later renewal keeps the stated ladder, and the
drop lands in the renewal year (5). The ladder that carries a jump is stated in full, one entry
per renewal of the 25-year amortization on a 5-year term: `condo.mortgage_renewal_rates: [0.0455
+ j, 0.0455, 0.0455, 0.0455]` on FTB-10L and FTB-25L. (FTB with `mortgage_renewal_years: 5` and no
`mortgage_renewal_rates` is refused by the loader: "condo.mortgage_renewal_years=5 is set without
condo.mortgage_renewal_rates".) Central line.

| config | jump | drop | best, gap | condo affordability peak, years above 32% | break-even drop (year 5, permanent) |
|---|---|---|---|---|---|
| FTB-10L | 0 | none | condo by 6,526 (3.25%), `tie` | 36.21%, years 1–5 | 2.05% |
| | +1.30 pp | none | rent by 7,530 (3.64%), `tie` | 36.21%, years 1–9 | none: rent cheaper throughout |
| | +2.37 pp | none | rent by 19,253 (9.30%), `option` | 37.01%, years 1–10 | none: rent cheaper throughout |
| FTB-25L | 0 | 20%, permanent | condo by 24,817 (5.93%), `option` | 36.21%, years 1–5 | 32.15% |
| | +1.30 pp | 20%, permanent | condo by 10,917 (2.52%), `tie` | 36.21%, years 1–9 | 25.35% |
| | +2.37 pp | none | condo by 40,147 (9.95%), `option` | 37.01%, years 1–10 | |
| | +2.37 pp | 20%, permanent | rent by 689 (0.16%), `tie` | 37.01%, years 1–10 | 19.66% |

Neither leg alone moves FTB-25L's state; together they make it a tie. A drop alone never moves a
condo's affordability ratio (the condo's cost array has no value term).

**Where the jump lands decides it.** The same +2.37 pp typed as the scalar
`mortgage_renewal_rates: 0.0692` applies to EVERY renewal, because the loader reads a scalar as a
one-entry list and the schedule carries the last entry forward. On FTB-25L, which prices four
renewals, that gives condo $432,244.22 (`tie`, 2.61%) against $403,362.00 for the first-only
ladder, years above 32% 1–11 against 1–10, and with a 20% permanent drop rent cheaper by $29,571
(`option`) against $689 (`tie`). On FTB-10L, which prices one renewal (year 6), the two ladders
give the same condo total, $226,280.89, and the same years above 32%, 1–10, so a 10-year config
cannot tell them apart.

### 1.7 Underwater years

On FTB the condo's value net of selling cost falls below the year-1 balance ($381,862 against
$459,450 × 0.95 = $436,477) at any drop above 12.51% in year 1. The engine prices no consequence of
that: no forced sale, no refused renewal, no lender at all. A permanent drop in year 1 leaves it
underwater in years 1–2 at 20%, 1–5 at 30% and 1–8 at 40%; recovered over 7 years, in years 1–4 at
40%; a drop in year 9 of up to 40% leaves no underwater year. At the 10-year sale the equity turns
negative only above a 46.16% drop. On FTB-25L the loan is repaid at the horizon.

The balance is the one the PV leg uses. With no jump the two balance sources agree on every row
above. With the +2.37 pp first-only ladder on FTB-10L the year-10 balance is $294,454 against
$283,356 unladdered, the sale-year boundary moves from 46.16% to 44.05%, and a 45% permanent drop
in year 1 is underwater in years 1–10 against 1–9.

### 1.8 History the engine's skill may cite (Statistics Canada, Bank of Canada)

Only Statistics Canada series (under the Statistics Canada Open Licence) and Bank of Canada series
(under its terms) may enter the engine, the skill or any public doc, each figure with its notice
(R7). This spec quotes no figure from CREA, Dallas Fed or JST data, and draws no comparison from
them.

**New Housing Price Index** (table 18-10-0205-01, monthly; real = divided by the CPI,
v41690973). A new-house, quality-held index, not a resale one, so the recovery times below
measure how long the new-house index took to regain its own peak, not how long resale prices
took.

| geography | nominal fall | peak → trough | years to trough | back to the peak, years after the trough |
|---|---|---|---|---|
| Toronto | −25.9% | 1989-12 → 1996-05 | 6.42 | 9.08 |
| Vancouver | −30.9% | 1981-03 → 1985-05 | 4.17 | 7.83 |
| Calgary | −22.9% | 1982-04 → 1984-08 | 2.33 | 4.17 |
| Edmonton | −23.8% | 1982-02 → 1985-03 | 3.08 | 4.58 |
| Edmonton | −17.1% | 2007-12 → 2019-11 | 11.92 | not regained by 2026-08 |
| Ontario | −19.4% | 1990-03 → 1996-05 | 6.17 | 7.33 |
| Canada | −11.1% | 1990-03 → 1996-05 | 6.17 | 6.08 |
| Montréal | none of 10% or more | | | |

The table is selective: it is not every nominal fall of 10% or more on these geographies.

In real terms Montréal fell 15.0% (1988-05 → 1998-10) and regained its real peak 5.83 years after
the trough; Toronto fell 38.1% (1989-04 → 1996-11) and has not regained it; Canada fell 27.9% over
20 years (1981-05 → 2001-05) and regained it in 2021-11. Across the 24 closed real episodes of 15%
or more, the trough-to-peak time runs from 1.83 years (Toronto, 1981) to 24.50 (Hamilton, 1989).
Most episodes start at the same national peaks, 1981 and the late 1980s, so they are a handful of
independent events, not twenty-four. The deepest real falls are still open at 2026-08, and are
deeper than Toronto's: Victoria −74.3% and Vancouver −62.9% (both from 1981-02), Windsor −43.0%
(1981-01), British Columbia −40.9% (1990-01), Greater Sudbury −40.8% (1981-04), Edmonton −40.6%
(2007-10) and Saint John, Fredericton and Moncton −40.4% (1981-01).

**What these mean against the panel's `d`.** The panel's drop is measured against the run's own
no-crash path (§5), so a historical fall compares with `d` only in the run's own terms and after
the trend over the fall is added back: `1 − (1 − fall) / (1 + g)^(years to trough)`, with the fall
and `g` both real in a real-mode run or both nominal in a nominal one. In real terms at 0% real
growth the fall IS the drop: Toronto's 38.1% real fall is a 38.1% drop. In nominal terms at the
examples' 2.1% trend, Toronto's nominal 25.9% is a 35.2% drop against trend, Vancouver's 36.6%,
Calgary's 26.5%, Edmonton's (1982) 28.5%, Ontario's 29.1% and Canada's 11.1% a 21.8%; comparing a
nominal fall with a real trend understates the drop. A one-year step of `d` is a peak-to-trough
fall of `1 − 1.021 × (1 − d)` against a 2.1% nominal trend: 8.11%, 18.32%, 28.53% and 38.74% for
10% to 40%. Recovery has the same caveat: history measures the time to regain the PEAK, while
`full:K` means back to the trend line; the two coincide only when the run's growth on its own axis
is 0.

**Permanent is not frozen in nominal terms.** At 0% real growth and 2.1% inflation a permanent
drop regains the pre-crash nominal price after 5.07, 10.74, 17.16 and 24.58 years for 10% to 40%,
and never regains the real one.

**Renewal jumps** (Bank of Canada Valet). Five-year change in the contracted uninsured 5-year
rate (V122667786): 1.96% in 2021-01 to 4.33% in 2026-01, +2.37 pp, the largest of its 103
five-year starts (about 1.7 independent windows); trough to peak 1.94% (2021-02) → 6.00%
(2023-11), +4.06 pp. The posted 5-year rate (V80691335): +1.30 pp over 2021-01 → 2026-01; its
largest five-year change since 1975 is +9.90 pp (1976-09 → 1981-09), over 561 starts (about 9.3
windows).

> Adapted from Statistics Canada, New housing price index, monthly (table 18-10-0205-01), and
> Consumer Price Index, monthly, not seasonally adjusted (table 18-10-0004-01, vector
> v41690973), reference periods 1981-01 to 2026-08, retrieved 2026-10-01. This does not
> constitute an endorsement by Statistics Canada of this product.
>
> Source: Bank of Canada, Valet series V122667786 (monthly, 2013-01 to 2026-07) and V80691335
> (weekly, 1975-01 to 2026-09), retrieved 2026-10-01. Changes were made: the weekly V80691335
> observations are averaged to calendar months, and the figures quoted are monthly values and
> differences between two months, computed for this document.

## 2. Rulings (2026-10-03)

Each one changes what a panel row MEANS. R1–R7 are ruled as written; everything after §2 is
written to them.

**R1. The verdict per row: a conditional Monte Carlo, ordinary dispersion kept, beside the
central line.** Each row runs the config's own Monte Carlo with the stated drop on every path,
the config's ordinary value dispersion kept, the same random numbers as the plain run, and no
extra draw; its `state` is the verdict's own rule and comparable with the plain run's. Each row
ALSO prints its central line (totals, gap, best and the margin rule's state), so the panel
reaches the central case, which a `price_shock` hazard cannot (§1.1). The break-even drop stays
deterministic and solved. Measured stake: P2b's 20% permanent row is `tie` with the dispersion
kept and `option` without it, at both seeds, and its central line is `option` (5.93%) (§1.4).
Cost: 0.48 s (10 years) to 1.06 s (25 years) per row at 5,000 paths.

**R2. A config with any owned `price_shock.annual_hazard` > 0 refuses the panel (X4).** A row is
"given this crash"; random crashes on top would make it "given this crash and maybe more".

**R3. A stated drop moves the house's maintenance.** Maintenance follows the stated value path,
as it does in today's Monte Carlo (maintenance is a rate on value), and the central line follows
it. Measured consequence: on the house example a 40% drop recovered over 7 years makes the house
$8,614 cheaper than no drop, and the year-1 permanent break-even is 38.85% against 29.83% in year
19 (§1.2, §1.3).

**R4. The engine ships no default grid and no historical anchor.** Drops, years and recovery are
typed on the command line every time; the engine has no default and no anchor for any of them.
The standard grid lives in the skill (§9), labelled as the assistant's.

**R5. The joint renewal jump is refused beside a renewal-rate path file (X7).** Shifting every row
of a fitted file is the `rate_shift` the path-file spec left out of scope (its ruling 2).

**R6. The skill's standard recovery set: `permanent`, `full:5` and `full:15`, each labelled as the
assistant's.** The ground is the measured spread of real trough-to-peak times on the shippable
index, 1.8 to 24.5 years over a handful of independent events (§1.8); five and fifteen sit inside
it, and `permanent` stands for the open falls. That spread measures how long the new-house index
took to regain its own peak, not how long resale prices took. The engine accepts any form.

**R7. Licences for the public docs.** Public docs carry only figures derived from Statistics
Canada and Bank of Canada data, each with its notice. CREA data is never published, not even in
derived form, and no comparison drawn from it appears here. The path-file spec's §11 and §12
already quote correlations derived from the Dallas Fed's International House Price Database; they
carry the citation the Dallas Fed asks for.

## 3. The surface

### 3.1 The flag

```
--crash-panel 'drop=0.10,0.20,0.30,0.40;year=1,9;recovery=permanent,full:5,full:15[;jump=0.0237]'
```

- `drop`: one or more fractions in (0, 0.99], the value's fall against its no-crash path in the
  drop year. Sorted and de-duplicated, as `--sweep` does.
- `year`: one or more whole years in 1..`years`. `years` itself is the sale year.
- `recovery`: one or more of `permanent`, `full:K` and `share:R:K`. `share:R:K` returns the share R
  in (0, 1] of the log drop, in equal log steps over the K ≥ 1 years after the drop year;
  `full:K` is `share:1:K`; `permanent` is `share:0`.
- `jump` (optional): a decimal added to the QUOTED rate of every laddered financed option's FIRST
  renewal, after the ladder is written out in full (§6). One market, so one jump for every option.
- Every field is required except `jump`; nothing defaults (R4). Rows are the full product of
  `drop × year × recovery`, at most 48 (§7, X9): 48 rows at 1.06 s is about 51 s of Monte Carlo.
- The panel runs on the base config. `--sweep`, `--break-even` and `--decompose` keep running on
  the base config beside it, and none re-solves anything at a panel row.

### 3.2 The text block (figures, not prose: which-risk §0.1 item 35)

```
crash panel — stated drops, each conditional on happening [drop, year, recovery: command line]
                          central line                                         futures (5,000)
  drop  sale value  condo     rent      rent − condo  level     best   state    best   P(best)  state   sd       underwater
  none  ×1          200,502   207,027   +6,525        0         condo  tie      condo  0.5450   tie     48,104   none
year 1 · permanent
  10%   ×0.900      232,312   207,027   −25,285       −31,810   rent   option   rent   0.7192   option  44,535   none
  20%   ×0.800      264,122   207,027   −57,095       −63,620   rent   option   rent   0.9158   option  41,073   condo 1–2
  ...
  break-even: too close to call from no drop to 5.31%; rent is cheaper above 5.31% (crossing 2.05%) [solved, central case]
```

(P1 at seed 42; its central line is FTB's. The gap is the difference of the printed totals, so it
reads +6,525 where §1.2's unrounded gap is $6,525.78, and the affordability column is left off
here for width.)

- `sale value` is `m(years)`, the sale value as a multiple of the no-crash path's. It is the figure
  that shows why a recovered drop leaves a condo's total unchanged.
- **Central line:** the totals, the gap, `best` and the state of the margin rule `--break-even`
  applies. With two options the gap is `B − A` in the order condo, house, rent (`rent − condo`,
  `rent − house`, `house − condo`), so its sign is comparable across rows; it is computed at the
  formatter as the difference of the two printed totals (which-risk §0.1 item 2). With three
  options it is runner-up − best, with both names.
- **`level`** is the row's gap minus the `none` row's gap, both as printed: how far the stated drop
  moved the central line. It is printed only with two options (X8).
- **Futures:** the conditional run's `verdict.best`, `verdict.prob_best` and `verdict.state`.
  When the state is `disagreement`, the cell names both options with their figures, the verdict's
  rule of 2026-09-04: `condo 0.4968 disagreement · rent 0.5032 of the futures` (P2, 32% permanent,
  seed 42); `P(best)` is then below 0.5. `sd` is the standard deviation over the futures of the
  same `B − A` difference, printed only with two options (X8). On a single-path run the futures
  columns are absent.
- `underwater` lists each owned option's years where `value_t × m(t) × (1 − selling_cost_rate)` is
  below the balance from the one source §6 names; `none` when there are none.
- **One break-even line per (year, recovery)**, tagged `[solved, central case]`, from these fixed
  templates and no others. `lo`, `hi` and `x` are the band's edges and the crossing; an edge
  `solve_crossings` returns as None is "no drop" at the bracket's low end, "a 99% drop" at its high
  end, and "the next crossing" when another crossing ends the band:
  - `break-even: A is cheaper below lo; too close to call from lo to hi; B is cheaper above hi (crossing x)`
  - `break-even: too close to call from no drop to hi; B is cheaper above hi (crossing x)`
  - `break-even: A is cheaper below lo; too close to call from lo to a 99% drop (crossing x)`
  - `break-even: too close to call from no drop to a 99% drop (crossing x)`
  - with no crossing, `break-even: no crossing from no drop to a 99% drop: ` and then the stretches
    of the bracket read by the margin rule the rows' central state uses, so the line never
    contradicts a row: `A is cheaper throughout`; `too close to call throughout`; `too close to
    call from no drop to hi; A is cheaper above hi`; `A is cheaper below lo; too close to call from
    lo to a 99% drop`; and, for a margin that enters the band more than once, the same clauses in
    order joined by `; `, with `A is cheaper from lo to hi` for a decisive stretch between two
    ties. The stretches are found by reading the rule at 34 evenly spaced drops and at every drop
    of the grid, and bisecting each change of state;
  - with other than two options, X8's code and fact instead.
  The no-crossing line carries no hint to widen: the bracket is the whole accepted range. (Ruled
  2026-10-03: FTB with `full:7` from year 1 is a tie in every row, and "condo is cheaper
  throughout" would have contradicted all of them.)
- Every row of a config with an `income` block carries each option's peak affordability ratio and
  its years above the threshold (`sweep.affordability_of`, as `--sweep` rows do): a jump moves the
  financed options' ratios and, under R3, a drop moves the house's. With `jump`, the header names
  it and the options it reached (`jump +2.37 pp at the first renewal: condo`).
- No closing line, no route advice, no explanation of a refusal beyond its one fact.

### 3.3 `--json`

A top-level `crash_panel` object, absent without the flag:

```
{"grid": {"drop": [...], "year": [...], "recovery": [{"form": "share", "share": 1.0, "years": 5}, ...],
          "jump": null | {"value": 0.0237, "options": ["condo"]}},
 "source": "command line",
 "no_drop": <row>,
 "rows": [<row>],
 "break_evens": [{"year", "recovery", "key": "crash.drawdown", "options", "bracket": [0, 0.99],
                  "break_evens": [...], "no_crossing": null | {"cheaper", "lo", "hi", "tie_bands"}}
                 | {"year", "recovery", "refused": {"code", "fact"}}],
 "refused": null | {"code", "fact"}}

<row> = {"drop", "year", "recovery", "sale_multiple",
         "central": {"totals": {...}, "best", "runner_up", "margin_pv", "margin_frac", "state", "rule"},
         "level_pv": float | null,
         "futures": null | {"best", "prob_best", "mc_best", "mc_prob_best", "state", "rule", "gap_sd": float | null},
         "underwater_years": {"condo": [...]}, "affordability": {...} | null}
```

`no_crossing` carries no `widen` key; its `tie_bands` lists the too-close-to-call stretches, each
`[lo, hi]` with `null` at the bracket's own end (`[]`: decisive throughout; `[[null, null]]`: too
close to call throughout). Each field's meaning goes in one place: a new
`docs/reference/API_CONTRACT.md` section, "The `crash_panel` block", which also says that
`prob_best` is below 0.5 in the `disagreement` state. The skill reads it there and never restates
it.

### 3.4 The read-back line

One line in `--read-back` and in `assumptions.read_back`, after the `renewals:` lines:

```
crash panel: drops 10%, 20%, 30%, 40%; years 1, 9; recovery permanent, full over 5 years, full over 15 years; stated on the command line, not a forecast and not a probability
```

`--read-back short` counts it in its closing line like every other full-block line.

## 4. How a stated drop composes with the value path

**One home for the multiplier.** A new module `src/hde/crash_panel.py` holds
`drop_path(years, d, c, recovery) -> Tuple[float, ...]`, the multiplier `m(t)` for t = 1..years:

```
m(t) = 1                                     t < c
m(t) = exp(−L × (1 − R × min(1, (t − c) / K)))   t ≥ c,   L = −ln(1 − d)
```

"Back to trend" is back to the no-crash path, not back to the pre-crash price (§5). Every
consumer reads this function; none re-derives `m`.

**The central line.** `_compute_condo_option` and `_compute_house_option` take an optional
`drop_path` (default None: today's call, byte-identical). `value_N` is multiplied by `m(years)`;
the house's maintenance in year t by `m(t)`; `_annual_costs_for_option` multiplies the house's
`house_val` by `m(t)` (R3).

**Selling costs.** Applied to the dropped value, unchanged: `equity_N = value_N × m(years) × (1 −
selling_cost_rate) − balance_N`. A drop `d` therefore costs `d × value_N × (1 −
selling_cost_rate)` of equity at sale, not `d × value_N`; §1.3's oracle is this identity.

**The Monte Carlo.** `_simulate_condo_pv_once` and `_simulate_house_pv_once` take the same
optional path and multiply every value track by `m(t) / m(t − 1)` in year t, after
`_apply_value_dispersion` (where `_apply_price_shock` would sit; R2 refuses a live hazard). No
draw is taken, so every row is common-random-number paired with the plain run and with every
other row, and a run with no value dispersion takes the drop too. §1.4 and §1.5 were measured
this way. An earlier prototype instead added `(ln m(t) − ln m(t − 1)) / s` to the year's value
z; that is exact only when each owned option has its own `s`, since a house and a condo with
different `value_growth_vol` share one z per path. On the one-owned-option households the two
forms give the same figures.

**Timing.** For a condo a permanent drop gives the same totals in every year (§1.2): only
`m(years)` reaches its total, in the central line and on every path. Timing matters when the
value comes back (a late drop has less time to) and for the house (maintenance, R3). The engine's
drop is a one-year step; a slide over F years whose trough falls before the sale prices exactly as
a step at the trough year, because only the sale value reaches a condo's total. Historical falls
took 2.33 to 6.42 years to the nominal trough (§1.8); a slide still under way at the sale is
priced as the smaller step it has reached.

**What a recovered drop leaves.** With `full:K` from year `c` and the sale in year `T`:

- when the recovery completes before the sale (`c + K ≤ T`), `m(T) = 1`: a condo's total is
  unchanged, whatever the drop (§1.2), and only a house's maintenance moves (R3);
- when it does not (`c + K > T`), the sale meets the share `(c + K − T) / K` of the log drop,
  `m(T) = (1 − d)^((c + K − T) / K)`, and the condo bears that part of the permanent loss: on
  FTB-25L at 20% from year 24 with `full:7`, 87.0% of the permanent row's added cost (log share
  6/7 = 85.7%).

Averaged over the T drop years `c = 1..T`, `full:K` leaves `Σ_{j=0}^{min(K,T)−1} (K − j)/K / T` of
the permanent log loss, which is `(K + 1) / (2T)` when `K ≤ T`: 0.12, 0.16 and 0.32 for `full:5`,
`full:7` and `full:15` at T = 25, and the condo's added cost follows at 0.124, 0.165 and 0.331 of
the permanent row's at a 20% drop. This is arithmetic over stated years, not a probability that
a drop falls in any of them. It is also why a hazard whose drops recover still moves a verdict:
its drops in the last K years of the horizon are the binding case.

**The demographic prior.** Its drift composes multiplicatively with `m(t)` in the Monte Carlo and
does not reach the central line, as today. Its `drawdown_weight_tilt` multiplies only a
`price_shock` hazard, which R2 refuses.

## 5. Real and nominal

`m(t)` multiplies the run's own value path whatever the mode, so the same stated drop is the same
fraction of the home in either mode. What differs is the path it multiplies: in nominal mode the
no-crash path includes inflation, so a permanent drop at 0% real growth regains the pre-crash
nominal price after 10.74 years at 20% (§1.8) while staying 20% below where the home would have
been; in real mode at 0% real growth it never regains the purchase price. That is why recovery is
defined against the path and not against the pre-crash price: a price-level definition would make
`permanent` mean "recovers with inflation" in nominal mode and "never" in real mode, and the same
household would get two answers to one question.

The `sale value` column is the multiple of the no-crash path. History compares with `d` only in the
run's own terms and after the trend over the fall is added back (§1.8). The skill carries that
conversion (§9), never the block.

## 6. Renewals, affordability, early exit

- **Renewal re-solve.** A drop never reaches a payment: the balance and each renewal's re-solve
  depend on the loan and the rates only (§1.1). The engine prices no loan-to-value test at renewal
  and no lender's response to an underwater borrower; the `underwater` column is the figure the
  reader needs to see where that gap bites.
- **The joint jump.** For every financed option that states `mortgage_renewal_years` and a ladder:
  1. write the quoted ladder out in full: one entry per renewal of the amortization,
     `n = ⌈mortgage_term_years / mortgage_renewal_years⌉ − 1` (the loader's own count), entry `i`
     being `quoted[min(i, len(quoted) − 1)]` (the schedule's carry-forward, made explicit);
  2. add `j` to entry 0 only;
  3. convert each entry once, `effective_mortgage_rate(q, mortgage_rate_compounding)` (`rates.py`,
     the loader's own conversion);
  4. give the row a copy of the option's params with `mortgage_renewal_rates` (effective) and
     `mortgage_renewal_rates_quoted` replaced (`dataclasses.replace`).
  The central line, the Monte Carlo, the affordability channel and the underwater balance all read
  that one ladder through their existing calls (`renewal_args_for`, `renewal_segments_for`), so no
  second function writes a ladder. Adding `j` to a ladder that was not written out would jump every
  renewal on a scalar ladder (§1.6). The jump lands at the first renewal, which the horizon must
  PRICE (`renewals_priced_inside` ≥ 1 on at least one option), or the panel refuses (X6).
  Affordability re-runs with the jumped ladder: on FTB-10L +2.37 pp moves the peak from 36.21% to
  37.01% and the years above 32% from 1–5 to 1–10 (§1.6).
- **The underwater balance** comes from one place, the split `_financing_pv` makes: `pv.balance_at`
  on `renewal_segments_for(params)` when the option has a ladder (the row's jumped copy under a
  jump), `pv.outstanding_balance` otherwise (§1.7).
- **Affordability without a jump.** A drop never moves the condo's or the renter's cost array. It
  moves the house's maintenance line under R3. The Monte Carlo's affordability channel keeps
  pricing the house's maintenance on the central path, as it does today for every channel-1
  draw; that gap predates this panel and is out of scope (§12).
- **Early exit.** There is none to interact with. A drop in year `years` is the sale into the
  trough, and `share:R:K` with `c + K > years` is the sale part-way back; both print as ordinary
  rows. An earlier sale is a different config (`years`), which the user runs separately.

## 7. Refusals

Each prints its code and one measured fact, and the legal neighbour one step away loads (§10 row 9).

| code | when | the fact printed | the neighbour that loads |
|---|---|---|---|
| X1 `drop_out_of_range` | a drop ≤ 0 or > 0.99 | `drop 1.0 is outside (0, 0.99]` | 0.99 |
| X2 `year_out_of_range` | a year < 1 or > `years` | `year 11 is past the 10-year horizon` | `years` |
| X3 `recovery_malformed` | R outside (0, 1], K < 1, an unknown form | `share 1.2 is outside (0, 1]` | `share:1:7` |
| X4 `hazard_wired` | any owned `price_shock.annual_hazard` > 0 (R2) | `condo.price_shock.annual_hazard is 0.03` | the same block at hazard 0, which the engine treats as unwired (`_world_draws`) |
| X5 `no_owned_option` | neither condo nor house priced | `no owned option is priced` | one owned option |
| X6 `jump_without_ladder` | `jump` and no financed option prices a renewal inside the horizon | `no financed option prices a renewal inside 4 years` | the same config with a renewal inside the horizon |
| X7 `jump_beside_path_file` | `jump` and a `renewal_rates.path` file (R5) | `renewal_rates.path is set` | the same flag without `jump` |
| X8 `not_two_options` | the break-even line, `level` and `sd` only, with other than two priced options; the rows still print | `3 options are priced` | two options |
| X9 `too_many_rows` | more than 48 rows | `the grid has 54 rows` | 48 |

A panel refused by X4 or X5 prints the refusal in place of the block and the run's other output is
unchanged; the exit code is the run's.

## 8. Honesty lines

- The header tag `[drop, year, recovery: command line]` and the read-back line say every figure of
  the grid was stated for this run. The engine never prints "likely", "expected", "historical" or
  any probability of a drop.
- `P(best)` is the probability over the futures the config draws, GIVEN the stated drop. It is
  never a probability of the drop.
- The engine prints no historical anchor (R4). The skill may cite only Statistics Canada and Bank
  of Canada figures (§1.8), with each one's notice, and labels any grid it chose as its own.
- What a drop does not reach is the skill's to say (§9), from §6's list: no forced sale, no
  loan-to-value test at renewal, no change to rent, fees or taxes, and maintenance only on a house.

## 9. Skill guidance (one home: `references/gates.md`, new §11)

SKILL.md is untouched; it stands at 2,597 words against `test_skill_contract.py`'s budget of fewer
than 2,600. In `references/gates.md` §6, "Smallest worst case →" becomes "Smallest worst case (a
named crash → `--crash-panel`, §11) →". New §11, the one home, appended after §10:

> ## 11. A named crash: `--crash-panel`
>
> When the user asks "what if prices crash", run the panel; never answer from the hazard channel.
> The standard grid, typed by you and labelled yours: drops 10%, 20%, 30%, 40%; years 1 and
> `years − 1`; recovery `permanent`, `full:5` and `full:15`. Quote each row's figures and each
> break-even line verbatim, and read their meaning in `docs/reference/API_CONTRACT.md`, "The
> `crash_panel` block". Each row has a central line and the futures beside it: quote both, and the
> `level` column as how far the drop moved the central gap. A `disagreement` row names both
> options with their figures; say so, never pick one. Say the rows are conditional: "if the value
> drops 20% next year and never recovers, renting comes out $57,095 cheaper" — never "a 20% crash
> is likely" or "in a crash". The panel's drop is measured against the run's own no-crash path, in
> the run's own terms: compare a historical fall with it only in the same terms (real fall against
> real trend in a real-mode run, nominal against nominal in a nominal one), with the trend over the
> fall added back. In real terms at 0% real growth the fall is the drop: Statistics Canada's New
> Housing Price Index for Toronto fell 38.1% in real terms from 1989 to 1996 and had not regained
> that peak by 2026, which is a 38.1% `permanent` drop so far. History measures the time to regain
> a peak; `full:K` means back to the trend line; they coincide only at 0% growth in the run's own
> terms. Cite only Statistics Canada or the Bank of Canada, and carry the notice with any figure
> derived from them: "Adapted from Statistics Canada, New housing price index, monthly (table
> 18-10-0205-01), and Consumer Price Index, monthly, not seasonally adjusted (table
> 18-10-0004-01), reference periods 1981-01 to 2026-08. This does not constitute an endorsement by
> Statistics Canada of this product." For a Bank of Canada series, name it, say "Source: Bank of
> Canada", and say what you changed (a monthly average, a five-year difference). Name, each with
> its direction, what a drop does not reach: no forced sale and no loan-to-value test at renewal
> (each favours buying); rent unchanged (favours buying, if market rents would fall too); fees and
> property taxes unchanged (favours renting, if a lower assessment would lower the bill); a
> house's maintenance falls with its value (favours the house). A recovered drop leaves a condo's
> total unchanged when the recovery ends before the sale, because the engine prices the home only
> at the sale: say that from the `sale value` column, not as reassurance. Use `jump` only for the
> joint question ("what if rates also jump at renewal"), with a figure you state as yours.

With both edits applied, `tests/test_skill_contract.py` gives 17 passed (measured, then
reverted). The flag is named only in references/, which that file's flag test does not read, so
the test passes before the flag exists; it is re-run after commit 5.

## 10. Tests: each class pinned, each pin mutated both ways

| # | Class | Pin | Mutation that must fail it |
|---|---|---|---|
| 1 | Opt-out | Without the flag, the nine `tests/fixtures/opted_out/*.json` documents are byte-identical (no new golden). | Any default `drop_path` that is not None |
| 2 | One home | `drop_path` is the only function computing `m`; a grep pin finds no other `exp(-` on a log drop in `src/hde`. | A second copy in `deterministic.py` |
| 3 | Oracle | FTB, permanent: the crossing equals 6,525.78 / 318,100.15 to 1e-9 relative. | Selling cost applied to the undropped value: the crossing moves to 0.019489 |
| 4 | Carried forward | A condo's permanent row is identical in years 1, 9 and 10. | The drop applied only in its own year (m back to 1): the totals equal the base |
| 5 | Back to the path, in log steps | `full:7` from year 1 leaves FTB-25L's condo total equal to the base bit for bit ($377,856.33); `share:0.5:5` from year 1 at 10% gives `m(10)` = 0.9487 and FTB's condo $216,825. | Recovery stepped in level instead of log (`m = 1 − d(1 − R·frac)`): `m(10)` = 0.95 |
| 6 | House maintenance (R3) | House example, year 1, `full:7`, 40%: house total $341,252 (< $349,866). | Maintenance left on the no-crash path: the total returns to $349,866 |
| 7 | No draw | The renter's PVs and each generator's end state are identical across every row and the plain run. | One `random()` taken per row |
| 8 | Conditional run | A path of all ones, built directly because X1 refuses a 0 drop, gives the plain run's `prob_best` exactly (P1 0.5450 at seed 42). | The panel runs on another seed or binding |
| 9 | Refusals both ways | Each of X1–X9 against its neighbour in §7. | Each refusal deleted, and each widened onto its neighbour (X1 widened to refuse 0.99; X4 widened to a hazard of 0; X2 widened to `years`) |
| 10 | Rendered output | Every line of the block matches one of §3.2's fixed templates; each gap equals the difference of its row's printed totals; each `level` equals the difference of two printed gaps. The no-crossing templates: FTB, `full:7` from year 1 prints `break-even: no crossing from no drop to a 99% drop: too close to call throughout [solved, central case]`, the house example's `full:7` prints `house is cheaper throughout`, and each other no-crossing template is pinned against its rows' states; no line of the block contains `widen`. FTB, permanent from year 1 prints the band-from-no-drop template. | A closing sentence added; a gap read from `margin_pv` and rounded separately; the panel's no-crossing template deleted, so `threshold_sentences`' line with its widen hint prints; the no-crossing template widened onto a row with a crossing (FTB permanent prints "no crossing") |
| 11 | Underwater | FTB, year 1: a 12% drop has no underwater year 1, a 13% drop has. FTB-10L with `jump=0.0237`, 45% permanent from year 1: underwater years 1–10. | Selling cost omitted: the year-1 boundary moves to 16.89%. The unladdered balance (`outstanding_balance`) under the jump: years 1–9 |
| 12 | Joint jump | FTB-25L (four priced renewals), `jump=0.0237`: condo $403,362.00 and years above 32% 1–10; with a 20% permanent drop, rent by $689, `tie`. | The jump on every renewal (`quoted[0] += j` on the scalar ladder): condo $432,244.22, years 1–11; rent by $29,571, `option` |
| 13 | Read-back | The line appears once in `--read-back` and in `assumptions.read_back`, after `renewals:`. | The line printed without the flag |
| 14 | Level apart from spread | P2b at seed 42, 20% permanent from year 1: `level` −40,835 (the central gaps' difference), `sd` 77,718, futures `condo` 0.6080 `tie`, central `condo` `option`. | `level` read from the futures' mean gap (−40,668); `sd` taken from the plain run (88,671) |
| 15 | Disagreement | P2 at seed 42, 32% permanent from year 1: the futures cell names `condo 0.4968 disagreement` and `rent 0.5032`; the JSON row carries `mc_best` and `mc_prob_best`. | `mc_best` or `mc_prob_best` dropped from the row |

## 11. Commit order

The suite is green at every commit, and row 1's goldens hold through commit 6.

1. `feat(crash_panel)`: `drop_path`, the grid parser, X1–X3 and X9, and their unit tests (rows 2,
   9 in part).
2. `feat(deterministic)`: the optional `drop_path` on both owned options and on
   `_annual_costs_for_option`; rows 3–6 and 11's first pin on the central line.
3. `feat(monte_carlo)`: the multiplier after dispersion; rows 7 and 8.
4. `feat(crash_panel)`: the panel runner (rows with their central line and conditional run, the
   level and spread, break-evens through `solve_crossings`, the joint jump by §6's four steps),
   X4–X8; rows 11 (second pin), 12, 14 and 15.
5. `feat(cli)`: the flag, the text block with its own break-even templates, the `--json` block,
   the read-back line, the API_CONTRACT section; rows 10 and 13.
6. `docs(skill)`: §9's two edits to `references/gates.md`.

## 12. Out of scope

- A probability of a crash, or any change to `price_shock`.
- Momentum or a fitted shape for ordinary moves.
- The Monte Carlo's affordability channel pricing the house's maintenance on the central path for
  every channel-1 draw (§6). It predates this panel.
- A forced sale, a loan-to-value test at renewal, mortgage-insurance requalification, and an
  early exit. Each is named as unpriced (§9).
- Rent, fees or property taxes responding to a drop.
- A `rate_shift` on a path file (R5).
- Composition with `--sweep` (a panel re-solved at every sweep point).

## 13. Measurements

Every command runs with `uv run python` from a checkout of 3b7306a, on the configs defined at the
top of this spec. The prototype wraps three engine functions in-process: for the central line,
`deterministic._financing_pv` (its `value_N` argument multiplied by `m(years)`, on calls from
`hde.deterministic` only, since `monte_carlo` imports the same function) and
`deterministic._maintenance_rate_for_year` (multiplied by `m(year)`); for the Monte Carlo,
`monte_carlo._apply_value_dispersion` (its returned tracks multiplied by `m(t) / m(t − 1)`, `t`
read from the caller's frame). Each wrapper is restored in a `finally` and the restore is
asserted. The verdict is `models.compute_verdict` on `compute_deterministic` and
`run_monte_carlo`.

| Figure | Command |
|---|---|
| §1.1 line numbers | `sed -n` on `src/hde/monte_carlo.py` (665, 1075, 1079, 1627) and `src/hde/deterministic.py` (169–191, 417, 482, 683) |
| central totals identical with and without `price_shock` | `compute_deterministic` on `tests/fixtures/uncertainty_surface.yaml` (via `load_config_dict`) and on a copy with both `price_shock` blocks and their `sources:` entries removed |
| §1.2 tables | the central-line wrapper per (drop, year, recovery) on FTB, FTB-25L and the house example |
| §1.3 house with maintenance on the no-crash path (29.21%) | the central-line wrapper with `_maintenance_rate_for_year` left unwrapped, `solve_crossings` on the house example, permanent from year 1 |
| §1.3 crossings, bands, no-crossing sentences, oracle | `break_even.solve_crossings('crash.drawdown', options, 0, hi, totals_at)` at hi = 0.95 and 0.99, then `break_even.threshold_sentences('crash.drawdown', out, out['tie_band_fraction'])`; `break_even.floor_at_zero('crash.drawdown')`; the oracle `gap / pv_single(value_N × (1 − selling_cost_rate), r, years)` and, for the mutation, `gap / pv_single(value_N, r, years)` |
| the households' configs and plain runs | each household rebuilt from FTB-10L or FTB-25L by the keys in the table at the top, at seeds 42 and 4242 |
| §1.4 table, seed-unstable rows, byte-identical renter PVs | the Monte Carlo wrapper on each household at seeds 42 and 4242: the plain run, permanent from year 1 and `full:7` from year T−1 at 10% to 40%, `full:7` from year 1 at 40%, `share:0.5:5` from year 1 at 30% (P2b); `res.rent.pvs.tobytes()` compared across rows |
| the `disagreement` row | P2, permanent from year 1 at 31%, 32%, 32.5%, 33%, 34%, 35%, both seeds: `verdict.best`, `state`, `prob_best`, `mc_best`, `mc_prob_best` |
| the dispersion row (R1) | P1, P2, P2b at both seeds, 20% permanent from year 1, `value_growth_vol` as configured and at 1e-6 |
| §1.5 level and spread | P1, P2, P2b at both seeds: no drop; permanent from year 1 at 10% to 40%; `full:5` from year T−1 and `full:15` from year 1 at 20%. `level` = central `rent − condo` minus the no-drop row's; the futures' gap = `res.rent.pvs − res.condo.pvs`, its mean and `std()`; the $620 bound is the largest |(futures' mean − no drop's) − level| over the 36 rows, $619.59; the recovered row: P2, `full:15` from year 1 at 20%, against the plain run at both seeds, `prob_condo_cheapest` equal and `max |Δ condo.pvs|` = 4.66e-10 |
| per-row cost 0.48 s / 1.06 s | `OMP_NUM_THREADS=1`, one P1 and one P2 conditional run (20% permanent from year 1), `run_monte_carlo` timed three times after a warm-up |
| §1.6 table | FTB-10L and FTB-25L with `mortgage_renewal_rates` [0.0455 + j, 0.0455, 0.0455, 0.0455] for j = 0, 0.0130, 0.0237; the central-line wrapper at no drop and a 20% permanent drop in year 5; `det.income_report.condo_ratios` and `years_condo_exceeds`; `solve_crossings` at drop year 5, permanent, bracket [0, 0.99] |
| §1.6 scalar against first-only | the same configs with `mortgage_renewal_rates: 0.0692`; `deterministic.renewals_priced_inside(spec.condo, years)` gives 1 on FTB-10L and 4 on FTB-25L; the loader refusal from FTB plus `condo.mortgage_renewal_years: 5` alone, via `uv run hde` |
| §1.7 underwater figures | `pv.outstanding_balance(loan, mortgage_rate, mortgage_term_years, t, payment)` and `pv.balance_at(renewal_segments_for(spec.condo), mortgage_term_years, loan, t)` for every year, against `initial_value × (1 + g)^t × m(t) × (1 − selling_cost_rate)`, on FTB, FTB-10L at j = 0.0237, FTB-25L and FTB-25L at j = 0.0237 |
| §4 what a recovered drop leaves | FTB-25L and FTB at 20% and 40%: the central-line wrapper for `full:5`, `full:7`, `full:15` at every drop year `c = 1..T`, the condo's added cost divided by the permanent row's, and `ln m(T) / ln(1 − d)`, each averaged over `c` |
| §1.8 NHPI table, real episodes, open falls | monthly peak-to-trough on every NHPI geography with 120+ months, nominal and divided by CPI v41690973, falls of 10% or more, from the Statistics Canada tables in the notice (retrieved 2026-10-01) |
| §1.8 R6 spread | the closed real episodes of 15% or more from that run: 24, minimum 1.83 years after the trough (Toronto 1981), maximum 24.50 (Hamilton 1989); open real episodes deeper than 38.1% |
| §1.8 trend conversions | `1 − (1 − fall) / 1.021^(years to trough)`; `1 − 1.021 × (1 − d)`; `ln(1 / (1 − d)) / ln(1.021)` |
| §1.8 renewal jumps | Valet V122667786, V122667780 and V80691335 as calendar-month means, rate at t + 60 months minus at t |
| licence names and notice wording | statcan.gc.ca/en/reference/licence and bankofcanada.ca/terms, fetched 2026-10-03 |
| SKILL.md 2,597 words, budget below 2,600 | `python3 -c "print(len(open('.claude/skills/hde/SKILL.md').read().split()))"`; `tests/test_skill_contract.py` |
| nine opted-out goldens | `ls tests/fixtures/opted_out` |
| §9's edits: 17 passed | both edits applied to `references/gates.md`, `python -m pytest -q -p no:cacheprovider tests/test_skill_contract.py`, the file restored |

## 14. As built (2026-10-03)

Where the build had to choose because this spec is silent, the choice and its home in
`docs/reference/API_CONTRACT.md`, "The `crash_panel` block":

- **Every whole-panel refusal prints in place.** §7 says so for X4 and X5; X1–X3, X6, X7 and X9
  print the same way, `crash panel — refused (<code>): <fact>`, with `refused` set in the JSON and
  the exit code the run's. A flag without the grid's shape exits 1, as `--sweep` does. The facts
  §7 does not give: `year 0 is before year 1`, `years 0 is below 1`, `years 2.5 is not a whole
  number`, `recovery '<token>' is not permanent, full:K or share:R:K`, and `1 option is priced`.
- **The `none` row prices the jump.** Under `jump` every row, `none` included, prices the jumped
  ladder, so `level` is the drop's move with the jump in place (§1.6's "+2.37 pp, none" row).
- **Futures are absent under `--no-monte-carlo`** as on a single-path run.
- **The affordability column** prints each option's `max <ratio> breaches years [...]`, the
  `--sweep` rows' clause.
- **The read-back line** carries `jump +<pp> pp at the first renewal: <options>` when `jump` is
  set; `share:R:K` reads `share R over K years` there and in the group lines; a refused panel
  carries no line; under `--read-back` no row is priced.
- **One break-even line per crossing** when an axis crosses more than once, each from §3.2's
  templates, with "the next crossing" for an edge another crossing ends.
- **The JSON** lists rows grouped by year, then recovery, then drop, in the break-even entries'
  order; `permanent` serialises as `{"form": "permanent", "share": 0.0, "years": null}`.
