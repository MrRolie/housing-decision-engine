# demoflow — Demographic Housing-Flow Scenario Module — Design

**Date:** 2026-07-21
**Status:** Approved design (operator 2026-07-21); elegance-gate 2A+2B folded (both
PROCEED-WITH-MODIFICATIONS, 2026-07-21 — 2B re-sequenced to rankings-first tranches with the
ScenarioPrior emitter deferred behind an S4b input-slot sketch; 2A subtractive mods folded: parquet
mirror cut, plex compute deferred to v1, CLI folded to run+tripwires, flat error classes,
enum→string serialization stated); spec pending operator review
**money-path:** no (personal decision tooling; touches no fund globs)
**load-bearing-claim:** yes (stress-tester) — "fail-loud loaders, no silent fallback" and
"schema-enforced output prohibition" are load-bearing correctness claims; stress-tester fires at
PR time regardless of money-path.

**Grounding provenance (read before contesting any premise here):**
`docs/research/2026-07-21-demographic-housing-flow-grounding/` — literature autopsy, data landscape,
repo audits, quant design, epistemic skeptic, walking-skeleton verdict (actuarial boundary PASS),
data-provisioning verdict (ISQ RMR multi-scenario workbooks verified). The BUILD-REDUCED adjudication
and altitude ruling live in the dossier README and are design invariants here, not open questions.

---

## 1. Intent (locked 2026-07-21, operator-confirmed)

A **policy-indexed scenario instrument — never a forecaster.** It emits (a) conditional stress
parameters for hde's S4b market-scenario layer, (b) relative geography/segment rankings, and
(c) tripwire baselines for the un-forecastable inputs. It is **FORBIDDEN from emitting any
unconditional crash probability or point price forecast** (the Mankiw–Weil guard). The prohibition is
enforced structurally: the output schema cannot express the forbidden quantities (§7), and a contract
test pins the schema to an allowlist. "Forecaster-lite" was named to the operator and rejected.

Consumers, in VALUE ORDER (2B gate re-sequencing, 2026-07-21): (1) the operator — multi-geography
**rankings + tripwires** are the core v0 output (this is where both the decision value and the
showcase value live); (2) a LinkedIn showcase framed as "scenario map + named epistemic limits" —
never a crash number; (3) hde S4b Monte-Carlo via the ScenarioPrior artifact — **deferred Tranche 2**,
gated on a real S4b demographic-input-slot sketch (S4b's roadmapped contract currently has no
demographic slot; building the emitter against an imagined consumer is the sequencing inversion the
gate caught). Model output must never be used to argue the operator's 30%-drawdown-survival stress
DOWN (skeptic ruling). **Binding cross-spec obligation recorded here:** the future S4b integration
spec MUST honor the `never_relax_stress` flag semantics (§7); the stress-relaxation guard's only
enforceable home is the consumer that runs the drawdown test. demoflow does NOT floor the tilt
(flag-not-clamp is deliberate — a universal floor would kill the legitimate borough-ranking signal;
flooring, if ever, is an operator decision at the S4b seam).

## 2. Placement & dependency topology

- `demoflow/` is a **separate uv project inside the housing-decision-engine repo** (own
  `pyproject.toml`, own lockfile, own venv, own tests). Sibling to `src/hde` + `mcp_server/`.
- **Why its own project, not a member of hde's distribution:** actuarial-system's wheel installs a
  top-level package literally named `mcp_server` (`actuarial-system/pyproject.toml`
  `[tool.hatch.build.targets.wheel] packages = ["mcp_server"]`); hde's repo ALSO ships a top-level
  `mcp_server` package. The two must never share an environment. demoflow's env installs
  actuarial-system (path dependency) and never installs hde's distribution; hde's env never installs
  demoflow. Collision is impossible by construction, not by discipline.
- **Import rules (both directions, test-enforced):** `hde` and `hde`'s `mcp_server` never import
  `demoflow`; `demoflow` never imports `hde` or hde's `mcp_server`. Coupling is the ScenarioPrior
  artifact file only.
