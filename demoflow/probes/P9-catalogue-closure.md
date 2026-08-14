# P9 — full-catalogue MEMBER-LEVEL closure sweep (StatCan WDS)

Written by `probes/run_p9.py`; nothing in this file is hand-edited.

Every figure below is COMPUTED by that run from the cached full-catalogue pull it names — the catalogue count, every match count, every listed cube and the pull digest alike. Nothing here is a remembered result: the closure claim is only as good as the pull it is derived from, and that pull is pinned by digest so the claim can be re-checked.
This run registered 15 provenance-tagged figures: 15 DERIVED from the cached pull and 0 CITED from sources outside it.

## Decision block

- `DECISION-VERDICT: CLOSED-AT-MEMBER-LEVEL`
- `DECISION-CLOSURE-LEVEL: dimension names AND every member name, all 8226 catalogue cubes`
- `DECISION-CATALOGUE-COUNT: 8226`
- `DECISION-RESOLVED-COUNT: 8226`
- `DECISION-CUBE-LIST-VINTAGE: pulled 2026-08-14, latest releaseTime in catalogue 2026-08-14T12:30:00Z`
- `DECISION-RAW-PULL-SHA256: ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a`
- `DECISION-INDEX-ARTIFACT: demoflow/data/catalogue_member_index_p9.json sha256 4e5f5bcff318cc7c25090582a2adbb1f85f3c23b9c2cf7ea429dde0c8e053fec`
- `DECISION-FLAGGED-COUNT: 878`
- `DECISION-MAINTAINER-CROSS: 4 cubes — 98-10-0621-01, 98-10-0622-01, 98-10-0623-01, 98-10-0624-01`
- `DECISION-POSITIVE-CONTROL: 98-10-0621-01, 43-10-0060-01 both FLAGGED`
- `DECISION-RESIDUAL: vocabulary-scoped; English member/dimension names only; StatCan WDS only`

## 1. What was scanned, and why the whole catalogue

Three absence claims in this arc were refuted by a cube the SEARCH could not see:
ruling F (HEAD against a host whose HEAD 404s on a GET-200 path, over guessed slugs),
ruling Q (a product-family + title-tier scope, which hid 43-10-0060-01) and ruling S
(selection on dimension NAMES, which hid 98-10-0621-01 — a cube carrying immigrant
status as MEMBERS of a `Population characteristics (46)` dimension). Each fix was
narrower than the failure, so this sweep does not select at all.

- Catalogue: **8226** cubes from `getAllCubesListLite`.
- Metadata resolved: **8226** cubes via `getCubeMetadata`, with NO title,
  family, subject or dimension pre-filter.
- Read: **29,741** dimension names and **2,282,860** member names.
- Pull wall clock: **1211s**, batch size 60.
- Raw pull sha256 (canonical form): `ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a`.

The raw pull is **5.29 GB** on disk — measured by this run, not estimated — and is
NOT committed. What is committed is the compact derived index
`demoflow/data/catalogue_member_index_p9.json`, pinned in `pins.WORKBOOK_SHA256`, with the
pull's digest pinned separately in `pins.RAW_SOURCE_SHA256` — the same DIV-F2 pattern
the 850 MB P2 upstream member uses. The digest is taken over a CANONICAL
re-serialization (catalogue first, then one response per line in productId order,
sorted keys, compact separators), because wire bytes are not stable across batch
boundaries and would anchor nothing.

## 2. The match rule (this IS the verdict's scope)

For each cube, each vocabulary is matched as a SUBSTRING against the normalized
`dimensionNameEn` of every dimension AND the normalized `memberNameEn` of every member
of every dimension. Normalization: NBSP -> space, whitespace runs collapsed, casefold.
The NBSP leg is not hypothetical — 43-10-0060-01's geography labels carry trailing
NBSPs while 98-10-0621-01's do not.

- IMMIGRANT-ish (13 terms): `immigrant`, `immigration`, `generation status`, `admission category`, `period of immigration`, `place of birth`, `citizenship`, `landed`, `permanent resident`, `non-permanent resident`, `newcomer`, `birthplace`, `migrant`
- HOUSEHOLD-ish (11 terms): `household maintainer`, `primary household maintainer`, `tenure`, `owner`, `renter`, `dwelling`, `housing`, `household size`, `persons per household`, `household type`, `shelter`

A vocabulary is **member-only** for a cube when it hits a member name and NO dimension
name. The **FLAGGED** class is: both vocabularies hit, at least one of them member-only.
That is the class 43-10-0060-01 and 98-10-0621-01 both fall into, and the class a
dimension-name search structurally cannot see.

