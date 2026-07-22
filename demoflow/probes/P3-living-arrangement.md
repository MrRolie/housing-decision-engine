# P3 — Census living-arrangement cross-tab hunt (RECORDED OBSERVATION)

Written by `probes/run_p3.py`; nothing in this file is hand-edited.

Every table in §2-§4 is generated row by row from the live WDS responses of the run that wrote this file.
Of the 6 narrative figures in §5, 6 are DERIVED (computed from live responses in this same run, each naming its source) and 0 are CITED (external to this run, printed with the citation inline).

## 1. Catalogue sweep (so a NOT-FOUND would be credible)

- `getAllCubesListLite` -> 8212 cubes in catalogue.
- Census-2021 (`981*`) cubes whose title mentions ['living arrangement', 'household living', 'household type of person']: `['98100081', '98100082', '98100134', '98100137', '98100147', '98100656', '98100657']`

Candidates probed (plan's three first, then sweep hits): `['98100134', '98100026', '98100040', '98100081', '98100082', '98100137', '98100147', '98100656', '98100657']`

## 2. Metadata probe — dimension lists verbatim

### 98100134 — QUALIFIES
- title: Census family status and household living arrangements, household type of person, age group and gender: Canada, provinces and territories, census metropolitan areas and census agglomerations
- release: 2022-07-13T08:30 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Gender (3a)', 'Age group (11)', 'Census year (3)', 'Census family status and household living arrangements (11)', 'Household type of person (10)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): True
  - a member 'Persons living alone' (living_alone numerator): True
  - a member 'Married spouses and common-law partners' (couple_share numerator): True

  Living-arrangement members of 98100134:
    - Total - Census family status and household living arrangements
    - Persons in census families
    - Married spouses and common-law partners
    - Married spouses
    - Common-law partners
    - Parents in one-parent families
    - Children in census families
    - Persons not in census families
    - Persons living with other relatives
    - Persons living with non-relatives only
    - Persons living alone

### 98100026 — does not qualify
- title: Age (in single years), average age and median age and gender: Canada, provinces and territories and economic regions
- release: 2022-04-27T08:30 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Age (in single years), average age and median age (128)', 'Gender (3)']
  - geography dimension with CMA members: False
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): True
  - a member 'Persons living alone' (living_alone numerator): False
  - a member 'Married spouses and common-law partners' (couple_share numerator): False

### 98100040 — does not qualify
- title: Structural type of dwelling and household size: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts
- release: 2022-04-27T08:30 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Structural type of dwelling (9)', 'Household size (8)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: False (dimension absent)
  - age dimension resolving 75+ (a '75' band and an '85' band): False
  - a member 'Persons living alone' (living_alone numerator): False
  - a member 'Married spouses and common-law partners' (couple_share numerator): False

### 98100081 — does not qualify
- title: Total income groups by household living arrangements for persons not in economic families: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts
- release: 2022-07-13T08:30 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Household living arrangements for persons not in economic families (3)', 'Age (9)', 'Gender (3a)', 'Presence of earner (3)', 'Total income groups (21)', 'Year (2)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): False
  - a member 'Persons living alone' (living_alone numerator): False
  - a member 'Married spouses and common-law partners' (couple_share numerator): False

### 98100082 — does not qualify
- title: After-tax income groups by household living arrangements for persons not in economic families: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts
- release: 2022-07-13T08:30 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Household living arrangements for persons not in economic families (3)', 'Age (9)', 'Gender (3a)', 'Presence of earner (3)', 'After-tax income group (18)', 'Year (2)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): False
  - a member 'Persons living alone' (living_alone numerator): False
  - a member 'Married spouses and common-law partners' (couple_share numerator): False

### 98100137 — does not qualify
- title: Census family status and household living arrangements, presence of parent in household, age group and gender: Canada, provinces and territories, census metropolitan areas and census agglomerations
- release: 2023-12-07T08:35 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Census year (3)', 'Gender (3a)', 'Age group (4)', 'Census family status and household living arrangements (11)', 'Presence of parent in household (3)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): False
  - a member 'Persons living alone' (living_alone numerator): True
  - a member 'Married spouses and common-law partners' (couple_share numerator): True

### 98100147 — does not qualify
- title: Military family structure and household living arrangements: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts
- release: 2023-11-15T08:30 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Number of children (6)', 'Age of youngest child (7)', 'Age (15D)', 'Gender (3)', 'Statistics (3)', 'Census family status and household living arrangements (6)', 'Military service status (4A)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): False
  - a member 'Persons living alone' (living_alone numerator): False
  - a member 'Married spouses and common-law partners' (couple_share numerator): True

