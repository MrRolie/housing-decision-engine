# Renewal-rate path file — design (2026-10-01)

**Status:** ruled 2026-10-01, not built. Measured against main at a2d1a7d. Main then moved to
1486fbc, which lands the ladder's anchor refusal and changes only `src/hde/sources.py`,
`src/hde/input_schema.py`, tests and docs. `--json` on all 7 examples and the fixture is
byte-identical at the two commits.
**Lineage:** `docs/specs/2026-09-03-mortgage-renewal-risk.md` §3, §10 and §11 (the ladder, and
the fitted process it deferred); `docs/specs/2026-09-22-which-risk-decides-it.md` §3 and §6
(the channel partition and the reversal register); `docs/specs/2026-09-27-events-in-one-world.md`
E10 (the central case prices something a future can price).

Every figure below was measured. §12 gives each one's command. "Prototype" means an uncommitted
patch of a2d1a7d that implements §3 to §6 just far enough to measure them. Its file and config
inputs are defined in §2 and §12.

## 0. The ruling

**Operator, 2026-10-01.** When a run draws renewal rates per future, the distribution comes from
the path file of a fitted model. The model is fitted outside the engine, parametric or
machine-learning. It writes sampled renewal-rate paths to a file, together with its method, its
data window and its validation record. The engine prices those paths, on the precedent of the
`market_scenario` prior file. The engine holds no rate model and ships no defaults. The
household's ladder (`mortgage_renewal_rates`) stays exactly as it is, and a casual run cannot
switch the channel on.

**Seat mechanism rulings** (built to as written; §0.1 records where this spec makes one exact):

1. **Central case.** The deterministic case prices ONE ACTUAL ROW of the file. That row is the
   one nearest the per-year median path, by Euclidean distance over the priced renewal years,
   and a tie goes to the lowest index. It is never the per-year mean. The read-back names the
   row and why. The level register carries the gap between that row and the futures' mean.
2. **v1 scope.** `rate_shift` is dropped. `provenance.validation` is required (free text, plus
   an optional structured block), as are the method, the data window, the source and the
   producer.
3. **The draw.** It is channel 8 (income stays 7): ONE `integers(0, N)` per path, LAST in
   `monte_carlo._draw_path_world`, and gated, so a config without the file takes no extra draw.
   Every row is a full path over the renewal grid. The loader refuses N < 2, a zero spread, a
   file that prices no renewal inside the horizon, mixed terms, bytes that change within one
   process (pinned by sha256), `mortgage_renewal_rates` beside the file, and a financed option
   with no `mortgage_renewal_years`.
4. **Reversal register.** Gate clause (b) generalises to a per-path financing-delta licence
   (b′), keyed by the recorded row index. It is pinned three ways: deleted, the gate goes
   not_exact; widened to `value_growth_rate`, it refuses; every boundary is confirmed by full
   re-simulation. The reversal key stays `<opt>.mortgage_rate`. The cost is named: a file run
   alone does not say where the renewal level flips.
5. **Correlation.** Renewal draws are independent of inflation, prices, the renter's return and
   the discount rate. The read-back says so in one clause. A jointly fitted model is board item
   13's.
6. **"No draw touches it".** These rows are emitted on BOTH branches of the reversal gate. The
   ladder's row is dropped only when re-drawing channel 8 measurably moved that option.
7. **Fixtures.** A NEW opt-in fixture carries a synthetic file labelled "synthetic, not a
   calibration". `tests/fixtures/uncertainty_surface.yaml` is untouched unless a roster test
   forces a change. The first commit proves byte identity, with the file opted out, on all 7
   examples and that fixture.
8. **No producer.** The repo ships no producer or fitting script. Calibration is the user's own
   work, and §2 is the contract a producer writes to.
9. **Skill.** An assistant never proposes, invents or hand-builds a path file. It uses one only
   when the user supplies it. The "no distribution around the ladder" sentence holds only when
   there is no file. New skill text goes in `references/`.
10. **Read-back: figures, not prose.** One line, on the precedent of the `--decompose` ruling of
    2026-09-26 (which-risk spec §0.1 item 35). Drawn-option prose regenerates review rounds, so
    new sentences are kept to a minimum.
11. **Anchors.** An `anchor:` on any renewal-rate key is refused. The file path must not reopen
    the ladder fix, which was in flight when this was ruled and has landed since (§3).

### 0.1 Where this spec makes a ruling exact

- **Ruling 1's tie is decided in exact arithmetic.** Float evaluation breaks the counterexample's
  true tie by rounding: the squared distances come out 0.0027000000000000006 and 0.0027, so
  `argmin` returns row 1. As rationals on the same parsed floats, the two are equal and the
  first minimum is row 0 (§5).
- **Ruling 3's zero-spread refusal is evaluated per reading option.** That is what makes
  ruling 6 hold. Every reading option then pays a different rate on some future at one or more
  of its priced renewals, so no option's renewal rate falls out of both the spread register and
  the NO ROW list (§3 R12, §6).
- **Ruling 3's "renewal grid" is the renewal years, never simulation years.** Column k is the
  rate at the k-th renewal, as `mortgage_renewal_rates` indexes it, so a row is a ladder a user
  could type (§2).

## 1. Why

A household that states a ladder sees one scenario it chose. The futures hold that ladder
fixed on every path, so the renewal rate has zero spread BY CONSTRUCTION (which-risk §3.5 item
1). A user who trusts a rate model (fitted to a published series, parametric or
machine-learning) has no way to bring that model's distribution into the answer today.

With the path file, the engine can size renewal-rate risk from a model the user trusts, and
the engine itself still forecasts nothing:

- the user's paths reach every payment re-solve, every affordability ratio and the
  decomposition's spread and level registers;
- the model's own method, window and validation record print beside every answer that uses
  them, so the answer says whose distribution it is;
- the engine contains no rate model, so it has no parameter it could default, and a run with no
  file is today's run byte for byte (§8).

## 2. The file format

JSON in UTF-8, schema `hde.renewal_rate_paths`, version `"1"`. The loader follows
`market_scenario.load_scenario_prior`:
- `json.loads(..., parse_constant=...)` refuses `NaN` and `Infinity`;
- every object has an exact allowlist of fields;
- every violation is collected, and the file is refused once.

