"""Contract tests for `pipeline.py` — the Tranche-1 orchestrator.

THE DATA SOURCE IS EXPLICIT IN EVERY TEST THAT RUNS THE PIPELINE (carry B11). The plan body
called `run_pipeline(out_dir=tmp_path, now_year=2026)` with no `data_dir`, so the suite's
result depended on whatever bytes `pins.DATA_DIR` happened to hold and no reader of the test
could tell which vintage it asserted against. `_DATA` below names it once.

WHAT THIS FILE PINS THAT NO UNIT TEST CAN. Every module under `src/` is a leaf with its own
contracts; the orchestrator is where they meet, and four of the arc's rulings are ORCHESTRATOR
obligations that no leaf can enforce — ruling O's central-only reconciliation scope
(`gates.py` says so in its own docstring), the operand-aligned ownership join (`hors_aligned.py`
is consumed by nothing until here), the RUN-CONTRACT central/sweep split, and spec §7c's
run-level exit code. Each gets a test that FAILS if the wiring is dropped, not merely one that
passes when it is present.
"""
import dataclasses
import hashlib
import inspect
import json
import math
import re
import shutil
import statistics
from pathlib import Path

import pandas as pd
import pytest

from demoflow.cohort.basis import (
    BASIS_DIGEST_AGES,
    BASIS_DIGEST_GENDERS,
    BASIS_DIGEST_YEARS,
    BASIS_SOURCE_KEY,
)
from demoflow.errors import CalibrationError, LoaderError
from demoflow.geography import RA_PROXY_MEMBERS, Geography, Scenario
from demoflow.loaders import census
from demoflow.loaders.census import (
    CENSUS_EXTRACT,
    OWNERSHIP_ARTIFACT,
    ownership_union_rates,
)
from demoflow.loaders.compo import FLOW_SPAN
from demoflow.loaders.constants import (
    CENTRAL_ASSUMPTIONS,
    CONSTANTS,
    SWEEP_GRID,
    assumptions_hash,
    sweep_leg_labels,
)
from demoflow.loaders.ircc import CSV_NAME as IRCC_CSV_NAME
from demoflow.loaders.living_arrangement import ARTIFACT as LIVING_ARRANGEMENT_ARTIFACT
from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256, raw_anchor
from demoflow.output.artifacts import DERIVED_ARTIFACT_KEYS, SOURCE_KEY_REGISTRY
from demoflow.output.rankings import CLOSED_COHORT_EXCEEDANCE_MEMBERS, rank_geographies
from demoflow.output.tripwires import (
    PR_LANDINGS_INDICATOR,
    REQUIRED_INDICATORS,
    Reason,
    Status,
)

import demoflow.output.artifacts as artifacts
import demoflow.output.rankings as rankings_mod
import demoflow.pipeline as pipeline

# The CENTRAL setting of the seventh sweep axis (spec amendment #20(D)), for the unit-level
# stock calls below. `_household_stock` and both its callers REQUIRE it as a keyword — the
# module read it off `CONSTANTS` until 2026-08-22, which is why no sweep leg could reach it —
# so a test that calls them states which leg it is standing on. Read through, never 0.04.
_CENTRAL_COLLECTIVE = CENTRAL_ASSUMPTIONS["collective_share_75plus"]

# The golden's pinned clock, restated here because `_run_identity` now takes it as a payload
# member (spec amendment #20(C)(3)) and a unit-level call has to state which run it is standing in.
_NOW = (2026, 12)
from demoflow.pipeline import (
    EXIT_CAUSE_TO_LISTING_CAUSE,
    RECONCILIATION_COHORT,
    RUN_ARTIFACTS,
    RUN_SOURCES,
    UNRULED_BAND,
    run_pipeline,
)

from ._prose_binding import EXP, PCT_PLAIN, PCT_SIGNED, PP, PP_ABS, bound_map, flat, says

# The run's data source, named ONCE and passed explicitly everywhere (carry B11).
_DATA = DATA_DIR

# THE SWEEP REDUCTION, named once and used only where it is SOUND (ruling V, run 34). Every
# test below that runs `run_pipeline` end to end to assert something about EMISSION, the
# identity bracket, the exit code or a gate's call count paid a full fourteen-leg robustness
# sweep for a verdict it never reads — measured at ~19s each against a suite already near five
# minutes, and the shape axis this run added would have made it worse. `sweep_axes=()` skips
# the legs, and `_rank_stability` then reports `rank_stable: False` on every row BY
# CONSTRUCTION: a run that did not evaluate the declared grid cannot certify stability across
# it. So the reduction can only ever weaken the claim, never manufacture one.
#
# IT IS NEVER USED BY A TEST THAT ASSERTS ON `rank_stable` — the `run` fixture and the golden
# both keep the full sweep — and `test_a_REDUCED_sweep_can_never_certify_rank_stability` pins
# both halves.
_NO_SWEEP: tuple[str, ...] = ()


def _data_copy(dest):
    """A private COPY of the committed data dir. Every byte-drift probe below mutates its own
    copy — the live tree is read-only to this suite."""
    return shutil.copytree(_DATA, dest)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """ONE full pipeline run for the whole module — it loads five workbooks and evaluates the
    ED grid FOURTEEN times (the central run, reused as the sweep's central leg AND as the one
    no-op `headship_shape` leg, plus `_rank_stability`'s thirteen remaining seven-axis legs), so a
    per-test run would multiply minutes of real I/O by every assertion below.

    IT KEEPS THE FULL SWEEP, deliberately: the assertions below include `rank_stable` on every
    row, which a reduced sweep reports `False` for by construction. The tests that reduce it
    (`sweep_axes=()`) are the ones asserting nothing about the robustness verdict.

    IT ALSO RECORDS THE RUN'S q CONSUMPTION, because that is the one measurement the basis
    digest's coverage claim needs and no unit test can make: `BASIS_DIGEST_*` must be a
    SUPERSET of what the model actually reads, and the population-lattice years come from
    DATA, not from any constant a unit test could bind to. The wrapper is a pass-through and
    it patches `pipeline.q_at` — the module global BOTH call sites resolve — so `basis_digest`
    itself, which calls `basis.q_at` internally, is deliberately not recorded: the digest's own
    lookups are not model consumption. try/finally, because a raising `run_pipeline` must not
    leak the patch into the rest of the module.
    """
    out = tmp_path_factory.mktemp("artifacts")
    consumed: set[tuple[int, str, int]] = set()
    real_q_at = pipeline.q_at

    def recording_q_at(age, gender, year):
        consumed.add((age, gender, year))
        return real_q_at(age, gender, year)

    pipeline.q_at = recording_q_at
    try:
        result = run_pipeline(data_dir=_DATA, out_dir=out, now_year=2026)
    finally:
        pipeline.q_at = real_q_at
    result["_q_consumption"] = consumed
    result["_docs"] = {
        "rankings": json.loads((out / "rankings.json").read_text(encoding="utf-8")),
        "tripwires": json.loads((out / "tripwire_baseline.json").read_text(encoding="utf-8")),
        "prior": json.loads((out / "scenario_prior.json").read_text(encoding="utf-8")),
    }
    return result


# ------------------------------------------------------------------ the plan's own bodies

def test_run_pipeline_emits_two_json_artifacts_with_identity_envelope(run):
    ranks = run["_docs"]["rankings"]
    assert ranks["schema"] == "demoflow.rankings.v1"
    assert "schema_version" in ranks and "assumptions_hash" in ranks
    assert "source_hashes" in ranks["data_vintage"]
    r0 = ranks["rankings"][0]
    assert isinstance(r0["geography"], str) and r0["rank"] == 1
    assert set(r0) == {"geography", "mean_ed_reference", "mean_ed_low", "mean_ed_high",
                       "rank", "rank_stable", "flags"}
    assert isinstance(r0["rank_stable"], bool)

    trip = run["_docs"]["tripwires"]
    assert trip["schema"] == "demoflow.tripwire_baseline.v1"
    assert trip["assumptions_hash"] == ranks["assumptions_hash"]
    assert {t["indicator"] for t in trip["indicators"]} == set(REQUIRED_INDICATORS)
    for t in trip["indicators"]:
        assert {"indicator", "current_value", "source", "as_of",
                "band_low", "band_high", "status"} <= set(t)


def test_the_supply_lookup_refuses_a_year_the_roll_forward_did_not_key():
    """The last silent-zero door on the model path, closed (this module's docstring claims ALL
    of them refuse; `listings.get(t, 0.0)` was the one that did not).

    UNREACHABLE THROUGH `_ed_series` BY CONSTRUCTION — the supply loop keys every year from the
    population frame's first through the ranking domain's last — so the rule is tested where it
    can be reached at all, which is the door itself. The sibling test below pins the WIRING; a
    rule tested only through a call site that cannot violate it is a check that cannot fail.

    THE DEFAULT WAS DEFLATING, which is what makes it worth a refusal rather than a comment: a
    missing year books supply as zero, excess demand rises, and the geography moves UP the
    ranking. Nothing downstream can tell that from a real shortage."""
    listings = {2030: 1234.5, 2031: 0.0}
    assert pipeline._listings_at(listings, 2030, ctx="MTL_RMR/reference") == 1234.5
    # a REAL zero is a measurement and must pass — the door refuses ABSENCE, never a zero value.
    assert pipeline._listings_at(listings, 2031, ctx="MTL_RMR/reference") == 0.0
    with pytest.raises(CalibrationError, match="2032"):
        pipeline._listings_at(listings, 2032, ctx="MTL_RMR/reference")


def test_the_ed_series_reads_supply_through_the_refusing_door():
    """The WIRING half. A source contract, and it is the honest instrument here: the defaulting
    lookup cannot be exercised through `_ed_series` on any real frame, so a behavioural test of
    the call site would be a test that cannot fail. STATED RESIDUAL, as the import-direction
    gate states its own: this reads one function's source text, so a defaulting read spelled
    some third way inside a helper it calls is not covered."""
    import inspect
    source = inspect.getsource(pipeline._ed_series)
    assert "_listings_at(" in source
    assert "listings.get(" not in source, "the silent-zero supply default is back"


def test_two_vintage_mixing_refused():
    """The plan called `refuse_cross_vintage({assumptions_hash()})` — a ONE-element set built
    from the hash computed on the line above, so the gate could not fire under ANY input
    (carry B4)."""
    with pytest.raises(CalibrationError):
        pipeline._refuse_mixed_identity({"identityA", "identityB"})
    with pytest.raises(CalibrationError):
        pipeline._refuse_mixed_identity(set())        # a run that recorded no identity at all


def test_the_run_identity_covers_the_data_vintage_the_assumptions_AND_THE_CLOCK(monkeypatch,
                                                                               tmp_path):
    """`assumptions_hash()` hashes the assumption SELECTION — four payload members since the
    round-3 audit (2026-08-22), the fourth being the anchor registry — and NOTHING about the
    data, so two runs over different source bytes produce an identical hash. The run's
    composition token covers both — and moving ANY of its three payload members moves it.

    The data leg moves REAL BYTES on a copy, not a declared digest: since review finding F1 the
    envelope hashes `data_dir` rather than transcribing a module constant, so a mutated
    `RUN_SOURCES` DIGEST no longer moves anything (and a mutated PINNED file refuses outright).
    A re-serialization of a derived artifact is the honest probe — identical semantics,
    different bytes — and it is the bytes the envelope claims to identify.

    THAT SENTENCE SAID "a mutated `RUN_SOURCES` record" AND WAS FALSE (corrected 2026-08-22): F1
    moved the DIGEST off disk and left the OTHER half of every record transcribed. `_source_hashes`
    still emits `extracted_at` straight off `source.extracted_at`, so a record edit moves
    `data_vintage` AND THIS token — measured, `extracted_at="2099-01-01"` moves both. It does NOT
    move the EMITTED `run_pairing`: amendment #22(C) took that field off this payload, and a
    declared-provenance edit moves no emitted number, so both documents' payloads stay
    byte-identical and the pairing token does not re-mint (measured 2026-08-23). The
    distinction is the whole point of the leg it is written next to, so it is now asserted rather
    than described: a claim that a mutation "no longer moves anything" is a coverage claim, and a
    coverage claim nothing evaluates is how this file's own record says these sentences rot.

    THE CLOCK LEG IS WHAT MAKES THIS THE RUN'S IDENTITY RATHER THAN ITS INPUTS' — two runs of
    identical data and identical assumptions at different clocks are different runs, and the
    composition gate is asked whether the RUN's declared identity held still. It was admitted by
    spec amendment #20(C)(3) to make this the EMITTED pairing token; amendment #22(C) retired that
    payload (nothing in it is output content or code identity, so a computation change emitted
    different documents under the same token) and the emitted field is now
    `artifacts.pairing_token` over both payloads. The clock leg stays HERE, where the question is
    about inputs sampled twice and no output content is required. Asserted DIRECTLY on the
    function rather than through a golden, which would only re-ratify whatever the emitter emits.

    AND IT IS DETERMINISTIC, not a nonce — pinned in the same body, because a random token would
    move the emitted bytes on every run and destroy the byte-stability the goldens rest on."""
    now = (2026, 12)
    base = pipeline._run_identity(_DATA, None, now)
    assert pipeline._run_identity(_DATA, None, now) == base        # deterministic, not a nonce
    assert pipeline._run_identity(_DATA, None, (2026, 11)) != base  # the MONTH moves it
    assert pipeline._run_identity(_DATA, None, (2027, 12)) != base  # so does the YEAR
    moved = _data_copy(tmp_path / "moved")
    artifact = moved / LIVING_ARRANGEMENT_ARTIFACT
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    artifact.write_text(json.dumps(payload, indent=4, sort_keys=True) + "\n", encoding="utf-8")
    assert pipeline._run_identity(moved, None, now) != base        # data moved
    monkeypatch.setattr(pipeline, "assumptions_hash", lambda: "0" * 16)
    assert pipeline._run_identity(_DATA, None, now) != base        # assumptions moved
    monkeypatch.undo()

    # THE DECLARED HALF OF A `RUN_SOURCES` RECORD STILL RIDES THE ENVELOPE. `extracted_at` is
    # DECLARED PROVENANCE — read off the record, never off disk — so it is exactly the field the
    # docstring's corrected sentence is about, and `data_vintage` and the COMPOSITION token must
    # both see it move. The EMITTED `run_pairing` must not and does not (amendment #22(C)): it
    # digests the two documents' payloads, and a declared-provenance edit moves no emitted number.
    #
    # EVERY `_Source` RECORD, NOT THE FIRST ONE. `_source_hashes` builds the entry in TWO
    # branches — the raw-anchor key takes its own — and the first key in sort order
    # (`census_tenure_age_98100231.csv`) is exactly the raw-anchor one, so a one-record probe
    # covers one branch and calls it coverage. Measured: hardcoding `extracted_at` in the
    # NON-anchor branch alone left a one-record version of this leg GREEN.
    vintage_before = pipeline._source_hashes(_DATA, None)
    declared = [n for n, s in sorted(pipeline.RUN_SOURCES.items())
                if isinstance(s, pipeline._Source)]
    assert len(declared) > 1, "only one declared file source — this loop would cover one branch"
    for name in declared:
        monkeypatch.setitem(pipeline.RUN_SOURCES, name,
                            dataclasses.replace(pipeline.RUN_SOURCES[name],
                                                extracted_at="2099-01-01"))
        assert pipeline._source_hashes(_DATA, None) != vintage_before, (
            f"a mutated `extracted_at` on RUN_SOURCES[{name!r}] left `data_vintage` "
            "byte-identical — declared provenance IS emitted, so it cannot sit outside the "
            "envelope, and this key's branch of `_source_hashes` is not carrying it")
        assert pipeline._run_identity(_DATA, None, now) != base, (
            f"a mutated `extracted_at` on RUN_SOURCES[{name!r}] left the COMPOSITION token "
            "unchanged — `_run_identity` hashes the source map, so a moved declaration must "
            "re-mint it (this is NOT the emitted `run_pairing`, which amendment #22(C) computes "
            "from both documents' payloads and which a provenance-only edit leaves alone)")
        monkeypatch.undo()


def test_an_identity_that_moves_mid_run_is_refused(monkeypatch, tmp_path):
    """The RED the plan's one-element set could never reach: a run whose declared identity
    changes WHILE its numbers are being computed publishes rows from two identities under one
    envelope. Sampling once cannot see it; sampling around the computation can."""
    seen = iter(["identity-before", "identity-after"])
    monkeypatch.setattr(pipeline, "_run_identity", lambda *a, **k: next(seen))
    with pytest.raises(CalibrationError, match="single-vintage"):
        run_pipeline(data_dir=_DATA, out_dir=tmp_path, now_year=2026, sweep_axes=_NO_SWEEP)
    assert not (tmp_path / "rankings.json").exists()


# ------------------------------------------------------- B5 / B5b / B6: the identity envelope

def test_the_envelope_covers_every_input_the_run_reads(run):
    """Carry B5b. `ALLOWED_SOURCE_KEYS` declared THREE of the tree's thirteen committed
    inputs and every population and immigrant-flow workbook was uncovered — for those the
    envelope could not make the data-vs-code call it exists to make."""
    emitted = set(run["_docs"]["rankings"]["data_vintage"]["source_hashes"])
    assert emitted == set(RUN_SOURCES) | set(RUN_ARTIFACTS) | {BASIS_SOURCE_KEY}
    # ...and the CPM mortality basis, which is not a file under `data_dir` at all (data-gate
    # finding F1): every q value the supply side rides on comes off it, and until run 33 two
    # runs over DIFFERENT upstream tables emitted different bytes under an IDENTICAL envelope.
    assert BASIS_SOURCE_KEY not in set(RUN_SOURCES) | set(RUN_ARTIFACTS)
    assert not (_DATA / BASIS_SOURCE_KEY).exists()
    # the five modelling inputs the plan's envelope missed entirely
    assert {"pop-as-rmr-base.xlsx", "pop-as-ra-base.xlsx", "compo-rmr-base.xlsx",
            "compo-ra-base.xlsx", "hors_aligned_csd_98100232.json"} <= emitted
    # ...and the four DERIVED artifacts every rate in the model is actually read from, which
    # the landed body covered only by naming their upstream sources (review finding F1).
    assert set(RUN_ARTIFACTS) == DERIVED_ARTIFACT_KEYS
    assert DERIVED_ARTIFACT_KEYS <= emitted
    assert emitted <= SOURCE_KEY_REGISTRY
    assert run["_docs"]["tripwires"]["data_vintage"] == \
        run["_docs"]["rankings"]["data_vintage"]


def test_a_derived_artifacts_own_bytes_ride_the_envelope(tmp_path):
    """REVIEW FINDING F1, and carry B5b read literally: EVERY rate in the model is read from
    one of four DERIVED artifacts, and the landed body named their upstream SOURCES instead —
    on the argument that each artifact refuses at load if its recorded source digests drift
    from the pins. That argument is FALSE in the payload direction, which is the direction the
    model's numbers live in: editing one rate cell and leaving `_provenance` untouched loads
    clean and moves every geography's ED under a byte-identical envelope, so §9's
    data-vs-code attribution could not be made for the inputs that drive the whole run.

    THE PROBE AGE IS DERIVED FROM THE MUTATED BAND, NEVER HARDCODED (operator ruling W,
    2026-08-20, and the re-derivation is the finding). This body mutates `next(iter(...))` — "the
    first band" — and the age it then probes used to be the literal 40. That pairing was green
    only by COINCIDENCE: the retired first band was `25-54`, which CONTAINED 40. Ruling W refined
    the ownership lattice to seven bands, so the first band is now `25-34`, 40 resolves to
    `35-44`, and the mutated cell stopped being read at all — the guard went VACUOUS and red in
    one step, which is the only reason the vacuity was visible. Re-pinning the literal to 30
    would rebuild the same coincidence one refinement later, so the age is RESOLVED from the
    chosen band's own `lo` and the resolution is asserted rather than assumed. The claim being
    guarded is unchanged and stays non-vacuous: an edited rate cell loads clean and moves the
    model."""
    from demoflow.loaders.census import _AGE_BANDS, load_ownership_rates, ownership_rate

    edited = _data_copy(tmp_path / "edited")
    artifact = edited / OWNERSHIP_ARTIFACT
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    band = next(iter(payload["rates"][Geography.MTL_RMR.value]))
    band_lo = {label: lo for label, lo, _hi in _AGE_BANDS}
    assert band in band_lo, (
        f"the first key of the rate row is {band!r}, which is not a band label — the probe age "
        f"below is derived from the mutated band and cannot be resolved (lattice: "
        f"{sorted(band_lo)})")
    payload["rates"][Geography.MTL_RMR.value][band] += 0.05        # a valid fraction, still
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pristine = pipeline._source_hashes(_DATA, ircc=None)
    moved = pipeline._source_hashes(edited, ircc=None)
    assert OWNERSHIP_ARTIFACT in pristine, "the envelope does not cover the derived rate artifacts"
    assert pristine[OWNERSHIP_ARTIFACT]["sha256"] != moved[OWNERSHIP_ARTIFACT]["sha256"]
    assert pipeline._run_identity(edited, None, _NOW) != pipeline._run_identity(_DATA, None, _NOW)
    # the edit really does move the model, which is why the envelope must be able to see it —
    # read at the mutated band's OWN lower edge, so the read cannot drift off the written cell
    assert ownership_rate(load_ownership_rates(data_dir=edited),
                          Geography.MTL_RMR, band_lo[band]) != \
        ownership_rate(load_ownership_rates(data_dir=_DATA), Geography.MTL_RMR, band_lo[band])


def test_a_moved_mortality_basis_moves_the_envelope_and_the_identity(monkeypatch):
    """DATA-GATE FINDING F1: the CPM basis is the sole source of every q value the supply side
    rides on, and it was OUTSIDE the envelope entirely — so the answer to "can two runs over
    different upstream bytes emit the same artifact identity?" was YES.

    The swap is the data gate's own prescription (`_BASE_TABLES` re-pointed at the package's
    `cpm2014_public_*` pair, the shape of actuarial-system re-publishing the combined tables).
    Both halves are asserted, because only the PAIR is the fix: the envelope MOVES (so the red
    is attributable to DATA) and `assumptions_hash` does NOT (so it is not mis-attributed to
    the assumption selection). The digest is taken through the §2-sanctioned public surface —
    `mortality._DATA_DIR` is a private reach-in the spec forbids the model path.
    """
    from actuarial import compat as mortality

    before = pipeline._source_hashes(_DATA, ircc=None)
    identity_before = pipeline._run_identity(_DATA, None, _NOW)
    assumptions_before = assumptions_hash()

    monkeypatch.setattr(mortality, "_base_cache", {})          # else the loaded arrays answer
    monkeypatch.setitem(mortality._BASE_TABLES, "CPM2014_combined",
                        ("cpm2014_public_male.csv", "cpm2014_public_female.csv", 2014))
    after = pipeline._source_hashes(_DATA, ircc=None)

    assert before[BASIS_SOURCE_KEY]["sha256"] != after[BASIS_SOURCE_KEY]["sha256"]
    assert {k: v for k, v in before.items() if k != BASIS_SOURCE_KEY} == \
        {k: v for k, v in after.items() if k != BASIS_SOURCE_KEY}, \
        "the basis swap moved a FILE digest — the probe is not isolating what it claims"
    assert pipeline._run_identity(_DATA, None, _NOW) != identity_before
    assert assumptions_hash() == assumptions_before, (
        "a moved mortality TABLE is a data move, not an assumption-selection move — "
        "attributing it to `assumptions_hash` would send the reader to the wrong ledger")


def test_the_basis_entry_publishes_a_declared_recording_date(run):
    """`extracted_at` for the basis is DECLARED, not stamped: the dependency is a uv path dep
    that publishes no pull date through any public surface, so the entry records the date its
    q surface was measured into this envelope and says so at its declaration. Bound to that ONE
    declaration site rather than re-typed here, so a second copy cannot drift into existence;
    `tests/test_basis_guard.py` holds the other half — the digest the date describes."""
    entry = run["_docs"]["rankings"]["data_vintage"]["source_hashes"][BASIS_SOURCE_KEY]
    assert entry["extracted_at"] == pipeline.BASIS_RECORDED_AT
    assert len(entry["sha256"]) == 64


def test_the_basis_digest_grid_covers_the_q_surface_the_run_actually_reads(run):
    """THE COVERAGE CLAIM, MEASURED RATHER THAN RE-TYPED. `cohort/basis.py` declares
    `BASIS_DIGEST_*` a superset of what the model consumes, and UNDER-covering is the failure
    that matters: a re-published table moving a q value outside the grid ships a moved basis
    under a BYTE-IDENTICAL envelope, which is the finding the digest exists to close.

    `tests/test_basis_guard.py` binds the AGE axis to the model's own constants (`ROLL_AGE`,
    `BAND_ENTRY_AGE`, the reconciliation cohort's decade) and can do it without I/O. THE YEAR
    AXIS HAS NO SUCH CONSTANT: the supply roll spans `range(base_year, last projected year+1)`
    off the ISQ population frame, so a unit-level assertion there can only re-type the grid's
    own literal — it fires when the GRID narrows and stays green when CONSUMPTION widens past
    it, which is the direction that actually ships the defect. Recording the real run closes
    both directions on all three axes, and catches what a data-side binding still could not:
    a NEW q call site in `pipeline.py` at an age or year outside the grid.

    MEASURED on this vintage: 80 distinct lookups, ages 75-84, years 2021-2051. The age axis
    carries 16 ages of slack; the YEAR axis carries NONE — consumption is exactly the grid, so
    the first ISQ vintage that extends the lattice under-covers immediately.

    SCOPE: the recorder patches `pipeline.q_at`, today's only consumer under `src/`. A future
    module importing `cohort.basis.q_at` directly would read a surface this test cannot see.
    """
    grid = {(age, gender, year) for age in BASIS_DIGEST_AGES
            for gender in BASIS_DIGEST_GENDERS for year in BASIS_DIGEST_YEARS}
    consumed = run["_q_consumption"]

    # NON-VACUITY FIRST: a recorder that captured nothing — or lost an axis — passes the subset
    # assertion trivially. Bound to the constants the guard test already binds, not new literals.
    _geo, _scen, recon_start, recon_age = RECONCILIATION_COHORT
    ages = {age for age, _, _ in consumed}
    years = {year for _, _, year in consumed}
    assert {gender for _, gender, _ in consumed} == {"M", "F"}
    assert pipeline.ROLL_AGE in ages
    assert set(range(recon_age, recon_age + 10)) <= ages
    assert set(range(recon_start, recon_start + 10)) <= years

    assert consumed <= grid, (
        f"the run reads q OUTSIDE the digested grid at {sorted(consumed - grid)[:8]} — the "
        f"basis digest is blind there, so a re-published table that moves those cells ships "
        f"under a byte-identical envelope. Widen `cohort/basis.BASIS_DIGEST_*` to cover them, "
        f"then re-mint the golden and `_BASIS_DIGEST_AT_DECLARATION` in the same commit")


def test_a_derived_artifacts_extraction_date_is_read_off_its_own_provenance(run):
    """Carry B6 for the four artifacts: their dates are not declared in this module at all —
    they are read from the bytes being hashed, so the two sites cannot drift because there is
    only one."""
    hashes = run["_docs"]["rankings"]["data_vintage"]["source_hashes"]
    for name in RUN_ARTIFACTS:
        recorded = json.loads((_DATA / name).read_text(encoding="utf-8"))["_provenance"]
        assert hashes[name]["extracted_at"] == recorded["extracted_at"]


def test_an_artifact_with_no_recorded_extraction_date_is_refused(tmp_path):
    """The absence half of the line above: a derived artifact that records no extraction date
    cannot have one invented for it (the plan stamped `"2026-07-21"` on every source), so the
    envelope refuses and names the file."""
    gutted = _data_copy(tmp_path / "gutted")
    artifact = gutted / OWNERSHIP_ARTIFACT
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["_provenance"].pop("extracted_at")
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(LoaderError, match=OWNERSHIP_ARTIFACT):
        pipeline._source_hashes(gutted, ircc=None)


@pytest.mark.parametrize("name", [CENSUS_EXTRACT, "pop-as-rmr-base.xlsx"])
def test_a_declared_sources_bytes_are_hashed_off_disk_not_transcribed(tmp_path, name):
    """Review finding F1's other half. The landed body emitted `WORKBOOK_SHA256[name]` and
    `raw_anchor(name)` — MODULE CONSTANTS — without ever hashing `data_dir`, so a declared
    source could be REPLACED and the envelope would publish its pin unchanged. The census
    extract is the sharpest case: no runtime path opens it, so nothing else refuses either and
    the whole run completed on a garbage extract."""
    drifted = _data_copy(tmp_path / "drifted")
    (drifted / name).write_bytes(b"garbage")
    with pytest.raises(LoaderError, match=name):
        pipeline._source_hashes(drifted, ircc=None)


def test_the_aligned_curves_own_source_is_covered(run):
    """Consuming the operand-aligned join (carry B3) adds a live model dependency; B5b names
    it in the same breath because a new input outside the envelope is a new blind spot."""
    hashes = run["_docs"]["rankings"]["data_vintage"]["source_hashes"]
    assert hashes["hors_aligned_csd_98100232.json"]["sha256"] == \
        WORKBOOK_SHA256["hors_aligned_csd_98100232.json"]


def test_a_declared_source_with_no_record_is_refused(monkeypatch):
    """Carry B5, the undeclared half."""
    monkeypatch.setitem(pipeline.RUN_SOURCES, "compo-rmr-base.xlsx", None)
    with pytest.raises(LoaderError, match="compo-rmr-base.xlsx"):
        pipeline._source_hashes(_DATA, ircc=None)


def test_an_absent_input_is_refused_not_filtered_out(tmp_path):
    """Carry B5, the ABSENCE half — the actual shape the plan shipped:
    `for name in ALLOWED_SOURCE_KEYS if (dd / name).exists()`. A missing input dropped silently
    out of the vintage and the artifact went out looking fully provenanced. An empty listing is
    data, never proof."""
    for name in ("pop-as-rmr-base.xlsx", "compo-rmr-base.xlsx"):
        (tmp_path / name).write_bytes((_DATA / name).read_bytes())
    with pytest.raises(LoaderError, match="census_tenure_age_98100231.csv"):
        pipeline._source_hashes(tmp_path, ircc=None)


def test_extracted_at_is_declared_provenance_never_one_stamped_literal(run):
    """Carry B6: the plan stamped `"extracted_at": "2026-07-21"` on EVERY source hash. The
    derived surfaces carry their OWN extraction dates and they are NOT all the same day."""
    hashes = run["_docs"]["rankings"]["data_vintage"]["source_hashes"]
    assert hashes["living_arrangement_98100134.json"]["extracted_at"] == "2026-08-08"
    assert hashes["hors_aligned_csd_98100232.json"]["extracted_at"] == "2026-08-15"
    assert hashes["pop-as-rmr-base.xlsx"]["extracted_at"] == "2026-07-21"
    assert len({v["extracted_at"] for v in hashes.values()}) > 1


@pytest.mark.parametrize("artifact,source", [
    ("living_arrangement.json", "living_arrangement_98100134.json"),
    ("ownership_hors_aligned.json", "hors_aligned_csd_98100232.json"),
    ("ownership_by_geo_age.json", "census_tenure_age_98100231.csv"),
    ("headship_by_age.json", "pop-as-qc-base.xlsx"),
])
def test_declared_extraction_dates_are_bound_to_the_artifacts_own_provenance(artifact, source):
    """`RUN_SOURCES` declares a date the derived artifacts ALSO record, so the two sites can
    drift. This is the gate that makes them one statement rather than two copies — the same
    discipline `constants.py` states for its own dict ("a second declaration site is a
    defect") applied where a second site is unavoidable."""
    provenance = json.loads((_DATA / artifact).read_text(encoding="utf-8"))["_provenance"]
    assert RUN_SOURCES[source].extracted_at == provenance["extracted_at"]


def test_the_census_extract_rides_its_raw_response_digest(run):
    """spec §7 defines the value as the sha256 of the RAW RESPONSE; the committed extract sits
    one link down pins.py's chain, so the raw anchor is what the envelope must publish."""
    hashes = run["_docs"]["rankings"]["data_vintage"]["source_hashes"]
    name = "census_tenure_age_98100231.csv"
    assert hashes[name]["sha256"] == raw_anchor(name)
    assert hashes[name]["sha256"] != WORKBOOK_SHA256[name]


# ------------------------------------------------------------- B1 / B7: the tripwire gate

def test_no_tripwire_value_is_a_hardcoded_literal(run, monkeypatch):
    """THE HEADLINE (carry B1). The plan fed `pr_landings_annual` a hardcoded 45000.0 sitting
    inside its own 40000-50000 band — a constant compared against a constant, green forever,
    on any data, in any era — and fed `natural_increase_sign` a fabricated -1200.0 and
    `cmhc_senior_sale_5yr` the model's OWN anchor. Every indicator now carries a MEASURED
    value or NULL, and this test binds the MECHANISM as well as the outcome: the only
    indicator the pipeline may hand a value to is the one whose value is computed from a feed."""
    records = run["_docs"]["tripwires"]["indicators"]
    assert {r["status"] for r in records} == {Status.UNKNOWN.value}
    assert all(r["current_value"] is None and r["as_of"] is None for r in records)

    handed = {}
    real = pipeline._evaluate_declared

    def spy(indicator, value, *, available, now):
        handed[indicator] = (value, available)
        return real(indicator, value, available=available, now=now)

    monkeypatch.setattr(pipeline, "_evaluate_declared", spy)
    pipeline._tripwire_results(pipeline.load_pr_landings(data_dir=_DATA), now=(2026, 12))
    # `pr_landings_annual` never passes through `_evaluate_declared` at all: its value comes
    # from `evaluate_pr_landings`, which measures it. Everything else is handed NOTHING.
    assert PR_LANDINGS_INDICATOR not in handed
    assert set(handed) == set(REQUIRED_INDICATORS) - {PR_LANDINGS_INDICATOR}
    assert all(value is None for value, _available in handed.values()), (
        f"a tripwire value was typed into the pipeline rather than measured: {handed}")


