"""P10 gates — is the ALIGNED hors-RMR residual built from a resolved territory, or guessed?

P10's product is a pair of immigrant inputs measured over a census residual whose territory
matches the ISQ flow row it multiplies, plus a SIZE for the ownership contamination amendment
#12(B) rules must not be corrected. Both halves fail the same way — a number that reads as
measured but rests on a membership nobody resolved, and a "near-uniform" verdict that could not
have come out otherwise — so these gates hold the note to:

  1. the Québec-part membership is RESOLVED from a live source and CLOSES on the CMA it
     partitions, with the Québec side selected two independent ways that must agree;
  2. the membership is VALIDATED against the ISQ row it aligns to, like-for-like universe,
     against a threshold DERIVED from innocent controls measured in the same construction;
  3. the withheld CSD cells are BOUNDED FIELD-WISE by a published complement rather than
     dropped, and the resulting envelope may not straddle the finding it is published under;
  4. every floor guard fires on a mutant applied to the fixture the green path really reads;
  5. the note regenerates BYTE-IDENTICALLY from that fixture through the real producer; and
  6. every figure the provenance header counts actually appears in the body — a registry that
     counts a figure the reader cannot find is describing a different document.

  PASS iff the note records EITHER
    (a) `MEASURED` carrying every evidence token, each agreeing with the producer; OR
    (b) `UNKNOWN-PROBE-FAILED` with a recorded exception TYPE and boundary.
  FAIL on an unresolved `[FILL`, a missing or unresolved token under a MEASURED verdict, or a
    note figure the producer does not reproduce.
  SKIP-with-reason ONLY if the recorded exception TYPE is network-class AND www150 is
    independently confirmed unreachable, probed with the SAME HTTP METHOD run_p10.py uses for
    it (POST — `getCubeMetadata` rejects GET, so a GET liveness check reports a healthy service
    as down and launders every recorded failure into a skip).

  The green path is entirely OFFLINE: the WDS and workbook boundaries are replaced by
  `fixtures/p10_boundary_capture.json`, one recording of the live responses (see
  `fixtures/make_p10_fixture.py` for what it contains and what it trims).
"""

import ast
import copy
import json
import re
from pathlib import Path

import pytest

from . import test_probes_common as common
from ._probe_asserts import (
    NETWORK_EXCEPTIONS,
    recorded_failure_type as _recorded_failure_type,
    source_reachable,
    token as _token,
)

PROBES = Path(__file__).resolve().parent.parent / "probes"
NOTE = PROBES / "P10-hors-operand-alignment.md"
CAPTURE = Path(__file__).resolve().parent / "fixtures" / "p10_boundary_capture.json"

WDS_LIVENESS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
LIVENESS_PID = 98100621
REACHABILITY_TIMEOUT = 10

# "NOT-FOUND" and "NONE" are INSIDE this set on purpose: P10 has no legitimate not-found
# outcome. Its only earned verdict is a measurement, and every DECISION token it emits is a
# value, a source, a residual or a verdict — a token reading NONE would be an unresolved field
# wearing an answer's clothes.
UNRESOLVED = {"", "UNKNOWN-PROBE-FAILED", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL", "[FILL]",
              "N/A", "NONE", "NOT-FOUND", "?"}

MEASURED = "MEASURED"
EVIDENCE_TOKENS = (
    "DECISION-CONSTRUCTION",
    "DECISION-ALIGNED-HEADSHIP",
    "DECISION-ALIGNED-RATIO",
    "DECISION-IMMIGRANT-LEG",
    "DECISION-BRACKET",
    "DECISION-BRACKET-ENCLOSURE",
    "DECISION-MEMBERSHIP",
    "DECISION-MEMBERSHIP-GATE",
    "DECISION-SUPPRESSION",
    "DECISION-ISQ-SEPARABILITY",
    "DECISION-CENSUS-INSEPARABILITY",
    "DECISION-DIRECT-SOURCE",
    "DECISION-RHO-CONTAMINATION",
    "DECISION-RHO-VERDICT",
    "DECISION-CATALOGUE-CLOSURE",
    "DECISION-SCOPE",
)


