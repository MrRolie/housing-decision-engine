"""The OPERAND-ALIGNED ownership curve for HORS_RMR (spec §6, the amendment-#12(B) reversal).

WHAT THIS SURFACE IS, and why it exists BESIDE `census.py`'s rather than inside it.
`census.derive_ownership_from_csv` measures every geography's owner-maintainer propensity from
one cube, 98-10-0231-01, at CMA grain. HORS_RMR is the only computed RESIDUAL there — the
Québec province NET of the six wholly-Québec CMAs — and that residual INCLUDES the Québec side
of the Ottawa-Gatineau CMA, because 98-10-0231-01 carries exactly one Ottawa-Gatineau member
and parents it to ONTARIO. The flows this rate multiplies come from ISQ's own hors-RMR row,
which EXCLUDES that territory (ISQ publishes `RMR d'Ottawa-Gatineau` separately, footnoted
*Partie québécoise uniquement*). The rate's territory must match the flow's territory; here it
did not. `census._ISQ_TERRITORY_NOTE` recorded the mismatch on 2026-08-08 and deferred it.

WHY THE FIX IS A SECOND ARTIFACT AND NOT AN EDIT TO THE FIRST. The shipped curve is what
`ownership_by_geo_age.json` publishes and what this repo's external published anchors pin; it
stays byte-identical. The aligned curve lands beside it with an EXPLICIT JOIN — `join` names
every modeled geography and states which curve it reads and why — so no reader has to infer
that HORS_RMR is the only re-pointed row. Seven of the eight geographies were never
contaminated: MTL_RMR and QC_RMR read their own CMA rows directly and the five RA members
borrow MTL_RMR, so none of them contains any part of Ottawa-Gatineau. That is proved at the
SOURCE rather than at the output — the puller checks live that no Québec-part CSD of
Ottawa-Gatineau is also a constituent of any netted CMA (`shared_csd_codes`), because a CSD
that sat in both would be netted out twice and would move a CMA's own denotation.

WHY #12(B) WAS REVERSED (the reason must survive, or a future reader will "restore" it).
Amendment #12(B) cleared this rate from correction on the ground that a BAND-UNIFORM relative
scaling of ρ cancels EXACTLY in ED — true, and premise-conditional. Probe P10 measured the
premise FALSE: on the FOUR-band lattice the model then had, the bands' relative contamination
ran +0.223% to +1.425%, a spread of 1.202 percentage points, all same-signed, and ADVERSARIALLY
arranged — the most contaminated band (25-54) was the one `D_native` is built from, the least
(75+) the one S then RODE through `initialize_households` at `pipeline.ROLL_AGE` — a read
operator ruling X1 has since removed, so that clause is HISTORY and not mechanism — so δ_D − δ_S
sat FAR from zero rather than near it. (P10 wrote that difference as "at or near the FULL
spread". The superlative was READ OFF THE ARRANGEMENT and never measured against `D_native`'s own
weights, so it is carried here as the probe's REASONING and not as a measurement — operator
ruling X7, 2026-08-21. The MEASURED difference is a current-lattice quantity and lives in
`_SUPERSEDES`; nothing is minted into P10's four-band record, whose own words stand unaltered at
`probes/P10-hors-operand-alignment.md`.) ED's numerator is a DIFFERENCE of flows, so
ΔED/ED = (δ_S − δ_OS) + (δ_D − δ_S)·D/(D−S) is AMPLIFIED rather than averaged, without bound
near flow balance, and with the multiplier turning negative for D < S. The absolute-units bound
is real and does not rescue it: rankings are relative and are decided near zero, which is
exactly where that bound is vacuous.

THOSE FOUR-BAND FIGURES ARE THE WARRANT AND ARE KEPT AS HISTORY (P10, 2026-08-15). Operator
ruling W (2026-08-20; spec §8 amendment #18) refined the lattice to SEVEN bands, and the
refutation got STRONGER rather than moving: the retired 25-54 band was averaging a steep
gradient, so on the current lattice the contamination runs +0.242% (75-84) to +3.559% (25-34) —
a spread of 3.318 percentage points, still all same-signed, and still adversarially arranged
with the SAME two roles. `D_native`'s weight now concentrates in 25-34, the MOST contaminated
of the seven — it reads FIVE bands and not one (it sums ages 18-74, so 25-34, 35-44, 45-54,
55-64 and 65-74, never either tail band), and 25-34 is the most heavily WEIGHTED of the five
because `demand/formation._ownership` returns 0.0 below `OWNERSHIP_LATTICE_FLOOR` 25: ages
18-24 contribute EXACTLY zero, so the formation gains pile on the first ages the lattice
admits. S reads the two least contaminated AT SERVED VALUES — 75-84 (+0.242%) and 85+
(+0.253%) — because operator ruling X1 (2026-08-21) stopped `_standing_stock` reading
ownership at `pipeline.ROLL_AGE` at all: the
lumped 75+ bucket is now valued at the POPULATION-WEIGHTED mean of the per-age rates over the
ages it holds, which spans both tail bands. That does not weaken the arrangement, and AT SERVED
VALUES the argument does not depend on a weighting: a weighted mean of two rates is a MEDIANT of
them, so δ_S lies between those two band deltas for EVERY feasible weight, and the whole SERVED
interval [+0.242%, +0.253%] sits below the next-lowest band, 45-54 at +0.273%.

THAT SCOPE IS THE LIMIT AND NOT A HEDGE, AND THE WEIGHTING IS NOT FREE TO CHOOSE (operator ruling
X6, 2026-08-21). The mediant bound is a property of the SERVED values: at the suppression HIGH
corner `85+` alone rises to +0.384%, ABOVE 45-54, so the ordering is not weight-free there. And
δ_S's weights are fixed by the quantity — S's rate is Σ_a pop(a)·ρ(a) / Σ_a pop(a) and the
contamination moves only its NUMERATOR, so each band delta enters δ_S weighted by the OWNER
HOUSEHOLDS that band contributes, pop(a)·ρ(a), never by households and never by plain population.
At the model's own weighting `85+` is 24.147% of the 75+ block (households 21.743%, population
26.450%) and the high-corner blend is +0.276%, which EXCEEDS 45-54 by 0.0029 pp; the
HOUSEHOLD-weighted corner blend clears 45-54 by 0.0005 pp and therefore reports a pass the model
does not have. The limit is documented rather than papered over, and the gate that holds it —
`test_x6_the_tail_ordering_is_a_SERVED_property_and_the_weighting_is_OWNER_POPULATION` in
`tests/test_pipeline.py` — is owner-population weighted for exactly that reason. (The
household-weighted mean of the two SERVED band contaminations, at this artifact's own aligned
household counts 110,150 / 30,605, is +0.244% — one point inside that interval, recorded because
it is the figure this surface's `supersedes` note restates; the owner-population weighting puts
the served blend at +0.244% too, so the SERVED reading is insensitive to the weighting and only
the CORNER is not.) Both figure sets are recorded because a
reversal whose warrant has been silently overwritten cannot be audited: the 1.202 is what the
seat ruled on, the 3.318 is what the run now carries.

THE CONSTRUCTION, in one line:

    aligned(band) = [province − Σ six wholly-QC CMAs]        (98-10-0231-01, the shipped pair)
                    − Σ the 16 Québec-side CSDs of Ottawa-Gatineau   (98-10-0232-01)

98-10-0232-01 is the census-division/subdivision SIBLING of the cube `census.py` reads: the
same `Age of primary household maintainer` × `Tenure` cross, one grain finer, and its Québec
province row is BIT-IDENTICAL to 98-10-0231-01's on the all-ages pair. One universe at two
grains, not a second source — which is what makes subtracting cells of one from the other
arithmetic rather than transport.

WHAT IT DOES NOT DO. It does not extend the curve below 25. Re-extracting the 25+ bands at
aligned territory is orthogonal to the sub-floor question, which spec §7 rules separately
("age-resolved headship first, then the floor") because the sub-floor convention is currently
the only thing suppressing the age-20 band-entry artifact in D_native.

SUPPRESSION IS BOUNDED, NEVER DROPPED. StatCan withholds small counts, and 13 of the 272
requested cells come back unpublished — every one of them a TAIL cell, at 7 of the 16
subdivisions. Since ruling W split the tail those 13 fall into TWO bands rather than one, and
UNEVENLY (re-measured on the committed extract 2026-08-21): `85+` carries 12 of them at those 7
subdivisions, of which FIVE withhold BOTH fields and two (2480140, 2483005) withhold the owner
field only; `75-84` carries exactly ONE — subdivision 2480065's owner field, whose household
field IS published. So the split produced a band, `75-84`, whose suppression is one-sided at
every address it touches, which the four-band union could not exhibit, and the envelope below is
one-sided there in consequence (see FOUR CORNERS). Those 7 subdivisions are small and rural but
they are NOT a size prefix, and the distinction is the reason the composition is gated by
ADDRESS rather than by count: the 7th-smallest subdivision (2482010, 380 households) publishes
every cell, while the 8th-smallest (2480140, 495) withholds one. A count-only gate would pass a
13-cell footprint that had moved to a different set of subdivisions.

Each withheld field is bounded ABOVE by a quantity the same cube
DOES publish at the same geography: the subdivision's own all-ages row MINUS everything it
publishes across the SEVEN bands, i.e. the unpublished remainder, which contains the missing
cell by construction. That remainder ranges over everything the subdivision publishes, so it did
not move when ruling W refined the lattice — but it is now charged to EACH suppressed band
separately, which makes every band's bound individually valid and the collection looser than one
union bound was. Looser is the correct direction for a bound. The bound is FIELD-WISE because
these subdivisions publish one field of a pair and withhold the other: dropping the published one
would net a territory's households out of one denominator and its owners out of another.

FOUR CORNERS, NOT TWO — and the two that bracket the rate are NOT the two that bracket the
subtraction. The SERVED value subtracts only what is published (subtract LEAST on both fields);
`aligned_bound_rate` subtracts every withheld field at its bound (subtract MOST on both). Those
are the two DIAGONAL corners of the withheld-cell rectangle, and they are the two SUBTRACTION
extremes — they are NOT the rate's. rate(s_o, s_t) = (S_o − s_o)/(S_t − s_t) FALLS in the
subtracted owners and RISES in the subtracted households, so the rate's extremes sit at the
OFF-DIAGONAL corners: `aligned_envelope_high_rate` (subtract least owner, most household) and
`aligned_envelope_low_rate` (subtract most owner, least household). Publishing only the diagonal
pair would state an interval the true value can sit OUTSIDE — measured on the current lattice at
`85+`, whose feasible maximum (+0.384%) lies well above the subtract-most/subtract-least pair's
upper end (+0.253%). All four are published; the OFF-diagonal pair is the envelope, and the
diagonal pair is kept because the subtraction extremes are what a reader reconciling counts
needs. (The same defect was first measured at run 25 review on the retired `75+` union, where
the feasible maximum +0.251% sat above the diagonal pair's +0.223%. Ruling W's split moved the
worked example to `85+` because that is now the only band withholding both fields of a pair at
any address — `75-84`'s one-sided suppression cannot produce this shape at all, and its envelope
is correspondingly [low, served] rather than two-sided.)

The two envelope corners are not equally tight, and the asymmetry is recorded rather than
smoothed. The HIGH corner is exactly ATTAINABLE: no cell in this extract withholds its
household field while publishing its owner field, so "every withheld owner at 0, every withheld
household at its remainder" satisfies owner <= total at every cell. For a band that withholds
NO household field the HIGH corner therefore coincides with the served rate — attainable and
tight in the strongest sense, because there is nothing left to vary. The LOW corner is a
CONSERVATIVE OUTER bound, not attained: reaching it would need positive withheld owners inside
cells whose withheld households are zero. An outer bound is what an envelope requires.

THE REVERSAL SURVIVES EVERY CORNER, which is the point of measuring them. On the current
seven-band lattice the spread that refutes #12(B)'s band-uniformity premise runs 3.318-3.499 pp
across the ENTIRE feasible box (3.318 pp at the served corner, 3.368 pp at the subtract-most
corner) — same-signed and adversarially arranged at every one. The narrowest feasible case
EQUALS the served corner here, and that is structural rather than lucky: the most contaminated
band, 25-34, withholds nothing at all, so its contamination is a POINT and no configuration of
the withheld cells can pull the spread down from the top end. The suppression cannot be the
thing that carries the reversal, because no feasible configuration of the withheld cells removes
it. (On the retired four-band lattice the same box ran 1.174-1.241 pp — see the history
paragraph above; the refinement widened it, it did not create it.)

STALENESS REFUSES AT LOAD (steering ruling L), on BOTH sources — an artifact derived from a
stale CSD extract is exactly as wrong as one derived from a stale Census extract — and every
rate is instantiated as a `constants.Anchor` at derivation AND at load, so an undated or
uncited curve serves nothing.
"""
import json
from pathlib import Path

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders import census
from demoflow.loaders.constants import Anchor
from demoflow.loaders.pins import (
    DATA_DIR,
    RAW_SOURCE_MEMBER,
    WORKBOOK_SHA256,
    raw_anchor,
    raw_member,
    verify_pin,
)
from demoflow.loaders.validate import assert_fraction

