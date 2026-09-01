# Closed-cohort migration assumption — evidence (spec §5 r3-F2)

Written by `probes/run_p7.py`; nothing in this file is hand-edited.

Scope: spec §5 r3-F2's closed-cohort omission — the 75+ net-migration rate it omits, measured over the FULL published span of StatCan's components-of-population-change and population-estimate cubes, per modeled geography.
This run registered 23 provenance-tagged figures: 17 DERIVED (computed here from the live responses named beside them) and 6 CITED (published elsewhere, quoted with their source).

Externally cited figures (NOT computed by this run):
- 1.000 %/yr — spec §5 r3-F2 MATERIALITY TRIPWIRE (steering ruling J, 2026-08-07)
- THE OMISSION STANDS for Tranche 1 — spec §5 r3-F2 STEERING RULING K (operator-ruled at the tripwire escalation, 2026-08-07)
- Components of population change by census metropolitan area and census agglomeration, 2021 boundaries — 17-10-0149-01 live cube metadata
- Components of population change by economic region, 2021 boundaries — 17-10-0151-01 live cube metadata
- Population estimates, July 1, by census metropolitan area and census agglomeration, 2021 boundaries — 17-10-0148-01 live cube metadata
- Population estimates, July 1, by economic region, 2021 boundaries — 17-10-0150-01 live cube metadata


## Decision block

- `DECISION-VERDICT: EVIDENCED-WITH-NAMED-EXCEEDANCE`
- `DECISION-SPAN: 2001/02–2024/25, 24 periods (the FULL published span)`
- `DECISION-COVERAGE: 7 of 8 modeled geographies MEASURED, 1 NOT-COVERED (HORS_RMR)`
- `DECISION-IDENTITY: EXACT — max |difference| 0 person`
- `DECISION-MAX-RATE: 1.6722 %/yr at LAVAL_RA13 2007/08`
- `DECISION-TRIPWIRE: FIRED — 3 geography-period(s) above 1.000 %/yr [cited: spec §5 r3-F2 MATERIALITY TRIPWIRE (steering ruling J, 2026-08-07)], in 1 of 7 measured geographies (LAVAL_RA13)`
- `DECISION-WINDOW-CONTRAST: latest-5-period max 0.7738 %/yr vs full-span max 1.6722 %/yr — the FULL SPAN rules`
- `DECISION-RESOLUTION: THE OMISSION STANDS for Tranche 1 [cited: spec §5 r3-F2 STEERING RULING K (operator-ruled at the tripwire escalation, 2026-08-07)]`

## 1. What the omission is

The 75+ owner roll-forward is CLOSED after band entry: post-entry net migration at
ages 75+ is OMITTED. That is a STATED ASSUMPTION with a sensitivity remark in
outputs — not a modeled mechanism. Spec §5 r3-F2 attaches a MATERIALITY TRIPWIRE to
it: a measured 75+ net-migration rate above 1.000 %/yr [cited: spec §5 r3-F2 MATERIALITY TRIPWIRE (steering ruling J, 2026-08-07)] in any modeled geography
escalates the altitude call back to the operator. The spec's stated rationale for
that level: 75+ all-cause exit hazards run ≥10%/yr, so a 1%/yr cap keeps the
omission's relative distortion near or under 10%.

## 2. The measured 75+ net-migration rate

### 2a. Sources (titles quoted verbatim from live cube metadata)

| table | productId | title | role in this measurement |
|---|---|---|---|
| [17-10-0149-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710014901) | `17100149` | Components of population change by census metropolitan area and census agglomeration, 2021 boundaries [cited: 17-10-0149-01 live cube metadata] | components numerator, CMA axis |
| [17-10-0151-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015101) | `17100151` | Components of population change by economic region, 2021 boundaries [cited: 17-10-0151-01 live cube metadata] | components numerator, economic-region axis |
| [17-10-0148-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710014801) | `17100148` | Population estimates, July 1, by census metropolitan area and census agglomeration, 2021 boundaries [cited: 17-10-0148-01 live cube metadata] | July-1 population denominator, CMA axis |
| [17-10-0150-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015001) | `17100150` | Population estimates, July 1, by economic region, 2021 boundaries [cited: 17-10-0150-01 live cube metadata] | July-1 population denominator, economic-region axis |

