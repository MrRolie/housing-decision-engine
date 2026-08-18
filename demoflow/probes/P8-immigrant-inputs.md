# P8 — the immigrant inputs: HEADSHIP and OWNERSHIP RATIO (rulings S and T)

Written by `probes/run_p8.py`; nothing in this file is hand-edited.

SCOPE OF THIS HEADER (it claims only what it can enforce): every rate, ratio, count, residual and threshold below is COMPUTED by this run from the live StatCan WDS responses and the two pinned ISQ workbooks it names — none is transcribed from the ruling it is checked against. The direction of that check is one-way: §6 states the ruled figures — ruling S's table row for HORS_RMR's superseded territory and amendment #13 for its ruled one, both recomputed here — and P10's committed note states the aligned territory's counts; this run recomputes each and a disagreement REFUSES the run rather than being published. What is CARRIED rather than recomputed is named where it is used and listed below: P10's membership derivation and P9's catalogue closure, each at the level its own note earned. The threshold in §4 is derived from innocent controls measured here in the same construction, never inherited. Quoted strings are verbatim from a live response, a workbook cell or a named in-repo file, and every absence claim is scoped to the search that produced it.
This run registered 69 provenance-tagged figures: 56 DERIVED (computed here from the live responses and pinned workbooks this run read) and 13 CITED (verbatim from a live response, a workbook header, the spec or a named in-repo file). The tagged set is the NARRATIVE figures — the ones a sentence rests on. Untagged numerals fall in two other classes, both stated rather than left to be assumed: TABLE CELLS, which are counts and rates this run computed from the coordinate-keyed live responses printed in the same row, and AUDIT METADATA — member ids, dimension positions, member counts, geoLevels and row indices. Every one of the three is traceable to a response or a file this run read; none is transcribed from the ruling this note is checked against.

Quoted or cited verbatim (not computed here):
- 8,308,475 — probe P3, quoted in spec §6
- 3,749,035 — loaders/census.py T13b docstring
- 1.144 — loaders/constants.py, verbatim: "ANTI-PATTERN, recorded so no future reader reaches for it: the POOLED all-immigrant owned-occupancy ratio is 1.144 (StatCan 36-28-0001, "Housing use of immigrants and non-permanent residents in ownership and rental markets", 2025-05-28 — immigrants 310 vs Canadian-born 271 owned units per 1,000). A pooled ratio says arrivals add MORE owners than natives and DEFEATS the §6 netting; P4 §4b records it as the anti-pattern, never a candidate. It is deliberately NOT an entry below."
- 1. Selon le découpage géographique des régions administratives au 1ᵉʳ juillet 2025. — header note of the pinned pop-as-ra-base.xlsx
- 1. Selon le découpage géographique et la dénomination du Recensement de 2021. — header note of the pinned pop-as-rmr-base.xlsx
- 25 children close EXACTLY on the CMA (1,488,307); 16 Québec-side by SGC prefix AND by census-tree ancestry, agreeing on all 25 — probes/P10-hors-operand-alignment.md DECISION-MEMBERSHIP, read this run
- PASS — resolved Québec part 353,293 vs ISQ 355,971 = -0.752%, against a threshold of 1.109% derived from the six wholly-QC CMAs (0.887% max innocent + 25%) — probes/P10-hors-operand-alignment.md DECISION-MEMBERSHIP-GATE, read this run
- EXACT — province 98-10-0621-01 NET of the six geoLevel-503 children of Quebec, NET of the 16 Québec-side census subdivisions of 98-10-0003-01's Ottawa-Gatineau CMA member 594, read from 98-10-0622-01 — probes/P10-hors-operand-alignment.md DECISION-CONSTRUCTION, read this run
- CLOSED-AT-MEMBER-LEVEL — probes/P9-catalogue-closure.md DECISION-VERDICT, read this run
- dimension names AND every member name, all 8226 catalogue cubes — probes/P9-catalogue-closure.md DECISION-CLOSURE-LEVEL, read this run
- vocabulary-scoped; English member/dimension names only; StatCan WDS only — probes/P9-catalogue-closure.md DECISION-RESIDUAL, read this run
- 2466 — 98-10-0622-01 `Montréal` classificationCode, verbatim from live metadata
- 2465 — 98-10-0622-01 `Laval` classificationCode, verbatim from live metadata

## 1. What this measures, and out of which universe

Both immigrant inputs come from ONE cube on ONE member: **98-10-0621-01** (`Before 2016` of `Population characteristics (46)`), with its census-division sibling **98-10-0622-01** supplying the two census divisions ruling T measures. Zero geography transport and zero metric transport: the cube publishes the owner-MAINTAINER propensity §6 defines, as counts, in one universe.

| cube | title (live) | released | archive |
|---|---|---|---|
| [98-10-0621-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810062101) | Population groups by housing suitability and condition of dwelling: Canada, provinces and territories, census metropolitan areas and census agglomerations | 2023-10-04T08:30 | CURRENT |
| [98-10-0622-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810062201) | Population groups by housing suitability and condition of dwelling: Canada, provinces and territories, census divisions and census subdivisions | 2023-10-04T08:30 | CURRENT |
| [43-10-0060-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=4310006001) | Selected housing characteristics, low income indicators and knowledge of official languages, by visible minority and other characteristics for the population in private households | 2023-01-23T08:30 | CURRENT |
| [98-10-0007-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000701) | Population and dwelling counts: Canada and census divisions | 2022-02-09T08:30 | CURRENT |

