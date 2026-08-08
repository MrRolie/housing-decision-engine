# demoflow — Demographic Housing-Flow Scenario Module — Design

**Date:** 2026-07-21
**Status:** Approved design (operator 2026-07-21); elegance-gate 2A+2B folded (both
PROCEED-WITH-MODIFICATIONS, 2026-07-21 — 2B re-sequenced to rankings-first tranches with the
ScenarioPrior emitter deferred behind an S4b input-slot sketch; 2A subtractive mods folded: parquet
mirror cut, plex compute deferred to v1, CLI folded to run+tripwires, flat error classes,
enum→string serialization stated); 2C cross-CONTEXT arm WAIVED by operator 2026-07-21 (session model
is Fable; residual gap recorded: the arm's catch mechanism is independent context + hunt-NEW framing,
not model tier — same-family folded-spec defects go unhunted by that arm; codex cross-FAMILY arm ran
regardless, per doctrine the waiver never reaches it); spec pending operator review
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
- **actuarial-system dependency:** uv path dependency (`../../actuarial-system` from the
  `demoflow/` project directory — one level under the HDE repo root, so two levels up to the
  sibling checkout; codex r6-F7 caught the §2/§3 contradiction — lain-local; showcase
  runs need both repos present, accepted at the operator fork 2026-07-21). Import surface pinned to
  `mcp_server.engine.mortality` public functions only: `set_active_mortality`, `active_mortality`,
  `get_qx`. No private reach-ins. Dependency weight (fastmcp/cvxpy/osqp ride along) accepted —
  lain-local batch tool.
- **Basis contract (gotcha codified in actuarial-system/CLAUDE.md):** the engine DEFAULTS to the US
  RP2014+MP2021 basis. Every demoflow entry point sets
  `set_active_mortality("CPM2014_combined", "CPM-B")` and then CHECKS `active_mortality()` echoes the
  Québec basis before any `get_qx` call — an explicit `if`-check raising `BasisError(Exception)`,
  NEVER a bare `assert` (stripped under `python -O` — codex F7). Single-threaded batch only
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
label, unknown geography label, negative or NON-FINITE (NaN/±Inf) values in ANY numeric input —
populations, headship/ownership/living-arrangement rates, immigrant propensities, hazards q —
(signed-FLOW carve-out, codex r9-F2: indicators that are legitimately signed — natural increase,
net migration components — are exempt from the negativity gate and bind finite-only; the nonneg
rule governs stocks and rates, never signed flows: the natural-increase tripwire's whole job is to
evaluate a negative value, not raise on it) —
non-monotone year index → **raise**, never impute, never warn-and-continue (codex r4-F3: the finite
contract is END-TO-END — every emitted JSON in every tranche, rankings and tripwires included,
serializes with `allow_nan=False` and asserts field finiteness pre-write). Two further loader
contracts (codex r5-F1/F2, ratio carve-out r7-F8): every FRACTION-valued input — living-alone,
couple-share, collective-share, headship, ownership, the immigrant PROPENSITY p_imm, φ_market, q —
is asserted ∈ [0, 1] (1+ε passes a mere finite/negative gate while producing negative buckets or
owners > households); the immigrant/non-immigrant ownership RATIO is a ratio, not a fraction —
asserted nonnegative-finite only (immigrants CAN out-own non-immigrants in a cell; ratio 1.2 with
p_nonimm 0.6 is a valid p_imm 0.72) — the [0,1] probability constraint binds the PRODUCT p_imm; and every loaded series declares its PRIMARY KEY (geography × year × scenario × sex ×
age-block) with duplicates → raise AND a CONTIGUOUS year lattice pinned to the EXPECTED DOMAIN
(codex r5-F2 + r6-F3): consecutive year differences exactly 1 AND endpoints equal to the file
family's declared span (2021–2051 for the RMR/RA workbooks) AND an identical year domain across
every geography × scenario × sex series — a missing terminal year for one geography must raise,
never silently shorten that geography's ranking mean. The `Statut` SUB-LATTICE is validated too
(codex r10-F5 — the raw lattice can be intact while a proj→est relabel silently shortens a ranking
mean): values ∈ {r, p, j-family per the metadata}, exactly ONE est→proj transition per series, and
an IDENTICAL projected-year domain across every geography × scenario × sex — deviation raises;
RED fixture relabels one geography's 2051 from proj to est. Cause-owner: all of
these are data/environment state → explicit named
error. Error classes follow hde's convention (sole precedent: `ConfigValidationError(Exception)`):
`LoaderError(Exception)` and `CalibrationError(Exception)`, flat, no hierarchy unless the degenerate
taxonomy genuinely forces one.

## 5. Cohort engine (supply side)

**Fork A (adjudicated):** consume ISQ **population-by-age** (not households) per geography × scenario;
apply our own living-arrangement split, ownership propensity, and decrements. **Invariant I1 —
mortality is counted exactly once,** via the CPM2014/CPM-B decrement below; no input that already
embeds mortality (ISQ *household* projections, all-cause retention rates) may enter the roll-forward.

