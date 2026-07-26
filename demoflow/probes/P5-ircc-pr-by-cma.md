# P5 — IRCC PR admissions by CMA (RECORDED OBSERVATION)

Written by `probes/run_p5.py`; nothing in this file is hand-edited.

SCOPE OF THIS HEADER (it claims only what it can enforce): the resolved package id, the CSV resource url, the observed column list, and every row / CMA / year / suppression / rounding count in §1-§3 are emitted by this run from the live CKAN search response and the live CSV pull — the column list is split from the fetched header, never a literal. The suppression/rounding CONVENTION is quoted verbatim from the live package notes (cited below). The expected package id is a cross-check constant; the run asserts the live-resolved id equals it and prints both.
This run registered 13 provenance-tagged figures: 12 DERIVED (computed from the live response this run) and 1 CITED (verbatim from the live package metadata). Untagged numerals elsewhere are audit metadata (result counts, resource counts, column positions) and reference labels (years, the base-5 rounding step), each traceable to the live response.

Quoted verbatim from the live package metadata:
- suppression/rounding convention (values 0-5 shown as "--"; others rounded to nearest 5) — live package notes of f7e5498e-0ad8-4417-85c9-9b8aff9b9eda: "Please note that in these datasets, the figures have been suppressed or rounded to prevent the identification of individuals when the datasets are compiled and compared with other publicly available statistics. Values between 0 and 5 are shown as “--“ and all other values are rounded to the nearest multiple of 5."

## 1. CKAN discovery (boundary 1 — open.canada.ca)

- Query (the plan's, with `&rows=100` appended so the predicate sweeps 100 results rather than CKAN's default 10): `https://open.canada.ca/data/api/3/action/package_search?q=permanent+residents+census+metropolitan+area+monthly&rows=100`
- `package_search` -> success, **231** total matches for the query; **100** returned and swept.
- Located predicate (org is IRCC AND carries a CSV resource whose name matches CMA/Metropolitan): **3** of the 100 swept matched (231 total). A LOCATED is earned by this live resolution, not by a hand-typed id.
- Of the 3 matched, **1** is titled "Monthly" (spec §4 names the monthly CSV); that one is selected deterministically — the siblings are Ad-Hoc / Specialized datasets, so selection does not depend on CKAN relevance order.
- Resolved package id: **`f7e5498e-0ad8-4417-85c9-9b8aff9b9eda`** — title *"Permanent Residents – Monthly IRCC Updates"*.
- Cross-check: resolved id EQUALS the expected `f7e5498e-0ad8-4417-85c9-9b8aff9b9eda` (kept only as a cross-check constant).
- Package carries 52 resources; the CMA CSV resource resolved to id `4665647e-eb0e-4870-8d5a-d461001887aa`.

## 2. Observed schema — the CMA CSV (boundary 2 — ircc.canada.ca)

- CSV resource url: `https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_CMA.csv`
- Delimiter (observed): **tab** (shipped as `.csv` but tab-delimited).
- **11** columns, **21217** data rows, **172** distinct CMA members, years **2015..2026**, 12 distinct month labels (monthly cadence).
- Observed column list (split from the fetched header):

  | # | column |
  |---:|---|
  | 0 | `EN_YEAR` |
  | 1 | `EN_QUARTER` |
  | 2 | `EN_MONTH` |
  | 3 | `FR_ANNEÉ` |
  | 4 | `FR_TRIMESTRE` |
  | 5 | `FR_MOIS` |
  | 6 | `EN_CENSUS_METROPOLITAN_AREA` |
  | 7 | `FR_RÉGION_MÉTROPOLITAINE_DE_RECENSEMENT` |
  | 8 | `EN_PROVINCE_TERRITORY` |
  | 9 | `FR_PROVINCE_TERRITOIRE` |
  | 10 | `TOTAL` |

- The table is CMA × month × **TOTAL** (PR admissions). `TOTAL` is column 10; the CMA member is column 6 (`EN_CENSUS_METROPOLITAN_AREA`).
- Modeled-CMA presence (both present): **Montréal** (present: 137 monthly rows, 137 numeric, 0 suppressed, range 170–6280), **Québec** (present: 137 monthly rows, 137 numeric, 0 suppressed, range 10–1240).

