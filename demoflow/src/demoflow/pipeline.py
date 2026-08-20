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
from demoflow.cohort.init import initialize_households
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
    load_ownership_rates, ownership_rate,
)
from demoflow.loaders.compo import FLOW_SPAN, load_immigrant_flows
from demoflow.loaders.constants import (
    ASSUMPTIONS_HASH_CHARS, CENTRAL_ASSUMPTIONS, CONSTANTS, MODEL_CHOICES, SWEEP_GRID,
    assumptions_hash,
)
from demoflow.loaders.hors_aligned import (
    ARTIFACT as ALIGNED_OWNERSHIP_ARTIFACT, aligned_ownership_rate, load_aligned_ownership_join,
    load_aligned_ownership_rates,
)
from demoflow.loaders.ircc import CSV_NAME as IRCC_CSV_NAME, load_pr_landings
from demoflow.loaders.isq import load_population
from demoflow.loaders.living_arrangement import (
    ARTIFACT as LIVING_ARRANGEMENT_ARTIFACT, couple_share, living_alone_rate,
    load_living_arrangement,
)
from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256, raw_anchor
from demoflow.output.artifacts import rankings_document, tripwire_document, write_json_strict
from demoflow.output.rankings import exclude_from_rankings, rank_geographies, refuse_cross_vintage
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

# THE TWO UNCITED MONEY-PATH LITERALS, now READ-THROUGH from the constants surface rather than
# declared here (run-32 stress gate F2). Each swings the shipped headline `mean_ed_*` numbers by
# 55-66% and neither was inside either identity token, so editing one moved every emitted number
# under a byte-identical envelope. `constants.MODEL_CHOICES` carries the values, its provenance
# twin carries the honest UNCITED derivation, and `assumptions_hash` now covers both — the same
# read-through binding `cohort/listings.py` uses for its three central assumptions. The names
# stay HERE because they are this module's own vocabulary; the VALUES are declared once.
#
# DO NOT INLINE EITHER NUMBER BACK. A redeclared literal equal to today's value passes every
# equality read, so `tests/test_constants.py` mutates `MODEL_CHOICES`, re-executes this module
# and asserts both names MOVED — a check only a read-through binding survives.
#
# ROLL_AGE — the single lumped 75+ bucket's hazard age (Tranche-1 coarseness, the plan body's).
# A MODEL choice and not an index: the bucket holds everyone 75+ and is decremented at one age,
# so raising or lowering it moves S for every geography.
# P_NONIMM_AGE — the age at which the non-immigrant ownership propensity is read for the
# immigrant leg. Spec §6 defines `p_imm(a) = p_nonimm(a) x ratio` age-indexed while the ISQ
# arrival flow carries no age axis, so one age must be chosen; ownership is BANDED, so 40
# selects the 25-54 band (quant gate F5 measures the band choice at the size of the whole
# signal, and the pick inside the band as inert).
ROLL_AGE = MODEL_CHOICES["roll_age"]
P_NONIMM_AGE = MODEL_CHOICES["p_nonimm_age"]

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
        "here, which is the only place they are checked at all (no runtime path opens this file)",
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

# The GENERATED artifacts the run OPENS — every rate the model multiplies comes out of these
# four files. Keyed by each loader's own name constant, never a restated literal.
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


def _run_identity(data_dir: Path | None, ircc) -> str:
    """The run's FULL identity: the assumption selection AND the data vintage, in one token.

    CARRY B4, and the reason this is a token rather than a widened `assumptions_hash()`.
    `assumptions_hash` covers the assumption SELECTION — the central/sweep values, banded and
    categorical alike, the unswept model choices and the ruled immigrant join table — and
    NOTHING about the data, so
    two runs over different source bytes produce an identical hash; the envelope could not make
    the data-vs-code call §9 rests on. Folding the data digest INTO that hash would fix
    the first half by destroying the second: one token that moves for either cause answers
    neither question. So the emitted envelope keeps TWO fields — `assumptions_hash` (the
    selection) and `data_vintage.source_hashes` (the bytes), the second of which this task
    widened from three inputs to every input the run reads — and the composition gate below
    gets a token over BOTH, which is the thing that has to be constant across a single run.
    """
    payload = json.dumps({"assumptions": assumptions_hash(),
                          "sources": _source_hashes(data_dir, ircc)}, sort_keys=True)
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
    `census_tenure_age_98100231.csv`, `living_arrangement_98100134.json`,
    `hors_aligned_csd_98100232.json` and `pop-as-qc-base.xlsx` are DERIVATION-time inputs that no
    runtime path opens, so for those four this is the only place the committed bytes are checked
    at all — and the landed body checked nothing, which is how a garbage census extract left a
    run completing with an unchanged envelope (review finding F1).
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
        published = raw_anchor(name) if source.publishes == _RAW_ANCHOR else digest
        out[name] = {"sha256": published, "extracted_at": source.extracted_at}

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
_TRIPWIRE_DECLARATIONS: dict[str, tuple[int, int, SourceKind]] = {
    PR_LANDINGS_INDICATOR: (2026, 1, SourceKind.WIRED),
    "temp_resident_stock": (2026, 1, SourceKind.WIRED),
    "isq_edition_watch": (2026, 1, SourceKind.WIRED),
    "registre_foncier_volume": (2026, 1, SourceKind.OPERATOR_SUPPLIED),
    "cmhc_senior_sale_5yr": (2021, 5, SourceKind.OPERATOR_SUPPLIED),
    "natural_increase_sign": (2026, 1, SourceKind.OPERATOR_SUPPLIED),
}


