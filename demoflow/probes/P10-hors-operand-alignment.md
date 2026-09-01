# P10 — HORS_RMR operand alignment: the ALIGNED immigrant inputs (amendment #12(A))

Written by `probes/run_p10.py`; nothing in this file is hand-edited.

SCOPE OF THIS HEADER (it claims only what it can enforce): every count, rate, ratio, residual, delta and threshold below is COMPUTED by this run from the live StatCan WDS responses and the two pinned ISQ workbooks it names — none is transcribed from the rulings or the audit record it is checked against. The check runs one way: those documents state the SHIPPED and BRACKET figures, this run recomputes them, and a disagreement REFUSES the run rather than being published. The ALIGNED figures are NEW measurements and are deliberately absent from the spec — they are proposed here, ruled elsewhere. Quoted strings are verbatim from a live response, a workbook cell or a named in-repo file, and every absence claim is scoped to the search that produced it.
This run registered 54 provenance-tagged figures: 43 DERIVED (computed here from the live responses and pinned workbooks this run read) and 11 CITED (verbatim from a live response, a workbook cell, the spec, the Task-26 audit record or a named in-repo file). The tagged set is the NARRATIVE figures — the ones a sentence rests on. Untagged numerals fall in two other classes, both stated rather than left to be assumed: TABLE CELLS, which are counts and rates this run computed from the coordinate-keyed live responses printed in the same row, and AUDIT METADATA — member ids, dimension positions, member counts, geoLevels, SGC codes and row indices. Every one of the three is traceable to a response or a file this run read.

Quoted or cited verbatim (not computed here):
- 2. Partie québécoise uniquement. — footnote line of the pinned compo-rmr-base.xlsx, verbatim
- RMR d'Ottawa-Gatineau2 — the Gatineau row label in compo-rmr-base.xlsx, verbatim
- Hors RMR — the hors-RMR row label in compo-rmr-base.xlsx, verbatim
- 1. Selon le découpage géographique et la dénomination du Recensement de 2021. — header note of the pinned compo-rmr-base.xlsx
- CLOSED-AT-MEMBER-LEVEL — probes/P9-catalogue-closure.md DECISION-VERDICT, read this run
- 4 cubes — 98-10-0621-01, 98-10-0622-01, 98-10-0623-01, 98-10-0624-01 — probes/P9-catalogue-closure.md DECISION-MAINTAINER-CROSS, read this run
- vocabulary-scoped; English member/dimension names only; StatCan WDS only — probes/P9-catalogue-closure.md DECISION-RESIDUAL, read this run
- 10.35% — spec §6 amendment #12(A), verbatim
- 3.9× — spec §6 amendment #12(A), verbatim
- 8,308,475 private-household persons vs 8,501,833 published — loaders/constants.py, verbatim
- ≈345,000 — spec §6 amendment #12(A), verbatim

## 1. The defect, and the principle that settles it

HORS_RMR's immigrant inputs are measured over the Québec province NET of the six wholly-QC CMAs. That residual INCLUDES the Québec side of Ottawa-Gatineau; the arrival flows it multiplies EXCLUDE it. Amendment #12(A) rules the principle — **the rate's territory must match the flow's territory** — and this run builds the residual that satisfies it.

| cube | title (live) | released | archive |
|---|---|---|---|
| [98-10-0621-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810062101) | Population groups by housing suitability and condition of dwelling: Canada, provinces and territories, census metropolitan areas and census agglomerations | 2023-10-04T08:30 | CURRENT |
| [98-10-0622-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810062201) | Population groups by housing suitability and condition of dwelling: Canada, provinces and territories, census divisions and census subdivisions | 2023-10-04T08:30 | CURRENT |
| [98-10-0003-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000301) | Population and dwelling counts: Census metropolitan areas, census agglomerations and census subdivisions (municipalities) | 2022-02-09T08:30 | CURRENT |
| [98-10-0231-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810023101) | Age of primary household maintainer by tenure: Canada, provinces and territories, census metropolitan areas and census agglomerations | 2022-09-21T08:30 | CURRENT |
| [98-10-0232-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810023201) | Age of primary household maintainer by tenure: Canada, provinces and territories, census divisions and census subdivisions | 2022-09-23T12:50 | CURRENT |
| [98-10-0623-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810062301) | Population groups by shelter cost: Canada, provinces and territories, census metropolitan areas and census agglomerations | 2023-10-04T08:30 | CURRENT |
| [98-10-0624-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810062401) | Population groups by shelter-cost-to-income ratio groups and core housing need: Canada, provinces and territories, census divisions and census subdivisions | 2023-10-04T08:30 | CURRENT |
| [43-10-0060-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=4310006001) | Selected housing characteristics, low income indicators and knowledge of official languages, by visible minority and other characteristics for the population in private households | 2023-01-23T08:30 | CURRENT |

