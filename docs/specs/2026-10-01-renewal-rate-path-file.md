# Renewal-rate path file — design (2026-10-01)

**Status:** ruled 2026-10-01, revised 2026-10-02 after two review rounds (§0.1 items 4 to 14),
built 2026-10-02, from commit 751bee2 on. Round 1 measured on main at a2d1a7d. Round 2's
figures, like the review's, are on 1486fbc, which changes only `sources.py` and
`input_schema.py` under `src/hde/`, and whose `--json` on all 7 examples and the fixture is
byte-identical to a2d1a7d's.
**Lineage:** `docs/specs/2026-09-03-mortgage-renewal-risk.md` §3, §10 and §11 (the ladder, and
the fitted process it deferred); `docs/specs/2026-09-22-which-risk-decides-it.md` §3 and §6
(the channel partition and the reversal register); `docs/specs/2026-09-27-events-in-one-world.md`
E10 (the central case prices something a future can price).

Every figure below was measured, and §12 gives each one's command. "Prototype" means an
uncommitted patch that implements §3 to §6 just far enough to measure them, on a2d1a7d in round
1 and on 1486fbc in round 2, where an independent rebuild on 1486fbc reproduced every round-2
figure. Its inputs are defined in §2 and §12. The build starts from origin/main, never from the
prototype.

## 0. The ruling

**Operator, 2026-10-01.** When a run draws renewal rates per future, the distribution comes from
the path file of a fitted model. The model is fitted outside the engine, parametric or
machine-learning. It writes sampled renewal-rate paths to a file, together with its method, its
data window and its validation record. The engine prices those paths, on the precedent of the
`market_scenario` prior file. The engine holds no rate model and ships no defaults. The
household's ladder (`mortgage_renewal_rates`) stays exactly as it is, and a casual run cannot
switch the channel on.

**Mechanism rulings** (built to as written; §0.1 records where this spec makes one exact):

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

### 0.1 Where this spec makes a ruling exact, and the rulings of 2026-10-02

1. **Ruling 1's tie is decided in exact arithmetic.** Float evaluation breaks the
   counterexample's true tie by rounding: the squared distances come out 0.0027000000000000006
   and 0.0027, so `argmin` returns row 1. As rationals on the same parsed floats they are
   equal, and the first minimum is row 0 (§5).
2. **Ruling 3's zero-spread refusal is evaluated per reading option** (R12). Every reading
   option that prices a renewal then pays a different rate on some future at one of them, so
   none falls out of both the spread register and the NO ROW list, which is what makes ruling 6
   hold (§6).
3. **Ruling 3's "renewal grid" is the renewal years.** Column k is the rate at the k-th
   renewal, as `mortgage_renewal_rates` indexes it (§2).
4. **Coverage.** A grid that misses a renewal inside any reading option's amortization is
   refused (R16), so nothing is carried forward; option o reads its first n_o columns (§2, §4).
5. **`as_of` is optional provenance** (§2).
6. **`renewal_rates.path` takes `user` only**; `assistant` is refused (R20), enforcing ruling 9.
7. **(b′) checks its premise:** identical recorded rows in the stated and probe runs, or the
   gate refuses (§6).
8. **The central row depends on the priced renewals**, so on the horizon; at any config the
   file loads against, an amortization cannot move it (§5). The read-back names it at each sweep
   point, and a crossing on a row switch says so.
9. **The did-you-mean change is accepted** (§8).
10. **Commit 1's goldens store the documents**, `engine_version` masked, never bare sha256s (§8).
11. **The test hard-codes and the stale "seven" comments join the commit plan** (§8).
12. **Engine remedy text never names the file key**, and the one-sided-uncertainty fix lists
    (config.py:836–846) do not gain it (§3).
13. **A file run gates the whole ladder-warning loop off** (config.py:874–985), the bias
    warning included, with no retargeted prose: the read-back's band already shows it (§7).
14. **Cuts.** File-run skill guidance has one home, gates.md §8. Elsewhere a sentence that a
    file run would make false gains a scope clause pointing there, and nothing more (§8, commit
    7). The independence clause is §7's exact string, and the JSON lists channel ids derived
    from `CHANNELS`.

## 1. Why

A household that states a ladder sees one scenario it chose. The futures hold it fixed on every
path, so the renewal rate has zero spread BY CONSTRUCTION (which-risk §3.5 item 1), and a user
who trusts a rate model has no way to bring its distribution into the answer. With the file,
the user's paths reach every payment re-solve, every affordability ratio and the
decomposition's registers, and the model's method, window and validation record print beside
every answer that uses them. The engine still forecasts nothing: it has no parameter to default,
and a run with no file is today's run byte for byte (§8).

## 2. The file format

JSON in UTF-8, schema `hde.renewal_rate_paths`, version `"1"`. The loader follows
`market_scenario.load_scenario_prior`: `json.loads(..., parse_constant=...)` refuses `NaN` and
`Infinity`, every object has an exact allowlist of fields, and every violation is collected
before the file is refused once.

| Field | Type | Meaning |
|---|---|---|
| `schema` | `"hde.renewal_rate_paths"` | exact |
| `schema_version` | `"1"` | exact |
| `term_years` | int ≥ 1 | the fixed term T that every rate in the file is quoted for |
| `renewal_years` | list of int | THE GRID: exactly `[T+1, 2T+1, …, KT+1]`, K ≥ 1. Column k of every row is the rate quoted for the contract that starts in simulation year kT+1, the k-th renewal. The opening term is the option's own `mortgage_rate` and is not in the file. |
| `compounding` | `semi_annual` \| `effective_annual` | the quote convention (`rates.MORTGAGE_COMPOUNDING`). The engine converts each rate once, by THIS field, through `rates.effective_mortgage_rate`. |
| `as_of` | optional ISO date `YYYY-MM-DD` | the date the paths start from. Provenance only: no engine arithmetic reads it, because the grid is indexed by renewal and the config states no purchase date. Echoed in `--json` (null when absent) and checked for form alone. The prior's `time_anchor_violations` is not reused: its messages describe a calendar-to-band mapping a renewal file does not have. |
| `provenance.method` | non-empty str | what model, fitted how |
| `provenance.data_window` | non-empty str | the data the fit used |
| `provenance.source` | non-empty str | the published series, by name |
| `provenance.producer` | non-empty str | who or what wrote the file |
| `provenance.validation.text` | non-empty str | the validation record, free text |
| `provenance.validation.metrics` | optional `{str: finite number}` | the structured block |
| `paths` | list of N ≥ 2 rows | each row holds exactly K finite numbers ≥ 0 (booleans refused): decimal rates as quoted. Rows are equally weighted and drawn with replacement. To weight a row, repeat it; a weights field is an unknown field. |

**Grid against the config** (§0.1 item 4).
- Every row covers every renewal inside the amortization of each reading option (R16). A rate
  carried forward would extend the model with a figure the engine chose.
- A grid year that no reading option reaches inside its amortization is refused (R17), by the
  ladder's surplus rule (`config._mortgage_renewal`). So K is exactly the largest n_o.
- A column past the horizon but inside an amortization is read by nothing, and the `renewals:`
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
5` and `renewal_rates: {path: m/two_paths.json}`. Its 20-year horizon and 25-year amortization
price the renewals in years 6, 11 and 16. Column 4 (year 21) is required by R16 and priced by
nothing.

## 3. The config surface

```yaml
renewal_rates:
  path: rate_paths.json        # relative to the working directory, as market_scenario.path is
house:
  mortgage_renewal_years: 5    # required beside the file; mortgage_renewal_rates is refused
