# QFE re-triage debt — DISCHARGED at the Task-26 fold (2026-08-15)

Standing since the run-5 fold; dispatched seat-side at run 22's close as
`mm-spine:quant-financial-engineer`, read-only, verdict-not-inheritance. Reviewed at `0ad4ac6`.
Filed here because teammate messages do not persist and committed records do — same treatment as the
2026-08-08 DIV discharge.

**Construction validated before any derivation** (this is what makes the rest credible): the QFE's own
WDS coordinate build reproduces P8 §2 exactly (MTL 860,685 / 452,595 / 252,225; QC_RMR 40,545 /
20,490 / 10,965; province 1,007,855 / 527,710 / 298,100), its sub-floor construction reproduces run
22's 5.90 / 5.40 / 5.66 and 5.02 / 5.30 / 4.72 exactly, and the 99,692.3 minimum reproduces.
**The seat independently re-verified the two headline findings live before acting** — see below.

---

## SUBJECT 1 — HORS_RMR rate-territory proxy: **SPLIT VERDICT**

**ownership leg SOUND · immigrant headship SOUND-WITH-NAMED-LIMIT · immigrant ratio NOT-SOUND**

The charter's "second-order" assumption holds for the quantity it was written about and does **not**
extend to the two the rulings added.

**The ownership leg is sound for a better reason than the charter had: ρ CANCELS in ED.** Verified
linear end to end — `owner_stock` (OS ∝ ρ), `native_formation` × `_ownership` (D_native ∝ ρ),
`p_imm`'s `p_nonimm` (D_imm ∝ ρ), `cohort/init.py:226-228` → `roll_one_year` → `market_listings`
(S ∝ ρ). ED = (D−S)/OS is EXACTLY invariant to a band-uniform relative scaling of ρ. Measured
contamination on the analogous all-households propensity is +1.49% (0.6909 → 0.7012) **and it
cancels.** Caveat: `initialize_households` takes a single scalar (the 75+ band) while OS spans all
bands and D_native spans 25-74, so a BAND-VARYING error leaves a second-order residual.
**This is why the ownership rate must NOT be "fixed" — the cancellation is what keeps ED stable, and
re-extracting to chase a cancelling term would be cost with no signal.**

**The immigrant ratio is not sound, and the errors ADD.** h_imm and r_imm are numerator-only, have no
cancellation channel, and MULTIPLY inside D_imm, so their same-signed relative errors compound:
h×r moves 0.49622 → 0.53850, **HORS_RMR's immigrant demand leg understated ≈7.6%–8.5%** across the
bracket. Measured via 98-10-0622-01 (already a ruled one-universe source under T):

| residual variant | settled persons | HEADSHIP | RATIO |
|---|---:|---:|---:|
| as shipped (Gatineau IN) | 84,785 | 0.5169 | 0.9600 |
| − CD Gatineau (2481) | 50,515 | 0.5218 (+0.95%) | **1.0320 (+7.50%)** |
| − CD Gat + Collines | 48,210 | 0.5228 (+1.15%) | 1.0242 (+6.69%) |
| − CD Gat + Coll + Papineau | 47,790 | 0.5218 (+0.94%) | 1.0230 (+6.56%) |

**Why the recorded 12.99% / 14.93% understated it:** those are TOTAL-PERSON weights, but the two new
quantities are immigrant-denominated, and **CD Gatineau holds 40.42% of the residual's `Before 2016`
stock against a 10.35% person weight — 3.9× the recorded figure.** Immigrants concentrate in the one
urban area inside the residual.

**Qualitative, not just quantitative:** 0.9600 → 1.0320 crosses 1.0. Shipped, settled immigrants
UNDER-own in hors-RMR; net of Gatineau they OUT-own.

**Live and ranking-relevant:** `load_immigrant_flows('compo-rmr-base.xlsx')` returns 78 HORS_RMR rows
with real flows (REFERENCE mean 4,669 permanents/yr), so the junction branch fired. Direction: D_imm
understated → ED understated → since rank 1 = most negative = highest risk, **HORS_RMR is ranked more
risky than truth.** A SINGLE-geography distortion, so it gets no order-preservation protection.

