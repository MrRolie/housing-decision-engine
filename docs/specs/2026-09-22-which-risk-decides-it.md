# Which risk decides it — design

**Status:** proposed, 2026-09-22. Design only, no engine code. Board item 4.

Every figure marked *(measured)* was taken from this tree at `c7bc3aa` on
`tests/fixtures/uncertainty_surface.yaml`, seed 42, at that fixture's own 2,000 paths unless
another count is named. Figures marked *(illustrative)* were not measured and are there to
show a shape. Nothing in this spec is quoted from the four design angles that preceded it
without being re-measured here; two of their headline numbers did not survive that, and §15
says which.

---

## 0. Rulings this spec is built under, and the seat's own verification

Three rulings were taken BEFORE this design and bind it. Two are the operator's.

**No cross-channel ranking; split the rows by EXACTNESS instead.** Ordering a renewal rate's
1.4 points against a rent's $310/mo needs a plausibility magnitude per input and the registry
has none. So no ordering. But the rows group by whether the engine computed a distance exactly
or estimated it — a fact about the MODEL, not a judgment about the world, so it costs no
honesty and the reader supplies the ordering from what he knows about his own life.

**A `--reversal` flag, not an always-on line.** Nothing changes for a run that does not ask, and
it stays out of the warnings channel that `2026-09-21-unpriced-dimensions.md` slice 2 owns.

**One solver, two consumers** (seat ruling, mechanism). The deterministic renewal-flip figure in
that slice and this module's central-case boundary are the SAME number. The solver lives here
and that line calls it. Named so neither builder can grow a second copy.

**The headline, re-measured by the seat rather than accepted.** The claim that decides this
spec's whole shape is that a variance decomposition names the WRONG channel. Verified
independently on `tests/fixtures/uncertainty_surface.yaml` at 2,000 paths, turning each channel
off the way the config actually allows — the lease-reset pair by DELETION, since the engine
refuses a zeroed hazard beside a stated market rent:

| | level shift in E[f] | P(rent cheapest) |
|---|---|---|
| baseline | — | 0.3350 |
| freeze the lease reset | **+127,876** | 0.5375 |
| freeze the renter's portfolio | −2,200 | 0.3310 |

The lease reset's level effect is 58x the portfolio's. The portfolio carries most of the spread
and relocates nothing; the reset carries little of the spread and moves the decision. Also
confirmed: `P(f > 0)` equals `verdict.prob_best` to the digit (0.3350 both), and D/sd = 0.109 —
the drawn channels scatter this decision nine times wider than the margin separating the two
options.

That is the argument for the three registers below, and it is why the obvious build is the
dangerous one.

## 0.1 Rulings on what the contract builder found, 2026-09-21

Typing the exchanged types found nine places where this document contradicts itself or prints a
figure with no field behind it. Every one is ruled here, in one place, so no builder has to
decide. Two were corrections to the document and are applied in §7 and §13 above; the rest are
below. The finding pattern is worth naming: **all nine came from writing the types, not from
reading the prose.** A field either exists or it does not, and that question cannot be answered
vaguely.

**1. The level register computes its own baseline, and the block says which sample it is.**
The register's freeze comparisons are PAIRED against `A`, so its baseline must be `f(A[:m])`
computed from `A`, never borrowed from `verdict`. And `verdict.prob_best` comes from the LEGACY
binding — one generator, the shipped stream — while `A` is spawn-keyed, so the two are different
samples of the same quantity and will differ by sampling noise. `futures_margin` and
`prob_best_base` therefore STAY, as the decomposition's own figures, labelled as such. This is
not a second home for one truth: it is two estimates from two named samples, and their
difference is information about the estimator. §2's bit-exact equality of `P(f > 0)` and
`verdict.prob_best` is a claim about the LEGACY binding only, and §2 is amended to say so.

**2. The gap figure is a subtraction, never a stored number.** §7's level closing printed a gap
that disagreed with the two figures printed beside it by $2,333. Render it as the difference of
those two, so they cannot disagree again. The same rule covers §7's `0.34` where the header
prints `0.3350`: one rounding, applied at the formatter, of one stored figure.

**3. The 10,000-path parenthetical is DROPPED.** §7 printed a ΣS at a second sample size. No
section licenses computing the decomposition twice, and at ~13x the shipped default that is
~26x. Track D removes the sentence. If the interaction question is worth a second sample later,
it arrives as its own ruled feature, not as a parenthetical.

**4. Four boundary kinds, not three.** §6's bullet list enumerates `best`, `mc_best`,
`decisive`; its own measured results carry `best` (1.6052%), `runner_up` (2.9549%) and
`mc_best` (2.7164%). `runner_up` was in the output and not the enumeration; `decisive` was in
the enumeration with nothing measured. All four are real questions, so `BOUNDARY_FIELDS` carries
four, and a kind the solver cannot reach on a given config REFUSES by name rather than being
silently absent — which is what `RefusedBoundary` is for.

**5. The structural zeros live inside the reversal register.** §7 renders a fourth section,
"NOT DRAWN IN THIS RUN", which the stated `spread`/`level`/`reversal` triple has no home for.
It goes in `reversal`, because §3.5's renewal row carries a number that comes from §6 and the
two render together. The contract builder chose this; it is now ruled rather than assumed.

**6. §4's provenance cell stands, and §7's draft is in breach of it.** The `economy` row must
list the `corr_inflation_*` keys AND the option vols they pull from, because which vols are
pulled depends on which rho is non-zero. Those cannot be static sizing keys; they arrive as
extra width entries from the track that reads the config. §7's draft lists only the corr keys
and is wrong. Track D fixes the draft.

**7. `P(f > 0) == 1` refuses the SPREAD register, and the level and reversal registers still
print.** With no sign variation the shares are undefined, so the spread register carries a
named refusal rather than empty rows. The binding in §5 runs one way — the spread may not print
without the level — so a refused spread beside a printed level is permitted and is the honest
shape.

**8. Two shelter-freeze figures, two methods, both real.** +$127,876 (§0, §5, §13) and
+$125,074 (§1, §3.4, §7) are not a disagreement to resolve by picking one. The first is the
seat's probe, which DELETED the lease-reset pair from the config — the only way this engine
allows the channel off, since it refuses a zeroed hazard beside a stated market rent — and so
also removes the market-escalation default. The second is the freeze mask, which suppresses the
draw and leaves the config alone. **The freeze-mask figure is what the register prints**, because
that is what the register does; the deletion probe is a config counterfactual and is labelled as
one wherever it appears. Same for the share: 0.10 is the measurement, and §1's "7.7%" and §7's
"8%" are roundings of it that should not have been typed as separate figures.

**9. Both of the contract builder's deviations are accepted.** The `TYPE_CHECKING` import of
`models.Verdict` is an import statement with zero runtime coupling, and the alternative — copying
the verdict's scalars — is a second home for the verdict's truth. `bracket_source` on both
reversal types is required by the correction at the end of §6: a bracket that converts an honest
refusal into an answer must show the reader the range it chose and whose figure it is.

**10. The flip column carries its interval, and §7's draft loses.** §3.3 says 95% intervals on
EVERY figure; §7's draft prints none on the flip column. `SpreadRow.flip_ci` is added. The
reason this column in particular may not be printed bare is the reason it exists: it is the one
figure in the table stated in decision space, so a reader takes it as the answer to "how often
does this change my mind" — and a point estimate with no width, standing where every
neighbouring figure carries one, reads as the most certain number in the table when it is not.

**11. A row is unresolved if EITHER of its two figures is unresolved.** The rule was unstated
and the assembly was about to have to invent it. Conservative is correct here for the same
reason the register refuses at all: the alternative prints one resolved figure beside one that
is noise and leaves the reader to notice. It also matches §7's own house row.

**12. §4's ΣS rule is kept and §4's own claim about it is deleted.** §4 says the residual prints
only when the interval lies entirely below 1, and then claims both branches are reachable on
this fixture, with T5 asserting the 10,000-path case takes the numeric branch. Measured by the
track that built the estimator: §4's own 10,000-path figure is 1.023 [0.969, 1.091], which
includes 1 and therefore REFUSES. So the residual refuses at both committed path counts and the
"both branches reachable on one fixture" sentence is false. The RULE stands — it is the refusal
this whole feature is built to be capable of, and a rule that bends to make its own example
work is not a rule. The sentence and T5 go. §0.1 item 3 already dropped the 10,000-path
parenthetical from the output; this removes the last thing that depended on it.