sources:
  renewal_rates.path: user     # the only class it takes (R20)
```

- `config._TOP_LEVEL_KEYS` gains `renewal_rates`, `config._SECTION_KEYS["renewal_rates"]` is
  `{"path"}`, and `input_schema._NOTES` gains the section (§8, commit 3).
- The file is loaded in `config._build_spec`, not at the CLI edge as the prior is:
  `compute_deterministic` prices the central row, and `load_config_dict` is the one path that
  every sweep point, break-even probe and reversal probe re-enters.
- A new module, `src/hde/rate_paths.py`, mirrors `market_scenario.py` and returns a
  `LoadedRatePaths`: sha256, quoted and effective rows, the central index, the priced columns
  and the provenance block. `ComparisonSpec.renewal_rate_paths: Optional[LoadedRatePaths] =
  None` must be a dataclass field, because `decomposition_run._spec_at` copies the spec with
  `dataclasses.replace`.
- A *reading option* is a condo or house that is not `all_cash` and has a full mortgage block.
  Its `mortgage_renewal_rates_quoted` and `mortgage_renewal_rates` hold the first n_o columns of
  the CENTRAL ROW, so every deterministic consumer reads it unchanged: `renewal_segments_for`,
  `_annual_costs_for_option`, the story curves and reversal admission.
- `sources:`: `renewal_rates.path` takes `user` only (R20 refuses `assistant`, R18 refuses
  `anchor:`), and undeclared it is `unattributed`. The block is never removed from the data
  before `build_source_echo` runs: `decomposition_run._given` reads the echo, and a width the
  echo never saw prints an empty "sized by".
- `sources.uncertainty_inputs`, `config.single_path_run` and `config.dispersion_sources` (owned
  side) all gain the file, together, under the existing mirror test (`sources.py`, the comment
  above `_SIM_VOLS`). `single_path_run` keeps the prior's field rule until E13's measured
  predicate replaces them all at once.
- **Engine remedy text never names the file key** (§0.1 item 12). The renewal-not-modelled
  remedies, the one-sided-uncertainty fix lists (config.py:836–846) and the message of the
  refusal at config.py:1636 stay byte-identical. `dispersion_sources` names the file only in
  its list of what carries spread.

**Refusals.** R1 to R18 and R20 are `ConfigValidationError` raised at load. Each names its key,
row, column or year.

| # | Refused | Message (figures in braces) |
|---|---|---|
| R1 | no file | `renewal_rates.path: no file at '{path}'` |
| R2 | not JSON, or `NaN`/`Infinity` | `'{path}' is not valid JSON: {error}` |
| R3 | unknown field at any level, or a missing required one | `'{path}': unknown field(s) {names} (exact allowlist)` / `missing field(s) {names}` |
| R4 | wrong schema or version | `'{path}' is {schema} version {v}; this engine reads hde.renewal_rate_paths version 1` |
| R5 | an empty provenance string, or a non-finite or non-number metric | `'{path}': provenance.{field} must be a non-empty string — the read-back prints it as the file's own words` |
| R6 | `compounding` | `'{path}': compounding {value!r} — must be semi_annual or effective_annual` |
| R7 | grid | `'{path}': renewal_years {given} for term_years {T} must be {expected} — column k is the rate at the k-th renewal, simulation year k·{T}+1; the opening term is the option's own mortgage_rate` |
| R8 | `as_of` present and not an ISO date | `'{path}': as_of {value!r} is not an ISO date (YYYY-MM-DD)` |
| R9 | row shape or value | `'{path}': paths[{i}] has {n} rates and renewal_years has {K}` / `paths[{i}][{k}] = {v!r}: a rate is a finite number >= 0` |
| R10 | N < 2 | `'{path}' has 1 row: a distribution needs two or more` |
| R11 | mixed terms | `{opt}.mortgage_renewal_years is {t}; '{path}' quotes {T}-year rates` |
| R12 | zero spread, per reading option that prices a renewal inside the horizon | `every row of '{path}' prices {opt}'s renewals in years {years} at the same rates: no future differs` |
| R13 | ladder beside the file | `{opt}.mortgage_renewal_rates is set beside renewal_rates.path — one market, two sources for its renewal rate` |
| R14 | financed, no term | `{opt} has a mortgage and no mortgage_renewal_years; renewal_rates.path quotes {T}-year rates` |
| R15 | nothing priced, with a reading option | `no reading option renews inside the {H}-year horizon (first renewal: year {T+1})` |
| R15 | nothing priced, with no reading option | `'{path}': no option carries a mortgage, so nothing reads a renewal rate`, checked first: with no mortgage there is no renewal year for the message above to name |
| R16 | grid too short | `'{path}' ends at year {y}; {opt} renews in year {r} inside its {A}-year amortization — every renewal needs a column, and the engine carries no rate forward` |
| R17 | grid past every amortization | `'{path}' renewal_years {y}: past every reading option's last renewal ({opt}: year {r})` |
| R18 | `anchor:` on `renewal_rates.path` | the existing `_anchor_declaration` refusal: `… an anchor sources a number, not str` (measured on `market_scenario.path`, §12) |
| R19 | bytes changed within one process | `'{path}' changed since this process first read it: sha256 {first[:12]}… first, {now[:12]}… now` |
| R20 | `assistant` on `renewal_rates.path` | `sources: 'renewal_rates.path' declared assistant — the path file is the user's own work and an assistant never proposes, invents or builds one; declare it user when the user supplied it` |

- R11 also covers two reading options with different terms. The ladder's refusal of
  `mortgage_renewal_years` without `mortgage_renewal_rates` (config.py:1636) is lifted only
  when the file is present.
- R18 needs no new code, and `_UNANCHORED_KEYS` (`sources.py:460`, the landed ladder fix) is
  not extended, because its message describes a stated ladder. On a file run the ladder key
  cannot be targeted: R13 refuses it, and `sources:` refuses a key the config does not set
  (measured). So the file does not reopen that fix (ruling 11).
- **R19.** Every load re-reads the bytes and pins the first sha256 per resolved path, in a
  module-level dict that `rate_paths.reset_pins()` clears for tests; parsing is cached by sha.
  `RatePathsChanged` subclasses neither `ConfigValidationError` nor `ValueError`, so no
  per-point capture (`break_even.py:507,713,906,1439,1842`, `sweep.py:205,213,412`,
  `unpriced.py:188`) folds it into one row's reason. `main()` catches it once, around
  everything after the first load, and exits 1 with `Error: {message}`, so every re-entry is
  covered by construction. A stand-in exception of that kind, raised from the second load,
  escapes `main()` today on `--sweep` (cli.py:421), on `--break-even` (cli.py:446 catches
  `ValueError` only), on `--decompose` and on `--read-back` with an income block (measured,
  §12). The read-back's escape is `unpriced_warnings` (unpriced.py:187), called at cli.py:367
  on the main run path outside any `try`, so by the code a plain run with an income block
  escapes too. That case is unmeasured, and §9 row 12 pins it. "This process", not "this run": a library session is one process too.
- Under `--no-monte-carlo`, `RATES_WITHOUT_MONTE_CARLO`, the sibling of
  `cli.PRIOR_WITHOUT_MONTE_CARLO`, warns: `renewal_rates draws only in Monte Carlo — this run
  prices the central row alone`.

## 4. The draw, the payment re-solve, affordability

