# P6 — MRC-level ISQ source hunt (RECORDED OBSERVATION)

Written by `probes/run_p6.py`; nothing in this file is hand-edited.

SCOPE OF THIS HEADER (it claims only what it can enforce): the resolved ISQ organization slug, the CKAN catalogue and swept-package counts, the sitemap loc and .xlsx counts, the swept and eligible candidate lists, every candidate's observed HTTP status / content-type / declared length / magic-byte result, the HEAD-vs-GET comparison, the opened workbook's sheet names, header position, geography-label count and label list, its scenario column, the per-target couronne name search AND the per-target administrative-region corroboration are ALL emitted by this run from live responses. The quoted strings are verbatim from live responses. Every absence claim is scoped to what was actually swept — never to what exists. What this run does NOT compute, and therefore does not claim: that the declared couronne MRCs EXHAUST RA14/15/16, or that they exactly compose the Montréal RMR's couronne — the RA check establishes MEMBERSHIP, not a partition. Nor does it claim anything about the candidates it did not open: exactly ONE workbook is opened and shape-checked, and the §2 table's other rows carry status-and-prefix evidence only.
This run registered 14 provenance-tagged figures: 12 DERIVED (computed from the live responses of this run) and 2 CITED (verbatim from a live response body). Untagged numerals elsewhere are audit metadata (candidate counts, byte lengths, row/column positions, HTTP status codes) and reference labels (slugs, urls, sheet names), each traceable to the live response this run read.

Quoted verbatim from the live responses:
- ISQ's own diffusion geographies, per a live CKAN package's notes — donneesquebec.ca package notes: "Alors que l’ISQ diffuse les données de population par région administrative, MRC, municipalité et RMR, c’est le MSSS qui diffuse les données pour les territoires du réseau de la santé et des services sociaux"
- the opened workbook's own caption — cell A1 of composantes-demographiques-projetees-mrc-du-quebec.xlsx: "Composantes démographiques projetées, scénario Référence A2021, MRC du Québec, 2020-2041"

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
- **The RA↔MRC correspondence — 10 of 10 declared targets corroborated.** This edition DOES publish an administrative-region column (column 2, header `RA1`), so the RA number this file DECLARES for each target is checked against the code the live response puts beside that MRC — an independent witness nothing here controls. Flip a declared key to the wrong RA and the check stops corroborating. Membership is what this establishes; it is NOT a partition. This run does not compute whether these MRCs EXHAUST RA14/15/16, nor whether they exactly compose the Montréal RMR's couronne — a v1 Geography-enum extension needs both, and they remain open. Scoped to the ONE workbook opened here: nothing is claimed about the RA column of the other candidates in the §2 table, which were not opened.

- **Which swept files would feed a v1 extension.** demoflow consumes two ISQ families at RMR level; the DECLARED term map {'pop-as-* (population by age and sex)': ['population', 'age', 'sexe'], 'compo-* (projected demographic components)': ['composantes-demographiques']} is matched against the ELIGIBLE slugs above (a slug match, not a schema comparison — no equivalence between the RMR and MRC editions is tested here):

  - **pop-as-* (population by age and sex)** -> 3 eligible slug(s) match: ['population-age-sexe-scenarios-mrc-quebec.xlsx', 'population-selon-lage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx', 'population-selon-le-groupe-dage-et-le-sexe-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx']
  - **compo-* (projected demographic components)** -> 3 eligible slug(s) match: ['composantes-demographiques-projetees-mrc-du-quebec.xlsx', 'composantes-demographiques-projetees-scenarios-mrc-quebec.xlsx', 'population-et-composantes-demographiques-projetees-scenario-reference-a-mrc-du-quebec-2016-2041.xlsx']

## 4. DECISION

- `DECISION-VERDICT: LOCATED`
- `DECISION-RESOURCE-URL: https://statistique.quebec.ca/fr/fichier/composantes-demographiques-projetees-mrc-du-quebec.xlsx`
- `DECISION-HTTP-STATUS: 200 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, Content-Length 517264)`  (observed by GET this run; the same url answered HTTP 404 to HEAD — the methods DISAGREE here, so a HEAD-only hunt would miss this file)
- `DECISION-BODY-SHAPE: 517264 bytes downloaded, magic-byte prefix matches 504b0304, opened to sheets ['Référence A2021'], MRC header cell at row 2 column 1, 122 distinct geography labels, no scenario column in this sheet`
- `DECISION-MRC-LABEL-COUNT: 122 (17 of them in the NN-Name administrative-region-subtotal form + 105 others)`  (distinct labels below the MRC-named header of the opened workbook. Precisely: the header NAMES an MRC axis and this count says that column is populated. It is NOT an MRC count — the column interleaves RA subtotals, hence the split; the full label list is emitted verbatim in §3. And it says NOTHING about the couronne — a large label set is equally consistent with the couronne being absent — which is why the per-target search below is a separate token)
- `DECISION-COURONNE-TARGETS: 10 of 10 declared couronne MRC targets found by exact name search — ALL declared targets present`
- `DECISION-RA-CORRESPONDENCE: 10 of 10 declared targets corroborated against the opened workbook's own RA column (column 2, header 'RA1')`  (MEMBERSHIP only. This run does NOT compute whether these MRCs partition RA14/15/16 or exactly compose the Montréal RMR's couronne — a v1 Geography-enum extension needs both and they remain open)
- `DECISION-SWEPT-POPULATION: the 25543 ISQ sitemap locs swept in §2 (22 matched the MRC×population predicate, 15 eligible) and the 8 CKAN packages swept in §1 from a 1617-package catalogue`
- `DECISION-SPEC-PREMISE: CONTRADICTED — ESCALATION`  (spec §8 records "no MRC workbook exists — probed 404, 2026-07-21". MEASURED THIS RUN: the plan's guessed slugs `pop-as-mrc-base.xlsx` -> HTTP 404, `pop-mrc-base.xlsx` -> HTTP 404, while the resource above answers 200 with a body this run opened and shape-checked. The two together say the 404 was a property of the GUESSED SLUG CONVENTION, not of the data. This note does NOT edit the spec — the contradiction is escalated, per envelope.)

- **Standing rule (spec §11.6): v0 PROCEEDS REGARDLESS.** A find enables a **v1** `Geography` enum extension for couronne-nord precision — never a v0 change. In v0 the RA14/15/16 rows keep their `ra_proxy` flag (spec §8): they remain ranking members, never balance participants, never emitted in `ScenarioPrior`. Nothing in this note licenses a v0 loader change.