PRODUCT_ID = 98100232
STATCAN_TABLE = "98-10-0232-01"
MEMBERSHIP_PRODUCT_ID = 98100003
MEMBERSHIP_TABLE = "98-10-0003-01"
EXTRACT = "hors_aligned_csd_98100232.json"
ARTIFACT = "ownership_hors_aligned.json"

# The ONE re-pointed row. Named as a constant rather than spelled inline, because the scope
# fence ("this re-points HORS_RMR ONLY") is enforced against it in three places.
ALIGNED_GEOGRAPHY = Geography.HORS_RMR

# --- the cube's own coordinate vocabulary --------------------------------------------------
# 98-10-0232-01 carries SIX dimensions where 98-10-0231-01 carries seven (no `Condominium
# status`), and its `Household type` member is spelled WITHOUT "census" — resolving by name
# against the wrong spelling returns a different, entirely plausible number.
DIMENSION_POSITIONS = {"Geography": 1, "Structural type of dwelling": 2,
                       "Household type including census family structure": 3,
                       "Statistics": 4, "Age of primary household maintainer": 5, "Tenure": 6}
STRUCT_TOTAL = "Total - Structural type of dwelling"
HOUSEHOLD_TOTAL = "Total - Household type including family structure"
STATISTIC = "Number of private households"
TENURE_TOTAL = "Total - Tenure"
TENURE_OWNER = "Owner"
TENURES = (TENURE_TOTAL, TENURE_OWNER)
AGE_TOTAL_MEMBER = census.MAINTAINER_TOTAL_MEMBER

