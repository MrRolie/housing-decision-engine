# P5b — Temporary-resident STOCK source pick (RECORDED OBSERVATION)

Written by `probes/run_p5b.py`; nothing in this file is hand-edited.

SCOPE OF THIS HEADER (it claims only what it can enforce): the catalogue size, the swept-candidate list, the resolved product id and title, the cadence label and its reference-period span, the archive status, the geography member COUNT and the member list, the CMA name-search results and the measure-type marker hits in §1-§3 are all emitted by this run from the live StatCan WDS responses — the cadence label is resolved from the live getCodeSets, never typed beside a raw frequency code. The footnote quotes are verbatim from the pick's live footnote list. §4 (IRCC / CKAN) and §5 (ISQ compo) are RECORDED COMPARISONS that do NOT gate the verdict: each states either its measured result or an explicit NOT MEASURED THIS RUN, and the pick's scope clause is a function of which. Every absence claim is scoped to what was swept.
This run registered 11 provenance-tagged figures: 8 DERIVED (computed from the live responses of this run) and 3 CITED (verbatim from the live cube footnotes). Untagged numerals elsewhere are audit metadata (candidate counts, resource counts, member counts, column indices) and reference labels (product ids, reference dates, the ISQ header/data row positions), each traceable to the live response or the named file this run read.

Quoted verbatim from the live response:
- point-in-time reference dates (the STOCK evidence) — live footnote of 17100121: "Estimates of the number of non-permanent residents: Q1 = January 1; Q2 = April 1; Q3 = July 1; Q4 = October 1."
- the definition of a non-permanent resident — live footnote of 17100121: "A non-permanent resident refers to a person from another country with a usual place of residence in Canada and who has a work or study permit or who has claimed refugee status (asylum claimants, protected persons and related groups). Family members living with work or study permit holders are also included unless these family members are already Canadian citizens, landed immigrants (permanent residents), or non-permanent residents themselves."
- the cross-programme comparison caution — live footnote of 17100121: "Statistics Canada collaborates closely with Immigration, Refugees and Citizenship Canada (IRCC) and other federal departments to estimate the number of non-permanent residents (NPRs) living in Canada. The demographic estimates from Statistics Canada are updated on an ongoing basis, as new or revised data become available from its partners. Caution should be exercised before comparing data on non-permanent residents from Statistics Canada's Demographic Estimates Program with temporary residents and asylum claimants from IRCC, due to the different objectives of the two data sources."

## 1. Catalogue sweep — the enumerated population the pick is earned over

- `getAllCubesListLite` -> **8214** cubes in the live StatCan catalogue.
- Sweep predicate over `cubeTitleEn` (case-insensitive phrase match). POPULATION terms ['non-permanent resident', 'non permanent resident', 'temporary resident'] make a cube PICK-ELIGIBLE; PERIPHERAL terms ['temporary foreign worker', 'study permit', 'work permit'] are swept too, so every absence claim below is scoped to a WIDER population than the pick pool.
- **10** titles matched; **5** of those matched a POPULATION term.
- Abbreviation check (why the predicate uses phrases, MEASURED not assumed): a bare `"npr"` substring predicate matches **4** catalogue titles, of which **0** also match a population term — so it contributes only term-collision noise (it matches the letters inside "nonprofit"), and no cube in this catalogue names the population by abbreviation alone.

**Every swept candidate, with the measured attributes the pick is decided on:**