Geography dimensions are detected STRUCTURALLY (any dimension with a member carrying a
non-null `geoLevel`), never by the dimension being NAMED `Geography` — a name test is
the same class of selection rule that hid 98-10-0621-01. CMA reach is the UNION of
`geoLevel` in [503, 505] and a member name containing
'(cma)' or '(rmr)'.

## 3. What the sweep found

| class | cubes |
|---|---:|
| **FLAGGED** — both vocabularies, >=1 member-only | **878** |
| both vocabularies, both at dimension level | 9 |
| exactly one vocabulary | 1660 |
| neither vocabulary | 5679 |
| catalogue total | 8226 |

Of the 878 FLAGGED cubes, **24** reach CMA geography.

The FLAGGED class is deliberately OVER-inclusive — it is a sensitivity floor, not a
shortlist. Read the titles in §3a: the `Canadian Business Counts` and
`Access to public transport` rows match on NAICS- and transit-worded members, not on
anything about immigrant households. That is the correct behaviour for an instrument
whose job is to miss nothing; §3b is where the question is asked narrowly.

**POSITIVE CONTROL.** 98-10-0621-01, 43-10-0060-01 are the two cubes whose misses produced rulings
Q and S. Both are re-found here in the FLAGGED class, by the floor guard rather than by
inspection: a sweep that could not re-find them would refuse to publish a verdict at
all, whatever totals it computed.

### 3a. The FLAGGED cubes that reach CMA

| table | title | immigrant match | household match | CMA |
|---|---|---|---|---|
| 23-10-0313-01 | Access to public transport by distance and public transport carrying capacity, geography, gender, and selected demographic and socio-economic characteristics, inactive | member-only | member-only | yes |
| 23-10-0314-01 | Access to public transport by distance and public transport carrying capacity, geography, gender, selected demographic and socio-economic characteristics, and count of public transport stops | member-only | member-only | yes |
| 33-10-0269-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, June 2020 | member-only | member-only | yes |
| 33-10-0306-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, December 2020 | member-only | member-only | yes |
| 33-10-0397-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, June 2021 | member-only | member-only | yes |
| 33-10-0495-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, December 2021 | member-only | member-only | yes |
| 33-10-0576-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, June 2022 | member-only | member-only | yes |
| 33-10-0663-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, December 2022 | member-only | member-only | yes |
| 33-10-0719-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, June 2023 | member-only | member-only | yes |
| 33-10-0763-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, June 2024 | member-only | member-only | yes |
| 33-10-0766-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, December 2024 | member-only | member-only | yes |
| 33-10-0808-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, December 2023 | member-only | member-only | yes |
| 33-10-1016-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, June 2025 | member-only | member-only | yes |
| 33-10-1097-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, December 2025 | member-only | member-only | yes |
| 33-10-1176-01 | Canadian Business Counts, with employees, census metropolitan areas and census subdivisions, June 2026 | member-only | member-only | yes |
| 43-10-0060-01 | Selected housing characteristics, low income indicators and knowledge of official languages, by visible minority and other characteristics for the population in private households | both | member-only | yes |
| 43-10-0073-01 | Selected economic housing characteristics, by visible minority and other sociodemographic characteristics for the population in private households | both | member-only | yes |
| 46-10-0025-01 | Immigrant status and selected places of birth for residential property owners in the census metropolitan areas of Toronto and Vancouver | both | member-only | yes |
| 46-10-0026-01 | Immigrant status and selected admission categories for residential property owners in the census metropolitan areas of Toronto and Vancouver | both | member-only | yes |
| 46-10-0052-01 | Single and multiple residential property owners by immigration characteristics, inactive | both | member-only | yes |
| 46-10-0098-01 | Residential property owners by immigration characteristics | both | member-only | yes |
| 98-10-0597-01 | Employment income statistics by industry sectors, highest level of education, immigrant status and period of immigration, work activity during the reference year, age and gender: Canada, provinces and territories, census metropolitan areas and census agglomerations with parts | both | member-only | yes |
| 98-10-0621-01 | Population groups by housing suitability and condition of dwelling: Canada, provinces and territories, census metropolitan areas and census agglomerations | member-only | both | yes |
| 98-10-0623-01 | Population groups by shelter cost: Canada, provinces and territories, census metropolitan areas and census agglomerations | member-only | both | yes |