# `census._AGE_BAND_SPEC`'s own band EDGES, in THIS cube's published age members. The edges are
# the model's and are cross-gated against census's spec; the constituents are whatever each
# cube publishes, and the two cubes publish different granularities of the same partition (9
# age dimension members here against 15 there). Sharing the constituents is therefore
# impossible and sharing the edges is mandatory.
#
# THIS CUBE IS WHY THE MODEL LATTICE IS TEN-YEAR AND NOT FIVE-YEAR (operator ruling W,
# 2026-08-20; spec §8 amendment #18). The 7-band partition below is the FINEST ONE BOTH CUBES
# CAN EXPRESS: of this cube's 9 age dimension members, 8 are age bands and every one at or
# above 25 is TEN-year (`25 to 34`, `35 to 44`, `45 to 54`, `55 to 64`, `65 to 74`) or a
# published tail member (`75 to 84`, `85 years and over`). THAT SENTENCE IS GATED, not merely
# recorded (audit 2026-08-21, which found it stated as verified fact with nothing under it):
# `test_p11_1_band_lattice_is_the_models_own_and_the_two_cubes_partition_it_alike` reads this
# cube's OWN age-dimension member index and declared member count off the committed pull and
# reds if a member appears inside or above the modeled span — so it has no five-year cell to
# subdivide 25-54 with, while 98-10-0231-01 does. Refining the CMA side to five years would
# therefore have left HORS_RMR the ONLY geography still carrying a thirty-year 25-54 band, and
# a lattice difference that lands on ONE geography is a NON-COMMON-MODE artifact — precisely
# the failure mode this whole surface exists to remove (a rate whose territory or grain does
# not match its neighbours' moves the RANKING, which is what the run is for). Measured: with
# HORS_RMR held coarse against a refined CMA side, five of the eight ranked rows move and
# HORS_RMR falls from rank 4 to 6; on this common partition it refines with everything else and
# holds rank 4.
#
# WHAT THE REFINEMENT DID TO THIS CURVE'S OWN SHAPE. The retired `25-54` band was a union of
# THREE members here and SIX there; it is now three separate bands on this side and three
# two-member bands on that side, and the retired `75+` — a two-member union on BOTH sides — is
# now two single-member bands. That last split is the one the suppression footprint sits in:
# the withheld cells are all tail cells, so both `75-84` and `85+` now carry withheld fields
# where one band did before (see `_subtract_band`).
CD_BAND_SPEC = (
    ("25-34", 25, 34, ("25 to 34 years",)),
    ("35-44", 35, 44, ("35 to 44 years",)),
    ("45-54", 45, 54, ("45 to 54 years",)),
    ("55-64", 55, 64, ("55 to 64 years",)),
    ("65-74", 65, 74, ("65 to 74 years",)),
    ("75-84", 75, 84, ("75 to 84 years",)),
    ("85+", 85, 200, ("85 years and over",)),
)
BAND_ORDER = tuple(label for label, *_ in CD_BAND_SPEC)
AGE_MEMBERS = (AGE_TOTAL_MEMBER,) + tuple(m for *_, members in CD_BAND_SPEC for m in members)

# --- the territory -------------------------------------------------------------------------
PROVINCE_CODE = "24"
PROVINCE_GEO_LEVEL = 2
CSD_GEO_LEVEL = 5
CMA_GEO_LEVEL = 503
QC_SGC_PREFIX = "24"
OG_CMA_MEMBER_NAME = "Ottawa - Gatineau"

# The Québec-side census subdivisions of the Ottawa-Gatineau CMA, by SGC code — the territory
# probe P10 resolved and this module's puller RE-DERIVES live before every pull (25 children of
# 98-10-0003-01's CMA member, closing exactly on the CMA's own population, 16 Québec-side by
# SGC prefix AND by census-tree ancestry, agreeing on all 25). Pinned here as well as re-derived
# because a live derivation that silently returned 15 or 17 members would still produce a
# perfectly plausible curve; the pinned tuple is what a drift REDS against.
# Anchor: probes/P10-hors-operand-alignment.md, DECISION-MEMBERSHIP.
QC_PART_CSDS = ("2480050", "2480055", "2480060", "2480065", "2480085", "2480140", "2480145",
                "2481017", "2482005", "2482010", "2482015", "2482020", "2482025", "2482030",
                "2482035", "2483005")
SOURCE_GEOGRAPHIES = (PROVINCE_CODE,) + QC_PART_CSDS