**13. The estimator is centred, which is a change to the mechanism and is taken on measured
grounds.** Saltelli 2010 is confirmed the right choice — the alternative (Janon/Monod 2014) is
~10x more accurate on a dominant channel but 2x worse on small ones and, decisively, gives ΣS
three times the spread because each channel gets its own denominator, so the quantity §4
branches on stops being a coherent sum. But the estimator as published is NOT invariant to its
target's own mean: the numerator carries an `E[f]·mean(f_AB − f_A)` term, zero in expectation
and noisy in sample, and the error grows with `|E f| / sd(f)` — about 1% at this fixture's
measured 0.23, 1.17x at 1σ, **2.1x at 3σ**. That last case is a DECISIVE run, which is exactly
when a reader is told the answer is settled. Centring the numerator's `f(B)` by its sample mean
removes the term, is identical in expectation, and costs one subtraction. Taken.

**14. Four silent resolutions, now named, one of them load-bearing.**
`SeedSequence(seed, <salt>)` as §3.3 writes it is a `TypeError` — `spawn_key` is keyword-only —
and is read as `spawn_key=(salt,)`, matching §3.2's idiom. `Var(f(A))` is the population
variance (ddof=0), matching the 1/N numerators. `np.sign(0) == 0`, so a future sitting exactly
at zero counts as flipped against any nonzero. And the load-bearing one: **the denominator is
`Var(f(A))` alone, never the pooled A∪B variance** some implementations use — pooling tightens
ΣS and could make §4's refusal branch unreachable, which would silently delete the refusal
rather than change a decimal.

**15. The published interval bounds will not reproduce, and that is not a bug.** Point estimates
never touch the bootstrap; bounds depend on the salt and the resample count. Measured: point
estimates bit-identical across salts while the dominant share's bounds move 0.707→0.717 and
0.867→0.881, and the sum's high bound 1.147→1.174; the resample count moves them too.
**Nobody tunes the salt to match a figure in this document.** Every interval printed in §7 is
re-taken once the streams land, and §10's assertions stay inequalities with margin rather than
equalities to a bound.

---

## 1. Why

The engine already says, on every run, that its verdict rests on uncertainty inputs the user
never stated. It names all seventeen of them on the fixture, flat and unranked. It cannot say
which one matters. A household reading that list has no way to know which number to go check,
and the answer it is checking is a three-state verdict whose middle state — a named
disagreement between the central case and the futures — is currently produced by a mechanism
the engine cannot describe.

**The wrong outcome, stated as what a reader concludes today.** On the fixture the engine
prints: *best guess says rent by $31,349; most futures say condo (57% cheapest) — the two
disagree, not decisive.* A reader concludes the disagreement is noise, or that it is "the
market". Both are false, and the engine can now prove it: freezing the **lease-reset channel
alone** — pricing the tenancy the way the central case prices it — moves the expected decision
margin by **+$125,074** *(measured, ±$1,775)* and takes P(rent cheapest) from **0.341 to
0.5355** *(measured)*. The disagreement is one channel, and that channel is `rent.reset_hazard`,
an input whose own config comment records that nobody possesses the number.

**The second wrong outcome, and the one that makes this feature dangerous if built naively.**
The obvious build — decompose the variance — would answer the question with *"the renter's
portfolio, 78% of the spread"* *(measured, 10,000 paths, 95% CI [0.731, 0.835])*. That is a
true statement about spread and a false answer to the board's question. The same measurement
says the portfolio moves the expected margin by **−$3,805 ± $5,383** *(measured)* — a level
effect indistinguishable from zero — while the lease reset, at **7.7%** of the spread, is the
channel that relocated the answer. **A variance decomposition alone names the wrong channel on
this repo's own flagship fixture.** That is the expensive failure the board item warns about,
committed by the first design anyone would write.

**The third wrong outcome: the channel the board says is the contribution has no variance at
all.** `house.mortgage_renewal_rates` is a path the user states, not a distribution. Measured:
moving it from a flat 2% to a flat 9% changes the house's PV by **$191,237**, changes which
option is the deterministic runner-up, and takes P(house cheapest) from **0.459 to 0.002** —
while the standard deviation of the house's PV stays **$118,379.6 at every one of those rates,
identical to the digit**, and the condo's and the renter's paths move by **exactly 0.0**
*(measured)*. A variance table prints that channel as a dash. A reader sees six rows with
numbers and one row with dashes and concludes renewal was weighed and found irrelevant. The
truth is the opposite: measured on this fixture, the verdict's own winner flips from rent to
house at a flat renewal rate of **1.6052%** *(measured, solved)* — inside the bracket the
engine already uses for a mortgage rate.

So the feature cannot be a variance decomposition. It has to answer three questions that are
different objects, and it has to print all three or it teaches the reader something false:

| question | the object | who owns it here |
|---|---|---|
| where does the decision's **spread** come from? | grouped Sobol indices on the decision margin | §3 spread register |
| what do the futures **price that the central case does not**? | the freeze mask's level shift | §3 level register |
| what would have to **change** for the verdict to change? | a solved boundary on a stated input | §6 reversal register |

**What this is not.** Not a study; a shipped surface with a flag, a JSON block and a test
plan. Not a second verdict: every probability and every state in this block comes back from
`models.compute_verdict`, never from arithmetic in the new module. Not a replacement for
`--sweep` or `--break-even`, which own the user-driven versions of §6 and are the route this
block prints when it refuses.

---

## 2. The one quantity everything is decomposed on

**`f`, the decision margin, priced on every path:**

```
f(ω) = min over the other priced options of PV_o(ω)  −  PV_best(ω)
```

where `best` is `verdict.best`, the deterministic winner. Three properties, all verified, and
they are why this is the target rather than a pairwise gap or a probability:

1. **Its deterministic value is the verdict's own margin.** With every channel frozen, `f`
   equals `verdict.margin_pv` on every path: measured at 31348.656075 on all 500 paths of a
   probe run, max deviation **5.8e-11** *(measured)*.
2. **Its sign is the decisiveness statistic.** `P(f > 0)` = 0.3350 = `prob_rent_cheapest` =
   `verdict.prob_best`, exactly *(measured)*.
3. **Every priced option is inside it.** The `min` keeps the third option in the target. The
   pairwise `PV[best] − PV[runner_up]` drops it: on this fixture the house is cheapest on 9.45%
   of futures, and a pairwise target would delete the house's channels from the table with no
   row saying so.

Measured on the shipped run: `E[f] = −$67,194`, `sd(f) = $286,506`, against a central-case
margin of `+$31,349`. **D/σ = 0.109** — the drawn channels scatter this decision nine times
wider than the margin that separates the two options. That ratio leads the block, because a
share of a spread means nothing until the reader knows how wide the spread is against the
answer.

One consequence to state plainly, because it is the fixture's whole story: `E[f]` is negative
while the central case is positive. The futures and the central case are on opposite sides,
which is what `state == "disagreement"` means, and the **level register** is the instrument
that says which channel put them there.

---

## 3. The mechanism

### 3.1 The channel partition — over primitive draws, not over config keys

The Sobol inputs are the **draw sites**, grouped. This is the one non-negotiable structural
decision and it is what makes the independence assumption true rather than assumed: the engine
builds every correlation by composing independent primitives (`_correlated_z` returns
`rho*z_inf + sqrt(1-rho²)*eps`, `monte_carlo.py:326`), so the primitives are independent even
where the resulting shocks are not. Grouping over config keys would import the dependence back.

Seven channels, a fixed table in the source with fixed integer ids, never derived from set
iteration order (the defect `_world_draws` already sorts `drift_bands` to avoid):

| id | channel | draw sites | sized by |
|---|---|---|---|
| 0 | `economy` | `_draw_inflation_factor`'s z per year | `economic.inflation_vol`, and the `corr_inflation_*` keys that decide what reads it |
| 1 | `market` | `crash_uniforms`, `crash_zs`, `z_value` in `_draw_path_world` | `<opt>.price_shock.*`, `simulation.value_growth_vol` |
| 2 | `population` | the scenario index and the band z's | `market_scenario` |
| 3 | `condo` | its fee eps, its other-cost eps, its event years and event-cost eps | `simulation.condo_fee_vol`, `other_cost_vol`, `condo.events` |
| 4 | `house` | its maintenance eps, other-cost eps, event years and event-cost eps | `house_maintenance_vol`, `other_cost_vol`, `house.events` |
| 5 | `shelter` | the escalation z, the renter's event years and cost eps, its other-cost eps, **and `reset_year`** | `rent_escalation_vol`, `other_cost_vol`, `rent.events`, `rent.reset_hazard` |
| 6 | `portfolio` | the per-year `z_inv` | `simulation.investment_return_vol` |