**Initialization — unit-preserving persons→households conversion (codex r1-F1, r2-F1):** at base
year, per (geography, age, sex), private-household persons partition into exactly THREE buckets
using SEX-SPECIFIC rates (codex r3-F1 — a pooled couple rate is not sex-conserving: 20 men + 100
women at couple_share=1 would fabricate 40 husbands, and at 85+ the female surplus is the ACTUAL
population structure): `Solo_s(a) = pop_s(a) × living_alone_rate_s(a)`;
`coupled_s(a) = pop_s(a) × (1 − living_alone_rate_s(a)) × couple_share_s(a)`;
`Other_s(a) = pop_s(a) × (1 − living_alone_rate_s(a)) × (1 − couple_share_s(a))` — persons living
with others (family/roommates, incl. seniors with adult children), EXPLICITLY EXCLUDED from the
cohort's owner-unit stock as presumptive non-maintainers (conservative undercount, labeled
assumption; collective/institutional persons removed before the partition via the Census collective
share). Couples form only from matched pairs, and matching is a MINIMUM, never an average (codex
r4-F1 — averaging 100 vs 80 coupled persons emits 90 couples when at most 80 matched pairs exist):
`Couple(a) = min(coupled_m(a), coupled_f(a))`; the EXCESS of the larger side,
`max − min` persons, routes to `Other` (they are real coupled persons whose partners fall outside
the same-age band — the same-age approximation makes them unmatchable here; routing to Other keeps
them excluded conservatively and preserves person conservation BY SEX exactly). Zero-zero branch:
`coupled_m = coupled_f = 0 → Couple = 0`, no ratio evaluated. Per-age-band coupled-count imbalance is EXPECTED under the same-age approximation (cross-age
coupling: older men partner younger; women outlive men — live Census breached the old 0.25 band
gate on 13/21 correct rows, refuting its premise; execution ruling 2026-07-25). Hard gates keep only
the invariants reality preserves: coupled_s ≥ 0; coupled_s ≤ its sex pool; and at the 75+ AGGREGATE,
coupled_m ≥ coupled_f (a reversal beyond |diff|/max > 0.25 at the aggregate ⇒ CalibrationError — that
direction IS invariant). The per-band imbalance profile is RECORDED in run artifacts as a diagnostic,
never a gate. min() matching + excess→Other are unchanged; couple_share values stay EXACTLY as cited
(§11.3 wins over any gate).
Person conservation asserted per sex: `Solo_s + coupled_s + Other_s = private pop_s`, and
post-match: `min + excess = coupled_larger` (nothing fabricated, nothing dropped).
Ownership rates are HOUSEHOLD-maintainer-denominated (Census tenure tables) and multiply HOUSEHOLD
counts, never person counts. Fixtures (§10): (a) 100 men + 100 women all coupled, 60% household
ownership → exactly 60 Couple owner units, 0 Solo, 0 Other; (b) GENERAL case — 200 persons,
living_alone 0.25, couple_share 0.80 → 50 Solo + 60 Couple + 30 Other, persons reconcile
50 + 120 + 30 = 200 (the all-coupled fixture alone cannot see a leaked residual).