def _source_reachable() -> bool:
    """Is the WDS metadata endpoint answering? POST — the method run_p10.py uses for it."""
    return source_reachable(
        WDS_LIVENESS,
        timeout=REACHABILITY_TIMEOUT,
        method="POST",
        data=json.dumps([{"productId": LIVENESS_PID}]).encode(),
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture(scope="module")
def probe():
    return common._load_probe("p10")


@pytest.fixture(scope="module")
def note() -> str:
    assert NOTE.exists(), f"{NOTE} was never written — run probes/run_p10.py"
    return NOTE.read_text(encoding="utf-8")


def _verdict(text: str) -> str:
    value = _token(text, "DECISION-VERDICT")
    assert value, "the note carries no DECISION-VERDICT token at all"
    return value


def _require_measured_or_skip(text: str) -> None:
    verdict = _verdict(text)
    if verdict == MEASURED:
        return
    assert verdict == "UNKNOWN-PROBE-FAILED", f"unknown verdict {verdict!r}"
    failure = _recorded_failure_type(text)
    assert failure, "an UNKNOWN verdict must record the exception TYPE that produced it"
    assert failure in NETWORK_EXCEPTIONS, (
        f"the note records a {failure} — a code/structural fault, not an outage. It must FAIL "
        f"here rather than launder into a skip.")
    assert not _source_reachable(), (
        f"the note records a {failure} but www150 answers POST right now — a recorded failure "
        f"against a healthy service is a real defect, not an outage.")
    pytest.skip(f"P10 recorded {failure} and www150 is confirmed unreachable")


# ===========================================================================
# THE OFFLINE FIXTURE — one recording of the live boundaries, replayed.
# ===========================================================================
_CAPTURE = json.loads(CAPTURE.read_text(encoding="utf-8"))
_CELLS = {tuple(key.split("|", 1)): value for key, value in _CAPTURE["cells"].items()}
_CELLS = {(int(pid), coordinate): value for (pid, coordinate), value in _CELLS.items()}
_REF_PER = "2021-01-01"
# Filler geography members are published at geoLevel 504 (census agglomeration) — a level these
# cubes really carry, and deliberately NOT 505: the note's Québec-part scan counts members at
# 505, so filler at that level would manufacture the very finding the scan exists to refute.
_FILLER_GEO_LEVEL = 504


def _pad(members: list, total: int) -> list:
    """Grow a trimmed member list back to the dimension's REAL size with inert filler.

    The live counts (166 / 5,468 / 1,159 / 63 geography members) are printed by the note and
    scanned by the Québec-part search, so a fixture carrying only the resolved members would
    make both unreproducible and the byte-equality gate meaningless. Filler cannot collide with
    a resolved member: its ids continue past the largest real one, its name is unique, it
    carries no classification code and no parent.
    """
    out = list(members)
    base = max((m["memberId"] for m in out), default=0) + 1
    for index in range(total - len(out)):
        out.append({"memberId": base + index, "memberNameEn": f"filler-{base + index}",
                    "geoLevel": _FILLER_GEO_LEVEL, "parentMemberId": None,
                    "classificationCode": None})
    assert len(out) == total, (len(out), total)
    return out


def _cube(pid: int) -> dict:
    entry = _CAPTURE["cubes"][str(pid)]
    dimensions = []
    for dim in entry["dimensions"]:
        members = [{"memberId": m["id"], "memberNameEn": m["name"], "geoLevel": m["geoLevel"],
                    "parentMemberId": m["parent"], "classificationCode": m["code"]}
                   for m in dim["members"]]
        dimensions.append({"dimensionPositionId": dim["pos"], "dimensionNameEn": dim["name"],
                           "member": _pad(members, dim["total"])})
    return {"productId": str(pid), "cubeTitleEn": entry["title"],
            "releaseTime": entry["release"], "archiveStatusEn": entry["archive"],
            "dimension": dimensions}


def _fake_meta(pids) -> list:
    """`getCubeMetadata` for the eight cubes, shaped like the live responses.

    DEEP-COPIED on the way out, and that is load-bearing rather than tidy: the mutation battery
    edits member dicts in place, and handing out shared objects would let one mutant's edit
    persist into every later test in the same process — a mutant that fires for the wrong
    reason is an unreachable mutant wearing a green tick.
    """
    return copy.deepcopy([{"status": "SUCCESS", "object": _cube(int(p))} for p in pids])


def _fake_data(requests: list, cells: dict | None = None) -> list:
    """`getData`, returned SORTED BY COORDINATE STRING and withholding what StatCan withholds.

    Not in request order — that is what the live endpoint does (measured 2026-08-07, recorded in
    run_p7.py), and a probe that zipped the two would pair every value with the wrong meaning
    while every count still looked plausible. A cell absent from the capture is returned the way
    the live endpoint returns a withheld one: `status: FAILED` with an EMPTY vectorDataPoint.
    """
    table = _CELLS if cells is None else cells
    out = []
    for request in requests:
        key = (int(request["productId"]), request["coordinate"])
        if key in table:
            out.append({"status": "SUCCESS",
                        "object": {"productId": str(key[0]), "coordinate": key[1],
                                   "vectorDataPoint": [{"refPer": _REF_PER,
                                                        "value": table[key]}]}})
        else:
            out.append({"status": "FAILED",
                        "object": {"productId": str(key[0]), "coordinate": key[1],
                                   "vectorDataPoint": []}})
    out.sort(key=lambda o: (o["object"]["coordinate"], o["object"]["productId"]))
    return out


def _isq_sheet(name: str, sheets: dict | None = None) -> list:
    """Rebuild a pinned workbook's row grid from the sparse capture, at its real width."""
    entry = (sheets or _CAPTURE["isq"])[name]
    width = entry["width"]

    def row(sparse: dict) -> tuple:
        cells = [None] * width
        for index, value in sparse.items():
            cells[int(index)] = value
        return tuple(cells)

    return [row(r) for r in entry["head"]] + [row(r) for r in entry["body"]]


def _wire(probe, tmp_path: Path, **overrides):
    """Point the probe's boundary seams at the fixture and its output at `tmp_path`.

    `new_run()` too: `_sections` registers `Fact`s, and a Fact with no active run raises a
    RuntimeError rather than the ProbeRefusal the guard tests look for — which would make every
    mutant below pass for the wrong reason. `main()` opens its own run.
    """
    probe.new_run()
    probe._meta = overrides.get("meta", _fake_meta)
    probe._data = overrides.get("data", _fake_data)
    probe._isq_rows = overrides.get("isq", _isq_sheet)
    for name, attribute in (("spec", "_spec_s6"), ("bracket", "_bracket_record"), ("p9", "_p9_note"),
                            ("constants", "_constants_source")):
        if name in overrides:
            setattr(probe, attribute, overrides[name])
    probe.OUT = tmp_path / "P10-offline.md"
    return probe.OUT


def _run_offline(probe, tmp_path: Path, **overrides) -> str:
    out = _wire(probe, tmp_path, **overrides)
    probe.main()
    return out.read_text(encoding="utf-8")


@pytest.fixture
def offline(tmp_path):
    """A fresh probe module wired to the fixture — module-scoped state cannot leak."""
    return common._load_probe("p10"), tmp_path


# ===========================================================================
# 1. The committed note: is the verdict resolved and is every token present?
# ===========================================================================
def test_p10_no_unfilled_placeholder(note):
    assert "[FILL" not in note, "an unresolved placeholder survived into the committed note"


def test_p10_records_a_resolved_verdict(note):
    _require_measured_or_skip(note)
    for name in EVIDENCE_TOKENS:
        value = _token(note, name)
        assert value is not None, f"a MEASURED note must carry `{name}`"
        assert value not in UNRESOLVED, f"`{name}` is unresolved: {value!r}"


def test_p10_note_is_generated_by_the_probe_that_claims_it(note):
    assert "Written by `probes/run_p10.py`" in note
    assert "nothing in this file is hand-edited" in note


def test_p10_the_scope_token_keeps_this_a_measurement_and_not_a_wiring(note):
    """The ordering constraint IS the deliverable's boundary: P8's note is citation-coupled to
    §6's figures, so wiring before the spec ruling would couple it to numbers §6 no longer
    carries. The note must say so where a consumer reads it."""
    scope = _token(note, "DECISION-SCOPE")
    assert "MEASURE ONLY" in scope, scope
    for name in ("immigrant_inputs.py", "run_p8.py", "P8-immigrant-inputs.md"):
        assert name in scope, f"the scope token does not name {name} as untouched"


# ===========================================================================
# 2. The producer, offline: regen equality against the committed note
# ===========================================================================
def test_p10_note_regenerates_byte_identically_from_the_fixture(offline, note):
    """REGEN EQUALITY ON THE PRODUCER, not on the artifact.

    A gate that only re-read the committed note would go green under any producer mutation the
    moment the note was regenerated through it. This runs the real derivation over a recording
    of the live boundaries and compares BYTES with what ships.
    """
    mod, tmp_path = offline
    got = _run_offline(mod, tmp_path)
    assert got == note, (
        "the producer no longer reproduces the committed note. If the live source moved, "
        "regenerate the note AND the fixture (tests/fixtures/make_p10_fixture.py) together — "
        "they are the two halves of one claim.")
    assert _run_offline(mod, tmp_path) == got, "the note is not deterministic across two runs"


def test_p10_reads_no_clock(probe):
    """No date may enter the note from the wall clock: a `date.today()` would look right on the
    day the note was built and break regen equality on the next — a one-day fuse no single run
    can see."""
    tree = ast.parse((PROBES / "run_p10.py").read_text(encoding="utf-8"))
    clocks = {("datetime", "now"), ("date", "today"), ("time", "time"), ("time", "monotonic")}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id, node.func.attr) in clocks):
            raise AssertionError(f"run_p10.py calls {node.func.value.id}.{node.func.attr}() at "
                                 f"line {node.lineno} — the note would stop regenerating")


# ===========================================================================
# 3. The arithmetic, directly — the definitions as code
# ===========================================================================
def test_p10_cell_arithmetic_is_the_definition_not_a_gloss(probe):
    cell = probe.Cell(persons=1000, maintainers=500, owner_maintainers=250)
    assert cell.headship == 0.5 and cell.owner_propensity == 0.5
    part = probe.Cell(persons=400, maintainers=100, owner_maintainers=40)
    assert probe.cell_minus(cell, part) == probe.Cell(600, 400, 210)
    assert probe.cell_sum([part, part]) == probe.Cell(800, 200, 80)
    assert probe.ownership_ratio(cell, part) == pytest.approx(0.5 / 0.4)


def test_p10_a_zero_denominator_refuses_rather_than_publishing_a_rate(probe):
    empty = probe.Cell(persons=0, maintainers=0, owner_maintainers=0)
    with pytest.raises(probe.ProbeRefusal):
        _ = empty.headship
    with pytest.raises(probe.ProbeRefusal):
        _ = empty.owner_propensity


def test_p10_relative_delta_is_a_relative_delta(probe):
    """#12(B) is written about a relative SCALING of ρ, because that is the one that cancels in
    ED. A percentage-point difference beside that sentence would be a different quantity."""
    assert probe.relative_pct(0.7012, 0.6909) == pytest.approx(1.4908, abs=1e-3)
    assert probe.relative_pct(1.0, 1.0) == 0.0
    with pytest.raises(probe.ProbeRefusal):
        probe.relative_pct(1.0, 0.0)


def test_p10_threshold_is_derived_from_the_innocent_controls(probe):
    """DERIVED, never inherited: a threshold that does not move with its calibration set is a
    hand-typed number one level up."""
    small = probe.derive_threshold({"a": -0.4, "b": 0.6})
    big = probe.derive_threshold({"a": -0.4, "b": 0.6, "c": 2.0})
    assert small["max_name"] == "b" and small["max_abs"] == pytest.approx(0.6)
    assert big["threshold"] > small["threshold"]
    assert small["threshold"] == pytest.approx(0.6 * (1 + probe.MARGIN_FRACTION))
    with pytest.raises(probe.ProbeRefusal):
        probe.derive_threshold({})
    with pytest.raises(probe.ProbeRefusal):
        probe.derive_threshold({"a": 0.0})