Release stamp carried by the components cubes' metadata: `2026-01-14T08:30`. MEASURED on this run's own metadata: 17-10-0149-01 publishes 114 age members and 17-10-0148-01 publishes 115 age members, and `75 to 79 years` resolves to member 93 in the first against 92 in the second. Member ids are therefore resolved BY NAME on every run: `_member` raises rather than falling back to a remembered id.

### 2b. What the rate is

```
net_migration(g, t) = Σ over {75 to 79 years, 80 to 84 years, 85 to 89 years, 90 years and older} of
    Immigrants − Net emigration + Net interprovincial migration
               + Net intraprovincial migration + Net non-permanent residents
rate(g, t)          = |net_migration(g, t)| / P75plus(g, t)
P75plus(g, t)       = July-1 START-of-period 75+ population, same geography,
                      summed over the same four bands
```

`Net emigration` enters WHOLE. `Emigrants`, `Returning emigrants` and `Net temporary
emigration` are its CHILDREN in the cube's own component hierarchy — adding them
beside it double-counts, and `Net temporary emigration` is unpublished from 2016/17
onward, so a build-from-the-parts form would also silently lose the last nine
periods.

### 2c. The floor guards that had to pass first

- **Span** — each of the 231 requested series covers ITS OWN cube's full
  declared span, contiguously; a span is a per-cube quantity, so it is recorded per
  cube:
  17-10-0149-01 (56 series, 24 periods); 17-10-0151-01 (140 series, 24 periods); 17-10-0148-01 (10 series, 25 periods); 17-10-0150-01 (25 series, 25 periods).
  Every components period's FOLLOWING July 1 is present in the population span —
  `_guard_identity` refuses without it. This is ruling K's window rule as code.
- **Published** — no null datapoint outside `Residual deviation`, which carries
  28 of them and enters the identity alone. A null coerced to zero would
  read as a measured zero, and an all-null response as a clean no-exceedance.
- **Identity** — the All-ages demographic accounting identity closes EXACTLY:
  `P(t+1) − P(t) = Births − Deaths + Immigrants − Net emigration + Net
  interprovincial + Net intraprovincial + Net non-permanent residents + Residual
  deviation`. Max |difference| **0 person** over
  168 geography-periods. This is what a mis-resolved geography, a
  mis-paired cube, an off-by-one period join or a flipped component sign fails —
  none of which a single-series check can see.
- **Coverage** — every modeled geography resolves to a live member whose
  classification code matches the declared one, or is recorded NOT-COVERED below.

### 2d. Full published span, per modeled geography

Span **2001/02–2024/25** (24 periods), 168 geography-periods measured.
`at-period` is the flow interval 1 July t → 1 July t+1.

| modeled geography | role | source axis | live member (class code) | max \|rate\| %/yr | at-period | n > tripwire |
|---|---|---|---|---:|---|---:|
| MTL_RMR | modeled member | census metropolitan area | Montréal (CMA), Quebec (`462`) | 0.1759 | 2022/23 | 0 |
| QC_RMR | modeled member | census metropolitan area | Québec (CMA), Quebec (`421`) | 0.5011 | 2024/25 | 0 |
| MTL_ISLAND_RA06 | modeled member | economic region (= RA06) | Montréal, Quebec (`2440`) | 0.8113 | 2009/10 | 0 |
| LAVAL_RA13 | modeled member | economic region (= RA13) | Laval, Quebec (`2445`) | 1.6722 | 2007/08 | 3 |
| LANAUDIERE_RA14_PROXY | ranking proxy (`ra_proxy`) | economic region (= RA14) | Lanaudière, Quebec (`2450`) | 0.6732 | 2006/07 | 0 |
| LAURENTIDES_RA15_PROXY | ranking proxy (`ra_proxy`) | economic region (= RA15) | Laurentides, Quebec (`2455`) | 0.7814 | 2002/03 | 0 |
| MONTEREGIE_RA16_PROXY | ranking proxy (`ra_proxy`) | economic region (= RA16) | Montérégie, Quebec (`2435`) | 0.5492 | 2017/18 | 0 |
| HORS_RMR | modeled member | **NOT-COVERED** | — | — | — | — |