| productId | title | terms matched | eligible |
|---|---|---|---|
| `17100023` | Estimates of non-permanent residents, quarterly, inactive | non-permanent resident | POPULATION |
| `17100044` | Estimates of non-permanent residents as of July 1st, by age and sex, inactive | non-permanent resident | POPULATION |
| `17100121` | Estimates of the number of non-permanent residents by type, quarterly | non-permanent resident | POPULATION |
| `17100158` | Estimates of the number of non-permanent residents on July 1, by age and gender | non-permanent resident | POPULATION |
| `32100218` | Temporary foreign workers in the agriculture and agri-food sectors, by industry | temporary foreign worker | peripheral only |
| `32100219` | Jobs filled by temporary foreign workers in the agriculture sector, and agricultural operations with at least one temporary foreign worker, by province | temporary foreign worker | peripheral only |
| `32100220` | Temporary foreign workers in the agriculture sector, by category of farm revenue | temporary foreign worker | peripheral only |
| `32100221` | Countries of citizenship for temporary foreign workers in the agricultural sector | temporary foreign worker | peripheral only |
| `33100678` | Business or organization hired workers from another country through the Temporary Foreign Worker Program in the last 12 months, second quarter of 2023 | temporary foreign worker | peripheral only |
| `98100361` | Non-permanent resident type by place of birth: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts | non-permanent resident | POPULATION |

## 2. Live metadata for every swept candidate (boundary `wds-meta`)

`getCubeMetadata` resolved **10** of the 10 swept product ids. Cadence labels are resolved from the live `getCodeSets` (17 frequency codes defined), never typed beside the raw code.

| productId | cadence (code) | reference span | archive status | geo members | (CMA)-marked | modeled CMAs found | stock markers | flow markers |
|---|---|---|---|---:|---:|---|---|---|
| `17100023` | Quarterly (9) | 1971-07-01..2018-04-01 | ARCHIVED -  a cube publicly available but no longer being updated | 15 | 0 | Montréal:0, Québec:0 | none | none |
| `17100044` | Annual (12) | 1971-01-01..2017-01-01 | ARCHIVED -  a cube publicly available but no longer being updated | 15 | 0 | Montréal:0, Québec:0 | as of | none |
| `17100121` | Quarterly (9) | 2021-07-01..2026-04-01 | CURRENT - a cube available to the public and that is current | 14 | 0 | Montréal:0, Québec:0 | number of | none |
| `17100158` | Annual (12) | 2021-01-01..2025-01-01 | CURRENT - a cube available to the public and that is current | 14 | 0 | Montréal:0, Québec:0 | number of, on july 1 | none |
| `32100218` | Annual (12) | 2016-01-01..2025-01-01 | CURRENT - a cube available to the public and that is current | 11 | 0 | Montréal:0, Québec:0 | none | none |
| `32100219` | Annual (12) | 2016-01-01..2018-01-01 | CURRENT - a cube available to the public and that is current | 11 | 0 | Montréal:0, Québec:0 | none | none |
| `32100220` | Annual (12) | 2016-01-01..2024-01-01 | CURRENT - a cube available to the public and that is current | 1 | 0 | Montréal:0, Québec:0 | none | none |
| `32100221` | Annual (12) | 2016-01-01..2025-01-01 | CURRENT - a cube available to the public and that is current | 11 | 0 | Montréal:0, Québec:0 | count | none |
| `33100678` | Occasional (18) | 2023-01-01..2023-01-01 | CURRENT - a cube available to the public and that is current | 14 | 0 | Montréal:0, Québec:0 | count | none |
| `98100361` | Occasional (18) | 2021-01-01..2021-01-01 | CURRENT - a cube available to the public and that is current | 174 | 43 | Montréal:1, Québec:1 | count, stock | none |

Marker columns are the RAW HITS, not a classification: a one-token match is a weak classifier and must not read as a stated measure type. The pick's measure type is decided in §3 on its title plus a verbatim footnote, and is the only measure-type claim this note makes.

**Why each non-pick candidate was rejected (computed from the row above, not typed per product):**

