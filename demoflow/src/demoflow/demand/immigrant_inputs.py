"""Immigrant-input JOIN TABLE — headship + ownership ratio per modeled geography.

Spec §6 rulings S and T with amendment #11 (codex r5-F4 named the join; r7-F8 rules the
ratio's units). Two numbers per modeled geography: the immigrant HEADSHIP (households formed
per person, a FRACTION) and the immigrant/non-immigrant ownership RATIO (nonneg-finite — the
[0,1] constraint binds the PRODUCT `p_imm`, never the ratio). Every modeled member resolves
or the run RAISES: there is no unstated default.

THE VALUES ARE MEASURED, and `probes/P8-immigrant-inputs.md` is the measurement. Both
quantities come from ONE cube on ONE member — StatCan 98-10-0621-01, `Before 2016` of
`Population characteristics (46)` — with its census-division sibling 98-10-0622-01 supplying
the two geographies ruling T measures; the province rows of the two agree BIT-IDENTICALLY on
that member's triple, which is what makes them one universe at two geography grains rather
than two sources. Zero geography transport and zero metric transport: the cube publishes the
owner-MAINTAINER propensity §6 defines, as counts, in one universe.

THE LITERALS BELOW ARE NOT FREE-STANDING. `tests/test_i2.py` couples every one of them to
P8's `DECISION-HEADSHIP` / `DECISION-RATIO` tokens ON THE DIGITS (never on a prose prefix,
which a reworded note detaches silently), and that coupling is itself proven three ways: it
REDs on a perturbed digit, REDs on a perturbed digit under reworded prose, and stays GREEN on
rewording alone. A regenerated P8 whose value moves therefore REDs this table instead of
leaving it a decorative copy of a measurement nobody re-checked.

PROVENANCE IS PER FIELD, and one flag could not have said it honestly (seat ruling, run 21):
under rulings Q AND T a geography may hold a cited ratio beside a borrowed headship, so
`ImmigrantInputs` carries `headship_provenance` and `ratio_provenance` separately. BOTH rulings
are named because both put a geography's two fields on independent footings, and citing only one
reads as though the other were silent on it: Q is the ruling about what the vocabulary must be
ABLE to state (a mixed pair — `pipeline.py` cites it at the `borrowed_prior` derivation for the
same reason), while T is why RA06/RA13 carry MEASURED provenance of their own rather than the
parent CMA's. The plan's single `flag` field — `None` for the CMAs, `"borrowed_prior"` elsewhere — is superseded: it
cannot express a mixed pair, and `None` cannot say "measured for THIS geography", which under
ruling S is an affirmative claim about a cube coordinate, not the absence of a caveat.

THE VOCABULARY IS THIS TABLE'S OWN — a CLOSED three-member set, deliberately NEITHER
`constants.ANCHOR_FLAGS` NOR either of spec §7's two emitter enums (ScenarioPrior rows
{borrowed_prior, ra_proxy, never_relax_stress}, spec:352-353; rankings rows {borrowed_prior,
ra_proxy, closed_cohort_exceedance}, spec:434):

  * `cited`             — measured directly for THIS geography by the ruled source.
  * `borrowed_prior`    — the parent CMA's value, standing in.
  * `computed_residual` — obtained by arithmetic over cited counts at a CONSTRUCTED territory.

The discriminator, stated plainly because all three sets share the string `borrowed_prior`:
an ANCHOR flag says where a CONSTANT came from; a §7 emitter member says what an output ROW
means; these say how THIS GEOGRAPHY'S INPUT was obtained. No emitter may import this set and
this set is neither of theirs — an emitter MAPS from these into its own §7 enum. The third
member is MINTED rather than silently widened into an existing set because HORS_RMR fits
neither: it is not `cited` (its territory is CONSTRUCTED — a netting, stated in full in that
row's own `source` and nowhere else — not measured), and it is not
`borrowed_prior` (nothing was borrowed). The mint is deliberate and loud; an unresolved
modeled member still raises.

WHICH netting lives in the ROW, never in this paragraph, and amendment #13 is why: it moved
HORS_RMR's territory (province-net-of-six-CMAs → that, further net of the Ottawa-Gatineau
CMA's Québec-side census subdivisions) and its digits (0.5169 → 0.5234, 0.9600 → 1.0248)
while leaving the FLAG untouched — still arithmetic over cited counts at a constructed
territory. So `computed_residual` cannot tell a reader which territory produced the number
and was never meant to; the `source` string is the only discriminator, which is what makes
a second copy of the construction up here a thing that would silently go stale.

NO ROW MIXES ITS PAIR TODAY — all five measured geographies are cited-or-computed on both
fields and the three RA proxies borrow both. The per-field carrier is kept anyway, because
the ruling that produced it is about what the vocabulary must be ABLE to state, and a mixed
pair is one census-division measurement away (`98-10-0623-01` / `98-10-0624-01` are recorded
by §6 as available and unused). `tests/test_i2.py` constructs a mixed row so the carrier is
exercised structure rather than an untested field.

NESTING IS ACCEPTED AND STATED (§6), not to be re-discovered later as a calibration finding:
RA06/RA13 are carried at census-division grain while MTL_RMR is at CMA grain, so the parts do
not reconcile to the whole. That is deliberate — rankings compare geographies, each at its
best available measurement, and I1/I2 bind PER GEOGRAPHY; neither asserts that modeled
geographies aggregate.

FLOW-VS-STOCK, the modeling choice this table hands its consumer: the demand operand is an
arrival FLOW while the ruled member is a settled STOCK. §6 takes that deliberately (I2
subtracts the full surviving arrival stock every year while the chain credits each cohort
once, so the arrival-year credit stands in for the cohort's whole residency, and an
arrival-window rate would systematically undercount it). The size of the choice is visible
rather than hidden: P8 §2a publishes the recent-arrival readings beside these (headship
0.3604 / 0.3431 / 0.3143, ratio 0.4211 / 0.3679 / 0.4472).

HORS_RMR COMPONENT FLOWS (arrivals) are a SEPARATE resolution and not this table's business:
three-way at probe P5/P6 (codex r7-F4) — (i) the compo workbook's own hors-RMR row; else
(ii) province compo net of all RMR rows, reconciliation-checked; else (iii) HORS_RMR is
EXCLUDED FROM RANKINGS ENTIRELY, recorded as a run-level exclusion naming the unresolved
input (pipeline `EXCLUDED_FROM_RANKINGS` → the rankings document's typed `exclusions[]`,
Task 29). A resolvable INPUT pair here never implies a resolvable arrival flow there.
"""
from dataclasses import dataclass

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders.validate import assert_fraction, assert_nonneg_finite