_TERRITORY = (
    "HORS_RMR, OPERAND-ALIGNED: the Québec province NET of the six wholly-Québec CMAs "
    "(98-10-0231-01, the shipped residual) NET of the "
    f"{len(QC_PART_CSDS)} Québec-side census subdivisions of the Ottawa-Gatineau CMA "
    f"(98-10-0232-01, resolved from {MEMBERSHIP_TABLE}'s own geography children of that CMA). "
    "The shipped residual INCLUDES the Québec side of Ottawa-Gatineau because 98-10-0231-01 "
    "parents that CMA to Ontario and publishes no Québec-part row; the ISQ flow row this rate "
    "multiplies EXCLUDES it. Four census divisions contribute to the CMA and no union of whole "
    "ones equals it — CD Gatineau entire, all seven Les Collines-de-l'Outaouais municipalities, "
    "seven of Papineau's and one of La Vallée-de-la-Gatineau's — so the membership is resolved "
    "at CSD grain rather than bracketed by whole CDs."
)
_JOIN_WHY_SHIPPED = (
    "never contaminated: this geography reads its own CMA row (or borrows one), and no part of "
    "the Ottawa-Gatineau CMA lies inside any of them — checked live against "
    f"{MEMBERSHIP_TABLE}'s constituent-CSD membership of the six netted CMAs"
)
_JOIN_WHY_ALIGNED = (
    "the ONLY computed residual, and the only geography whose census territory included the "
    "Québec side of Ottawa-Gatineau while its ISQ flow operand excluded it (spec §6 amendment "
    "#12(A)'s principle: the rate's territory must match the flow's territory)"
)
_SUPERSEDES = (
    "spec §6 amendment #12(B), which cleared this rate from correction on the ground that a "
    "band-uniform relative scaling of the ownership propensity cancels exactly in ED. That "
    "premise is measured FALSE. CURRENT READING, on the SEVEN-band lattice this artifact is "
    "built over (operator ruling W, 2026-08-20; spec §8 amendment #18): the bands' relative "
    "contamination spans 3.318 percentage points (+0.242% at 75-84 to +3.559% at 25-34), all "
    "same-signed, and is adversarially arranged — the most contaminated band (25-34) is the "
    "most heavily WEIGHTED of the FIVE bands D_native reads, and the only two S reads are the "
    "two LEAST contaminated AT SERVED VALUES (75-84 at +0.242% and 85+ at +0.253%). "
    "D_NATIVE READS FIVE "
    "BANDS, NOT ONE (corrected 2026-08-21: the earlier wording, 'the one D_native is built "
    "from', stated a weight CONCENTRATION as an EXCLUSIVITY). It sums ages 18-74, so it reads "
    "25-34, 35-44, 45-54, 55-64 and 65-74, and never either tail band. The weight "
    "concentrates in 25-34 because `demand/formation._ownership` returns 0.0 below "
    "OWNERSHIP_LATTICE_FLOOR 25, so ages 18-24 contribute EXACTLY zero and the formation "
    "gains pile on the first ages the lattice admits (mechanism in `demand/formation.py`). "
    "S does NOT read a band at pipeline.ROLL_AGE: operator "
    "ruling X1 (2026-08-21) values the lumped 75+ bucket at the POPULATION-WEIGHTED mean of the "
    "per-age rates over the ages it holds, so the read spans BOTH tail bands and no single age "
    "selects it (ROLL_AGE still carries the hazard and the living-arrangement read). The "
    "arrangement is therefore WEIGHT-INDEPENDENT AT SERVED VALUES rather than weaker: a "
    "weighted mean of two rates is a MEDIANT of them, so δ_S lies between those two band "
    "deltas at every feasible weight, and the whole SERVED interval sits below the next-lowest "
    "band, 45-54 at +0.273%. THAT SCOPE IS THE LIMIT AND NOT A HEDGE, AND THE WEIGHTING IS NOT "
    "FREE TO CHOOSE (operator ruling X6, 2026-08-21). The mediant bound is a property of the "
    "SERVED values: at the suppression HIGH corner 85+ alone rises to +0.384%, ABOVE 45-54, so "
    "the ordering is not weight-free there. And δ_S's weights are fixed by the quantity — S's "
    "rate is Σ_a pop(a)·ρ(a) / Σ_a pop(a) and the contamination moves only its NUMERATOR, so "
    "each band delta enters δ_S weighted by the OWNER HOUSEHOLDS that band contributes, "
    "pop(a)·ρ(a), never by households and never by plain population. At the model's own "
    "weighting 85+ is 24.147% of the 75+ block (households 21.743%, population 26.450%) and "
    "the high-corner blend is +0.276%, which EXCEEDS 45-54 by 0.0029 pp; the HOUSEHOLD-weighted "
    "corner blend clears 45-54 by 0.0005 pp and therefore reports a pass the model does not "
    "have. The HOUSEHOLD-WEIGHTED MEAN of the two SERVED band contaminations, at this "
    "artifact's own aligned household counts 110,150 / 30,605, is +0.244% — one point inside "
    "that interval, not the bound the argument rests on; the owner-population weighting puts "
    "the served blend at +0.244% too, so the SERVED reading is insensitive to the weighting "
    "and only the CORNER is not. So the band-difference term of "
    "ΔED/ED = (δ_S − δ_OS) + (δ_D − δ_S)·D/(D−S) is LARGE, same-signed and adversarially "
    "arranged rather than near zero — and it is 60% OF THAT SPREAD, NOT AT OR NEAR ALL OF IT "
    "(operator ruling X7, 2026-08-21, striking a superlative this note carried and never "
    "earned: it was read off the arrangement, never measured against D_native's own weights). "
    "MEASURED on the reference scenario's projected years, δ_D = ΔD/D = +2.243% against δ_S "
    "+0.244%, a difference of 1.999 pp against the 3.318 pp served spread. THE #12(B) REVERSAL "
    "IS UNAFFECTED: it needs the difference to be large, same-signed and adversarially "
    "arranged, never maximal — δ_D +2.243% against δ_S +0.244% served and +0.276% at the 85+ "
    "high corner, so the difference stays ~2.0 pp and same-signed at BOTH corners. It is "
    "amplified by D/(D−S), which is unbounded near flow balance and NEGATIVE for D < S. The "
    "absolute-units bound on |ΔED| is true and does not rescue it: rankings are relative and "
    "are decided near zero, which is where that bound is vacuous. "
    "THE WARRANT THE SEAT RULED ON is probe P10's measurement of 2026-08-15, taken against the "
    "FOUR-band lattice the model then carried (25-54 / 55-64 / 65-74 / 75+): a spread of 1.202 "
    "percentage points, +0.223% to +1.425%, most contaminated 25-54, least 75+ — same finding, "
    "same two roles, coarser lattice. It is recorded as that dated warrant and NOT as a current "
    "reading, and it is not deleted: the retired 25-54 band was averaging a steep gradient, so "
    "the refinement made the refutation STRONGER rather than moving it (3.318 against 1.202), "
    "and a reversal whose warrant has been overwritten cannot be audited. "
    "THE SUPPRESSION DOES NOT CARRY THIS: the spread stays strictly positive, same-signed and "
    "adversarially arranged at every corner of the feasible withheld-cell box, not only at the "
    "served point — see `suppression.envelope.band_spread_pp`, which records the box's narrowest "
    "and widest. Do not restore #12(B) without measuring the premise again."
)
_ROUNDING_NOTE = (
    "StatCan rounds every count to the nearest 5, INDEPENDENTLY per cube and per cell. An "
    "aligned band count is therefore a sum of rounded cells: one province cell plus six CMA "
    "cells per 98-10-0231-01 constituent, plus one cell per 98-10-0232-01 constituent at each "
    "of the 16 subdivisions. `envelope_per_field` is 2.5 x that count — DERIVED from the "
    "lattice rather than tuned to an observed delta — and is a worst case in which every cell "
    "rounds the same way. No correction is applied and no reconciliation is asserted."
)
_MULTIPLICAND_NOTE = (
    "WHAT THIS RATE MAY MULTIPLY: owner-maintainer HOUSEHOLDS / total private HOUSEHOLDS — a "
    "household-denominated rate, so its multiplicand is a household count, never a person "
    "count (spec §6, codex r2-F2). Identical in kind to the shipped ownership curve this one "
    "sits beside; only the TERRITORY differs."
)
_UNIVERSE_NOTE = (
    "98-10-0232-01 is 98-10-0231-01's census-division/subdivision sibling: the same "
    "`Age of primary household maintainer` x `Tenure` cross at one finer grain. Their Québec "
    "province rows are asserted BIT-IDENTICAL on the all-ages pair — the identity that makes "
    "subtracting cells of one from a residual of the other arithmetic rather than transport. "
    "The SEVEN BAND rows are NOT asserted identical (four until operator ruling W refined the "
    "lattice on 2026-08-20): the two cubes publish different age granularities of the same "
    "partition — ten-year members inside 25-54 on the CD side against five-year members on the "
    "CMA side — so their banded sums carry independent round-to-5 error. Only the EDGES are "
    "shared, which is why the lattices are joined on edges and never on constituents."
)


# --- helpers ---------------------------------------------------------------------------------

def assert_band_lattice() -> None:
    """The aligned bands must BE the model's bands (`census._AGE_BAND_SPEC`), edges included.

    Two lattices spelled in two modules is a drift vector, and the drift is invisible: a curve
    measured over 25-49 instead of 25-54 is still a plausible fraction at every band. Only the
    EDGES can be shared — the constituents cannot, because the two cubes publish different age
    granularities of the same partition.
    """
    mine = {label: (lo, hi) for label, lo, hi, _ in CD_BAND_SPEC}
    theirs = {label: (lo, hi) for label, lo, hi, _ in census._AGE_BAND_SPEC}
    if mine != theirs:
        raise LoaderError(
            f"{ARTIFACT}: the aligned band lattice {mine} is not the model's {theirs} — the "
            "curve would be measured over different age bands than `ownership_rate` looks up")


def _assert_anchor_typed(rates: dict, provenance: dict, where: str) -> None:
    """constants.py's charter rule, enforced rather than stated: every rate is instantiated as
    an `Anchor` built from the payload's OWN as_of and source, at derivation AND at load."""
    for geo, bands in rates.items():
        if not isinstance(bands, dict):
            raise LoaderError(f"{where}: rates[{geo}] is {type(bands).__name__}, expected an object")
        for band, value in bands.items():
            try:
                Anchor(value=value, as_of=provenance.get("as_of", ""),
                       source=provenance.get("source", ""), unit="fraction")
            except LoaderError as exc:
                raise LoaderError(
                    f"{where}: aligned ownership[{geo},{band}] is not a valid Anchor — "
                    f"{exc}") from exc