`98-10-0621-01` is the ruled source (unchanged), `98-10-0622-01` its census-division/subdivision sibling, `98-10-0003-01` the membership, `98-10-0231-01`/`98-10-0232-01` the ownership curve's own pair, `98-10-0623-01`/`98-10-0624-01` scanned only for a Québec-part member, and `43-10-0060-01` the one cube that publishes that part — with the wrong metric, §3.

## 2. The ISQ side is SEPARABLE — measured on the OPERAND's own workbook

The flows come from `compo-rmr-base.xlsx`, and that workbook publishes **RMR d'Ottawa-Gatineau2 [cited: the Gatineau row label in compo-rmr-base.xlsx, verbatim]** as a row of its own, beside **Hors RMR [cited: the hors-RMR row label in compo-rmr-base.xlsx, verbatim]**. Its footnote '2' reads, verbatim: *2. Partie québécoise uniquement. [cited: footnote line of the pinned compo-rmr-base.xlsx, verbatim]* — so the Gatineau row IS the Québec part, by the publisher's own statement. Its header note fixes the delineation: *1. Selon le découpage géographique et la dénomination du Recensement de 2021. [cited: header note of the pinned compo-rmr-base.xlsx]*.

Quoting is not the measurement. The measurement is that the workbook's own parts CLOSE on its province row with Gatineau counted as one of them: over 26 published years of `Immigrants permanents` under Référence (A2026), the 8 regional rows sum to the province row within 3 persons/yr (tolerance ±10, the workbook's own rounding step). A hors-RMR row that also contained the Gatineau flow would double-count it, and the same sum would then overshoot by that row's whole size — a mean of 2,135 permanent immigrants a year against hors-RMR's own 4,669. The operand this rate multiplies is the second number; the rate was measured over a territory carrying both.

(9 cells are published as `...` — the terminal year of a (t)→(t+1) flow table — and are excluded from the closure rather than coerced to a number.)

## 3. The census side is INSEPARABLE at CMA grain, and no cube with this cross publishes the part

`98-10-0621-01` carries exactly 1 member naming Gatineau: `Ottawa - Gatineau (CMA), Ont./Que.` (id 81, geoLevel 503, SGC 505), parented to `Ontario` (id 54). It is therefore NOT one of the six geoLevel-503 children of Quebec the residual is taken net of, and its Québec half stays inside the residual. There is no Québec-part member to subtract at this grain.

That absence is scoped to a search, not assumed. P9 closed the catalogue at **CLOSED-AT-MEMBER-LEVEL [cited: probes/P9-catalogue-closure.md DECISION-VERDICT, read this run]** and named the cubes carrying the maintainer × population-characteristics cross: **4 cubes — 98-10-0621-01, 98-10-0622-01, 98-10-0623-01, 98-10-0624-01 [cited: probes/P9-catalogue-closure.md DECISION-MAINTAINER-CROSS, read this run]**. This run scanned all four for a geography member at CMA-PART grain (geoLevel 505) or a name carrying both `Gatineau` and `part`:

| cube | geography members | at geoLevel 505 or named as a part |
|---|---:|---:|
| 98-10-0621-01 | 166 | 0 |
| 98-10-0622-01 | 5,468 | 0 |
| 98-10-0623-01 | 166 | 0 |
| 98-10-0624-01 | 5,468 | 0 |

`43-10-0060-01` DOES publish it — `Ottawa–Gatineau (Quebec part) (CMA), Ontario/Quebec` (id 16, geoLevel 505, SGC 24505) — and cannot serve, for a reason that is structural rather than a preference: its dimensions are `Geography`, `Gender`, `Age group and first official language spoken`, `Immigrant and generation status`, `Visible minority`, `Highest certificate, diploma or degree`, `Indicators`. There is no household-maintainer axis and no count statistic; its indicators are person-weighted PERCENTAGES. Reading the ruled maintainer-denominated quantities off it is exactly the metric transport ruling S eliminated. The residual carried from P9 stands: **vocabulary-scoped; English member/dimension names only; StatCan WDS only [cited: probes/P9-catalogue-closure.md DECISION-RESIDUAL, read this run]**.