### 98100656 — does not qualify
- title: Labour force status by visible minority, household type of person and selected characteristics: Canada, provinces and territories and census metropolitan areas with parts
- release: 2025-01-02T08:45 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Gender (3)', 'Age (11B)', 'Immigrant and generation status (9)', 'Visible minority (15)', 'Religion (10)', 'Household type of person (10)', 'Labour force status (3A)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): False
  - a member 'Persons living alone' (living_alone numerator): False
  - a member 'Married spouses and common-law partners' (couple_share numerator): False

### 98100657 — does not qualify
- title: Household type of person by visible minority, religion and selected characteristics: Canada, provinces and territories and census metropolitan areas with parts
- release: 2024-12-04T08:30 | status: CURRENT - a cube available to the public and that is current
- dimensions = ['Geography', 'Gender (3)', 'Age (13C)', 'Marital status (9)', 'Generation status (4)', 'Religion (10)', 'Household type of person (10)', 'Visible minority (15)']
  - geography dimension with CMA members: True
  - sex/gender dimension with >=2 non-total members: True (['Total - Gender', 'Men+', 'Women+'])
  - age dimension resolving 75+ (a '75' band and an '85' band): False
  - a member 'Persons living alone' (living_alone numerator): False
  - a member 'Married spouses and common-law partners' (couple_share numerator): False

## 3. Live data probe — values at CMA x age x SEX

A cube being SHAPED right does not prove values survive at this granularity; small
cells get suppressed. The verdict below is written only after real values return for
every required cell across all 7 wholly-Québec geographies.

- **98100134**: pulled 126 coordinates; 42/42 (geo x sex x age) cells resolve BOTH rates.
- `LIVE PROBE VERDICT: FOUND-AT-CMA` on productId 98100134.

## 4. Derived per-sex rates — Census 2021, productId 98100134

`living_alone = alone / pop`; `couple_share = coupled / (pop - alone)` — conditional
on NOT living alone, matching spec §5 `coupled_s = pop_s x (1 - living_alone_s) x couple_share_s`.
Universe is persons in PRIVATE households (see §5 below), which is the denominator
the spec's partition requires.

