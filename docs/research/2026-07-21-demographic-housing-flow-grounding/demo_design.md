## Québec/Montréal Demographic Housing-Flow Model — Defensible Design

The whole point of this literature is that demographic demand identities are not price forecasts. Every canonical model in this class (Mankiw-Weil, the US "silver tsunami") failed because it treated a partial-equilibrium cohort story as a closed system while supply elasticity, financing (rate lock-in), income, and migration all moved the opposite way. So the deliverable is NOT a crash forecast. It is a **scenario-conditioning engine** that converts the one genuinely-exogenous, decision-relevant Québec lever — provincially-controlled immigration levels — into an explicit price-drift/shock-probability fan that S4b consumes as priors. Its defensibility comes from (a) never emitting a point number, (b) carrying a financing-friction term the failed models lacked, (c) resolving geography instead of aggregating (the Japan/Montréal-vs-Québec-City bifurcation lesson), and (d) being honest that its headline output is dominated by non-identifiable priors.

---

### 1. FORMAL MODEL SHAPE

Annual net-flow accounting for owner-occupier housing in geography g, dwelling type d, year t, under ISQ migration scenario s ∈ {low, reference, high}. Core identity, per (g,d,t,s):

    Excess-demand fraction  ED = [ D_owner − (S_market + C_construction) ] / Stock

where positive ED → upward price-pressure prior, negative → downward/crash-risk prior. ED is then mapped through a reduced-form elasticity layer (Section 3) to a drift/shock prior — it is NEVER read as price directly.

**Supply side — owner exits (the "sell/transfer wave"):**

Start from owner-households by age-of-reference-person a, at base year, O(a,g,d,t0), from Census tenure×age-of-maintainer cross-tabs. Roll forward, then apply a **multiple-decrement (competing-risks) exit process**. Three competing exits:
- q_mort — mortality, from CIA CPM2014/CPM-B (actuarial-system).
- q_ltc — LTC/morbidity-driven move (to care facility / with family).
- q_down — voluntary downsizing/relocation (sell to rent or smaller).

Combined via independent competing hazards: annual exit prob = 1 − exp(−(μ_mort + μ_ltc + μ_down)), with a multiple-decrement table allocating exits by cause (needed because the cause drives the transfer-vs-sale split downstream).

**CRITICAL — the decrement is at the HOUSEHOLD level, not the individual.** An individual death in a couple-owner household does NOT vacate the unit; the surviving spouse retains. So mortality enters through last-survivor / joint-life logic on coupled owner-households (single-life for solo owners), using couple-vs-solo composition by age from Census. Individual-death ≠ household-dissolution ≠ unit-vacating. This is the load-bearing actuarial subtlety and the reason actuarial-system's individual-scalar mortality API is insufficient as-is.

**CRITICAL — mortality must be counted ONCE, not three times.** Death is latently embedded in three candidate inputs: (i) ISQ *household* projections (which already shrink elderly households via headship/dissolution dynamics), (ii) the explicit CPM2014 decrement, and (iii) the CMHC/Myers empirical selling/retention anchors. Stacking them double- or triple-counts the sell wave and inflates exactly the crash conclusion the model exists to estimate. Resolution — a NAMED FORK that must be decided at design lock:
- **Fork A (recommended):** consume ISQ *population*-by-age (not households), apply own headship + ownership propensity + all three decrements. Mortality applied exactly once (ours, from CPM2014). More assumptions, but clean provenance and no hidden death.
- **Fork B:** consume ISQ *household* counts as the stock, and the decrement model only *decomposes and times* exits (cause-split for the estate-lag convolution + last-survivor unit-retention) rather than re-reducing counts — mortality is ISQ's, not re-applied.
Fork A is preferred because it keeps mortality basis, headship, and ownership all explicit and Québec-calibrated. Either way, the design must not silently assume both.

**Transfer-vs-market-sale split with estate-to-market conversion lag:** exits do not all become listings a buyer competes for.
- φ_market(cause): fraction hitting the open market promptly (voluntary downsizing ≈ immediate listing).
- φ_estate: death/LTC exits pass to heirs; of those, a fraction eventually lists after lag L (heir-retention hazard), the rest retained. Directional prior only (Trust&Will: ~73% of inherited eventually transact, ~27% retained; heir-retention buys DELAY, not permanent absorption — most inherited homes eventually list).
- Estate pipeline as a convolution: S_market(t) = φ_market·E_voluntary(t) + Σ_τ φ_estate·convert(τ)·E_death+ltc(t−τ).
- Registre foncier mutation counts (admin-region, cause-blind) = a coarse validation check on total modeled turnover.