## 4. The EXACT construction — the CMA's Québec-part membership, resolved live

`98-10-0003-01` publishes `Ottawa - Gatineau` (id 594, geoLevel 503, SGC 505) with its constituent census subdivisions as geography-dimension CHILDREN. This run reads that hierarchy: 25 children, of which 16 carry a Québec SGC code.

### 4a. The children CLOSE on the CMA — a partition, not a selection

Their 2021 populations sum to 1,488,307 against the CMA's own 1,488,307 — EXACTLY, with the Québec side at 353,293 and the Ontario side at 1,135,014. A child list that did not close on its own parent would make 'the Québec side of this CMA' a slice of an unknown whole, so the closure is a refusal condition rather than a remark.

### 4b. The Québec side, selected TWO ways

Every one of the 25 children is classified twice: by SGC prefix (`24`) and STRUCTURALLY, by asking whether the same SGC code resolves in `98-10-0622-01` to a geoLevel-5 member whose census division is a child of that cube's Quebec member. The two agree on all 25; a disagreement refuses the run. The Québec-side members, with the census division each sits in — four different CDs, which is why no whole-CD union is this territory:

| SGC | census subdivision | census division | settled persons | maintainers | owner-maintainers |
|---|---|---|---:|---:|---:|
| 2480050 | Thurso | Papineau (SGC 2480) | 20 | 15 | 10 |
| 2480055 | Lochaber | Papineau (SGC 2480) | 15 | 10 | 10 |
| 2480060 | Lochaber-Partie-Ouest | Papineau (SGC 2480) | 25 | withheld (≤ 10) | withheld (≤ 5) |
| 2480065 | Mayo | Papineau (SGC 2480) | withheld (≤ 5) | withheld (≤ 0) | withheld (≤ 5) |
| 2480085 | Mulgrave-et-Derry | Papineau (SGC 2480) | 15 | withheld (≤ 15) | withheld (≤ 10) |
| 2480140 | Val-des-Bois | Papineau (SGC 2480) | withheld (≤ 5) | withheld (≤ 5) | withheld (≤ 5) |
| 2480145 | Bowman | Papineau (SGC 2480) | withheld (≤ 0) | withheld (≤ 0) | withheld (≤ 0) |
| 2481017 | Gatineau | Gatineau (SGC 2481) | 34,270 | 17,465 | 10,190 |
| 2482005 | L'Ange-Gardien | Les Collines-de-l'Outaouais (SGC 2482) | 105 | 55 | 55 |
| 2482010 | Notre-Dame-de-la-Salette | Les Collines-de-l'Outaouais (SGC 2482) | 20 | withheld (≤ 5) | withheld (≤ 5) |
| 2482015 | Val-des-Monts | Les Collines-de-l'Outaouais (SGC 2482) | 410 | 200 | 180 |
| 2482020 | Cantley | Les Collines-de-l'Outaouais (SGC 2482) | 570 | 270 | 255 |
| 2482025 | Chelsea | Les Collines-de-l'Outaouais (SGC 2482) | 670 | 320 | 305 |
| 2482030 | Pontiac | Les Collines-de-l'Outaouais (SGC 2482) | 175 | 100 | 95 |
| 2482035 | La Pêche | Les Collines-de-l'Outaouais (SGC 2482) | 370 | 205 | 170 |
| 2483005 | Denholm | La Vallée-de-la-Gatineau (SGC 2483) | withheld (≤ 10) | withheld (≤ 5) | withheld (≤ 5) |

`Gatineau` names both the census division (id 1943, geoLevel 3) and the city inside it (id 1944, geoLevel 5); every member above is resolved by SGC code AND geoLevel, so the two cannot be confused.

### 4c. The membership, VALIDATED against the ISQ row it aligns to

Like-for-like, with no universe transport inside the comparison: census TOTAL population against ISQ's TOTAL-population estimate. The resolved Québec part measures 353,293 against ISQ's 355,971 — **-0.752%**. The threshold is DERIVED from innocent controls measured the same way, the six wholly-QC CMAs, whose census↔ISQ identity is not in question:

