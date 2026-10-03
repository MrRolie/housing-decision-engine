# Crash stress panel — design (2026-10-03)

**Status:** proposed, 2026-10-03. Design only; no engine code is written by this document.
Measured against main at 3b7306a.
**Lineage:** `docs/specs/2026-09-21-one-world-simulation.md` §2 (one housing market per path);
`docs/specs/2026-09-22-which-risk-decides-it.md` §0.1 item 35 (the block prints figures, not
interpretation); `docs/specs/2026-10-01-renewal-rate-path-file.md` (the ladder, the path file and
its ruling 2, `rate_shift` out of scope).

Every figure below was measured, and §13 gives each one's command. "Prototype" means
exploratory scripts that wrap three engine functions in-process and restore them (§13 says which);
they are not committed, and the engine was not edited. "The worked households" are five
condo-against-rent configs kept outside this repo: P1 and P1b (10 years), P2, P2b and P2m (25
years), which differ only in their volatilities. P1's and P1b's central line equals
`examples/first_time_buyer_montreal.yaml`'s to the dollar; P2, P2b and P2m share one 25-year
central line.

---

## 0. What is asked, and the shape this spec gives it

The question: "a panel to help the decision in the case of a real estate market crash: simulate
multiple market crashes of different magnitude that happen once."

The answer this spec builds is a CONDITIONAL panel. Each row says: if the home's value drops by
`d` in year `c` and comes back in the stated way, here are the totals, the gap, the verdict and
its decisiveness. It never says how likely a drop is. The probability of a crash stays where it
is today, in `price_shock`, and the panel refuses to run beside one (§7, R2).

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
  $399,506.53).
- The central line has no value path. The condo's sale value is the closed form
  `initial_value × (1 + g)^years` (`deterministic.py:417`); the house tracks a yearly value only
  to price maintenance (`deterministic.py:482`, `maintenance_rate × house_value`).
- The sale value enters a total in exactly one place: `equity_N = value_N × (1 − selling_cost_rate)
  − balance_N` (`deterministic.py:191`). The mortgage balance, the payment and every renewal
  re-solve depend on the loan and the rates, never on the value.
- The house's maintenance follows the crashed value in the Monte Carlo (`monte_carlo.py:1075`,
  then `:1079`), but the affordability channel prices the house's maintenance on the central
  value path on every path (`deterministic.py:683`, called from `monte_carlo.py:1627`).
- The engine sells only at the horizon. There is no early exit; unpriced-dimensions §9 lists it
  as "solve `years` over the user's own range".

### 1.2 The panel on the central line (prototype)

The prototype multiplies `value_N` by `m(years)` and each house maintenance year by `m(year)`
(§4), and leaves everything else alone.

**`examples/first_time_buyer_montreal.yaml`** (condo against rent, 10 years, nominal, 0% real
growth). Base: condo $200,502, rent $207,027; condo cheaper by $6,526 (3.25%), `tie`.

| year | recovery | drop | condo | rent | rent − condo | best | state (margin rule) |
|---|---|---|---|---|---|---|---|
| 1 | permanent | 10% | 232,312 | 207,027 | −25,284 | rent | option |
| 1 | permanent | 20% | 264,122 | 207,027 | −57,094 | rent | option |
| 1 | permanent | 30% | 295,932 | 207,027 | −88,904 | rent | option |
| 1 | permanent | 40% | 327,742 | 207,027 | −120,714 | rent | option |
| 1 | half over 5 | 10% | 216,825 | 207,027 | −9,798 | rent | tie |
| 1 | half over 5 | 20% | 234,084 | 207,027 | −27,057 | rent | option |
| 1 | full over 7 | 10% to 40% | 200,502 | 207,027 | +6,526 | condo | tie |
| 9 | full over 7 | 10% | 227,970 | 207,027 | −20,943 | rent | option |
| 9 | full over 7 | 40% | 313,293 | 207,027 | −106,265 | rent | option |
| 9 or 10 | permanent | 10% to 40% | as year 1, permanent | | | | |

**`examples/mortgage_house_vs_rent.yaml`** (house against rent, 20 years). Base: house
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

### 1.3 The break-even drop: `solve_crossings` does it unchanged