def test_pr_landings_goes_through_the_wired_evaluator(monkeypatch):
    """`evaluate_pr_landings` carries the measured-realized path, the plan-era gate, the
    degenerate-feed floor, the freshness gate and ruling U's member-set completeness contract.
    The plan's literal bypassed ALL of them."""
    seen = {}
    real = pipeline.evaluate_pr_landings

    def spy(landings, **kwargs):
        seen.update(kwargs)
        seen["landings"] = landings
        return real(landings, **kwargs)

    monkeypatch.setattr(pipeline, "evaluate_pr_landings", spy)
    results, _log = pipeline._tripwire_results(pipeline.load_pr_landings(data_dir=_DATA), now=(2026, 12))
    assert seen, "the pipeline never called evaluate_pr_landings"
    assert seen["band"] == pipeline.TRIPWIRE_BANDS[PR_LANDINGS_INDICATOR]
    assert seen["now"] == (2026, 12)
    assert {r.indicator for r in results} == set(REQUIRED_INDICATORS)
    # CALLING it is not enough — the plan could call it and then emit something else. The
    # evaluator's `result` is the ONLY thing that may reach the artifact (`PRLandingsEvaluation`
    # says so), so the emitted record must BE that object.
    emitted = next(r for r in results if r.indicator == PR_LANDINGS_INDICATOR)
    expected = real(seen["landings"], band=seen["band"], now=seen["now"],
                    freshness_years=seen["freshness_years"]).result
    assert emitted == expected


def test_the_committed_tree_has_no_closed_plan_year_and_says_so(run):
    """Live state today: the IRCC feed is not committed, so no plan-governed year has closed.
    UNKNOWN / source_unavailable / exit 1 is the CORRECT answer and the pipeline must be able
    to emit it rather than route around it."""
    assert not (_DATA / IRCC_CSV_NAME).exists()
    record = next(r for r in run["_docs"]["tripwires"]["indicators"]
                  if r["indicator"] == PR_LANDINGS_INDICATOR)
    assert record["status"] == Status.UNKNOWN.value
    assert record["reason"] == Reason.SOURCE_UNAVAILABLE.value
    assert record["current_value"] is None and record["as_of"] is None
    assert run["exit_code"] == 1


def test_an_unruled_band_can_never_report_within_band():
    """Carry B7. `[0, 1e9]` and `[-1e9, 1e9]` are decorative greens in a fail-safe gate —
    `natural_increase_sign` was fed a live -1200.0 against [-1e9, 1e9] and reported OK forever
    BY CONSTRUCTION. A band is a RULED value; where none exists the placeholder is DEGENERATE,
    which admits no value as OK (`v <= lo or v >= hi` is true for every v when lo == hi)."""
    lo, hi = UNRULED_BAND
    assert lo == hi
    for indicator in ("temp_resident_stock", "registre_foncier_volume", "natural_increase_sign"):
        assert pipeline.TRIPWIRE_BANDS[indicator] == UNRULED_BAND


def test_an_unruled_band_refuses_to_judge_a_real_measurement():
    """The placeholder is fail-safe only while nothing is compared against it. The day a feed
    lands for one of these indicators, the run REFUSES until a band is ruled — a gate that
    fires exactly when the question becomes real."""
    with pytest.raises(CalibrationError, match="no ruled band"):
        pipeline._evaluate_declared("natural_increase_sign", 1234.0, available=True, now=2026)


def test_run_exit_code_is_the_coverage_gate(run):
    """Carry B2. `exit_code` ranges only over the results it is HANDED — one OK result exits 0,
    however short of the required set. `run_exit_code` requires the evaluated multiset to EQUAL
    the code-owned required set, and this is where it gets its first production consumer."""
    assert "exit_code" not in vars(pipeline), (
        "the pipeline imported `exit_code` — the gate that cannot ask the coverage question")
    from demoflow.output.tripwires import TripwireResult, exit_code
    one_ok = [TripwireResult(PR_LANDINGS_INDICATOR, 45000.0,
                             "IRCC PR admissions by CMA (open.canada.ca monthly CSV)",
                             2026, 40000.0, 50000.0, Status.OK)]
    assert exit_code(one_ok) == 0            # the gate the plan used
    assert pipeline.run_exit_code(one_ok) == 1   # the gate that asks the coverage question
    assert run["exit_code"] == pipeline.run_exit_code(run["tripwires"])


def test_the_run_calls_run_exit_code_not_the_verdict_only_gate(monkeypatch, tmp_path):
    """The behavioural contrast above cannot see the substitution ON THE COMMITTED TREE: all
    six required indicators are present and all six are UNKNOWN, so `exit_code` and
    `run_exit_code` BOTH return 1 and agree. Measured — a mutant swapping one for the other
    passed. The coverage gate's use is therefore bound structurally."""
    called = []
    real = pipeline.run_exit_code
    monkeypatch.setattr(pipeline, "run_exit_code",
                        lambda results: (called.append(len(results)), real(results))[1])
    pipeline.run_pipeline(data_dir=_DATA, out_dir=tmp_path, now_year=2026,
                          sweep_axes=_NO_SWEEP)
    assert called == [len(REQUIRED_INDICATORS)]


# --------------------------------------------------- B3: the operand-aligned ownership join

def test_hors_rmr_reads_the_operand_aligned_curve_and_the_others_do_not(run):
    """Carry B3. Nothing under `src/` imported `hors_aligned` before this task, so ED was still
    computed from the operand-MISALIGNED rates that spec §6 amendment #12(B) was reversed to
    fix. The join is CONSUMED — not re-derived by a hardcoded geography test."""
    read = pipeline._ownership_reader(_DATA)
    assert read.reads_aligned(Geography.HORS_RMR) is True
    for geo in Geography:
        if geo is not Geography.HORS_RMR:
            assert read.reads_aligned(geo) is False
    from demoflow.loaders.census import load_ownership_rates, ownership_rate
    shipped = ownership_rate(load_ownership_rates(data_dir=_DATA), Geography.HORS_RMR, 40)
    assert read(Geography.HORS_RMR, 40) != shipped


def test_the_published_ed_is_computed_from_the_aligned_curve_and_never_the_shipped_one(
        monkeypatch):
    """The test above pins the READER's routing; this one pins that the ED the run PUBLISHES is
    the number the aligned curve produces. The pair is the B8 idiom — a value test and its
    consumption twin — and it is needed for the same measured reason: a mutant reading
    `ownership_rate(load_ownership_rates(), geo, a)` directly inside `_ed_series`, bypassing the
    reader on the DEMAND side, left the routing test GREEN (the reader object still answers
    correctly) and the whole suite green, while moving HORS_RMR's mean ED from -0.00029045 to
    -0.00042867 — carry B3's exact named defect restored, and the join back to decoration. THAT
    MUTATION MEASUREMENT IS PRE-RULING-V: its baseline is the retired band-curve golden, on which
    HORS_RMR was rank 1. On the resolved curve HORS_RMR is rank 4 at +0.0011023443 and rank 1 is
    LANAUDIERE_RA14_PROXY, so the delta stands as the dated reason this test exists and not as a
    reading of the committed vintage.

    THE PROVENANCE LEG IS WHAT KILLS THAT MUTANT, and the value legs alone measurably do NOT:
    the bypass was PARTIAL — `_standing_stock` and `_band_entry_stock` still read through the
    reader — so the series computed with a shipped-forced reader still differed from the
    published one and every `!=` leg stayed green (measured: 52/52 under the mutant). A
    geography the join sends to the aligned curve must never read the shipped curve AT ALL, at
    any point in the function, which is the property carry B3 actually names. Both legs are
    kept: the provenance leg catches a bypass anywhere on the path, the value legs catch a
    consumer that reads the right curve and computes the wrong number from it.
    """
    from demoflow.loaders.hors_aligned import aligned_ownership_rate, aligned_ownership_union

    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    def series(geo, read_ownership):
        return pipeline._ed_series(geo, Scenario.REFERENCE, frames, read_ownership,
                                   pipeline.CENTRAL_LEG)

    class AlignedOnly:
        """Every ownership read answered from the aligned curve, with NO join consulted — the
        point of this arm is that it cannot route. Since operator ruling X2 the ED path asks the
        reader two questions (a rate AT an age, and the aggregate OVER `P_NONIMM_RANGE`), so
        this arm answers both from the aligned surface; a bare `lambda geo, age` would now
        AttributeError on the second and stop testing the first."""

        def __call__(self, geo, age):
            return aligned_ownership_rate(read.aligned, geo, age)

        def p_nonimm(self, geo):
            return aligned_ownership_union(*pipeline.P_NONIMM_RANGE, data_dir=_DATA)

    # --- value: the published series IS the aligned curve's, and the choice moves the number.
    # The shipped-forced reader is built on a REPLICA join, never the committed one, whose
    # loader refuses a second aligned row (`hors_aligned._verify_join`'s scope fence).
    replica = {geo: dict(row) for geo, row in read.join.items()}
    replica[Geography.HORS_RMR.value]["reads"] = "shipped"
    published = series(Geography.HORS_RMR, read)
    aligned_only = series(Geography.HORS_RMR, AlignedOnly())
    # THE WRONG-TERRITORY SPAN UNION HAS TO BE HANDED BACK EXPLICITLY, because
    # `_ownership_reader` deliberately drops it (see its docstring): every row the join sends to
    # the aligned curve loses its shipped `P_NONIMM_RANGE` union, so a routing drift REFUSES
    # instead of quietly serving the census-net territory. This arm wants the misaligned number
    # measured rather than refused, so it opts in — and the opt-in being visible HERE is the
    # point: no production path can reach this value, and one line of test code is what it costs
    # to reach it deliberately.
    misaligned_union = dict(read.shipped_union)
    misaligned_union[Geography.HORS_RMR.value] = ownership_union_rates(
        *pipeline.P_NONIMM_RANGE, data_dir=_DATA)[Geography.HORS_RMR.value]
    assert Geography.HORS_RMR.value not in read.shipped_union, (
        "the census-net span union is reachable on the shipped route again — a join re-point "
        "would serve HORS_RMR a rate measured over the wrong territory")
    misaligned = series(Geography.HORS_RMR,
                        pipeline._OwnershipReader(read.shipped, read.aligned, replica,
                                                  misaligned_union, read.aligned_union))
    assert published == aligned_only    # the curve HORS_RMR's ED is actually computed FROM
    assert published != misaligned      # ... and the choice is material, not cosmetic

    # --- provenance: which curve each geography's ED READS, over the whole function.
    curves = []
    real_aligned, real_shipped = pipeline.aligned_ownership_rate, pipeline.ownership_rate
    monkeypatch.setattr(pipeline, "aligned_ownership_rate",
                        lambda *a: (curves.append("aligned"), real_aligned(*a))[1])
    monkeypatch.setattr(pipeline, "ownership_rate",
                        lambda *a: (curves.append("shipped"), real_shipped(*a))[1])

    series(Geography.HORS_RMR, read)
    assert set(curves) == {"aligned"}, f"HORS_RMR's ED read the shipped curve: {set(curves)}"
    curves.clear()
    series(Geography.MTL_RMR, read)
    assert set(curves) == {"shipped"}, f"MTL_RMR's ED read the aligned curve: {set(curves)}"


def test_the_join_drives_the_choice_not_a_hardcoded_geography():
    """A geography test in the pipeline would be a THIRD statement of a scope fence the
    artifact already carries and `hors_aligned._verify_join` already validates. Re-point the
    join and the reader FOLLOWS it (or refuses) — it never quietly disagrees with the artifact.

    The re-pointing is done on a REPLICA join here, never on the committed one: the artifact's
    own loader would refuse a second aligned row (`_verify_join`'s scope fence), which is
    exactly why the pipeline must not carry an independent copy of that rule."""
    read = pipeline._ownership_reader(_DATA)
    assert set(read.join) == {g.value for g in Geography}
    assert read.join[Geography.HORS_RMR.value]["reads"] == "operand_aligned"

    swapped = {geo: dict(row) for geo, row in read.join.items()}
    swapped[Geography.HORS_RMR.value]["reads"] = "shipped"
    follower = pipeline._OwnershipReader(read.shipped, read.aligned, swapped)
    assert follower.reads_aligned(Geography.HORS_RMR) is False

    gutted = {geo: dict(row) for geo, row in read.join.items()}
    gutted.pop(Geography.QC_RMR.value)
    with pytest.raises(LoaderError, match="QC_RMR"):
        pipeline._OwnershipReader(read.shipped, read.aligned, gutted)(Geography.QC_RMR, 40)


# ------------------------------------------------------ B10: borrowed_prior from provenance

def test_borrowed_prior_is_derived_from_input_provenance_not_a_geography_set(run):
    """Carry B10. The plan marked `RA_PROXY_MEMBERS | {HORS_RMR}` borrowed — two flags for one
    fact on the RA rows, and a WRONG one on HORS_RMR, whose join-table provenance is
    `computed_residual` (nothing was borrowed). `borrowed_prior` answers "were this geography's
    INPUTS borrowed from a coarser prior?", which `ImmigrantInputs` already answers PER FIELD."""
    flags = {r["geography"]: set(r["flags"]) for r in run["_docs"]["rankings"]["rankings"]}
    for geo in RA_PROXY_MEMBERS:
        assert "borrowed_prior" in flags[geo.value]
        assert "ra_proxy" in flags[geo.value]           # a DIFFERENT question, still answered
    assert "borrowed_prior" not in flags[Geography.HORS_RMR.value]
    assert "ra_proxy" not in flags[Geography.HORS_RMR.value]


def test_ruling_k_flag_rides_every_row_of_its_geography(run):
    """Ruling K is ALREADY wired in `rankings.py`; a pipeline change that stops the flag riding
    a LAVAL_RA13 row is a defect."""
    flags = {r["geography"]: set(r["flags"]) for r in run["_docs"]["rankings"]["rankings"]}
    for geo in CLOSED_COHORT_EXCEEDANCE_MEMBERS:
        assert "closed_cohort_exceedance" in flags[geo.value]
    for geo in Geography:
        if geo not in CLOSED_COHORT_EXCEEDANCE_MEMBERS and geo.value in flags:
            assert "closed_cohort_exceedance" not in flags[geo.value]


# ------------------------------------------------------------ ruling O: reconciliation scope

def test_the_central_run_invokes_the_reconciliation_gate(monkeypatch, tmp_path):
    """RULING O AS AN OBLIGATION FIRST. The plan's pipeline never imported or called
    `check_reconciliation` at all, so a carry phrased only as "don't let a sweep leg trip it"
    is satisfied by calling it NOWHERE — a gate that cannot fail, the class this task is full
    of. The CENTRAL-ASSUMPTION run MUST invoke it."""
    calls = []
    real = pipeline.check_reconciliation
    monkeypatch.setattr(pipeline, "check_reconciliation",
                        lambda retention: (calls.append(retention), real(retention))[1])
    run_pipeline(data_dir=_DATA, out_dir=tmp_path, now_year=2026, sweep_axes=_NO_SWEEP)
    assert len(calls) == 1, f"expected exactly one central-run call, got {len(calls)}"
    from demoflow.cohort.gates import RECONCILIATION_BAND
    lo, hi = RECONCILIATION_BAND
    assert lo <= calls[0] <= hi


def test_sweep_legs_never_re_run_the_reconciliation_gate(monkeypatch):
    """Ruling O's other half, and the measured reason: at q_live 0.06 — the sweep grid's OWN
    low endpoint — the spec-pinned cohort RAISES on the correct model while a doubled decrement
    PASSES, inverted at 21/21 start years. Binding every leg makes the spec self-contradictory.

    IT NOW COVERS FOURTEEN LEGS RATHER THAN TWO (run-33's five axes, ruling V's shape axis
    and amendment #20(D)'s collective-share axis)
    and the assertion is
    unchanged, which is the point: widening the sweep must not widen the gate's scope with it."""
    calls = []
    monkeypatch.setattr(pipeline, "check_reconciliation", lambda retention: calls.append(retention))
    lo, hi = SWEEP_GRID["q_live_per_year"]
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geos = [Geography.MTL_RMR, Geography.QC_RMR]
    central = pipeline._ed_dict(geos, frames, read, pipeline.CENTRAL_LEG)
    stable, rows_moved = pipeline._rank_stability(geos, frames, read, central)
    assert calls == [], "a sweep leg ran the central-run-only reconciliation gate"
    assert set(stable) == set(geos)
    # ...and the emitted per-leg map covers EXACTLY the declared legs (amendment #20(C)(2)):
    # a count for a leg that was not evaluated, or a leg with no count, is a published
    # measurement nothing made.
    assert set(rows_moved) == sweep_leg_labels()
    assert len(pipeline._sweep_legs()) == 14
    assert (lo, hi) == (0.06, 0.11)


def test_a_reconciliation_violating_central_run_refuses(monkeypatch, tmp_path):
    """The RED case ruling O requires. A zero-mortality basis is a real INPUT mutation (the
    decrement source), not a stubbed gate: retention rises to (1 - q_live)^10 = 0.4166, above
    the band's 0.40 upper edge, and the central run must refuse rather than ship."""
    monkeypatch.setattr(pipeline, "q_at", lambda age, gender, year: 0.0)
    with pytest.raises(CalibrationError, match="retention"):
        run_pipeline(data_dir=_DATA, out_dir=tmp_path, now_year=2026)
    assert not (tmp_path / "rankings.json").exists()


def test_the_reconciliation_cohort_is_the_spec_pinned_one():
    """Composition is a caller obligation `check_reconciliation` cannot verify (codex r9-F4):
    the band is well-defined only against the mix the INITIALIZATION EQUATIONS produce on the
    committed vintage for MTL_RMR. `tests/test_rollforward.py` discharged it with a private
    helper and recorded that Task 29's pipeline is where it folds — this is that fold."""
    assert RECONCILIATION_COHORT == (Geography.MTL_RMR, Scenario.REFERENCE, 2035, 75)


# -------------------------------------------------------------- the silent-zero doors

def test_a_missing_population_year_refuses_rather_than_scaling_by_one(run):
    """Carry B9. `_scale` fell through to `if p_isq > 0 else 1.0` for a year the frame does not
    contain — a SILENT scale of 1.0 where a refusal belongs."""
    frames = pipeline._load_all(_DATA)
    rows = frames.pop[(frames.pop["geography"] == Geography.MTL_RMR)
                      & (frames.pop["scenario"] == Scenario.REFERENCE)]
    with pytest.raises(LoaderError, match="1066"):
        pipeline._pop_by_age(rows, 1066, ctx="MTL_RMR/reference/1066")


def test_a_holed_age_lattice_refuses_rather_than_deflating_demand():
    """The deflating door: an empty or holed `resident_pop_t` yields D_native = 0.0 SILENTLY,
    because `native_formation`'s loop simply finds nothing to add. A missing population is not
    zero demand."""
    import pandas as pd
    holed = pd.DataFrame({"year": [2030] * 3, "age": [0, 1, 2], "sex": ["M"] * 3,
                          "population": [10.0, 10.0, 10.0]})
    with pytest.raises(LoaderError, match="age lattice"):
        pipeline._pop_by_age(holed, 2030, ctx="fixture")


def test_an_absent_arrival_flow_refuses(run):
    frames = pipeline._load_all(_DATA)
    rows = frames.compo[(frames.compo["geography"] == Geography.MTL_RMR)
                        & (frames.compo["scenario"] == Scenario.REFERENCE)]
    with pytest.raises(LoaderError, match="2051"):
        pipeline._arrival_flow(rows, 2051, ctx="MTL_RMR/reference")


# ------------------------------------------------------------------ the exits->cause mapping

def test_exit_causes_map_explicitly_to_listing_causes():
    """`rollforward` emits {estate, living}; `market_listings` takes {voluntary, estate} as its
    two arguments. The mapping is EXPLICIT and total in both directions — a positional hand-off
    would put the estate flow through the voluntary fraction with every number still plausible.

    THE IMAGE IS BOUND TO THE CONSUMER'S OWN PARAMETER NAMES, not to a per-cause accessor's
    vocabulary. It used to call `listings.phi_market(cause)` per mapped cause; that function is
    deleted (round-3 elegance audit, 2026-08-22 — zero non-test callers, and it read the FROZEN
    module constants), so the check that every mapped cause is one the consumer KNOWS is made
    against `market_listings`' signature, which is the surface the pipeline actually calls.
    """
    import inspect

    from demoflow.cohort.listings import market_listings

    assert EXIT_CAUSE_TO_LISTING_CAUSE == {"estate": "estate", "living": "voluntary"}
    params = inspect.signature(market_listings).parameters
    assert {f"{cause}_by_year" for cause in EXIT_CAUSE_TO_LISTING_CAUSE.values()} <= set(params), (
        f"`_split_exits` emits {sorted(EXIT_CAUSE_TO_LISTING_CAUSE.values())} and "
        f"`market_listings` takes {sorted(params)} — a mapped cause the supply term has no "
        "parameter for is a flow that silently leaves S")
    with pytest.raises(CalibrationError, match="exit cause"):
        pipeline._split_exits({"estate": 1.0, "moved_to_mars": 2.0}, ctx="fixture")


def test_arrival_flows_are_timed_off_the_interval_start(run):
    """`compo.YEAR_SEMANTICS` states the one fact a §6 consumer cannot get wrong: the row
    labeled t is the t -> t+1 bridge and lands in Population(t+1). The plan credited
    arrivals(t) into year t and subtracted them from P_ISQ(t) — mis-timing every cohort by one
    year, in the exact shape the loader constant was written to prevent."""
    assert pipeline._arrival_year(2030) == 2029
    assert FLOW_SPAN == (2025, 2050)
    # the flow span maps EXACTLY onto the projected stock lattice under the corrected timing
    frames = pipeline._load_all(_DATA)
    years = pipeline._projected_years(
        frames.pop[(frames.pop["geography"] == Geography.MTL_RMR)
                   & (frames.pop["scenario"] == Scenario.REFERENCE)])
    assert (pipeline._arrival_year(years[0]), pipeline._arrival_year(years[-1])) == FLOW_SPAN


# ===========================================================================================
# SPEC AMENDMENT #27 — THE LABELED-WINDOW IMPULSE. The test class that did not exist.
# ===========================================================================================
#
# WHY AN IMPULSE AND NOT A LEVEL PIN. `ED(t)` subtracted a supply flow over `[t, t+1)` from a
# demand flow over `(t-1, t]` for fifteen review rounds and 1,280 tests were green: every ED
# test either pinned an OUTPUT VALUE (which a re-minted golden re-ratifies along with the
# defect) or pinned one leg's labeling in isolation. A one-year offset is invisible to both. It
# is NOT invisible to a delta function: put a single arrival at one end of the domain and a
# single estate exit at the other, and the year each one SURFACES in the ED series is the
# convention, read directly, with no level to calibrate.
#
# THE TWO IMPULSES SIT AT THE FIRST AND FINAL PROJECTED YEARS on purpose — the domain
# boundaries are where a one-year shift either drops a year or reaches past the last one, which
# is #27's own fingerprint (the run read a listings year lying WHOLLY BEYOND the last modeled
# demand year while computing five it never read).
#
# WHAT IS MOCKED AND WHY IT IS STILL A REAL SEAM TEST. The demand LEVEL arithmetic, the native
# leg and the ED denominator are replaced by constants — each is pinned to death elsewhere and
# each would only add noise to a window oracle. What is NOT mocked is the line under test:
# `_ed_series` iterates the real projected lattice, keys the exits through the real
# `_exit_landing_year`, convolves the real estate lag through the real `market_listings`, and
# reads the real refusing door `_listings_at`. Reverting the translation to the identity — the
# shipped convention before #27 — moves the estate impulse one year early and REDS the table.
_IMPULSE_ARRIVALS = 1000.0          # persons, one cohort, one published flow interval
_IMPULSE_ESTATE = 400.0             # owner households, one roll window
_IMPULSE_OWNER_STOCK = 10_000.0     # flat denominator: the fixture is about years, not levels
_IMPULSE_LAG = 1                    # estate lag, so the exit's landing year is visible too


def test_a_SINGLE_arrival_and_a_SINGLE_estate_exit_surface_in_the_RULED_years(monkeypatch,
                                                                              frames):
    """Spec amendment #27's impulse oracle, with the expected table written out.

    The domain is the committed lattice: projected years 2026-2051, so the FIRST projected year
    is 2026 and the FINAL is 2051.

        ARRIVAL IMPULSE   one cohort in the published flow interval labeled 2025, i.e. the
                          window (2025, 2026].  `_arrival_year(2026) = 2025`, so it is credited
                          as immigrant demand at t = 2026 — the FIRST projected year — and
                          nowhere else.
        EXIT IMPULSE      one estate flow measured by the roll over [2049, 2050), i.e. the
                          window (2049, 2050].  `_exit_landing_year(2049) = 2050`, and the
                          estate lag L = 1 lists it at 2050 + 1 = 2051 — the FINAL projected
                          year — and nowhere else.

    THE EXPECTED TABLE (phi_voluntary and the eventual-listing fraction both 1.0, so S is the
    raw exit flow and every number below is exact):

        t       D_imm(t)   raw exits keyed(t)   S(t)      ED(t) = (D - S) / 10,000
        2026    1000.0     -                    0.0       +0.1
        2027..2050  0.0    -                    0.0        0.0
        2051    0.0        estate 400.0 @ 2050  400.0     -0.04

    Under the START-labeled convention this module shipped before #27, the same estate flow is
    keyed 2049, lists at 2050, and the table's last two rows read `ED(2050) = -0.04`,
    `ED(2051) = 0.0` — one year early, which is the whole defect, expressed as two cells.
    """
    geo, scen = Geography.MTL_RMR, Scenario.REFERENCE
    pop_g_s = frames.pop[(frames.pop["geography"] == geo)
                         & (frames.pop["scenario"] == scen)]
    years = pipeline._projected_years(pop_g_s)
    first, final = years[0], years[-1]
    assert (first, final) == (2026, 2051)          # the committed lattice, named not assumed

    arrival_interval = pipeline._arrival_year(first)          # 2025 — window (2025, 2026]
    # THE ROLL WINDOW IS CHOSEN FROM THE RULED ARITHMETIC, NOT FROM THE CODE UNDER TEST: the
    # end label of `[y, y+1)` is `y+1` and the estate lag adds L, so the flow that must reach
    # S at the FINAL year is measured over `[final - 1 - L, final - L)`. Deriving it from
    # `_exit_landing_year` here would make the fixture agree with whatever the module does and
    # the table below would never red.
    exit_roll_start = final - 1 - _IMPULSE_LAG                # 2049 — window (2049, 2050]

    # --- the two impulses, and nothing else anywhere on the domain.
    monkeypatch.setattr(pipeline, "_arrival_flow",
                        lambda compo, flow_year, ctx: (_IMPULSE_ARRIVALS
                                                       if flow_year == arrival_interval else 0.0))
    monkeypatch.setattr(pipeline, "immigrant_formation",
                        lambda arrivals, hs, p_nonimm, ratio: arrivals)
    monkeypatch.setattr(pipeline, "native_formation",
                        lambda t_map, tm1_map, hs, own: 0.0)
    monkeypatch.setattr(pipeline, "owner_stock",
                        lambda pop, hs, own: _IMPULSE_OWNER_STOCK)

    seen_exits, seen_supply = {}, []
    real_roll = pipeline.roll_one_year

    def impulse_roll(stock, age, year, q_live, qx):
        nxt, _ = real_roll(stock, age=age, year=year, q_live=q_live, qx=qx)
        exits = {"estate": _IMPULSE_ESTATE if year == exit_roll_start else 0.0, "living": 0.0}
        seen_exits[year] = exits["estate"]
        return nxt, exits

    real_listings_at = pipeline._listings_at

    def watched_listings_at(listings, year, ctx):
        value = real_listings_at(listings, year, ctx)
        seen_supply.append((year, value))
        return value

    monkeypatch.setattr(pipeline, "roll_one_year", impulse_roll)
    monkeypatch.setattr(pipeline, "_listings_at", watched_listings_at)

    assumptions = dataclasses.replace(pipeline.CENTRAL_LEG, estate_lag_years=_IMPULSE_LAG,
                                      estate_eventual_fraction=1.0, phi_voluntary=1.0)
    ed = pipeline._ed_series(geo, scen, frames, pipeline._ownership_reader(_DATA), assumptions)

    # --- RAW exits: keyed by the roll-START year the roll-forward iterates, one impulse only.
    assert {y: v for y, v in seen_exits.items() if v} == {exit_roll_start: _IMPULSE_ESTATE}, (
        "the roll measures the exit flow over [2049, 2050) and this is the START key it "
        "iterates — the translation is applied where the exits are KEYED, not here")

    # --- S(t): the supply term as the balance actually read it, per projected year.
    assert [y for y, _ in seen_supply] == years
    supply = dict(seen_supply)
    assert {t: v for t, v in supply.items() if v} == {final: _IMPULSE_ESTATE}, (
        f"the single estate flow over (2049, 2050] must reach S at {final} — the FINAL "
        f"projected year — under the estate lag {_IMPULSE_LAG}; got "
        f"{ {t: v for t, v in supply.items() if v} }. A START-labeled key lands it at "
        f"{final - 1}, one year early: the #27 defect, at one cell.")

    # --- ED(t): the expected table, exactly.
    expected = {t: 0.0 for t in years}
    expected[first] = _IMPULSE_ARRIVALS / _IMPULSE_OWNER_STOCK          # +0.1
    expected[final] = -_IMPULSE_ESTATE / _IMPULSE_OWNER_STOCK           # -0.04
    assert dict(zip(years, ed)) == expected, (
        "the arrival impulse must surface at the FIRST projected year and the exit impulse at "
        "the FINAL one; any other pair of years is a cross-leg window misalignment")


# THE VOLUNTARY LEG NEEDED ITS OWN IMPULSE, and the gap was MEASURED rather than reasoned about
# (adversarial verification of amendment #27, 2026-08-23). The estate impulse above zeroes
# `living` at every roll year, so the voluntary listings series is identically zero through the
# whole fixture — and the hand-worked ED fixture derives BOTH of its supply keys from one
# `_exit_landing_year` call, so a PER-CAUSE asymmetry at the keying site is invisible to it too.
# Mutating `_ed_series` to end-label the estate leg alone and leave `living` at its roll-START
# key therefore passed all 25 convention oracles and died only on `test_golden`'s output pin —
# which is precisely the shape amendment #27 ruled the labeled-window fixture exists to replace
# ("a re-minted golden re-ratifies the defect along with it"). This test closes the other half.
#
# TWO IMPULSES AT TWO DIFFERENT ROLL WINDOWS, so it pins each leg's landing year AND the offset
# BETWEEN them: the estate window is placed so that its lag carries it to `final - 1` while the
# voluntary window lands on `final`. Any single-leg shift, any shift of both, and any change to
# the estate lag's convolution moves at least one of those two cells.
_IMPULSE_VOLUNTARY = 300.0          # owner households, one roll window; deliberately != estate


def test_the_VOLUNTARY_and_ESTATE_legs_land_on_their_OWN_ruled_years(monkeypatch, frames):
    """Amendment #27's fixture obligation, for the leg the estate impulse cannot see.

        VOLUNTARY IMPULSE   the roll's `living` exits over `[final - 1, final)` — window
                            `(final - 1, final]`. `market_listings` applies NO lag to the
                            voluntary leg, so its end label IS its listing year: `final`.
        ESTATE IMPULSE      the roll's `estate` exits over `[final - 3, final - 2)` — window
                            `(final - 3, final - 2]`, end label `final - 2`, plus the estate
                            lag L = 1, listing at `final - 1`.

    THE TWO ROLL WINDOWS ARE DERIVED FROM THE RULED ARITHMETIC AND NEVER FROM
    `_exit_landing_year`: the end label of `[y, y+1)` is `y+1`, the voluntary leg carries no lag
    and the estate leg carries L, so the flows that must reach S at `final` and `final - 1` are
    measured over `[final - 1, final)` and `[final - 1 - L - 1, final - L - 1)`. Deriving either
    from the module would make this fixture agree with whatever the module does.

        t              S(t)                     ED(t) = (0 - S) / 10,000
        final - 1      estate    400.0          -0.04
        final          voluntary 300.0          -0.03
        every other    0.0                       0.0
    """
    geo, scen = Geography.MTL_RMR, Scenario.REFERENCE
    pop_g_s = frames.pop[(frames.pop["geography"] == geo)
                         & (frames.pop["scenario"] == scen)]
    years = pipeline._projected_years(pop_g_s)
    first, final = years[0], years[-1]
    assert (first, final) == (2026, 2051)          # the committed lattice, named not assumed

    voluntary_roll_start = final - 1                       # 2050 -> lands `final`, no lag
    estate_roll_start = final - 1 - _IMPULSE_LAG - 1       # 2048 -> lands `final - 1` with L

    # --- NO demand anywhere on the domain: every cell of the table below is pure supply.
    monkeypatch.setattr(pipeline, "_arrival_flow", lambda compo, flow_year, ctx: 0.0)
    monkeypatch.setattr(pipeline, "immigrant_formation",
                        lambda arrivals, hs, p_nonimm, ratio: arrivals)
    monkeypatch.setattr(pipeline, "native_formation",
                        lambda t_map, tm1_map, hs, own: 0.0)
    monkeypatch.setattr(pipeline, "owner_stock",
                        lambda pop, hs, own: _IMPULSE_OWNER_STOCK)

    seen_exits, seen_supply = {}, []
    real_roll = pipeline.roll_one_year

    def impulse_roll(stock, age, year, q_live, qx):
        nxt, _ = real_roll(stock, age=age, year=year, q_live=q_live, qx=qx)
        exits = {"estate": _IMPULSE_ESTATE if year == estate_roll_start else 0.0,
                 "living": _IMPULSE_VOLUNTARY if year == voluntary_roll_start else 0.0}
        seen_exits[year] = dict(exits)
        return nxt, exits

    real_listings_at = pipeline._listings_at

    def watched_listings_at(listings, year, ctx):
        value = real_listings_at(listings, year, ctx)
        seen_supply.append((year, value))
        return value

    monkeypatch.setattr(pipeline, "roll_one_year", impulse_roll)
    monkeypatch.setattr(pipeline, "_listings_at", watched_listings_at)

    assumptions = dataclasses.replace(pipeline.CENTRAL_LEG, estate_lag_years=_IMPULSE_LAG,
                                      estate_eventual_fraction=1.0, phi_voluntary=1.0)
    ed = pipeline._ed_series(geo, scen, frames, pipeline._ownership_reader(_DATA), assumptions)

    # --- RAW exits: each impulse at the roll-START year the roll-forward iterates, once.
    assert {y: v for y, v in seen_exits.items() if any(v.values())} == {
        estate_roll_start: {"estate": _IMPULSE_ESTATE, "living": 0.0},
        voluntary_roll_start: {"estate": 0.0, "living": _IMPULSE_VOLUNTARY}}, (
        "the roll emits each flow at the START of the window it measures; the translation is "
        "applied where the exits are KEYED, not here")

    # --- S(t): the supply term as the balance actually read it, per projected year. This is the
    # assertion a per-cause asymmetry at the keying site cannot survive.
    assert [y for y, _ in seen_supply] == years
    supply = dict(seen_supply)
    assert {t: v for t, v in supply.items() if v} == {final - 1: _IMPULSE_ESTATE,
                                                     final: _IMPULSE_VOLUNTARY}, (
        f"the voluntary flow over ({voluntary_roll_start}, {final}] must reach S at {final} and "
        f"the estate flow over ({estate_roll_start}, {estate_roll_start + 1}] at "
        f"{final - 1} under the lag {_IMPULSE_LAG}; got "
        f"{ {t: v for t, v in supply.items() if v} }. A leg keyed at its window's START lands "
        "one year early — and a leg keyed at its START while the OTHER is end-labeled is the "
        "same cross-leg misalignment #27 fixed, hiding inside a re-minted golden")

    # --- ED(t): the expected table, exactly. No demand anywhere, so ED is -S/OwnerStock.
    expected = {t: 0.0 for t in years}
    expected[final - 1] = -_IMPULSE_ESTATE / _IMPULSE_OWNER_STOCK        # -0.04
    expected[final] = -_IMPULSE_VOLUNTARY / _IMPULSE_OWNER_STOCK         # -0.03
    assert dict(zip(years, ed)) == expected, (
        "each supply impulse must surface at the ONE year its own window closes on; any other "
        "pair of years is a cross-leg window misalignment")


