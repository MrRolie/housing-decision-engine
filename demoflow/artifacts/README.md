# The committed golden (spec §10)

`rankings.json`, `tripwire_baseline.json` and (since Tranche 2, spec §7(a))
`scenario_prior.json` are **build artifacts**, generated from the committed data vintage and
committed alongside the code that produces them. Never hand-edit them: regenerate and commit
what the generator emits.

NOTE (Tranche 2): the pairing/identity protocol below is written against the original
rankings+tripwire PAIR. `scenario_prior.json` carries the same envelope discipline — same
identity members, one shared `run_pairing`, its own §7(a) vintage shape
{isq_edition, census_year, constants_as_of, source_hashes} plus a root `mapping_version` — and
the pairing token now digests all THREE payloads; every step below applies to it identically,
read "both files" as "all three files".

```bash
cd demoflow && uv run python scripts/gen_golden.py
```

`tests/test_golden.py` re-runs the pipeline and diffs both files — parsed first, then byte for
byte. Nothing is normalized out of that diff; a golden with holes in it has stopped pinning the
thing it was built to pin.

**The claims on this page are TEST-BOUND, in six marked spans**, and THAT COUNT IS ITSELF BOUND:
`::test_the_readme_binds_its_OWN_count_of_marked_spans` reads the number out of the sentence you
are reading and compares it to the markers in the file, so a span added without a word here reds.
A nested marker pair counts as its own span — `<!-- SWEEP-AXES -->` is sliced by its own markers
and carries its own set-equality against `constants.SWEEP_GRID`, so it is bound in its own right
rather than by sitting inside another span.
`tests/test_golden.py::test_the_readme_binds_the_hash_and_every_shipped_row` binds the
`<!-- CURRENT-STATE -->` span to the shipped bytes AND to `constants.assumptions_hash()` itself;
`::test_the_readme_discloses_every_raw_anchor_row` binds the `<!-- RAW-ANCHOR-KEYS -->` span to a
filesystem measurement; `::test_the_readme_binds_the_SWEEP_COUNTS_and_the_axis_census` binds the
`<!-- SWEEP-COUNTS -->` count words and the nested axis roster to the declared grid;
`::test_the_readme_carries_ALL_THREE_named_limits_bound_to_their_instruments` PINS the
`<!-- NAMED-LIMITS -->` span's content whole, by digest — every addition, deletion and rewording
reds, in any spelling — and separately binds its ratio, exponential and multiple figures to the
roles they are attached to, each limit's instrument to the paragraph that states it, and the whole
section to carrying nothing but that span. The role bindings are the half that survives a
DELIBERATE re-mint of the digest, so they name the figures they reach rather than all of them;
`::test_the_readme_binds_the_RATIO_ENDPOINT_claims` binds the
`<!-- RATIO-ENDPOINTS -->` span's per-endpoint rows-moved counts to the emitted `rows_moved`
map, and `tests/test_pipeline.py` binds the same span's rank-1 leader and holds/changes verdict to a
re-ranking of the ED grid at each endpoint. This page went stale by two rulings once — every ED
figure wrong, ranks 2 and 3 swapped, and a sign headline asserting the exact opposite of the
shipped file — because prose that quotes shipped digits was bound to nothing. **Every 16-hex
identity token this page quotes is either the CURRENT one, inside the current-state span, or sits
inside a section whose heading says `HISTORY`** — a token presented as current from anywhere else
is refused. Quote a digit inside a marked span, or under a HISTORY heading, or do not quote it.
The census reads a BARE token as well as a backticked one, so dropping the backticks is not a way
past it; it is anchored on both sides against hex and against a decimal point, which is what keeps
a 16-digit run inside an ED figure from reading as an identity token.

## What is pinned, and what is not

| Input | Pin | Where |
|---|---|---|
| data directory | `demoflow/data/` | `golden.GOLDEN_DATA_DIR` |
| `now` (freshness clock) | `2026-12` | `golden.GOLDEN_NOW_YEAR` / `GOLDEN_NOW_MONTH` |
| every **committed** source's bytes | sha256 of the file, in the file | `data_vintage.source_hashes[key].sha256` |
| the **raw upstream** member behind one extract | sha256 of the *upstream response*, in the file | `data_vintage.source_hashes[key].sha256` + `pins.RAW_SOURCE_SHA256` |
| that extract's **own committed bytes**, alongside | sha256 of the file, in the file | `data_vintage.source_hashes[key].committed_sha256` |
| the CPM mortality basis | sha256 of the q surface, in the file | `data_vintage.source_hashes["mortality_basis:…"]` |
| the assumption selection | 16 hex chars, in the file | `assumptions_hash` |
| both documents' CONTENT, for PAIRING the two files | 16 hex chars, in **both** files | `run_pairing` |
| how many rows each robustness leg moved | one count per declared leg | `rows_moved` (rankings only) |
| each tripwire's freshness + coverage declaration | per indicator row | `freshness_years`, `source_kind` |

**`sha256` carries TWO semantics across the twelve file-backed keys, and the one row that is not
what it looks like now publishes BOTH.** Eleven of them put the sha256 of the committed file in
`sha256`, so `sha256sum demoflow/data/<key>` reproduces it. **One does not:**