def _spec_for(indicator: str) -> TripwireSpec:
    as_of, freshness, kind = _TRIPWIRE_DECLARATIONS[indicator]
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
                              freshness_years=_TRIPWIRE_DECLARATIONS[PR_LANDINGS_INDICATOR][1])
    log.append(f"{PR_LANDINGS_INDICATOR}: {pr.log}")

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
    """

    _ALIGNED = "operand_aligned"
    _SHIPPED = "shipped"

    def __init__(self, shipped: dict, aligned: dict, join: dict) -> None:
        self.shipped, self.aligned, self.join = shipped, aligned, join

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


def _ownership_reader(data_dir: Path | None) -> _OwnershipReader:
    return _OwnershipReader(load_ownership_rates(data_dir=data_dir),
                            load_aligned_ownership_rates(data_dir=data_dir),
                            load_aligned_ownership_join(data_dir=data_dir))


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


# ===========================================================================================
# THE 75+ COHORT
# ===========================================================================================

# `roll_one_year` emits exits keyed by ITS vocabulary; `phi_market` accepts a DIFFERENT one.
# Stated as an explicit total map rather than handed over positionally: `market_listings`
# takes (voluntary, estate) in that order and both are `dict[int, float]`, so a transposition
# runs clean and puts the estate flow through the voluntary fraction with no lag — every
# number still plausible, the whole supply term wrong.
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
                     read_ownership) -> Stock:
    """Owner-unit Stock from a population slice, through spec §5's INITIALIZATION EQUATIONS.

    `Other` (persons living with others) is excluded from the owner stock as presumptive
    non-maintainers — `HouseholdInit` carries no `owner_other` for exactly that reason.
    """
    pop_by_sex = {s: float(rows[rows["sex"] == s]["population"].sum()) for s in ("M", "F")}
    h = initialize_households(
        pop_by_sex,
        living_alone_rate_by_sex={s: living_alone_rate(la, geo, age, s) for s in ("M", "F")},
        couple_share_by_sex={s: couple_share(la, geo, age, s) for s in ("M", "F")},
        collective_share=CONSTANTS["collective_share_75plus"].value,
        ownership_rate=read_ownership(geo, age),
    )
    return Stock(couple=h.owner_couple, solo_m=h.owner_solo_m, solo_f=h.owner_solo_f)


def _standing_stock(pop_g_s: pd.DataFrame, year: int, geo: Geography, la: dict,
                    read_ownership) -> Stock:
    """The 75+ owner stock standing at `year` — the roll-forward's initial condition."""
    rows = pop_g_s[(pop_g_s["year"] == year) & (pop_g_s["age"] >= BAND_ENTRY_AGE)]
    if rows.empty:
        raise LoaderError(f"{geo.value}: no 75+ population at {year} — the roll-forward has no "
                          "initial condition and an empty one is not a zero one")
    return _household_stock(rows, geo, ROLL_AGE, la, read_ownership)


def _band_entry_stock(pop_g_s: pd.DataFrame, year: int, geo: Geography, la: dict,
                      read_ownership) -> Stock:
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
    return _household_stock(rows, geo, BAND_ENTRY_AGE, la, read_ownership)


def _add(a: Stock, b: Stock) -> Stock:
    return Stock(a.couple + b.couple, a.solo_m + b.solo_m, a.solo_f + b.solo_f)