# THE ROLL LOOP'S SPAN NEEDED ITS OWN PIN, and the gap was found by the same adversarial
# verification round (2026-08-23). Every test above pins WHERE a keyed exit lands; none pins
# THAT every roll window keyed one. Dropping the loop's final year — `range(base_year,
# years[-1] + 1)` narrowed to `range(base_year, years[-1])` — keys nothing at `final + 1`,
# and the WHOLE suite stayed green: no demand year pairs with the window (final, final+1], so
# the missing write is output-invariant TODAY and silently wrong the day the demand domain
# grows one year past the flow lattice. `_listings_at` guards the READ side (a missing key
# refuses); this test guards the WRITE side, which nothing else does.
#
# The oracle is the span itself, derived from the ruled arithmetic and never from the code:
# the roll iterates `[base_year, years[-1]]`, each window `[y, y+1)` end-labels to `y+1`, so
# the keyed supply years MUST be exactly `{base_year + 1 .. years[-1] + 1}` — contiguous, no
# interior gaps, and closing ONE YEAR BEYOND the last projected demand year.


def test_the_roll_loop_KEYS_a_supply_year_for_every_window_it_iterates(monkeypatch, frames):
    """Write-side span pin for amendment #27's keying site.

    Reads the supply dict as `_ed_series` WRITES it — by watching `market_listings`' inputs —
    because that dict never crosses the function boundary otherwise. A dropped final roll
    year, an interior `continue` on a zero exit, or any future refactor that keys conditionally
    breaks contiguity here and REDS, even though every downstream number would be unchanged.
    """
    geo, scen = Geography.MTL_RMR, Scenario.REFERENCE
    pop_g_s = frames.pop[(frames.pop["geography"] == geo)
                         & (frames.pop["scenario"] == scen)]
    years = pipeline._projected_years(pop_g_s)
    base_year = int(pop_g_s["year"].min())

    seen: dict[str, dict[int, float]] = {}
    real_market_listings = pipeline.market_listings

    def watched_market_listings(voluntary_by_year, estate_by_year, **kwargs):
        seen["voluntary"] = dict(voluntary_by_year)
        seen["estate"] = dict(estate_by_year)
        return real_market_listings(voluntary_by_year=voluntary_by_year,
                                    estate_by_year=estate_by_year, **kwargs)

    monkeypatch.setattr(pipeline, "market_listings", watched_market_listings)

    assumptions = pipeline.CENTRAL_LEG
    pipeline._ed_series(geo, scen, frames, pipeline._ownership_reader(_DATA), assumptions)

    expected_span = set(range(base_year + 1, years[-1] + 2))
    for cause in ("voluntary", "estate"):
        assert set(seen[cause]) == expected_span, (
            f"the {cause} leg's keyed supply years must be exactly "
            f"{{base_year + 1 .. years[-1] + 1}} = {{{base_year + 1}..{years[-1] + 1}}} — "
            f"one key per iterated roll window, contiguous, closing one year PAST the last "
            f"projected demand year. Got {min(seen[cause])}..{max(seen[cause])} with "
            f"{len(seen[cause])} keys; a dropped or conditional keying is the silent-zero "
            f"class this module refuses")


def test_the_i2_operand_binding_catches_a_mis_wired_consumer(monkeypatch, tmp_path):
    """`demand/i2.py` names this test by name and assigns it to THIS task: "the CONSUMER-side
    check is a PIPELINE mutation (Task 29): with arrivals > 0, feeding P_ISQ instead of
    P_resident changes the emitted demand and fails the integration assertion. The identity
    alone cannot catch a mis-wired consumer, because it holds regardless of what native
    formation reads." The mutation is on the DECOMPOSITION, so the run must refuse."""
    monkeypatch.setattr(pipeline, "p_resident", lambda p_isq, surviving_arrivals: p_isq)
    with pytest.raises(CalibrationError, match="I2 double-entry"):
        run_pipeline(data_dir=_DATA, out_dir=tmp_path, now_year=2026)


def test_native_formation_reads_the_netted_operands_at_both_t_and_t_minus_1(monkeypatch):
    """Route (b) of §6's operand binding — the one `demand/i2.py` assigns to THIS task by name.

    The test above is route (a): it mutates the DECOMPOSITION, so the value handed to formation
    stops equalling P_ISQ - Σ arrivals and `assert_i2_identity` fires. It says nothing about
    which variable the CONSUMER then reads, and i2.py states exactly that — "the identity alone
    cannot catch a mis-wired consumer, because it holds regardless of what native formation
    reads". In `_ed_series` the assertion and the call are joined by a shared local name and
    nothing else; this is what binds them.

    Measured PRE-RULING-V, handing `native_formation` the RAW ISQ maps instead: MTL_RMR's mean
    ED +0.002767760 -> +0.003883128 (+40%) and HORS_RMR's SIGN flips, -0.000290446 ->
    +0.001087254 — a reordered published ranking with the rest of the suite green. Both baselines
    are the retired band-curve golden, on which HORS_RMR was rank 1 and MTL_RMR rank 6; on the
    resolved curve they are rank 4 at +0.0011023443 and rank 5 at +0.0019111440, and rank 1 is
    LANAUDIERE_RA14_PROXY. READ THE MUTANT FIGURE +0.001087254 AS A BAND-CURVE NUMBER, NEVER AN
    ARTIFACT ONE: it falls 1.5e-5 from the committed resolved-curve HORS_RMR reference
    +0.0011023443 by coincidence, and the two have nothing to do with each other. The deltas
    stand as the dated reason this test exists.

    BOTH operands are pinned, once per projected year: a swap on t-1 alone is the same defect
    at half the magnitude.
    """
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geo, scen = Geography.MTL_RMR, Scenario.REFERENCE
    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    compo_g_s = frames.compo[(frames.compo["geography"] == geo)
                             & (frames.compo["scenario"] == scen)]
    years = pipeline._projected_years(pop_g_s)

    def raw(year):
        return sum(pipeline._pop_by_age(pop_g_s, year, ctx="operand").values())

    def netted(year):
        """§6's P_resident = P_ISQ - Σ surviving arrivals, written out here rather than
        borrowed from `p_resident`, so the oracle is the spec equation and not the code."""
        return raw(year) - sum(pipeline._surviving_arrivals(compo_g_s, year, ctx="operand"))

    seen = []
    real_native_formation = pipeline.native_formation
    monkeypatch.setattr(pipeline, "native_formation",
                        lambda t_map, tm1_map, hs, own: (
                            seen.append((sum(t_map.values()), sum(tm1_map.values()))),
                            real_native_formation(t_map, tm1_map, hs, own))[1])
    pipeline._ed_series(geo, scen, frames, read, pipeline.CENTRAL_LEG)

    assert len(seen) == len(years)                       # once per projected year
    # approx, not ==: the operand is rebuilt per age as p * (P_resident / P_ISQ), so its sum
    # meets P_resident in the last bits only. The gap being tested is >5%, four orders clear.
    assert [s[0] for s in seen] == pytest.approx([netted(t) for t in years])
    assert [s[1] for s in seen] == pytest.approx([netted(t - 1) for t in years])

    # The discriminator, and it covers BOTH legs: 2035 is a t-1 operand (for 2036) as well as a
    # t one, and there P_ISQ 4,484,077 stands against P_resident 4,199,054. (At the FIRST
    # projected year alone the two coincide by construction — no arrival cohort has landed
    # before the flow span opens — so that year is carried by the years after it, not tested by
    # itself.)
    assert 0.0 < netted(2035) < 0.95 * raw(2035)


def test_owner_stock_takes_the_raw_isq_population_never_the_netted_resident_one(monkeypatch):
    """The neighbouring operand binding, on the SAME function and unbound in the same way. §6's
    operand binding governs the FORMATION equation ALONE; `balance/owner_stock.py` states at its
    own use site that netting the surviving arrival cohorts out of THIS denominator would shrink
    the stock and scale |ED| away from zero. `_ed_series` passes the raw map and says so in a
    comment — and measured PRE-RULING-V, swapping it for `resident_t` moved MTL_RMR's mean ED
    from +0.00276776 to +0.00297395 (+7.4%, away from zero exactly as the comment predicts) with
    the whole suite still green. That baseline is the retired band-curve golden, on which MTL_RMR
    was rank 6; it is rank 5 at +0.0019111440 on the resolved curve, so the delta stands as the
    dated reason this test exists and not as a reading of the committed vintage.

    The operand is pinned per PROJECTED YEAR, not once: a swap at any single year is the same
    silent defect. The two operands differ by the surviving arrivals alone, which the closing
    assertion measures so the binding is a real discriminator rather than a tautology.
    """
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geo, scen = Geography.MTL_RMR, Scenario.REFERENCE
    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    compo_g_s = frames.compo[(frames.compo["geography"] == geo)
                             & (frames.compo["scenario"] == scen)]
    years = pipeline._projected_years(pop_g_s)
    raw_totals = [sum(pipeline._pop_by_age(pop_g_s, t, ctx="operand").values()) for t in years]

    seen = []
    real_owner_stock = pipeline.owner_stock
    monkeypatch.setattr(pipeline, "owner_stock",
                        lambda pop, hs, own: (seen.append(sum(pop.values())),
                                              real_owner_stock(pop, hs, own))[1])
    pipeline._ed_series(geo, scen, frames, read, pipeline.CENTRAL_LEG)
    assert seen == raw_totals   # P_ISQ, collectives included, once per projected year

    # and the netted operand is a MATERIALLY different number — 2035 carries P_ISQ 4,484,077
    # against P_resident 4,199,054 — so the assertion above discriminates.
    p_isq = raw_totals[years.index(2035)]
    p_res = pipeline.p_resident(p_isq, pipeline._surviving_arrivals(compo_g_s, 2035,
                                                                    ctx="operand"))
    assert 0.0 < p_res < 0.95 * p_isq


def test_the_per_age_P_resident_operand_is_NONNEG_BY_COMPOSITION(frames, monkeypatch):
    """Spec §6's `P_resident(a,g,s,t) >= 0` — bound where the guarantee ACTUALLY lives (r12-F1).

    THE PROSE IT REPLACES POINTED AT NOTHING. `demand/formation.py` said the property was
    "asserted per cell before any consumer" by `demand/i2.py`'s `assert_p_resident_nonneg`, which
    is spec §6's own wording. Measured: that function takes a SCALAR, has ONE production call
    site, and evaluates on the (geography, scenario, year) TOTAL — 27 times per geography-scenario
    against 2,727 per-age cells, with no call context carrying an age — and the per-age operand
    is not representable there at all, since `_surviving_arrivals` returns a flat list of YEAR
    flows with no age index. Nothing downstream re-checks the sign either: `_households` binds
    finiteness and rate PRESENCE, never nonnegativity, so a negative cell would enter the
    formation sum as a plausible float and the run would publish it.

    SO THE PROPERTY IS A COMPOSITION, and this test binds the composition ON THE PRODUCTION PATH
    rather than on a re-implementation of it: `native_formation` is wrapped, so what is measured
    is the operand `_ed_series` actually hands the consumer, once per projected year at both `t`
    and `t-1`. Each cell is `P_ISQ(a) x scale` with `P_ISQ(a) >= 0` refused at load
    (`loaders/isq.py`, codex r4-F3) and `scale = P_resident_total / P_ISQ_total >= 0` refused by
    the total-level gate.

    ARM 2 IS WHAT MAKES IT A THEOREM RATHER THAN A PROPERTY OF THIS VINTAGE. On the committed
    data the total-level gate never fires (P_resident is comfortably positive everywhere), so
    arm 1 alone would pass with that gate deleted. Driving the arrivals past P_ISQ makes the
    scale the only thing standing between the loader's nonneg cells and negative demand: the run
    must REFUSE, and it must refuse BEFORE the operand is formed. MEASURED with the gate no-op'ed
    to `return value` (2026-08-23, this fixture, `1e12` arrivals): no raise, 26 formation calls,
    and EVERY cell of every operand negative — smallest -15,408,913,855.0 persons, largest
    -13,846,979,863.5. The figures are a property of the 1e12 above and of nothing else; what
    reproduces across any choice is the SIGN, which is what the assertions read.
    """
    read = pipeline._ownership_reader(_DATA)
    geo, scen = Geography.MTL_RMR, Scenario.REFERENCE
    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    years = pipeline._projected_years(pop_g_s)

    smallest_cell = []
    real_native_formation = pipeline.native_formation

    def watched(resident_t, resident_tm1, headship, ownership):
        smallest_cell.append(min(min(resident_t.values()), min(resident_tm1.values())))
        return real_native_formation(resident_t, resident_tm1, headship, ownership)

    monkeypatch.setattr(pipeline, "native_formation", watched)
    pipeline._ed_series(geo, scen, frames, read, pipeline.CENTRAL_LEG)

    assert len(smallest_cell) == len(years), (
        "native formation was not entered once per projected year, so the minimum below is over "
        "the wrong set of operands")
    assert min(smallest_cell) >= 0.0, (
        f"a NEGATIVE per-age P_resident cell reached native formation: {min(smallest_cell)} — "
        "nothing in `formation.py` would have refused it")

    # ARM 2: the factor the committed data never exercises. Arrivals five orders past MTL_RMR's
    # P_ISQ (~4.5e6) make P_resident_total negative, which is the ONLY way this operand's cells
    # can go negative — the loader has already refused a negative P_ISQ(a).
    smallest_cell.clear()
    monkeypatch.setattr(pipeline, "_surviving_arrivals", lambda *args, **kwargs: [1e12])
    with pytest.raises(CalibrationError, match="P_resident negative"):
        pipeline._ed_series(geo, scen, frames, read, pipeline.CENTRAL_LEG)
    assert not smallest_cell, (
        "the refusal must come BEFORE the operand is formed; native formation was handed a map "
        f"whose smallest cell is {min(smallest_cell) if smallest_cell else None}")


# ---------------------------------------------------- B8: band entry, not a magic fraction

def test_band_entry_entrants_are_the_initialization_equations(run):
    """Carry B8, resolved by spec §5 rather than by citing the number. The plan added
    `max(entrants.owner_units - stock.owner_units, 0.0) * 0.1` as all-COUPLE inflow: an uncited
    0.1, a partial RE-ANCHORING to the ISQ 75+ stock that `rollforward.py`'s own first line
    forbids ("band-entry-only entrants; NEVER re-anchored to ISQ 75+ stocks"), and an unstated
    entrant mix. Spec §5 states the rule instead of a parameter, and implementing it leaves no
    free parameter to cite."""
    from demoflow.cohort.init import initialize_households
    from demoflow.cohort.rollforward import BAND_ENTRY_AGE
    from demoflow.loaders.constants import CONSTANTS
    from demoflow.loaders.living_arrangement import couple_share, living_alone_rate

    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geo, scen, year = Geography.MTL_RMR, Scenario.REFERENCE, 2035
    pop_g_s = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
    got = pipeline._band_entry_stock(pop_g_s, year, geo, frames.la, read,
                                     collective_share=_CENTRAL_COLLECTIVE)

    rows = pop_g_s[(pop_g_s["year"] == year) & (pop_g_s["age"] == BAND_ENTRY_AGE)]
    want = initialize_households(
        {s: float(rows[rows["sex"] == s]["population"].sum()) for s in ("M", "F")},
        living_alone_rate_by_sex={s: living_alone_rate(frames.la, geo, BAND_ENTRY_AGE, s)
                                  for s in ("M", "F")},
        couple_share_by_sex={s: couple_share(frames.la, geo, BAND_ENTRY_AGE, s)
                             for s in ("M", "F")},
        collective_share=CONSTANTS["collective_share_75plus"].value,
        ownership_rate=read(geo, BAND_ENTRY_AGE))
    assert (got.couple, got.solo_m, got.solo_f) == (
        want.owner_couple, want.owner_solo_m, want.owner_solo_f)
    # PER STATE, never one number booked as couples — the plan's inflow put 100% into Couple.
    assert got.solo_m > 0.0 and got.solo_f > 0.0
    # and the entrant is the newly-aged-75 cohort, not a share of the 75+ AGGREGATE gap
    assert got.owner_units < pipeline._standing_stock(
        pop_g_s, year, geo, frames.la, read,
        collective_share=_CENTRAL_COLLECTIVE).owner_units


def test_the_ed_roll_forward_takes_its_entrants_from_band_entry_only(monkeypatch):
    """The test above pins `_band_entry_stock`'s VALUE; this one pins that the ED roll-forward
    is what consumes it. Measured — a mutant restoring the plan's
    `max(ISQ_75plus(t+1) - rolled(t), 0) * 0.1` inflow left the value test GREEN, because the
    helper still existed and was simply no longer called.

    `_standing_stock` is called EXACTLY ONCE, for the initial condition. A second call inside
    the loop is the ISQ re-anchoring `rollforward.py`'s first line forbids, whatever fraction
    of the gap it books."""
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    entry, standing = [], []
    real_entry, real_standing = pipeline._band_entry_stock, pipeline._standing_stock
    monkeypatch.setattr(pipeline, "_band_entry_stock",
                        lambda *a, **k: (entry.append(a[1]), real_entry(*a, **k))[1])
    monkeypatch.setattr(pipeline, "_standing_stock",
                        lambda *a, **k: (standing.append(a[1]), real_standing(*a, **k))[1])
    pipeline._ed_series(Geography.QC_RMR, Scenario.REFERENCE, frames, read,
                        pipeline.CENTRAL_LEG)
    assert len(standing) == 1, f"the roll-forward re-anchored to the ISQ 75+ stock {standing}"
    # one band-entry cohort per rolled year, from the year after the base through the last
    # population year — the cohort's ONLY entry point.
    assert entry == list(range(2022, 2052))


def test_an_absent_band_entry_cohort_refuses():
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    pop_g_s = frames.pop[(frames.pop["geography"] == Geography.MTL_RMR)
                         & (frames.pop["scenario"] == Scenario.REFERENCE)]
    with pytest.raises(LoaderError, match="band entry"):
        pipeline._band_entry_stock(pop_g_s, 2052, Geography.MTL_RMR, frames.la, read,
                                   collective_share=_CENTRAL_COLLECTIVE)


# ------------------------------------------------------------- domain, sweep, exclusions

def test_ranking_domain_is_the_projected_contiguous_lattice(run):
    frames = pipeline._load_all(_DATA)
    years = pipeline._projected_years(
        frames.pop[(frames.pop["geography"] == Geography.MTL_RMR)
                   & (frames.pop["scenario"] == Scenario.REFERENCE)])
    assert years == list(range(2026, 2052))
    assert years[-1] == int(frames.pop["year"].max())


def test_rank_stable_covers_every_ranked_geography(run):
    rows = run["_docs"]["rankings"]["rankings"]
    assert len(rows) == len([g for g in Geography])
    assert all(isinstance(r["rank_stable"], bool) for r in rows)
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_the_robustness_sweep_evaluates_EVERY_declared_axis_at_BOTH_endpoints():
    """CRITICAL — run-33 quant F1 and stress F1, reached independently, and the seat reproduced
    it: `rank_stable: true` shipped on all eight golden rows as a verdict over ONE of the
    declared axes. `_rank_stability` iterated `SWEEP_GRID["q_live_per_year"]` alone; the grid
    declares FOUR, and `constants.py` states a FIFTH as an existing fact of this very module —
    "Task 29 perturbs the join table with a uniform override spanning
    CONSTANTS['immigrant_ownership_ratio_sweep_span']" — for which no code existed anywhere in
    the tree. Spec §7b asks whether the ordering changes ANYWHERE IN THE SWEEP GRID; a verdict
    computed over one axis cannot answer that question, and the one it does answer is the axis
    that turned out not to move the order.

    THIS IS THE AXIS-COVERAGE ASSERTION `test_rank_stable_covers_every_ranked_geography` DOES
    NOT MAKE. That test pins GEOGRAPHY coverage and bool TYPE, and both held while four of five
    axes were silently absent — which is why the narrowing shipped green.

    ONE AXIS OFF-CENTRAL PER LEG is asserted too, and it is a contract rather than a style: a leg
    that moved two axes at once could not attribute a reorder to either, and the union verdict
    would then be true of a combination the spec never declared.
    """
    legs = pipeline._sweep_legs()
    declared = set(SWEEP_GRID) | {pipeline.RATIO_SWEEP_AXIS}
    assert {axis for axis, _ in legs} == declared, "a declared robustness axis is never evaluated"
    assert len(legs) == 2 * len(declared)

    for axis in declared:
        endpoints = (SWEEP_GRID[axis] if axis in SWEEP_GRID
                     else CONSTANTS["immigrant_ownership_ratio_sweep_span"].value)
        assert (sorted(getattr(leg, axis) for a, leg in legs if a == axis)
                == sorted(endpoints)), f"{axis} is not evaluated at both declared endpoints"

    # AT MOST ONE AXIS OFF-CENTRAL PER LEG, and the ONE leg that moves none is named. Since
    # ruling V `headship_shape` is a CATEGORICAL axis whose admissible set contains the central
    # value, so its `expo_cum_fc` endpoint IS the central leg — provably, not accidentally.
    # Every other axis is a spec §5 band with both endpoints off-central, and one that drifted
    # onto its central value would be an inert leg the exemption must not cover.
    no_op = []
    for axis, leg in legs:
        moved = [f for f in pipeline.SWEEP_LEG_FIELDS
                 if getattr(leg, f) != getattr(pipeline.CENTRAL_LEG, f)]
        if not moved:
            no_op.append((axis, getattr(leg, axis)))
            continue
        assert moved == [axis], f"leg for {axis} moved {moved} — a leg perturbs ONE axis"
    assert no_op == [("headship_shape", CENTRAL_ASSUMPTIONS["headship_shape"])], (
        f"legs that move no assumption at all: {no_op} — only the categorical shape axis may "
        "declare its central value as an endpoint")


def test_every_declared_sweep_axis_actually_REACHES_the_ED_NUMBERS():
    """THE SECOND DOOR, and it is the one the original CRITICAL walked through: a leg field
    reachable in NAME and inert in EFFECT. `_sweep_legs` refuses a declared axis that has no leg
    FIELD, which closes declared -> field. Nothing closed field -> CONSUMED, and that is the half
    that actually failed — `phi_voluntary` was a declared `SWEEP_GRID` axis the whole time and
    still could not move an ED number, because `market_listings` read the module constant instead
    of an argument.

    MEASURED SURVIVABLE, which is why this is a test and not a comment. THE MAGNITUDES ARE NOT
    RESTATED HERE — the sentence that stood in their place quoted "four grid fields ... 8 of the
    12 legs INERT" with NO DATE, against a grid that carries five numeric fields and fourteen
    legs today, while its own twin at `pipeline._sweep_legs` carried the SAME battery dated to the pre-PR
    audit-gate fold and said in as many words that it had not been re-measured on either widening. Two
    copies of one measurement, one of them dated and one not, is how the copy without the date
    becomes the wrong one. So the record lives at the twin and this docstring points at it: read
    `pipeline._sweep_legs.__doc__` for the battery, the commit it was measured at, the grid it
    was measured on, and the fact that it has NOT been re-measured since.
    WHAT IS DATE-FREE AND STILL TRUE is the MECHANISM, which is what this test exists for and
    what no widening changes: nothing else sees such a mutant, because the CENTRAL run is
    untouched so no golden byte moves, and because the ratio axis ALONE saturates the union
    verdict (it reorders seven of eight rows at 0.155 and the union over its two endpoints
    reaches all eight), so `false` on every row stays satisfiable by ONE live axis. A one-axis
    sweep is exactly the defect run 33 exists to close, and it would have shipped green a second
    time.

    ONE GEOGRAPHY AT `REFERENCE` IS ENOUGH, and the cost is stated rather than hidden: thirteen ED
    series on frames loaded ONCE — measured at 4s end to end, most of it that single load, against
    a suite already near five minutes. All eight geographies move on every leg that moves an
    assumption at all (measured), so
    the choice of geography is not load-bearing. Iterating LEGS rather than AXES is deliberate
    too — it also catches a declared endpoint that has drifted onto the central value, which is
    an inert leg by a different route.
    """
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geo = Geography.MTL_RMR
    central = pipeline._ed_series(geo, Scenario.REFERENCE, frames, read, pipeline.CENTRAL_LEG)

    for axis, leg in pipeline._sweep_legs():
        series = pipeline._ed_series(geo, Scenario.REFERENCE, frames, read, leg)
        if leg == pipeline.CENTRAL_LEG:
            # The ONE declared no-op leg (see the axis-coverage test, which names it and reds
            # on a second). Its ED series MUST equal the central one — that identity is what
            # makes the sweep's reuse of the central grid sound rather than a dropped leg.
            assert series == central, (
                f"the {axis!r} leg is `==` the central leg but produces a DIFFERENT ED series "
                "— the leg object no longer determines the numbers")
            continue
        assert series != central, (
            f"the {axis!r} leg at endpoint {getattr(leg, axis)!r} reproduces the CENTRAL ED "
            f"series at {geo.value} — the axis is swept in NAME and its field never reaches the "
            f"model, so `rank_stable` reports a verdict over a grid it did not vary")


def test_the_central_leg_reads_the_RULED_per_geography_ratio_and_never_a_scalar():
    """The other side of the ratio axis, and it is the reason the override is a sweep-only
    field with `None` as its central value. Task 25b DELETED the plan's `immigrant_ratio_center`
    scalar because rulings S/T measure the ratio PER GEOGRAPHY — so the headline run must read
    the join table row by row, and a central scalar here would silently replace five ruled
    measurements with one number. The override exists for the SWEEP alone."""
    assert pipeline.CENTRAL_LEG.immigrant_ownership_ratio is None
    assert "immigrant_ratio_center" not in SWEEP_GRID and "immigrant_ratio_center" not in CENTRAL_ASSUMPTIONS
    assert pipeline.CENTRAL_LEG == pipeline.Assumptions(**CENTRAL_ASSUMPTIONS)


def test_a_declared_sweep_axis_the_ED_grid_cannot_VARY_is_REFUSED(monkeypatch):
    """The forward guard stress F1 asks for by name — "a future axis added to the constant cannot
    go unswept". The failure this closes is the one that already happened: an axis declared in
    `SWEEP_GRID` and absent from the sweep's product fell out SILENTLY, and `rank_stable` then
    reported a verdict over a grid it had not covered. A declared axis the leg cannot carry now
    REFUSES the run rather than shrinking the sweep."""
    monkeypatch.setitem(SWEEP_GRID, "tenure_transition_rate", (0.1, 0.2))
    with pytest.raises(CalibrationError, match="tenure_transition_rate"):
        pipeline._sweep_legs()


def test_rank_stable_is_FALSE_on_every_row_of_the_committed_vintage(run):
    """THE MEASURED STATE, pinned so it cannot quietly revert to the false attestation.

    `false` on all eight rows is the CORRECT output of the seven-axis sweep, not a regression:
    the join-table ratio axis reorders the published ranking at both of its declared endpoints,
    and the union over every axis therefore finds no geography whose rank is unchanged
    everywhere.

    THE GRID AXES DO NOT LEAVE THE ORDER INTACT ANY MORE, and a reader must not take the run-33
    reading forward. On the BAND curve the four `SWEEP_GRID` axes left the published order intact
    at both endpoints — which is exactly why sweeping one of them and calling it `rank_stable`
    produced a green verdict for a year. That clause is the correct HISTORY of the defect and not
    a description of this vintage: `SWEEP_GRID` declares SIX axes now (`headship_shape` joined at
    ruling V, `collective_share_75plus` at spec amendment #20(D)) and grid axes DO reorder.
    WHICH ones and at which endpoint is no longer stated in any prose, here or in
    `pipeline.py` or in `artifacts/README.md`: it is the EMITTED `rows_moved` map (amendment
    #20(C)(2)), re-derived every run, because the run-35 prose reading of it had gone stale in
    eight of twelve cells by 2026-08-22 — including which endpoint of `q_live_per_year` and
    `phi_voluntary` reorders. The two claims that are PINNED rather than narrated are the union
    verdict asserted below and, in `test_the_join_table_ratio_endpoint_is_the_axis_THAT_REORDERS`,
    that the ratio AXIS moves every row across its two endpoints with rank 1 changing hands at the
    low one. Dropping the ratio leg would NOT return this field to `true`: the grid-only union is
    4 of 8 rows on these bytes — `HORS_RMR`, `LAURENTIDES_RA15_PROXY`, `LAVAL_RA13` and `MTL_RMR`,
    across TWO non-ratio legs (`phi_voluntary=0.7` at four rows and `q_live_per_year=0.06` at two,
    both of them also moved by the first) — so four rows would still read `false`. It was 3 of 8
    before spec amendment #24(A) re-based the levels and 2 of 8 between #24(A) and #27, whose
    end-labelling revived `q_live_per_year` as a reordering axis. With two non-ratio legs moving
    rows the union is no longer a function of the emitted per-leg COUNTS at all: it is re-derived
    by re-ranking, in `tests/test_golden.py::test_the_readme_binds_the_GRID_ONLY_union_to_the_emitted_rows_moved`,
    which is where the membership above is bound.

    It also kills the one silent failure the axis-coverage test above cannot see: a
    `_sweep_legs()` that returned NOTHING would satisfy every set assertion vacuously and make
    the union verdict trivially TRUE.
    """
    rows = run["_docs"]["rankings"]["rankings"]
    assert len(rows) == len([g for g in Geography])
    assert [r["rank_stable"] for r in rows] == [False] * len(rows), (
        "the seven-axis sweep reorders the ranking at the join-table ratio endpoints, so no row "
        "is rank-stable on the committed vintage — a True here means an axis stopped being swept")


# `artifacts/README.md`'s RATIO-ENDPOINTS span, read by leg (4) of the gate below. The clause is
# the SAME rigid form `tests/test_golden.py` reads, deliberately: two gates over one written form
# beats two forms, and a re-word that breaks one breaks both rather than silently splitting them.
_README_RATIO_BEGIN = "<!-- RATIO-ENDPOINTS:BEGIN -->"
_README_RATIO_END = "<!-- RATIO-ENDPOINTS:END -->"
_README_ENDPOINT_CLAUSE = re.compile(
    r"At `(?P<leg>immigrant_ownership_ratio=[0-9.]+)`: \*\*rank 1 "
    r"(?P<verdict>CHANGES HANDS|HOLDS)\*\*, the leader is `(?P<leader>[A-Z][A-Z_0-9]*)`, "
    r"and \*\*(?P<moved>[a-z]+)\*\* rows move")