**HORS_RMR is NOT-COVERED, never approximated:** the residual 'territory outside the CMAs' is neither a census metropolitan area nor an economic region, so NEITHER cube publishes it; a province-minus-CMAs residual would manufacture an age-structured migration series no source published. It is
therefore NOT evaluated against the tripwire, and is recorded as unevaluated —
an unevaluated geography is not a passing one.

### 2e. The named exceedances

3 geography-period(s) exceed the tripwire, all in LAVAL_RA13:

| geography | period | 75+ net migration | 75+ population (1 July, start) | rate %/yr |
|---|---|---:|---:|---:|
| LAVAL_RA13 | 2007/08 | +400 | 23,921 | **1.6722** |
| LAVAL_RA13 | 2008/09 | +295 | 25,515 | **1.1562** |
| LAVAL_RA13 | 2009/10 | +282 | 27,095 | **1.0408** |

Every geography that never exceeds the tripwire peaks at **0.8113 %/yr** (MTL_ISLAND_RA06 2009/10).

## 3. Tripwire evaluation and the OPERATOR RESOLUTION (steering ruling K)

**Evaluated on the FULL published span** (2001/02–2024/25, 24 periods): the
tripwire **FIRED** — 3 geography-period(s)
above it.

The same measurement restricted to the latest 5 periods
(2020/21–2024/25) peaks at 0.7738 %/yr,
against a full-span peak of 1.6722 %/yr. That window is RECORDED and REFUSED as
evidence, per ruling K: a window whose sole visible effect is to remove the
exceedance is not evidence. The full span rules.

**OPERATOR RESOLUTION (2026-08-07):** THE OMISSION STANDS for Tranche 1 [cited: spec §5 r3-F2 STEERING RULING K (operator-ruled at the tripwire escalation, 2026-08-07)]. The verdict form is
`EVIDENCED-WITH-NAMED-EXCEEDANCE` — the omission is evidenced rather than
unevidenced-pending, and the exceedance it carries is named rather than smoothed by a
window. Every ranking row of an exceeding geography carries the
`closed_cohort_exceedance` flag (added to the closed flags enum by the same
amendment). That flag's WIRING is the rankings task's job; this note records the
ruling, not its implementation. The omission remains a stated assumption with a
sensitivity remark in outputs, not a modeled mechanism; adding a reconciled
post-entry migration term without reintroducing ISQ-embedded mortality is a v1 item.

## 4. What the ISQ compo source cannot establish (ruling J's refuted prescription)

The spec's ORIGINAL evidence prescription pointed here. Ruling J refuted it for the
committed vintage; the section is kept because that refutation is the record of why
§2's source had to be found at all.

### What the compo workbooks cannot establish

The spec asks for the 75+ net-migration share as the assumption's evidence. It is
**not computable from the compo workbooks: they carry no age axis** (no `Âge`, no
`Groupe d'âge` column — only region x scenario x year). The omitted 75+ term is
therefore **unbounded by this source alone**; bounding it needs an age-structured
migration source (ISQ migration-by-age tables or StatCan components by age), which
is what §2 above supplies.

### Observable ALL-AGE magnitudes — flow-interval years 2025-2050, per scenario x geography

`year` semantics: `year` is the ISQ flow-interval START: the row labeled t covers 1 July t -> 1 July t+1 (the sheet's own 'Année / du 1er juillet / de (t) à (t+1)' header) and it lands in Population(t+1), NOT Population(t). A §6 consumer that subtracts arrivals(year=t) from P_ISQ(t) mis-times every arrival cohort by one year.

| geography | scenario | Σ immigrants_permanents | Σ npr_net_flow |
|---|---|---:|---:|
| HORS_RMR | high | 172,685 | 928 |
| HORS_RMR | low | 70,146 | -14,907 |
| HORS_RMR | reference | 121,390 | -6,990 |
| MTL_RMR | high | 999,999 | -109,954 |
| MTL_RMR | low | 414,450 | -214,149 |
| MTL_RMR | reference | 707,199 | -162,051 |
| QC_RMR | high | 305,918 | -2,755 |
| QC_RMR | low | 124,088 | -15,815 |
| QC_RMR | reference | 215,013 | -9,284 |

These are ALL-AGE flows. The spec's assumption asserts that senior migration flows
are thin; this source can neither corroborate nor refute that, because it carries no
age axis. The magnitudes above are therefore CONTEXT for the assumption — the scale
of the all-age flows the omitted 75+ term is a sub-share of — never its bound.