- `17100023` — archive status is "ARCHIVED -  a cube publicly available but no longer being updated" (not CURRENT); series ends 2018-04-01, earlier than the pick's 2026-04-01.
- `17100044` — archive status is "ARCHIVED -  a cube publicly available but no longer being updated" (not CURRENT); series ends 2017-01-01, earlier than the pick's 2026-04-01.
- `17100158` — series ends 2025-01-01, earlier than the pick's 2026-04-01.
- `32100218` — title matched only a peripheral permit/worker term, not a temporary-resident population term (its subject is "Temporary foreign workers in the agriculture and agri-food sectors, by industry"); series ends 2025-01-01, earlier than the pick's 2026-04-01.
- `32100219` — title matched only a peripheral permit/worker term, not a temporary-resident population term (its subject is "Jobs filled by temporary foreign workers in the agriculture sector, and agricultural operations with at least one temporary foreign worker, by province"); series ends 2018-01-01, earlier than the pick's 2026-04-01.
- `32100220` — title matched only a peripheral permit/worker term, not a temporary-resident population term (its subject is "Temporary foreign workers in the agriculture sector, by category of farm revenue"); series ends 2024-01-01, earlier than the pick's 2026-04-01.
- `32100221` — title matched only a peripheral permit/worker term, not a temporary-resident population term (its subject is "Countries of citizenship for temporary foreign workers in the agricultural sector"); series ends 2025-01-01, earlier than the pick's 2026-04-01.
- `33100678` — title matched only a peripheral permit/worker term, not a temporary-resident population term (its subject is "Business or organization hired workers from another country through the Temporary Foreign Worker Program in the last 12 months, second quarter of 2023"); one-time reference period (2023-01-01) — cubeStartDate equals cubeEndDate, so it cannot supply a fresh current value; series ends 2023-01-01, earlier than the pick's 2026-04-01.
- `98100361` — one-time reference period (2021-01-01) — cubeStartDate equals cubeEndDate, so it cannot supply a fresh current value; series ends 2021-01-01, earlier than the pick's 2026-04-01.

## 3. The pick — `17100121` (StatCan table 17-10-0121-01)

- Title (live): *"Estimates of the number of non-permanent residents by type, quarterly"* — https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710012101
- **Cadence: Quarterly** (frequencyCode 9, label resolved from the live code set), reference periods **2021-07-01..2026-04-01**.
- **Currency: CURRENT - a cube available to the public and that is current**; last released 2026-06-17T08:30.
- **Geography: 14 members**, of which 0 carry a ['(CMA)', 'census metropolitan', 'RMR'] marker and 0 carry a `(CA)` marker. The full member list, verbatim from the live response, so the level is self-evidencing rather than glossed:

  1. Canada
  2. Newfoundland and Labrador
  3. Prince Edward Island
  4. Nova Scotia
  5. New Brunswick
  6. Quebec
  7. Ontario
  8. Manitoba
  9. Saskatchewan
  10. Alberta
  11. British Columbia
  12. Yukon
  13. Northwest Territories
  14. Nunavut

- **Modeled-CMA search: NO.** Searched the 14 members BY NAME for **Montréal** (name hits 0, of which 0 carry a CMA marker), **Québec** (name hits 0, of which 0 carry a CMA marker). A cube title is never treated as evidence of its members; only this search is.
- **Measure type: STOCK.** Title stock markers ['number of']. No flow markers. Point-in-time reference dates, quoted verbatim from the live footnotes: "Estimates of the number of non-permanent residents: Q1 = January 1; Q2 = April 1; Q3 = July 1; Q4 = October 1." — a value stated AT a reference date is a level, not a movement, which is what spec:473 consumes.

- Schema (dimensions and member counts, live):

  | # | dimension | members |
  |---:|---|---:|
  | 1 | Geography | 14 |
  | 2 | Non-permanent resident types | 11 |

- Definition (verbatim, live footnote): "A non-permanent resident refers to a person from another country with a usual place of residence in Canada and who has a work or study permit or who has claimed refugee status (asylum claimants, protected persons and related groups). Family members living with work or study permit holders are also included unless these family members are already Canadian citizens, landed immigrants (permanent residents), or non-permanent residents themselves."

## 3b. Does any swept candidate carry the modeled CMAs?