def test_the_join_table_ratio_endpoint_is_the_axis_THAT_REORDERS(run):
    """WHICH axis carries the verdict, measured rather than asserted — so a future regression
    that drops the ratio leg reds HERE with its cause named, instead of flipping eight booleans
    back to `true` with no reader able to say why.

    MEASURED at the low endpoint 0.155. The permutation below is PRE-RULING-V and is kept as the
    record of the run-32 reproduction, not as a description of the current model — it was taken
    against the BAND-curve central order, which the ruling-V curve commit replaced: HORS_RMR 1->4, LAURENTIDES
    2->6, LANAUDIERE 3->7, LAVAL_RA13 4->1, MONTEREGIE 5->3, MTL_RMR 6->2, QC_RMR 7->8,
    MTL_ISLAND_RA06 8->5 (it reproduced run-32's quant and stress gates independently — both ran
    an out-of-tree harness, this runs the shipped code).

    ON THE RESOLVED CURVE, re-measured at the run-35 re-mint: LANAUDIERE 1->6, LAVAL_RA13 2->3,
    LAURENTIDES 3->7, HORS_RMR 4->8, MTL_RMR 5->1, MONTEREGIE 6->4, QC_RMR 7->5, MTL_ISLAND_RA06
    8->2. Both permutations are kept as DATED RECORDS and neither is pinned.

    THE WITNESS IS NOW THE UNION OF THE AXIS'S TWO ENDPOINTS, re-measured at operator ruling W
    (2026-08-20), and the widening is the finding. Until ruling W this gate evaluated the LOW
    endpoint alone and asserted that EVERY ranked geography moves there — true on both earlier
    curves, and stated as structural. The seven-band ownership lattice FALSIFIES it: at 0.155
    seven of eight rows move and LAVAL_RA13 holds rank 3, so the strong claim now reds on a
    lattice refinement rather than on a dropped sweep leg. Relaxing it to "seven of eight" would
    convert a measured witness into a fitted threshold, so the ENDPOINT SET was widened instead
    and the strong claim recovered at the axis level: the union over 0.155 and 1.033 moves all
    eight rows, which was ALSO true before ruling W. That is what restores "structural, and holds
    on both curves" — the property this gate is for.

    MEASURED AT RULING W, per endpoint: 0.155 moves SEVEN rows (LAVAL_RA13 holds rank 3) and
    displaces rank 1; 1.033 moves FOUR and rank 1 HOLDS. Measured at HEAD before the refinement,
    for the same two legs: 0.155 moved EIGHT and displaced rank 1; 1.033 moved SIX and displaced
    rank 1 as well. Both of those 1.033 clauses moved with the lattice, so both are restated here
    rather than one — a stale count beside a live assertion is the defect this file keeps closing.

    RE-MEASURED AFTER OPERATOR RULING X (2026-08-21) and UNCHANGED, which is worth stating
    because it was not safe to assume: X1 re-weighted the 75+ ownership read and X2 replaced the
    immigrant leg's point read with the 25-54 aggregate, so both endpoints were re-run. 0.155
    still moved SEVEN with LAVAL_RA13 the sole fixed point (at rank 3) and still displaced rank 1
    (LANAUDIERE_RA14_PROXY -> MTL_RMR); 1.033 still moved FOUR (LAURENTIDES_RA15_PROXY,
    LAVAL_RA13, QC_RMR, MTL_ISLAND_RA06) and rank 1 HELD. The dated permutation at 0.155 then:
    LANAUDIERE 1->6, LAURENTIDES 2->7, LAVAL_RA13 3->3, HORS_RMR 4->8, MTL_RMR 5->1,
    MONTEREGIE 6->4, QC_RMR 7->5, MTL_ISLAND_RA06 8->2. It differs from the run-35 record above
    only in where LAURENTIDES and LAVAL_RA13 sit in the CENTRAL order — every swept destination
    is the same — so the axis's structure survived both rulings.

    RE-MEASURED AT SPEC AMENDMENT #24(A) (2026-08-23) AND THE HIGH ENDPOINT MOVED, which is why
    the HOLDS clause above is now in the past tense. The conversion divided the immigrant leg by
    a per-geography pooled-denominator bias — no rank moved in the CENTRAL order, but it lifted
    LAVAL_RA13 toward the leaders (its bias is the one above 1, so its leg went DOWN while the
    other seven went up) and the high endpoint now displaces rank 1 as well: 1.033 moves FIVE
    (LANAUDIERE_RA14_PROXY, LAURENTIDES_RA15_PROXY, LAVAL_RA13, QC_RMR, MTL_ISLAND_RA06) with
    LAVAL_RA13 taking rank 1 and LANAUDIERE_RA14_PROXY dropping to 2. 0.155 is unchanged at SEVEN
    with LAVAL_RA13 still the sole fixed point at rank 3. So BOTH endpoints displace the leader
    now, to a DIFFERENT geography each — leg (2) below is scoped to the low endpoint anyway,
    because that is the one whose displacement has held across every ruling.

    Two ED grids are evaluated here rather than one, and the extra cost is stated rather than
    hidden: it is the price of a witness that survived the refinement, and the union over all
    fourteen sweep legs is still covered by the run fixture's own `rank_stable` above.
    """
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geos = [g for g in Geography if g in set(frames.pop["geography"])]
    span = CONSTANTS["immigrant_ownership_ratio_sweep_span"].value
    central_order = [r["geography"] for r in run["_docs"]["rankings"]["rankings"]]

    swept_at = {}
    for ratio in span:
        leg = dataclasses.replace(pipeline.CENTRAL_LEG, immigrant_ownership_ratio=ratio)
        swept = rank_geographies(pipeline._ed_dict(geos, frames, read, leg))
        swept_order = [r.geography.value for r in sorted(swept, key=lambda r: r.rank)]
        assert set(swept_order) == set(central_order)
        swept_at[ratio] = (swept_order,
                           [g for g in central_order
                            if central_order.index(g) != swept_order.index(g)])

    lo, hi = span
    lo_order, lo_moved = swept_at[lo]
    _hi_order, hi_moved = swept_at[hi]

    # (1) THE STRUCTURAL CLAIM, at the axis rather than at one endpoint: no ranked geography is
    # invisible to the ratio axis. A row this axis cannot move at EITHER end is a row whose
    # `rank_stable=False` is being carried by something else, and the verdict's witness would
    # have quietly moved elsewhere.
    union = set(lo_moved) | set(hi_moved)
    assert union == set(central_order), (
        f"the ratio axis leaves {sorted(set(central_order) - union)} in place at BOTH endpoints "
        "— the axis is no longer the one that reorders every row, so re-derive which axis carries "
        "the `rank_stable` verdict before relaxing this")
    # (2) And rank 1 — the geography the whole artifact exists to name — changes hands. Scoped to
    # the LOW endpoint because that is the displacement that has survived every ruling; since
    # amendment #24(A) the HIGH endpoint displaces it too (to a different geography), and the
    # per-endpoint verdicts are bound exactly against a re-ranking by leg (4) rather than asserted
    # here — a second pinned displacement would be a claim this leg cannot attribute.
    assert lo_order[0] != central_order[0], (
        "rank 1 did not change hands at the low endpoint, which is the leg that displaces it")
    # (3) NON-VACUITY of (1): the union could be satisfied by two much weaker legs (1 + 7). These
    # are the ruling-W MEASUREMENTS, not tuned floors — if either drops, the union claim above is
    # resting on less than it was measured on and the cause needs naming here.
    assert len(lo_moved) >= 7 and len(hi_moved) >= 5, (
        f"the endpoints moved {len(lo_moved)} and {len(hi_moved)} rows against the 7 and 5 "
        f"measured at spec amendment #24(A) (the high endpoint was 4 at ruling W and the "
        f"conversion widened it) — re-derive what stopped moving before re-pinning these")

    # (4) THE CONSUMER PAGE'S PER-ENDPOINT CLAIMS, against the orders just computed. This leg
    # lives HERE rather than in `tests/test_golden.py` because the two ED grids it needs are the
    # two this test already evaluated; binding the leader over there would buy a second pair.
    #
    # THE MEASURED DEFECT IT CLOSES. `artifacts/README.md` said rank 1 "changes hands again" at
    # 1.033 and named `LAVAL_RA13` as the leader there. Neither is true — rank 1 HOLDS and
    # LAVAL_RA13 is rank 2 — and the sentence sat OUTSIDE every marked span on the page, so a
    # claim about the artifact's SINGLE HEADLINE OUTPUT, on the axis the page itself calls "WHAT
    # CARRIES THE VERDICT", was bound by nothing while THIS FILE and `pipeline.py` both said
    # HOLDS. The span is bound from both sides now: `tests/test_golden.py` holds the rows-moved
    # counts against the emitted `rows_moved` map, and this holds the LEADER and the VERDICT
    # against a re-ranking. A claim naming the wrong leader OR the wrong endpoint reds.
    from demoflow.golden import GOLDEN_DIR
    from demoflow.loaders.constants import RATIO_SWEEP_AXIS, sweep_leg_label

    readme = (GOLDEN_DIR / "README.md").read_text(encoding="utf-8")
    span_lo = readme.index(_README_RATIO_BEGIN) + len(_README_RATIO_BEGIN)
    span_hi = readme.index(_README_RATIO_END)
    assert 0 < span_lo < span_hi, (
        "artifacts/README.md carries no RATIO-ENDPOINTS span, or carries it inverted — a slice "
        "taken from a failed find is a gate that cannot fail")
    span = flat(readme[span_lo:span_hi])

    stated = {m["leg"]: (m["verdict"], m["leader"])
              for m in _README_ENDPOINT_CLAUSE.finditer(span)}
    computed = {sweep_leg_label(RATIO_SWEEP_AXIS, ratio):
                ("HOLDS" if order[0] == central_order[0] else "CHANGES HANDS", order[0])
                for ratio, (order, _moved) in swept_at.items()}
    assert stated == computed, (
        f"artifacts/README.md's RATIO-ENDPOINTS span states {stated} for the ratio axis' "
        f"endpoints; this run re-ranks the ED grid at each and measures {computed}. The page "
        "shipped 'at 1.033 it changes hands again (-> LAVAL_RA13)' against a run in which rank 1 "
        "HOLDS with LANAUDIERE_RA14_PROXY. Each clause must read 'At `<leg>`: **rank 1 CHANGES "
        "HANDS|HOLDS**, the leader is `GEO`, and **<word>** rows move'")


def test_hors_rmr_is_ranked_and_the_exclusion_path_still_exists(run):
    """Spec §8's branch (iii) did NOT fire for the committed vintage — `compo-rmr-base.xlsx`
    ships its own hors-RMR row — so the exclusion list is legitimately EMPTY. The PATH must
    exist and be exercised, because a future vintage without that row must EXCLUDE rather than
    emit a partial ED."""
    ranked = {r["geography"] for r in run["_docs"]["rankings"]["rankings"]}
    assert Geography.HORS_RMR.value in ranked
    assert run["_docs"]["rankings"]["exclusions"] == []

    import pandas as pd
    empty = pd.DataFrame({"geography": [], "scenario": [], "year": [],
                          "immigrant_permanents": []})
    unresolved = pipeline._unresolved_immigrant_flows(empty, [Geography.HORS_RMR])
    assert unresolved == {Geography.HORS_RMR: "immigrant_component_flows"}


# ------------------------------------------------------------------ emission is all-or-nothing

def test_neither_artifact_is_emitted_when_the_second_document_refuses(monkeypatch, tmp_path):
    """Review finding F2. `artifacts.py` states the contract inside the refusal it raises —
    "NO file is emitted and the run exits nonzero" — and the landed emission order contradicted
    it: `rankings.json` was WRITTEN before `tripwire_document` was even BUILT, so any refusal in
    the second document shipped the first file alone. Both documents are now built and validated
    before either is written, so a refusal leaves the output directory exactly as it found it."""
    monkeypatch.setattr(pipeline, "tripwire_document",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("refused")))
    out = tmp_path / "artifacts"
    with pytest.raises(ValueError, match="refused"):
        run_pipeline(data_dir=_DATA, out_dir=out, now_year=2026, sweep_axes=_NO_SWEEP)
    assert not out.exists() or list(out.iterdir()) == []


def test_an_io_failure_on_the_second_write_leaves_neither_artifact(monkeypatch, tmp_path):
    """Stress gate F8. "EMISSION IS ALL-OR-NOTHING" over-claimed: VALIDATION was
    all-or-nothing, the WRITES were a bare sequential loop, so an I/O failure on the SECOND
    document left the first on disk — a mismatched-identity pair nothing in the tree
    cross-checks (`refuse_cross_vintage` operates WITHIN a run, over a set the pipeline
    itself builds, and the rankings file carries the same envelope either way). Measured by
    the gate on the committed documents: `['rankings.json']` survived the failure.

    Both documents are now STAGED beside their final names and renamed only after every
    write has succeeded, so the failure leaves neither artifact and no staging file."""
    real = artifacts._dump_json
    written = []

    def flaky(path, obj):
        written.append(Path(path).name)
        if len(written) == 2:
            raise OSError("disk full")
        real(path, obj)

    monkeypatch.setattr(artifacts, "_dump_json", flaky)
    out = tmp_path / "artifacts"
    with pytest.raises(OSError, match="disk full"):
        run_pipeline(data_dir=_DATA, out_dir=out, now_year=2026, sweep_axes=_NO_SWEEP)
    assert len(written) == 2, f"the failure was not on the second document: {written}"
    assert list(out.iterdir()) == [], f"a half-emitted pair survived: {list(out.iterdir())}"


def test_the_ircc_feed_is_read_once_inside_the_identity_bracket(monkeypatch, tmp_path):
    """Review finding F3. The feed is deliberately UNPINNED (`PRLandings.sha256` is RECORDED,
    monthly refresh), so its bytes are the one input in the envelope that can legitimately move
    between two reads. The landed body loaded it TWICE — once for the envelope and the identity
    token, once for the verdict — and `_refuse_mixed_identity` is sampled BEFORE
    `_tripwire_results` runs, so the published digest and the published verdict could come from
    two different reads with nothing structurally able to see it."""
    calls = []
    real = pipeline.load_pr_landings
    monkeypatch.setattr(pipeline, "load_pr_landings",
                        lambda **kw: (calls.append(kw), real(**kw))[1])
    run_pipeline(data_dir=_DATA, out_dir=tmp_path, now_year=2026, sweep_axes=_NO_SWEEP)
    assert len(calls) == 1, f"the IRCC feed was read {len(calls)} times in one run"


def test_every_emitted_number_is_finite(run):
    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, float):
            assert math.isfinite(node)
    walk(run["_docs"]["rankings"])
    walk(run["_docs"]["tripwires"])


# ------------------------------------- 29c carries C2/C3: the tripwire path that builds nothing
#
# `demoflow tripwires` is a STATUS LISTING. The plan's CLI answered it by calling `run_pipeline`,
# which loads five workbooks, evaluates the ED grid fourteen times (the central run, reused as one
# of the seven-axis sweep's fourteen legs — ~20s of real I/O) and writes BOTH artifacts — so asking for six
# statuses re-emitted `rankings.json` as a side effect.
# `evaluate_tripwires` is the path that does neither, and the three tests below bind "neither"
# structurally rather than by reading the body.


def test_evaluate_tripwires_cannot_emit_because_it_takes_no_out_dir(tmp_path, monkeypatch):
    """Carry C3, discharged by SIGNATURE rather than by discipline: a function with nowhere to
    write cannot acquire an emission by a later edit that forgets why."""
    import inspect
    assert "out_dir" not in inspect.signature(pipeline.evaluate_tripwires).parameters
    monkeypatch.chdir(tmp_path)
    pipeline.evaluate_tripwires(data_dir=_DATA, now_year=2026)
    assert list(tmp_path.iterdir()) == [], "the tripwire path wrote into the working directory"


def test_evaluate_tripwires_never_builds_the_demographic_model(monkeypatch):
    """Carry C2. Not "it is fast" — the ED grid and the ranking sweep are POISONED, so a body
    that reaches either one dies instead of merely costing four grid evaluations."""
    def poison(*a, **kw):
        raise AssertionError("the tripwire path built the demographic model")
    for name in ("_ed_dict", "_ed_series", "rank_geographies", "_rank_stability", "_load_all"):
        monkeypatch.setattr(pipeline, name, poison)
    result = pipeline.evaluate_tripwires(data_dir=_DATA, now_year=2026)
    assert sorted(r.indicator for r in result["tripwires"]) == sorted(REQUIRED_INDICATORS)
    assert "rankings" not in result


def test_evaluate_tripwires_uses_the_run_level_coverage_gate(monkeypatch):
    """Carry C4 at its source. On the committed tree all six indicators are present and all six
    are UNKNOWN, so `exit_code` and `run_exit_code` AGREE at 1 and no committed-data assertion
    can see a substitution (measured in the sibling test above). One OK result separates them."""
    from demoflow.output.tripwires import TripwireResult, exit_code
    one_ok = [TripwireResult(PR_LANDINGS_INDICATOR, 45000.0,
                             "IRCC PR admissions by CMA (open.canada.ca monthly CSV)",
                             2026, 40000.0, 50000.0, Status.OK)]
    monkeypatch.setattr(pipeline, "_tripwire_results", lambda landings, now: (one_ok, ["x"]))
    assert exit_code(one_ok) == 0
    assert pipeline.evaluate_tripwires(data_dir=_DATA, now_year=2026)["exit_code"] == 1


def test_the_cheap_tripwire_path_returns_the_SAME_verdict_as_the_full_run(run):
    """The point of the whole split. A second evaluation path is only a saving if it cannot
    disagree with the one that emits the artifact — otherwise `demoflow tripwires` becomes a
    second opinion an operator has to reconcile against `tripwire_baseline.json`."""
    cheap = pipeline.evaluate_tripwires(data_dir=_DATA, now_year=2026)
    assert cheap["tripwires"] == run["tripwires"]
    assert cheap["tripwire_log"] == run["tripwire_log"]
    assert cheap["exit_code"] == run["exit_code"]
    # ...and the listing is ATTRIBUTABLE: the same two identity fields the EMITTED document
    # carries, so a listing and a committed `tripwire_baseline.json` can be told apart when they
    # disagree instead of both being unlabelled readings of an unpinned monthly feed. Compared
    # against the WRITTEN document rather than against `run`'s own return value, because the
    # file is what an operator holds in their hand.
    emitted = run["_docs"]["tripwires"]
    assert cheap["assumptions_hash"] == emitted["assumptions_hash"]
    assert cheap["data_vintage"] == emitted["data_vintage"]
    assert cheap["data_vintage"]["source_hashes"], "an empty vintage merely LOOKS provenanced"


# ===========================================================================================
# OPERATOR RULING V: the headship SHAPE axis, and the bill it comes with
# ===========================================================================================

def test_the_headship_shape_axis_is_declared_ONCE_and_bound_to_the_CURVE_it_selects():
    """THREE declaration sites, bound by this test so none can drift alone.

    `census.HEADSHIP_SHAPES` owns the CONSTRUCTION (which tangent rules exist);
    `SWEEP_GRID["headship_shape"]` owns the ROBUSTNESS SELECTION (which the sweep varies);
    the artifact's `central_shape` owns what a bare `load_headship_rates()` would serve. A
    shape carried in the artifact and absent from the grid rides the headline unswept; a shape
    declared in the grid and absent from the artifact makes a sweep leg raise at load. Neither
    is visible from inside either file.
    """
    from demoflow.loaders.census import HEADSHIP_CENTRAL_SHAPE, HEADSHIP_SHAPES, load_headship_curves
    assert set(SWEEP_GRID["headship_shape"]) == set(HEADSHIP_SHAPES)
    assert CENTRAL_ASSUMPTIONS["headship_shape"] == HEADSHIP_CENTRAL_SHAPE
    assert set(load_headship_curves(data_dir=_DATA)) == set(HEADSHIP_SHAPES)
    payload = json.loads((_DATA / "headship_by_age.json").read_text(encoding="utf-8"))
    assert payload["central_shape"] == CENTRAL_ASSUMPTIONS["headship_shape"]


def test_the_ED_grid_reads_the_LEG_shape_and_never_the_artifact_default():
    """The selection must live where `assumptions_hash()` can see it. A run that fell back on
    the artifact's own `central_shape` would have a second selection site outside the identity
    token — the exact defect this audit round already named for the immigrant inputs — and a
    sweep leg that fell back on it would be swept in NAME and inert in EFFECT."""
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geo, scen = Geography.MTL_RMR, Scenario.REFERENCE
    central = pipeline._ed_series(geo, scen, frames, read, pipeline.CENTRAL_LEG)
    other = pipeline._ed_series(geo, scen, frames, read, dataclasses.replace(
        pipeline.CENTRAL_LEG, headship_shape="expo_cum_fb"))
    assert other != central, (
        "the `expo_cum_fb` leg reproduces the central ED series — the shape argument does not "
        "reach the model, so `rank_stable` would report a verdict over a grid it never varied")
    with pytest.raises(LoaderError, match="shape"):
        pipeline._ed_series(geo, scen, frames, read, dataclasses.replace(
            pipeline.CENTRAL_LEG, headship_shape="expo_cum_nope"))


def test_exactly_ONE_declared_leg_equals_the_central_leg_and_it_is_the_shape_axis():
    """THE ONE DECLARED NO-OP LEG, named so it cannot hide a real one.

    `headship_shape` is a CATEGORICAL axis with exactly two admissible constructions, and the
    central value is one of them — so its `expo_cum_fc` leg IS the central leg, provably rather
    than accidentally. Every OTHER axis is a spec §5 BAND whose endpoints are both off-central,
    and an endpoint that drifted onto its central value would be an inert leg by a different
    route. This test keeps that distinction: one exempt leg, named, and any second one reds.
    """
    identical = [axis for axis, leg in pipeline._sweep_legs() if leg == pipeline.CENTRAL_LEG]
    assert identical == ["headship_shape"], (
        f"declared legs equal to the central leg: {identical} — a numeric endpoint that has "
        "drifted onto its central value is an inert sweep leg")


def test_the_no_op_shape_leg_REUSES_the_central_grid_rather_than_recomputing_it():
    """The bill for adding a twelfth leg, paid where it is provably free: a leg whose
    assumptions are `==` the central leg's cannot produce a different ED grid, so the sweep
    reuses the headline's instead of evaluating 24 more ED series to rediscover it. Asserted
    rather than commented, because a silent reuse is indistinguishable from a dropped leg."""
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geos = [Geography.MTL_RMR]
    central = pipeline._ed_dict(geos, frames, read, pipeline.CENTRAL_LEG)
    calls = []
    real = pipeline._ed_dict
    monkey = lambda g, f, r, a: (calls.append(a), real(g, f, r, a))[1]
    pipeline._ed_dict = monkey
    try:
        pipeline._rank_stability(geos, frames, read, central)
    finally:
        pipeline._ed_dict = real
    assert pipeline.CENTRAL_LEG not in calls, "the no-op shape leg re-evaluated the central grid"
    assert len(calls) == len(pipeline._sweep_legs()) - 1


def test_a_REDUCED_sweep_can_never_certify_rank_stability():
    """THE COST KNOB, AND ITS FAIL-SAFE. Most tests that run the pipeline end to end do not
    care about the robustness verdict, and paying fourteen ED grids for each of them is what
    makes a gate slow enough that people stop running it. `sweep_axes` lets a caller evaluate
    fewer legs — and a run that did not evaluate the DECLARED grid cannot claim a rank is
    stable across it, so every row comes back `False` by construction. The reduction can
    therefore only ever weaken the claim, never manufacture one: the run-32 CRITICAL was a
    `true` shipped over a grid that was never swept, and this closes that door in the one
    place a shortcut could reopen it.

    THE COMMITTED DEFAULT IS THE FULL SET, and `golden.generate_golden` never passes the
    argument — a golden minted from a reduced sweep is the exact defect run 33 existed to
    close."""
    import inspect
    assert inspect.signature(run_pipeline).parameters["sweep_axes"].default is None
    assert "sweep_axes" not in inspect.getsource(__import__(
        "demoflow.golden", fromlist=["generate_golden"]).generate_golden)

    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geos = [Geography.MTL_RMR, Geography.QC_RMR]
    central = pipeline._ed_dict(geos, frames, read, pipeline.CENTRAL_LEG)
    # ...and a reduced sweep publishes NO per-leg count either (amendment #20(C)(2)): it
    # evaluated no leg, and an empty map beside `rank_stable: false` would read as "nothing
    # moved" — the opposite of what a sweep that never ran measured.
    for axes in ((), ("q_live_per_year",)):
        assert pipeline._rank_stability(geos, frames, read, central, sweep_axes=axes) == (
            {g: False for g in geos}, None)
    with pytest.raises(CalibrationError, match="not declared"):
        pipeline._rank_stability(geos, frames, read, central, sweep_axes=("no_such_axis",))
    assert len(pipeline._sweep_legs(("q_live_per_year",))) == 2


# ============================================================================================
# RULINGS X1 / X2 — THE TWO LUMPED READS, WIRED. GOLDEN-INDEPENDENT BY CONSTRUCTION.
# ============================================================================================
#
# WHY THIS SECTION EXISTS, AND WHY IT IS NOT `test_golden.py`. Rulings X1 and X2 changed WHICH
# rate two consumers multiply — the lumped 75+ owner bucket (X1) and the immigrant leg's
# propensity (X2). The run that landed them shipped with NO test that pinned either value:
# reverting `_standing_stock` to `read_ownership(geo, ROLL_AGE)` left the ENTIRE real suite
# green, and reverting `p_nonimm` to a point read inside `P_NONIMM_RANGE` gave 1143 passed /
# 0 failed. Both reverts move every published ED — so a re-minted golden WOULD red on them.
# THAT IS NOT A GATE. `scripts/gen_golden.py` re-mints from whatever the code emits, so a check
# that only fires through the golden ratifies the mutant along with the fix; the golden is the
# RECORD of a ruled number, and these are the gates that decide whether it may be re-minted.
#
# EACH PIN BELOW WAS VERIFIED TO RED UNDER ITS MUTANT WITH THE GOLDEN RE-GENERATED UNDER THAT
# MUTANT, which is the property "the re-mint is self-ratifying" actually being killed:
#   M1  `_standing_stock` reverted to `read_ownership(geo, ROLL_AGE)`
#   M2  `p_nonimm` reverted to a point read inside the span, spelled to evade a literal grep
#   M3  `p_nonimm` as the UNWEIGHTED MEAN of the span's three band rates
# The failing node ids are recorded in the run record, not here: a test naming the mutant it
# catches goes stale the moment the mutant is respelled.
#
# THE VALUES ARE MEASURED ON THE REFERENCE SCENARIO AT EACH FRAME'S OWN FIRST YEAR, which is
# where `_ed_series` takes the standing stock. They are literals rather than recomputations of
# the code under test: a leg that re-derived the population weighting here would pass under any
# weighting the code chose, including a band read.
_X1_STANDING_RATE = {
    "MTL_RMR": 0.5599109544965435,
    "MTL_ISLAND_RA06": 0.5583240006063737,
    "LAVAL_RA13": 0.5592516554435545,
    "QC_RMR": 0.5274919385882947,
    "HORS_RMR": 0.6490440998641852,
    "LANAUDIERE_RA14_PROXY": 0.5618859607833083,
    "LAURENTIDES_RA15_PROXY": 0.5625735734929677,
    "MONTEREGIE_RA16_PROXY": 0.5616690336818816,
}
# WHAT THE REVERT WOULD SERVE — the band read at `ROLL_AGE`, six of the eight rows identical
# because five borrow MTL_RMR's curve and MTL_RMR owns it. Pinned so the non-vacuity leg is a
# MEASUREMENT and not a hope: without it a gate that happened to be reading the point value
# would still be green.
_X1_POINT_READ_AT_ROLL_AGE = {
    "MTL_RMR": 0.5722653000099837,
    "MTL_ISLAND_RA06": 0.5722653000099837,
    "LAVAL_RA13": 0.5722653000099837,
    "QC_RMR": 0.559783363421747,
    "HORS_RMR": 0.6693599636858829,
    "LANAUDIERE_RA14_PROXY": 0.5722653000099837,
    "LAURENTIDES_RA15_PROXY": 0.5722653000099837,
    "MONTEREGIE_RA16_PROXY": 0.5722653000099837,
}
# X2: the span aggregate each geography's immigrant leg multiplies. HORS_RMR's is the
# OPERAND-ALIGNED territory's; the other seven are the census extract's, and the five RA rows
# borrow MTL_RMR's.
_X2_P_NONIMM = {
    "MTL_RMR": 0.5119964493642796,
    "MTL_ISLAND_RA06": 0.5119964493642796,
    "LAVAL_RA13": 0.5119964493642796,
    "QC_RMR": 0.5775769888793841,
    "HORS_RMR": 0.6901488081776652,
    "LANAUDIERE_RA14_PROXY": 0.5119964493642796,
    "LAURENTIDES_RA15_PROXY": 0.5119964493642796,
    "MONTEREGIE_RA16_PROXY": 0.5119964493642796,
}
# THE FORBIDDEN CONSTRUCTION (M3): the unweighted mean of MTL_RMR's three span band rates. Not
# a rate — the bands carry materially different household counts — and off by -1.005 pp.
_X2_FORBIDDEN_RATE_MEAN = 0.5019448407852299


@pytest.fixture(scope="module")
def frames():
    """The loaded input frames, once. Five workbooks and four artifacts per construction."""
    return pipeline._load_all(_DATA)


def _base_year_75plus(frames, geo):
    """The reference-scenario slice `_ed_series` builds the standing stock from."""
    pop = frames.pop[(frames.pop["geography"] == geo)
                     & (frames.pop["scenario"] == Scenario.REFERENCE)]
    return pop[(pop["year"] == int(pop["year"].min()))
               & (pop["age"] >= pipeline.BAND_ENTRY_AGE)]


def test_x1_the_lumped_75plus_bucket_is_valued_at_ITS_OWN_population_weighted_rate(
        frames, monkeypatch):
    """Ruling X1's wiring, caught at the ARGUMENT rather than at the output.

    `_standing_stock` hands `_household_stock` ONE rate for the whole age>=75 slice. Which rate
    that is, is the whole of ruling X1, and it is invisible in every other assertion in this
    suite: the resulting Stock is a plausible household count under either read, and the ED it
    feeds is a plausible ED. So the argument is captured.

    THE NON-VACUITY LEG IS THE ONE THAT MAKES THIS A CHECK. Asserting the captured rate equals
    the population-weighted mean would also pass if the code computed the mean and the mean
    happened to equal the band read. It does not — the pair is pinned — so the second assert
    says the two reads are MEASURABLY different at every geography and names by how much.
    """
    captured = []
    real = pipeline._household_stock
    # `**kw` FORWARDS rather than swallows, so the real call keeps whatever the caller passes —
    # today `direction_ctx`, spec §5's third hard gate (wired 2026-08-22). A fixed positional
    # signature here made this spy the thing that broke when the gate was wired, and a spy that
    # DROPS a kwarg is worse: the wrapped call would run with the gate silently off and every
    # assertion below would still pass.
    monkeypatch.setattr(pipeline, "_household_stock",
                        lambda rows, geo, age, la, ownership, **kw:
                        (captured.append((geo.value, age, ownership)),
                         real(rows, geo, age, la, ownership, **kw))[1])
    read = pipeline._ownership_reader(_DATA)
    for geo in Geography:
        pop = frames.pop[(frames.pop["geography"] == geo)
                         & (frames.pop["scenario"] == Scenario.REFERENCE)]
        captured.clear()
        pipeline._standing_stock(pop, int(pop["year"].min()), geo, frames.la, read,
                                 collective_share=_CENTRAL_COLLECTIVE)
        assert len(captured) == 1, f"{geo.value}: the standing stock is no longer one init call"
        _geo, age, rate = captured[0]
        assert isinstance(rate, float), (
            f"{geo.value}: `_household_stock` was handed {rate!r} rather than a resolved rate — "
            "a callable here means the lumped caller can resolve its own rate from `age`, which "
            "is the defect ruling X1 corrected")
        assert rate == pytest.approx(_X1_STANDING_RATE[geo.value], rel=1e-12), (
            f"{geo.value}: the lumped 75+ bucket is valued at {rate!r}, not the slice's own "
            f"population-weighted mean {_X1_STANDING_RATE[geo.value]}")
        # NON-VACUITY: the band read at `ROLL_AGE` is a different number, and it is the number
        # the ruling X1 revert would serve.
        point = read(geo, pipeline.ROLL_AGE)
        assert point == pytest.approx(_X1_POINT_READ_AT_ROLL_AGE[geo.value], rel=1e-15), (
            f"{geo.value}: the `ROLL_AGE` band read moved — re-derive this pin before trusting "
            "the discrimination below")
        assert rate != pytest.approx(point, rel=1e-9), (
            f"{geo.value}: the lumped rate equals the `ROLL_AGE` band read, so this gate cannot "
            "tell the population-weighted mean from the point read it replaced")
        assert rate < point, (
            f"{geo.value}: the population-weighted mean is no longer BELOW the 75-84 band read — "
            "the measured direction of the narrowing ruling X1 removed has reversed")


def _hors_tail_weightings(frames, read):
    """The three candidate weightings of HORS_RMR's 75+ block, at the row selection
    `_standing_stock` itself makes — and the one the model's own arithmetic picks.

    δ_S is the contamination of the rate S is valued at, and that rate is
    `sum_a pop(a)*rho(a) / sum_a pop(a)` (`_population_weighted_ownership`). The contamination
    moves rho and therefore ONLY THE NUMERATOR, so each band's delta enters δ_S weighted by
    `pop(a)*rho(a)` — the OWNER POPULATION that band contributes — and neither by households
    (a census-2021 count of a different quantity) nor by plain population.
    """
    from demoflow.loaders.hors_aligned import CD_BAND_SPEC

    geo = Geography.HORS_RMR
    # THE SPLIT AGE COMES OFF THE MODEL'S OWN LATTICE, never a literal 85: a blend needs to know
    # which bands it is over, and a lattice refinement that added a third tail band would
    # otherwise be silently folded into two.
    tail = [(label, lo) for label, lo, _hi, *_ in CD_BAND_SPEC if lo >= pipeline.BAND_ENTRY_AGE]
    assert [label for label, _lo in tail] == ["75-84", "85+"], (
        f"the 75+ block is no longer exactly the two lattice bands 75-84 and 85+ ({tail}) — δ_S "
        "is a blend over whatever bands it holds, and this helper splits it at ONE age")
    (lower, _), (upper, split) = tail
    per_age = _base_year_75plus(frames, geo).groupby("age")["population"].sum()
    pop = {lower: 0.0, upper: 0.0}
    owner = {lower: 0.0, upper: 0.0}
    for age, people in per_age.items():
        band = upper if int(age) >= split else lower
        pop[band] += float(people)
        owner[band] += float(people) * read(geo, int(age))
    bands = _aligned_provenance()["bands"]
    hh = {b: bands[b]["aligned_households"] for b in (lower, upper)}
    return {"households": hh[upper] / sum(hh.values()),
            "owner-population": owner[upper] / sum(owner.values()),
            "population": pop[upper] / sum(pop.values())}


def _aligned_provenance():
    from demoflow.loaders.hors_aligned import ARTIFACT
    return json.loads((_DATA / ARTIFACT).read_text(encoding="utf-8"))["_provenance"]


def _reversal_record():
    """The three copies of the #12(B) reversal record that a reader can meet, named."""
    from demoflow.loaders import hors_aligned
    return {"hors_aligned._SUPERSEDES": hors_aligned._SUPERSEDES,
            "the emitted _provenance.supersedes": _aligned_provenance()["supersedes"],
            "hors_aligned.__doc__": hors_aligned.__doc__}


