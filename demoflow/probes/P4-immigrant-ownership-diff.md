# P4 — Immigrant/non-immigrant ownership ratio (Tranche-1 coarse-netting multiplier)

Written by `probes/run_p4.py`; nothing in this file is hand-edited.

The catalogue sweep and dimension-level audit in §1-§3 are generated from the live WDS responses of the run that wrote this file. The fallback band in §4 is computed from CITED published rates: the input homeownership rates are external (each printed with its source and a verbatim quote); every RATIO and band endpoint is computed in code from those rates — no ratio is hand-typed.
§4 tags its headline figures with provenance. This run registered 13: 11 DERIVED (computed from the cited rates in this same run) and 2 CITED (external published rates, printed with the citation inline). Untagged numerals elsewhere are: §1-§3 audit metadata (product ids, dimension labels, counts of what was checked); the cited source rates and figures shown in the §4 tables and verbatim quotes (traceable to the named articles); reference labels (census/horizon years, age ranges); and the per-row ratios and inline ranges computed beside those cited rates.

Externally cited figures:
- recent-immigrant vs Canadian-born fifth-year homeownership rates, 7 provinces (e.g. Ontario 40.2% vs 47.8%) — Statistics Canada, catalogue 46-28-0001, "The homeownership trajectories of recent immigrants", Chart 1, released 2026-06-16. https://www150.statcan.gc.ca/n1/pub/46-28-0001/2026001/article/00002-eng.htm
- owned units per 1,000 people: immigrants 310 (pooled) / 115 (recent 0-5yr) vs Canadian-born 271 — Statistics Canada, catalogue 36-28-0001, "Housing use of immigrants and non-permanent residents in ownership and rental markets", released 2025-05-28. https://www150.statcan.gc.ca/n1/pub/36-28-0001/2025005/article/00003-eng.htm

## 1. Catalogue sweep — title-level immigrant × tenure cross

- `getAllCubesListLite` -> 8214 cubes in catalogue.
- Titles mentioning immigrant/origin AND tenure/owner/rent (14):
  - `33100840` Number of enterprises in Canada, by geography and immigrant status of owner
  - `33100845` Number of enterprises in Canada, by revenue group and immigrant status of owner
  - `33100850` Number of enterprises in Canada, by enterprise size and immigrant status of owner
  - `33100855` Number of enterprises in Canada, by industry and immigrant status of owner
  - `37100127` Apprentices' employment status by sex, aboriginal identity and immigrant status, Canada
  - `46100025` Immigrant status and selected places of birth for residential property owners in the census metropolitan areas of Toronto and Vancouver
  - `46100026` Immigrant status and selected admission categories for residential property owners in the census metropolitan areas of Toronto and Vancouver
  - `46100032` Immigrant status of residential property owners by period of immigration and number of properties owned
  - `46100033` Immigrant status of residential property owners by period of immigration and place of birth
  - `46100034` Immigrant status of residential property owners by period of immigration and admission category
  - `46100052` Single and multiple residential property owners by immigration characteristics, inactive
  - `46100098` Residential property owners by immigration characteristics
  - `98100543` Eligibility for instruction in the minority official language by collapsed criteria of eligibility accounting for parents’ citizenship: Canada, provinces and territories, census divisions and census subdivisions
  - `98100544` Eligibility for instruction in the minority official language by collapsed criteria of eligibility accounting for parents’ citizenship: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts

Breakdown of the 14 hits by product-family prefix: {'33': 4, '37': 1, '46': 7, '98': 2}. None is a free Census immigrant × TENURE cross-tab: the `33` rows count enterprise OWNERS; the `46` rows are CHSP residential-property OWNERS (a numerator, not a rate; homeownership coverage excludes Québec); the rest matched a tenure keyword only as a TITLE SUBSTRING and are NOT about housing tenure — e.g. `37100127` on app-RENT-ices (apprentices) and the `98` pair on pa-RENT-s' (parents') citizenship. Title search alone cannot prove absence, so §2 audits at the DIMENSION level.

## 2. Dimension-level audit — the auditable NOT-FOUND

Probed metadata for 173 distinct 98* cubes (95 housing-family, 80 immigrant-family).