# The join table's OWN closed provenance vocabulary — see the docstring's discriminator.
INPUT_PROVENANCE = frozenset({"cited", "borrowed_prior", "computed_residual"})

# FLOOR GATE (§6, cross-cube and wired as one): the SETTLED living-alone shares from
# 43-10-0060-01 indicator `Population living alone`, member `Admitted to Canada more than 10
# years ago` — the member nearest the ruled `Before 2016` cut and the stricter bound (P8 §5
# measured 0.154 > 0.134 and 0.164 > 0.127 against the pooled figures). Each person living
# alone maintains exactly one household, so immigrant headship must EXCEED the share; a value
# at or below it is a defect, not a datum. Keys are EXACTLY the geographies the source
# publishes a member for — `FLOOR_NOT_COVERED` carries the rest, with reasons.
LIVING_ALONE_FLOOR: dict[Geography, float] = {
    Geography.MTL_RMR: 0.154,
    Geography.QC_RMR: 0.164,
}

# NOT-COVERED IS RECORDED, NEVER INFERRED FROM SILENCE (absence discipline). P8 §5 searched
# all 63 geography members of 43-10-0060-01: 0 at geoLevel 3 (the census-division level RA06
# and RA13 publish at) and 0 carrying SGC 2466/2465. Substituting the province figure (0.156,
# measured there) would be a geography transport the ruling does not make.
FLOOR_NOT_COVERED: dict[Geography, str] = {
    Geography.HORS_RMR:
        "43-10-0060-01 publishes no hors-RMR member (P8 §5 searched its 63 geography members "
        "for 'outside'/'non-cma'/'rest of'/'remainder'/'hors': 0 matches). NOT COVERED — no "
        "stand-in substituted",
    Geography.MTL_ISLAND_RA06:
        "43-10-0060-01 carries 0 members at geoLevel 3 and none with classificationCode 2466 "
        "(P8 §5, all 63 members searched). The census-division measurement exists in "
        "98-10-0622-01; the living-alone floor does not. NOT COVERED",
    Geography.LAVAL_RA13:
        "43-10-0060-01 carries 0 members at geoLevel 3 and none with classificationCode 2465 "
        "(P8 §5, all 63 members searched). NOT COVERED",
    Geography.LANAUDIERE_RA14_PROXY:
        "borrowed MTL_RMR value: the floor ran at MTL_RMR (0.5259 > 0.154) and this row "
        "carries that geography's number. 43-10-0060-01 publishes no member for this "
        "territory, so nothing is floored HERE",
    Geography.LAURENTIDES_RA15_PROXY:
        "borrowed MTL_RMR value: the floor ran at MTL_RMR (0.5259 > 0.154) and this row "
        "carries that geography's number. 43-10-0060-01 publishes no member for this "
        "territory, so nothing is floored HERE",
    Geography.MONTEREGIE_RA16_PROXY:
        "borrowed MTL_RMR value: the floor ran at MTL_RMR (0.5259 > 0.154) and this row "
        "carries that geography's number. 43-10-0060-01 publishes no member for this "
        "territory, so nothing is floored HERE",
}