def _read_extract(extract_path: Path, verify: bool) -> tuple[dict, dict]:
    """(payload, {(geography_code, age member, tenure): value or None}) from the pinned pull.

    A withheld cell is carried as `None`, never elided: the derivation must be able to tell a
    SUPPRESSED cell (bounded below) from an ABSENT one (a hole the subtraction would net
    around), and a dict that simply lacks the key cannot express the difference.
    """
    extract_path = Path(extract_path)
    if verify:
        verify_pin(extract_path, EXTRACT)
    payload = json.loads(extract_path.read_text(encoding="utf-8"))
    cells: dict[tuple[str, str, str], int | None] = {}
    for cell in payload.get("cells", []):
        key = (cell["geography_code"], cell["age_member"], cell["tenure"])
        if key in cells:
            raise LoaderError(
                f"{extract_path.name}: duplicate cell for {key} — the extract's dimension "
                "address is not unique (payload copied?)")
        value = cell["value"]
        if value is not None and (not isinstance(value, int) or value < 0):
            raise LoaderError(f"{extract_path.name}: {key} carries a non-count value {value!r}")
        cells[key] = value

    expected = {(geo, age, tenure) for geo in SOURCE_GEOGRAPHIES
                for age in AGE_MEMBERS for tenure in TENURES}
    if set(cells) != expected:
        extra = sorted(set(cells) - expected)[:3]
        missing = sorted(expected - set(cells))[:3]
        raise LoaderError(
            f"{extract_path.name}: geography set / cell lattice drifted — "
            f"{len(set(cells) - expected)} unrequested (e.g. {extra}), "
            f"{len(expected - set(cells))} missing (e.g. {missing}). A dropped or added "
            "subdivision changes what the aligned residual DENOTES while every rate stays a "
            "plausible fraction.")

    # The suppression SCOPE, re-checked at derivation and not only at pull time: the bound's own
    # denominator is the subdivision's all-ages row, and a bound over an unpublished bound is
    # not a bound. A withheld province cell is outside the declared scope entirely.
    for (geo, age, tenure), value in cells.items():
        if value is not None:
            continue
        if geo == PROVINCE_CODE:
            raise LoaderError(
                f"{extract_path.name}: the province {age}/{tenure} cell is unpublished — "
                "suppression is a property of tiny geographies, and accepting it at the "
                "province row would let an outage read as a publication rule")
        if age == AGE_TOTAL_MEMBER:
            raise LoaderError(
                f"{extract_path.name}: subdivision {geo} withholds its all-ages {tenure} row, "
                "so the unpublished remainder that bounds its withheld bands cannot be "
                "computed — an interval with no upper end is not one")
    return payload, cells


def _subtract_band(cells: dict, members: tuple[str, ...]) -> tuple[tuple[int, int],
                                                                   tuple[int, int], int]:
    """The 16 subdivisions' counts for one band: (subtract-least, subtract-most, withheld).

    FIELD-WISE, because a subdivision publishes its household count while withholding the owner
    count of the same band: dropping the published one would net a territory's households out
    of one denominator and its owners out of another. The upper bound on a withheld field is
    the subdivision's own all-ages count MINUS everything it publishes across all SEVEN bands
    (four until operator ruling W refined the lattice on 2026-08-20) — the unpublished remainder,
    which contains the missing cell by construction, and which is CLAMPED at zero rather than
    allowed negative by the round-to-5 step. The remainder itself did not move at the refinement
    — it ranges over everything the subdivision publishes, however that is cut — but it is now
    charged to each suppressed band separately rather than to one union band.

    These two returns are the per-field SUBTRACTION extremes, and the caller must not read them
    as the rate's: each field independently lies in [published, published + remainder], so the
    feasible region is a RECTANGLE in (households, owners) and the rate's extremes sit at its
    OFF-diagonal corners. The caller forms all four (see `derive_aligned_ownership`).
    """
    low, high, withheld = [0, 0], [0, 0], 0
    for geo in QC_PART_CSDS:
        totals = [cells[(geo, AGE_TOTAL_MEMBER, tenure)] for tenure in TENURES]
        published = [0, 0]
        band_low = [0, 0]
        band_missing = [False, False]
        for _label, _lo, _hi, other_members in CD_BAND_SPEC:
            for member in other_members:
                for field, tenure in enumerate(TENURES):
                    value = cells[(geo, member, tenure)]
                    if value is None:
                        if member in members:
                            band_missing[field] = True
                            withheld += 1
                        continue
                    published[field] += value
                    if member in members:
                        band_low[field] += value
        for field in range(2):
            remainder = max(totals[field] - published[field], 0)
            low[field] += band_low[field]
            high[field] += band_low[field] + (remainder if band_missing[field] else 0)
    return (low[0], low[1]), (high[0], high[1]), withheld


def _count_empty_complements(cells: dict) -> int:
    """Fields where a subdivision's unpublished remainder is ZERO — the withheld cell is bounded
    AT zero rather than estimated. Recorded because it is the one case where the bound adds
    nothing, and a bound whose zero case is invisible is a bound nobody has seen behave."""
    empty = 0
    for geo in QC_PART_CSDS:
        for field, tenure in enumerate(TENURES):
            values = [cells[(geo, member, tenure)]
                      for _l, _lo, _hi, members in CD_BAND_SPEC for member in members]
            if not any(v is None for v in values):
                continue
            published = sum(v for v in values if v is not None)
            if cells[(geo, AGE_TOTAL_MEMBER, tenure)] - published <= 0:
                empty += 1
    return empty


def _rate(owner: int, total: int, ctx: str) -> float:
    """owner/total with every degenerate named BEFORE the division — a subtraction that carried
    the residual out of the feasible region must surface as LoaderError, never as a
    ZeroDivisionError or a rate above 1."""
    if total <= 0:
        raise LoaderError(f"{ctx}: non-positive household total {total} after subtraction")
    if owner < 0:
        raise LoaderError(f"{ctx}: negative owner count {owner} after subtraction")
    if owner > total:
        raise LoaderError(f"{ctx}: owner households {owner} exceed total {total}")
    return assert_fraction(ctx, owner / total)


# --- derivation (ruling B: the ONLY producer of aligned rates) --------------------------------