def test_x6_the_tail_ordering_is_a_SERVED_property_and_the_weighting_is_OWNER_POPULATION(frames):
    """Operator ruling X6 (2026-08-21): the two claims the reversal record used to make
    unscoped — that S reads the two LEAST contaminated bands, and that the mediant bound is
    weight-independent — are properties of the SERVED values, and the weighting that decides
    them is the model's own.

    WHY THIS GATE IS IN THIS FILE AND NOT BESIDE THE ARTIFACT'S OTHER GATES. The weighting is
    `pop(a)*rho(a)` over HORS_RMR's base-year 75+ slice: it needs the ISQ population frame and
    the routed ownership reader, which is orchestrator state. A loader-side gate could only
    reach the census HOUSEHOLD counts — and those are the weighting that reports a pass the
    model does not have, which is the whole finding.

    WHAT WOULD HAVE SHIPPED. Two independent reviewers measured this corner with HOUSEHOLD
    weights and reported the S-side blend CLEARING 45-54 by +0.000539 pp. Under the model's own
    owner-population weighting the same corner EXCEEDS 45-54 by 0.0029 pp. The household reading
    is not a rounding difference from the right answer — it is on the other side of the
    inequality, so a household-weighted gate here would have been a FALSE GREEN, and ruling X6
    forbids one. This gate is owner-population weighted for that reason; the single leg below
    that mentions the household reading asserts the DIVERGENCE (the two weightings straddle
    45-54 at this corner), never the household ordering as a pass.

    THE HIGH-CORNER LEG IS A LIMIT TRIPWIRE, NOT A PASS. It asserts that the documented limit is
    still real: if a data refresh moved the 85+ suppression envelope enough for the corner blend
    to fall back below 45-54, the prose would be over-cautious rather than wrong, and it should
    be re-read rather than left standing.
    """
    read = pipeline._ownership_reader(_DATA)
    bands = _aligned_provenance()["bands"]
    weights = _hors_tail_weightings(frames, read)

    # The weights are quoted in prose with no scenario named, so all three scenarios must agree
    # on the base-year 75+ mix or the unqualified figures are reference-only.
    geo = Geography.HORS_RMR
    mixes = set()
    for scen in Scenario:
        pop = frames.pop[(frames.pop["geography"] == geo) & (frames.pop["scenario"] == scen)]
        rows = pop[(pop["year"] == int(pop["year"].min()))
                   & (pop["age"] >= pipeline.BAND_ENTRY_AGE)]
        per_age = rows.groupby("age")["population"].sum()
        mixes.add(tuple(sorted((int(a), float(p)) for a, p in per_age.items())))
    assert len(mixes) == 1, (
        "the three scenarios no longer share HORS_RMR's base-year 75+ age mix, so the weightings "
        "quoted in `hors_aligned`'s prose are REFERENCE-only and must say so")

    served = {b: bands[b]["relative_delta_pct"] for b in ("75-84", "85+")}
    corner = {b: bands[b]["relative_delta_envelope_high_pct"] for b in ("75-84", "85+")}
    next_lowest = bands["45-54"]["relative_delta_pct"]
    assert bands["45-54"]["relative_delta_envelope_low_pct"] == next_lowest == \
        bands["45-54"]["relative_delta_envelope_high_pct"], (
        "45-54 now carries withheld cells, so it is no longer the envelope-INVARIANT band this "
        "comparison is made against and the corner has two moving sides")

    blend = lambda w, d: w * d["85+"] + (1 - w) * d["75-84"]
    # (1) THE SERVED CLAIM, which is the one the record makes and is TRUE at every weighting.
    for name, w in weights.items():
        assert blend(w, served) < next_lowest, (
            f"the SERVED tail blend under {name} weighting is {blend(w, served)}, no longer below "
            f"45-54's {next_lowest} — the mediant argument's served form has stopped holding")
    # (2) THE LIMIT, at the model's own weighting: the corner ordering is NOT weight-free.
    op = blend(weights["owner-population"], corner)
    assert op > next_lowest, (
        f"at the 85+ envelope-HIGH corner the owner-population-weighted blend is {op}, no longer "
        f"ABOVE 45-54's {next_lowest} — the limit `hors_aligned` documents has gone stale and the "
        "prose should be re-read, not left standing")
    # (3) THE DIVERGENCE — the reason a household-weighted gate here is forbidden. This asserts
    # that the two weightings sit on OPPOSITE sides of 45-54 at this corner; it never asserts
    # the household ordering as a pass.
    hh = blend(weights["households"], corner)
    assert hh < next_lowest < op, (
        f"the household-weighted corner blend {hh} and the owner-population one {op} no longer "
        f"straddle 45-54's {next_lowest} — `hors_aligned` says a household-weighted check here "
        "reports a pass the model does not have, and that is now a different statement")

    # (4) EVERY FIGURE THE PROSE QUOTES FOR THIS, in all three copies of the record — bound to
    # the LABEL it belongs to and to nothing else. See `tests/_prose_binding.py` for why the
    # retired `assert figure in flat` form is not a gate: with every figure merely PRESENT,
    # swapping the household and owner-population share labels shipped GREEN (measured
    # 2026-08-21), which leaves the record naming the HOUSEHOLD share as the model's own
    # weighting — the exact falsehood ruling X6 was issued about. The three maps below are
    # asserted as EQUALITIES over a CLOSED label universe, so a transposition moves a value to
    # the wrong key, a deletion empties one, and an added false attribution puts a second value
    # under one. All three red.
    #
    # THE THREE FIGURE KINDS ARE KEPT APART because a band label carries two of them: `85+`
    # states a signed contamination (+0.253%) and an unsigned share of the 75+ block (24.147%).
    shares = {"the household 85+ share": r"(?<!-)(?<!owner )households",
              "the plain-population 85+ share": r"(?<!-)population",
              "the owner-population 85+ share (the model's own weighting)":
                  r"own weighting `?85\+`?"}
    want_shares = {"the household 85+ share": {f"{100 * weights['households']:.3f}%"},
                   "the plain-population 85+ share": {f"{100 * weights['population']:.3f}%"},
                   "the owner-population 85+ share (the model's own weighting)":
                       {f"{100 * weights['owner-population']:.3f}%"}}
    # Every band the record attributes a contamination to, plus the two BLENDS by their role
    # names. Bands the record states no figure for are asserted to state none — that is the
    # exclusivity leg, and it is what makes an ADDED attribution red.
    bands_pct = {b: rf"`?{re.escape(b)}`?" for b in
                 ("25-34", "35-44", "45-54", "55-64", "65-74", "75-84", "85+")}
    bands_pct["the 85+ envelope-HIGH corner (`alone rises to`)"] = r"alone rises to"
    bands_pct["the owner-population high-corner blend"] = r"high-corner blend is"
    want_pct = {b: set() for b in bands_pct}
    for b in ("25-34", "45-54", "75-84", "85+"):
        want_pct[b] = {f"+{bands[b]['relative_delta_pct']:.3f}%"}
    want_pct["the 85+ envelope-HIGH corner (`alone rises to`)"] = {f"+{corner['85+']:.3f}%"}
    want_pct["the owner-population high-corner blend"] = {f"+{op:.3f}%"}
    # The two pp clearances, each bound to the WEIGHTING WHOSE READING IT IS. Transposing them
    # IS the X6 falsehood — and naming the roles by the VERB alone did not gate it: measured
    # GREEN 2026-08-21, moving the two SUBJECTS instead of the two figures left all three maps
    # on this page unchanged (every figure stays on its own role phrase) while the sentence
    # became "the HOUSEHOLD-weighted corner blend EXCEEDS 45-54 by 0.0029 pp; the high-corner
    # blend is +0.276%, which clears 45-54 by 0.0005 pp" — ruling X6 exactly inverted, with the
    # household weighting doing the excluding and the model's own weighting reporting the pass
    # it does not have. The subject is therefore INSIDE the label: whoever EXCEEDS must be the
    # high-corner blend, and whoever CLEARS must be the household-weighted one.
    clearance = {"the corner blend's excess over 45-54 (the model's own weighting)":
                     r"high-corner blend is [+-]\d+\.\d+%, which EXCEEDS 45-54 by",
                 "the household reading's false clearance":
                     r"HOUSEHOLD-weighted corner blend clears 45-54 by"}
    want_clearance = {"the corner blend's excess over 45-54 (the model's own weighting)":
                          {f"{op - next_lowest:.4f} pp"},
                      "the household reading's false clearance":
                          {f"{next_lowest - hh:.4f} pp"}}

    # THE SCOPE QUALIFIER, REQUIRED ON THE CLAIM IT SCOPES rather than pooled over the copy.
    # `assert "AT SERVED VALUES" in flat` stood here and is not a gate either: the phrase occurs
    # TWICE in every copy, so dropping it from the FIRST — the tail-ordering claim — shipped
    # GREEN and left the record making the unscoped claim X6 forbids. Each row below requires
    # the JOINED form at least once AND forbids the claim's keywords appearing UNSCOPED, which
    # is the per-occurrence form of the same requirement and does not depend on a count.
    # THE FORBID HALF OF EACH ROW IS MATCHED CASE-INSENSITIVELY (run 48). These patterns
    # spell their subjects in emphasis capitals because that is how the record writes them, and
    # a case-sensitive forbid therefore misses the SAME claim typed the other way — an ADDITIVE
    # unscoped "the arrangement is weight-independent, full stop" beside the correctly scoped
    # sentence satisfied all three rows. The REQUIRED half stays case-SENSITIVE: it asserts the
    # record's own spelling of the scope qualifier, and relaxing it would let the qualifier
    # arrive in a casing the rest of these gates do not recognise. The `(?:LEAST|least)`
    # alternation the first row used to carry is folded into the flag.
    scoped = (
        ("the tail-ordering claim (S reads the two least contaminated bands)",
         r"two\s+(?:LEAST|least)\s+contaminated\s+AT SERVED VALUES",
         r"two\s+least\s+contaminated(?!\s+AT SERVED VALUES)"),
        ("the mediant / weight-independence claim",
         r"WEIGHT-INDEPENDENT AT SERVED VALUES"
         r"|AT SERVED VALUES the argument does not depend on a weighting",
         r"WEIGHT-INDEPENDENT(?! AT SERVED VALUES)"
         r"|(?<!AT SERVED VALUES )the argument does not depend on a weighting"),
        ("the interval claim (the whole interval sits below 45-54)",
         r"whole SERVED interval", r"whole interval"),
    )

    for where, text in _reversal_record().items():
        flat_text = flat(text)
        for what, labels, want, figure, glue in (
                ("the three 85+ weighting shares", shares, want_shares, PCT_PLAIN, {}),
                ("the band contaminations and the corner blends", bands_pct, want_pct,
                 PCT_SIGNED, {}),
                ("the two 45-54 clearances", clearance, want_clearance, PP_ABS,
                 {"after": r" ", "before": None})):
            observed = bound_map(flat_text, labels, figure, **glue)
            assert observed == want, (
                f"{where} does not attribute {what} the way this run measures them. It binds "
                f"{ {k: sorted(v) for k, v in observed.items() if v != want[k]} }; measured "
                f"{ {k: sorted(v) for k, v in want.items() if v != observed[k]} }. A figure "
                "present but attached to the WRONG label, a dropped one, and a true set with a "
                "FALSE pair added all land here — ruling X6 is about the attribution, not the "
                "digits")
        # THE DIRECTION OF THE HIGH-CORNER READING **AND WHOSE CORNER IT IS**, in ONE clause.
        # The map above binds +0.384% to `alone rises to` and says NOTHING about which side of
        # 45-54 it lands on, so "alone rises to +0.384%, BELOW 45-54" shipped GREEN (measured
        # 2026-08-21) while contradicting leg (2)'s own `op > next_lowest`. ABOVE is the entire
        # content of the sentence — it is the reason the ordering is not weight-free there.
        #
        # AND THE SUBJECT IS INSIDE THE CLAUSE, which the first cut of this gate left out. The
        # required span STARTED after the band name, so the band was context rather than part
        # of the example: RELABELLING it in both source copies to "at the suppression HIGH
        # corner 75-84 alone rises to +0.384%, ABOVE 45-54" shipped the FULL SUITE GREEN
        # (measured 2026-08-21) while stating the opposite of the ruling. 75-84's suppression is
        # ONE-SIDED — its envelope is [low, served] at +0.242% — and 85+'s TWO-SIDED
        # suppression is the entire reason the ordering is not weight-free at the corner, so
        # the relabelled sentence is contradicted by this same docstring two lines later and by
        # the artifact. Same defect and same cure as the ED-move gate's: the band is named ONCE
        # below and both the figure lookup and the required clause read that one name.
        corner_band = "85+"
        rises = (rf"corner `?{re.escape(corner_band)}`? alone rises to "
                 rf"{re.escape(f'+{corner[corner_band]:.3f}%')}, ABOVE 45-54")
        assert re.search(rises, flat_text), (
            f"{where} no longer states the envelope-high corner as `corner {corner_band} alone "
            f"rises to +{corner[corner_band]:.3f}%, ABOVE 45-54` (backticks around the band are "
            "optional — the docstring writes them, the emitted copy does not). Three things sit "
            "in that one span: WHOSE corner it is, the figure, and the DIRECTION. Another band "
            "there is false — only 85+ is suppressed on BOTH sides — and BELOW contradicts leg "
            "(2) of this same test")
        # THE HOUSEHOLD-WEIGHTED TAIL BLEND AND THE TWO COUNTS IT IS FORMED AT, in ONE ordered
        # clause — IN EVERY COPY. This assert stood in `tests/test_hors_aligned_ownership.py`
        # against `hors_aligned.__doc__` ALONE, and the clause is hard-wrapped differently in
        # the three copies, so that one anchor reached one of them: a COORDINATED swap of the
        # two counts in `_SUPERSEDES` and in the emitted `_provenance.supersedes` shipped GREEN
        # (measured 2026-08-21 through the generator, so the twin-equality and byte-for-byte
        # gates were satisfied too), leaving the PUBLISHED record forming the blend at 85+'s
        # count first. This loop already iterates all three copies, which is the whole reason
        # the clause belongs here.
        tail_counts = [bands[b]["aligned_households"] for b in ("75-84", "85+")]
        count_blend = (sum(c * served[b] for c, b in zip(tail_counts, ("75-84", "85+")))
                       / sum(tail_counts))
        counts_clause = (f"aligned household counts {tail_counts[0]:,} / {tail_counts[1]:,}, "
                         f"is +{count_blend:.3f}%")
        assert counts_clause in flat_text, (
            f"{where} no longer states the household-weighted tail blend BOUND to the counts it "
            f"is formed at — expected the contiguous clause {counts_clause!r}, with 75-84's "
            "count FIRST. Both digit strings survive a swap, so presence is not this claim")
        for claim, joined, unscoped in scoped:
            assert re.search(joined, flat_text), (
                f"{where} no longer states {claim} with its scope ATTACHED — ruling X6 is that "
                "the mediant bound is a property of the SERVED values, so the qualifier has to "
                "sit on the claim it scopes and not merely somewhere in the same record")
            assert not re.findall(unscoped, flat_text, re.IGNORECASE), (
                f"{where} states {claim} UNSCOPED: "
                f"{re.findall(unscoped, flat_text, re.IGNORECASE)!r}. At the "
                "85+ envelope-high corner that band alone rises above 45-54, so the claim is "
                "false without `AT SERVED VALUES` on it — and another, scoped, occurrence of "
                "the qualifier elsewhere in the record does not repair this one")
        # AND WHICH SIDE OF 45-54 THAT INTERVAL SITS ON. The scope leg above requires the words
        # "whole SERVED interval" and says NOTHING about the DIRECTION, so "sits below the
        # next-lowest band" -> "sits above" shipped the FULL SUITE GREEN in all three copies
        # (measured 2026-08-21, regenerated through `gen_hors_aligned.py` then `gen_golden.py`,
        # so the artifact, byte-for-byte and vintage gates were satisfied as well). BELOW is the
        # ordering conclusion rulings X1 and X6 BOTH rest on — "S reads the two LEAST
        # contaminated" bands IS the claim that the served interval sits under every other band —
        # so ABOVE hands a future reader the refutation dressed as the finding, with the scope
        # qualifier still correctly attached to it. The word is DERIVED from leg (1)'s own
        # measurement, and 45-54 is named in the span because a relabelling there is the same
        # one-word inversion by another route.
        side = "below" if max(served.values()) < next_lowest else "above"
        interval = f"sits {side} the next-lowest band, 45-54 at +{next_lowest:.3f}%"
        assert interval in flat_text, (
            f"{where} no longer states which side of 45-54 the whole SERVED interval sits on — "
            f"expected the contiguous clause {interval!r}. The direction is the conclusion, not "
            f"decoration: leg (1) of this test measures every served tail blend BELOW 45-54's "
            f"+{next_lowest:.3f}%, and that ordering is what the adverse-arrangement argument "
            "and ruling X6's mediant bound are both built on")
        # THE DERIVATION'S OWN PIVOT WORD. δ_S's weighting is forced by WHICH HALF of
        # Σ_a pop(a)·ρ(a) / Σ_a pop(a) the contamination moves, and the record says the
        # NUMERATOR — which is what makes each band delta enter weighted by pop(a)·ρ(a).
        # NOTHING held that word: swapping it to DENOMINATOR in both source copies and
        # regenerating shipped the FULL SUITE GREEN (measured 2026-08-21). With the denominator
        # moving instead, the weighting derived is plain POPULATION — precisely the reviewers'
        # error ruling X6 exists to correct, handed to the reader as the record's own reasoning,
        # and the conclusion clause below still standing so the record is CONTRADICTORY rather
        # than uniformly false. One word, and it is the load-bearing one.
        assert "the contamination moves only its NUMERATOR" in flat_text, (
            f"{where} no longer derives the weighting from the NUMERATOR of "
            "Σ_a pop(a)·ρ(a) / Σ_a pop(a). That word is the derivation: only the numerator "
            "moving makes the weight pop(a)·ρ(a); a DENOMINATOR there derives plain "
            "population, which is the weighting ruling X6 was issued to refuse")
        assert "never by households and never by plain population" in flat_text, (
            f"{where} no longer names the weighting δ_S is forced to (owner households, "
            "pop(a)*rho(a)) — that omission is what let two reviewers weight it by households")
        # RESTORED-FORM FORBIDS, CASE-FOLDED — with ONE deliberate exception, and the
        # exception is the reason this list is not simply routed through `says` (run 48).
        # Three of these four are retired UNSCOPED sentences that appear nowhere in the
        # ratified record in any casing, so folding case costs nothing and closes the emphasis
        # rewrite. `S reads the TWO LEAST` is different: its LIVE, CORRECT successor is written
        # `S reads the two least contaminated AT SERVED VALUES` in `hors_aligned.__doc__` —
        # the same words, lower-cased and SCOPED — so a case-folded bare substring REDS ON THE
        # SENTENCE THE RECORD IS SUPPOSED TO SAY (measured on the ratified bytes). Its real
        # discriminator was never the casing; it is the SCOPE QUALIFIER, so it carries the same
        # negative lookahead the `scoped` rows above use and is matched case-insensitively like
        # them. A forbid that cannot let the record state its own corrected claim is a tax an
        # author deletes, and the deletion is what actually loses the guard.
        for retired in (r"the argument no longer depends on a weighting",
                        r"S reads the TWO LEAST(?!\s+contaminated\s+AT SERVED VALUES)",
                        r"the whole interval sits below the next-lowest band",
                        r"arrangement is therefore WEIGHT-INDEPENDENT rather than weaker"):
            assert not re.search(retired, flat_text, re.IGNORECASE), (
                f"{where} has restored the UNSCOPED form {retired!r} — at the 85+ high corner "
                "that band alone rises above 45-54, so the ordering is not weight-free there")


def test_x7_the_band_difference_is_MEASURED_and_is_not_the_FULL_spread(frames):
    """Operator ruling X7 (2026-08-21): δ_D − δ_S is a LARGE, same-signed fraction of the band
    spread — measured, not the whole of it. The record said "at or near the FULL spread".

    THE SUPERLATIVE WAS NEVER MEASURED. Probe P10 read it off the ARRANGEMENT (most contaminated
    band on the D side, least on the S side) and said so: it "leaves the consequence sized by a
    quantity outside the probe". Ruling W then split the coarse 25-54 band into three, and only
    ONE of the three carries the +3.559% — so on the current lattice δ_D is a weighted mean over
    five bands, four of which are near the bottom of the range, and the difference lands near
    three fifths of the spread rather than at its top.

    δ_D IS COMPUTED BY ITS DEFINITION AND THROUGH PRODUCTION CODE. It is ΔD/D — the symbol the
    ΔED/ED identity uses — so `native_formation` is called twice per projected year, once with
    the operand-aligned curve HORS_RMR is served and once with the census-net curve it would have
    read under #12(B), and the pooled relative move is δ_D. Re-implementing the formation gain
    loop here would put a second, drifting copy of the D-side weights in the suite; the whole
    point of the figure is that it is the weighting the model actually forms.

    THE REVERSAL IS UNAFFECTED AND THAT IS ASSERTED, not asserted away: #12(B)'s premise is
    band-UNIFORMITY, which needs the difference to be large, same-signed and adversarially
    arranged — never maximal. It is ~2.0 pp at BOTH suppression corners.
    """
    from demoflow.demand.formation import native_formation
    from demoflow.demand.i2 import assert_p_resident_nonneg, p_resident
    from demoflow.loaders.hors_aligned import CD_BAND_SPEC

    geo = Geography.HORS_RMR
    prov = _aligned_provenance()
    bands = prov["bands"]
    read = pipeline._ownership_reader(_DATA)

    def curve(field):
        return {age: bands[label][field] for label, lo, hi, *_ in CD_BAND_SPEC
                for age in range(lo, min(hi, 100) + 1)}

    aligned, shipped = curve("aligned_rate"), curve("shipped_rate")
    assert sorted(aligned) == list(range(25, 101)), (
        f"the reconstructed curve no longer spans the pipeline's own 25..100 lattice: "
        f"{sorted(aligned)[:3]}..{sorted(aligned)[-3:]}")
    assert all(aligned[a] == read(geo, a) for a in aligned), (
        "the ALIGNED arm is not the curve the model actually serves HORS_RMR, so this measures "
        "the contamination of something else")
    assert any(shipped[a] != aligned[a] for a in aligned), (
        "the two curves are identical, so this test cannot measure a contamination at all")

    pop_g_s = frames.pop[(frames.pop["geography"] == geo)
                         & (frames.pop["scenario"] == Scenario.REFERENCE)]
    compo = frames.compo[(frames.compo["geography"] == geo)
                         & (frames.compo["scenario"] == Scenario.REFERENCE)]
    years = pipeline._projected_years(pop_g_s)
    shape = pipeline.headship_curve(frames.headship, pipeline.CENTRAL_LEG.headship_shape)
    headship = {a: pipeline.headship_rate(shape, a) for a in range(0, 101)}

    def resident(year):
        by_age = pipeline._pop_by_age(pop_g_s, year, ctx=f"{geo.value}/{year}")
        p_isq = sum(by_age.values())
        surviving = pipeline._surviving_arrivals(compo, year, ctx=f"{geo.value}/{year}")
        p_res = assert_p_resident_nonneg(p_resident(p_isq, surviving),
                                         ctx=f"{geo.value}/{year}")
        return {a: p * (p_res / p_isq) for a, p in by_age.items()}

    d_aligned = d_shipped = 0.0
    resident_tm1 = resident(years[0] - 1)
    for t in years:
        resident_t = resident(t)
        d_aligned += native_formation(resident_t, resident_tm1, headship, aligned)
        d_shipped += native_formation(resident_t, resident_tm1, headship, shipped)
        resident_tm1 = resident_t
    assert d_shipped > 0.0, "D_native pooled to zero — there is nothing to take a ratio of"
    delta_d = 100 * (d_aligned - d_shipped) / d_shipped

    weights = _hors_tail_weightings(frames, read)
    served = {b: bands[b]["relative_delta_pct"] for b in ("75-84", "85+")}
    corner = {b: bands[b]["relative_delta_envelope_high_pct"] for b in ("75-84", "85+")}
    blend = lambda w, d: w * d["85+"] + (1 - w) * d["75-84"]
    # δ_S at the model's own weighting AND at the household weighting the record also quotes:
    # the SERVED reading is insensitive to the choice at the precision the prose states, and
    # that insensitivity is asserted rather than assumed.
    delta_s = blend(weights["owner-population"], served)
    assert f"+{delta_s:.3f}%" == f"+{blend(weights['households'], served):.3f}%", (
        "the served tail blend now renders differently under owner-population and household "
        "weighting, so `+0.244%` no longer stands for both and the prose must name which")
    spread = prov["suppression"]["envelope"]["band_spread_pp"]["at_served_corner"]
    diff = delta_d - delta_s
    fraction = 100 * diff / spread
    corner_diff = delta_d - blend(weights["owner-population"], corner)

    # THE CLAIM, as an interval rather than a point: large, same-signed, and NOT the spread.
    assert 0.4 * spread < diff < 0.8 * spread, (
        f"δ_D − δ_S is {diff} pp against a {spread} pp spread ({fraction:.1f}%) — outside the "
        "band this record's corrected quantifier describes; re-measure before re-wording")
    assert diff > 0 and corner_diff > 0, (
        f"δ_D − δ_S has changed sign at a suppression corner (served {diff}, corner "
        f"{corner_diff}) — the adverse arrangement, not just its size, would need re-measuring")
    assert f"{diff:.1f}" == f"{corner_diff:.1f}" == "2.0", (
        f"the difference is no longer ~2.0 pp at BOTH corners (served {diff}, 85+ high corner "
        f"{corner_diff}) — that pair is what the record states as the reversal's warrant")

    # THE FRACTION IS PUBLISHED AT WHOLE PERCENT, and that is a precision decision rather than
    # a rounding habit: at one decimal it moves between the two δ_S weightings this record
    # itself calls immaterial (60.2% owner-population against 60.3% household), so a 1-dp figure
    # would read as stale to anyone who recomputed it the other way — the drift ruling X5 exists
    # to prevent. The inputs (+2.243%, +0.244%, 1.999 pp) are stable at the precision quoted.
    hh_fraction = 100 * (delta_d - blend(weights["households"], served)) / spread
    assert f"{fraction:.0f}" == f"{hh_fraction:.0f}", (
        f"the fraction of the spread now differs at WHOLE percent between the owner-population "
        f"({fraction}) and household ({hh_fraction}) weightings of δ_S — the record publishes one "
        "figure for both and would have to name which")

    # THE RETIRED SUPERLATIVE cannot come back into the two copies that ASSERT the current
    # reading. The module docstring is excluded on purpose and checked differently below: its
    # four-band history paragraph QUOTES the phrase as P10's words, which is the attribution
    # ruling X7 asked for and not a restoration.
    for where in ("hors_aligned._SUPERSEDES", "the emitted _provenance.supersedes"):
        flat = " ".join(_reversal_record()[where].split())
        assert "at or near the full spread" not in flat.lower(), (
            f"{where} has restored the superlative ruling X7 struck. It was read off the "
            f"arrangement and never measured; measured, the difference is {fraction:.0f}% of the "
            "spread")
        # THE FOUR JOINED PHRASES, each asserted as the ONLY value its role name carries. The
        # phrases were already label-bound, which defeats a transposition; what a bare `in`
        # leaves open is the ADDITIVE falsehood — keeping "a difference of 1.999 pp" and adding
        # "a difference of 2.500 pp" beside it satisfies presence. `set(...) == {measured}` does
        # not, and it makes a DELETION red as `set()` rather than as a missing substring.
        for what, pattern, measured in (
                ("δ_D = ΔD/D on the reference projected years",
                 r"δ_D = ΔD/D = \+(\d+\.\d+)%", f"{delta_d:.3f}"),
                ("the measured band difference",
                 r"a difference of (\d+\.\d+) pp", f"{diff:.3f}"),
                ("the difference as a fraction of the spread",
                 r"(\d+)% OF THAT SPREAD", f"{fraction:.0f}"),
                ("the served band spread",
                 r"the (\d+\.\d+) pp served spread", f"{spread:.3f}")):
            # IGNORECASE (run 48): every one of these role phrases is prose, so an added
            # FALSE pair written "A DIFFERENCE OF 9.999 PP" or "99% of that spread" was
            # invisible to the set-equality this leg is built on and shipped beside the true
            # one — the additive falsehood the `set(...) == {measured}` shape exists to refuse.
            found = set(re.findall(pattern, flat, re.IGNORECASE))
            assert found == {measured}, (
                f"{where} attaches {sorted(found)} to {what}; this run measures {measured}. A "
                "second value under the same role name is an ADDED attribution, not a second "
                "quotation — every mention has to carry the measured figure")
        # EVERY figure this record attaches to δ_D or δ_S, not merely one of them. A
        # presence-only check ("+2.243% appears somewhere") passes a record that states the
        # measured value once and a stale one beside it — the same presence-vs-attribution hole
        # the X3 recurrence found in the offset gate, and this gate had it until it was mutation-
        # tested (2026-08-21: swapping the FIRST occurrence for the other candidate construction
        # left the gate green, because the second occurrence still carried the right digits).
        for symbol, value in (("δ_D", delta_d), ("δ_S", delta_s)):
            found = re.findall(rf"{symbol}[^%]{{0,20}}\+(\d+\.\d+)%", flat)
            assert found, f"{where} states no percentage figure for {symbol} at all"
            assert set(found) == {f"{value:.3f}"}, (
                f"{where} attaches {sorted(set(found))} to {symbol}; the measured value is "
                f"{value:.3f}% and every mention has to carry it")
    doc = " ".join(_reversal_record()["hors_aligned.__doc__"].split())
    if "at or near the FULL spread" in doc:
        assert ('The superlative was READ OFF THE ARRANGEMENT and never measured against '
                "`D_native`'s own weights") in doc, (
            "the module docstring states the retired superlative without the attribution that "
            "makes it P10's reasoning rather than this run's measurement — either mark it the "
            "way the four-band history paragraph does, or drop the phrase")


def test_x1_the_borrowed_ownership_curve_no_longer_pins_its_rows_in_lockstep(frames):
    """The property that only a POPULATION-weighted read can have, asserted as a property.

    Five geographies borrow MTL_RMR's ownership curve and MTL_RMR owns it, so all SIX rows read
    identical band rates — under the retired point read they were pinned to one number
    (0.5722653000099837) and their 75+ age composition, which is the one thing a borrowed rate
    row does not flatten, could not reach S at all. It reaches it now.

    THIS LEG SURVIVES A DATA REFRESH where the value pins above would need re-deriving, which is
    why it is separate: it asserts DISTINCTNESS and an ordering, not magnitudes.
    """
    read = pipeline._ownership_reader(_DATA)
    curve_rows = [Geography.MTL_RMR, *census._BORROWS_FROM]
    assert len(curve_rows) == 6, f"the MTL-curve row set moved: {curve_rows}"
    rates = {}
    for geo in curve_rows:
        rows = _base_year_75plus(frames, geo)
        rates[geo.value] = pipeline._population_weighted_ownership(
            rows, geo, read, ctx=f"{geo.value} test")
        assert read(geo, pipeline.ROLL_AGE) == read(Geography.MTL_RMR, pipeline.ROLL_AGE), (
            f"{geo.value} no longer reads MTL_RMR's curve — this test's premise is gone")
    assert len(set(rates.values())) == len(rates), (
        f"the six rows reading MTL_RMR's curve are pinned in lockstep again: {rates} — a point "
        "read inside the 75+ block cannot differentiate them, so S has stopped seeing each "
        "geography's own 75+ age composition")
    assert max(rates.values()) < read(Geography.MTL_RMR, pipeline.ROLL_AGE), (
        "every row's blend must sit below the 75-84 band rate the point read served")


def test_x1_an_empty_75plus_slice_REFUSES_rather_than_dividing_zero_by_zero(frames):
    """`_population_weighted_ownership`'s refusal branch, which nothing reached.

    0/0 has no rate, and any default would value the whole bucket at a rate no age in it
    published — the silent-zero door this codebase closes everywhere else.
    """
    read = pipeline._ownership_reader(_DATA)
    rows = _base_year_75plus(frames, Geography.MTL_RMR)
    empty = rows.assign(population=0.0)
    with pytest.raises(CalibrationError, match="population-weighted ownership"):
        pipeline._population_weighted_ownership(empty, Geography.MTL_RMR, read, ctx="probe")
    with pytest.raises(CalibrationError, match="population-weighted ownership"):
        pipeline._population_weighted_ownership(rows.iloc[0:0], Geography.MTL_RMR, read,
                                                ctx="probe")


def test_x2_the_immigrant_legs_propensity_is_the_SPAN_aggregate_at_every_geography():
    """Ruling X2's value, at the object the ED path actually asks.

    THE NEGATIVE LEGS ARE THE GATE. Every candidate here is a plausible ownership fraction, so
    the wrong construction does not announce itself. Three are named and forbidden: any single
    band rate from inside the span (the pre-X2 point read, which under ruling W's split resolves
    to a sub-band rather than the span), the unweighted mean of the span's band rates, and — for
    HORS_RMR — the CENSUS-NET territory's union, which `_ownership_reader` deliberately does not
    carry.
    """
    read = pipeline._ownership_reader(_DATA)
    lo, hi = pipeline.P_NONIMM_RANGE
    assert (lo, hi) == (25, 54), f"P_NONIMM_RANGE moved to {(lo, hi)} — re-derive these pins"
    band_labels = [b[0] for b in census.bands_spanning(lo, hi)]

    for geo in Geography:
        served = read.p_nonimm(geo)
        assert served == pytest.approx(_X2_P_NONIMM[geo.value], rel=1e-15), geo.value
        curve = read.aligned if read.reads_aligned(geo) else read.shipped
        inside = [curve[geo.value][label] for label in band_labels]
        assert served not in inside, (
            f"{geo.value}: the immigrant leg is served {served}, one of its own span band rates "
            f"{inside} — a point read inside the span, which is what ruling X2 removed")
        mean_of_rates = sum(inside) / len(inside)
        assert served != pytest.approx(mean_of_rates, rel=1e-9), (
            f"{geo.value}: the immigrant leg is served the unweighted MEAN of its span band "
            f"rates ({mean_of_rates}) — a mean of rates is not a rate")
    # THE HARDCODED SET-MEMBERSHIP TWIN OF THE LOOP ABOVE WAS DELETED HERE (2026-08-21 audit):
    #   assert _X2_FORBIDDEN_RATE_MEAN not in {read.p_nonimm(g) for g in Geography}
    # It could not fail while the `rel=1e-15` value pin at the top of the loop passed: the CLOSEST
    # served union sits 1.963e-02 relative from the literal (MTL_RMR's 0.5119964493642796 against
    # 0.5019448407852299) — about 13 orders of magnitude outside that tolerance — so set
    # non-membership was entailed by the pins rather than checked, at every one of the eight rows.
    # THE LOAD-BEARING LEGS ARE THE LIVE-COMPUTED ONES
    # INSIDE THE LOOP — `served not in inside` and `served != approx(mean_of_rates)` — because
    # they re-derive the forbidden constructions from the curve each geography actually reads
    # instead of comparing against one geography's frozen number; those two are what caught
    # mutation M3, and they keep discriminating after a data refresh moves every pin here.
    #
    # THE LITERAL IS RE-SITED, NOT DROPPED: it now anchors the forbidden construction's own value
    # so the live leg is a MEASUREMENT and not a hope — the same shape
    # `tests/test_census_ownership.py` uses for `_UNION_RATE_MEAN_MTL`.
    mtl = read.shipped[Geography.MTL_RMR.value]
    forbidden_mean = sum(mtl[b] for b in band_labels) / len(band_labels)
    assert forbidden_mean == pytest.approx(_X2_FORBIDDEN_RATE_MEAN, rel=1e-15), (
        f"the forbidden unweighted mean of MTL_RMR's span band rates is now {forbidden_mean}, "
        f"not the pinned {_X2_FORBIDDEN_RATE_MEAN} — re-derive it before trusting the "
        "discrimination in the loop above, and re-derive the -1.005 pp figure below with it")
    # THE -1.005 pp FIGURE both `census.py` and `constants.MODEL_CHOICE_PROVENANCE` restate as
    # the size of the forbidden construction's error, gated so the prose cannot drift off it.
    gap_pp = 100 * (read.p_nonimm(Geography.MTL_RMR) - forbidden_mean)
    assert round(gap_pp, 3) == 1.005, (
        f"the union sits {gap_pp:.4f} pp above the mean of its band rates, not the 1.005 pp "
        "`census.py` and `constants.MODEL_CHOICE_PROVENANCE` both restate")