`break_even.solve_crossings(key, options, lo, hi, totals_at)` takes any callable. With
`key = "crash.drawdown"`, bracket [0, 0.95] and `totals_at(d)` returning the prototype's
crashed totals, it returns the crossing and the tie-band edges, and its band sentence renders the
figures as percentages (`sweep._fmt_value` formats an unknown leaf as a rate). The rest of the
break-even machinery (`solve_break_even`, `_affordability_at`, `deterministic_boundaries`,
`_ranking_at`) reaches values only through `load_at(raw, key, v)` on a YAML key, so it cannot be
reused for an axis that is not in the YAML.

An exact oracle exists for a condo against rent with a permanent drop: the condo's total rises by
`d × value_N × (1 − selling_cost_rate) / (1 + r)^years`, linear in `d`, so the crossing is
`d* = gap / (value_N × (1 − selling_cost_rate) / (1 + r)^years)`. The solver matches it to six
digits on both central lines:

| central line | year | recovery | crossing | tie band | oracle |
|---|---|---|---|---|---|
| first-time buyer (= P1, P1b) | 1, 9 or 10 | permanent | 2.0515% | below the bracket's low end to 5.31% | 6,525.78 / 318,100.15 = 0.020515 |
| | 1 | half over 5 | 4.0609% | to 10.33% | |
| | 1 | full over 7 | none: condo cheaper throughout | | |
| | 9 | half over 5 / full over 7 | 2.2768% / 2.3893% | to 5.88% / 6.16% | |
| P2, P2b, P2m | 1, 24 or 25 | permanent | 32.1548% | 21.81% to 43.02% | 65,652.41 / 204,176.38 = 0.321548 |
| | 1 | half over 5 | 53.97% | 38.86% to 67.53% | |
| | 1 | full over 7 | none: condo cheaper throughout | | |
| | 24 | half over 5 / full over 7 | 35.02% / 36.40% | | |
| house against rent | 1 / 19 / 20 | permanent | 38.85% / 29.83% / 29.51% | 30.70%–47.41% / 23.57%–36.40% / 23.32%–36.02% | 29.21% if maintenance ignored |

The first-time buyer's base is already inside the tie band, so the band's low edge is the
bracket's low end.

### 1.4 Does a stated crash change a decision? (conditional Monte Carlo, worked households)

The prototype adds the drop to the world's value z's, `Δz_t = (ln m(t) − ln m(t−1)) / s`, which
is exact for the lognormal model and consumes no draw. Every row is therefore common-random-number
paired with the baseline: the renter's 5,000 PVs have one sha256 per household and seed across
all 25 rows. The baselines reproduce the households' recorded baseline verdicts exactly (P1
0.5450/0.5476, P1b 0.5056/0.5044, P2 0.8582/0.8558, P2b 0.7774/0.7808, P2m 0.9060/0.8978).
"Changes a decision" means `verdict.best` or `verdict.state` differs from the baseline at BOTH
seeds 42 and 4242; a run with |P − 0.65| < 0.02 flags the change as near the floor.

| households | drop, year 1 or year T−1, permanent | full recovery over 7 years from year 1 | full recovery over 7 years from year T−1 |
|---|---|---|---|
| P1 (base `tie`, P 0.545) | every drop from 10%: rent `option`, P 0.72 at 10%, 0.92 at 20% | no change at any size | every drop from 10%: rent `option` |
| P1b (base `tie`, P 0.506) | every drop: rent `option`; at 10% P 0.669/0.675, near the floor | no change | every drop: rent; 10% is `tie`/`option` (0.647/0.651), near the floor |
| P2 (base `option`, P 0.858) | 10%, 20%: no change (P 0.77; 0.660/0.667 at 20%, near the floor); 30%: `tie` (0.52); 40%: rent `tie` (0.62) | no change | 30%: `tie` (0.58); 40%: rent `tie` (0.56) |
| P2b (base `option`, P 0.777) | 10%: no change; 20%: `tie` (0.61/0.62); 30%: `tie`; 40%: rent `tie` | no change | 20%: `tie`, near the floor (0.63/0.64); 30%, 40% as permanent |
| P2m (base `option`, P 0.906) | 10%, 20%: no change; 30%: `tie` (0.55); 40%: rent `tie` (0.63) | no change | 30%: `tie` (0.62); 40%: rent `tie` (0.55) |

With half recovery over 5 years from year 1, P2b's 30% row is `tie` at seed 42 (0.643) and
`option` at seed 4242 (0.655): seed-unstable, not a change.