- `98-10-0621-01` and `98-10-0622-01` publish the SAME dimension list, name for name, in this order: `Geography`, `Tenure including presence of mortgage payments and subsidized housing (totals include farm operators) (8)`, `Gender (3)`, `Primary household maintainer (2)`, `Statistics (3B)`, `Population characteristics (46)`, `Housing suitability and dwelling condition (6)`.
- headship = `Person is primary household maintainer` ÷ `Total - Household maintainer`. The second member is ALL persons, not a maintainer subset — the two names sit next to each other and reading them the other way inverts the rate.
- ratio = the `Before 2016` owner-maintainer propensity ÷ the `Non-immigrants` one, where propensity = `Owner` maintainers ÷ all maintainers.
- Every member id below was resolved BY NAME from the live metadata and then checked against the id the ruling pinned; a move refuses the run rather than being corrected silently.

### 1a. Three universe corroborations

1. Québec total primary household maintainers read **3,749,035** from this cube's maintainer axis. The tree already cites that same published private-household count in `loaders/census.py`'s T13b docstring: 3,749,035 [cited: loaders/census.py T13b docstring]. The agreement is the universe check — this cube's maintainer universe IS the private-household universe, which is what lets a headship computed here sit beside rates derived from that count.
2. Québec total persons read **8,308,480** against probe P3's independently measured 8,308,475 [cited: probe P3, quoted in spec §6] private-household persons — a gap of 5 persons, one rounding step, from a different cube and a different extraction path.
3. Geography labels: `98-10-0621-01` carries 0 of 166 members with a trailing non-breaking space and `98-10-0622-01` carries 0 of 5468, while `43-10-0060-01` carries 34 of 63. Scanned over EVERY geography member of each cube, not over the handful this run resolves.

## 2. The ruled inputs, RECOMPUTED (98-10-0621-01, CMA grain)

| geography | persons | maintainers | owner-maintainers | HEADSHIP | non-imm propensity | settled propensity | RATIO |
|---|---:|---:|---:|---:|---:|---:|---:|
| MTL_RMR | 860,685 | 452,595 | 252,225 | **0.5259** | 0.5785 | 0.5573 | **0.9634** |
| QC_RMR | 40,545 | 20,490 | 10,965 | **0.5054** | 0.6006 | 0.5351 | **0.8910** |
| HORS_RMR | 48,120 | 25,185 | 18,085 | **0.5234** | 0.7007 | 0.7181 | **1.0248** |
| HORS_RMR (SUPERSEDED — Gatineau IN) | 84,785 | 43,825 | 29,355 | **0.5169** | 0.6977 | 0.6698 | **0.9600** |
| QC_PROVINCE | 1,007,855 | 527,710 | 298,100 | **0.5236** | 0.6282 | 0.5649 | **0.8993** |

`HORS_RMR` is the province NET of the six wholly-QC CMAs AND net of the Ottawa-Gatineau CMA's Québec-side census subdivisions — the operand-aligned territory amendment #13 rules, §2b. The six are resolved STRUCTURALLY as the geoLevel-503 children of the Quebec member (memberId 24): Drummondville (CMA), Que. (id 30, code 447), Montréal (CMA), Que. (id 35, code 462), Québec (CMA), Que. (id 36, code 421), Saguenay (CMA), Que. (id 40, code 408), Sherbrooke (CMA), Que. (id 48, code 433), Trois-Rivières (CMA), Que. (id 51, code 442). The Québec side of Ottawa-Gatineau is parented to Ontario in this cube, so it is NOT one of those six and stays inside the residual until it is netted out by subdivision — which is the whole of the correction below. The SUPERSEDED row is the construction that stopped there: it is published because §6's ruling-S table still states its pair (0.5169 / 0.9600) as the record of what shipped, and because §2a's per-member readings are properties of that same territory. It is not a candidate; it is the measurement being corrected.

**The ISQ RMR workbook's own `Territoire hors des RMR` row is what the ALIGNMENT closes on, and the gap is measured rather than argued.** ISQ publishes 2,384,575 for 2021; province net of the same six CMAs is 2,740,546 — a difference of 355,971, which is exactly the workbook's `RMR d'Ottawa-Gatineau2` row (355,971). ISQ nets Gatineau out on its side; the SUPERSEDED census construction kept it in, and that mismatch IS the defect #13 corrects. Two rows with the same name for two different territories is precisely the substitution this note refuses to make — and the aligned row above is the one that no longer makes it.

The province row differs from the residual precisely because the province CONTAINS the CMAs: 0.5236 / 0.8993 at province level against 0.5169 / 0.9600 net of them.

### 2a. EVERY population-characteristic member at EVERY CMA-grain geography

Both quantities, all five immigrant-status members, at all four geographies this cube serves — so the ruled cut can be judged against the members it was chosen over rather than presented alone.