def _validate_ratio(ratio: float) -> float:
    """The ownership RATIO is NOT a fraction (codex r7-F8): it can validly exceed 1 —
    immigrants CAN out-own non-immigrants in a cell, and THREE of the ruled geographies
    measure above 1 (RA06 1.0757, RA13 1.1112, and HORS_RMR 1.0248 since amendment #13 moved
    it to the operand-aligned territory). Only the PRODUCT `p_imm` binds [0,1]."""
    return assert_nonneg_finite("immigrant_ownership_ratio", ratio)


@dataclass(frozen=True)
class ImmigrantInputs:
    """One geography's immigrant inputs, with PER-FIELD provenance and its citation.

    Validated at construction in `constants.Anchor`'s style, so a bad edit lands at IMPORT
    rather than inside a run: units on both numbers, provenance membership on both fields, a
    non-empty citation, and the living-alone floor wherever the source publishes one.
    """

    geography: Geography
    immigrant_headship: float
    ownership_ratio: float
    headship_provenance: str
    ratio_provenance: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise LoaderError(f"immigrant inputs for {self.geography.value}: empty source — an "
                              f"uncited join-table row is a defect")
        for field, provenance in (("headship_provenance", self.headship_provenance),
                                  ("ratio_provenance", self.ratio_provenance)):
            if provenance not in INPUT_PROVENANCE:
                raise LoaderError(
                    f"immigrant inputs for {self.geography.value}: unknown provenance "
                    f"{provenance!r} on {field} (closed join-table vocabulary "
                    f"{sorted(INPUT_PROVENANCE)}; constants.ANCHOR_FLAGS and spec §7's two "
                    f"EMITTER enums are separate sets and not this one)")
        assert_fraction(f"immigrant_headship[{self.geography.value}]", self.immigrant_headship)
        _validate_ratio(self.ownership_ratio)

        floor = LIVING_ALONE_FLOOR.get(self.geography)
        if floor is not None and not self.immigrant_headship > floor:
            raise LoaderError(
                f"immigrant headship {self.immigrant_headship} at {self.geography.value} is at "
                f"or below the settled living-alone floor {floor} (43-10-0060-01, §6 FLOOR "
                f"GATE) — each person living alone maintains exactly one household, so this is "
                f"a defect, not a datum")