**Stock-flow discipline (I1 at the equation level — codex F2):** ISQ population enters the owner
roll-forward EXACTLY ONCE per cohort — at band entry (base-year stock + each year's newly-aged-75
entrants from ISQ cohort aging; their pre-75 mortality is ISQ's, disjoint from our 75+ decrements).
Post-entry, stocks evolve ONLY by our decrements; the roll-forward is NEVER re-anchored to ISQ's
projected 75+ stocks in later years (those stocks embed deaths — re-anchor + decrement = the
double-count). The plan writes the t→t+1 stock-flow equation with every death term appearing exactly
once, plus a mutation test — **asserted against the ORACLE fixture's exact pinned numbers, NOT the
aggregate envelope (codex r7-F5: the envelope cannot carry this — at q_live's low end, doubled
mortality still retains ≈0.25, inside [0.20, 0.40]):** applying the CPM decrement twice must change
the hand-computed oracle values (exact inequality against the pinned expectations); the envelope
remains a coarse gross-error backstop only. **Named omission (codex r3-F2, deliberate
altitude call):** the post-entry cohort is CLOSED — net migration at ages 75+ after band entry is
omitted. **AMENDED 2026-08-07 (steering ruling J):** the original evidence prescription ("the
`compo-*` workbooks bound the magnitude — record the 75+ net-migration share there") is REFUTED
for the committed vintage — both compo workbooks carry NO age axis (whole-sheet scan, zero `âge`
header hits; region × scenario × year totals only), so no 75+ share is computable there. The
evidence leg is RE-POINTED: an AGE-STRUCTURED migration source (ISQ interregional migration by
age group; else StatCan components-of-growth by age) supplies the measured 75+ net-migration
rate (|75+ net migration| / 75+ population, per modeled geography) recorded in the probe note.
MATERIALITY TRIPWIRE: a measured rate above 1%/yr in any modeled geography×scenario ESCALATES
the closed-cohort altitude call back to the operator (rationale: 75+ all-cause exit hazards run
≥10%/yr, so a 1%/yr cap keeps the omission's relative distortion near or under 10%). Until that
probe lands, the note carries the omission as UNEVIDENCED-PENDING — never as bounded.
**RESOLVED 2026-08-07 (steering ruling K; operator-ruled at the tripwire escalation):** the
probe ran (StatCan 17-10-0149/0151 components + 17-10-0148/0150 populations; identity
verified exact at All-ages) and the tripwire FIRED — Laval (RA13) 75+ net-migration reached
1.672% / 1.156% / 1.041% per year in 2007/08–2009/10 (full published span 2001/02–2024/25;
every other covered geography ≤ 0.81%; latest-5-period max 0.774%). THE OMISSION STANDS for
Tranche 1: the note's verdict form is EVIDENCED-WITH-NAMED-EXCEEDANCE (full-span per-geography
table; HORS_RMR recorded NOT-COVERED by the source, never approximated), and every ranking
row of an exceeding geography carries the `closed_cohort_exceedance` flag (enum amended
above; wired at the rankings task). The tripwire is evaluated on the FULL published span — a
window whose sole visible effect is to remove the exceedance is not evidence. This is a stated
assumption with a sensitivity remark in outputs, not a modeled mechanism; adding a reconciled
post-entry migration term without reintroducing ISQ-embedded mortality is a v1 item.

**Household states, tracked per (geography, age, year, scenario):**
`Couple`, `Solo_m`, `Solo_f` — owner-households, age = reference person (couples: same-age
approximation, stated). **Pinned competing-risk algebra (codex F3): death resolves first; living
exit is survivor-conditional; branches partition to 1 by construction.** With q_m, q_f from
CPM2014+CPM-B (year-projected) and q_live survivor-conditional:

- `Couple`: P(both die) = `q_m·q_f` → dissolution (estate); P(exactly one dies) =
  `q_m(1−q_f) + q_f(1−q_m)` → **widowed `Solo_{surviving sex}`, unit retained** (widowhood is a
  state, not a same-year coincidence; the new widow is NOT living-exit-eligible in the transition
  year — eligible from the next year); P(no death) = `(1−q_m)(1−q_f)`, splitting `q_live` →
  living exit, `1−q_live` → remain.
- `Solo_s`: death `q_s` → dissolution (estate); survivors split `(1−q_s)·q_live` → living exit,
  `(1−q_s)(1−q_live)` → remain. Partition fixture (§10): q_s=0.20, q_live=0.10 → death 0.20,
  living-exit 0.08, remain 0.72; all branches ≥0, sum exactly 1.

**Living-exit calibration (Invariant I3 — calibration targets are not interchangeable):**
`q_live` anchored to the CMHC survivor-conditional figure: 36%/5yr (75+, QC) → annualized
`1−(1−0.36)^{1/5} ≈ 8.5%/yr`, band **[6%, 11%]/yr**, age-shape (flat vs rising) as a sensitivity
axis. The Myers all-cause retention numbers are NEVER a calibration target.

**Reconciliation gate (I1's aggregate backstop — honest claim, codex F2; composition PINNED
r9-F4 — retention is state-dependent, so an unpinned cohort mix makes the gate ambiguous):** roll
a 75-year-old owner cohort forward one decade, where the cohort's household-state and sex
composition is the one the INITIALIZATION EQUATIONS produce on the committed data vintage for
MTL_RMR (pinned by construction, recorded in the fixture); all-cause retention (survivors still
owning / initial) must land in **[0.20, 0.40]** (Myers 0.26–0.31 envelope, widened). Outside →
**raise CalibrationError**. Per-state retention paths (Solo_m, Solo_f, Couple) are additionally
pinned in the oracle fixture. This catches GROSS mortality double-counting; it is an aggregate
band, not a proof of exactly-once — the exactly-once guarantee lives in the stock-flow equation +
mutation test above. Both together are the enforcement.

**Transfer-vs-market split:** exits carry cause; `φ_market(cause)` fractions with estate-lag
convolution — voluntary exits list promptly (φ≈0.9, band [0.7,1.0]); death/estate exits convert to
listings with lag L ∈ [1,3]yr and eventual-listing fraction band [0.6, 0.85] (US survey prior,
labeled `borrowed_prior`). Registre foncier mutation counts are the coarse validation check.

## 6. Demand side

**Invariant I2 — no demand double-count (mirror of I1), EXECUTABLE (codex r5-F3):** ISQ scenario
populations already CONTAIN immigrants. The immigrant channel therefore **decomposes** the projected
population — it never adds demand on top — and the decomposition is an EQUATION with a gate, not a
principle: per (age, geography, scenario, year t),

    P_resident(t) = P_ISQ(t) − Σ_c SurvivingArrivalCohort_c(t)

where arrival cohorts come from the `compo-*` annual flows and survive forward on the same CPM
basis (mortality once — their post-arrival deaths are ours, their pre-arrival dynamics are the
flow's). **Operand binding (codex r6-F1 — the identity alone cannot catch a mis-wired consumer,
because it holds regardless of what native formation reads):** native formation's ONLY population
parameter is P_resident by construction (single code path, no access to P_ISQ), and the
double-entry mutation test operates at the PIPELINE level: with arrivals > 0,
`D_native(P_resident) ≠ D_native(P_ISQ)` in the fixture, and the emitted demand must equal the
P_resident evaluation — feeding P_ISQ at the call site changes the output and fails the
integration assertion. The decomposition-identity gate remains as the data-side check; the
operand assertion is the consumer-side check; both run. **Nonnegativity (codex r7-F3 — the
identity is tautological when P_resident is DERIVED from it):** `P_resident(a,g,s,t) ≥ 0` is
asserted per cell BEFORE any consumer — surviving arrivals exceeding P_ISQ in a cell means the
arrival-survival assumptions contradict the scenario population (CalibrationError), never a
negative resident base flowing into formation.

**Tranche 1 (core) — COARSE netting, dimensionally explicit (codex r2-F2):** ISQ component
arrival flows are PERSON-denominated; ownership propensities are HOUSEHOLD-maintainer-denominated —
persons never multiply a household rate directly. The chain is: arrivals(persons) × immigrant
headship rate (households formed per person — Census immigrant household size / maintainer rate,
probe §11) → immigrant HOUSEHOLDS → × the immigrant ownership propensity, DEFINED (codex r4-F5 — a bare "differential"
is ambiguous between relative multiplier and absolute probability): `p_imm(a) = p_nonimm(a) ×
ratio`, where `ratio` = the **Census immigrant/non-immigrant ownership RATIO at CMA level**
(banded), `p_nonimm(a)` is the resident-base Census propensity already loaded, and the resulting
`p_imm` is asserted ∈ [0,1] → immigrant owner-household demand.

**Native formation DEFINED, disjoint from S (codex r6-F2 — without a sign rule, a 75+ headship
decline enters D as negative formation while the SAME dissolutions enter S: double-counting the
senior release):** `D_native(g,t,s) = Σ_{a_min < a < 75} max(0, H_resident(a,t) −
H_resident(a−1, t−1)) × ownership(a)` **summed over 19 ≤ a < 75, PLUS the explicit age-18 term**
(codex r7-F7 boundary, summation corrected r10-F4 — the earlier strict inequality excluded the very
term the boundary rule requires): `D_native = max(0, H_resident(18, t)) × ownership(18) +
Σ_{19 ≤ a < 75} max(0, H_resident(a,t) − H_resident(a−1, t−1)) × ownership(a)` — new entrants at 18
form against zero prior stock, by equation, never by array wraparound (fixture: nonzero
H_resident(18), zero elsewhere → D = H(18)×ownership(18), not zero; plus the planted terminal-age
wraparound catch). GROSS formations from the
UNDER-75 resident base only (cohort-followed headship gains, floored at zero). All 75+ stock dynamics — dissolution, downsizing, estate release — live
EXCLUSIVELY in S via the cohort engine; the age-75 boundary makes D and S structurally disjoint.
Reconciliation fixture: a two-year run with no arrivals, one 75+ cohort declining in headship, and
one supply-side exit must show the decline in S only, D unchanged. **Full-geography join for the
immigrant inputs (codex r5-F4 — the base-ownership borrowing rule does not cover them):** immigrant
headship and the immigrant/non-immigrant ratio resolve per modeled geography from an EXPLICIT
source table — MTL_RMR/QC_RMR: their CMA values direct; RA members: parent-CMA value,
`borrowed_prior`; HORS_RMR: province-level value, `borrowed_prior` (a province-net residual for
these cross-tabs is not cheaply available); every modeled member must resolve or the run raises —
no unstated default under the no-imputation policy. Dimensional
test (§10): 100 arriving persons as 50 two-person households vs as 100 one-person households MUST
produce different D (identical D = the units defect). This coarse netting is load-bearing: without
it a new (rental-skewed) immigrant reads as a new buyer and the ownership-flow inversion collapses
to raw population — the netting IS the showcase's originality claim. Native formation =
headship-rate deltas on the resident base.

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
schema_version, mapping_version,
data_vintage {isq_edition, census_year, constants_as_of,
              source_hashes: {<source>: sha256-of-raw-response, extracted_at}},
              # codex r3-F6: census_year is not a PIT vintage — StatCan tables get corrected
              # in place; every non-ISQ source's RAW RESPONSE is hashed at extract time and
              # the hash is part of artifact identity (ISQ files are already byte-pinned)
assumptions_hash, geography, dwelling_type, horizon_year, scenario,
demo_drift_mean, demo_drift_p10, demo_drift_p90,   # REAL (CPI-deflated) annualized price-drift
                                                    # prior, decimal/yr — matches hde's real-terms
                                                    # comparison mode and annual periods
drawdown_weight_tilt,                               # ≥0 multiplier on S4b's OWN shock probability;
                                                    # 1.0 = neutral; S4b composes it, we never emit
                                                    # an absolute probability
excess_demand_fraction,                             # raw structural signal, transparency
flags[]                                             # CLOSED enum (codex r2-F3): exactly
                                                    # {borrowed_prior, ra_proxy, never_relax_stress}
                                                    # — value-bearing or unknown flag strings are
                                                    # REJECTED at validation (an open flags[] is a
                                                    # serialization side-channel for the prohibited
                                                    # quantities); never_relax_stress contract-tested
                                                    # present on every row whose tilt < 1.0
```

**Prohibition + integrity enforcement (strengthened per codex F6):** the schema is an allowlist; a
contract test asserts the emitted field set equals it exactly — no `crash_probability`, no point
forecast, no unconditional quantity can be added without failing the test and amending this spec.
Further contract tests: `never_relax_stress` present in `flags[]` on EVERY row with
`drawdown_weight_tilt < 1.0`; row keys form the COMPLETE Cartesian product of the declared
(geography × dwelling_type × horizon × scenario) domains with NO duplicates; every numeric field
finite (JSON serialized with `allow_nan=False` — Python's default permits NaN); band ordering
`p10 ≤ mean ≤ p90` on every row; `drawdown_weight_tilt ≥ 0`; horizon/scenario values drawn only
from the declared enums. Each violation is a distinct RED fixture in §10. S4b
consumes drift bands as priors on its price-drift generator and the tilt on its shock weights — raw
conditional inputs; S4b self-computes its shocks (locus rule: substrate supplies raw inputs,
consumer derives).

**ED→prior mapping (the danger zone, isolated — TRANCHE 2; units PINNED NOW, codex r3-F7 — the
ambiguity was worth 100×):** `balance/mapping.py`, version-stamped; v0 form is LINEAR THROUGH THE
ORIGIN: `demo_drift = β × ED`, where ED is the dimensionless fraction of §7 and β converts to
DECIMAL real drift per year per unit ED — worked fixture: `ED = 0.01, β = 2.0 → demo_drift = 0.02
decimal/yr = 2%/yr real`. β band [1.0, 4.0] in these units with a UNIFORM distribution over the
interval (codex r6-F5 — an interval alone leaves quantiles undefined): demo_drift quantiles follow
in closed form from the linear map (for ED ≥ 0, p10/p90 of drift = β's 10th/90th quantiles × ED;
reversed for ED < 0; mean = 2.5 × ED). Zero intercept by construction (no demographic tilt at flow
balance); any knots/saturation or a non-uniform β prior are a Tranche-2 decision made WITH the S4b
sketch, never improvised. p10/p90 spans INCLUDE β uncertainty (not just input scenarios). Every artifact row carries
`mapping_version`; changing the mapping without a version bump fails a test. β is unvalidatable
until the consumer exists — a further reason this whole layer waits for the S4b sketch.

**Tranche 1's `balance/` stops at the raw excess-demand fraction, DEFINED (codex F4) — all terms
annual, household-denominated, per (geography g, year t, scenario s):**

    ED(g,t,s) = [ D(g,t,s) − S(g,t,s) ] / OwnerStock(g,t,s)

    D = native owner-household formation (headship deltas × ownership propensity)
      + immigrant-cohort formation (arrival flows × immigrant-differential propensity)   # §6
    S = Σ_cause exits(cause) × φ_market(cause), with estate exits lagged L years          # §5
    OwnerStock(g,t,s) = Σ_over_all_ages pop(a,g,t,s) × headship(a) × ownership(a)
      — DEFINED (codex r3-F3): annual re-estimation from ISQ scenario population with BASE-YEAR
      Census headship and ownership rates held constant (PIT-fixed, labeled assumption). This is a
      stock LEVEL estimate; ISQ-embedded mortality is correct here and does not conflict with I1,
      which governs the 75+ exit FLOW model only. No carried-forward under-75 stock exists — the
      denominator has exactly one defining equation.

Denominator guard with a NUMERIC boundary (codex r9-F5): `OwnerStock < 1,000` households → raise
(no modeled geography legitimately carries fewer; fixtures at 999 / 1,000 / 1,001) — never emit an
unbounded fraction, and never leave "near-zero" to implementation taste. ED is scale-invariant
(households/households); a hand-worked fixture (§10) pins one unique ED value from the spec alone,
including a delayed estate listing crossing a horizon boundary.

**(b) Rankings table — TRANCHE 1 CORE OUTPUT.** Relative geography ordering by demographic-flow
risk: per-geography excess-demand trajectories under the three scenarios, ranked, with the
scenario-fan spread shown. **Ranked set includes RA14/15/16 (couronne/periphery proxies)** —
justification per 2A mod 5: they are RANKING MEMBERS carrying the periphery-erosion signal (the
skeptic's strongest-honest-output), NOT participants in any balance identity (v0 models no
cross-geography flows), and they are excluded from any future ScenarioPrior emission. They carry the
`ra_proxy` label: exact RA data used as couronne/periphery proxies — the caveat is geographic scope,
not data quality.
**Identity envelope on SHIPPED files (codex r7-F6 — §9's artifact identity must be carried, not
just defined):** rankings and tripwire JSON each open with the same top-level envelope
{schema_version, data_vintage (incl. source_hashes), assumptions_hash} above their rows; a
consumer (and the same-vintage refusal check) reads identity from the envelope and rejects
mixed-identity row sets; contract-tested with a two-vintage mixing RED.

**No open string anywhere — the GENERAL rule (codex r9-F3, closing the side-channel class rather
than the next instance):** EVERY string-typed position in every emitted artifact — field values,
enum members, map KEYS (source_hashes keys are drawn from the code-owned source registry; values
must be 64-hex), timestamps (ISO-8601-validated) — is either registry/enum-bound or
format-validated. No free-form string exists in any demoflow artifact; a validator walks the full
document tree asserting this, so a future field addition cannot silently reopen the channel.

**Tranche-1 output allowlists (codex r5-F5, value channels closed r6-F4 — the prohibition must
bind SHIPPED formats AND their string fields):** the rankings JSON and tripwire JSON each carry an
exact nested field allowlist — rankings row: {geography, mean_ed_reference, mean_ed_low,
mean_ed_high, rank, rank_stable, flags[]} with `rank_stable` a TYPED boolean carrying the r8-F1
robustness-sweep verdict (codex r9-F1 — the mandated stability result needs a schema home, never a
flag string) and `flags[]` a CLOSED enum {borrowed_prior, ra_proxy, closed_cohort_exceedance
— **added by steering ruling K, 2026-08-07 (operator-resolved): rides every ranking row of a
geography whose measured 75+ net-migration rate historically exceeded the 1%/yr materiality
cap (currently: LAVAL_RA13), marking its rank lower-confidence under the closed-cohort
assumption**} (scenario
semantics per the collapse rule below); tripwire record: {indicator, current_value, source, as_of,
band_low, band_high, status, reason?} with `reason` drawn from a CLOSED machine-token enum {stale,
source_unavailable, operator_input_missing, non_finite, malformed_band, future_as_of,
missing_indicator, duplicate_indicator} AND `source` BOUND to the code-owned
registry (codex r7-F1 — each indicator's source string is declared in the registry constant; the
record must equal it exactly, so `source` cannot carry smuggled content) — NO free-text string
field exists in either format (an open string is the same serialization side-channel the
ScenarioPrior flags enum closes). **UNKNOWN-branch nullability (codex r7-F2 — a first-run failure has
no honest measurement):** `current_value` and `as_of` are NULLABLE exactly when status=UNKNOWN with
reason ∈ {source_unavailable, operator_input_missing, missing_indicator, **non_finite** (codex
r8-F2 — a NaN/Inf measurement cannot ride a finite-only JSON: current_value is null, the offending
raw value goes to the run log, never the artifact)} — null, NEVER a fabricated finite value; every
other status requires all fields non-null; contract-tested both ways. **empty_registry is a
RUN-level terminal error, not a per-indicator reason (codex r10-F6 — with no indicators there is
nothing to attach an UNKNOWN record to):** removed from the per-indicator reason enum; an empty
baseline emits NO artifact and exits nonzero with the named error. Contract tests assert field
sets equal the allowlists exactly AND every enum-typed value is a member, with RED fixtures adding
a `crash_probability` field AND smuggling `"crash_probability=0.35"` through flags[]/reason — all
independent of the goldens. Epistemic limit (codex r10-F1, same class as r4-F4): field allowlists
bind VOCABULARY, not value semantics — no schema proves a number in an allowed field was derived
conditionally; that guarantee lives in the single derivation path (the version-stamped mapping
module is the only producer of tilt/drift values, origin-asserted in the Tranche-2 emitter tests)
plus review. Named, not hand-waved.

**Scenario-named fan fields (codex r6-F6 — scenario identity vs min/max are DIFFERENT semantics
and can cross):** `mean_ed_low` / `mean_ed_high` are SCENARIO-NAMED — the Faible (D2026) and Fort
(E2026) scenario means respectively, whatever their numeric order; the ranking tiebreak uses the
scenario-named Faible mean; any min/max "fan envelope" is derived at display time, never stored.
A scenario-crossing fixture (Faible mean +0.02, Fort mean −0.03) pins the field semantics.

**Run contract for banded assumptions (codex r8-F1 — bands alone leave the run underdetermined;
two conforming implementations must not emit different rankings from identical data):** a Tranche-1
run evaluates every banded assumption at its declared CENTRAL value — q_live 0.085/yr flat
age-shape, φ_market voluntary 0.9 / estate eventual 0.725, estate lag L=2, immigrant ratio band
center — as the headline; band ENDPOINTS enter only through the mandated robustness sweep, reported
per geography as a rank-stability flag (does the ordering change anywhere in the sweep grid?).
The central values + sweep grid are enumerated in `constants.py` and covered by assumptions_hash —
the hash identifies the selection, the spec's central-value rule DETERMINES it.

**Ranking temporal domain (codex r8-F3):** ranking means average over PROJECTED years only
(`Statut = proj` rows — estimation years are history, not scenario), the full contiguous annual
lattice from the first projected year through 2051, both endpoints included; a fixture pins a pair
of trajectories whose ordering would reverse under an all-years average.

**Ranking collapse rule (codex F4, fan wording reconciled r8-F4 — the earlier min/max sentence
contradicted the scenario-named fields):** rank by MEAN ED over the domain above under the
REFERENCE scenario, ascending (most negative ED = highest demographic-flow risk = rank 1); the fan
is REPORTED per geography as the SCENARIO-NAMED Faible and Fort means (mean_ed_low / mean_ed_high
per the field semantics below — min/max envelopes are display-derived only, never stored); ties
(exact mean-ED equality) break by the scenario-named Faible mean (worst case), then by enum order
as the final deterministic tiebreak. A
fixture (§10) pins one unique ordering, including an exact-tie case and a scenario-crossing case.
**Composition rule:** rankings are computed within a single run (one data vintage, one
assumptions_hash) — cross-vintage comparison is refused at the emitter.

**(c) Tripwire baselines** — file of (indicator, current value, source, as_of, threshold band),
with a per-indicator SOURCE-COVERAGE declaration (codex F5): `wired` (IRCC PR-by-CMA landings;
temporary-resident stock — source named at probe §11; ISQ edition watch) vs `operator-supplied`
(Registre foncier transfer volume — manual v0; CMHC senior-sale-rate refresh; natural-increase
sign, annual ISQ release). **Fail-safe contract (this is a verification gate — it must refuse,
never false-green):** each indicator's result ∈ {OK, CROSSED, UNKNOWN(reason)}; UNKNOWN fires on
source-unavailable, operator-input-missing, or `as_of` older than the indicator's declared
freshness limit — a stale baseline is NEVER reported as within-band. Threshold endpoints evaluate
as CROSSED (closed bands). **Completeness integrity (codex r2-F4 + r3-F4 — no vacuous green, no
co-deletion):** the required-indicator set is a VERSIONED CONSTANT IN DEMOFLOW SOURCE CODE, not in
the baseline file it validates (a self-declared set dies to co-deletion: removing an indicator from
both the declaration and the records leaves an internally consistent partial registry). The
evaluator asserts exact-key equality of the baseline's records against the code-owned set — empty
registry, missing required indicator, or duplicate key ⇒ UNKNOWN/nonzero. **Value integrity (codex
r3-F5):** a present, fresh indicator whose current value is NaN/±Inf/non-numeric, whose `as_of` is
in the future, or whose band is inverted (lower > upper) ⇒ UNKNOWN, never within-band (naive
comparisons classify NaN as inside every band — both boundary checks are False); tripwire JSON is
emitted with `allow_nan=False` too. Exit code: 0 only when every code-required indicator is present
exactly once, finite, fresh, well-banded, and OK; nonzero otherwise. Epistemic limit (codex r4-F4):
no runtime check defends the checker's own source from a coordinated edit — the residual guard is
that the golden-baseline TEST pins the full required-indicator name list LITERALLY in the test body
(a third, test-owned copy), so a co-deletion must touch code + baseline + test in one diff — a
PR-visible act, which is review's job to catch, not the runtime's. Scheduling is out of scope v0.

## 8. Junction table (typed, per 9b)

| Junction | Left | Right | Rule |
|---|---|---|---|
| Geography | ISQ row labels per workbook — **verified 2026-07-21 to carry trailing whitespace and embedded footnote digits** (`'RMR de Montréal '`, `"RMR d'Ottawa-Gatineau2"`) | `Geography` enum {MTL_RMR, MTL_ISLAND_RA06, LAVAL_RA13, QC_RMR, HORS_RMR, LANAUDIERE_RA14_PROXY, LAURENTIDES_RA15_PROXY, MONTEREGIE_RA16_PROXY} | NORMALIZE first (strip whitespace, strip trailing footnote digits), THEN a TOTAL label map over the workbook's verified label set (codex r4-F2): 'RMR de Montréal' → MTL_RMR, 'RMR de Québec' → QC_RMR, **'Territoire hors des RMR' → HORS_RMR (the workbook's OWN literal row supplies HORS_RMR population directly — codex r7-F4: stated explicitly, never a residual)**; the five present-but-unmodeled rows (Ottawa-Gatineau QC-part, Saguenay, Sherbrooke, Trois-Rivières, Drummondville, plus 'Le Québec') → an explicit `IGNORED` sentinel (recognized-and-excluded — a valid workbook must LOAD); only a label outside the verified set raises. HORS_RMR COMPONENT FLOWS (arrivals): three-way resolution recorded at probe P5/P6 — (i) the compo workbook's own hors-RMR row if present; else (ii) province compo minus all RMR rows, reconciliation-checked; else (iii) HORS_RMR is **EXCLUDED FROM RANKINGS ENTIRELY — no ED is computed for it** (codex r10-F2: a supply-side-only ED would have to feed P_ISQ to native formation, omit a demand term, or invent arrivals — each contradicts a stated contract); the run emits a run-level exclusion record naming the unresolved input, and the rankings cover the remaining members — never a partial ED, never an unstated default. | RA14/15/16 rows carry `ra_proxy` (exact RA data used as couronne/periphery proxies — ranking members, never balance participants, never emitted in ScenarioPrior); Laval is exact (RA13 ≡ ville); couronne-nord precision is DEFERRED to v1 (§11.6: a find enables v1, never v0). MRC-level ISQ projection workbooks EXIST — the 2026-07-21 'no MRC workbook (404)' finding was a METHOD ARTIFACT: HEAD 404s where GET 200s on ISQ's descriptive-French slugs, and the original probe's guessed slugs also 404 on GET, so absence was a property of slug + verb, never the data (P6 probe + independent steering re-verification, 2026-07-28; discovery path = sitemap.xml, 3,273 xlsx locs). v1 is PARKED behind two recorded residuals: the RA↔MRC axis is EDITION-SPECIFIC (present in A2021, absent from the 2025 scenarios workbook), and membership-vs-partition of RA14/15/16 vs the RMR couronne is not yet computed |
| Age | ISQ `Années d'âge` sheet — **verified: TWO-ROW header (sheet rows 7–8) mixing grouped-age (0-19, 20-64, …), single-year `Âge` block (0..100+), Âge moyen/médian, and a `100+` terminal column — **AMENDED 2026-08-07 (steering ruling I): `100+` occurs exactly ONCE per sheet in the committed edition (measured across all three pop workbooks by two independent probes); the duplicate-name hazard is CROSS-SHEET (`Groupes d'âge` carries its own `100+` column), not within-sheet — the 2026-07-21 junction note mis-scoped it** | CPM table integer ages | Loader selects the single-year block by header-GROUP context (`Âge`), never by bare column name (cross-sheet duplicates + future-edition drift); `100+` → capped at CPM table max (≥100 verified live — skeleton q₁₀₀ returned); grouped-age columns ignored. **Terminal-bucket semantics (codex r5-F6): 100+ is an ABSORBING age bucket** — each year its stock = surviving prior 100+ stock (table-max hazards) + surviving age-99 age-ins; never overwritten or reinitialized; three-year fixture reconciles mass with each decrement applied once |
| Sex | ISQ numeric sex codes — **verified: {1.0, 2.0, 3.0}, NOT M/F labels** | actuarial-system `gender` strings | Explicit code→gender map, TRIPLE-checked (codex r2-F5 — additivity alone is swap-symmetric and cannot orient male vs female while mortality is sex-specific): (1) additivity code-3 ≈ code-1 + code-2 per geography×year×scenario (raise if not); (2) semantics pinned from the ISQ metadata at probe time (recorded observation); (3) ORIENTATION guard — at ages 85+, the female-mapped code's population must exceed the male-mapped code's in every geography×year (the universal old-age female survival advantage; raise on violation = swapped map). Code 3 is VALIDATION-ONLY, never enters modeling (exclusion tested). Any other code → raise |
| Scenario | ISQ `Référence (A2026)/Faible (D2026)/Fort (E2026)` | `{reference, low, high}` | Explicit map at load; missing any of the three for a geography×year → raise |
| Year | ISQ `Année` + `Statut` (est/proj) | int calendar year | `Statut` is revision status, NOT scenario (skeleton friction #3); est vs proj recorded in vintage |
| Ownership rate | Census CMA cross-tab (MTL CMA ≡ MTL_RMR; QC CMA ≡ QC_RMR) | cohort engine propensities | CMA↔RMR treated as identical geography (same StatCan delineation); RA-level rows reuse their parent CMA rate with `borrowed_prior`; **HORS_RMR has its OWN named source (codex r1-F8, corrected r4-F2): the residual is Québec-province tenure×age NET of ALL Québec CMAs — not merely MTL+QC (the other RMRs are neither MTL/QC nor hors-RMR); probe §11 item 2 pulls province + every QC CMA the table carries, or the table's own non-CMA/CA aggregate row if published; `borrowed_prior`-flagged if only coarser geography is available** — a strict full-geography join must find a rate for every MODELED enum member or raise |

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
- **Codex-fold fixtures (round 1 F1/F3/F4/F6 + round 2 F1–F5)**: persons→households initialization
  — all-coupled fixture (100+100, 60% → 60 Couple / 0 Solo / 0 Other) AND the general-case fixture
  (200 persons, 0.25/0.80 → 50 Solo + 60 Couple + 30 Other, persons reconcile 200); competing-risk
  partition (0.20/0.08/0.72, sums to 1); dimensional headship test (100 arrivals as 50 couples vs
  100 singles → DIFFERENT D); hand-worked ED fixture (unique value, estate-lag boundary crossing) +
  ranking fixture (unique ordering, exact tie, scenario crossing); sex-code orientation guard RED
  (swapped 1↔2 map must raise on the 85+ female-excess check) + code-3 exclusion test; couple
  matching fixtures (codex r3-F1 + r4-F1): coupled 100 vs 80 → exactly 80 Couple + 20 excess→Other
  (never 90 averaged); 20 vs 100 → CalibrationError (balance breach at 0.8); 0 vs 0 → 0 Couple, no
  error, no division; post-match per-sex conservation asserted in all three; tripwire completeness + value-integrity REDs (empty registry, missing required
  indicator vs the CODE-owned set, duplicate key, NaN/±Inf/non-numeric current value, future
  as_of, inverted band → nonzero, never exit 0); Tranche 2 adds one RED fixture per ScenarioPrior integrity rule (missing row, duplicate
  key, NaN, inverted band, negative tilt, unknown enum, value-bearing/unknown flag string). The
  double-decrement mutation test rides the cohort-engine build task.
- **Loader pins**: recorded sha256 fixtures; schema-drift fixture (mutated sheet) MUST raise; the
  fail-loud claims get their adversarial pass from stress-tester at PR time (load-bearing-claim tag).
- **Contract tests**: ranking same-vintage refusal; import-direction tests (demoflow⊥hde both
  ways). Tranche 2 adds: ScenarioPrior field allowlist; `never_relax_stress` on every tilt<1.0 row;
  mapping_version bump enforcement.
- **Golden artifacts (Tranche 1)**: one committed rankings output + one tripwire-baseline output
  from the committed data vintage (JSON, diffable). Tranche 2 adds the golden ScenarioPrior.
- **Basis guard tests (codex F7 — two directions, both explicit):** (a) normal path: a fresh
  interpreter entry point that sets the Québec basis SUCCEEDS (the US default before set is
  expected, not an error); (b) guard path: with `set_active_mortality` stubbed to a no-op so
  `active_mortality()` returns the US basis, `BasisError` is raised and `get_qx` is never called —
  verified under `python -O` too (the guard must survive assertion-stripping).

## 11. Plan Task-1 probes (execution-hardening; run at plan execution, not spec time)

1. demoflow env stands up: uv project + path dep on actuarial-system; `get_qx` fires cross-env with
   the QC basis (in-repo proven; cross-env install mechanical but unproven).
2. StatCan WDS table-API pull of 98-10-0231-01 — MTL + QC CMAs AND the Québec-province total AND
   every other QC CMA the table carries (or its non-CMA/CA aggregate row if published): the
   HORS_RMR rate derives as province-net-of-ALL-CMAs (codex r1-F8 + r4-F2 — netting only MTL+QC
   wrongly folds the five other RMRs into hors-RMR). CA caveat (codex r5-F7): a published
   "non-CMA/CA" row EXCLUDES Census Agglomerations while province-minus-CMAs INCLUDES them — use
   the published row only if it reconciles exactly against the computed residual (numerators AND
   denominators); otherwise compute the residual and record which geography HORS_RMR actually
   denotes in the probe note.
3. Census living-arrangement cross-tab hunt — SEX-SPECIFIC rates required (living-alone AND
   couple shares by age × sex; the r3-F1/r4-F1 matching depends on both). Fallbacks are
   PER-INPUT (codex r4-F6 — the living-alone fallback cannot supply couple_share): living-alone →
   vitrine 28% + widened band per-sex; couple_share → pinned at probe time from the Census
   province-level profile with citation (recorded observation). If neither the cross-tab nor a
   citable couple_share exists, initialization RAISES (LoaderError) — couple_share has no
   invented default.
4. Census immigrant vs non-immigrant homeownership by CMA (the Tranche-1 coarse-netting
   differential — Census-covered for Québec, unlike CHSP).
5. IRCC PR-by-CMA CSV download + schema record.
5b. Temporary-resident STOCK source (codex F5): StatCan NPR estimates (17-10-0121-01 family) vs
   IRCC temporary-resident tables — pick one, record schema + cadence; until wired the tripwire
   reports UNKNOWN, never a stale within-band.
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
`never_relax_stress` contract enforcement (rides the emitter). **Named contract DEBTS the sketch
session inherits (codex r10-F3 — the emitter is not functionally determined without them):** the
ED-trajectory → horizon_year-row aggregation rule (endpoint vs period-mean — pinned with a
distinguishing fixture), and the ED → drawdown_weight_tilt mapping (currently unspecified; the β
rule determines drift only).
**v1+:** MRC-level couronne split (pending source); plex demand compute + supply stock from rôle
CUBF (2A mod 2 — operator may pull forward with a named decision it informs); StatCan paid custom
tabulation (CT-level immigrant tenure); >2051 horizon tail (only QC-total reaches 2071 — any
extension is a named extrapolation); actuarial-system multiple-decrement combinator (charter
extension, operator sign-off); tripwire scheduling/cron.
**CUT (not deferred):** parquet mirror (revisit only at columnar scale); `weak_identification`
flag (dies with the v0 plex compute).
**REJECTED (not deferred):** forecaster-lite.
