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
import json
import math
import shutil
from pathlib import Path

import pytest

from demoflow.cohort.basis import (
    BASIS_DIGEST_AGES,
    BASIS_DIGEST_GENDERS,
    BASIS_DIGEST_YEARS,
    BASIS_SOURCE_KEY,
)
from demoflow.errors import CalibrationError, LoaderError
from demoflow.geography import RA_PROXY_MEMBERS, Geography, Scenario
from demoflow.loaders.census import CENSUS_EXTRACT, OWNERSHIP_ARTIFACT
from demoflow.loaders.compo import FLOW_SPAN
from demoflow.loaders.constants import (
    CENTRAL_ASSUMPTIONS,
    CONSTANTS,
    SWEEP_GRID,
    assumptions_hash,
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
import demoflow.pipeline as pipeline
from demoflow.pipeline import (
    EXIT_CAUSE_TO_LISTING_CAUSE,
    RECONCILIATION_COHORT,
    RUN_ARTIFACTS,
    RUN_SOURCES,
    UNRULED_BAND,
    run_pipeline,
)

# The run's data source, named ONCE and passed explicitly everywhere (carry B11).
_DATA = DATA_DIR

# THE SWEEP REDUCTION, named once and used only where it is SOUND (ruling V, run 34). Every
# test below that runs `run_pipeline` end to end to assert something about EMISSION, the
# identity bracket, the exit code or a gate's call count paid a full twelve-leg robustness
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
    ED grid TWELVE times (the central run, reused as the sweep's central leg AND as the one
    no-op `headship_shape` leg, plus `_rank_stability`'s eleven remaining six-axis legs), so a
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


def test_the_run_identity_covers_the_data_vintage_as_well_as_the_assumptions(monkeypatch,
                                                                            tmp_path):
    """`assumptions_hash()` hashes `CENTRAL_ASSUMPTIONS` + `SWEEP_GRID` and NOTHING about the
    data, so two runs over different source bytes produce an identical hash. The run's
    composition token covers both — and moving EITHER moves it.

    The data leg moves REAL BYTES on a copy, not a declared digest: since review finding F1 the
    envelope hashes `data_dir` rather than transcribing a module constant, so a mutated
    `RUN_SOURCES` record no longer moves anything (and a mutated PINNED file refuses outright).
    A re-serialization of a derived artifact is the honest probe — identical semantics,
    different bytes — and it is the bytes the envelope claims to identify."""
    base = pipeline._run_identity(_DATA, ircc=None)
    moved = _data_copy(tmp_path / "moved")
    artifact = moved / LIVING_ARRANGEMENT_ARTIFACT
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    artifact.write_text(json.dumps(payload, indent=4, sort_keys=True) + "\n", encoding="utf-8")
    assert pipeline._run_identity(moved, ircc=None) != base       # data moved
    monkeypatch.setattr(pipeline, "assumptions_hash", lambda: "0" * 16)
    assert pipeline._run_identity(_DATA, ircc=None) != base       # assumptions moved


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
    data-vs-code attribution could not be made for the inputs that drive the whole run."""
    edited = _data_copy(tmp_path / "edited")
    artifact = edited / OWNERSHIP_ARTIFACT
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    band = next(iter(payload["rates"][Geography.MTL_RMR.value]))
    payload["rates"][Geography.MTL_RMR.value][band] += 0.05        # a valid fraction, still
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pristine = pipeline._source_hashes(_DATA, ircc=None)
    moved = pipeline._source_hashes(edited, ircc=None)
    assert OWNERSHIP_ARTIFACT in pristine, "the envelope does not cover the derived rate artifacts"
    assert pristine[OWNERSHIP_ARTIFACT]["sha256"] != moved[OWNERSHIP_ARTIFACT]["sha256"]
    assert pipeline._run_identity(edited, ircc=None) != pipeline._run_identity(_DATA, ircc=None)
    # the edit really does move the model, which is why the envelope must be able to see it
    from demoflow.loaders.census import load_ownership_rates, ownership_rate
    assert ownership_rate(load_ownership_rates(data_dir=edited), Geography.MTL_RMR, 40) != \
        ownership_rate(load_ownership_rates(data_dir=_DATA), Geography.MTL_RMR, 40)


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
    from mcp_server.engine import mortality

    before = pipeline._source_hashes(_DATA, ircc=None)
    identity_before, assumptions_before = pipeline._run_identity(_DATA, ircc=None), assumptions_hash()

    monkeypatch.setattr(mortality, "_base_cache", {})          # else the loaded arrays answer
    monkeypatch.setitem(mortality._BASE_TABLES, "CPM2014_combined",
                        ("cpm2014_public_male.csv", "cpm2014_public_female.csv", 2014))
    after = pipeline._source_hashes(_DATA, ircc=None)

    assert before[BASIS_SOURCE_KEY]["sha256"] != after[BASIS_SOURCE_KEY]["sha256"]
    assert {k: v for k, v in before.items() if k != BASIS_SOURCE_KEY} == \
        {k: v for k, v in after.items() if k != BASIS_SOURCE_KEY}, \
        "the basis swap moved a FILE digest — the probe is not isolating what it claims"
    assert pipeline._run_identity(_DATA, ircc=None) != identity_before
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
    correctly) and the whole suite green, while moving rank-1 HORS_RMR's mean ED from
    -0.00029045 to -0.00042867 — carry B3's exact named defect restored, and the join back to
    decoration.

    THE PROVENANCE LEG IS WHAT KILLS THAT MUTANT, and the value legs alone measurably do NOT:
    the bypass was PARTIAL — `_standing_stock` and `_band_entry_stock` still read through the
    reader — so the series computed with a shipped-forced reader still differed from the
    published one and every `!=` leg stayed green (measured: 52/52 under the mutant). A
    geography the join sends to the aligned curve must never read the shipped curve AT ALL, at
    any point in the function, which is the property carry B3 actually names. Both legs are
    kept: the provenance leg catches a bypass anywhere on the path, the value legs catch a
    consumer that reads the right curve and computes the wrong number from it.
    """
    from demoflow.loaders.hors_aligned import aligned_ownership_rate

    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    def series(geo, read_ownership):
        return pipeline._ed_series(geo, Scenario.REFERENCE, frames, read_ownership,
                                   pipeline.CENTRAL_LEG)

    # --- value: the published series IS the aligned curve's, and the choice moves the number.
    # The shipped-forced reader is built on a REPLICA join, never the committed one, whose
    # loader refuses a second aligned row (`hors_aligned._verify_join`'s scope fence).
    replica = {geo: dict(row) for geo, row in read.join.items()}
    replica[Geography.HORS_RMR.value]["reads"] = "shipped"
    published = series(Geography.HORS_RMR, read)
    aligned_only = series(Geography.HORS_RMR,
                          lambda geo, age: aligned_ownership_rate(read.aligned, geo, age))
    misaligned = series(Geography.HORS_RMR,
                        pipeline._OwnershipReader(read.shipped, read.aligned, replica))
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

    IT NOW COVERS TWELVE LEGS RATHER THAN TWO (run-33's five axes plus ruling V's shape axis)
    and the assertion is
    unchanged, which is the point: widening the sweep must not widen the gate's scope with it."""
    calls = []
    monkeypatch.setattr(pipeline, "check_reconciliation", lambda retention: calls.append(retention))
    lo, hi = SWEEP_GRID["q_live_per_year"]
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geos = [Geography.MTL_RMR, Geography.QC_RMR]
    central = pipeline._ed_dict(geos, frames, read, pipeline.CENTRAL_LEG)
    stable = pipeline._rank_stability(geos, frames, read, central)
    assert calls == [], "a sweep leg ran the central-run-only reconciliation gate"
    assert set(stable) == set(geos)
    assert len(pipeline._sweep_legs()) == 12
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
    """`rollforward` emits {estate, living}; `phi_market` accepts {estate, voluntary}. The
    mapping is EXPLICIT and total in both directions — a positional hand-off would put the
    estate flow through the voluntary fraction with every number still plausible."""
    from demoflow.cohort.listings import phi_market
    assert EXIT_CAUSE_TO_LISTING_CAUSE == {"estate": "estate", "living": "voluntary"}
    for cause in EXIT_CAUSE_TO_LISTING_CAUSE.values():
        phi_market(cause)                      # every mapped cause is one phi_market knows
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

    Measured, handing `native_formation` the RAW ISQ maps instead: MTL_RMR's mean ED
    +0.002767760 -> +0.003883128 (+40%) and rank-1 HORS_RMR's SIGN flips, -0.000290446 ->
    +0.001087254 — a reordered published ranking with the rest of the suite green.

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
    comment — and measured, swapping it for `resident_t` moved MTL_RMR's mean ED from
    +0.00276776 to +0.00297395 (+7.4%, away from zero exactly as the comment predicts) with the
    whole suite still green.

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
    got = pipeline._band_entry_stock(pop_g_s, year, geo, frames.la, read)

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
        pop_g_s, year, geo, frames.la, read).owner_units


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
        pipeline._band_entry_stock(pop_g_s, 2052, Geography.MTL_RMR, frames.la, read)


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

    MEASURED SURVIVABLE, which is why this is a test and not a comment. A mutant that ignores the
    four grid fields inside `_ed_series` (reading `CENTRAL_LEG`'s values in their place) leaves 8
    of the 12 legs INERT at max|delta ED| = 0.0 and passes the ENTIRE suite — the axis-coverage
    test above, the `rank_stable is False` pin, and both golden byte-matches included. Nothing
    sees it because the CENTRAL run is untouched, so no golden byte moves; and because the ratio
    axis ALONE saturates the union verdict (it reorders all eight rows at 0.155), so `false` on
    every row stays satisfiable by ONE live axis. A one-axis sweep is exactly the defect run 33
    exists to close, and it would have shipped green a second time.

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

    `false` on all eight rows is the CORRECT output of the six-axis sweep, not a regression:
    the join-table ratio axis reorders the published ranking at both of its declared endpoints,
    and the union over every axis therefore finds no geography whose rank is unchanged
    everywhere. The four grid axes alone leave the order intact — which is exactly why sweeping
    one of them and calling it `rank_stable` produced a green verdict for a year.

    It also kills the one silent failure the axis-coverage test above cannot see: a
    `_sweep_legs()` that returned NOTHING would satisfy every set assertion vacuously and make
    the union verdict trivially TRUE.
    """
    rows = run["_docs"]["rankings"]["rankings"]
    assert len(rows) == len([g for g in Geography])
    assert [r["rank_stable"] for r in rows] == [False] * len(rows), (
        "the six-axis sweep reorders the ranking at the join-table ratio endpoints, so no row "
        "is rank-stable on the committed vintage — a True here means an axis stopped being swept")


def test_the_join_table_ratio_endpoint_is_the_axis_THAT_REORDERS(run):
    """WHICH axis carries the verdict, measured rather than asserted — so a future regression
    that drops the ratio leg reds HERE with its cause named, instead of flipping eight booleans
    back to `true` with no reader able to say why.

    MEASURED at the low endpoint 0.155, and the permutation reproduces run-32's quant and stress
    gates independently (both ran an out-of-tree harness, this runs the shipped code): HORS_RMR
    1->4, LAURENTIDES 2->6, LANAUDIERE 3->7, LAVAL_RA13 4->1, MONTEREGIE 5->3, MTL_RMR 6->2,
    QC_RMR 7->8, MTL_ISLAND_RA06 8->5. Every ranked geography moves, and rank 1 — the geography
    the whole artifact exists to name — changes hands. The 1.033 endpoint moves four rows; the
    union is what `rank_stable` reports.

    Only the LOW endpoint is evaluated here, and that is a cost decision stated rather than
    hidden: it is one ED grid, it is the endpoint that moves every row, and the union over all
    twelve legs is already covered by the run fixture's own `rank_stable` above.
    """
    frames = pipeline._load_all(_DATA)
    read = pipeline._ownership_reader(_DATA)
    geos = [g for g in Geography if g in set(frames.pop["geography"])]
    lo, _hi = CONSTANTS["immigrant_ownership_ratio_sweep_span"].value
    leg = dataclasses.replace(pipeline.CENTRAL_LEG, immigrant_ownership_ratio=lo)

    swept = rank_geographies(pipeline._ed_dict(geos, frames, read, leg))
    swept_order = [r.geography.value for r in sorted(swept, key=lambda r: r.rank)]
    central_order = [r["geography"] for r in run["_docs"]["rankings"]["rankings"]]

    assert set(swept_order) == set(central_order)
    moved = [g for g in central_order if central_order.index(g) != swept_order.index(g)]
    assert moved == central_order, f"only {len(moved)} of {len(central_order)} rows moved"
    assert swept_order[0] != central_order[0], "rank 1 did not change hands"


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
# which loads five workbooks, evaluates the ED grid twelve times (the central run, reused as one
# of the six-axis sweep's twelve legs — ~20s of real I/O) and writes BOTH artifacts — so asking for six
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
    care about the robustness verdict, and paying twelve ED grids for each of them is what
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
    assert pipeline._rank_stability(geos, frames, read, central, sweep_axes=()) == {
        g: False for g in geos}
    assert pipeline._rank_stability(geos, frames, read, central,
                                    sweep_axes=("q_live_per_year",)) == {g: False for g in geos}
    with pytest.raises(CalibrationError, match="not declared"):
        pipeline._rank_stability(geos, frames, read, central, sweep_axes=("no_such_axis",))
    assert len(pipeline._sweep_legs(("q_live_per_year",))) == 2