# ===========================================================================
# 4. Suppression — field-wise, bounded, and never straddling the finding
# ===========================================================================
def test_p10_the_bounded_sum_is_field_wise(probe):
    """The defect this shape exists to refuse: these subdivisions publish settled PERSONS while
    withholding settled MAINTAINERS, so dropping the whole geography would net a territory's
    persons out of one denominator and its maintainers out of another — which does not merely
    widen the interval, it MOVES the point estimate."""
    low, high, withheld = probe.bounded_sum([((100, None, 25), (9, 4, 2)),
                                             ((10, 5, 5), (0, 0, 0))])
    assert withheld == 1
    assert low == (110, 5, 30), "a published field must count at BOTH ends of the interval"
    # Only the withheld field widens: fields 0 and 2 are published at both geographies, so
    # their bounds (9 and 2) are never added — an interval that widened a field the source
    # states would be reporting uncertainty the data does not have.
    assert high == (110, 9, 30)


def test_p10_a_withheld_field_with_no_bound_refuses(probe):
    with pytest.raises(probe.ProbeRefusal):
        probe.bounded_sum([((None, 1, 1), (None, 0, 0))])
    with pytest.raises(probe.ProbeRefusal):
        probe.bounded_sum([])


def test_p10_the_complement_bound_is_clamped_and_the_clamp_is_reported(probe):
    """Both inputs are rounded to 5 independently, so a geography with no immigrants at all can
    publish a total one step BELOW its non-immigrant count. A negative bound would put the top
    of an interval under its bottom."""
    bound, clamped = probe.complement_bound(probe.Cell(100, 50, 25), probe.Cell(90, 45, 20))
    assert bound == probe.Cell(10, 5, 5) and clamped == 0
    bound, clamped = probe.complement_bound(probe.Cell(100, 50, 25), probe.Cell(105, 50, 25))
    assert bound == probe.Cell(0, 0, 0) and clamped == 1


def test_p10_the_envelope_is_taken_at_the_boxs_corners(probe):
    """Pairing low-with-low reports an interval NARROWER than the uncertainty: headship is
    largest when the fewest maintainers and the MOST persons are netted out, and those are
    opposite corners of the box the withheld cells leave."""
    shipped = probe.Cell(1000, 500, 250)
    low = probe.Cell(100, 50, 25)
    high = probe.Cell(120, 60, 35)
    nonimm = probe.Cell(800, 400, 200)
    got = probe.bounded_pair(shipped, low, high, nonimm)
    assert got["headship"] == pytest.approx(450 / 900)
    assert got["headship_band"][0] == pytest.approx(440 / 900)
    assert got["headship_band"][1] == pytest.approx(450 / 880)
    assert got["headship_band"][0] < got["headship"] < got["headship_band"][1]
    assert got["ratio_band"][0] < got["ratio"] < got["ratio_band"][1]


def test_p10_the_ratio_band_must_not_straddle_the_finding(probe):
    """The qualitative claim is that the ALIGNED ratio crosses 1.0. If the envelope contains 1.0
    the crossing is not earned at this run's own resolution, and a verdict inside its own
    uncertainty is not a verdict."""
    probe._guard_ratio_band(1.0244, 1.0264)
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_ratio_band(0.9950, 1.0100)


def test_p10_the_measured_envelope_clears_one_and_the_note_publishes_it(offline, note):
    """On the real numbers, not on a constructed pair: both ends of the measured envelope sit
    above 1.0, and the note prints the envelope beside the point estimate rather than only the
    point estimate."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    aligned = mod.LAST_RUN["aligned"]
    low, high = aligned["ratio_band"]
    assert low > 1.0 and high > 1.0, (low, high)
    assert aligned["pair"][1] > 1.0 > mod.LAST_RUN["shipped"]["pair"][1], (
        "the run no longer measures the ratio CROSSING 1.0 — the note's qualitative claim")
    assert f"[{low:.4f}, {high:.4f}]" in note, "the note does not publish the ratio envelope"
    token = _token(note, "DECISION-ALIGNED-RATIO")
    assert f"{low:.4f}-{high:.4f}" in token and "CROSSES 1.0" in token, token


def test_p10_every_count_in_the_suppression_paragraph_is_measured_over_its_own_set(offline):
    """§4d's counts must each be measured over the set the sentence attaches them to.

    The defect class this closes is quiet because BOTH numbers are individually true: the
    withheld CELLS span two cube pairs (settled-immigrant triples in 98-10-0622-01 and
    maintainer-age bands in 98-10-0232-01), while the settled triple's incomplete-CSD count
    spans one. Composed into "N cells came back with no data point, at M subdivisions" they
    read as one measurement of one set, and M is then the wrong number for N — a subdivision
    withholding only ρ cells is dropped, one withholding only settled cells is counted.

    Re-derived here from the BOUNDARY TRAFFIC and the fixture, never from the producer's own
    `withheld`/`incomplete`: a gate reading those variables would restate the producer instead
    of checking it. The geography ids are inverted PER CUBE, and the reason is a namespace
    rather than a measured disagreement — 98-10-0622-01 and 98-10-0232-01 DO agree on all 16
    QC-part CSDs at this vintage, which is exactly why a shared map is worth declining: it
    would pass here today and mis-key silently the first time the agreement lapses.
    """
    mod, tmp_path = offline
    seen: list[tuple[int, str]] = []

    def data(requests):
        seen.extend((int(r["productId"]), r["coordinate"]) for r in requests)
        return _fake_data(requests)

    text = _run_offline(mod, tmp_path, data=data)
    code_of = {}
    for pid in (mod.CD_PID, mod.RHO_CD_PID):
        geo = next(d for d in _CAPTURE["cubes"][str(pid)]["dimensions"] if d["pos"] == 1)
        code_of[pid] = {m["id"]: m["code"] for m in geo["members"]}
    qc_codes = set(mod.PINNED_QC_PART_CODES)

    def csd_code(pid: int, coordinate: str):
        return code_of.get(pid, {}).get(int(coordinate.split(".")[0]))

    withheld = [(pid, c) for pid, c in seen
                if (pid, c) not in _CELLS and csd_code(pid, c) in qc_codes]
    per_cube = {pid: sum(1 for p, _ in withheld if p == pid)
                for pid in (mod.CD_PID, mod.RHO_CD_PID)}
    subdivisions = {csd_code(pid, c) for pid, c in withheld}
    assert min(per_cube.values()) > 0, (
        f"the fixture no longer withholds cells in both cube pairs ({per_cube}), so this gate "
        f"would pass vacuously — re-derive it or delete it")

    para = text.split("### 4d.")[1].split("Both ends are carried")[0]
    lead = re.search(r"([\d,]+) came back with no data point, at ([\d,]+) of the ([\d,]+) "
                     r"subdivisions", para)
    assert lead, f"§4d no longer opens with the requested-cells sentence: {para[:400]!r}"
    cells, at_csds, of_csds = (int(g.replace(",", "")) for g in lead.groups())
    assert cells == len(withheld), (cells, len(withheld))
    assert at_csds == len(subdivisions), (
        f"§4d attaches {at_csds} subdivisions to its {cells} withheld cells, which actually "
        f"fall at {len(subdivisions)}: {sorted(subdivisions)}. The two counts are measured "
        f"over different sets.")
    assert of_csds == len(mod.PINNED_QC_PART_CODES), (of_csds, mod.PINNED_QC_PART_CODES)

    # Each cube's own count, attached to that cube — the decomposition, held to the same rule.
    for pid, count in per_cube.items():
        assert re.search(rf"\b{count}\b[^.]*{re.escape(mod.table_number(pid))}", para), (
            f"§4d does not attach {pid}'s own {count} withheld cells to "
            f"{mod.table_number(pid)}: {para!r}")

    # And the population claim: "at most N people" must be the max over the SAME subdivisions.
    member = _CAPTURE["cubes"][str(mod.MEMBER_PID)]
    geo_dim = next(d for d in member["dimensions"] if d["pos"] == 1)
    stat_dim = next(d for d in member["dimensions"] if d["pos"] != 1)
    count_id = next(m["id"] for m in stat_dim["members"]
                    if m["name"] == mod.MEMBER_COUNT_2021)
    pops = {m["code"]: _CELLS[(mod.MEMBER_PID, mod.coord(m["id"], count_id))]
            for m in geo_dim["members"] if m["code"] in subdivisions}
    assert len(pops) == len(subdivisions), (sorted(pops), sorted(subdivisions))
    assert f"at most {max(pops.values()):,.0f} people" in para, (
        f"§4d's population ceiling is not the maximum over the {len(subdivisions)} "
        f"subdivisions its cells fall at ({max(pops.values()):,.0f}): {para!r}")


# ===========================================================================
# 5. Membership — resolved, closed, cross-checked, validated
# ===========================================================================
def test_p10_membership_must_close_on_the_cma_it_partitions(probe):
    probe._guard_membership_closes({"a": 60, "b": 40}, 100)
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_membership_closes({"a": 60, "b": 41}, 100)
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_membership_closes({}, 100)


def test_p10_the_quebec_side_is_selected_two_ways_and_they_must_agree(probe):
    """SGC prefix and census-tree ancestry are two independent readings of one claim. A
    disagreement is a finding about the geography axis, never a tie broken by whichever ran
    first."""
    probe._guard_qc_split([("Gatineau", True, True), ("Ottawa", False, False)])
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._guard_qc_split([("Gatineau", True, False)])
    assert "Gatineau" in str(exc.value)
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_qc_split([])


def test_p10_the_membership_gate_is_two_sided_and_names_its_controls(probe):
    probe._guard_membership_pop(-0.752, 1.109, {"MTL": -0.887})
    for bad in (1.5, -1.5):
        with pytest.raises(probe.ProbeRefusal) as exc:
            probe._guard_membership_pop(bad, 1.109, {"MTL": -0.887})
        assert "MTL" in str(exc.value)


def test_p10_the_resolved_part_sits_inside_the_innocent_spread(offline):
    """The strongest honest sentence the gate supports, asserted on the real numbers: not "it
    passes" — which is a function of the margin — but "it is less discrepant than territories
    whose census↔ISQ identity is settled"."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    membership = mod.LAST_RUN["membership"]
    innocent = [abs(v) for v in membership["innocent"].values()]
    assert membership["children"] == 25 and membership["qc"] == 16
    assert abs(membership["residual"]) < max(innocent), "no longer inside the innocent spread"
    assert abs(membership["residual"]) <= membership["threshold"]
    assert membership["threshold"] != 1.0, "the gate is not carrying an inherited 1%"