**Demand side — two streams:**
- Native household formation: net new owner-households from domestic population (ISQ headship rates by age × ownership propensity by age). Embeds domestic aging.
- Immigrant/NPR demand: immigrant cohorts by landing year × a tenure-transition curve ownership_rate(YSL, admission_class) — immigrants land as renters and convert to owners over ~5–15 yrs on an S-curve. Inflow volumes from IRCC PR-by-CMA + MIFI PR/temporary-resident thresholds, under the three ISQ variants. This is the offset the entire exercise measures.

D_owner(g,d,t,s) = native_formation + Σ_cohorts Immig(c, t−YSL, s) × Δownership_rate(YSL, class) × dwelling_choice(d).

**Geography & dwelling type:** resolve Montréal RMR (island core) vs. off-island (Laval, Montérégie MRCs) vs. Québec City RMR — never aggregate (Japan lesson; and the within-Québec inversion where Montréal is projected to SHRINK ~4.5% while Québec City grows ~21%, opposite the Tokyo/NYC "core = safe" intuition). Plex (2–5 unit) is a distinct d. Two plex nuances: (1) plex demand is partly investor/yield-driven (rate-sensitive), and the household-flow model captures only the owner-occupier slice — investor demand is an out-of-model rate-sensitive driver that must be flagged, not silently omitted; (2) the distinctively Québec channel is the immigrant owner-occupier-landlord buying a plex to live in one unit and rent the rest — a demand pathway the ROC ownership curve does not capture, connecting the immigrant demand stream directly to plex dwelling type. Folding this in is what makes the "first Québec-specific synthesis" claim real rather than a ROC model with a haircut.