def _listings_at(listings: dict[int, float], year: int, ctx: str) -> float:
    """The supply term S at `year` — REFUSING a year the roll-forward never keyed.

    `listings.get(year, 0.0)` stood here, in a module whose own docstring says "every silent-zero
    door on the model path refuses instead". It is UNREACHABLE as written and the door is closed
    anyway, because unreachability here is a property of two loops staying in step rather than of
    anything structural: the supply loop keys `voluntary` at every year from the population
    frame's first through `years[-1]`, which covers the whole ranking domain, and nothing binds
    those two ranges together except that one line writes them and another reads them.

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


def _reconciliation_retention(frames: Frames, read_ownership, q_live: float) -> float:
    geo, scen, start_year, age = RECONCILIATION_COHORT
    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    return roll_cohort_decade(
        start_age=age, start_year=start_year, q_live=q_live, qx=q_at,
        initial=_band_entry_stock(pop_g_s, start_year, geo, frames.la, read_ownership))


# ===========================================================================================
# THE ROBUSTNESS SWEEP'S ASSUMPTION LEG (spec §7b run contract; run-32 quant F1 / stress F1)
# ===========================================================================================
#
# `rank_stable: true` SHIPPED ON ALL EIGHT ROWS AS A VERDICT OVER ONE OF SIX DECLARED AXES
# (five when the narrowing was found; `headship_shape` joined at ruling V).
# `_rank_stability` iterated `SWEEP_GRID["q_live_per_year"]`; the grid declares FOUR, and
# `constants.py` states a FIFTH as an existing fact of THIS module — "Task 29 perturbs the join
# table with a uniform override spanning CONSTANTS['immigrant_ownership_ratio_sweep_span']" —
# for which no code existed anywhere in the tree. Two committed contracts in direct
# contradiction, green because no test crossed them. And the omission was not benign: ON THE BAND
# CURVE the four grid axes left the published order INTACT at both endpoints, while the ratio axis
# reordered EVERY row at 0.155 (rank 1 changes hands) and four rows at 1.033. The one axis that
# was swept was the one that could not have failed.
#
# THOSE PER-LEG FIGURES ARE PRE-RULING-V AND THREE OF THEM NO LONGER HOLD. Re-measured on the
# resolved curve at the run-35 re-mint, by re-running `_rank_stability`'s own leg loop (central
# order reproduces the committed `rankings.json` exactly): `estate_eventual_fraction` and
# `estate_lag_years` still move NOTHING at either endpoint, but `q_live_per_year` reorders 2 rows
# at 0.11, `phi_voluntary` 3 rows at 1.0, the new `headship_shape` axis 3 rows at `expo_cum_fb`,
# and the ratio axis 8 rows at 0.155 (rank 1 -> MTL_RMR) and SIX — not four — at 1.033 (rank 1 ->
# LAVAL_RA13). THE VERDICT IS UNCHANGED AND SO IS ITS MECHANISM: 0.155 is still the only leg that
# moves ALL eight rows, so it alone saturates the union and `rank_stable` stays `false` everywhere.
# What changed is the MARGIN — the resolved curve packs ranks 1-4 inside 2.6e-4 — so a reader must
# not carry "only the ratio axis can reorder" forward from the sentence above. `artifacts/README.md`
# holds the same table, and NO test pins these per-leg counts (the pins are the union verdict,
# all-8-move at 0.155, and rank-1-changes-hands there).
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
# STATED RESIDUAL, because it is the one thing this wiring does NOT close. `SWEEP_GRID` rides
# `assumptions_hash`; `CONSTANTS` does not, and the ratio span now feeds an EMITTED field. So
# narrowing that span (the one edit that would legitimately flip a `rank_stable` back to `true`)
# moves the artifact under a byte-identical `assumptions_hash`, and `artifacts/README.md`'s
# reading table would route the reader to its "the code moved" bucket — a mis-attribution of the
# same class run 33 closed for the mortality basis and the ruled join table. The fix is one
# payload key in `constants.assumptions_hash`; it is NOT taken here because that token's coverage
# is a §7b identity question with its own owner, and widening it silently from inside the sweep
# is how a second contract starts disagreeing with the first.
RATIO_SWEEP_AXIS = "immigrant_ownership_ratio"
RATIO_SWEEP_SPAN_ANCHOR = "immigrant_ownership_ratio_sweep_span"


@dataclass(frozen=True)
class Assumptions:
    """Every SWEPT assumption the ED grid reads, at ONE setting — the headline's or a leg's;
    banded and categorical alike since ruling V added `headship_shape` (the membership rule is
    `loaders/constants.py`'s MODEL_CHOICES header, and the body below marks the categorical one).

    The five named fields are `CENTRAL_ASSUMPTIONS`' own keys, so `Assumptions(**CENTRAL_
    ASSUMPTIONS)` is the central leg and a key added there without a field here raises AT
    IMPORT rather than being dropped from the sweep. `immigrant_ownership_ratio` is the sixth
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
    the split is measured, not assumed — MEASURED AT 98c2f10, against that commit's five-axis
    ten-leg grid: with that one test removed, a mutant that ignored all four numeric
    `SWEEP_GRID` fields inside `_ed_series` left 8 of those 10 legs at max|delta ED| = 0.0 and
    passed the remaining 1139 tests — the central run is untouched so no golden byte moves, and
    the ratio axis alone keeps `rank_stable` false on every row. Ruling V's `headship_shape`
    axis widens the grid to twelve legs and does not weaken that split: it adds one LIVE leg
    (`expo_cum_fb`) and one inert BY CONSTRUCTION (the `expo_cum_fc` leg, which IS `CENTRAL_LEG`
    and reuses the central grid), so the same mutant would now leave 9 of 12 inert. That is
    arithmetic on the two new legs, not a re-run — the mutation battery has NOT been re-measured
    on the twelve-leg grid.
    """
    declared = {axis: SWEEP_GRID[axis] for axis in sorted(SWEEP_GRID)}
    declared[RATIO_SWEEP_AXIS] = CONSTANTS[RATIO_SWEEP_SPAN_ANCHOR].value
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
    p_nonimm = read_ownership(geo, P_NONIMM_AGE)

    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    compo_g_s = frames.compo[(frames.compo["geography"] == geo)
                             & (frames.compo["scenario"] == scen)]
    years = _projected_years(pop_g_s)
    base_year, last_pop_year = int(pop_g_s["year"].min()), int(pop_g_s["year"].max())

    # --- supply: roll the lumped 75+ owner bucket from the frame's first year.
    stock = _standing_stock(pop_g_s, base_year, geo, frames.la, read_ownership)
    listings_in: dict[str, dict[int, float]] = {
        cause: {} for cause in EXIT_CAUSE_TO_LISTING_CAUSE.values()}
    for year in range(base_year, years[-1] + 1):
        nxt, exits = roll_one_year(stock, age=ROLL_AGE, year=year, q_live=q_live, qx=q_at)
        for cause, value in _split_exits(exits, ctx=f"{ctx}/{year}").items():
            listings_in[cause][year] = value
        entry_year = year + 1
        stock = (_add(nxt, _band_entry_stock(pop_g_s, entry_year, geo, frames.la, read_ownership))
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
    # inefficiency while the run evaluated three ED grids; the six-axis sweep evaluates TWELVE
    # and it rode every one. `_projected_years` ASSERTS the lattice is CONTIGUOUS, and that
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
                    sweep_axes: tuple[str, ...] | None = None) -> dict[Geography, bool]:
    """The RUN-CONTRACT robustness sweep (codex r8-F1): a geography's rank is STABLE iff it is
    unchanged across EVERY leg `_sweep_legs` declares — six axes at both endpoints each,
    twelve legs — measured against the central value. Spec §7b's question is "does the ordering change
    ANYWHERE IN THE SWEEP GRID?", so the verdict is a UNION and a single reordering leg is
    enough to make a geography unstable.

    IT RETURNS `False` FOR EVERY GEOGRAPHY ON THE COMMITTED VINTAGE, and that is the measured
    answer rather than a regression. Re-measured at the run-35 re-mint on the resolved headship
    curve: the ratio override reorders EVERY row at 0.155 and six rows at 1.033, `q_live_per_year`
    two rows at 0.11, `phi_voluntary` three at 1.0, `headship_shape` three at `expo_cum_fb`, and
    only the two estate axes leave the order intact at both endpoints. The 0.155 leg is still the
    only one that moves all eight, so the union verdict rests on the same single leg it always did
    — but the pre-ruling-V reading of this docstring ("the four `SWEEP_GRID` axes leave the
    published order intact... four rows at 1.033") is retired, not merely restated: three axes
    that could not reorder the band curve reorder this one. The narrow sweep that shipped `true`
    was evaluating the one axis that could not have failed (run-32 quant F1 / stress F1, reached
    independently; `_sweep_legs` carries the contradiction the two committed contracts had been
    holding).

    THE CENTRAL LEG IS HANDED IN, NOT RECOMPUTED, and that is a contract rather than a saving.
    The run contract says the headline IS the central-value evaluation, so a sweep that
    re-derives its own central leg has two computations that must agree and nothing making them
    agree — the shape `constants.py` forbids one level down ("a consumer that REDECLARES one of
    these values as its own literal moves the run's numbers while the hash stays byte-identical").
    Passing the headline in makes "the sweep's central leg is the headline" structural.

    NO SWEEP LEG RUNS `check_reconciliation` — ruling O, and the reason is measured, not
    stylistic (it binds all twelve legs now, and the q_live pair is still the one that trips):
    at q_live 0.06, the sweep grid's OWN low endpoint, the spec-pinned cohort retains
    0.4565 on the CORRECT model (the gate RAISES) while a doubled decrement retains 0.3724 (the
    gate PASSES), inverted at 21/21 start years. Run at sweep scope this gate would reject the
    right model and accept the wrong one. The sweep's product is RANK STABILITY; calibration is
    the central run's job.
    """
    legs = _sweep_legs(sweep_axes)
    if sweep_axes is not None and set(sweep_axes) != set(SWEEP_GRID) | {RATIO_SWEEP_AXIS}:
        # FAIL-SAFE, and it is the whole safety of the knob: a run that did not evaluate the
        # DECLARED grid cannot show a rank is stable ACROSS it, so it reports `False` and the
        # legs are not evaluated at all (which is where the saving comes from). The reduction
        # can therefore only ever weaken the claim — the run-32 CRITICAL was a `true` shipped
        # over a grid that was never swept, and this is the one place a cost shortcut could
        # reopen that door.
        return {g: False for g in geos}
    grids = [central_ed]
    for _axis, leg in legs:
        # A leg whose assumptions are `==` the central leg's cannot produce a different grid.
        # `headship_shape` is categorical and its central value is one of its two admissible
        # members, so exactly ONE declared leg is a provable no-op; reusing the headline grid
        # for it saves 24 ED series per run. Reusing it SILENTLY would be indistinguishable
        # from dropping the leg, so `tests/test_pipeline.py` names the exempt leg and reds on
        # a second one — a numeric endpoint drifted onto its central value is an inert leg by
        # a different route and must still be caught.
        grids.append(central_ed if leg == CENTRAL_LEG
                     else _ed_dict(geos, frames, read_ownership, leg))
    orders = [{r.geography: r.rank for r in rank_geographies(grid)} for grid in grids]
    return {g: all(o[g] == orders[0][g] for o in orders) for g in geos}


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
    to run `run_pipeline`, which loads five workbooks, evaluates the ED grid TWELVE times (the
    central run + `_rank_stability`'s twelve-leg six-axis sweep, one leg of which reuses the
    central grid) and WRITES BOTH DOCUMENTS — so a
    status listing
    re-emitted `rankings.json` into whatever directory the operator happened to be standing in.
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
    and were each paying a full twelve-leg sweep for it — a gate slow enough that people stop
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
    identity = _run_identity(data_dir, landings)

    present = [g for g in Geography if g in set(frames.pop["geography"])]
    unresolved = _unresolved_immigrant_flows(frames.compo, present)
    geos = [g for g in present if g not in unresolved]

    # RULING O — the CENTRAL-ASSUMPTION run, and only it, discharges the reconciliation gate.
    check_reconciliation(
        _reconciliation_retention(frames, read_ownership, CENTRAL_LEG.q_live_per_year))

    ed = _ed_dict(geos, frames, read_ownership, CENTRAL_LEG)
    ed, exclusions = exclude_from_rankings(ed, unresolved)

    # `borrowed_prior` says the geography's INPUTS were borrowed from a coarser prior, and
    # `ImmigrantInputs` answers that PER FIELD over its own closed vocabulary — under ruling Q a
    # geography may carry a cited ratio beside a borrowed headship, which a hardcoded geography
    # set cannot express. The plan derived it from `RA_PROXY_MEMBERS | {HORS_RMR}`, which put a
    # second flag on the RA rows for the fact `ra_proxy` already states and a WRONG one on
    # HORS_RMR, whose provenance is `computed_residual` — nothing was borrowed.
    def _borrowed_inputs(g: Geography) -> bool:
        row = resolve_immigrant_inputs(g)
        return "borrowed_prior" in (row.headship_provenance, row.ratio_provenance)

    borrowed = {g for g in geos if _borrowed_inputs(g)}
    stable = _rank_stability(geos, frames, read_ownership, ed, sweep_axes)
    # spec §7b's composition rule, sampled AROUND the whole computation (see the gate).
    _refuse_mixed_identity({identity, _run_identity(data_dir, landings)})
    rankings = rank_geographies(ed, borrowed=borrowed, rank_stable=stable)

    trips, trip_log = _tripwire_results(landings, now=(now_year, now_month))
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
    # gives no atomic multi-file rename, so narrowing is the honest ceiling, not closing.
    documents = {
        "rankings.json": rankings_document(rankings, vintage, ah, source_keys,
                                           exclusions=exclusions),
        "tripwire_baseline.json": tripwire_document(trips, vintage, ah, source_keys),
    }
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