def test_p10_the_exact_construction_is_not_the_whole_cd_bracket(offline, note):
    """Preference order, measured: the fallback the mandate ranked second does NOT reproduce the
    exact pair, and the note says which half it misses rather than presenting the bracket as if
    it enclosed the answer."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    run = mod.LAST_RUN
    headships = [pair[0] for pair in run["bracket"].values()]
    ratios = [pair[1] for pair in run["bracket"].values()]
    assert len(run["bracket"]) == 3
    assert run["encloses"]["headship"] == (min(headships) <= run["aligned"]["pair"][0]
                                           <= max(headships))
    assert run["encloses"]["ratio"] == (min(ratios) <= run["aligned"]["pair"][1] <= max(ratios))
    assert not run["encloses"]["headship"], (
        "the whole-CD bracket now encloses the exact headship — the note's §5a claim is the "
        "opposite and must be regenerated with the measurement")
    enclosure = _token(note, "DECISION-BRACKET-ENCLOSURE")
    assert "headship OUTSIDE" in enclosure and "ratio INSIDE" in enclosure, enclosure


# ===========================================================================
# 6. The ownership leg — BOTH halves of the verdict, held to the measurement
# ===========================================================================
def test_p10_the_rho_verdict_states_the_false_premise_and_refuses_the_easy_bound(offline, note):
    """#12(B) rests on ρ scaling BAND-UNIFORMLY. The measurement contradicts that, and the
    tempting repair — "the residual is bounded by the spread" — does not survive ED's own
    algebra: ED's numerator is a DIFFERENCE of flows, so a band-varying δ is AMPLIFIED there by
    D/(D−S) rather than averaged, and that factor grows without bound as the flows approach
    balance. Checked numerically at three regimes while the note was written: +1.0% relative at
    D/(D−S)=1.4, +8.4% at 7.7, +54% at 46, on one and the same measured δ set.

    So this gate holds the note to three things at once — the premise is false, the structure is
    ADVERSE (the most contaminated band is the one D_native is built from, the least is the one
    S rides), and the consequence is priced only in ED's own units. A note asserting the
    relative bound would be an unearned all-clear; one asserting alarm without the absolute
    bound would be an unearned alarm.
    """
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    rho = mod.LAST_RUN["rho"]
    bands = [rho[band]["delta"] for band in mod.RHO_BAND_ORDER]
    spread = mod.LAST_RUN["rho_spread"]
    assert spread == pytest.approx(max(bands) - min(bands))
    assert all(delta > 0 for delta in bands), "the bands are no longer same-signed"
    assert spread > 0.5, "the spread collapsed — the FALSE-premise half of the verdict moved"
    assert rho["25-54"]["delta"] == max(bands) and rho["75+"]["delta"] == min(bands), (
        "the adverse structure the note reports — D_native's band most contaminated, S's band "
        "least — no longer holds, and the note's sentence about it must move with it")
    verdict = _token(note, "DECISION-RHO-VERDICT")
    assert "FALSE as measured" in verdict, verdict
    assert f"{spread:.3f}" in verdict and "STRUCTURALLY ADVERSE" in verdict, verdict
    assert "does NOT certify" in verdict, (
        "the note must not read as clearing #12(B)'s cost/signal conclusion — the relative size "
        "of the residual depends on D/(D−S), which this probe does not measure")
    assert "D/(D−S)" in verdict, verdict
    assert "NOT a data absence" in verdict, (
        "the note must not let 'do not correct ρ' read as 'ρ cannot be corrected' — "
        "98-10-0232-01 publishes the aligned curve's other half")
    body = note[note.index("## 6."):note.index("## 7.")]
    for band in mod.RHO_BAND_ORDER:
        assert band in body, f"the note does not publish the {band} band"
    assert "ΔED / ED  =  (δ_S − δ_OS)  +  (δ_D − δ_S) × D / (D − S)" in body, (
        "the note states a consequence for ED without the identity it follows from")


# P10's ρ lattice, FROZEN at what the 2026-08-15 run measured (see the gate below for why it is
# frozen rather than refreshed). Test-owned, and deliberately a third copy: the probe publishes
# band LABELS and cube MEMBERS but not the edges those labels stand for, so a widening of P10's
# own record is a PR-visible act here rather than an inferred one.
_P10_FROZEN_BANDS = (("25-54", 25, 54), ("55-64", 55, 64), ("65-74", 65, 74), ("75+", 75, 200))


def test_p10_the_rho_bands_are_an_exact_coarsening_of_the_models_lattice(probe):
    """The probe's bands ARE the model's — at the lattice the probe RAN on, 2026-08-15.

    RE-SCOPED AT OPERATOR RULING W (2026-08-20), and the re-scope is the finding. This gate read
    `census._AGE_BAND_SPEC` LIVE and asserted the probe's four bands equalled it. That was the
    right check while the model carried the four bands P10 measured; ruling W refined the live
    lattice to seven, so a live equality read now demands the PROBE be regenerated to match.

    IT MUST NOT BE, and that is a documentary constraint rather than a feasibility one — the WDS
    endpoints this probe reads are reachable. P10 is a DATED record of a live run, and its
    four-band ρ table is the WARRANT for reversing spec §6 amendment #12(B):
    `test_hors_aligned_ownership.py` pins that measurement as
    `_P10_FOUR_BAND_SPREAD_PP = 1.2024094264527192` and asserts the refined lattice's WORST
    feasible spread EXCEEDS it, which is what makes "the refinement strengthened the reversal" a
    checked claim instead of a sentence. Re-measuring P10 at seven bands would turn that
    comparison into the spread against itself and leave `hors_aligned.py`'s "THOSE FOUR-BAND
    FIGURES ARE THE WARRANT AND ARE KEPT AS HISTORY (P10, 2026-08-15)" pointing at a note that no
    longer carries them. So the probe's lattice is frozen at what it measured, and what this gate
    checks is the RELATION between the two lattices rather than their equality.

    THE RELATION IS EXACT COARSENING, which is the property the warrant actually needs: every
    frozen band must be the union of consecutive live bands with the SAME OUTER EDGES, and its
    cube members must be exactly the live members tiled across that span — checked on BOTH cubes,
    against `census._AGE_BAND_SPEC` on the CMA side and `hors_aligned.CD_BAND_SPEC` on the CD
    side, because the two cubes publish different granularities of the same partition. That is
    stronger than the old equality in the direction that matters: it reds if the live lattice
    moves to something P10's figures cannot be compared against. RED/GREEN-measured, 2026-08-21,
    because "what would this catch" is the question a relation check has to answer — it reds on a
    moved OUTER edge of a frozen band, on a gap or overlap in the tiling, and on a dropped or
    added cube member; it stays GREEN on an INTERNAL re-cut of a frozen band's span (say `25-34` /
    `35-44` re-cut to `25-39` / `40-44`), because the frozen band is then still the exact union of
    the same members over the same population, which is precisely the comparability the warrant
    needs. It is weaker than the old equality in exactly one direction — it no longer forces the
    probe to be re-run when the model refines — and that is the point.
    """
    from demoflow.loaders import census, hors_aligned

    frozen_order = tuple(label for label, _lo, _hi in _P10_FROZEN_BANDS)
    assert probe.RHO_BAND_ORDER == frozen_order, (
        f"the probe's frozen four-band record has MOVED to {probe.RHO_BAND_ORDER} — it is a dated "
        "measurement, not a mirror of the live spec, and moving it invalidates the #12(B) "
        "reversal's warrant")
    # NON-VACUITY: the coarsening check below only does work while the two lattices DIFFER. If
    # ruling W were ever reverted, direct equality is the right assertion again and this says so
    # rather than leaving a relation check that ranges over a single band each.
    assert probe.RHO_BAND_ORDER != tuple(l for l, _lo, _hi, _m in census._AGE_BAND_SPEC), (
        "the live lattice equals the probe's frozen one again — restore the direct equality "
        "assertion rather than keeping a coarsening check with nothing to coarsen")

    for cube, frozen_spec, live_spec in (
            ("98-10-0231-01 (CMA)", probe.RHO_BANDS_CMA, census._AGE_BAND_SPEC),
            ("98-10-0232-01 (CD)", probe.RHO_BANDS_CD, hors_aligned.CD_BAND_SPEC)):
        for label, lo, hi in _P10_FROZEN_BANDS:
            inside = [b for b in live_spec if lo <= b[1] and b[2] <= hi]
            assert inside, f"{cube} {label}: no live band lies inside {(lo, hi)} at all"
            assert (inside[0][1], inside[-1][2]) == (lo, hi), (
                f"{cube} {label}: the live bands inside {(lo, hi)} run "
                f"{(inside[0][1], inside[-1][2])} — the two lattices no longer share this band's "
                "OUTER EDGES, so P10's measurement on it is not comparable to the current one")
            for prev, nxt in zip(inside, inside[1:]):
                assert nxt[1] == prev[2] + 1, (
                    f"{cube} {label}: live bands {prev[0]} and {nxt[0]} leave a gap or overlap "
                    f"inside {(lo, hi)} — the coarsening is not a partition")
            tiled = tuple(m for b in inside for m in b[3])
            assert frozen_spec[label] == tiled, (
                f"{cube} {label}: the probe measured {frozen_spec[label]} but the live lattice "
                f"tiles that span with {tiled} — the refinement is not EXACT, so P10's figure "
                "and the current one are measuring different populations")
            edges = [int(re.match(r"(\d+)", name).group(1)) for name in frozen_spec[label]]
            assert min(edges) == lo and max(edges) <= hi, (label, frozen_spec[label])


def test_p10_the_two_cubes_agree_on_the_all_households_contamination(offline, note):
    """The ρ pair and the RULED cube measure the same quantity through different crosses. Their
    agreement is what makes the band table a measurement of the territory rather than of one
    cube's quirks — and the note states it as an agreement, not as two numbers."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    assert f"{mod.LAST_RUN['rho']['TOTAL']['delta']:+.3f}%" in note
    assert "different cubes, different crosses, the same figure" in note