**The ordinary value dispersion decides one row.** Holding the stated drop and setting
`value_growth_vol` to 1e-6 instead of the household's figure: P2b at a 20% permanent drop in
year 1 is `option` (0.7086/0.7004) instead of `tie` (0.6080/0.6172), at both seeds. P1, P2 and
P2b's other rows keep their states.

### 1.5 The "2022-like" variant: a renewal jump with the drop

The first priced renewal's rate is raised by `j`, every later renewal keeps the stated ladder, and
the drop lands in the renewal year (5). Central line; `examples/first_time_buyer_montreal.yaml`
with `condo.mortgage_renewal_years: 5` added, and P2.

| config | jump | drop | best, gap | condo affordability peak, years above 32% | break-even drop (year 5, permanent) |
|---|---|---|---|---|---|
| first-time buyer + 5-year term | 0 | none | condo by 6,526 (3.25%), `tie` | 36.21%, years 1–5 | 2.05% |
| | +1.30 pp | none | rent by 7,530 (3.64%), `tie` | 36.21%, years 1–9 | none: rent cheaper throughout |
| | +2.37 pp | none | rent by 19,253 (9.30%), `option` | 37.01%, years 1–10 | none: rent cheaper throughout |
| P2 | 0 | 20%, permanent | condo by 24,817 (5.93%), `option` | 36.21%, years 1–5 | 32.15% |
| | +2.37 pp | none | condo by 40,147 (9.95%), `option` | 37.01%, years 1–10 | |
| | +2.37 pp | 20%, permanent | rent by 689 (0.16%), `tie` | 37.01%, years 1–10 | 19.66% (25.35% at +1.30 pp) |

Neither leg alone moves P2's state; together they make it a tie. A drop alone never moves a
condo's affordability ratio (the condo's cost array has no value term).

### 1.6 Underwater years

On the first-time buyer the condo's value net of selling cost falls below the year-1 balance
($381,862 against $459,450 × 0.95) at any drop above 12.51% in year 1. The engine prices no
consequence of that: no forced sale, no refused renewal, no lender at all. A permanent drop in
year 1 leaves it underwater in years 1–2 at 20%, 1–5 at 30% and 1–8 at 40%; recovered over 7
years, in years 1–4 at 40%; a drop in year 9 of up to 40% leaves no underwater year. At the
10-year sale the equity turns negative only above a 46.16% drop. On P2 the loan is repaid at the
horizon.

### 1.7 History the engine may ship (Statistics Canada, Bank of Canada)

Only Statistics Canada (Open Government Licence) and Bank of Canada (its terms) series may enter
the engine or the skill. CREA's terms forbid publishing its data, the Dallas Fed series has no
licence text, and the JST macrohistory dataset is non-commercial and share-alike; this spec quotes
no figure from any of the three.

**New Housing Price Index** (18-10-0205-01, monthly, real = deflated by CPI v41690973). A
new-house, quality-held index: smoother than resale prices, so its falls are shallower and
slower than a resale index's would be.

| geography | nominal fall | peak → trough | years to trough | back to the peak, years after the trough |
|---|---|---|---|---|
| Toronto | −25.9% | 1989-12 → 1996-05 | 6.42 | 9.08 |
| Vancouver | −30.9% | 1981-03 → 1985-05 | 4.17 | 7.83 |
| Calgary | −22.9% | 1982-04 → 1984-08 | 2.33 | 4.17 |
| Edmonton | −23.8% | 1982-02 → 1985-03 | 3.08 | 4.58 |
| Ontario | −19.4% | 1990-03 → 1996-05 | 6.17 | 7.33 |
| Canada | −11.1% | 1990-03 → 1996-05 | 6.17 | 6.08 |
| Montréal | none of 10% or more | | | |

In real terms Montréal fell 15.0% (1988-05 → 1998-10) and regained its real peak 5.83 years after
the trough; Toronto fell 38.1% (1989-04 → 1996-11) and has not regained it; Canada fell 27.9% over
20 years (1981-05 → 2001-05) and regained it in 2021-11. Across the closed real episodes of 15% or
more, the trough-to-peak time runs from 1.83 years (Toronto, 1981) to 24.50 (Hamilton, 1989).
Most episodes start at the same national peaks, 1981 and the late 1980s, so they are a handful of
independent events, not twenty-four.

