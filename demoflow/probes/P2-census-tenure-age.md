# P2 — StatCan 98-10-0231-01 tenure x age (RECORDED OBSERVATION)

## 1. Live pull — request and response, verbatim

- request URL: `https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/98100231/en`
- response body: `{"status":"SUCCESS","object":"https://www150.statcan.gc.ca/n1/tbl/csv/98100231-eng.zip"}`
- resolved zip url: `https://www150.statcan.gc.ca/n1/tbl/csv/98100231-eng.zip`
- zip members: `['98100231_MetaData.csv', '98100231.csv']`
- extracted_at (PINNED vintage, not a run clock): `2026-07-21`

## 2. Raw response identity (the PIT chain, upstream of `data_vintage.source_hashes`)

| link | sha256 | bytes |
|---|---|---|
| raw zip (`98100231-eng.zip`) | `76cd0ff16999a32c1f5342dc0eb78462d1b429f41cc07db98497cf2b587279bf` | 36,271,822 |
| raw inner CSV (`98100231.csv`) | `773f7af8deac87087f02d5464292f8a3e71351a7b1d735e47d983b7fd32b7b2b` | 850,971,474 |
| committed extract (`census_tenure_age_98100231.csv`) | `74673e57d1ae05824726b815e7263c18bb1b7d0419a3fbc52b8f6d6c704ee8da` | 10,511,241 |

**The inner CSV hash is the stable raw anchor.** Zip byte-stability across re-downloads is NOT guaranteed (archive metadata — timestamps, ordering, compressor settings — can shift without the data changing), so the zip hash is recorded for provenance but the inner member's hash is what a re-pull must reproduce.

The raw table is NOT committed: 850,971,474 bytes uncompressed is ~8x GitHub's hard file limit. The committed extract carries its own separate pin (row above), and that pin is the value `data_vintage.source_hashes` takes for this source (spec:315-316). This note is the upstream source for that structure; the structure itself is NOT built here.

## 3. Filter predicate (verbatim — the extract is mechanically re-derivable)

Applied to the raw inner CSV pinned above. Two axes only; **every other dimension, all 15 age bands and all 4 tenure columns are RETAINED**:

1. `GEO` ∈ the 7 wholly-Québec geographies:
   - `Quebec`
   - `Montréal (CMA), Que.`
   - `Québec (CMA), Que.`
   - `Saguenay (CMA), Que.`
   - `Sherbrooke (CMA), Que.`
   - `Trois-Rivières (CMA), Que.`
   - `Drummondville (CMA), Que.`
2. `Statistics (3C)` == `Number of private households` (exact string equality; the other two members are confidence-interval bounds that nothing downstream consumes)

Rows are re-emitted VERBATIM — the extract is the raw header plus the subset of raw data lines that satisfy the predicate. The sole transformation is UTF-8 BOM removal from the header. No reserialization, no dtype coercion, no column renaming.

- extract rows (excl. header): **50,400**
- rows per GEO: `{"Quebec": 7200, "Drummondville (CMA), Que.": 7200, "Montréal (CMA), Que.": 7200, "Québec (CMA), Que.": 7200, "Saguenay (CMA), Que.": 7200, "Sherbrooke (CMA), Que.": 7200, "Trois-Rivières (CMA), Que.": 7200}`
- target GEOs NOT FOUND in the table: `none — all 7 present verbatim` (a target producing no rows raises; this line can only ever be reached when every one of them was found)

### Why 7 geographies and not 3

`HORS_RMR` = province net of **ALL** Québec CMAs (spec:499, spec:550; codex r4-F2 / r1-F8). Netting only Montréal+Québec would wrongly fold the other four wholly-Québec CMAs into the residual.

### Excluded on purpose

- `Ottawa - Gatineau (CMA), Ont./Que.` — DGUID `2021S0503505`, parent member `Ontario` (Member ID `54`, classification code `[35]`) — NOT the Québec member (Member ID `24`, classification code `[24]`). Parentage is derived from the table's own metadata member, so 'not wholly-Québec' is structural here, not a reading of the name suffix. This table publishes no separable Québec-part row, so its Québec side is INSEPARABLE and sits INSIDE the residual.

## 4. What HORS_RMR actually denotes here (spec:552-554)