_MEASURED = {
    Geography.MTL_RMR: ImmigrantInputs(
        geography=Geography.MTL_RMR, immigrant_headship=0.5259, ownership_ratio=0.9634,
        headship_provenance="cited", ratio_provenance="cited",
        source="StatCan 98-10-0621-01 (2021 Census, released 2023-10-04), geography member 35 "
               "'Montréal (CMA), Que.', `Before 2016` of `Population characteristics (46)`: "
               "452,595 maintainers / 860,685 persons; owner-maintainer propensity 0.5573 vs "
               "non-immigrant 0.5785. DIRECT and cited — P8 DECISION-SOURCE-MTL_RMR"),
    Geography.QC_RMR: ImmigrantInputs(
        geography=Geography.QC_RMR, immigrant_headship=0.5054, ownership_ratio=0.8910,
        headship_provenance="cited", ratio_provenance="cited",
        source="StatCan 98-10-0621-01 (2021 Census, released 2023-10-04), geography member 36 "
               "'Québec (CMA), Que.', `Before 2016` of `Population characteristics (46)`: "
               "20,490 maintainers / 40,545 persons; owner-maintainer propensity 0.5351 vs "
               "non-immigrant 0.6006. DIRECT and cited — P8 DECISION-SOURCE-QC_RMR"),
    Geography.HORS_RMR: ImmigrantInputs(
        geography=Geography.HORS_RMR, immigrant_headship=0.5234, ownership_ratio=1.0248,
        headship_provenance="computed_residual", ratio_provenance="computed_residual",
        source="OPERAND-ALIGNED per spec §6 amendment #13. StatCan 98-10-0621-01 province "
               "member 24 NET of its six geoLevel-503 wholly-QC CMA children (30 "
               "Drummondville, 35 Montréal, 36 Québec, 40 Saguenay, 48 Sherbrooke, 51 "
               "Trois-Rivières) AND NET of the 16 Québec-side census subdivisions of the "
               "Ottawa-Gatineau CMA, whose counts are read at subdivision grain from the "
               "census-division sibling 98-10-0622-01: 25,185 maintainers / 48,120 persons. "
               "Still a CONSTRUCTED territory — arithmetic over cited counts, computed rather "
               "than borrowed, so neither `cited` nor `borrowed_prior` describes it — but a "
               "DIFFERENT one from the pair this row used to serve (0.5169 / 0.9600, the same "
               "residual with the Québec side of Ottawa-Gatineau still IN because that CMA is "
               "parented to Ontario in this cube and so is not one of the six netted above). "
               "WHY THE TERRITORY MOVED, load-bearing and the REVERSE of what this row "
               "previously warned: the rate's territory must match the territory of the "
               "arrival FLOW it multiplies, and that flow is ISQ's 'Territoire hors des RMR' "
               "row, which EXCLUDES the Québec side of Ottawa-Gatineau (P8 §2 measured the "
               "old gap at exactly the ISQ Gatineau row, 355,971 persons). This residual now "
               "excludes it too, so the two operands are one territory. The 16-subdivision "
               "MEMBERSHIP is carried from probes/P10-hors-operand-alignment.md — "
               "98-10-0003-01's Ottawa-Gatineau member 594 publishes 25 CSD children closing "
               "exactly on the CMA, 16 Québec-side by SGC prefix AND census-tree ancestry, "
               "gated against the ISQ row at -0.752% — and every member is re-resolved live "
               "in the P8 run. 18 withheld settled fields at 7 of the 16 are bounded "
               "field-wise, envelope 0.5225-0.5236 and 1.0228-1.0264. P8 "
               "DECISION-SOURCE-HORS_RMR and DECISION-HORS-ALIGNMENT"),
    Geography.MTL_ISLAND_RA06: ImmigrantInputs(
        geography=Geography.MTL_ISLAND_RA06, immigrant_headship=0.5555, ownership_ratio=1.0757,
        headship_provenance="cited", ratio_provenance="cited",
        source="StatCan 98-10-0622-01 (census-division sibling, same release, one universe: "
               "the two cubes' province rows are bit-identical on the ruled triple), CD "
               "'Montréal' member 1732 / geoLevel 3 / SGC 2466: 299,230 maintainers / 538,620 "
               "persons; owner-maintainer propensity 0.4529 vs a renter-heavy non-immigrant "
               "base at 0.4210 — which is why the ratio exceeds 1 LOCALLY while the CMA "
               "reading is 0.9634 (composition, not contradiction). MEASURED and cited on the "
               "amendment-#11 territory gate (province-controlled share residual +0.279%, "
               "threshold 1.586% derived from six innocent controls) — P8 §4b"),
    Geography.LAVAL_RA13: ImmigrantInputs(
        geography=Geography.LAVAL_RA13, immigrant_headship=0.4816, ownership_ratio=1.1112,
        headship_provenance="cited", ratio_provenance="cited",
        source="StatCan 98-10-0622-01, CD 'Laval' member 1730 / geoLevel 3 / SGC 2465 (NOT the "
               "same-named census SUBDIVISION 1731 / SGC 2465005 — resolution requires name "
               "AND geoLevel AND parent): 57,390 maintainers / 119,160 persons; "
               "owner-maintainer propensity 0.7274 vs non-immigrant 0.6546, and the product "
               "the [0,1] assertion binds is 0.6546 × 1.1112 = 0.727. MEASURED and cited on "
               "the amendment-#11 territory gate (share residual +0.611% ≤ 1.586%) — P8 §4b"),
}