**What these mean against the panel's `d`.** The panel's drop is measured against the run's own
no-crash path (§5), so a historical fall compares with `d` only after the trend over the fall is
added back: `1 − (1 − fall) / (1 + g)^(years to trough)`. At the examples' 2.1% nominal trend,
Toronto's 25.9% is a 35.2% drop against trend, Vancouver's 36.6%, Calgary's 26.5%, Edmonton's
28.5%, Ontario's 29.1% and Canada's 11.1% a 21.8%. A one-year step of `d` is a peak-to-trough fall
of `1 − 1.021 × (1 − d)`: 8.11%, 18.32%, 28.53% and 38.74% for 10% to 40%.

**Permanent is not frozen in nominal terms.** At 0% real growth and 2.1% inflation a permanent
drop regains the pre-crash nominal price after 5.07, 10.74, 17.16 and 24.58 years for 10% to 40%,
and never regains the real one.

**Renewal jumps** (Bank of Canada Valet). Five-year change in the contracted uninsured 5-year
rate (V122667786): 1.96% in 2021-01 to 4.33% in 2026-01, +2.37 pp, the largest of its 103
five-year starts (about 1.7 independent windows); trough to peak 1.94% (2021-02) → 6.00%
(2023-11), +4.06 pp. The posted 5-year rate (V80691335): +1.30 pp over 2021-01 → 2026-01; its
largest five-year change since 1975 is +9.90 pp (1976-09 → 1981-09), over 561 starts (about 9.3
windows).

## 2. Rulings needed (directional)

Each one changes what a panel row MEANS. The recommendation is the seat's to accept or reverse;
everything after §2 is written to the recommendation and names what moves if it is reversed.

**R1. The verdict per row: conditional Monte Carlo, ordinary dispersion kept.** Each row runs the
config's own Monte Carlo with the stated drop on every path (common random numbers, no draw
taken), so its `state` is the verdict's own rule and comparable to the plain run's. Reversal
options: the central line only (the margin rule, as `--break-even` does, cheaper, and its state is
not the plain run's), or the Monte Carlo with the value dispersion silenced (a quiet market around
the crash). Measured stake: P2b's 20% row is `tie` with the dispersion kept and `option` without
it, at both seeds (§1.4). Cost: 0.37 s (10 years) to 0.77 s (25 years) per row at 5,000 paths.

**R2. A config with a `price_shock` hazard above 0 refuses the panel.** A row is "given this
crash"; random crashes on top make it "given this crash and maybe more", and, per the seat's shape
probe, the worked households' volatilities are full-sample sizes whose windows already contain
earlier falls. Reversal options:
silence the hazard inside the panel (draws still taken, so the streams hold), or stack it.

**R3. A stated drop moves the house's maintenance.** It is today's convention in the Monte Carlo
(maintenance is a rate on value), and the central line follows it. Measured stake: on the house
example a 40% drop recovered by year 8 makes the house $8,614 cheaper than no drop, and the
year-1 break-even is 38.85% against 29.83% in year 19 (§1.2, §1.3). Reversal: maintenance stays on
the no-crash path, which makes a permanent drop's figures independent of its year for both owned
options.

**R4. The engine ships no grid and no history.** Drops, years and recovery are typed on the
command line every time; the engine has no default and no anchor for any of them. The standard
grid and the shippable history (§1.7) live in the skill, which labels them the assistant's. Reversal:
an engine default grid, printed with its own tag.

**R5. The joint jump refuses beside a renewal-rate path file.** Shifting every row of a fitted
file is the `rate_shift` the path-file spec ruled out (its ruling 2). Reversal: shift every row by
`j` at the first renewal column.

**R6. The skill's standard recovery set: permanent, and full over 7 years.** History gives no
single figure: real trough-to-peak times on the shippable index run 1.83 to 24.50 years over a handful
of independent events, and the deepest falls (Toronto 1989, −38.1% real) are still open. Seven
years is the seat's probe anchor; on the shippable index it is near the fast end. Reversal: full
over 10 years, or three forms (permanent, full over 5, full over 15). The engine accepts any.