**The renter split is not deferrable.** Measured, lumping the renter into one channel gives
`renter 0.809` — a row that names nothing a household can act on. Split, it gives
`portfolio 0.877 / shelter 0.100` at 2,000 paths, and the level register then separates them
completely: the portfolio's level effect is **−$3,805 ± 5,383** and the shelter's is
**+$125,074 ± 1,775** *(both measured)*. One is pure risk, one is an omitted cost. A slice that
ships them lumped ships a table not worth printing.

`_simulate_rent_pv_once` has five draw sites; exactly one of them (`z_inv`,
`monte_carlo.py:946`) moves to `portfolio`. That is the only place a simulator's internals are
threaded, and a working split was built and measured for this spec.

**Income is not a channel.** `_compute_income_affordability_once` returns booleans; its draws
reach no PV. It is a structural zero (§3.5), not a measured zero.

### 3.2 The streams seam, and the binding that verifies it

`run_monte_carlo(spec, streams=None)`. `streams` maps each channel id to a generator, and every
draw site reads its own channel's generator instead of the single `rng`.

**There is exactly one draw path.** `streams=None` builds a binding in which **every channel
maps to the same generator object**, `np.random.default_rng(sim.random_seed)`. The execution
order of the draw sites is unchanged, so the consumed stream is byte-identical to today's, and
`tests/fixtures/uncertainty_surface_mc_golden.json` proves it. This replaces the statistical
"reconciliation gate" an earlier angle proposed: a variance comparison between two independent
samples has no power — measured, the fixture's `Var(f)` carries about 7% seed-to-seed relative
noise, while dropping a whole channel's shock moves it by ~3% — so that gate would refuse
correct runs and pass real bugs. **A gate that cannot fail is not a gate.** The golden can fail,
and it fails on any reordering of any draw.

For the decomposition the binding is addressed, never positionally spawned:

```
np.random.default_rng(np.random.SeedSequence(entropy=sim.random_seed,
                                             spawn_key=(matrix_id, channel_id, path_index)))
```

Per-path keying (rather than one long stream per channel) is required, not preferred: the
draw COUNT of `_sample_event_year_hazard` (`:477`) and `_sample_reset_year` (`:499`) depends on
the outcome, because both return early inside their year loop. Sequential per-channel streams
would silently desynchronise the moment a channel's count varied, and the answer would be wrong
with no symptom. Per-path keys also make the table non-perturbing: adding an eighth channel
cannot move channels 0–6, and a config with a different `k_live` gets the same draws for the
channels it shares.

### 3.3 The spread register — grouped Sobol by pick-freeze

`A` and `B` are two independent draws of the full channel set. `A_B^(c)` is `A` with channel
`c`'s streams taken from `B` — so `f(A)` and `f(A_B^(c))` differ **only** in channel `c`.

```
S_c   (Saltelli 2010) = mean( f(B) · (f(A_B^(c)) − f(A)) ) / Var(f(A))
S_Tc  (Jansen 1999)   = mean( (f(A) − f(A_B^(c)))² ) / (2 · Var(f(A)))
flip_c                = mean( sign(f(A)) ≠ sign(f(A_B^(c))) )
```

95% intervals on every figure and on `ΣS_c` from a 300-resample bootstrap over **path indices**
(vectorised, sub-second, no extra model evaluation). The bootstrap generator is
`SeedSequence(sim.random_seed, <fixed salt>)` — never the run's stream, so it consumes nothing
and reproduces across processes.

`flip_c` is decoded in the output and is never optional: it is the only column that speaks in
decision space, and on the fixture it is measured at **0.406 for the portfolio against a share
of 0.877** — the two numbers a reader will otherwise conflate, printed side by side.

### 3.4 The level register — the freeze mask

For each channel `c`, re-price every path with `c` **frozen at the value
`compute_deterministic` uses**, every other channel reading its own unchanged `A` stream. The
difference is paired, so its standard error is small: measured SEs on the fixture run $179 to
$5,383 against level effects up to $125,074.

Per-channel freeze rules, each naming the deterministic treatment it must reproduce:

| channel | frozen means |
|---|---|
| `economy` | `inflation_vol = 0`: `_draw_inflation_factor` returns the base factor and `z = 0`, and `PathWorld.inflation_is_stochastic` goes False, which is exactly what `world.corr` already does at zero vol |
| `market` | no crash draw and `value_growth_vol = 0` — the multiplier is 1.0, **not** `exp(−vol²/2)`; `_apply_price_shock` is not reached |
| `population` | no band drift and `drawdown_weight_tilt = 1.0`; `compute_deterministic` reads the prior only for its provenance block (`deterministic.py:760-766`) |
| `condo` / `house` | its own vol at 0, its other-cost vol at 0, and every event at `_event_year_deterministic` — **the clamped expected year, not `expected_year`**, so a config setting `min_year`/`max_year` still reproduces the central case — with `base_cost` |
| `shelter` | the renter's vols at 0, its events deterministic, and `reset_year = None` |
| `portfolio` | `investment_return_vol = 0`, so the capital leg compounds the world's own rates exactly as the deterministic engine does |

**The identity that makes this a fact rather than a claim:** with *every* channel frozen, `f`
equals `verdict.margin_pv` on every path, bit for bit. Measured: 31348.656075 on every path,
max deviation 5.8e-11. A mask that misses a draw site fails it; a mask that reaches a site
belonging to another channel fails it. This is the sharpest test in the plan and it costs one
run of `m` paths.

The level register prints only rows whose `|Δ| > 2·SE`. The rest are named as *indistinguishable
from zero at this sample size* — which is the honest reading of the portfolio's
`−$3,805 ± 5,383`, and is a row a reader must see rather than an absence.

**What the level register is, said exactly, because it is easy to misread:** it is not "what if
this input were different". It is *what the simulated futures price that the central case does
not*. A channel with a large level effect is a cost the deterministic line omits, and the block
says so in those words.

### 3.5 Structural zeros — three kinds, all resolved from the spec, none costing an evaluation

1. **The renewal ladder.** `mortgage_renewal_rates` feeds `renewal_args_for` into the
   deterministic `_financing_pv`, which runs identically on every path (`monte_carlo.py:686-694`,
   `785-790`). No draw exists, so the variance is 0 **by construction, not by measurement**. Its
   row carries a number from §6, never a dash.
2. **The income channel.** `income.pay_drop_events` reaches only
   `_compute_income_affordability_once`, which returns booleans. It cannot move either PV.
3. **A drawn channel that reaches nothing — the real-mode inflation trap.** In REAL mode
   `_effective_growth_rate` discards the inflation factor by construction, so `z_inflation`
   reaches a cash flow only through a non-zero `corr_inflation_*`. With every correlation at
   zero the channel draws every year and moves nothing. Measured on `advanced_config.yaml`
   forced to real mode with the correlations zeroed: `sd(condo PV) = 37,594.47` and
   `P(condo cheapest) = 0.3463`, **identical at `inflation_vol` 0.001, 0.010 and 0.300**. The
   engine detects this from the spec (`econ.mode == "real"` and every `corr_inflation_*` at 0),
   spends **no** evaluations on it, and prints it as a named zero with the reason. A measured
   `0.00` in that row would read as "inflation does not matter", which is not what is true.

### 3.6 Liveness

A channel is live when at least one of its draw sites consumes a draw, computed from the spec
the way `_world_draws` already computes the world's. `k_live` measured over every shipped
config:

| config | `k_live` | `num_sims` | live channels |
|---|---|---|---|
| `first_time_buyer_montreal.yaml` | 0 | 5,000 | — (`single_path_run` is True) |
| `income_shock.yaml` | 1 | 5,000 | condo |
| `basic_config.yaml` | 2 | 10,000 | condo, house |
| `mortgage_house_vs_rent.yaml` | 2 | 5,000 | house, shelter |
| `rent_vs_condo_vs_house.yaml` | 2 | 5,000 | condo, house |
| `advanced_config.yaml` | 3 | 15,000 | economy, condo, house |
| `showcase_demographic_prior.yaml` | 5 | 5,000 | market, population, condo, house, portfolio |
| `uncertainty_surface.yaml` | 7 | 2,000 | all seven |