| geography | population-characteristic member | persons | maintainers | owner-maintainers | headship | owner propensity | ratio vs non-imm |
|---|---|---:|---:|---:|---:|---:|---:|
| MTL_RMR | Non-immigrants | 3,021,830 | 1,252,635 | 724,630 | 0.4145 | 0.5785 | 1.0000 |
| MTL_RMR | Total immigrants | 1,022,940 | 511,070 | 266,470 | 0.4996 | 0.5214 | 0.9013 |
| MTL_RMR | Before 2016 | 860,685 | 452,595 | 252,225 | 0.5259 | 0.5573 | 0.9634 |
| MTL_RMR | Recent immigrants: 2016 to 2021 | 162,255 | 58,475 | 14,245 | 0.3604 | 0.2436 | 0.4211 |
| MTL_RMR | Non-permanent residents | 161,680 | 72,000 | 7,135 | 0.4453 | 0.0991 | 0.1713 |
| QC_RMR | Non-immigrants | 746,855 | 355,550 | 213,555 | 0.4761 | 0.6006 | 1.0000 |
| QC_RMR | Total immigrants | 54,855 | 25,400 | 12,045 | 0.4630 | 0.4742 | 0.7895 |
| QC_RMR | Before 2016 | 40,545 | 20,490 | 10,965 | 0.5054 | 0.5351 | 0.8910 |
| QC_RMR | Recent immigrants: 2016 to 2021 | 14,310 | 4,910 | 1,085 | 0.3431 | 0.2210 | 0.3679 |
| QC_RMR | Non-permanent residents | 15,395 | 7,005 | 470 | 0.4550 | 0.0671 | 0.1117 |
| HORS_RMR | Non-immigrants | 2,529,180 | 1,165,570 | 813,230 | 0.4608 | 0.6977 | 1.0000 |
| HORS_RMR | Total immigrants | 103,960 | 49,840 | 31,240 | 0.4794 | 0.6268 | 0.8984 |
| HORS_RMR | Before 2016 | 84,785 | 43,825 | 29,355 | 0.5169 | 0.6698 | 0.9600 |
| HORS_RMR | Recent immigrants: 2016 to 2021 | 19,170 | 6,025 | 1,880 | 0.3143 | 0.3120 | 0.4472 |
| HORS_RMR | Non-permanent residents | 19,690 | 8,195 | 895 | 0.4162 | 0.1092 | 0.1565 |
| QC_PROVINCE | Non-immigrants | 6,892,110 | 3,058,105 | 1,921,035 | 0.4437 | 0.6282 | 1.0000 |
| QC_PROVINCE | Total immigrants | 1,210,600 | 599,370 | 315,825 | 0.4951 | 0.5269 | 0.8388 |
| QC_PROVINCE | Before 2016 | 1,007,855 | 527,710 | 298,100 | 0.5236 | 0.5649 | 0.8993 |
| QC_PROVINCE | Recent immigrants: 2016 to 2021 | 202,740 | 71,660 | 17,725 | 0.3535 | 0.2473 | 0.3938 |
| QC_PROVINCE | Non-permanent residents | 205,775 | 91,565 | 8,750 | 0.4450 | 0.0956 | 0.1521 |

The RECENT rows are what make the flow-vs-stock modeling choice §6 names visible rather than hidden — the operand is an arrival FLOW and the ruled member is a settled STOCK: headship 0.3604 / 0.3431 / 0.3143 and ratio 0.4211 / 0.3679 / 0.4472 at MTL_RMR / QC_RMR / HORS_RMR. Crediting an arrival cohort at the settled rate is a choice taken deliberately, and this table is its size.

Immigrant headship measures HIGHER than the general population at the settled reading (0.5259 vs 0.4364 at MTL_RMR), and the pooled stock also clears the general population (0.4996) though it sits BELOW the settled reading — the recent member (0.3604) is what pulls the pool down. So the immigrant channel contributes MORE household formation per settled person than a general-rate model would have credited. Measured, not assumed either way.

**These rows are the SUPERSEDED territory's**, and they are the right ones to print here: they come from `98-10-0621-01` alone, which publishes no Québec-part member to net out at this grain (§2b), so every per-member reading at CMA grain is a property of the residual that keeps Gatineau in. The aligned correction is measured at the three members the ruled pair needs — `Total - Age`, `Non-immigrants`, `Before 2016` — and is deliberately NOT extended to the rest: an aligned `Recent immigrants` row would be a figure this run did not measure.

### 2b. THE OPERAND ALIGNMENT — HORS_RMR's ruled territory (amendment #13)

The rate's territory must match the flow's territory. The residual above is measured over a census territory that INCLUDES the Québec side of Ottawa-Gatineau, while the arrival flows it multiplies come from ISQ's `Territoire hors des RMR` row, which EXCLUDES it. Amendment #13 rules the corrected construction: the same province-net-of-six residual, NET of that CMA's Québec-side census subdivisions.

**The MEMBERSHIP is carried BY REFERENCE from P10 and RE-RESOLVED here; the VALUES are recomputed.** P10 derived which subdivisions those are — 25 children close EXACTLY on the CMA (1,488,307); 16 Québec-side by SGC prefix AND by census-tree ancestry, agreeing on all 25 [cited: probes/P10-hors-operand-alignment.md DECISION-MEMBERSHIP, read this run] — and validated the resolved part against the ISQ row it aligns to: PASS — resolved Québec part 353,293 vs ISQ 355,971 = -0.752%, against a threshold of 1.109% derived from the six wholly-QC CMAs (0.887% max innocent + 25%) [cited: probes/P10-hors-operand-alignment.md DECISION-MEMBERSHIP-GATE, read this run]. This run does not repeat that derivation. It reads P10's own §4b table, and then looks EVERY one of its 16 members up live in `98-10-0622-01` by SGC code AND geoLevel 5, checking the name the two documents give it and re-establishing the Québec-side property two independent ways in the cube the counts are actually subtracted from — the `24` province prefix on the SGC code that cube gives the member, and the census tree (the member's census division is a geoLevel-3 child of that cube's Quebec member, id 884). BOTH readings place all 16 inside Québec: a member either one puts outside it refuses the run, and so does a disagreement between them. P10's rows are read by their SGC code and never SELECTED on that prefix — a parser that filtered on it would drop an off-province row without a word and leave the first reading unable to fail. Four census divisions contribute — `Papineau` (SGC 2480), `Gatineau` (SGC 2481), `Les Collines-de-l'Outaouais` (SGC 2482), `La Vallée-de-la-Gatineau` (SGC 2483) — which is why no whole-CD union is this territory.