**Financing-friction term (what killed Myers' timing):** a rate lock-in multiplier on q_down (and partially q_ltc): each 1pp of market-rate premium over a cohort's origination rate cuts sale probability ~18%. Without this the model repeats Myers' error of predicting an exodus that rate lock-in suppresses. Financing regimes change faster than demographics and can dominate the near-term sign.

---

### 2. IDENTIFIABLE vs ASSUMPTION (with leverage)

**Identifiable from data:**
- Owner-households by age/geography at base year — Census tenure×age-of-maintainer (free at CMA/CD; CT-level requires paid custom tabulation).
- Household/population roll-forward by age/geography/scenario — ISQ projections, RMR/MRC, 2021–2071, 3 migration variants. Directly identifiable, scenario-bearing. (Finest = MRC; Montréal boroughs NOT projected.)
- Mortality decrement q_mort — CIA CPM2014/CPM-B, fully Québec-calibrated (actuarial-system).
- Immigration inflow volumes — IRCC PR-by-CMA + MIFI PR/temporary-resident plans (CMA granularity only, no CT; suppressed <5).
- Physical stock incl. plex — Ville de Montréal rôle d'évaluation, parcel-level CUBF, but ZERO owner-demographic fields.
- New construction — CMHC HMIP starts/completions (CMA floor).
- Total transfer volume (validation) — Registre foncier mutations, admin-region, cause-blind.

**Assumptions / priors (leverage-ranked, highest first):**
1. **ED→price-drift/shock elasticity map** — NOT structural. The literature's cardinal warning: demographic demand ≠ price because supply elasticity, rates, income are endogenous. Highest leverage, least identifiable → forces wide bands and is the reason output is priors not forecast.
2. **Immigrant ownership-by-YSL curve for Québec** — CHSP excludes Québec entirely (structural, not a lag). Borrow from ROC-CHSP with a load-bearing (not cosmetic) Québec discount: Montréal is the lowest-ownership major Canadian metro, so the Toronto/Vancouver/Prairie ROC curve materially overstates immigrant→owner conversion. Medium-identifiable IF a paid custom Census tab (tenure × landing-cohort × admission-class × CMA) is bought; otherwise a discounted borrowed prior. THIS IS THE DEMAND OFFSET THE MODEL EXISTS TO ESTIMATE — its uncertainty dominates the net-flow sign.
3. **q_ltc / q_down age-curves** — no Québec data. Calibrate to the CMHC survivor-conditional figure (below), wide bands. Sets the size of the exit wave.
4. **Transfer-vs-sale split φ and estate lag L** — only US survey data (non-authoritative), nothing Québec. Governs timing of supply arrival.
5. **Couple last-survivor → unit-vacating link** — household composition identifiable from Census; the "surviving spouse stays now, exits later" timing is an assumption.
6. **Dwelling-choice / plex owner-vs-investor split** — partial from Census; investor slice is assumption.

**Calibration-target discipline (do NOT mix these — they measure different quantities):**
- CMHC 36% (75+, Québec, 2016–2021) is a **5-year, survivor-conditional living-owner sale rate** — it EXCLUDES death (a dead owner isn't in the later census to be counted as "sold"). It maps to (q_ltc + q_down) NET of mortality, and 36%/5yr ≈ ~8.5%/yr — annualize it or the exit rate is ~5× too large.
- Myers retention (0.26–0.31 for 75→85 over a decade) is **all-cause including death** → maps to TOTAL exit, and is used ONLY as a sanity check on the summed decrement, never as the calibration target for the non-mortality curves.
- Reconciliation test: does combined 75+ annual exit (mortality included) reconcile to ≈ 1 − 0.28 over a decade? If it blows past, mortality is being counted twice — the check that catches the fork error.

**Net:** the crash-likelihood conclusion is dominated by items 1–3, which the data cannot pin. That is the honest case for scenario priors over a forecast.

---

### 3. OUTPUT CONTRACT → S4b SCENARIO PRIORS

S4b currently has no principled way to set shock parameters; this model supplies them as **distributions conditioned on ISQ variant**, as a tilt/shift on S4b's existing baseline — never a replacement, never a point forecast.

Emitted object — a versioned parquet/JSON the engine reads, one row per (geography, dwelling_type, horizon_year, isq_variant):

    { geography, dwelling_type, horizon_year, isq_variant,
      demo_drift_mean, demo_drift_p10, demo_drift_p90,   // annualized real price-drift attributable to demographic net-flow
      drawdown_prob_5yr,                                  // P(>20% real drawdown over 5yr), demographically-conditioned tail weight
      excess_demand_fraction,                             // the raw structural signal, for transparency
      assumptions_hash, data_vintage }

Illustrative shape (Montréal plex, 2035): reference immigration → −0.5%/yr [−2.0, +1.0]; low (the realized-2025 Québec drawdown path — natural decrease + NPR cuts) → −2.5%/yr [−5, 0]; high → +0.5%. S4b consumes demo_drift_* as priors on its price-drift generator and drawdown_prob_5yr as a tilt on its shock weights. The three ISQ variants ARE the scenario axis — the model deliberately hands S4b the full immigration-policy fan because immigration is the swing factor and, in Québec, the most exogenous/decision-relevant lever (provincially set, cuttable by fiat).

**Discipline inherited from the mm-infra Y1 memo:** emit a thesis/conditioning signal with wide honest bands; never a captured-dollar or point number. This is a personal-buy-decision + mission-side ("land" vector) tool, not a fund revenue term.

---

### 4. ARCHITECTURE

**Home:** a standalone package that housing-decision-engine imports (the sole consumer). Keeps the decision engine clean and lets the demographic model be independently tested and showcased. Module boundaries:
- `data/` — thin adapters over bulk downloads (Census, ISQ, IRCC/MIFI, rôle d'évaluation, CMHC HMIP, Registre foncier). Mostly files, not live APIs.
- `decrement/` — the multiple-decrement engine; imports actuarial-system.
- `cohort/` — cohort-component roll-forward.
- `demand/` — immigrant YSL tenure-transition + native formation + plex owner-landlord channel.
- `balance/` — net-flow → excess-demand → drift/shock prior (the reduced-form elasticity layer + financing-friction term; explicitly the "danger zone", widest bands).
- `output/` — ScenarioPrior emitter (versioned, hashed assumptions).

**Imports FROM actuarial-system:** the Québec CPM2014/CPM-B tables + get_qx as the mortality leg; a NEW multiple-decrement primitive (below); the Lee-Carter/CBD surface-fitter as a *template* (copied pattern, not import) for fitting q_ltc/q_down hazard surfaces if data ever appears.

**What actuarial-system must ADD (a genuine, reusable actuarial capability — "build the evolution layer, not the pipeline"):**
- A **cause-agnostic multiple-decrement / competing-risks combinator** (`MultipleDecrementTable`) that takes cause-specific hazards (μ_mort from existing tables + externally-supplied μ_ltc, μ_down) and returns dependent decrement probabilities + a by-cause exit allocation. None exists today (grep-confirmed zero decrement/multi-state machinery).
- A **last-survivor / joint-life household wrapper** converting individual mortality to household-dissolution (current API is individual-scalar).
- (Optional but honest) the vectorized cohort batch API + the ContextVar thread-safety fix already in its roadmap, since the model runs many cohorts × geographies × scenarios. Can be looped for v1.
- Boundary crisp: the cause-agnostic COMBINATOR lives in actuarial-system (genuinely reusable); the specific data-starved LTC/downsizing HAZARD CURVES live in the housing module (housing-specific).
- **This is a charter/roadmap EXTENSION requiring explicit operator sign-off, not a silent in-scope expansion.** A housing decrement use is longevity-side (does not trip the P&C gate) but is NOT automatically in scope — no decrement primitive exists to reuse. Upside: it gives actuarial-system its first named external consumer, satisfying its charter's consumer gate positively.

**Why it must NOT couple into mm-infra:**
- mm-infra's demographic-confidence layer is equity-fear-premium / VRP-demand — disjoint on purpose, asset class (US-listed equities vs Québec real estate), geography, and mechanism. The 2026-07-18 Y1 memo already ruled that layer a thesis-signal with NO $/yr capture.
- mm-infra doctrine forbids packages/ importing research/; its demographic code is deleted from HEAD anyway — there is no shared library to couple into.
- Coupling would invent a false money-path linkage (this is personal/mission-side, not a fund revenue term) and risk contaminating fund doctrine with a model that shares only demographic-projection ANCESTRY. Correct isolation = the same discipline the Y1 memo modeled. The only shared thing is method (age-cohort projection + sensitivity bands) — copy the pattern from git history if useful, never import.

---

### 5. EFFORT ESTIMATE & WALKING SKELETON

**Effort to defensible v1 (~10–14 build-sessions):**
- actuarial-system multiple-decrement combinator + last-survivor wrapper (+ tests): 2–3
- Data loaders (6 sources, mostly bulk files): 2–3
- Cohort roll-forward + demand side (immigrant YSL + plex channel): 2–3
- Balance → prior mapping + financing-friction + S4b output contract + wiring: 2
- Calibration, scenario fan, sensitivity, showcase polish: 2–3
**Long-pole external dependency (calendar, not build):** the paid StatCan custom tabulation for CT-level immigrant tenure × landing-cohort. This is a Skeleton-First step-zero PROVISIONING item if CT granularity is wanted; the free CMA-level path avoids it for v0. Procure early or scope to CMA.

**Walking skeleton (thinnest end-to-end slice, ONE live dataset → ONE number):**
Pull the ISQ Montréal-RMR projection file (Fork-A: population-by-age), take the 75+ owner cohort (Census ownership propensity), apply CPM2014 mortality from actuarial-system, and produce ONE number: **mortality-driven owner-household dissolutions, Montréal 75+, 2035, reference scenario.**

- **Load-bearing boundary is the actuarial-system import, NOT the ISQ parse.** The ISQ file is a trivial download; the untested integration reality is whether actuarial-system's get_qx actually fires live against the CPM2014 Québec basis (given its module-level `_active_base` global, single-decrement-only, individual-scalar API). Frame the skeleton's pass/fail as "the actuarial-system import fires live with the Québec basis and returns a plausible q_x curve," not "the ISQ CSV loaded." That is the boundary Skeleton-First wants hit first.
- Then evolve outward one slice at a time: add q_ltc/q_down decrements (calibrated survivor-conditional to CMHC ~8.5%/yr) → last-survivor household logic → estate-lag convolution → demand side (immigrant YSL + plex) → balance layer → S4b prior emission.

**Honest framing for the LinkedIn showcase:** the pitch is "first Québec-specific synthesis of boomer wealth-release vs immigrant absorption" — the literature confirms this synthesis genuinely does not exist for Québec — presented with LOUD uncertainty bands and the immigration-policy fan, NOT a scary crash number. The value is structured conditioning + making the exogenous lever explicit, not a point crash probability.