| Field | Type | Meaning |
|---|---|---|
| `schema` | `"hde.renewal_rate_paths"` | exact |
| `schema_version` | `"1"` | exact |
| `term_years` | int ≥ 1 | the fixed term T that every rate in the file is quoted for |
| `renewal_years` | list of int | THE GRID: exactly `[T+1, 2T+1, …, KT+1]`, K ≥ 1. Column k of every row is the rate quoted for the contract that starts in simulation year kT+1, the k-th renewal. The opening term is the option's own `mortgage_rate` and is not in the file. |
| `compounding` | `semi_annual` \| `effective_annual` | the quote convention (`rates.MORTGAGE_COMPOUNDING`). The engine converts each rate once, by THIS field, through `rates.effective_mortgage_rate`. |
| `as_of` | ISO date `YYYY-MM-DD` | the date the producer's paths start from. Provenance only: no engine arithmetic reads it, because the grid is indexed by renewal, as the ladder is, and the config states no purchase date. It is echoed in `--json` and checked for form alone. The prior's `time_anchor_violations` is not reused. Its two messages describe the prior's calendar-to-band mapping ("demographic band", "horizon-band mapping") and name `data_vintage.constants_as_of`, and a renewal file has neither. |
| `provenance.method` | non-empty str | what model, fitted how |
| `provenance.data_window` | non-empty str | the data the fit used |
| `provenance.source` | non-empty str | the published series, by name |
| `provenance.producer` | non-empty str | who or what wrote the file |
| `provenance.validation.text` | non-empty str | the validation record, free text |
| `provenance.validation.metrics` | optional `{str: finite number}` | the structured block |
| `paths` | list of N ≥ 2 rows | each row holds exactly K finite numbers ≥ 0 (booleans refused): decimal rates as quoted. Rows are equally weighted and drawn with replacement. To weight a row, repeat it; a weights field is an unknown field. |

**Grid against the config.**
- Every row must cover every renewal that a reading option prices inside the horizon (no
  carry-forward: that would extend the model with a figure the engine chose).
- A grid year that no reading option reaches inside its amortization is refused, by the same
  rule as the ladder's surplus refusal (`config._mortgage_renewal`).
- A grid year past the horizon but inside an amortization is read by nothing. The `renewals:`
  line marks it "not priced — past the horizon", as it marks a ladder's.

**Worked minimal example**, `m/two_paths.json`: the two-scenario file of ruling 1. Its sha256
is `b3827bb92169…` (these bytes with a trailing newline).

```json
{
  "schema": "hde.renewal_rate_paths",
  "schema_version": "1",
  "term_years": 5,
  "renewal_years": [6, 11, 16, 21],
  "compounding": "effective_annual",
  "as_of": "2026-10-01",
  "provenance": {
    "method": "synthetic, not a calibration: two hand-set paths",
    "data_window": "none",
    "source": "none",
    "producer": "the worked example of the path-file spec",
    "validation": {"text": "none: an example, not a model"}
  },
  "paths": [
    [0.02, 0.02, 0.02, 0.02],
    [0.08, 0.08, 0.08, 0.08]
  ]
}
```

`m/hvr_example.yaml` is `examples/mortgage_house_vs_rent.yaml` with `house.mortgage_renewal_years:
5` and `renewal_rates: {path: m/two_paths.json}`. Its horizon is 20 years and its amortization
25, so it prices the renewals in years 6, 11 and 16, and column 4 (year 21) is unpriced.

## 3. The config surface

```yaml
renewal_rates:
  path: rate_paths.json        # relative to the working directory, as market_scenario.path is
house:
  mortgage_renewal_years: 5    # required beside the file; mortgage_renewal_rates is refused
sources:
  renewal_rates.path: user
```

- `config._TOP_LEVEL_KEYS` gains `renewal_rates`, `config._SECTION_KEYS["renewal_rates"]` is
  `{"path"}`, and `input_schema._NOTES` gains the section.
- The file is loaded in `config._build_spec`, not at the CLI edge as the prior is.
  `compute_deterministic` prices the central row, and `load_config_dict` is the one path that
  every sweep point, break-even probe and reversal probe re-enters.
- A new module, `src/hde/rate_paths.py`, mirrors `market_scenario.py` and returns a
  `LoadedRatePaths`: sha256, quoted and effective rows, the central index, the priced columns
  and the provenance block.
- `ComparisonSpec.renewal_rate_paths: Optional[LoadedRatePaths] = None` is a dataclass field.
  It must be a field, because `decomposition_run._spec_at` copies the spec with
  `dataclasses.replace`, which carries only fields.
- Each reading option's `mortgage_renewal_rates_quoted` and `mortgage_renewal_rates` hold the
  CENTRAL ROW, so every deterministic consumer reads it unchanged: `renewal_segments_for`,
  `_annual_costs_for_option`, the story curves, the warnings and reversal admission.
- A *reading option* is a condo or house that is not `all_cash` and has a full mortgage block.
- `sources:`: `renewal_rates.path` is attributable like `market_scenario.path`. It takes `user`
  or `assistant`, and with no declaration it is `unattributed`. The block is never removed
  from the data before `build_source_echo` runs. `decomposition_run._given` reads the echo, and
  a width the echo never saw prints an empty "sized by".
- `sources.uncertainty_inputs`, `config.single_path_run` and `config.dispersion_sources` (on
  the owned side) all gain the file. They move together under the existing mirror test
  (`sources.py`, the comment above `_SIM_VOLS`). `single_path_run` keeps the field rule the
  prior already has; E13's measured predicate will replace them all at once.

**Refusals.** R1 to R18 are `ConfigValidationError` raised at load. Each names its key, row,
column or year.