**Suppression: BOUNDED by the published complement, never dropped.** StatCan withholds small counts at these subdivisions. Of the 144 cells this run requested across the 16 of them, 18 came back with no data point, every one a `Before 2016` field, at 7 of the 16 subdivisions — the other two members are published at every one of them, which is what makes the bound available at all, and the count the bounded sum carried is asserted equal to the count the boundary reported. Each is bounded above by a quantity the SAME cube publishes at the SAME geography — `Total - Age` minus `Non-immigrants`, i.e. all immigrants and non-permanent residents together, which contains `Before 2016` by construction — and the bound's own two legs are required to be published (`_guard_required_complete`), because an interval whose upper end is itself unmeasured is not a bound. FIELD-WISE: a subdivision publishing settled persons while withholding settled maintainers keeps the published count, since dropping the geography would net its persons and its maintainers out of different denominators — a bias, not a wider interval. 0 field(s) needed the clamp for a rounding-step negative.

| construction | settled persons | maintainers | owner-maintainers | HEADSHIP | RATIO |
|---|---:|---:|---:|---:|---:|
| as shipped (Gatineau IN) — SUPERSEDED | 84,785 | 43,825 | 29,355 | 0.5169 | 0.9600 |
| **ALIGNED (published counts only) — RULED** | **48,120** | **25,185** | **18,085** | **0.5234** | **1.0248** |
| aligned, every withheld field at its bound | 48,100 | 25,145 | 18,050 | 0.5228 | 1.0244 |

**Aligned: headship 0.5234 (+1.254%), ratio 1.0248 (+6.744%) — and the ratio CROSSES 1.0.** Shipped, settled immigrants under-own in hors-RMR; aligned, they OUT-own. The non-immigrant base moves too and is netted across the same territory: 0.6977 shipped against 0.7007 aligned. The suppression envelope is [1.0228, 1.0264] on the ratio and [0.5225, 0.5236] on the headship — taken at the box's OPPOSITE corners (headship is largest when the fewest maintainers and the most persons are netted out), so it is the envelope rather than the two sums paired. Neither end straddles 1.0, which is a refusal condition here rather than a remark: amendment #13 rules the crossing with BOTH ends above 1.0, and a verdict inside its own uncertainty is not a verdict.

The two factors MULTIPLY inside D_imm and their errors are same-signed, so the immigrant demand leg moves by their product: **+8.083%**. Rank 1 is the most negative ED, so the shipped construction ranked HORS_RMR more risky than truth — which is why #13 rules the aligned pair rather than recording the gap as a caveat.

**What this run does NOT re-derive, stated as the reference it is.** The 25-child closure on the Ottawa-Gatineau CMA, the two-way selection of the Québec side at the membership cube, and the population gate against the ISQ row are P10's measurements, read from its committed note this run: EXACT — province 98-10-0621-01 NET of the six geoLevel-503 children of Quebec, NET of the 16 Québec-side census subdivisions of 98-10-0003-01's Ottawa-Gatineau CMA member 594, read from 98-10-0622-01 [cited: probes/P10-hors-operand-alignment.md DECISION-CONSTRUCTION, read this run]. What this run adds is independent of them only where it can be: every member is re-resolved live, its Québec-side property re-checked in this cube, and every count above is read from the live responses rather than transcribed from P10 — the figures are then checked against P10's own digits, so a divergence refuses instead of publishing two measurements of one territory that disagree.

## 3. The census-division sibling (98-10-0622-01) and the one-universe check

| geography | census division | persons | maintainers | owner-maintainers | HEADSHIP | non-imm propensity | settled propensity | RATIO |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MTL_ISLAND_RA06 | `Montréal` (id 1732, geoLevel 3, SGC 2466) | 538,620 | 299,230 | 135,510 | **0.5555** | 0.4210 | 0.4529 | **1.0757** |
| LAVAL_RA13 | `Laval` (id 1730, geoLevel 3, SGC 2465) | 119,160 | 57,390 | 41,745 | **0.4816** | 0.6546 | 0.7274 | **1.1112** |

`Laval` names BOTH the census division (id 1730, geoLevel 3) and a census SUBDIVISION inside it (id 1731, geoLevel 5, SGC 2465005). Resolution therefore requires name AND geoLevel AND parent, and refuses on more than one match — a name-only lookup would publish a city's numbers under a region's label.

Every member at both census divisions, on the same cross as §2a:

| geography | population-characteristic member | persons | maintainers | owner-maintainers | headship | owner propensity | ratio vs non-imm |
|---|---|---:|---:|---:|---:|---:|---:|
| MTL_ISLAND_RA06 | Non-immigrants | 1,168,390 | 502,530 | 211,560 | 0.4301 | 0.4210 | 1.0000 |
| MTL_ISLAND_RA06 | Total immigrants | 652,730 | 343,815 | 143,185 | 0.5267 | 0.4165 | 0.9892 |
| MTL_ISLAND_RA06 | Before 2016 | 538,620 | 299,230 | 135,510 | 0.5555 | 0.4529 | 1.0757 |
| MTL_ISLAND_RA06 | Recent immigrants: 2016 to 2021 | 114,110 | 44,585 | 7,680 | 0.3907 | 0.1723 | 0.4092 |
| MTL_ISLAND_RA06 | Non-permanent residents | 138,240 | 64,020 | 5,375 | 0.4631 | 0.0840 | 0.1994 |
| LAVAL_RA13 | Non-immigrants | 288,925 | 105,975 | 69,370 | 0.3668 | 0.6546 | 1.0000 |
| LAVAL_RA13 | Total immigrants | 135,315 | 62,065 | 43,345 | 0.4587 | 0.6984 | 1.0669 |
| LAVAL_RA13 | Before 2016 | 119,160 | 57,390 | 41,745 | 0.4816 | 0.7274 | 1.1112 |
| LAVAL_RA13 | Recent immigrants: 2016 to 2021 | 16,155 | 4,670 | 1,605 | 0.2891 | 0.3437 | 0.5250 |
| LAVAL_RA13 | Non-permanent residents | 5,310 | 1,745 | 285 | 0.3286 | 0.1633 | 0.2495 |