| geography | sex | age | pop | living alone | coupled | living_alone | couple_share |
|---|---|---|---:|---:|---:|---:|---:|
| Quebec | Men+ | 65 to 74 years | 472,160 | 108,680 | 331,475 | 0.2302 | 0.9119 |
| Quebec | Men+ | 75 to 84 years | 227,135 | 52,075 | 160,525 | 0.2293 | 0.9170 |
| Quebec | Men+ | 85 years and over | 53,520 | 15,900 | 31,905 | 0.2971 | 0.8481 |
| Quebec | Women+ | 65 to 74 years | 505,355 | 160,060 | 294,415 | 0.3167 | 0.8526 |
| Quebec | Women+ | 75 to 84 years | 261,520 | 112,260 | 115,760 | 0.4293 | 0.7756 |
| Quebec | Women+ | 85 years and over | 80,300 | 45,565 | 14,905 | 0.5674 | 0.4291 |
| Montréal (CMA), Que. | Men+ | 65 to 74 years | 193,870 | 42,735 | 135,550 | 0.2204 | 0.8969 |
| Montréal (CMA), Que. | Men+ | 75 to 84 years | 98,450 | 21,165 | 70,150 | 0.2150 | 0.9077 |
| Montréal (CMA), Que. | Men+ | 85 years and over | 26,800 | 7,495 | 16,295 | 0.2797 | 0.8441 |
| Montréal (CMA), Que. | Women+ | 65 to 74 years | 221,985 | 72,630 | 120,855 | 0.3272 | 0.8092 |
| Montréal (CMA), Que. | Women+ | 75 to 84 years | 121,640 | 52,835 | 50,195 | 0.4344 | 0.7295 |
| Montréal (CMA), Que. | Women+ | 85 years and over | 41,385 | 22,965 | 7,390 | 0.5549 | 0.4012 |
| Québec (CMA), Que. | Men+ | 65 to 74 years | 47,450 | 10,870 | 34,290 | 0.2291 | 0.9374 |
| Québec (CMA), Que. | Men+ | 75 to 84 years | 23,285 | 5,330 | 16,870 | 0.2289 | 0.9396 |
| Québec (CMA), Que. | Men+ | 85 years and over | 4,850 | 1,560 | 2,920 | 0.3216 | 0.8875 |
| Québec (CMA), Que. | Women+ | 65 to 74 years | 53,705 | 18,955 | 31,150 | 0.3529 | 0.8964 |
| Québec (CMA), Que. | Women+ | 75 to 84 years | 27,905 | 13,010 | 12,535 | 0.4662 | 0.8416 |
| Québec (CMA), Que. | Women+ | 85 years and over | 7,580 | 4,765 | 1,470 | 0.6286 | 0.5222 |
| Saguenay (CMA), Que. | Men+ | 65 to 74 years | 11,340 | 2,465 | 8,290 | 0.2174 | 0.9341 |
| Saguenay (CMA), Que. | Men+ | 75 to 84 years | 5,070 | 1,135 | 3,665 | 0.2239 | 0.9314 |
| Saguenay (CMA), Que. | Men+ | 85 years and over | 1,175 | 410 | 645 | 0.3489 | 0.8431 |
| Saguenay (CMA), Que. | Women+ | 65 to 74 years | 11,335 | 3,370 | 7,185 | 0.2973 | 0.9021 |
| Saguenay (CMA), Que. | Women+ | 75 to 84 years | 5,820 | 2,490 | 2,745 | 0.4278 | 0.8243 |
| Saguenay (CMA), Que. | Women+ | 85 years and over | 1,705 | 1,025 | 325 | 0.6012 | 0.4779 |
| Sherbrooke (CMA), Que. | Men+ | 65 to 74 years | 13,095 | 3,230 | 9,165 | 0.2467 | 0.9290 |
| Sherbrooke (CMA), Que. | Men+ | 75 to 84 years | 6,515 | 1,520 | 4,680 | 0.2333 | 0.9369 |
| Sherbrooke (CMA), Que. | Men+ | 85 years and over | 1,450 | 435 | 885 | 0.3000 | 0.8719 |
| Sherbrooke (CMA), Que. | Women+ | 65 to 74 years | 14,455 | 5,180 | 8,260 | 0.3584 | 0.8906 |
| Sherbrooke (CMA), Que. | Women+ | 75 to 84 years | 7,515 | 3,400 | 3,475 | 0.4524 | 0.8445 |
| Sherbrooke (CMA), Que. | Women+ | 85 years and over | 2,185 | 1,350 | 445 | 0.6178 | 0.5329 |
| Trois-Rivières (CMA), Que. | Men+ | 65 to 74 years | 10,665 | 2,770 | 7,295 | 0.2597 | 0.9240 |
| Trois-Rivières (CMA), Que. | Men+ | 75 to 84 years | 5,185 | 1,290 | 3,620 | 0.2488 | 0.9294 |
| Trois-Rivières (CMA), Que. | Men+ | 85 years and over | 1,045 | 330 | 620 | 0.3158 | 0.8671 |
| Trois-Rivières (CMA), Que. | Women+ | 65 to 74 years | 11,550 | 4,095 | 6,575 | 0.3545 | 0.8820 |
| Trois-Rivières (CMA), Que. | Women+ | 75 to 84 years | 6,020 | 2,685 | 2,745 | 0.4460 | 0.8231 |
| Trois-Rivières (CMA), Que. | Women+ | 85 years and over | 1,695 | 1,025 | 325 | 0.6047 | 0.4851 |
| Drummondville (CMA), Que. | Men+ | 65 to 74 years | 6,305 | 1,535 | 4,370 | 0.2435 | 0.9161 |
| Drummondville (CMA), Que. | Men+ | 75 to 84 years | 2,845 | 675 | 1,985 | 0.2373 | 0.9147 |
| Drummondville (CMA), Que. | Men+ | 85 years and over | 510 | 170 | 285 | 0.3333 | 0.8382 |
| Drummondville (CMA), Que. | Women+ | 65 to 74 years | 6,660 | 2,235 | 3,945 | 0.3356 | 0.8915 |
| Drummondville (CMA), Que. | Women+ | 75 to 84 years | 3,190 | 1,380 | 1,480 | 0.4326 | 0.8177 |
| Drummondville (CMA), Que. | Women+ | 85 years and over | 770 | 480 | 140 | 0.6234 | 0.4828 |

### 4b. Couple-balance observation — a finding for Task 15b, recorded RAW

