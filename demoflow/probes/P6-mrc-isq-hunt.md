# P6 — MRC-level ISQ source hunt (RECORDED OBSERVATION)

Written by `probes/run_p6.py`; nothing in this file is hand-edited.

SCOPE OF THIS HEADER (it claims only what it can enforce): the resolved ISQ organization slug, the CKAN catalogue and swept-package counts, the sitemap loc and .xlsx counts, the swept and eligible candidate lists, every candidate's observed HTTP status / content-type / declared length / magic-byte result, the HEAD-vs-GET comparison, the opened workbook's sheet names, header position, geography-label count and label list, its scenario column, the per-target couronne name search, the per-target administrative-region corroboration, the per-edition RA-column probe of §3b, the per-RA membership sets of §3c and the spec-premise state of §4 are ALL emitted by this run from live reads. The quoted strings are verbatim. Every absence claim is scoped to what was actually swept — never to what exists. What this run does NOT compute, and therefore does not claim: which of the swept editions is CURRENT (no live response states it, so §3b ranks none and emits each caption instead); that any cross-edition join is VALID (§3b tests no label-set agreement or vintage compatibility between two workbooks); and whether the declared MRCs compose the Montréal RMR couronne (§3c measures that this file carries no metropolitan-area axis and records the limit rather than reaching for a second source). ONE workbook is opened in full; §3b opens the others' HEADER ROWS ONLY, so its rows carry header-scoped evidence and say nothing about those files' data below the header.
This run registered 17 provenance-tagged figures: 14 DERIVED (computed from the live responses of this run) and 3 CITED (verbatim from a live response body). Untagged numerals elsewhere are audit metadata (candidate counts, byte lengths, row/column positions, HTTP status codes) and reference labels (slugs, urls, sheet names), each traceable to the live response this run read.

Quoted verbatim from the live responses:
- ISQ's own diffusion geographies, per a live CKAN package's notes — donneesquebec.ca package notes: "Alors que l’ISQ diffuse les données de population par région administrative, MRC, municipalité et RMR, c’est le MSSS qui diffuse les données pour les territoires du réseau de la santé et des services sociaux"
- the opened workbook's own caption — cell A1 of composantes-demographiques-projetees-mrc-du-quebec.xlsx: "Composantes démographiques projetées, scénario Référence A2021, MRC du Québec, 2020-2041"
- spec §8's CURRENT text on the MRC premise — 2026-07-21-demoflow-demographic-scenario-module-design.md: "| RA14/15/16 rows carry `ra_proxy` (exact RA data used as couronne/periphery proxies — ranking members, never balance participants, never emitted in ScenarioPrior); Laval is exact (RA13 ≡ ville); couronne-nord precision is DEFERRED to v1 (§11.6: a find enables v1, never v0). MRC-level ISQ projection workbooks EXIST — the 2026-07-21 'no MRC workbook (404)' finding was a METHOD ARTIFACT: HEAD 404s where GET 200s on ISQ's descriptive-French slugs, and the original probe's guessed slugs also 404 on GET, so absence was a property of slug + verb, never the data (P6 probe + independent steering re-verification, 2026-07-28; discovery path = sitemap.xml, 3,273 xlsx locs). v1 is PARKED behind two recorded residuals: the RA↔MRC axis is EDITION-SPECIFIC (present in A2021, absent from the 2025 scenarios workbook), and membership-vs-partition of RA14/15/16 vs the RMR couronne is not yet computed |"

## 1. Boundary A — Données Québec CKAN (the enumerable open-data catalogue)

- `organization_list` -> **142** organizations. The ISQ slug is RESOLVED from that live list by the title predicate `'institut de la statistique'`: **`isq`** (title match).
- `package_search?rows=0` -> **1617** packages in the catalogue (`1617` reported).
- Swept: **8** distinct packages — 7 from `organization:isq` and the remainder from the live term query `https://www.donneesquebec.ca/recherche/api/3/action/package_search?q=MRC+projection+population+perspectives+demographiques&rows=100`.
- Candidate predicate (the SAME two-tier predicate boundary B uses, applied to title + notes + every resource name and url): an MRC term ['mrc', 'municipalites-regionales-de-comte'] AND a projection term ['projet', 'scenario', 'perspectives-demographiques'] AND a population term ['population', 'composantes-demographiques', 'menages', 'demographiques']. **1** of the 8 swept packages matched: ['Système de grilles vectorielles pour une infrastructure québécoise de données spatiales, mise à jour 2026'].

  This boundary is therefore NOT an absence: 1 swept package(s) matched the slug predicate. None of them is opened or body-checked here — this boundary contributes the second searched population, and the verdict is earned on boundary B below, where a candidate's bytes are actually inspected. Whether a match is a real MRC-projection dataset or a slug-predicate false positive is left to the reader: the titles are printed above, unglossed.