# RA members borrow their PARENT CMA (§6; deliberately NOT extended to census-division unions,
# which would need a CD→RA correspondence this tree does not have and would re-open P6's
# edition-specific RA↔MRC axis). Borrowed rows are DERIVED from the parent row rather than
# re-typed, so a parent value that moves under a P8 re-run moves them with it — the proxies
# are coupled to the note THROUGH the parent, and re-typing would break that silently.
_PARENT_CMA = {
    Geography.LANAUDIERE_RA14_PROXY: Geography.MTL_RMR,
    Geography.LAURENTIDES_RA15_PROXY: Geography.MTL_RMR,
    Geography.MONTEREGIE_RA16_PROXY: Geography.MTL_RMR,
}

def _borrowed(member: Geography, parent: Geography) -> ImmigrantInputs:
    row = _MEASURED[parent]
    return ImmigrantInputs(
        geography=member,
        immigrant_headship=row.immigrant_headship,      # DERIVED, never re-typed
        ownership_ratio=row.ownership_ratio,
        headship_provenance="borrowed_prior", ratio_provenance="borrowed_prior",
        source=f"parent-CMA borrow: the {parent.value} pair, standing in for a territory the "
               f"ruled cubes do not measure at this grain (§6 — RA14/15/16 stay proxies). "
               f"Borrowed from: {row.source}")


_TABLE: dict[Geography, ImmigrantInputs] = (
    dict(_MEASURED) | {member: _borrowed(member, parent) for member, parent in _PARENT_CMA.items()}
)


def resolved_selection() -> dict[str, dict[str, object]]:
    """The RESOLVED table as plain data — what `constants.assumptions_hash` identifies.

    QUANT GATE F4 (run 32): these pairs are the ruled values amendments #13/#14 exist to
    govern, and they sat outside BOTH identity tokens — not in `data_vintage.source_hashes`
    (they are source literals, not files under `data/`) and not in `assumptions_hash` (which
    covered `CENTRAL_ASSUMPTIONS` + `SWEEP_GRID` only). So a RULED value could move and re-mint
    nothing, while a ratio change of that class reorders up to 7 of 8 geographies (measured).

    IT RANGES OVER THE WHOLE TABLE, borrowed rows included: a proxy's pair is DERIVED from its
    parent, so re-hashing it costs nothing and a future row that stops being derived is covered
    without an edit here. The `source` CITATIONS are deliberately absent — see the residual
    `assumptions_hash` states: identity must not move on a reworded note, and the prose is
    coupled to the digits by `tests/test_i2.py` instead. The per-field provenance TOKENS ARE
    included: they are consumed (a `borrowed_prior` on either field flags the emitted rankings
    row), so a relabel with unchanged digits still moves the artifact.
    """
    return {geography.value: {"immigrant_headship": row.immigrant_headship,
                              "ownership_ratio": row.ownership_ratio,
                              "headship_provenance": row.headship_provenance,
                              "ratio_provenance": row.ratio_provenance}
            for geography, row in sorted(_TABLE.items(), key=lambda kv: kv[0].value)}


def resolve_immigrant_inputs(geography: Geography) -> ImmigrantInputs:
    """The full-geography join (codex r5-F4): every MODELED member resolves, or raise.

    No unstated default under the no-imputation policy — a geography that fell out of the
    table is a wiring defect, and serving a plausible pair for it would put an unmeasured
    number into the demand equation with no way to see it downstream.
    """
    row = _TABLE.get(geography)
    if row is None:
        raise LoaderError(
            f"no immigrant inputs resolvable for {geography.value} — every modeled geography "
            f"must resolve from the ruling-S/T join table (spec §6); there is no unstated "
            f"default. Resolvable today: {sorted(g.value for g in _TABLE)}")
    return row