## 3. Suppression / rounding convention and materiality

- Convention (quoted verbatim from the live package notes): "Please note that in these datasets, the figures have been suppressed or rounded to prevent the identification of individuals when the datasets are compiled and compared with other publicly available statistics. Values between 0 and 5 are shown as “--“ and all other values are rounded to the nearest multiple of 5."
- Tallied over the live TOTAL column: **4678** suppressed (`--`) cells of 21217 total; **16539** numeric cells, of which **0** are NOT multiples of 5 (0 confirms base-5 rounding).
- **Handling (spec §4):** a suppressed `--` cell is treated as a **0-band** (the true value is 0–5). For the TWO modeled CMAs this convention is **immaterial**: Montréal has **0** suppressed cells, Québec has **0** suppressed cells — 0 suppressed across both, so only base-5 rounding (±2.5 per monthly cell) applies to the tripwire's targets, negligible against the MIFI plan level (~45k/yr, a spec §4 constant).

## 4. Category axis (recorded divergence from spec §4 'by CMA + category')

- **0** of 52 resources in THIS package cross a CMA term with an immigration-category term (enumerated live). The CMA table above is geography × month × TOTAL only — no category dimension.
- Immigration category is published at the **Province/Territory** level in a sibling resource: `https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_IMMCAT.csv`. This is scoped to THIS package's resources — it is NOT a claim that category×CMA exists nowhere in IRCC open data.
- The PR-landings tripwire (spec §7) compares realized landings vs the MIFI plan level, which needs `TOTAL` only; the category axis is not required for it.

## 5. Semantic caveat for Task 28 (destination vs residence)

- The main CMA resource's name and metadata do NOT state whether the CMA is place of residence or intended destination at landing (the resource `description` is empty). The French-speaking (ex-QC) sibling resources DO name theirs "...Census Metropolitan Area of Intended Destination". Task 28 should treat the CMA as IRCC's intended-destination-at-admission by convention, but this is NOT confirmed in this resource's metadata — recorded, not asserted.

## DECISION

- `DECISION-VERDICT: LOCATED`
- `DECISION-PACKAGE-ID: f7e5498e-0ad8-4417-85c9-9b8aff9b9eda`
- `DECISION-CSV-URL: https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_CMA.csv`
- `DECISION-CSV-XLSX-UNROUNDED-URL: https://www.ircc.canada.ca/opendata-donneesouvertes/data/EN_ODP-PR-CMA.xlsx`  (the unrounded XLSX source, for when base-5 rounding matters)
- `DECISION-DELIMITER: tab`
- `DECISION-COLUMNS: EN_YEAR | EN_QUARTER | EN_MONTH | FR_ANNEÉ | FR_TRIMESTRE | FR_MOIS | EN_CENSUS_METROPOLITAN_AREA | FR_RÉGION_MÉTROPOLITAINE_DE_RECENSEMENT | EN_PROVINCE_TERRITORY | FR_PROVINCE_TERRITOIRE | TOTAL`
- `DECISION-SUPPRESSED-CONVENTION: cells shown as "--" are values 0-5 (suppressed); treat as a 0-band per spec §4. All other values are rounded to the nearest multiple of 5.`
- `DECISION-FOUND-AT-CMA: YES`  (numeric monthly rows in the live pull: Montréal 137, Québec 137 — both present)
- `DECISION-CATEGORY-AT-CMA: NOT-IN-PACKAGE`  (0 of 52 resources in this package cross a CMA term with an immigration-category term — see §4; category is Province/Territory only: `https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_IMMCAT.csv`; the tripwire needs TOTAL only)

- Standing rule (spec §7): this source feeds the PR-landings TRIPWIRE (realized PR landings vs the MIFI plan level), NOT the demand model (which uses ISQ compo "Immigrants permanents"). If the source becomes unavailable the tripwire reports UNKNOWN — never a stale within-band.