- CITED, verbatim from a live package's own `notes` (resolved by predicate, not typed): *"Alors que l’ISQ diffuse les données de population par région administrative, MRC, municipalité et RMR, c’est le MSSS qui diffuse les données pour les territoires du réseau de la santé et des services sociaux."* This is a statement about ISQ's publication practice quoted from CKAN — it is NOT evidence about the file opened in §3, which is verified by its own bytes, and nothing in the verdict rests on it.

## 2. Boundary B — ISQ's own product pages / full-edition downloads

- `https://statistique.quebec.ca/sitemap.xml` -> **25543** distinct `<loc>` entries (deduped: the raw document repeats each url once per hreflang alternate, so an un-deduped count would overstate the population every absence claim below is scoped to), of which **3273** are `.xlsx` download urls.
- Sweep predicate over the url slug (case-insensitive substring): an MRC term ['mrc', 'municipalites-regionales-de-comte'] AND a population term ['population', 'composantes-demographiques', 'menages', 'demographiques'] makes a url SWEPT; a projection term ['projet', 'scenario', 'perspectives-demographiques'] additionally makes it ELIGIBLE (spec §8's junction consumes projected population by scenario, so an estimates workbook is a different product). **22** swept, **15** eligible — every absence claim is therefore scoped to the WIDER swept set.
- The swept count is DEDUPED BY FILE: 33 matching locs collapse to 22 distinct slugs, because the sitemap lists `/fr/fichier/<slug>` and `/en/fichier/<slug>` separately for the same workbook.

**Every eligible candidate, observed live by GET** (status, content-type, declared length and the first 8 bytes — only a prefix is read, so a 17MB candidate costs a handshake rather than a download). A bare 200 is NOT treated as evidence: the magic-byte column is what separates a workbook from an HTML page served at 200.

| candidate (slug) | HTTP | content-type | Content-Length | magic bytes | workbook prefix? |
|---|---:|---|---:|---|---|
| `composantes-demographiques-projetees-mrc-du-quebec.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 517264 | `504b030414000600` | YES |
| `composantes-demographiques-projetees-scenarios-mrc-quebec.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 1987961 | `504b030414000600` | YES |
| `nombre-de-menages-prives-projetes-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 22004 | `504b030414000600` | YES |
| `nombre-de-menages-prives-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 31793 | `504b030414000600` | YES |
| `nombre-de-menages-prives-scenario-reference-a2021-mrc-du-quebec-2020-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 28937 | `504b030414000600` | YES |
| `nombre-de-menages-prives-selon-le-groupe-dage-de-la-personne-reference-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 346094 | `504b030414000600` | YES |
| `nombre-menages-prives-selon-groupe-age-de-la-personne-reference-scenario-reference-a2021-mrc-du-quebec-2020-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 293506 | `504b030414000600` | YES |
| `nombre-total-menages-prives-projetes-mrc.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 82053 | `504b030414000600` | YES |
| `part-des-grands-groupes-dage-et-age-moyen-de-la-population-des-mrc-du-quebec-scenario-reference-a-2016-et-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 22684 | `504b030414000600` | YES |
| `population-age-sexe-scenarios-mrc-quebec.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 17300853 | `504b030414000600` | YES |
| `population-et-composantes-demographiques-projetees-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 588161 | `504b030414000600` | YES |
| `population-projetee-des-mrc-du-quebec-scenario-reference-a-2016-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 21227 | `504b030414000600` | YES |
| `population-selon-lage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 4882720 | `504b030414000600` | YES |
| `population-selon-le-groupe-dage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 1760565 | `504b030414000600` | YES |
| `population-totale-projetee-scenarios-mrc-quebec.xlsx` | 200 | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 85094 | `504b030414000600` | YES |

- **15** of the 15 eligible candidates answered 200 with a workbook magic-byte prefix. Note the exact scope of that number: it is a STATUS-AND-PREFIX result, not a body-shape result — exactly ONE candidate is opened and shape-checked in §3, and only that one carries the three evidence pieces a LOCATED requires.

**The plan body's two GUESSED slugs, probed live by this run** (so the comparison in §4 is measured here rather than recalled):

| guessed slug | HTTP (GET) |
|---|---:|
| `pop-as-mrc-base.xlsx` | 404 |
| `pop-mrc-base.xlsx` | 404 |

## 3. Body-shape check — is `composantes-demographiques-projetees-mrc-du-quebec.xlsx` really MRC-level?

- Selected DETERMINISTICALLY from the 15 verified candidates by the rule stated in the code before its result: 6 of them match a DECLARED demoflow family, and this is the smallest of those by declared `Content-Length` (517264 bytes) — family **compo-* (projected demographic components)**. A shape witness only has to be sufficient; the note does NOT claim this is the newest edition — the caption and release line below are read from its own bytes and state which edition it is.
- Full GET -> 517264 bytes; prefix `504b030414000600` matches the `504b0304` workbook magic; opened with 1 sheet(s): ['Référence A2021'].
- **Method comparison, measured on this same url:** GET -> **200**, HEAD -> **404**. The two DISAGREE, so on this host a HEAD-only hunt (which is what the plan body's P6 sketch performs) would record this live workbook as absent. That is a measured property of this endpoint, not a general rule.
- Caption cell A1 (verbatim): *"Composantes démographiques projetées, scénario Référence A2021, MRC du Québec, 2020-2041"*
- No cell in the header block names a diffusion date this run.
- Geography column located by a header cell BEGINNING `MRC` at row 2, column 1 (0-indexed); the cell reads `MRC`. Prefix, not equality and not substring — measured reason: equality misses the 2016-2041 edition (whose header reads "MRC par région administrative") and a substring test locks onto the caption row, which also contains "mrc", and counts zero labels below it.
- Full header row (verbatim): ['Code', 'MRC', 'RA1', 'Année (t)', 'Population', 'Naissances', 'Indice', 'Décès', 'Espérance de vie', 'Accroissement', 'Immigrants', 'Émigration', 'Solde', 'RNP (t)', 'RNP (t+1)', 'Solde', 'Entrants', 'Sortants', 'Solde', 'Solde', 'Entrants', 'Sortants', 'Solde', 'Solde', 'Solde', 'Solde', 'Ajustement', 'Accroissement', 'Population'].
- **122 distinct geography labels** below that header, which decompose as **17 + 105**: labels in the `NN  Name` administrative-region-SUBTOTAL form, plus the remainder. That split is emitted because the raw total would read as an MRC count and be wrong — this column interleaves RA subtotals with the MRC rows. What the remainder contains is NOT asserted here; the full list is emitted verbatim from the live response, so the LEVEL is self-evidencing rather than glossed — a count alone would leave "MRC-level" a word beside a number (P5b's precedent):

  1. 01  Bas-Saint-Laurent
  2. 02  Saguenay–Lac-Saint-Jean
  3. 03  Capitale-Nationale
  4. 04  Mauricie
  5. 05  Estrie
  6. 06  Montréal
  7. 07  Outaouais
  8. 08  Abitibi-Témiscamingue
  9. 09  Côte-Nord
  10. 10  Nord-du-Québec
  11. 11  Gaspésie–Îles-de-la-Madeleine
  12. 12  Chaudière-Appalaches
  13. 13  Laval
  14. 14  Lanaudière
  15. 15  Laurentides
  16. 16  Montérégie
  17. 17  Centre-du-Québec
  18. Abitibi
  19. Abitibi-Ouest
  20. Acton
  21. Administration régionale Kativik
  22. Antoine-Labelle
  23. Argenteuil
  24. Arthabaska
  25. Avignon
  26. Beauce-Sartigan
  27. Beauharnois-Salaberry
  28. Bellechasse
  29. Bonaventure
  30. Brome-Missisquoi
  31. Bécancour
  32. Caniapiscau
  33. Charlevoix
  34. Charlevoix-Est
  35. Coaticook
  36. Communauté maritime des Îles-de-la-Madeleine
  37. D'Autray
  38. Deux-Montagnes
  39. Drummond
  40. Eeyou Istchee2
  41. Gatineau
  42. Jamésie
  43. Joliette
  44. Kamouraska
  45. L'Assomption
  46. L'Islet
  47. L'Érable
  48. L'Île-d'Orléans
  49. La Côte-de-Beaupré
  50. La Côte-de-Gaspé
  51. La Haute-Côte-Nord
  52. La Haute-Gaspésie
  53. La Haute-Yamaska
  54. La Jacques-Cartier
  55. La Matanie
  56. La Matapédia
  57. La Mitis
  58. La Nouvelle-Beauce
  59. La Rivière-du-Nord
  60. La Tuque
  61. La Vallée-de-l'Or
  62. La Vallée-de-la-Gatineau
  63. La Vallée-du-Richelieu
  64. Lac-Saint-Jean-Est
  65. Laval
  66. Le Domaine-du-Roy
  67. Le Fjord-du-Saguenay
  68. Le Golfe-du-Saint-Laurent
  69. Le Granit
  70. Le Haut-Richelieu
  71. Le Haut-Saint-François
  72. Le Haut-Saint-Laurent
  73. Le Rocher-Percé
  74. Le Val-Saint-François
  75. Les Appalaches
  76. Les Basques
  77. Les Chenaux
  78. Les Collines-de-l'Outaouais
  79. Les Etchemins
  80. Les Jardins-de-Napierville
  81. Les Laurentides
  82. Les Maskoutains
  83. Les Moulins
  84. Les Pays-d'en-Haut
  85. Les Sources
  86. Longueuil
  87. Lotbinière
  88. Lévis
  89. Manicouagan
  90. Marguerite-D'Youville
  91. Maria-Chapdelaine
  92. Maskinongé
  93. Matawinie
  94. Memphrémagog
  95. Minganie
  96. Mirabel
  97. Montcalm
  98. Montmagny
  99. Montréal
  100. Mékinac
  101. Nicolet-Yamaska
  102. Nouveau toponyme officiel à venir.
  103. Papineau
  104. Pierre-De Saurel
  105. Pontiac
  106. Portneuf
  107. Québec
  108. Rimouski-Neigette
  109. Rivière-du-Loup
  110. Robert-Cliche
  111. Roussillon
  112. Rouville
  113. Rouyn-Noranda
  114. Saguenay
  115. Sept-Rivières
  116. Shawinigan
  117. Sherbrooke
  118. Thérèse-De Blainville
  119. Trois-Rivières
  120. Témiscamingue
  121. Témiscouata
  122. Vaudreuil-Soulanges

- Scenario axis: **0** — no cell in this sheet's header row names a scenario axis. The sheet-name list above is emitted verbatim; this note draws no conclusion from it about how this edition separates its scenarios.

**The declared couronne targets, searched BY NAME in those labels — 10 of 10 found.** The label COUNT above does not bear on couronne precision (a large MRC set is equally consistent with the couronne being absent); this per-target search is the measurement that does.

| declared RA (spec §8 `ra_proxy`) | declared MRC target | found in the opened workbook? | RA code observed beside it | agrees with the declared RA number? |
|---|---|---|---|---|
| RA14 Lanaudière | Les Moulins | YES — 'Les Moulins' | ['14'] | CORROBORATED |
| RA14 Lanaudière | L'Assomption | YES — "L'Assomption" | ['14'] | CORROBORATED |
| RA15 Laurentides | Thérèse-De Blainville | YES — 'Thérèse-De Blainville' | ['15'] | CORROBORATED |
| RA15 Laurentides | Deux-Montagnes | YES — 'Deux-Montagnes' | ['15'] | CORROBORATED |
| RA15 Laurentides | Mirabel | YES — 'Mirabel' | ['15'] | CORROBORATED |
| RA15 Laurentides | La Rivière-du-Nord | YES — 'La Rivière-du-Nord' | ['15'] | CORROBORATED |
| RA16 Montérégie | Roussillon | YES — 'Roussillon' | ['16'] | CORROBORATED |
| RA16 Montérégie | Marguerite-D'Youville | YES — "Marguerite-D'Youville" | ['16'] | CORROBORATED |
| RA16 Montérégie | La Vallée-du-Richelieu | YES — 'La Vallée-du-Richelieu' | ['16'] | CORROBORATED |
| RA16 Montérégie | Vaudreuil-Soulanges | YES — 'Vaudreuil-Soulanges' | ['16'] | CORROBORATED |

- The target list is **DECLARED in this file** from spec §8's three `ra_proxy` rows, not derived from the response; what is COMPUTED is the search result per target, and a miss is published as a miss (none missed this run).
- **The RA↔MRC correspondence — 10 of 10 declared targets corroborated.** This edition DOES publish a SEPARATE administrative-region column (column 2, header `RA1`), so the RA number this file DECLARES for each target is checked against the code the live response puts beside that MRC — an independent witness nothing here controls. Flip a declared key to the wrong RA and the check stops corroborating. What this establishes is MEMBERSHIP — each declared target is present and sits under the RA number this file declares for it. It is NOT a partition, and this section makes no partition claim: §3c computes what the workbook can actually say about exhaustion. Scoped to the ONE workbook opened here; §3b opens the other verified candidates and reports the RA axis across them, so the edition scope of this corroboration is measured rather than assumed.

- **Which swept files would feed a v1 extension.** demoflow consumes two ISQ families at RMR level; the DECLARED term map {'pop-as-* (population by age and sex)': ['population', 'age', 'sexe'], 'compo-* (projected demographic components)': ['composantes-demographiques']} is matched against the ELIGIBLE slugs above (a slug match, not a schema comparison — no equivalence between the RMR and MRC editions is tested here):

  - **pop-as-* (population by age and sex)** -> 3 eligible slug(s) match: ['population-age-sexe-scenarios-mrc-quebec.xlsx', 'population-selon-lage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx', 'population-selon-le-groupe-dage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx']
  - **compo-* (projected demographic components)** -> 3 eligible slug(s) match: ['composantes-demographiques-projetees-mrc-du-quebec.xlsx', 'composantes-demographiques-projetees-scenarios-mrc-quebec.xlsx', 'population-et-composantes-demographiques-projetees-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx']

## 3b. Residual (i) — is the RA↔MRC axis EDITION-SPECIFIC? (RECORDED, non-gating)

Every one of the 15 verified candidates is opened and asked the same question its own header row answers. The split is **8 / 3 / 4** — a SEPARATE RA column / an RA grouping NAMED in the geography header only / neither.

That middle state is kept distinct on purpose. Three editions head their GEOGRAPHY column `MRC par région administrative`: that cell NAMES an RA grouping, but there is no second column, so **no RA code can be read per MRC** from those files. Counting them with the `RA1` editions would report a machine-readable axis where none exists — and the v1 constraint turns on exactly that difference.

Each row's edition is its OWN caption cell, verbatim. This run does NOT rank the editions by recency: no live response states which is current, so that judgment is left to the reader with the captions in front of them.

| candidate (slug) | opened? | geography header | RA axis | caption cell A1 (verbatim) |
|---|---|---|---|---|
| `composantes-demographiques-projetees-mrc-du-quebec.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Composantes démographiques projetées, scénario Référence A2021, MRC du Québec, 2020-2041* |
| `composantes-demographiques-projetees-scenarios-mrc-quebec.xlsx` | yes | `MRC` | **none** | *Composantes démographiques projetées, scénarios de 2025, MRC du Québec, 2024-2051* |
| `nombre-de-menages-prives-projetes-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | yes | `MRC par région administrative` | NAMED IN THE GEOGRAPHY HEADER ONLY (`MRC par région administrative`, col 1 = the geography column) — no per-MRC RA code | *Nombre de ménages privés projetés, scénario Référence (A), MRC du Québec, 2016-2041* |
| `nombre-de-menages-prives-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Nombre de ménages privés, scénario Référence (A), MRC du Québec, 2016-2041* |
| `nombre-de-menages-prives-scenario-reference-a2021-mrc-du-quebec-2020-2041.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Nombre de ménages privés, scénario Référence A2021, MRC du Québec, 2020-2041* |
| `nombre-de-menages-prives-selon-le-groupe-dage-de-la-personne-reference-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Nombre de ménages privés selon le groupe d'âge de la personne-référence, scénario Référence (A), MRC du Québec, 2016-2041* |
| `nombre-menages-prives-selon-groupe-age-de-la-personne-reference-scenario-reference-a2021-mrc-du-quebec-2020-2041.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Nombre de ménages privés selon le groupe d'âge de la personne-référence, scénario Référence A2021, MRC du Québec, 2020-2041* |
| `nombre-total-menages-prives-projetes-mrc.xlsx` | yes | `MRC` | **none** | *Nombre total de ménages privés, scénarios de 2025, MRC du Québec, 2021-2051* |
| `part-des-grands-groupes-dage-et-age-moyen-de-la-population-des-mrc-du-quebec-scenario-reference-a-2016-et-2041.xlsx` | yes | `MRC par région administrative` | NAMED IN THE GEOGRAPHY HEADER ONLY (`MRC par région administrative`, col 1 = the geography column) — no per-MRC RA code | *Part des grands groupes d'âge et âge moyen de la population des MRC du Québec, scénario Référence (A), 2016 et 2041* |
| `population-age-sexe-scenarios-mrc-quebec.xlsx` | yes | `MRC` | **none** | *Population selon l'âge et le sexe, scénarios de 2025, MRC du Québec, 2021-2051* |
| `population-et-composantes-demographiques-projetees-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Population et composantes démographiques projetées, scénario Référence (A), MRC du Québec, 2016-2041* |
| `population-projetee-des-mrc-du-quebec-scenario-reference-a-2016-2041.xlsx` | yes | `MRC par région administrative` | NAMED IN THE GEOGRAPHY HEADER ONLY (`MRC par région administrative`, col 1 = the geography column) — no per-MRC RA code | *Population projetée des MRC du Québec, scénario Référence (A), 2016-2041* |
| `population-selon-lage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Population selon l'âge et le sexe, scénario Référence (A), MRC du Québec, 2016-2041* |
| `population-selon-le-groupe-dage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx` | yes | `MRC` | **SEPARATE column `RA1`** (col 2) | *Population selon le groupe d'âge et le sexe, scénario Référence (A), MRC du Québec, 2016-2041* |
| `population-totale-projetee-scenarios-mrc-quebec.xlsx` | yes | `MRC` | **none** | *Population totale, scénarios de 2025, MRC du Québec, 2021-2051* |

- **Measured consequence for a v1 extension.** The axis IS edition-specific: 8 opened candidate(s) publish a separate RA column, 3 name the grouping in the geography header only, and 4 carry neither. So a v1 that pins a workbook from either of the latter two groups would get its projection values and its machine-readable RA↔MRC axis from DIFFERENT workbooks — a cross-edition join. This run does NOT validate such a join: it tests no label-set agreement, no vintage compatibility and no reconciliation between any two editions. That is a v1 design constraint, recorded here.
- **Caption co-occurrence (computed over ALL THREE groups, NOT a recency ranking).** Marker(s) ['scénarios de 2025']: carried by 4/4 of the no-axis files, 0/8 of the separate-RA-column files and 0/3 of the header-named-only files (marker `scénarios de 2025`). The separation is between the no-axis and separate-column groups; the header-named-only group's counts are printed rather than folded into that claim, because it is a THIRD state and a two-group separation says nothing about it. This run tests only CO-OCCURRENCE: it does not claim the marker causes the absence, does not rank the editions, and says nothing about files outside the swept set.
- Scope asymmetry, stated because the two halves differ: the *candidate population* is sweep-scoped (every verified candidate in §2), while each *edition label* is file-scoped (that workbook's own caption). And this whole section is HEADER-ROW-scoped — only the first 12 rows of each non-picked candidate were read, so it says nothing about their data below the header.

## 3c. Residual (ii) — membership vs partition (RECORDED, non-gating)

§3 established MEMBERSHIP: each declared target is present, under the RA number this file declares for it. This section asks the harder question — **EXHAUSTION**: what is the FULL set of MRCs the opened workbook assigns to each declared RA, and how do the declared targets relate to it? Rows in the `NN  Name` administrative-region-SUBTOTAL form are EXCLUDED from these sets (they are the RA's own subtotal line, not one of its MRCs); the exclusion count is printed per RA so it can be checked.

| declared RA | MRCs the workbook assigns to it | declared targets | relation | RA-subtotal rows excluded |
|---|---:|---:|---|---:|
| RA14 Lanaudière | 6 | 2 | **PROPER SUBSET — declared targets do NOT exhaust this RA** | 0 |
| RA15 Laurentides | 8 | 4 | **PROPER SUBSET — declared targets do NOT exhaust this RA** | 0 |
| RA16 Montérégie | 15 | 4 | **PROPER SUBSET — declared targets do NOT exhaust this RA** | 0 |

The MRCs each declared RA carries, verbatim, with the declared targets marked — so the relation above is checkable rather than taken:

- **RA14 Lanaudière** -> D'Autray, Joliette, **L'Assomption**, **Les Moulins**, Matawinie, Montcalm
  - present in the workbook but NOT declared by this file: ["D'Autray", 'Joliette', 'Matawinie', 'Montcalm']
- **RA15 Laurentides** -> Antoine-Labelle, Argenteuil, **Deux-Montagnes**, **La Rivière-du-Nord**, Les Laurentides, Les Pays-d'en-Haut, **Mirabel**, **Thérèse-De Blainville**
  - present in the workbook but NOT declared by this file: ['Antoine-Labelle', 'Argenteuil', 'Les Laurentides', "Les Pays-d'en-Haut"]
- **RA16 Montérégie** -> Acton, Beauharnois-Salaberry, Brome-Missisquoi, La Haute-Yamaska, **La Vallée-du-Richelieu**, Le Haut-Richelieu, Le Haut-Saint-Laurent, Les Jardins-de-Napierville, Les Maskoutains, Longueuil, **Marguerite-D'Youville**, Pierre-De Saurel, **Roussillon**, Rouville, **Vaudreuil-Soulanges**
  - present in the workbook but NOT declared by this file: ['Acton', 'Beauharnois-Salaberry', 'Brome-Missisquoi', 'La Haute-Yamaska', 'Le Haut-Richelieu', 'Le Haut-Saint-Laurent', 'Les Jardins-de-Napierville', 'Les Maskoutains', 'Longueuil', 'Pierre-De Saurel', 'Rouville']

- **What the relation means, and only that.** A `PROPER SUBSET` says the declared targets are SOME of the MRCs this workbook puts under that RA — so this file's own RA grouping is WIDER than the couronne set declared here, and the declared set therefore does NOT exhaust the RA. That is a statement about this file's RA assignment; it is NOT a statement about which MRCs belong to the couronne, which nothing here measures.

- **What this workbook CANNOT answer, measured rather than asserted.** Whether the declared MRCs exactly COMPOSE the Montréal RMR couronne is a metropolitan-area question. Matching the metropolitan-area markers ['rmr', 'cma', 'métropolitaine', 'metropolitaine', 'metropolitan'] against this file's own header cells and geography labels yields **0 + 0** hits respectively — with zero of each, nothing in this file's geography axis names a metropolitan area, so the file supplies no RMR membership for any MRC and the couronne-composition question is NOT ANSWERABLE from it. Per steering ruling G this run deliberately does NOT consult a second source to close it: the limit is the result. Either way this changes no verdict: §11.6 stands — a find enables v1, never v0.

## 4. Spec-premise cross-check (RECORDED, non-gating, READ-ONLY)

- Read live from `docs/specs/2026-07-21-demoflow-demographic-scenario-module-design.md` (READ-ONLY; this probe never writes there). Row located by the marker `'couronne-nord precision'`.
- **State: AMENDED** — old-premise marker 'no mrc workbook exists' absent; amended marker 'mrc-level isq projection workbooks exist' PRESENT.
- Quoted verbatim from the spec as it stands NOW: *"| RA14/15/16 rows carry `ra_proxy` (exact RA data used as couronne/periphery proxies — ranking members, never balance participants, never emitted in ScenarioPrior); Laval is exact (RA13 ≡ ville); couronne-nord precision is DEFERRED to v1 (§11.6: a find enables v1, never v0). MRC-level ISQ projection workbooks EXIST — the 2026-07-21 'no MRC workbook (404)' finding was a METHOD ARTIFACT: HEAD 404s where GET 200s on ISQ's descriptive-French slugs, and the original probe's guessed slugs also 404 on GET, so absence was a property of slug + verb, never the data (P6 probe + independent steering re-verification, 2026-07-28; discovery path = sitemap.xml, 3,273 xlsx locs). v1 is PARKED behind two recorded residuals: the RA↔MRC axis is EDITION-SPECIFIC (present in A2021, absent from the 2025 scenarios workbook), and membership-vs-partition of RA14/15/16 vs the RMR couronne is not yet computed |"*

  Why this is read rather than typed: this note's DECISION block cites spec §8. A typed quote of a locked artifact goes stale the moment the artifact is amended — which is exactly what happened here — and a stale quote is a claim nothing computed. Nothing in this section moves the verdict.

## 5. DECISION

- `DECISION-VERDICT: LOCATED`
- `DECISION-RESOURCE-URL: https://statistique.quebec.ca/fr/fichier/composantes-demographiques-projetees-mrc-du-quebec.xlsx`
- `DECISION-HTTP-STATUS: 200 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, Content-Length 517264)`  (observed by GET this run; the same url answered HTTP 404 to HEAD — the methods DISAGREE here, so a HEAD-only hunt would miss this file)
- `DECISION-BODY-SHAPE: 517264 bytes downloaded, magic-byte prefix matches 504b0304, opened to sheets ['Référence A2021'], MRC header cell at row 2 column 1, 122 distinct geography labels, no scenario column in this sheet`
- `DECISION-MRC-LABEL-COUNT: 122 (17 of them in the NN-Name administrative-region-subtotal form + 105 others)`  (distinct labels below the MRC-named header of the opened workbook. Precisely: the header NAMES an MRC axis and this count says that column is populated. It is NOT an MRC count — the column interleaves RA subtotals, hence the split; the full label list is emitted verbatim in §3. And it says NOTHING about the couronne — a large label set is equally consistent with the couronne being absent — which is why the per-target search below is a separate token)
- `DECISION-COURONNE-TARGETS: 10 of 10 declared couronne MRC targets found by exact name search — ALL declared targets present`
- `DECISION-RA-CORRESPONDENCE: 10 of 10 declared targets corroborated against the opened workbook's own RA column (column 2, header 'RA1')`  (MEMBERSHIP only, and only what was measured: all 10 declared targets present, each carrying the RA code this file declares for it. EXHAUSTION is a different question and is computed separately in §3c; the RMR-couronne composition is measured there to be unanswerable from this workbook. See DECISION-RESIDUAL-II below)
- `DECISION-SWEPT-POPULATION: the 25543 ISQ sitemap locs swept in §2 (22 matched the MRC×population predicate, 15 eligible) and the 8 CKAN packages swept in §1 from a 1617-package catalogue`
- `DECISION-SPEC-PREMISE: ALREADY AMENDED — no live conflict remains`  (state read LIVE from the spec in §4 — old-premise marker 'no mrc workbook exists' absent; amended marker 'mrc-level isq projection workbooks exist' PRESENT. MEASURED THIS RUN: the plan's guessed slugs `pop-as-mrc-base.xlsx` -> HTTP 404, `pop-mrc-base.xlsx` -> HTTP 404, while the resource above answers 200 with a body this run opened and shape-checked. The two together say the 404 was a property of the GUESSED SLUG CONVENTION, not of the data. This note never edits the spec.)
- `DECISION-RESIDUAL-I-RA-AXIS: of 15 candidate workbooks opened, 8 publish a SEPARATE administrative-region column, 3 name the grouping in the geography header ONLY (no per-MRC RA code), 4 carry neither; the axis is EDITION-SPECIFIC, so a v1 pinning an edition from the latter two groups must source it from a different workbook — an unvalidated cross-edition join`  (RECORDED OBSERVATION — see §3b; changes no verdict. This run does not rank the editions by recency: no live response states which is current)
- `DECISION-RESIDUAL-II-PARTITION: membership 10 of 10 (§3); exhaustion RA14 Lanaudière -> PROPER SUBSET; RA15 Laurentides -> PROPER SUBSET; RA16 Montérégie -> PROPER SUBSET; RMR-couronne composition NOT ANSWERABLE from this workbook (0 header cells and 0 geography labels match a metropolitan-area marker)`  (RECORDED OBSERVATION — see §3c; changes no verdict. No second source was consulted to close it, per steering ruling G)

- **Standing rule (spec §11.6): v0 PROCEEDS REGARDLESS.** A find enables a **v1** `Geography` enum extension for couronne-nord precision — never a v0 change. In v0 the RA14/15/16 rows keep their `ra_proxy` flag (spec §8): they remain ranking members, never balance participants, never emitted in `ScenarioPrior`. Nothing in this note licenses a v0 loader change.