# ===========================================================================
# 7. Response handling — the WDS traps, and the suppressible scope
# ===========================================================================
def test_p10_responses_are_keyed_by_coordinate_not_request_order(probe):
    requests = [{"productId": 98100621, "coordinate": probe.coord(35, 1, 1, 1, 1, 12, 1),
                 "latestN": 1},
                {"productId": 98100621, "coordinate": probe.coord(24, 1, 1, 1, 1, 12, 1),
                 "latestN": 1}]
    response = list(reversed([
        {"status": "SUCCESS",
         "object": {"productId": "98100621", "coordinate": r["coordinate"],
                    "vectorDataPoint": [{"refPer": "2021-01-01", "value": i}]}}
        for i, r in enumerate(requests)]))
    series, withheld = probe._guard_response(requests, response, set())
    assert series[(98100621, requests[0]["coordinate"])] == 0
    assert series[(98100621, requests[1]["coordinate"])] == 1
    assert withheld == []


def test_p10_a_withheld_cell_is_tolerated_only_inside_the_declared_scope(probe):
    """Suppression is a property of tiny geographies, declared IN ADVANCE by coordinate. The
    same empty response outside that scope is an outage, and accepting it there would let a
    service failure read as a publication rule this note then reasons about."""
    inside = {"productId": 98100622, "coordinate": probe.coord(1954, 1, 1, 2, 1, 12, 1),
              "latestN": 1}
    outside = {"productId": 98100621, "coordinate": probe.coord(24, 1, 1, 2, 1, 12, 1),
               "latestN": 1}
    empty = [{"status": "FAILED",
              "object": {"productId": str(r["productId"]), "coordinate": r["coordinate"],
                         "vectorDataPoint": []}} for r in (inside, outside)]
    scope = {(98100622, inside["coordinate"])}
    _series, withheld = probe._guard_response([inside], [empty[0]], scope)
    assert withheld == [(98100622, inside["coordinate"])]
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._guard_response([outside], [empty[1]], scope)
    assert "suppressible" in str(exc.value)


def test_p10_a_reference_period_that_is_not_the_census_year_refuses(probe):
    requests = [{"productId": 98100621, "coordinate": probe.coord(24, 1, 1, 1, 1, 12, 1),
                 "latestN": 1}]
    response = [{"status": "SUCCESS",
                 "object": {"productId": "98100621", "coordinate": requests[0]["coordinate"],
                            "vectorDataPoint": [{"refPer": "2016-01-01", "value": 1}]}}]
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._guard_response(requests, response, set())
    assert "2021" in str(exc.value)


def test_p10_member_resolution_refuses_ambiguity_and_asserts_the_pin(probe):
    metas = {int(r["object"]["productId"]): r["object"] for r in _fake_meta([98100622])}
    gatineau = probe._member(metas, 98100622, 1, "Gatineau", geo_level=3, parent=884)
    assert gatineau["memberId"] == probe.PINNED_CD_GATINEAU_ID
    probe._guard_pinned_id(98100622, "CD Gatineau", gatineau, probe.PINNED_CD_GATINEAU_ID)
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_pinned_id(98100622, "CD Gatineau", gatineau, 9999)
    # `Gatineau` names the census division AND the city inside it: name alone must refuse.
    with pytest.raises(probe.ProbeRefusal):
        probe._member(metas, 98100622, 1, "Gatineau")