def test_x2_the_ED_path_CONSUMES_the_readers_p_nonimm_and_never_an_age_read(frames):
    """The consumption twin of the value test above — the B8 idiom, for the reason it exists.

    A mutant that puts `read_ownership(geo, <some age in the span>)` back inside `_ed_series`
    leaves `p_nonimm` answering correctly and every value leg above GREEN, because the reader
    object is still right; only the CALLER changed. Two legs close that, and neither depends on
    how the mutant is spelled:

      1. CALL — `_ed_series` must ask the reader for the aggregate at least once per series. A
         bypass stops asking.
      2. PERTURBATION — a reader whose `p_nonimm` returns a different value must MOVE the series.
         A bypass ignores it and the series is byte-identical, which is the assertion that fails.

    Leg 2 is the load-bearing one: leg 1 alone would pass a mutant that called `p_nonimm` and
    then threw the answer away.
    """
    read = pipeline._ownership_reader(_DATA)

    calls = []
    class Counting:
        def __call__(self, geo, age):
            return read(geo, age)
        def reads_aligned(self, geo):
            return read.reads_aligned(geo)
        def p_nonimm(self, geo):
            calls.append(geo.value)
            return read.p_nonimm(geo)

    baseline = pipeline._ed_series(Geography.MTL_RMR, Scenario.REFERENCE, frames, read,
                                   pipeline.CENTRAL_LEG)
    counted = pipeline._ed_series(Geography.MTL_RMR, Scenario.REFERENCE, frames, Counting(),
                                  pipeline.CENTRAL_LEG)
    assert calls == ["MTL_RMR"], (
        f"`_ed_series` asked the reader for the `P_NONIMM_RANGE` aggregate {calls} times — a "
        "consumer that stopped asking is reading the propensity somewhere else")
    assert counted == baseline

    class Shifted(Counting):
        def p_nonimm(self, geo):
            return read.p_nonimm(geo) * 1.01

    shifted = pipeline._ed_series(Geography.MTL_RMR, Scenario.REFERENCE, frames, Shifted(),
                                 pipeline.CENTRAL_LEG)
    assert shifted != baseline, (
        "moving the reader's `P_NONIMM_RANGE` aggregate by 1% left the ED series IDENTICAL — "
        "the immigrant leg is reading its propensity from somewhere other than `p_nonimm`, "
        "which is ruling X2's defect restored (the value tests cannot see this: the reader "
        "still answers correctly, it is just no longer being asked)")


def test_x2_the_reader_REFUSES_a_span_aggregate_it_was_never_HANDED():
    """`_OwnershipReader.p_nonimm`'s refusal, and the wrong-territory door `_ownership_reader`
    shuts.

    TWO DIFFERENT REFUSALS, both hand-written and neither reached before. A reader built for the
    join-contract tests carries no unions at all and must not fall back to a band read. And a
    geography the join sends to the ALIGNED curve carries no shipped union by construction (see
    `_ownership_reader`), so a join re-point hits this refusal instead of silently serving a rate
    measured over the census-net territory — the ~1 pp wrong-territory error the whole
    operand-alignment surface exists to remove.
    """
    read = pipeline._ownership_reader(_DATA)
    bare = pipeline._OwnershipReader(read.shipped, read.aligned, read.join)
    for geo in Geography:
        with pytest.raises(LoaderError, match="ownership union"):
            bare.p_nonimm(geo)

    assert Geography.HORS_RMR.value not in read.shipped_union, (
        "the census-net span union is carried on the shipped route again")
    assert set(read.shipped_union) == {g.value for g in Geography
                                       if not read.reads_aligned(g)}, (
        "the shipped union map is no longer exactly the rows the join sends to the shipped "
        "curve — it is pruned BY THE JOIN, never by naming a geography")
    repointed = {geo: dict(row) for geo, row in read.join.items()}
    repointed[Geography.HORS_RMR.value]["reads"] = "shipped"
    drifted = pipeline._OwnershipReader(read.shipped, read.aligned, repointed,
                                        read.shipped_union, read.aligned_union)
    with pytest.raises(LoaderError, match="ownership union"):
        drifted.p_nonimm(Geography.HORS_RMR)
    # ... and every other geography still answers, so the refusal is scoped and not a blanket.
    for geo in Geography:
        if geo is not Geography.HORS_RMR:
            assert drifted.p_nonimm(geo) == pytest.approx(_X2_P_NONIMM[geo.value], rel=1e-15)

    # THE MIRROR LEG, and the asymmetry it closes is why it is here (2026-08-21). Everything
    # above re-points the ALIGNED row to the SHIPPED curve — the direction that already refused,
    # because `_ownership_reader` prunes the shipped union map. The OPPOSITE re-point had no
    # fence at all: `p_nonimm` returned the single `aligned_union` — measured over
    # ALIGNED_GEOGRAPHY's territory ALONE — to ANY geography the join marked aligned, while
    # `__call__` on the same reader REFUSED it through `aligned_ownership_rate`. Measured before
    # the fix: `p_nonimm(LAVAL_RA13)` served 0.6901488081776652 where that row's own span union
    # is 0.5119964493642796, 17.8 pp of wrong territory, on a path evaluated once per (leg,
    # geography, scenario). Reachable today only through a hand-built reader (`hors_aligned._verify_join` refuses
    # a second aligned row at load), which is exactly why it needed a test rather than a reader.
    from demoflow.loaders.hors_aligned import ALIGNED_GEOGRAPHY

    assert ALIGNED_GEOGRAPHY is Geography.HORS_RMR, (
        f"the aligned territory moved to {ALIGNED_GEOGRAPHY.value} — re-derive this leg")
    repointed_up = {geo: dict(row) for geo, row in read.join.items()}
    repointed_up[Geography.LAVAL_RA13.value]["reads"] = "operand_aligned"
    mirrored = pipeline._OwnershipReader(read.shipped, read.aligned, repointed_up,
                                         read.shipped_union, read.aligned_union)
    assert mirrored.reads_aligned(Geography.LAVAL_RA13), "the re-point did not take"
    # BOTH accessors must refuse, and the point of the leg is that they now agree.
    with pytest.raises(LoaderError, match="not re-pointed by the operand-aligned surface"):
        mirrored(Geography.LAVAL_RA13, 40)
    with pytest.raises(LoaderError, match="territory ALONE"):
        mirrored.p_nonimm(Geography.LAVAL_RA13)
    # SCOPED, not a blanket: the one geography the union WAS measured over still answers, and so
    # does every row the join still sends to the shipped curve.
    assert mirrored.p_nonimm(Geography.HORS_RMR) == pytest.approx(
        _X2_P_NONIMM[Geography.HORS_RMR.value], rel=1e-15), (
        "the aligned row itself now refuses — the fence is on the geography, not on the curve")
    for geo in Geography:
        if geo not in (Geography.HORS_RMR, Geography.LAVAL_RA13):
            assert mirrored.p_nonimm(geo) == pytest.approx(_X2_P_NONIMM[geo.value], rel=1e-15)


# (X3 RECURRENCE, 2026-08-21) THE ATTRIBUTION HALF OF THE OFFSET GATE. Until this landed, the
# gate below asked only whether a figure appeared SOMEWHERE in the UNION of the two documents —
# `any(f"{offset:.3f} pp" in d for d in docs)` — which is a PRESENCE test, not an attribution
# one. A verifier shipped two mutations green against that form: (a) swapping four borrower
# offsets between geographies (MTL_ISLAND<->LAVAL, LANAUDIERE<->LAURENTIDES) AND the two
# own-territory offsets (MTL<->QC), leaving the prose reading "-0.636 pp at MTL_RMR
# (0.5599109544965435 against 0.5615325746167329)" — self-contradictory on its own line — and
# (b) stripping all three own-territory offsets out of `_standing_stock.__doc__` entirely, which
# `MODEL_CHOICE_PROVENANCE["roll_age"]` alone then satisfied. Class membership (which rows sit
# above and below) and the FIGURES themselves were already gated and still are; what was open
# was within-class ATTRIBUTION and document SITING, and re-attributing an offset to the wrong
# row is precisely the defect ruling X3 repaired.
#
# WHY A PATTERN AND NOT A PROXIMITY WINDOW. A "nearest geography name" or fixed-character-window
# rule reads plausible and is measurably false-green here: in `two sit below it (MTL_ISLAND_RA06
# -0.321 pp, LAVAL_RA13 -0.228 pp)` the swapped text puts the OTHER row's name 38 characters from
# the figure and its own 1 character away, so any window wide enough to admit
# `LANAUDIERE_RA14_PROXY +0.035 pp` (22 characters of name before the figure) also admits the
# swap. The two forms this prose is ACTUALLY written in are `<GEOGRAPHY> <figure>` and
# `<figure> at|for|in|(<GEOGRAPHY>`, so those two — and no wider neighbourhood — are accepted.
# They live in `tests/_prose_binding.py` now, shared with the two other gates of this shape.
#
# AND THE BARE COMMA IS NOT GLUE, corrected 2026-08-21 when this gate was generalized. The
# retired local `_FIGURE_GLUE = r"[\s,]{0,2}(?:at |for |in |\()?"` made a comma sufficient
# between figure and name, so in the LIST `(MTL_ISLAND_RA06 -0.321 pp, LAVAL_RA13 -0.228 pp)` it
# bound -0.321 pp to LAVAL_RA13 as well: a list separator read as an attribution. That is
# invisible to a per-pair `assert attributes(...)` — every pair it was asked about was true —
# and it surfaces the moment the gate asks for the WHOLE set a row is attributed, which is what
# closes the ADDITIVE falsehood. `_prose_binding.BEFORE` requires an explicit connective.
#
# WHAT THE PER-PAIR FORM COULD NOT SEE. Keeping every correct pair and ADDING
# "LAVAL_RA13 -0.321 pp" (-0.321 is MTL_ISLAND_RA06's figure; LAVAL's is -0.228) shipped GREEN
# against it, because each pair it checked was still stated. A previous agent recorded that "no
# finite pattern can forbid an addition"; that is wrong for exactly this prose, because the
# figures in these sets are pairwise DISTINCT and the label universe is CLOSED (all eight ranked
# rows). Asserting the observed geography -> figures relation EQUALS the measured one forbids the
# addition, and the same equality subsumes the swap and the deletion.


# The two ROLES the narrowing/offset figures play, named once: the region legs
# inside the test below key on them and the `by_role` table is built from them.
_NARROWING = "the point read's NARROWING, above the union"
_OFFSET = "the weighted mean's OFFSET, below the union"


def test_x1_the_docstrings_QUOTE_the_computed_narrowing_and_offset_figures():
    """Rulings X3 and X5: every pp figure `_standing_stock` and `MODEL_CHOICE_PROVENANCE`
    restate, recomputed here from the two union accessors and compared against the prose.

    THIS GATE EXISTS BECAUSE THE PROSE WENT WRONG THREE TIMES IN THE SAME PARAGRAPH, every
    time in a way nothing could red on. (X5) HORS_RMR's narrowing shipped as "+1.654 pp", which is the
    CENSUS-NET curve's reading — a real number about the wrong curve, since the join sends that
    geography to the operand-aligned one, where it is +1.670. An unnamed baseline is how a figure
    like that drifts, so the baseline is now named in the prose AND both readings are computed
    below, with the census-net one asserted to BE the retired figure so the drift's cause stays
    on the record. (X3) The paragraph also said the weighted read "restores the aggregate"; it
    does not — the population-weighted mean sits BELOW the household-weighted union the retired
    flat band supplied AT THE THREE GEOGRAPHIES THAT READ THEIR OWN TERRITORY, by the
    three offsets computed here.

    AND THE CORRECTION OF THAT ITSELF SHIPPED AN OVER-CLAIM, which is the third (2026-08-21):
    "systematically BELOW", FALSE at three of the eight ranked rows. THIS GATE IS WHY IT
    SURVIVED — it iterated `served`, the three geographies that read their own territory, so
    the five rows that BORROW MTL_RMR's curve were never asked. They STRADDLE the union that
    curve supplied them, and one of the three above it is the RANK-1 headline row. The loop
    below now covers all EIGHT and asserts the direction PER CLASS: strictly below for the three
    that own their territory, straddling for the five that borrow.

    THE 85+ HOUSEHOLD SHARE IS RECOVERED FROM RATES, not from counts, so this test needs no
    private count reader: a two-band union is a convex combination of its band rates, so the
    weight is (union - r_85) / (r_7584 - r_85) exactly.
    """
    from demoflow.loaders.census import load_ownership_rates
    from demoflow.loaders.hors_aligned import (
        aligned_ownership_union,
        load_aligned_ownership_rates,
    )
    from demoflow.loaders.constants import MODEL_CHOICE_PROVENANCE

    tail_union = ownership_union_rates(75, 200, data_dir=_DATA)
    shipped = load_ownership_rates(data_dir=_DATA)
    aligned = load_aligned_ownership_rates(data_dir=_DATA)
    read = pipeline._ownership_reader(_DATA)

    # {geography: (own served 75+ household union, 75-84 rate, 85+ rate)} on the curve each
    # geography ACTUALLY READS — which for HORS_RMR is the aligned one.
    served = {
        Geography.MTL_RMR: (tail_union[Geography.MTL_RMR.value],
                            shipped[Geography.MTL_RMR.value]["75-84"],
                            shipped[Geography.MTL_RMR.value]["85+"]),
        Geography.QC_RMR: (tail_union[Geography.QC_RMR.value],
                           shipped[Geography.QC_RMR.value]["75-84"],
                           shipped[Geography.QC_RMR.value]["85+"]),
        Geography.HORS_RMR: (aligned_ownership_union(75, 200, data_dir=_DATA),
                             aligned[Geography.HORS_RMR.value]["75-84"],
                             aligned[Geography.HORS_RMR.value]["85+"]),
    }
    # SITED PER DOCUMENT, not pooled into a union (see the note above this test): the three
    # own-territory figures are stated in BOTH documents and are required in both, so dropping
    # them from either one reds; the five borrowed-row offsets live in `_standing_stock` alone.
    docs = {"pipeline._standing_stock.__doc__": pipeline._standing_stock.__doc__,
            'MODEL_CHOICE_PROVENANCE["roll_age"]': MODEL_CHOICE_PROVENANCE["roll_age"]}
    shares: dict[Geography, float] = {}

    # {document: {geography: the COMPLETE set of pp figures it may attribute to that row}}.
    # Built for ALL EIGHT rows, including the ones a document states nothing for — that is the
    # exclusivity leg, and an empty expected set is the strongest form of it.
    want: dict[str, dict[str, set[str]]] = {where: {g.value: set() for g in Geography}
                                            for where in docs}
    # {geography: {role: its figure}} — the same figures split by the ROLE each plays, which is
    # what the region legs at the bottom of this test assert. See the note there.
    by_role: dict[str, dict[str, set[str]]] = {}
    for geo, (union, r_lo, r_hi) in served.items():
        assert read(geo, pipeline.ROLL_AGE) == pytest.approx(r_lo, rel=1e-15), (
            f"{geo.value}: `ROLL_AGE` no longer resolves to the 75-84 band, so the narrowing "
            "these figures describe is about a different read")
        # (X5) THE NARROWING the point read imposed, against the curve's OWN served union.
        narrowing = 100 * (r_lo - union)
        # (X3) THE OFFSET the population-weighted read introduces — BELOW the union, always.
        offset = 100 * (_X1_STANDING_RATE[geo.value] - union)
        assert offset < 0, f"{geo.value}: the weighted mean no longer sits below the union"
        # Both figures are stated in BOTH documents and are required in both, so dropping one
        # from either reds. They are also DISTINCT from each other and from every other row's
        # pair, which is what makes the set equality below a functional check rather than a
        # count: with eight rows and sixteen figures no two collide at three decimals.
        for where in docs:
            want[where][geo.value] = {f"+{narrowing:.3f} pp", f"{offset:.3f} pp"}
        by_role[geo.value] = {_NARROWING: {f"+{narrowing:.3f} pp"},
                              _OFFSET: {f"{offset:.3f} pp"}}
        shares[geo] = 100 * (1 - (union - r_hi) / (r_lo - r_hi))

    # THE OTHER FIVE ROWS — the class this gate could not see until 2026-08-21, which is exactly
    # how "systematically BELOW" shipped green. Each of the five BORROWS MTL_RMR's curve, so the
    # union its retired flat band supplied it is MTL_RMR's, and every one of them was pinned to
    # that single number under the point read. Their population-weighted means STRADDLE it.
    #
    # ASSERTED AS A DIRECTION PER CLASS, never as one direction for all eight: `offset < 0` is
    # the claim for a geography that reads its OWN territory (above), and STRADDLE is the
    # claim for the five that borrow. A single universal direction is the false statement being
    # removed, so a gate that asserted one would re-encode it.
    mtl_union = tail_union[Geography.MTL_RMR.value]
    borrowed = {g: 100 * (_X1_STANDING_RATE[g.value] - mtl_union) for g in census._BORROWS_FROM}
    assert len(borrowed) == 5, (
        f"the borrowed-curve row set moved: {sorted(g.value for g in borrowed)}")
    assert set(borrowed) | set(served) == set(Geography), (
        f"the two classes no longer cover all eight ranked rows: own-territory "
        f"{sorted(g.value for g in served)}, borrowed {sorted(g.value for g in borrowed)} — a "
        "row in neither is a row this gate does not ask about, which is the hole that let the "
        "over-claim ship")
    assert min(borrowed.values()) < 0 < max(borrowed.values()), (
        f"the five borrowed-curve rows no longer STRADDLE the union their retired flat band "
        f"supplied ({borrowed}) — `_standing_stock` says they straddle, and reason (iii)'s own "
        f"spread of those rows entails it")
    above = sorted(g.value for g, off in borrowed.items() if off > 0)
    below = sorted(g.value for g, off in borrowed.items() if off < 0)
    assert (below, above) == (
        ["LAVAL_RA13", "MTL_ISLAND_RA06"],
        ["LANAUDIERE_RA14_PROXY", "LAURENTIDES_RA15_PROXY", "MONTEREGIE_RA16_PROXY"]), (
        f"which borrowed rows sit above the union has moved: below={below}, above={above} — "
        "`_standing_stock` names both sets, so the prose is now wrong about WHICH rows")
    # EVERY offset the paragraph quotes, recomputed — the same discipline the three above get.
    # The five borrowed-row offsets live in `_standing_stock` ALONE, so `roll_age` is required
    # to attribute NOTHING to those rows: that half of the map is what sites each figure in the
    # document that states it, and it is why the `want` table below covers both documents.
    for geo, off in borrowed.items():
        want["pipeline._standing_stock.__doc__"][geo.value] = {f"{off:+.3f} pp"}

    # THE WHOLE RELATION, ASSERTED AS AN EQUALITY, per document and per row. This one leg
    # replaces the three per-pair `_attributes(...)` asserts that stood here: a transposition
    # moves a figure to the wrong row, a drop empties a row, and an ADDED false pair — the
    # measured evasion, "LAVAL_RA13 -0.321 pp" beside every correct pair — puts a second figure
    # under a row that has one. The label universe is CLOSED (all eight ranked rows), which is
    # what makes the addition reachable at all.
    geo_labels = {g.value: re.escape(g.value) for g in Geography}
    for where, doc in docs.items():
        observed = bound_map(doc, geo_labels, PP)
        for geo in Geography:
            assert observed[geo.value] == want[where][geo.value], (
                f"{geo.value}: {where} attributes {sorted(observed[geo.value])} to this row; "
                f"this run measures {sorted(want[where][geo.value])}. Write each figure BOUND "
                f"to its row — '{geo.value} <figure> pp', '<figure> pp at {geo.value}' or "
                f"'<figure> pp ({geo.value})'. A figure present but attached to another row is "
                "the X3 defect; an extra figure attached to THIS row is a false attribution "
                "that every presence check passes")

    # AND THE SAME RELATION PER ROLE, scoped to the region that announces each — because the
    # per-document map above is blind to a WITHIN-ROW transposition. Swapping `+1.073 pp at
    # MTL_RMR` (the point read's narrowing) with `-0.162 pp at MTL_RMR` (the weighted mean's
    # offset) leaves MTL_RMR's figure SET unchanged, so its equality passes while each role
    # states the OTHER's figure — the narrowing reported as -0.162 pp and the mean reported as
    # sitting below the union by +1.073 pp, each beside the true operand pair. Measured GREEN
    # 2026-08-21 in BOTH documents.
    #
    # SPLITTING BY SIGN PER ROW DOES NOT CLOSE THIS, and was measured not to: the narrowing is
    # positive and the offset negative at every row, so the swap moves both figures and the
    # per-row sign partition is identical before and after. Only the SITE separates the roles.
    role_regions = {
        "pipeline._standing_stock.__doc__": {
            _NARROWING: ("Measured against each geography's OWN served 75+ household union",
                         "IT IS A SMALL, DECLARED, MEASURED MODEL CHANGE"),
            _OFFSET: ("this POPULATION-weighted mean sits BELOW it",
                      "IT IS NOT BELOW EVERYWHERE")},
        'MODEL_CHOICE_PROVENANCE["roll_age"]': {
            _NARROWING: ("which sits above each geography's OWN served age>=75 "
                         "household-weighted union", "THE BASELINE IS NAMED DELIBERATELY"),
            _OFFSET: ("the weighted mean sits BELOW the retired flat band's household-weighted "
                      "union", "and no weight aggregates the couple bucket exactly")},
    }
    for where, roles in role_regions.items():
        text = flat(docs[where])
        for role, (opens, closes) in roles.items():
            start, end = text.find(opens), text.find(closes)
            # A `find` that MISSES returns -1, and a region sliced from -1 is not the role's —
            # that is a gate which cannot fail, so both anchors are required, and in order.
            assert 0 <= start < end, (
                f"{where}: the region that states {role} is not locatable ({opens!r} at "
                f"{start}, {closes!r} at {end}) — these two sentences have been reorganised, so "
                "re-site this leg rather than widening it")
            observed = bound_map(text[start:end], geo_labels, PP)
            expected = {g.value: by_role.get(g.value, {}).get(role, set()) for g in Geography}
            assert observed == expected, (
                f"{where}: the sentence stating {role} binds "
                f"{ {k: sorted(v) for k, v in observed.items() if v != expected[k]} }; this run "
                f"measures { {k: sorted(v) for k, v in expected.items() if v != observed[k]} }. "
                "The per-document map above cannot see this — both figures stay bound to the "
                "same row, so a swap between the two ROLES satisfies its set equality")

    # THE 85+ SHARE RANGE, as a range BOUND to the block it describes: the prose states one span
    # for all three geographies, so the endpoints are what is gated. `21.6` stood here until
    # 2026-08-21 because the HORS_RMR end had been taken off the census-net curve along with the
    # +1.654 (see below). The f-string fixes the endpoint ORDER, so a transposed span reds on the
    # substring; the set equality is what makes a SECOND, false span red.
    span = f"{min(shares.values()):.1f}-{max(shares.values()):.1f}%"
    for where, d in docs.items():
        # THE DENOMINATOR IS PART OF THE CLAIM. The span stayed bound to `85+ households`
        # while what it is a share OF was free, so "85+ households 21.7-25.8% of the province's
        # households" shipped GREEN (measured 2026-08-21) — a share of the wrong universe, off
        # by an order of magnitude, with the endpoints intact. So the figure carries the
        # denominator as a lookahead, which keeps the captured group the span itself.
        #
        # BOTH SPELLINGS OF THE RIGHT DENOMINATOR ARE ACCEPTED, and that is a fix, not a
        # loosening (2026-08-21). Requiring the bare "of the block" made this gate PRESCRIBE
        # the wording it rejected: making the denominator MORE precise — "of the block" ->
        # "of the 75+ block" in both documents, which is what its own failure message spelled
        # out — RED, so an author who followed the failure text got a permanent red. A gate
        # whose message cannot be obeyed is a tax, not a guard. The optional `75+ ` admits the
        # more precise spelling and nothing else: any OTHER universe (`the province's
        # households`, `the households`) still reds, which is the falsehood being closed.
        found = bound_map(d, {"the 85+ share of the 75+ block": r"85\+ households(?: are)?"},
                          r"\d+\.\d+-\d+\.\d+%(?= of the (?:75\+ )?block)", before=None)
        assert found == {"the 85+ share of the 75+ block": {span}}, (
            f"85+ households are {span} of the 75+ block across the three curves and {where} "
            f"binds {sorted(found['the 85+ share of the 75+ block'])} to that phrase. Write the "
            "span with its denominator attached — `<span> of the block` or `<span> of the 75+ "
            "block`, both accepted; the denominator is what makes it a share of the 75+ block "
            "rather than of the province")
        # AND THE DIRECTION OF THE RATE GAP THAT PRODUCES THE NARROWING. The share above says
        # how MUCH of the block 85+ is; this says which SIDE of 75-84 its ownership rate sits
        # on, and the two together are why a point read at `ROLL_AGE` narrows the value upward
        # at all. Nothing held the direction: "materially lower" -> "materially higher" in both
        # documents shipped the FULL SUITE GREEN (measured 2026-08-21). If 85+ owned at a HIGHER
        # rate the +1.073 pp narrowing could not arise, so the paragraph would explain the
        # ruling with its own refutation. The verb differs between the two documents
        # (`owning` in `_standing_stock`, `own` in the `roll_age` provenance), which is the only
        # thing the alternation admits.
        # AND THE SUBJECT IS INSIDE THE SPAN, which the first cut of this leg left out — the
        # same defect the `corner_band` worked example had, and the same cure. With the required
        # span starting at the VERB, WHICH band owns at the lower rate was context rather than
        # part of the claim, so inserting a false subject — "...21.7-25.8% of the block, and
        # 75-84 owning at a materially lower rate" — shipped the FULL SUITE GREEN (measured
        # 2026-08-21) with the share leg above still true and the sentence now naming the
        # OPPOSITE band as the lower-owning one. It is 85+ that owns lower; 75-84 is the band
        # being compared AGAINST, and were 75-84 the lower one the +1.073/+2.593/+1.670 pp
        # narrowings could not have the sign they are measured to have. Both spellings of the
        # denominator stay admitted here for the reason the leg above admits them: a gate must
        # not forbid the wording its neighbour's failure message prescribes.
        # BOTH CASINGS OF THE DIRECTION WORD, and the reason is this file's own recurring
        # defect rather than tidiness (found by run 47's message sweep). This gate's failure
        # message renders the claim in its FIRST sentence as "own at a materially LOWER rate" —
        # the emphasis capitals this prose uses everywhere — and writing exactly that in both
        # documents RED (measured 2026-08-21), so the message advertised a form its own gate
        # rejected. Same class as the `of the 75+ block` denominator and the `S's NUMERATOR`
        # label: a cost whose instructions cannot be followed. The alternation admits the two
        # casings of ONE word and nothing else — `higher` in either casing still reds, which is
        # the falsehood this leg exists for.
        lower = (rf"85\+ households(?: are)? {re.escape(span)} of the (?:75\+ )?block and "
                 r"own(?:ing)? at a materially (?:lower|LOWER) rate")
        assert re.search(lower, flat(d)), (
            f"{where} no longer states in ONE span that it is 85+ households — {span} of the "
            f"75+ block — that own at a materially LOWER rate. Expected `85+ households[ are] "
            f"{span} of the [75+ ]block and own[ing] at a materially lower rate`. The subject "
            "has to sit inside the claim: with the span starting at the verb, another band can "
            "be named as the one owning lower while every figure around it stays true, and that "
            "direction is what makes the point read a NARROWING rather than a widening")

    # THE RETIRED FIGURE'S PROVENANCE, pinned so the drift cannot be re-introduced as a mystery:
    # +1.654 pp is HORS_RMR measured entirely on the CENSUS-NET curve, which it does not read.
    census_net = 100 * (shipped[Geography.HORS_RMR.value]["75-84"]
                        - tail_union[Geography.HORS_RMR.value])
    assert round(census_net, 3) == 1.654, (
        f"the census-net reading is now {census_net:.3f} pp, not the +1.654 the `roll_age` "
        "provenance records as the retired figure — restate that history")
    # BOUND TO THE ROW IT DRIFTED AT, not merely present. `"1.654" in ...` stood here: the
    # digits appearing anywhere satisfied it, so re-attributing the retired figure to MTL_RMR or
    # QC_RMR — a falsehood about which row's baseline was wrong, which is the whole of ruling
    # X5 — would have shipped green. The clause names the row and the figure in one span.
    # THE BASELINE IS IN THE CLAUSE, not merely in the paragraph. With the clause ending at
    # the figure, RE-ATTRIBUTING the retired reading to the OPERAND-ALIGNED curve — "which is
    # the OPERAND-ALIGNED curve's reading and not the census-net residual" — shipped GREEN
    # (measured 2026-08-21) while stating the exact inverse of ruling X5: the drifted figure was
    # the CENSUS-NET reading of a geography that reads the operand-aligned curve, and naming the
    # wrong baseline is the whole defect X5 was issued about.
    stood = re.findall(r"(\w+)'s figure stood here as \+(\d+\.\d+) pp, which is the "
                       r"CENSUS-NET curve's reading",
                       flat(MODEL_CHOICE_PROVENANCE["roll_age"]))
    assert stood == [(Geography.HORS_RMR.value, f"{census_net:.3f}")], (
        f"the `roll_age` provenance records the retired figure as {stood} — it was HORS_RMR's, "
        f"and it is the CENSUS-NET reading (+{census_net:.3f} pp) of a geography that reads the "
        "operand-aligned curve. Naming WHICH baseline the drifted figure was against is the "
        "only reason it can be recognised if it comes back")

    # RULING X1'S INTERNAL-INCONSISTENCY ASYMMETRY, AND WHICH HALF IS WHICH. The `roll_age` note
    # records the defect X1 closed as ED's DENOMINATOR already being age-resolved while the S
    # NUMERATOR valued the same households through ONE band read. NO test file read that clause
    # at all — it is the only surface in this arc's ranked list with no gate-bearing reader — so
    # swapping the two words shipped the FULL SUITE GREEN (measured 2026-08-21) with the
    # asymmetry stated exactly backwards, which inverts WHICH SIDE of the ratio was the coarse
    # one and so which side X1 had to repair. Two legs, because the sentence carries two
    # independent transpositions: the ROLE WORDS against the quantity each belongs to, and the
    # two RATES against the read each is the product of.
    qc = Geography.QC_RMR
    qc_lo, qc_hi = served[qc][1], served[qc][2]
    roll = flat(docs['MODEL_CHOICE_PROVENANCE["roll_age"]'])
    # BOTH SPELLINGS OF THE S LABEL, and that is a FIX rather than a loosening (2026-08-21).
    # The bare `r"the S"` made this gate PRESCRIBE a wording it rejected: its own failure
    # message below spells the claim out as "S's NUMERATOR valued the same households through
    # one band read", and an author who wrote the prose that way got `halves["S's half"]:
    # set()` — a PERMANENT RED for following the instructions. Same trap, same cure and same
    # precedent as the 85+ share's denominator ("of the block" vs "of the 75+ block") twenty
    # lines above: accept the two forms this claim is actually written in and NOTHING wider.
    # WIDENING RATHER THAN REWORDING THE MESSAGE is the choice here, because the message states
    # the ruling in the most natural English for it and the possessive is the form a future
    # author reaches for; a message bent to fit a needlessly narrow regex would leave the tax in
    # place and merely stop advertising it. The alternation still admits nothing else — any
    # other subject ("ED's NUMERATOR", "the denominator") reds, which is the falsehood gated.
    halves = bound_map(roll, {"ED's half of the ratio": r"ED's",
                              "S's half": r"(?:the S|S's)"},
                       r"DENOMINATOR|NUMERATOR", before=None)
    assert halves == {"ED's half of the ratio": {"DENOMINATOR"}, "S's half": {"NUMERATOR"}}, (
        f"the `roll_age` note binds {halves} to the two halves of ruling X1's inconsistency. It "
        "was ED's DENOMINATOR that was already age-resolved and S's NUMERATOR that valued the "
        "same households through one band read; the two words swapped states the asymmetry "
        "backwards, and no other gate in this suite reads that clause")
    reads = bound_map(roll, {"the age-resolved read": rf"{qc.value}'s 85\+ households at",
                             "the one-band read": r"those same households at"},
                      r"\d+\.\d{4}", after=r" ", before=None)
    assert reads == {"the age-resolved read": {f"{qc_hi:.4f}"},
                     "the one-band read": {f"{qc_lo:.4f}"}}, (
        f"the `roll_age` note attaches {reads} to the two reads of {qc.value}'s 85+ households. "
        f"The age-resolved sum values them at {qc_hi:.4f} — the 85+ band rate — and the retired "
        f"single band read valued them at {qc_lo:.4f}, the 75-84 rate `ROLL_AGE` resolved to. "
        "Transposing the two figures inverts which read was the coarse one, and that asymmetry "
        "IS the inconsistency the ruling closed")

    # A QUARTER — the one derived ratio the X3 paragraph states in words rather than digits.
    qc_union = tail_union[Geography.QC_RMR.value]
    qc_share = (qc_union - _X1_STANDING_RATE[Geography.QC_RMR.value]) / (
        shipped[Geography.QC_RMR.value]["75-84"] - qc_union)
    assert 0.20 <= qc_share <= 0.30, (
        f"the QC_RMR offset is {qc_share:.3f} of the defect being repaired, no longer 'a "
        "quarter' — `_standing_stock` says a quarter in words")