def derive_aligned_ownership(csv_path: Path | str, extract_path: Path | str, *,
                             verify_extract_pin: bool = True) -> dict:
    """Compute the operand-aligned HORS_RMR ownership curve from the TWO pinned sources.

    Both are verified against their pins before a single count is read — a derivation run on an
    unpinned vintage breaks the PIT chain while emitting perfectly plausible fractions, which is
    precisely how a retired typed curve once survived in this package.

    `verify_extract_pin=False` exists for the FIXTURE paths only (a synthetic extract built to
    exercise the suppression bound's zero case, and the drifted-geography refusal): it never
    weakens the committed path, where `scripts/gen_hors_aligned.py` calls this with the default.
    """
    assert_band_lattice()
    csv_path = Path(csv_path)
    cube = census.read_totals_cube(csv_path)          # verifies the P2 pin
    payload, cells = _read_extract(Path(extract_path), verify_extract_pin)

    # Universe: the two cubes' province all-ages rows must be BIT-IDENTICAL. If they are not,
    # subtracting cells of one from a residual of the other is transport, not arithmetic.
    sibling_owner, sibling_total = census._band_counts(
        cube, census._PROVINCE, (AGE_TOTAL_MEMBER,), "aligned-universe")
    csd_owner = cells[(PROVINCE_CODE, AGE_TOTAL_MEMBER, TENURE_OWNER)]
    csd_total = cells[(PROVINCE_CODE, AGE_TOTAL_MEMBER, TENURE_TOTAL)]
    if (csd_owner, csd_total) != (sibling_owner, sibling_total):
        raise LoaderError(
            f"{ARTIFACT}: {STATCAN_TABLE}'s Québec province all-ages row "
            f"{(csd_owner, csd_total)} is not bit-identical to "
            f"{census.CENSUS_EXTRACT}'s {(sibling_owner, sibling_total)} — the two cubes are "
            "not one universe at two grains, so the CSD subtraction is a metric transport")

    bands: dict[str, dict] = {}
    rates: dict[str, float] = {}
    for label, _lo, _hi, cd_members in CD_BAND_SPEC:
        ctx = f"aligned-ownership[{ALIGNED_GEOGRAPHY.value},{label}]"
        cma_members = next(m for lbl, _l, _h, m in census._AGE_BAND_SPEC if lbl == label)
        shipped_owner, shipped_total = census.net_of_qc_cmas(cube, cma_members, ctx)
        (sub_total, sub_owner), (hi_total, hi_owner), withheld = _subtract_band(cells, cd_members)
        aligned_owner, aligned_total = shipped_owner - sub_owner, shipped_total - sub_total
        bound_owner, bound_total = shipped_owner - hi_owner, shipped_total - hi_total
        # The OFF-diagonal corners — the rate's actual extremes over the feasible rectangle.
        # rate = (S_o - s_o)/(S_t - s_t) falls in s_o and rises in s_t, so the maximum takes
        # the LEAST subtracted owners against the MOST subtracted households, and the minimum
        # takes the reverse. Transposing these two lines yields a narrower interval that is
        # still feasible-looking and still plausible, which is why the test oracle types both
        # 75+ literals rather than asserting a relation between them.
        env_hi_owner, env_hi_total = shipped_owner - sub_owner, shipped_total - hi_total
        env_lo_owner, env_lo_total = shipped_owner - hi_owner, shipped_total - sub_total
        rates[label] = _rate(aligned_owner, aligned_total, ctx)
        shipped_rate = _rate(shipped_owner, shipped_total, f"{ctx} (shipped)")
        bands[label] = {
            "cd_members": list(cd_members),
            "shipped_households": shipped_total,
            "shipped_owner_households": shipped_owner,
            "shipped_rate": shipped_rate,
            "subtracted_households": sub_total,
            "subtracted_owner_households": sub_owner,
            "aligned_households": aligned_total,
            "aligned_owner_households": aligned_owner,
            "aligned_rate": rates[label],
            "aligned_bound_households": bound_total,
            "aligned_bound_owner_households": bound_owner,
            "aligned_bound_rate": _rate(bound_owner, bound_total, f"{ctx} (bound)"),
            # The ENVELOPE — the off-diagonal corners, which bracket the rate. The diagonal
            # pair above brackets the SUBTRACTION and does not bracket this.
            "aligned_envelope_low_rate": _rate(env_lo_owner, env_lo_total,
                                               f"{ctx} (envelope low)"),
            "aligned_envelope_high_rate": _rate(env_hi_owner, env_hi_total,
                                                f"{ctx} (envelope high)"),
            "relative_delta_pct": (rates[label] - shipped_rate) / shipped_rate * 100,
            "withheld_cells": withheld,
        }
        bands[label]["relative_delta_bound_pct"] = (
            (bands[label]["aligned_bound_rate"] - shipped_rate) / shipped_rate * 100)
        bands[label]["relative_delta_envelope_low_pct"] = (
            (bands[label]["aligned_envelope_low_rate"] - shipped_rate) / shipped_rate * 100)
        bands[label]["relative_delta_envelope_high_pct"] = (
            (bands[label]["aligned_envelope_high_rate"] - shipped_rate) / shipped_rate * 100)

    # The all-ages row, which every one of these subdivisions publishes in full. Evidence only:
    # it is not a model band and is never served, but it is the figure the two cubes agree on
    # and the one the ruled cube's own independent cross corroborates.
    ctx = f"aligned-ownership[{ALIGNED_GEOGRAPHY.value},all ages]"
    all_shipped_owner, all_shipped_total = census.net_of_qc_cmas(cube, (AGE_TOTAL_MEMBER,), ctx)
    all_sub_owner = sum(cells[(g, AGE_TOTAL_MEMBER, TENURE_OWNER)] for g in QC_PART_CSDS)
    all_sub_total = sum(cells[(g, AGE_TOTAL_MEMBER, TENURE_TOTAL)] for g in QC_PART_CSDS)
    all_ages_shipped = _rate(all_shipped_owner, all_shipped_total, f"{ctx} (shipped)")
    all_ages_aligned = _rate(all_shipped_owner - all_sub_owner,
                             all_shipped_total - all_sub_total, ctx)

    # The BAND SPREAD, over the whole feasible suppression box — the figure #12(B)'s
    # band-uniformity premise is refuted by, so it is DERIVED here rather than narrated. Each
    # band's relative contamination is an INTERVAL (a point where no cell is withheld), so the
    # spread is too: it is widest when the most-contaminated band sits at its top while the
    # least sits at its bottom, and narrowest at the reverse. Written for the general case
    # rather than for "only 75+ has holes", because a re-pin can move the footprint.
    rel_lows = {label: min(b["relative_delta_envelope_low_pct"],
                           b["relative_delta_envelope_high_pct"]) for label, b in bands.items()}
    rel_highs = {label: max(b["relative_delta_envelope_low_pct"],
                            b["relative_delta_envelope_high_pct"]) for label, b in bands.items()}
    rels = {label: b["relative_delta_pct"] for label, b in bands.items()}
    rels_bound = {label: b["relative_delta_bound_pct"] for label, b in bands.items()}
    max_rel, min_rel = max(rels.values()), min(rels.values())
    max_rel_bound, min_rel_bound = max(rels_bound.values()), min(rels_bound.values())
    max_rel_low, min_rel_low = max(rel_lows.values()), min(rel_lows.values())
    max_rel_high, min_rel_high = max(rel_highs.values()), min(rel_highs.values())

    n_cma = {label: len(members) for label, _lo, _hi, members in census._AGE_BAND_SPEC}
    rounded_cells = {label: n_cma[label] * (1 + len(census._QC_CMAS)) + len(members) * len(QC_PART_CSDS)
                     for label, _lo, _hi, members in CD_BAND_SPEC}

    provenance = {
        "as_of": "2021",
        "source": (
            f"StatCan {census.STATCAN_TABLE} (committed extract "
            f"{census.CENSUS_EXTRACT}) province NET of the six wholly-Québec CMAs, NET of the "
            f"{len(QC_PART_CSDS)} Québec-side census subdivisions of the Ottawa-Gatineau CMA "
            f"read from StatCan {STATCAN_TABLE} (committed extract {EXTRACT}) — DERIVED, never "
            "transcribed (steering ruling B)"),
        "sources": {
            census.CENSUS_EXTRACT: WORKBOOK_SHA256[census.CENSUS_EXTRACT],
            EXTRACT: WORKBOOK_SHA256[EXTRACT],
        },
        # The one anchor a re-extract cannot move with — for the 0231 leg only. The CSD extract
        # is a WDS coordinate pull and IS its own raw response (pins.py's ISQ parenthetical
        # applies), so inventing an upstream member for it would name a nonexistent object.
        "raw_source_sha256": raw_anchor(census.CENSUS_EXTRACT),
        "raw_source_member": raw_member(census.CENSUS_EXTRACT),
        "statcan_tables": [census.STATCAN_TABLE, STATCAN_TABLE, MEMBERSHIP_TABLE],
        "extracted_at": payload["_pull"]["pulled_at"],
        "derived_by": "demoflow.loaders.hors_aligned.derive_aligned_ownership",
        "generator": "demoflow/scripts/gen_hors_aligned.py",
        "measure": ("owner-maintainer households / total private households, at the `Total -` "
                    "member of every non-age dimension, over the OPERAND-ALIGNED territory"),
        "territory": _TERRITORY,
        "multiplicand_note": _MULTIPLICAND_NOTE,
        "universe": {
            "note": _UNIVERSE_NOTE,
            "province_all_ages": {"households": sibling_total,
                                  "owner_households": sibling_owner,
                                  "bit_identical_across_the_pair": True},
        },
        "membership": payload["_pull"]["membership"],
        "bands": bands,
        "all_ages": {
            "shipped_households": all_shipped_total,
            "shipped_owner_households": all_shipped_owner,
            "shipped_rate": all_ages_shipped,
            "aligned_households": all_shipped_total - all_sub_total,
            "aligned_owner_households": all_shipped_owner - all_sub_owner,
            "aligned_rate": all_ages_aligned,
            "relative_delta_pct": (all_ages_aligned - all_ages_shipped) / all_ages_shipped * 100,
            "note": ("EVIDENCE, never served: not a model band. Published here because it is "
                     "the row both cubes agree on bit-for-bit and the one the ruled immigrant "
                     "cube (98-10-0621-01) independently corroborates at the same magnitude."),
        },
        "suppression": {
            "withheld_cells": sum(b["withheld_cells"] for b in bands.values()),
            "bound": ("FIELD-WISE upper bound: each withheld field is bounded by its own "
                      "subdivision's all-ages count MINUS everything that subdivision publishes "
                      "across the SEVEN bands (the unpublished remainder, which contains the "
                      "missing cell by construction), clamped at zero for the round-to-5 step. "
                      "The remainder ranges over everything the subdivision publishes, so it did "
                      "NOT move when operator ruling W (2026-08-20) refined the lattice from four "
                      "bands to seven — but it is now charged to EACH suppressed band separately, "
                      "which makes every band's bound individually valid and the collection looser "
                      "than the single union bound the four-band lattice took. Looser is the "
                      "correct direction for a bound. "
                      "The SERVED rate subtracts only what is published; `aligned_bound_rate` "
                      "subtracts every withheld field at its bound. Those two are the "
                      "SUBTRACTION extremes (the DIAGONAL corners of the feasible rectangle) "
                      "and they do NOT bracket the rate — see `envelope`."),
            "envelope": {
                "note": (
                    "THE BRACKET ON THE RATE, which is not the bracket on the subtraction. "
                    "Each withheld field lies independently in [0, its remainder], so the "
                    "feasible region is a RECTANGLE; rate = (S_o - s_o)/(S_t - s_t) falls in "
                    "the subtracted owners and rises in the subtracted households, so the "
                    "rate's extremes sit at the OFF-DIAGONAL corners — "
                    "`aligned_envelope_high_rate` (least owner, most household subtracted) and "
                    "`aligned_envelope_low_rate` (the reverse). Publishing only the diagonal "
                    "pair would state an interval the true value can sit OUTSIDE. The HIGH "
                    "corner is exactly ATTAINABLE: no cell here withholds its household field "
                    "while publishing its owner field, so every withheld owner at 0 against "
                    "every withheld household at its remainder satisfies owner <= total at "
                    "every cell. The LOW corner is a CONSERVATIVE OUTER bound, not attained — "
                    "reaching it would need positive withheld owners inside cells whose "
                    "withheld households are zero. An outer bound is what an envelope needs."),
                "band_spread_pp": {
                    "at_served_corner": max_rel - min_rel,
                    "at_subtract_most_corner": max_rel_bound - min_rel_bound,
                    "narrowest_feasible": max(max_rel_low - min_rel_high, 0.0),
                    "widest_feasible": max_rel_high - min_rel_low,
                },
                "all_bands_same_signed_across_the_box": min_rel_low > 0,
                "reversal_note": (
                    "#12(B)'s premise is band-UNIFORMITY, so what refutes it is the SPREAD "
                    "across bands, and the spread must survive the suppression or the "
                    "suppression is carrying the reversal. It does: the band spread stays "
                    "strictly positive and same-signed at EVERY corner of the feasible box, "
                    "so no feasible configuration of the withheld cells removes it."),
            },
            "empty_complement_fields": _count_empty_complements(cells),
        },
        "rounding": {
            "note": _ROUNDING_NOTE,
            "rounded_cells_per_field": rounded_cells,
            "envelope_per_field": {label: 2.5 * n for label, n in rounded_cells.items()},
        },
        "supersedes": _SUPERSEDES,
        "scope_fence": (
            "This re-points HORS_RMR ONLY. Every other geography reads the shipped curve "
            f"({census.OWNERSHIP_ARTIFACT}) unchanged — see `join`. The sub-floor ordering "
            "constraint of spec §7 does NOT bind this surface: re-extracting the 25+ bands at "
            "aligned territory is orthogonal to extending the curve below 25, and this curve "
            "does not extend below 25."),
    }

    join = {
        geo.value: {
            "reads": ("operand_aligned" if geo is ALIGNED_GEOGRAPHY else "shipped"),
            "artifact": (ARTIFACT if geo is ALIGNED_GEOGRAPHY else census.OWNERSHIP_ARTIFACT),
            "why": (_JOIN_WHY_ALIGNED if geo is ALIGNED_GEOGRAPHY else _JOIN_WHY_SHIPPED),
        }
        for geo in Geography
    }
    payload_rates = {ALIGNED_GEOGRAPHY.value: {label: rates[label] for label in BAND_ORDER}}
    _assert_anchor_typed(payload_rates, provenance, "derive_aligned_ownership")
    return {"_provenance": provenance, "join": join, "rates": payload_rates}