- **actuarial-system dependency:** uv path dependency (`../actuarial-system` — lain-local; showcase
  runs need both repos present, accepted at the operator fork 2026-07-21). Import surface pinned to
  `mcp_server.engine.mortality` public functions only: `set_active_mortality`, `active_mortality`,
  `get_qx`. No private reach-ins. Dependency weight (fastmcp/cvxpy/osqp ride along) accepted —
  lain-local batch tool.
- **Basis contract (gotcha codified in actuarial-system/CLAUDE.md):** the engine DEFAULTS to the US
  RP2014+MP2021 basis. Every demoflow entry point sets
  `set_active_mortality("CPM2014_combined", "CPM-B")` and then asserts `active_mortality()` echoes the
  Québec basis before any `get_qx` call; assertion failure raises. Single-threaded batch only
  (the engine's module-level `_active_base` global is a documented v1 concurrency assumption);
  demoflow performs no concurrent engine calls. Scalar `get_qx` loop is accepted for v0 (no
  vectorization request into actuarial-system).
- **actuarial-system charter note:** this makes demoflow that repo's first live external consumer
  using EXISTING machinery only. The multiple-decrement/last-survivor combinator extension remains
  explicitly DEFERRED (altitude ruling) and would need its own operator sign-off.

## 3. Package layout

```
demoflow/
  pyproject.toml            # own uv project; path dep on ../../actuarial-system
  src/demoflow/
    geography.py            # Geography enum + per-source label junction maps (§8)
    loaders/                # isq.py, census.py, ircc.py, constants.py (MIFI/CMHC anchors)
    cohort/                 # household-state roll-forward + decrements (§5)
    demand/                 # native formation + immigrant YSL decomposition (§6)
    balance/                # excess-demand fraction (Tranche 1); ED→prior mapping (Tranche 2) (§7)
    output/                 # rankings / tripwire emitters (T1); ScenarioPrior emitter (T2) (§7)
    cli.py                  # `demoflow run` (emits rankings + artifacts), `demoflow tripwires`
  tests/
  data/                     # committed small reference workbooks (ISQ xlsx, ~8.4MB total)
                            # + sha256 pins; runtime prefers pinned re-download, falls back
                            # to committed copy on network absence — NEVER silently to a
                            # different vintage (§4)
```

No service, no scheduler, no database, no MCP server in v0. Tripwires are a CLI the operator (or a
future cron, out of scope here) runs; outputs are files. Rankings are a byproduct of `run` (single
vintage, §7b), not a separate pipeline invocation — no third subcommand. Packaging discipline: no
empty stage-directories; a stage becomes a package only at ≥2 real modules (loaders/ qualifies
day one), otherwise a flat module.

## 4. Data contracts

| Source | Status | Access | Loader policy |
|---|---|---|---|
| ISQ `pop-as-rmr-base.xlsx`, `pop-as-ra-base.xlsx`, `pop-as-qc-base.xlsx`, `compo-rmr-base.xlsx`, `compo-ra-base.xlsx` (mise à jour 2026) | **VERIFIED live 2026-07-21** (provisioning verdict) | Undocumented slug URLs `statistique.quebec.ca/fr/fichier/<slug>.xlsx` | URL + sha256 pinned; verified copies committed under `demoflow/data/`; on drift (404 / size / checksum / schema) → **raise LoaderError** naming expected vs actual; a NEW ISQ edition is adopted only by an explicit pin bump (that bump is itself the annual-edition tripwire §7c) |
| StatCan Census 98-10-0231-01 (tenure × age of maintainer, Montréal + Québec CMAs) | Value verified (56.2% owner, 75+, MTL CMA); **table-API access path not yet hit** | StatCan WDS table API | **Plan Task-1 probe** (execution-hardening): pull via the table API, pin the request; the fragile FOGS chart-page path is forbidden in code |
| Census living-arrangement cross-tab (household type × age, CMA) | Not yet verified at needed granularity | StatCan WDS | **Plan Task-1 probe.** Fallback if unavailable free at CMA level: ISQ vitrine 28% living-alone (65+, QC-wide) with a widened band [24%, 34%] and a `borrowed_prior` flag |
| IRCC PR admissions by CMA + category | Known open data; not downloaded this session | open.canada.ca monthly CSV | **Plan Task-1 probe**; suppressed-<5 cells handled as 0-band |
| MIFI plan levels (PR 45k/yr; 2026 temporary thresholds), CMHC senior-sale anchor (36%/5yr, 75+, QC), Myers retention envelope | Documented in dossier | Versioned constants module with source citations | Constants carry `as_of` dates; tripwires compare realized values against them |
| Registre foncier monthly transfer counts (validation only) | Known open data | donneesquebec.ca | v0: manual validation input, not a wired loader |

Degenerate policy (load-bearing-claim scope, applies to every loader): empty sheet, missing scenario
label, unknown geography label, negative or NaN population, non-monotone year index → **raise**, never
impute, never warn-and-continue. Cause-owner: all of these are data/environment state → explicit named
error. Error classes follow hde's convention (sole precedent: `ConfigValidationError(Exception)`):
`LoaderError(Exception)` and `CalibrationError(Exception)`, flat, no hierarchy unless the degenerate
taxonomy genuinely forces one.

## 5. Cohort engine (supply side)

**Fork A (adjudicated):** consume ISQ **population-by-age** (not households) per geography × scenario;
apply our own living-arrangement split, ownership propensity, and decrements. **Invariant I1 —
mortality is counted exactly once,** via the CPM2014/CPM-B decrement below; no input that already
embeds mortality (ISQ *household* projections, all-cause retention rates) may enter the roll-forward.

**Household states, tracked per (geography, age, year, scenario):**
`Couple`, `Solo_m`, `Solo_f` — owner-households, age = reference person (couples: same-age
approximation, stated). Annual transitions at age *a* with q_m, q_f from CPM2014+CPM-B (year-projected):

- `Couple`: exactly-one-dies `q_m(1−q_f) + q_f(1−q_m)` → **widowed `Solo_{surviving sex}`, unit
  retained** (the skeleton's first-order fix — widowhood is a state, not a same-year coincidence);
  both-die `q_m·q_f` → dissolution (estate); living exit `q_live` → exit by cause; else remain.
- `Solo_s`: death `q_s` → dissolution (estate); living exit `q_live` → exit by cause; else remain.

**Living-exit calibration (Invariant I3 — calibration targets are not interchangeable):**
`q_live` anchored to the CMHC survivor-conditional figure: 36%/5yr (75+, QC) → annualized
`1−(1−0.36)^{1/5} ≈ 8.5%/yr`, band **[6%, 11%]/yr**, age-shape (flat vs rising) as a sensitivity
axis. The Myers all-cause retention numbers are NEVER a calibration target.

**Reconciliation gate (Invariant I1's executable form):** roll a 75-year-old owner cohort forward one
decade; all-cause retention (survivors still owning / initial) must land in **[0.20, 0.40]** (Myers
0.26–0.31 envelope, widened). Outside the envelope → **raise CalibrationError**. This makes
double-counted mortality (the crash-inflating failure mode) mechanically unshippable.

**Transfer-vs-market split:** exits carry cause; `φ_market(cause)` fractions with estate-lag
convolution — voluntary exits list promptly (φ≈0.9, band [0.7,1.0]); death/estate exits convert to
listings with lag L ∈ [1,3]yr and eventual-listing fraction band [0.6, 0.85] (US survey prior,
labeled `borrowed_prior`). Registre foncier mutation counts are the coarse validation check.

## 6. Demand side

**Invariant I2 — no demand double-count (mirror of I1):** ISQ scenario populations already CONTAIN
immigrants. The immigrant channel therefore **decomposes** the projected population into arrival
cohorts (flows from the `compo-*` components workbooks, by scenario) vs resident base — it never adds
demand on top.

**Tranche 1 (core) — COARSE netting:** ownership propensity is differential at one level only:
resident base uses Census age curves; the immigrant-arrival stock uses the **Census immigrant vs
non-immigrant homeownership differential at CMA level** (free, Census-covered for Québec — probe
task §11), applied as a banded multiplier. This coarse netting is load-bearing: without it a new
(rental-skewed) immigrant reads as a new buyer and the ownership-flow inversion collapses to raw
population — the netting IS the showcase's originality claim. Native formation = headship-rate
deltas on the resident base.

**Tranche 2 (deferred with the emitter):** the years-since-landing S-curve **borrowed from ROC CHSP**
(CHSP excludes Québec — Québec discount multiplier band **[0.60, 0.85]**, labeled `borrowed_prior`;
the widest-leverage, least-validatable demand assumption) and the plex owner-occupier-landlord tilt.

**Dwelling-type axis v0:** schema field retained for forward-compatibility; v0 emits `all` only.
The plex demand compute (occupancy-share priors + owner-landlord tilt) is **deferred to v1**
alongside its supply source (rôle CUBF stock, §13) — v0 plex rows would have carried a
self-discrediting `weak_identification` flag; ship the geography signal clean instead.
[2A mod 2 — flagged for operator confirm: if a directional plex read is wanted in v0 despite weak
identification, name the concrete decision it informs.]

## 7. Outputs (the contract layer)

**(a) ScenarioPrior artifact — TRANCHE 2 (deferred; gated on a one-page S4b demographic-input-slot
sketch, authored when S4b's own design session runs).** Versioned **JSON only** (parquet mirror CUT
per 2A — one consumer, ≤240 rows; a binary mirror defeats golden-artifact diffing). One row per
(geography, dwelling_type, horizon_year ∈ {2030,2035,2040,2045,2050}, scenario ∈ {low, reference,
high} mapped at load from ISQ labels {D2026, A2026, E2026}). The `geography` field carries the
Geography enum's **string value** — the enum never crosses the file boundary:

```
schema_version, mapping_version, data_vintage {isq_edition, census_year, constants_as_of},
assumptions_hash, geography, dwelling_type, horizon_year, scenario,
demo_drift_mean, demo_drift_p10, demo_drift_p90,   # REAL (CPI-deflated) annualized price-drift
                                                    # prior, decimal/yr — matches hde's real-terms
                                                    # comparison mode and annual periods
drawdown_weight_tilt,                               # ≥0 multiplier on S4b's OWN shock probability;
                                                    # 1.0 = neutral; S4b composes it, we never emit
                                                    # an absolute probability
excess_demand_fraction,                             # raw structural signal, transparency
flags[]                                             # e.g. borrowed_prior, ra_proxy,
                                                    # never_relax_stress (contract-tested present
                                                    # on every row whose tilt < 1.0)
```

**Prohibition enforcement:** the schema is an allowlist; a contract test asserts the emitted field
set equals it exactly — no `crash_probability`, no point forecast, no unconditional quantity can be
added without failing the test and amending this spec. A second contract test asserts
`never_relax_stress` is present in `flags[]` on EVERY row with `drawdown_weight_tilt < 1.0`. S4b
consumes drift bands as priors on its price-drift generator and the tilt on its shock weights — raw
conditional inputs; S4b self-computes its shocks (locus rule: substrate supplies raw inputs,
consumer derives).

**ED→prior mapping (the danger zone, isolated — TRANCHE 2):** `balance/mapping.py`, version-stamped;
monotone piecewise-linear real-drift response with slope band β ∈ [1.0, 4.0] (%/yr per unit ED
fraction); p10/p90 spans INCLUDE β uncertainty (not just input scenarios). Every artifact row carries
`mapping_version`; changing the mapping without a version bump fails a test. β is unvalidatable
until the consumer exists — a further reason this whole layer waits for the S4b sketch. Tranche 1's
`balance/` stops at the raw `excess_demand_fraction` per (geography, year, scenario) — a structural
quantity honest on its own.

**(b) Rankings table — TRANCHE 1 CORE OUTPUT.** Relative geography ordering by demographic-flow
risk: per-geography excess-demand trajectories under the three scenarios, ranked, with the
scenario-fan spread shown. **Ranked set includes RA14/15/16 (couronne/periphery proxies)** —
justification per 2A mod 5: they are RANKING MEMBERS carrying the periphery-erosion signal (the
skeptic's strongest-honest-output), NOT participants in any balance identity (v0 models no
cross-geography flows), and they are excluded from any future ScenarioPrior emission. They carry the
`ra_proxy` label: exact RA data used as couronne/periphery proxies — the caveat is geographic scope,
not data quality.
**Composition rule:** rankings are computed within a single run (one data vintage, one
assumptions_hash) — cross-vintage comparison is refused at the emitter.

**(c) Tripwire baselines** — file of (indicator, current value, source, as_of, threshold band):
IRCC PR-by-CMA landings; temporary-resident stock vs MIFI plan; Registre foncier transfer volume;
natural-increase sign; CMHC senior-sale-rate refresh; **ISQ edition watch** (new `mise à jour` —
pin-bump trigger). `demoflow tripwires` recomputes and reports crossings; scheduling is out of scope
v0.

## 8. Junction table (typed, per 9b)

| Junction | Left | Right | Rule |
|---|---|---|---|
| Geography | ISQ row labels ("RMR de Montréal", "Montréal", "Laval", …) per workbook | `Geography` enum {MTL_RMR, MTL_ISLAND_RA06, LAVAL_RA13, QC_RMR, HORS_RMR, LANAUDIERE_RA14_PROXY, LAURENTIDES_RA15_PROXY, MONTEREGIE_RA16_PROXY} | Explicit per-source label→enum map; unknown label → raise. RA14/15/16 rows carry `ra_proxy` (exact RA data used as couronne/periphery proxies — ranking members, never balance participants, never emitted in ScenarioPrior); Laval is exact (RA13 ≡ ville); couronne-nord precision is DEFERRED (no MRC workbook exists — probed 404, 2026-07-21; plan task hunts an MRC source) |
| Age | ISQ single-year `0..99, "100 et plus"` | CPM table integer ages | "100 et plus" → capped at table max; assert CPM table covers ≥100 at load |
| Sex | ISQ M/F labels | actuarial-system `gender` strings | Explicit two-entry map; anything else → raise |
| Scenario | ISQ `Référence (A2026)/Faible (D2026)/Fort (E2026)` | `{reference, low, high}` | Explicit map at load; missing any of the three for a geography×year → raise |
| Year | ISQ `Année` + `Statut` (est/proj) | int calendar year | `Statut` is revision status, NOT scenario (skeleton friction #3); est vs proj recorded in vintage |
| Ownership rate | Census CMA cross-tab (MTL CMA ≡ MTL_RMR; QC CMA ≡ QC_RMR) | cohort engine propensities | CMA↔RMR treated as identical geography (same StatCan delineation); RA-level rows reuse CMA rate with `borrowed_prior` flag until a finer cross-tab lands |

## 9. Operational-future statement (item 10)

Stateless batch CLI; no services, no concurrent writers, no persisted identity beyond artifact files.
Artifact identity = (data_vintage, assumptions_hash, mapping_version, schema_version) — a change in
any re-mints the artifact BY DESIGN; S4b runs record which artifact they consumed (hde side, S4b
design's obligation). ISQ edition refresh does not silently change outputs (pins). A future cron for
tripwires would be a new operational surface — explicitly out of scope of this spec.

## 10. Testing

TDD throughout (mm-spine discipline). Anchors:
- **Oracle-anchored cohort math**: hand-computed 2-cohort, 3-year example (fixture with the full
  arithmetic in comments); transition identities (state mass conservation: every household ends in
  exactly one of {remain, widowed, dissolved, exited}).
- **RED calibration gates**: a config that double-counts mortality MUST raise CalibrationError
  (reconciliation gate test); a q outside [0,1] MUST raise.
- **Loader pins**: recorded sha256 fixtures; schema-drift fixture (mutated sheet) MUST raise; the
  fail-loud claims get their adversarial pass from stress-tester at PR time (load-bearing-claim tag).
- **Contract tests**: ranking same-vintage refusal; import-direction tests (demoflow⊥hde both
  ways). Tranche 2 adds: ScenarioPrior field allowlist; `never_relax_stress` on every tilt<1.0 row;
  mapping_version bump enforcement.
- **Golden artifacts (Tranche 1)**: one committed rankings output + one tripwire-baseline output
  from the committed data vintage (JSON, diffable). Tranche 2 adds the golden ScenarioPrior.
- **Basis assertion test**: entry point on a fresh interpreter must fail if the Québec basis is not
  active (guards the US-default gotcha).

## 11. Plan Task-1 probes (execution-hardening; run at plan execution, not spec time)

1. demoflow env stands up: uv project + path dep on actuarial-system; `get_qx` fires cross-env with
   the QC basis (in-repo proven; cross-env install mechanical but unproven).
2. StatCan WDS table-API pull of 98-10-0231-01 (MTL + QC CMAs).
3. Census living-arrangement cross-tab hunt (fallback: vitrine 28% + widened band).
4. Census immigrant vs non-immigrant homeownership by CMA (the Tranche-1 coarse-netting
   differential — Census-covered for Québec, unlike CHSP).
5. IRCC PR-by-CMA CSV download + schema record.
6. MRC-level ISQ source hunt for couronne-nord precision (404 on slug convention; try product pages /
   full-edition downloads); if found → Geography enum extension in v1, not v0.

## 12. Effort & sequencing (re-cut per 2B gate, 2026-07-21)

**Execution precondition:** the S4a closeout lane (PR + merge of `feat/housing-decision-engine-s4a`)
runs FIRST — demoflow's build starts from post-merge main. Rationale: recovery-point hygiene (this
spec is committed on that branch; two arcs must not entangle), not an artifact dependency.

**Tranche 1 (~2–3 sessions) — the value core:** T1a loaders + junctions (+ §11 probes);
T1b cohort engine + calibration gates; T1c coarse demand netting + excess-demand fractions +
rankings + tripwires + golden artifacts. **The LinkedIn showcase ships off Tranche 1** (map +
inversion headline + tripwire table + epistemic-limits framing) — none of the deferred machinery
is visible to that audience.

**Tranche 2 (deferred; own gate):** ScenarioPrior emitter + ED→drift mapping (β) + YSL fine
structure + QC-discount multiplier. Gated on the named artifact: a one-page S4b
demographic-input-slot sketch (authored in S4b's design session, which itself consumes merged S4a).
Deferral costs nothing — the artifact is unconsumable until S4b exists.

Handed off Opus-main per steering routing.

## 13. Deferred ledger (explicitly out of v0 / Tranche 1)

**Tranche 2 (gated on S4b input-slot sketch):** ScenarioPrior emitter; ED→drift mapping (β band);
immigrant YSL S-curve + ROC-CHSP borrowing + QC-discount multiplier [0.60, 0.85];
`never_relax_stress` contract enforcement (rides the emitter).
**v1+:** MRC-level couronne split (pending source); plex demand compute + supply stock from rôle
CUBF (2A mod 2 — operator may pull forward with a named decision it informs); StatCan paid custom
tabulation (CT-level immigrant tenure); >2051 horizon tail (only QC-total reaches 2071 — any
extension is a named extrapolation); actuarial-system multiple-decrement combinator (charter
extension, operator sign-off); tripwire scheduling/cron.
**CUT (not deferred):** parquet mirror (revisit only at columnar scale); `weak_identification`
flag (dies with the v0 plex compute).
**REJECTED (not deferred):** forecaster-lite.