def test_x1_the_ED_move_is_OPPOSITE_the_rate_move_at_every_one_of_the_eight_rows(frames):
    """The CONSEQUENCE clause ruling X3's repaired paragraph now states, measured rather than
    reasoned — and the reason the unqualified "systematically BELOW" was worth a ruling.

    WHAT THE FALSE ADJECTIVE TAUGHT. A reader who takes "the weighted mean sits systematically
    below the union" infers that ruling X1 lowered S's ownership rate everywhere, hence raised
    ED everywhere. At three of the eight ranked rows the rate went UP, and at the RANK-1
    HEADLINE ROW — LANAUDIERE_RA14_PROXY, the most negative ED and the row the ranking is read
    off — ED went DOWN. A sign error at rank 1 is the whole output.

    THE ORACLE IS A DIRECTION, NOT A MAGNITUDE, so this survives a data refresh that would move
    every pin in this file: for each geography the standing 75+ bucket is valued BOTH ways — at
    the population-weighted mean the model serves, and at the union its retired flat band
    supplied — and the two mean reference EDs are compared. The assertion is that the ED move is
    strictly OPPOSITE the rate move, at every row, which is the mechanism (a lower ownership
    rate is a smaller S, hence a larger D - S) rather than a number.
    """
    read = pipeline._ownership_reader(_DATA)
    tail_union = ownership_union_rates(75, 200, data_dir=_DATA)
    from demoflow.loaders.hors_aligned import aligned_ownership_union
    # The union the RETIRED FLAT BAND supplied each row: HORS_RMR's off the operand-aligned
    # curve it actually reads, the five borrowers MTL_RMR's along with the curve they borrow.
    retired = {g: (aligned_ownership_union(75, 200, data_dir=_DATA) if g is Geography.HORS_RMR
                   else tail_union[g.value]) for g in Geography}
    real = pipeline._population_weighted_ownership
    mean = lambda series: sum(series) / len(series)

    moves = {}
    for geo in Geography:
        served = mean(pipeline._ed_series(geo, Scenario.REFERENCE, frames, read,
                                          pipeline.CENTRAL_LEG))
        try:
            pipeline._population_weighted_ownership = (
                lambda rows, g, ro, ctx, _v=retired[geo]: _v)
            counterfactual = mean(pipeline._ed_series(geo, Scenario.REFERENCE, frames, read,
                                                      pipeline.CENTRAL_LEG))
        finally:
            pipeline._population_weighted_ownership = real
        rate_move = _X1_STANDING_RATE[geo.value] - retired[geo]
        ed_move = served - counterfactual
        moves[geo.value] = (rate_move, ed_move)
        assert rate_move != 0.0 and ed_move != 0.0, (
            f"{geo.value}: valuing the bucket at the retired flat band's union changed nothing "
            f"(rate {rate_move}, ED {ed_move}) — this row cannot discriminate the two reads")
        assert (rate_move > 0) is (ed_move < 0), (
            f"{geo.value}: the rate moved {rate_move:+.3e} and mean reference ED moved "
            f"{ed_move:+.3e} — the SAME direction. A lower ownership rate is a smaller S and so "
            "a LARGER D - S; the same sign means S is no longer what this rate feeds")

    lowered = sorted(g for g, (_r, ed) in moves.items() if ed < 0)
    assert lowered == ["LANAUDIERE_RA14_PROXY", "LAURENTIDES_RA15_PROXY",
                       "MONTEREGIE_RA16_PROXY"], (
        f"the rows whose ED the X1 repair LOWERED are now {lowered} — `_standing_stock` names "
        "these three, and that the RANK-1 row is among them is the paragraph's whole point")
    # THE RAISED SET, BY NAME. `len(moves) - len(lowered) == 5` stood here and was replaced
    # (2026-08-21 audit). THE ENTAILMENT IS WORTH RECORDING BECAUSE IT WAS NOT THE ONE CLAIMED:
    # that assert was reported as unable to red first, and it is not — with `lowered` pinned to
    # three names it also says |Geography| == 8, which nothing else in THIS test pins, so a NINTH
    # ranked row whose ED ROSE would have red exactly there. It is replaced anyway, because a
    # COUNT is the weakest available form of the claim: it cannot say WHICH rows rose, and
    # `_standing_stock` names them. An exact list on both sides subsumes the count (five names is
    # length five), keeps the ninth-row coverage, and closes the same within-class ATTRIBUTION
    # hole the X3 recurrence found one gate above.
    raised = sorted(g for g, (_r, ed) in moves.items() if ed > 0)
    assert raised == ["HORS_RMR", "LAVAL_RA13", "MTL_ISLAND_RA06", "MTL_RMR", "QC_RMR"], (
        f"the rows whose ED the X1 repair RAISED are now {raised} — `_standing_stock` names the "
        "three own-territory rows and the two borrowers below MTL_RMR's union as the rows whose "
        "ownership rate FELL, and the ED move is opposite the rate move at every row")

    # THE RULE ITSELF, AS THE PARAGRAPH STATES IT — one contiguous DERIVED clause. The two list
    # asserts above pin WHICH rows moved which way; nothing read the SENTENCE that states the
    # rule. `pipeline._standing_stock.__doc__` is twinned to nothing — no generator emits it and
    # no artifact restates it — so it has no regeneration backstop whatsoever, and swapping
    # RAISED and LOWERED in it shipped the FULL SUITE GREEN (measured 2026-08-21) twelve lines
    # from the behavioural gate that refutes it, turning the OPPOSITE-move ruling into a
    # SAME-move claim.
    #
    # THE SPAN RUNS FROM THE HEADER, not from the FELL/ROSE sentence alone, because the same
    # one-word cost buys three more inversions inside the same paragraph: OPPOSITE -> SAME in
    # the header, and "a smaller S, hence a larger D-S" transposed in the mechanism clause that
    # explains WHY the move is opposite. Those two are LITERAL here and the per-row assert above
    # entails them — `(rate_move > 0) is (ed_move < 0)` at every row IS the opposition, and it
    # reds first if the model ever stops having it. The two COUNTS and the two POLARITY words are
    # DERIVED from `moves`, so this leg reads the prose against the model and not against a
    # transcription of it.
    spelled = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
               8: "eight"}
    fell = [g for g, (r, _e) in moves.items() if r < 0]
    rose = [g for g, (r, _e) in moves.items() if r > 0]
    assert len(fell) + len(rose) == len(moves), (
        f"{sorted(set(moves) - set(fell) - set(rose))}: this row's ownership rate did not move "
        "at all. The paragraph partitions the eight rows into the ones whose rate FELL and the "
        "ones whose rate ROSE, so a row in neither is a row the sentence cannot be about")
    polarity = {}
    for direction, rows in (("FELL", fell), ("ROSE", rose)):
        signs = {moves[g][1] > 0 for g in rows}
        assert len(signs) == 1, (
            f"the rows whose rate {direction} no longer move mean reference ED in ONE direction "
            f"({ {g: moves[g][1] for g in rows} }) — the paragraph states one polarity for the "
            "whole class, so it cannot be restated while the class is split")
        polarity[direction] = "RAISED" if signs.pop() else "LOWERED"
    rule = (
        "THE SIGN OF THE ED MOVE IS THE OPPOSITE OF THE SIGN OF THE RATE MOVE, at every one of "
        f"the {spelled[len(moves)]} rows — a lower ownership rate is a smaller S, hence a larger "
        f"D-S. So the {spelled[len(fell)]} rows whose rate FELL had their mean reference ED "
        f"{polarity['FELL']}, and the {spelled[len(rose)]} whose rate ROSE had it "
        f"{polarity['ROSE']}")
    assert rule in flat(pipeline._standing_stock.__doc__), (
        "`_standing_stock` no longer states the ED-move rule the way this run measures it. "
        f"Expected the contiguous clause:\n  {rule}\nEvery word of that span is load-bearing and "
        "each sits one edit from its own inverse: OPPOSITE (the per-row assert above measures "
        "the opposition), the smaller-S/larger-D-S mechanism that explains it, the two COUNTS, "
        "and the two POLARITY words. Nothing emits this docstring, so no regeneration and no "
        "twin equality would catch a flip here — restate the paragraph to match the model")

    # THE MAGNITUDES THE PARAGRAPH QUOTES, each BOUND to the row and the arm it is about.
    # `assert f"{headline:.3e}" in _standing_stock.__doc__` stood here and pinned only that the
    # digits appear somewhere: the docstring states THREE exponential figures, two of them at
    # MTL_RMR, so moving `-1.078e-06` onto another row — or onto the per-age arm, whose whole
    # point is that it is 1.5x this repair — satisfied presence while saying the opposite thing.
    # The three role phrases below each name their own row inline, so the map equality is what
    # makes a transposition between them red.
    headline = moves["LANAUDIERE_RA14_PROXY"][1]
    RANK1 = "the rank-1 row (LANAUDIERE_RA14_PROXY) under this repair"
    ARM_D = "the per-age arm (arm D) at MTL_RMR"
    REPAIR = "this repair itself at MTL_RMR"
    ed_moves = {
        RANK1: r"At LANAUDIERE_RA14_PROXY this repair RAISED S's ownership rate and LOWERED "
               r"mean reference ED \(by",
        ARM_D: r"the per-age arm moves MTL_RMR's mean reference ED by",
        REPAIR: r"against this repair's own"}
    doc = flat(pipeline._standing_stock.__doc__)
    observed = bound_map(doc, ed_moves, EXP, after=r" ", before=None)
    # THE RANK-1 FIGURE IS THE WHOLE PARENTHETICAL, not the first figure inside it. Measured
    # 2026-08-21: a label-bound binder alone still passed `(by -1.078e-06 or by -9.999e-06)`,
    # because the true figure is the one it reaches and the added one sits behind it. Capturing
    # the parenthesis CONTENT makes the addition red — the attribution IS the parenthetical.
    attributed = re.findall(r"LOWERED mean reference ED \(by ([^)]*)\)", doc)
    assert attributed == [f"{headline:.3e}"], (
        f"`_standing_stock` attributes {attributed} to the ED move of {RANK1}; this run measures "
        f"{headline:.3e} — the figure that makes the sign concrete rather than asserted, and "
        "that clause must carry it and nothing else")
    assert observed[RANK1] == {f"{headline:.3e}"}, (
        f"`_standing_stock` binds {sorted(observed[RANK1])} to the ED move of {RANK1}; this run "
        f"measures {headline:.3e} — the figure that makes the sign concrete rather than "
        "asserted, and it must carry that role ALONE")
    # AND THE DOCSTRING STATES EXACTLY THREE exponential figures — one per role. This is the
    # exclusivity leg for the roles whose value this test does NOT measure: an added fourth
    # figure anywhere in the paragraph reds here even though no single role binder reaches it.
    all_exp = re.findall(EXP, doc)
    assert len(all_exp) == len(ed_moves), (
        f"`_standing_stock` states {len(all_exp)} exponential figures {all_exp}; the paragraph "
        f"has {len(ed_moves)} roles for them ({', '.join(ed_moves)}). A figure with no role is "
        "an attribution nothing checks")
    # THE OTHER TWO ROLES ARE QUOTED HERE, NOT MEASURED, and the residual is stated rather than
    # papered over: both compare against the `ROLL_AGE` POINT read (the 75-84 band rate), while
    # this test's counterfactual values the bucket at the RETIRED FLAT BAND's union — a different
    # baseline, so this test's +5.61e-06 at MTL_RMR is not the paragraph's +4.28e-05 and pinning
    # one to the other would be a transcription dressed as a measurement. What IS gated is the
    # SHAPE that makes the rank-1 figure non-transposable: each role carries exactly ONE figure,
    # none of them the rank-1 row's, and arm D differs from the repair it is claimed to be 1.5x.
    for role in (ARM_D, REPAIR):
        assert len(observed[role]) == 1 and f"{headline:.3e}" not in observed[role], (
            f"`_standing_stock` binds {sorted(observed[role])} to the ED move of {role} — one "
            "figure, and never the rank-1 row's, whose sign is the paragraph's whole point")
    assert observed[ARM_D] != observed[REPAIR], (
        f"`_standing_stock` now states the same ED move for {ARM_D} and {REPAIR} "
        f"({sorted(observed[ARM_D])}) — the paragraph's claim is that arm D is 1.5x the fix, "
        "which needs the two to differ")
    # AND THE RATIO, MEASURED AGAINST ITSELF. Distinctness pins that the two figures differ,
    # never their ORDER: swapping them makes arm D 0.68x the fix while the sentence still reads
    # "1.5x the fix", which inverts "ARM D IS STILL REJECTED, and MORE firmly than the wrong
    # label argued" into a claim that the rejected arm is SMALLER than the repair. Measured
    # GREEN 2026-08-21. No baseline read is needed for this and none is available (see the note
    # above — this test's counterfactual values the bucket at a different union): the RATIO is
    # the claim the paragraph makes, so the two bound figures are asked to satisfy it.
    arm_d, repair = (float(next(iter(observed[role]))) for role in (ARM_D, REPAIR))
    # THE MULTIPLIER IS READ OUT OF THE PROSE, never hardcoded here. A literal `== 1.5` stood
    # at this line and was half a gate in BOTH directions (measured 2026-08-21). It derived the
    # ratio from the two bound figures but never READ the sentence — `1.5x` occurred in this
    # suite only in comments and failure messages, never in an assert — so mutating the
    # DOCSTRING ALONE to "ARM D IS NOW PREFERRED, and MORE firmly than the wrong label argued:
    # ... i.e. 0.7x the fix, so it is not a larger, separate model change but a refinement of
    # the fix" shipped the FULL SUITE GREEN with the paragraph recommending the arm ruling X4
    # REJECTS. And the mirror was a maintenance tax: a legitimate data refresh moving the true
    # ratio to 1.4, with the prose correctly updated, would have RED here against a literal
    # nothing measured. Parsing the STATED multiplier closes the gap and removes the tax in one
    # move. `findall` rather than `search`: an ADDED second multiplier is a red too, not a
    # first-match pass.
    stated = re.findall(r"i\.e\. ([\d.]+)x the fix", doc)
    assert len(stated) == 1, (
        f"`_standing_stock` states {len(stated)} arm-D multipliers {stated}; the paragraph has "
        "one role for one, written `i.e. <n>x the fix`. A second is an attribution no "
        "measurement reaches")
    # AND WHICH FIGURE IS THE LARGER, which parsing the multiplier STOPPED gating and is the one
    # regression this arc caused rather than found (measured 2026-08-21). The retired `== 1.5`
    # literal was silently anchoring the ORDER: no stated multiplier could satisfy it unless arm
    # D exceeded the repair. Reading the multiplier out of the prose removed the author-tax and
    # the anchor together, so TRANSPOSING the two quoted figures and restating the multiplier
    # CONSISTENTLY — "by +4.28e-05 against this repair's own +6.32e-05, i.e. 0.7x the fix" — is a
    # self-consistent paragraph that passes the ratio leg while the verdict clause below still
    # reads "a larger, separate model change". Arm D would be SMALLER than the repair it is
    # rejected for exceeding. This is DERIVED FROM THE VERDICT, not a new claim: "larger" is
    # exactly `arm_d > repair`, and it costs a legitimate refresh nothing — a true ratio that
    # moved to 1.4 with the prose restated stays green here, which a literal never did.
    assert arm_d > repair, (
        f"`_standing_stock` states {ARM_D} at {arm_d:.3e} and {REPAIR} at {repair:.3e}, so the "
        f"per-age arm is {arm_d / repair:.2f}x the fix — SMALLER. Ruling X4's verdict, still "
        "standing four lines below in that same paragraph, is that arm D is 'a larger, separate "
        "model change'; a multiplier under 1 contradicts it no matter how consistently the two "
        "figures and the ratio are restated. Fix the paragraph, not this line")
    assert round(arm_d / repair, 1) == float(stated[0]), (
        f"`_standing_stock` states {ARM_D} at {arm_d:.3e} against {REPAIR} {repair:.3e}, a "
        f"ratio of {arm_d / repair:.2f}x, while the paragraph says {stated[0]}x. This asserts "
        "the PROSE against the two figures it quotes, so a data refresh that moves the ratio is "
        "repaired by restating the sentence — not by editing this line")
    # AND THE VERDICT, because the multiplier alone does not carry the conclusion: 0.7x is a
    # perfectly self-consistent paragraph that recommends the rejected arm.
    for clause in ("ARM D IS STILL REJECTED",
                   "not a refinement of the fix but a larger, separate model change"):
        assert clause in doc, (
            f"`_standing_stock` no longer states {clause!r}. Ruling X4's conclusion is that arm "
            "D is REJECTED and is a LARGER, SEPARATE model change; the ratio above is its "
            "evidence, not the finding. Restating that verdict is a SOURCE amendment, not a "
            "test edit")


def test_the_min_pairing_theorem_ARM_D_IS_REJECTED_ON_is_STATED_and_HOLDS(frames):
    """The one-character theorem the rejection of per-age summation (arm D) rests on.

    `_standing_stock`'s WHAT IT IS NOT paragraph states `match_couples` is a min-pairing and
    `sum_a min(m_a, f_a) <= min(sum m, sum f)`, and NO test in this suite mentioned that clause
    at all: flipping `<=` to `>=` shipped the FULL SUITE GREEN (measured 2026-08-21, 1187
    passed), turning the theorem into its own converse with nothing beside it to contradict the
    flip. The converse is what would make per-age initialization LOSSLESS, so the flip deletes
    the entire reason arm D is not simply a finer version of this repair.

    A THEOREM GATED ONLY AS A STRING IS STILL ONLY PROSE, so the direction is DERIVED from the
    model's own numbers rather than matched against a literal. The two sides are built from the
    three inputs `_household_stock` itself uses — population by age and sex, the collective
    share, and the living-arrangement reads — with the LA read taken AT EACH AGE, which is
    exactly the per-age split the paragraph rejects, and the pairing taken through
    `match_couples` itself rather than a re-implementation of `min`.

    THE STRICTNESS LEG IS WHAT REFUTES `>=`. `<=` is satisfied by equality too, and equality is
    the shape a suite passes vacuously; a STRICT gap at every one of the eight geographies makes
    `>=` false rather than merely unstated. The gap exists because the binding sex CHANGES
    inside the slice — the paragraph names the crossover (the female coupled count binds from 75
    into the mid-90s) — and that crossover is the whole mechanism, so this leg would red if a
    refresh ever removed it, which is when the sentence would need rewriting anyway.
    """
    from demoflow.cohort.init import match_couples
    from demoflow.loaders.living_arrangement import couple_share, living_alone_rate

    collective = CONSTANTS["collective_share_75plus"].value
    gaps: dict[str, tuple[float, float]] = {}
    for geo in Geography:
        rows = _base_year_75plus(frames, geo)
        coupled: dict[str, dict[int, float]] = {}
        for sex in ("M", "F"):
            by_age = rows[rows["sex"] == sex].groupby("age")["population"].sum()
            coupled[sex] = {
                int(a): float(people) * (1.0 - collective)
                * (1.0 - living_alone_rate(frames.la, geo, int(a), sex))
                * couple_share(frames.la, geo, int(a), sex)
                for a, people in by_age.items()}
        ages = sorted(set(coupled["M"]) | set(coupled["F"]))
        # NON-VACUITY: a one-age slice makes the two sides EQUAL by construction, so the
        # strictness leg below would be asserting nothing about a lumped bucket.
        assert len(ages) > 1, (
            f"{geo.value}: the base-year 75+ slice carries {len(ages)} ages, so per-age and "
            "lumped pairing are the same computation and this theorem has no content here")
        per_age = sum(match_couples(coupled["M"].get(a, 0.0), coupled["F"].get(a, 0.0))[0]
                      for a in ages)
        lumped = match_couples(sum(coupled["M"].values()), sum(coupled["F"].values()))[0]
        gaps[geo.value] = (per_age, lumped)
        assert per_age < lumped, (
            f"{geo.value}: summing the per-age minima gives {per_age} against the lumped "
            f"minimum {lumped} — no STRICT loss, so `>=` would also be satisfiable here and "
            "this gate could not tell the theorem from its converse. Either one sex now binds "
            "at every age in the slice (which is the `tight only where` case the paragraph "
            "names) or the coupled construction has changed; the paragraph has to be restated "
            "before this leg is widened")

    # `match_couples` is named inside the required span, because relabelling WHICH operation
    # the theorem is about is the same inversion by another route.
    #
    # THE DERIVATION BELOW IS PRESENTATIONAL, AND SAYING SO IS THE HONEST VERSION (2026-08-22).
    # Its `else ">="` is UNREACHABLE: `assert per_age < lumped` above ran for every geography in
    # `gaps`, so `all(p <= l ...)` cannot be False by the time this line evaluates. It reads like
    # a measurement and it is a restatement of one. THE ASSERT IS THE LEG that refutes the flip —
    # STRICTLY, which is the part that matters: `<=` is satisfied by equality too, and the
    # converse `>=` would also hold under equality, so only a measured STRICT gap tells the
    # theorem from its converse. Left as a derivation rather than a literal because it keeps the
    # operator and the measurement in one place, and because a hardcoded "<=" here would need the
    # reader to go find what makes it true; but nothing about `<=` is discovered on this line.
    direction = "<=" if all(p <= l for p, l in gaps.values()) else ">="
    clause = f"is a min-pairing and sum_a min(m_a, f_a) {direction} min(sum m, sum f)"
    assert clause in flat(pipeline._standing_stock.__doc__), (
        f"`_standing_stock` no longer states the min-pairing theorem as {clause!r}. This run "
        f"measures the per-age minima summing BELOW the lumped minimum at all "
        f"{len(gaps)} geographies "
        f"({ {g: f'{p:.1f} < {l:.1f}' for g, (p, l) in gaps.items()} }), so `<=` is the "
        "direction the model has. The converse is the claim that per-age initialization loses "
        "no couples, which is the entire reason arm D is rejected as a SEPARATE model change "
        "rather than adopted as a finer one. Nothing emits this docstring, so no regeneration "
        "and no twin equality would catch the flip — restate the paragraph to match the model")


def test_x4_the_two_CHANNELS_of_the_per_age_gap_keep_their_own_RANGES_and_their_ORDER():
    """Ruling X4's finding is WHICH channel dominates the per-age-vs-lumped gap, and the two
    ranges that say so were bound to nothing (measured 2026-08-21: transposing them ships the
    full suite green).

    X4 exists BECAUSE the gap had been mislabelled as matching-dominated — the retired sentence
    attributed 0.90-1.03 of it to matching alone. The repaired sentence states the two channels
    against the FULL per-age split: min-pairing is the SMALL one and the living-arrangement
    re-read is the large one. Swapping the two spans restores exactly the mislabel the ruling
    was issued against, with both spans still present and every neighbouring figure intact.

    WHAT THIS GATES AND WHAT IT DOES NOT. The suite does not re-derive the two decompositions
    (that is an arm-D computation this repair deliberately does not run), so the span ENDPOINTS
    are the paragraph's own measurement and are not re-measured here. What is gated is the
    ATTRIBUTION and the ORDER: each channel carries exactly one span, the spans are disjoint,
    and min-pairing's sits entirely BELOW the LA re-read's — which is X4's finding stated as an
    inequality rather than as four digit strings, so a transposition reds on the claim and a
    legitimate refresh that moved both spans consistently stays green.
    """
    doc = flat(pipeline._standing_stock.__doc__)
    RANGE = r"\d+\.\d+-\d+\.\d+%"
    MATCHING, LA = "min-pairing (per-age matching)", "the living-arrangement re-read"
    spans = bound_map(doc, {MATCHING: r"min-pairing is only", LA: r"the LA re-read is"},
                      RANGE, before=None)
    for role, found in spans.items():
        assert len(found) == 1, (
            f"`_standing_stock` binds {sorted(found)} to {role}'s share of the per-age gap — "
            "one channel states one span. An empty set is a dropped attribution; a second span "
            "is a share no measurement in that paragraph reaches")
    ends = {role: tuple(float(x) for x in next(iter(found)).rstrip("%").split("-"))
            for role, found in spans.items()}
    assert ends[MATCHING][0] <= ends[MATCHING][1] and ends[LA][0] <= ends[LA][1], (
        f"`_standing_stock` states {ends} — a span written high-end-first is not a range, and "
        "the order of the two endpoints is part of each claim")
    assert ends[MATCHING][1] < ends[LA][0], (
        f"`_standing_stock` gives {MATCHING} {ends[MATCHING]}% of the per-age gap and {LA} "
        f"{ends[LA]}% of it, so the two spans OVERLAP or are the wrong way round. Ruling X4's "
        "whole content is that the gap is LA-re-read-dominated and min-pairing is the small "
        "channel; the transposed sentence restores the matching-dominated mislabel the ruling "
        "was issued to correct")

    # AND THE WORKED EXAMPLE THE SAME SENTENCE HANGS ON THOSE RANGES. The two MTL_RMR moves
    # were bound to nothing either, so they could be swapped independently of the spans and
    # leave the paragraph internally consistent about the wrong channel.
    moves = bound_map(doc, {MATCHING: r"per-age matching", LA: r"the LA re-read"},
                      PCT_SIGNED, after=None, before=r" from ")
    for role, found in moves.items():
        assert len(found) == 1, (
            f"`_standing_stock` binds {sorted(found)} to the MTL_RMR couple-stock move THROUGH "
            f"{role} — the clause is `<figure> from <channel>`, one figure per channel")
    magnitude = {role: abs(float(next(iter(found)).rstrip("%"))) for role, found in moves.items()}
    assert magnitude[LA] > magnitude[MATCHING], (
        f"`_standing_stock` moves MTL_RMR's couple stock by {magnitude[LA]}% through {LA} and "
        f"{magnitude[MATCHING]}% through {MATCHING} — the worked example now contradicts the "
        "two spans three lines above it, which put min-pairing at a few per cent of the gap "
        "and the LA re-read at nearly all of it")


# ===========================================================================================
# SPEC §5's THIRD HARD GATE, WIRED (round-3 audit finding, 2026-08-22)
# ===========================================================================================
#
# `cohort/init.assert_aggregate_coupled_direction` had ZERO production callers — its only
# callers were in `tests/test_init.py` — while TWO committed contracts said it fired:
# `cohort/init.py`'s carry still read "it does not exist as code yet", and
# `loaders/living_arrangement.py` named it among the gates that "fire on MODELLED counts in the
# initialization task". Task 29 HAD landed: `pipeline._standing_stock` is the caller the carry
# described (renamed from `_init_stock`), `HouseholdInit` returns exactly `coupled_m`/`coupled_f`
# and `_household_stock` DISCARDED both. One line was missing.
#
# WIRING COST IS ZERO: all eight geographies run M > F at 75+, worst signed (F-M)/max -0.1155
# (MTL_ISLAND_RA06) against the 0.25 bound. The tests below are what stop it going inert again —
# a one-off injection proof cannot, which is the finding's own class.

def _sex_swapped_rate_reads(monkeypatch):
    """Transpose the M/F living-arrangement reads inside `pipeline`, the injection the audit
    measured: the FULL ED grid computed with NO refusal anywhere, LAVAL_RA13 flipping sign and
    the negative-ED count dropping 3 -> 2 — which destroys the published three-negative-signs
    reading that rank 1 is read off.

    Patched on `pipeline`'s own names (it imports both functions by value), so the swap is
    exactly at the junction the gate is scoped to and touches no loader.
    """
    other = {"M": "F", "F": "M"}
    real_alone, real_couple = pipeline.living_alone_rate, pipeline.couple_share
    monkeypatch.setattr(pipeline, "living_alone_rate",
                        lambda la, geo, age, sex: real_alone(la, geo, age, other[sex]))
    monkeypatch.setattr(pipeline, "couple_share",
                        lambda la, geo, age, sex: real_couple(la, geo, age, other[sex]))


def test_the_75plus_aggregate_direction_gate_FIRES_on_the_standing_stock_path(frames,
                                                                             monkeypatch):
    """The wired RED, on real data, at every geography — and the pristine GREEN beside it.

    Both directions are asserted in one body because either alone is worthless here: the raise
    alone would pass on a gate that refuses every input, and the pristine pass alone is what the
    whole 1190-test suite already reported while the gate had no caller at all.
    """
    read = pipeline._ownership_reader(_DATA)
    for geo in Geography:
        pop = frames.pop[(frames.pop["geography"] == geo)
                         & (frames.pop["scenario"] == Scenario.REFERENCE)]
        year = int(pop["year"].min())

        # PRISTINE: the gate passes on every published row (measured headroom, worst -0.1155).
        pipeline._standing_stock(pop, year, geo, frames.la, read,
                                 collective_share=_CENTRAL_COLLECTIVE)

        with monkeypatch.context() as swapped:
            _sex_swapped_rate_reads(swapped)
            with pytest.raises(CalibrationError, match="direction reversed") as exc:
                pipeline._standing_stock(pop, year, geo, frames.la, read,
                                         collective_share=_CENTRAL_COLLECTIVE)
        assert geo.value in str(exc.value), (
            f"the gate raised without naming {geo.value} — a refusal that does not name the "
            "geography sends the reader to the wrong row of an eight-row ranking")


def test_the_gate_is_scoped_to_the_75plus_AGGREGATE_and_NOT_to_band_entry(frames, monkeypatch):
    """The scoping decision, as a check rather than as prose.

    `_band_entry_stock` hands a SINGLE age-75 cohort and deliberately passes no `direction_ctx`:
    spec §5 states the direction claim at the 75+ AGGREGATE, and steering ruling A's content is
    that a PER-BAND gate is wrong — a per-band direction gate is a different overreach in the
    same family. Nothing is lost by the scoping: the same transposition is caught on the
    standing leg above, in the same run, before any ED is emitted.
    """
    read = pipeline._ownership_reader(_DATA)
    geo = Geography.MTL_ISLAND_RA06          # the worst-headroom row (-0.1155)
    pop = frames.pop[(frames.pop["geography"] == geo)
                     & (frames.pop["scenario"] == Scenario.REFERENCE)]
    year = int(pop["year"].min())

    _sex_swapped_rate_reads(monkeypatch)
    band_entry = pipeline._band_entry_stock(pop, year, geo, frames.la, read,
                                            collective_share=_CENTRAL_COLLECTIVE)
    assert band_entry.owner_units > 0.0, (
        "the band-entry leg returned no stock under the swap — this test asserts it stays "
        "UNGATED, so it must still compute the cohort it always computed")
    with pytest.raises(CalibrationError, match="direction reversed"):
        pipeline._standing_stock(pop, year, geo, frames.la, read,
                                 collective_share=_CENTRAL_COLLECTIVE)


def test_the_direction_gate_is_a_KEYWORD_the_standing_caller_supplies(frames, monkeypatch):
    """The wiring itself, read at the argument — the shape `test_x1_...` uses for the rate.

    A spy that DROPPED the kwarg would leave every other assertion in this file passing with
    the gate off, so what is pinned is that `_standing_stock` supplies one and
    `_band_entry_stock` does not.
    """
    import inspect

    seen = []
    real = pipeline._household_stock
    read = pipeline._ownership_reader(_DATA)
    geo = Geography.MTL_RMR
    pop = frames.pop[(frames.pop["geography"] == geo)
                     & (frames.pop["scenario"] == Scenario.REFERENCE)]
    year = int(pop["year"].min())

    assert "direction_ctx" in inspect.signature(real).parameters

    def spy(rows, geography, age, la, ownership, *, collective_share, direction_ctx=None):
        seen.append(direction_ctx)
        return real(rows, geography, age, la, ownership, collective_share=collective_share,
                    direction_ctx=direction_ctx)

    monkeypatch.setattr(pipeline, "_household_stock", spy)
    pipeline._standing_stock(pop, year, geo, frames.la, read,
                             collective_share=_CENTRAL_COLLECTIVE)
    pipeline._band_entry_stock(pop, year, geo, frames.la, read,
                               collective_share=_CENTRAL_COLLECTIVE)

    standing, entry = seen
    assert standing is not None and geo.value in standing, (
        f"`_standing_stock` handed direction_ctx={standing!r} — the 75+ aggregate leg must name "
        "the geography it is gating")
    assert entry is None, (
        f"`_band_entry_stock` handed direction_ctx={entry!r} — the single age-75 cohort is NOT "
        "the 75+ aggregate the gate is scoped to (steering ruling A)")


# ===========================================================================================
# `_population_weighted_ownership`'s GUARDS (round-3 audit, LOW finding, 2026-08-22)
# ===========================================================================================

def _pop_rows(cells):
    """A minimal `_standing_stock`-shaped population frame: (age, population) pairs, one sex."""
    return pd.DataFrame([{"age": age, "sex": "F", "population": pop} for age, pop in cells])


@pytest.mark.parametrize("cells,written", [
    ([(80, float("nan")), (90, 100.0)], "nan"),
    ([(80, float("inf")), (90, 100.0)], "inf"),
    ([(80, -50.0), (90, 100.0)], "negative"),
])
def test_the_population_weighted_rate_REFUSES_a_malformed_age_cell(cells, written):
    """The guard the function ADVERTISED and did not have — all three measured holes.

    `groupby("age")["population"].sum()` is skipna=True, so a NaN cell became 0.0, that age fell
    OUT of the weighting and `persons <= 0.0` never saw it: `[(80, NaN), (90, 100.0)]` returned
    age 90's rate ALONE, a plausible number computed over half the slice. `+inf` returned nan
    with no refusal and died later inside `match_couples` on a message naming `coupled_m` — the
    wrong operand entirely. A negative-then-positive slice could return a rate OUTSIDE [0,1]
    (constructed 1.404). None is reachable through the live door (`loaders/isq.py` refuses
    non-finite AND negative populations on every kept row), which is why this was a
    misadvertised guard and a misattributed failure rather than a wrong published number.
    """
    # `match="population"` is TOO LOOSE and was measured so (round-3 verify F2): the return
    # `assert_fraction` message also contains "population", so the `+inf` leg passed on the
    # DOWNSTREAM refusal while the per-cell guard was disabled — the one leg whose whole point is
    # that the guard sits BEFORE the skipna groupby. Anchoring on `population[age=` pins the
    # POSITION, which is this fix's load-bearing claim.
    with pytest.raises(LoaderError, match=r"population\[age="):
        pipeline._population_weighted_ownership(
            _pop_rows(cells), Geography.MTL_RMR, lambda geo, age: 0.5, ctx="probe")


def test_the_population_weighted_rate_is_a_FRACTION_and_the_empty_slice_still_refuses():
    """The return assertion, and the one refusal the function always had.

    With nonneg cells and rates in [0,1] the mean is in [0,1] by arithmetic, so the fraction
    assert cannot fire on live input — it is the positional check `balance/owner_stock.py` makes
    for the same reason, closing the direction where a caller's own `read_ownership` hands back
    a rate the weighting would otherwise pass on to `initialize_households`. The empty-slice
    refusal is separately non-vacuous: 0/0 has no rate.
    """
    rows = _pop_rows([(80, 300.0), (90, 100.0)])
    assert pipeline._population_weighted_ownership(
        rows, Geography.MTL_RMR, lambda geo, age: 0.75, ctx="probe") == pytest.approx(0.75)
    # weights are the model's own and the mean is between the two rates it averages
    mixed = pipeline._population_weighted_ownership(
        rows, Geography.MTL_RMR, lambda geo, age: 0.4 if age == 80 else 0.8, ctx="probe")
    assert mixed == pytest.approx((300.0 * 0.4 + 100.0 * 0.8) / 400.0)

    with pytest.raises(LoaderError, match=r"fraction outside \[0,1\]"):
        pipeline._population_weighted_ownership(
            rows, Geography.MTL_RMR, lambda geo, age: 1.4, ctx="probe")
    with pytest.raises(CalibrationError, match="0/0"):
        pipeline._population_weighted_ownership(
            _pop_rows([(80, 0.0)]), Geography.MTL_RMR, lambda geo, age: 0.5, ctx="probe")