**Direction A — 98* housing/dwelling/tenure/maintainer cubes carrying an IMMIGRANT dimension:**
  - `98100327` Housing suitability by visible minority and immigrant status and period of immigration: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts — immigrant dim ['Immigrant status and period of immigration (11)']; tenure dim NONE
  - `98100328` Shelter-cost-to-income ratio by visible minority and immigrant status and period of immigration: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts — immigrant dim ['Immigrant status and period of immigration (11)']; tenure dim NONE
  - `98100656` Labour force status by visible minority, household type of person and selected characteristics: Canada, provinces and territories and census metropolitan areas with parts — immigrant dim ['Immigrant and generation status (9)']; tenure dim NONE
  -> 3 carry an immigrant dimension; 0 of those ALSO carry a tenure dimension. (Housing suitability, shelter-cost-to-income and labour force are NOT tenure.)

**Direction B — 98* immigrant/period-of-immigration cubes carrying a TENURE dimension:**
  -> 0 of 80 immigrant cubes carry a tenure dimension: `[]`.

## 3. Targeted candidates — how each resolves

- **98100279** (the plan's product id) resolves to **"Presence of grandparents in household by Indigenous identity: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts"** — dimensions ['Geography', 'Registered or Treaty Indian status (3)', 'Age (4A)', 'Gender (3)', 'Statistics (3)', 'Presence of grandparents in household (10)', 'Indigenous identity (9)']. Nothing to do with immigrant status or tenure; a plan-author guess (same class as P3's candidates).
- **98100327** "Housing suitability by visible minority and immigrant status and period of immigration: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts" — HAS an immigrant dimension ['Immigrant status and period of immigration (11)'] at CMA geography, but its housing axis is ['Housing suitability (6)', 'Dwelling condition (4)'], NOT tenure (owner/renter). No ownership rate derivable.
- **98100328** "Shelter-cost-to-income ratio by visible minority and immigrant status and period of immigration: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts" — HAS an immigrant dimension ['Immigrant status and period of immigration (11)'] at CMA geography, but its housing axis is ['Shelter-cost-to-income ratio (8)', 'Core housing need (3)'], NOT tenure (owner/renter). No ownership rate derivable.
- **46100098** "Residential property owners by immigration characteristics" (CHSP) — dimensions ['Geography', 'Number of residential properties owned', 'Immigration status', 'Immigration characteristics', 'Estimates']. It counts property OWNERS by immigration status (a numerator), NOT owner households over total households, so it yields no ownership RATE; its 'Proportion of owners by immigration status' estimate is the owner-pool COMPOSITION, not owners/population. Its 136 geographies include 0 Québec-named members -> the Montréal/Québec CMA cells are absent (the CHSP homeownership coverage gap).

## LIVE HUNT VERDICT: NOT-FOUND-AT-CMA

No free StatCan cube publishes an immigrant/non-immigrant ownership RATE at the Montréal/Québec CMA level: §2 dimension-audited the title-selected candidate pool (every 98* cube whose title carries a housing OR an immigrant term — both directions) and found no immigrant × tenure cross. That title-selected pool is where such a cube MUST surface: under StatCan's naming a genuine immigrant×tenure cross-tab would carry an immigrant or a housing term in its title, so the residual reliance on title-selection is bounded, not exhaustive coverage of all 98* cubes. CHSP (`46*`) is an owners-numerator that excludes Québec (§3). Therefore the spec §6 documented-fallback path applies.

## 4. Documented fallback multiplier band (CITED rates -> DERIVED ratio)

Basis: **Source 1** — Statistics Canada, catalogue **46-28-0001**, *The homeownership trajectories of recent immigrants*, Chart 1 (released 2026-06-16). https://www150.statcan.gc.ca/n1/pub/46-28-0001/2026001/article/00002-eng.htm
  - verbatim: "the homeownership rate for recent immigrants in the fifth year after admission rose from 35.7% in 2018 to 40.2% in 2021, while that for Canadian-born individuals fell from 50.7% to 47.8%" (Ontario) — Chart 1 reports the fifth-year vs Canadian-born rate for all seven covered provinces.
  - metric: individual homeownership RATE (tax filers 25-54 owning ≥1 residential property, over that group); population = RECENT immigrants, which matches the netting's semantic target (arrivals are recent, rental-skewed).