### 3a. BIT-IDENTITY, asserted on the RULED TRIPLE and nowhere else

The two cubes' Québec province rows agree EXACTLY on the ruled `Before 2016` triple — persons 1,007,855, maintainers 527,710, owner-maintainers 298,100 — which is what makes them ONE universe at two geography grains rather than two sources. They do NOT agree cube-wide, and this note does not claim they do: 4 province cells differ by exactly 5. Of the 42 province counts read from the two cubes, 0 are not a multiple of 5 — so a 5-person disagreement is exactly what rounding applied independently per cube produces, an explanation this run can offer only because it measured that property rather than assuming it.

| popchar member | field | 98-10-0621-01 | 98-10-0622-01 | gap |
|---|---|---:|---:|---:|
| Non-immigrants | maintainers | 3,058,105 | 3,058,100 | +5 |
| Total immigrants | maintainers | 599,370 | 599,365 | +5 |
| Total immigrants | owner-maintainers | 315,825 | 315,820 | +5 |
| Non-permanent residents | persons | 205,775 | 205,770 | +5 |

A note claiming cube-wide identity would assert what its own data contradicts, and a gate pinning that claim would pin a falsehood. So the gate binds the ruled triple EXACTLY, tolerates ±5 elsewhere, and refuses beyond it.

### 3b. The ratio EXCEEDS 1 at both, and that is COMPOSITION — measured, not asserted

On the island the NON-immigrant base is renter-heavy: its owner-maintainer propensity is only **0.4210**, against the settled-immigrant **0.4529** — so the ratio is 1.0757 LOCALLY while the same measurement CMA-wide is 0.9634, where the non-immigrant base is 0.5785. Both are true at their own scale; printing only the ratio would leave the reader to take the explanation on trust.
At Laval the same shape: non-immigrant 0.6546 against settled 0.7274, and the product the [0,1] assertion binds is 0.6546 × 1.1112 = 0.727.

**This is NOT the pooled-ratio anti-pattern** recorded in `loaders/constants.py` (1.144 [cited: loaders/constants.py, verbatim: "ANTI-PATTERN, recorded so no future reader reaches for it: the POOLED all-immigrant owned-occupancy ratio is 1.144 (StatCan 36-28-0001, "Housing use of immigrants and non-permanent residents in ownership and rental markets", 2025-05-28 — immigrants 310 vs Canadian-born 271 owned units per 1,000). A pooled ratio says arrivals add MORE owners than natives and DEFEATS the §6 netting; P4 §4b records it as the anti-pattern, never a candidate. It is deliberately NOT an entry below."]). That one pools ACROSS RECENCY, and this run can show what pooling costs from its own numbers: pooling `Before 2016` with `Recent immigrants: 2016 to 2021` into `Total immigrants` moves the island ratio from 1.0757 to 0.9892 — i.e. it erases the >1 finding entirely — and at MTL_RMR from 0.9634 to 0.9013, with the recent member sitting at 0.4092 and 0.4211 respectively. A single pooled number stands in for a spread that wide, which is what defeats the netting by construction. This reading is decomposed: one member, named.

## 4. Ruling T's TERRITORY GATE — the province-controlled share residual

**The construction ruling T first named is REFUSED and is not implemented here.** It compared `98-10-0622-01`'s population against the ISQ RA total — a PRIVATE-HOUSEHOLD count against a TOTAL-POPULATION estimate — and measured, it trips at the Québec province CONTROL, where territory identity is not in question. A gate that fires where the answer is known is measuring the universe gap, not the territory. Amendment #11 replaced it with:

```
residual(g) = ( part_census(g) / total_census  ÷  part_ISQ(g) / total_ISQ ) − 1
```

Each geography's share of its OWN source's provincial total. Census side: `98-10-0622-01` persons against a province total of 8,308,480 — the province person count `98-10-0621-01` publishes, which this run compared cube against cube and refuses on a disagreement — so the RA residuals and the innocent controls share one denominator rather than two that happen to be close. ISQ side: the pinned workbooks against 8,572,020, likewise checked equal across the two workbooks. A universe offset that is uniform across the province cancels by construction; what survives is the geography-VARYING part, and that is exactly what the innocent controls measure.

### 4a. The innocent controls — territories whose identity is NOT in question

The six wholly-QC CMAs. Two independent facts, both measured this run, put their identity beyond question:

1. Every one of the six joins on an EXACT code. The `code` column below IS the census member's `classificationCode`, and it is the key this run looked the ISQ row up under — the workbook's own `Code` axis — so the `ISQ row` beside it is the row that code retrieved. A census code the workbook does not publish refuses the run rather than printing.
2. The RMR workbook DECLARES the delineation it uses, in its own header note: *1. Selon le découpage géographique et la dénomination du Recensement de 2021. [cited: header note of the pinned pop-as-rmr-base.xlsx]*. So its rows are census territories by the publisher's own statement, not by inference from the code agreement.

The RA workbook declares a DIFFERENT one: *1. Selon le découpage géographique des régions administratives au 1ᵉʳ juillet 2025. [cited: header note of the pinned pop-as-ra-base.xlsx]* — an administrative delineation dated four years after the census, with no correspondence to the SGC in this tree. That is why RA06 and RA13 need a gate and why these six can calibrate it: the six are census territories by declaration, the two under test are not.