| geography | census 2021 population | ISQ July-1 2021 | residual |
|---|---:|---:|---:|
| Drummondville (CMA), Que. | 101,610 | 102,356 | -0.729% |
| Montréal (CMA), Que. | 4,291,732 | 4,330,143 | -0.887% |
| Québec (CMA), Que. | 839,311 | 844,774 | -0.647% |
| Saguenay (CMA), Que. | 161,567 | 162,376 | -0.498% |
| Sherbrooke (CMA), Que. | 227,398 | 229,294 | -0.827% |
| Trois-Rivières (CMA), Que. | 161,489 | 162,531 | -0.641% |
| **Ottawa-Gatineau, Québec part (resolved here)** | **353,293** | **355,971** | **-0.752%** |

The largest innocent |residual| is 0.887% (Montréal (CMA), Que.); the threshold is that maximum plus 25% of it — 1.109%. The resolved part sits INSIDE the innocent spread, not merely under the bound: 2 of the 6 controls are further out. What this gate CANNOT do: it bounds the census-vs-July-1 estimate gap, it does not separate that gap from a membership difference — a difference smaller than 3,947 persons would not be seen.

### 4d. Suppression: BOUNDED by the published complement, never dropped

StatCan withholds small counts. Of the cells this run requested at the 16 Québec-part CSDs, 31 came back with no data point, at 8 of the 16 subdivisions — all of them rural municipalities of at most 926 people. Two cubes are involved and each bounds its own, so the split is stated rather than averaged: 13 of them are maintainer-age cells of `98-10-0232-01`, bounded against that cube's own unpublished remainder and carried in §6. The other 18 are settled-immigrant counts of `98-10-0622-01`, and they are neither dropped nor guessed: each is bounded above by a quantity the same cube DOES publish at the same geography — `Total - Age` minus `Non-immigrants`, i.e. all immigrants and non-permanent residents together, which contains `Before 2016` by construction. Both ends are carried to the published figures:

- FIELD-WISE, because these subdivisions publish some counts of a triple and withhold others: 18 of the 48 settled-member counts are withheld, at 7 subdivisions, and a published count is never discarded because a neighbouring one in the same triple is missing.
- subtracting only what is published: persons 36,665, maintainers 18,640, owner-maintainers 11,270;
- suppressed at their bound (subtract most): persons 36,685, maintainers 18,680, owner-maintainers 11,305;
- the complement is EMPTY at 1 of those 7, where the cube publishes the same total and non-immigrant count: the withheld cell is bounded at zero rather than estimated, and 0 fields needed the bound clamped for a rounding-step negative.
- the whole withheld mass is at most 20 persons against a subtraction of 36,665.

## 5. The ALIGNED immigrant inputs

| construction | settled persons | maintainers | owner-maintainers | HEADSHIP | non-imm propensity | settled propensity | RATIO |
|---|---:|---:|---:|---:|---:|---:|---:|
| as shipped (Gatineau IN) | 84,785 | 43,825 | 29,355 | 0.5169 | 0.6977 | 0.6698 | 0.9600 |
| **ALIGNED (published counts only)** | 48,120 | 25,185 | 18,085 | 0.5234 | 0.7007 | 0.7181 | 1.0248 |
| aligned, every withheld field at its bound | 48,100 | 25,145 | 18,050 | 0.5228 | 0.7007 | 0.7178 | 1.0244 |

**Aligned: headship 0.5234 (+1.254%), ratio 1.0248 (+6.744%) — and the ratio CROSSES 1.0.** Shipped, settled immigrants under-own in hors-RMR; aligned, they out-own. The suppression bound is [1.0228, 1.0264] on the ratio and [0.5225, 0.5236] on the headship — taken at the box's OPPOSITE corners (headship is largest when the fewest maintainers and the most persons are netted out), so it is the envelope rather than the two sums paired. Neither end straddles 1.0, which is a refusal condition here, not a remark.