### 4a. Cited rates and the ratio derived from them

Fifth year after admission, 2021 (recent-immigrant % / Canadian-born % -> ratio):

| province | recent immigrant (5yr) | Canadian-born | ratio (derived) |
|---|---:|---:|---:|
| Prince Edward Island | 49.8% | 52.5% | 0.949 |
| Nova Scotia | 48.1% | 49.8% | 0.966 |
| New Brunswick | 56.6% | 54.8% | 1.033 |
| Ontario | 40.2% | 47.8% | 0.841 |
| Manitoba | 47.9% | 50.0% | 0.958 |
| Alberta | 39.7% | 51.9% | 0.765 |
| British Columbia | 37.5% | 43.3% | 0.866 |

**Recommended band (rule: min / mean / max of the 7 province ratios, all computed from the cited rates):** low **0.765** (Alberta), center **0.911**, high **1.033** (New Brunswick). The band honestly spans >1.0 (New Brunswick recent immigrants OUT-own Canadian-born) — spec:129-131 permits ratio > 1; the multiplier is asserted nonnegative-finite, NOT < 1.

**WHY the fifth year is the anchor (stated, so a stateless Task-15 reader sees it):** demoflow projects to 2051+, so an arrival cohort's CUMULATIVE owner-household contribution over the horizon is dominated by its settled-state ownership, not its first-year rental skew; the fifth-year rate is the closest published proxy for that settled state, and year 1 (mean ratio 0.210) is a first-year-only artifact. This is a defensible anchor — NOT the only reading (see 4b), and P4 does not rule between them.

**WHAT the recommended band's WIDTH measures — READ THIS before using it as a sweep grid:** its endpoints are cross-PROVINCIAL dispersion at a FIXED tenure (fifth year) — a SECONDARY axis (whether Alberta differs from New Brunswick, which is not the question about Montréal). The DOMINANT uncertainty is the TENURE anchor itself, which swings the ratio ~33% (year-3 center 0.614 vs year-5 center 0.911) and is NOT inside this band. It is emitted as a SEPARATE machine-readable band in 4b (`DECISION-RATIO-TENURE-SENSITIVITY`); Task 15's robustness sweep grid must span BOTH axes, not the fifth-year cross-province spread alone.

### 4b. The tenure-anchor uncertainty (the DOMINANT axis) + pooled-vs-recent (recorded, NOT resolved — Task-15 findings)

**Source 2** — Statistics Canada, catalogue **36-28-0001**, *Housing use of immigrants and non-permanent residents in ownership and rental markets* (released 2025-05-28). https://www150.statcan.gc.ca/n1/pub/36-28-0001/2025005/article/00003-eng.htm
  - verbatim: "immigrants occupy, on average, 310 owned units ... per 1,000 people ..., compared with ... 271 owned units ... for Canadian-born individuals"; recent immigrants (0 to 5 years) occupy 115 owned units per 1,000.

Pooled ALL-immigrant owned-occupancy ratio = **1.144** (≥ 1: established immigrants own at native-or-higher rates), while the RECENT (0-5yr) ratio = **0.424**. A pooled ratio would say arrivals add MORE owners than natives and would DEFEAT the netting (spec §6: a new rental-skewed immigrant must NOT read as a new buyer). The recent-immigrant reading is therefore required. Within the recent evidence, earlier tenure is far lower still — year 1 and year 3 province rates:

| province | year 1 | year 3 | year 5 |
|---|---:|---:|---:|
| Prince Edward Island | 10.5% | 35.9% | 49.8% |
| Nova Scotia | 11.5% | 33.5% | 48.1% |
| New Brunswick | 14.5% | 41.3% | 56.6% |
| Ontario | 7.4% | 24.9% | 40.2% |
| Manitoba | 13.4% | 32.0% | 47.9% |
| Alberta | 8.3% | 23.4% | 39.7% |
| British Columbia | 8.2% | 25.0% | 37.5% |