| CMA (census member) | code | ISQ row | census persons | ISQ population | share residual |
|---|---:|---|---:|---:|---:|
| Drummondville (CMA), Que. | 447 | RMR de Drummondville | 98,570 | 102,356 | **-0.644%** |
| Montréal (CMA), Que. | 462 | RMR de Montréal | 4,206,455 | 4,330,143 | **+0.225%** |
| Québec (CMA), Que. | 421 | RMR de Québec | 817,105 | 844,774 | **-0.207%** |
| Saguenay (CMA), Que. | 408 | RMR de Saguenay | 157,895 | 162,376 | **+0.325%** |
| Sherbrooke (CMA), Que. | 433 | RMR de Sherbrooke | 220,105 | 229,294 | **-0.963%** |
| Trois-Rivières (CMA), Que. | 442 | RMR de Trois-Rivières | 155,535 | 162,531 | **-1.269%** |

The largest innocent |residual| is **1.269%** (Trois-Rivières (CMA), Que.). The threshold is that maximum PLUS a stated margin of 25% of it — 0.317 percentage points — giving **1.586%**. The margin is a cushion, not the calibration: the calibration is the measured maximum, and the cushion exists because six controls make that maximum a noisy estimate of the innocent spread's upper edge. Ruling T's original 1% is deliberately NOT used — it was calibrated against the refuted construction's semantics and does not transfer.

### 4b. The two geographies under test

| geography | census persons | ISQ population | share residual | vs threshold |
|---|---:|---:|---:|---|
| MTL_ISLAND_RA06 | 1,959,355 | 2,015,879 | **+0.279%** | PASS (0.279% ≤ 1.586%) |
| LAVAL_RA13 | 429,555 | 440,489 | **+0.611%** | PASS (0.611% ≤ 1.586%) |

Both residuals sit INSIDE the innocent |residual| range: 3 of the 6 controls — Drummondville (CMA), Que., Sherbrooke (CMA), Que., Trois-Rivières (CMA), Que. — carry a LARGER |share residual| than either geography under test, and every one of those is a census territory by the ISQ workbook's own declaration. That is stronger than the threshold comparison alone — the two geographies under test are not merely under a bound, they are less discrepant IN ABSOLUTE VALUE than territories whose identity is settled — and absolute value is what the gate rules on, since amendment #11 sets the threshold on the maximum innocent |residual|.

**THE SIGNED DECOMPOSITION DOES NOT RUN THE SAME WAY, and is published rather than left inside the absolute value.** The innocent controls span -1.269% to +0.325% (Trois-Rivières (CMA), Que. to Saguenay (CMA), Que.), 4 of the 6 of them NEGATIVE (Drummondville (CMA), Que., Québec (CMA), Que., Sherbrooke (CMA), Que., Trois-Rivières (CMA), Que.); 2 of 2 geographies under test measure POSITIVE (MTL_ISLAND_RA06 +0.279%, LAVAL_RA13 +0.611%). The largest positive innocent control is Saguenay (CMA), Que. at +0.325%, and LAVAL_RA13 measures ABOVE it. The gate PASSES on |residual| and this note does not restate that as agreement in SIGN. What the sign would MEAN is not decidable from this construction: §4c's second limit — the residual cannot separate a territory difference from a region-varying universe component — binds the sign exactly as it binds the magnitude, and six controls do not fix a direction. Measured and recorded here, deliberately un-attributed.

### 4c. What this gate CANNOT do

Passing does not establish that a census division IS an ISQ région administrative. It fails to REFUTE that, at the resolution this construction has — the gate trips only above 1.586%, and the innocent spread it is calibrated on already runs to 1.269%. In persons, at each geography's own ISQ population, that trip point is **31,976** at MTL_ISLAND_RA06, **6,987** at LAVAL_RA13 — a territory difference smaller than that would not be seen at all. The residual also cannot SEPARATE a territory difference from a region-varying universe difference; the innocent controls bound the second, they do not remove it. Both limits are published beside the verdict so a reader can price the claim rather than take it.

### 4d. Code axes — RECORDED, and deliberately NOT the gate