The full listing — every cube matching BOTH vocabularies at any level, with the
dimension and member names that matched — is the committed index
`demoflow/data/catalogue_member_index_p9.json`. Single-vocabulary and non-matching cubes are counted
in that file's `class_counts` and not enumerated: listing them would be most of the
catalogue, and a 5.29 GB copy of the pull is not an index.

### 3b. The DIRECT fork-class cross — a maintainer DIMENSION with immigrant vocabulary

Narrower than the FLAGGED class and asked directly: **exactly 4 cubes** in the whole catalogue
carry a `household maintainer` DIMENSION together with any immigrant-vocabulary
term at either level — 98-10-0621-01, 98-10-0622-01, 98-10-0623-01, 98-10-0624-01.
No other cube in the catalogue carries that maintainer dimension alongside immigrant
vocabulary at any level at all.

| table | title | immigrant match | CMA |
|---|---|---|---|
| 98-10-0621-01 | Population groups by housing suitability and condition of dwelling: Canada, provinces and territories, census metropolitan areas and census agglomerations | member-only | yes |
| 98-10-0622-01 | Population groups by housing suitability and condition of dwelling: Canada, provinces and territories, census divisions and census subdivisions | member-only | no |
| 98-10-0623-01 | Population groups by shelter cost: Canada, provinces and territories, census metropolitan areas and census agglomerations | member-only | yes |
| 98-10-0624-01 | Population groups by shelter-cost-to-income ratio groups and core housing need: Canada, provinces and territories, census divisions and census subdivisions | member-only | no |

Read against the rulings this arc already carries: 98-10-0621-01 is the CMA cube ruling
S draws both immigrant inputs from; 98-10-0622-01 is its census-division/subdivision
sibling, which ruling T measures RA06 and RA13 from; 98-10-0623-01 (CMA) and
98-10-0624-01 (CD/CSD) carry the same cross in the shelter-cost family and are recorded
as available CORROBORATION, not used by the module.

This is a property of a VINTAGE, not an invariant of the method, so it is recorded and
left falsifiable rather than made a floor guard: a later catalogue may legitimately
publish a fifth such cube, and a guard here would turn a StatCan release into a probe
failure. It moves with the pull digest above, which is what makes it re-checkable.

## 4. The closure, stated at the level actually achieved

**The search is closed at MEMBER level over the full StatCan WDS catalogue as of the
pull of 2026-08-14 (8226 cubes, raw pull sha256 `ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a`).**
Every cube's dimension names and every one of its member names were read and matched
against both vocabularies. No cube was excluded by title, product family, subject,
release date, archive status or dimension name.

**What this does NOT close — named, not buried:**

1. **Vocabulary.** A cube whose relevant axis is worded outside the two lists in §2 is
   not reached by this sweep. The lists are printed above precisely so a reader can
   judge them: e.g. an axis worded only as `country of origin`, `mother tongue`,
   `visible minority`, `ethnic origin`, `occupancy`, `condominium` or `household
   composition` carries no term from either list. This is a REAL residual and the
   honest limit of a substring sweep.
2. **Language.** Only `cubeTitleEn`, `dimensionNameEn` and `memberNameEn` were scanned.
   A cube whose English naming differs from its French naming in a way that moves a
   term out of the vocabulary is not reached.
3. **Punctuation forms.** Matching is a plain substring test after NBSP and whitespace
   normalization: a name spelling `non\u2011permanent` with a non-breaking hyphen, or
   hyphenating a multi-word term differently, is not reached.
4. **Everything outside StatCan WDS.** ISQ, IRCC, CMHC, JLR, municipal rôle and every
   other publisher are entirely outside this sweep's universe.

This note therefore makes NO unscoped absence claim — it does not assert that nothing
further exists. It says what was scanned, how, and what would still slip through —
which is the standing consequence ruling S records: an absence claim in this arc is
provisional until the search itself has been closed at the level the claim is stated
at, and a scoped verdict must name its selection level, not merely its pool.

## 5. Reproducing this

```
cd demoflow && uv run python probes/run_p9.py --pull  --cache DIR   # 1211s -> 5.29 GB, as measured here
cd demoflow && uv run python probes/run_p9.py --cache DIR
```

The derivation is a pure function of the cache: every date and timing figure above is
read from the cache's own `manifest.json`, never from the clock, so re-deriving from
the same pull reproduces this file and the committed index BYTE-FOR-BYTE. A re-pull
that yields a different digest is a new catalogue VINTAGE — re-pin
`pins.RAW_SOURCE_SHA256` deliberately and regenerate both artifacts; the probe refuses
to write against an unpinned or drifted pull.