| # | Refused | Message (figures in braces) |
|---|---|---|
| R1 | no file | `renewal_rates.path: no file at '{path}'` |
| R2 | not JSON, or `NaN`/`Infinity` | `'{path}' is not valid JSON: {error}` |
| R3 | unknown or missing field, at any level | `'{path}': unknown field(s) {names} (exact allowlist)` / `missing field(s) {names}` |
| R4 | wrong schema or version | `'{path}' is {schema} version {v}; this engine reads hde.renewal_rate_paths version 1` |
| R5 | an empty provenance string, or a non-finite or non-number metric | `'{path}': provenance.{field} must be a non-empty string — the read-back prints it as the file's own words` |
| R6 | `compounding` | `'{path}': compounding {value!r} — must be semi_annual or effective_annual` |
| R7 | grid | `'{path}': renewal_years {given} for term_years {T} must be {expected} — column k is the rate at the k-th renewal, simulation year k·{T}+1; the opening term is the option's own mortgage_rate` |
| R8 | `as_of` not an ISO date | `'{path}': as_of {value!r} is not an ISO date (YYYY-MM-DD)` |
| R9 | row shape or value | `'{path}': paths[{i}] has {n} rates and renewal_years has {K}` / `paths[{i}][{k}] = {v!r}: a rate is a finite number >= 0` |
| R10 | N < 2 | `'{path}' has 1 row: a distribution needs two or more` |
| R11 | mixed terms | `{opt}.mortgage_renewal_years is {t}; '{path}' quotes {T}-year rates` |
| R12 | zero spread, per reading option that prices a renewal inside the horizon | `every row of '{path}' prices {opt}'s renewals in years {years} at the same rates: no future differs` |
| R13 | ladder beside the file | `{opt}.mortgage_renewal_rates is set beside renewal_rates.path — one market, two sources for its renewal rate` |
| R14 | financed, no term | `{opt} has a mortgage and no mortgage_renewal_years; renewal_rates.path quotes {T}-year rates` |
| R15 | nothing priced | `no reading option renews inside the {N}-year horizon (first renewal: year {T+1})` |
| R16 | grid too short | `'{path}' ends at year {y}; {opt} renews in year {r} inside the {N}-year horizon` |
| R17 | grid past every amortization | `'{path}' renewal_years {y}: past every reading option's last renewal ({opt}: year {r})` |
| R18 | `anchor:` on `renewal_rates.path` | the existing `_anchor_declaration` refusal: `… an anchor sources a number, not str` (measured on `market_scenario.path`, §12) |
| R19 | bytes changed within one process | `'{path}' changed during this run: sha256 {first[:12]}… was priced, {now[:12]}… is on disk` |

- R11 also covers two reading options with different terms.
- The ladder's refusal of `mortgage_renewal_years` without `mortgage_renewal_rates`
  (`config.py:1636`) is lifted only when the file is present.
