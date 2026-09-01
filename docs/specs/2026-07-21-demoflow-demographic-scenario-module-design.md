# demoflow — Demographic Housing-Flow Scenario Module — Design

**Date:** 2026-07-21
**Status:** Approved design (operator 2026-07-21); elegance-gate 2A+2B folded (both
PROCEED-WITH-MODIFICATIONS, 2026-07-21 — 2B re-sequenced to rankings-first tranches with the
ScenarioPrior emitter deferred behind an S4b input-slot sketch; 2A subtractive mods folded: parquet
mirror cut, plex compute deferred to v1, CLI folded to run+tripwires, flat error classes,
enum→string serialization stated); 2C cross-CONTEXT arm WAIVED by operator 2026-07-21 (the session ran on a top-tier model;
residual gap recorded: the arm's catch mechanism is independent context + hunt-NEW framing,
not model tier — same-family folded-spec defects go unhunted by that arm; codex cross-FAMILY arm ran
regardless, per doctrine the waiver never reaches it); spec pending operator review
**Scope:** personal decision tooling — nothing here places trades or moves money
**load-bearing-claim:** yes (stress-tester) — "fail-loud loaders, no silent fallback" and
"schema-enforced output prohibition" are load-bearing correctness claims; stress-tester fires at
PR time regardless.
**QUALIFIED BY AMENDMENT #25(B), 2026-08-23 — "schema-enforced output prohibition" OVERSTATES what a
schema can do, and §7 already said so.** Field allowlists, finite checks, closed string enums and
band ordering bind **VOCABULARY AND SHAPE, never numeric PROVENANCE**. An unconditional crash
probability can be computed and placed in an allowed numeric field — `drawdown_weight_tilt` is the
named candidate — while satisfying every stated schema invariant. §7 records this as its own
epistemic limit (codex r10-F1: *"field allowlists bind VOCABULARY, not value semantics — no schema
proves a number in an allowed field was derived conditionally"*), so this header and §7 disagreed
about the same guarantee, and the header is the one a reader meets first. **Read it as: the schema
forbids the VOCABULARY of an unconditional forecast — there is no field to put a `crash_probability`
in and no free string to smuggle one through — while conditionality of a number inside an allowed
field rests on the single derivation path and the version-stamped mapping, not on the schema.**
The field this bites is TRANCHE-2 and unbuilt, so nothing shipped is affected; it is corrected here
because the Tranche-2 author will read this header as a guarantee it was never able to give.

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
enforced structurally: the output schema cannot express the forbidden quantities'
VOCABULARY (§7) — per the #25(B) qualification above, allowlists bind vocabulary and SHAPE, never
numeric PROVENANCE, and a contract
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
- **actuarial dependency:** uv path dependency on an external actuarial package (a private
  checkout two levels up from the `demoflow/` project directory, declared in its own
  `pyproject.toml`; codex r6-F7 caught the §2/§3 contradiction; showcase
  runs need both repos checked out side by side, accepted at the operator fork 2026-07-21). Import surface pinned to
  `mcp_server.engine.mortality` public functions only: `set_active_mortality`, `active_mortality`,
  `get_qx`. No private reach-ins. Dependency weight (fastmcp/cvxpy/osqp ride along) accepted —
  local batch tool.
- **Basis contract:** the mortality engine DEFAULTS to the US
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
  pyproject.toml            # own uv project; path dep on the external actuarial package
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
mortality still retains ≈0.25, inside [0.20, 0.40] — FIGURE CORRECTED by ruling O 2026-08-08: measured on the spec-pinned cohort, a doubled decrement retains 0.3900 at the LOW q_live end and 0.2293 at the HIGH end, so ≈0.25 belongs to the HIGH end; the envelope's blindness to a doubled decrement is confirmed and WIDER than the original figure claimed):** applying the CPM decrement twice must change
the hand-computed oracle values (exact inequality against the pinned expectations); the envelope
remains a coarse gross-error backstop only. **RULING O (steering amendment #6, 2026-08-08): the reconciliation gate binds the CENTRAL-ASSUMPTION run ONLY — sweep legs never re-run check_reconciliation.** The band's Myers anchor is central-only, and binding every leg makes the spec self-contradictory: measured at q_live = 0.06 (the sweep grid's own low endpoint), the spec-pinned cohort retains 0.4565 (gate RAISES on the CORRECT model) while a doubled decrement retains 0.3724 (gate PASSES) — inverted at 21/21 start years. The sweep's product is rank stability; the central run's gate is the calibration check (binds the Task-29 orchestrator). **Named omission (codex r3-F2, deliberate
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
basis — **and "the same CPM basis" means MORTALITY ONLY, which amendment #12 states here because the
omission is load-bearing on BOTH sides of this identity.** Interprovincial out-migration is not
modeled: if real, the surviving-cohort term is too large, P_resident is too small, and native D is
understated. The same unnamed assumption runs the other way in §6's demand chain, whose immigrant
rate is measured on survivors AND stayers (persons present in Québec in 2021 who arrived before 2016)
while its operand is a GROSS arrival flow — applying one to the other implies 100% retention and
OVERSTATES the credit. The two errors partially offset with different magnitudes, and
`assert_p_resident_nonneg` (r7-F3) only trips on a full-cell contradiction, so it is a coarse
detector rather than a size check. No retention number is asserted. **What would settle it:** a Québec
immigrant-retention rate by years-since-landing (IRCC IMDB longitudinal, or MIFI présence-au-Québec).
The mortality leg this clause originally stated stands unchanged
(mortality once — their post-arrival deaths are ours, their pre-arrival dynamics are the flow's). **Operand binding (codex r6-F1 — the identity alone cannot catch a mis-wired consumer,
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
**RE-POINTED BY AMENDMENT #23(B), 2026-08-23 — the sentence above was a FALSE COVERAGE CLAIM and is
read from here forward as follows.** The assertion runs on the (geography, scenario, year) TOTAL,
which is the granularity its operand exists at; the per-CELL property holds BY COMPOSITION, not by a
per-cell assertion. A per-age assertion is not representable in Tranche 1 at all — the arrivals
operand is a per-YEAR flow carrying no age index — so the original wording named a check that could
not be written, not one that was skipped.

**Tranche 1 (core) — COARSE netting, dimensionally explicit (codex r2-F2):** ISQ component
arrival flows are PERSON-denominated; ownership propensities are HOUSEHOLD-maintainer-denominated —
persons never multiply a household rate directly. The chain is: arrivals(persons) × immigrant
headship rate (households formed per person — Census immigrant household size / maintainer rate,
probe §11) → immigrant HOUSEHOLDS → × the immigrant ownership propensity, DEFINED (codex r4-F5 — a bare "differential"
is ambiguous between relative multiplier and absolute probability): `p_imm(a) = p_nonimm(a) ×
ratio`, where `ratio` = the **Census immigrant/non-immigrant ownership RATIO at CMA level**
(banded), `p_nonimm(a)` is the resident-base Census propensity already loaded, and the resulting
`p_imm` is asserted ∈ [0,1] → immigrant owner-household demand.
**CORRECTED BY AMENDMENT #24(A), 2026-08-23 — `p_nonimm(a)` AS LOADED IS NOT A NON-IMMIGRANT RATE.**
The cube it is read from carries NO immigrant dimension at all, so its denominator is ALL
maintainers — immigrants, non-immigrants AND non-permanent residents. Multiplying that by a ratio
whose own denominator IS non-immigrant-only does not recover immigrant ownership. Read the definition
above with #24(A)'s conversion applied; the operand's universe is stated there rather than assumed
here.

**RULINGS P / Q / R / S / T — the immigrant inputs, RESOLVED (steering amendments #7 through #14;
operator-ruled 2026-08-13 and 2026-08-14).** The paragraph above named two source premises that did
not survive being hit live. **RULING S is the operative one: BOTH immigrant inputs now come from a
single cube, StatCan 98-10-0621-01, with ZERO geography and ZERO metric transport.** The lineage is
kept short on purpose — P ruled the ratio's READING (eventual, not arrival-window); Q re-pointed the
ratio's source when a second probe reached a cube the first could not; R ruled headship absent; S
supersedes Q's values and REVERSES R's absence on a third measurement. What follows is the resolved
present, not a history.

**RULING S (amendment #9, operator-ruled 2026-08-14) — the values that bind.** Source:
**StatCan 98-10-0621-01**, "Population groups by housing suitability and condition of dwelling"
(2021 Census, released 2023-10-04, CURRENT), `Before 2016` member of its `Population
characteristics` dimension — the SAME member for both quantities, because under I2's whole-residency
argument a ratio and a headship drawn from two different immigrant-member definitions would mix two
cohort definitions inside one product. Seat-verified live against the WDS coordinates:

| geography | immigrant HEADSHIP (maintainers ÷ persons) | ownership RATIO (owner-maintainer propensity ÷ non-immigrant) |
|---|---|---|
| MTL_RMR | **0.5259** | **0.9634** |
| QC_RMR | **0.5054** | **0.8910** |
| HORS_RMR | **0.5234** | **1.0248** | ← SUPERSEDED BY AMENDMENT #13; the ruling-S values were 0.5169 / 0.9600

**THE TABLE CARRIES THE RULED VALUES, AND THAT IS A RULE, NOT A COURTESY (amendment #14,
2026-08-18).** HORS_RMR's row above was 0.5169 / 0.9600 under ruling S and is now the
operand-aligned pair amendment #13 rules; the suppression envelope is 0.5225-0.5236 / 1.0228-1.0264
and the superseded construction is described in #13(A). **Amendment #13 originally stated that
supersession in PROSE and left this row untouched, which left the locked spec carrying two
contradicting statements about the same ruled quantity for three days — and, worse, made the
supersession INVISIBLE to the gates.** `_guard_s6_rows` / `_guard_rows_match_spec` key on these
TABLE ROWS, so the §6 → P8 → join-table coupling that exists to stop a moved value landing quietly
could not see the move: the seat's own run-26 premise "the coupling is RED right now" was measured
FALSE by the implementer, because both the note and the join table still agreed with a table row
nobody had changed.

**AND THE COUPLING IS WEAKER THAN THAT DIAGNOSIS IMPLIED — measured by the seat at this amendment,
by mutation.** Setting this row to garbage (0.9999 / 7.7777) DOES red exactly one gate, so the
coupling is not decorative. But swapping the row between the two LEGITIMATE pairs — ruled
0.5234 / 1.0248 against superseded 0.5169 / 0.9600 — reds NOTHING, in either direction, because the
note carries both pairs and the gate is satisfied by PRESENCE in the note rather than by identity
with the RULED pair. So the machinery can catch a typo and cannot catch a supersession, which is the
one thing an amendment does. **This is recorded as an OPEN DEFECT with a named owner: the gate must
bind this row to the note's DECISION-token pair specifically, and a swap between the ruled and
superseded pairs must RED in both directions.** Until that lands, this table's correctness rests on
the seat updating it, not on anything that fails. **STANDING RULE, binding on every future amendment: an amendment that moves a
RULED VALUE must update this table in the same commit. Prose alone is not a supersession the
machinery can see, and the other four rows are bound by exactly the same gates — a prose-only
amendment moving MTL_RMR, QC_RMR, RA06 or RA13 would be invisible in exactly the same way.**

**AMENDMENT #19 (2026-08-21, seat-verified by execution) — AMENDMENT #14's OPEN DEFECT IS CLOSED, AND
IT WAS CLOSED MORE BROADLY THAN #14 ASKED. The paragraph above is retired as a live claim and kept as
the record of what was wrong.** #14 required that "the gate must bind this row to the note's
DECISION-token pair specifically, and a swap between the ruled and superseded pairs must RED in both
directions". That landed: `probes/run_p8.py::_guard_s6_ruled_columns` reads each ruled row's pair from
the table's own HEADSHIP and RATIO **columns by header** — never from the row's prose, which is what
made a row-keyed read unable to tell a ruled pair from a superseded one stated beside it — and
`_guard_ruled_columns_match` asserts identity against the note's published pairs in both directions.
**Generalized to the CLASS rather than the instance**, which #14 explicitly worried about when it
named the other four rows: the gate
`tests/test_probe_p8.py::test_p8_EVERY_ruled_row_reds_on_a_moved_pair_not_only_HORS_RMR`
runs THREE mutants against ALL FIVE ruled rows — the prose-only move onto another
LEGITIMATE pair (the exact evasion #14 measured as reding nothing), the two columns TRADED, and the
garbage pair the old machinery already caught, kept deliberately as a regression leg so strengthening
could not silently cost the case that already worked. Every mutant must refuse at
`boundary == "citation"` and must NAME the row that moved. A companion gate,
`test_p8_the_ruled_column_parser_refuses_what_it_could_not_read`, closes the level-up defect a
strengthened parser invites: no table, no header naming the columns, a header naming one twice, a
ruled cell carrying two figures or none, a row missing — each is a REFUSAL, never a quietly smaller
coupled set. **So the sentence "this table's correctness rests on the seat updating it, not on
anything that fails" is now FALSE, and that is the point of this amendment: a governing document
asserting a defect it no longer has is itself a false claim, and it is the kind that decays quietly
because nothing fails when it goes stale.** #14's STANDING RULE is UNAFFECTED and still binds — an
amendment that moves a ruled value updates this table in the same commit; the machinery now also
fails if it does not. Surfaced by a test-hardening sweep that found the P10 twin of this shape still
open and checked whether the P8 remedy had landed rather than assuming from the spec's text; verified
by the seat by running the gates and reading their mutants, not on the sweep's word.

RA members borrow their parent CMA, `borrowed_prior`. HORS_RMR is the province NET of the six
wholly-QC CMAs NET OF the 16 Québec-side CSDs of the Ottawa-Gatineau CMA (amendment #13's
operand-aligned construction) — computed rather than borrowed
(province-level readings are 0.5236 and 0.8993, and differ from the residual precisely because the
province contains the CMAs).

**Why this source and not the previous two.** `Primary household maintainer` × `Population
characteristics` × `Tenure` at CMA level gives BOTH quantities as COUNTS, in one universe, with
confidence-interval members published alongside. The ratio it yields is the owner-MAINTAINER
propensity — *exactly* the quantity this section defines — so ruling Q's METRIC transport is not
reduced but ELIMINATED. The universe is corroborated three independent ways: Québec total
maintainers = **3,749,035**, the published private-household count already cited in
`loaders/census.py`'s T13b docstring; total persons 8,308,480 against probe P3's independently
measured 8,308,475 private-household persons; and the geography labels here carry no trailing
non-breaking spaces, unlike 43-10-0060's.

**The METRIC direction is now MEASURED, and this supersedes the instruction not to assert it.**
Amendment #8 routed the direction to the Task-26 QFE as unmeasurable-here; it is measurable, and it
runs one way: the person-weighted proxy OVERSTATES the maintainer-denominated ratio at every
geography — MTL 0.9682 → 0.9634 (−0.5%), QC_RMR 0.9223 → 0.8910 (−3.4%), province 0.9219 → 0.8993.
Small at Montréal, not at Québec. **The Task-26 QFE carry therefore NARROWS to adequacy review of
the ruled inputs — it is no longer a direction-measurement task.**

**What the earlier sources become.** 43-10-0060-01 is retained as the SIBLING CROSS-CHECK, not
deleted — as a COARSE consistency check across two named axes, never a like-for-like agreement: its
0.9682 and this ruling's 0.9634 differ in BOTH the member cut (>10 years vs ≥5 years) and the metric
(person-weighted share vs maintainer propensity), so their closeness at Montréal bounds the combined
size of those two differences and asserts nothing stronger. P4's three 46-28-0001 anchors likewise STAY — `SWEEP_GRID` sources
the [0.155, 1.033] span from them, and the sweep span is UNCHANGED under this ruling. The layering
is explicit: **measured (98-10-0621) > sibling-measured (43-10-0060) > borrowed (P4)**.

**RULING T (amendment #10, operator-ruled 2026-08-14) — RA06 and RA13 are MEASURED, not borrowed.**
The catalogue-closure sweep (P9) found **StatCan 98-10-0622-01**, the census-division/subdivision
sibling of the ruled cube: dimension list identical name for name, and the Québec province rows
**BIT-IDENTICAL** across both cubes — persons 1,007,855, maintainers 527,710, owner-maintainers
298,100, giving 0.5236 and 0.8993 in each, seat-verified live. This is ONE universe at two geography
grains, not a second source. Two modeled geographies are exact 1:1 matches to its census divisions
and take their own measured values on the same `Before 2016` member:

| geography | census division | immigrant HEADSHIP | ownership RATIO |
|---|---|---|---|
| MTL_ISLAND_RA06 | `Montréal` (id 1732, geoLevel 3) | **0.5555** | **1.0757** |
| LAVAL_RA13 | `Laval` (id 1730, geoLevel 3) | **0.4816** | **1.1112** |

**GATE — quantified, never eyeballed; CONSTRUCTION CORRECTED BY AMENDMENT #11.** Each 1:1 claim is
verified by a population comparison against the ISQ RA workbook for the same geography (both 2021
vintage), with the delta REPORTED; above threshold it is a SEAT_QUESTION, not a footnote (the
Gatineau territory precedent at T13). A match that passes is flagged **`cited`, NOT
`borrowed_prior`** — a measured value at a verified-coincident territory is not a borrowing.

**Amendment #11 (2026-08-14) — the gate's ESTIMATOR, after the literal construction was REFUTED BY
ITS OWN CONTROL.** As first written this gate compared 98-10-0622-01's population against the ISQ RA
total — a PRIVATE-HOUSEHOLD count against a TOTAL-POPULATION estimate. Measured, it trips at both
RAs (−2.804%, −2.482%) **and at the Québec PROVINCE control (−3.074%), where territory identity is
not in question.** A gate that fires where the answer is known is measuring the universe gap, not
the territory; that gap is already recorded in this tree at `loaders/constants.py:139` ("8,308,475
private-household persons vs 8,501,833 published"), and 98-10-0622-01 publishes no
total-population statistic to compare against. The construction is therefore REFUSED and replaced:

- **The gate is the PROVINCE-CONTROLLED SHARE RESIDUAL** — each geography's share of its own
  source's provincial total, census against ISQ, so the universe offset cancels by construction
  rather than being argued away. Measured: RA06 **+0.279%**, RA13 **+0.611%**. Only the two sources
  ruling T already names are used; no additional cube enters the GATE.
- **The threshold is DERIVED, not inherited.** The 1% of the original wording was calibrated against
  the refuted construction's semantics and does not transfer. It is set from innocent controls
  measured in the same construction — the six wholly-QC CMAs, whose ISQ populations
  (`pop-as-rmr-base.xlsx`) and census CMA rows describe territories whose identity is not in
  question — as the maximum innocent residual plus a stated margin, published in the P8 note beside
  the RA residuals. A threshold with a measured basis is the point; an inherited figure would be a
  hand-typed number one level up, which is the class this section keeps closing.
- **Code axes are RECORDED, and deliberately do NOT carry the gate.** Both sides publish codes, but
  in different systems: ISQ keys its rows on région-administrative codes 0-17 (Montréal 6, Laval 13,
  "découpage géographique des régions administratives au 1ᵉʳ juillet 2025"), while the census
  publishes SGC classification codes (CD Montréal 2466, CD Laval 2465, the CSD Laval 2465005
  correctly avoided). The SGC codes agreeing across 98-10-0622-01 and 98-10-0007-01 establishes that
  two CENSUS cubes mean the same census division — it does not establish that the division equals
  the ISQ région administrative, and no correspondence between the two code systems exists in this
  tree. So the population residual carries the gate and the code agreement is corroboration.
- Census TOTAL population (98-10-0007-01: RA06 −0.576%, RA13 −0.482%, province −0.819%) is retained
  as a SECOND DIAGNOSTIC in the note — a like-for-like universe check that also passes — but it is
  not the gate, because admitting a cube ruling T never named in order to repair a gate is scope
  creep with no discriminating power the controlled residual lacks.

Lineage, recorded because a wrong why outdamages a missing one: the "quantified population
comparison" wording was advisor-recommended, seat-ruled into amendment #10 without checking that the
two sides shared a universe, and refuted by the probe that tried to execute it.

**THE RATIO EXCEEDS 1 AT BOTH, and that is COMPOSITION, not contradiction.** On the island the
NON-immigrant base is renter-heavy — its owner-maintainer propensity is only 0.4210 — so immigrants
out-own LOCALLY while still under-owning CMA-wide at 0.9634. Both readings are true at their own
scale, and the finer grain is the reason the CMA figure could not show it. **This is NOT the pooled-
ratio anti-pattern** recorded in `loaders/constants.py`: that one pools ACROSS RECENCY and defeats
the netting by construction, while this is a properly decomposed settled-member reading at a finer
geography. The [0,1] assertion on the product is untouched — at Laval 0.6546 × 1.1112 = 0.727.

**NESTING IS ACCEPTED AND STATED, not to be discovered later as a calibration finding.** With
RA06/RA13 at census-division grain and MTL_RMR at CMA grain, the parts no longer reconcile to the
whole. That is deliberate: the rankings compare geographies, each carried at its best available
measurement, and invariants I1 and I2 are indifferent to it — I1 counts mortality once PER
GEOGRAPHY, I2 binds P_resident PER GEOGRAPHY, and neither asserts that modeled geographies
aggregate. A reviewer meeting this must read it as ruled, not as drift.

**Deliberately NOT extended:** RA14/15/16 stay proxies and HORS_RMR stays the computed province-net
residual. Building those from census-division unions needs a CD→RA correspondence that does not
exist in this tree and re-opens P6's edition-specific RA↔MRC axis (a three-state split measured over
15 editions), which is exactly what keeps the couronne build PARKED. Recorded as available, not
used: `98-10-0623-01` (CMA, shelter cost) and `98-10-0624-01` (CD/CSD) carry the same
`Primary household maintainer` × `Population characteristics` cross and would independently
corroborate these quantities.

**RULING R's ABSENCE CLAIM IS REVERSED, and the reason generalizes.** R stated that no free source
crosses immigrant status with household-maintainer status. What reproduces is the MAINTAINER count
(16) and the empty dimension-name intersection; the immigrant-dimension count is selection-rule
dependent and did NOT reproduce (156 under run 16's rule, 175 under run 17's own). The conclusion is
what fails. 98-10-0621-01 crosses them at both modeled CMAs **because it carries
immigrant status as MEMBERS of a `Population characteristics (46)` dimension rather than as a
dimension NAME** — and it sits INSIDE the sweep's own title-selected pool and INSIDE its 16-cube
maintainer set. This is the third instance in this arc of an absence claim being a property of the
SEARCH rather than of the data (ruling F: HEAD-vs-GET and guessed slugs; ruling Q: a product-family
and title-tier scope; ruling S: dimension-name selection). R's named caveat — that a general rate
"plausibly OVERSTATES" immigrant formation — is also refuted for the pooled stock, which measures
HIGHER than the general population (0.4996 vs 0.4364 at MTL), and holds only for recent arrivals.
The standing consequence: **an absence claim in this arc is provisional until the search itself has
been closed at the level the claim is stated at**, and a scoped verdict must name its selection
level, not merely its pool.

**Why the arrival-window reading stays REFUSED, from this section's own equations** (ruling P's
argument, unchanged by S and the reason `Before 2016` rather than `Recent immigrants` is the ruled
member): I2 subtracts the FULL surviving arrival stock from P_resident in every year, while the
demand chain credits each arrival cohort exactly ONCE, in its arrival year. Years 2+ of every cohort
therefore belong to NEITHER channel, and the arrival-year credit necessarily stands in for the
cohort's whole residency — an arrival-window rate would systematically undercount it. The
flow-vs-stock gap this leaves is a MODELING CHOICE, deliberately taken and named here, not an
unnamed transport: the operand is an arrival flow and the ruled member is a settled stock, and the
same cube publishes the recent-arrival readings (headship 0.3604 / 0.3431 / 0.3143; ratio 0.4211 /
0.3679 / 0.4472) so the size of that choice is visible rather than hidden.

**The r5-F4 join, resolved:** MTL_RMR and QC_RMR are DIRECT and CITED for both quantities (this
supersedes amendment #7's empty-direct-tier clause, written when no CMA measurement was known); RA
members borrow the parent CMA, `borrowed_prior`; HORS_RMR is the province-net residual, computed;
an unresolved modeled member still RAISES, and there is still no unstated default. **This also
supersedes the r5-F4 parenthetical BELOW** (at the
full-geography join in section 6, ~300 lines further down — this said "above" when written, which is
why four later sweeps never reached the literal; corrected at its own line per #28) — "(a province-net residual for these cross-tabs is not
cheaply available)" — which ruling S falsifies by computing exactly that residual from published
counts, subtracting the six wholly-QC CMAs from the province in one query batch. The sweep span
stays **[0.155, 1.033] UNCHANGED** — robustness is never narrowed on the strength of a new cube —
and P4's three 46-28-0001 anchors (year-1 0.210, year-3 0.614, year-5 0.911) STAY as documented
constants: `SWEEP_GRID` sources that very span from
`CONSTANTS["immigrant_ownership_ratio_sweep_span"]`, so culling them would break the sweep's own
source.

**FLOOR GATE, retained from ruling R and still free — but it is a CROSS-CUBE gate and must be wired
as one.** 98-10-0621-01 carries no living-alone indicator; the shares come from the sibling cube
**43-10-0060-01, indicator 8**, and the member must match the ruled one rather than the pooled
stock: the SETTLED living-alone shares are **0.154 MTL and 0.164 QC_RMR** (the pooled all-immigrant
figures 0.134/0.127 that ruling R named belong to a different member and are the looser floor). Use
the settled shares — nearer in definition and stricter as a bound. Immigrant headship must EXCEED
them, since each person living alone maintains exactly one household; the ruled values clear with
room (0.5259, 0.5054). A value below the floor is a defect, not a datum.

**AMENDMENT #12 (2026-08-15, QFE-measured at the Task-26 fold) — three corrections to this block,
none of which reopens the ruled source or member.**

**(A) HORS_RMR's immigrant values are SUPERSEDED PENDING RECOMPUTE, on an OPERAND-ALIGNMENT defect.**
The ruled table's HORS_RMR headship 0.5169 and ratio 0.9600 are measured over a census residual that
INCLUDES the Québec side of Ottawa-Gatineau, while the flows they multiply come from ISQ's literal
`Territoire hors des RMR` row, which EXCLUDES it — ISQ publishes `RMR d'Ottawa-Gatineau` separately
(*Partie québécoise uniquement*), so the territory is separable on the ISQ side and inseparable on the
census side. The ownership artifact's `isq_territory_note` recorded this mismatch on 2026-08-08 and
deferred it to "the task that joins rate × population"; that task has now run. **The governing
principle, ruled here: the rate's territory must match the flow's territory.** The recorded
12.99%/14.93% person-weights UNDERSTATE the effect on these two quantities because they are
immigrant-denominated, and CD Gatineau holds **40.42% of the residual's `Before 2016` stock against a
10.35% person weight — 3.9×**. Net of CD Gatineau the values measure 0.5218 (+0.95%) and **1.0320
(+7.50%), crossing 1.0**: shipped, settled immigrants under-own in hors-RMR; aligned, they out-own.
Because headship and ratio MULTIPLY inside D_imm and their errors are same-signed, the immigrant
demand leg is understated ≈7.6-8.5%, ED is understated, and since rank 1 is most-negative HORS_RMR is
ranked MORE RISKY than truth — a single-geography distortion with no order-preservation protection.
The recompute selects its residual construction by matching the ISQ row it aligns to (the ISQ
Gatineau row converts to ≈345,000 private-household persons at this tree's measured universe ratio,
between the CD-Gatineau and CD-Gatineau+Collines+Papineau brackets) and publishes the bracket as
sensitivity. **The ruled SOURCE and MEMBER are untouched; only the territory arithmetic is corrected.**

**(B) HORS_RMR's OWNERSHIP rate is NOT to be "fixed", and the reason must survive.** **[REVERSED BY #13(B)
BELOW: the rate WAS corrected — the cancellation premise measured band-NON-uniform. Read what follows
as the superseded argument it is, never as an instruction. Marker added by #28.]** It carries the
same contamination (+1.49% measured on the analogous all-households propensity) and it is SOUND
anyway, because **a band-uniform relative scaling of the ownership propensity ρ CANCELS EXACTLY in
ED** — verified linear end to end: OwnerStock ∝ ρ, D_native ∝ ρ, D_imm ∝ ρ through `p_nonimm`, and
S ∝ ρ through initialization and roll-forward. Correcting it would be cost with no signal; a future
reader who "fixes" it without this paragraph will not know the cancellation was what kept ED stable.
The residual is second-order and named: `initialize_households` takes a single scalar (the 75+ band)
while OwnerStock spans all bands and D_native spans 25-74, so a BAND-VARYING error does not fully
cancel.

**(C) The flow-vs-stock cost was stated at the wrong SIZE, and cost (i) below is now partly stale.**
The equation multiplies headship × ratio, so the choice's cost is the PRODUCT, not either factor:
settled vs recent is 0.5067/0.1518 at MTL_RMR (**3.34×**), 0.4503/0.1262 at QC_RMR (3.57×),
0.4962/0.1406 at HORS_RMR (3.53×), 0.5976/0.1599 at RA06 (3.74×), 0.5352/0.1518 at RA13 (3.53×) — a
3.3×-3.7× span with the ruled member at its top, which is roughly two orders of magnitude larger than
the netting discount that cost (i) numbers. **Cost (i)'s "~4-11%" is `1 − ratio` and describes
MTL_RMR and QC_RMR ONLY** (**CORRECTED 2026-08-23, amendment #28:** this read "the THREE CMA-grain
members" — #13 crossed HORS_RMR's aligned ratio to **1.0248**, joining RA06 and RA13 as own-ratio
PREMIUMS, so the discount describes TWO members and the three RA proxies inherit MTL_RMR's): under ruling T the RA06 and RA13 ratios exceed 1, so for them it is
not a discount but a PREMIUM of −7.6% and −11.1%. **Containment, recorded as the inheritance it is:**
Task 29's uniform ratio override spans [0.155, 1.033], scaling each immigrant leg to 0.139×-0.174× of
headline — below the recent-equivalent 0.268×-0.300× — so the downside is contained in MAGNITUDE, but
by inheritance from P4's borrowed ROC-CHSP year-1 floor rather than by construction from the measured
recent member, and in a different SHAPE (a uniform override compresses cross-geography differences;
the recent reading moves both factors together). Immigrant HEADSHIP has no sweep axis at all, so a
`rank_stable` verdict is evidence, not proof, on this axis.

**AMENDMENT #13 (2026-08-15) — the recompute #12(A) ordered has LANDED, and #12(B) is REVERSED.**

**(A) HORS_RMR's immigrant values, now MEASURED at exact territory:** headship **0.5234**, ratio
**1.0248** (suppression envelope 0.5225-0.5236 and 1.0228-1.0264). These supersede the
SUPERSEDED-PENDING-RECOMPUTE marks of #12(A). The immigrant demand leg was understated **+8.083%**,
and the ratio CROSSES 1.0 with BOTH envelope ends above it — at aligned territory, settled immigrants
in hors-RMR OUT-own non-immigrants rather than under-owning them.

**The construction is RULED, not preferred, and the fallback #12(A) named is REFUSED.**
98-10-0003-01 publishes the Ottawa-Gatineau CMA (member 594) with its **25 constituent CSDs as
geography children**, closing exactly on the CMA total (1,488,307 = QC 353,293 + ON 1,135,014); **16
are Québec-side**, selected two independent ways — SGC prefix AND census-tree ancestry in
98-10-0622-01 — agreeing on all 25. Four census divisions contribute, three of them PARTIALLY, so no
whole-CD union is this territory. The whole-CD bracket #12(A) ranked second **does not enclose the
exact headship** (0.5234 sits above its own 0.5218-0.5228 range): it would have published a value no
member of its own range produces. Membership gate: QC-part census population 353,293 against ISQ's
355,971 = −0.752%, inside a 1.109% threshold derived from the six wholly-QC CMAs.

**(B) #12(B) IS REVERSED. The ownership rate WAS corrected, and the reason it had to be is that
#12(B)'s clearance was premise-conditional.** That clearance said a band-uniform relative scaling of
ρ cancels exactly in ED — true as stated, and the premise is false. Measured, the contamination is
**not band-uniform**: all-ages +0.918%, **25-54 +1.425%**, 55-64 +0.315%, 65-74 +0.304%, **75+
+0.223%** — spread **1.2024 pp**, all same-signed, and **at the suppression bound it WIDENS to
1.2121 pp**, so the structure holds at both corners rather than as a point estimate. The arrangement
is adversarial by structure, not by chance: the MOST contaminated band (25-54) is the one D_native is
built from, the LEAST (75+) is the one S rides through `initialize_households`, so δ_D − δ_S sits at
or near the full spread. Because ED's numerator is a DIFFERENCE of flows this is amplified rather
than averaged — ΔED/ED = (δ_S − δ_OS) + (δ_D − δ_S)·D/(D−S), measured at +1.0% relative at
D/(D−S)=1.4, +8.4% at 7.7 and +54% at 46 — **unbounded near flow balance, with the multiplier turning
NEGATIVE for D < S so sufficient amplification carries ED across zero rather than rescaling it.**
Rank 1 is most-negative ED, so this lands precisely where rankings are decided; the bounded-absolute
argument that would have let it stand is true and irrelevant, because rankings are relative and
decided near zero, which is exactly where that bound is vacuous.

**AMENDMENT #18 (2026-08-21, operator ruling W + seat rulings X1–X7) — THE OWNERSHIP LATTICE IS SEVEN
BANDS, AND THE TWO CONSUMERS THAT NEEDED A LUMPED AGGREGATE NOW COMPUTE ONE. Every four-band figure
in (B) above is retired as CURRENT and preserved as HISTORY; the structural argument it carries
SURVIVES and is now weight-independent rather than point-estimated.**

**(A) THE LATTICE. Operator ruling W (2026-08-20) split the retired four bands into seven** —
`25-34, 35-44, 45-54, 55-64, 65-74, 75-84, 85+` in `census._AGE_BAND_SPEC`, with
`hors_aligned.CD_BAND_SPEC` tiling the same edges from the CSD cube. **Why it was not cosmetic:** the
retired 30-year `25-54` band made every age in the immigrant leg's cited reasoning range return one
rate, so the pick inside it was inert. Split, the three sub-bands publish materially different rates
(MTL_RMR: 25-34 **0.343547**, 35-44 **0.540707**, 45-54 **0.621581**) and the pick moves the ranked
artifact. **Seven is the FINEST COMMON partition, measured, not designed:** the CMA cube
(98-10-0231-01) publishes five-year members but the CSD cube (98-10-0232-01) publishes ten-year ones,
and `assert_band_lattice` requires the two cubes to tile identical EDGES, so ten-year is the floor a
five-year refinement cannot clear. That claim is now GATED against the CD cube's own age-dimension
member index and its declared member count — a five-year re-pin cannot pass (8/8 mutations RED).
`OWNERSHIP_LATTICE_FLOOR` stays 25: amendment #12's ordering constraint still binds, and ruling W did
not touch it.

**(B′) THE CONTAMINATION FIGURES, RE-MEASURED ON THE SEVEN-BAND LATTICE.** Relative deltas: 25-34
**+3.5591%**, 45-54 **+0.2732%**, 75-84 **+0.2416%**, 85+ **+0.2533%**; spread **3.3175 pp** at the
served corner, **widening to 3.4993 pp** at the suppression bound — so the both-corners structure
(B) relied on holds, an order of magnitude wider than the retired 1.2024 pp. All seven same-signed
positive. **THE ADVERSARIAL ARRANGEMENT SURVIVES, AND AT SERVED VALUES IT IS NOW A BOUND RATHER THAN A
POINT.** `S` reads ownership only at ages ≥ 75, i.e. exactly the two least contaminated bands as
served, and because ruling X1 makes δ_S a convex combination of those two band deltas, δ_S is a
**MEDIANT** confined to [+0.2416%, +0.2533%] for every feasible 75+ mix — strictly below the
next-lowest band (45-54, +0.2732%) irrespective of weighting. The household-weighted instance is
**+0.2441%**. **NAMED LIMIT (seat ruling X6) — that weight-independence is a SERVED-VALUE property and
does NOT survive the suppression envelope.** At its high corner 85+ alone reaches **+0.3845%**, above
45-54, so the ordering stops being weight-free; and the weighting that decides it is neither
households nor population but **pop(a)·ρ(a)** — owner-population — because δ_S weights each band
delta by the owner households it contributes. Measured, 85+'s share of the 75+ block is 21.74% by
households, **24.15% by owner-population**, 26.45% by population, and the corner blend is 0.2726
(households, clearing 45-54 by +0.00054 pp) but **0.2761 by owner-population, EXCEEDING 45-54 by
0.0029 pp** (0.2794 and −0.0062 pp by population). Any future gate on this ordering must use
owner-population weighting; a household-weighted check reports a pass the model does not have.
**#12(B)'s reversal is UNAFFECTED either way** — δ_D ≈ +2.243% against δ_S ≈ +0.244% served and
+0.276% at the corner, so δ_D − δ_S is **1.999 pp** served and **1.967 pp** at corner: large,
same-signed, and 2.0 pp at one decimal either way. #12(B)'s premise is band-UNIFORMITY, and refuting
it needs the difference large, same-signed and adversarially arranged — never maximal. What retires is
only the stronger reading that S rides the two least contaminated bands under any weighting at either
corner. **AND THE QUANTIFIER IN (B) IS CORRECTED (seat ruling X7):** δ_D − δ_S does NOT sit "at or
near the FULL spread" — it is **60%** of the 3.3175 pp served spread. Two notes on that figure, both
of which the record gates rather than assumes. First, δ_D is published as **ΔD/D = +2.243%**, computed
by calling production `native_formation` twice per projected year (aligned curve against census-net)
and pooling over the 26 reference years — that is the δ_D the amplification identity below actually
uses, and its gate calls production code instead of a re-implemented gain loop that could drift. The
alternative aligned-ρ-weighted construction reads +2.2646%; the two differ by weighting BASE, not by
error, and both refute the superlative (60.25% and 60.90%). Second, the fraction is stated at WHOLE
percent deliberately: at one decimal it flips between δ_S's household (60.3%) and owner-population
(60.2%) readings, which this same amendment rules immaterial, and a knife-edge figure is precisely the
drift class ruling X5 exists to close. **A correction the seat owes its own text:** the δ_S figure
+0.244111% quoted upstream is the HOUSEHOLD-weighted blend — the weighting X6 above rules wrong for
this quantity. Owner-population gives **+0.244392%**; both render +0.244%, and the record gates that
they still do, so the single published figure is licensed rather than assumed. The amplification
identity
ΔED/ED = (δ_S − δ_OS) + (δ_D − δ_S)·D/(D−S) is unchanged, and the "unbounded near flow balance,
multiplier negative for D < S" conclusion stands on a wider spread. **Two prose corrections to (B):**
the most-contaminated band is now `25-34`, and it is the most heavily WEIGHTED of the five bands
`D_native` reads (18 ≤ a < 75 spans five), not the only one; and `S` no longer "rides through
`initialize_households`" at a single band at all — see (C).

**(C) SEAT RULING X — THE UNIFYING PRINCIPLE, and it is the whole of X.** Refining a lattice
correctly serves every consumer that reads ownership PER AGE. It BREAKS every consumer that needed an
AGGREGATE OVER A LUMPED AGE RANGE, because the coarse band that used to supply that aggregate no
longer exists and a point read inside the range silently becomes a sub-band read. **Re-pointing such a
consumer at a sub-band is a model change wearing a lattice refinement's clothes.** An exhaustive
enumeration — grep of every reader call site, PLUS runtime instrumentation of **every** leg × geography
× scenario evaluation of a golden run, PLUS the `initialize_households` bottleneck audit — closes at
**exactly four** rate consumers, of which two were lumped:
*(CORRECTED AT ITS OWN LINE BY AMENDMENT #30 — the retracted words, quoted: this line said
"**exactly three** rate consumers, of which two were lumped", and the parenthetical below said
"The ENUMERATION — three consumers". Rulings X1 and X2 each added a lumped consumer to the list
this sentence introduces, and neither edited the count — #28's diagnosed habit, one more
instance, caught by codex round 16. The rest stands: the count is deliberately not written
here. It was measured as 288 on the TWELVE-leg grid this
paragraph was written against; amendment #20(D) added a seventh axis, so a golden run is now 336
evaluations, and a figure derived from the grid goes stale every time the grid widens. The
ENUMERATION — four consumers, the list below — is what this paragraph asserts, and it is
grid-independent.)*
- `pipeline`'s per-age dict over `range(25, 101)`, feeding `native_formation` and `owner_stock` —
  age-resolved, CORRECT, and it is what GAINS from ruling W;
- `_band_entry_stock` at age 75 exactly — a genuine single-age read, CORRECT;
- `_standing_stock` over the whole 75+ bucket — LUMPED, repaired by **X1**;
- the immigrant leg's `p_nonimm` over 25-54 — LUMPED, repaired by **X2**.

**(D) X2 RESTORES ITS CONSUMER EXACTLY. X1 DELIBERATELY DOES NOT, AND THAT ASYMMETRY IS THE POINT.**
Ruling W had silently moved `p_nonimm` from the retired band's household-weighted union **0.511996**
to `35-44` alone, **0.540707** — an undeclared +2.87 pp shift already baked into an artifact. X2
computes the aggregate BY CONSTRUCTION (owner counts and total counts summed over the three
sub-bands, THEN divided — never a mean of the three rates, which reads 0.501945, **−1.005 pp**, and is
now a gated negative): MTL_RMR **0.511996**, QC_RMR **0.577577**, HORS_RMR **0.690149** from the
ALIGNED cube's own band counts, five borrowers taking MTL_RMR's. That is the retired value to the
digit, so on this axis ruling W is restored to a pure refinement. **X2 also DISSOLVES a sweep-axis
fork rather than parameterizing it:** no discrete age pick survives, so `MODEL_CHOICES ∩ SWEEP_GRID =
∅` needs no amendment. `MODEL_CHOICES` carries `p_nonimm_range: (25, 54)` — the SPAN, kept inside
`assumptions_hash` rather than removed, because removing it would leave an uncovered literal. What
remains UNCITED is now a band, not a point inside a band: a strictly smaller exposure.

**X1 is a small, DECLARED, MEASURED model change on S — NOT a restoration, and the earlier claim that
it "restores the aggregate" is RETRACTED.** `_standing_stock` now applies the POPULATION-weighted mean
of the per-age rates over the ages present in its slice (ages 75–100, one call per geography ×
scenario at the base year), where before it multiplied the entire bucket by one rate read at
`ROLL_AGE`. The retired flat band supplied the HOUSEHOLD-weighted union, and the population-weighted
mean is not that number: it sits **−0.162 pp (MTL_RMR), −0.636 pp (QC_RMR), −0.361 pp (HORS_RMR)**
below it at the three geographies with their own census territory — at QC_RMR a quarter of the
2.593 pp defect being repaired — while the five borrowers STRADDLE it, each weighting the shared curve
by its own age composition. **RULED population-weighted, for four reasons, the fourth decisive:**
(i) vintage consistency — the weights come from the same ISQ base-year population frame that supplies
the stock being valued, whereas census-2021 household counts are a different quantity from a different
vintage; (ii) it uses the model's own data rather than importing an external weighting; (iii) it
DIFFERENTIATES the five borrowing geographies, breaking a lockstep artifact that had pinned six rows
to one rate and thereby manufactured apparent rank robustness; (iv) the COUPLE bucket has no per-age
decomposition under aggregate matching, so **no weight aggregates it exactly** — exactness is
unavailable in principle, which is why "restores" is the wrong word for ANY choice here. The residual
is declared, not hidden. Tranche 2's age-indexed 75+ lattice is what removes the need for a weight.

**NAMED LIMIT — the fix a reader will reach for is WRONG, and it is wrong by more than the fix.**
Reading per-age and summing `_household_stock` (the shape `balance/owner_stock.py` uses) would move
MTL_RMR's ED by **+6.32e-05** against X1's own **+4.28e-05** — **1.5× the repair** — because it also
changes couple matching and living arrangement. `match_couples` is a min-pairing and
Σ_a min(m_a, f_a) ≤ min(Σm, Σf) — a theorem, tight only where one sex dominates at every age, and the
crossover to male-binding is confined to the top single years (earliest age 95; age 98 at MTL_RMR) —
so per-age summation forces spouses to be the SAME AGE and discards age-discordant couples into the
EXCLUDED `Other` bucket. Decomposed two ways, because the denominator decides the number: against the
FULL per-age split, min-pairing is **1.3–8.9%** of the gap and the LIVING-ARRANGEMENT band re-read
**73.9–100.3%** (85+ female `couple_share` 0.401 against 75-84's 0.730; couple stock −18.7% from the
la re-read, a further −0.149% from matching); within the la-LUMPED family, where ownership is the only
channel open, min-pairing carries **0.88–0.98**. Both readings reject the arm. **Living-arrangement
rates stay read at `ROLL_AGE`** — pre-existing lumping, out of ruling W's scope, and not to be
"fixed" in passing.

**(E) THE RANKED OUTPUT, and one retraction a future reader must not reconcile against.** Ruling W +
X together: three geographies cross into NEGATIVE mean reference ED where the pre-W artifact had all
eight positive, and the order changes; ranks are then STABLE across both X repairs (0/8 rows move
under either), so the ranking claim is robust to them while the LEVELS are not — `p_nonimm` alone is a
first-order magnitude driver (−66% at MTL_RMR). Ratified values, agreed to ≤4.1e-15 by **four**
independent implementations (the build, an independent golden regeneration in a separate isolated
tree, a from-scratch reimplementation of §5/§6 with its own CSV parser, and a fourth orchestrator
importing no `pipeline`/`golden`/`output` module): LANAUDIERE_RA14_PROXY **−0.001132104126** (1),
LAURENTIDES_RA15_PROXY **−0.000877041660** (2), LAVAL_RA13 **−0.000507703667** (3), HORS_RMR
**+0.000165772596** (4), MTL_RMR **+0.000189088495** (5), MONTEREGIE_RA16_PROXY **+0.000411424174**
(6), QC_RMR **+0.003373308961** (7), MTL_ISLAND_RA06 **+0.004331603441** (8); `assumptions_hash`
**fe7c631104c5182b**, `rank_stable: false` on every row. **THESE ARE
THIS MINT'S VALUES AND HASH, NOT THE STANDING OUTPUT (scope added by #28, 2026-08-23):** three later
re-mints — #20(D), #22(C), #24(A) — have since moved every level and the hash, and the #27 event-time
fix moves them again. The current record is the test-bound CURRENT-STATE span of
`demoflow/artifacts/README.md`. **RETRACTED:** an earlier seat measurement
published a table differing from these by up to 8.98e-06 (0.79% at rank 1). Its cause is recorded so
the class is recognisable — the measuring harness patched the shared reader keyed on `(geography,
age)`, and since `p_nonimm` and the per-age dict BOTH asked age 40, the patch contaminated the
age-resolved consumer with the lumped aggregate: **the very error ruling X exists to prevent,
committed inside the measurement of ruling X.** A probe that patches a shared reader cannot
distinguish two consumers that ask the same question with the same arguments. The build's refusal to
re-mint against an unratified number is what kept it out of the artifact.

**(F) BOTH REPAIRS ARE GATED GOLDEN-INDEPENDENTLY, which is the property that makes this amendment
checkable.** A gate that only fires through `test_golden.py` is not a gate, because `gen_golden.py`
re-ratifies whatever the code emits. Demonstrated: for each of three reverts — `_standing_stock` back
to a point read, `p_nonimm` back to a point read spelled arithmetically to evade a literal grep, and
`p_nonimm` as the forbidden rate-mean — the golden was RE-MINTED UNDER THE MUTANT (so `test_golden.py`
went GREEN, exhibiting the self-ratification) and the suite still went RED elsewhere, at named tests.
Ten further respellings — weight-by-households, read-the-union-then-discard-it, arithmetic
midpoint off the pre-built dict, wrong-territory bypass at both construction and consumption, and
deletion of the routing prune — all fail to ship green. The absence claim is a property of that
search: thirteen behavioural mutants in total, not exhaustive over all edits.

**How the corrected curve lands, and one thing that must NOT be done to it.** The aligned curve
(`loaders/hors_aligned.py`, artifact `data/ownership_hors_aligned.json`, extract
`data/hors_aligned_csd_98100232.json` from 98-10-0232-01) sits BESIDE the shipped curve with the join
explicit, re-pointing **HORS_RMR ONLY** — proven, not asserted: re-deriving the shipped artifact after
the refactor moves zero geography × band values. **`load_ownership_rates` is NOT re-pointed**, because
the committed T13b external-anchor gates pin HORS_RMR's SHIPPED residual at `rel=1e-12`; re-pointing
would red ruled gates. A future reader who "simplifies" the two curves into one must move those gates
first, deliberately.

**(C) Two figures in #12(A) were the SEAT's own errors, corrected by the probe that executed it:**
the "10.35% person weight" is the MAINTAINER weight (10.336%) — the person weight is 10.770%; and the
"≈345,000" conversion measures 347,875 at the recorded province ratio against the **347,710**
private-household persons the resolved membership actually carries (local universe ratio 0.9842 vs
province-wide 0.9773).

**LINEAGE, recorded because this block is the clearest specimen of how this document gets things
right:** the QFE NAMED the band-varying caveat and graded it second-order; P10 MEASURED it and found
the adversarial arrangement; the ruling followed the measurement, not the grade. A clearance that
rests on an unmeasured premise is a hypothesis wearing a verdict's clothes.

**Costs, recorded rather than argued away:** (i) at the ruled settled reading the netting discount
is ~4-11% for MTL_RMR and QC_RMR ONLY (#28 — see #12(C) as corrected for the members it no longer
describes; the pre-flag at #12(C) was never discharged at this figure) — this section's "the netting IS the showcase's originality claim" holds STRUCTURALLY but
is materially small, and is to be stated at that size and never louder (the stress-relaxation ban's
sibling: a result is never promoted past what it measures). The large newcomer effect is real but
lives in the RECENCY COMPOSITION the same cube measures, which is Tranche 2's years-since-landing
S-curve, not v0. (ii) The credit is timing-biased EARLY, a whole cohort's formation landing in its
arrival year — also Tranche 2's fix, not a v0 defect to patch. (iii) Immigrant headship measures
HIGHER than the general population for the settled stock (0.5259 vs 0.4364 at MTL), so the
immigrant channel contributes more household formation per person than a general-rate model would
have credited — the direction is now measured rather than assumed either way.

**Binds Task 25b:** no uncited literals — the plan's 0.62/0.70/0.66 and 0.42/0.45/0.43 are all OUT,
superseded by the ruling-S table. The plan's `resolve_immigrant_inputs(MTL_RMR).flag is None`
assertion is RE-RULED: under S both MTL quantities are direct and CITED, so that member's flag IS
None — but `ImmigrantInputs` still needs PER-FIELD provenance, because RA members and HORS_RMR carry
different provenance per field (a borrowed parent-CMA value beside a computed residual), and one
flag cannot describe a pair honestly.

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
`borrowed_prior`; HORS_RMR: the province-net residual, COMPUTED (**CORRECTED
2026-08-23, amendment #28:** this read "province-level value, `borrowed_prior` (a province-net
residual for these cross-tabs is not cheaply available)" — ruling S both supersedes that resolution
and FALSIFIES the parenthetical, computing exactly that residual from published counts); every modeled member must resolve or the run raises —
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
    #   ^ NAME IS STALE, VALUE IS NOT (amendment #26(A)): the quantity is a yr⁻¹ RATE, not a
    #     fraction. TRANCHE-2 and unbuilt, so the emitter may still be named honestly — a
    #     Tranche-2 author renaming it to `excess_demand_rate` is RULED IN ADVANCE and needs no
    #     further amendment; keeping the stale name requires a unit note at the field.
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
ORIGIN: `demo_drift = β × ED`, where **ED carries units of yr⁻¹** (amendment #12 established this and
**AMENDMENT #26(A), 2026-08-23, edits THIS LINE, which had gone on saying "the dimensionless
fraction of §7" for fourteen review rounds after the correction landed 30 lines below it — the THIRD
instance in this document of a retraction that never edited its own sentence, and the one that names
the pattern as a habit rather than an accident**) and β is **DIMENSIONLESS**, converting to DECIMAL
real drift per year per unit ED — worked fixture: `ED = 0.01, β = 2.0 → demo_drift = 0.02
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
unbounded fraction, and never leave "near-zero" to implementation taste. **ED is SCALE-INVARIANT but
NOT dimensionless — amendment #12 corrects the label, not the equation.** D and S are annual FLOWS
(households/yr) over a stock LEVEL (households), so ED composes as **yr⁻¹**, a net turnover rate. It
is invariant to geography size, which is the property the rankings need, and no numeric error
followed from the old wording because §7's β is stated as drift per year per unit ED and absorbs the
yr⁻¹ either way — but "dimensionless" was a gloss beside a correct number, which is the class this
document keeps closing. A hand-worked fixture (§10) pins one unique ED value from the spec alone,
including a delayed estate listing crossing a horizon boundary.

**The r9-F5 guard is a STRUCTURAL FLOOR, not a plausibility check (amendment #12).** Measured across
the full frame — 744 cells, 8 geographies × 3 scenarios × 31 years — OwnerStock runs 99,692.3 to
1,189,439.0, so 1,000 sits exactly 100× below any real value. It correctly bounds arithmetic
pathology in a function that takes a bare float and cannot be geography-aware, and its zero detection
power in the 1k-99k gap costs nothing because those defects (a truncated age lattice, a wrong
scenario slice, a partly-built curve) are already refused upstream by `owner_stock`'s absent-rate
raises and its nonneg-finite assertion. Do NOT read "no modeled geography legitimately carries fewer"
as calibration — calibrated to this frame it would be ~50,000. A geography-aware plausibility band
belongs at Task 29, where geography identity exists.

**NAMED LIMIT — the sub-floor convention's cost on BOTH sides of ED (amendment #12, QFE-measured).**
Ages below the Census ownership lattice floor contribute zero to OwnerStock AND their formation terms
are zeroed in D_native. The QFE priced both legs in ED's own unit and the numerator leg DOMINATES by
roughly 30×–200× (additive 0.195-0.337% of OwnerStock against the denominator's multiplicative
0.96-1.65%); the two are equal only at |ED| ≈ 19-21%/yr, against an ISQ-implied stock movement of
0.10-0.63%/yr. **Direction: for ED < 0 — the decline regime this module exists to measure — BOTH legs
push PESSIMISTIC.** Any statement that the convention makes ED optimistic is priced on the smaller leg
alone and is sign-wrong where it matters. The denominator leg's near-uniformity does NOT transfer to
the numerator: an additive non-uniform shift can reorder where a multiplicative near-uniform one
cannot. Tripwires have ZERO exposure — no §7(c) indicator consumes OwnerStock or ED. And the premise
under all of this is itself false: the committed extract DOES publish owner-maintainer counts below
25 (Québec 20-24: 17,170 owners of 106,605 households), so the floor is a choice in
`census._AGE_BAND_SPEC`, not the data's silence — the fourth instance in this arc of an absence claim
that was a property of the search, and the first inside our own code. **ORDERING CONSTRAINT, binding
on any fix:** the convention is currently the only thing suppressing the age-20 band-entry artifact in
D_native (21,353 households, 100% of computed D_native being band-entry mass), so extending the
ownership curve below 25 BEFORE an age-resolved headship curve lands would multiply that artifact into
demand instead of zeroing it. **Age-resolved headship first, then the floor.**
**SATISFIED — DISCHARGED BY AMENDMENT #23(D), 2026-08-23.** The age-resolved curve LANDED under
operator ruling V (2026-08-19, seat runs 34/35): `data/headship_by_age.json`, read by
`demand/formation.py` and `balance/owner_stock.py`, with `headship_shape` a declared central AND
sweep axis. The ordering constraint above is discharged; `OWNERSHIP_LATTICE_FLOOR` stays 25 per
amendment #18(A), which is now a SEPARATE decision rather than a blocked one. This note exists
because the paragraph read as an OPEN precondition for four days after the thing it waited on
shipped, and a future reader would have re-derived a constraint that was already met.

**AMENDMENT #20 (2026-08-22, round-3 audit gates; seat-verified) — TWO NAMED LIMITS ON THE RANKING'S
ROBUSTNESS, AND FOUR AUTHORIZATIONS. The ranked artifact's ORDER is sound as computed and its
ROBUSTNESS CLAIM IS NARROWER THAN `rank_stable` IMPLIES; both limits below reorder ranks under
defensible alternative constructions that the declared sweep structurally cannot reach.** Neither is a
computation error: the eight published values were reproduced bit-identically by four independent
implementations, and no rank is decided inside numerical noise — forward, reversed, sorted, `fsum` and
exact rational summation all give the same rank vector, worst deviation from exact arithmetic 3.17e-19.

**SCOPE OF EVERY MEASURED FIGURE IN (A) AND (B) BELOW — added by amendment #28, 2026-08-23.** They were
measured on the PRE-#24(A) ED grid: the ranked spread was then 5.464e-03 and the exact-arithmetic noise
3.17e-19, the two figures quoted immediately above. #24(A) re-based every level, and the #27 event-time
correction re-bases them again. The instruments' DEFINITIONS and the limits' EXISTENCE are unchanged and
are what this amendment is authority for; the CURRENT deltas, sign counts, reorder pairs and
rank-reliance verdict live in the test-bound `<!-- NAMED-LIMITS -->` span of
`demoflow/artifacts/README.md`, re-derived at every mint. **Do not take rank-reliance guidance from the
figures below** — as re-measured at #24(A) they had already INVERTED against the shipped page.

**(A) NAMED LIMIT — ED's NUMERATOR AND DENOMINATOR ESTIMATE THE SAME 75+ OWNER-HOUSEHOLD BLOCK ON TWO
BASES THAT DISAGREE BY ROUGHLY 1.5×, AND NOTHING IN THE MODULE MEASURES OR BOUNDS IT.** S is generated
by a CLOSED-COHORT roll-forward — base-year standing stock plus age-75 entrants, decremented at
`q_live`, never re-anchored to a later population. The ED DENOMINATOR re-estimates the same block every
year as `Σ_{a≥75} pop(a,t)·headship(a)·ownership(a)`, a cross-section. SEAT-MEASURED, the rolled/static
ratio at MTL_RMR runs **0.9505 at the 2021 BASE year — the roll's initial condition, which is OUTSIDE
the ranking domain — 0.8088 at 2026, the domain's FIRST year, and 0.6472 at 2051**. It falls at all
eight geographies across the 26-year domain, and **NOT monotonically**: strictly monotone at exactly ONE
(MTL_ISLAND_RA06), the other seven dipping and recovering inside a large net fall. The cross-geography
spread of the ratio runs **7.4 pp (2036) to 11.1 pp (2051), 12.2 pp at the base year** — a level AND an
ordering effect, not a wash. The round-3 gate reported this as "monotone" with a "7.6 pp" spread; both
are retired here as unreproduced — the fall is real and the spread is LARGER than the gate's figure.
**The load-bearing part is a contradiction internal to this tree, and the seat verified it directly
rather than on the gate's word:** the denominator's own base-year curves imply a `headship·ownership`
decline over 75→85 of `(0.52730×0.53069)/(0.64892×0.57227) = 0.7535`, i.e. **2.79 %/yr**, while the
engine decrements the same households at `q_live = 8.5 %/yr` — a **3.05×** disagreement. Run that
implied retention through the module's own calibration gate and it sits **ABOVE** `check_reconciliation`'s
band `(0.20, 0.40)`, while the engine's retention on the spec-pinned cohort is **0.3571**, inside it.
**Each half of the ED quotient would fail the other half's calibration check.** SIZING INSTRUMENT, and
it is NAMED because a sensitivity number is meaningless without the perturbation that produced it: the
seat RE-ANCHORS the rolled 75+ stock to that year's cross-section estimate before each roll — carrying S
on the denominator's basis, explicitly violating I1, a MEASUREMENT and never a proposed construction.
Measured: mean reference ED moves by **−3.46e-03 … −5.12e-03** per row — of the order of the ENTIRE
published ranked spread of **5.464e-03** — **FOUR of eight rows change sign**, and the ordering moves
**HORS_RMR 4→6 with MONTEREGIE_RA16_PROXY 6→4**. The gate's own re-basing reported a narrower delta band
(−4.05e-03 … −5.03e-03) and SIX sign changes; that instrument was not stated, the seat could not
reproduce it, and only the seat's reproduced figures are published here. The REORDER is identical under
both, which is the part the named limit rests on.
**Why `rank_stable: false` does not price this:** `q_live` moves the hazard INSIDE the closed cohort; no
declared axis moves the BASIS. The sweep is honest about what it varied and silent about this.
**Held as a NAMED LIMIT rather than repaired, deliberately.** The two quantities are not literally
identical — the cross-section embeds cohort effects and the 75+ net migration this module omits, and
institutionalisation properly rides `headship(a)`, which does fall (0.649 at 75 → 0.527 at 85 → 0.457 at
100). So the finding is *"two internal constructions of one quantity disagree by ~1.5× and nothing
bounds it"*, NOT *"S is wrong"*. Closing it means either re-anchoring the roll-forward to each year's
population or making the denominator cohort-consistent, and both are Tranche-2-scale changes to the
supply model that would move every published number. **Tranche 1 ships the reading with the disagreement
DECLARED and SIZED. Any consumer reading LEVELS rather than ORDER must be handed this paragraph — which
makes `artifacts/README.md` carrying EVERY named limit (two at this amendment; #24(A)
added a THIRD, and the README gate binds all three — #28) a Tranche-1-blocking obligation of this
amendment, not a courtesy: a limit declared only in a spec the consumer never opens is undeclared.**

**(B) NAMED LIMIT — SPEC §6's I2 IDENTITY IS STATED PER-AGE, IMPLEMENTED AT THE TOTAL, AND ALLOCATED
UNIFORMLY; ITS GATE COMPARES ONLY SUMS AND SO ADMITS ANY ALLOCATION.** §6 requires
`P_resident(t) = P_ISQ(t) − Σ_c SurvivingArrivalCohort_c(t)` **per (age, geography, scenario, year)**.
The implementation nets at the total and applies one uniform multiplicative scale to all 101 ages;
`assert_i2_identity` compares `sum(resident_t.values())` against the total, which is satisfied by every
allocation. The netting is not small and it grows: at LANAUDIERE_RA14_PROXY the scale runs 0.99776
(2026) → **0.94198 (2051)**, and the DEEPEST-netted row is MTL_ISLAND_RA06 at 0.98818 → **0.78037**,
because the surviving-arrival stock carries every cohort landed since 2025 forward. Between **24.7 %
and 31.8 %** of that charge — measured at all eight geographies at both endpoints — lands on ages
(0-16, 75-100) that NEITHER leg of the `native_formation` sum reads, while `immigrant_formation` credits
100 % of `arrivals(t−1)`.
SIZING INSTRUMENT, seat-built INSIDE this tree so that it needs no source this tree does not have:
charge the ENTIRE netting to the ages that actually carry DEMAND WEIGHT, population-proportional within
that range, leaving every other age unnetted — satisfying the identical I2 sum the shipped uniform scale
satisfies. **THE CHARGE BAND IS 25-74, AND ESTABLISHING WHICH BAND IS THE EXTREME WAS ITSELF A
MEASUREMENT, NOT A READING OF THE CODE.** `native_formation` iterates `AGE_MIN=18 … AGE_BOUNDARY−1=74`,
but `_ownership` RETURNS 0.0 below `OWNERSHIP_LATTICE_FLOOR=25` (the documented sub-floor convention),
so every gain at 18-24 is multiplied by zero; age 24 carries weight ONLY through `a=25`'s prior-cohort
term. Charging 17-74 or 18-74 therefore DILUTES the netting across ages that cannot convert it into
demand, and both understate: measured, 17-74 gives −3.83e-04 … −9.89e-04 and 18-74 gives
−3.99e-04 … −1.03e-03, both reordering MTL_RMR 5→6 / MONTEREGIE 6→5.
**At the true band 25-74 the effect is roughly DOUBLE and the reorder is DIFFERENT: −9.04e-04 …
−1.912e-03 per row, span 2.1×, THREE rows change sign, and the ordering moves HORS_RMR 4→6 with
MONTEREGIE_RA16_PROXY 6→4** — that pair AS MEASURED PRE-#24(A). **The clause
"ranks 1, 2, 3, 5, 7 and 8 hold" that stood here is RETRACTED (amendment #28, 2026-08-23): the #24(A)
re-basing INVERTED it — rows this clause named as HOLDING are, on the shipped grid, among those a
consumer must NOT rely on, and a rank it omitted is among the few that DO. No reliance verdict is
restated here on purpose: it is read from the test-bound NAMED-LIMITS span of the consumer page, which
is re-derived at every mint, and never from this line.** **That is the SAME reorder limit (A)'s
independent instrument produces**, from a different perturbation on a different leg, which is the
strongest single fact in this amendment: ranks 4-6 are the ranking's soft middle under both limits.
Across all three bands, without exception and with no row where it is conservative, **the shipped
uniform allocation is biased UP (LESS risky) at ALL EIGHT rows** — direction, not magnitude, is the
durable finding. The 17-74 figures this amendment published at its landing commit are RETIRED here
rather than deleted, because the dilution is the evidence: a charge band chosen from what the loop ITERATES rather than from what the
arithmetic WEIGHTS understates by a factor of two, and this amendment made that error before measuring
its way out of it.
**HOW LARGE THE NETTING IS, stated because the sensitivity is otherwise unanchored:** at
MTL_ISLAND_RA06 / high / 2051 the surviving-arrival stock being netted out is **3.19× the ENTIRE 18-24
population** — the sub-floor band cannot absorb it even in principle, and an instrument that tried
REFUSED — and **44.4 % of the whole 25-74 population**. This is not a rounding-scale adjustment being
allocated; it is a large mass whose age placement is unconstrained by anything in the module.
**The gate's larger figure is NOT published, and why is the point:** it measured against a cohort-aged
per-age arrival profile (four reorders, six sign flips, a 12× span) that is the auditor's and not this
tree's — `MODEL_CHOICE_PROVENANCE["p_nonimm_range"]` records verbatim that no source here carries a PR
arrival age distribution, which is precisely why the uniform scale is forced, and precisely why the seat
could not reproduce that instrument. **So the numbers above are a SENSITIVITY BOUND, not a truth claim,
and the defect is not the uniform allocation itself but that it was undocumented at its site, ungated
beyond a sum, and undeclared as a robustness axis while reordering the published ranking.**
Tranche 1 declares it here and states the choice at the site. Closing it requires an arrival age
distribution this tree does not have — acquiring one is Tranche-2 work, and until then a per-age
allocation would be a fabricated profile dressed as a measurement, which this module refuses on
principle. **RIDER, bounded and unmeasured:** §6 says the arrival cohorts survive forward on the CPM
basis, MORTALITY ONLY; the implementation applies NO mortality (declared "coarse by design"). Direction:
the subtraction is too large → `P_resident` too small → `D_native` understated → geographies read MORE
risky, differentially where immigration is heaviest. At a 26-year maximum cohort age on a working-age
profile this is order-of-magnitude below the allocation effect.

**(C) AUTHORIZED, because §7 closes the envelope and each of these needs a declared position.** §7's
`{schema, schema_version, data_vintage, assumptions_hash}` is hereby widened by exactly three optional
members (**CORRECTED BY #22(B), 2026-08-23: three optional members BESIDE the required `exclusions`,
which had already shipped unauthorized — "exactly three" was FALSE when written**), and `output/artifacts.py`'s refusal on an undeclared position is otherwise UNCHANGED:
  1. **`data_vintage.source_hashes[*].committed_sha256`, OPTIONAL, populated only for sources whose
     `publishes` is the RAW ANCHOR.** Measured: 11 of 12 file-backed keys hash to their committed file
     and `census_tenure_age_98100231.csv` publishes the raw upstream member's digest per §7's own
     `sha256-of-raw-response` definition — two semantics under one field name, undisclosed, and since
     ruling X2 that extract supplies `p_nonimm`, a rate the model multiplies once per leg × geography ×
     scenario — **336 times on the seven-axis grid this amendment's own ruling (D) created; the "288"
     written here at amendment #20's landing commit was the TWELVE-leg arithmetic, measured stale by the round-4 gate and
     corrected in place. It understated the exposure this item exists to close, so the ruling stands
     unchanged and its ground is firmer than stated.** The
     vintage INVARIANT holds (all three routes by which those bytes can change either REFUSE or move the
     envelope, verified by execution); what a consumer lost is VERIFIABILITY. The committed digest is
     ALREADY COMPUTED AND ALREADY PIN-CHECKED — `_source_hashes` takes it, hands it to `_verify_pinned`,
     and then at `pipeline.py:415` `published = raw_anchor(name) if source.publishes == _RAW_ANCHOR else
     digest` drops it for exactly the one key whose consumers most need it. Emitting it costs an
     assignment; what it buys is the declared position.
  2. **A per-leg `rows_moved` map in the rankings envelope.** The per-leg sweep table currently exists in
     three unpinned prose copies which the module's own README declares "a dated reading", and this
     module has already had that table go stale once. `_rank_stability` already builds `legs` and
     `orders`; emitting the count converts a self-declared drift residual into a computed field and
     DELETES prose rather than adding machinery.
  0. **`schema_version` DOES NOT BUMP for these three.** All three are OPTIONAL members: a consumer
     written against the current version reads every emitted document unchanged, and a bump would
     invalidate pinned consumers to announce fields they may ignore. The version bumps when a REQUIRED
     member is added, removed, or changes meaning — the raw-anchor semantics of `sha256` are UNCHANGED
     here, which is why item 1 ADDS a field rather than redefining that one.
  3. **A per-run pairing token in BOTH documents** (or a sibling manifest carrying both documents'
     digests). Emission ATOMICITY is closed — a second-write failure leaves both files unchanged — but
     DETECTION is not: a failure between the two `os.replace` calls leaves a mismatched pair on disk
     whose `assumptions_hash` and `data_vintage` are IDENTICAL, so no consumer can refuse it. The run
     already computes `_run_identity` over assumptions AND source bytes and emits it nowhere. "POSIX has
     no atomic multi-file rename" bounds atomicity; it does not bound detection, and the residual must
     stop being recorded as an unclosable ceiling.
     **RULED, because emitting `_run_identity` AS IT STANDS WOULD NOT CLOSE THIS.** Its payload is
     verbatim `{"assumptions": assumptions_hash(), "sources": _source_hashes(data_dir, ircc)}` — it does
     NOT cover `now_year`/`now_month`. Two runs identical in every input but the clock produce an
     identical `assumptions_hash`, an identical `data_vintage`, an identical `_run_identity` and
     DIFFERENT `tripwire_baseline.json` bytes, because `now` is the freshness axis: that pair is exactly
     the mismatched pair this item exists to detect, and the bare token cannot see it. The emitted token
     MUST be deterministic over (assumption selection, source bytes, **`now`**). **SUPERSEDED BY
     #22(C)/(E), 2026-08-23:** the token is deterministic over both documents' canonical PAYLOAD
     digests, and `now` is deliberately NOT in it — #22(E) measured it content-invisible on these
     bytes and guarded it with a direct pin on the golden clock instead. An implementer following the
     MUST above rebuilds the exact token #22(C) retired. The nonce prohibition stands unchanged. A random nonce is
     forbidden on the same argument the goldens rest on — it would move the emitted bytes on every run
     and destroy byte-stability under a pinned `now`; the deterministic token stays stable exactly when
     the inputs including the clock are.

**(D) RULED — `collective_share_75plus` BECOMES A DECLARED ROBUSTNESS AXIS, and the `CONSTANTS` registry
enters `assumptions_hash`.** It is read into every 75+ stock slice, carries a declared band `(0.02,
0.08)`, has no sweep leg, and moving it to its OWN BAND HIGH — an in-band edit needing no new citation —
reorders the published ranking (HORS_RMR 4→5, MTL_RMR 5→4). **MEASURED AT the forbid-casing hardening commit, BEFORE THE
IDENTITY-ENVELOPE WIDENING THIS AMENDMENT ALSO RULES: at those bytes `assumptions_hash` and
`data_vintage` stayed byte-identical across the reorder.** The tense matters and is deliberate — the
widening half lands with this amendment's code, so the invisibility is a DATED FINDING and not a
standing property, and a reader who finds the hash moving has found the fix, not a contradiction. The
regression that keeps it fixed is therefore part of the ruling: **post-widening, moving this anchor MUST
move `assumptions_hash`**, asserted directly and not through the golden (a golden regenerated from the
emitting code re-ratifies whatever it emits). By `MODEL_CHOICES`' own membership rule — a discrete pick with a measured,
admissible alternative is a sweep axis — it qualifies, and `rank_stable` presently attests robustness
over a grid that never varied a ±2× axis which alone reorders. The aggravating fact is that the plan
SCHEDULES that edit ("the executor updates `collective_share_75plus` when P3 lands a firmer figure",
quoted in `constants.py`'s own header) and `test_collective_share_is_fraction_and_refinable` asserts
only `0.0 <= value <= 1.0` — **not even the anchor's OWN declared band**, so it would not red on a move
to 0.5 — while four sibling anchors pin exact values (0.36; (0.26,0.31); (0.20,0.40); 0.28 WITH its
band; 45000). The one anchor left unpinned is the one that reorders the ranking invisibly. Verified at
the seat: at 0.08 the order becomes HORS_RMR 5 / MTL_RMR 4 with `assumptions_hash` UNCHANGED at
`fe7c631104c5182b`; at the band LOW 0.02 the order HOLDS, so the axis is one-sided and the high
endpoint is the one that must be swept. **BOTH HALVES ARE
TRANCHE-1-BLOCKING and neither is optional:** the registry joins the `assumptions_hash` payload, and the
anchor joins the declared sweep. They need not be one COMMIT — the hash half rides the identity-envelope
widening already in flight, the sweep half is its own change — but a Tranche-1 PR carrying one without
the other ships a token that moves for the anchor beside a `rank_stable` computed over a grid that still
never varied it, which is a worse state than either half alone.

**AMENDMENT #21 (2026-08-22, escalated by run 49's fix agent, seat-verified before ruling) — THE
TRIPWIRE DOCUMENT PUBLISHES ITS BANDS AND WITHHOLDS ITS DECLARATIONS, WHICH LEAVES THE HASH-LEDGER'S
OWN EXCLUSION ARGUMENT UNSOUND. `freshness_years` AND `source_kind` ARE AUTHORIZED AS OPTIONAL PER-ROW
MEMBERS OF `tripwire_baseline.json`.**

Run 49 widened `assumptions_hash` to the whole `CONSTANTS` registry and, in doing so, had to rule on
four other unhashed selections. Two of them are tripwire ledgers and both were ruled OUT, on ONE
argument: what the output PUBLISHES per row does not need the token, because *"a move announces itself
in the diff"* — the token exists for selections the output does not show. That argument is correct, and
it holds for `pipeline.TRIPWIRE_BANDS`, whose every endpoint is emitted as `band_low`/`band_high` in the
row it governs. **It does NOT hold for `pipeline._TRIPWIRE_DECLARATIONS`, and the seat verified the
asymmetry rather than taking it on report:** `TRIPWIRE_RECORD_REQUIRED` is exactly
`{indicator, current_value, source, as_of, band_low, band_high, status}` plus optional `reason` — the
eight keys the shipped artifact carries — while `TripwireSpec` holds `freshness_years` and `source_kind`
under a comment that states the gap verbatim at the field: *"coverage declaration (wired/operator) —
internal, NOT emitted"*. **So one ledger is excluded from the token because it is published, and the
other is excluded alongside it while being published nowhere. The exclusion of the second rests on
nothing.** That is not a future defect; the JUSTIFICATION IS WRONG TODAY, and an unsound reason left
standing in the code is the class this module keeps re-finding.

**THE HOLE THE UNSOUNDNESS LEAVES, and it is real but not yet reachable.** `freshness_years` is the
freshness axis' declaration: move it and a landed indicator's emitted `status` can flip — STALE to
FRESH, or a band verdict to `UNKNOWN` — while `assumptions_hash` and `data_vintage` stay byte-identical,
because neither token covers it and no emitted field shows it. **Measured, it is unreachable on these
bytes:** all six declared indicators ship `status=UNKNOWN` with `current_value=null` (three
`source_unavailable`, three `operator_input_missing`), so no freshness comparison is evaluated at all.
The reachability condition is therefore precise and worth stating because it names WHO trips it: **the
first indicator whose source is wired makes this live.** That is S4b / Tranche-2 work, and a Tranche-2
author wiring a source will not read a limit buried in a Tranche-1 spec — which is the argument for
closing it now rather than declaring it.

**RULED — PUBLISH, DO NOT HASH.** The coherent closes are exactly two: publish the declaration in the
row it governs, or fold `_TRIPWIRE_DECLARATIONS` into the hash payload. **Hashing is REFUSED**, on the
argument the run already made for `TRIPWIRE_BANDS` and on `_run_identity`'s own: BOTH emitted documents
carry the SAME `assumptions_hash`, so hashing a tripwire-only declaration would re-mint the RANKINGS'
identity for a verification-gate ruling that cannot move a single ED — one token moving for two causes
answers neither. Publishing closes it in the document that owns it, costs the rankings' identity
nothing, and makes the hash-ledger's exclusion argument TRUE for both ledgers instead of one.

**WHAT IS AUTHORIZED, and nothing beyond it.** §7's tripwire row gains `freshness_years` and
`source_kind` as OPTIONAL members. `source_kind` serializes as its declared string, never as the enum
repr. `schema_version` DOES NOT BUMP, on amendment #20(C0)'s ruling and for its reason: both are
optional, so a consumer pinned to the current version reads every emitted document unchanged. The
fields ship INERT in Tranche 1 — six UNKNOWN rows — and that is the point: the declaration becomes
checkable BEFORE the work that makes it load-bearing, not after. `TRIPWIRE_RECORD_REQUIRED` stays a
closed set and the emitter's refusal on an undeclared position is UNCHANGED; the two new members join
the OPTIONAL set, and a test must hold that the published values equal `_TRIPWIRE_DECLARATIONS`' own —
asserted directly, never through the golden, which re-ratifies whatever the emitter emits.

**NOT AUTHORIZED, and named so the boundary is not read as an invitation:** no new tripwire indicator,
no change to any band, no wiring of any indicator source, and no change to the `UNKNOWN`-on-missing-input
behaviour. This amendment publishes two declarations that already exist. It does not make a single
tripwire fire.

**AMENDMENT #22 (2026-08-23, codex cross-family round 11 on the amended bytes; every item verified
by an independent adversarial pass that was told to REFUTE it) — ONE FALSE COVERAGE CLAIM RETRACTED,
ONE SHIPPED MEMBER RETROACTIVELY AUTHORIZED, AND THE PAIRING TOKEN'S PAYLOAD RE-SPECIFIED.**

Round 11 was owed: amendments #20 and #21 landed after the loop closed at r10, so the recorded
`reviewed_sha256` was stale against these bytes. It returned four HIGH findings; four verifiers ran
each finding's own falsifiable check (two of them against the LIVE call site rather than a
reconstructed cohort). Two confirmed, two downgraded to restatements of limits already declared here.
The two downgrades are recorded below without amending anything, because a finding that restates a
published limit changes no obligation — but the reasons are worth keeping, since both arrived as HIGH.

**(A) RETRACTED — §10's double-count RED names a gate that CANNOT raise it.** §10 Testing requires
*"a config that double-counts mortality MUST raise CalibrationError (reconciliation gate test)"*. §5
measures the opposite and RULING O narrows it further: on the spec-pinned cohort a doubled decrement
retains **0.3900 at the low q_live end, 0.3001 central, 0.2293 high**, against a gate band of
[0.20, 0.40] — and ruling O confines the gate to the CENTRAL-ASSUMPTION run alone, which is precisely
where 0.3001 sits mid-band. The live path returns `None`. `tests/test_reconciliation_gate.py` says so
in writing: it *"never asserts that the band detects a double-count"*. **So §10 asserted a RED test
that cannot exist, and no amendment had re-pointed it.** This is NOT the same thing as §5's disclosure
that the envelope cannot prove exactly-once — that disclosure is accurate and stays. A disclosed
limitation and a false coverage claim are different defects, and this document carried both about the
same gate.
**RULED: the double-count RED belongs to the ORACLE-EXACT mutation test, not the reconciliation gate.**
§10's bullet is read, from this amendment forward, as: a config that double-counts mortality MUST fail
the oracle-exact roll-forward mutation test; the reconciliation gate's [0.20, 0.40] band catches GROSS
double-counting only and is not a proof of exactly-once. The q∉[0,1] half of that bullet is unaffected.
I1's exactly-once guarantee was never resting on the band — §5:248-250 already said so — which is why
this retraction removes a false claim and weakens no invariant.

**(B) RETROACTIVELY AUTHORIZED — `exclusions`, and #20(C)'s "exactly three" was FALSE WHEN WRITTEN.**
The HORS_RMR terminal branch (§8, case (iii)) mandates *"a run-level exclusion record naming the
unresolved input"*. That record had **no schema home in this document**: `exclusions` and
`unresolved_input` appear ZERO times in it. Meanwhile the implementation already ships `exclusions` as
a **REQUIRED root member** of the rankings document with a closed two-field row schema, registry-bound
values and a per-row contract — i.e. exactly the envelope widening §7's closure rule reserves to a
seat amendment, taken on no authority but the code's. Amendment #20(C) had to name
`committed_sha256`, `rows_moved` and the pairing token to put three OPTIONAL members in the envelope,
and while doing so it stated the envelope widens *"by exactly three optional members"*. **That was
false as written: a fourth, REQUIRED root member was already there.** The asymmetry was total — the
rankings row and the tripwire record each carry a spec-enumerated field allowlist; the exclusion
record alone carried none.
**RULED: `exclusions` is a REQUIRED root member of the rankings document, an array (possibly empty),
whose row field allowlist is EXACTLY {`geography`, `unresolved_input`}** — `geography` bound to the
`Geography` registry, `unresolved_input` bound to a closed code-owned token set. `schema_version` does
NOT bump: this authorizes what has shipped in every emitted document since the member was added, so no
consumer's reading changes. A contract test must hold the emitter's field set equal to this allowlist
DIRECTLY, never through the golden — the golden re-ratifies whatever the emitter emits, which is how a
required member reached production unauthorized in the first place. #20(C)'s "exactly three" is
CORRECTED to: three optional members, beside the required `exclusions` authorized here.
**The finding that produced this was itself DOWNGRADED**, and the record should say why: codex claimed
case (iii) would either fail validation or validate without an explicit exclusion. Exercised at the
cause, it does neither — it emits the exclusion row, seven ranked rows, and passes every validator. The
consequence was refuted on shipped bytes; the SPEC gap the attempt exposed is what survived, and it is
the mirror of the claim rather than the claim.

**(C) RE-SPECIFIED — the pairing token must bind OUTPUT CONTENT, because its ruled payload cannot see
a computation change. This is the amendment correcting ITS OWN author.** #20(C)(3) ruled the token
*"deterministic over (assumption selection, source bytes, `now`)"*, and the implementation follows that
ruling verbatim. **Nothing in that payload is code identity or output content**, so two runs over
identical data, identical assumption selection and the same `now` — separated only by a computation
change touching no constant, no data byte and no schema — emit DIFFERENT payloads in both documents
under a byte-identical envelope AND the SAME token. Measured: the published ranking REORDERED
(HORS_RMR 4→6, MTL_RMR 5→4, MONTEREGIE_RA16_PROXY 6→5) with the token unmoved. `now` is
`(year, month)`, so this needs two runs in the same calendar month — the ordinary developer loop, not
an adversary. And the mixed pair the rename loop can actually leave — NEW `rankings.json` beside STALE
`tripwire_baseline.json` — validates, its tokens match, and the consumer protocol published on the
shipped README accepts it.
**So three statements in this repository are false as written:** #20(C)(3)'s *"the residual must stop
being recorded as an unclosable ceiling"* (the detection it claims to close is not closed), the
pipeline's *"refuses EXACTLY the mismatch this loop can leave"*, and the README's *"what closed is the
DETECTION"*. A consumer following a published protocol that cannot refuse a bad pair is a check that
cannot fail, which is the failure this module treats as cardinal — so the ruling is to make the claim
TRUE, not to retract it.
**RULED, and NO NEW AUTHORITY IS NEEDED — this SELECTS the OR-branch #20(C)(3) already authorized**
("or a sibling manifest carrying both documents' digests"). The token is deterministic over the
**canonical PAYLOAD digests of BOTH documents** — each document's content EXCLUDING its identity
envelope, so there is no self-reference (the token sits inside both files). It therefore moves whenever
either payload moves, for ANY cause including a code change, which is the property the ruled payload
lacked. The nonce prohibition is unchanged and unaffected: this is a pure function of emitted content,
so byte-stability under identical inputs AND identical code is preserved exactly.
**CONSEQUENCE, stated because it is not free:** both committed goldens' `run_pairing` value re-mints.
That is a golden change, gated by the full suite, and it is the price of a token that answers the
question its consumer contract says it answers. `schema_version` does not bump — the member's name,
type and position are unchanged; what changes is what it is computed FROM.

**(D) RECORDED, NOT AMENDED — the I2 age-allocation finding restates NAMED LIMIT (B) verbatim.**
Codex reported that §6 states the I2 identity per age while the gate compares only totals, so
materially different age allocations pass it and reorder the ranking. Every part of that reproduced:
two age vectors with bit-identical totals both pass at all eight geographies and both domain
endpoints, per-age cells differ by up to **8,558 persons**, `D_native` differs by **7.05%–48.99%**,
and the reorder reproduces #20(B)'s published figures EXACTLY. **It is amended nowhere because
#20(B) already states it verbatim, sizes it, and publishes the same reorder** — and no consumer-path
surface claims per-age coverage: the emitted rankings carry `rank_stable: false` on every row, and the
gate's own docstring claims totals only. A gate that accurately describes its own narrowness is a
disclosed limitation; the verification confirmed the disclosure is arithmetically correct. Closing the
MECHANISM needs an arrival age distribution these bytes do not contain, which is Tranche-2 acquisition
work and is already stated as such.

**(E) RULED, on a premise of MY OWN that the build measured FALSE — the token does NOT widen to
cover `now`, and the clock's guard moves to a direct pin.** Implementing (C) exposed that
#20(C)(3) admitted `now` to the payload on a stated scenario: two runs differing only in the clock
emit *"DIFFERENT `tripwire_baseline.json` bytes, because `now` is the freshness axis"*. **Measured on
these bytes, that is false.** Two full runs one month apart, everything else identical, emit
payloads that are byte-identical in BOTH documents — all six tripwire indicators are structurally
`UNKNOWN` with null `as_of` and null `current_value`, so the clock reaches no emitted value at all.
A content-based token therefore cannot see the clock, and #20(C)(3)'s named scenario is undetectable
by construction rather than by oversight.
**RULED: do not widen the token, on three grounds.** (1) A token over content AND an input that the
content does not reflect answers two questions and therefore neither — **the exact argument
amendment #21 used to REFUSE hashing `_TRIPWIRE_DECLARATIONS`**, and it binds here for the same
reason. (2) The pair that escapes is byte-identical in every content field of both documents, so
every number a consumer reads is the number its run produced; refusing it is a FALSE POSITIVE, and a
gate that refuses correct pairs teaches consumers to ignore it. (3) It self-heals: the day the first
indicator carries a real value, `as_of` puts the clock inside the tripwire payload and the token sees
it through CONTENT, which is the axis that matters.
**WHAT ACTUALLY CLOSES THE INPUT SIDE is a three-token consumer protocol, not a fatter token.**
`run_pairing` answers *did these two payloads come from one emission*; `data_vintage` answers *which
data vintage*; `assumptions_hash` answers *which assumption selection*. All three ride BOTH files, so
a consumer compares all three — and the shipped README instruction, which named only the first, was
incomplete and is corrected. That incompleteness was itself a real hole: a failed rename leaving new
rankings beside stale tripwires whose payloads coincide carries MATCHING pairing tokens while the two
files disagree on `data_vintage`.
**THE COST, PAID DELIBERATELY AND REPAID IN ONE LINE.** Before (C), the emitted token covered the
clock, so moving `GOLDEN_NOW_MONTH` re-minted both goldens and forced somebody to look. It no longer
does: a clock-only change now moves no committed byte and reds nothing — **measured, by mutating the
pin and observing 14 of 15 golden tests still pass.** A declared input that no gate holds is the class
this module keeps re-finding, so the guard is restored where it belongs, as a direct pin on the
declaration: `tests/test_golden.py::test_the_goldens_declared_CLOCK_is_pinned_because_no_emitted_byte_holds_it`.
It is self-retiring by design and cheap enough to leave standing after it retires.

**AMENDMENT #23 (2026-08-23, codex cross-family round 12 + a commissioned §10 sweep; every item
measured by an independent pass told to REFUTE it) — ONE REAL CONTRACT GAP CLOSED, TWO FALSE
COVERAGE CLAIMS RE-POINTED IN PLACE, ONE SHIPPED RULING FINALLY WRITTEN DOWN, AND A HYPOTHESIS OF MY
OWN REFUTED.**

Round 12 returned four findings: three CONFIRMED-and-NEW, one REFUTED. **None is a shipping defect
— every emitted byte was and remains correct.** All three confirmed items are the same species: a
sentence in this document claiming a check that does not exist or cannot exist. That species now has
a name and a standard treatment (re-point in place, dated, quoting the measurement), applied here
three times.

**(A) CLOSED — §7(b) had NO whole-document set contract, and the asymmetry is the argument.** §7(a)
mandates as a contract test that ScenarioPrior row keys form *"the COMPLETE Cartesian product … with
NO duplicates"* — for an artifact that is GATED AND UNBUILT. §7(c) mandates *"every code-required
indicator is present exactly once"* for the tripwire baseline, and the code enforces it as multiset
equality. **§7(b) — labelled TRANCHE 1 CORE OUTPUT, the artifact that actually ships — had neither**,
and §8 stated the obligation (*"the rankings cover the remaining members"*) with no contract
anywhere holding it. Measured to BUILD, VALIDATE and WRITE before this amendment: a geography
simultaneously RANKED and EXCLUDED; duplicated exclusion records; duplicate rank values; a rank-99
gap; contiguous-but-2-based ranks; all-ranks-1; the same geography ranked twice; and a ONE-ROW
ranking covering 1 of 8 modeled geographies.
**RULED: the emitted rankings document is contract-tested AS A SET, at its builder AND at the strict
writer.** The geographies it RANKS and those it EXCLUDES are each duplicate-free; the two sets are
DISJOINT; their union EQUALS the modeled geography domain; and the `rank` values form the contiguous
permutation 1..len(rankings). An empty `rankings` array is legitimate ONLY when the exclusion records
cover the domain. The domain is `geography.MODELED_GEOGRAPHIES`, **derived** from the per-workbook
expected sets the loaders already enforce — never a typed literal, which is the stale-constant class
this module keeps re-finding; a test binds the registry union, the population-workbook union and the
`Geography` enum equal (n=8) so a divergence REDS instead of silently picking a side. Each violation
above is a distinct RED fixture at BOTH doors, the write-path arms mutating an already-built valid
document so the writer's enforcement is proven independent of the builder.
**Two prose statements went false with this change and are corrected with it:** the validator that
called itself *"the rankings sibling of the completeness rule"* while enforcing only
`|rows| + |exclusions| >= 1` (overstated by 7/8), and `write_json_strict`'s *"WHAT IS STILL NOT
CHECKED HERE, and deliberately: COMPLETENESS"* — a stated design decision, now reversed in place with
the measurement as its reason rather than deleted.

**(B) RE-POINTED — §6's per-cell nonnegativity named a check that is UNREPRESENTABLE.** §6 asserted
`P_resident(a,g,s,t) >= 0` *"asserted per cell BEFORE any consumer"*. Measured:
`assert_p_resident_nonneg` takes a SCALAR, has ONE production call site, and runs **27 times on
(geography, scenario, year) TOTALS against 2,727 per-age cells** created and handed to
`native_formation` in a single (geography, scenario); **zero** call contexts carry an age. It is not
an unimplemented check but an unwritable one — `_surviving_arrivals` returns a flat list of per-YEAR
flows with no age index, so *"surviving arrivals exceeding P_ISQ in a cell"* is not an expressible
input. The claimed consequence is false as a gate property too: a TOTAL-PRESERVING reallocation
carrying a **−33,143-person cell at age 26** passes both the I2 identity gate and the nonnegativity
gate and reaches `native_formation`, moving `D_native` by **−43.63%**.
**The property nevertheless HOLDS on every shipped byte, and #23(B) states WHERE it comes from**, which
is the part nothing said: every emitted cell is `P_ISQ(a) x (P_resident_total / P_ISQ_total)`, with
`P_ISQ(a) >= 0` refused at load (measured minimum per-age cell 568.0) and the scale nonnegative
because the total-level gate refuses a negative numerator and the call site refuses a non-positive
denominator. **BY COMPOSITION, not by assertion.** §10 gains the composition fixture: the operand
handed to `native_formation`, measured on the production path, plus the adversarial arm where
arrivals exceed P_ISQ and the run must refuse before any operand is formed. The reading "per cell
meant the (geography, scenario, year) cell" is not available: §6 writes the subscripts itself, and
the guard's own unit test fabricates `ctx="MTL/2035/ref/age40"` — the authors read it age-resolved too.
**Only ONE of round 12's three legs on this surface was new.** The per-age identity with uniform
allocation, and the arrival cohorts surviving with NO mortality applied (measured: the first-landed
cohort is 25,485.0 in BOTH 2026 and 2051 — zero decrement over 26 years), are both stated in
amendment #20(B)'s rider and were recorded in #22(D). Restating a declared limit changes no
obligation; naming a check that cannot exist does.

**(C) RETRACTED — §10's `20 vs 100 → CalibrationError` requires a RED that is mutually exclusive with
§5 AND with the committed data.** The shipped test at that exact fixture asserts the NEGATION
(`test_match_couples_20_v_100_per_band_imbalance_is_recorded_not_gated`), because steering ruling A
of 2026-07-25 retired the per-band balance gate and §5 carries that ruling — while §10 was never
re-pointed. `grep "ruling A"` returns ZERO hits in §10. This was not settled by reading the
contradiction: a verifier REINSTATED the per-band gate that would make §10 true and measured **33
failed / 1,173 passed / 36 errors**, including the gate refusing the CORRECT model on real committed
data at MTL_RMR 85+ (|21572.63 − 11789.00| / 21572.63 > 0.25). So the retracted bullet did not merely
lack a test; satisfying it would break the model.
**Half of round 12's finding here DIED and the record should say so:** the 0.25 boundary is NOT
underspecified. §5 writes *"beyond |diff|/max > 0.25"* (strict), the code implements
`> _REVERSAL_BOUND`, exactly 0.25 was measured to PASS at three different scales while
0.2500000009999999 RAISES, and two shipped tests pin the bound to [0.25, 0.26). Two conforming
implementations cannot differ there.

**(D) WRITTEN DOWN AT LAST — operator ruling V shipped four days before this document mentioned it.**
`grep -c "ruling V"`: **spec 0, code 45.** It is not a pending idea: `data/headship_by_age.json` is
read by `demand/formation.py` and `balance/owner_stock.py`, and `headship_shape` is one of the seven
declared axes making a golden run 336 legs, feeding the EMITTED `rank_stable`. Two consequences, both
now fixed: §6's *"Age-resolved headship first, then the floor"* read as an OPEN precondition after
the curve had landed (marked SATISFIED in place), and §10 carried no obligation for a Tranche-1
component that moves the ranked artifact — **the mirror of (C): there, a ruling landed and §10 kept
the old requirement; here, a ruling landed and §10 gained none.** §10 gains the robustness-sweep
anchor: `SWEEP_GRID` keys read through `CONSTANTS[...].band` and never a literal; each declared axis
produces a leg at BOTH declared endpoints, with a NAMED exemption for a provably-inert categorical
leg; `headship_shape`'s alternative leg is exercised; and moving any declared anchor inside its own
band MUST move `assumptions_hash`, asserted directly and never through the golden.
Rulings B, D, G, H, L and N are likewise spec-absent while code-cited. **Ruling V is the only one
whose subject is a live model component rather than a process or probe rule**, which is why it alone
is folded here; the others are recorded as a known, bounded gap.

**(E) REFUTED — the `run_pairing` optional-vs-required "conflict" is not one, and the refutation
INVERTS the argument.** Round 12 claimed that one `schema_version` denoting documents with and
without a load-bearing detection field must be either unsafe or backward-incompatible. Measured:
pre-token artifacts carrying the same `schema_version` genuinely exist in this repository's history,
and TODAY'S validator accepts them verbatim — so #20(C0)'s no-bump ruling and the README's *"a
consumer pinned to version 1 reads both documents unchanged"* are TRUE against real historical bytes.
On whether #22(B)'s retroactive-REQUIRED precedent transfers: **it does not, and the non-transfer is
exactly why OPTIONAL is correct.** `exclusions` is present in EVERY golden that ever existed, so
declaring it required changed no consumer's reading; `run_pairing` is absent from every golden before
it was introduced, so requiring it would either force a version bump or make today's validator refuse
artifacts this repository actually shipped. The finding treated those legacy artifacts as proof the
contract is broken; measured, they are the reason it is written this way.
**One real residue, and the OBVIOUS FIX IS THE WRONG ONE.** The published consumer protocol never
said what an ABSENT token means: a consumer using a defaulting read on two pre-token documents
compares nothing to nothing and the step passes VACUOUSLY. **Refuse-on-absence would break the
backward compatibility just measured**, so the instruction shipped instead is: absent means NO
PAIRING EVIDENCE — not a refusal — fall back to comparing `data_vintage` and `assumptions_hash`.

**(F) MY OWN HYPOTHESIS, REFUTED BY THE SWEEP I COMMISSIONED TO CONFIRM IT.** Two of two §10 bullets
checked had come back CONFIRMED false-coverage (#22(A) and (C) above), both for the same structural
reason, and I recorded that as a defect CLASS rather than two incidents — then commissioned an
exhaustive §10 sweep instead of waiting for one per review round. **The sweep refuted the
generalization: 34 atomic claims enumerated and checked — 29 HOLDS, ZERO new false coverage, 1
UNVERIFIABLE-AS-WRITTEN, 2 DERIVATIVE (the two already known), 2 DEFERRED-BY-SPEC (Tranche-2 tests
correctly absent).** §10 owes no further amendment. The two instances were two instances. Recorded
because a refuted hypothesis of the author's is worth exactly as much as a confirmed one, and because
the sweep's method is the reusable part: **locate a bullet's test by its FIXTURE VALUES, never by its
NAME** — (C) was invisible to a name search and obvious the moment `20 vs 100` was matched.
The sweep's one non-derivative catch is the **UNVERIFIABLE-AS-WRITTEN** bullet: *"the fail-loud claims
get their adversarial pass from stress-tester at PR time"* is not a test and names no closed set, so
nothing can be checked against it. Its binding form, adopted here: **every `raise LoaderError` /
`raise CalibrationError` site reachable from a public loader entry point carries a RED in `tests/`** —
mechanically checkable today. Also worth recording as an independent confirmation of #22(A): under a
double-decrement mutant the oracle tests went RED (10 of them) while `test_reconciliation_gate.py`
stayed FULLY GREEN — the retraction's premise, re-measured by a pass that was not looking for it.

**AMENDMENT #24 (2026-08-23, codex cross-family round 13; four findings, three CONFIRMED-and-NEW and
one REFUTED, each measured by an independent pass told to refute it) — ONE REAL MODEL DEFECT IN THE
SHIPPED NUMBERS, TWO GATES THAT CANNOT REFUSE WHAT THEY CLAIM TO, AND A DEPENDENCY WORRY THAT TURNED
OUT TO BE ALREADY CLOSED.**

Round 13 left the prose and gate surfaces the previous two rounds worked over and reached the model.
**(A) is the first finding in this arc's audit history to make an EMITTED NUMBER wrong.**

**(A) CONFIRMED, SHIPPING, AND FIXED — `p_imm` multiplies an ALL-MAINTAINER rate by a
NON-IMMIGRANT-DENOMINATED ratio, so every emitted `mean_ed_*` is biased.**
The decisive fact was answered from the data's own columns, never from prose: **the age-banded
ownership cube has NO immigrant dimension**, so the propensity read from it is
`owner maintainers / ALL maintainers`. Measured bit-exactly — the shipped `p_nonimm(MTL_RMR)` is
`490,275 / 957,575 = 0.5119964493642796`, the exact float the model multiplies, recomputed straight
from the committed CSV. Corroborated ACROSS CUBES: that cube's MTL total private households
**1,835,705** equals the immigrant cube's non-immigrants 1,252,635 + immigrants 511,070 +
non-permanent residents 72,000 = **1,835,705, difference 0** — so the operand's universe is provably
all three groups. The ratio's denominator is non-immigrant-only. The emitted product is therefore
`p_imm_true × B` with `B = p_all / p_nonimm`, measured per geography: MTL_RMR **0.940022**, QC_RMR
0.970180, MTL_ISLAND_RA06 0.939637, HORS_RMR 0.990212, and LAVAL_RA13 **1.016742**.
**This is a false coverage claim, not a declared limit.** The definition above calls the product
*"the immigrant ownership propensity, DEFINED"* and asserts it in [0,1] as a probability, and the
loader says verbatim *"The non-immigrant ownership propensity"* while serving the all-maintainer
rate. Nothing in this spec, in any amendment, in the constants' own pooled-ratio ANTI-PATTERN record,
or on the consumer page declares the operand's immigrant-status universe. The nearest neighbour pools
across RECENCY (all immigrants vs recent arrivals) — a different axis, and about the ratio's
NUMERATOR, not the operand's denominator.
**RULED: FIX IT, do not declare it.** `B` is computed per geography from the SAME cube that already
supplies the ratio, so the correction uses data the run already loads; codex's own refuting condition
named this remedy ("algebraically converted from the pooled curve using matched immigrant weights"),
which makes the fix the thing that was missing rather than a new model. Two facts decided the ruling
over a named limit. First, **a PUBLISHED value changes SIGN**: MTL_ISLAND_RA06's `mean_ed_low` goes
from **−3.6598846e-04 to +6.118465e-05**, and a consumer reads that as shrinking-versus-growing
excess demand at the low end — a semantic flip, not a rounding. Second, the largest reference-mean
delta is **6.8700e-04, or 12.57% of the entire published pre-fix ranked spread** (5.4637e-03), on a
leg that is itself a first-order contributor.
**ERRATUM, 2026-08-23, same day — THE TWO POST-FIX FIGURES ABOVE WERE WRONG WHEN FIRST WRITTEN, AND
THE INSTRUMENT IS WHY.** They were first published as `+5.829e-05` and `6.823e-04 / 12.49%`. Both
land EXACTLY — to seven and five figures respectively — under **MTL_RMR's `B` applied at
MTL_ISLAND_RA06**, and NEITHER lands under this amendment's own ruling that `B` is per-geography.
Two independent verifiers reached that conclusion separately. So the ruling and its illustrations
contradicted each other, in a document that is LOCKED and that the next reader trusts over the code.
The figures above are now the SHIPPED ones, computed under the ruling with RA06's own
`B = 0.939637`. **The rule this cost, for the third time in this arc: a sensitivity figure is
meaningless without its instrument named beside it, and a figure inherited from a report is not a
measurement until it is re-derived under the ruling that will actually ship.**
**WHAT THE FIX CORRECTS AND WHAT IT CANNOT — NEW NAMED LIMIT (C), declared because the fix is partial
by construction.** `B` is a per-geography SCALAR, so the conversion corrects the LEVEL. It cannot
correct the SHAPE: the age curve comes from a cube with no immigrant dimension, so no age-resolved
non-immigrant curve is derivable from these bytes at all. The corrected operand is therefore
"non-immigrant LEVEL, all-maintainer SHAPE", and that residual is a NAMED LIMIT with its instrument
named, not a silent approximation. An age-resolved immigrant-status tenure cube is Tranche-2
acquisition work and is already listed as such.
**ORDER SURVIVES, and the record says so as plainly as it says the levels are wrong.** Zero of eight
rows reorder at the measured `B`, at an own-composition variant, or at TWICE the measured deviation;
the first reorder needs 3×. Tranche 1's headline product is the relative ordering, and it is
unaffected — which is what makes this fix low-risk, not what makes it skippable.
**The direction is NOT uniform**, exactly as the finding predicted around ratio = 1: LAVAL_RA13 is
the single geography with `B > 1`, the one place the shipped immigrant leg is OVER-stated. Everywhere
else it is under-stated. And the reported algebra was right but INCOMPLETE — a two-group correction
predicts `B_MTL = 0.97252` against the measured 0.940022, because the pooled denominator carries a
THIRD group the finding did not name: non-permanent residents, weight 0.0392 at propensity ratio
0.1713. **The real bias is roughly double the two-group prediction**, which is the argument for
measuring `B` from the counts rather than deriving it from a stated weight.

**(B) CONFIRMED — the IRCC completeness rule re-admits, for one cell per member, exactly the
truncation it was written to refuse; and the residual it DECLARED is a different, smaller exposure.**
The rule's third clause tests member-set PRESENCE, while month-completeness is demanded only of the
MODELED members. A feed carrying all twelve month tokens province-wide, twelve of twelve for each
modeled member, and **exactly ONE cell for each of the 29 other required members** satisfies every
clause, publishes **46,385 against a true 60,010**, and emits `status=OK` with `reason` null and no
run-log line naming anything.
**Why this is not the declared residual.** The declared residual's consequence is CONDITIONAL — *if*
the "an unpublished month means zero" inference is false, an interior gap hides landings. **The
measured false green holds when that inference is TRUE**, and on the committed bytes it looks true
(zero literal-zero cells). So a reader who does exactly what this document invites — re-test the
assumption, find it sound, discharge the residual — is still exposed, because truncation-in-transit
and omission-as-published are different causes and the gate cannot tell them apart. *That is a check
that cannot fail for the reader who follows the document*, which is this module's cardinal failure
mode.
**The size, which was never stated while every sibling case was sized:** the declared residual is
+152 on real data, 0.25%, verdict-inert. The ADMISSIBLE MAXIMUM is **13,625, or 22.70% — enough to
cross the band and still report OK. Ninety times the declared residual.** And the clause's refusal
costs one cell to evade: the same member dropped is refused at damage 675; at one cell it is admitted
at damage 670.
**RULED — AND THEN WITHDRAWN THE SAME DAY, BECAUSE THE RULING WAS WRONG ON THE FACTS.** The first
ruling here read: *month-completeness is demanded of EVERY member that contributes to the summed
provincial value, not of the modeled members alone.* The build agent commissioned to implement it
**refused, and it was right.** Measured on this module's own committed bytes, that closure refuses
the **HONEST** year under BOTH candidate scopes: over the 32 CONTRIBUTING members, 11 fall short of
twelve months, the minimum being **three**, at Hawkesbury (Quebec part); restricted to the 31
formally required members it still fails, 10 short, minimum **eight**, at Lachute. IRCC does not
publish every CMA in every month. So the ruled gate could never clear on real publication practice,
and this module's own encoded rules — *a rule that can never clear is not a gate*, and *EARNED, NOT
TUNED* — forbid exactly that. **Landing it would have converted an evadable gate into a dead one and
called it a fix.** (One label correction inherited from the refusal: the universe is 32 CONTRIBUTING
members, not 32 "required" ones — Hawkesbury is not in the required set, and the ruling's own
"contributes" wording is what makes 32 the right count.)
**Three narrower closures were evaluated and each has a stated refutation.** A per-member cell or
month FLOOR is a tuned threshold with no derivation, which this module refuses on principle.
SET-EQUALITY on the month calendar breaks **6 of the 12 real years** in the committed history and
remains evadable anyway, because an attacker controls the shared set and can shrink it to one month.
The one closure that fits the module's precedent — **each member must publish at least as many
months as its own historical minimum**, derived rather than tuned and immune to relabeling — depends
on a 12-year per-member feed that is **absent from the tree**, and cannot be written today without
inventing the numbers it rests on.
**RE-RULED: the hole is recorded OPEN, with its attack preserved, and the closure is a named
Tranche-2 obligation that lands WITH the feed.** This inverts amendment #21's precedent rather than
following it, and the inversion is the point: #21 closed a measured-unreachable hole early because
the fix was available and free. Here the fix is NOT available — the data it needs does not exist in
this repository — so the honest act is to hand the next author the ATTACK rather than a limit, and
certainly rather than a gate that cannot fire.
**THE EVASION RECIPE, PRESERVED VERBATIM BECAUSE ITS PROBE DIED WITH THE SESSION THAT BUILT IT.**
Take the committed IRCC PR-landings fixture; relabel the plan year so the closure logic considers it;
keep a full twelve-of-twelve month calendar for the two MODELED members only; for every OTHER member
of the required set publish exactly ONE month — the one carrying that member's minimum cell — so the
member is present and the subset check is satisfied; drop the non-required members entirely. Every
clause then passes: the subset check sees all required members, the month-completeness check reads
only the modeled members' calendars and sees twelve, and NO clause compares any member's month count
against anything. Two independent runs reproduced it — 46,385 published against a true 60,010
(22.70% withheld) and 46,300 against 60,010 (22.85%), the difference being only a minimum-cell
tie-break. Both emitted `status=OK`, `reason` null, no run-log line, and a completeness log reading
"12 months" that was true of two members out of thirty-two.
**Nothing is reachable today** — the feed is absent and all six indicators ship `UNKNOWN` — and zero
emitted bytes moved for this item.

**(C) CONFIRMED — the three-token consumer protocol compares THREE of the FOUR identity members this
document declares, and the shipped page claims the enumeration is COMPLETE.**
`schema_version` sits inside the identity envelope, and the pairing token is computed over the
payload with that envelope SUBTRACTED — so it is invisible to the token **by construction**, which is
the same property that makes the token computable at all. Measured on the committed goldens: flipping
one file's `schema_version` leaves its payload digest bit-identical and the token unmoved, and a pair
differing ONLY in `schema_version` passes all three published steps. No code anywhere compares it
across a pair.
**Amendment #22(E) is NOT falsified on its own scoping** and the record should be exact about that:
it said the three tokens are what closes *the input side*, and `schema_version` is a code-identity
declaration rather than an input. What IS false is the consumer page's UNIVERSAL — that the envelope
comparison catches every member of the class but one named exception — and §7(b)'s
"rejects mixed-identity row sets" read against the four-member identity §9 declares.
**RULED: a FOURTH comparison, on `schema_version` ALONE.** It must not extend to `schema`: the two
documents carry DIFFERENT `schema` strings by design, so comparing that would refuse every honest
pair. **The fix is free, and by this document's own test:** all seven historical golden pairs carry
`schema_version` "1" on BOTH files, including the four that predate the pairing token — so amendment
#23(E)'s transfer question ("present in every artifact that ever existed?") PASSES here. This is the
`exclusions` camp, not the `run_pairing` camp: a fourth comparison refuses no honest pair and breaks
no legacy consumer.

**(D) REFUTED — the mortality dependency IS inside artifact identity, and the worry that a queued
sibling merge could silently move published rankings is measurably wrong.**
The finding reasoned from the dependency declaration and this spec, and did not reach the module that
closes it: a digest over the q surface the model actually consumes, taken through the sanctioned
public entry point, rides `data_vintage.source_hashes` UNCONDITIONALLY in BOTH documents, and the run
identity inherits it. It has since run 33. So §9's *"a change in any re-mints the artifact BY
DESIGN"* is TRUE, because the basis digest is inside `data_vintage`. This is REFUTED rather than
downgraded: it neither restates a declared limit nor exposes an overclaim.
**The seat's merge concern, answered with four measured layers** and recorded here because it governs
pending work: the production environment installs the sibling as a NON-EDITABLE wheel SNAPSHOT with
its own copy of the tables, so sibling edits reach nothing until a dependency re-sync; after a
re-sync, any movement in q re-mints the basis digest in both documents; the pairing token re-mints
with it; and a committed guard pins the basis digest at declaration while both goldens carry that
same value, so a moved table REDS with an instruction to re-declare in the same commit. **A sibling
change can move ranks; it cannot move them invisibly, which was the claim.**
**ONE WATCH ITEM for the coordinated merge, named because it is the single thin place:** the
seat-coordinated import swap must stay on the three public names, and one test —
that the basis digest reaches no private engine surface — is the only guard between that swap and a
digest taken over a private surface. **The unmet half of the finding's own refutation recipe stands as
a lineage limit, not a detection gap:** the dependency is declared by PATH and pins no revision, so
identity records WHAT the tables contained, never WHICH revision produced them. Detection is closed;
point-in-time provenance is not, and that distinction is the whole of what survives.

**AMENDMENT #25 (2026-08-23, codex cross-family round 14) — TWO STALE LITERALS RE-POINTED WHERE A
READER ACTUALLY MEETS THEM, AND THE LESSON ABOUT WHY MY OWN SWEEP MISSED THEM.**

Round 14 returned four findings against the post-#24 bytes. One is derivative of a hole this document
already records open; one is under verification; the two settled here share a shape worth naming.

**(A) §10's mortality bullet is RE-POINTED IN PLACE — because amendment #22(A) retracted the CLAIM and
never edited the LINE.** #22(A) ruled that the double-count RED belongs to the oracle-exact mutation
test, since the reconciliation band cannot detect a doubled decrement at the only scope ruling O
permits. **But §10's literal checklist entry kept saying "MUST raise CalibrationError (reconciliation
gate test)" for two more amendments.** Fixed at the line itself.
**THE LESSON, and it indicts a method of mine rather than a fact:** the §10 sweep I commissioned
called that same bullet DERIVATIVE and correctly declined to re-report it, because the sweep read the
document WITH its amendments applied and saw the obligation already dispositioned. Codex read the
section the way a READER does — in place, top to bottom — and saw a checklist demanding an impossible
test. Both were right about what they read. **So: a retraction that lives only in an amendment does
not repair the sentence it retracts. From here, a retraction edits the literal text at its own line,
dated, and the amendment carries the reasoning** — which is what #23(C) already did for the balance
bullet in the very same section, and #22(A) did not. The inconsistency was mine.

**(B) §1's "schema-enforced output prohibition" is QUALIFIED — the header promised what §7 already
admitted it could not deliver.** Allowlists, finite checks, closed enums and band ordering bind
vocabulary and shape, never numeric PROVENANCE, so an unconditional probability can sit in an allowed
numeric field and satisfy every schema invariant. §7 has recorded exactly that as its epistemic limit
since codex r10-F1. The header and §7 disagreed about the same guarantee and **the header is the one a
reader meets first.** Corrected there rather than in §7, and the distinction is stated positively: the
schema forbids the VOCABULARY of an unconditional forecast — no field to hold a `crash_probability`,
no free string to smuggle one — while CONDITIONALITY of a number inside an allowed field rests on the
single derivation path and the version-stamped mapping. **Not a shipping defect:** the field it bites
is Tranche-2 and unbuilt. Corrected anyway, because the Tranche-2 author will read that header as a
guarantee.

**(D) DOWNGRADED, AND THE UNDERDETERMINATION IS CLOSED BY WRITING THE COMPOSITION DOWN — plus a
SCOPING CORRECTION to amendment #24(A) that matters more than the finding.**
Round 14 argued that amendment #18's ownership BORROW and #24(A)'s per-geography bias `B` compose
into an operand that recovers neither population, so two conforming implementations diverge.
**Measured, the composition is FOUR classes and not one, and the finding's own premise of "five RA
borrowers" is factually TWO:**
- **own level ÷ own bias** — MTL_RMR, QC_RMR.
- **own (aligned) level ÷ own bias, with a DECLARED territory mismatch in the correction factor** —
  HORS_RMR, already stated at its row.
- **parent level ÷ PARENT bias, no mixing whatsoever** — the three RA proxies. The borrowing helper
  passes the parent's own bias block through, verified by object identity, so no seam exists there.
- **parent level ÷ OWN bias — the ONLY cross-geography seam in the module** — MTL_ISLAND_RA06 and
  LAVAL_RA13, and nowhere else. `B` is never internally mixed at any geography; there are no
  normalization weights; the whole composition is one scalar division.
**SCOPED, because my first wording here was looser than the code and the build agents corrected it
on the page before I corrected it in the spec.** The `÷ B` happens on the **IMMIGRANT LEG'S operand
ALONE**, once, at a single call site — native formation and the supply side read the borrowed
ownership curve **UNDIVIDED at all five borrowing rows.** That is measurement, not inference: the
bias has exactly ONE definition and exactly ONE consumer in the tree. And the emitted
`borrowed_prior` flag fires on **EITHER** immigrant-leg provenance field, not both — ruling Q exists
precisely to permit a cited ratio beside a borrowed headship — so the flag's subject is per-FIELD
provenance and never a geography set, even though on today's bytes every flagged row happens to
borrow both.
**RULED: the shipped composition is correct, and here is the algebra that says so.**
`p_all(parent)/B(RA) = p_nonimm(RA)_true × [p_all(parent)/p_all(RA)]` — it DOES recover the RA's own
non-immigrant propensity, multiplied by **exactly the level-borrow error amendment #18 already
declares** and that the native leg already carries. So "recovers neither" is true as exact algebra
and false as an inference: no re-anchoring formula is needed, because #18's premise IS
`p_all(RA) ≈ p_all(parent)`, and applying a per-geography `B` to that borrowed level is the literal
composition of §8/#18 and #24(A) in the order they were written. **The rival reading**
(`p_all(parent)/B(parent)` — borrow the parent's NON-IMMIGRANT rate) recovers the same target up to a
SECOND, undeclared error quantity, and it collapses four Montréal-parented rows onto one identical
operand, discarding the only locally-measured ownership information RA06 and LAVAL_RA13 have.
#24(A)'s erratum had already rejected it at RA06 by name.
**Why DOWNGRADED and not REFUTED: the COMPOSITION was stated nowhere.** Both halves are written
separately — the borrow at its loader, the per-geography `B` here — and the composition, its
justification, and the fact that it applies at exactly two geographies appear in no document. The
erratum touches only RA06, only as figure provenance, and never mentions LAVAL_RA13, **the single
geography where the two readings materially diverge.** A Laval implementer had nothing to cite. That
is a documentation defect, not a model defect, and the paragraph above is its closure.
**⚠ SCOPING CORRECTION TO #24(A), and it narrows a claim of mine.** #24(A) states that order survives
"at the measured `B`, at an own-composition variant, and at TWICE the measured deviation; the first
reorder needs 3×". **That envelope varied `B` AND ONLY `B`. It never priced the composition axis.**
Measured on the finding's own named remedy — an explicit level re-anchoring — operands move −27.26% at
RA06 and +22.39% at LAVAL_RA13, **FOUR of eight rows REORDER** (ranks 3/4 and 7/8 swap), TWO published
values change sign, and the largest reference delta is **51.714% of the published spread.** A
re-anchoring is NOT a conforming implementation of this document — it needs a formula nothing states —
so it is a THIRD MODEL rather than a second reading, and the finding as filed moves no rank. But
**#24(A)'s order-invariance envelope must be read as scoped to `B`, not to the composition**, and that
is precisely why the rule above had to be written down rather than left composable.
**DISCLOSURE — RULED, and the flag does NOT change.** The emitted `borrowed_prior` flag's subject is
the IMMIGRANT leg, per ruling Q and by deliberate design, and the code states the hazard in terms: a
reader who takes it as "this row's rates were borrowed" reads LAVAL_RA13 and MTL_ISLAND_RA06 wrong,
because those two borrow the ownership CURVE while their immigrant inputs are their own. Adding the
flag to those rows would make one token mean two different provenances — the exact confusion the
routing exists to prevent — so **the flag stays as it is.** What is wrong is WHERE the disclosure
lives: in a code comment and in a second artifact's inline marker, not on the consumer page a rankings
reader actually opens. **RULED: the consumer page must name which rows borrow the ownership curve,
state that the emitted flag does NOT carry that fact, and point at the artifact that publishes it** —
bound to the loader's own borrow registry rather than a typed list. **LANDED**, as its own section
outside every digest-pinned span, with two gates reading the borrow roster from the registry, the
flagged roster from the EMITTED artifact, the seam from immigrant-input block identity, and the
publishing file out of the prose then opened. **The precise asymmetry, now published: the flag can
never OVER-state — every flagged row does also borrow the curve — it can only UNDER-state, and at
exactly two rows it does.** One further defect surfaced while landing it: the CURRENT-STATE span, one
section ABOVE the new disclosure, already stated the very confusion this item rules against, and was
corrected with it.

**(C) RECORDED, NOT AMENDED — the IRCC false-clean finding is this document's own open hole read back
to it.** Round 14 re-raised the truncation attack and its ~22.7% suppression, and noted itself that
the branch is unreachable while the feed is unwired. That is amendment #24(B) verbatim, including the
attack recipe preserved there and the Tranche-2 closure obligation. **Derivative: no new fact, no new
obligation.** Recorded only so the ledger shows the loop re-derived a declared hole rather than
finding a new one — which is itself evidence about where the review is converging.

**AMENDMENT #26 (2026-08-23, codex cross-family round 15) — TWO MORE RETRACTIONS THAT NEVER EDITED
THEIR OWN LINE, AND THE ADMISSION THAT THIS IS NOW A HABIT.**

**CORRECTED BEFORE THIS AMENDMENT EVER LANDED.** Its first draft opened "Round 15 produced no
shipping defect and no rank movement" — written while round 15's fourth finding was still under
verification, and **FALSIFIED by that verification: round 15 confirmed the event-time window
misalignment, a SHIPPING DEFECT in which `ED(t)`'s numerator subtracts a supply flow over `[t, t+1)`
from a demand flow over `(t−1, t]`.** A reviewer caught the sentence in this draft. Recording it
rather than quietly deleting it, because writing a false summary INTO the amendment whose own item
(D) names amendment-only-retraction as a habit is the sharpest available demonstration that the habit
is real and that I am not exempt from it. The event-time defect is dispositioned in its own
amendment; items (A)–(D) below stand as written.

What round 15 ALSO produced is the SAME SHAPE round 14 produced, twice more — and at three instances
the pattern stops being an accident.

**(A) EDITED IN PLACE — §7's mapping paragraph called ED "the dimensionless fraction" for fourteen
review rounds after the correction landed THIRTY LINES BELOW IT.** Amendment #12 established that ED
is **yr⁻¹**, a net turnover rate — annual FLOWS over a stock LEVEL — and §7 itself says so, in a
paragraph that even names the failure class: *"'dimensionless' was a gloss beside a correct number,
which is the class this document keeps closing."* **The line thirty lines above it went on saying
"dimensionless" anyway.** β is DIMENSIONLESS, and that is now stated where the mapping is defined.
No numeric error followed, because β is specified as drift per year per unit ED and absorbs the unit
either way — the defect is that two conforming implementations could disagree over a NON-annual
period, where a 12× divergence is exactly what the annual worked fixture cannot distinguish.
**The Tranche-2 field name `excess_demand_fraction` reinforces the stale reading**, so a Tranche-2
author renaming it to a rate is RULED IN ADVANCE and needs no further amendment; keeping the stale
name requires a unit note at the field.

**(B) QUALIFIED — §9's artifact-identity tuple is INPUT identity and is not unique over payloads.**
Every member of `(data_vintage, assumptions_hash, mapping_version, schema_version)` is an INPUT
declaration, and amendment #22(C) established BY MEASUREMENT that a code-only change touching no
constant, no data byte and no schema reorders the published ranking while all four stay fixed. So the
tuple collides across materially different payloads and §9's *"a change in any re-mints the artifact
BY DESIGN"* is true only of what the tuple can see. Read identity as **the tuple PLUS `run_pairing`**
— the content half, which moves whenever either payload moves for any cause. **Third member of a
family now:** #25(B) corrected §1's schema claim, #23(E) the pairing protocol, this one §9's tuple —
each an identity or guarantee statement written BEFORE the token it needed existed, and each left
standing after the token arrived.

**(C) RECORDED, DERIVATIVE — the optional-member/no-bump tension is round 12's finding from the other
side.** Round 12 asked whether TODAY's validator accepts YESTERDAY's artifacts; it was REFUTED by
measurement (pre-token artifacts with the same `schema_version` exist and validate). Round 15 asks
the reverse — whether YESTERDAY's validator accepts TODAY's added optional members. **The reverse
direction is genuinely untested, and it is also unreachable: this module has no external SOFTWARE
consumer.** There is no pinned-version validator anywhere to break: S4b's file contract does not
exist yet, and §1's value-order consumers — the operator and the showcase — are READERS, not
validators. (Framing corrected before this block committed; #27 below makes the same correction.) **Recorded as the precise open condition rather than
fixed: the no-bump rationale assumes a consumer that IGNORES unknown fields, and the first real
consumer is where that assumption gets tested.** A Tranche-2 author reading #20(C0)'s
backward-compatibility argument should read it as scoped to consumers that tolerate unknown members.

**(D) THE HABIT, NAMED, because three instances in two rounds is a process defect and not a set of
typos.** Every one of #25(A), #26(A) and #26(B) is the same failure: a ruling was written as an
amendment and the sentence it retracted was left in place, hundreds of lines away from its own
correction. **A retraction that does not edit its own line is not a retraction; it is a second,
contradicting claim.** The rule is now: an amendment that retracts or re-points ANY sentence edits
that sentence, dated, at its own location, and carries only the reasoning in the amendment block.
**And the auditing consequence, which cost real budget to learn:** a sweep that reads this document
WITH its amendments applied cannot see this class at all — it resolves the contradiction and reports
clean, which is exactly what the commissioned §10 sweep did. Finding these requires reading the
document as a first-time READER does, in place, with no amendment resolution.

**AMENDMENT #27 (2026-08-23, codex cross-family round 15, finding 1; verified by an independent
adversarial pass and adopted after an unframed strategic review) — `ED(t)` SUBTRACTS TWO ADJACENT,
DISJOINT 12-MONTH WINDOWS. THIS IS AN IDENTITY ERROR, NOT A NAMED LIMIT, AND IT IS FIXED.**

Year labels on the population frames are 1-July LEVELS: the row labeled t covers 1 July t → 1 July
t+1 and lands in Population(t+1). Against that:
- **Both DEMAND legs are END-labeled, window `(t−1, t]`.** `native_formation` differences the previous
  iteration's frame against the current one; `_arrival_year(t) = t − 1`; and `_surviving_arrivals(t)`
  ranges to `t − 1`, so the cohort credited as immigrant demand at t is exactly the cohort netted out
  of the resident base at t. **I2's netting and the immigrant credit share ONE convention.**
- **Both SUPPLY legs are START-labeled, window `[t, t+1)`.** The roll keys exits at the roll-START
  year, and market listings read them at that key with the estate lag applied on top.
- **So the numerator subtracts a supply flow over `[t, t+1)` from a demand flow over `(t−1, t]`.**
  Each pair is internally coherent; the two pairs are offset from each other by exactly one year.

**WHY THIS IS A BUG AND NOT A BASIS — the triage rule this module has followed implicitly and now
states.** §7's identity carries the SAME t on D, S and OwnerStock and assigns no transition to the
exits. A confirmed violation of the module's own identity is an IMPLEMENTATION ERROR: it gets FIXED,
whatever its rank impact. A defensible alternative construction is a BASIS: it gets BOUNDED and
PUBLISHED as a named limit with its instrument. **This one cannot honourably become a fourth named
limit** — the named limits are alternatives a reasonable modeller might choose, whereas this has a
known mechanical remedy and the module already CONTAINS the translation helper, applied at one seam
and not the other.

**THE DIRECTION IS FORCED, not chosen.** The demand labeling is compelled by the committed bytes:
crediting arrivals(t) at t RAISES at the final domain year, and a start-labeled native leg would need
a population frame one year past the last one that exists. **End-labeling is therefore the only
self-consistent convention computable on these data**, and the shipped output differs from it.

**THE FINGERPRINT.** The run computes SEVEN years of listings it NEVER READS — 2021-2025 before
the ranking domain opens, plus 2052 and 2053 that the estate lag pushes past it (this said
"five", counting only the leading five; corrected on measurement) — while reading a listings
year lying WHOLLY BEYOND the last modeled demand year — averaging 26 demand-years over
`(2025, 2051]` against 26 supply-years over `[2026, 2052)`.

**NOTHING HELD IT, AND THAT IS THE FINDING'S REAL LESSON.** 1,280 tests do not pin the cross-leg
alignment. The hand-worked ED fixture pins the estate LAG and passes demand as two BARE UNLABELED
NUMBERS; the cohort oracle pins only within-supply labeling. Under the corrected convention the suite
runs 1277/3 and **all three reds are output pins, not convention oracles.** **RULED: the fix lands
WITH a LABELED-WINDOW fixture** — the hand-worked fixture carries window labels on D exactly as it
already does on the estate lag — because a class no test can express will recur.

**MEASURED CONSEQUENCE.** All 24 published `mean_ed_*` move on an exact identity —
`delta(t) = [listings(t) − listings(t−1)] / OwnerStock(t)`, verified to 1.6e-19 — the largest by
**32.4% of its own magnitude**, and one year by **1.58× its row's own |mean ED|**. Mixed per-cell
signs are self-explaining: a negative cell means the listings series locally DIPPED, which is the
senior-exit wave crest receding. **The published `rank` column and EVERY HEADLINE SIGN survive**, on a
624-cell scan across all three scenarios, because the correction is near-uniform across the soft
middle relative to the rank-4/5 gap.

**WHY IT IS FIXED BEFORE RELEASE and not after, on three grounds that a strategic review found
dominant.** (1) **The cascade is paid ONCE.** A post-release fix re-mints the artifacts and re-derives
the digest-pinned consumer page a SECOND time. (2) **The published epistemic guidance was itself
measured on the defective series** — the named limits' threshold, the rank-reliance bullet and the
(A)/(B) convergence claim were all built from the misaligned ED grid, and this document's own history
shows such a re-measurement changing conclusions QUALITATIVELY rather than merely re-digiting them
(#24(A) silenced an entire sweep axis as a reordering axis). Shipping headline guidance measured on a
known-defective baseline and then re-issuing different guidance is worse than fixing first —
especially for the showcase consumer, whose whole framing IS the named limits. (3) **The per-year
trajectory, not the mean, is what a Tranche-2 consumer will read**, and the mean absorbs this offset
as a boundary-and-trend effect while every individual year stays misaligned. Fixing before any
consumer exists is the cheap moment: no recalibration, no migration.

**AND A CORRECTION TO THE FRAMING THIS SEAT USED WHILE DECIDING IT.** I had recorded the consumer as
"S4b, which does not exist yet", which made level precision look like work for an absent reader. §1
ranks consumers in VALUE ORDER and S4b is THIRD: **first the operator, for whom rankings AND tripwires
ARE the core v0 output; second the showcase, which ships off Tranche 1.** Two live consumers today,
both of whom make correctness the product. **This is the last level fix Tranche 1 should absorb**:
afterwards the triage rule is that a further level finding must move a RANK, flip a HEADLINE SIGN, or
break a PUBLISHED CONTRACT PROMISE to earn a cascade — otherwise it is a Tranche-2 note. The published
limits already establish that basis uncertainty dominates residual level error by an order of
magnitude.

**WHAT THE FIX ACTUALLY MEASURED — recorded because an amendment that authorizes a cascade and never
records what it moved leaves the next reader unable to tell a PREDICTION from a RESULT.** The change
landed at exactly ONE line, the keying site in `_ed_series`'s roll loop, via a new
`_exit_landing_year(roll_start_year) -> roll_start_year + 1` placed beside the arrival trio so the two
labelling translations read side by side. NOT at `market_listings` (it convolves the lag ON TOP of
whatever key it is handed, so a translation there double-counts for every caller) and NOT at
`_listings_at` (a read-side shift leaves the dict's keys meaning start-year while its reader means
end-year, and the next direct reader recommits the bug); both reasons are stated at those two sites.

**BOTH HARD INVARIANTS HELD.** No rank moves — the rank column is identical before and after at all
three scenarios — and ZERO headline signs flip. All 24 `mean_ed_*` move; the largest is **32.44 %** of
its own magnitude (HORS_RMR/reference) and the largest single-year move **1.582×** its row's own
|mean ED| (HORS_RMR/reference/2033). The exact identity reproduces at **mean residual 1.607e-19** over
the 624-cell scan — that figure is a MEAN, not a max (max 1.655e-18) — and the source-computed grid
after the fix is **bitwise identical to the ruled construction at all 624 cells**. Suite 1282 passed
(the original 1280 plus the two new fixtures), root 191.

**THIS AMENDMENT WARNED THE NAMED LIMITS' CONCLUSIONS MIGHT CHANGE IN KIND RATHER THAN MERELY IN
DIGITS. FOR LIMIT (C) THEY DID, THREE TIMES — AND EVERY CHANGE STRENGTHENS THE LIMIT:**
  1. **The OLDEST vertex now reorders TWO pairs and REACHES RANK 4** (LAVAL_RA13 3→4 with HORS_RMR
     4→3, alongside the MTL_RMR 5→6 / MONTEREGIE 6→5 crossing). The page's claim that the youngest
     vertex is the ONLY perturbation on it that moves rank 4 is now FALSE, and is corrected at its own
     line.
  2. **The threshold TIGHTENED, 20.9 % → 17.6 %, and the deciding pair changed hands** — from
     HORS_RMR vs MTL_RMR to LAURENTIDES_RA15_PROXY vs LAVAL_RA13, which is the SAME pair that is now
     the table's narrowest rank-deciding gap. Two independent measurements landing on one pair.
  3. **The multiple INVERTED its reading, 1.08× → 0.91×** (−2.97 pp against #24(A)'s +3.27 pp). The
     retired sentence said a shape effect LARGER than the level fix suffices to reorder; a shape effect
     SMALLER than it now suffices. **The conclusion STRENGTHENS — it does not reverse.**

**(A) AND (B) DID NOT CHANGE IN KIND.** (A)'s ratios, sign-flip set and reorder set are unchanged and
its band is re-measured −3.46e-03 … −5.12e-03 → **−3.35e-03 … −4.92e-03** — it is the one instrument
whose band moves at all, because it perturbs S, the leg this amendment re-labelled. (B) is identical
at every printed digit under both conventions and **structurally so, not coincidentally**:
ΔED = [D_B − D_shipped] / OwnerStock, so S cancels out of the delta algebraically. **The (A)/(B)
convergence claim and the consumer page's ORDER-reliance list both survive UNCHANGED.** Every
instrument was rebuilt from the page's own description and validated by reproducing the published
pre-#27 figures on the OLD convention before being re-run on the new one.

**`q_live_per_year = 0.06` IS A REORDERING AXIS AGAIN.** #24(A) silenced it; this end-labelling revived
it (2 rows), which broke the grid-only union's readability off the emitted counts — and the existing
gate REFUSED exactly as designed rather than reporting a stale union. The union is FOUR rows because
`q_live`'s two are a SUBSET of `phi_voluntary`'s four, a fact no pair of counts could express. The gate
now re-derives the union by RE-RANKING the ED grid at each nonzero non-ratio leg and binds the page's
stated MEMBERSHIP — the form no count can fake. The paragraph asserting #24(A) had SILENCED that axis
is corrected at its own line.

**THE PUBLISHED 2.00e-19 NOISE FLOOR COULD NOT BE REPRODUCED, AND IS RETIRED IN PLACE RATHER THAN
RE-DIGITED FROM A GUESS.** No aggregation of the reconstructed instrument reaches it — max, mean and
median, over all cells and reference-only, across four float summation orders and exact `Fraction`;
the closest was the median at 2.17e-19. It is replaced by **1.83e-18 WITH ITS AGGREGATION NAMED ON THE
PAGE**: the max over all 24 published means across four summation orders. Order-invariance of the rank
vector was re-verified across all five summation methods. **Third time this arc has paid for the
named-instrument rule** — a sensitivity figure without its perturbation is not a measurement.

**ONE FIGURE IS DELIBERATELY LEFT UN-RE-MEASURED, AND IS NAMED RATHER THAN QUIETLY CARRIED.**
`pipeline._standing_stock.__doc__`'s two ED-move figures — arm D **+6.32e-05** and the X1 repair
**+4.28e-05** — are pre-#27 readings of a now-retired series. **The perturbation that produced arm D's
number is recorded NOWHERE**, so reconstructing it would be a fabricated instrument wearing a
measurement's clothes; that is precisely the failure the named-instrument rule exists to stop. They
keep a dated basis note at their own line. Their gate binds their RATIO against the stated `1.5x`, so
they move together or not at all, and their DIRECTION claim (arm D exceeds the repair, hence still
rejected) carries on the ratio alone. A Tranche-2 author re-measuring arm D must re-measure both.

**AMENDMENT #28 (2026-08-23, commissioned first-time-reader sweep over the WHOLE document) —
THIRTEEN LIVE STALE LITERALS, EVERY ONE NOW EDITED AT ITS OWN LINE; AND THE ROLE CONFLATION THAT
KEEPS PRODUCING THEM, NAMED AND DEFERRED RATHER THAN PAPERED OVER.**
Amendments #25 and #26 each caught retractions that never edited their own line and treated them as
instances; #26(D) named the habit. **Naming it did not stop it** — finding 10 below was CREATED
between #26 and #27, inside the same uncommitted bytes, after the naming. So this amendment closes
the class by ENUMERATION instead of by rule: one first-time-reader pass over all 2,214 lines with NO
amendment resolution (the pass that matters, because a reader WITH the amendments applied resolves
each contradiction and correctly reports it dispositioned — that is why this seat's own §10 sweep at
#23(F) came back clean), a correction registry built from amendments #6-#27 and rulings A-X, ~45
candidate literals adjudicated one at a time against that registry, registry-keyed greps for skimmed
instances, and both shipped artifacts read wherever a literal claims an emitted field set.

**THE COUNT, REPORTED EITHER WAY — because only a measured count over an ENUMERATED set closes a
class, where silence leaves it open: 13 live instances against the 4 this seat knew of. SIX are
act-wrong** (a reader who follows them builds the wrong thing), seven mislead or cite wrongly.
Every one is corrected AT ITS OWN LINE, with the retracted words QUOTED at the site so the corpse
stays recognisable to the next reader — the sweep confirmed that quoted-and-labelled corpses are
correctly NOT flagged, which is what makes the quoting safe.

**THE TWO THAT MATTER MOST.** (1) **§7's run contract named a central scalar the headline never
computes** — "immigrant ratio band center", on the DOMINANT axis, whose endpoints each displace rank
1. Rulings S/T measured that ratio PER GEOGRAPHY and it has no central value at all; an implementer
following the retracted words runs the headline at roughly 0.594 against the ruled 0.96-1.11. This
repo's ratification practice includes from-scratch reimplementation FROM THIS DOCUMENT, so that
paragraph has real implementers. (2) **#20(B)'s rank-reliance clause had INVERTED against the
shipped page.** It said ranks 1, 2, 3, 5, 7 and 8 hold; after #24(A) re-based the grid, the
test-bound consumer page reports the rows that clause named as holding among those a consumer must
NOT rely on, and a rank it omitted among the few that do. A consumer taking reliance guidance from
this spec got the OPPOSITE of the tested record. Both are corrected; the second is corrected by
POINTING at the test-bound span rather than by restating a verdict the #27 cascade moves again.

**WHAT THIS SWEEP STRUCTURALLY CANNOT SEE, stated so the count above is honest:** (a) a correction
the pass failed to recognise AS a correction, and (b) two body sentences contradicting each other
with NO amendment mediating — neither is reachable from a registry keyed on amendments. A confirming
round is scoped to exactly those two classes and sequenced AFTER this amendment and the #27 cascade
land: running it sooner re-litigates bytes about to be edited twice. It doubles as the fresh-context
verification of this amendment's OWN thirteen edits, which this seat authored — **a verifier inside
the fold shares the fold's blind spot.**

**THE CLASS DIAGNOSIS, and why it is NOT fixed here.** This document is simultaneously an
APPEND-ONLY AUDIT TRAIL — amendments are historical and must stay quotable exactly as written — and
a NORMATIVE IMPLEMENTATION CONTRACT read top-to-bottom by reimplementers. Those roles pull opposite
ways: the trail wants sentences frozen, the contract wants every line currently true. **Thirteen
findings is the tax on conflating them, and it is charged per audit round.** The fix is NOT a third
copy of the live rules inside this document — that is precisely the two-copies-drift failure, and the
consumer page's marked spans already ARE the test-bound current-truth surface, re-derived at every
mint. Recorded instead as a **TRANCHE-2 OBLIGATION on the next spec this seat writes: separate the
amendment log from the normative contract from day one, and have the contract POINT AT test-bound
spans rather than restate them.** Deliberately not restructured now — this document is days from a
publish branch, fifteen audit rounds have converged on its line anchors, and a restructure would
reset every one of them while buying nothing on a document about to freeze.

**PROVENANCE, because a finding set is only as good as its verification.** The sweep was commissioned
by this seat and run by a peer session with no stake in this document's history. **No finding was
landed on the peer's word:** the seat confirmed all 13 literals against the file, and seven against
ground truth OUTSIDE it — finding 1 against `pipeline.py`'s `None`-central branch, finding 2 against
the shipped `tripwire_baseline.json` (ten keys on every indicator row, against an eight-member
allowlist this document called exact), finding 4 against the shipped NAMED-LIMITS span, finding 8
against #13's own table row (HORS_RMR's aligned ratio 1.0248), finding 14 against the shipped
`assumptions_hash` **(numbering note, amendment #30: these citations use the SWEEP'S internal
F-numbers, which run to fourteen because the fourteenth landed as the #18(E) housekeeping
scope-line rather than as a numbered finding — the published enumeration above closes at
thirteen, and codex round 16 read "finding 14" against it with no way to map the two)**. The peer's two proposals this seat did NOT take verbatim are recorded as such:
its paste text for finding 4 restated the current reliance verdict, which the #27 cascade would
stale within days, and its finding-9 wording detached the `§7` pointer from the claim it qualifies.

**THE THIRTEEN, each corrected in place:** (1) §7 run contract, the immigrant-ratio central scalar
[ACT-WRONG]; (2) §7's tripwire allowlist, missing #21's `freshness_years`/`source_kind`, together
with the "field sets equal the allowlists exactly" claim that made the omission bite [ACT-WRONG];
(3) #20(C)(3)'s superseded MUST over `now`, which rebuilds the exact token #22(C) retired
[ACT-WRONG]; (4) #20's rank-reliance inversion plus a dated scope over every pre-#24(A) figure in
(A)/(B) [ACT-WRONG]; (5) §6's superseded HORS_RMR resolution rule — and ruling S's pointer to it
said "above" when the literal sits ~300 lines BELOW, which is why four later sweeps never reached it
[ACT-WRONG]; (6) §7(b)'s three-member identity refusal, named false by #24(C) and left standing
[ACT-WRONG]; (7) #12(B)'s unmarked "NOT to be fixed" header, reversed by #13(B); (8) the netting
discount's member list and its bare "~4-11%", now two members not three; (9) §1's restatement of the
schema-prohibition overstatement #25(B) qualified only at the header; (10) #26(C)'s "no external
consumer" framing, corrected before those bytes ever committed; (11) §10's fail-loud bullet, whose
obligation #23(F) had already ruled unverifiable-as-written; (12) "BOTH named limits" where there are
now three; (13) #20(C)'s "exactly three optional members", recorded false by #22(B) without editing
the line that says it. Housekeeping, same pass: #18(E)'s ratified table and hash now carry a scope
line marking them as that mint's, not the standing output.

**AMENDMENT #29 (2026-08-23, the P10 citation read moves onto the public record) — THE SHIPPED
SUITE NOW READS NOTHING OUTSIDE WHAT SHIPS, FOR THIS COUPLING.** `run_p10.py`'s
`_guard_citation` verified eight recomputed figures against the Task-26 QFE re-triage record,
which had resolved into an internal verification record — a document
that never ships, which made every test exercising that coupling unrunnable from any checkout
that does not carry internal ledger files, and made the guard itself unverifiable by its public.
The bracket figures now live in their own **public measured record**
(`docs/research/2026-08-15-task26-hors-residual-bracket-record.md`, landed 2026-08-24), authored
INDEPENDENTLY of the probe's own emission so the cross-document check remains a check that can
fail; the probe reads it (`_qfe_record` → `_bracket_record`), and the record's closing rule
stands verbatim: **never update this record to make a red go away** — a digit changed here must
be justified at the spec and re-measured against 98-10-0622-01. The dispatch file remains the
historical audit trail of the re-triage decision; this coupling no longer reads it.

**AMENDMENT #30 (2026-08-24, codex cross-family round 16 — the confirming round #28 scoped) —
TWO UNMEDIATED CONTRADICTIONS, BOTH CORRECTED AT THEIR OWN LINE; ZERO CLASS-A FINDINGS; THE
LOOP CLOSES.** Round 16 ran under exactly the scope #28 mandated: a first-time-reader pass
reporting only (a) corrections unrecognisable as such and (b) body-vs-body contradictions with
no amendment mediating. It returned **zero class-A findings**, two class-B: the rate-consumer
enumeration here above ("exactly three" under a four-bullet list, X1/X2's additions never
re-measuring the count), and this document's own provenance paragraph citing "finding 14"
against an enumeration of thirteen (sweep F-numbering, unmapped). Both corrected in place;
both corrections quote their corpses. Coupling verification also passed: the P10 probe reads
the public record and every required figure literal is present verbatim. **With round 16
returning no shipping defect and its findings folded, the codex loop is declared DRY at round
16, per its own stopping rule.**

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
mixed-identity row sets; contract-tested with a two-vintage mixing RED. **QUALIFIED BY #24(C) +
#26(B), 2026-08-23:** pair-identity comparison has FOUR members — add `schema_version`, which the
pairing token is blind to by construction — plus `run_pairing` as the CONTENT half. The trio named
here cannot refuse a schema_version-only or a code-only mismatch.

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
band_low, band_high, status, reason?, freshness_years?, source_kind?} (the last two OPTIONAL per
amendment #21, 2026-08-22 — measured, every shipped indicator row carries TEN keys) with `reason` drawn from a CLOSED machine-token enum {stale,
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
sets equal the allowlists AS AMENDED exactly (**#28:** amendment #21's two optional per-row members
are IN the tripwire allowlist — a validator built from the pre-#21 literal refuses every shipped row) AND every enum-typed value is a member, with RED fixtures adding
a `crash_probability` field AND smuggling `"crash_probability=0.35"` through flags[]/reason — all
independent of the goldens. Epistemic limit (codex r10-F1, same class as r4-F4): field allowlists
bind VOCABULARY, not value semantics — no schema proves a number in an allowed field was derived
conditionally; that guarantee lives in the single derivation path (the version-stamped mapping
module is the only producer of tilt/drift values, origin-asserted in the Tranche-2 emitter tests)
plus review. Named, not hand-waved.

**Amendment #17 / seat-ruled 2026-08-19 — a NON-FINITE band endpoint is a RUN-LEVEL TERMINAL, not an
UNKNOWN record.** The value-integrity rule above sends an inverted band to UNKNOWN, and the
implementation extended that to non-finite endpoints — but `_unknown_measured` passes the offending
endpoint through UNCOERCED into `band_low`/`band_high`, and the contract validator REJECTS exactly
that record because §7 emits with `allow_nan=False`. Four of the five malformed-band sub-cases
(±Inf and NaN on each endpoint) therefore died at the contract boundary with a bare `ValueError`
instead of producing a record. **The third producer/contract seam of this build**, one branch over
from amendment #16's and found by the pre-PR data-integrity gate. The band is the CALLER's, injected,
so a non-finite band is a caller/config defect — deterministic, independent of the feed — which is
the shape of a terminal, not of a per-indicator UNKNOWN; and the module already ruled the sibling
case this way, raising a named terminal for a NON-COERCIBLE endpoint on the grounds that it cannot
ride the record's float-typed fields. A non-finite endpoint cannot ride them either. **The FINITE
inversion case (`lo > hi`) is UNCHANGED and keeps its UNKNOWN(`malformed_band`)** — it serializes, so
"inverted band → UNKNOWN" above stays exactly true. No `Reason` member is added and the record
allowlist is untouched; the refusal moves to where `check_registry`'s run-level terminal already
lives. Pinned by the generalized seam test: every record each producer can emit must validate against
its contract validator, parametrized over the full sub-case set.



**Amendment #16 / seat-ruled 2026-08-19 — `duplicate_indicator` JOINS the nullable reasons.** The
nullability rule above enumerates four reasons; `duplicate_indicator` was left out while
`missing_indicator` was included, and the two are produced by the SAME function on the SAME branch.
`check_registry` emits a duplicate record with `current_value` and `as_of` both null — it has no
honest measurement, exactly the r7-F2 logic that put the other four in — so that record FAILED the
contract validator's non-null branch. **The producer and the contract disagreed, and no test crossed
them**, which is the same seam class as the 64-vs-16 assumptions-hash width run 30 found one module
over. Unreachable in practice only because nothing in Tranche 1 currently emits a duplicate, which is
a property of today's callers and not of the contract. The nullable set is therefore
{`source_unavailable`, `operator_input_missing`, `missing_indicator`, `non_finite`,
**`duplicate_indicator`**}, and the seam is pinned by a test asserting that every record
`check_registry` can produce validates. No `Reason` member is added — the enum already carried this
token; only the nullability set moves.


**Amendment #15 / RULING U (seat-ruled 2026-08-18) — the WIRED indicator's completeness contract is
MEMBER-SET, not month-presence.** This section pinned the tripwire RECORD contract and left
completeness to the implementation, which chose "twelve distinct months on the selected year". That
check is a UNION over members and two members satisfy it: measured on the 2026-08-18 vintage, a feed
truncated to the two modeled CMAs publishes the Montréal+Québec PAIR total (45,895) as the PROVINCIAL
realized, status OK, exit 0, against a true provincial 60,010 — the scope confusion this section's
own SCOPE rule forbids, re-entering through a data path rather than a literal. **A plan-governed year
is CLOSED only when (i) all twelve month tokens are present province-wide, (ii) each MODELED member
carries all twelve, and (iii) every member of a CODE-OWNED REQUIRED SET is present with at least one
cell.** The required set is the cross-year INTERSECTION of the feed's Quebec members — 31 across all
twelve published years (2015–2026), with `Hawkesbury (Quebec part)` OPTIONAL because it appears in
only 6 of 12 — checked as `REQUIRED ⊆ present`. It is the LARGEST set that clears every real year,
which is what makes it earned rather than tuned, and it closes all eleven real closed years including
2020 (provincial 25,005, the historical minimum, all 31 published). **A threshold was considered and
REJECTED on that anchor:** 2020's collapse is 38% against 2019 (40,315 -> 25,005) and 58% under
2025's 60,010, and any cell-count or annual-total floor loose enough to admit a swing that size also
admits a large truncation. The member set admits 2020 and refuses the truncation because it asks WHO
reported, not HOW MUCH. The subset direction is deliberate — a delineation ADDITION still
closes and still sums provincially; a removal or rename reds to UNKNOWN, because a structural change
in the feed is when a human must look. **Named residual, with its assumption stated:** non-modeled
members carry a PRESENCE bar rather than twelve-of-twelve, because 11 of 32 members show interior
month gaps in the real 2025 data; that bar rests on the reading that an unpublished month means zero
landings (the feed publishes `--` for 1–5 and omits true zeros), which is an INFERENCE about IRCC
publication behaviour and NOT a documented IRCC statement. The reason enum is unchanged — the
truncation state surfaces as `source_unavailable` like every other empty-closed-years cause, so the
RUN LOG must name member-set truncation or a reader cannot tell a pre-era refusal from a gutted feed.


**Scenario-named fan fields (codex r6-F6 — scenario identity vs min/max are DIFFERENT semantics
and can cross):** `mean_ed_low` / `mean_ed_high` are SCENARIO-NAMED — the Faible (D2026) and Fort
(E2026) scenario means respectively, whatever their numeric order; the ranking tiebreak uses the
scenario-named Faible mean; any min/max "fan envelope" is derived at display time, never stored.
A scenario-crossing fixture (Faible mean +0.02, Fort mean −0.03) pins the field semantics.

**Run contract for banded assumptions (codex r8-F1 — bands alone leave the run underdetermined;
two conforming implementations must not emit different rankings from identical data):** a Tranche-1
run evaluates every banded assumption at its declared CENTRAL value — q_live 0.085/yr flat
age-shape, φ_market voluntary 0.9 / estate eventual 0.725, estate lag L=2, and the immigrant ownership ratio
read PER GEOGRAPHY from the ruled join table of section 6 (**CORRECTED 2026-08-23,
amendment #28:** this read "immigrant ratio band center", which rulings S/T retired. The ratio is
measured per geography and has NO central scalar: `_ed_series` carries
`immigrant_ownership_ratio: float | None` holding `None` at the headline, and the uniform override
over `CONSTANTS['immigrant_ownership_ratio_sweep_span']` is SWEEP-ONLY. An implementer following the
retracted words computes the DOMINANT axis at roughly 0.594 instead of the ruled per-geography
0.96-1.11) — as the headline; band ENDPOINTS enter only through the mandated robustness sweep, reported
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
any re-mints the artifact BY DESIGN;
**QUALIFIED BY AMENDMENT #26(B), 2026-08-23 — that tuple is INPUT identity and is NOT unique over
payloads.** Every member of it is an INPUT declaration, and amendment #22(C) established by
measurement that a code-only computation change touching no constant, no data byte and no schema
REORDERS the published ranking while all four stay fixed. So the tuple can collide across materially
different payloads, and the sentence above is true only of what it can see. **The emitted
`run_pairing` is the CONTENT half** — deterministic over both documents' canonical payload digests,
so it moves whenever either payload moves, for any cause. Read artifact identity as **the tuple PLUS
`run_pairing`**; the tuple alone answers *which inputs*, never *which computation*. This is the same
correction #25(B) applied to §1's schema claim and #23(E) to the pairing protocol: an identity
statement that predates the token it needs. S4b runs record which artifact they consumed (hde side, S4b
design's obligation). ISQ edition refresh does not silently change outputs (pins). A future cron for
tripwires would be a new operational surface — explicitly out of scope of this spec.

## 10. Testing

TDD throughout. Anchors:
- **Oracle-anchored cohort math**: hand-computed 2-cohort, 3-year example (fixture with the full
  arithmetic in comments); transition identities (state mass conservation: every household ends in
  exactly one of {remain, widowed, dissolved, exited}).
- **RED calibration gates**: a config that double-counts mortality MUST fail the **ORACLE-EXACT
  roll-forward mutation test** — **RE-POINTED IN PLACE BY AMENDMENT #25(A), 2026-08-23. The words
  that stood here, "MUST raise CalibrationError (reconciliation gate test)", were RETRACTED by
  amendment #22(A) and this line was not edited to match**, so the literal checklist kept demanding
  a RED that cannot exist while the retraction sat 600 lines away. The reconciliation gate's
  [0.20, 0.40] band catches GROSS double-counting only and is NOT a proof of exactly-once: the
  central doubled-decrement retention is 0.3001, mid-band, and ruling O confines the gate to the
  central run — so the gate returns None exactly where this bullet demanded it raise. Independently
  re-confirmed by a §10 sweep that was not looking for it: under a double-decrement mutant, ten
  oracle tests go RED while `tests/test_reconciliation_gate.py` stays FULLY GREEN.** A q outside
  [0,1] MUST raise, and that half is unaffected.
- **Codex-fold fixtures (round 1 F1/F3/F4/F6 + round 2 F1–F5)**: persons→households initialization
  — all-coupled fixture (100+100, 60% → 60 Couple / 0 Solo / 0 Other) AND the general-case fixture
  (200 persons, 0.25/0.80 → 50 Solo + 60 Couple + 30 Other, persons reconcile 200); competing-risk
  partition (0.20/0.08/0.72, sums to 1); dimensional headship test (100 arrivals as 50 couples vs
  100 singles → DIFFERENT D); hand-worked ED fixture (unique value, estate-lag boundary crossing,
  and — amendment #27 — an EXPLICIT WINDOW LABEL on every operand, so a one-year event-time offset
  on either leg REDS instead of passing as two bare unlabelled numbers) +
  ranking fixture (unique ordering, exact tie, scenario crossing); sex-code orientation guard RED
  (swapped 1↔2 map must raise on the 85+ female-excess check) + code-3 exclusion test; couple
  matching fixtures (codex r3-F1 + r4-F1): coupled 100 vs 80 → exactly 80 Couple + 20 excess→Other
  (never 90 averaged); 20 vs 100 → **RETRACTED BY AMENDMENT #23(C): the per-band imbalance is
  RECORDED, NOT GATED — no CalibrationError, `match_couples(20.0, 100.0)` returns
  `(20.0, 0.0, 80.0)` and the imbalance 0.8 rides the result as a diagnostic**; 0 vs 0 → 0 Couple, no
  error, no division; post-match per-sex conservation asserted in all three; tripwire completeness + value-integrity REDs (empty registry, missing required
  indicator vs the CODE-owned set, duplicate key, NaN/±Inf/non-numeric current value, future
  as_of, inverted band → nonzero, never exit 0); Tranche 2 adds one RED fixture per ScenarioPrior integrity rule (missing row, duplicate
  key, NaN, inverted band, negative tilt, unknown enum, value-bearing/unknown flag string). The
  double-decrement mutation test rides the cohort-engine build task.
- **Loader pins**: recorded sha256 fixtures; schema-drift fixture (mutated sheet) MUST raise; the
  fail-loud claims are held by the **#23(F) binding form** — every `raise LoaderError` /
  `raise CalibrationError` site reachable from a public loader entry point carries a RED in `tests/` —
  with stress-tester's PR-time pass (load-bearing-claim tag) as the adversarial SUPPLEMENT. #23(F)
  ruled the bare "adversarial pass at PR time" wording UNVERIFIABLE-AS-WRITTEN: it names no closed
  set, so nothing could be checked against it.
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

Handed off to the main steering seat per steering routing.

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