def test_p10_a_member_is_resolvable_by_its_sgc_code_at_one_grain_only(probe):
    metas = {int(r["object"]["productId"]): r["object"] for r in _fake_meta([98100622])}
    by_code = {}
    for member in metas[98100622]["dimension"][0]["member"]:
        by_code.setdefault((str(member.get("classificationCode")), member.get("geoLevel")),
                           []).append(member)
    city = probe._member_by_code(98100622, by_code, "2481017", 5, "Gatineau city")
    assert city["memberId"] == probe.PINNED_CSD_GATINEAU_ID
    with pytest.raises(probe.ProbeRefusal):
        probe._member_by_code(98100622, by_code, "2481017", 3, "Gatineau city at the wrong grain")


def test_p10_isq_rows_are_resolved_by_label_and_the_pinned_code_asserted(probe):
    labels = {0: "Le Québec", 505: "RMR d'Ottawa-Gatineau2", 999: "Hors RMR"}
    assert probe._isq_code("book", labels, "RMR d'Ottawa-Gatineau", 505) == 505
    assert probe._isq_marker(labels[505]) == "2"
    with pytest.raises(probe.ProbeRefusal):
        probe._isq_code("book", labels, "RMR d'Ottawa-Gatineau", 999)   # a renumbered axis
    with pytest.raises(probe.ProbeRefusal):
        probe._isq_code("book", labels, "Nowhere", 505)                 # renamed or dropped
    with pytest.raises(probe.ProbeRefusal):
        probe._isq_code("book", {1: "Laval", 2: "Laval "}, "Laval", 1)  # ambiguous


def test_p10_the_quoted_footnote_must_be_read_not_typed(probe):
    probe._guard_footnote("RMR d'Ottawa-Gatineau2", "2", "2. Partie québécoise uniquement.")
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_footnote("RMR d'Ottawa-Gatineau", "", "2. Partie québécoise uniquement.")
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_footnote("RMR d'Ottawa-Gatineau2", "2", "2. Une note sans portée.")


def test_p10_the_isq_parts_must_close_within_a_stated_tolerance(probe):
    assert probe._guard_isq_parts("book", 100.0, {1: 60, 2: 40}, 0) == 0
    assert probe._guard_isq_parts("book", 100.0, {1: 60, 2: 43}, 5) == 3
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_isq_parts("book", 100.0, {1: 60, 2: 46}, 5)


# ===========================================================================
# 8. Floor guards over the whole derivation — each mutant applied to the
#    fixture the green path really reads, so no mutant is unreachable.
# ===========================================================================
def _cells_with(**changes) -> dict:
    table = dict(_CELLS)
    table.update(changes)
    return table


def _drop_cells(*keys) -> dict:
    return {k: v for k, v in _CELLS.items() if k not in keys}


def _meta_edited(edit) -> callable:
    def meta(pids):
        out = _fake_meta(pids)
        for item in out:
            edit(int(item["object"]["productId"]), item["object"])
        return out
    return meta


def _isq_edited(book: str, edit) -> callable:
    def isq(name):
        sheets = copy.deepcopy(_CAPTURE["isq"])
        if name == book:
            edit(sheets[book])
        return _isq_sheet(name, sheets)
    return isq


def _geo(obj: dict) -> list:
    return obj["dimension"][0]["member"]


def _coordinate(pid: int, prefix: str) -> tuple:
    """The one captured coordinate at `pid` starting with `prefix` — refuses on ambiguity."""
    hits = [key for key in _CELLS if key[0] == pid and key[1].startswith(prefix)]
    assert len(hits) == 1, (prefix, len(hits))
    return hits[0]


_OG_CHILD_GATINEAU = 603          # 98-10-0003-01: the city, inside the Ottawa-Gatineau CMA
_OG_MEMBER = 594