**The tenure anchor is unresolved — three defensible readings, P4 rules between NONE:**
  1. FRESH-ARRIVAL: year-1 band [0.155, 0.210, 0.268] (min/mean/max of the 7 year-1 province ratios), rising toward the 0-5yr per-capita ratio 0.424. The §6 netting target IS the recent-arrival stock, which owns near the year-1 rate before accumulating tenure, so this reading is squarely in scope; right if p_imm captures arrival-window ownership.
  2. SETTLED / long-horizon (year 5): center **0.911** — right if p_imm captures a cohort's CUMULATIVE owner demand over a projection to 2051 (see 4a); this is the RECOMMENDED anchor.
  3. STOCK-POOLED (all vintages): ratio **1.144** (≥1) — right if p_imm re-applies to the whole accumulated immigrant household stock; this DEFEATS the netting and is recorded as the anti-pattern, not a candidate.

**Second machine-readable band — the TENURE axis (rule: min/mean/max of the 7 YEAR-3 province ratios):** low **0.451** (Alberta), center **0.614**, high **0.754** (New Brunswick). Task 15's robustness sweep grid must cover ALL THREE tenure-anchor bands (year 1/3/5 — reading #1's year-1 band is the fresh-arrival floor) — the full plausible range across the tenure anchor AND geography is roughly [0.155, 1.033]. Tranche 2 replaces this coarse ratio with the years-since-landing S-curve, which resolves the tenure axis properly. P4 records both axes and does NOT calibrate.

### 4c. borrowed_prior — three transport axes, stated out loud

- **GEOGRAPHY**: Québec is NOT a covered province in Source 1 (CHSP homeownership coverage excludes it), so the ROC-province band stands in for the Montréal/Québec CMAs. Montréal's tenure structure differs materially from the ROC — this is a genuine borrow, not a formality.
- **METRIC**: Source 1 is INDIVIDUAL residential-property ownership (ages 25-54); the spec's `p_nonimm` is a household-maintainer tenure propensity (Census). The RATIO is transported across metric definitions (both groups measured identically within the source).
- **TENURE-PROFILE**: the fifth-year rate stands in for the full arrival-stock tenure distribution; §4b records the fresher-cohort pull.

All three are why the constant lands `borrowed_prior` (spec §6). This is NOT a silent 1.0: it is a cited, banded, published figure with its borrow declared.

## DECISION

- `DECISION-FOUND-AT-CMA: NO`
- `DECISION-RATIO-MULTIPLIER-BAND: [0.765, 0.911, 1.033]`  (low, center, high — the immigrant/non-immigrant ownership ratio for `p_imm = p_nonimm × ratio`; width = cross-provincial dispersion at the fifth-year anchor, a SECONDARY axis)
- `DECISION-RATIO-TENURE-SENSITIVITY: [0.451, 0.614, 0.754]`  (the DOMINANT axis — year-3 tenure anchor; the fresh-arrival year-1 floor is lower still, see §4b; Task 15's sweep grid must span the full plausible range across the year-1/3/5 anchors ≈ [0.155, 1.033])
- `DECISION-RATIO-FLAG: borrowed_prior`
- `DECISION-RATIO-SOURCE: Statistics Canada, catalogue 46-28-0001 ("The homeownership trajectories of recent immigrants"), Chart 1 recent-immigrant vs Canadian-born fifth-year homeownership rates by province, 2021; ratio band = min/mean/max across the 7 covered provinces`
- `DECISION-RATIO-CITATION: Statistics Canada. Catalogue 46-28-0001, "The homeownership trajectories of recent immigrants", released 2026-06-16. https://www150.statcan.gc.ca/n1/pub/46-28-0001/2026001/article/00002-eng.htm (pooled-vs-recent cross-check: catalogue 36-28-0001, https://www150.statcan.gc.ca/n1/pub/36-28-0001/2025005/article/00003-eng.htm)`

- Standing rule (spec §6): the multiplier is load-bearing; a silent 1.0 is FORBIDDEN (it would collapse the netting). This probe records a cited, banded, `borrowed_prior` multiplier — never an invented number and never a bare 1.0. Task 15 lands it in constants and declares the central value; the CMA cross-tab does not exist free, so the borrow is mandatory.