**CA caveat (codex r5-F7):** a published `non-CMA/CA` row would EXCLUDE Census Agglomerations while province-minus-CMAs INCLUDES them. This table publishes **no** such row. Computed from the metadata member (`98100231_MetaData.csv`), the Geography dimension has **166 members** = `Canada` + 13 provinces/territories + 41 CMAs + 111 CAs; sub-provincial members that are neither CMA nor CA: `none`. The spec:552-554 else-branch therefore fires: **the residual is COMPUTED**, and:

> **HORS_RMR here denotes: Québec outside the six wholly-Québec CMAs — INCLUDING all 23 Census Agglomerations AND the Québec side of Ottawa-Gatineau.**

Confirmed from metadata parentage: the Québec member has 6 CMA children (all kept) and 23 CA children (all inside the residual). Beyond those, 2 cross-border CAs carry `Que.` in the name but are parented elsewhere — `Campbellton (CA), N.B./Que.` (parent: New Brunswick), `Hawkesbury (CA), Ont./Que.` (parent: Ontario) — so their Québec parts are likewise inseparable and likewise fall inside the residual. Names and parents are resolved from the metadata member, not enumerated by hand.

- wholly-Québec CMAs (metadata-derived, children of the Québec member): `["Drummondville (CMA), Que.", "Montréal (CMA), Que.", "Québec (CMA), Que.", "Saguenay (CMA), Que.", "Sherbrooke (CMA), Que.", "Trois-Rivières (CMA), Que."]`
- QC-name-matching CMAs seen in the data (7): `["Drummondville (CMA), Que.", "Montréal (CMA), Que.", "Ottawa - Gatineau (CMA), Ont./Que.", "Québec (CMA), Que.", "Saguenay (CMA), Que.", "Sherbrooke (CMA), Que.", "Trois-Rivières (CMA), Que."]` — the extra one is `Ottawa - Gatineau (CMA), Ont./Que.` (excluded).

## 5. Observed table shape

- columns (17), verbatim as received: `["REF_DATE", "GEO", "DGUID", "Structural type of dwelling (10)", "Condominium status (3)", "Household type including census family structure (16)", "Statistics (3C)", "Age of primary household maintainer (15)", "Coordinate", "Tenure (4):Total - Tenure[1]", "Symbol", "Tenure (4):Owner[2]", "Symbol", "Tenure (4):Renter[3]", "Symbol", "Tenure (4):Dwelling provided by the local government, First Nation or Indian band[4]", "Symbol"]`
- Tenure is WIDE (in columns, not rows): 4 tenure columns with 4 duplicate `Symbol` columns interleaved after each. Duplicate names are preserved verbatim; positional access is required (a `DictReader` collapses them). Tenure columns as received: `["Tenure (4):Total - Tenure[1]", "Tenure (4):Owner[2]", "Tenure (4):Renter[3]", "Tenure (4):Dwelling provided by the local government, First Nation or Indian band[4]"]`
- **DUPLICATE MEMBER LABELS (not just duplicate column names).** Computed from the metadata member: `Household type including census family structure (16)` has 16 members but only 14 distinct labels — repeated: `With children`, `Without children`. Members are distinguished by member id / `Coordinate`, NOT by label — this is why rows are re-emitted verbatim. Any downstream dedup or group-by keyed on the LABEL would silently merge distinct members and destroy rows.
- UTF-8 BOM on the raw member's first bytes: **True** (observed on the raw bytes before decoding, since `utf-8-sig` strips a BOM whether or not one is there); stripped in the extract.
- age members (15): `["15 to 19 years", "20 to 24 years", "25 to 29 years", "30 to 34 years", "35 to 39 years", "40 to 44 years", "45 to 49 years", "50 to 54 years", "55 to 59 years", "60 to 64 years", "65 to 69 years", "70 to 74 years", "75 to 84 years", "85 years and over", "Total - Age of primary household maintainer"]`
- **There is no single `75 years and over` member.** 75+ must be summed from `75 to 84 years` + `85 years and over`.
- StatCan rounds counts to the nearest 5, so tenure components do NOT reconcile exactly to totals. This is a property of the source, not a defect; it is recorded, never 'fixed'.

## 6. Oracle — recomputed from the COMMITTED extract, re-read from disk

`Montréal (CMA), Que.`, `Total -` member of every non-age dimension, statistic `Number of private households`, summing age bands `75 to 84 years` + `85 years and over`:

- owner households: **113,730**
- total households: **202,535**
- owner share: **56.1533%** → rounds to the spec's 56.2%

This is the proof the filter dropped and mangled nothing.

## 7. Verdict

- VERDICT: WIRED (WDS endpoint live; table pulled, filtered, pinned and committed).