- **Channel 8.** `decomposition.CHANNELS` gains `Channel(id=8, key="rates", label="the
  renewal rates", sizing_keys=("renewal_rates.path",))`, and `decomposition.channel()` looks up
  by id; it indexes by position today, which breaks once ids skip 7.
  `decomposition_run._CHANNEL_OPTIONS[8] = ("condo", "house")`. Income stays 7 and
  unfreezable.
  - `run_monte_carlo`'s id guard (`0 <= c <= 6`, monte_carlo.py:1435) and its legacy-binding
    guard (`frozenset(range(7))`, :1451) derive their ids from `decomposition.CHANNELS`; they
    cannot import `decomposition_run.ALL_CHANNEL_IDS` at module level, because
    `decomposition_run` imports `monte_carlo`. Their messages, and `_AddressedBinding`'s, gain
    8.
  - A legacy-binding `freeze=range(7)` is then refused on every run, including one with no
    file, where it was safe. That over-wide case is accepted: no source caller makes the call
    (every `freeze=` in `src/hde` goes through `decomposition_run._run` and
    `addressed_streams`), and the precise guard would have to read the config to decide whether
    channel 8 draws, which is the predicted-liveness class (which-risk §0.1 item 39).
- **The draw.** `WorldDraws.rate_rows` is N with a file and 0 without one, and
  `PathWorld.rate_row` is `Optional[int]`. LAST in `_draw_path_world`: `if draws.rate_rows and
  not b.frozen_at(8): rate_row = int(b.gen(8).integers(0, draws.rate_rows))`. A frozen channel 8
  sets `rate_rows = 0`, so the path prices the option's own ladder, the central row (§5).
  `Generator.integers(0, 1)` does not advance the generator, one more reason R10 refuses N = 1.
- **The frozen rebuild keeps the rows.** When any channel is frozen, `run_monte_carlo`
  rebuilds `WorldDraws` field by field (monte_carlo.py:1541–1545), and the rebuild must carry
  `rate_rows=0 if 8 in frozen else world_draws.rate_rows`. Leaving it out is a live mutant: on
  `m/hvr_example.yaml` at 2,000 paths, freezing channel 4 alone moves the level by $90 in the
  prototype and by −$71,683 in the mutant, and for each c in 0 to 6 `freeze=(c,)` records the
  unfrozen run's rows in the prototype and different rows in the mutant.
- **Per-option columns** (§0.1 item 4). Option o reads the first n_o columns of a row, for the
  central row and on every path. The prototype gave every option all K: on `m/two_opts.yaml`
  (condo amortized over 10 years, 1 renewal; house over 25, 4) with `m/semi.json`, the `condo
  renewals:` line printed four quoted rates, 4.00%, 5.00%, 6.00% and 7.00%, for its one
  renewal. An option with n_o = 0 takes the empty ladder, which prices as a typed one does
  (`m/condo5.yaml`'s condo, amortized over its 5-year term: the same `total_pv` with `[]` as
  with `[0.05]`).
- **Payment re-solve.** `renewal_args_for(params, rates=None)` gains the override, and the two
  financing call sites (monte_carlo.py:952, :1070) pass the path's effective row cut to n_o
  columns, or None for the option's own ladder. `pv.renewal_schedule` re-amortizes the remaining
  balance over the remaining amortization at each renewal, so there is no new financial
  arithmetic. Both options read the same row on a path, because the rate is the market's.
