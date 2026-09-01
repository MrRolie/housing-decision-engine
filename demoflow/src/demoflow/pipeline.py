"""Tranche-1 pipeline (spec §5/§6/§7, rounds 7-9) — the orchestrator, and the place four of
this arc's rulings are DISCHARGED because no leaf module can discharge them.

Every module under `src/` is a leaf with its own contracts. Four obligations live only here,
each stated at its own gate below and each carrying a test that REDs if the wiring is dropped:

  * RULING O — `check_reconciliation` binds the CENTRAL-ASSUMPTION run ONLY. `gates.py` says
    so in its own docstring and cannot enforce it: it takes a bare float and has no notion of
    which run is calling. The plan's pipeline body never imported or called it at all, which
    satisfies "don't let a sweep leg trip it" by calling it NOWHERE — a gate that cannot fail.
  * THE OPERAND-ALIGNED OWNERSHIP JOIN — `loaders/hors_aligned.py` exists, is tested, and was
    consumed by NOTHING, so ED was still computed from the operand-misaligned HORS_RMR rates
    that spec §6 amendment #12(B) was REVERSED to fix. The join is read from the artifact and
    OBEYED here; the pipeline states no scope fence of its own.
  * THE RUN CONTRACT (codex r8-F1) — central values are the headline, band endpoints enter
    only through the robustness sweep, and the sweep's product is `rank_stable`, never a
    re-calibration.
  * spec §7c's RUN-LEVEL EXIT CODE — `run_exit_code`, not `exit_code`. The latter ranges over
    the results it is HANDED, so one OK result exits 0 however short of the required set.

WHAT IS COARSE BY DESIGN (Tranche 1). The 75+ owner stock is a SINGLE lumped bucket rolled at
a fixed age, not an age-indexed lattice; the surviving-arrival cohorts carry no mortality of
their own. YSL / the ED->drift beta mapping are Tranche 2. The sweep is NOT on that list any
more: until run 33 it varied q_live alone, which made `rank_stable` a verdict over one of five
declared axes, and the four it skipped included the only axis that then moved the BAND-curve
order — a uniqueness ruling V retired: three grid axes reorder the resolved curve (`_sweep_legs`
carries the re-measurement).

WHAT IS NOT COARSE, because coarse is not the same as silent. Every silent-zero door on the
model path refuses instead: a year the population frame does not carry, a holed age lattice, an
arrival-flow row that is not published, an exit cause with no listing cause, a source the run
read but cannot hash. Each of those produced a plausible number in the plan body and none of
them could be seen downstream.

THE ARRIVAL TIMING IS THE LOADER'S, NOT THE PLAN'S. `compo.YEAR_SEMANTICS` states the one fact
a §6 consumer cannot get wrong: the flow row labeled t covers 1 July t -> 1 July t+1 and lands
in Population(t+1). The plan body credited arrivals(t) into year t AND subtracted them from
P_ISQ(t) — mis-timing every cohort by one year, in the exact shape that loader constant was
written to prevent. Corrected here, the flow span (2025-2050) maps EXACTLY onto the projected
stock lattice (2026-2051) with no gap and no year silently arriving at zero.

AND THE EXIT TIMING IS THIS MODULE'S TOO (spec amendment #27). `_arrival_year` exists to
END-label a start-labeled published flow, and for fifteen review rounds the SUPPLY side got no
such translation: the roll keys its exits at the roll-START year, so `ED(t)` subtracted a
`[t, t+1)` supply flow from a `(t-1, t]` demand flow — two adjacent, DISJOINT twelve-month
windows, each pair internally coherent and the two pairs offset by exactly one year. Nothing
held it: 1,280 tests did not pin the cross-leg alignment. `_exit_landing_year` is the missing
sibling, applied at the one place the exits are keyed, and the two labelling translations now
sit side by side so the asymmetry cannot come back unread.
"""
import hashlib
import json
import os
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from demoflow.balance.excess_demand import excess_demand
from demoflow.balance.owner_stock import owner_stock
from demoflow.cohort.basis import BASIS_SOURCE_KEY, basis_digest, q_at
from demoflow.cohort.gates import check_reconciliation
from demoflow.cohort.init import assert_aggregate_coupled_direction, initialize_households
from demoflow.cohort.listings import market_listings
from demoflow.cohort.rollforward import BAND_ENTRY_AGE, Stock, roll_cohort_decade, roll_one_year
from demoflow.demand.formation import immigrant_formation, native_formation, total_owner_demand
from demoflow.demand.i2 import assert_i2_identity, assert_p_resident_nonneg, p_resident
from demoflow.demand.immigrant_inputs import resolve_immigrant_inputs
from demoflow.errors import CalibrationError, LoaderError
from demoflow.geography import Geography, Scenario
from demoflow.loaders.census import (
    CENSUS_EXTRACT, HEADSHIP_ARTIFACT, OWNERSHIP_ARTIFACT, headship_curve, headship_rate,
    load_headship_curves,
    load_ownership_rates, ownership_rate, ownership_union_rates,
)
from demoflow.loaders.compo import FLOW_SPAN, load_immigrant_flows
from demoflow.loaders.constants import (
    ASSUMPTIONS_HASH_CHARS, CENTRAL_ASSUMPTIONS, CONSTANTS, MODEL_CHOICES, RATIO_SWEEP_AXIS,
    RATIO_SWEEP_SPAN_ANCHOR, SWEEP_GRID, assumptions_hash, declared_sweep_grid, sweep_leg_label,
)
from demoflow.loaders.hors_aligned import (
    ALIGNED_GEOGRAPHY, ARTIFACT as ALIGNED_OWNERSHIP_ARTIFACT, aligned_ownership_rate,
    aligned_ownership_union, load_aligned_ownership_join, load_aligned_ownership_rates,
)
from demoflow.loaders.ircc import CSV_NAME as IRCC_CSV_NAME, load_pr_landings
from demoflow.loaders.isq import load_population
from demoflow.loaders.living_arrangement import (
    ARTIFACT as LIVING_ARRANGEMENT_ARTIFACT, couple_share, living_alone_rate,
    load_living_arrangement,
)
from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256, raw_anchor
from demoflow.loaders.validate import assert_fraction, assert_nonneg_finite
from demoflow.output.artifacts import (rankings_document, scenario_prior_document,
                                       stamp_pairing_token, tripwire_document,
                                       write_json_strict)
from demoflow.output.rankings import exclude_from_rankings, rank_geographies, refuse_cross_vintage
from demoflow.output.scenario_prior import build_scenario_prior_rows, prior_vintage
from demoflow.output.tripwires import (
    PR_LANDINGS_INDICATOR, SourceKind, TripwireResult, TripwireSpec, check_registry,
    evaluate_indicator, evaluate_pr_landings, run_exit_code,
)

POP_WORKBOOKS = ("pop-as-rmr-base.xlsx", "pop-as-ra-base.xlsx")
COMPO_WORKBOOKS = ("compo-rmr-base.xlsx", "compo-ra-base.xlsx")

# Where a document is serialized before it is renamed into place (see the emission block at
# the foot of `run_pipeline`). Named rather than inlined so a reader who finds one of these
# after a crash can grep for what left it there.
STAGING_SUFFIX = ".partial"

# THE TWO UNCITED DECISION-CRITICAL SELECTIONS, READ-THROUGH from the constants surface rather
# than declared here (run-32 stress gate F2). Each swings the shipped headline `mean_ed_*` numbers by
# 55-66% and neither was inside either identity token, so editing one moved every emitted number
# under a byte-identical envelope. `constants.MODEL_CHOICES` carries the values, its provenance
# twin carries the honest UNCITED derivation, and `assumptions_hash` now covers both — the same
# read-through binding `cohort/listings.py` uses for its three central assumptions. The names
# stay HERE because they are this module's own vocabulary; the VALUES are declared once.
#
# DO NOT INLINE EITHER VALUE BACK. A redeclared literal equal to today's value passes every
# equality read, so `tests/test_constants.py` mutates `MODEL_CHOICES`, re-executes this module
# and asserts both names MOVED — a check only a read-through binding survives.
#
# ROLL_AGE — the single lumped 75+ bucket's hazard age (Tranche-1 coarseness, the plan body's).
# A MODEL choice and not an index: the bucket holds everyone 75+ and is decremented at one age,
# so raising or lowering it moves S for every geography. IT NO LONGER SELECTS THE BUCKET'S
# OWNERSHIP RATE (operator ruling X1, 2026-08-21): `_standing_stock` values the bucket at the
# POPULATION-WEIGHTED mean of the per-age rates over the ages it actually holds, so the rate is
# the slice's own and no band read at this age enters S. What still rides ROLL_AGE is the
# HAZARD and the living-arrangement read, both unchanged. NOT retired here: Tranche 2's
# age-indexed 75+ lattice is what removes the single-bucket coarseness itself.
# P_NONIMM_RANGE — the age span the ALL-MAINTAINER ownership propensity is read OVER for the
# immigrant leg (the name predates amendment #24(A), which measured that the cube behind it has
# no immigrant dimension; `_OwnershipReader.p_nonimm` states what the rate is and where the
# conversion to a non-immigrant LEVEL happens). Spec §6 defines `p_imm(a) = p_nonimm(a) x ratio` age-indexed while the ISQ
# arrival flow carries no age axis, so the leg needs ONE rate for the whole span PR arrivals
# concentrate in. THIS WAS AN AGE (`p_nonimm_age = 40`) UNTIL RULING X2: 40 selected whichever
# band contained it, which under the retired 30-year `25-54` band WAS the 25-54 household-
# weighted union and after ruling W was `35-44` alone (+2.87 pp, an undeclared shift). The span
# is now read as an aggregate BY CONSTRUCTION — `census.ownership_union_rates` sums owner and
# total counts over 25-34 / 35-44 / 45-54 and divides once — so no age inside it is picked and
# there is no point pick left to sweep. What remains UNCITED is the SPAN, recorded at
# `MODEL_CHOICE_PROVENANCE["p_nonimm_range"]`.
ROLL_AGE = MODEL_CHOICES["roll_age"]
P_NONIMM_RANGE = MODEL_CHOICES["p_nonimm_range"]

# The full single-year age lattice the ISQ population frames publish. A cell missing from it is
# a HOLED frame, never an empty cohort — see `_pop_by_age`.
POP_AGES = tuple(range(0, 101))


# ===========================================================================================
# THE IDENTITY ENVELOPE — every input the run READS, with its digest and its extraction date.
# ===========================================================================================
#
# THE PLAN COVERED THREE OF THIRTEEN (and the fourteenth, the mortality basis, is not a file at
# all — see BASIS_RECORDED_AT). Its `ALLOWED_SOURCE_KEYS` named `ownership_by_geo_age.json`,
# `headship_by_age.json` and `living_arrangement.json` and filtered them through `.exists()`, so
# every population and immigrant-flow workbook — the inputs that drive the entire model — was
# outside the envelope, and an absent input VANISHED from the vintage instead of refusing. The
# envelope's claim is that a red is attributable to data-vs-code; for ten inputs it could not
# make that call.
#
# THE DIGESTS ARE TAKEN OVER `data_dir`, NEVER TRANSCRIBED FROM A REGISTRY (review finding F1).
# The landed body emitted `WORKBOOK_SHA256[name]` and `raw_anchor(name)` — MODULE CONSTANTS —
# and checked only that the file existed, on the argument that the loaders verify their pins on
# the way in. Two things were wrong with it. The argument does not cover the census extract at
# all: no runtime path opens that file, so replacing it with `b"garbage"` left the run COMPLETING
# and publishing its pin unchanged (measured). And a "digest" that is read from the same constant
# the check compares against is a check that cannot fail. Every declared file is hashed here from
# the bytes on disk, and a pinned file whose bytes have drifted REFUSES — the envelope publishes
# what it verified, not a second unverified copy of it.
#
# THE FOUR DERIVED RATE ARTIFACTS ARE DECLARED TOO, and that is the other half of F1. The landed
# body named their upstream SOURCES instead, on the argument that each artifact refuses at load
# if its recorded source digests drift from the pins (steering ruling L). That gate is real and
# still runs — and it is blind in the direction the model's numbers live in: the loaders verify
# `_provenance`, never the payload. Editing one rate cell and leaving `_provenance` alone loads
# clean, moves every geography's ED and can REORDER the rankings under a byte-identical envelope
# (measured). Every rate in this model is read from one of those four files, so the sources are
# kept AND the artifacts are added; neither substitutes for the other.
#
# RECORDED, NOT PINNED, for those four — the same class as the IRCC feed rather than a weaker
# one. They are GENERATED by `scripts/gen_*.py` from pinned sources, so a pin here would make
# every legitimate regeneration a registry edit in this file. What §9 needs from the envelope is
# ATTRIBUTION — two runs over different bytes must be distinguishable — and a digest taken over
# the bytes read discharges that whether or not a second registry also fixes them.
#
# `census_tenure_age_98100231.csv` PUBLISHES its raw anchor while being verified like any other
# pinned file, and that substitution is spec §7's own: the extract sits one link down pins.py's
# chain (raw response -> filter predicate -> committed extract), so the RAW member's digest is
# what §7's field is defined as. `publishes` decides which digest rides the artifact; it never
# decides whether the file is checked.
#
# `extracted_at` IS PROVENANCE, NOT A STAMPED LITERAL (the plan wrote "2026-07-21" onto every
# source hash regardless of when the file was extracted). For the derived artifacts it is READ
# out of the bytes being hashed, so there is only one site and nothing to drift; for the acquired
# sources it is declared below and bound BY TEST to the artifact `_provenance` that records it.
_ISQ_PULL = "2026-07-21"          # git add-date of all five ISQ workbooks; the same date
                                  # `headship_by_age.json._provenance` records for their
                                  # sibling pop-as-qc-base.xlsx.

_COMMITTED = "committed"          # publish the digest of the committed file itself
_RAW_ANCHOR = "raw_anchor"        # publish the RAW upstream member's pinned digest (spec §7)

# THE MORTALITY BASIS IS A THIRD SOURCE CLASS — not a file under `data_dir`, and the one input
# the envelope missed entirely until run 33 (data gate F1). It is the SOLE source of every q
# value the supply side rides on, it lives behind a uv path dependency with no digest, and
# `_source_hashes` ranges over `data_dir` — so two runs over DIFFERENT upstream mortality tables
# emitted DIFFERENT `rankings.json` bytes under a BYTE-IDENTICAL envelope, and the golden's
# attribution table then routed the reader to "the CODE moved", which is a WRONG verdict, not a
# vague one. `cohort/basis.py` computes the digest over the q SURFACE through the §2-sanctioned
# public entry point; `mortality._DATA_DIR` is a private reach-in the spec forbids.
#
# RECORDED, NOT PINNED — the IRCC feed's class, for the IRCC feed's reason: actuarial-system may
# legitimately re-publish, and a pin would turn every refresh into a refusal instead of a
# re-mint. Unlike the feed it is declared UNCONDITIONALLY: every run reads q.
#
# `extracted_at` IS A DECLARED RECORDING DATE, and it is the one entry in this envelope whose
# date is neither an upstream pull nor an artifact's own `_provenance`. The dependency publishes
# no date through any public surface, so the honest field is the day this basis surface was
# measured into the envelope — declared and stated. `tests/test_basis_guard.py` holds a
# test-owned copy of the digest this date describes, so a MOVED basis reds with "re-declare the
# date in the same commit" instead of shipping a fresh digest under a stale date; the golden
# alone would say only "re-mint". Inventing the CPM table's publication
# date would be the precise-but-unsupported citation `loaders/constants.py` refuses by name.
BASIS_RECORDED_AT = "2026-08-19"