# --- loaders ------------------------------------------------------------------------------

def _verify_artifact_provenance(payload: dict, path: Path) -> None:
    """STEERING RULING L — identity checked on EVERY load, for BOTH sources plus the anchor.

    The no-drift gate proves the committed artifact equals a fresh derivation, but it is a TEST:
    it defends the repo, not a runtime load. This compares IDENTITY (recorded source digests vs
    the pins registry) and REFUSES rather than serving. Every message names the digest at fault:
    "this artifact is stale" without saying which source moved sends the reader to the wrong file.
    """
    provenance = payload.get("_provenance") if isinstance(payload, dict) else None
    if not isinstance(provenance, dict):
        raise LoaderError(
            f"{path.name}: no `_provenance` block — an artifact that records no source digest "
            "cannot be shown to derive from the pinned sources, so it is indistinguishable from "
            "a hand-authored rate table (steering ruling B) and is refused (ruling L)")
    sources = provenance.get("sources")
    if not isinstance(sources, dict):
        raise LoaderError(
            f"{path.name}: no `_provenance.sources` map of source file -> sha256 — the artifact "
            "records no source identity at all and is refused (steering ruling L)")
    for name in (census.CENSUS_EXTRACT, EXTRACT):
        expected = WORKBOOK_SHA256.get(name)
        if expected is None:
            raise LoaderError(
                f"{path.name}: no sha256 pin registered for {name!r} — the aligned artifact "
                "cannot be checked against its source (PIT chain unpinned)")
        recorded = sources.get(name)
        if recorded is None:
            raise LoaderError(
                f"{path.name}: `_provenance.sources` records no sha256 for {name!r} — one of the "
                "two derivation inputs is unaccounted for, so a stale vintage of it could not be "
                "detected (steering ruling L)")
        if recorded != expected:
            raise LoaderError(
                f"{path.name}: STALE aligned-ownership artifact — recorded sha256 for {name} "
                f"{recorded} does not match the pinned digest {expected}. Regenerate with "
                "`uv run python scripts/gen_hors_aligned.py`; never hand-edit it.")

    raw_expected = raw_anchor(census.CENSUS_EXTRACT)
    if provenance.get("raw_source_sha256") != raw_expected:
        raise LoaderError(
            f"{path.name}: recorded `_provenance.raw_source_sha256` "
            f"{provenance.get('raw_source_sha256')} does not match the pinned upstream anchor "
            # `.get`, never the raising accessor: this message already refuses for the better
            # reason (vintage drift), and a half-registered member must not replace it.
            f"{raw_expected} for {RAW_SOURCE_MEMBER.get(census.CENSUS_EXTRACT, '?')} — the "
            "shipped leg was cut from a DIFFERENT upstream vintage (or the anchor was dropped); "
            "regenerate with `uv run python scripts/gen_hors_aligned.py`")

    _assert_anchor_typed(payload.get("rates", {}), provenance, path.name)