- R18 needs no new code. The ladder fix landed on main as 4c44e99..f59ca1b and lists the two
  ladder keys in `_UNANCHORED_KEYS` (`sources.py:460` at 1486fbc). That list is not extended,
  because its message describes a stated ladder ("a renewal rate is a stated scenario for a rate
  set years from now"). The ladder key itself cannot be targeted on a file run: R13 refuses it,
  and `sources:` refuses a key the config does not set ("a source can only be declared for a key
  the config sets", measured). So the file path does not reopen that fix (ruling 11).
- **R19.** Every load re-reads the bytes and pins the first sha256 it sees for the resolved
  path. Parsing is cached by sha. The error is `rate_paths.RatePathsChanged`, which subclasses
  neither `ConfigValidationError` nor `ValueError`. The per-point captures at
  `break_even.py:507,713,906,1439,1842`, `sweep.py:205,213,412` and `unpriced.py:188` catch
  those two, and they would fold a changed file into one row's reason. Instead the CLI catches
  it beside `ScenarioPriorError` (`cli.py:341,403`) and the run ends. One `--decompose`
  process read the file 6 times in the prototype, on a run whose only reversal key refused, so
  no scan ran. A licensed key adds a read per scan point.
- Under `--no-monte-carlo`, `RATES_WITHOUT_MONTE_CARLO` is the sibling of
  `cli.PRIOR_WITHOUT_MONTE_CARLO`: `renewal_rates draws only in Monte Carlo — this run prices
  the central row alone`.

## 4. The draw, the payment re-solve, affordability

- **Channel 8.**
  - `decomposition.CHANNELS` gains `Channel(id=8, key="rates", label="the renewal rates",
    sizing_keys=("renewal_rates.path",))`, and `decomposition.channel()` looks up by id. Today
    it indexes by position, which breaks the moment ids skip 7.
  - `run_monte_carlo`'s id guard (`0 <= c <= 6`, monte_carlo.py:1435) and its legacy-binding
    guard (`frozenset(range(7))`, :1451) both derive their ids from `decomposition.CHANNELS`,
    as `decomposition_run.ALL_CHANNEL_IDS` does. They cannot import `ALL_CHANNEL_IDS` itself at
    module level, because `decomposition_run` imports `monte_carlo` (`decomposition_run.py:101`);
    `decomposition.py` imports nothing from the package at run time. The id lists in their
    messages, and in `_AddressedBinding`'s message, gain 8.
  - `decomposition_run._CHANNEL_OPTIONS[8] = ("condo", "house")`.
  - Income stays 7 and stays unfreezable. No source line passes `range(7)` except :1451
    (`grep -rn "range(7)" src/hde`).
  - After this change a legacy-binding `freeze=range(7)` is refused on every run, including a
    run with no file, where it was safe. That over-wide case is accepted. No source caller makes
    the call: every `freeze=` in `src/hde` goes through `decomposition_run._run`, which passes
    `addressed_streams`. The two tests that do make it are rewritten in commit 4. The precise guard would have to read the config to decide whether channel 8
    draws, which is the predicted-liveness class (which-risk §0.1 item 39).
- **The draw.**
  - `WorldDraws.rate_rows` is N with a file and 0 without one. `PathWorld.rate_row` is
    `Optional[int]`.
  - LAST in `_draw_path_world`: `if draws.rate_rows and not b.frozen_at(8): rate_row =
    int(b.gen(8).integers(0, draws.rate_rows))`.
  - A frozen channel 8 sets `rate_rows = 0`, so the path prices the option's own ladder, which
    is the central row. That makes freezing channel 8 equivalent to pricing the central row
    (§5).
  - `Generator.integers(0, 1)` does not advance the generator, which is one more reason R10
    refuses N = 1.
- **Payment re-solve.**
  - `renewal_args_for(params, rates=None)` gains the override, and the two financing call sites
    (monte_carlo.py:952, :1070) pass that path's effective row, or None for the option's own
    ladder.
  - `pv.renewal_schedule` re-amortizes the remaining balance over the remaining amortization at
    each renewal. There is no new financial arithmetic.
  - Both options read the same row on a path, because the rate is the market's.
- **Affordability per path** (the events lane's C12 class).
  - `_annual_costs_for_option` gains `renewal_rates=None` and threads it into
    `renewal_segments_for`.
  - `run_monte_carlo._path_costs` keys its cache on `(option, reset_year, fired, rate_row)`
    and builds that row's array.
  - Prototype, `m/hvr_example.yaml` plus `income: {annual_income: 150000,
    affordability_threshold: 0.32}`:
    - the central row's peak ratio is 28.10% and row 1's is 38.55%;
    - there is no deterministic house breach;
    - P(house exceeds) is 0.508, which equals the share of paths that drew row 1.
- **Recorded rows.** `ComparisonMonteCarloResult.renewal_rate_rows: Optional[np.ndarray] =
  None` holds the row index of each path. `mc_to_dict` never emits it, because index arrays,
  like PV arrays, never cross a surface boundary.
- **Independence (ruling 5).**
  - The row index is a primitive of its own: independent of channel 0's z, of channel 1's
    draws, of channel 6's `z_inv`, and of the fixed `discount_rate`.
  - Within a row, the producer's serial and term structure is kept, because whole rows are
    drawn.
  - A jointly fitted file (rates and inflation per row) would make one primitive feed channels
    0 and 8. The partition would then have to merge them (which-risk §3.1). That is why the
    joint model is board item 13's.
- **Legacy binding.** Under `streams=None`, every channel shares one generator (`_OneStream`).
  On a file run, every draw after channel 8's moves to a new position in the stream, so the
  run's other summaries are not draw-for-draw comparable with the same seed without the file.
  The decomposition's rows are the measurement of channel 8, never a before-and-after
  difference.

## 5. The central case (ruling 1)

- **The rule.** Let P be the largest number of renewals that any reading option prices inside
  the horizon (`renewals_priced_inside`).
  - For each column k ≤ P, the median of the N quoted rates is taken (the mean of the two
    middle values when N is even).
  - Each row's squared Euclidean distance to that median path is taken over columns 1..P.
  - The central row is the FIRST row at the minimum.
  - Both steps are computed in exact rational arithmetic (`fractions.Fraction`) on the parsed
    floats, because float evaluation breaks a true tie by rounding (§0.1). The cost is N·P
    rational operations, once per load.
- **Injection.** The central row's K columns become each reading option's ladder (§3).
- **Measured on the counterexample** (main, typed ladders on `examples/mortgage_house_vs_rent.yaml`,
  5-year term):
  - the per-year mean path (5%) prices the house at **$363,941.75**;
  - row 0 (2%) prices it at **$296,909.29**, and row 1 (8%) at **$438,752.15**.
- **On the futures** (prototype, `m/hvr_example.yaml`, 5,000 paths):
  - the 2,460 paths that draw row 0 price the house from $277,674.54 to $318,418.37;
  - the 2,540 that draw row 1 price it from $419,293.02 to $467,443.65;
  - no future prices the house between $318,418.37 and $419,293.02, the interval that holds
    the mean path's $363,941.75. Pricing the mean would price a house no future reaches, which
    is E10's class.
- **The tie.** Rows 0 and 1 are equidistant from the median, so the lowest index wins. The
  central row is row 0, and the central case is $296,909.29. That is bit-identical to the same
  config with `[0.02, 0.02, 0.02, 0.02]` typed as the ladder (296909.29108796926 both ways). The
  median never splits the difference. The central case is always one future's path.
- **Level register.** Channel 8's level row is the margin shift with channel 8 frozen at the
  central row. On the counterexample: **+$71,772 (± $1,586)**, and with channel 8 frozen
  P(house cheapest) is 1.00.
- **All-frozen identity.** With channel 8 frozen beside channels 0 to 6, every path prices the
  central case. On the file run, `all_frozen_path_spread` is 0.0 and `all_frozen_deviation` is
  5.82e-11.

## 6. `--decompose`

- **Spread row.** One row, "the renewal rates", for channel 8.
  - It is sized by `renewal_rates.path='{path}' [{tag}]`.
  - Whether it is live is measured by `_DrawRecorder` and `_liveness`, never read off the
    config (which-risk §0.1 item 39).
  - Counterexample (prototype): alone **0.99 [0.96, 1.01]**, with interaction 0.99 [0.96,
    1.02], flips 0.9% [0.7, 1.2].
  - A channel 8 that drew and moved nothing gets the existing `_dead_draw_rows` row.
  - The work ceiling still clears the default. With nine streams drawing,
    `planned_evaluations(10000, 9, 2000)` is 130,000, against `EVALUATION_CEILING` 250,000
    (118,000 at eight today). The ceiling's comment says "at seven channels" and is corrected in
    commit 4.
- **Level row.** As in §5.
- **Reversal register, clause (b′).** For the candidate key x (here `<opt>.mortgage_rate`),
  probe value x₁, stated value x₀ and path rows ρᵢ:
  - Let Fin(ρ; x) be the named option's `_financing_pv` summed at `value_N = 0`, with ρ's
    effective rates. Let c be the central row and Gᵢ(x) = Fin(ρᵢ; x) − Fin(c; x).
  - Let Δᵢ be the per-path PV delta, and dᵢ = Δᵢ − [Gᵢ(x₁) − Gᵢ(x₀)].
  - **(b′):** `max |dᵢ − mean d| ≤ 1e-9 · sd(PV)`. Clause (a), that the other options are
    bit-identical, is unchanged.
  - Without a file, every path prices the central ladder, so Gᵢ is 0.0 exactly, dᵢ = Δᵢ, and
    (b′) IS (b), bit for bit.
  - The free curve at v shifts path i by `[det(v) − det(x₀)] + [Gᵢ(v) − Gᵢ(x₀)]` for the named
    option, and by today's shift for the others. Without a file the added term is 0.0, so
    today's curve is reproduced bit for bit.
  - Fin is computed once per distinct row per value.

  | Measured (prototype, 200 gate paths, (b′) exactly as defined above) | (b) | (b′) |
  |---|---|---|
  | `m/hvr_example.yaml`, `house.mortgage_rate` → 10% | 7.00e-02 of sd: refused | 1.42e-15 |
  | `m/hvr_ar1.yaml`, `house.mortgage_rate` → 10% | 1.76e-01: refused | 5.55e-15 |
  | `m/hvr_ar1.yaml`, `house.mortgage_rate` → 1% | 1.60e-01: refused | 5.90e-15 |
  | `m/hvr_ar1.yaml`, widened to `house.value_growth_rate` → 5% | 1.79e-01 | **1.79e-01: refused** |
  | fixture, no file, `house.mortgage_rate` → 10% | 9.524697909411047e-16 | 9.524697909411047e-16 |
  | fixture, no file, `house.mortgage_renewal_rates` → 10% | 9.524697909411047e-16 | 9.524697909411047e-16 |
  | fixture, no file, `house.value_growth_rate` → 5% | 2.744209111776317 | 2.744209111776317: refused |

  **The central row's leg is subtracted on purpose.** A (b′) that subtracts only each path's own
  leg, Fin(ρᵢ; x₁) − Fin(ρᵢ; x₀), licenses the same keys, but it is not (b) without a file: on
  the fixture's `house.mortgage_rate` it gives 9.572e-16 against (b)'s 9.525e-16. Only the Gᵢ form
  is 0.0 exactly when every row is the central row.

  Clause (a) held on every file run: moving `house.mortgage_rate` moved no other option, and
  both runs drew the same row on every path.

  **Confirmation by full re-simulation** (`m/hvr_ar1.yaml`, 5,000 paths). P(house cheapest) on
  the (b′) curve equals a full re-simulation at 6% (0.9992) and at 7.5% (0.9792). At 7.5% the
  constant-shift curve gives 0.9844, so a curve licensed by (b) would have been 0.52 points
  wrong. Every printed boundary keeps today's confirming re-simulation (`_confirmed_boundaries`).

  **What a file run does not say:** `<opt>.mortgage_renewal_rates` is refused beside the file,
  so the register has no renewal-LEVEL axis. Where the renewal level flips the verdict is the
  ladder run's answer (on the fixture's ladder, the central winner changes at 1.6052%). That
  `not_exact` "is unreachable for a financing-leg key on a correct engine" (break_even.py, the
  gate branch) stays true under (b′).
- **"No draw touches it" rows (ruling 6).**
  - `zeros.append(_stated_path_zero(key))` (break_even.py:2339) runs on the exact branch only.
    It moves above the gate's branch, so the licensed and the not_exact row both emit it.
  - Measured (prototype, without (b′)): `house.mortgage_rate` went not_exact on all four fields,
    and the block's NO ROW list was empty, though no draw touches the contract rate.
  - The three states:
    1. *No file.* Both `stated_path` rows print, as today.
    2. *File, channel 8 live.* The renewal rate is in the spread and the level. The contract
       rate's row prints on either gate branch.
    3. *File, channel 8 drew and is dead.* `_dead_draw_rows` names it.
  - The ladder's `stated_path` row never reaches the drop rule in v1. `reversal_candidates`
    reads the raw config, and on a file run the raw config cannot state the ladder (R13). On a
    run with no file, channel 8 never draws. So v1 has no ladder row to drop and builds no drop
    branch. Any later version that lets a ladder and a file coexist drops the ladder's row only
    when re-drawing channel 8 measurably moved that option (ruling 6).
- **JSON and homes.** `decomposition.spread.rows[]` and `level.rows[]` carry `channel_id` 8 and
  `key` `"rates"`. The channel table in `docs/reference/API_CONTRACT.md` (one home) and which-risk
  §3.1's table both gain the row.

## 7. The read-back line

One line in `serialization.format_assumptions`, after `demographic prior:`. It holds the figures
of ruling 10 and nothing else:

```
renewal rate paths: {path} · sha256 {sha[:12]}… · central row {i} of {N:,} (nearest the per-renewal median{tie}): {r_1:.2%}, …, {r_P:.2%} as quoted ({compounding}) · 5–95% by renewal: year {y_1} {p5_1:.2%}–{p95_1:.2%}, …, year {y_P} {p5_P:.2%}–{p95_P:.2%} · method: {method} · data window: {data_window} · validation: {validation.text} · drawn independently of inflation, prices, the renter's return and the discount rate
```

- `{tie}` is `, tied with {k} other row(s), lowest index` when the minimum is shared, and empty
  otherwise.
- `{compounding}` is `semi-annual` or `effective annual`.
- The band is `numpy.percentile(column, [5, 95])` (linear) over the N quoted rows, for the
  priced columns only.
- The method, window and validation are printed verbatim: they are the file's own words, and
  the engine checks that they are present, not that they are true.
- Whose file it is prints where every key's source prints: in the `sources` echo lines.

The template filled with the figures measured on `m/hvr_example.yaml` (the prototype does not
print this line):

```
renewal rate paths: m/two_paths.json · sha256 b3827bb92169… · central row 0 of 2 (nearest the per-renewal median, tied with 1 other row, lowest index): 2.00%, 2.00%, 2.00% as quoted (effective annual) · 5–95% by renewal: year 6 2.30%–7.70%, year 11 2.30%–7.70%, year 16 2.30%–7.70% · method: synthetic, not a calibration: two hand-set paths · data window: none · validation: none: an example, not a model · drawn independently of inflation, prices, the renter's return and the discount rate
```

**The siblings that change.** Two surfaces turn false on a file run (prototype, rendered output
of `m/hvr_example.yaml`), and one is mislabelled by code reading:

- `renewal_source_clause` printed "a stated scenario, not a forecast — the engine anchors no
  renewal rate, and the read-back cannot tell whose figure it is". On a file run it becomes the
  figure `central row {i} of {path}`.
- The bias warning printed "the stated renewal path prices the mortgage $46,305 below its
  contract rate …; state the renewal path you want stressed". Its subject becomes
  `{path}'s central row {i}`, and its remedy clause is dropped on a file run.
- `assumptions.mortgage_renewals[].compounding` prints `opt.mortgage_rate_compounding`
  (`serialization.py:582`). A semi-annual file beside an effective-annual contract would then
  label the file's quotes with the contract's convention. On a file run it prints the file's
  `compounding`.

**Siblings checked:**

- The one-rate-per-block ambiguity warning stays silent on a file run, because the file
  declares its own grid (R7) instead of leaving the reading to the engine.
- `renewal_line`'s "rates as quoted (semi-annual)" clause prints only when quoted ≠ effective,
  which happens only under a semi-annual conversion, so it stays true.
- The Act 2 sentence and the paid-curve kinks are the central case's figures, unlabelled as
  "stated", and stay as they are.

**`--json`.** `assumptions.renewal_rate_paths` is the provenance block:
- `path`, `file_sha256`, `schema_version`, `term_years`, `renewal_years`, `priced_years`,
  `compounding`, `as_of` and `rows`;
- `central_index`, `central_rates_quoted` and `tied_rows`;
- `band` as `{year: [p5, p95]}`;
- `provenance` verbatim, with source, producer and validation metrics;
- `independent_of: ["inflation", "prices", "the renter's return", "the discount rate"]`.

## 8. Back-compatibility and the commit order

**With no file:**
- no draw is taken, because the draw is gated;
- `rate_row` is None, so `renewal_args_for(opt)` makes exactly today's call;
- `_path_costs` takes today's key path;
- `renewal_rate_rows` is None and is never serialized;
- (b′) is (b) bit for bit;
- the registers iterate only the streams that drew and the channels that are live.

Measured, a2d1a7d against the prototype:
- `--json` stdout and stderr are byte-identical on all 7 examples and the fixture;
- the fixture's `--decompose` text, stderr and `--json` are byte-identical.

**The flagship fixture** stays untouched, because no roster test forces a change.

| Suite | Failed | Passed |
|---|---|---|
| a2d1a7d | 1 | 2,438 |
| prototype | 12 | 2,427 |

The baseline's one failure is the merge-marker test, which needs `git` and fails in an archive.
The prototype's 12 are that same test plus 11 others:

- **Seven pins of the seven-channel table:**
  - two in `test_channel_streams.py`: a legacy-binding `freeze` of `range(7)` is now partial;
  - four in `test_decomposition_contract.py`: slots 0 to 6, `channel(8)` must raise, the
    hash-seed stability check, and the pointer test, which pins `channel()`'s positional body
    line verbatim;
  - one in `test_decomposition_contract_doc.py`: the key list.
- **Four `test_input_schema.py` tests** (three in `TestCompleteness`, one in
  `TestRequiredFlagsAreTrue`). The prototype declares the section with no `_NOTES`.

None of the 12 is a roster test of the flagship fixture, `uncertainty_surface_mc_golden.json`
passed, and no numeric golden moved.

**Commit order.** The suite is green at every commit, and commit 1's goldens are unchanged
through commit 7.

1. `test`: the opted-out goldens. For each of the 7 examples and the fixture, the sha256 of
   the `--json` document produced in-process with the run date pinned. The date has to be
   pinned because the fixture's document depends on it: it differs between run dates 2026-10-01
   and 2028-06-01. Add the fixture's `--decompose --json` sha256 too. Captured at a2d1a7d, and
   green on main.
2. `refactor`: `channel()` looks up by id, and the two freeze guards derive their ids from
   `CHANNELS`. It is still 7 channels, so no figure moves. The pointer test's pinned body line
   is updated here. Measured on that change alone, it is the only one of the three table-pin
   files' 255 tests that fails: the test pins `    if not 0 <= channel_id < len(CHANNELS):`
   verbatim.
3. `feat(rate_paths)`: the loader, R1 to R19, the config surface with its `input_schema._NOTES`
   section (the four `test_input_schema.py` tests force it into this commit), the source and uncertainty
   mirror, and the new opt-in fixture (§9).
4. `feat(monte_carlo)`: channel 8, the draw, the per-path re-solve and affordability, the
   central row, and the identity pins. The other six table pins are rewritten here to derive
   from `CHANNELS`. The legacy-binding refusal's message, which ends "a freeze of all seven
   channels", is corrected too.
5. `feat(break_even)`: (b′) and its free curve, and the zero rows on both gate branches.
6. `feat(serialization)`: the read-back line, §7's three siblings that change, the `--json`
   block, and the rows in API_CONTRACT and which-risk §3.1.
7. `docs(skill)`:
   - `references/gates.md` §6, after "turn the uncertainty inputs ON": "`renewal_rates.path` is
     not one of those switches: use a path file only when the user supplies one, and never
     propose, invent or hand-build one."
   - `references/gates.md` §8. "Once the config states `mortgage_renewal_years` +
     `mortgage_renewal_rates` the risk is PRICED" gains "or a `renewal_rates` file". "Name
     instead the one path the run holds, with no distribution around it" then holds for a
     ladder only. For a file, the line to read back is `renewal rate paths:`.
   - `references/answer-template.md` §8. "With a renewal path stated the item moves out of this
     section" gains "or a `renewal_rates` file". "As ONE scenario with no distribution around
     it" holds for a ladder only. For a file, the `renewal rate paths:` line goes into the
     assumptions.
   - SKILL.md line 160 changes from "renewal risk unless a path is stated (toward buying;
     stated, it is priced)" to "renewal risk unless a ladder or path file prices it (toward
     buying)". The old sentence is false on a file run. The edit takes SKILL.md from 2,597 to
     2,596 words, under the 2,600 limit in `tests/test_skill_contract.py`.
   - `references/quick-sense.md` line 73 ("renewal risk when no renewal path is stated") and
     `references/translation.md` line 22 ("with no renewal path … renewal risk is not modelled")
     gain "and no `renewal_rates` file".
   - The last five sentences are false on a file run as they stand today: each makes "no path
     stated" mean "not modelled" (`git grep -n -i renewal -- .claude/skills/hde/`, read for
     that class).