- **Affordability per path** (the events lane's C12 class). `_annual_costs_for_option` gains
  `renewal_rates=None` and threads it into `renewal_segments_for`, and
  `run_monte_carlo._path_costs` keys its cache on `(option, reset_year, fired, rate_row)`. On
  `m/hvr_example.yaml` plus `income: {annual_income: 150000, income_growth_rate: 0.0,
  affordability_threshold: 0.32}` (prototype), the central row's peak ratio is 28.10% and row
  1's is 38.55%, there is no deterministic house breach, and P(house exceeds) is 0.508, the
  share of paths that drew row 1.
- **Recorded rows.** `ComparisonMonteCarloResult.renewal_rate_rows: Optional[np.ndarray] =
  None` holds each path's row index. `mc_to_dict` never emits it: index arrays, like PV arrays,
  never cross a surface boundary.
- **Independence (ruling 5).** Its one statement is §7's exact string. Whole rows keep the
  producer's serial and term structure. A
  jointly fitted file would make one primitive feed channels 0 and 8, which the partition would
  have to merge (which-risk §3.1); that is board item 13's.
- **Legacy binding.** Under `streams=None` every channel shares one generator (`_OneStream`),
  so on a file run every draw after channel 8's moves in the stream. The decomposition's rows
  measure channel 8; they are never a before-and-after difference.

## 5. The central case (ruling 1)

- **The rule.** Let P be the largest number of renewals that any reading option prices inside
  the horizon (`renewals_priced_inside`). For each column k ≤ P the median of the N quoted
  rates is taken (the mean of the two middle values when N is even). Each row's squared
  Euclidean distance to that median path is taken over columns 1..P, and the central row is the
  FIRST row at the minimum. Both steps run in exact rational arithmetic (`fractions.Fraction`)
  on the parsed floats (§0.1 item 1), at a cost of N·P rational operations once per load.
- **What it depends on** (§0.1 item 8). The central row depends on the priced renewals, so on
  the horizon. At any config the file loads against, an amortization cannot move it (the second
  bullet below).
  - On `m/hvr_ar1.yaml` (2,000 rows) through `sweep.load_at`, it is row 251 at 6 and 10 years
    (P = 1), 1153 at 11 and 15 (P = 2), and 1003 at 16 and 20 (P = 3).
  - R16 and R17 make K the largest n_o at any config the file loads against, so there P =
    min(K, ⌊(H − 1)/T⌋) for horizon H. A `<opt>.mortgage_term_years` point that would change P
    changes the largest n_o, and R16 or R17 refuses it, which `run_sweep` records as that
    point's error row (sweep.py:412). The prototype has neither refusal and gives row 1153 at
    term 15 and 251 at term 10.
  - On a file run every sweep point's line names its central row, whatever the key. A
    break-even whose bracketing values price different central rows says so: `… the central
    row switches here: row {i} at {lo}, row {j} at {hi}`.
- **Injection.** The central row's first n_o columns become option o's ladder (§3).
- **Measured on the counterexample** (main, typed ladders on `examples/mortgage_house_vs_rent.yaml`,
  5-year term): the per-year mean path (5%) prices the house at **$363,941.75**, row 0 (2%) at
  **$296,909.29**, and row 1 (8%) at **$438,752.15**.
- **On the futures** (prototype, `m/hvr_example.yaml`, 5,000 paths): the 2,460 paths that draw
  row 0 price the house from $277,674.54 to $318,418.37, and the 2,540 that draw row 1 from
  $419,293.02 to $467,443.65. No future prices it between $318,418.37 and $419,293.02, the
  interval that holds the mean path's $363,941.75: pricing the mean would price a house no
  future reaches, which is E10's class.
- **The tie.** Rows 0 and 1 are equidistant from the median, so the lowest index wins: the
  central case is row 0's $296,909.29, bit-identical to the same config with `[0.02, 0.02, 0.02,
  0.02]` typed as the ladder (296909.29108796926 both ways). The central case is always one
  future's path.
- **Level register.** Channel 8's level row is the margin shift with channel 8 frozen at the
  central row. On the counterexample: **+$71,772 (± $1,586)**, and with channel 8 frozen
  P(house cheapest) is 1.00.
- **All-frozen identity.** With channel 8 frozen beside channels 0 to 6, every path prices the
  central case: on the file run, `all_frozen_path_spread` is 0.0 and `all_frozen_deviation` is
  5.82e-11.

## 6. `--decompose`

- **Spread row.** One row, "the renewal rates", for channel 8, sized by
  `renewal_rates.path='{path}' [{tag}]`. Whether it is live is measured by `_DrawRecorder` and
  `_liveness`, never read off the config (which-risk §0.1 item 39). Counterexample (prototype):
  alone **0.99 [0.96, 1.01]**, with interaction 0.99 [0.96, 1.02], flips 0.9% [0.7, 1.2]. A
  channel 8 that drew and moved nothing gets the existing `_dead_draw_rows` row. The work
  ceiling still clears the default: with nine streams drawing, `planned_evaluations(10000, 9,
  2000)` is 130,000 against `EVALUATION_CEILING` 250,000 (118,000 at eight today).
- **Level row.** As in §5.
- **Reversal register, clause (b′).** For the candidate key x (here `<opt>.mortgage_rate`),
  probe value x₁, stated value x₀ and path rows ρᵢ:
  - Fin(ρ; x) is the named option's `_financing_pv` summed at `value_N = 0`, with the option's
    n_o columns of ρ's effective rates. With c the central row, Gᵢ(x) = Fin(ρᵢ; x) − Fin(c; x).
    Δᵢ is the per-path PV delta, and dᵢ = Δᵢ − [Gᵢ(x₁) − Gᵢ(x₀)].
  - **Premise** (§0.1 item 7). The gate first compares the `renewal_rate_rows` the stated and
    the probe run recorded, and any difference refuses the licence (the key goes not_exact),
    because dᵢ subtracts a per-row term. On every file run measured, the two runs drew the same
    row on every path.
  - **(b′):** `max |dᵢ − mean d| ≤ 1e-9 · sd(PV)`. Clause (a), that the other options are
    bit-identical, is unchanged.
  - Without a file every path prices the central ladder, so Gᵢ is 0.0 exactly, dᵢ = Δᵢ, and
    (b′) IS (b), bit for bit.
  - The free curve at v shifts path i by `[det(v) − det(x₀)] + [Gᵢ(v) − Gᵢ(x₀)]` for the named
    option, and by today's shift for the others; without a file the added term is 0.0. Fin is
    computed once per distinct row per value.

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
  leg, Fin(ρᵢ; x₁) − Fin(ρᵢ; x₀), licenses the same keys but is not (b) without a file: on the
  fixture's `house.mortgage_rate` it gives 9.572e-16 against (b)'s 9.525e-16.

  **Confirmation by full re-simulation** (`m/hvr_ar1.yaml`, 5,000 paths). P(house cheapest) on
  the (b′) curve equals a full re-simulation at 6% (0.9992) and at 7.5% (0.9792). At 7.5% the
  constant-shift curve gives 0.9844, so a curve licensed by (b) would have been 0.52 points
  wrong. Every printed boundary keeps today's confirming re-simulation (`_confirmed_boundaries`).

  **What a file run does not say:** `<opt>.mortgage_renewal_rates` is refused beside the file,
  so the register has no renewal-LEVEL axis. Where the renewal level flips the verdict is the
  ladder run's answer (on the fixture's ladder, the central winner changes at 1.6052%).
- **"No draw touches it" rows (ruling 6).** `zeros.append(_stated_path_zero(key))`
  (break_even.py:2339) runs on the exact branch only; it moves above the gate's branch, so the
  licensed and the not_exact row both emit it. Measured (prototype, without (b′)):
  `house.mortgage_rate` went not_exact on all four fields and the NO ROW list was empty, though
  no draw touches the contract rate. With no file both `stated_path` rows print, as today; with
  a live channel 8 the renewal rate is in the spread and the level; a channel 8 that drew and is
  dead is named by `_dead_draw_rows`. v1 builds no drop branch for the ladder's row:
  `reversal_candidates` reads the raw config, which cannot state the ladder on a file run (R13),
  and on a run with no file channel 8 never draws.
- **JSON and homes.** `decomposition.spread.rows[]` and `level.rows[]` carry `channel_id` 8,
  `channel` `"rates"` and `label` `"the renewal rates"`, and no `key` field (measured on the
  opt-in fixture's `--decompose --json`). `docs/reference/API_CONTRACT.md` has no channel
  table: its one home for the ids is the streams sentence of § The `decomposition` block,
  which lists `6 portfolio, 8 rates`. Which-risk §3.1's table gains the row.

## 7. The read-back line

One line in `serialization.format_assumptions`, after `demographic prior:`, holding the figures
of ruling 10 and nothing else:

```
renewal rate paths: {path} · sha256 {sha[:12]}… · central row {i} of {N:,} (nearest the per-renewal median{tie}): {r_1:.2%}, …, {r_P:.2%} as quoted ({compounding}) · 5–95% by renewal: year {y_1} {p5_1:.2%}–{p95_1:.2%}, …, year {y_P} {p5_P:.2%}–{p95_P:.2%} · method: {method} · data window: {data_window} · validation: {validation.text} · drawn independently of every other draw (the discount rate is fixed)
```

- `{tie}` is `, tied with {k} other row(s), lowest index` when the minimum is shared, and empty
  otherwise. `{compounding}` is `semi-annual` or `effective annual`.
- The band is `numpy.percentile(column, [5, 95])` (linear) over the N quoted rows, for the
  priced columns only.
- The method, window and validation are printed verbatim: the engine checks that they are
  present, not that they are true. Whose file it is prints in the `sources` echo lines.

Filled with the figures measured on `m/hvr_example.yaml` (the prototype does not print it):

```
renewal rate paths: m/two_paths.json · sha256 b3827bb92169… · central row 0 of 2 (nearest the per-renewal median, tied with 1 other row, lowest index): 2.00%, 2.00%, 2.00% as quoted (effective annual) · 5–95% by renewal: year 6 2.30%–7.70%, year 11 2.30%–7.70%, year 16 2.30%–7.70% · method: synthetic, not a calibration: two hand-set paths · data window: none · validation: none: an example, not a model · drawn independently of every other draw (the discount rate is fixed)
```

**The read-back section.** `_read_back_sections` (serialization.py:1559–1615) is a fixed list
of labelled sections with no entry for this line, so `assumptions.read_back`, `--read-back` and
`--read-back short` would all drop it. It gains `("renewal rate paths", <the echo's lines with
that prefix>, [])` directly after `"renewals"` (:1589). The short block carries nothing for it,
as for `renewals`, so its closing line names "renewal rate paths" among what it left out. The
`demographic prior:` line has the same gap: on `examples/showcase_demographic_prior.yaml` it
prints once on stdout and is absent from `--read-back`, `--read-back short` and
`assumptions.read_back` (out of scope, §10).

**What changes on a file run.**
- `renewal_source_clause` ("a stated scenario, not a forecast — the engine anchors no renewal
  rate, and the read-back cannot tell whose figure it is") becomes `central row {i} of {path}`
  for an option that reads a column, and is absent for one that reads none (`m/condo5.yaml`'s
  condo), because no row prices anything for it.
- `assumptions.mortgage_renewals[].compounding` prints `opt.mortgage_rate_compounding`
  (serialization.py:582), which would label a semi-annual file's quotes with an
  effective-annual contract's convention. On a file run it prints the file's `compounding`.
- The ladder-warning loop (config.py:874–985) is gated off whole (§0.1 item 13). In the
  prototype three of its branches fire on file runs, each naming a key the config cannot set:
  "opens at" on `m/hvr_opens_at.yaml`, whose central row opens at the contract rate 4.40%;
  "mortgage_renewal_rates are inert" on `m/condo5.yaml`'s condo; and the bias warning ("the
  stated renewal path prices the mortgage $46,305 below its contract rate …") on
  `m/hvr_example.yaml`.

**The rendered-output pin.** On the stdout and stderr of `m/hvr_opens_at.yaml`,
`m/condo5.yaml` and `m/hvr_example.yaml`, rebuilt as fixtures, none of `mortgage_renewal_rates`,
`opens at`, `are inert`, `the stated renewal path` or `a stated scenario` appears, and every
remaining `stated` sits inside the sources echo's `user-stated:` label. The bare word cannot be
the pin, because that label carries it on any run with a `sources:` block. If the gated output
carries another legitimate `stated`, the pin names that line, measured, and keeps the five
phrases. In the prototype the lines carrying `mortgage_renewal_rates` or `stated` number 3 on
stdout and 1 on stderr, 6 and 2, and 3 and 1.

**`--json`.** `assumptions.renewal_rate_paths` carries `path`, `file_sha256`,
`schema_version`, `term_years`, `renewal_years`, `priced_years`, `compounding`, `as_of` (null
when absent), `rows`, `central_index`, `central_rates_quoted`, `tied_rows`, `band` as `{year:
[p5, p95]}`, `provenance` verbatim, and `independent_of_channels`: `[c.id for c in CHANNELS if
c.id != 8]`, which is `[0, 1, 2, 3, 4, 5, 6]` in the prototype.

## 8. Back-compatibility and the commit order

**With no file**, no draw is taken (the draw is gated); `rate_row` is None, so
`renewal_args_for(opt)` makes exactly today's call; `_path_costs` takes today's key path;
`renewal_rate_rows` is None and never serialized; (b′) is (b) bit for bit; and the registers
iterate only the streams that drew and the channels that are live. One message changes, on a
config the loader refuses either way (§0.1 item 9): a top-level `renewal_rate` printed `unknown
key 'renewal_rate'` on main and prints `unknown key 'renewal_rate' — did you mean
'renewal_rates'?` in the prototype.

Measured, a2d1a7d against the prototype: `--json` stdout and stderr are byte-identical on all 7
examples and the fixture, and so are the fixture's `--decompose` text, stderr and `--json`. The
flagship fixture stays untouched, because no roster test forces a change. The suite gave 1
failed / 2,438 passed on a2d1a7d (the merge-marker test, which needs `git` and fails in an
archive) and 12 / 2,427 on the prototype: that test, seven pins of the seven-channel table (two
in `test_channel_streams.py`, four in `test_decomposition_contract.py`, one in
`test_decomposition_contract_doc.py`) and four `test_input_schema.py` tests, because the
prototype has no `_NOTES` for the section. None is a roster test of the flagship fixture,
`uncertainty_surface_mc_golden.json` passed, and no numeric golden moved.

**Commit order.** The suite is green at every commit, and commit 1's goldens are unchanged
through commit 7.

1. `test`: the opted-out goldens: for each of the 7 examples and the fixture, the `--json`
   document itself, produced in-process with the run date pinned and `engine_version`
   (top-level, `"0.4.0"`) masked, plus the fixture's `--decompose --json` document. The date is
   pinned because the fixture's document differs between run dates 2026-10-01 and 2028-06-01.
   No bare sha256 of a whole document is stored: a version bump would move every hash and say
   nothing about which field moved. Captured at a2d1a7d, and green on main.
2. `refactor`: `channel()` looks up by id, and the two freeze guards derive their ids from
   `CHANNELS`. Still 7 channels, so no figure moves. The pointer test's pinned body line (`    if
   not 0 <= channel_id < len(CHANNELS):`) is updated here; measured on that change alone, it is
   the only one of the three table-pin files' 255 tests that fails.
3. `feat(rate_paths)`: the loader, R1 to R20, the config surface, the source and uncertainty
   mirror, the new opt-in fixture (§9), and the schema text:
   - `_NOTES["top"]["renewal_rates"]` carries ruling 9: "a renewal-rate path file the USER
     supplies (schema hde.renewal_rate_paths), written by a model fitted outside the engine; an
     assistant never proposes, invents or builds one". `_NOTES["renewal_rates"]["path"]` says
     `sources:` declares it `user`.
   - The `mortgage_renewal_years` note's `required_if` (input_schema.py:157 and its house twin
     at :351), "requires mortgage_renewal_rates — the two renewal keys travel together", is
     false on a file run. It gains "— or a renewal_rates.path file, which supplies the rates and
     refuses mortgage_renewal_rates", keeping the "travel together" that test_input_schema.py:117
     pins.
   - Two `TestRequiredFlagsAreTrue` tests key on `KNOWN_GOOD`, whose options are all cash, so
     R15 would refuse a file there; they take the new fixture as the `renewal_rates` section's
     known-good config. With the `_NOTES` text added, these two are the only failures in
     `test_input_schema.py` and `test_skill_contract.py` (2 failed, 32 passed, measured).
4. `feat(monte_carlo)`: channel 8, the draw, the frozen rebuild, the per-option columns, the
   per-path re-solve and affordability, the central row and the identity pins, plus:
   - the other six table pins, rewritten to derive from `CHANNELS`;
   - the stream hard-codes, derived from `decomposition_run.STREAM_IDS`:
     `tests/decomposition_oracles.py:34` (`STREAMS = tuple(range(8))`), the `range(8)` seed
     dicts at `test_decomposition_run.py:1073`, `test_decomposition_contract_doc.py:2558` and
     `test_decomposition_sentences.py:432`, and the undrawn-stream set at
     `test_decomposition_liveness.py:219`. The asserts at `test_decomposition_run.py:277` and
     :841 state what the no-file fixture drew, which stays streams 0 to 7;
   - the stale "seven": monte_carlo.py:56, :1402, :1448 and :1458 (the legacy-binding refusal's
     message), decomposition_run.py:127, :139 and :143–144, decomposition_math.py:287,
     test_channel_streams.py:272 and API_CONTRACT.md:251. `decomposition_households.py:162` and
     :463 describe fixtures whose live channels stay seven, and `sweep.py:220`'s `range(8)`
     counts bracket doublings;
   - the `range(7)` asserts at `test_decomposition_liveness.py:470`,
     `test_decomposition_run.py:276` and `test_decomposition_contract_doc.py:436` and :624
     state what no-file fixtures make live, so they stay, like :277 and :841. The builder
     confirms each on the built tree, since row 4's mutation names literal `range(7)`.
5. `feat(break_even)`: (b′) with its premise check and free curve, the zero rows on both gate
   branches, and the row-switch note.
6. `feat(serialization)`: the read-back line and its section, §7's file-run changes (the
   ladder-warning gate included), the central row on each sweep point's line, the `--json`
   block, and the rows in API_CONTRACT and which-risk §3.1.
7. `docs(skill)`: exactly these five edits (§0.1 item 14).
   - `references/gates.md` §8, the one home, after "read back the engine's `renewals:` line.":
     "A `renewal_rates` path file prices it as a distribution instead: read back the `renewal
     rate paths:` line, whose model and validation are the file's own words. Use a file only
     when the user supplies one; never propose, invent or build one."
   - `references/answer-template.md` §8, the one scope clause: "as ONE scenario with no
     distribution around it" gains "when the path is a ladder (a path file: gates §8)".
   - `references/gates.md:141`: "with every vol at 0" gains "and no `renewal_rates` file".
   - `references/translation.md:22`, two scope clauses. "an `anchor:` declaration on the
     ladder is refused at load" gains " — or, instead of a ladder, a path file the user
     supplied (gates §8)". Placed there, after the whole ladder clause, the ladder's "yours to
     label as an estimate" cannot be read as covering a file. The last cell's "prices it as ONE
     stated scenario" gains " (a ladder; a path file: gates §8)".
   - `references/quick-sense.md:73`: "named as one stated scenario, when it is" gains " a
     ladder; a path file: gates §8", inside the existing parenthesis.
   - On a copy with the first four edits and commit 3's schema text, `test_skill_contract.py`
     passes (17), and SKILL.md is untouched at 2,597 words (measured). The builder re-runs it
     with all five.

## 9. Tests: the classes this invites, each pinned and mutated both ways

Each refusal is pinned with the legal config one step away (the events lane's §3 rule), and each
pin names the mutation that must fail it.

| # | Class | Pin | Mutation that must fail it |
|---|---|---|---|
| 1 | One world | A typed ladder equal to the central row reproduces `compute_deterministic` bit for bit; the all-frozen identity holds on a file run (0.0 spread, 5.82e-11). | A per-year-mean centre ($363,941.75 ≠ $296,909.29); a float `argmin` (row 1 on the tie); "row 0 always", on the new fixture, whose central row is not 0 |
| 2 | Predicted liveness | R10, R12 and R15 refuse at load. Channel 8's row exists exactly when `_DrawRecorder` saw stream 8 advance. One `integers(0, N)` per path on stream 8, counted by a wrapper on its generator or checked against a fresh same-seed generator advanced once per path; a before-and-after state check cannot kill a second draw, because the PCG state is the same after one and two `integers(0, 2)` calls and only `has_uint32` differs (measured). | A second draw per path; a liveness flag read off `spec.renewal_rate_paths` |
| 3 | Stream order and opt-out | Commit 1's goldens and `uncertainty_surface_mc_golden.json`. Under the legacy binding, path 0's world draws on a file run equal the same config's without the file. | Moving the draw before the inflation loop |
| 4 | Channel-count hard-codes | `freeze=ALL_CHANNEL_IDS` is allowed on the legacy binding; `freeze=range(7)` is refused as partial; `channel(8)` resolves; `channel(7)` and `channel(9)` raise. | Any surviving positional `CHANNELS[i]`, literal `range(7)`, or `range(8)` of commit 4's list |
| 5 | One market | Two reading options draw the same row on every path. | A per-option draw |
| 6 | Per-option columns | On `m/two_opts.yaml`'s shape, each option's ladder, per-path override and `renewals:` line carry n_o rates: 1 for the condo, 4 for the house. | Every option given all K columns (the prototype printed four for the condo) |
| 7 | Per-path affordability (C12) | P(house exceeds) 0.508 = the share of row-1 paths, on §4's config (its income block holds `income_growth_rate: 0.0`; without it the peaks are 27.18% and 29.84% and P is 0.0, which the mutation also gives). | Central costs on every path: P = 0.0 (measured) |
| 8 | Freeze isolation | On the new fixture, for each c in 0 to 6, `freeze=(c,)` records the unfrozen run's rate row on every path. | `rate_rows` left out of the frozen rebuild (measured: different rows for every c; channel 4's level −$71,683 against $90) |
| 9 | (b′) | It licenses `mortgage_rate` on a file run (residual ≤ 1e-9·sd) and matches re-simulation (§6). With no file, (b′) and (b) are bit-identical on the fixture's two licensed keys. A probe whose recorded rows differ is refused. **First pin the builder lands:** the register's own output under (b′), end to end on the new fixture, which was not measured here. | Deleted: not_exact (7.00e-02, 1.76e-01). Widened to `value_growth_rate`: refuses (1.79e-01). A gate that refuses everything fails the no-file pin. A (b′) without the central row's leg fails the no-file bit identity (9.572e-16 against 9.525e-16). The premise check deleted. |
| 10 | Vanishing zero row | The contract rate's row prints on both gate branches. | Restoring line 2339's placement (the prototype lost the row) |
| 11 | Rendered output | §7's pin on the three configs. On a semi-annual file beside an effective-annual contract, `assumptions.mortgage_renewals[].compounding` is `semi_annual`. | The loop's gate deleted (the prototype's hits, §7) or narrowed to the bias branch; the source clause restored |
| 12 | File integrity | Bytes rewritten between two loads raise `RatePathsChanged`. `--sweep`, `--break-even`, `--decompose`, a plain run with an income block and `--read-back` with one each exit 1 with one `Error: '…' changed since this process first read it` line and no `Traceback`. `rate_paths.reset_pins()` runs before each test. The printed sha is the sha of the bytes priced. | The catch in `main()` removed (today's escape, measured); `RatePathsChanged` made a `ValueError`, which a sweep row swallows |
| 13 | Refusals both ways | Every R-row against its neighbour: N = 2 loads; one varying column loads; at a 25-year amortization, 5-year term and 20-year horizon, `[6, 11, 16, 21]` loads, `[6, 11, 16]` refuses (R16) and `[1, 6, 11, 16]` refuses (R7); a condo whose amortization ends before a column the house reads loads; a file with no `as_of` loads. | Each refusal deleted, and each widened onto its neighbour; R16 measured against the horizon instead of the amortization |
| 14 | Sources and anchors | `user` loads; `assistant` refuses (R20); `anchor:<a registry name>` refuses (R18). | R20 deleted; R20 widened to `user` |
| 15 | Read-back | Every figure on §7's line is recomputed independently: the exact central row, linear percentiles, the sha of the bytes. On the rendered output the line appears once in `--read-back` and in `assumptions.read_back`, right after the `renewals:` lines, and `--read-back short`'s closing line names it. A no-file read-back is unchanged. | Any template field read from a second source; the section left out (today's gap) |
| 16 | Row switch | A `--sweep years` across a P boundary names each point's central row (251, 1153, 1003 on `m/hvr_ar1.yaml`; a point with H ≤ T is R15's refusal); a break-even bracketing a switch says so. | The central row computed once and reused at every point |

**The new fixture.** `tests/fixtures/renewal_rate_paths.yaml` (house against rent, a 5-year
term, a horizon that leaves the last column unpriced) and
`tests/fixtures/renewal_rate_paths_synthetic.json`, committed as data. Its `provenance.method`
begins "synthetic, not a calibration", and its recipe is described there in words; no script
ships (ruling 8). Its rows are chosen so that the central row is not row 0, the compounding is
semi-annual, and the reversal register reaches boundaries. The configs of §7's rendered-output
pin and of `m/two_opts.yaml`'s shape are committed beside it as test data.

## 10. Out of scope

- **`rate_shift`** (ruling 2). Without it, a file run has no renewal-level crossing (§6).
- **Correlation with any other channel** (ruling 5, board item 13). A joint fit merges
  channels in the partition (§4).
- **A producer or fitting script, or any calibrated file** (ruling 8).
- **The flagship fixture** (ruling 7). See §8 for the roster check.
- **Row weights, several terms in one file, variable- or trigger-rate products, prepayment
  penalties, and the qualifying-rate test at renewal.**
- **A calendar check on `as_of`.** The config states no purchase date to check it against.
- **The `demographic prior:` line's absence from the read-back sections** (§7).

## 11. Open questions

Neither of these can be settled by measuring inside the engine.

1. **Which way does independence bias the channel's share?** It depends on a sign the data
   does not settle (§12). Over the same five-year window, the change in the CMHC five-year rate
   (Statistics Canada v733833) has moved WITH the log change in house prices: +0.21 to +0.68
   across four price series (the NHPI for Montréal, nominal and CPI-deflated, and the Dallas
   Fed's international index for Canada, nominal and real), on about 6 to 9 independent
   windows. That co-movement would partly hedge a buyer, so independence would overstate the
   combined channel. Against the price change over the FOLLOWING five years the sign is mixed
   (−0.26 to +0.41), and a one-year rate change against the following year's price change is
   negative since 1991 (−0.16 to −0.30), the sign under which independence would understate
   it. The engine cannot sign the covariance without a jointly fitted model, and that is board
   item 13's.

   > The authors acknowledge use of the dataset described in Mack and Martínez-García (2011).
   > Mack, A., and E. Martínez-García. 2011. "A Cross-Country Quarterly Database of Real House
   > Prices: A Methodological Note." Globalization and Monetary Policy Institute Working Paper
   > No. 99, Federal Reserve Bank of Dallas. The figures above were computed from the database
   > by 2026-10-02; the date it was consulted was not recorded.
2. **What is the smallest N a file needs?** Drawing with replacement means a 50-row file at
   10,000 paths is a 50-point distribution. The read-back prints N. Whether some N should be
   refused is a product rule, not a measurement.

## 12. Measurements

*Main* is a `git archive` of a2d1a7d (round 1) or of 1486fbc (marked r2). *Prototype* is the
same archive with the prototype patch applied, and *mutant* is the r2 prototype without the
`rate_rows=` line of the frozen `WorldDraws` rebuild. The patch, the mutant and the scripts are
not committed; r2's `m/` configs are the review's. Each is a delta on §2's two files:
- `m/hvr_opens_at.yaml`: `m/hvr_example.yaml` pointed at `m/opens_at.json`, which is
  `m/two_paths.json` with rows `[0.044, 0.05, 0.05, 0.05]`, `[0.03, 0.04, 0.04, 0.04]` and
  `[0.06, 0.06, 0.06, 0.06]`.
- `m/condo5.yaml`: `m/hvr_example.yaml` plus a condo (`initial_value` 400000, `down_payment`
  80000, `monthly_fee` 300, `mortgage_rate` 0.044 `effective_annual`, `mortgage_term_years` 5,
  `mortgage_renewal_years` 5, `purchase_costs` 5000, `value_growth_rate` 0.031, a 3000
  `property_tax` line escalating at 0.021).
- `m/two_opts.yaml`: `m/condo5.yaml` with the condo's `mortgage_term_years` 10, pointed at
  `m/semi.json`, which is `m/two_paths.json` with `compounding` `semi_annual` and rows `[0.03,
  0.04, 0.05, 0.06]`, `[0.05, 0.06, 0.07, 0.08]` and `[0.04, 0.05, 0.06, 0.07]`.

| Figure | Command |
|---|---|
| $296,909.29 / $438,752.15 / $363,941.75 (main) | `uv run python -c "import copy, yaml; from hde.config import load_config_dict as load; from hde.deterministic import compute_deterministic as det; raw = yaml.safe_load(open('examples/mortgage_house_vs_rent.yaml')); raw['house']['mortgage_renewal_years'] = 5; [print(r, round(det(load(dict(copy.deepcopy(raw), house=dict(raw['house'], mortgage_renewal_rates=[r] * 4)))).house.total_pv, 2)) for r in (0.02, 0.08, 0.05)]"` |
| float tie 0.0027000000000000006 against 0.0027, `argmin` 1; exact tie, first minimum 0 (main) | `uv run python -c "import numpy as np; from fractions import Fraction as F; rows = np.array([[0.02] * 3, [0.08] * 3]); d2 = ((rows - np.median(rows, axis=0)) ** 2).sum(axis=1); print(d2.tolist(), int(np.argmin(d2))); ex = [[F(x) for x in r] for r in rows.tolist()]; m = [(a + b) / 2 for a, b in zip(*ex)]; e2 = [sum((x - y) ** 2 for x, y in zip(r, m)) for r in ex]; print(e2[0] == e2[1], e2.index(min(e2)))"` |
| `integers(0, 1)` does not advance the generator (main) | `uv run python -c "import numpy as np; g = np.random.default_rng(1); s = g.bit_generator.state; g.integers(0, 1); print(g.bit_generator.state == s)"` |
| after one and after two `integers(0, 2)` calls the PCG state is identical, `has_uint32` is 1 then 0, and two calls differ from a fresh generator after one (main, r2) | `uv run python -c "import numpy as np; st = lambda g: g.bit_generator.state; g1 = np.random.default_rng(7); g1.integers(0, 2); g2 = np.random.default_rng(7); g2.integers(0, 2); g2.integers(0, 2); print(st(g1)['state'] == st(g2)['state'], st(g1)['has_uint32'], st(g2)['has_uint32'], st(g2) == st(g1))"` |
| R18: the anchor refusal on a path key (main) | `uv run python -c "import yaml; from hde.config import load_config_dict; raw = yaml.safe_load(open('tests/fixtures/uncertainty_surface.yaml')); raw['sources']['market_scenario.path'] = 'anchor:mortgage_rate.contracted_5y_uninsured'; load_config_dict(raw)"` |
| the fixture's `--json` depends on the run date (main) | `cli.main()` in-process with `datetime.date.today` patched to 2026-10-01 and then 2028-06-01; the two documents differ |
| `engine_version` is top-level `"0.4.0"` (main, r2) | `uv run hde examples/basic_config.yaml --json`, walked for every key containing `version` or `date` |
| byte identity, file opted out (main and prototype) | `uv run hde <config> --json`, stdout and stderr sha256, for `examples/*.yaml` and `tests/fixtures/uncertainty_surface.yaml`, in both trees; `uv run hde tests/fixtures/uncertainty_surface.yaml --decompose`, text and `--json`, in both trees |
| the example's sha256, its exact central row 0 (tied with row 1), its band 2.30%–7.70% (prototype) | `sha256sum m/two_paths.json`; `numpy.percentile(rows[:, k], [5, 95])` |
| central $296,909.29 bit-identical to the typed ladder; the futures' ranges (prototype) | `load_config_dict` and `compute_deterministic` on `m/hvr_example.yaml` against the same config with `renewal_rates` removed and `[0.02] * 4` typed; `run_monte_carlo` on the file run |
| 0.99 [0.96, 1.01]; +$71,772 (± $1,586); 0.0 and 5.82e-11; not_exact 7.00e-02 with an empty NO ROW list (prototype) | `uv run hde m/hvr_example.yaml --decompose`, and the same with `--json` |
| §6's (b)/(b′) table (prototype) | `run_monte_carlo` at `simulation.num_sims` 200, stated and probe (`sweep.load_at`); (b) by `break_even._shift_deviation_over_sd`; (b′) with Gᵢ as §6 defines it, Fin by `deterministic._financing_pv` at `value_N = 0` with `renewal_args_for` overridden by the row. `m/hvr_ar1.yaml` is `m/hvr_example.yaml` pointed at `m/ar1.json`: 2,000 rows × 4, AR(1) φ 0.5, stationary sd 1 pp around 4.5%, semi-annual, `numpy.random.default_rng(20261001)`, synthetic (regenerated from that recipe: sha256 `4ea1ca85a121…` both times). |
| 9.572e-16 for the per-path-leg form (prototype) | the same, with dᵢ = Δᵢ − [Fin(ρᵢ; x₁) − Fin(ρᵢ; x₀)], on the fixture's `house.mortgage_rate` → 10% |
| 130,000 and 118,000 against 250,000 (main) | `uv run python -c "from hde.decomposition_run import planned_evaluations as p, _level_paths as m, EVALUATION_CEILING as c; print([p(10000, k, m(10000)) for k in (8, 9)], c)"` |
| `_UNANCHORED_KEYS` at `sources.py:460`; the ladder's anchor and `market_scenario.path`'s both refused (main, r2) | `git grep -n _UNANCHORED_KEYS origin/main -- src/hde/sources.py`; R18's command, and the same with the fixture's `house.mortgage_renewal_rates` declared `anchor:mortgage_rate.contracted_5y_uninsured` |
| 1486fbc touches only `sources.py` and `input_schema.py` under `src/`; `--json` byte-identical to a2d1a7d (repo, r2) | `git diff --stat a2d1a7d origin/main -- src/`; the opt-out sha256 command above |
| commit 2 alone breaks only the pointer test: 1 failed / 254 passed (main + that change) | `channel()` by id and both guards from `decomposition.CHANNELS`, then `uv run --extra dev python -m pytest -q tests/test_decomposition_contract.py tests/test_channel_streams.py tests/test_decomposition_contract_doc.py` |
| a module-level `from .decomposition_run import ALL_CHANNEL_IDS` in `monte_carlo.py` is circular (main + that line) | `uv run python -c "import hde.monte_carlo"` raises `ImportError: cannot import name 'single_path_run' from partially initialized module 'hde.config'` |
| no source caller freezes on the legacy binding (main) | `grep -rn "freeze=" src/hde`: lines 851, 878 and 987 of `decomposition_run.py`, all through `_run` and `addressed_streams` |
| the config states no purchase date (main) | `uv run hde --print-schema \| grep -io '"[a-z_]*\(date\|calendar\|purchase\)[a-z_]*"' \| sort -u` prints only the three `*purchase_costs*` keys |
| `sources:` refuses a key the config does not set (main) | the fixture with `house.mortgage_renewal_*` removed and `sources: {house.mortgage_renewal_rates: user}`, through `load_config_dict` |
| 0.9992, 0.9792 and 0.9844 (prototype) | `m/hvr_ar1.yaml` at 5,000 paths: the shifted base arrays through `break_even._cheapest_probabilities`, against `run_monte_carlo(load_at(raw, "house.mortgage_rate", v))` |
| 27.18%, 29.84% and P 0.0 without `income_growth_rate: 0.0` (§9 row 7; the build) | §4's config without that field: the peak of `deterministic._annual_costs_for_option` per row against `_compute_income_trajectory`, then `run_monte_carlo`'s `affordability_mc.prob_house_exceeds` |
| 28.10%, 38.55%, 0.508 and 0.0 (prototype) | §4's config, `income_growth_rate: 0.0` included, `run_monte_carlo`, then the same with `deterministic._annual_costs_for_option` patched to the central row |
| 1 failed / 2,438 passed and 12 failed / 2,427 passed, with §8's list (main and prototype) | `uv run --extra dev python -m pytest -q -p no:cacheprovider` in both trees (846 s and 879 s) |
| every line number cited in this spec (main, r2) | `grep -n` and `sed -n` on the cited files |
| `demographic prior:`: 1 line on stdout, 0 on `--read-back`, 0 on `--read-back short`, 0 in `assumptions.read_back` (main, r2) | `uv run hde examples/showcase_demographic_prior.yaml` bare, with `--read-back`, with `--read-back short` and with `--json`, each counted for lines containing `demographic prior:` |
| the opens-at, inert and bias warnings on file runs; lines with `mortgage_renewal_rates` or `stated`: 3/1, 6/2, 3/1 on stdout/stderr; four quoted rates on the condo's one renewal (prototype, r2) | `uv run hde m/<config>.yaml > out 2> err` for `hvr_opens_at`, `condo5`, `hvr_example` and `two_opts`; `grep -c 'mortgage_renewal_rates\|stated'` on each stream; `grep 'condo renewals'` on `two_opts`'s stdout |
| `user-stated:` carries "stated" on a run with `sources:` (main, r2) | `uv run hde tests/fixtures/uncertainty_surface.yaml 2>&1 \| grep -o "[a-z-]*stated[a-z-]*"` |
| the empty ladder prices `m/condo5.yaml`'s condo as `[0.05]` does (main, r2) | `m/condo5.yaml` without `renewal_rates` and with ladders typed; `spec.condo.mortgage_renewal_rates = []`; `compute_deterministic(spec).condo.total_pv` compared |
| freeze isolation: rows identical for c in 0 to 6 and channel 4 at $90 (prototype); rows different for every c and channel 4 at −$71,683 (mutant) (r2) | `uv run python ../m_freeze_rows.py m/hvr_example.yaml` in each tree: `decomposition_run._run(spec, MATRIX_A, freeze=(c,))` at 2,000 paths, its `_rate_rows` against the unfrozen run's, and the mean margin shift |
| central rows 251, 1153, 1003 by horizon; 1153 at term 15, 251 at term 10 (prototype, r2) | `uv run python ../m_row_switch.py`: `sweep.load_at` on `m/hvr_ar1.yaml` for `years` 6, 10, 11, 15, 16, 20 and `house.mortgage_term_years` 25, 15, 10, printing `renewal_rate_paths.central_index` |
| the escape from `main()` on `--sweep`, `--break-even` and `--read-back` with income (r2), and on `--decompose` (the recheck); one load and exit 0 without them (prototype) | `uv run python ../m_r19_escape.py <flags>`: `config._build_spec` wrapped to raise from its second call, `cli.main()` in-process on `m/hvr_example.yaml` at 200 paths, `INCOME=1` adding an income block |
| the did-you-mean message on `renewal_rate` (main and prototype, r2) | `uv run python ../m_didyoumean.py`: `examples/mortgage_house_vs_rent.yaml` plus a top-level `renewal_rate: {path: x.json}`, through `load_config_dict` |
| `CHANNELS` ids `[0, …, 6]` (main) and `[0, …, 6, 8]` (prototype) (r2) | `uv run python -c "from hde.decomposition import CHANNELS; print([c.id for c in CHANNELS])"` |
| commit 3's and 7's text: `test_skill_contract.py` 17 passed, `test_input_schema.py` 2 failed (the `KNOWN_GOOD` tests), SKILL.md 2,597 words (prototype, r2) | the edits on a copy, then `uv run --extra dev python -m pytest -q -p no:cacheprovider tests/test_skill_contract.py tests/test_input_schema.py`, and `python3 -c "print(len(open('.claude/skills/hde/SKILL.md').read().split()))"` |
| §11's co-movement: same five-year window +0.32/+0.50, +0.44/+0.40, +0.68/+0.38, +0.45/+0.21; following window +0.32/+0.41, +0.25/+0.36, +0.13/+0.03, −0.26/−0.10; one-year rate change against the following year's price change, since 1991, −0.16, −0.24, −0.29, −0.30 (all starts / 1991+; public data, outside the engine) | Pearson over overlapping annual starts t through 2025, December values (Q4 for the Dallas Fed series): x = v733833(t+h) − v733833(t) in percentage points, y = ln(P(b)/P(a)) with [a, b] = [t, t+h] (same) or [t+h, t+2h] (following), h = 5 or 1. Price series: Statistics Canada v111955484 (NHPI, Montréal), that divided by CPI v41690973, and the Dallas Fed International House Price Database HPI and RHPI for Canada (Mack and Martínez-García 2011, Globalization and Monetary Policy Institute Working Paper No. 99; the full citation is under §11 Q1). Independent windows ≈ n/h |
| the stream hard-codes and the "seven" comments (main, r2) | `grep -rn "range(8)" tests src`; `grep -rn -i "\bseven\b" src tests docs/reference .claude` |