<!-- RAW-ANCHOR-KEYS:BEGIN -->
* `census_tenure_age_98100231.csv` puts in `sha256` the digest of the **raw upstream member** it
  was filtered from (StatCan 98-10-0231-01, zip member 98100231.csv, 850,971,474 bytes, not
  committed), per spec §7's sha256-of-raw-response definition — `773f7af8de…`. That key therefore
  carries a SECOND, optional field: `committed_sha256` = `74673e57d1…`, the digest of the bytes
  the run actually read off disk, which is what `sha256sum` reproduces and which is verified on
  every run against `pins.WORKBOOK_SHA256`. So verify this key against `committed_sha256`, not
  against `sha256` — the mismatch a consumer used to hit here is now a named field rather than an
  expected surprise. No other key carries it (spec amendment #20(C)(1)), and a test measures that
  set against the emitter's own declaration rather than trusting this paragraph.
<!-- RAW-ANCHOR-KEYS:END -->

The raw anchor is the one link in the chain a re-extract cannot move with — re-cut the extract
and its pin, the artifact's recorded digest and a fresh derivation all move together, so putting
the committed digest in `sha256` would make the whole legitimate-refresh motion pass on a
materially different vintage. That is why the committed digest joins the row as its OWN field
instead of replacing the anchor. `pins.py` carries the argument in full. This matters more since
operator ruling X2 (2026-08-21): that extract now supplies `p_nonimm`, **a rate the model
multiplies 336 times per run** — one per leg × geography × scenario — so it is a live model input
and not only a derivation-time one. **That figure is COMPUTED, never typed:** it shipped as `288`
until run 52, which was the RETIRED twelve-leg grid's product, and
`tests/test_golden.py::test_the_readme_binds_the_p_nonimm_EXPOSURE_COUNT` now reads the number out
of the sentence above and compares it to `len(sweep_leg_labels())` × the shipped ranking's row
count × the scenario count, so the next grid widening moves this page or reds.
`pipeline.RUN_SOURCES` marks the row `publishes=_RAW_ANCHOR` and is the single declaration of
which keys behave this way.

`extracted_at` inside `source_hashes` is **declared provenance**, read from each derived
artifact's own `_provenance` block (hence the three different dates) — never a wall-clock
stamp. It is stable across runs and it belongs in the diff.

**The mortality basis rides the envelope and is not a file.** Every `q` value the supply side
uses comes from actuarial-system's CPM2014 + CPM-B tables, which live outside this repo behind a
uv path dependency with no digest — so before run 33 two runs over *different upstream mortality
tables* emitted different `rankings.json` bytes under a **byte-identical** envelope, and the
table at the bottom of this page then sent the reader hunting a code defect that did not exist.
The run now publishes `mortality_basis:CPM2014_combined+CPM-B`: a sha256 over the **q surface**
the model consumes (ages 75–100 × M/F × 2021–2051), taken through the same guarded public entry
point every lookup uses — spec §2 forbids reaching into the engine's private table registry.
It is **recorded, not pinned**, like the IRCC feed: a legitimate re-publish upstream is a
**re-mint**, not a refusal. Its `extracted_at` is the one date in this envelope that is neither
an upstream pull nor an artifact's own `_provenance` — the dependency publishes no date through
any public surface, so the entry declares the day its surface was measured into the envelope
(`pipeline.BASIS_RECORDED_AT`), and a test reds if the digest moves off that declaration.

**`now` is an input and neither document records its VALUE.** The freshness gate takes an
injected `(year, month)` so a verdict is reproducible, and spec §7 closes the envelope —
`output/artifacts.py` RAISES on any undeclared position, so a `now` field would need its own
amendment. `demoflow/golden.py` is still the artifact's only provenance for the clock, which is
why the generation path is committed source rather than a remembered shell line. What the
documents DO carry since spec amendment #20(C)(3) is `run_pairing`, a 16-hex token — and since
amendment #22(C) what it is computed FROM is both documents' **payload**: each file's content
OUTSIDE its identity envelope, digested through the one canonical serialization the writer pins.
So it moves whenever either document's content moves, **for any cause** — an upstream refresh, a
ruling, or a model change that touches no constant, no data byte and no schema. That last one is
why the payload was re-specified: the token used to be computed over (assumption selection, source
bytes, `now`), none of which is output content, so a computation change emitted a REORDERED ranking
under a byte-identical token and a consumer comparing it accepted the pair. Emission is
all-or-nothing, but the two renames are a loop, so a failure between them can leave a mismatched
pair whose `assumptions_hash` and `data_vintage` are identical. **Compare `run_pairing` across
the two files before you read either.** They differ ⇒ the pair is not from one run, refuse it.
**ABSENT IS NOT A MATCH.** A document emitted before amendment #20(C)(3) carries no
`run_pairing` at all — such artifacts exist and are still VALID, and this tree's validator
accepts them — so a consumer reading the field with `.get()` on two of them compares `None` to
`None`, and the step above passes VACUOUSLY having proved nothing. Absence is NOT a refusal
either: refusing it would break exactly the backward compatibility the un-bumped
`schema_version` was kept for. Absent on either file means NO PAIRING EVIDENCE, and the pair is
then judged on the two fields below alone.
**Then compare `data_vintage`, `assumptions_hash` AND `schema_version` across the two files as
well** — those three are what refuses a mismatched pair the token cannot see. Equal tokens mean the
two runs' PAYLOADS coincided, not that there was one run: two runs that moved an ENVELOPE field
without moving a number — a re-declared `extracted_at` (measured 2026-08-23), an added
`committed_sha256`, an anchor edit no ED reads — emit byte-identical payloads and therefore the SAME
token, and the mismatch then shows in those three fields alone.
**`schema_version` IS THE FOURTH COMPARISON AND IT IS NEW (spec amendment #24(C)).** The identity
this page declares has FOUR members and the protocol compared THREE of them. `schema_version` sits
INSIDE the identity envelope and the token is computed over the payload with that envelope
SUBTRACTED, so the token is blind to it BY CONSTRUCTION — the same property that makes the token
computable without hashing itself. Measured on the committed pair: flip one file's `schema_version`
and its payload digest is bit-identical, the token does not move, and every step above passes. Two
documents that disagree about the format they declare are not one run's output, whatever their
content digests agree on.
**`schema` is NOT compared, and the exclusion is a ruling rather than an omission.** The two
documents carry DIFFERENT `schema` strings by design (`demoflow.rankings.v1` against
`demoflow.tripwire_baseline.v1`), so comparing that field would refuse EVERY honest pair. The
compared set is therefore the identity envelope less exactly that one member;
`artifacts.pair_identity_mismatches` is these four steps as code, and a test binds the set it
compares to the envelope's own so a sixth envelope field joins one side or the other by a decision
rather than by silence.
POSIX gives no atomic multi-file rename, so the window stays; what closed is the DETECTION of a
pair whose two files' CONTENT came from different runs.

**THE ONE PAIR NO CHECK ON THIS PAGE CAN REFUSE — measured 2026-08-23, not reasoned.** The token
refuses no pair whose two runs' PAYLOADS coincided; the envelope comparison above catches every
member of that class but one, and this is it.
**THAT ENUMERATION WAS FALSE UNTIL THE FOURTH COMPARISON EXISTED, and it is corrected by the step
above rather than by a re-wording (spec amendment #24(C)).** The class had TWO uncaught members: the
clock-only pair below, and a pair differing only in `schema_version` — an identity member this page
declares and which nothing here and nothing in the code compared across a pair. With that step
added the enumeration is exhaustive over the envelope: `schema` differs by design and cannot
discriminate two runs, the other four are compared, so a pair that survives every step differs in
no envelope field at all. `now` is not payload; neither document records it. So the clock reaches this token only through content, and on
this tree it reaches none: all six indicators are structurally UNKNOWN with a null `as_of` and a
null `current_value`, so a December run and a November run emit BYTE-IDENTICAL documents. Two runs
separated only by the clock therefore carry the same token. What that costs is nothing a reader
can act on — the pair is content-identical to an honest one in BOTH files, so every number you
read is the number the run produced — and it costs one gate: a clock-only re-mint no longer moves
a committed byte, so `demoflow/golden.py`'s pin is the clock's only provenance AND its only guard.
It stops being invisible the day the first indicator carries a real value, which is the same event
that re-mints the golden. #22(C) traded a distinction with no consequence for one with a measured
one.

`demoflow run`'s `--out` defaults to the relative `artifacts`, so a run invoked from `demoflow/`
lands here by design. That is a convenience, not the minting path: use the script above, so the
committed bytes carry the pinned `now` rather than today's date.

## THE SHIPPED MINT — the current ranking and its identity

<!-- CURRENT-STATE:BEGIN -->
`assumptions_hash` is `e03504aaffd0a35a`. `data_vintage.source_hashes` carries thirteen entries:
twelve file-backed (eleven committed digests, one raw anchor — see above) and the mortality
basis. `exclusions` is empty: all eight modeled geographies are ranked.

**Rank 1 is the MOST NEGATIVE `mean_ed_reference`.** A negative ED is a reading — supply
exceeding demand at that geography over the projected years — not an error and not a failure of
the run. The figures below are the artifact's own full-precision values, verbatim.

| rank | geography | `mean_ed_reference` | `mean_ed_low` | `mean_ed_high` |
|---|---|---|---|---|
| 1 | `LANAUDIERE_RA14_PROXY` | -0.000861816054566814 | -0.003955989878047007 | 0.0023291205374152777 |
| 2 | `LAURENTIDES_RA15_PROXY` | -0.000599967268849611 | -0.003978412893017653 | 0.0028024255329287687 |
| 3 | `LAVAL_RA13` | -0.0004921670100473161 | -0.002626128516366279 | 0.0016854370483882204 |
| 4 | `HORS_RMR` | 0.00024822935467663234 | -0.0026216655846809313 | 0.0028158877823177613 |
| 5 | `MTL_RMR` | 0.0006693437674490574 | -0.0029960504180002925 | 0.004039480181615847 |
| 6 | `MONTEREGIE_RA16_PROXY` | 0.0008143468805139723 | -0.0032136391088007483 | 0.004518014006882055 |
| 7 | `QC_RMR` | 0.0036821317213199885 | -0.0011231683052316621 | 0.008067088356442346 |
| 8 | `MTL_ISLAND_RA06` | 0.005032692684347393 | 6.630128456943239e-05 | 0.00948518462616907 |

**THREE rows carry a negative `mean_ed_reference`, and rank 1 is one of them** — ranks 1, 2 and
3. **SEVEN of the eight carry a negative `mean_ed_low`**, and the exception is
`MTL_ISLAND_RA06`, whose low-scenario mean crossed zero under spec amendment #24(A) — from
-3.660e-04 to +6.118e-05 ON THE PRE-#27 SERIES, and 6.630128456943239e-05 at this mint, where
spec amendment #27 re-based every level again. Both legs of that pair are a dated reading of a
retired convention and are stated as one; what is CURRENT is the table above. A consumer reads
the crossing as shrinking-versus-growing excess demand at the low end, so it is a semantic flip
and not a rounding. `rank_stable` is `false` on every row (next
section). Row flags: `borrowed_prior` + `ra_proxy` on the three RA proxies, whose immigrant
inputs are borrowed (the ownership-curve borrow is wider — see the next section),
`closed_cohort_exceedance` on `LAVAL_RA13`, none on the other four.

**The table is TIGHT in the middle.** Ranks 2 and 3 sit 1.08e-04 apart — `LAURENTIDES_RA15_PROXY` and
`LAVAL_RA13`, the narrowest rank-deciding gap in the table — and ranks 1–6 span
1.68e-03. Read a rank as an ordering over that spacing, not as a distance.
**THE TIGHTEST PAIR MOVED WITH SPEC AMENDMENT #27**, from ranks 5-6 to ranks 2-3: the end-labelling correction is near-uniform across the soft middle, so it left every rank in place while re-ordering WHICH adjacent gap is the narrowest. The superlative is re-derived from all seven adjacent gaps on every run, never carried.

**What this mint's model is.** FIVE model changes sit between it and the last order this page
recorded — and the ORDER survived all five, which is why this section describes levels:

* **Seven ownership bands** (operator ruling W, 2026-08-20). `census._AGE_BAND_SPEC` was
  refined from a flat `25-54` + `75+` shape to `25-34 / 35-44 / 45-54 / 55-64 / 65-74 / 75-84 /
  85+`. The lattice FLOOR stays 25.
* **The 75+ bucket is valued at its OWN population-weighted rate** (operator ruling X1,
  2026-08-21). `pipeline._standing_stock` values the lumped `age >= 75` slice at
  `Σ_a pop(a)·ρ(a) / Σ_a pop(a)` over exactly the ages it holds, instead of a point read at
  `ROLL_AGE` (80) — which, once ruling W split the flat band, resolved to `75-84` ALONE and
  valued the whole bucket at the upper half of the gradient the refinement had just exposed.
  `ROLL_AGE` still carries the hazard and the living-arrangement read; it no longer selects a
  band.
* **The immigrant leg reads a 25-54 AGGREGATE, not an age** (operator ruling X2, 2026-08-21).
  `p_nonimm` is formed by construction from owner counts and total counts summed across
  `25-34 / 35-44 / 45-54` and divided ONCE — never a mean of the three band rates, which is off
  by -1.005 pp at MTL_RMR because the bands carry materially different household counts. The
  retired pick was an AGE (40), which ruling W had made live.
* **The immigrant leg's propensity is CONVERTED off the pooled denominator** (spec amendment
  #24(A), 2026-08-23). The cube that curve is read from carries NO immigrant dimension, so the
  rate it serves is owner maintainers over ALL maintainers, while the immigrant/non-immigrant
  ownership RATIO it multiplies is denominated on non-immigrants alone. The shipped product was
  therefore the true immigrant propensity times a per-geography factor `B = p_all / p_nonimm`,
  measured from the ratio's OWN cube's counts: 0.940022 at `MTL_RMR`, 0.970180 at `QC_RMR`,
  0.939637 at `MTL_ISLAND_RA06`, 0.990212 at `HORS_RMR` and 1.016742 at `LAVAL_RA13` — the one
  geography above 1, i.e. the one place the shipped leg was OVER-stated. `pipeline._ed_series`
  now divides by it. **All 24 emitted values moved and ZERO of eight rows reordered.** What the
  conversion CANNOT do is correct the age SHAPE: `B` is a per-geography scalar and no
  age-resolved non-immigrant curve exists in these bytes, so the corrected operand is
  "non-immigrant LEVEL, all-maintainer SHAPE" — a named limit whose closing is Tranche-2
  acquisition work.
* **The supply legs are END-LABELED, like the demand legs** (spec amendment #27, 2026-08-23).
  `ED(t)`'s numerator subtracted a SUPPLY flow measured over `[t, t+1)` from a DEMAND flow
  measured over `(t-1, t]` — two adjacent, DISJOINT twelve-month windows. The roll-forward keys
  its exits at the roll-START year and the market-listing convolution reads them at that key,
  while both demand legs are windows ending at `t`: `native_formation` differences the `t-1`
  frame against the `t` frame, and `_arrival_year(t) = t - 1` end-labels the published arrival
  flow. `pipeline._exit_landing_year` is the missing supply-side sibling of that translation and
  is applied at the one place the exits are keyed. The direction is FORCED, not chosen: crediting
  arrivals(t) at t raises at the final domain year and a start-labeled native leg would need a
  population frame past the last one that exists, so end-labelling is the only self-consistent
  convention these bytes can carry. **All 24 emitted values moved on the exact identity
  `delta(t) = [listings(t) - listings(t-1)] / OwnerStock(t)` — the largest by 32.4% of its own
  magnitude and one year by 1.58x its row's own |mean ED| — and ZERO of eight rows reordered,
  with no headline sign flipped, on a 624-cell scan across all three scenarios.** What it DID
  move qualitatively is measured below: the narrowest rank-deciding gap, limit (C)'s reorder
  threshold, and two sweep legs.
<!-- CURRENT-STATE:END -->

## THE OWNERSHIP CURVE IS BORROWED AT FIVE ROWS, AND THE EMITTED FLAG DOES NOT SAY SO

**Five of the eight ranked rows do not read their own ownership curve.** RA-level geographies are
absent from the CMA-level tenure table this module reads its age-banded ownership rates from, so
each of them reuses its parent CMA's COMPUTED curve (spec §8). That borrow understates the island
and overstates the couronne — a declared v0 imprecision, not a defect — but it is a LEVEL a
consumer comparing ranks across those rows is reading THROUGH, and no field of `rankings.json`
publishes it.

**THE EMITTED `borrowed_prior` FLAG IS NOT THAT FACT** (spec amendment #25(D)). Its subject is the
row's IMMIGRANT leg: it says that ONE OR BOTH of that row's two immigrant-leg inputs — the
immigrant headship rate and the immigrant/non-immigrant ownership ratio — was taken from a coarser
prior instead of measured at that geography. It is a PER-FIELD provenance and not a geography set,
because ruling Q permits a cited ratio beside a borrowed headship; on these bytes every flagged row
borrows both. It says NOTHING about the ownership curve. The two are easy to confuse because the
WORD is the same and the row sets OVERLAP WITHOUT MATCHING: every flagged row does also borrow the
curve, so the flag never OVER-states — what it cannot do is UNDER-state, and at two rows it does.
Read the emitted flag as "this row's rates were borrowed" and you read those rows wrong. **The flag
deliberately stays as it is:** amendment #25(D) rules that putting it on them would make one token
carry two different provenances, which is the confusion this section exists to remove rather than
relocate.

**TWO OF THE FIVE ADDITIONALLY DIVIDE THE BORROWED LEVEL BY THEIR OWN BIAS — the module's only
cross-geography seam** (spec amendment #25(D)). On the IMMIGRANT leg alone, `pipeline._ed_series`
divides the borrowed 25-54 ownership union by the geography's measured pooled-denominator bias `B`
(named limit (C) below is what that division is for and what it cannot reach). At the rows whose
immigrant inputs are their OWN, that is the parent's LEVEL over the row's OWN bias — the one place
in this module where two geographies' measurements meet inside one operand. At the other borrowers
the borrowing helper passes the parent's whole immigrant-input block through, so the level AND the
bias are both `MTL_RMR`'s and nothing is mixed. The native-formation and supply legs read the
borrowed curve UNDIVIDED everywhere. A consumer comparing these rows to each other should know they
are not one class.

**WHERE THE OWNERSHIP BORROW IS PUBLISHED:** `ownership_by_geo_age.json`, under `demoflow/data/` —
every borrowing rate row carries an inline `"_flag": "borrowed_prior"`, and that file's
`_provenance.borrowed_prior` note states the parent and the direction of the imprecision. Until
this section existed the fact lived there and in code comments, and a rankings consumer opens
neither of those surfaces.

**THE ROSTERS BELOW ARE READ OUT OF THIS PAGE AND COMPARED, so a registry change or a moved flag
reds this section instead of aging it.**
`tests/test_golden.py::test_the_readme_binds_the_OWNERSHIP_BORROW_roster_to_the_registry` takes the
borrowing set from `census._BORROWS_FROM` itself, the lender from the same registry's values, the
seam split from which rows carry their own immigrant-input block, and the publishing file from that
file's own inline markers;
`::test_the_readme_binds_the_BORROWED_PRIOR_flag_claim_to_the_emitted_rows` takes the flagged and
unflagged rosters from the shipped `rankings.json`. EVERY count word in this section is read out of
its own sentence and measured against what it counts — an unbound count word beside a bound
roster is the staleness this page has shipped before.

* **BORROW THE OWNERSHIP CURVE** — `MTL_ISLAND_RA06`, `LAVAL_RA13`, `LANAUDIERE_RA14_PROXY`,
  `LAURENTIDES_RA15_PROXY`, `MONTEREGIE_RA16_PROXY`
* **LEND IT** — `MTL_RMR`
* **CARRY THE EMITTED FLAG** — `LANAUDIERE_RA14_PROXY`, `LAURENTIDES_RA15_PROXY`,
  `MONTEREGIE_RA16_PROXY`
* **BORROW THE CURVE AND CARRY NO FLAG** — `MTL_ISLAND_RA06`, `LAVAL_RA13`
* **DIVIDE THE BORROWED LEVEL BY THEIR OWN BIAS** — `MTL_ISLAND_RA06`, `LAVAL_RA13`
* **TAKE THE PARENT BIAS ALONG WITH ITS LEVEL** — `LANAUDIERE_RA14_PROXY`,
  `LAURENTIDES_RA15_PROXY`, `MONTEREGIE_RA16_PROXY`
## THREE NAMED LIMITS ON THIS RANKING — read them before you read a LEVEL, and before you read rank 1, 2, 3, 5 or 6

<!-- NAMED-LIMITS:BEGIN -->
Spec amendment #20 (2026-08-22) names two constructions inside this module that REORDER the
published ranking under defensible alternatives the declared sweep structurally cannot reach,
and amendment #24(A) (2026-08-23) adds a THIRD — the residual its own fix could not close.
None of the three is a computation error: no rank is decided inside numerical noise — forward,
reversed, sorted, `fsum` and exact `fractions.Fraction` summation all give the same rank vector,
and the WORST deviation from exact arithmetic is 1.00e-18: the MAXIMUM, over all 24
published means and those four float summation orders, of the distance between the mean
AS EMITTED — `sum(series) / len(series)`, the float division included, which is the
arithmetic `output/rankings.py` actually performs — and the exact rational mean of the
same values. The division rounding is named because it is most of the figure: against the
float SUM alone the maximum is 4.67e-19. The four orders are a NO-OP rather than a
spread, which is what makes this census reproducible at all — on every one of the 24
series all four produce a BIT-IDENTICAL sum, so the rank vector is invariant by
construction and not merely by measurement. **THE FIGURE PUBLISHED HERE AT THE #27 MINT,
1.83e-18, IS RETIRED AS UNREPRODUCED** (adversarial verification, 2026-08-23, corrected
at its own line per amendment #26(D)): it named its aggregation, and the aggregation it
named does not yield it — max/mean/median of the deviation of the mean, of the sum, and
of the spread across orders were all measured and none lands on it, the nearest
constructions being 1.87e-18 (the four order-deviations SUMMED at the worst cell, which
is not a maximum) and 1.73e-18 (one ulp at that magnitude). That is the SAME failure it
was itself introduced to repair on 2.00e-19, which named no aggregation at all, and the
direction is conservative in both readings: the true floor is SMALLER than either
retired figure, so nothing the span concludes from it weakens. The floor sits fourteen orders
below the narrowest rank-deciding gap the current-state span publishes, which is where that gap
is stated once and bound. Amendment #20's own
eight values were reproduced bit-identically by four independent implementations; amendment
#24(A) has since moved every one of them, so that reproduction is a record of the arithmetic and
not of these digits. **`rank_stable` does not price any of them, and no widening of the
declared grid would**: the sweep varies declared ASSUMPTIONS, and each limit below moves a BASIS
the grid has no axis for. A limit declared only in a spec the consumer never opens is undeclared,
which is why all three are on this page.

**(A) ED's numerator and denominator estimate the same 75+ owner-household block on two bases
that disagree by roughly 1.5x, and nothing in the module measures or bounds it.** Supply is a
CLOSED-COHORT roll-forward — base-year standing stock plus age-75 entrants, decremented at
`q_live`, never re-anchored to a later population. The ED DENOMINATOR re-estimates the same block
every year as a cross-section. **The sizing instrument is NAMED, because a sensitivity number
without the perturbation that produced it is not a measurement: re-anchor the rolled 75+ stock to
that year's cross-section estimate before each roll** — carrying S on the denominator's basis,
explicitly violating I1, a MEASUREMENT and never a proposed construction. The rolled/static ratio
at `MTL_RMR` runs 0.9505 at the 2021 base year, which is outside the ranking domain, 0.8088 at
2026, the domain's first year, and 0.6472 at 2051 — the three ratios are properties of the roll
and the population frames, so spec amendment #27 left them untouched. On that instrument the mean
reference ED moves -3.35e-03 to -4.92e-03 per row — the order of the ENTIRE published
ranked spread of 5.895e-03 — THREE of eight rows change sign, and the ordering moves
**MTL_RMR 5→6 with MONTEREGIE_RA16_PROXY 6→5**, with `LAVAL_RA13` 3→2 against
`LAURENTIDES_RA15_PROXY` 2→3. **THIS BAND MOVED WITH AMENDMENT #27 AND (B)'s DID NOT**, which is
the instruments' own arithmetic and not a coincidence: (A) perturbs S, the leg #27 re-labelled,
while (B) and (C) perturb the DEMAND legs, so their per-row DELTA is independent of the supply
convention in exact arithmetic and re-measures identically at every digit this page prints —
MEASURED, and stated at the precision that was measured: the two arms differ only in the last
bits of the double, because the supply term cancels out of the delta algebraically and not
bitwise. Not one of (A)'s CONCLUSIONS moved — same three
sign-changing rows, same four reordered ranks.

**(B) Spec §6's I2 identity is stated PER-AGE, implemented at the TOTAL, allocated UNIFORMLY, and
gated only on the SUM.** One uniform multiplicative scale nets the surviving arrival cohorts out
of all 101 ages, and the gate compares totals, which every allocation satisfies. **The sizing
instrument, again named: charge the ENTIRE netting to 25-74**, population-proportional within
that band, leaving every other age unnetted — satisfying the identical I2 sum the shipped uniform
scale satisfies. The band is 25-74 and not 18-74 because `_ownership` returns 0.0 below the
lattice floor at 25, so every formation gain at 18-24 is multiplied by zero; a band chosen from
what the loop ITERATES rather than from what the arithmetic WEIGHTS dilutes the netting and
understates it by about half. At the true band the mean reference ED moves -9.04e-04 to
-1.912e-03 per row, span 2.1x, THREE rows change sign, and the ordering moves **MTL_RMR 5→6 with
MONTEREGIE_RA16_PROXY 6→5**, with `LAVAL_RA13` 3→1 taking the lead,
`LANAUDIERE_RA14_PROXY` 1→2 and `LAURENTIDES_RA15_PROXY` 2→3. Direction, not magnitude, is
the durable finding: with no exception
and no row where it is conservative, **the shipped uniform allocation reads LESS RISKY at all
eight rows**.

**(C) Amendment #24(A) corrects the immigrant operand's LEVEL with a per-geography scalar and
CANNOT correct its SHAPE, so the operand ships as "non-immigrant LEVEL, all-maintainer SHAPE".**
The immigrant leg multiplies ONE rate — the household-weighted union of the ownership cube's
25-34, 35-44 and 45-54 members over ages 25-54 — and that union's internal age weights are
ALL-MAINTAINER, because the cube carries no immigrant dimension at all. Dividing by `B` re-bases
the union's LEVEL and leaves those weights exactly where they were, wrong by however much the
immigrant age composition inside the span differs; no age-resolved immigrant-status curve is
derivable from these bytes. **The sizing instrument is NAMED, and it is a CONSTRUCTED BOUND
rather than a measurement of reality: charge the whole 25-54 span to one published sub-band at a
time**, keeping each geography's own `B`. The immigrant weights are unknowable here — but they
are WEIGHTS, so every re-weighting lies in the convex hull of the span's own three sub-band
rates, which at `MTL_RMR` are 0.3435, 0.5407 and 0.6216 against the shipped union's 0.5120. The
mean reference ED is AFFINE and increasing in this operand and no row's value depends on
another's, so a pairwise gap that keeps its sign at all three vertices keeps it over the WHOLE
simplex: the bound is COMPLETE, not three spot checks. At the YOUNGEST vertex the mean reference
ED moves -2.82e-04 to -3.74e-03 per row, THREE of eight rows change sign, and SIX of eight rows
reorder — rank 1 changes hands with `LAVAL_RA13` 3→1, and even rank 4 moves, `HORS_RMR` 4→6. At
the MIDDLE vertex nothing moves at all: +6.08e-05 to +8.63e-04 per row, no row changes sign, and
no pair crosses anywhere on the segment. At the OLDEST the mean moves +1.58e-04 to +2.44e-03 and
ONE row changes sign, and **spec amendment #27 WIDENED WHAT THIS VERTEX REORDERS from one pair to
two**: the measured instruments' own pair still moves, **MTL_RMR 5→6 with MONTEREGIE_RA16_PROXY
6→5**, and now so does **LAVAL_RA13 3→4 with HORS_RMR 4→3** — so the OLDEST vertex reaches rank 4
as well, which before #27 only the youngest vertex did. The per-row BAND is unchanged, because
(C) perturbs the demand leg alone; what moved is the baseline those crossings are measured
against. **The THRESHOLD is the durable
half, and it is exact rather than sampled**: the published order holds under every re-weighting
that moves LESS than 17.6% of the way from the all-maintainer weights toward any point of that
simplex, the minimum being attained toward the youngest vertex — a -2.97 pp move in the
`MTL_RMR` operand, against the +3.27 pp the level correction itself applied. **THAT THRESHOLD
TIGHTENED WITH #27, FROM 20.9%, AND THE PAIR THAT DECIDES IT CHANGED HANDS** — from `HORS_RMR`
against `MTL_RMR` to `LAURENTIDES_RA15_PROXY` against `LAVAL_RA13`, the SAME pair that is now the
table's narrowest rank-deciding gap, reached from an independent direction. A shape effect
0.91x the size of the level fix already found necessary, in the opposite direction, is enough to
reorder the table — and that multiple was 1.08x before #27, so a residual SMALLER than the level
correction #24(A) already applied now suffices. The conclusion strengthens; it does not reverse. **What this bound does NOT reach, stated rather than implied:** it re-weights
the cube's own ALL-MAINTAINER band rates, so it bounds the WEIGHTING residual and says nothing
about an immigrant-specific rate INSIDE a band. That half is unsized and stays unsized — the
cube has no immigrant dimension to read one from.

**THE CONVERGENCE IS THE STRONGEST FACT ON THIS PAGE.** (A) and (B) are two independent MEASURED
instruments, perturbing different legs of the quotient, and they produce the SAME reorder in the
middle of the table, flip the SAME three rows' signs, and agree on the whole ordering from rank 3
down — the two perturbed rankings differ from each other in exactly one place, whether
`LAVAL_RA13` leads or sits second. **Ranks 4, 7 and 8 are the only rows that hold under both of
the measured instruments.** Ranks 2, 3, 5 and 6 move under both measured instruments; rank 1
holds under (A) and moves under (B). (C)'s oldest vertex reaches that same middle pair from a
THIRD leg, which corroborates the softness rather than measuring it — and since spec amendment
#27 it ALSO crosses `LAVAL_RA13` against `HORS_RMR`, so the only rank the MEASURED instruments
leave standing in the top half is reached by the bound from BOTH of its outer vertices, not just
the youngest. (C) is a constructed
bound, and its youngest vertex reaches further than either measured instrument does.

* A consumer reading **ORDER** may rely on rank 4 and on the bottom pair under the MEASURED
  instruments, and **must not rely on ranks 1, 2, 3, 5 or 6**. That list is UNCHANGED by spec
  amendment #27 — both measured instruments re-measured to the same reordered ranks and the same
  three sign flips, because #27's correction is near-uniform across the soft middle. (C) does not
  narrow the list — it is a BOUND, and inside it the published order is untouched — but past its
  threshold rank 4 moves too, and since #27 it does so at BOTH of (C)'s outer vertices rather
  than at the youngest alone, from a threshold that tightened — stated once, above.
* A consumer reading **LEVELS** gets neither: both measured limits move every level, (A) alone
  moves it by the order of the whole published spread, and (C) is a statement about the levels
  and nothing else.
* Do **not** read `rank_stable: false` as covering this. That field is the verdict of the declared
  sweep, and the declared sweep cannot reach any of these bases — `q_live` moves the hazard
  INSIDE the closed cohort, no declared axis moves the roll's BASIS, the uniform I2 allocation is
  not an assumption the grid carries at all, and the ownership cube's age weights are not an
  assumption either. The sweep is honest about what it varied and silent here.

None of the three is repaired in Tranche 1, deliberately. Closing (A) means either re-anchoring
the roll-forward to each year's population or making the denominator cohort-consistent — both
Tranche-2-scale changes to the supply model that would move every published number. Closing (B)
needs a PR arrival age distribution no source in this tree carries, and until one lands a per-age
allocation would be a fabricated profile dressed as a measurement. Closing (C) needs an
age-resolved immigrant-status tenure cube, which is Tranche-2 acquisition work and is already
listed as such.
<!-- NAMED-LIMITS:END -->

## The IRCC feed is DECLARED ABSENT

`data/ircc_pr_by_cma.csv` is deliberately **not committed**. Committing it would flip
`pr_landings_annual` from structurally UNKNOWN to a live verdict, so the honest committed state
of this repo is the one the golden pins: `UNKNOWN` / `source_unavailable`, and no IRCC key in
`data_vintage.source_hashes`.

Two consequences, both intended:

* Drop the feed into `data/` and the diff tests red **with no code change**. That is the
  expected **re-mint**, not a regression — re-run the generator and commit the new bytes.
* A golden minted *with* the feed then fails in any checkout *without* it. This is the one
  input whose absence is load-bearing, so `test_golden_declares_the_absent_ircc_feed` names it:
  a red there tells you which direction you are in before you read a byte diff.

**A fixture-backed golden is rejected.** It would stamp a non-live vintage into a committed
artifact and destroy exactly the data-vs-code attribution the table below rests on.

## The tripwire exit code pins nothing today

All six indicators are structurally UNKNOWN — one wired feed uncommitted, two wired to nothing,
three operator-supplied with no operator input — so `run_exit_code` returns **1 on every
vintage**. Do not read that 1 as a verdict about Québec housing, and do not treat it as
something the golden asserts: it is a constant, and it will change the day the first real input
lands. That change is **success**, and it re-mints this golden.

Supplying a value to make it green would be a fabricated operator input. Don't.

**Every indicator row now publishes the two declarations it is GOVERNED by** — `freshness_years`
and `source_kind` (`wired` or `operator_supplied`), spec amendment #21. They ship INERT: with
every `current_value` null, no freshness comparison is evaluated, so nothing in this baseline's
verdicts depends on them yet. That is the point of publishing them now rather than later. Move
`freshness_years` once a source is wired and a landed indicator's `status` can flip — STALE to
FRESH, or a band verdict to UNKNOWN — while `assumptions_hash` and `data_vintage` stay
byte-identical, because neither token covers it. Published, the move announces itself in the
diff, which is the same argument that keeps `band_low`/`band_high` out of the hash.

**`band_low: 0.0, band_high: 0.0` ON THREE ROWS IS A PLACEHOLDER, NOT A ZERO-WIDTH BAND.**
`temp_resident_stock`, `registre_foncier_volume` and `natural_increase_sign` publish that pair
because no threshold has been RULED for them — it is `pipeline.UNRULED_BAND`, a statement that no
band exists, and the emitted row cannot tell you that: nothing in the schema distinguishes an
unruled placeholder from a ruled interval that happens to be empty. Do not read those two zeros
as a band those indicators were measured against. **What the run does instead of disclosing it in
the row is REFUSE:** a real measurement arriving against that placeholder raises rather than
publishing a verdict off a width nobody set, and since 2026-08-22 that refusal covers BOTH
evaluation paths (it guarded only the five declared indicators and not the PR-landings one).
Giving the row a field of its own is a schema change and therefore a spec question, not this
page's to make.

<!-- SWEEP-COUNTS:BEGIN -->
## `rank_stable` is a SEVEN-AXIS verdict, and `false` everywhere is the measured state

Every row of `rankings.json` carries `"rank_stable": false`. That is the honest output of the
robustness sweep, **not** a regression and not a hole — do not read it as a broken gate, and do
not expect a re-mint to turn it green.

Spec §7b asks one question: *does the ordering change anywhere in the sweep grid?* The run
answers it over **seven declared axes at both endpoints each — fourteen legs**, unioned.

**HOW MANY ROWS EACH LEG MOVED IS NOW AN EMITTED FIELD, not a table on this page.** Read
`rows_moved` in `rankings.json`: one count per declared leg, keyed `<axis>=<endpoint>`,
re-derived on every run (spec amendment #20(C)(2)). The table that used to sit here was an
inherited measurement this page itself labelled "a dated reading" — and it HAD gone stale:
measured 2026-08-22, **eight of its twelve surviving cells were wrong**, including which endpoint
of `q_live_per_year` and of `phi_voluntary` reorders. Prose could not keep up with the model, so
the count moved into the document the model emits.

Six axes live in `constants.SWEEP_GRID` — <!-- SWEEP-AXES:BEGIN -->`q_live_per_year`,
`phi_voluntary`, `estate_eventual_fraction`, `estate_lag_years`, the categorical
`headship_shape` (ruling V) and `collective_share_75plus`<!-- SWEEP-AXES:END --> (spec amendment
#20(D), whose endpoints are the anchor's own declared band). The seventh is the uniform
join-table override over
`CONSTANTS["immigrant_ownership_ratio_sweep_span"]`: rulings S/T measure the ratio per geography,
so it has no central scalar and therefore no grid entry — `pipeline.Assumptions` carries it as a
sweep-only field. `headship_shape` is the one CATEGORICAL axis and the one whose low endpoint IS
the central choice, so that leg is a provable no-op and `_rank_stability` reuses the headline
grid for it.
<!-- SWEEP-COUNTS:END -->

**WHAT CARRIES THE VERDICT is the ratio AXIS, not any single leg** — and since spec amendment
#24(A) the axis is TWO-SIDED on rank 1: both of its endpoints displace the published leader, each
with a different geography. That is not a return to the claim this page shipped until run 52. That
sentence named a third geography as the 1.033 leader and was measured false twice over; what is
true now was measured at this mint, by re-ranking the ED grid at each endpoint. Per endpoint, now
bound:

<!-- RATIO-ENDPOINTS:BEGIN -->
* At `immigrant_ownership_ratio=0.155`: **rank 1 CHANGES HANDS**, the leader is `MTL_RMR`, and
  **seven** rows move — the ranking is a near-complete reversal, and since operator ruling W's
  seven-band lattice `LAVAL_RA13` is the sole fixed point, holding rank 3.
* At `immigrant_ownership_ratio=1.033`: **rank 1 CHANGES HANDS**, the leader is `LAVAL_RA13`, and
  **five** rows move, `LANAUDIERE_RA14_PROXY` among them dropping to rank 2.

So BOTH endpoints displace the published leader, to a DIFFERENT geography each, and between them
they move every ranked geography — which is what carries the union verdict to all eight rows. NO
single leg does that: the widest single leg is the low endpoint at seven of eight.
<!-- RATIO-ENDPOINTS:END -->

Every claim in that span is re-derived, not transcribed: the two rows-moved counts are compared
to the emitted `rows_moved` map, and the leader identity and the holds/changes verdict to a
re-ranking of the ED grid at each endpoint. Dropping the ratio legs would not return this field
to `true` either — the grid-only union is four of eight rows, measured by re-ranking the ED grid
at each non-ratio leg that moves anything and taking the UNION of the rows they move: `HORS_RMR`,
`LAURENTIDES_RA15_PROXY`, `LAVAL_RA13` and `MTL_RMR`, across the two legs `phi_voluntary=0.7`
(four rows) and `q_live_per_year=0.06` (two rows, both of them also moved by the first).
**THAT COUNT READ `three of eight` UNTIL SPEC AMENDMENT #24(A) RE-BASED THE LEVELS, THEN `two`
UNTIL #27 RE-LABELLED THE SUPPLY WINDOWS**, and each correction is stated rather than made
silently: the sentence sat OUTSIDE every marked span with nothing re-deriving it, which is
exactly how it carried a pre-#24(A) figure through the re-mint that falsified it. **#27 is also
what made the union stop being readable off the emitted counts at all**: with a SECOND non-ratio
leg now moving rows, two per-leg COUNTS do not determine their UNION — they may share every row,
one row or none — so the gate that used to compare the count to `rows_moved` now re-derives the
union itself and refuses to sum counts. The membership above is that re-derivation.

**What is test-pinned, and what is not.** Pinned and re-checked on every run: the union verdict
(`rank_stable is False` on every row); that the ratio AXIS moves every row across its two
endpoints and that rank 1 changes hands at the low one; that every declared axis actually MOVES
the ED numbers; and — new at this mint — that every emitted `rows_moved` count equals an
independent re-derivation of its own leg (`tests/test_pipeline.py`). What is NOT pinned is any
narrative about WHICH axis is quiet: that is what the emitted map is for.

**Before run 33 this field shipped `true` on all eight rows as a verdict over ONE of those axes**
(the grid was five-axis then; `headship_shape` joined at the ruling-V mint and `collective_share_75plus`
at spec amendment #20(D) — NAMED rather than called "this mint", which is what it said until
the #24(A) re-mint aged it by one). `_rank_stability` iterated `q_live_per_year` alone while `constants.py` stated the
ratio override as an existing fact of the pipeline — two committed contracts in contradiction,
green because no test crossed them, and **on the band curve** the axis that was swept happened to
be one that did not move the order. That last clause is history — and the sentence that
stood here CORRECTING it had itself gone stale, which is recorded rather than quietly
replaced because it is the second figure in this UNPINNED stretch of the page that the
#24(A) re-mint falsified — a stretch that describes the bound spans from just outside them,
which is the one position here that reads as bound and is not. It asserted that
`q_live_per_year` still reorders rows, and therefore that the run-33 one-axis sweep would
today catch itself on some rows. It reorders two rows at `q_live_per_year=0.06`
on THESE bytes — and getting there took two reversals, which is the whole reason this page does
not narrate the axis roster. It moved two rows before spec amendment #24(A); #24(A) re-based
every level and SILENCED it, reordering nothing at either endpoint; **spec amendment #27's
end-labelling REVIVED it, back to two rows at the low endpoint**. `collective_share_75plus` and
`estate_eventual_fraction` moved rows before #24(A) and still move none. So the run-33 one-axis
sweep would TODAY catch itself on two of eight rows again — the unearned attestation shrinks a
little and the multi-axis union is what earns the rest. WHICH axis is quiet is a narrative this
page does not keep: read `rows_moved`, and read the grid-only union above, which is now a
re-derived MEASUREMENT because two non-ratio legs move rows and their counts cannot decide
their overlap. None of it changes why the one-axis verdict was a defect. Two checks now stand where none did, and they cover DIFFERENT doors.
`pipeline._sweep_legs` refuses the run outright if a declared axis has no leg FIELD to carry it
— declared → field. `tests/test_pipeline.py::test_every_declared_sweep_axis_actually_REACHES_the_ED_NUMBERS`
pins that each leg's field actually MOVES the ED numbers — field → consumed. The second is not
redundant: `phi_voluntary` was a declared axis carried in name and inert in effect, which the
refusal cannot see, and a mutant that reproduces that shape passes the other tests (the
central run does not move, so no golden byte moves, and the ratio axis alone holds these
booleans at `false`).

**What would make a row `true` again** is a narrower sweep or a moved band — and **every one of
those edits is an `assumptions_hash` event**, which was new one mint ago. The `SWEEP_GRID` axes
always were. The ratio span was NOT: `CONSTANTS` sat outside that token, so narrowing
`immigrant_ownership_ratio_sweep_span` would have flipped these booleans under a byte-identical
`assumptions_hash` and landed in the "the code moved" row of the table below.
`constants.assumptions_hash` now hashes the whole anchor registry — value and band, via
`resolved_constants()` — so that residual is closed and the envelope names the cause. The same
widening is what makes `collective_share_75plus` safe to sweep: its value AND its band ride the
token, so a refinement of the anchor re-mints rather than moving the ranking invisibly.

## HISTORY — the published ORDER moved at operator ruling V (the age-resolved-headship mint)

**This section quotes SUPERSEDED figures on purpose.** It is the record of a previous mint, it is
outside the test-bound span above, and none of its numbers describe the shipped file. Read the
current-state section for what ships.

The ranking then was **not** the one that shipped before the ruling-V mint. That commit replaced the
six-band headship rate — one flat value reused at every age inside a band — with a single-year
graduation that closes on every published maintainer-age member (operator ruling V, 2026-08-19).
Measured **at that mint**:

| Geography | rank before | rank at the ruling-V mint | `mean_ed_reference` before | at the ruling-V mint |
|---|---|---|---|---|
| `LANAUDIERE_RA14_PROXY` | 3 | 1 | +0.000196 | +0.000851 |
| `LAVAL_RA13` | 4 | 2 | +0.000613 | +0.000958 |
| `LAURENTIDES_RA15_PROXY` | 2 | 3 | +0.000085 | +0.001031 |
| `HORS_RMR` | 1 | 4 | -0.000290 | +0.001102 |
| `MTL_RMR` | 6 | 5 | +0.002768 | +0.001911 |
| `MONTEREGIE_RA16_PROXY` | 5 | 6 | +0.001902 | +0.002250 |
| `QC_RMR` | 7 | 7 | +0.005461 | +0.005586 |
| `MTL_ISLAND_RA06` | 8 | 8 | +0.007213 | +0.006003 |

**Why it moved.** The retired band curve put the whole 0–19 → 20–34 rise on the single age 20,
where `ownership(20) = 0` zeroed it; the resolved curve spreads that rise across ages 20–34, most
of it *above* the lattice floor. `demand/formation.py` carries the measurement (MTL_RMR at
`Scenario.REFERENCE`, the 26 projected years pooled): the largest single-age share of native demand
falls from 79.9% at age 35 to 26.1% at age 26. Formation mass is redistributed WITHIN each band, so
a geography's own population age mix now converts into owner demand at a resolution the band rate
could not express — and the eight geographies have different age mixes, so their excess demands
move by different amounts. Nothing about the ED equation, the ownership lattice or the immigrant
leg changed there.

At that mint `assumptions_hash` moved `f39a8a240c60d777` → `9a876ab547fcafdd`, because ruling V
put `headship_shape` into the hashed selection twice — as a `CENTRAL_ASSUMPTIONS` pick
(`expo_cum_fc`) and as a `SWEEP_GRID` axis. That attribution was checked, not asserted:
recomputing the token from payload copies with `headship_shape` dropped from both dicts
reproduced `f39a8a240c60d777` exactly. `data_vintage` moved too — the `headship_by_age.json`
digest, whose `_provenance` prose was rewritten in the same run.

**The design panel's order table is PROBE-GRADE and was only partly reproduced.**
`docs/research/2026-08-19-headship-curve-design-panel.md` priced that order first-order (raw ISQ
population standing in for `P_resident`, per-year ED replaced by its mean) and got the direction
right where it mattered most — `HORS_RMR`'s sign flip and every row turning positive — while
missing the permutation. Read the panel for the design, never for the numbers.

**Rulings W, X1 and X2 then moved the order AGAIN, and back across zero.** Every figure in the
table above is superseded: three rows now carry a NEGATIVE `mean_ed_reference` and rank 1 is one
of them. The sentence *"the golden now carries none"* stood on this page for two rulings after it
stopped being true — which is why the current-state span is test-bound and this one is dated.

## HISTORY — three re-mints, and only the last moved an ED

**This section names two SUPERSEDED identity tokens on purpose.** Both are recorded as prior
mints; the shipped token is in the current-state span above.

`assumptions_hash` `fe7c631104c5182b` → `1df514df81440809` at the first of them. `data_vintage`
did **not** move and no emitted VALUE moved: the leaf diff over both documents was that one field.
The cause was a deliberate widening of the token's payload, not a model change.
`constants.assumptions_hash` gained a fourth payload member — the anchor registry's values and
bands (`resolved_constants()`) — after a round-3 audit measured that `CONSTANTS
["collective_share_75plus"]`, a LIVE input to `initialize_households` for every 75+ stock slice,
sat outside both identity tokens: moving it to `0.08`, its own declared band high, reordered the
published ranking (HORS_RMR 4→5, MTL_RMR 5→4) while both tokens stayed byte-identical. That is
the worked example of the third row of the table below producing a WRONG verdict, and it is the
same class run 33 closed for the mortality basis and the ruled join table.

`1df514df81440809` → `16d6c13342c8c335` at the second. Again **no ED value
moved** — all eight `mean_ed_*` figures and every rank are byte-identical to the previous mint.
Two causes, both deliberate:

* **The other half of the same ruling.** `collective_share_75plus` became a DECLARED robustness
  axis (spec amendment #20(D)), so it joined `CENTRAL_ASSUMPTIONS` and `SWEEP_GRID` — read through
  from its anchor, never redeclared — which moves the token by construction. Its central value is
  the anchor's own, which is why the headline numbers did not move: what changed is that the
  sweep now varies it. A Tranche-1 PR carrying the hash half without this one would have shipped
  a token that moves for the anchor beside a `rank_stable` computed over a grid that never varied
  it, which is a worse state than either half alone.
* **Five new OPTIONAL emitted members** (spec amendments #20(C) and #21), which is why the BYTES
  moved further than the token. This page shipped that count as "four" beside an enumeration of
  five, having already shipped a stale count twice, so the count AND the enumeration are now read
  out of the list below and compared to `output/artifacts.py`'s own optional-member declarations
  by `tests/test_golden.py::test_the_readme_binds_the_OPTIONAL_MEMBER_census`. **What that gate
  holds is AGREEMENT, not a ceiling** — it reds when this page and the code DISAGREE, so a sixth
  member declared here and in `output/artifacts.py` together passes it. Measured at the round-4 blocker-fix commit:
  adding a consistent sixth left the full suite green (the suite COUNT is deliberately not
  spelled — nothing gates it, and this page has already shipped a stale count twice). A sixth
  that is actually EMITTED moves the golden bytes and reds `test_rankings_match_golden` instead,
  so the Tranche-2 floor does hold — via a different gate than this sentence used to name, and
  NOT for a member declared optional but emitted only under conditions the golden vintage
  never reaches:
  * `committed_sha256` — the raw-anchor row of `data_vintage.source_hashes`, both documents
  * `rows_moved` — `rankings.json` only, one count per declared sweep leg
  * `run_pairing` — BOTH documents, deterministic over both documents' canonical PAYLOAD
    digests (spec amendment #22(C) re-specified this payload; it was (assumptions, source
    bytes, `now`), which no output content could move)
  * `freshness_years` — per indicator row of `tripwire_baseline.json`
  * `source_kind` — per indicator row of `tripwire_baseline.json`

  `schema_version` did **not** bump: every one of them is optional, so a consumer pinned to
  version `1` reads both documents unchanged, and a bump would invalidate pinned consumers in
  order to announce fields they may ignore.

**AND ONE OF THEM MOVED `data_vintage`, WHICH THE TABLE BELOW WOULD MIS-ATTRIBUTE.**
`committed_sha256` is a new FIELD inside `data_vintage.source_hashes[census_tenure_age_98100231.csv]`,
so that block's bytes differ while every published DIGEST and every `extracted_at` is unchanged —
no source was refreshed and nothing was re-pinned. The reading table's first row is about a moved
digest; diff the digests, not the block, before you accept it.

**`16d6c13342c8c335` → the token in the current-state span at the THIRD, and this one DID move
every ED.** Spec amendment #24(A) converted the immigrant leg's propensity off the pooled
denominator it had been reading — see the current-state section for the factor and its per-geography
values. All 24 emitted `mean_ed_*` figures moved, one of them across zero, `run_pairing` re-minted
with them, and `data_vintage` did **not** move: no source was refreshed and no digest re-pinned.
**The published ORDER did not change** — zero of eight rows reordered — which is why the
current-state table's ranks are the same ranks the previous two mints carried while none of its
figures are the same figures.

## Reading a red

**The attribution names the FIRST cause only.** `tests/test_golden.py::_match_golden` checks
`data_vintage`, then `assumptions_hash`, then both documents' **payload**, then `run_pairing`, and
fails on the first that differs, so a red that reads "the DATA moved" does **not** mean the
assumption selection held. Diff all three tokens before you accept any row below.

**THE ORDER CHANGED WITH SPEC AMENDMENT #22(C), AND THE ORDER IS LOAD-BEARING.** `run_pairing`
used to be the NARROW token — only the clock could move it alone, which is what made
"`run_pairing` differs and the other two do not" mean "the clock moved". It now digests both
documents' payloads, which makes it the WIDEST field in either file: it moves for a model change
too. Tested before it, and above it in the table, is therefore the PAYLOAD — a model change is the
thing `run_pairing` cannot move without. Left in its old position, that row would attribute every
model change to the clock.

| What moved | What it means | What to do |
|---|---|---|
| `data_vintage.source_hashes` | an upstream source was refreshed or re-pinned (IRCC restates overlapping cells; ISQ re-publishes workbooks; actuarial-system re-publishes the CPM tables) | confirm the refresh was deliberate, then re-mint |
| `assumptions_hash` | the assumption selection changed — the banded central/sweep values (`CENTRAL_ASSUMPTIONS` / `SWEEP_GRID`), the unbanded model choices (`MODEL_CHOICES`), a ruled immigrant input (`demand/immigrant_inputs.py`), or an anchor's value or band (`CONSTANTS`) | confirm the ruling behind it, then re-mint |
| the rows / indicators themselves, both tokens above IDENTICAL | **the code moved** — a model change | this is the default-defect case: explain it before re-minting |
| `run_pairing` ALONE in THIS file, with its own payload and both tokens above IDENTICAL | **the OTHER document's payload moved, or the pairing token's own definition did.** Since amendment #22(C) the token digests BOTH payloads, so a change confined to the sibling file (a moved tripwire band, measured) moves this file's `run_pairing` by itself. Read the sibling's own red first; if its payload held too, what changed is `artifacts.pairing_token`'s payload or the canonical serialization it hashes | confirm the sibling's change, or the emitter change, was deliberate, then re-mint |
| nothing — values identical, bytes differ | the serialization moved (indent, key order, encoding, line endings) | `artifacts._canonical_bytes` pins all four and `_dump_json` writes exactly those bytes; treat as a code red |
| the file is missing | the golden was never minted in this checkout | run the generator |

**THE CLOCK IS NO LONGER IN THIS TABLE, and its absence is a narrowing rather than a simplification
(amendment #22(C), measured).** `golden.GOLDEN_NOW_YEAR` / `GOLDEN_NOW_MONTH` can move without a
single committed byte changing, because on this tree the clock reaches no emitted value — see the
measured residual under "What is pinned". A clock re-pin therefore reds nothing here and is held
only by the pin living in committed source. The row returns by itself the day an indicator carries
a real value, since the clock then moves the tripwire PAYLOAD and lands in the row above it.

**What EVERY ROW ABOVE DOES NOT COVER, stated because it is the class this page got wrong once.**
Any attribution that rests on "the assumption SELECTION held" is only as good as
`assumptions_hash`'s coverage. Three selections are still outside
`assumptions_hash` by decision, and each is outside for a ledger reason rather than an oversight:
`pipeline.TRIPWIRE_BANDS` (every band is PUBLISHED per row as `band_low`/`band_high`, so a move
announces itself in the diff, and hashing it would re-mint the RANKING's token for a
verification-gate ruling that cannot touch an ED); `pipeline._TRIPWIRE_DECLARATIONS` (same
ledger, and since spec amendment #21 for the same REASON rather than merely beside it: its
`freshness_years` / `source_kind` halves are now PUBLISHED in the row they govern, so "a move
announces itself in the diff" is true of both tripwire ledgers instead of one. It was excluded
alongside its sibling while being published nowhere, which made the exclusion rest on nothing);
and `golden.GOLDEN_NOW_*` (the generator's clock, not the run's selection —
hashing it would stamp the golden's `now` into every run's token). `tests/test_constants.py::
test_the_hash_stays_OUT_of_the_tripwire_and_generator_ledgers` holds those three decisions as a
check rather than as this paragraph.