## 9. Tests: the classes this invites, each pinned and mutated both ways

Each refusal is pinned with the legal config one step away (the events lane's §3 rule). Each
pin names the mutation that must fail it.

| # | Class | Pin | Mutation that must fail it |
|---|---|---|---|
| 1 | One world | A typed ladder equal to the central row reproduces `compute_deterministic` bit for bit (measured). The all-frozen identity holds on a file run (measured: 0.0 spread, 5.82e-11). | A per-year-mean centre ($363,941.75 ≠ $296,909.29); a float `argmin` (row 1 on the tie); "row 0 always", on the new fixture, whose central row is not 0 |
| 2 | Predicted liveness | R10, R12 and R15 refuse at load. Channel 8's row exists exactly when `_DrawRecorder` saw stream 8 advance. Exactly one `integers` call per path on stream 8 (a generator-state instrument). | A second draw per path; a liveness flag read off `spec.renewal_rate_paths` |
| 3 | Stream order and opt-out | Commit 1's goldens and `uncertainty_surface_mc_golden.json`. Under the legacy binding, path 0's world draws (inflation, crash, drift, value) on a file run equal the same config's without the file. | Moving the draw before the inflation loop |
| 4 | Channel-count hard-codes | `freeze=ALL_CHANNEL_IDS` is allowed on the legacy binding; `freeze=range(7)` is refused as partial (§4 says why on a run with no file too); `channel(8)` resolves; `channel(7)` and `channel(9)` raise. | Any surviving positional `CHANNELS[i]` or literal `range(7)` |
| 5 | One market | A config with two reading options draws the same row for condo and house on every path. | A per-option draw |
| 6 | Per-path affordability (C12) | P(house exceeds) 0.508 = the share of row-1 paths, on §4's config. | Central costs on every path: P = 0.0 (measured) |
| 7 | (b′) | It licenses `mortgage_rate` on a file run (residual ≤ 1e-9·sd) and matches re-simulation (measured, §6). With no file, (b′) and (b) are bit-identical on the fixture's two licensed keys. **First pin the builder lands:** the register's own output under (b′), end to end on the new fixture, which was not measured here. | Deleted: not_exact (7.00e-02, 1.76e-01). Widened to `value_growth_rate`: refuses (1.79e-01). A gate that refuses everything fails the no-file pin. A (b′) without the central row's leg fails the no-file bit identity (9.572e-16 against 9.525e-16). |
| 8 | Vanishing zero row | The contract rate's row prints on both gate branches. | Restoring line 2339's placement (the prototype lost the row) |
| 9 | The siblings that change | The RENDERED text of a file run contains "stated" on no renewal surface. On a semi-annual file beside an effective-annual contract, `assumptions.mortgage_renewals[].compounding` is `semi_annual`. | Any of the three restored |
| 10 | File integrity | Bytes rewritten between two loads in one process raise `RatePathsChanged`, and a sweep does not swallow it. The printed sha equals the sha of the bytes priced. | Catching it as `ConfigValidationError` |
| 11 | Refusals both ways | Every R-row against its neighbour: N = 2 loads; one varying column loads; `[6, 11, 16]` loads and `[1, 6, 11]` refuses; a condo whose amortization ends before a column the house reads loads. | Each refusal deleted, and each widened onto its neighbour |
| 12 | Anchors | `renewal_rates.path: anchor:<a registry name>` refuses; `user` and `assistant` load. | — (the existing branch, measured) |
| 13 | Read-back | Every figure on §7's line is recomputed independently in the test: the exact central row, linear percentiles, the sha of the bytes. | Any template field read from a second source |

**The new fixture.** `tests/fixtures/renewal_rate_paths.yaml` (house against rent, a 5-year
term, a horizon that leaves the last column unpriced) and
`tests/fixtures/renewal_rate_paths_synthetic.json`, committed as data. Its `provenance.method`
begins "synthetic, not a calibration", and its recipe is described there in words; no script
ships (ruling 8). Its rows are chosen so that the central row is not row 0, the compounding is
semi-annual, and the reversal register reaches boundaries.

## 10. Out of scope

- **`rate_shift`** (ruling 2). Without it, a file run has no renewal-level crossing (§6).
- **Correlation with any other channel** (ruling 5, board item 13). A joint fit merges
  channels in the partition (§4).
- **A producer or fitting script, or any calibrated file** (ruling 8).
- **The flagship fixture** (ruling 7). See §8 for the roster check.
- **Row weights, several terms in one file, variable- or trigger-rate products, prepayment
  penalties, and the qualifying-rate test at renewal.**
- **A calendar check on `as_of`.** The config states no purchase date for it to be checked
  against (§2).

## 11. Open questions

Neither of these can be settled by measuring inside the engine.

1. **Does independence understate the channel's share?** If rates and prices move in opposite
   directions, as they usually do, independence probably understates it. The engine cannot
   sign that covariance without a jointly fitted model, and that is board item 13's.
2. **What is the smallest N a file needs?** Drawing with replacement means a 50-row file at
   10,000 paths is a 50-point distribution. The read-back prints N. Whether some N should be
   refused is a product rule, not a measurement.

## 12. Measurements

Commands marked *main* run in a `git archive` of a2d1a7d. Commands marked *prototype* run in the
same archive with the prototype patch applied; the patch and its scripts are not committed.

| Figure | Command |
|---|---|
| $296,909.29 / $438,752.15 / $363,941.75 (main) | `uv run python -c "import copy, yaml; from hde.config import load_config_dict as load; from hde.deterministic import compute_deterministic as det; raw = yaml.safe_load(open('examples/mortgage_house_vs_rent.yaml')); raw['house']['mortgage_renewal_years'] = 5; [print(r, round(det(load(dict(copy.deepcopy(raw), house=dict(raw['house'], mortgage_renewal_rates=[r] * 4)))).house.total_pv, 2)) for r in (0.02, 0.08, 0.05)]"` |
| float tie 0.0027000000000000006 against 0.0027, `argmin` 1; exact tie, first minimum 0 (main) | `uv run python -c "import numpy as np; from fractions import Fraction as F; rows = np.array([[0.02] * 3, [0.08] * 3]); d2 = ((rows - np.median(rows, axis=0)) ** 2).sum(axis=1); print(d2.tolist(), int(np.argmin(d2))); ex = [[F(x) for x in r] for r in rows.tolist()]; m = [(a + b) / 2 for a, b in zip(*ex)]; e2 = [sum((x - y) ** 2 for x, y in zip(r, m)) for r in ex]; print(e2[0] == e2[1], e2.index(min(e2)))"` |
| `integers(0, 1)` does not advance the generator (main) | `uv run python -c "import numpy as np; g = np.random.default_rng(1); s = g.bit_generator.state; g.integers(0, 1); print(g.bit_generator.state == s)"` |
| R18: the anchor refusal on a path key (main) | `uv run python -c "import yaml; from hde.config import load_config_dict; raw = yaml.safe_load(open('tests/fixtures/uncertainty_surface.yaml')); raw['sources']['market_scenario.path'] = 'anchor:mortgage_rate.contracted_5y_uninsured'; load_config_dict(raw)"` |
| line 2339; :1435 and :1451; 2,597 words (main) | `grep -n "zeros.append(_stated_path_zero" src/hde/break_even.py`; `grep -n "0 <= c <= 6\|frozenset(range(7))" src/hde/monte_carlo.py`; `wc -w .claude/skills/hde/SKILL.md` |
| 2,596 words after the line-160 edit (main) | the edit applied to a copy, then `python3 -c "print(len(open('SKILL.md').read().split()))"` |
| the fixture's `--json` depends on the run date (main) | `cli.main()` in-process with `datetime.date.today` patched to 2026-10-01 and then 2028-06-01; the two documents differ |
| byte identity, file opted out (main and prototype) | `uv run hde <config> --json`, stdout and stderr sha256, for `examples/*.yaml` and `tests/fixtures/uncertainty_surface.yaml`, in both trees; `uv run hde tests/fixtures/uncertainty_surface.yaml --decompose`, text and `--json`, in both trees |
| the example's sha256, its exact central row 0 (tied with row 1), its band 2.30%–7.70% (prototype) | `sha256sum m/two_paths.json`; `numpy.percentile(rows[:, k], [5, 95])` |
| central $296,909.29 bit-identical to the typed ladder; the futures' ranges (prototype) | `load_config_dict` and `compute_deterministic` on `m/hvr_example.yaml` against the same config with `renewal_rates` removed and `[0.02] * 4` typed; `run_monte_carlo` on the file run |
| 0.99 [0.96, 1.01]; +$71,772 (± $1,586); 0.0 and 5.82e-11; not_exact 7.00e-02 with an empty NO ROW list (prototype) | `uv run hde m/hvr_example.yaml --decompose`, and the same with `--json` |
| §6's (b)/(b′) table (prototype) | `run_monte_carlo` at `simulation.num_sims` 200, stated and probe (`sweep.load_at`); (b) by `break_even._shift_deviation_over_sd`; (b′) with Gᵢ as §6 defines it, Fin by `deterministic._financing_pv` at `value_N = 0` with `renewal_args_for` overridden by the row. `m/hvr_ar1.yaml` is `m/hvr_example.yaml` pointed at `m/ar1.json`: 2,000 rows × 4, AR(1) φ 0.5, stationary sd 1 pp around 4.5%, semi-annual, `numpy.random.default_rng(20261001)`, synthetic (regenerated from that recipe: sha256 `4ea1ca85a121…` both times). |
| 9.572e-16 for the per-path-leg form (prototype) | the same, with dᵢ = Δᵢ − [Fin(ρᵢ; x₁) − Fin(ρᵢ; x₀)], on the fixture's `house.mortgage_rate` → 10% |
| 130,000 and 118,000 against 250,000 (main) | `uv run python -c "from hde.decomposition_run import planned_evaluations as p, _level_paths as m, EVALUATION_CEILING as c; print([p(10000, k, m(10000)) for k in (8, 9)], c)"` |
| `_UNANCHORED_KEYS` at `sources.py:460`; the ladder's anchor refused and `market_scenario.path`'s still refused (1486fbc) | `git log --oneline a2d1a7d..origin/main`; `git grep -n _UNANCHORED_KEYS origin/main -- src/hde/sources.py`; R18's command above, and the same with the fixture's `house.mortgage_renewal_rates` declared `anchor:mortgage_rate.contracted_5y_uninsured`, in a `git archive` of 1486fbc |
| 1486fbc touches only `sources.py` and `input_schema.py` under `src/`; `--json` byte-identical to a2d1a7d (repo, 1486fbc) | `git diff --stat a2d1a7d origin/main -- src/`; the opt-out sha256 command below, in a `git archive` of 1486fbc |
| commit 2 alone breaks only the pointer test: 1 failed / 254 passed (main + that change) | `channel()` by id and both guards from `decomposition.CHANNELS`, then `uv run --extra dev python -m pytest -q tests/test_decomposition_contract.py tests/test_channel_streams.py tests/test_decomposition_contract_doc.py` |
| a module-level `from .decomposition_run import ALL_CHANNEL_IDS` in `monte_carlo.py` is circular (main + that line) | `uv run python -c "import hde.monte_carlo"` raises `ImportError: cannot import name 'single_path_run' from partially initialized module 'hde.config'` |
| no source caller freezes on the legacy binding (main) | `grep -rn "freeze=" src/hde`: lines 851, 878 and 987 of `decomposition_run.py`, all through `_run` and `addressed_streams` |
| the config states no purchase date (main) | `uv run hde --print-schema \| grep -io '"[a-z_]*\(date\|calendar\|purchase\)[a-z_]*"' \| sort -u` prints only the three `*purchase_costs*` keys |
| `sources:` refuses a key the config does not set (main) | the fixture with `house.mortgage_renewal_*` removed and `sources: {house.mortgage_renewal_rates: user}`, through `load_config_dict` |
| 0.9992, 0.9792 and 0.9844 (prototype) | `m/hvr_ar1.yaml` at 5,000 paths: the shifted base arrays through `break_even._cheapest_probabilities`, against `run_monte_carlo(load_at(raw, "house.mortgage_rate", v))` |
| 28.10%, 38.55%, 0.508 and 0.0 (prototype) | §4's config, `run_monte_carlo`, then the same with `deterministic._annual_costs_for_option` patched to the central row |
| 6 file reads in one `--decompose` (prototype) | the loader wrapped with a counter, `cli.main()` run in-process with `m/hvr_example.yaml --decompose` |
| 1 failed / 2,438 passed and 12 failed / 2,427 passed, with §8's list (main and prototype) | `uv run --extra dev python -m pytest -q -p no:cacheprovider` in both trees (846 s and 879 s) |