- **`98100361`** *"Non-permanent resident type by place of birth: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts"* DOES carry both modeled CMAs: Montréal -> ['Montréal (CMA), Que.']; Québec -> ['Québec (CMA), Que.'] (among 174 geography members, 43 CMA-marked and 117 CA-marked).
  - Measured disqualifier for the tripwire slot: cadence **Occasional** (18), reference span **2021-01-01..2021-01-01** — cubeStartDate EQUALS cubeEndDate, i.e. a single reference period, so it cannot supply the fresh current value spec:473 requires. Its archive status is "CURRENT - a cube available to the public and that is current".

**This note proposes NO combination of the two.** They are separate products with separate reference periods and methods; nothing here licenses disaggregating or benchmarking the pick's province total to a CMA using the cube above. The pick's own live footnotes carry the programme-comparison caution: "Statistics Canada collaborates closely with Immigration, Refugees and Citizenship Canada (IRCC) and other federal departments to estimate the number of non-permanent residents (NPRs) living in Canada. The demographic estimates from Statistics Canada are updated on an ongoing basis, as new or revised data become available from its partners. Caution should be exercised before comparing data on non-permanent residents from Statistics Canada's Demographic Estimates Program with temporary residents and asylum claimants from IRCC, due to the different objectives of the two data sources." The CMA absence in the pick is a RECORDED LIMIT, not a gap to fill.

## 4. The spec-named alternative — IRCC temporary-resident tables (RECORDED, non-gating)

- Live query: `https://open.canada.ca/data/api/3/action/package_search?q=temporary+residents&rows=100`
- `package_search` -> 52 total matches, 52 returned and swept; **11** are IRCC packages whose title names temporary residents.

| package | frequency | resources | CMA-named | CMA-named & not [ARCHIVED] | point-in-time-named | permit-class scope |
|---|---|---:|---:|---:|---:|---|
| Algorithmic Impact Assessment - Advanced Analytics Triage of Overseas Temporary Resident Visa Applications | as_needed | 5 | 0 | 0 | 0 | visa, application |
| Automate the review of non-complex applications for Temporary Resident Visas and Work Permits made under the Canada-Ukraine Authorization for Emergency Travel (CUAET) | not_planned | 7 | 0 | 0 | 0 | work permit, visa, application |
| Facts & Figures 2015: Immigration Overview - Temporary Residents – Annual IRCC Updates | P1Y | 80 | 0 | 0 | 27 | total (no class term) |
| Facts and Figures 2016: Immigration Overview - Temporary Residents – Annual IRCC Updates | P1Y | 124 | 0 | 0 | 46 | total (no class term) |
| Facts and Figures 2017 - Immigration Overview - Temporary Residents | P1Y | 123 | 0 | 0 | 45 | total (no class term) |
| Specialized Research Datasets: Temporary Resident – Ad Hoc IRCC (Specialized Datasets) | as_needed | 54 | 6 | 6 | 0 | total (no class term) |
| Temporary Residents: Study Permit Holders – Monthly IRCC Updates | P1M | 30 | 2 | 0 | 6 | study permit |
| Temporary Residents: Temporary Foreign Worker Program (TFWP) and International Mobility Program (IMP) Work Permit Holders – Monthly IRCC Updates | P1M | 51 | 5 | 5 | 12 | work permit |
| Temporary Residents: Work Permit Holders – Ad Hoc IRCC (Specialized Datasets) | not_planned | 40 | 4 | 4 | 0 | work permit |
| Transition from Temporary Resident to Permanent Resident Status – Monthly IRCC Updates | P1M | 12 | 0 | 0 | 0 | total (no class term) |
| [ARCHIVED] Temporary Resident Application Processing – Quarterly IRCC Updates | as_needed | 10 | 0 | 0 | 0 | application |