Spec §5 carries a data-sanity gate `|coupled_m - coupled_f| / max <= 0.25`
(breach => CalibrationError). Evaluated on these RAW Census counts:

| geography | age | coupled_m | coupled_f | \|diff\|/max | vs 0.25 gate |
|---|---|---:|---:|---:|---|
| Quebec | 65 to 74 years | 331,475 | 294,415 | 0.1118 | ok |
| Quebec | 75 to 84 years | 160,525 | 115,760 | 0.2789 | BREACH |
| Quebec | 85 years and over | 31,905 | 14,905 | 0.5328 | BREACH |
| Montréal (CMA), Que. | 65 to 74 years | 135,550 | 120,855 | 0.1084 | ok |
| Montréal (CMA), Que. | 75 to 84 years | 70,150 | 50,195 | 0.2845 | BREACH |
| Montréal (CMA), Que. | 85 years and over | 16,295 | 7,390 | 0.5465 | BREACH |
| Québec (CMA), Que. | 65 to 74 years | 34,290 | 31,150 | 0.0916 | ok |
| Québec (CMA), Que. | 75 to 84 years | 16,870 | 12,535 | 0.2570 | BREACH |
| Québec (CMA), Que. | 85 years and over | 2,920 | 1,470 | 0.4966 | BREACH |
| Saguenay (CMA), Que. | 65 to 74 years | 8,290 | 7,185 | 0.1333 | ok |
| Saguenay (CMA), Que. | 75 to 84 years | 3,665 | 2,745 | 0.2510 | BREACH |
| Saguenay (CMA), Que. | 85 years and over | 645 | 325 | 0.4961 | BREACH |
| Sherbrooke (CMA), Que. | 65 to 74 years | 9,165 | 8,260 | 0.0987 | ok |
| Sherbrooke (CMA), Que. | 75 to 84 years | 4,680 | 3,475 | 0.2575 | BREACH |
| Sherbrooke (CMA), Que. | 85 years and over | 885 | 445 | 0.4972 | BREACH |
| Trois-Rivières (CMA), Que. | 65 to 74 years | 7,295 | 6,575 | 0.0987 | ok |
| Trois-Rivières (CMA), Que. | 75 to 84 years | 3,620 | 2,745 | 0.2417 | ok |
| Trois-Rivières (CMA), Que. | 85 years and over | 620 | 325 | 0.4758 | BREACH |
| Drummondville (CMA), Que. | 65 to 74 years | 4,370 | 3,945 | 0.0973 | ok |
| Drummondville (CMA), Que. | 75 to 84 years | 1,985 | 1,480 | 0.2544 | BREACH |
| Drummondville (CMA), Que. | 85 years and over | 285 | 140 | 0.5088 | BREACH |

13 of the rows above breach the gate. This is NOT a data defect and is NOT
resolved here: at 75+ the male coupled count genuinely exceeds the female one
(older men partner with younger women; women outlive men), so the surplus is real
population structure — exactly what spec §5's `Couple(a) = min(coupled_m, coupled_f)`
matching plus `max - min -> Other` was written to absorb.

**Open for Task 15b — stated, deliberately NOT resolved here.** The rows above are
the raw cited Census values; P3 neither calibrates them nor rules on where the gate
belongs. The tension 15b inherits: the gate is a TOLERANCE (<= 0.25), not an
equality, so it is satisfiable from either side within [0, 1] — but every such
adjustment moves a rate away from the cited Census figure, which sits against
§11.3's cited-or-raise rule. Choosing among calibrating, re-placing the gate, and
accepting the breach is 15b's call, not this probe's.

### 4c. Cross-check against the spec's named living_alone fallback