@dataclass(frozen=True)
class _Source:
    """One ACQUIRED input the run declares: when it was acquired, why it rides the envelope,
    and which digest spec §7 wants published for it. The bytes are hashed off `data_dir` and
    checked against `pins.WORKBOOK_SHA256` in every case."""

    extracted_at: str
    why: str
    publishes: str = _COMMITTED


RUN_SOURCES: dict[str, _Source] = {
    POP_WORKBOOKS[0]: _Source(_ISQ_PULL, "ISQ scenario population (RMR)"),
    POP_WORKBOOKS[1]: _Source(_ISQ_PULL, "ISQ scenario population (RA)"),
    COMPO_WORKBOOKS[0]: _Source(_ISQ_PULL, "ISQ arrival flows (RMR)"),
    COMPO_WORKBOOKS[1]: _Source(_ISQ_PULL, "ISQ arrival flows (RA)"),
    "pop-as-qc-base.xlsx": _Source(
        _ISQ_PULL,
        "the headship curve's DENOMINATOR (QC persons by single year of age) — read by this "
        "run through headship_by_age.json, whose _provenance names it"),
    CENSUS_EXTRACT: _Source(
        _ISQ_PULL,
        "StatCan 98-10-0231-01 tenure x age — the ownership and headship surfaces' source. "
        "PUBLISHES the RAW upstream member's digest per spec §7's sha256-of-raw-response "
        "definition; the committed extract's own bytes are verified against pins.WORKBOOK_SHA256 "
        "here, and SEPARATELY at loaders/pins.verify_pin inside census.read_totals_cube, which "
        "`_ownership_reader` calls once per run for the P_NONIMM_RANGE aggregate — so this is "
        "one of TWO independent checks, not the only one. It stays because the envelope must "
        "publish the digest of bytes IT read (this claim was stale from operator ruling X2, "
        "2026-08-21, until 2026-08-21: the extract had no runtime reader before that ruling)",
        publishes=_RAW_ANCHOR),
    "living_arrangement_98100134.json": _Source(
        "2026-08-08",
        "StatCan 98-10-0134-01 per-sex living arrangements — read through "
        "living_arrangement.json, whose _provenance records this extraction date"),
    "hors_aligned_csd_98100232.json": _Source(
        "2026-08-15",
        "StatCan 98-10-0232-01 CSD extract — the operand-aligned HORS_RMR ownership curve's "
        "second source, a LIVE model dependency as of this task (the join is consumed), read "
        "through ownership_hors_aligned.json, whose _provenance records this date"),
}

# The GENERATED artifacts the run OPENS. Keyed by each loader's own name constant, never a
# restated literal.
#
# THE PRODUCT IS DELIBERATELY NOT WRITTEN, here or at the three sibling sites below (~440, and
# `_OwnershipReader`'s two). It was "288 times per run" in all four and in four test copies, and
# 288 is 12 legs x 24 — the RETIRED twelve-leg grid. Run 51 deleted seven unbound sweep-count
# WORDS from these docstrings on the ground that a count no gate holds is a staleness generator,
# and 288 survived that sweep because it was the derived PRODUCT of a word, not the word: culling
# the words did not cull the arithmetic built out of them. So these sites now state the
# FACTORIZATION, which cannot go stale when the grid widens. The one place the magnitude carries
# a point a consumer acts on — `artifacts/README.md`'s raw-anchor exposure claim — COMPUTES it
# from `len(sweep_leg_labels()) x geographies x scenarios` and is bound by
# `tests/test_golden.py::test_the_readme_binds_the_p_nonimm_EXPOSURE_COUNT`.
#
# NOT "EVERY RATE THE MODEL MULTIPLIES" — that sentence stood here and is FALSE since operator
# ruling X2 (2026-08-21). `p_nonimm` IS a rate the model multiplies — ONCE PER (leg, geography,
# scenario), every run — and it comes out of the PINNED CENSUS EXTRACT
# `census_tenure_age_98100231.csv`, not out of any of these four: the derived ownership artifact
# publishes band RATES and no counts, and a household-weighted union over a span cannot be
# recovered from rates without the weights. Seven of the eight geographies read it there; the
# eighth, HORS_RMR, reads its span union off `ALIGNED_OWNERSHIP_ARTIFACT`'s own band COUNTS,
# which IS one of these four. The extract is carried in `RUN_SOURCES` above with its digest, so
# the envelope covers it either way — what was wrong was the SCOPE claim, not the coverage.
RUN_ARTIFACTS: dict[str, str] = {
    OWNERSHIP_ARTIFACT: "ownership rate by geography x age band — the ED denominator's tenure "
                        "surface and the household-init tenure split",
    HEADSHIP_ARTIFACT: "headship rate by single year of age — the persons->households map on "
                       "both sides of the balance",
    LIVING_ARRANGEMENT_ARTIFACT: "per-sex living-alone and couple shares — spec §5's "
                                 "initialization equations for every cohort in the 75+ band",
    ALIGNED_OWNERSHIP_ARTIFACT: "the operand-aligned HORS_RMR ownership curve AND the join that "
                                "routes each geography to its curve (spec §6, the #12(B) "
                                "reversal) — consumed by `_OwnershipReader`",
}