- **Measured reason the IRCC family is not picked:** **0** of the 11 swept IRCC temporary-resident packages satisfy ALL THREE of (a) a CMA-named resource that is not [ARCHIVED]-labelled, (b) a point-in-time-named resource, (c) a total scope rather than a single permit class — 6 of the 11 are titled for a permit class ['study permit', 'work permit', 'visa', 'application'], which publishes a SUBSET of the temporary-resident population, not the total spec:473 consumes. So none of them offers a maintained, CMA-level, point-in-time count of the temporary-resident total. The counts above are what this run measured, scoped to this query — not a claim about IRCC holdings outside it.

## 5. The in-repo alternative — ISQ compo NPR column (RECORDED, non-gating)

- File read: `docs/research/2026-07-21-demographic-housing-flow-grounding/data/compo-rmr-base.xlsx` (header rows [5, 6, 7, 8, 9] searched across 38 columns).
- NPR column LOCATED at 0-indexed column **18** (matches the plan's pinned column 18).
- Label read from the workbook: **"Solde de résidents non permanents n"**.
- First data row (10, 0-indexed) value: **-72314**.
- **Measured reason it does not fill the STOCK slot:** the label leads with "Solde" (a net balance), and the first data value -72314 is NEGATIVE — a population STOCK cannot be below zero, so this column is a net FLOW over the year, not a level. spec:473 consumes a STOCK, so this column is recorded as a complement (it is already the demand model's NPR input), never as the stock indicator.

## DECISION

- `DECISION-VERDICT: LOCATED`
- `DECISION-SOURCE-PID: 17100121`  (StatCan table 17-10-0121-01; resolved from the live sweep of 8214 catalogue cubes, not typed)
- `DECISION-SOURCE-TITLE: Estimates of the number of non-permanent residents by type, quarterly`  (cubeTitleEn from the live getCubeMetadata response)
- `DECISION-CADENCE: Quarterly (frequencyCode 9, label from the live getCodeSets); reference periods 2021-07-01..2026-04-01`
- `DECISION-GEO-LEVEL: 14 members: 1 named exactly "Canada", 0 carrying a CMA marker, 0 carrying a (CA) marker, 13 other; the full member list is emitted verbatim in §3`
- `DECISION-CMA-AVAILABLE: NO`  (computed by searching the pick's 14 live geography members BY NAME for Montréal: 0 CMA-marked hit(s) of 0 name hit(s), Québec: 0 CMA-marked hit(s) of 0 name hit(s) — never inferred from the cube title)
- `DECISION-MEASURE-TYPE: STOCK`  (title stock markers ['number of']; flow markers none; the live footnote states point-in-time reference dates, so the value is a level at a date, not a movement — which is what spec:473 consumes)
- `DECISION-CURRENCY: CURRENT - a cube available to the public and that is current; last released 2026-06-17T08:30; series runs to 2026-04-01`
- `DECISION-PICK: StatCan 17-10-0121-01 (productId 17100121) — chosen over the 10 StatCan cubes swept in §1, the 11 IRCC temporary-resident packages swept in §4, the in-repo ISQ compo NPR column measured in §5`
- `DECISION-PICK-LIMIT: no CMA breakdown — the modeled CMAs Montréal (name hits 0, CMA-marked 0), Québec (name hits 0, CMA-marked 0) are ABSENT from the pick's 14 geography members; the coarsest geography containing them that IS present is ['Quebec']; the only swept cube carrying both is ['98100361'], disqualified in §3b and NOT combinable with the pick`
- `DECISION-TRIPWIRE-STATUS: UNKNOWN — the source is RECORDED here, not yet wired; per spec:473 the temporary-resident-stock indicator reports UNKNOWN until wired, never a stale within-band`

- Standing rule (spec:473): this source feeds the TRIPWIRE BASELINE registry's temporary-resident-stock indicator (current value + as_of + freshness limit), NOT the demand model — the demand model's NPR input is the ISQ compo net-flow column measured in §5. The two are different quantities and this note proposes no substitution between them.