**R7. Licences for the public docs.** This spec quotes no CREA, Dallas Fed or JST figure; the
path-file spec §11 already quotes correlations derived from the Dallas Fed series. Ruling asked:
may derived figures from the Dallas Fed (citation required, no licence found) or CREA ("derived
results may be cited", publication of the data forbidden) appear in public docs at all, or only
in private ones.

## 3. The surface

### 3.1 The flag

```
--crash-panel 'drop=0.10,0.20,0.30,0.40;year=1,9;recovery=permanent,full:7[;jump=0.0237]'
```

- `drop`: one or more fractions in (0, 1), the value's fall against its no-crash path in the
  drop year. Sorted and de-duplicated, as `--sweep` does.
- `year`: one or more whole years in 1..`years`. `years` itself is the sale year.
- `recovery`: one or more of `permanent`, `full:K` and `share:R:K`. `share:R:K` returns the share R
  in (0, 1] of the log drop, in equal log steps over the K ≥ 1 years after the drop year;
  `full:K` is `share:1:K`; `permanent` is `share:0`.
- `jump` (optional): a decimal added to the rate of every financed option's FIRST PRICED renewal,
  on top of its stated ladder. It is added on the ladder's QUOTED axis (the option's own
  `mortgage_rate_compounding`, `mortgage_renewal_rates_quoted`) and converted once by the loader,
  as every typed rate is; both configs of §1.5 quote `effective_annual`, so there the two axes
  coincide. One market, so one jump for every option.
- Every field is required except `jump`; nothing defaults (R4). Rows are the full product of
  `drop × year × recovery`, at most 48 (§7, X9): 48 rows at 0.77 s is about 37 s of Monte Carlo.
- The panel runs on the base config. `--sweep`, `--break-even` and `--decompose` keep running on
  the base config beside it, and none re-solves anything at a panel row.

### 3.2 The text block (figures, not prose: which-risk §0.1 item 35)

```
crash panel — stated drops, each conditional on happening [drop, year, recovery: command line]
year 1 · permanent
  drop  sale value  condo     rent      rent − condo  best   P(best)  state   underwater
  10%   ×0.900      232,312   207,027   −25,284       rent   0.7192   option  none
  20%   ×0.800      264,122   207,027   −57,094       rent   0.9158   option  condo 1–2
  ...
  break-even: condo is cheaper below the bracket's low end; too close to call between the bracket's low end and 5.31%; rent is cheaper above 5.31% (crossing 2.05%) [solved, central case]
```

(The totals and underwater years are the first-time buyer's central line, the P column P1's at
seed 42.)

- `sale value` is `m(years)`, the sale value as a multiple of the no-crash path's. It is the figure
  that shows why a recovered drop leaves a condo's total unchanged.
- The gap is computed at the formatter as the difference of the two printed totals (which-risk
  §0.1 item 2). With three options it is runner-up − best, with both names.
- `P(best)` is the conditional run's `verdict.prob_best`; on a single-path run the column is headed
  `margin` and prints `verdict.margin_frac`, and `state` is the margin rule's.
- `underwater` lists each owned option's years where `value_t × (1 − selling_cost_rate)` is below
  the balance; `none` when there are none.
- One break-even line per (year, recovery), in `--break-even`'s band grammar, tagged
  `[solved, central case]`. With other than two options it prints the refusal code instead (X8).
- Every row of a config with an `income` block carries each option's peak affordability ratio and
  its years above the threshold (`sweep.affordability_of`, as `--sweep` rows do): a jump moves the
  financed options' ratios and, under R3, a drop moves the house's. With `jump`, the header names it
  (`jump +2.37 pp at each financed option's first priced renewal`).
- No closing line, no route advice, no explanation of a refusal beyond its one fact.

### 3.3 `--json`

A top-level `crash_panel` object, absent without the flag:

```
{"grid": {"drop": [...], "year": [...], "recovery": [{"form": "share", "share": 1.0, "years": 7}, ...],
          "jump": null},
 "source": "command line",
 "rows": [{"drop", "year", "recovery", "sale_multiple", "totals": {...}, "best", "runner_up",
           "margin_pv", "margin_frac", "prob_best", "mc_best", "state", "rule",
           "underwater_years": {"condo": [...]}, "affordability": {...} | null}],
 "break_evens": [{"year", "recovery", "key": "crash.drawdown", "options", "bracket": [0, 0.95],
                  "break_evens": [...], "cheaper_throughout"?: ...} | {"year", "recovery", "refused": {"code", "fact"}}],
 "refused": null | {"code", "fact"}}
```