The two factors MULTIPLY inside D_imm and their errors are same-signed, so the immigrant demand leg moves by their product: **+8.083%**. The contaminant's size explains it — CD Gatineau alone holds 40.420% of the shipped residual's settled persons against a 10.770% share of its persons and 10.336% of its maintainers, and the full Québec part holds 43.245% against 13.107%. (Amendment #12(A) states that weight's counterpart as 10.35% [cited: spec §6 amendment #12(A), verbatim] — a PERSON weight — and draws 3.9× [cited: spec §6 amendment #12(A), verbatim] from it. Measured, 10.35% is CD Gatineau's MAINTAINER share (10.336%); its person share is 10.770%. The concentration multiple is 3.91× at the maintainer denominator and 3.75× at the person one, so the amendment's figure is the maintainer reading; the label is what moves, and the multiple with it.)

### 5a. The whole-CD bracket, as sensitivity — and what it would have missed

The mandate's fallback construction, measured anyway, because a bracket is only judgeable beside the exact value it was standing in for:

| construction | settled persons | HEADSHIP | RATIO | residual persons |
|---|---:|---:|---:|---:|
| − Gatineau (2481) | 50,515 | 0.5218 | 1.0320 | 2,367,100 |
| − Gatineau (2481) + Les Collines-de-l'Outaouais (2482) | 48,210 | 0.5228 | 1.0242 | 2,312,815 |
| − Gatineau (2481) + Les Collines-de-l'Outaouais (2482) + Papineau (2480) | 47,790 | 0.5218 | 1.0230 | 2,288,830 |
| **exact (16 QC-part CSDs)** | **48,120** | **0.5234** | **1.0248** | **2,305,105** |

The whole-CD range is 0.5218-0.5228 on the headship and 1.0230-1.0320 on the ratio, and it contains 1 of the two exact values: the ratio INSIDE, the headship OUTSIDE. That is the measured cost of the fallback construction, and it is structural rather than bad luck: FOUR census divisions contribute to this CMA and no union of whole ones equals it — CD Gatineau entire, all seven Les Collines municipalities, seven of Papineau's and one of La Vallée-de-la-Gatineau's — so every whole-CD variant is simultaneously short of one territory and long on another.

## 6. The OWNERSHIP propensity — SIZED here, and not corrected

Amendment #12(B) rules that HORS_RMR's ownership propensity ρ is NOT to be corrected, because a BAND-UNIFORM relative scaling of ρ cancels exactly in ED. The premise is the claim, so it is measured — in the model's OWN lattice: `98-10-0231-01` is the cube `loaders/census.py` reads, `98-10-0232-01` is its CSD sibling (province rows bit-identical on the all-ages pair of counts the guard binds — the four bands are subtracted across the pair too, at granularities the two cubes do not share, and are NOT asserted identical), and the bands are `census._AGE_BAND_SPEC`'s own.

| band | shipped households | shipped owners | ρ shipped | ρ aligned | relative Δ | withheld CSD cells |
|---|---:|---:|---:|---:|---:|---:|
| all ages | 1,223,585 | 845,355 | 0.6909 | 0.6972 | **+0.918%** | 0 |
| 25-54 | 522,535 | 355,560 | 0.6805 | 0.6901 | **+1.425%** | 0 |
| 55-64 | 275,450 | 205,915 | 0.7476 | 0.7499 | **+0.315%** | 0 |
| 65-74 | 240,310 | 175,595 | 0.7307 | 0.7329 | **+0.304%** | 0 |
| 75+ | 153,430 | 99,915 | 0.6512 | 0.6527 | **+0.223%** | 13 |

**The band-uniform premise is FALSE in its strict form.** The four model bands' relative contamination runs +0.223% to +1.425% — a spread of 1.202 percentage points, wider than the aggregate move itself. The shape is two-valued rather than noisy: 25-54 carries +1.425% and the three older bands sit within 0.092 pp of each other.

**What that costs in ED is NOT bounded by the spread, and the arithmetic says so.** ED = (D − S) / OwnerStock is linear in ρ through every term, so under ρ(a) → ρ(a)(1 + δ(a)) each of D, S and OwnerStock picks up its own ρ-weighted mean of δ and, to first order,

```
ΔED / ED  =  (δ_S − δ_OS)  +  (δ_D − δ_S) × D / (D − S)
```

The first term lies inside the spread. The SECOND does not: its multiplier is GROSS demand over NET excess demand, which is ≈1 only when |ED| is of the order of D / OwnerStock and grows without bound as the two flows approach balance — the regime this module exists to measure. The numerator of ED is a DIFFERENCE of flows, so a band-varying δ is amplified there rather than averaged. What the spread does bound is the ABSOLUTE move, |ΔED| ≤ 1.202% × (D + |D − S|) / OwnerStock: second-order in ED's own units, and of unmeasured size RELATIVE to ED. Both D/(D−S) and D/OwnerStock are outputs of the model, not quantities this probe reads, so it prices what it can and names what it cannot.

**And the structure is adverse rather than neutral.** The band carrying the largest contamination is 25-54 at +1.425% — the band D_native is built from — while S rides ρ(75+) through `initialize_households`, the band carrying the SMALLEST at +0.223%. So δ_D − δ_S sits at or near the FULL spread rather than near zero, which is the worst arrangement of these four numbers for a cancellation argument. **This run therefore does not certify #12(B)'s cost/signal conclusion: it measures the premise FALSE and leaves the consequence sized by a quantity outside the probe.** (The withheld CSD cells reach only the 75+ band: netting them out at their bound instead of leaving them unsubtracted moves that band's Δ to +0.213%, widening the spread to 1.212 — the adverse structure holds at either end.)

Two things this measurement does NOT say. It does not say the correction is unavailable: `98-10-0232-01` publishes the identical cross at CSD grain, so an aligned ρ curve is extractable — what #12(B) rules is a cost/signal judgment, not a data absence. And it does not say the SIGN is safe: for D < S — the decline regime the module exists to measure — the multiplier D/(D − S) is NEGATIVE and unbounded near balance, so a large enough amplification carries ED across zero rather than merely rescaling it, and rank 1 is the most negative mean ED. How close to balance this geography runs is the model's output, not this probe's. Two cubes, one answer: the RULED cube (98-10-0621-01, maintainer counts crossed with population characteristics rather than with maintainer age) puts the same all-households contamination at +0.918%, against the +0.918% the ownership pair measures — different cubes, different crosses, the same figure. Under the whole-CD construction it reads +1.490%, which is the figure amendment #12(B) states.

## 7. Rounding, and the universe conversion, stated as approximations

- Every count is rounded to 5 INDEPENDENTLY per cube. The aligned settled triple is a province cell minus 6 CMA cells minus 16 CSD cells — 23 rounded cells — so its worst-case rounding envelope is ±46 persons against a base of 48,120: it moves the fourth decimal of the headship at most.
- The two cube pairs' province rows are bit-identical on the RULED `Before 2016` triple and on the ρ pair's all-ages row — the two identities the guards bind, not a cube-wide one — and differ by no more than 5 elsewhere: 1 province cell measured as drifting (`Non-immigrants` maintainers 3,058,105 vs 3,058,100), and anything beyond the rounding step refuses the run. That cell is not idle: the aligned non-immigrant propensity subtracts a `Non-immigrants` triple across the pair too, so the drift enters its denominator — at 5 in 1,038,750 it moves neither published figure at the resolution this note prints them.
- The private-household universe is NOT the total-population universe, and the conversion between them is an approximation that carries a LOCAL error. This tree records the province-wide gap in `loaders/constants.py` — 8,308,475 private-household persons vs 8,501,833 published [cited: loaders/constants.py, verbatim] — i.e. a ratio of 0.9773, at which ISQ's Gatineau row converts to 347,875; §6 states that conversion as ≈345,000 [cited: spec §6 amendment #12(A), verbatim]. The resolved membership actually carries 347,710 private-household persons — a LOCAL ratio of 0.9842, above the province-wide one, which is why the measured figure lands above both conversions. Nothing in this note's arithmetic uses the conversion: the membership is validated total-against-total in §4c and the immigrant inputs are private-household on both sides of every ratio.

## 8. Scope

MEASURE ONLY. This run wires nothing: `demand/immigrant_inputs.py`, `probes/run_p8.py` and `probes/P8-immigrant-inputs.md` are untouched, and the ruled §6 table still carries 0.5169 / 0.9600 — which this run RECOMPUTES and agrees with, as the contaminated measurement it is. The aligned values above are proposed to the spec, not applied: P8's note is citation-coupled to §6's stated figures, so wiring before the ruling would couple that note to numbers the ruling no longer carries. Order: spec, then P8, then the join table.

## DECISION

- `DECISION-VERDICT: MEASURED`
- `DECISION-CONSTRUCTION: EXACT — province 98-10-0621-01 NET of the six geoLevel-503 children of Quebec, NET of the 16 Québec-side census subdivisions of 98-10-0003-01's Ottawa-Gatineau CMA member 594, read from 98-10-0622-01`
- `DECISION-ALIGNED-HEADSHIP: 0.5234 (envelope 0.5225-0.5236) — shipped 0.5169, +1.254%`
- `DECISION-ALIGNED-RATIO: 1.0248 (envelope 1.0228-1.0264) — shipped 0.9600, +6.744%, CROSSES 1.0`
- `DECISION-IMMIGRANT-LEG: headship × ratio moves +8.083% — D_imm understated by that much at HORS_RMR, ED understated, rank-1-is-most-negative so the geography is ranked MORE RISKY than truth`
- `DECISION-BRACKET: −Gatineau 0.5218/1.0320; −Les Collines-de-l'Outaouais 0.5228/1.0242; −Papineau 0.5218/1.0230 — cumulative whole-CD variants, published as sensitivity`
- `DECISION-BRACKET-ENCLOSURE: ratio INSIDE, headship OUTSIDE the whole-CD range — the fallback construction could not have produced the exact headship`
- `DECISION-MEMBERSHIP: 25 children close EXACTLY on the CMA (1,488,307); 16 Québec-side by SGC prefix AND by census-tree ancestry, agreeing on all 25`
- `DECISION-MEMBERSHIP-GATE: PASS — resolved Québec part 353,293 vs ISQ 355,971 = -0.752%, against a threshold of 1.109% derived from the six wholly-QC CMAs (0.887% max innocent + 25%)`
- `DECISION-SUPPRESSION: 31 withheld cells across both cubes; 18 of the 48 settled-member counts, at 7/16 QC-part CSDs; bounded FIELD-WISE above by Total - Age − Non-immigrants at the same geography; envelope width 0.0036 on the ratio and 0.0010 on the headship, straddling nothing`
- `DECISION-ISQ-SEPARABILITY: MEASURED — compo-rmr-base.xlsx's 8 regional rows close on its province row within 3/yr with Gatineau as its own row (footnote: 2. Partie québécoise uniquement.); hors-RMR mean 4,669 vs the Gatineau row's 2,135 permanents/yr`
- `DECISION-CENSUS-INSEPARABILITY: 98-10-0621-01 member 81 `Ottawa - Gatineau (CMA), Ont./Que.` at geoLevel 503 parented to Ontario (54) — one member, no Québec-part member at this grain`
- `DECISION-DIRECT-SOURCE: ABSENT across the 4 maintainer-cross cubes P9 names, scanned live at geoLevel 505 and by name; 43-10-0060-01 publishes the part (member 16) but carries no maintainer axis and person-weighted percentages — the metric transport ruling S eliminated`
- `DECISION-RHO-CONTAMINATION: all ages +0.918%; 25-54 +1.425%; 55-64 +0.315%; 65-74 +0.304%; 75+ +0.223% — 98-10-0231-01/98-10-0232-01 in census._AGE_BAND_SPEC's own bands`
- `DECISION-RHO-VERDICT: the band-uniform premise of #12(B) is FALSE as measured — spread 1.202 pp across the four model bands, all same-signed and STRUCTURALLY ADVERSE (D_native's 25-54 band carries +1.425%, the 75+ band S rides carries +0.223%, so δ_D − δ_S is at or near the full spread). ΔED/ED = (δ_S − δ_OS) + (δ_D − δ_S)·D/(D−S): second-order in ED's OWN UNITS (|ΔED| ≤ 1.202% × (D + |D−S|)/OwnerStock) but amplified RELATIVE to ED by D/(D−S), a model output this probe does not read and which grows without bound near flow balance. This run PRICES the contamination and does NOT certify #12(B)'s cost/signal conclusion. NOT a data absence: 98-10-0232-01 publishes the aligned curve's other half`
- `DECISION-CATALOGUE-CLOSURE: CLOSED-AT-MEMBER-LEVEL at dimension names AND every member name, all 8226 catalogue cubes — residual vocabulary-scoped; English member/dimension names only; StatCan WDS only (read from probes/P9-catalogue-closure.md this run, not restated)`
- `DECISION-SCOPE: MEASURE ONLY — nothing wired by this run; demand/immigrant_inputs.py, probes/run_p8.py and probes/P8-immigrant-inputs.md are untouched and the aligned values are NOT in the spec. Spec ruling first, then P8's regeneration, then the join table`