# Each mutant is paired with the BOUNDARY it must fire at. Asserting only that something
# refused is the weaker gate this arc keeps finding: a mutant that trips an unrelated guard is
# an UNREACHABLE mutant wearing a green tick, and the guard it was written for is then covered
# by nothing. Measured 2026-08-15: all 21 fire, each at its own boundary.
@pytest.mark.parametrize("mutation, boundary", [
    ("meta-without-dimensions", "wds-meta"),
    ("membership-member-moved", "wds-meta"),
    ("membership-does-not-close", "membership"),
    ("membership-population-drifts", "membership"),
    ("quebec-split-disagrees", "membership"),
    ("quebec-part-membership-changes", "membership"),
    ("cma-children-set-changes", "wds-meta"),
    ("a-direct-source-appears", "direct-source"),
    ("census-cubes-disagree-on-the-ruled-triple", "universe"),
    ("rho-cubes-disagree-on-the-province", "universe"),
    ("an-unsuppressible-cell-is-withheld", "wds-data"),
    ("the-suppression-bound-is-itself-withheld", "wds-data"),
    ("wrong-reference-period", "wds-data"),
    ("isq-flow-parts-do-not-close", "isq-workbook"),
    ("isq-footnote-gone", "isq-workbook"),
    ("isq-row-relabelled", "isq-workbook"),
    ("isq-flow-column-renamed", "isq-workbook"),
    ("spec-figure-perturbed", "citation"),
    ("bracket-figure-perturbed", "citation"),
    ("p9-tokens-gone", "p9"),
    ("constants-universe-line-gone", "constants"),
])
def test_p10_floor_guards_are_load_bearing(offline, mutation, boundary):
    """Each guard must actually fire, AND fire for its own reason.

    Every mutation below is applied to the same fixture
    `test_p10_note_regenerates_byte_identically_from_the_fixture` proves passes clean, so no
    mutant is unreachable, and the recorded boundary pins WHICH guard caught it.
    """
    mod, tmp_path = offline
    meta, data, isq = _fake_meta, _fake_data, _isq_sheet
    extra: dict = {}

    if mutation == "meta-without-dimensions":
        meta = _meta_edited(lambda pid, obj: obj.update(dimension=[])
                            if pid == mod.CMA_PID else None)
    elif mutation == "membership-member-moved":
        def move(pid, obj):
            if pid != mod.MEMBER_PID:
                return
            for member in _geo(obj):
                if member["memberId"] == _OG_MEMBER:
                    member["memberId"] = 5940
        meta = _meta_edited(move)
    elif mutation == "membership-does-not-close":
        key = _coordinate(mod.MEMBER_PID, f"{_OG_CHILD_GATINEAU}.")
        data = lambda reqs: _fake_data(reqs, _cells_with(**{}) | {key: _CELLS[key] - 500})  # noqa: E731,E501
    elif mutation == "membership-population-drifts":
        # Closure PRESERVED (child and CMA move together), so the closure guard cannot fire
        # first and mask the population gate — two gates covering one text is how one of them
        # becomes unreachable without anybody noticing.
        child = _coordinate(mod.MEMBER_PID, f"{_OG_CHILD_GATINEAU}.")
        whole = _coordinate(mod.MEMBER_PID, f"{_OG_MEMBER}.")
        table = dict(_CELLS)
        table[child] += 20_000
        table[whole] += 20_000
        data = lambda reqs: _fake_data(reqs, table)                          # noqa: E731
    elif mutation == "quebec-split-disagrees":
        # A Québec-coded child whose census-tree ancestry says otherwise: the CSD's census
        # division is re-parented out of Quebec, so the SGC prefix and the tree disagree.
        def reparent(pid, obj):
            if pid != mod.CD_PID:
                return
            for member in _geo(obj):
                if str(member.get("classificationCode")) == "2483" and member["geoLevel"] == 3:
                    member["parentMemberId"] = 1
        meta = _meta_edited(reparent)
    elif mutation == "quebec-part-membership-changes":
        def orphan(pid, obj):
            if pid != mod.MEMBER_PID:
                return
            for member in _geo(obj):
                if str(member.get("classificationCode")) == "2483005":
                    member["parentMemberId"] = None
        meta = _meta_edited(orphan)
    elif mutation == "cma-children-set-changes":
        def demote(pid, obj):
            if pid != mod.CMA_PID:
                return
            for member in _geo(obj):
                if member["memberId"] == 40:
                    member["geoLevel"] = 504
        meta = _meta_edited(demote)
    elif mutation == "a-direct-source-appears":
        def publish_part(pid, obj):
            if pid != mod.CMA_PID:
                return
            _geo(obj).append({"memberId": 9001, "memberNameEn": "Ottawa–Gatineau (Quebec part)",
                              "geoLevel": mod.CMA_PART_GEO_LEVEL, "parentMemberId": 24,
                              "classificationCode": "24505"})
        meta = _meta_edited(publish_part)
    elif mutation == "census-cubes-disagree-on-the-ruled-triple":
        key = _coordinate(mod.CD_PID, "884.1.1.1.1.12.1")
        data = lambda reqs: _fake_data(reqs, _cells_with(**{}) | {key: _CELLS[key] + 40})  # noqa: E731,E501
    elif mutation == "rho-cubes-disagree-on-the-province":
        key = next(k for k in _CELLS if k[0] == mod.RHO_CD_PID and k[1].startswith("884."))
        data = lambda reqs: _fake_data(reqs, dict(_CELLS) | {key: _CELLS[key] + 500})  # noqa: E731,E501
    elif mutation == "an-unsuppressible-cell-is-withheld":
        data = lambda reqs: _fake_data(                                      # noqa: E731
            reqs, _drop_cells(_coordinate(mod.CMA_PID, "24.1.1.1.1.12.1")))
    elif mutation == "the-suppression-bound-is-itself-withheld":
        # A QC-part CSD stops publishing `Non-immigrants`: the withheld settled cells at that
        # geography then have no upper end, and an interval with an unmeasured end is not one.
        keys = [k for k in _CELLS if k[0] == mod.CD_PID and k[1].startswith("1954.")
                and ".10." in k[1]]
        assert keys, "the fixture no longer carries the non-immigrant cells the bound needs"
        data = lambda reqs: _fake_data(reqs, _drop_cells(*keys))             # noqa: E731
    elif mutation == "wrong-reference-period":
        def data(reqs):
            out = _fake_data(reqs)
            for item in out:
                if item["object"]["vectorDataPoint"]:
                    item["object"]["vectorDataPoint"][0]["refPer"] = "2016-01-01"
                    break
            return out
    elif mutation == "isq-flow-parts-do-not-close":
        def bump(sheet):
            for row in sheet["body"]:
                if row.get("1") == "999" and row.get("3") == 2030:
                    row["16"] = row["16"] + 1000
        isq = _isq_edited(mod.ISQ_FLOW_BOOK, bump)
    elif mutation == "isq-footnote-gone":
        def drop_footnote(sheet):
            sheet["head"] = [row for row in sheet["head"]
                             if mod.ISQ_PART_FOOTNOTE_MARKER not in str(row.get("0", ""))]
        isq = _isq_edited(mod.ISQ_FLOW_BOOK, drop_footnote)
    elif mutation == "isq-row-relabelled":
        def relabel(sheet):
            for row in sheet["body"]:
                if row.get("1") == "505":
                    row["2"] = "RMR de Gatineau2"
        isq = _isq_edited(mod.ISQ_FLOW_BOOK, relabel)
    elif mutation == "isq-flow-column-renamed":
        def rename(sheet):
            for row in sheet["head"]:
                if row.get("16") == "Immigrants":
                    row["16"] = "Immigrants et résidents"
        isq = _isq_edited(mod.ISQ_FLOW_BOOK, rename)
    elif mutation == "spec-figure-perturbed":
        real = mod._spec_s6()
        assert "0.9600" in real
        extra["spec"] = lambda: real.replace("0.9600", "0.9640")
    elif mutation == "bracket-figure-perturbed":
        real = mod._bracket_record()
        assert "1.0242" in real
        extra["bracket"] = lambda: real.replace("1.0242", "1.0252")
    elif mutation == "p9-tokens-gone":
        extra["p9"] = lambda: "# P9\n\nno decision tokens survive here\n"
    elif mutation == "constants-universe-line-gone":
        extra["constants"] = lambda: '"""a docstring with no recorded universe gap."""\n'

    _wire(mod, tmp_path, meta=meta, data=data, isq=isq, **extra)
    with pytest.raises(mod.ProbeRefusal) as exc:
        mod._sections(["-"])
    assert exc.value.boundary == boundary, (
        f"{mutation} refused at {exc.value.boundary!r}, not at the {boundary!r} guard it was "
        f"written for: {exc.value}")


def test_p10_a_refusal_routes_to_unknown_and_never_to_a_friendlier_verdict(offline):
    """The failure path is a real path, not a comment: a refused run must still write a note,
    and that note must record UNKNOWN with the boundary — never a partial MEASURED."""
    mod, tmp_path = offline

    def boom(pids):
        raise mod.ProbeRefusal("wds-meta", "synthetic outage for the failure-path test")

    text = _run_offline(mod, tmp_path, meta=boom)
    assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED"
    assert "LIVE PROBE FAILED: ProbeRefusal:" in text
    assert "LIVE PROBE FAILED-AT: wds-meta" in text
    assert "DECISION-ALIGNED-RATIO" not in text


def test_p10_refusal_is_not_a_network_exception_name(probe):
    assert probe.ProbeRefusal.__name__ not in NETWORK_EXCEPTIONS
    assert issubclass(probe.ProbeRefusal, RuntimeError)
    assert not issubclass(probe.ProbeRefusal, OSError)


# ===========================================================================
# 9. The note's own claims, held to what the run measured
# ===========================================================================
def test_p10_every_registered_figure_appears_in_the_body(offline):
    """The provenance header counts figures and presents the count as a description of this
    document. A registered Fact that never reaches the prose makes that description false in the
    quiet direction — the header claims a figure the reader cannot find.
    """
    mod, tmp_path = offline
    _wire(mod, tmp_path)
    log = mod.new_run()                    # supersedes _wire's, so this reads its OWN registry
    body = "\n".join(mod._sections(["-"]))
    missing = [f.text for f in log.facts if f.text not in body]
    assert not missing, f"registered but absent from the note body: {missing}"
    assert len(log.facts) > 30, len(log.facts)


