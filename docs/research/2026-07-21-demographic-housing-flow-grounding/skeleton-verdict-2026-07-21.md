# Walking-Skeleton Verdict — 2026-07-21

Skeleton-First step-zero probe, run live 2026-07-21 (background agent). Probe script
preserved as `skeleton_probe_mortality.py`; raw ISQ CSV (20.6MB) not retained — re-downloadable at the
recorded URL below.

## 1. BOUNDARY VERDICT: PASS

actuarial-system's mortality engine (`mcp_server/engine/mortality.py`) fired live via `uv run python`
with `set_active_mortality("CPM2014_combined", "CPM-B")` set explicitly. **Spec-relevant gotcha
confirmed: the engine DEFAULTS to the US RP2014+MP2021 basis** — the Québec basis must be set
explicitly per call context (module-level `_active_base` global, single-threaded assumption). No
exceptions, no silent US fallback once set; `active_mortality()` echoed the QC basis.

q_x spot values, calendar year 2035, CPM2014 + CPM-B projected:

| Age | Male | Female |
|-----|--------|--------|
| 75  | 0.0156 | 0.0115 |
| 85  | 0.0596 | 0.0426 |
| 95  | 0.2367 | 0.1803 |
| 100 | 0.3534 | 0.3049 |

Sanity: raw CPM2014 base-year q_75 = 0.0218 (M) / 0.0147 (F) — in the expected 0.02–0.04 zone; 2035
values lower because CPM-B applies ~21 yrs of improvement (~1.5–1.8%/yr) — expected, not a red flag.
Curve monotone and smooth to ~0.24–0.35 by 95–100.

## 2. THE NUMBER: ≈ 1,605 mortality-driven owner-household dissolutions, 2035

**Geography caveat: computed for région administrative 06 (Montréal island, ~2.06M), NOT the RMR
(~4.29M) — see friction #1.** Crude RMR scale-up (~2.08×): ≈ 3,335/yr (context only, not a computed
result). Naive comparator with no last-survivor discount: ≈ 3,473/yr.

Derivation: pop 75+ 2035 = 226,533 (ISQ open CSV, RSS 06, single track) → 28% living-alone (ISQ
vitrine, 65+ proxy) → 63,429 solo + 81,552 couple households → ×56.2% ownership (StatCan 2021 Census,
Montréal CMA, Table 98-10-0231-01) → 81,479 owner households 75+ → solo blended q_x 0.04263 → 1,520
solo dissolutions; couple same-year-double-death proxy q 0.001853 → 85 couple dissolutions.

Named assumptions: 90+ bucket treated as age-90 (understates); mixed-sex couples on the same blended
curve; ownership rate uniform across solo/couple; couple dissolution = both die same year (structurally
undercounts — see friction #4).

## 3. Sources

- ISQ open CSV (used; fallback geography): donneesquebec.ca dataset
  `estimations-et-projections-de-population-comparables`, resource
  `05c3c53d-db97-4bc3-8221-d8af47b4b93e/download/estimationprojectionuniquedonneesouvertes.csv`;
  metadata PDF resource `53e14e89-453f-4a9f-a07f-dbd2681a2055`.
- ISQ true RMR multi-scenario product (BLOCKED, see friction #1):
  `statistique.quebec.ca/en/produit/publication/projections-population-selon-groupe-age-scenario-rmr`.
- Ownership: StatCan Table 98-10-0231-01 (FOGS chart page pattern is fragile; use the table API).
- Living-alone: `statistique.quebec.ca/vitrine/vieillissement/themes/population/situation-menages`
  (28%, 65+, 2021 — a 75-84/85+ split surfaced in search but failed primary-source verification; dropped).

## 4. FRICTION LOG (spec-shaping — read before writing the spec)

1. **RMR-granularity multi-scenario data NOT machine-readable-in-hand.** ISQ's RMR age×scenario table
   is behind a client-rendered Next.js widget (`noRequete: "projections-pop-rmr-age"`); no static
   download found; the data XHR never fired under headless capture (traceforge: page shell only, chart
   component doesn't mount in that rendering path). Fallback fired: région 06 via the open CSV. This is
   the arc's TOP PROVISIONING ITEM — the scenario fan (low/ref/high) is the model's output axis.
2. **The machine-readable CSV lives on the MSSS health-geography axis (RSS/RTS/RLS)**, not ISQ's
   admin-region/RMR products. RSS 06 ≈ région 06 is a lucky coincidence for Montréal — do NOT assume it
   generalizes to other RMRs.
3. **`Statut` column (r/p/j) is revision status, not scenario** — r=révisée, p=provisoire, j=projetée
   (confirmed via metadata PDF). The CSV carries exactly ONE projection track — no low/ref/high variants.
4. **The same-year couple-death proxy structurally undercounts** — couples overwhelmingly dissolve via
   the second, later death of a widowed survivor; the crude product misses that entirely and roughly
   halves the total (1,605 vs 3,473). The spec must model widowhood as a state (couple → widowed-solo →
   dissolution), not as a same-year coincidence. This validates the household-level design insistence
   and elevates it from refinement to first-order.
5. **StatCan FOGS `alternative.cfm` URLs are undocumented/fragile** — durable path is Table
   98-10-0231-01 via the regular table browser/API.
6. **Living-alone share finer than 65+ not cheaply verifiable** — needs a proper Census cross-tab
   (household type × age of maintainer) rather than the vitrine headline figure.

## Scale note (no over-conclusion)

Island owner households 75+ ≈ 81.5k. Mortality-driven dissolutions ≈ 1.6–3.5k/yr (proxy-dependent) vs
the CMHC survivor-conditional living-sale channel (~8.5%/yr of 75+ owners ≈ 6.9k/yr island-scale) —
the living-sale channel dominates mortality at this age band, consistent with the literature's
exits-accelerate-late finding. Numbers are skeleton-grade; direction only.
