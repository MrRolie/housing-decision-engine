# Data-Provisioning Verdict — ISQ Multi-Scenario Projections — 2026-07-21

Follow-up probe to skeleton friction #1 (scenario variants not machine-readable-in-hand).
**VERDICT: VERIFIED at true RMR granularity — the spec fork (région-ratio fallback) is MOOT.**
Verified copies saved in `data/` (re-downloadable at the URLs below; keep copies — the URLs are
undocumented, see fragility note).

## Verified files (downloaded + structurally inspected, 2026-07-21)

| File | Coverage confirmed |
|---|---|
| `pop-as-rmr-base.xlsx` | 3 scenarios — Référence (A2026) / Faible (D2026) / Fort (E2026) — × years 2021–2051 × sex × BOTH grand age-groups AND single-year age 0–100+; `RMR de Montréal` a literal row (also Québec RMR, Ottawa-Gatineau QC-part, Saguenay, Sherbrooke, Trois-Rivières, Drummondville, hors-RMR). `Statut` = est/proj. |
| `pop-as-ra-base.xlsx` | Same structure at all 17 régions administratives incl. `Montréal` (06). |
| `pop-as-qc-base.xlsx` | Québec total; horizon extends to **2071**. |
| `compo-rmr-base.xlsx`, `compo-ra-base.xlsx` | Growth components (fertility/mortality/migration) by scenario, 2025–2051 — NOT age-structured. Useful for scenario narrative + tripwire baselines. |

Source edition embedded in the files: ISQ, *Perspectives démographiques du Québec et de ses régions,
mise à jour 2026* (published 2026-07-09 — twelve days before this probe).

Download URLs (pattern: `https://statistique.quebec.ca/fr/fichier/<slug>.xlsx`):
`pop-as-rmr-base`, `pop-as-ra-base`, `pop-as-qc-base`, `compo-rmr-base`, `compo-ra-base`.

## Fragility note (loader-spec relevant)

- The `/fr/fichier/<slug>.xlsx` URLs are **undocumented** — discovered by naming-convention inference
  from the one working link on the ISQ vieillissement vitrine (animated-pyramid page), then
  guess-and-check. The official document page's "Detailed tables" links are `<a>` tags with **no href
  and no click handler** (confirmed site defect — a Playwright click fires zero network requests), and
  the interactive RMR widget's data XHR never mounts headless. Loaders must therefore: pin the slug
  URLs, checksum the downloads, and fail loud on 404/size-drift rather than assuming stability.
- BDSO (bdso.gouv.qc.ca) is a mirrored front-end of the same CMS (same broken links) — not an
  alternative API. `data.statistique.quebec.ca` does not resolve (false lead). donneesquebec.ca has no
  ISQ multi-scenario projection dataset (only the single-track health-territory CSV).

## Consequences for the spec

1. ScenarioPrior contract indexes directly on the file's own scenario labels (A2026/D2026/E2026) —
   no derived variant ratios needed.
2. RMR-level horizon is 2051 (not 2071 — only the Québec-total file reaches 2071). A >2051 tail, if
   wanted, is an explicit extrapolation assumption, named as such.
3. Skeleton's single-track health-geography CSV is retired from the design — the RMR workbook
   supersedes it entirely (single-year age included).
4. The 2026 edition being 12 days old means the model launches on the freshest available demographic
   base; edition-refresh becomes a natural annual tripwire (new edition slug/watch).