Census-derived Québec-province 65+ living-alone rate (both sexes pooled, the
vitrine's own universe): **0.3091** (30.9%).
The spec's ISQ vitrine point estimate is 0.28 with widened band
[0.24, 0.34]. Observed value inside that band: **True** — the widened band was correctly specified, and the direct Census
measurement supersedes it for every geography in the table above.

## 5. Universe, vintage, and the re-derivation recipe (for Task 15b)

- productId `98100134` = StatCan Table **98-10-0134-01**, 2021 Census, released
  2022-07-13T08:30. Vintage pinned here; a re-pull must reproduce these counts.
- **Universe is persons in PRIVATE households.** Measured, not assumed: this cube's
  Québec all-ages/all-genders total is 8,308,475 against the published 2021 Census
  Québec population of 8,501,833 — a 2.27% gap that is the collective /
  non-private-household population. So the rate denominators already exclude
  collectives, which is what spec §5's partition requires. (A 75+-SPECIFIC collective
  share is NOT derivable from this cube alone — it needs total population BY AGE — so
  Task 15's `collective_share_75plus` keeps its existing flag; P3 does not land it.)
- The cube's two independent definitions of living-alone **AGREE on every cell compared**: `Persons living alone`
  (living-arrangements dimension) vs `In a one-person household` (household-type dimension)
  — compared cell by cell, 42/42 geography x sex x age cells match.
- Living-arrangements hierarchy additivity: worst deviation 10 persons across the
  126 identities checked (21 component cells carry no published
  value and were counted as zero). Census random-rounds to base 5, so a small non-zero
  residual is EXPECTED — Task 15b must reconcile with a tolerance, never exact sums.
- Recipe: POST `getDataFromCubePidCoordAndLatestNPeriods` with a coordinate whose
  slots are the dimension-position-ordered member ids; hold `Census year` = 2021 and
  `Household type of person` = its Total member; vary geography, gender, age group,
  and the living-arrangements member across the three rows named in §4.

### 5b. Traps confirmed live (they bite the Task 15b loader too)

1. **Response order != request order.** Observed on this cube: keying results by
   `zip(requests, responses)` mislabels values (a province count lands on a CMA)
   and the output still looks plausible. Key on the coordinate the RESPONSE carries.
2. **`status: FAILED` cells with an empty `vectorDataPoint`** exist (e.g. women 85+
   under `Children in census families`). Blind `[0]` indexing raises mid-pull.
3. **Random rounding to base 5** — reconcile with a tolerance, never exact equality.

## DECISION — SEX-SPECIFIC rates required (living_alone AND couple_share by age x sex; r3-F1/r4-F1)

- `DECISION-FOUND-AT-CMA: YES`
  FOUND at CMA granularity: productId `98100134` (StatCan Table 98-10-0134-01)
  publishes living arrangements x age group x GENDER x geography, and the live pull
  returned non-suppressed values for all 7 wholly-Québec geographies at 75-84 and 85+
  for both Men+ and Women+. Both required rates come from this ONE table.

- PER-INPUT fallbacks (codex r4-F6 — the living-alone fallback CANNOT supply couple_share):
  * `living_alone` -> spec's named fallback is the ISQ vitrine 0.28 (65+, QC), widened band [0.24, 0.34] PER-SEX, flagged `borrowed_prior`.
    **NOT NEEDED** — §4 supplies directly measured per-sex, per-age, per-CMA rates,
    so the `borrowed_prior` flag does not attach to `living_alone` for any geography
    in that table. The constant stays defined for geographies outside it.
  * `couple_share` -> pinned at probe time WITH CITATION, below. The province-level
    fallback is likewise not needed: the cross-tab resolves at CMA granularity.

- `DECISION-COUPLE-SHARE-SOURCE: StatCan Table 98-10-0134-01 (WDS productId 98100134), member "Married spouses and common-law partners" over the not-living-alone population, by age group x gender x geography, 2021 Census`
- `DECISION-COUPLE-SHARE-CITATION: Statistics Canada. Table 98-10-0134-01, "Census family status and household living arrangements, household type of person, age group and gender: Canada, provinces and territories, census metropolitan areas and census agglomerations", 2021 Census, released 2022-07-13T08:30. https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810013401`
  * Quebec / 75 to 84 years: couple_share M=0.9170 F=0.7756 | living_alone M=0.2293 F=0.4293
  * Quebec / 85 years and over: couple_share M=0.8481 F=0.4291 | living_alone M=0.2971 F=0.5674
  * Montréal (CMA), Que. / 75 to 84 years: couple_share M=0.9077 F=0.7295 | living_alone M=0.2150 F=0.4344
  * Montréal (CMA), Que. / 85 years and over: couple_share M=0.8441 F=0.4012 | living_alone M=0.2797 F=0.5549
  * Québec (CMA), Que. / 75 to 84 years: couple_share M=0.9396 F=0.8416 | living_alone M=0.2289 F=0.4662
  * Québec (CMA), Que. / 85 years and over: couple_share M=0.8875 F=0.5222 | living_alone M=0.3216 F=0.6286

- Standing rule either way: if NEITHER the cross-tab NOR a citable couple_share exists,
  initialization RAISES (LoaderError). `couple_share` has NO invented default (spec §11.3).