*(measured)*. Five of seven shipped examples are at `k_live ≥ 2`, so the feature engages on
them; the cost section is written against that fact and not against a hope that most configs
are trivial.

---

## 4. Interaction

**The premise the panel was convened on needs one correction, and the design rests on it.** The
one-world fix did not make the channels dependent. It made the **options** share draws. Measured
on the fixture: `corr(condo, house) = 0.9176`, and `corr(condo, rent) = −0.0085`,
`corr(house, rent) = −0.0177`. Those are correlations between **outputs** that read the same
crash uniform and the same value z. The crash uniform and the value z remain independent draws.
Sobol's independence assumption is on the **inputs**, and with the partition defined over draw
sites it holds exactly.

The `corr_inflation_*` keys look like a counterexample and are not: `_correlated_z` composes two
independent primitives and the model reads both. The consequence is honest and belongs in the
provenance cell: at `rho = 0.5`, **rho² = 0.25** — a quarter, not a half — of that shock's
variance is attributed to `economy`, because knowing the inflation path really would tell you a
quarter of it. The `economy` row's provenance cell therefore lists the `corr_inflation_*` keys
**and** the option vols they pull from, or the cell is itself a wrong answer.

**What does not vanish is model non-linearity**, and that is what the design reports rather than
disclaims. `S_Tc − S_c` per channel and `1 − ΣS_c` in total are the measurement of it.

**Why the naive method is refused, measured rather than argued.** Leave-one-out on `Var(f)` —
turn each channel off, see how much the variance drops — run on the fixture over ten
config-level channels produced:

- shares summing to **0.9493**, not 1;
- **four negative shares** (value dispersion −0.0026, the population prior −0.0077,
  `other_cost_vol` −0.0085, rent escalation −0.0039), which are unpaired-sample noise, not
  findings;
- and the pathology that kills it: the lease reset reads **9.75% of the variance** while moving
  `E[f]` by **+$127,876** — switching off the single largest mover of the answer looks like a
  10% channel.

*(all measured)*. Pick-freeze **re-draws** rather than removes, so the mean is preserved and the
first two failures cannot occur; and the level register answers the third question directly
instead of letting it contaminate the first.

**What the output says about interaction, computed, and able to come out either way.** The rule:

- when the bootstrap CI of `ΣS_c` lies entirely **below 1**, the residual prints as
  `1 − ΣS_c` with its interval, and is named as movement no single channel owns;
- when that CI **includes or exceeds 1**, no residual number prints. The line reads: *the
  first-order shares add to 1.16 [1.04, 1.31] — above the whole, which is estimator noise and
  not a finding. Interaction is not measurable at this sample size; raise
  `simulation.num_sims`.*

Both branches are reachable on this one fixture: at its committed 2,000 paths `ΣS_c = 1.164
[1.042, 1.310]`, and at the shipped default 10,000 it tightens to `1.023 [0.969, 1.091]`
*(both measured)*. **No share is ever clamped into [0, 1].** The house's measured
`S = −0.001 [−0.002, 0.001]` prints as `not resolved at 2,000 futures`, never as `0.00`. A
clamped number is the cheap all-clear in this feature's costume.

---

## 5. The unanchored problem

Most of the widths this block ranks are figures the assistant typed. On the fixture,
`unstated_uncertainty` returns **seventeen** entries and **not one** volatility is user-stated.
A ranking of those widths is a ranking of somebody's guesses. Four mechanisms, all in the
engine, all computed from `spec.sources` through the existing `unstated_uncertainty`
(`sources.py:751`) — no second classifier:

**1. Every row carries its widths and their source class, in the table.** Not a footnote. A
reader cannot see the ranking without seeing whose numbers produced it.

**2. Channels the engine deliberately ships at zero print as named zero rows with the key that
turns them on.** Specifically `simulation.value_growth_vol` and `rent.reset_hazard` — the two
keys the one-world spec shipped unanchored on purpose. Silence about a channel that is off would
let a reader conclude that prices, or a lease ending, had been weighed and found not to matter.

**3. The superlative is gated on provenance.** When the leading channel's widths are all user-
stated or anchored, the block may write *"X decides the spread of this answer"*. When any of
them is assistant-typed, it may not; it writes the share and then: *this ranking is a property
of widths you did not state — the figure to check first is `<key> = <value>`.* Change one
`sources:` entry from `assistant` to `user` and the sentence changes. That is the test.

**4. One computed provenance figure, able to be absent, and bound to the residual's own branch.**
The first-order shares of the channels whose widths are entirely assistant-typed, summed and
named as a sum of first-order shares — never as a joint share. **It prints only when `ΣS_c` took
the numeric branch of §4.** When `ΣS_c` took the refusal branch, the same number is noise, and a
block that refuses to print it as a residual and then prints it as a provenance finding is
telling the reader two different things about one figure. On the fixture at its committed 2,000
paths the refusal branch is taken, so the line reads only: *every channel above is sized by a
figure the assistant chose, not by you.* At 10,000 paths, where `ΣS_c` resolves, it carries the
sum. On a config where every width is the user's or an anchor's, the clause does not print at
all.

**5. The level register is BOUND to the spread table, structurally** *(operator ruling
2026-09-22, superseding this section's earlier "label" default)*. The fork this section left
open was: label the ranking, or refuse to rank when the top width is assistant-chosen. The
answer was neither. The ranking prints — a refusal would delete the only thing this feature can
say on nearly every config shipped today, and the index is solved from the user's own config
the way `break_even.RATE_BRACKETS` already is. But the spread table may not be emitted without
the level register beside it, and this is a property of the CODE, not a convention a formatter
is trusted to honour: one function emits both registers or neither, and a caller cannot reach
the spread rows alone. Mechanisms 1–4 above all stand and are all still required.

The reason is measured, in §0: the spread table's top row on this repo's own fixture is the
renter's portfolio at 0.88 of the scatter, and freezing it moves the decision by −$2,200, while
the tenancy at 0.10 of the scatter moves it by +$127,876 — 58x. The countervailing view was not
weak, and it is exactly what the binding answers: on the fixture *"your portfolio, 0.88"* is
entirely a consequence of an assistant typing `0.10` into `investment_return_vol`, and a
labelled finding is still a finding a reader will quote. A label can be lost in a copy-paste.
The row that corrects it cannot be, if the code will not emit one without the other.

**And the honest limit, recorded rather than argued away:** §6's register is the part of this
feature that does not have this problem at all, because a stated input's reversal distance is
solved from the user's own numbers with no width in it anywhere. That is a reason to build §6
in slice 1, not a reason to think §5 is solved.

---

## 6. The reversal register — the half that Sobol cannot touch

The board item has two clauses and the second one is *"state the conditions under which the
verdict reverses"*. No decomposition of drawn channels can answer it for an input that is not
drawn, which is exactly the input the board calls the contribution.

**Candidates.** Inputs the config **states** that carry no distribution in this run and move at
least one option's deterministic PV. A sizing key of a drawn channel (`*_vol`, a hazard, a
correlation) is **never** a candidate — it appears as a width in §3's provenance cell. That rule
closes a hole by construction: `compute_deterministic` reads no dispersion input, so a
deterministic curve over a vol key is a flat line, and a flat line under this heading would
print *"this risk does not affect the verdict"* about every risk. Slice 1's candidate set is the
financing-leg keys of each financed owned option: `<opt>.mortgage_renewal_rates` and
`<opt>.mortgage_rate`.

**The admission test is a measurement, not a list.** One `load_at` + `compute_deterministic` at
the far end of the key's bracket — 1.2 ms *(measured)* — and the key is admitted only if some
option's deterministic PV moves. A key that moves nothing is not printed as a flat curve; it is
not a candidate. That is what excludes `mortgage_renewal_rates` on an all-cash option, and it is
the same screen that would exclude a vol key even if the candidate rule above ever loosened.

**The exactness gate, and why the curve is free.** For a candidate `x` and a probe value `x₁`
at the far end of its bracket, re-run `m = min(200, num_sims)` paths through `sweep.load_at` and
require **both**:

- **(a)** every option the key does not name is **bit-identical** — catching any key that
  changes the draw stream;
- **(b)** the option it names moves by **one constant on every path**:
  `max_i |Δ_i − mean(Δ)| ≤ 1e-9 · sd(PV)`.

This is an **exactness test, not a tolerance**. Measured separation on the fixture:

| key | worst per-path deviation / sd | gate | free curve vs a true re-simulation |
|---|---|---|---|
| `house.mortgage_renewal_rates` | **2.0e-15** | licensed | probabilities identical: 0.6215 / 0.0395 / 0.3390 both ways |
| `house.mortgage_rate` | **2.0e-15** | licensed | identical: 0.6110 / 0.0510 / 0.3380 both ways |
| `rent.monthly_rent` | 1.8e-01 | refused | would have been 2.5 points wrong |
| `house.value_growth_rate` | 1.8e+00 | refused | would have been 4.8 points wrong |

*(all measured)*. Fourteen orders of magnitude separate the licensed from the refused, so
nothing here rests on a tuned threshold. The mechanism behind the licence is structural and
readable: `_financing_pv` is one terminal call and `equity_N = value_N·(1−s) − balance_N` has no
clamp, so `balance_N` separates additively from the path-dependent value.

**What is solved.** At each candidate value, the licensed curve shifts each option's PV array by
its deterministic delta, rebuilds the summary with `_summarize_array` (so `mc_mean_best` is not
stale), and hands the result to **`models.compute_verdict`** — the engine's own rule. The
boundaries reported are the nearest values at which the verdict object changes:

- `best` changes (the central case's winner),
- `mc_best` changes (the option most futures call cheapest),
- `decisive` changes.

Deterministic crossings are solved through **`break_even.solve_crossings`**, called directly on
the relevant pair — `--break-even` itself refuses a three-option config (*"needs exactly two
priced options"*, verified), but its solver takes a pair and a `totals_at` callable and is the
one home for this truth. `sweep.flattened_path_note` prints on any key the config states as a
path, so the row never claims the user stated a flat rate they did not.

**Two refusals with real failure states.** (i) A `mc_best` boundary whose bracket-wide `|ΔP|` is
under `2·SE`, `SE = sqrt(p(1−p)/N)`, is not printed — it is not identified inside Monte Carlo
noise. On the fixture `SE ≈ 0.0105` at 2,000 paths and `P(condo)` runs 0.245 → 0.657 across
1%–10%, so the boundary is resolved by a wide margin. (ii) Every printed boundary is
**confirmed by one full re-simulation at the solved value**, and the row refuses if the
confirmed probabilities differ from the free curve's. Measured at the solved boundary:
free 0.1915 / 0.5185 / 0.2900, re-simulated 0.1915 / 0.5185 / 0.2900 — identical.

**What this produces on the fixture** *(all measured, solved)*:

- the verdict's own winner flips from rent to the house at a flat renewal rate of **1.6052%**;
- the runner-up swaps from condo to house at **2.9549%**;
- the majority swaps from condo to house at **2.7164%**;
- and `RATE_BRACKETS` needs a `mortgage_renewal_rates` entry — it has none today.

**CORRECTED 2026-09-21, by the builder, against the code.** The clause above originally read
"so the bracket a sweep of it uses is borrowed silently from `mortgage_rate`". That is false.
`RATE_BRACKETS` is keyed by the LEAF, so `mortgage_renewal_rates` gets no bracket at all and
`solve_break_even` REFUSES with a named reason (`break_even.py:401`) — the engine was already
honest here and the spec accused it of a silent borrow it does not perform. The entry is still
needed, but it converts an honest refusal into an answer, which is a higher bar than replacing
a silent default: the bracket's width is assistant-chosen, so it must be PRINTED, as
`break_even.py:67` already requires of every bracket.

And the refusal branch that sentence pointed at carries a defect of its own, found the same
way. It is category-general — twelve rate-shaped leaves still reach it — and its message is
instance-specific: it tells the user *"the engine forecasts no renewal path and defaults
none"* whatever key they asked about, so `--break-even economic.inflation_rate` is answered
with a sentence about renewal. A fix written for renewal leaked its instance's prose into the
shared branch, and adding this entry makes it strictly wrong for all twelve, because the one
key the sentence was about is the one key leaving the branch. Track C owns the repair.

---

## 7. The output

A block under the verdict, printed only on `--decompose`, and mirrored in `--json` as
`decomposition` with sub-blocks `spread`, `level`, `reversal`. Drafted on
`tests/fixtures/uncertainty_surface.yaml` at its own 2,000 paths. Every number below is
*(measured)* except the two marked.

```
which risk decides it — 2,000 futures, seven channels live

  best guess says rent by $31,349 (7.8% of rent PV); most futures say condo (57% cheapest) —
  the two disagree, not decisive [hde verdict rule]. Across the futures that $31,349 margin
  averages −$67,194 and scatters by $286,506 (1 s.d.) — 9.1x the margin itself. What follows
  splits that scatter, and then says what the futures price that the central case does not.

  THE SPREAD — where the $286,506 comes from
  channel              alone   with interaction   flips the sign   width comes from
  the renter's
    portfolio          0.88     0.84               41%             simulation.investment_return_vol=10%
                       [0.78,1.00]                                   [assistant]
  the housing market   0.14     0.13               13%             simulation.value_growth_vol=7%,
                       [0.11,0.17]                                   condo/house price_shock.annual_hazard=3%
                                                                     [assistant; severity_vol anchored]
  your tenancy         0.10     0.09               13%             rent.reset_hazard=7%/yr,
                       [0.08,0.12]                                   simulation.rent_escalation_vol=6% [assistant]
  the population       0.03     0.03                6%             market_scenario.path [assistant],
                       [0.02,0.05]                                   geography [user] — the prior's own rows
                                                                     carry their citations
  the condo's costs    0.01     0.01                4%             simulation.condo_fee_vol=8%,
                       [0.01,0.02]                                   other_cost_vol=10% [assistant]
  the economy          0.01     0.01                4%             economic.inflation_vol=1.2% ×
                       [-0.00,0.01]                                  corr_inflation_condo=0.5 (rho²=0.25 of
                                                                     the fee shock), corr_inflation_house=0.5,
                                                                     corr_inflation_other=0.4,
                                                                     corr_inflation_event_cost=0.3 [assistant]
  the house's costs    not resolved at 2,000 futures (-0.001 [-0.002, 0.001])   0.4%
                                                                   simulation.house_maintenance_vol=20%
                                                                     [assistant]

  the first-order shares add to 1.16 [1.04, 1.31] — above the whole, which is estimator noise
  and not a finding. Interaction is not measurable at 2,000 futures; raise simulation.num_sims.
  (at 10,000 they add to 1.02 [0.97, 1.09].)

  "alone" means: if you learned that channel's realization exactly and nothing else, the
  spread's variance would fall by that fraction. It is NOT how often the channel changes the
  answer — that is the next column, and on your portfolio the two are 0.88 and 41%.
  "flips the sign" is a FRACTION OF FUTURES, not a share of the spread: re-drawing that one
  channel and nothing else, this percentage of futures changes sides on whether rent is the
  cheapest option in them. 0.88 and 41% are different kinds of number about the same channel,
  and this column does not sum to anything.

  THE LEVEL — what the futures price that the central case does not
  channel              price it as the central case does, and the margin moves   P(rent cheapest)
  your tenancy            +$125,074  (± $1,775)                                   0.34 -> 0.54
  the housing market       -$38,314  (± $2,252)                                   0.34 -> 0.28
  the population           +$11,064  (± $1,095)                                   0.34 -> 0.35
  the condo's costs         +$5,232  (±   $786)                                   0.34 -> 0.35
  indistinguishable from zero at 2,000 futures: your portfolio (-$3,805 ± $5,383),
    the house's costs (-$886 ± $179), the economy (-$252 ± $642).

  the central case says rent by $31,349; the futures say -$67,194. Freezing all seven channels
  reproduces the central case exactly, and these seven shifts account for $98,114 of that
  $98,543 gap.
  [ARITHMETIC CORRECTED 2026-09-21: this draft read "$100,876 gap". 31,349 - (-67,194) is
  98,543; $100,876 implies a futures mean of -$69,527, a SECOND estimate of E[f] inside one
  block. A builder renders this figure as the SUBTRACTION of the two printed beside it, never
  as a stored third number, so the two can never disagree again. Caught by the contract
  builder.]
  READ THIS COLUMN AS: a cost the central case leaves out, not as a risk. Your lease ending is
  8% of the spread and four times the margin in level — it is why the central case and the
  futures name different winners. Your portfolio is 88% of the spread and moves the margin by
  nothing that resolves — it is the opposite: pure risk.

  NOT DRAWN IN THIS RUN — zero by construction, not by measurement
  your renewal rate    house.mortgage_renewal_rates is a path you stated
      (4.60%, 5.00%, 4.80%, 4.40%), not a distribution. The engine anchors no forward rate and
      draws none, so renewal carries no spread here at all. It carries this instead: replacing
      the stated path with one flat rate, the verdict's own winner changes from rent to the
      house at 1.61%, the runner-up changes from the condo to the house at 2.95%, and the
      option most futures call cheapest changes at 2.72%. Every grid point replaces the whole
      path with ONE figure applied at each renewal, so your stated path is not a point on that
      line. On the same axis: your contract 4.35%, which is
      itself the contracted 5-year uninsured anchor, and today's posted 5-year 6.09% — a list
      price to bracket a guess from above, never a ceiling on a 2031 renewal
      [mortgage_rate.contracted_5y_uninsured, mortgage_rate.posted_5y].
  your income          income.pay_drop_events moves the affordability report, not either
      option's present value, so it cannot move this margin.

  every channel above is sized by a figure the assistant chose, not by you. This ranking is a
  property of widths you did not state; the figure to check first is
  simulation.investment_return_vol = 10%.
```

Two lines in that draft are *(illustrative)*: the bracketed interval on `the economy`'s
`with interaction` figure is shown rounded, and the anchor label on `severity_vol` is written
from the registry's shape rather than re-read. Everything else, including every share, every
interval, every dollar figure, every probability and all three solved rates, was measured for
this spec.

**Formatter rules, which are what keep this a measurement:**

1. **Both registers print, or neither does.** A build that ships the spread table alone is the
   §1 failure. This is a single assertion in the formatter and a test.
2. **The level register's closing sentence has three branches, one per verdict state, and the
   formatter picks by `verdict.state` rather than by the sign of anything.** On `disagreement`
   it names the channel that put the central case and the futures on different sides, as drafted
   above. On `option` it says how much of the decisiveness survives each channel being priced the
   central case's way — `P(best cheapest)` moves toward 1.0 in that column, not away from it, and
   a sentence written for the disagreement mechanism would be false there. On `tie` it says which
   channel, if the central case priced it, would move the run out of the tie band. A formatter
   with one branch prints a disagreement explanation on an agreement, which is the §1 failure in
   miniature.
3. No column is ever labelled *importance* or *contribution to the answer*.
4. The flip column is never optional.
5. The residual line is printed, never inferred, and takes the refusal branch when the CI
   permits.
6. A share outside [0, 1] prints as `not resolved`, never clamped.
7. Every row's source class is **inline on that row**, never deferred to a trailing footnote.
   The one sentence that is allowed to sit below the tables is §5's gated provenance line,
   because it is about the table as a whole rather than about any row in it.

---

## 8. Silence, and the refusals

The unpriced spec's guard, applied verbatim: **the block prints figures solved from this run,
and the same feature must be able to print nothing. A block that cannot come out silent is a
disclaimer. One that can is a measurement.**

**Silent — nothing printed, nothing computed, no stream built, no draw consumed:**

1. `--decompose` not passed. This is every run shipped today, and it is what makes the absence
   invariant trivially true.

**Refuses, each with its own named reason, each reachable and tested:**

2. `--no-monte-carlo`, or `config.single_path_run(spec)` is True — there are no futures.
   Reachable today on `examples/first_time_buyer_montreal.yaml` *(measured)*.
3. Fewer than two options priced (`verdict.rule == "single_option"`) — no margin exists.
4. `k_live == 1` — the table would read 1.00 and be a tautology. The channel is **named** and no
   numbers print: *one channel carries all of this run's spread: the condo's own costs. There is
   nothing to split.* Reachable today on `examples/income_shock.yaml` *(measured)*.
5. `Var(f) == 0` with `k_live ≥ 1` — one option is cheapest on every path, so there is no
   decision spread to apportion, and every index is 0/0.
6. The budget gate: `num_sims · (k_live + 2) + m · k_live` above the ceiling. It names the
   figure and the two ways out (lower `num_sims` for the decomposition, or say which channels to
   hold). This is a gate on **work**, not a cap on `k_live` — a cap at 7 under a 7-channel
   taxonomy could never fire, which is the defect shape this repo names by hand.
7. A boundary in §6 that is not identified inside Monte Carlo noise, or whose confirming
   re-simulation disagrees with the free curve.

**Prints, but with no shares:** `P(f > 0) == 1` — every future agrees with the central case.

**The pinned pairs**, in the unpriced spec's own shape, and the assertion that this is not text:

- two configs differing in exactly one key — `simulation.investment_return_vol: 0.10` against
  `0.0`, on a spec whose only other live width is `condo_fee_vol` — one printing a two-row
  table, the other falling to refusal 4 and printing no numbers;
- two configs differing only in `simulation.value_growth_vol`, both printing, with different
  shares **and different level rows**.

If either passes trivially the block has become text and the test says so. `PROMPTS.md` gains
one sentence giving silence its meaning, so a user who sees nothing knows it is an answer.

---

## 9. Cost

**Model evaluations:** `num_sims · (k_live + 2)` for the spread register — the `A` and `B`
matrices plus one `A_B^(c)` per live channel — plus `m · k_live` for the level register, where
`m = min(num_sims, 2000)` by default because a paired mean needs far fewer paths than a variance
ratio. Structural zeros cost nothing. Bootstrap intervals cost no model evaluations.

**Measured on this machine, `uncertainty_surface.yaml`, 25 years, three options, all seven
channels live:**

| what | measured |
|---|---|
| shipped `run_monte_carlo`, 2,000 paths | 0.714 s — **357 µs/path** |
| with per-path per-channel seeding | **454 µs/path** (+27%; 40.9 s for 90,000 evaluations) |
| `load_config_dict` + `compute_deterministic` | 1.2–2.0 ms |
| spread register, 2,000 paths, `k=7` (18,000 evaluations) | **8.8 s** |
| level register, 2,000 paths, `k=7` (14,000 evaluations) | **8.6 s** |
| shipped `run_monte_carlo` at the default 10,000 paths | **4.14 s** |
| spread register at the shipped default 10,000 paths (90,000 evaluations) | **40.9 s** |

So the honest figures: the fixture at its own 2,000 paths costs about **17 s** against a 0.71 s
base run; the same config at the **shipped `num_sims` default of 10,000** costs about
**41 s + 14 s ≈ 55 s** against a measured **4.14 s** base run — roughly **13x**. §3.6's table
says five of seven shipped examples engage, so that multiple is the common case and not a
worst case built to look bad.

**That is why it is opt-in.** `--decompose`, optionally `--decompose=N` to run the decomposition
at its own sample size. §13 puts the automatic-vs-opt-in question to the operator, because
"first-class output, not a one-off study" is the board's phrasing and a flag is a reading of it.

**What it does to a run that does not ask: nothing.** Not one extra draw, not one extra branch
taken. The `streams=None` binding is today's stream, and the golden proves it.

---

## 10. Test plan

Every test with the mutation that kills it. No test that could pass on a broken engine.

**T1 — ABSENCE, byte level.** With no flag, `uncertainty_surface_mc_golden.json` is
byte-identical, every shipped example's `--json` and text are byte-identical, and a counting
proxy around the generator asserts the total draws consumed is unchanged.
*Kills it:* build the per-channel binding unconditionally, or reorder any draw site.

**T2 — THE ALL-FROZEN IDENTITY.** With every channel frozen, `f` equals `verdict.margin_pv` on
every path (measured: 31348.656075, max deviation 5.8e-11). One assertion per option that the
frozen PV equals `compute_deterministic`'s.
*Kills it:* a mask that misses a draw site (dead mask) — e.g. leaving the population tilt on, or
freezing value dispersion at `exp(−vol²/2)` instead of 1.0; or a mask that reaches another
channel's site.

**T3 — DEAD-CHANNEL EXACTNESS (the alignment test, and the sharpest available).** On a spec with
exactly one live channel `c`, for every dead channel `d`, `f(A_B^(d))` must equal `f(A)` **bit
for bit**, so `S_d = S_Td = 0.0` and `S_c = 1.0` with no estimator noise at all.
*Kills it:* two channels sharing an id, or positional stream spawning that reshuffles when
`k_live` changes.

**T4 — KNOWN ANSWER, analytic.** A spec with two live, additive, independent channels of known
variance ratio: **one other-cost line on an owned option and one on the renter** (two different
option groups — `other_cost_vol` is a single global key and both lines of the *same* option land
in the *same* group, so a two-line-one-option construction would be a tautology), with
`shock_model: normal` so the multiplier is linear and the ratio is genuinely analytic, and every
world channel off. Assert `S_1`, `S_2` inside their bootstrap intervals of the analytic values
and `ΣS ≈ 1`.
*Kills it:* dropping the 2 from Jansen's denominator — `S_T` doubles.

**T5 — INTERACTION IS DETECTED, AND THE REFUSAL FIRES.** On a spec where two channels genuinely
compound (`value_growth_vol` live with a live `price_shock` hazard, the crash multiplying a value
the dispersion already moved), assert `S_Tc > S_c` on both rows. Paired with the converse: on the
fixture at 2,000 paths the residual line must take the **refusal** branch (`ΣS = 1.164
[1.042, 1.310]`), and at 10,000 the numeric branch (`1.023 [0.969, 1.091]`).
*Kills it:* printing `S_c` in the interaction column (the residual then reports 0); or clamping
`ΣS` to 1, which makes the refusal branch unreachable.

**T6 — THE LEVEL REGISTER SEPARATES THE TWO CHANNELS THAT MATTER, and the spread register does
not.** On the fixture **at its committed seed 42 and its committed 2,000 paths**, assert
`share(shelter) < 0.15` and `level(shelter) > $100,000` and
`|level(portfolio)| < 2·SE(portfolio)` and — on the **lower bootstrap bound**, not the point
estimate — `lower(share(portfolio)) > 0.7`. Measured: 0.100 [0.081, 0.122]; +$125,074 ± 1,775;
−$3,805 ± 5,383; 0.877 [0.775, 0.999]. The seed is named in the test so that reseeding the
fixture is a deliberate act with a failing test attached, not a silent re-tuning.
*Kills it:* ship the spread register alone — the assertion names exactly what the reader would
have been told. This is the regression surface for §1's second wrong outcome.

**T7 — BOTH REGISTERS OR NEITHER.** The formatter emits the level block whenever it emits the
spread block.
*Kills it:* any future change that makes the level column conditional on its own significance —
the "indistinguishable from zero" rows must still print.

**T8 — THE TARGET IS THE MARGIN, NOT A LEVEL.** Assert the market channel's share of `f` is below
0.25 while its share of the condo's own PV is above 0.85, and that `P(f > 0)` equals
`verdict.prob_best` exactly.
*Kills it:* re-point the feature at per-option PV; or drop the third option by targeting the
deterministic pair — the house's flip column goes to exactly 0 and the equality with
`prob_best` breaks on any config where the third option wins futures.

**T9 — THE THREE STRUCTURAL ZEROS.** A financed run prints the renewal row and an all-cash run
does not; a run with an `income:` block prints the income row and one without does not; a
REAL-mode config with `inflation_vol > 0` and every `corr_inflation_*` at 0 prints `economy` as a
named structural zero **and spends no evaluations on it** (assert the evaluation count is
`num_sims · (k_live + 2)` with `economy` excluded from `k_live`).
*Kills it:* print any of the three unconditionally, or treat the real-mode case as a live channel
— the measured-zero row would then read as "inflation does not matter", and the evaluation count
assertion fails.

**T10 — THE EXACTNESS GATE DISCRIMINATES.** `house.mortgage_renewal_rates` and
`house.mortgage_rate` license (deviation/sd 2.0e-15) and `rent.monthly_rent` (1.8e-01) and
`house.value_growth_rate` (1.8e+00) do not; and the free curve for a refused key is asserted to
differ from a true re-simulation by more than the tolerance (measured 2.5 and 4.8 points).
*Kills it:* license everything → the second assertion fails; license nothing → the first fails;
drop check (a) → a key that changes the draw stream licenses.

**T11 — THE BOUNDARY IS CONFIRMED LIVE.** At each solved boundary, a full re-simulation's
probabilities equal the free curve's exactly (measured 0.1915 / 0.5185 / 0.2900 both ways), and
the row refuses when they do not.
*Kills it:* apply the shift with the wrong sign, take the delta from the wrong option, or reuse
the base `summary` instead of rebuilding it with `_summarize_array` — `mc_mean_best` goes stale
and the confirmed verdict differs.

**T12 — ONE HOME PER TRUTH.** The reversal register's deterministic crossing equals
`break_even.solve_crossings`' on the same pair to the cent, and equals
`story_plots.solve_rent_threshold`'s where they overlap.
*Kills it:* a second bisection written inside the new module.

**T13 — SILENCE IS REAL, AND SO IS EACH REFUSAL.** One test per case in §8, plus both pinned
pairs.
*Kills it:* loosen refusal 4 from `k_live == 1` to `k_live == 0` — the one-channel config starts
printing a 1.00 row and the pair test fails; or let any refusal fall through to silence.

**T14 — PROVENANCE AND ITS GATED SENTENCE.** Flip one `sources:` entry from `assistant` to
`user` and assert the superlative gate changes and the trailing provenance sentence changes,
while the table is otherwise identical.
*Kills it:* hardcode either sentence; or infer the class from the key name rather than from
`spec.sources`.

**T15 — REPRODUCIBILITY ACROSS PROCESSES.** Two subprocess runs at the same seed produce
byte-identical `decomposition` JSON, bootstrap intervals included.
*Kills it:* seed the bootstrap from the run's stream or from time; derive a channel id from set
iteration order.

---

## 11. Smallest shippable slice

**Slice 1 is both registers on one config, plus the financing-leg reversal rows.** Anything
smaller ships §1's failure.

In: the `streams` seam and its legacy binding; the seven-channel partition with fixed ids; the
renter split into `shelter` and `portfolio`; the freeze mask and its all-frozen identity; the
Saltelli/Jansen pair with bootstrap intervals; the flip column; the level register with paired
SEs and the `|Δ| > 2·SE` rule; the three structural zeros; the reversal register restricted to
`<opt>.mortgage_renewal_rates` and `<opt>.mortgage_rate` with the exactness gate, the confirming
re-simulation and a `RATE_BRACKETS` entry for the renewal ladder; the formatter with all seven
rules; every refusal in §8; the `--json` block; the `PROMPTS.md` sentence.

**What slice 1 proves, and it is one sentence:** that on the engine's own flagship fixture the
channel carrying 88% of the spread moves the answer by nothing that resolves, the channel
carrying 8% is what made the central case and the futures disagree, and the channel with no
spread at all reverses the verdict inside its own plausible bracket. None of those three
statements can be made by the engine today, and the third is the master's-project contribution.

---

## 12. Parallel work

Four tracks, no shared files, three of which start immediately once the channel table (seven
names, seven integer ids) is fixed as data. That table is a decision, not work.

- **A — `monte_carlo.py` only.** The `streams` seam, the legacy binding, the freeze mask, the
  renter split. Its contract is three assertions and no user-visible output: the golden is
  byte-identical with no streams; `f` with every channel frozen equals `verdict.margin_pv` bit
  for bit; `f(A_B^(d))` equals `f(A)` bit for bit for any dead `d`. This track is one builder,
  not two, because all four changes touch the same draw sites.
- **B — pure numpy, no engine import.** Saltelli/Jansen, the bootstrap, the flip column, the
  level arithmetic and the `ΣS` refusal rule, developed and tested against synthetic tables with
  analytic answers. This is the leg most likely to be subtly wrong and the one that needs no
  Monte Carlo at all to test.
- **C — the reversal register**, on `sweep.load_at` / `with_value` / `break_even.solve_crossings`
  / `flattened_path_note`, plus the `RATE_BRACKETS` entry and the exactness gate. Depends on none
  of A or B.
- **D — the formatter, the `--json` block, the `PROMPTS.md` silence sentence, the skill's two
  lines.** Was blocked on fork 1; that fork is ruled (§13) and D starts with the others. The
  ruling is a constraint on D's shape, not only on its wording: the function that renders the
  spread rows renders the level register too, and there is no caller-reachable path to one
  without the other. A test asserts that, by calling the narrowest public entry point the
  formatter exposes and finding both registers in what comes back.

A and B meet at the index table's shape; C and D meet at the block.

---

## 13. Forks — ALL THREE NOW RULED

The three forks this design left open were put to the operator on 2026-09-22 and answered. The
rulings are binding and the sections they touch are amended above; they are restated here
because a later reader will find the arguments for the rejected side and should know they were
weighed rather than missed.

**Fork 1 — the spread register's ranking, when every width in it is assistant-chosen.**
RULED: print the shares, but NEVER ALONE. The spread table may not appear without the level
register beside it, structurally, not by convention. The reason is the seat's §0 measurement:
the spread table's top row on this repo's own fixture is the renter's portfolio at 0.78–0.88 of
the scatter, and freezing it moves the decision by −$2,200, while the lease reset at under 0.08
of the scatter moves it by +$127,876. A reader given the spread table alone quotes the channel
that matters least. Binding the two means the correction cannot be lost in a copy-paste, which
a label can be. §5's "label" default is superseded; its provenance mechanisms 1–4 all stand and
are still required.

**Fork 2 — opt-in or automatic.** RULED before this spec was written: a `--reversal` flag. The
spec's own reasoning from measured cost agrees.

**Fork 3 — does slice 1 carry the reversal register, roughly doubling it?** RULED: YES. Two
reasons, and the second is the stronger. It is the only part of this feature with no
assistant-chosen width anywhere in it, because a stated input's reversal distance is solved from
the user's own numbers. And it is where the finding lives: the verdict's winner flips at a flat
renewal rate of 1.6052%, inside the bracket the engine already uses for a mortgage rate, while
that channel prints a dash in any variance table because its spread is identically zero.
Shipping the spread table without it would ship the half that can mislead and hold back the half
that cannot.

**The pre-ruling text that stood here has been deleted, deliberately.** It said *"this spec
takes label (§5)"* and *"this fork blocks track D"*, both now false, and it was the passage a
later reader would have quoted against the binding above. The arguments for the rejected sides
survive in the three paragraphs above and in §5 and §15; what is gone is only the statement of
a default that no longer holds. Caught by the contract builder (2026-09-21), reading the
section against the code it was about to type.

---

## 14. What this deliberately leaves open

- **Drawing the renewal rate.** Board item 1 slice 2. It turns §6's most important row from a
  solved boundary into a measured share as well, and it can be built in parallel with everything
  here: the row's shape does not change, only whether it carries a spread column too.
- **Splitting `market` into crash / ordinary dispersion, and the option channels into
  costs / events.** Each costs one more `N`. Add them when a run shows the coarse row leading and
  the user asks which half.
- **Second-order indices `S_cd`.** The residual says how much interaction exists; naming which
  pair owns it costs another `N` per pair, and on this fixture the residual does not resolve.
- **Decomposing anything other than `f`** — p95, end wealth, the affordability report. Board item
  8 owns the ranking figure; decomposing something the verdict does not read would be a second
  verdict.
- **The reversal register beyond the financing leg.** Rent level, growth rates and horizon are
  mostly gate refusals today, which is the honest output and proves the gate discriminates; the
  joint move along a two-input ray turns §4's non-additivity sentence into a measurement and is
  slice 3.
- **A price ↔ income correlation** (board item 13). It would be an eighth channel, and the
  per-path keying was chosen so that adding one cannot move channels 0–6.
- **The tie state.** `f` and its sign are well defined on a tie, but the header's sentence is
  not, and the block should be read once more against `state == "tie"` before slice 1 lands.

---

## 15. What was rejected, and why

Four designs were produced independently and each was critiqued by someone who did not write it.
This spec is one of them grafted with parts of the other three. Stated fairly, so a later reader
who finds a rejected idea attractive can see it was considered.

**Sobol on the pairwise gap, with the structural zeros printed by name — the base of this spec,
rejected only in its target and its verification.** Its load-bearing idea — that the Sobol inputs
must be the primitive draws, grouped by draw site, so the independence assumption holds exactly —
is correct, is the reason this spec exists in this shape, and was verified here. Two things were
changed. Its target, `PV[best] − PV[runner_up]`, silently deletes the third option; `f` keeps it
and has the better identity (`P(f>0) = prob_best` exactly, and `f` frozen equals the verdict's own
margin). And its verification, a statistical comparison of the split sample's `Var(f)` against
the shipped run's, has no power: the fixture's variance carries ~7% seed-to-seed noise and a real
missing shock moves it ~3%, so the gate would refuse correct runs and pass real bugs. The legacy
binding in §3.2 replaces it with a byte-exact check. Its own worked example also misstated its
fixture's verdict — it printed the Monte Carlo mean as "the central case" and named the
deterministic loser as the winner — which is why §7's draft is measured line by line.

**The reversal curve as the primary output — rejected as the primary, grafted whole as §6.** Its
mechanism is exact and cheap and was verified here: the financing-leg keys shift every path by
one constant to 2e-15 of the PV's own sd, and the free re-ranking equals a true re-simulation to
the last digit. But its deltas come from `compute_deterministic`, which reads no dispersion
input, so a curve over any *risk* channel is a flat line by construction — a feature titled
"which risk decides it" whose mechanism can only answer "not this one" about every risk. Measured:
the delta is exactly 0.0 on `value_growth_vol`, `condo_fee_vol` and `inflation_vol`. Its published
header also computed its spread on the wrong pair — `sd(condo − house) = $47,823` printed under a
rent-versus-condo heading whose true spread is `$286,813` — which is a 6x error in the confident
direction, on the one number it nominated as its own guard. §6 keeps the mechanism, restricts its
candidates to stated inputs by construction so the flat-curve artifact cannot occur, tightens its
gate from a 1%-of-sigma tolerance into an exactness test, and adds the confirming re-simulation.

**Shapley over a channel taxonomy on `P(det best cheapest)` — rejected; its freeze mask
grafted.** The freeze mask and the identity it makes provable (all channels frozen reproduces
`compute_deterministic` bit for bit) is the best idea in that design, and it is §3.4 of this one;
its diagnosis that the early-returning hazard samplers make draw counts outcome-dependent is
correct and is why §3.2 keys per path. But exact enumeration costs `2^k` full runs — 128 runs at
`k_live = 7`, several minutes at the shipped default — and its value function saturates: a
probability bounded in [0, 1] driven to its floor by one channel makes the solo effects sum to
far more than the whole (its own critic measured 179 points against a 66-point total), so the
printed interaction figure is a true number with a false explanation attached. And its "doubt"
column measures the same level effect this spec puts in its own register, mixed with spread and
uncomparable row-by-row against its dollar column, which was computed on a different contest.

**First-order decision share from one run, recorded rather than freed — rejected.** Its machinery
is cheap, correct and reproducible, and three of its disciplines are in this spec verbatim: the
residual is printed rather than rescaled, negative indices are stored as measured rather than
clipped, and a partition error becomes a checkable property that refuses. It was rejected because
its argmax is not what the board asks for, which its critic demonstrated by sweeping its own
leader from 0 to double its shipped size with no change to the verdict at all; and because its
stated reason for ignoring the one-world coupling is false about the code —
`_simulate_rent_pv_once` reads `world.inflation_factors` and `world.z_inflation` and never touches
`world.crash_draw` or `world.value_z`, so on a rent-versus-own decision the crash and the value
dispersion are differential, not common, and nothing cancels. Measured here:
`corr(condo, rent) = −0.0085`. Its recorder is in any case superseded by the stream split, which
yields `S_c` **and** `S_Tc` **and** the flip column from the same machinery.

---

## 16. The guard — how a builder cannot ship the expensive failure quietly

This feature's output is a claim about which uncertainty matters. If it is wrong, it is wrong in
the most expensive way this engine can be wrong: it tells a household to stop worrying about the
thing that will decide their answer. Six mechanisms, each with a failure state, stand between a
builder and that outcome. None of them is prose.

1. **T6** asserts, on the committed fixture, that the channel with 88% of the spread has a level
   effect indistinguishable from zero and the channel with 8% moves the margin by more than
   $100,000. A build that ships the spread register alone fails a test whose name is the mistake.
2. **T7** asserts both registers print together. There is no configuration of the formatter in
   which the spread table stands alone.
3. **T2** makes the level register a fact: all channels frozen must reproduce the verdict's own
   margin bit for bit. A mask that quietly misses a draw site cannot pass.
4. **T3** makes the channel partition a fact: replacing a dead channel's draws must change
   nothing, exactly, with no estimator noise to hide behind.
5. **T9 and §6** make the renewal ladder impossible to print as a dash: it is a structural zero
   **and** it carries three solved rates from the user's own config, and a run that prices a
   financed option and prints neither fails.
6. **The residual refusal and the no-clamp rule** mean the block's own arithmetic can say *this
   does not resolve* — and on the repo's flagship fixture, at the paths that fixture commits, it
   does say exactly that. A feature whose headline line is capable of refusing on its own
   showcase is a feature that will refuse on a stranger's config too.