def _run_identity(data_dir: Path | None, ircc, now: tuple[int, int]) -> str:
    """The run's FULL identity: the assumption selection, the data vintage AND the clock, in one
    token. THE COMPOSITION GATE'S input (`_refuse_mixed_identity`) and NOT AN EMITTED FIELD.

    IT WAS EMITTED as `run_pairing` under spec amendment #20(C)(3), and amendment #22(C)
    re-specified that field's payload away from this function: the token now binds both
    documents' canonical payload digests (`artifacts.pairing_token`), because nothing in the
    payload below is output content or code identity, so a computation change emitted different
    documents under the same token. THIS function keeps its payload unchanged and its job
    unchanged — it answers "did the run's declared identity move WHILE the numbers were being
    computed", which is a question about the inputs, sampled twice, and needs no output content
    at all. The clock leg still belongs here for exactly that reason.

    CARRY B4, and the reason this is a token rather than a widened `assumptions_hash()`.
    `assumptions_hash` covers the assumption SELECTION — the central/sweep values, banded and
    categorical alike, the unswept model choices, the ruled immigrant join table and (since the
    round-3 audit, 2026-08-22) the anchor registry's values and bands — and
    NOTHING about the data, so
    two runs over different source bytes produce an identical hash; the envelope could not make
    the data-vs-code call §9 rests on. Folding the data digest INTO that hash would fix
    the first half by destroying the second: one token that moves for either cause answers
    neither question. So the emitted envelope keeps TWO fields — `assumptions_hash` (the
    selection) and `data_vintage.source_hashes` (the bytes), the second of which this task
    widened from three inputs to every input the run reads — and the composition gate below
    gets a token over BOTH, which is the thing that has to be constant across a single run.

    `now` IS THE THIRD PAYLOAD MEMBER, and it is what makes this the RUN's identity rather than
    the inputs' — a run is pinned to a clock, and two runs of identical data and identical
    assumptions at different clocks are different runs. It was admitted by amendment #20(C)(3) on
    a stronger claim than today's tree supports: that two runs differing only in the CLOCK emit
    DIFFERENT `tripwire_baseline.json` bytes, because `now` is the freshness axis. MEASURED FALSE
    on the committed vintage (2026-08-23) — all six indicators are structurally UNKNOWN with a
    null `as_of` and a null `current_value`, so the clock reaches no emitted value and a December
    run and a November run emit byte-identical documents apart from the pairing token. The
    premise becomes true the day the first indicator carries a real value; until then the clock
    is an input this function sees and no output records, which is precisely why it cannot be the
    pairing token's job (amendment #22(C)) and can still be this one's.

    DETERMINISTIC, NEVER A NONCE. A random token would let the composition gate fire on every
    honest run; this one is stable exactly when the inputs including the clock are.
    """
    payload = json.dumps({"assumptions": assumptions_hash(),
                          "sources": _source_hashes(data_dir, ircc),
                          "now": list(now)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:ASSUMPTIONS_HASH_CHARS]


def _refuse_mixed_identity(identities: set[str]) -> None:
    """spec §7b's composition rule — "rankings are computed within a single run (one data
    vintage, one assumptions_hash); cross-vintage comparison is refused at the emitter" — with
    an input that can actually fail.

    The plan called `refuse_cross_vintage({assumptions_hash()})`: a ONE-element set built from
    the hash computed on the line above, so the gate could not fire under ANY input. The set
    here is sampled BEFORE the ED grid and AGAIN after the robustness sweep, so what it refuses
    is a run whose declared identity MOVED while its numbers were being computed — rows from
    two identities under one envelope, which is exactly what §7b forbids and what no
    single-sample check can see.

    That shape is reachable rather than theoretical in this tree: `CENTRAL_ASSUMPTIONS` is a
    plain mutable dict and `cohort/listings.py` binds three of its members READ-THROUGH AT
    IMPORT (`tests/test_listings.py` mutates the dict and reloads the module to prove it), so
    an in-process assumption edit moves the run's numbers and its hash together.
    """
    refuse_cross_vintage(identities)


def _read_declared(dd: Path, name: str) -> bytes:
    """The bytes of one declared input, refusing an absent file by name.

    ABSENCE IS DATA, NEVER PROOF (carry B5). The plan wrote
    `for name in ALLOWED_SOURCE_KEYS if (dd / name).exists()`, so a missing input dropped out of
    the vintage and the artifact shipped looking fully provenanced.
    """
    path = dd / name
    if not path.is_file():
        raise LoaderError(
            f"identity envelope: {name} is declared as an input this run reads but is not "
            f"present at {dd} — an absent input is reported, never inferred away")
    return path.read_bytes()


def _verify_pinned(name: str, digest: str) -> None:
    """Refuse a declared source whose BYTES have moved off its pin.

    This is `pins.verify_pin`'s check taken over bytes this function has already read, rather
    than a second read of the same file. It is not a duplicate of the loaders' own pin checks:
    `living_arrangement_98100134.json`, `hors_aligned_csd_98100232.json` and
    `pop-as-qc-base.xlsx` are DERIVATION-time inputs that no runtime path opens, so for those
    THREE this is the only place the committed bytes are checked at all — and the landed body
    checked nothing, which is how a garbage census extract left a run completing with an
    unchanged envelope (review finding F1).

    `census_tenure_age_98100231.csv` LEFT THAT SET at operator ruling X2 (2026-08-21): the
    immigrant leg's propensity is an aggregate over `P_NONIMM_RANGE` formed from that extract's
    own counts, which the derived rate artifact does not publish, so `_ownership_reader` now
    opens it once per run through `census.read_totals_cube` — which `verify_pin`s it itself.
    Its check here is therefore a second, independent one rather than the only one. It stays:
    the envelope must publish the digest of bytes IT read, not one another module vouched for.
    """
    expected = WORKBOOK_SHA256.get(name)
    if expected is None:
        raise LoaderError(
            f"identity envelope: {name} is declared as a pinned input but pins.WORKBOOK_SHA256 "
            "registers no digest for it — an unpinned file cannot be published as a verified "
            "one, so the run refuses rather than emitting a digest it did not check")
    if digest != expected:
        raise LoaderError(
            f"identity envelope: sha256 drift for {name} — pinned {expected}, read {digest} at "
            "run time. The envelope publishes the bytes it verified; a run over different bytes "
            "is a different vintage and must be re-pinned deliberately, never absorbed")


def _artifact_extracted_at(name: str, raw: bytes) -> str:
    """A derived artifact's OWN recorded extraction date, read from the bytes being hashed.

    Carry B6, with the second declaration site removed rather than bound: the plan stamped
    "2026-07-21" onto every source hash, and an artifact that records no date has none — not
    today's, and not its neighbour's.
    """
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise LoaderError(
            f"identity envelope: {name} is a declared derived artifact but is not readable JSON "
            f"({exc}) — its provenance cannot be read, so its extraction date cannot be "
            "published") from exc
    provenance = payload.get("_provenance") if isinstance(payload, dict) else None
    recorded = provenance.get("extracted_at") if isinstance(provenance, dict) else None
    if not isinstance(recorded, str):
        raise LoaderError(
            f"identity envelope: {name} records no `_provenance.extracted_at` ({recorded!r}) — "
            "the date is READ from the artifact rather than stamped on it, so an artifact that "
            "states no extraction date has none and the run refuses rather than inventing one")
    return recorded


def _source_hashes(data_dir: Path | None, ircc) -> dict:
    """spec §7 `data_vintage.source_hashes`, over EVERY input the run read.

    Three refusal doors on the FILE inputs, all of them carry B5/B5b's and all of them naming
    the file: an input that is absent, one that is declared but carries no source record, and
    one whose pinned bytes have drifted. A declared input that cannot be hashed is never dropped.

    THE FILES ARE HASHED OFF DISK; the two non-file inputs are not files and say so. The
    mortality basis is digested over the q surface it answers with (see BASIS_RECORDED_AT) and
    the IRCC feed's digest is recorded at read time. Both are declared here rather than left
    out — an input outside the envelope is the one class §9's attribution cannot make a call on.
    """
    dd = data_dir or DATA_DIR
    out: dict[str, dict[str, str]] = {}
    for name, source in sorted(RUN_SOURCES.items()):
        if not isinstance(source, _Source):
            raise LoaderError(
                f"identity envelope: {name} is declared as an input this run reads but carries "
                f"no source record ({source!r}) — an input read but unhashed cannot be "
                "attributed, so the run refuses rather than shipping a partial vintage")
        digest = hashlib.sha256(_read_declared(dd, name)).hexdigest()
        _verify_pinned(name, digest)
        datetime.fromisoformat(source.extracted_at)      # a calendar, not a shape
        entry = {"sha256": digest, "extracted_at": source.extracted_at}
        if source.publishes == _RAW_ANCHOR:
            # TWO SEMANTICS, TWO FIELDS (spec amendment #20(C)(1)). `sha256` publishes the RAW
            # upstream member's digest per §7's sha256-of-raw-response definition — the one link
            # a re-extract cannot move with — and `committed_sha256` publishes the digest of the
            # bytes THIS RUN READ off disk, which is the one a consumer reproduces with
            # `sha256sum`. It was already computed and already pin-checked two lines up and then
            # DROPPED, for exactly the one key whose consumers most need it (since ruling X2 that
            # extract supplies `p_nonimm`, a rate the model multiplies once per leg x
            # geography x scenario). The
            # vintage INVARIANT never needed it; VERIFIABILITY did.
            entry = {"sha256": raw_anchor(name), "extracted_at": source.extracted_at,
                     "committed_sha256": digest}
        out[name] = entry

    for name in sorted(RUN_ARTIFACTS):
        raw = _read_declared(dd, name)
        recorded = _artifact_extracted_at(name, raw)
        datetime.fromisoformat(recorded)                 # a calendar, not a shape
        out[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "extracted_at": recorded}

    # The mortality basis joins from OUTSIDE `data_dir` entirely (see BASIS_RECORDED_AT): the
    # digest is taken over the q surface the model consumes, through the public basis surface.
    # Unconditional — every run reads q, including the tripwire listing, which inherits the
    # envelope's refusal doors by the same design that gave it the other twelve entries.
    datetime.fromisoformat(BASIS_RECORDED_AT)            # a calendar, not a shape
    out[BASIS_SOURCE_KEY] = {"sha256": basis_digest(), "extracted_at": BASIS_RECORDED_AT}

    # The IRCC feed joins from the other side: its digest is RECORDED at read time (monthly
    # refresh, no pin) and it is declared ONLY when the run actually read it. Declaring it
    # unconditionally would put a key in the envelope for bytes no run touched.
    if ircc is not None and ircc.available and ircc.sha256:
        out[IRCC_CSV_NAME] = {"sha256": ircc.sha256, "extracted_at": _ircc_extracted_at(ircc)}
    return out


def _ircc_extracted_at(ircc) -> str:
    """The feed's own coverage statement as a calendar date.

    `PRLandings.as_of` is `YYYY-MM` — an ISO-8601 year-month, which `datetime.fromisoformat`
    rejects, so it cannot ride the envelope's ISO-8601-validated position unchanged. The first
    of the published month is the earliest instant the period can denote and is DERIVED from
    the feed rather than stamped: nothing here invents a day the feed did not publish, it
    widens a month to the date form the field is defined in.
    """
    year, month = ircc.latest_period
    return f"{year:04d}-{month:02d}-01"


def _data_vintage(data_dir: Path | None, ircc) -> dict:
    """spec §7's Tranche-1 envelope. `artifacts.DATA_VINTAGE_FIELDS` closes it at
    `source_hashes` — §7a's fuller {isq_edition, census_year, constants_as_of} shape belongs to
    the Tranche-2 ScenarioPrior emitter, and the ISQ edition identity is already carried by
    digest (the workbooks are byte-pinned)."""
    return {"source_hashes": _source_hashes(data_dir, ircc)}


# ===========================================================================================
# THE TRIPWIRE GATE — no hardcoded value, no vacuous band, no green that cannot go red.
# ===========================================================================================
#
# THE DEFECT THIS REPLACES, stated so it cannot be restored by someone who reads only the
# result: the plan built `TripwireSpec("pr_landings_annual", 40000.0, 50000.0, ...)` and fed it
# `45000.0 if pr.available else None` — a literal sitting inside its own band, compared against
# that band, green forever, on any data, in any era. It never called `evaluate_pr_landings`, so
# the measured-realized path, the plan-era gate, the degenerate-feed floor, the freshness gate
# and ruling U's member-set completeness contract were all bypassed. It fed
# `natural_increase_sign` a hand-typed -1200.0 against a [-1e9, 1e9] band, which reports OK
# forever BY CONSTRUCTION, and `cmhc_senior_sale_5yr` the model's OWN anchor value against a
# band bracketing it — the same shape one file over.
#
# THE RULE APPLIED HERE, uniformly: an indicator's current value is MEASURED FROM A SOURCE or it
# is NULL. An operator-supplied indicator with no operator input carries None, which the gate
# turns into `operator_input_missing`; a wired indicator with no wired source is `available=False`,
# which the gate turns into `source_unavailable`. Both are UNKNOWN, and UNKNOWN is the honest
# answer — spec §7c is a verification gate and "must refuse, never false-green".
#
# A BAND IS A RULED VALUE, NOT AN IMPLEMENTER'S JUDGMENT CALL. `output/tripwires.py` states it
# at the top of its own file: no band literal lives there, because a threshold typed inside the
# gate is a parameter the gate invented and the same edit that widened it would silently
# re-verdict every past run. That argument does not stop at the module boundary, so the three
# bands the plan left VACUOUS — `temp_resident_stock` [0, 1e9], `registre_foncier_volume`
# [0, 1e9], `natural_increase_sign` [-1e9, 1e9] — are not re-typed here at some plausible width.
UNRULED_BAND = (0.0, 0.0)
# A DEGENERATE band admits NO value as OK: `evaluate_indicator`'s closed-band test is
# `v <= lo or v >= hi`, which is true for every real v when lo == hi. So the placeholder is
# fail-safe BY CONSTRUCTION rather than by anyone remembering to keep the value null — the
# opposite of [0, 1e9], which reports OK for every positive number. It is a placeholder for a
# threshold that does not exist, never a threshold, and `_evaluate_declared` REFUSES to judge a
# real measurement against it: the day a feed lands for one of these three, the run stops until
# a band is ruled, instead of quietly publishing a verdict off a number nobody set.

TRIPWIRE_BANDS: dict[str, tuple[float, float]] = {
    # Kept VERBATIM from the plan. These three are not vacuous and a band is not this
    # implementer's to move; each is recorded with what it is anchored to and what it is not.
    PR_LANDINGS_INDICATOR: (40000.0, 50000.0),
    # ^ brackets CONSTANTS["mifi_pr_annual_plan"] = 45,000/yr (MIFI Plan d'immigration du Québec
    #   2026-2029, released 2025-11-06). The LEVEL is anchored; the +/-5,000 half-width is the
    #   plan document's and is anchored in neither constants.py nor probes/P5.
    "isq_edition_watch": (2025.5, 2027.5),
    "cmhc_senior_sale_5yr": (0.30, 0.42),
    # ^ brackets CONSTANTS["cmhc_senior_sale_5yr"] = 0.36. Note that the SPEC-ruled band on this
    #   quantity's annualized twin is CONSTANTS["q_live_annual"].band = [0.06, 0.11]/yr, which
    #   compounds to [0.2661, 0.4416] over five years — a DIFFERENT interval. Recorded, not
    #   reconciled: choosing between them is a band ruling.
    "temp_resident_stock": UNRULED_BAND,
    "registre_foncier_volume": UNRULED_BAND,
    "natural_increase_sign": UNRULED_BAND,
}

# (as_of, freshness_years, source_kind) per indicator — the plan's, unchanged. All six are
# UNKNOWN under a nullable reason on the committed tree, so `as_of` is emitted NULL and the
# freshness gate is never reached; these matter the moment a real value lands.
# PUBLISHED PER ROW since spec amendment #21 (2026-08-22): `freshness_years` and `source_kind`
# join `tripwire_baseline.json`'s OPTIONAL members. Run 49 ruled this ledger OUT of
# `assumptions_hash` on the argument that what the output PUBLISHES needs no token — true for
# `TRIPWIRE_BANDS`, whose endpoints ride every row as `band_low`/`band_high`, and NOT true for
# this one, which was published nowhere. Publishing (not hashing) is what makes the exclusion
# sound for both: hashing a tripwire-only declaration would re-mint the RANKINGS' identity for a
# verification-gate ruling that cannot move a single ED, because both documents carry the same
# `assumptions_hash`.
# `as_of` IS `None` FOR PR LANDINGS, AND THAT IS THE FIX RATHER THAN THE GAP (2026-08-22). It
# read `2026`, and that literal governed NOTHING: `_tripwire_results` routes this one indicator
# through `evaluate_pr_landings`, which DERIVES `as_of` from the feed itself (`max` of the closed
# plan-governed years) — the only honest as_of for a REALIZED-landings measurement — and takes
# only members [1] and [2] from this row. So `_spec_for(PR_LANDINGS_INDICATOR)` is never called,
# and the ledger amendment #21 has just made load-bearing was publishing a plausible-looking year
# that nothing read and nothing could contradict. `None` says "derived at evaluation, not declared
# here" in the type, and `_spec_for` refuses it rather than passing it on, so re-routing this
# indicator through the declared path is a named error instead of a silently null as_of.
_TRIPWIRE_DECLARATIONS: dict[str, tuple[int | None, int, SourceKind]] = {
    PR_LANDINGS_INDICATOR: (None, 1, SourceKind.WIRED),
    "temp_resident_stock": (2026, 1, SourceKind.WIRED),
    "isq_edition_watch": (2026, 1, SourceKind.WIRED),
    "registre_foncier_volume": (2026, 1, SourceKind.OPERATOR_SUPPLIED),
    "cmhc_senior_sale_5yr": (2021, 5, SourceKind.OPERATOR_SUPPLIED),
    "natural_increase_sign": (2026, 1, SourceKind.OPERATOR_SUPPLIED),
}


def _spec_for(indicator: str) -> TripwireSpec:
    as_of, freshness, kind = _TRIPWIRE_DECLARATIONS[indicator]
    if as_of is None:
        raise CalibrationError(
            f"tripwire {indicator!r} declares no `as_of` — its measurement DATES ITSELF from the "
            "feed (see `evaluate_pr_landings`), so it has no declared as_of to evaluate against "
            "and must not be routed through the declared path. A `TripwireSpec` built here would "
            "carry a null as_of into the generic gate, which is the shape a record cannot ride")
    lo, hi = TRIPWIRE_BANDS[indicator]
    return TripwireSpec(indicator, lo, hi, as_of, freshness, kind)


def _evaluate_declared(indicator: str, value, available: bool, now: int) -> TripwireResult:
    """Evaluate one declared indicator, refusing to judge a value against an unruled band."""
    if TRIPWIRE_BANDS[indicator] == UNRULED_BAND and available and value is not None:
        raise CalibrationError(
            f"tripwire {indicator!r} has a real measurement ({value!r}) and no ruled band — "
            f"the placeholder {UNRULED_BAND} is a statement that no threshold exists, not a "
            "threshold. A band is a ruled value; the run refuses rather than publishing a "
            "verdict off a width nobody set")
    return evaluate_indicator(_spec_for(indicator), value, available=available, now=now)


def _tripwire_results(landings, now: tuple[int, int]):
    """The six code-required indicators, evaluated. Returns (results, run-log lines).

    `now` is INJECTED as (year, month) for `output/tripwires.py`'s stated reason: a wall-clock
    read inside a verification gate makes its verdict unreproducible, and freshness is exactly
    what an auditor re-checks.

    THE FEED IS HANDED IN, NOT RE-READ (review finding F3). The landed body called
    `load_pr_landings` a SECOND time here while `run_pipeline` had already loaded it for the
    envelope and the identity token — and `_refuse_mixed_identity` is sampled before this
    function runs, so the published digest and the published verdict could come from two
    different reads of a deliberately UNPINNED, monthly-refreshing feed with nothing structurally
    able to see it. One read per run puts the feed's bytes inside the bracket the composition
    gate already claims to cover.
    """
    log: list[str] = []
    pr = evaluate_pr_landings(landings, band=TRIPWIRE_BANDS[PR_LANDINGS_INDICATOR], now=now,
                              freshness_years=_TRIPWIRE_DECLARATIONS[PR_LANDINGS_INDICATOR][1],
                              source_kind=_TRIPWIRE_DECLARATIONS[PR_LANDINGS_INDICATOR][2])
    log.append(f"{PR_LANDINGS_INDICATOR}: {pr.log}")

    # THE UNRULED-BAND REFUSAL NOW COVERS BOTH PATHS (2026-08-22). `_evaluate_declared` refuses
    # to judge a real measurement against `UNRULED_BAND` — "a band is a ruled value; the run
    # refuses rather than publishing a verdict off a width nobody set" — and `evaluate_pr_landings`
    # had no such check, so the same placeholder on THIS indicator would have produced a published
    # verdict instead of a refusal. It is not reachable today (this band is ruled, and the three
    # unruled indicators all route through `_evaluate_declared`), which is exactly why it is closed
    # now: the asymmetry was in the guard, not in the data, and an argument that holds for one of
    # two paths is the class this module keeps re-finding. POST-evaluation because the measurement
    # is DERIVED from the feed here rather than handed in — there is no value to test until the
    # evaluation has produced one — and BEFORE the result joins `results`, so a refused verdict
    # cannot reach the emitter.
    if (TRIPWIRE_BANDS[PR_LANDINGS_INDICATOR] == UNRULED_BAND
            and pr.result.current_value is not None):
        raise CalibrationError(
            f"tripwire {PR_LANDINGS_INDICATOR!r} evaluated a real measurement "
            f"({pr.result.current_value!r}) against no ruled band — the placeholder "
            f"{UNRULED_BAND} is a statement that no threshold exists, not a threshold. A band is "
            "a ruled value; the run refuses rather than publishing a verdict off a width nobody "
            "set (the same refusal `_evaluate_declared` makes for the other five)")

    results = [pr.result]
    for indicator, value, available, note in (
        # WIRED, and NOT wired to anything in this repo. probes/P5b-temp-resident-stock.md
        # rules it: "DECISION-TRIPWIRE-STATUS: UNKNOWN — the source is RECORDED here, not yet
        # wired; per spec:473 the temporary-resident-stock indicator reports UNKNOWN until
        # wired, never a stale within-band".
        ("temp_resident_stock", None, False,
         "no temporary-resident feed is wired in this repo (probe P5b, DECISION-TRIPWIRE-STATUS)"),
        # WIRED, and the same shape. The plan fed it a hardcoded 2026.0 inside a hardcoded
        # (2025.5, 2027.5) band: both literals live in the same file, so it is green forever.
        # The edition this run uses is the PINNED workbooks' and cannot move without a
        # deliberate re-pin, and detecting a NEW ISQ edition means reading ISQ's own
        # publication surface, which no committed source carries. The real edition guard is
        # already elsewhere and is fail-loud: `geography.SCENARIO_LABEL_TO_ENUM` raises on an
        # unknown ISQ scenario label, so a different-edition workbook cannot load at all.
        ("isq_edition_watch", None, False,
         "no ISQ edition-publication source is committed; the pinned workbooks cannot report "
         "an edition other than their own, and a drifted edition is already refused at load "
         "by the scenario-label junction"),
        ("registre_foncier_volume", None, True,
         "manual v0 indicator (spec §7c) — no operator input supplied for this run"),
        # The plan fed this CONSTANTS["cmhc_senior_sale_5yr"].value = 0.36 against a band
        # bracketing 0.36. An operator-supplied indicator fed the model's OWN anchor is a
        # constant compared against a constant: it cannot report anything but OK, and what it
        # exists to detect is a CMHC refresh moving away from that anchor.
        ("cmhc_senior_sale_5yr", None, True,
         "no CMHC senior-sale-rate refresh supplied for this run; the model's own anchor "
         f"({CONSTANTS['cmhc_senior_sale_5yr'].value}) is not a measurement of it"),
        # The plan fed this a hand-typed -1200.0 against [-1e9, 1e9].
        ("natural_increase_sign", None, True,
         "no ISQ natural-increase release supplied for this run"),
    ):
        results.append(_evaluate_declared(indicator, value, available=available, now=now[0]))
        log.append(f"{indicator}: {note}")

    # Completeness over the CODE-owned required set (empty here — every required indicator is
    # evaluated above; `check_registry` RAISES on an unregistered or empty set).
    results += check_registry([r.indicator for r in results])
    return results, log


# ===========================================================================================
# THE OWNERSHIP CURVE — read the join, never re-derive the scope fence.
# ===========================================================================================

class _OwnershipReader:
    """`rate(geography, age)` routed by `ownership_hors_aligned.json`'s own `join` block.

    The join names every modeled geography and states which curve it reads and why; it is
    validated for CONTENT at load (`hors_aligned._verify_join` — exactly one geography reads
    the aligned curve, and it must be the pinned one). A `geography is HORS_RMR` test in this
    file would be a THIRD statement of that fence and the one a reader would have to reconcile
    against the artifact by hand.

    TWO QUESTIONS, ONE ROUTER (operator ruling X2, 2026-08-21). `__call__` answers "the rate AT
    an age"; `p_nonimm` answers "the rate OVER `P_NONIMM_RANGE`", which is a household-weighted
    aggregate and not any band's value. Both are routed by the SAME join, because the routing
    question — whose territory is this geography's — is identical for both and a second
    dispatch would be a second place for the scope fence to drift.

    WHAT THE PARAGRAPH ABOVE DOES **NOT** LICENSE, and the distinction cost a real defect
    (2026-08-21). "No `geography is HORS_RMR` test in this file" is a rule about re-deriving the
    JOIN — which geography reads which curve. It is NOT a licence to skip the check that the
    aligned CURVE is only ever read at the geography it was measured over. `__call__` does not
    skip it: it routes through `aligned_ownership_rate`, which REFUSES a geography that is not
    `ALIGNED_GEOGRAPHY`. `p_nonimm` returned `self.aligned_union` — one float, pinned to that
    same territory by construction — to ANY geography the join marked aligned, with no check at
    all. Measured: with a join re-pointed so LAVAL_RA13 reads aligned, `read(LAVAL_RA13, 40)`
    refuses while `p_nonimm(LAVAL_RA13)` returned 0.6901488081776652 for a geography whose own
    span union is 0.5119964493642796 — 17.8 pp of wrong-territory rate, on a path evaluated
    once per (leg, geography, scenario). So `p_nonimm` now carries the MIRROR of
    `aligned_ownership_rate`'s
    fence, which is the accessor's own guard restated at the one aligned path that had none, and
    not a third statement of the join.

    THE UNIONS ARE RESOLVED ONCE, at construction (see `_ownership_reader`): the census side
    forms its aggregate from the pinned 10 MB extract, and the ED path is evaluated once per
    (leg, geography, scenario) across the whole declared sweep.
    """

    _ALIGNED = "operand_aligned"
    _SHIPPED = "shipped"

    def __init__(self, shipped: dict, aligned: dict, join: dict,
                 shipped_union: dict | None = None, aligned_union: float | None = None) -> None:
        self.shipped, self.aligned, self.join = shipped, aligned, join
        # DEFAULT `None`, and asking for a union that was never resolved REFUSES rather than
        # falling back to a band read. The join-contract tests construct this reader with the
        # three routing arguments alone, on purpose; nothing on the model path may.
        self.shipped_union, self.aligned_union = shipped_union, aligned_union

    def reads_aligned(self, geography: Geography) -> bool:
        row = self.join.get(geography.value)
        if not isinstance(row, dict) or row.get("reads") not in (self._ALIGNED, self._SHIPPED):
            raise LoaderError(
                f"ownership join states nothing usable for {geography.value}: {row!r} — the "
                "join is the run's statement of which curve each geography reads, and a "
                "geography it does not answer for has no curve rather than a default one")
        return row["reads"] == self._ALIGNED

    def __call__(self, geography: Geography, age: int) -> float:
        if self.reads_aligned(geography):
            return aligned_ownership_rate(self.aligned, geography, age)
        return ownership_rate(self.shipped, geography, age)

    def p_nonimm(self, geography: Geography) -> float:
        """The ALL-MAINTAINER ownership propensity over `P_NONIMM_RANGE`, for the immigrant leg.

        THIS DOCSTRING SAID "the non-immigrant ownership propensity" AND THAT WAS FALSE
        (amendment #24(A), 2026-08-23). The cube this rate is read from — 98-10-0231-01, via
        `census.ownership_union_rates` — carries NO immigrant dimension, so its denominator is
        every private-household maintainer: immigrants, non-immigrants AND non-permanent
        residents. Corroborated across cubes at MTL_RMR, where that cube's total private
        households (1,835,705) equals the immigrant cube's three population-characteristics
        members summed, difference 0. The shipped `p_nonimm(MTL_RMR)` is
        490,275 / 957,575 = 0.5119964493642796 over the span — an all-maintainer rate, recomputed
        from the committed CSV.
        THE METHOD NAME IS KEPT ON PURPOSE. `P_NONIMM_RANGE` and
        `MODEL_CHOICES["p_nonimm_range"]` are the span's declared identity and the consumer page
        binds a claim about this accessor by name; renaming the accessor would move three
        published surfaces to restate a fact the caller already states at the conversion. WHAT
        CONSUMES THIS converts it: `_ed_series` divides by the geography's pooled-denominator
        bias `B` before the ratio multiplies, and the converted operand is
        "non-immigrant LEVEL, all-maintainer SHAPE" — a per-geography scalar cannot correct a
        SHAPE, which is spec §6's NAMED LIMIT (C) and Tranche-2 acquisition work.

        NOT A BAND READ. The §6 immigrant equation multiplies an arrival flow that carries no
        age axis, so it needs one rate for the whole span — the span's owner counts over its
        total counts, which is what the two union accessors form. Reading any single age inside
        the span instead returns one sub-band's rate: at MTL_RMR that is 0.3435 (25-34), 0.5407
        (35-44) or 0.6216 (45-54) against the span's own 0.5120.
        """
        aligned = self.reads_aligned(geography)
        if aligned and geography is not ALIGNED_GEOGRAPHY:
            # THE MIRROR OF `aligned_ownership_rate`'s FENCE. `aligned_union` is ONE float,
            # measured over ALIGNED_GEOGRAPHY's territory alone, so handing it to a second
            # aligned geography serves a rate for the wrong territory — a plausible ownership
            # fraction, which is why nothing downstream could notice. `__call__` refuses this
            # through the rate accessor; this path did not, and the asymmetry is what made the
            # hazard `_ownership_reader` closed on the SHIPPED side survive on the aligned one.
            raise LoaderError(
                f"{geography.value} is marked operand_aligned but the aligned "
                f"{P_NONIMM_RANGE[0]}-{P_NONIMM_RANGE[1]} ownership union is measured over "
                f"{ALIGNED_GEOGRAPHY.value}'s territory ALONE — there is one aligned span "
                "union, not one per geography, so this would serve a wrong-territory rate. A "
                "second aligned geography needs its own union extracted, not this one reused")
        union = self.aligned_union if aligned else (self.shipped_union or {}).get(geography.value)
        if union is None:
            raise LoaderError(
                f"no {P_NONIMM_RANGE[0]}-{P_NONIMM_RANGE[1]} ownership union for "
                f"{geography.value} on the {'aligned' if aligned else 'shipped'} curve — this "
                "reader was built without one, and the immigrant leg's propensity is an "
                "aggregate over that span, never a band rate read at some age inside it")
        return union


def _ownership_reader(data_dir: Path | None) -> _OwnershipReader:
    """The routed rate reader, with both `P_NONIMM_RANGE` aggregates already formed.

    The union reads happen HERE and not on the ED path: `ownership_union_rates` parses the
    pinned Census extract, and the ED path runs once per (leg, geography, scenario).

    THE SHIPPED MAP IS PRUNED TO WHAT THE JOIN ACTUALLY ROUTES TO IT, and that is a HAZARD
    being closed rather than a tidy-up. `census.ownership_union_rates` has a STRICT join — it
    raises unless it emits a rate for every modeled geography — so it necessarily builds a
    HORS_RMR entry, and that entry is the CENSUS-NET residual over the span (0.6804520271369382
    at 25-54). HORS_RMR does not read it: the join sends that geography to the operand-aligned
    territory, whose own span union is 0.6901488081776652. The two are ~1 pp apart and BOTH are
    plausible HORS_RMR ownership fractions, so a join re-point, a new geography, or a routing
    refactor could serve the wrong TERRITORY without anything looking wrong — which is the exact
    defect class `hors_aligned.py` exists to remove, reappearing one level up.

    Dropping it from the SOURCE is not available (the strict join requires it) and leaving it
    reachable is what has no gate, so it is dropped HERE, at the routing boundary, and dropped
    BY THE JOIN rather than by naming a geography: any row the join sends to the aligned curve
    loses its shipped union, so asking for one hits `p_nonimm`'s refusal instead of a
    wrong-territory rate. The routing question is asked through `reads_aligned`, the one place
    that fence is stated, which is why a throwaway router is built first.
    """
    lo, hi = P_NONIMM_RANGE
    shipped = load_ownership_rates(data_dir=data_dir)
    aligned = load_aligned_ownership_rates(data_dir=data_dir)
    join = load_aligned_ownership_join(data_dir=data_dir)
    router = _OwnershipReader(shipped, aligned, join)
    return _OwnershipReader(
        shipped, aligned, join,
        shipped_union={geo: rate
                       for geo, rate in ownership_union_rates(lo, hi, data_dir=data_dir).items()
                       if not router.reads_aligned(Geography(geo))},
        aligned_union=aligned_ownership_union(lo, hi, data_dir=data_dir))


# ===========================================================================================
# LOADING
# ===========================================================================================

@dataclass(frozen=True)
class Frames:
    pop: pd.DataFrame
    compo: pd.DataFrame
    # EVERY carried headship shape, not one curve: `headship_shape` is a declared robustness
    # axis, so a leg must be able to reach the other arm without re-reading and re-verifying
    # the same artifact bytes once per leg.
    headship: dict[str, dict[int, float]]
    la: dict


def _load_all(data_dir: Path | None) -> Frames:
    pop = pd.concat([load_population(w, data_dir=data_dir) for w in POP_WORKBOOKS],
                    ignore_index=True)
    compo = pd.concat([load_immigrant_flows(w, data_dir=data_dir) for w in COMPO_WORKBOOKS],
                      ignore_index=True)
    return Frames(pop=pop, compo=compo,
                  headship=load_headship_curves(data_dir=data_dir),
                  la=load_living_arrangement(data_dir=data_dir))


def _projected_years(pop_g_s: pd.DataFrame) -> list[int]:
    """The ranking temporal domain (codex r8-F3): PROJECTED years only (`Statut = proj` — the
    estimation years are history, not scenario), the full CONTIGUOUS annual lattice through the
    last projected year, both endpoints included.

    `status` holds plain strings (`r` / `p` / `proj`), so the str-Enum repr trap that makes an
    `.astype(str)` filter on the geography and scenario columns silently select an empty frame
    does not reach here. Contiguity is ASSERTED rather than assumed: the domain is load-bearing
    (an all-years average can REVERSE a pair's order), and a gap would quietly re-weight the
    mean rather than raise.
    """
    proj = sorted(int(y) for y in pop_g_s[pop_g_s["status"] == "proj"]["year"].unique())
    if not proj:
        raise LoaderError("no projected (Statut=proj) years in the population slice — the "
                          "ranking domain is projected years only and cannot be empty")
    if proj != list(range(proj[0], proj[-1] + 1)):
        raise LoaderError(f"projected year lattice is not contiguous: {proj} — spec §7b averages "
                          "the FULL contiguous annual lattice, so a gap silently re-weights it")
    return proj


def _pop_by_age(pop_g_s: pd.DataFrame, year: int, ctx: str) -> dict[int, float]:
    """{single year of age: persons} for one (geography, scenario, year).

    TWO SILENT DOORS CLOSED HERE, and both produced plausible floats in the plan body:

      * A YEAR THE FRAME DOES NOT CARRY summed to 0.0 and fell through `_scale`'s
        `p_isq > 0 else 1.0` branch — a silent scale of ONE where a refusal belongs (carry B9).
      * A HOLED AGE LATTICE reached `native_formation`, whose loop simply finds nothing to add,
        so an empty or partial `resident_pop_t` yields D_native = 0.0 with no trace. A missing
        population is not zero demand. `native_formation` refuses an absent RATE and an absent
        PRIOR COHORT; the frame's own completeness is this function's to refuse.
    """
    rows = pop_g_s[pop_g_s["year"] == year]
    if rows.empty:
        raise LoaderError(
            f"{ctx}: the population frame carries no rows for year {year} — an absent year is "
            "not an empty population; scaling it to 1.0 (or summing it to 0.0) publishes a "
            "number for a year nobody projected")
    by_age = {int(a): float(v) for a, v in rows.groupby("age")["population"].sum().items()}
    missing = [a for a in POP_AGES if a not in by_age]
    if missing:
        raise LoaderError(
            f"{ctx}: year {year} is missing {len(missing)} of {len(POP_AGES)} single-year age "
            f"cells (first absent: {missing[:5]}) — a holed age lattice DEFLATES native "
            "formation silently, because the formation sum finds nothing to add at the ages "
            "it cannot see")
    return by_age


def _arrival_year(stock_year: int) -> int:
    """The compo row that lands IN `stock_year`.

    `compo.YEAR_SEMANTICS`: the row labeled t covers 1 July t -> 1 July t+1 and lands in
    Population(t+1), NOT Population(t) — "a §6 consumer that subtracts arrivals(year=t) from
    P_ISQ(t) mis-times every arrival cohort by one year". The plan body did exactly that on
    BOTH legs (the surviving-cohort subtraction and the arrival credit).

    THIS IS THE DEMAND HALF OF A PAIR, and it was the only half for fifteen rounds:
    `_exit_landing_year` below does the same job for the SUPPLY legs (spec amendment #27). Read
    the two together — a labelling translation that exists at one seam of a subtraction and not
    the other is the defect that amendment fixed.
    """
    return stock_year - 1


def _arrival_flow(compo_g_s: pd.DataFrame, flow_year: int, ctx: str) -> float:
    rows = compo_g_s[compo_g_s["year"] == flow_year]
    if rows.empty:
        raise LoaderError(
            f"{ctx}: no immigrant-flow row for interval year {flow_year} (published span "
            f"{FLOW_SPAN}) — an unpublished flow is not a zero flow, and summing an empty "
            "slice to 0.0 deletes a whole arrival cohort from demand with every downstream "
            "number still plausible")
    return float(rows["immigrants_permanents"].sum())


def _surviving_arrivals(compo_g_s: pd.DataFrame, stock_year: int, ctx: str) -> list[float]:
    """§6's Σ_c SurvivingArrivalCohort_c(t) — every cohort that has LANDED by `stock_year`.

    Coarse by design (Tranche 1): arrival cohorts carry no mortality of their own, so a cohort
    that landed contributes its full flow in every later year. The base is the flow series'
    first published interval, not the population frame's first year: no arrival cohort exists
    before the flows begin, and ranging over years the flow frame does not publish would sum
    absent rows to zero — the door `_arrival_flow` closes.
    """
    first_flow = FLOW_SPAN[0]
    return [_arrival_flow(compo_g_s, y, ctx)
            for y in range(first_flow, _arrival_year(stock_year) + 1)]


def _exit_landing_year(roll_start_year: int) -> int:
    """The END LABEL of the exit flow the roll-forward measures over `[roll_start_year,
    roll_start_year + 1)` — spec amendment #27's translation, and the SUPPLY-side sibling of
    `_arrival_year` above.

    `roll_one_year(stock, year=y)` transitions the stock from y to y+1, so every exit it emits
    is a flow over the interval `[y, y+1)` and belongs to the year the interval CLOSES. Both
    demand legs are already END-labeled — `native_formation` differences the t-1 frame against
    the t frame, and `_arrival_year(t) = t - 1` end-labels a start-labeled published flow — so
    subtracting an exit keyed at its interval's START subtracts a `[t, t+1)` supply flow from a
    `(t-1, t]` demand flow. Adjacent, disjoint, twelve-month windows: each pair internally
    coherent, the two pairs offset by exactly one year.

    THE DIRECTION IS FORCED BY THE COMMITTED BYTES, not chosen (spec amendment #27). Crediting
    arrivals(t) at t RAISES at the final domain year (`_arrival_flow` refuses an unpublished
    interval, and the flow span closes at 2050 against a 2051 domain end), and a start-labeled
    native leg would need the population frame one year PAST the last one that exists. End
    labeling is therefore the only self-consistent convention computable here, so it is the
    SUPPLY legs that move onto the demand convention.

    A FUNCTION AND NOT A `+ 1` AT THE CALL SITE, for `_arrival_year`'s own reason: the offset is
    a claim about a published interval's semantics, so it gets a name, a docstring and a test
    that pins the claim rather than the arithmetic. It is applied at the ONE place the exits are
    keyed — `_ed_series`'s roll loop — because a translation sprinkled at read sites leaves the
    dict's keys meaning one thing while a consumer reads them as another, which is the shape
    this amendment exists to close.
    """
    return roll_start_year + 1


# ===========================================================================================
# THE 75+ COHORT
# ===========================================================================================

# `roll_one_year` emits exits keyed by ITS vocabulary; `market_listings` takes a DIFFERENT one.
# Stated as an explicit total map rather than handed over positionally: `market_listings`
# takes (voluntary, estate) in that order and both are `dict[int, float]`, so a transposition
# runs clean and puts the estate flow through the voluntary fraction with no lag — every
# number still plausible, the whole supply term wrong. `_split_exits` below is where the
# vocabulary is REFUSED, in both directions, and since `listings.phi_market` was deleted
# (round-3 elegance audit, 2026-08-22) it is the only place that can be.
EXIT_CAUSE_TO_LISTING_CAUSE = {"estate": "estate", "living": "voluntary"}


def _split_exits(exits: dict, ctx: str) -> dict[str, float]:
    """{listing cause: households} — refusing an exit vocabulary this map does not cover."""
    unmapped = sorted(set(exits) - set(EXIT_CAUSE_TO_LISTING_CAUSE))
    absent = sorted(set(EXIT_CAUSE_TO_LISTING_CAUSE) - set(exits))
    if unmapped or absent:
        raise CalibrationError(
            f"{ctx}: roll-forward exit cause(s) {unmapped} have no listing cause and "
            f"{absent} are absent — the map is TOTAL in both directions "
            f"({EXIT_CAUSE_TO_LISTING_CAUSE}); an unmapped cause would silently drop out of "
            "the supply term")
    return {EXIT_CAUSE_TO_LISTING_CAUSE[cause]: float(value) for cause, value in exits.items()}


def _household_stock(rows: pd.DataFrame, geo: Geography, age: int, la: dict,
                     ownership: float, *, collective_share: float,
                     direction_ctx: str | None = None) -> Stock:
    """Owner-unit Stock from a population slice, through spec §5's INITIALIZATION EQUATIONS.

    `Other` (persons living with others) is excluded from the owner stock as presumptive
    non-maintainers — `HouseholdInit` carries no `owner_other` for exactly that reason.

    THE OWNERSHIP RATE ARRIVES FROM THE CALLER AND IS REQUIRED (operator ruling X1,
    2026-08-21). The two callers value DIFFERENT populations: `_band_entry_stock` hands a single
    age-75 cohort and reads the rate at that age, while `_standing_stock` hands the whole
    age>=75 slice and must hand the slice's own POPULATION-WEIGHTED rate — no age inside a
    lumped slice returns the aggregate the slice needs. There is deliberately no default and no
    `read_ownership` here: a function that could resolve its own rate from `age` would silently
    give the lumped caller the wrong one, which is exactly the defect ruling X1 corrects.

    THE COLLECTIVE SHARE ARRIVES FROM THE CALLER TOO, AND IS REQUIRED (spec amendment #20(D),
    2026-08-22). It used to be read here as `CONSTANTS["collective_share_75plus"].value` — a
    LIVE headline input, in its own declared band, that no sweep leg could reach through this
    signature. That is the run-32 CRITICAL's shape exactly: `phi_voluntary` was a declared axis
    the whole time and went unswept because `market_listings` read a module constant instead of
    its argument. There is no default, deliberately: a default here is a second place the run's
    selection could come from, and an axis whose endpoint cannot reach the arithmetic is an axis
    `rank_stable` claims to have varied and did not.

    `age` still governs the LIVING-ARRANGEMENT reads. That lumping is pre-existing and separately
    documented (`loaders/living_arrangement.py` publishes 75-84/85+ and this reads one point in
    the block); ruling X1 is scoped to the ownership weighting and does not touch it.

    `direction_ctx` WIRES SPEC §5's THIRD HARD GATE, and it is a keyword rather than an
    unconditional call because the gate is AGGREGATE-SCOPED (round-3 audit finding, 2026-08-22).
    `cohort/init.assert_aggregate_coupled_direction` had ZERO production callers — its only
    callers were in `tests/test_init.py` — while `cohort/init.py` still carried "it does not
    exist as code yet" and `loaders/living_arrangement.py` named it among the gates that fire on
    MODELLED counts. Task 29 HAD landed: `_standing_stock` is the caller the carry described,
    `HouseholdInit` returns exactly `coupled_m`/`coupled_f`, and this function discarded both.
    Only `_standing_stock` passes a context, because §5 states the claim at the 75+ AGGREGATE and
    `_band_entry_stock` hands a SINGLE age-75 cohort — a direction gate applied per band is the
    overreach steering ruling A retired the per-band magnitude gate for, and the gate's own
    docstring says "call this on 75+ aggregate counts, not per band".

    WIRING COST IS ZERO, MEASURED: all eight geographies run M > F, worst signed (F-M)/max
    -0.1155 (MTL_ISLAND_RA06) against the 0.25 bound, so it passes on every row today. What
    shipped silently without it, CONFIRMED by injection: transposing the M/F living-arrangement
    reads below computes the FULL ED grid with NO refusal anywhere — LAVAL_RA13 flips SIGN, the
    negative-ED count drops 3 -> 2 (destroying the published three-negative-signs reading) and
    MTL_RMR moves ~40x the tightest rank-deciding gap. The gate raises at all eight rows.

    WHAT WIRING IT DOES NOT CLOSE, stated because the gate is ONE-DIRECTIONAL (`coupled_f <=
    coupled_m` returns early): an ISQ *sex-column* transposition also moves the negative count
    3 -> 2 and leaves M > F, so it passes this gate untouched. This closes the
    living-arrangement / rate-junction class, not the ISQ-column class.
    """
    pop_by_sex = {s: float(rows[rows["sex"] == s]["population"].sum()) for s in ("M", "F")}
    h = initialize_households(
        pop_by_sex,
        living_alone_rate_by_sex={s: living_alone_rate(la, geo, age, s) for s in ("M", "F")},
        couple_share_by_sex={s: couple_share(la, geo, age, s) for s in ("M", "F")},
        collective_share=collective_share,
        ownership_rate=ownership,
    )
    if direction_ctx is not None:
        assert_aggregate_coupled_direction(h.coupled_m, h.coupled_f, ctx=direction_ctx)
    return Stock(couple=h.owner_couple, solo_m=h.owner_solo_m, solo_f=h.owner_solo_f)


def _population_weighted_ownership(rows: pd.DataFrame, geo: Geography, read_ownership,
                                   ctx: str) -> float:
    """The population-weighted mean of the per-age ownership rates over the ages in `rows`.

    sum_a pop(a) x rate(geo, a) / sum_a pop(a), both sexes pooled per age — the aggregate rate a
    LUMPED bucket has to be valued at, formed from the age-resolved rates the lattice publishes.
    A zero-population slice REFUSES: 0/0 has no rate, and a `rows` frame that summed to zero
    would otherwise produce one by division.

    EVERY POPULATION CELL IS ASSERTED NONNEG-FINITE ON THE RAW ROWS, BEFORE THE GROUPBY, and the
    guard is `owner_stock`'s, mirrored rather than invented (round-3 audit finding, 2026-08-22).
    THE POSITION IS THE WHOLE FIX and a check on the grouped sums would not be one: that sum is
    where the NaN DISAPPEARS. This
    function advertised a degenerate-slice refusal it DID NOT HAVE, and the audit measured all
    three holes: `[(80, NaN), (90, 100.0)]` returned age 90's rate ALONE, because
    `groupby("age")["population"].sum()` is skipna=True — the NaN cell became 0.0, that age fell
    out of the weighting and `persons <= 0.0` never saw it; `[(80, +inf), (90, 100.0)]` returned
    nan with no refusal and died later inside `match_couples`, on a message naming `coupled_m`
    rather than the population that was malformed; and a negative-then-positive slice could
    return a rate OUTSIDE [0,1] (constructed: 1.404). NONE of the three is reachable through the
    live door — `loaders/isq.py` refuses non-finite AND negative populations on every kept row —
    so this was a misadvertised guard and a misattributed failure, never a wrong number. Both
    halves are worth closing at the same cost: a guard the docstring claims must exist, and a
    refusal must name the operand it is about.

    THE RETURN IS ASSERTED A FRACTION for the second half of that: with nonneg cells and rates
    already in [0,1] the mean is in [0,1] by arithmetic, so this assert cannot fire on live
    input — it is the positional check `owner_stock` makes for the same reason, closing the one
    direction where a future caller supplying its own `read_ownership` could hand back a rate
    the weighting would silently pass on to `initialize_households`.
    """
    for age, people in zip(rows["age"], rows["population"]):
        assert_nonneg_finite(f"{ctx}: population[age={age}]", people)
    # Nonneg-finite per cell => nonneg-finite per grouped sum, by arithmetic. `skipna=True` can
    # no longer erase anything, because nothing skippable survived the loop above.
    per_age = rows.groupby("age")["population"].sum()
    weighted = persons = 0.0
    for age, people in per_age.items():
        weighted += float(people) * read_ownership(geo, int(age))
        persons += float(people)
    if persons <= 0.0:
        raise CalibrationError(
            f"{ctx}: the age slice carries {persons} persons — a population-weighted ownership "
            "rate over an empty slice is 0/0, and a default would value the whole bucket at a "
            "rate no age in it published")
    return assert_fraction(f"{ctx}: population-weighted ownership rate", weighted / persons)


def _standing_stock(pop_g_s: pd.DataFrame, year: int, geo: Geography, la: dict,
                    read_ownership, *, collective_share: float) -> Stock:
    """The 75+ owner stock standing at `year` — the roll-forward's initial condition.

    ONE RATE MULTIPLIES THE WHOLE BUCKET, AND IT IS THE BUCKET'S OWN (operator ruling X1,
    2026-08-21). The slice below is every age >= 75 and the rate applied to it is the
    POPULATION-WEIGHTED mean of the per-age rates over exactly those ages — the aggregate a
    lumped bucket has to be valued at, built from the rates the seven-band lattice publishes.

    WHAT THIS REPLACED. The rate used to be read at `ROLL_AGE` (80), which resolved to the flat
    `75+` band while that band existed — the household-weighted union over this same population,
    so the point read WAS that union and the coarseness cost nothing. Operator ruling W
    (2026-08-20) split that band, and 80 then resolved to `75-84` ALONE: the bucket was valued
    at the upper half of the very gradient the refinement exposed. Measured against each
    geography's OWN served 75+ household union — the baseline has to be NAMED, because a figure
    against the census-net residual differs and an unnamed one drifted here once: +1.073 pp at
    MTL_RMR (0.5722653000099837 against 0.5615325746167329), +2.593 pp at QC_RMR
    (0.5597833634217469 against 0.5338550157591566) and +1.670 pp at HORS_RMR on the OPERAND-
    ALIGNED curve it actually reads (0.6693599636858829 against 0.6526588753507868), with 85+
    households 21.7-25.8% of the block and owning at a materially lower rate.

    IT IS A SMALL, DECLARED, MEASURED MODEL CHANGE ON S — NOT A RESTORATION (operator ruling X3,
    2026-08-21, correcting this docstring's own earlier "restores the aggregate"). The retired
    flat band supplied the HOUSEHOLD-weighted union; this POPULATION-weighted mean sits BELOW it
    AT THE THREE GEOGRAPHIES THAT READ THEIR OWN TERRITORY — -0.162 pp at MTL_RMR
    (0.5599109544965435 against 0.5615325746167329), -0.636 pp at QC_RMR (0.5274919385882947
    against 0.5338550157591566), -0.361 pp at HORS_RMR (0.6490440998641852 against
    0.6526588753507868) — which at QC_RMR is a QUARTER of the 2.593 pp defect being repaired.

    IT IS NOT BELOW EVERYWHERE, and the phrase "systematically BELOW" stood here saying it was
    until 2026-08-21. The FIVE geographies that BORROW MTL_RMR's curve STRADDLE the single union
    that curve supplied all six of its rows: two sit below it (MTL_ISLAND_RA06 -0.321 pp,
    LAVAL_RA13 -0.228 pp) and THREE sit ABOVE — LANAUDIERE_RA14_PROXY +0.035 pp,
    LAURENTIDES_RA15_PROXY +0.104 pp, MONTEREGIE_RA16_PROXY +0.014 pp. Reason (iii) below
    already ENTAILED that and the sentence contradicted it four lines later: the new spread
    0.5583240006063737-0.5625735734929677 straddles 0.5615325746167329, so some row is above it
    by arithmetic. The old gate could not see it because it iterated the three geographies with
    their own territory ALONE; it now iterates all eight and asserts the direction PER CLASS.

    THE SIGN OF THE ED MOVE IS THE OPPOSITE OF THE SIGN OF THE RATE MOVE, at every one of the
    eight rows — a lower ownership rate is a smaller S, hence a larger D-S. So the five rows
    whose rate FELL had their mean reference ED RAISED, and the three whose rate ROSE had it
    LOWERED; one of those three is the RANK-1 HEADLINE ROW. At LANAUDIERE_RA14_PROXY this repair
    RAISED S's ownership rate and LOWERED mean reference ED (by -1.197e-06). So the unqualified
    adjective taught the wrong SIGN at the very row the ranking is read off, which is why it was
    worth a ruling rather than a copy-edit. Population weighting STAYS, ruled, for four
    reasons worth recording rather than for exactness:
      (i)   VINTAGE CONSISTENCY — the weights come from the same ISQ base-year population frame
            that supplies the very stock being valued, whereas census-2021 household counts are
            a different quantity from a different vintage;
      (ii)  it uses the model's OWN data instead of importing an external weighting;
      (iii) it DIFFERENTIATES the geographies that borrow MTL_RMR's curve through their own 75+
            age composition, breaking a lockstep artifact: all SIX rows that read that curve
            (MTL_RMR owns it; FIVE borrow it) were pinned identical at 0.5722653000099837 under
            the point read and now spread 0.5583240006063737-0.5625735734929677 — the age
            composition is the one thing a borrowed rate row does not flatten;
      (iv)  decisively, EXACTNESS IS UNAVAILABLE IN PRINCIPLE, so "restores" is the wrong word
            for ANY choice here: under aggregate matching the COUPLE bucket has no per-age
            decomposition at all (`match_couples` pairs the summed pools), so there is no weight
            that aggregates it exactly.

    WHAT IT IS NOT: PER-AGE SUMMATION OF `_household_stock`, which is the obvious candidate and
    is WRONG here — measured. Splitting the slice per age changes COUPLE MATCHING and the
    LIVING-ARRANGEMENT read as well: `match_couples` is a min-pairing and
    sum_a min(m_a, f_a) <= min(sum m, sum f) — a theorem, tight only where one sex binds at every
    age — so per-age initialization forces spouses to be the SAME AGE and dumps every
    age-discordant couple into the EXCLUDED `Other` bucket, while the per-age split ALSO forces
    the living-arrangement band to be re-read (85+ female `couple_share` 0.401 against 75-84's
    0.730 at MTL_RMR).

    THE ATTRIBUTION OF THAT GAP WAS MISLABELLED HERE, AND BOTH DENOMINATORS ARE NOW NAMED
    (operator ruling X4, 2026-08-21). This docstring said a decomposition "attributed 0.90-1.03
    of the whole per-age-vs-lumped gap to matching alone"; that ratio is real but its denominator
    is the LA-LUMPED FAMILY — arms with the living arrangement held at `ROLL_AGE` in BOTH legs,
    where matching is nearly the only channel left open and re-measures at 0.88-0.98 of that
    family's gap. Against the FULL per-age split, which re-reads the living-arrangement band,
    min-pairing is only 1.3-8.9% of the gap and the LA re-read is 73.9-100.3% of it: at MTL_RMR
    the couple stock moves -18.72% from the LA re-read and a further -0.149% from per-age
    matching. The min-pairing loss is small there because the FEMALE coupled count binds at
    every age from 75 into the mid-90s once the LA band is read per age — the earliest crossover
    across the eight geographies is age 95, and at MTL_RMR it is 98.

    ARM D IS STILL REJECTED, and MORE firmly than the wrong label argued: the per-age arm moves
    MTL_RMR's mean reference ED by +6.32e-05 against this repair's own +4.28e-05, i.e. 1.5x the
    fix, so it is not a refinement of the fix but a larger, separate model change. THOSE TWO
    FIGURES ARE PRE-#27 MEASUREMENTS AND ARE NOT RE-MEASURED HERE (noted 2026-08-23, at their own
    line rather than in an amendment): both were taken against the `ROLL_AGE` POINT read on the
    START-labeled ED series, and spec amendment #27 re-based every ED level. What is GATED is
    their RATIO and the rejection it carries, which is a claim about two arms of the SAME series
    and survives a common re-basing; the digits are a dated reading of a retired series. The
    rank-1 figure above IS re-measured on every run — `tests/test_pipeline.py` computes it — and
    the perturbation that produced arm D's number is not recorded anywhere, which is exactly why
    it is labelled rather than re-digited from a reconstruction. Real 75+
    couples are age-discordant, so aggregate matching is the better model at this grain; the
    weighted rate repairs the ownership weighting and touches nothing else. Tranche 2's
    age-indexed 75+ lattice is what removes the single-bucket coarseness, and it has to move the
    living-arrangement and hazard reads WITH the ownership read rather than one of the three.

    THE LIVING-ARRANGEMENT READS STAY AT `ROLL_AGE`, deliberately: that lumping is pre-existing
    and separately documented, and it is not in ruling W's scope. `ROLL_AGE` also still carries
    the HAZARD — it is the age the bucket is decremented at, which is what makes it a MODEL
    choice (`MODEL_CHOICE_PROVENANCE["roll_age"]`). What it no longer does is select an
    ownership band.

    `_band_entry_stock` below is unaffected: it reads at BAND_ENTRY_AGE 75 on a single age-75
    cohort, where the point read IS the right one.

    THIS IS ALSO SPEC §5's THIRD HARD GATE'S CALL SITE (round-3 audit, 2026-08-22): the slice
    below IS the 75+ aggregate the gate is scoped to, so it is the only caller that passes
    `_household_stock` a `direction_ctx`. `cohort/init.py`'s carry named this function (under
    its former name `_init_stock`) as the caller that "does not exist as code yet"; it did, and
    the call did not. That docstring and the argument for keeping `_band_entry_stock` out of it
    live at `_household_stock`.
    """
    rows = pop_g_s[(pop_g_s["year"] == year) & (pop_g_s["age"] >= BAND_ENTRY_AGE)]
    if rows.empty:
        raise LoaderError(f"{geo.value}: no 75+ population at {year} — the roll-forward has no "
                          "initial condition and an empty one is not a zero one")
    return _household_stock(rows, geo, ROLL_AGE, la, _population_weighted_ownership(
        rows, geo, read_ownership, ctx=f"{geo.value}/{year} standing 75+ stock"),
        collective_share=collective_share,
        direction_ctx=f"{geo.value} 75+ ({year})")


def _band_entry_stock(pop_g_s: pd.DataFrame, year: int, geo: Geography, la: dict,
                      read_ownership, *, collective_share: float) -> Stock:
    """The cohort ENTERING the modeled band at `year` — spec §5's band-entry entrants.

    THIS REPLACES THE PLAN'S UNCITED 0.1, and the divergence is the SPEC's, not a preference.
    The plan body wrote:

        entrants = _init_stock(pop_g_s, min(year + 1, max_year), ...)
        inflow = max(entrants.owner_units - stock.owner_units, 0.0) * 0.1
        stock = Stock(nxt.couple + inflow, nxt.solo_m, nxt.solo_f)

    Three things are wrong with it and only one is the magic number. (1) The 0.1 has no
    derivation in the spec, the plan or the constants surface, where every other model constant
    carries an anchor. (2) It measures the rolled stock against the ISQ 75+ stock and books a
    tenth of the gap, which is a PARTIAL RE-ANCHORING TO ISQ — `rollforward.py`'s own first line
    says "band-entry-only entrants; NEVER re-anchored to ISQ 75+ stocks", and I1 is the
    invariant that forbids it. (3) It books the whole inflow as COUPLES, so the entrant mix is a
    fourth unstated assumption.

    Spec §5 states the rule instead of a parameter: band-entry composition comes from the
    INITIALIZATION EQUATIONS on that year's newly-aged-75 ISQ population, per sex and per
    household state — `rollforward.roll_cohort_multi_year` records the same sentence and names
    Task 29's pipeline as the owner of that signature. Implemented, the free parameter
    DISAPPEARS: there is nothing left to cite because there is nothing left to choose.
    """
    rows = pop_g_s[(pop_g_s["year"] == year) & (pop_g_s["age"] == BAND_ENTRY_AGE)]
    if rows.empty:
        raise LoaderError(
            f"{geo.value}: no age-{BAND_ENTRY_AGE} population at {year} — band entry is the "
            "cohort's ONLY entry point (spec §5 stock-flow discipline), so an absent entrant "
            "cohort would silently freeze the stock rather than empty it")
    return _household_stock(rows, geo, BAND_ENTRY_AGE, la,
                            read_ownership(geo, BAND_ENTRY_AGE),
                            collective_share=collective_share)


def _add(a: Stock, b: Stock) -> Stock:
    return Stock(a.couple + b.couple, a.solo_m + b.solo_m, a.solo_f + b.solo_f)


def _listings_at(listings: dict[int, float], year: int, ctx: str) -> float:
    """The supply term S at `year` — REFUSING a year the roll-forward never keyed.

    `listings.get(year, 0.0)` stood here, in a module whose own docstring says "every silent-zero
    door on the model path refuses instead". It is UNREACHABLE as written and the door is closed
    anyway, because unreachability here is a property of two loops staying in step rather than of
    anything structural: the supply loop keys `voluntary` at `_exit_landing_year` of every roll
    year from the population frame's first through `years[-1]`, i.e. at
    `base_year + 1 .. years[-1] + 1`, which covers the whole ranking domain because the first
    projected year is five years past the frame's first; and nothing binds those two ranges
    together except that one line writes them and another reads them.

    THE KEY THIS READS IS AN END LABEL (spec amendment #27) and no translation happens here.
    `_ed_series` end-labels the exits at the ONE place they are keyed, so `year` means the same
    window on both sides of the subtraction — `(year-1, year]`. A `+ 1` added here as well would
    double-count the offset, and it is the shape the amendment closed: the exits used to be
    keyed at their window's START and read at `t`, subtracting a `[t, t+1)` supply flow from a
    `(t-1, t]` demand flow.

    THE DEFAULT IS THE DEFLATING ONE, which is why this is the door and not merely a lookup. ED
    is demand MINUS supply over stock: a missing listing year books supply as ZERO, which pushes
    excess demand UP and a geography's rank TOWARD the top. The failure surfaces as a better
    ranking, not as a hole — the shape spec §7b's domain gate and `_pop_by_age`'s holed-lattice
    gate both exist to refuse one level down.
    """
    if year not in listings:
        raise CalibrationError(
            f"{ctx}: no market-listing entry for {year} — the supply term would default to 0.0, "
            f"which INFLATES excess demand and moves the geography UP the ranking rather than "
            f"showing a hole (keyed years {min(listings, default=None)}-"
            f"{max(listings, default=None)})")
    return listings[year]


# ===========================================================================================
# RULING O — the reconciliation gate, CENTRAL RUN ONLY
# ===========================================================================================

# spec §5's pinned reconciliation cohort: "the cohort's household-state and sex composition is
# the one the INITIALIZATION EQUATIONS produce on the committed data vintage for MTL_RMR".
# START YEAR and SCENARIO are the two coordinates the spec sentence does not fix; both are
# carried from `tests/test_rollforward.py`, which measured every start year 2021-2041 in band
# (0.3505-0.3593) so the pin selects a number and not a verdict, and which records that Task
# 29's pipeline is where its private cohort builder folds.
RECONCILIATION_COHORT = (Geography.MTL_RMR, Scenario.REFERENCE, 2035, BAND_ENTRY_AGE)


def _reconciliation_retention(frames: Frames, read_ownership, q_live: float,
                              collective_share: float) -> float:
    """RULING O's gate input, on the CENTRAL assumptions and only them — which is why both
    swept quantities it reads are handed in by the caller rather than defaulted here."""
    geo, scen, start_year, age = RECONCILIATION_COHORT
    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    return roll_cohort_decade(
        start_age=age, start_year=start_year, q_live=q_live, qx=q_at,
        initial=_band_entry_stock(pop_g_s, start_year, geo, frames.la, read_ownership,
                                  collective_share=collective_share))


# ===========================================================================================
# THE ROBUSTNESS SWEEP'S ASSUMPTION LEG (spec §7b run contract; run-32 quant F1 / stress F1)
# ===========================================================================================
#
# `rank_stable: true` SHIPPED ON ALL EIGHT ROWS AS A VERDICT OVER ONE OF THE DECLARED AXES
# (there were five when the narrowing was found; `headship_shape` joined at ruling V and
# `collective_share_75plus` at spec amendment #20(D), so there are SEVEN now).
# `_rank_stability` iterated `SWEEP_GRID["q_live_per_year"]`; the grid declared FOUR, and
# `constants.py` stated a FIFTH as an existing fact of THIS module — "Task 29 perturbs the join
# table with a uniform override spanning CONSTANTS['immigrant_ownership_ratio_sweep_span']" —
# for which no code existed anywhere in the tree. Two committed contracts in direct
# contradiction, green because no test crossed them. And the omission was not benign: ON THE BAND
# CURVE the four grid axes left the published order INTACT at both endpoints, while the ratio axis
# reordered EVERY row at 0.155 (rank 1 changes hands). The one axis that was swept was the one
# that could not have failed.
#
# THE PER-LEG COUNTS ARE NO LONGER PROSE ANYWHERE — they are the EMITTED `rows_moved` map (spec
# amendment #20(C)(2)), re-derived on every run. They lived in three unpinned copies (here,
# `_rank_stability`'s docstring, and `artifacts/README.md`'s table), the README declared them "a
# dated reading" against itself, and they HAD gone stale: measured 2026-08-22 on these bytes,
# EIGHT of the twelve cells that survived from the run-35 reading were wrong, including which
# ENDPOINT of `q_live_per_year` and of `phi_voluntary` reorders (the LOW one, not the high) and
# whether `estate_eventual_fraction` reorders at all (it does, 2 rows at 0.6). Re-measuring them
# into prose would only re-start the clock; emitting them ends it. What stays here is the part
# that is stable across every re-measurement this arc has done and is separately PINNED by
# `tests/test_pipeline.py`: the ratio axis is the one whose two endpoints TOGETHER move every
# ranked row, which is what carries the union verdict to all eight, and 0.155 alone moves seven of
# eight (LAVAL_RA13 holds rank 3 since ruling W). THE PER-ENDPOINT COUNT IS DELIBERATELY NOT
# RESTATED HERE any more: it was "1.033 moves the four that include it" and spec amendment #24(A)
# made it FIVE (LAVAL_RA13 now takes rank 1 there), which is this comment's own argument turned on
# itself — an unbound per-leg count goes stale at the next model change. The count is emitted in
# `rows_moved` and bound to the consumer page from both sides; the union claim is the part that has
# survived every re-measurement this arc has done.
#
# WHY A LEG OBJECT AND NOT FOUR MORE PARAMETERS. `_ed_series` is called once per (geography,
# scenario) per leg, and a positional list of five band values threaded through three call
# layers is the shape where an endpoint silently lands on the wrong axis — the same
# operand-mix-up class this module's header already names twice. One frozen record, and each leg
# is CONSTRUCTED as the central leg with exactly one field replaced, so "a leg perturbs one axis"
# is a property of how the legs are built rather than a rule someone has to follow
# (`tests/test_pipeline.py` pins it against the central leg, field by field).
#
# THE RATIO AXIS IS DELIBERATELY NOT A `SWEEP_GRID` MEMBER. That dict's keyset is held EQUAL to
# `CENTRAL_ASSUMPTIONS`' by test, on the stated ground that an unswept central assumption
# silently claims `rank_stable` it never tested — the membership rule is stated ONCE, at
# `loaders/constants.py`'s MODEL_CHOICES header, and since ruling V it is "is there something to
# sweep", never "is it a float" (`headship_shape` is central, categorical and swept).
# Rulings S/T measure the ratio PER GEOGRAPHY, so Task 25b deleted the central scalar and there
# is no central value for a grid entry to pair with. The override's central setting is therefore
# `None` — meaning "read the ruled join-table row" — and the span lives where P4 put it, in
# `CONSTANTS`. A scalar here would silently replace five ruled measurements with one number.
#
# THE RESIDUAL THAT STOOD HERE IS CLOSED (round-3 audit, 2026-08-22), and it is recorded rather
# than deleted because the closing move is the one this note prescribed. `SWEEP_GRID` rode
# `assumptions_hash` and `CONSTANTS` did not, while the ratio span feeds an EMITTED field — so
# narrowing that span (the one edit that would legitimately flip a `rank_stable` back to `true`)
# moved the artifact under a byte-identical `assumptions_hash`, and `artifacts/README.md`'s
# reading table routed the reader to its "the code moved" bucket — a mis-attribution of the same
# class run 33 closed for the mortality basis and the ruled join table. The fix WAS one payload
# key in `constants.assumptions_hash` and it is now taken, registry-wide: `resolved_constants()`
# is the fourth payload member, so this span and every other anchor re-mint the identity token
# when they move. The audit's LIVE finding was a different member of the same registry —
# `collective_share_75plus`, a headline input to `initialize_households` whose in-band move to
# 0.08 reordered the published ranking under a byte-identical envelope.
# `RATIO_SWEEP_AXIS` / `RATIO_SWEEP_SPAN_ANCHOR` / `declared_sweep_grid` are IMPORTED from
# `loaders/constants.py` (above), not declared here. They moved there when the rankings artifact
# began publishing a per-leg `rows_moved` map (spec amendment #20(C)(2)): `output/artifacts.py`
# binds that map's keys to the declared legs and cannot import this module, so the declared grid
# and the leg-label spelling have to live in the leaf both sides already read.


@dataclass(frozen=True)
class Assumptions:
    """Every SWEPT assumption the ED grid reads, at ONE setting — the headline's or a leg's;
    banded and categorical alike since ruling V added `headship_shape` (the membership rule is
    `loaders/constants.py`'s MODEL_CHOICES header, and the body below marks the categorical one).

    The six named fields are `CENTRAL_ASSUMPTIONS`' own keys, so `Assumptions(**CENTRAL_
    ASSUMPTIONS)` is the central leg and a key added there without a field here raises AT
    IMPORT rather than being dropped from the sweep. `immigrant_ownership_ratio` is the seventh
    axis and has no central value by construction (see the section note): `None` means every
    geography reads its RULED join-table ratio, and a float is the uniform override the sweep
    applies across all geographies at once.
    """

    q_live_per_year: float
    phi_voluntary: float
    estate_eventual_fraction: float
    estate_lag_years: int
    # The one CATEGORICAL axis (ruling V). It carries no default, deliberately: a default here
    # would be a second declaration of the central value, and the central value lives in
    # `CENTRAL_ASSUMPTIONS` alone.
    headship_shape: str
    # Spec amendment #20(D), 2026-08-22 — the anchor that was a live headline input with no leg.
    # No default, for the reason above: `CENTRAL_ASSUMPTIONS` reads it through from
    # `CONSTANTS["collective_share_75plus"]`, and that chain has exactly one value in it.
    collective_share_75plus: float
    immigrant_ownership_ratio: float | None = None


SWEEP_LEG_FIELDS = tuple(f.name for f in fields(Assumptions))
CENTRAL_LEG = Assumptions(**CENTRAL_ASSUMPTIONS)


def _sweep_legs(axes: tuple[str, ...] | None = None) -> list[tuple[str, Assumptions]]:
    """The sweep's product: every declared axis at BOTH declared endpoints, ONE axis off-central
    per leg. Spec §7b asks "does the ordering change ANYWHERE IN THE SWEEP GRID?", so the legs
    are a UNION over axes and never a joint perturbation — a leg that moved two axes could not
    attribute a reorder to either, and the verdict would then cover a combination the spec never
    declared.

    A DECLARED AXIS WITH NO LEG FIELD REFUSES THE RUN, and that is exactly HALF of the forward
    guard the gates asked for by name ("a future axis added to the constant cannot go unswept").
    It closes DECLARED -> FIELD: an axis present in `SWEEP_GRID` and absent from the leg can no
    longer fall out SILENTLY and leave `rank_stable` a verdict over a grid it had not covered.

    IT DOES NOT CLOSE FIELD -> CONSUMED, and that is the door the failure actually walked
    through: `phi_voluntary` was a declared axis the whole time, and it went unswept because
    `market_listings` read the module constant instead of the argument — carried in name,
    inert in effect. Nothing in this function can see that. `tests/test_pipeline.py::
    test_every_declared_sweep_axis_actually_REACHES_the_ED_NUMBERS` owns the second door and
    the split is measured, not assumed — MEASURED AT the pre-PR audit-gate fold, against that round's five-axis
    ten-leg grid: with that one test removed, a mutant that ignored all four numeric
    `SWEEP_GRID` fields inside `_ed_series` left 8 of those 10 legs at max|delta ED| = 0.0 and
    passed the remaining 1139 tests — the central run is untouched so no golden byte moves, and
    the ratio axis alone keeps `rank_stable` false on every row. Ruling V's `headship_shape`
    axis widened the grid and did not weaken that split: it adds one LIVE leg
    (`expo_cum_fb`) and one inert BY CONSTRUCTION (the `expo_cum_fc` leg, which IS `CENTRAL_LEG`
    and reuses the central grid), so the same mutant would leave 9 of those 12 inert. That is
    arithmetic on the two new legs, not a re-run, and the grid has widened AGAIN since — spec
    amendment #20(D) added `collective_share_75plus`, widening the live grid past the arithmetic
    above. The mutation battery has NOT been re-measured on either widening.
    """
    declared = declared_sweep_grid()
    if axes is not None:
        unknown = sorted(set(axes) - set(declared))
        if unknown:
            raise CalibrationError(
                f"the robustness axes {unknown} are not declared (declared: "
                f"{sorted(declared)}) — a caller cannot sweep an axis the run contract does "
                f"not carry")
        declared = {axis: endpoints for axis, endpoints in declared.items() if axis in axes}

    legs: list[tuple[str, Assumptions]] = []
    for axis, endpoints in declared.items():
        if axis not in SWEEP_LEG_FIELDS:
            raise CalibrationError(
                f"the robustness axis {axis!r} is DECLARED and the ED grid has no way to vary it "
                f"(leg fields: {list(SWEEP_LEG_FIELDS)}) — a declared axis the sweep drops makes "
                f"`rank_stable` a verdict over a grid it never covered, which is the run-32 "
                f"CRITICAL this refusal exists to prevent. Add the field and thread it through "
                f"`_ed_series`, or remove the declaration")
        legs += [(axis, replace(CENTRAL_LEG, **{axis: endpoint})) for endpoint in endpoints]
    return legs


# ===========================================================================================
# EXCESS DEMAND
# ===========================================================================================

def _ed_series(geo: Geography, scen: Scenario, frames: Frames, read_ownership,
               assumptions: Assumptions) -> list[float]:
    """ED at every PROJECTED year (the ranking domain), for one (geography, scenario).

    EVERY BANDED ASSUMPTION ARRIVES IN `assumptions` AND NOTHING IS READ FROM A MODULE DEFAULT,
    which is the contract the narrow sweep broke. The headline run passes `CENTRAL_LEG`; each
    robustness leg passes one axis moved to a declared endpoint. Until run 33 only `q_live` was
    a parameter here and the other three grid axes rode `market_listings`' defaults, so a leg
    could not reach them at all — `cohort/listings.py` states the same fact at its own signature.

    THE IMMIGRANT RATIO IS THE ONE FIELD WITH A `None` CENTRAL SETTING, and the branch below is
    the whole reason: `None` reads the RULED per-geography ratio from the §6 join table (rulings
    S/T measure it per geography, so there is no central scalar), while a float is the sweep's
    UNIFORM override — spec §6 amendment #12(C)'s containment argument is stated over exactly
    that uniform construction, and it was resting on code that did not exist.
    """
    ctx = f"{geo.value}/{scen.value}"
    q_live = assumptions.q_live_per_year
    inputs = resolve_immigrant_inputs(geo)
    ratio = (inputs.ownership_ratio if assumptions.immigrant_ownership_ratio is None
             else assumptions.immigrant_ownership_ratio)
    # THE SHAPE COMES OFF THE LEG, never off the artifact's own `central_shape` (ruling V):
    # the headline passes `CENTRAL_ASSUMPTIONS["headship_shape"]` and each sweep leg passes its
    # endpoint, so the run's shape selection sits in ONE place and `assumptions_hash()` covers
    # it. A fallback to the artifact default would be a second selection site outside the
    # identity token — the defect this audit round already named for the immigrant inputs.
    curve = headship_curve(frames.headship, assumptions.headship_shape)
    headship = {a: headship_rate(curve, a) for a in range(0, 101)}
    ownership = {a: read_ownership(geo, a) for a in range(25, 101)}
    # AMENDMENT #24(A) — THE ONE PLACE THE POOLED DENOMINATOR IS CONVERTED, and the two names
    # here are not decoration. What the reader serves is `p_all`: the age-banded ownership cube
    # carries NO immigrant dimension, so its rate is owner maintainers over ALL maintainers —
    # immigrants, non-immigrants AND non-permanent residents. `inputs.ownership_ratio`'s
    # denominator is non-immigrants ALONE. Multiplying the two emitted `p_imm_true x B`, so
    # every published `mean_ed_*` was biased: at MTL_ISLAND_RA06 `mean_ed_low` was the WRONG
    # SIGN. `B` is computed from the ratio's OWN cube's counts, per geography, and is the one
    # place a scalar could have been typed and is not.
    #
    # WHAT THIS CORRECTS AND WHAT IT CANNOT — spec §6 NAMED LIMIT (C), declared because the fix
    # is partial BY CONSTRUCTION. `B` is a per-geography SCALAR, so this corrects the LEVEL and
    # cannot correct the SHAPE: no age-resolved non-immigrant curve is derivable from these
    # bytes at all. The operand below is "non-immigrant LEVEL, all-maintainer SHAPE".
    #
    # `B` DOES NOT MOVE WITH THE SWEEP's RATIO OVERRIDE, deliberately. The ratio above is an
    # ASSUMPTION axis the declared grid varies; `B` is a MEASUREMENT of the census composition
    # the propensity curve was pooled over, so a leg that overrides the ratio uniformly still
    # divides by the geography's measured bias. Moving it with the override would make the
    # sweep's endpoints mean two things at once.
    p_all = read_ownership.p_nonimm(geo)
    p_nonimm = p_all / inputs.pooled.pooled_denominator_bias

    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    compo_g_s = frames.compo[(frames.compo["geography"] == geo)
                             & (frames.compo["scenario"] == scen)]
    years = _projected_years(pop_g_s)
    base_year, last_pop_year = int(pop_g_s["year"].min()), int(pop_g_s["year"].max())

    # --- supply: roll the lumped 75+ owner bucket from the frame's first year.
    #
    # THE EXITS ARE KEYED AT THEIR WINDOW'S END LABEL (spec amendment #27), which is the ONE
    # line that carries this whole correction. `roll_one_year(year=y)` measures a flow over
    # `[y, y+1)`; both demand legs below are windows `(t-1, t]`; so keying the exits at `y`
    # subtracted two adjacent, DISJOINT twelve-month windows. `_exit_landing_year` is the
    # supply-side sibling of `_arrival_year` and states why the direction is forced. The
    # translation is applied HERE and nowhere else: `market_listings` convolves the estate lag
    # ON TOP of whatever key it is handed, and `_listings_at` reads that same key, so a second
    # translation at either of them would double-count the offset while leaving the dict's keys
    # meaning one thing and their reader meaning another.
    collective_share = assumptions.collective_share_75plus
    stock = _standing_stock(pop_g_s, base_year, geo, frames.la, read_ownership,
                            collective_share=collective_share)
    listings_in: dict[str, dict[int, float]] = {
        cause: {} for cause in EXIT_CAUSE_TO_LISTING_CAUSE.values()}
    for year in range(base_year, years[-1] + 1):
        nxt, exits = roll_one_year(stock, age=ROLL_AGE, year=year, q_live=q_live, qx=q_at)
        for cause, value in _split_exits(exits, ctx=f"{ctx}/{year}").items():
            listings_in[cause][_exit_landing_year(year)] = value
        entry_year = year + 1
        stock = (_add(nxt, _band_entry_stock(pop_g_s, entry_year, geo, frames.la, read_ownership,
                                            collective_share=collective_share))
                 if entry_year <= last_pop_year else nxt)
    listings = market_listings(voluntary_by_year=listings_in["voluntary"],
                              estate_by_year=listings_in["estate"],
                              lag=assumptions.estate_lag_years,
                              eventual_fraction=assumptions.estate_eventual_fraction,
                              phi_voluntary=assumptions.phi_voluntary)

    # --- demand + the balance, per projected year.
    def resident(year: int):
        """(P_resident by age, RAW P_ISQ by age, P_ISQ total, surviving arrivals).

        BOTH population maps are returned because the two equations take DIFFERENT operands
        and every mix-up is invisible in the numbers: native formation consumes P_resident
        (§6's operand binding) while OwnerStock consumes the RAW ISQ population, collectives
        included (`balance/owner_stock.py` states it at the use site).
        """
        by_age = _pop_by_age(pop_g_s, year, ctx=f"{ctx}/{year}")
        p_isq = sum(by_age.values())
        surviving = _surviving_arrivals(compo_g_s, year, ctx=f"{ctx}/{year}")
        p_res = assert_p_resident_nonneg(p_resident(p_isq, surviving), ctx=f"{ctx}/{year}")
        if p_isq <= 0.0:
            raise CalibrationError(f"{ctx}/{year}: ISQ population is {p_isq} — a geography with "
                                   "no people has no ED, and a scale of 1.0 would invent one")
        scale = p_res / p_isq
        return {a: p * scale for a, p in by_age.items()}, by_age, p_isq, surviving

    # ONE `resident()` EVALUATION PER YEAR, CARRIED FORWARD. Every projected year is both a `t`
    # and the next year's `t-1`, and evaluating both legs inside the iteration re-derived each
    # year TWICE — the pandas row selections in `_pop_by_age` / `_surviving_arrivals`, which the
    # profile says is where this function spends two thirds of its time. That was a private
    # inefficiency while the run evaluated three ED grids; the declared sweep evaluates one grid
    # per leg and it rode every one. `_projected_years` ASSERTS the lattice is CONTIGUOUS, and that
    # assertion is what makes the carry sound rather than merely faster: the previous iteration's
    # `t` IS this iteration's `t-1`, never a year the frame might skip. The values are unchanged
    # bit-for-bit (`resident` is a pure function of the year) — measured against the committed
    # golden, whose only moved field is `rank_stable`.
    series = []
    resident_tm1 = resident(years[0] - 1)[0]
    for t in years:
        resident_t, raw_t, p_isq_t, surviving_t = resident(t)
        assert_i2_identity(sum(resident_t.values()), p_isq_t, surviving_t)   # operand binding
        arrivals_t = _arrival_flow(compo_g_s, _arrival_year(t), ctx=f"{ctx}/{t}")
        D = total_owner_demand(
            native_formation(resident_t, resident_tm1, headship, ownership),
            immigrant_formation(arrivals_t, inputs.immigrant_headship, p_nonimm, ratio))
        # OwnerStock takes RAW ISQ population — P_ISQ, collectives included — never P_resident:
        # §6's operand binding governs the FORMATION equation alone, and netting arrivals out of
        # this denominator would scale |ED| away from zero (balance/owner_stock.py states it at
        # the use site).
        os = owner_stock(raw_t, headship, ownership)
        series.append(excess_demand(D, _listings_at(listings, t, ctx=f"{ctx}/{t}"), os))
        resident_tm1 = resident_t
    return series


def _ed_dict(geos, frames: Frames, read_ownership, assumptions: Assumptions) -> dict:
    return {g: {sc: _ed_series(g, sc, frames, read_ownership, assumptions)
                for sc in (Scenario.REFERENCE, Scenario.LOW, Scenario.HIGH)} for g in geos}


def _rank_stability(geos, frames: Frames, read_ownership, central_ed: dict,
                    sweep_axes: tuple[str, ...] | None = None
                    ) -> tuple[dict[Geography, bool], dict[str, int] | None]:
    """The RUN-CONTRACT robustness sweep (codex r8-F1): a geography's rank is STABLE iff it is
    unchanged across EVERY leg `_sweep_legs` declares — every declared axis at both of its
    endpoints — measured against the central value. Spec §7b's question is "does the ordering
    change ANYWHERE IN THE SWEEP GRID?", so the verdict is a UNION and a single reordering leg is
    enough to make a geography unstable.

    IT RETURNS TWO THINGS, and the second is EMITTED (spec amendment #20(C)(2)): the per-leg
    count of geographies whose rank moved out of the published order, keyed by
    `constants.sweep_leg_label`. That table used to live in THREE unpinned prose copies which
    `artifacts/README.md` itself declared "a dated reading, [to] re-measure rather than trust
    after any model change" — and it HAD gone stale once. A computed field replaces the prose
    instead of adding machinery beside it: the loop below already builds `legs` and `orders`.
    `None` (never an empty map) is the answer when the DECLARED grid was not evaluated — see the
    fail-safe branch — because a zero is a claim and absence is data.

    IT RETURNS `False` FOR EVERY GEOGRAPHY ON THE COMMITTED VINTAGE, and that is the measured
    answer rather than a regression. WHICH LEGS MOVE WHAT IS NO LONGER STATED HERE: it is the
    emitted `rows_moved` map, re-derived on every run, so a model change re-measures it instead
    of dating a paragraph. What survives as prose is the MECHANISM, and it is the AXIS's and not
    one leg's: the ratio axis' two endpoints TOGETHER move every ranked row, which is what
    saturates the union and holds the verdict at `false` everywhere. NO SINGLE LEG DOES — 0.155
    moves seven of eight and LAVAL_RA13 holds rank 3 there, which ruling W's lattice refinement
    falsified and `tests/test_pipeline.py` pins at the axis level for exactly that reason. The
    narrow sweep that
    shipped `true` was evaluating the one axis that could not have failed (run-32 quant F1 /
    stress F1, reached independently; `_sweep_legs` carries the contradiction the two committed
    contracts had been holding).

    THE CENTRAL LEG IS HANDED IN, NOT RECOMPUTED, and that is a contract rather than a saving.
    The run contract says the headline IS the central-value evaluation, so a sweep that
    re-derives its own central leg has two computations that must agree and nothing making them
    agree — the shape `constants.py` forbids one level down ("a consumer that REDECLARES one of
    these values as its own literal moves the run's numbers while the hash stays byte-identical").
    Passing the headline in makes "the sweep's central leg is the headline" structural.

    NO SWEEP LEG RUNS `check_reconciliation` — ruling O, and the reason is measured, not
    stylistic (it binds every declared leg now, and the q_live pair is still the one that trips):
    at q_live 0.06, the sweep grid's OWN low endpoint, the spec-pinned cohort retains
    0.4565 on the CORRECT model (the gate RAISES) while a doubled decrement retains 0.3724 (the
    gate PASSES), inverted at 21/21 start years. Run at sweep scope this gate would reject the
    right model and accept the wrong one. The sweep's product is RANK STABILITY; calibration is
    the central run's job.
    """
    legs = _sweep_legs(sweep_axes)
    if sweep_axes is not None and set(sweep_axes) != set(declared_sweep_grid()):
        # FAIL-SAFE, and it is the whole safety of the knob: a run that did not evaluate the
        # DECLARED grid cannot show a rank is stable ACROSS it, so it reports `False` and the
        # legs are not evaluated at all (which is where the saving comes from). The reduction
        # can therefore only ever weaken the claim — the run-32 CRITICAL was a `true` shipped
        # over a grid that was never swept, and this is the one place a cost shortcut could
        # reopen that door. `None` for `rows_moved` for the same reason: a run that evaluated no
        # leg has no per-leg count, and an empty map beside `rank_stable: false` would read as
        # "nothing moved".
        return {g: False for g in geos}, None
    grids: list[dict] = [central_ed]
    for _axis, leg in legs:
        # A leg whose assumptions are `==` the central leg's cannot produce a different grid.
        # `headship_shape` is categorical and its central value is one of its two admissible
        # members, so exactly ONE declared leg is a provable no-op; reusing the headline grid
        # for it saves one ED series per (geography, scenario) — the same `rankings rows x
        # len(Scenario)` product whose 12-leg form shipped as a stale `288` until run 52, so it
        # is stated as the product and not as a typed figure. Reusing it SILENTLY would be
        # indistinguishable from dropping the leg, so `tests/test_pipeline.py` names the exempt
        # leg and reds on a second one — a numeric endpoint drifted onto its central value is an
        # inert leg by
        # a different route and must still be caught.
        grids.append(central_ed if leg == CENTRAL_LEG
                     else _ed_dict(geos, frames, read_ownership, leg))
    orders = [{r.geography: r.rank for r in rank_geographies(grid)} for grid in grids]
    stable = {g: all(o[g] == orders[0][g] for o in orders) for g in geos}
    # `orders[0]` is the CENTRAL order and `orders[i+1]` is leg `i`'s — the enumeration and the
    # append above are the same sequence, which is what makes this a count of the leg it names.
    rows_moved = {sweep_leg_label(axis, getattr(leg, axis)):
                  sum(1 for g in geos if orders[i + 1][g] != orders[0][g])
                  for i, (axis, leg) in enumerate(legs)}
    return stable, rows_moved


def _unresolved_immigrant_flows(compo: pd.DataFrame, geos) -> dict[Geography, str]:
    """spec §8's HORS_RMR three-way resolution, branch (iii): a geography whose component
    arrival flows cannot be resolved is EXCLUDED FROM RANKINGS ENTIRELY — no ED, never a
    partial one — and named in a typed run-level exclusion record.

    Branch (i) fires for the committed vintage (`compo-rmr-base.xlsx` ships its own hors-RMR
    row), so this returns EMPTY today and HORS_RMR is RANKED. The path exists and is exercised
    because a future vintage without that row must exclude rather than emit a partial ED — a
    branch that is only ever described is a branch nobody has run.
    """
    present = set(compo["geography"]) if len(compo) else set()
    return {g: "immigrant_component_flows" for g in geos if g not in present}


# ===========================================================================================
# THE RUN
# ===========================================================================================

def evaluate_tripwires(data_dir: Path | None = None, now_year: int = 2026,
                       now_month: int = 12) -> dict:
    """Evaluate spec §7c's six indicators and NOTHING ELSE — the path behind `demoflow tripwires`.

    IT TAKES NO `out_dir`, AND THAT IS THE POINT (run-30 carry C3). Asking for six statuses used
    to run `run_pipeline`, which loads five workbooks, evaluates the ED grid once per declared
    sweep leg (the central run + `_rank_stability`'s sweep, one leg of which reuses the central
    grid) and WRITES BOTH DOCUMENTS — so a status listing re-emitted `rankings.json` into
    whatever directory the operator happened to be standing in.
    A function with nowhere to write cannot reacquire that behaviour by a later edit that forgets
    why; the separation is structural rather than a rule someone has to remember.

    IT MUST NOT BE A SECOND OPINION. A cheap evaluation path is only a saving if it cannot
    disagree with the one that emits `tripwire_baseline.json`, so both go through the SAME
    `_tripwire_results` over the SAME single feed read, and the same `run_exit_code`; a test
    asserts the two paths return equal results, log and code on the committed tree. Nothing
    demographic is reachable from here — the tripwires are a data-freshness gate on the inputs,
    not a readout of the model.

    `now_month` defaults to the LAST month of `now_year` for `run_pipeline`'s stated reason: an
    under-specified call makes a feed look as OLD as that year permits, so it refuses rather than
    certifies. The CLI supplies the real month.

    IT RETURNS THE IDENTITY ENVELOPE TOO, and that is what makes the listing an ATTRIBUTABLE
    reading rather than a floating opinion. A listing carrying neither `assumptions_hash` nor
    `data_vintage` cannot be checked against a committed `tripwire_baseline.json` at all: the two
    can disagree — different bytes, different assumption selection, a re-pinned workbook — with no
    field on either side able to reveal it, and "re-run it and compare" is precisely the second
    read of an unpinned monthly feed that `_tripwire_results` exists to prevent. The SAME two
    fields the document carries are returned here, computed off the SAME single feed read.

    IT INHERITS THE ENVELOPE'S REFUSAL DOORS, and that is the intended trade: `_data_vintage`
    hashes every declared input OFF DISK, so an absent, unhashable or pin-drifted input now
    stops the LISTING too, with the file named, instead of printing six statuses under a
    provenance it could not state. Both outcomes exit nonzero; only one of them says why.
    """
    landings = load_pr_landings(data_dir=data_dir)
    trips, trip_log = _tripwire_results(landings, now=(now_year, now_month))
    return {"tripwires": trips, "tripwire_log": trip_log, "exit_code": run_exit_code(trips),
            "assumptions_hash": assumptions_hash(),
            "data_vintage": _data_vintage(data_dir, landings)}


def run_pipeline(data_dir: Path | None = None, out_dir: Path | None = None,
                 now_year: int = 2026, now_month: int = 12,
                 sweep_axes: tuple[str, ...] | None = None) -> dict:
    """Emit `rankings.json` + `tripwire_baseline.json`, and return the run's own record.

    `now_month` defaults to the LAST month of `now_year`, which is the fail-safe end of the
    freshness axis: a caller who does not state the month makes a feed look as OLD as that year
    permits, so an under-specified call refuses (UNKNOWN/stale) rather than certifies. The CLI
    supplies the real month.

    `sweep_axes=None` — THE COMMITTED DEFAULT — evaluates every declared robustness axis at
    both endpoints. A caller may name FEWER axes, and a run that did so reports
    `rank_stable: false` on every row by construction (see `_rank_stability`): it did not
    evaluate the declared grid, so it cannot certify stability across it. The knob exists
    because most end-to-end tests of this function assert nothing about the robustness verdict
    and were each paying the full declared sweep for it — a gate slow enough that people stop
    running it has stopped working. `golden.generate_golden` never passes it: a golden minted
    from a reduced sweep is the defect the widened sweep exists to close.
    """
    frames = _load_all(data_dir)
    read_ownership = _ownership_reader(data_dir)
    ah = assumptions_hash()

    # THE IDENTITY ENVELOPE. `assumptions_hash` identifies the ASSUMPTION SELECTION and the
    # data vintage rides `data_vintage.source_hashes` — two tokens for two questions, which is
    # what makes a red attributable to data-vs-code. Folding the data digest into the
    # assumptions hash would give one token that moves for both and answers neither.
    landings = load_pr_landings(data_dir=data_dir)
    vintage = _data_vintage(data_dir, landings)
    now = (now_year, now_month)
    identity = _run_identity(data_dir, landings, now)

    present = [g for g in Geography if g in set(frames.pop["geography"])]
    unresolved = _unresolved_immigrant_flows(frames.compo, present)
    geos = [g for g in present if g not in unresolved]

    # RULING O — the CENTRAL-ASSUMPTION run, and only it, discharges the reconciliation gate.
    check_reconciliation(
        _reconciliation_retention(frames, read_ownership, CENTRAL_LEG.q_live_per_year,
                                  CENTRAL_LEG.collective_share_75plus))

    ed = _ed_dict(geos, frames, read_ownership, CENTRAL_LEG)
    ed, exclusions = exclude_from_rankings(ed, unresolved)

    # `borrowed_prior` says the geography's IMMIGRANT INPUTS were borrowed from a coarser prior,
    # and `ImmigrantInputs` answers that PER FIELD over its own closed vocabulary — under ruling Q
    # a geography may carry a cited ratio beside a borrowed headship, which a hardcoded geography
    # set cannot express. The plan derived it from `RA_PROXY_MEMBERS | {HORS_RMR}`, which put a
    # second flag on the RA rows for the fact `ra_proxy` already states and a WRONG one on
    # HORS_RMR, whose provenance is `computed_residual` — nothing was borrowed.
    #
    # IT IS NOT THE OWNERSHIP BORROW, and the two are easy to confuse because the WORD is the
    # same and the geography sets overlap without matching. FIVE geographies borrow MTL_RMR's
    # ownership CURVE (MTL_RMR owns it; `census._BORROWS_FROM` names them) — and LAVAL_RA13 and
    # MTL_ISLAND_RA06 carry NO `borrowed_prior` flag despite doing so, because their immigrant
    # ratio and headship inputs are their own. A reader who takes the emitted flag as "this row's
    # rates were borrowed" will read those two rows wrong. The flag's subject is the immigrant
    # leg; the ownership borrow is published in `ownership_by_geo_age.json`'s own inline
    # `_flag: borrowed_prior` per rate row, which is a different surface.
    def _borrowed_inputs(g: Geography) -> bool:
        row = resolve_immigrant_inputs(g)
        return "borrowed_prior" in (row.headship_provenance, row.ratio_provenance)

    borrowed = {g for g in geos if _borrowed_inputs(g)}
    stable, rows_moved = _rank_stability(geos, frames, read_ownership, ed, sweep_axes)
    # spec §7b's composition rule, sampled AROUND the whole computation (see the gate).
    _refuse_mixed_identity({identity, _run_identity(data_dir, landings, now)})
    rankings = rank_geographies(ed, borrowed=borrowed, rank_stable=stable)

    # TRANCHE-2 (spec §7(a)): the ScenarioPrior rows, from the SAME central-assumption ED grid
    # the rankings rank — one computation, three documents, one vintage. The horizon lookup is
    # by POSITION in each geography's projected-year lattice; the builder refuses ragged
    # lattices and horizons the frame does not project, so a row is never indexed into a year
    # the grid did not compute.
    lattices = {g: _projected_years(frames.pop[(frames.pop["geography"] == g)
                                               & (frames.pop["scenario"] == Scenario.REFERENCE)])
                for g in geos}
    prior_rows = build_scenario_prior_rows(ed, lattices, borrowed)

    trips, trip_log = _tripwire_results(landings, now=now)
    source_keys = frozenset(vintage["source_hashes"])

    # EMISSION IS ALL-OR-NOTHING (review finding F2), AND THE WRITES ARE PART OF THAT CLAIM
    # (run-33 stress gate F8). Both documents are BUILT AND VALIDATED before either is
    # written: the landed body wrote `rankings.json` and only then built `tripwire_document`,
    # so a refusal in the second document shipped the first file alone — contradicting the
    # sentence `artifacts.py` raises inside that very refusal ("NO file is emitted and the run
    # exits nonzero"). A half-emitted pair is worse than no pair: the rankings file carries the
    # same envelope either way, so nothing downstream can tell, and `refuse_cross_vintage`
    # operates WITHIN a run over a set this function itself builds.
    #
    # THE VALIDATION HALF WAS TRUE AND THE WRITE HALF WAS NOT. The writes were a bare
    # sequential loop, so an I/O failure on the SECOND document left the first on disk —
    # measured, `['rankings.json']` survived. Each document is therefore SERIALIZED to a
    # staging name beside its final one and RENAMED only after every write has succeeded, and
    # the staging files are removed on any exit. THE RESIDUAL, stated rather than papered
    # over: the renames themselves are a loop, so a failure BETWEEN two `os.replace` calls
    # still leaves a mismatched pair. That window is a same-directory metadata operation on a
    # file that already exists, where the old window spanned a full open-and-serialize; POSIX
    # gives no atomic multi-file rename, so narrowing is the honest ceiling ON THE WINDOW.
    # IT IS NOT THE CEILING ON THE RESIDUAL, and recording it as one is what spec amendment
    # #20(C)(3) ruled against. DETECTION IS THE `run_pairing` TOKEN BOTH DOCUMENTS BELOW CARRY,
    # and what it binds is spec amendment #22(C)'s ruling: the CANONICAL PAYLOAD DIGESTS OF BOTH
    # DOCUMENTS — each file's content outside its identity envelope. So it moves whenever either
    # payload moves, FOR ANY CAUSE, and a consumer comparing it across the pair refuses any
    # mismatch this loop can leave in which the two files' CONTENT came from different runs —
    # including a computation change touching no constant, no data byte and no schema, which
    # #20(C)(3)'s (assumptions, sources, `now`) payload was blind to and which this comment
    # previously claimed was covered.
    #
    # WHAT IT DOES NOT REFUSE, because a gate description broader than the gate is this module's
    # cardinal defect: a pair whose two files' PAYLOADS are byte-identical to the honest run's.
    # `now` is not payload — it is an input neither document records — so on today's tree, where
    # every tripwire indicator is structurally UNKNOWN and the clock reaches no emitted value, two
    # runs separated only by the clock produce the same token. That pair is content-identical to an
    # honest one in both files, so nothing downstream reads a different number for having accepted
    # it; `data_vintage` and `assumptions_hash` ride both files for the other two axes and a
    # consumer compares them directly. The clock becomes visible to this token through CONTENT the
    # moment the first indicator carries a real value.
    #
    # ATOMICITY IS BOUNDED BY POSIX AND DETECTION IS NOT — that split is unchanged; what changed
    # is that the token can now SEE a code change, which is the half the earlier claim asserted
    # without having.
    #
    # THE TOKEN IS STAMPED AFTER BOTH PAYLOADS EXIST (`stamp_pairing_token` owns the ordering),
    # because it is a function of both — the builders cannot be called once each in sequence and
    # handed a token computed before either ran.
    documents = stamp_pairing_token(
        lambda token: {
            "rankings.json": rankings_document(rankings, vintage, ah, source_keys,
                                               run_pairing=token, exclusions=exclusions,
                                               rows_moved=rows_moved),
            "tripwire_baseline.json": tripwire_document(trips, vintage, ah, source_keys,
                                                        run_pairing=token),
            "scenario_prior.json": scenario_prior_document(prior_rows,
                                                           prior_vintage(source_hashes=vintage[
                                                               "source_hashes"]),
                                                           ah, source_keys, run_pairing=token),
        })
    out_dir = Path(out_dir) if out_dir else Path.cwd() / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    staged = {name: out_dir / (name + STAGING_SUFFIX) for name in documents}
    try:
        for name, document in documents.items():
            write_json_strict(staged[name], document, source_keys)
        for name, tmp in staged.items():
            os.replace(tmp, out_dir / name)
    finally:
        for tmp in staged.values():
            tmp.unlink(missing_ok=True)
    return {"rankings": rankings, "tripwires": trips, "tripwire_log": trip_log,
            "exclusions": exclusions, "exit_code": run_exit_code(trips), "out_dir": out_dir,
            "artifacts": list(documents), "assumptions_hash": ah, "data_vintage": vintage}