**SEAT RE-VERIFICATION (independent, live):** every figure reproduced — shipped 0.5169/0.9600, netted
0.5218/1.0320, +0.95%/+7.50%, ratio crossing 1.0, CD Gatineau at 40.42% of the residual's
Before-2016 persons. The seat also settled the territory question the charter's P2 line made ambiguous:
ISQ's workbook publishes `505 RMR d'Ottawa-Gatineau` (footnote 2, *Partie québécoise uniquement*)
alongside `999 Territoire hors des RMR`, so **the ISQ operand EXCLUDES the QC side while the census
residual INCLUDES it** — exactly as the ownership artifact's `isq_territory_note` already recorded,
and that note explicitly deferred the reconciliation to "the task that joins rate × population".

---

## SUBJECT 2 — sub-floor convention: **NOT-SOUND** (run 22's pricing, on two measured counts)

**(a) THE FLOOR'S STATED PREMISE IS FALSE FOR THE COMMITTED EXTRACT.**
`census_tenure_age_98100231.csv` publishes owner-maintainer counts BELOW 25 at every geography the
derivation reads:

| | 15-19 owner/total | 20-24 owner/total | rate(20-24) | vs rate(25-54) |
|---|---|---|---:|---:|
| Quebec | 1,150 / 10,920 | 17,170 / 106,605 | 0.1611 | — |
| Montréal (CMA) | 615 / 5,075 | 6,080 / 52,120 | 0.1167 | 0.5120 |
| Québec (CMA) | 90 / 1,225 | 1,585 / 13,270 | 0.1194 | 0.5776 |

So `census._zero_support_note`'s "publishes no owner-maintainer rate below 25, so the rate is
UNDEFINED there" — mirrored in `formation.OWNERSHIP_LATTICE_FLOOR` and `owner_stock._ownership` — is
**not a publication absence. It is `_AGE_BAND_SPEC` starting at 25-54.** The asymmetry sits inside one
module: `_HEADSHIP_BAND_SPEC` reads `15 to 19 years` and `20 to 24 years` from the same age dimension
of the same extract, while the ownership spec drops them with no recorded reason — and the drop is
then described downstream as the data's silence.

**SEAT-VERIFIED INDEPENDENTLY:** the extract carries both bands, `_HEADSHIP_BAND_SPEC` (census.py:156)
reads both, `_AGE_BAND_SPEC` (census.py:141) starts at 25-54.

**This is the arc's FOURTH absence-claim-as-a-property-of-the-search instance (rulings F, Q, S), and
the FIRST inside our own code rather than upstream.** Scope: the claim is false for the committed
extract; the headship note's separate under-15 claim remains true.

Re-priced with the rates the extract publishes, δ as % of shipped OwnerStock (REFERENCE): the loose
bound was **~4× too high** — MTL_RMR 5.896% → **1.292%**, QC_RMR 5.402% → **1.067%**, HORS_RMR
4.174% → **1.611%**, RA06 6.806% → 1.504%, RA13 5.662% → 1.239%, RA14/15/16 ≈0.96/0.96/1.03%.

**Near-uniformity FALSIFIED, with the falsifier named:** exact uniformity would give exact rank
invariance, so the SPREAD is what matters — 0.65pp measured across all eight (max pairwise
differential ED distortion 0.647%), but **the two geographies that set the spread were never measured,
and which one sets it SWAPS between constructions** (loose argmax RA06 on young-adult mass; measured
argmax HORS_RMR, whose 20-24 ownership is 0.2789 — rural young adults own far more).

**(b) THE UNPRICED NUMERATOR LEG DOMINATES BY 30×–200×, AND ITS SIGN IS OPPOSITE.** The same
convention zeroes D_native's 18-24 terms — an ADDITIVE hit to the numerator (0.195–0.337% of OS)
against the denominator leg's multiplicative 0.96–1.65%. The two legs are equal in effect only when
|ED| ≈ 19–21%/yr, against an ISQ-implied stock movement of 0.10–0.63%/yr. **For ED < 0 — the decline
regime this module exists to measure — BOTH legs push PESSIMISTIC. Run 22's "OwnerStock understated →
ED overstated → optimistic" is priced on the smaller leg and is SIGN-WRONG exactly where it matters.**
Ranking protection does not carry over: an additive non-uniform shift can reorder where a
multiplicative near-uniform one cannot.

**Tripwires: ZERO exposure** — no §7(c) baseline indicator consumes OwnerStock or ED. Rankings-only.

**Sentence discipline the QFE imposed on itself:** ΔD is an order-of-magnitude BOUND, never a
measurement — it rides the banded headship curve (94.92% of sub-floor OwnerStock mass and ~97.6% of
sub-floor D mass sit in the 20-24 slice inheriting the 20-34 rate), the single-age-inside-a-band reuse
`_zero_support_note` forbids. What survives that contamination is the CROSSOVER, not the level,
because both legs carry the same artifact and it largely cancels in their ratio.

**ORDERING CONSTRAINT, binding:** the sub-floor convention is currently the only thing suppressing the
age-20 band-entry artifact in D_native (21,353 households, 100% of computed D_native being band-entry
mass). Extending the ownership curve below 25 BEFORE an age-resolved headship curve lands would
multiply that artifact into demand instead of zeroing it. **Age-resolved headship FIRST, then the
floor.**

---

## SUBJECT 3 — ruled immigrant inputs: **SOUND-WITH-NAMED-LIMITS**

The settled-member choice is validated against the equations: I2 removes the full surviving arrival
stock from P_resident every year while the chain credits each cohort once at arrival, so a once-credit
REQUIRES an eventual rate, and `Before 2016` is the only published quantity carrying that meaning.

**(i) The cost is stated at the wrong SIZE.** The equation multiplies headship × ratio, but the spec
publishes the factors separately and numbers a different, smaller quantity. As the product:
MTL_RMR settled 0.5067 vs recent 0.1518 (**3.34×**), QC_RMR 0.4503 / 0.1262 (3.57×), HORS_RMR 0.4962 /
0.1406 (3.53×), RA06 0.5976 / 0.1599 (3.74×), RA13 0.5352 / 0.1518 (3.53×). The numbered "~4-11%" is
`1 − ratio`, the netting discount — a different quantity. **LIVE STALENESS:** under ruling T that
sentence no longer covers all five members — at RA06 and RA13 the ratios EXCEED 1, so the "discount"
is a PREMIUM of −7.6% and −11.1%.

**(ii) Containment is by inheritance, not construction.** Task 29's uniform ratio override spans
[0.155, 1.033], scaling each immigrant leg to 0.139×–0.174× headline — below the recent-equivalent
0.268×–0.300×. So the downside IS contained in magnitude, but via P4's borrowed ROC-CHSP year-1 floor
and in a different SHAPE (a uniform override compresses cross-geography differences; the recent
reading is a near-uniform joint move of BOTH factors). Immigrant HEADSHIP has no sweep axis at all.
A `rank_stable` verdict is evidence, not proof, on this axis.

**(iii) Attrition is the load-bearing unnamed assumption, on BOTH sides of the same identity.** The
rate's denominator is survivors AND stayers; the operand is a gross arrival flow, so applying it
implies 100% retention and OVERSTATES the credit. The same gap runs the other way through I2 —
§6 survives arrival cohorts "on the same CPM basis", mortality only — so real interprovincial
out-migration makes the surviving-cohort term too large, P_resident too small, and native D
understated. Partial offset, different magnitudes; `assert_p_resident_nonneg` only trips on a full-cell
contradiction. **What would settle it:** a Québec immigrant-retention rate by years-since-landing
(IRCC IMDB longitudinal, or MIFI présence-au-Québec).

---

## ED equation

**Dimensionally the equation is right and the LABEL is wrong.** D and S are annual FLOWS
(households/yr), OwnerStock is a stock LEVEL, so ED composes as **yr⁻¹** — a net turnover rate. It is
scale-invariant but NOT dimensionless, while `excess_demand.py:10` and spec §7 both say dimensionless.
No numeric error follows (§7's β absorbs the yr⁻¹), but it is the gloss-beside-a-correct-number class.

**MIN_OWNER_STOCK = 1000: SOUND as a structural floor, NOT a plausibility check.** Across the full
frame (744 cells) min 99,692.3, max 1,189,439.0 — exactly 100× below any real value. It correctly
bounds arithmetic pathology in a function that takes a bare float and cannot be geography-aware, and
its zero detection power in the 1k–99k gap costs nothing because those defects are already refused
upstream by `owner_stock`'s absent-rate raises. Change: keep the value, **disclaim the plausibility
reading** in the docstring, and put a geography-aware band at Task 29 where geography identity exists.

---

## QFE's priority order (adopted by the seat)

1. **Subject 2(a)** — cheapest, retires a convention, a bound, a duplicated literal and a false
   sentence at once. **Gated behind the age-resolved headship curve.**
2. **Subject 1's ratio** — one geography, ~8% on its immigrant demand leg, a sign change across 1.0,
   pessimistic, no cancellation channel, measurable from an already-ruled cube.
3. **Subject 3 (i)/(ii)** — sentence-level; no value moves.

Not blocking Tranche 1 by itself: Subject 3's core choice, and Subject 1's ownership leg.