- ISQ keys the RA workbook on région-administrative codes 0-17. This run resolved `Montréal` and `Laval` BY LABEL in the workbook and read back codes 6 and 13, each then asserted against the code pinned for it — the ISQ mirror of the by-name resolution the census side uses, so the gate fetches on the workbook's own identity for the row rather than on a typed integer. The delineation is the one its own header note states.
- The census publishes SGC classification codes: CD Montréal 2466 [cited: 98-10-0622-01 `Montréal` classificationCode, verbatim from live metadata] and CD Laval 2465 [cited: 98-10-0622-01 `Laval` classificationCode, verbatim from live metadata] in `98-10-0622-01`, the same two codes in `98-10-0007-01` (2466 and 2465).
- **SGC agreement across two CENSUS cubes establishes that two CENSUS cubes mean the same census division. It does NOT establish that the census division equals the ISQ région administrative** — no correspondence between the two code systems exists in this tree. So the population residual carries the gate and the code agreement is corroboration. (The six CMAs above are a different case: there the ISQ workbook and the census share ONE code system, by the RMR workbook's own declaration.)

### 4e. Second diagnostic — census TOTAL population (98-10-0007-01), never the gate

A like-for-like universe check: total population against total population, no private-household restriction on either side.

| geography | census 2021 population | ISQ July-1 2021 | delta |
|---|---:|---:|---:|
| MTL_ISLAND_RA06 | 2,004,265 | 2,015,879 | **-0.576%** |
| LAVAL_RA13 | 438,366 | 440,489 | **-0.482%** |
| QC_PROVINCE | 8,501,833 | 8,572,020 | **-0.819%** |

All three are the same small negative — a census count taken in May against a July-1 estimate, plus net undercoverage — and the two geographies under test are CLOSER to their ISQ counterpart than the province is. It is a corroboration and nothing more: admitting `98-10-0007-01` into the GATE would mean repairing a gate by adding cubes until it passed, which is what amendment #11 refuses. The gate above uses only the two sources ruling T names.

## 5. The FLOOR GATE — cross-cube, and wired knowingly

`98-10-0621-01` publishes no living-alone indicator, so the floor comes from `43-10-0060-01` indicator `Population living alone` — a DIFFERENT cube, with a different immigrant axis. The member must be the ruled-adjacent one: `Admitted to Canada more than 10 years ago`, not the pooled `Immigrants`.

| geography | ruled headship | settled living-alone | pooled living-alone (NOT used) | clears by |
|---|---:|---:|---:|---:|
| MTL_RMR | 0.5259 | **0.154** | 0.134 | 0.372 |
| QC_RMR | 0.5054 | **0.164** | 0.127 | 0.341 |

Each person living alone maintains exactly one household, so headship must EXCEED the living-alone share; a value at or below it is a defect, not a datum. §6 names the settled member on two grounds — nearer in definition to the ruled `Before 2016` cut, and stricter as a bound. This run measures the SECOND: 0.154 > 0.134 and 0.164 > 0.127. It does not measure the first, which is a claim about definitions rather than a quantity.

**COVERAGE, and the absence is EARNED rather than assumed.** The floor binds at MTL_RMR, QC_RMR only. For the other three modeled geographies — HORS_RMR, MTL_ISLAND_RA06, LAVAL_RA13 — all 63 of this cube's geography members were searched this run, and the search is reported rather than summarised:

  | uncovered geography | searched for | members matching |
  |---|---|---:|
  | HORS_RMR | `memberNameEn containing any of ['outside', 'non-cma', 'rest of', 'remainder', 'hors']` | 0 |
  | MTL_ISLAND_RA06 | `classificationCode == '2466'` | 0 |
  | LAVAL_RA13 | `classificationCode == '2465'` | 0 |

The cube's geography members carry these geoLevels: `0` × 1, `1` × 6, `2` × 13, `503` × 41, `505` × 2 — **0** of them at geoLevel 3, the census-division level RA06 and RA13 are published at. Substituting the province figure (0.156, measured here) would be a geography transport the ruling does not make, so these three are recorded NOT COVERED rather than floored against a stand-in. Scoped to this cube and these predicates — not a claim that no source anywhere carries them.

## 6. The SIBLING CROSS-CHECK, at exactly its coarse strength

All five members of this cube's `Immigrant and generation status` axis, both indicators, at all three geographies it serves. Values are published as PERCENTAGES and divided by 100 at the boundary; nothing here is a maintainer propensity.

| geography | immigrant member | ownership share | living-alone share | ownership vs non-immigrant |
|---|---|---:|---:|---:|
| MTL_RMR | Non-immigrants | **0.661** | 0.155 | 1.0000 |
| MTL_RMR | Immigrants | 0.558 | 0.134 | 0.8442 |
| MTL_RMR | Admitted to Canada in the last 10 years | 0.379 | 0.092 | 0.5734 |
| MTL_RMR | Admitted to Canada more than 10 years ago | **0.640** | 0.154 | 0.9682 |
| MTL_RMR | Non-permanent residents | 0.136 | 0.164 | 0.2057 |
| QC_RMR | Non-immigrants | **0.695** | 0.182 | 1.0000 |
| QC_RMR | Immigrants | 0.511 | 0.127 | 0.7353 |
| QC_RMR | Admitted to Canada in the last 10 years | 0.369 | 0.086 | 0.5309 |
| QC_RMR | Admitted to Canada more than 10 years ago | **0.641** | 0.164 | 0.9223 |
| QC_RMR | Non-permanent residents | 0.118 | 0.174 | 0.1698 |
| QC_PROVINCE | Non-immigrants | **0.704** | 0.163 | 1.0000 |
| QC_PROVINCE | Immigrants | 0.563 | 0.134 | 0.7997 |
| QC_PROVINCE | Admitted to Canada in the last 10 years | 0.385 | 0.089 | 0.5469 |
| QC_PROVINCE | Admitted to Canada more than 10 years ago | **0.649** | 0.156 | 0.9219 |
| QC_PROVINCE | Non-permanent residents | 0.140 | 0.166 | 0.1989 |

The two bolded members are the only ones this note uses: `Non-immigrants` as the base and `Admitted to Canada more than 10 years ago` as the comparator, giving **0.9682** at MTL_RMR, **0.9223** at QC_RMR, **0.9219** at QC_PROVINCE — against ruling S's 0.9634 / 0.8910 / 0.8993 from 98-10-0621-01.

**This is a COARSE consistency check across two named axes, never a like-for-like agreement.** The sibling's 0.9682 and ruling S's 0.9634 differ in BOTH the member cut (`Admitted to Canada more than 10 years ago`, i.e. more than 10 years, against `Before 2016`, i.e. at least five) AND the metric (a person-weighted ownership share against a maintainer propensity). Their closeness at Montréal therefore bounds the COMBINED size of those two differences and asserts nothing stronger — in particular it does not validate either quantity, and neither figure may be substituted for the other.

## 7. The catalogue search, carried BY REFERENCE

This note makes no absence claim of its own. P9 closed the search and this run reads P9's own tokens rather than restating them: verdict **CLOSED-AT-MEMBER-LEVEL [cited: probes/P9-catalogue-closure.md DECISION-VERDICT, read this run]**, at **dimension names AND every member name, all 8226 catalogue cubes [cited: probes/P9-catalogue-closure.md DECISION-CLOSURE-LEVEL, read this run]**. The residual P9 records and this note therefore inherits: **vocabulary-scoped; English member/dimension names only; StatCan WDS only [cited: probes/P9-catalogue-closure.md DECISION-RESIDUAL, read this run]**. A re-run of P9 that narrows its closure narrows this sentence with it, which a restated absolute would not.

## 8. Scope

PROBE ONLY. Nothing here is wired into `demand/immigrant_inputs.py`; the plan's task 25b is that consumer and a separate run. The values above are the measurement task 25b consumes, and the per-field provenance §6 requires is visible in the DECISION block: MTL_RMR and QC_RMR direct and `cited`; RA06 and RA13 measured at census-division grain and `cited`, on the strength of the gate in §4; HORS_RMR computed as the operand-aligned residual of §2b — the province net of the six wholly-QC CMAs and of the Ottawa-Gatineau Québec part, with the membership carried from P10.

## DECISION

- `DECISION-VERDICT: MEASURED`
- `DECISION-HEADSHIP: MTL_RMR 0.5259; QC_RMR 0.5054; HORS_RMR 0.5234; MTL_ISLAND_RA06 0.5555; LAVAL_RA13 0.4816 — 98-10-0621-01/98-10-0622-01 `Before 2016`, maintainers ÷ persons, recomputed this run`
- `DECISION-RATIO: MTL_RMR 0.9634; QC_RMR 0.8910; HORS_RMR 1.0248; MTL_ISLAND_RA06 1.0757; LAVAL_RA13 1.1112 — settled owner-maintainer propensity ÷ non-immigrant, same member, same universe`
- `DECISION-SOURCE-MTL_RMR: 98-10-0621-01 member 35 — DIRECT, cited, both fields`
- `DECISION-SOURCE-QC_RMR: 98-10-0621-01 member 36 — DIRECT, cited, both fields`
- `DECISION-SOURCE-HORS_RMR: 98-10-0621-01 province member 24 NET of the six geoLevel-503 children [30, 35, 36, 40, 48, 51] NET of the 16 Ottawa-Gatineau Québec-part census subdivisions read from 98-10-0622-01 (membership carried from probes/P10-hors-operand-alignment.md, every member re-resolved live by SGC code and geoLevel 5) — OPERAND-ALIGNED computed residual per amendment #13, both fields`
- `DECISION-HORS-ALIGNMENT: RULED 0.5234 / 1.0248 (suppression envelope 0.5225-0.5236 and 1.0228-1.0264, neither ratio end straddling 1.0); SUPERSEDED 0.5169 / 0.9600 — the same residual with the Québec side of Ottawa-Gatineau still IN, which §6's ruling-S row states and amendment #13 supersedes. Immigrant demand leg +8.083%; headship +1.254%, ratio +6.744%. 18 withheld settled fields at 7 of 16 subdivisions, bounded FIELD-WISE by `Total - Age` − `Non-immigrants` at the same geography`
- `DECISION-SOURCE-MTL_ISLAND_RA06: 98-10-0622-01 CD Montréal member 1732 (SGC 2466) — MEASURED, cited, both fields`
- `DECISION-SOURCE-LAVAL_RA13: 98-10-0622-01 CD Laval member 1730 (SGC 2465) — MEASURED, cited, both fields`
- `DECISION-TERRITORY-GATE: PASS — province-controlled share residual RA06 +0.279%, RA13 +0.611%; both inside the innocent |residual| range (3 of 6 innocent controls are further out in |.|). SIGNED, recorded and NOT attributed: innocent span -1.269% to +0.325%, 4 of 6 negative; 2 of 2 under test positive; above every positive innocent control: LAVAL_RA13`
- `DECISION-TERRITORY-THRESHOLD: 1.586% = max innocent |residual| 1.269% (Trois-Rivières (CMA), Que.) + 0.317 pp margin (25% of the max); DERIVED from the six wholly-QC CMAs, NOT ruling T's inherited 1%`
- `DECISION-TERRITORY-DIAGNOSTIC: 98-10-0007-01 total population RA06 -0.576%, RA13 -0.482%, province -0.819% — corroborating, NEVER the gate`
- `DECISION-FLOOR-GATE: PASS — headship exceeds the settled living-alone share at MTL_RMR 0.5259 > 0.154; QC_RMR 0.5054 > 0.164 (43-10-0060-01 indicator `Population living alone`, `Admitted to Canada more than 10 years ago` member)`
- `DECISION-FLOOR-COVERAGE: binds at MTL_RMR, QC_RMR; HORS_RMR, MTL_ISLAND_RA06, LAVAL_RA13 NOT COVERED — searched all 63 geography members of 43-10-0060-01 this run: 0 at geoLevel 3 (census division) and 0 carrying SGC 2466/2465; no stand-in substituted`
- `DECISION-UNIVERSE-IDENTITY: the two cubes' province rows are BIT-IDENTICAL on the ruled Before 2016 triple (1,007,855 / 527,710 / 298,100) and differ by exactly 5 on 4 other province cells — NOT cube-wide identity`
- `DECISION-SIBLING-CROSS-CHECK: COARSE — 43-10-0060-01 0.9682 vs ruled 0.9634 at MTL_RMR bounds the COMBINED size of a member-cut difference and a metric difference; asserts nothing stronger`
- `DECISION-CATALOGUE-CLOSURE: CLOSED-AT-MEMBER-LEVEL at dimension names AND every member name, all 8226 catalogue cubes — residual vocabulary-scoped; English member/dimension names only; StatCan WDS only (read from probes/P9-catalogue-closure.md this run, not restated)`
- `DECISION-SCOPE: PROBE ONLY — NOT wired into demand/immigrant_inputs.py by this run and NOT to be read as wired; plan task 25b is that consumer and a separate run`