def _verify_join(payload: dict, path: Path) -> None:
    """The SCOPE FENCE, validated for CONTENT at runtime — not merely for its key set.

    `join` is the artifact's own runtime statement of "this re-points HORS_RMR ONLY", so a
    key-set check is a check that cannot catch the thing it exists for: measured at run 25
    review, an artifact whose join declared MTL_RMR reads the operand-aligned curve LOADED
    CLEAN, and so did one whose join re-pointed nothing at all with every `why` blanked. Each
    row is therefore read: exactly one geography reads the aligned curve and it is the pinned
    one, every other reads the shipped curve, each `artifact` matches its own `reads`, and each
    `why` says something — a join row that states no reason is the inference this whole surface
    exists to remove.
    """
    join = payload.get("join")
    if not isinstance(join, dict) or set(join) != {g.value for g in Geography}:
        raise LoaderError(
            f"{path.name}: `join` must name every modeled geography exactly once — got "
            f"{sorted(join) if isinstance(join, dict) else join!r}")
    aligned = sorted(g for g, row in join.items()
                     if isinstance(row, dict) and row.get("reads") == "operand_aligned")
    if aligned != [ALIGNED_GEOGRAPHY.value]:
        raise LoaderError(
            f"{path.name}: exactly one geography may read the operand-aligned curve and it "
            f"must be {ALIGNED_GEOGRAPHY.value} — this join says {aligned or 'none'}. The "
            "other seven territories were never contaminated; a second re-pointed row is a "
            "SCOPE-FENCE breach, not a rounding artifact.")
    for geo, row in sorted(join.items()):
        if not isinstance(row, dict):
            raise LoaderError(f"{path.name}: `join[{geo}]` is not an object")
        reads = row.get("reads")
        if reads not in ("operand_aligned", "shipped"):
            raise LoaderError(
                f"{path.name}: `join[{geo}].reads` is {reads!r}, expected 'operand_aligned' "
                "or 'shipped'")
        expected = ARTIFACT if reads == "operand_aligned" else census.OWNERSHIP_ARTIFACT
        if row.get("artifact") != expected:
            raise LoaderError(
                f"{path.name}: `join[{geo}]` reads {reads!r} but its artifact "
                f"{row.get('artifact')!r} does not match — it must be {expected!r}, or a "
                "reader is told to open a file that does not carry that curve")
        if not str(row.get("why") or "").strip():
            raise LoaderError(
                f"{path.name}: `join[{geo}]` states no reason — the join exists so no reader "
                "has to INFER why this geography reads the curve it reads")


def _read_verified(data_dir: Path | None) -> tuple[dict, Path]:
    """Read + FULLY verify the aligned artifact ONCE, for all three accessors.

    Every refusal cause lives on this shared path — the provenance identity legs, the strict
    join on `rates`, AND the `join` block itself — for the reason
    `census._read_verified_ownership` records: a check that runs only in one accessor lets the
    others state a confident answer for a curve no run may use. Measured here at run 25 review
    with the `join` validation sitting in `load_aligned_ownership_join` alone: a dropped or
    gutted join refused the join and still served the rates AND a confident vintage record,
    which is the same split-legs shape census.py measured on 2026-08-14. That vintage accessor
    is deleted (round-3 elegance audit, 2026-08-22 — nothing outside `tests/` called it); the
    three that remain still share this path, and the measurement is why.
    """
    path = (data_dir or DATA_DIR) / ARTIFACT
    if not path.exists():
        raise LoaderError(f"aligned ownership artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _verify_artifact_provenance(payload, path)
    _verify_join(payload, path)
    rates = payload.get("rates")
    if not isinstance(rates, dict) or set(rates) != {ALIGNED_GEOGRAPHY.value}:
        raise LoaderError(
            f"{path.name}: `rates` must carry exactly {ALIGNED_GEOGRAPHY.value} and nothing "
            f"else (strict join) — got {sorted(rates) if isinstance(rates, dict) else rates!r}. "
            "This surface re-points ONE geography; a second row here would be a second curve "
            "served under a provenance block that describes one territory.")
    missing = [label for label in BAND_ORDER if label not in rates[ALIGNED_GEOGRAPHY.value]]
    if missing:
        raise LoaderError(
            f"{path.name}: aligned ownership rate missing for bands: {missing} (strict join)")
    return payload, path


def load_aligned_ownership_rates(data_dir: Path | None = None) -> dict:
    """{geography value: {band: rate}} — the re-pointed row alone, shaped like the shipped
    table so the two are join-compatible without a reshape at the call site."""
    return _read_verified(data_dir)[0]["rates"]


def load_aligned_ownership_join(data_dir: Path | None = None) -> dict:
    """The EXPLICIT geography -> curve map. Read from the artifact rather than rebuilt here, so
    a consumer and a reviewer are looking at the same statement of which row is re-pointed.

    No check of its own: `_read_verified` has already validated this block's CONTENT, which is
    what makes that function's "every refusal cause lives on the shared path" true rather than
    stated. A divergent local check here is exactly how the legs split apart before.
    """
    return _read_verified(data_dir)[0]["join"]


def aligned_ownership_union(lo: int, hi: int, data_dir: Path | None = None) -> float:
    """Owner households / total households over ages [lo, hi] on the ALIGNED territory.

    THE SIBLING OF `census.ownership_union_rates`, for the one geography this surface
    re-points (operator ruling X, 2026-08-21). A consumer that multiplies a whole age span by
    ONE rate needs the span's household-weighted union, and no point read inside the span
    returns it — see that function's header for why the seven-band lattice made the two
    questions distinguishable.

    IT READS THIS ARTIFACT'S OWN BAND COUNTS, which is why HORS_RMR needs its own accessor
    rather than a row in the census map: the aligned territory is the shipped residual MINUS 16
    census subdivisions, so its counts are not the census net's and its union is not the census
    net's either (0.690149 against 0.680452 over 25-54). The counts are the SERVED pair —
    `aligned_owner_households` / `aligned_households`, the published-cells-only subtraction —
    so this union sits on exactly the same subtraction as the served band rates beside it, and
    never on a bound corner.

    Full verification runs first (`_read_verified`), so a union cannot be served off an
    artifact whose rates or join would be refused.
    """
    payload, path = _read_verified(data_dir)
    bands = payload["_provenance"].get("bands")
    if not isinstance(bands, dict):
        raise LoaderError(
            f"{path.name}: `_provenance.bands` is absent or not an object, so the aligned "
            f"{lo}-{hi} union has no counts to form — the served RATES cannot substitute (a "
            "mean of band rates is not a rate) and a union computed from them would be wrong "
            "by the band-size weighting")
    owner = total = 0
    for label, _lo, _hi, _members in census.bands_spanning(lo, hi):
        cell = bands.get(label)
        if not isinstance(cell, dict):
            raise LoaderError(
                f"{path.name}: `_provenance.bands[{label}]` is absent — the {lo}-{hi} union is "
                "an EXACT union of the model's bands and a missing constituent makes it a "
                "shorter span, not a smaller number")
        for field in ("aligned_owner_households", "aligned_households"):
            if not isinstance(cell.get(field), int):
                raise LoaderError(
                    f"{path.name}: `_provenance.bands[{label}].{field}` is "
                    f"{cell.get(field)!r}, not a count — the union is formed from counts and "
                    "divided once, so a missing count is a refusal and never a skipped term")
        owner += cell["aligned_owner_households"]
        total += cell["aligned_households"]
    return assert_fraction(f"aligned-ownership-union[{ALIGNED_GEOGRAPHY.value},{lo}-{hi}]",
                           _rate(owner, total, ctx=f"aligned union {lo}-{hi}"))


def aligned_ownership_rate(rates: dict, geography: Geography, age: int) -> float:
    """Lookup with the same shape as `census.ownership_rate`, refusing any geography this
    surface does not re-point — a caller that reached here for MTL_RMR is reading the wrong
    curve, and returning the shipped value would hide that."""
    if geography is not ALIGNED_GEOGRAPHY:
        raise LoaderError(
            f"{geography.value} is not re-pointed by the operand-aligned surface — read it from "
            f"{census.OWNERSHIP_ARTIFACT} via `census.ownership_rate` (see the artifact's `join`)")
    for label, lo, hi, _members in CD_BAND_SPEC:
        if lo <= age <= hi:
            geo_rates = rates.get(geography.value) or {}
            if label not in geo_rates:
                raise LoaderError(f"no aligned ownership rate for {geography.value} band {label}")
            return assert_fraction(f"aligned-ownership[{geography.value},{label}]",
                                   geo_rates[label])
    raise LoaderError(f"no modeled age band for age {age}")