Each field's meaning goes in one place: a new `docs/reference/API_CONTRACT.md` section, "The
`crash_panel` block". The skill reads it there and never restates it.

### 3.4 The read-back line

One line in `--read-back` and in `assumptions.read_back`, after the `renewals:` lines:

```
crash panel: drops 10%, 20%, 30%, 40%; years 1, 9; recovery permanent, full over 7 years; stated on the command line, not a forecast and not a probability
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
other row. The prototype's z-shift reproduces this exactly when `value_growth_vol > 0`; the build
applies the multiplier directly, so a run with no value dispersion takes it too.

**Timing.** For a condo a permanent drop gives the same totals in every year (§1.2): only
`m(years)` reaches its total. Timing matters when the value comes back (a late drop has less time
to) and for the house (maintenance, R3). The engine's drop is a one-year step; a slide over F years
whose trough falls before the sale prices exactly as a step at the trough year, because only the
sale value reaches a condo's total. Historical falls took 2.33 to 6.42 years to the trough
(§1.7); a slide still under way at the sale is priced as the smaller step it has reached.

**The demographic prior.** Its drift composes multiplicatively with `m(t)` in the Monte Carlo and
does not reach the central line, as today. Its `drawdown_weight_tilt` multiplies only a
`price_shock` hazard, which R2 refuses.

## 5. Real and nominal

`m(t)` multiplies the run's own value path whatever the mode, so the same stated drop is the same
fraction of the home in either mode. What differs is the path it multiplies: in nominal mode the
no-crash path includes inflation, so a permanent drop at 0% real growth regains the pre-crash
nominal price after 10.74 years at 20% (§1.7) while staying 20% below where the home would have
been; in real mode at 0% real growth it never regains the purchase price. That is why recovery is
defined against the path and not against the pre-crash price: a price-level definition would make
`permanent` mean "recovers with inflation" in nominal mode and "never" in real mode, and the same
household would get two answers to one question.

The `sale value` column is the multiple of the no-crash path. History compares with `d` only after
the trend over the fall is added back (§1.7). The skill carries that conversion (§9), never the
block.

## 6. Renewals, affordability, early exit

- **Renewal re-solve.** A drop never reaches a payment: the balance and each renewal's re-solve
  depend on the loan and the rates only (§1.1). The engine prices no loan-to-value test at renewal
  and no lender's response to an underwater borrower; the `underwater` column is the figure the
  reader needs to see where that gap bites.
- **The joint jump.** `quoted_ladder[0] += j`, then the loader's one conversion, on every financed option that states
  `mortgage_renewal_years` and a ladder, in each row and in the central case of that row, through
  `renewal_args_for` (no second ladder builder). The jump lands at the first renewal the horizon
  PRICES (`renewals_priced_inside` ≥ 1), or the panel refuses (X6). Affordability re-runs with the
  jumped ladder: on the first-time buyer +2.37 pp moves the peak from 36.21% to 37.01% and the
  years above 32% from 1–5 to 1–10 (§1.5).
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
| X1 `drop_out_of_range` | a drop ≤ 0 or ≥ 1 | `drop 1.0 is outside (0, 1)` | 0.99 |
| X2 `year_out_of_range` | a year < 1 or > `years` | `year 11 is past the 10-year horizon` | `years` |
| X3 `recovery_malformed` | R outside (0, 1], K < 1, an unknown form | `share 1.2 is outside (0, 1]` | `share:1:7` |
| X4 `hazard_wired` | any owned `price_shock.annual_hazard` > 0 (R2) | `condo.price_shock.annual_hazard is 0.03` | the same block at hazard 0, which the engine treats as unwired (`_world_draws`) |
| X5 `no_owned_option` | neither condo nor house priced | `no owned option is priced` | one owned option |
| X6 `jump_without_ladder` | `jump` and no financed option prices a renewal inside the horizon | `no financed option prices a renewal inside 4 years` | the same config with a renewal inside the horizon |
| X7 `jump_beside_path_file` | `jump` and a `renewal_rates.path` file (R5) | `renewal_rates.path is set` | the same flag without `jump` |
| X8 `not_two_options` | the break-even line only, with other than two priced options; the rows still print | `3 options are priced` | two options |
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
  of Canada figures (§1.7), with the series named, and labels any grid it chose `assistant`.
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
> `years − 1`; recovery `permanent` and `full:7`. Quote each row's figures and each break-even line
> verbatim, and read their meaning in `docs/reference/API_CONTRACT.md`, "The `crash_panel` block".
> Say the rows are conditional: "if the value drops 20% next year and never recovers, renting
> comes out $57,094 cheaper" — never "a 20% crash is likely" or "in a crash". The panel's drop is
> measured against the run's own no-crash path; when you compare it to a historical fall, add the
> trend back first (Toronto's new-house index fell 25.9% from 1989 to 1996, about a 35% drop
> against a 2.1% nominal trend), and cite only Statistics Canada's New Housing Price Index or the
> Bank of Canada, naming the series. Name, each with its direction, what a drop does not reach: no
> forced sale and no loan-to-value test at renewal (each favours buying); rent unchanged (favours
> buying, if market rents would fall too); fees and property taxes unchanged (favours renting, if a
> lower assessment would lower the bill); a house's maintenance falls with its value (favours the
> house). A recovered drop leaves a condo's total unchanged because the engine prices the home
> only at the sale: say that from the `sale value` column, not as reassurance. Use `jump` only for the joint question
> ("what if rates also jump at renewal"), with a figure you state as yours.

With both edits applied, `tests/test_skill_contract.py` gives 17 passed (measured, then
reverted). The flag is named only in references/, which that file's flag test does not read, so
the test passes before the flag exists; the builder re-runs it after commit 5.

## 10. Tests: each class pinned, each pin mutated both ways

| # | Class | Pin | Mutation that must fail it |
|---|---|---|---|
| 1 | Opt-out | Without the flag, the nine `tests/fixtures/opted_out/*.json` documents are byte-identical (no new golden). | Any default `drop_path` that is not None |
| 2 | One home | `drop_path` is the only function computing `m`; a grep pin finds no other `exp(-` on a log drop in `src/hde`. | A second copy in `deterministic.py` |
| 3 | Oracle | First-time buyer, permanent: the crossing equals 6,525.78 / 318,100.15 to 1e-9 relative. | Selling cost applied to the undropped value: the crossing moves to 0.019489 |
| 4 | Carried forward | A condo's permanent row is identical in years 1, 9 and 10. | The drop applied only in its own year (m back to 1): the totals equal the base |
| 5 | Back to the path, in log steps | `full:7` from year 1 leaves the condo's total equal to the base bit for bit (P2, $377,856); `share:0.5:5` from year 1 at 10% gives `m(10)` = 0.9487 and the first-time buyer's condo $216,825. | Recovery stepped in level instead of log (`m = 1 − d(1 − R·frac)`): `m(10)` = 0.95 |
| 6 | House maintenance (R3) | House example, year 1, `full:7`, 40%: house total $341,252 (< $349,866). | Maintenance left on the no-crash path: the total returns to $349,866 |
| 7 | No draw | The renter's PVs and each generator's end state are identical across every row and the plain run. | One `random()` taken per row |
| 8 | Conditional run | A path of all ones, built directly because X1 refuses a 0 drop, gives the plain run's `prob_best` exactly (P1 0.5450 at seed 42). | The panel runs on another seed or binding |
| 9 | Refusals both ways | Each of X1–X9 against its neighbour in §7. | Each refusal deleted, and each widened onto its neighbour (X4 widened to a hazard of 0; X2 widened to `years`) |
| 10 | Rendered output | Every line of the block matches one of the fixed templates; each gap equals the difference of its row's printed totals. | A closing sentence added; a gap read from `margin_pv` and rounded separately |
| 11 | Underwater | First-time buyer, year 1: a 12% drop has no underwater year 1, a 13% drop has. | Selling cost omitted: the boundary moves to 16.89% |
| 12 | Joint jump | First-time buyer + 5-year term, +2.37 pp: condo $226,281, years above 32% 1–10. | The jump on every renewal instead of the first |
| 13 | Read-back | The line appears once in `--read-back` and in `assumptions.read_back`, after `renewals:`. | The line printed without the flag |

## 11. Commit order

The suite is green at every commit, and row 1's goldens hold through commit 6.

1. `feat(crash_panel)`: `drop_path`, the grid parser, X1–X3 and X9, and their unit tests (rows 2,
   9 in part).
2. `feat(deterministic)`: the optional `drop_path` on both owned options and on
   `_annual_costs_for_option`; rows 3–6 and 11 on the central line.
3. `feat(monte_carlo)`: the multiplier after dispersion; rows 7 and 8.
4. `feat(crash_panel)`: the panel runner (rows, conditional runs, break-evens through
   `solve_crossings`, the joint jump through `renewal_args_for`), X4–X8; row 12.
5. `feat(cli)`: the flag, the text block, the `--json` block, the read-back line, the
   API_CONTRACT section; rows 10 and 13.
6. `docs(skill)`: §9's two edits to `references/gates.md`.

## 12. Out of scope

- A probability of a crash, or any change to `price_shock`.
- Momentum or a fitted shape for ordinary moves. The seat's shape probe found that, with the
  horizon spread held, momentum up to φ = 0.5 changed no worked household's decision; it found the
  `value_growth_vol` schema label ("ANNUAL") invites a one-year figure where the households sized a
  horizon-equivalent one. That label is its own fix.
- The Monte Carlo's affordability channel pricing the house's maintenance on the central path for
  every channel-1 draw (§6). It predates this panel.
- A forced sale, a loan-to-value test at renewal, mortgage-insurance requalification, and an
  early exit. Each is named as unpriced (§9).
- Rent, fees or property taxes responding to a drop.
- A `rate_shift` on a path file (R5).
- Composition with `--sweep` (a panel re-solved at every sweep point).

## 13. Measurements

The prototype is nine scripts, run with `uv run python` from a checkout where the engine at
3b7306a is installed and the worked households are available. `crash_probe.py` wraps
`deterministic._financing_pv` (multiplying `value_N` by `m(years)`) and
`deterministic._maintenance_rate_for_year` (multiplying by `m(year)`) for the central line, and
`monte_carlo._draw_path_world` (adding `Δz_t` to `z_value`) for the Monte Carlo; each wrapper is
restored in a `finally` and the restore is asserted.

| Figure | Command |
|---|---|
| §1.1 line numbers | `grep -n` and `sed -n` on `src/hde/monte_carlo.py` and `src/hde/deterministic.py` |
| central totals identical with and without `price_shock` | `misc.py` (a): `compute_deterministic` on `tests/fixtures/uncertainty_surface.yaml` and on a copy with both `price_shock` blocks and their `sources:` entries removed |
| §1.2 tables, §1.3 crossings and oracle | `run_det.py`: `det_result` per (drop, year, recovery) on the two examples and the households; `break_even.solve_crossings('crash.drawdown', options, 0.0, 0.95, totals_at)`; the oracle `gap / pv_single(value_N × (1 − selling_cost_rate), r, years)` |
| §1.4 table, CRN sha, baselines | `run_mc.py` then `tab_mc.py`: each household at seeds 42 and 4242, 5,000 paths, 24 rows plus the base |
| the dispersion row (R1) | `volcheck.py`: P1, P2, P2b at both seeds with `value_growth_vol` as configured and at 1e-6, drops 0 to 30% in year 1, permanent |
| per-row cost 0.37 s / 0.77 s | `misc.py` (b): one P1 and one P2 conditional run, timed |
| §1.5 table | `run_joint.py`: ladder `[r + j, r, r, r]`, drop in year 5; `det.income_report` for the ratios |
| §1.6 underwater figures | `misc.py` (c): `pv.outstanding_balance` at years 1 and `years` against the value net of selling cost; `underwater.py`: every year, per row |
| §1.7 NHPI table and real episodes | `history_sc.py`: monthly peak-to-trough on every NHPI geography with 120+ months, nominal and divided by CPI v41690973, falls of 10% or more |
| §1.7 trend conversions | `1 − (1 − fall) / 1.021^(years to trough)`; `1 − 1.021 × (1 − d)`; `ln(1 / (1 − d)) / ln(1.021)` |
| §1.7 renewal jumps | `history_sc.py`: Valet V122667786, V122667780 and V80691335 as calendar-month means, rate at t + 60 months minus at t |
| SKILL.md 2,597 words, budget below 2,600 | `python3 -c "print(len(open('.claude/skills/hde/SKILL.md').read().split()))"`; `tests/test_skill_contract.py` |
| nine opted-out goldens | `ls tests/fixtures/opted_out` |
| §9's edits: 17 passed | both edits applied to `references/gates.md`, `python -m pytest -q -p no:cacheprovider tests/test_skill_contract.py`, the file restored |