# ============================================================================================
# SPEC AMENDMENT #20(C) + #21 — THE FOUR NEW EMITTED POSITIONS, ASSERTED DIRECTLY
# ============================================================================================
#
# NONE of these reads the committed golden, and that is the point rather than a preference: a
# golden regenerated from the emitting code re-ratifies whatever the code emits, so it can never
# be the proof of a claim about the emitted surface. Each leg below compares the EMITTED value
# against the declaration or the computation it is supposed to be, on this run's own bytes.
#
# `schema_version` DOES NOT BUMP for any of them (amendment #20(C0)): all four are OPTIONAL, so a
# consumer pinned to version "1" reads every emitted document unchanged. That is asserted too —
# a bump would invalidate pinned consumers in order to announce fields they may ignore.

def test_the_four_new_envelope_members_did_NOT_bump_the_schema_version(run):
    for name in ("rankings", "tripwires"):
        assert run["_docs"][name]["schema_version"] == "1", (
            f"{name}: amendment #20(C0) rules the version UNCHANGED for the optional members "
            "this run added — a bump invalidates every pinned consumer to announce fields it "
            "may ignore")


def test_the_raw_anchor_row_publishes_BOTH_digests_and_only_that_row(run):
    """Amendment #20(C)(1). `sha256` at the raw-anchor key is the RAW upstream member's digest
    (§7's sha256-of-raw-response), which a re-extract cannot move with; `committed_sha256` is the
    digest of the bytes THIS RUN READ, which is the one a consumer reproduces with `sha256sum`.
    Two semantics under one field name was the defect and it was undisclosed; one field each is
    the fix, and it cost an assignment because `_source_hashes` already computed and pin-checked
    the committed digest before dropping it.

    BOTH DIRECTIONS, and against the FILESYSTEM rather than against the emitter: exactly the keys
    `RUN_SOURCES` marks `publishes=_RAW_ANCHOR` carry the field, the published value IS the
    committed file's digest, and the two digests DIFFER at that key (if they were equal the field
    would be decoration and the disclosure would be describing nothing)."""
    published = run["_docs"]["rankings"]["data_vintage"]["source_hashes"]
    declared = {name for name, src in pipeline.RUN_SOURCES.items()
                if src.publishes == pipeline._RAW_ANCHOR}
    assert declared, "no key publishes a raw anchor — this gate would pass vacuously"
    assert {k for k, v in published.items() if "committed_sha256" in v} == declared

    for name in declared:
        entry = published[name]
        on_disk = hashlib.sha256((_DATA / name).read_bytes()).hexdigest()
        assert entry["committed_sha256"] == on_disk, (
            f"{name}: the published committed digest is not the digest of the committed bytes — "
            "a consumer running `sha256sum` gets a mismatch on the ONE field that exists to "
            "reproduce")
        assert entry["sha256"] == raw_anchor(name) != on_disk, (
            f"{name}: `sha256` must stay the RAW upstream member's pinned digest and must DIFFER "
            "from the committed one — equal digests would make the whole two-field split, and "
            "the README row that discloses it, describe nothing")


def test_the_per_leg_rows_moved_map_is_EMITTED_and_re_derives(run):
    """Amendment #20(C)(2). The per-leg sweep table used to live in three unpinned prose copies
    which `artifacts/README.md` declared "a dated reading" against itself, and it HAD gone stale
    — measured 2026-08-22, EIGHT of its twelve surviving cells were wrong. It is a computed field
    now, and this is the leg that makes it one: RE-DERIVED here from the declared grid, without
    calling `_rank_stability`, so an enumeration or offset error inside that function shows up as
    a mismatch rather than as an internally consistent lie.
    """
    emitted = run["_docs"]["rankings"]["rows_moved"]
    assert set(emitted) == sweep_leg_labels()

    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geos = [g for g in Geography if g in set(frames.pop["geography"])]
    central = {r.geography: r.rank
               for r in rank_geographies(pipeline._ed_dict(geos, frames, read,
                                                           pipeline.CENTRAL_LEG))}
    from demoflow.loaders.constants import declared_sweep_grid, sweep_leg_label

    for axis, endpoints in declared_sweep_grid().items():
        for endpoint in endpoints:
            leg = dataclasses.replace(pipeline.CENTRAL_LEG, **{axis: endpoint})
            order = {r.geography: r.rank
                     for r in rank_geographies(pipeline._ed_dict(geos, frames, read, leg))}
            moved = sum(1 for g in geos if order[g] != central[g])
            label = sweep_leg_label(axis, endpoint)
            assert emitted[label] == moved, (
                f"{label}: the artifact publishes {emitted[label]} rows moved and an independent "
                f"re-derivation measures {moved}")
    # NON-VACUITY: a map of zeros would satisfy every equality above if the re-derivation were
    # broken in the same way. Some leg must move some row, or the sweep measures nothing.
    assert sum(emitted.values()) > 0


def test_the_pairing_token_is_in_BOTH_documents_and_binds_BOTH_PAYLOADS(run):
    """Amendment #20(C)(3), payload re-specified by amendment #22(C). Emission is all-or-nothing,
    but the renames are a LOOP: a failure between two `os.replace` calls leaves a mismatched set
    on disk whose `assumptions_hash` and `data_vintage` are IDENTICAL, so those
    two cannot refuse it. POSIX bounds ATOMICITY, not DETECTION — the residual stops being an
    unclosable ceiling the moment every file carries a token a consumer can compare.

    The token must be the SAME in every document (otherwise it refuses every honest run) and it
    must be `artifacts.pairing_token`'s over ALL EMITTED payloads — Tranche 2 added
    `scenario_prior.json`, so the token now binds THREE payloads; asserting it over the old pair
    alone would let a stale token ship beside a prior nobody hashed. THAT SECOND LEG USED TO
    ASSERT `== pipeline._run_identity(...)`, over (assumptions, sources, `now`), and #22(C)
    retired that payload because none of its three members is output content or code identity: a
    computation change emitted different documents under the same token, measured — see
    `test_a_computation_change_MOVES_the_pairing_token`. Recomputed here from the documents' own
    content, so a stale or mis-stamped token reds rather than being merely well-formed."""
    ranks, trips = run["_docs"]["rankings"], run["_docs"]["tripwires"]
    prior = run["_docs"]["prior"]
    assert len({ranks["run_pairing"], trips["run_pairing"], prior["run_pairing"]}) == 1, (
        "the documents of one run carry DIFFERENT pairing tokens — the field would refuse "
        "every honest run instead of the mismatched one")
    assert ranks["run_pairing"] == artifacts.pairing_token(
        {"rankings.json": ranks, "tripwire_baseline.json": trips,
         "scenario_prior.json": prior}), (
        "the emitted `run_pairing` is not the pairing function of the payloads that shipped "
        "beside it — the token identifies content it was not computed from")
    assert ranks["run_pairing"] != pipeline._run_identity(_DATA, None, _NOW), (
        "the emitted token still equals the RUN-IDENTITY token, whose payload amendment #22(C) "
        "retired because it cannot see a computation change")
    assert ranks["run_pairing"] != ranks["assumptions_hash"], (
        "the pairing token equals the assumption token — one token that moves for either cause "
        "answers neither question, which is the split the envelope exists to keep")
    assert ranks["run_pairing"] != pipeline._run_identity(_DATA, None, _NOW), (
        "the emitted token still equals the RUN-IDENTITY token, whose payload amendment #22(C) "
        "retired because it cannot see a computation change")
    assert ranks["run_pairing"] != ranks["assumptions_hash"], (
        "the pairing token equals the assumption token — one token that moves for either cause "
        "answers neither question, which is the split the envelope exists to keep")


# --- amendment #22(C): the pairing token binds OUTPUT CONTENT -------------------------------

def _median_collapse(geo, scen, series):
    """A CHANGED ED COLLAPSE RULE and nothing else — the mean over the projected years replaced by
    the MEDIAN over the same years. It touches no constant (so `assumptions_hash` cannot move), no
    data byte (so `data_vintage` cannot move) and no schema, which is exactly the class of change
    the retired token payload was blind to. `_scenario_mean`'s empty/non-finite refusals are
    delegated to the real function so the mutation narrows nothing but the collapse."""
    xs = list(series)
    if not xs:
        return rankings_mod._scenario_mean(geo, scen, series)
    return statistics.median(xs)


@pytest.fixture(scope="module")
def pairing(tmp_path_factory):
    """THREE reduced-sweep runs over the committed vintage, same `now`: the baseline, a REPEAT of
    it, and one with the ED collapse rule changed. `sweep_axes=()` because nothing below reads a
    robustness verdict, and the full sweep would pay fourteen ED grids per run for it.

    The mutation is applied to the PRODUCTION function through the real emitters — not mocked, not
    injected at the seam under test — so what the assertions read is the artifact a developer's
    ordinary loop would actually leave on disk."""
    out = {name: tmp_path_factory.mktemp(f"pairing_{name}")
           for name in ("base", "repeat", "mutated")}
    for name in ("base", "repeat"):
        run_pipeline(data_dir=_DATA, out_dir=out[name], now_year=_NOW[0], now_month=_NOW[1],
                     sweep_axes=_NO_SWEEP)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rankings_mod, "_scenario_mean", _median_collapse)
        run_pipeline(data_dir=_DATA, out_dir=out["mutated"], now_year=_NOW[0],
                     now_month=_NOW[1], sweep_axes=_NO_SWEEP)
    return {name: {doc: json.loads((path / doc).read_text(encoding="utf-8"))
                   for doc in ("rankings.json", "tripwire_baseline.json")}
            for name, path in out.items()}


def test_a_computation_change_MOVES_the_pairing_token(pairing):
    """THE ESCAPE amendment #22(C) closes, reproduced end to end. Two runs over identical data,
    identical assumption selection and the SAME `now` — separated only by a change to the ED
    collapse rule — emitted DIFFERENT rankings under the SAME token, so a consumer following the
    published protocol accepted a pair from two different computations.

    `now` is `(year, month)`, so this needs two runs in the same calendar month: the ordinary
    developer loop, not an adversary.

    THE NON-VACUITY LEGS ARE THE POINT OF THIS TEST, and they are asserted rather than described.
    The retired payload's three members are (assumption selection, source bytes, `now`); the first
    two ride the emitted envelope and are checked BYTE-IDENTICAL across the pair here, the third
    is the same argument passed to both runs. So the retired token was necessarily identical, and
    the published ranking REORDERED underneath it."""
    base, mut = pairing["base"]["rankings.json"], pairing["mutated"]["rankings.json"]

    # (1) the retired payload did not move: both of its emitted members are byte-identical
    assert base["assumptions_hash"] == mut["assumptions_hash"]
    assert base["data_vintage"] == mut["data_vintage"]

    # (2) the OUTPUT did move, and visibly — a reorder, not merely a digit
    order = lambda doc: [(r["rank"], r["geography"]) for r in doc["rankings"]]
    assert order(base) != order(mut), (
        "the collapse-rule change did not reorder the published ranking — this test would then "
        "assert the token moves for a change nothing downstream can see")
    assert artifacts.payload_of(base) != artifacts.payload_of(mut)

    # (3) ...so the token MUST have moved
    assert base["run_pairing"] != mut["run_pairing"], (
        f"a computation change reordered the published ranking {order(base)} -> {order(mut)} and "
        f"the pairing token did NOT move ({base['run_pairing']}) — a consumer comparing it "
        "accepts a pair from two different computations, which is a check that cannot fail")


def test_the_mixed_pair_a_failed_rename_leaves_is_REFUSABLE(pairing):
    """The pair the rename loop can actually leave: a NEW `rankings.json` beside a STALE
    `tripwire_baseline.json`. Before #22(C) it validated, its tokens MATCHED, and the consumer
    protocol on the shipped README accepted it.

    The two envelope tokens are asserted identical across the mixed pair FIRST, because that is
    what makes `run_pairing` load-bearing rather than decorative here: `assumptions_hash` and
    `data_vintage` structurally cannot refuse this pair, so if the pairing token cannot either,
    nothing can."""
    new_rankings = pairing["mutated"]["rankings.json"]
    stale_tripwires = pairing["base"]["tripwire_baseline.json"]

    assert new_rankings["assumptions_hash"] == stale_tripwires["assumptions_hash"]
    assert new_rankings["data_vintage"] == stale_tripwires["data_vintage"]
    assert new_rankings["run_pairing"] != stale_tripwires["run_pairing"], (
        "the mixed pair a failed rename leaves carries ONE pairing token across two runs' "
        "documents — the consumer protocol published on artifacts/README.md tells a reader to "
        "compare this field and refuse a mismatch, and here it cannot")

    # ...and the honest pair each run DOES leave is still ACCEPTED, in both runs — a token that
    # refused every pair would satisfy the assertion above and be useless.
    for name in ("base", "mutated"):
        docs = pairing[name]
        assert docs["rankings.json"]["run_pairing"] == docs["tripwire_baseline.json"]["run_pairing"]


def test_the_pairing_token_is_BYTE_STABLE_across_identical_runs(pairing):
    """THE NONCE PROHIBITION, unchanged by #22(C) and asserted on the emitted field. A pure
    function of emitted content: two runs with identical inputs AND identical code produce
    identical bytes, which is what the committed goldens rest on — a random token would re-mint
    them on every run."""
    for doc in ("rankings.json", "tripwire_baseline.json"):
        assert pairing["base"][doc]["run_pairing"] == pairing["repeat"][doc]["run_pairing"], (
            f"{doc}: two runs over identical inputs and identical code emit DIFFERENT pairing "
            "tokens — the token is not a function of content alone")
        assert pairing["base"][doc] == pairing["repeat"][doc]     # the whole document, in fact


def test_the_published_tripwire_declarations_ARE_the_declarations(run):
    """Amendment #21. `freshness_years` and `source_kind` are published per row, and the values
    published must be `pipeline._TRIPWIRE_DECLARATIONS`' own — asserted DIRECTLY against that
    ledger, never through the golden.

    WHY THE FIELDS EXIST AT ALL: run 49 ruled `TRIPWIRE_BANDS` out of `assumptions_hash` because
    its endpoints ARE published per row ("a move announces itself in the diff") and ruled this
    ledger out on the same argument while it was published NOWHERE. The exclusion of the second
    rested on nothing. Publishing makes the argument true for both, and costs the rankings'
    identity nothing — hashing a tripwire-only declaration would re-mint the RANKINGS' token for a
    verification-gate ruling that cannot move a single ED.

    THE FIELDS SHIP INERT and that is asserted here too, because it is the whole reason this
    could land in Tranche 1: every indicator is UNKNOWN with a null `current_value`, so no
    freshness comparison is evaluated and no published verdict depends on the declaration yet. The
    declaration becomes checkable BEFORE the work that makes it load-bearing."""
    rows = {t["indicator"]: t for t in run["_docs"]["tripwires"]["indicators"]}
    assert set(rows) == set(pipeline._TRIPWIRE_DECLARATIONS)
    for indicator, (_as_of, freshness, kind) in pipeline._TRIPWIRE_DECLARATIONS.items():
        row = rows[indicator]
        assert row["freshness_years"] == freshness, (
            f"{indicator}: the row publishes freshness_years={row['freshness_years']!r} against "
            f"the declared {freshness!r}")
        assert row["source_kind"] == kind.value, (
            f"{indicator}: the row publishes source_kind={row['source_kind']!r} against the "
            f"declared {kind.value!r}")
        # THE DECLARED STRING, NEVER THE ENUM REPR: under py3.12 str-Enum `str(SourceKind.WIRED)`
        # is 'SourceKind.WIRED', which is the shape an f-string path ships into the artifact.
        assert "SourceKind" not in row["source_kind"]
        # INERT: no freshness comparison is reached, so no published verdict rests on the value.
        assert row["status"] == "UNKNOWN" and row["current_value"] is None


def test_the_pr_landings_as_of_declaration_is_DEAD_AND_TYPED_DEAD():
    """The one declaration in this ledger that governs nothing, and now says so.

    MEASURED (2026-08-22): `_TRIPWIRE_DECLARATIONS[PR_LANDINGS_INDICATOR]` carried `as_of=2026`,
    and `_tripwire_results` passes only members [1] and [2] to `evaluate_pr_landings` — which
    DERIVES the as_of from the feed, because a realized-landings measurement dates itself. So
    `_spec_for` is never called for this indicator and the year was a plausible-looking literal
    that nothing read and nothing could contradict, inside the ledger amendment #21 has just made
    load-bearing.

    A DEAD DECLARATION IS NOT CLOSED BY A COMMENT SAYING IT IS DEAD. `None` puts it in the type,
    and `_spec_for` REFUSES rather than building a spec with a null as_of — so if some future run
    routes this indicator through the declared path, it gets a named error instead of a generic
    freshness gate silently comparing against nothing. Both halves are asserted here because the
    refusal is otherwise unreachable from any test, which is the class this module keeps finding.
    """
    declared_as_of, freshness, kind = pipeline._TRIPWIRE_DECLARATIONS[PR_LANDINGS_INDICATOR]
    assert declared_as_of is None, (
        "PR landings declares an `as_of` that nothing reads — `evaluate_pr_landings` derives it "
        "from the feed. Declare `None` or wire the declaration, never both")
    assert freshness is not None and kind is not None, (
        "the OTHER two members of this row ARE read by `_tripwire_results` and must stay declared")
    with pytest.raises(CalibrationError, match="declares no `as_of`"):
        pipeline._spec_for(PR_LANDINGS_INDICATOR)
    # ...and the five that DO route through the declared path still build a spec.
    for indicator in sorted(set(pipeline._TRIPWIRE_DECLARATIONS) - {PR_LANDINGS_INDICATOR}):
        assert pipeline._spec_for(indicator).as_of is not None, (
            f"{indicator} routes through `_evaluate_declared` and must carry a declared as_of")


def test_the_unruled_band_refusal_reaches_the_PR_LANDINGS_PATH_TOO(tmp_path):
    """Both evaluation paths refuse a real measurement against `UNRULED_BAND`, not just one.

    `_evaluate_declared` has always refused it — "a band is a ruled value; the run refuses rather
    than publishing a verdict off a width nobody set". `evaluate_pr_landings` had NO such check,
    so the same placeholder on this indicator would have published a verdict computed against a
    zero-width band. NOT REACHABLE ON THE COMMITTED TREE (this band is ruled, and the three
    unruled indicators all route through the other path), which is the reason to close it now
    rather than to leave it: the asymmetry was in the GUARD, not in the data, and an argument that
    holds for one of two paths is unsound for the pair.

    THE MEASUREMENT HAS TO BE REAL for the guard to have anything to refuse, so the fixture year
    is relabeled into a CLOSED plan-governed year — the same helper `tests/test_tripwires.py`
    uses for its own realized-value cases, imported rather than re-implemented, because a second
    copy of that relabel is the drift this tree refuses everywhere else."""
    from .test_tripwires import QC_2025_PROVINCE, _lines, _plant, _relabel_year

    landings = _plant(tmp_path, _relabel_year(_lines(), "2025", "2026"))
    # non-vacuity: the guard is only meaningful if this feed really does produce a measurement
    ruled = pipeline._tripwire_results(landings, (2027, 3))[0][0]
    assert ruled.current_value == QC_2025_PROVINCE, (
        "the relabeled fixture produced no measurement, so the refusal below would pass "
        "vacuously — the guard tests `current_value is not None`")

    saved = pipeline.TRIPWIRE_BANDS[PR_LANDINGS_INDICATOR]
    pipeline.TRIPWIRE_BANDS[PR_LANDINGS_INDICATOR] = pipeline.UNRULED_BAND
    try:
        with pytest.raises(CalibrationError, match="no ruled band"):
            pipeline._tripwire_results(landings, (2027, 3))
    finally:
        pipeline.TRIPWIRE_BANDS[PR_LANDINGS_INDICATOR] = saved
    assert pipeline.TRIPWIRE_BANDS[PR_LANDINGS_INDICATOR] == saved


# ------------------------------------------------- the A2 call-count factorization, bound

_GRID_CLAUSE = re.compile(r"(\d+) x (\d+) x (\d+) x (\d+) = ([\d,]+) calls per run")
_DERIVED_CLAUSE = re.compile(r"([\d,]+) (?:times )?\(([\d,]+) x the (\d+) ages")
_LATTICE = {"headship": re.compile(r"headship_rate\(curve, a\) for a in range\((\d+), (\d+)\)"),
            "ownership": re.compile(r"read_ownership\(geo, a\) for a in range\((\d+), (\d+)\)")}


def test_the_A2_call_counts_are_the_GRID_PRODUCT_and_never_a_typed_LITERAL():
    """Round 4 A2 replaced "no production caller runs it today" at two sites with the caller's
    real per-run call count. That cure planted the defect A4 was dispatched to remove: the count
    is legs x geographies x scenarios x projected years, and this grid has already widened twice
    — so an UNBOUND product here is the third stale-count incident on the same quantity waiting
    to happen, planted by the run sent to fix the second. This gate makes the product DERIVED
    instead: each factor is read from its own authority (`sweep_leg_labels()`, the committed
    ranking, `Scenario`, `_projected_years`), never typed here, and the age multipliers are read
    off the two `range(...)` comprehensions `_ed_series` builds its lattices with.

    THE OCCURRENCE CENSUS IS THE HALF THAT CLOSES THE EVASION. Checking only the one stated
    factorization per surface would leave the DERIVED counts beside it (`<grid> x the N ages`)
    free to keep a stale first factor — occurrence-selective drop, the evasion `_prose_binding`
    names. So per surface the number of times the product is spelled must equal the number of
    positions this gate actually reached; any further mention reds until it is bound too. That
    is also why this docstring names no figure: a literal here would be the same rot one layer
    out, unreachable by the census below.

    WHAT IS DELIBERATELY NOT BOUND: the instrumented totals that are not grid products — the
    `_households` and `_require_prior_cohort` entry counts and `formation`'s sub-floor reads.
    Those are DATED measurements, the idiom `pipeline._sweep_legs.__doc__` already uses for its
    battery: a dated observation ages visibly and can be re-measured, while undated
    present-tense arithmetic rots silently. The split is the point — bind the arithmetic, date
    the measurements.
    """
    from demoflow.balance import owner_stock as owner_stock_module
    from demoflow.demand.formation import OWNERSHIP_LATTICE_FLOOR, native_formation
    from demoflow.golden import GOLDEN_DIR

    # --- the four factor authorities, none of them typed here.
    legs = len(sweep_leg_labels())
    geographies = len(json.loads((GOLDEN_DIR / "rankings.json").read_text())["rankings"])
    scenarios = len(Scenario)
    frames = pipeline._load_all(_DATA)
    domains = {(geo, scen): len(pipeline._projected_years(
                   frames.pop[(frames.pop["geography"] == geo)
                              & (frames.pop["scenario"] == scen)]))
               for geo in Geography for scen in Scenario}
    assert len(set(domains.values())) == 1, (
        f"the projected-year domain is not uniform across the grid "
        f"({sorted(set(domains.values()))}) — a single year factor cannot describe the call "
        "count, so both docstrings need the per-cell form instead")
    years = next(iter(domains.values()))
    factors = (legs, geographies, scenarios, years)
    grid = legs * geographies * scenarios * years

    # --- the age lattices `_ed_series` itself builds, read off its source, not typed.
    source = inspect.getsource(pipeline._ed_series)
    lattice = {}
    for name, pattern in _LATTICE.items():
        found = pattern.findall(source)
        assert len(found) == 1, (
            f"`_ed_series` no longer builds its {name} lattice as one `range(...)` comprehension "
            f"({found}) — this gate reads the age factors off that line, so re-point it")
        lo, hi = (int(x) for x in found[0])
        lattice[name] = (lo, hi - lo)
    assert lattice["ownership"][0] == OWNERSHIP_LATTICE_FLOOR, (
        f"`_ed_series` reads ownership from age {lattice['ownership'][0]} while the floor is "
        f"{OWNERSHIP_LATTICE_FLOOR} — the sub-floor count below is derived from the floor")
    ages = {lattice["headship"][1]: "the population lattice",
            OWNERSHIP_LATTICE_FLOOR: "the ages below the ownership floor",
            lattice["ownership"][1]: "the ages at or above the ownership floor"}

    surfaces = {"balance/owner_stock.py module docstring": owner_stock_module.__doc__,
                "demand/formation.py native_formation.__doc__": native_formation.__doc__}
    for where, doc in surfaces.items():
        flattened = flat(doc)
        stated = _GRID_CLAUSE.findall(flattened)
        assert len(stated) == 1, (
            f"{where} states the per-run call count {len(stated)} times ({stated}) — the A2 "
            "sentence must carry its factorization exactly once, so a reader has one place to "
            "check and a widening grid has one place to fail")
        *stated_factors, stated_product = stated[0]
        assert tuple(int(f) for f in stated_factors) == factors, (
            f"{where} writes the grid as {' x '.join(stated_factors)} where the run's own "
            f"authorities give {' x '.join(str(f) for f in factors)} — legs from "
            "`sweep_leg_labels()`, geographies from the committed ranking, scenarios from "
            "`Scenario`, years from `_projected_years`")
        assert int(stated_product.replace(",", "")) == grid, (
            f"{where} multiplies its own factors to {stated_product}, not {grid:,} — the "
            "product and the factorization disagree inside one sentence")

        derived = _DERIVED_CLAUSE.findall(flattened)
        for total, first, age_factor in derived:
            assert int(first.replace(",", "")) == grid, (
                f"{where} derives {total} from a first factor of {first}, but the run's grid is "
                f"{grid:,} — this is the occurrence-selective drop the census below also catches")
            assert int(age_factor) in ages, (
                f"{where} multiplies the grid by {age_factor} ages, which is none of the "
                f"lattices `_ed_series` builds ({sorted(ages)}: {list(ages.values())})")
            assert int(total.replace(",", "")) == grid * int(age_factor), (
                f"{where} states {total} for {first} x {age_factor} = {grid * int(age_factor):,} "
                f"— {ages[int(age_factor)]} is the factor, and the product is wrong")

        checked = 1 + len(derived)
        assert flattened.count(f"{grid:,}") == checked, (
            f"{where} spells {grid:,} {flattened.count(f'{grid:,}')} times and this gate reached "
            f"{checked} of them (1 stated factorization + {len(derived)} derived counts) — an "
            "unreached occurrence keeps a stale first factor when the grid widens, so give it a "
            "`N x the M ages` form or drop the number")

        # AND THE SAME CENSUS ON EACH DERIVED TOTAL, which the grid census above cannot see.
        # Round-4 verify measured it: `882,336` is stated ONCE with its `<grid> x <ages>`
        # factorization and a SECOND time bare, and the bare one was reached by nothing —
        # `882,336 -> 999,999` there left this gate passing and the full suite green. That is the
        # occurrence-selective drop this gate's own docstring claims to close, one level down from
        # where it was closing it: a derived product is exactly as rottable as the grid product,
        # so it is counted the same way.
        for total, _first, _age_factor in derived:
            spelled = flattened.count(total)
            reached = sum(1 for t, _f, _a in derived if t == total)
            assert spelled == reached, (
                f"{where} spells the derived count {total} {spelled} times and this gate reached "
                f"{reached} of them — a bare restatement carries a stale product past the "
                "factorization census, so give every occurrence its `N x the M ages` form or "
                "drop the number")


# ===========================================================================================
# AMENDMENT #24(A) — THE POOLED-DENOMINATOR CONVERSION, ON THE ED PATH
# ===========================================================================================
#
# The join table's own gates (`tests/test_i2.py`) hold the counts against P8's digits and hold
# `B` against those counts. What they cannot see is whether the ED path APPLIES it: `B` could be
# computed perfectly and never divide anything, and every value leg in this file would stay green
# because the reader still answers correctly and the join table still resolves.

def _pooled_at(bias_scale: float):
    """A `PooledOwnership` block whose `B` is `bias_scale`, built from counts.

    `p_nonimm` is fixed at 1/2 and the two other groups are given the owner counts that make the
    POOLED rate `bias_scale/2`, so `B = p_all / p_nonimm = bias_scale` exactly in binary floating
    point for the scales used below. Counts, never a typed `B` — the class has no seam to inject
    one through, which is the property amendment #24(A) rules.

    THE REACHABLE RANGE IS [0.5, 1.5] and the assert states it rather than clamping into it: with
    1024 non-immigrant maintainers at rate 1/2 and 1024 maintainers across the other two groups,
    the pooled owner count runs from 512 (nobody else owns) to 1536 (everybody else does). A
    silent clamp would build a block whose `B` is not the one the caller asked for and green the
    algebraic identity below on two points that were secretly the same."""
    from demoflow.demand.immigrant_inputs import PooledOwnership
    # non-immigrants: 1024 maintainers, 512 owners (rate 1/2). Others: 1024 maintainers total.
    others = int(round(1024 * bias_scale)) - 512      # owners needed across the other two groups
    assert 0 <= others <= 1024, f"bias {bias_scale} is outside the reachable [0.5, 1.5]"
    return PooledOwnership(non_immigrant=(1024, 512), immigrant=(512, min(others, 512)),
                           non_permanent_resident=(512, max(others - 512, 0)))


def _series_with_bias(frames, read, geo, bias):
    """`(the block's ACTUAL B, the series)` with `geo`'s pooled block replaced.

    The realised `B` is READ BACK off the block rather than assumed equal to `bias`: the counts
    are integers, so a requested scale that is not a dyadic multiple of 1/1024 lands nearby, and
    an algebraic identity checked against the REQUESTED value would fail on that rounding and be
    "fixed" with a tolerance wide enough to hide the thing it tests."""
    real = pipeline.resolve_immigrant_inputs
    block = _pooled_at(bias)

    def patched(g):
        row = real(g)
        return dataclasses.replace(row, pooled=block) if g is geo else row

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline, "resolve_immigrant_inputs", patched)
        return (block.pooled_denominator_bias,
                pipeline._ed_series(geo, Scenario.REFERENCE, frames, read, pipeline.CENTRAL_LEG))


def test_24A_the_ED_path_DIVIDES_the_propensity_by_the_pooled_bias(frames):
    """`B` reaches the emitted series, and it reaches it as a DIVISOR on the immigrant leg alone.

    THE ALGEBRA IS THE ORACLE, which is what makes this stronger than "the series moved". The
    conversion enters as `p_nonimm = p_all / B`, and `p_imm` multiplies the immigrant leg
    linearly, so for a fixed (geography, scenario, year)
    `ED(B) = c + d/B` for constants `c` (native demand, supply, denominator) and `d`. Three
    distinct biases therefore have to agree on `d`: `(ED(B1) - ED(B2)) / (1/B1 - 1/B2)` must equal
    the same quotient taken over `(B1, B3)`, at EVERY year of the series. A mutant that applied
    `B` anywhere else — to the native leg, to the denominator, as a multiplier, once per run
    instead of per geography — breaks that identity rather than merely shifting a number.

    NON-VACUITY: `d` is asserted non-zero, so a build in which `B` reaches nothing at all (every
    quotient 0/x = 0, identity trivially satisfied) reds here."""
    read = pipeline._ownership_reader(_DATA)
    geo = Geography.MTL_ISLAND_RA06
    # THE LOW END IS BOUNDED BY A REAL GUARD, not by taste: `formation.p_imm` asserts the
    # converted operand is a fraction, and dividing this geography's ~0.512 aggregate by a bias
    # below that pushes it above 1 and RAISES. So the three points sit at and above 3/4.
    (b1, s1), (b2, s2), (b3, s3) = (_series_with_bias(frames, read, geo, b)
                                    for b in (1.0, 1.5, 0.75))
    assert len({b1, b2, b3}) == 3, f"the three biases collapsed to {(b1, b2, b3)}"
    assert len(s1) == len(s2) == len(s3) > 1

    for year, (e1, e2, e3) in enumerate(zip(s1, s2, s3)):
        d12 = (e1 - e2) / (1 / b1 - 1 / b2)
        d13 = (e1 - e3) / (1 / b1 - 1 / b3)
        assert d12 != 0.0, (
            f"year index {year}: the bias moves the series by nothing — `B` is computed and then "
            "discarded, which is the mutant every value leg in this file passes")
        assert d12 == pytest.approx(d13, rel=1e-9), (
            f"year index {year}: the bias does not enter as a pure 1/B factor on the immigrant "
            f"leg — the two secants give {d12!r} and {d13!r}. It is being applied to something "
            "else as well, or applied more than once")


def test_24A_the_conversion_is_what_moved_the_SIGN_at_MTL_ISLAND_RA06(frames):
    """The amendment's headline consequence, reproduced through the production function.

    At `B = 1` the path computes exactly the pre-conversion product (an all-maintainer rate times
    a non-immigrant-denominated ratio) — so this test carries the RED and the GREEN in one body:
    the unconverted mean low-scenario ED is NEGATIVE and the converted one is POSITIVE. A consumer
    reads that as shrinking-versus-growing excess demand, which is why amendment #24(A) ruled a
    fix rather than a declared limit.

    The LOW scenario is the one that crosses, so the series is taken there rather than at
    reference; `MTL_ISLAND_RA06` is the geography, and both are named by the amendment."""
    from demoflow.output.rankings import _scenario_mean
    read = pipeline._ownership_reader(_DATA)
    geo = Geography.MTL_ISLAND_RA06

    real = pipeline.resolve_immigrant_inputs

    def unconverted(g):
        row = real(g)
        return dataclasses.replace(row, pooled=_pooled_at(1.0))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline, "resolve_immigrant_inputs", unconverted)
        before = _scenario_mean(geo, Scenario.LOW, pipeline._ed_series(
            geo, Scenario.LOW, frames, read, pipeline.CENTRAL_LEG))
    after = _scenario_mean(geo, Scenario.LOW, pipeline._ed_series(
        geo, Scenario.LOW, frames, read, pipeline.CENTRAL_LEG))

    assert before < 0.0 < after, (
        f"the unconverted low-scenario mean at {geo.value} is {before!r} and the converted one is "
        f"{after!r} — amendment #24(A) rests on that crossing, so a build where both share a sign "
        "has either lost the conversion or lost the geography it was measured at")
    assert pipeline.resolve_immigrant_inputs(geo).pooled.pooled_denominator_bias < 1.0, (
        f"{geo.value}'s pooled bias is not below 1, so the conversion RAISES its immigrant leg — "
        "the direction the sign crossing above depends on")