def test_p10_the_incomplete_triple_count_is_provenance_tagged(offline):
    """The direction the gate above cannot see: a NARRATIVE numeral in the body that no `Fact`
    registers.

    `test_p10_every_registered_figure_appears_in_the_body` closes registered→body. Body→
    registered is the open one, and the count of QC-part CSDs whose settled triple is incomplete
    fell through it: §4d's field-wise bullet, the sentence that follows it and the
    DECISION-SUPPRESSION token all rest on that number, while the note's own header reserves
    untagged numerals for TABLE CELLS and AUDIT METADATA — it is neither. The regression is
    measured, not hypothetical: the count carried `Fact.derived` until §4d's LEAD sentence was
    re-measured onto the withheld-cell UNION, and the tag left with the variable it had been
    attached to.

    Scoped to this one figure deliberately. A general body→registered scanner would trip on the
    denominators that are untagged BY DESIGN (the 48 = 3x16 settled-member counts, the innocent
    controls) and would be a different claim than the one this gate makes.

    The expected value is re-derived from the BOUNDARY TRAFFIC rather than read off the
    producer's `incomplete`: `_guard_required_complete` refuses the run unless `Total - Age` and
    `Non-immigrants` are published in FULL at every QC-part CSD, so on the green path a withheld
    98-10-0622-01 cell at one of those geographies can only be a settled-triple field.
    """
    mod, tmp_path = offline
    seen: list[tuple[int, str]] = []

    def data(requests):
        seen.extend((int(r["productId"]), r["coordinate"]) for r in requests)
        return _fake_data(requests)

    _wire(mod, tmp_path, data=data)
    log = mod.new_run()                    # supersedes _wire's, so this reads its OWN registry
    body = "\n".join(mod._sections(["-"]))

    geo = next(d for d in _CAPTURE["cubes"][str(mod.CD_PID)]["dimensions"] if d["pos"] == 1)
    code_of = {m["id"]: m["code"] for m in geo["members"]}
    incomplete = {code_of.get(int(coordinate.split(".")[0]))
                  for pid, coordinate in seen
                  if pid == mod.CD_PID and (pid, coordinate) not in _CELLS}
    incomplete &= set(mod.PINNED_QC_PART_CODES)
    assert incomplete, (
        "the fixture no longer withholds a settled-triple field at any QC-part CSD, so this "
        "gate would pass vacuously — re-derive it or delete it")

    bullet = re.search(r"counts are withheld, at ([\d,]+) subdivisions", body)
    assert bullet, "§4d no longer carries the field-wise bullet this gate reads"
    printed = int(bullet.group(1).replace(",", ""))
    assert printed == len(incomplete), (
        f"§4d's field-wise bullet says {printed} subdivisions; the settled-triple gaps in the "
        f"boundary traffic fall at {len(incomplete)}: {sorted(incomplete)}")

    tagged = [f for f in log.facts
              if f.text == str(printed) and "incomplete" in f.source]
    assert tagged, (
        f"§4d prints {printed} as a narrative figure but no Fact registers it — the header's "
        f"tagged/untagged contract admits it in neither untagged class. Registered texts: "
        f"{sorted(f.text for f in log.facts)}")


def test_p10_the_provenance_arithmetic_closes(note):
    line = re.search(r"This run registered (\d+) provenance-tagged figures: (\d+) DERIVED "
                     r".*?and (\d+) CITED", note, re.S)
    assert line, "the note carries no parseable provenance summary"
    total, derived, cited = (int(g) for g in line.groups())
    assert total == derived + cited and derived > 25 and cited > 5, (total, derived, cited)


def test_p10_every_bit_identity_claim_is_scoped_and_the_drift_is_named(offline, note):
    """P8 §3a's rule, applied at P10 — and P10 needs it harder than P8 did.

    P8 subtracts only the ruled triple across the cube pair, so "bit-identical on the ruled
    triple, ±5 elsewhere" says everything there. P10 ALSO subtracts a `Non-immigrants` triple
    across the pair (it is the aligned non-immigrant propensity's denominator), and one province
    cell of exactly that triple drifts by the rounding step — so an unscoped claim that the
    pair is identical "on the quantities subtracted across them" asserts what this run's own
    data contradicts. The note must scope each bit-identity claim to what a guard actually
    BINDS, and print the drifting cell's two values rather than counting it anonymously.
    """
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    drifted = mod.LAST_RUN["universe_drift"]
    assert drifted, ("the fixture no longer carries a drifting province cell, so this gate "
                     "would pass vacuously — re-derive it or delete it")
    for _key, _field, left, right in drifted:
        assert abs(left - right) <= mod._ROUNDING_TOLERANCE, (left, right)
        assert f"{int(left):,}" in note and f"{int(right):,}" in note, (
            f"the note counts a drifting province cell but never prints the pair "
            f"{int(left):,}/{int(right):,} a reader would need to check it")
    for sentence in re.findall(r"[^.]*bit-identical[^.]*\.", note, re.I):
        assert mod.PC_SETTLED in sentence or "all-ages" in sentence, (
            f"unscoped bit-identity claim: {sentence.strip()!r}")


def test_p10_the_separability_claim_is_measured_and_not_only_quoted(offline, note):
    """Quoting ISQ's footnote establishes what the row MEANS; it does not establish that the
    hors-RMR row excludes it. The closure of the workbook's own parts is what does, so the note
    must carry the measurement beside the quotation."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    flow = mod.LAST_RUN["flow"]
    assert max(abs(g) for g in flow["gaps"].values()) <= mod.ISQ_FLOW_TOLERANCE
    assert flow["gatineau_mean"] > 0 and flow["hors_mean"] > 0
    assert "Partie québécoise uniquement" in note
    # BOUND TO THE ROW EACH MEAN IS FROM, in one ordered clause. `hors_mean in note and
    # gatineau_mean in note` stood here and is the presence-vs-attribution shape (2026-08-21
    # class sweep): both figures merely present, so transposing them — the Gatineau row's mean
    # reported as hors-RMR's own — passed, and that is precisely the territory confusion this
    # whole probe exists to measure. The operand this rate multiplies is the hors-RMR row.
    token = _token(note, "DECISION-ISQ-SEPARABILITY")
    assert token.startswith("MEASURED"), token
    flat_token = " ".join(token.split())
    assert (f"hors-RMR mean {flow['hors_mean']:,.0f} vs the Gatineau row's "
            f"{flow['gatineau_mean']:,.0f}") in flat_token, (
        f"the separability token does not bind each mean to its ROW — expected "
        f"hors-RMR {flow['hors_mean']:,.0f} against Gatineau {flow['gatineau_mean']:,.0f}, in "
        f"that order: {token!r}")
    # AND ONE MEAN PER ROW: a contiguous clause makes a swap and a drop red, never an ADDITION,
    # so a second hors-RMR mean stated beside the true one would satisfy it.
    for role, pattern in (("hors-RMR", r"hors-RMR mean ([\d,]+)"),
                          ("the Gatineau row", r"Gatineau row's ([\d,]+)")):
        # IGNORECASE (run 48): an ADDED mean written "hors-RMR MEAN 9,999" is exactly what a
        # case-sensitive role pattern cannot see, and this leg exists for the addition.
        found = set(re.findall(pattern, flat_token, re.IGNORECASE))
        assert len(found) == 1, (
            f"the separability token attaches {sorted(found)} to {role} — one mean per row, or "
            "a reader cannot tell which figure the operand is")


def test_p10_the_absence_of_a_direct_source_is_earned_by_a_live_scan(offline, note):
    """A NOT-AVAILABLE verdict must be EARNED. The four maintainer-cross cubes P9's closure
    names are scanned member by member, and the ONE cube that does publish the Québec part is
    named with the reason it cannot serve — an absence claim beside its own falsifier."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    scanned = mod.LAST_RUN["scanned"]
    assert set(scanned) == set(mod.MAINTAINER_CROSS)
    assert all(hits == [] for hits in scanned.values()), scanned
    token = _token(note, "DECISION-DIRECT-SOURCE")
    assert "43-10-0060-01" in token and "maintainer axis" in token, token


def test_p10_the_note_states_what_the_membership_gate_cannot_do(note):
    body = note.lower()
    assert "what this gate cannot do" in body
    assert "would not be seen" in body


def test_p10_the_aligned_values_are_RULED_and_the_spec_carries_what_this_run_measures(offline):
    """The ordering constraint, RETIRED BY THE EVENT IT WATCHED FOR — and replaced by the
    stronger check that event makes possible.

    Until 2026-08-15 §6 did not carry these figures, and this test asserted their ABSENCE so
    that nothing could be wired on unruled numbers; it said so out loud the moment the seat
    ruled (amendment #13). The successor form is a CITATION COUPLING rather than a scope note:
    the spec must now carry exactly what this run measures, so a later edit to either side that
    moves a ruled value reds here. Wiring — P8's regeneration and the join-table update —
    remains a separate run's work, and is not what this test governs.
    """
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    s6 = mod._spec_s6()
    aligned = mod.LAST_RUN["aligned"]["pair"]
    assert f"{aligned[0]:.4f}" in s6 and f"{aligned[1]:.4f}" in s6, (
        "spec §6 must carry the aligned pair this run measures (amendment #13 ruled them in): "
        "a mismatch means the spec and this probe disagree about a RULED value")
    for label, token in mod.LAST_RUN["coupled"]:
        assert isinstance(token, str) and token, label
