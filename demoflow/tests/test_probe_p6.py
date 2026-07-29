"""P6 gates — does the committed note LOCATE an MRC-level ISQ source with all its evidence,
EARN a not-found over a real searched population, or honestly record UNKNOWN?

The plan's version asserted `"v0 PROCEEDS REGARDLESS" in NOTE.read_text()`. run_p6.py writes
that sentence on EVERY branch (it is a spec invariant, not an outcome), so that assertion can
never be False — it passes on a run that located everything AND on a run that fabricated
everything. A gate that cannot fail is not a gate. The gates below assert the OUTCOME
(RULING-2) over R7's three-valued vocabulary:

  PASS iff the note records EITHER
    (a) LOCATED carrying EVERY evidence token — the resource url, the OBSERVED http status,
        the body-shape result, the MRC label count, the couronne per-target search, the RA
        correspondence, the swept population and the spec-premise verdict — each
        INDEPENDENTLY gated so a bare or placeholder token fails; OR
    (b) NOT-FOUND carrying the population it is SCOPED to (an absence with no searched
        population is not an absence); OR
    (c) UNKNOWN-PROBE-FAILED with a recorded reason.
  FAIL on an unresolved `[FILL`, a verdict missing any evidence, tokens that contradict each
    other, or none of the three.
  SKIP-with-reason ONLY if the hunt was attempted and the source is independently confirmed
    unreachable — and only when the RECORDED exception TYPE is network-class (a code fault
    must not launder into a skip), probed with the SAME HTTP method run_p6.py uses against
    that host (GET — every request the probe makes for evidence is a GET).

  The green path is OFFLINE — it reads the committed note. Only the failure branch probes
  reachability, and only to decide fail-vs-skip.

  test_p6_no_unfilled_placeholder        -> the fabrication surface stays closed
  test_p6_records_a_resolved_verdict     -> the load-bearing RULING-2 / R7 gate
  test_p6_floor_guard_earns_verdict      -> the floor guards are load-bearing (mutation test)
  test_p6_earned_not_found_is_reachable  -> NOT-FOUND is a REACHABLE value, distinct from UNKNOWN
  test_p6_ra_corroboration_is_falsifiable-> the declared RA grouping can actually fail
  test_p6_records_v0_framing             -> the spec invariant (ADDITIVE, explicitly NON-JUDGING)
"""

import re
from pathlib import Path

import pytest

from ._probe_asserts import (
    NETWORK_EXCEPTIONS,
    recorded_failure_type as _recorded_failure_type,
    source_reachable,
    token as _token,
)

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P6-mrc-isq-hunt.md"

# The two liveness targets, one per boundary. BOTH are GET, because every request run_p6.py
# makes for evidence is a GET — the sitemap fetch, the candidate observation and the full
# download alike. This is not cosmetic: run_p6.py MEASURES that this ISQ host answers HEAD
# with 404 on a path whose GET is 200, so a HEAD-based liveness check here would report a
# perfectly healthy host as unreachable and launder every recorded failure into pytest.skip
# — the cardinal cheap all-clear. (test_probe_contracts.py enforces the method match.)
#
# `source_reachable` closes the response without reading it, so pointing the ISQ check at
# the 13MB sitemap costs headers, not a download.
CKAN_LIVENESS = "https://www.donneesquebec.ca/recherche/api/3/action/package_search?rows=0"
ISQ_LIVENESS = "https://statistique.quebec.ca/sitemap.xml"
REACHABILITY_TIMEOUT = 15

# NOTE: "NOT-FOUND" is deliberately ABSENT — R7 makes it a real verdict here (P3's pattern),
# so a shared set containing it would reject a legitimate earned outcome. "NONE" is absent
# for the same reason it is in p5b: several tokens may legitimately read "none".
UNRESOLVED = {"", "UNKNOWN-PROBE-FAILED", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL",
              "[FILL]", "N/A", "?"}

# The boundaries run_p6.py can attribute a failure to.
BOUNDARIES = ("ckan", "isq-sitemap", "isq-file")


def _note_text() -> str:
    assert NOTE.exists(), f"{NOTE} is missing — run `uv run python probes/run_p6.py` first"
    return NOTE.read_text(encoding="utf-8")


def _recorded_failure_boundary(text: str) -> str | None:
    found = re.search(rf"LIVE PROBE FAILED-AT:\s*({'|'.join(BOUNDARIES)})", text)
    return found.group(1) if found else None


def _source_reachable(boundary: str) -> bool:
    """Cheap GET liveness probe against the host of the boundary RECORDED as failing.

    Two boundaries, two hosts: probing the wrong one would fail a genuine outage as "the
    probe is broken" (p5's point B). GET, never HEAD — see the constants above for the
    measured reason. Any exception means unreachable.
    """
    return source_reachable(
        CKAN_LIVENESS if boundary == "ckan" else ISQ_LIVENESS,
        timeout=REACHABILITY_TIMEOUT,
        method="GET",
    )


def _fail_or_skip_on_recorded_failure(text: str) -> None:
    """Failure-branch policy for an UNKNOWN-PROBE-FAILED verdict. Never a silent pass."""
    if "LIVE PROBE FAILED" not in text:
        pytest.fail(
            f"{NOTE} records DECISION-VERDICT: UNKNOWN-PROBE-FAILED but no `LIVE PROBE FAILED` "
            f"reason — an unexplained UNKNOWN is not a recorded observation. Re-run run_p6.py."
        )
    recorded = _recorded_failure_type(text)
    if recorded is None:
        pytest.fail(f"{NOTE} records LIVE PROBE FAILED with no parseable exception type.")
    if recorded not in NETWORK_EXCEPTIONS:
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED: {recorded} — a code/structural fault (or a "
            f"floor-guard refusal), not a network outage, so an unreachable source does not "
            f"excuse it. Re-run run_p6.py."
        )
    boundary = _recorded_failure_boundary(text)
    if boundary is None:
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED with no parseable `LIVE PROBE FAILED-AT` "
            f"boundary (expected one of {BOUNDARIES}) — the skip gate cannot decide which host "
            f"to probe, and an unattributed failure must not launder into a skip."
        )
    if _source_reachable(boundary):
        host = "donneesquebec.ca" if boundary == "ckan" else "statistique.quebec.ca"
        pytest.fail(
            f"{NOTE} records LIVE PROBE FAILED ({recorded}) at boundary '{boundary}' while "
            f"{host} answers — the probe is broken, not the source. Re-run run_p6.py."
        )
    pytest.skip(
        f"{NOTE} records a network-class failure ({recorded}) at boundary '{boundary}', "
        f"independently confirmed unreachable — the hunt is genuinely unrecordable here, NOT "
        f"a pass. Per spec §11.6 v0 proceeds regardless; only the v1 extension waits."
    )


def test_p6_no_unfilled_placeholder():
    """Gate 1 — the committed note must never carry an unfilled `[FILL` slot.

    The plan's sketch emitted one (`- MRC workbook found?  [FILL: yes/no]`): a hand-write
    invitation for the very answer the probe exists to COMPUTE, which is the fabrication
    surface this probe family was hardened against. run_p6.py raises at write time if any
    placeholder survives; this gate is the committed-artifact half of that.
    """
    text = _note_text()
    assert "[FILL" not in text, (
        f"{NOTE} still contains an unresolved `[FILL` placeholder — the note must be GENERATED "
        f"by probes/run_p6.py, never hand-filled. Re-run: uv run python probes/run_p6.py"
    )


def test_p6_records_a_resolved_verdict():
    """Gate 2 — the RULING-2 outcome gate over R7's three-valued vocabulary.

    Every evidence token is asserted INDEPENDENTLY: a LOCATED that resolved the url but left
    the body shape, the label count, the couronne search or the RA correspondence bare must
    FAIL here, not pass on the strength of the tokens that did resolve. Cross-token
    CONSISTENCY is asserted too — a token that contradicts its neighbour is the defect this
    probe family keeps reintroducing beside correctly-computed values.
    """
    text = _note_text()
    verdict = _token(text, "DECISION-VERDICT")
    assert verdict in {"LOCATED", "NOT-FOUND", "UNKNOWN-PROBE-FAILED"}, (
        f"{NOTE} records no resolved `DECISION-VERDICT` (got {verdict!r}). It must be LOCATED "
        f"(with ALL evidence), NOT-FOUND (EARNED over a stated searched population), or "
        f"UNKNOWN-PROBE-FAILED (with a reason)."
    )

    if verdict == "UNKNOWN-PROBE-FAILED":
        _fail_or_skip_on_recorded_failure(text)  # -> fail (bad) or skip (confirmed outage)
        return

    # --- BOTH resolved verdicts must state the population they are scoped to --------
    swept = _token(text, "DECISION-SWEPT-POPULATION")
    assert swept is not None and swept.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-SWEPT-POPULATION` (got {swept!r})."
    )
    counts = [int(n) for n in re.findall(r"\d+", swept)]
    assert counts and max(counts) > 0, (
        f"{NOTE}'s DECISION-SWEPT-POPULATION states no non-zero population: {swept!r}. R7: a "
        f"verdict over an unswept or empty population is unearned — 'not among 0 things' is "
        f"the vacuous-absence signature the floor guard exists to refuse."
    )

    premise = _token(text, "DECISION-SPEC-PREMISE")
    assert premise is not None and premise.upper() not in UNRESOLVED, (
        f"{NOTE} records no `DECISION-SPEC-PREMISE` (got {premise!r}) — spec §8 asserts \"no "
        f"MRC workbook exists\", so this run must state whether it stands."
    )

    if verdict == "NOT-FOUND":
        # An EARNED absence: scoped, and consistent with the premise it leaves standing.
        scope = _token(text, "DECISION-NOT-FOUND-SCOPE")
        assert scope is not None and scope.upper() not in UNRESOLVED, (
            f"{NOTE} claims NOT-FOUND but records no `DECISION-NOT-FOUND-SCOPE` ({scope!r}). "
            f"An absence claim must say what it is an absence AMONG."
        )
        assert premise.upper().startswith("NOT CONTRADICTED"), (
            f"{NOTE} records NOT-FOUND but `DECISION-SPEC-PREMISE` is {premise!r} — a run that "
            f"located nothing cannot contradict any premise. (The premise TEXT is never "
            f"quoted here — §4 reads it live; see the cross-artifact-staleness note in "
            f"run_p6.py's docstring.)"
        )
        return

    # --- a LOCATED must carry EVERY evidence piece R7 requires ----------------------
    url = _token(text, "DECISION-RESOURCE-URL")
    assert (url is not None and url.upper() not in UNRESOLVED
            and url.lower().startswith("http") and url.lower().endswith(".xlsx")), (
        f"{NOTE} claims LOCATED but records no usable `DECISION-RESOURCE-URL` (got {url!r}). "
        f"A located verdict must carry the workbook url resolved from the swept population."
    )

    status = _token(text, "DECISION-HTTP-STATUS")
    assert status is not None and status.strip().startswith("200"), (
        f"{NOTE} claims LOCATED but `DECISION-HTTP-STATUS` is {status!r}. R7's second evidence "
        f"piece is the OBSERVED status of a real request, and only a 200 can carry a body."
    )

    shape = _token(text, "DECISION-BODY-SHAPE")
    assert shape is not None and shape.upper() not in UNRESOLVED and len(shape) >= 40, (
        f"{NOTE} claims LOCATED but records no substantive `DECISION-BODY-SHAPE` ({shape!r})."
    )
    # PRESENCE-ONLY, and labelled as such. The LOCATED branch writes the literal
    # "magic-byte prefix matches" unconditionally, so this assertion cannot fail on a bad run
    # and it does NOT enforce "a bare 200 cannot earn a LOCATED" — it pins the token's SHAPE
    # so a later edit cannot quietly drop the magic-byte evidence from the note. The rule
    # itself is enforced where it can actually fail: `_is_workbook_response` screens the
    # candidate, `_guard_body` refuses the shape, and mutation 1 in
    # test_p6_floor_guard_earns_verdict shows the LOCATED is fabricated without the guard.
    # (Contrast the NEXT assertion, which is genuinely falsifiable: a zero label count is a
    # value the note can really emit, and the neutered-guard run does emit it.)
    assert "magic-byte prefix matches" in shape, (
        f"{NOTE}'s DECISION-BODY-SHAPE no longer records a magic-byte check at all: "
        f"{shape!r} — the token's shape changed, not the run's outcome."
    )
    assert re.search(r"[1-9]\d* distinct geography labels", shape), (
        f"{NOTE}'s DECISION-BODY-SHAPE states no NON-ZERO geography label count: {shape!r}. "
        f"'0 distinct geography labels' is the fabrication signature the floor-guard mutation "
        f"asserts on, so it must not pass here either."
    )

    labels = _token(text, "DECISION-MRC-LABEL-COUNT")
    total = re.match(r"^([1-9]\d*)\b", (labels or "").strip())
    assert total, (
        f"{NOTE} claims LOCATED but `DECISION-MRC-LABEL-COUNT` does not start with a positive "
        f"integer ({labels!r}) — an MRC-level claim over an empty column is unearned."
    )
    # The count must arrive DECOMPOSED and the decomposition must CLOSE. These columns
    # interleave administrative-region subtotal rows with the MRC rows, so a raw total reads
    # as an MRC count and is wrong; a split that does not add up is worse than none.
    parts = re.search(r"\((\d+) of them .*?\+ (\d+) others\)", labels or "")
    assert parts, (
        f"{NOTE}'s DECISION-MRC-LABEL-COUNT states no aggregate/remainder decomposition "
        f"({labels!r}). The column interleaves RA subtotals, so the bare total would read as "
        f"an MRC count and be wrong."
    )
    assert int(parts.group(1)) + int(parts.group(2)) == int(total.group(1)), (
        f"{NOTE}'s DECISION-MRC-LABEL-COUNT decomposition does not add up: {labels!r}."
    )

    couronne = _token(text, "DECISION-COURONNE-TARGETS")
    assert couronne is not None and couronne.upper() not in UNRESOLVED, (
        f"{NOTE} claims LOCATED but records no `DECISION-COURONNE-TARGETS` ({couronne!r})."
    )
    found = re.match(r"^(\d+) of (\d+)", couronne.strip())
    assert found and int(found.group(2)) > 0, (
        f"{NOTE}'s DECISION-COURONNE-TARGETS does not state a 'k of n' per-target result over "
        f"a non-empty declared target set: {couronne!r}. The label COUNT above does not bear "
        f"on couronne precision; this search is what does, so it must be stated separately."
    )
    n_hit, n_declared = int(found.group(1)), int(found.group(2))
    # The gloss must AGREE with the count beside it — the depth-2 defect this family keeps
    # reintroducing is a correct number with a hand-written adjective next to it.
    if n_hit < n_declared:
        assert "ALL declared targets present" not in couronne and "MISSING" in couronne, (
            f"{NOTE} records {n_hit} of {n_declared} couronne targets found while the token "
            f"still reads as complete: {couronne!r}. A gloss must not contradict its own count."
        )

    ra = _token(text, "DECISION-RA-CORRESPONDENCE")
    assert ra is not None and ra.upper() not in UNRESOLVED, (
        f"{NOTE} claims LOCATED but records no `DECISION-RA-CORRESPONDENCE` ({ra!r}) — spec "
        f"§8's proxies are RA14/15/16, so the note must state what it did or did not establish "
        f"about that axis."
    )
    # If any declared target DISAGREED with the live RA code, the note must say so in full,
    # not only in the DECISION line.
    if "DISAGREEING" in ra.upper():
        assert "NOT CORROBORATED" in text, (
            f"{NOTE}'s DECISION-RA-CORRESPONDENCE reports a disagreement ({ra!r}) but the body "
            f"never marks a target NOT CORROBORATED — the decision line and the evidence "
            f"table contradict each other."
        )

    # The premise token must AGREE with the state §4 read live out of the spec file. The
    # note used to TYPE the premise as a quoted string; steering then amended §8 and the
    # quote became a claim about a locked artifact the artifact no longer made. This gate is
    # what keeps the DECISION line and the live read from drifting apart again.
    state = re.search(r"\*\*State: ([A-Z ]+)\*\*", text)
    assert state, f"{NOTE} records no §4 spec-premise state line."
    expected = {
        "PREMISE STANDS": "CONTRADICTED — ESCALATION",
        "AMENDED": "ALREADY AMENDED — no live conflict remains",
        "INDETERMINATE": "INDETERMINATE — the spec row did not match either marker",
        "NOT MEASURED THIS RUN": "NOT CHECKED — the spec file was not read this run",
    }[state.group(1).strip()]
    assert premise == expected, (
        f"{NOTE}'s DECISION-SPEC-PREMISE is {premise!r} but §4 read the spec state as "
        f"{state.group(1).strip()!r}, which requires {expected!r}. A LOCATED contradicts the "
        f"premise only while the premise is actually IN the spec — once amended, "
        f"'CONTRADICTED' would assert a conflict with text that no longer exists."
    )

    # --- the two RESIDUALS (steering ruling G): recorded, computed, self-consistent ------
    residual_i = _token(text, "DECISION-RESIDUAL-I-RA-AXIS")
    assert residual_i is not None and residual_i.upper() not in UNRESOLVED, (
        f"{NOTE} claims LOCATED but records no `DECISION-RESIDUAL-I-RA-AXIS` ({residual_i!r})."
    )
    split = re.search(r"of (\d+) candidate workbooks opened, (\d+) publish a SEPARATE "
                      r"administrative-region column, (\d+) name the grouping in the "
                      r"geography header ONLY \(no per-MRC RA code\), (\d+) carry neither",
                      residual_i)
    assert split, (
        f"{NOTE}'s DECISION-RESIDUAL-I-RA-AXIS states no three-way split: {residual_i!r}. "
        f"Two states would fuse the editions that publish a real RA column with those whose "
        f"GEOGRAPHY header merely names the grouping — reporting a machine-readable axis "
        f"where none exists."
    )
    n_opened, n_sep, n_named, n_none = (int(g) for g in split.groups())
    assert n_sep + n_named + n_none == n_opened, (
        f"{NOTE}'s residual-(i) split does not add up: {residual_i!r}."
    )
    # The counts must agree with the §3b TABLE they summarise. This is the gate for a defect
    # that actually shipped here: the split read `0 / 0 / 0` while the table one line below
    # it showed `SEPARATE column RA1` rows. Nothing compared the two.
    table = text.split("## 3b.")[1].split("## 3c.")[0]
    rows_sep = len(re.findall(r"^\| .*\| \*\*SEPARATE column ", table, re.M))
    rows_named = len(re.findall(r"^\| .*\| NAMED IN THE GEOGRAPHY HEADER ONLY", table, re.M))
    assert (rows_sep, rows_named) == (n_sep, n_named), (
        f"{NOTE}'s residual-(i) counts ({n_sep} separate, {n_named} header-named) disagree "
        f"with its own §3b table ({rows_sep} separate, {rows_named} header-named). A summary "
        f"that contradicts the evidence printed under it is the defect this gate exists for."
    )

    residual_ii = _token(text, "DECISION-RESIDUAL-II-PARTITION")
    assert residual_ii is not None and residual_ii.upper() not in UNRESOLVED, (
        f"{NOTE} claims LOCATED but records no `DECISION-RESIDUAL-II-PARTITION` "
        f"({residual_ii!r})."
    )
    # Every exhaustion relation must come from the COMPUTED set-algebra vocabulary — a word
    # outside it is prose that no set operation produced.
    # The membership figure must equal the couronne count it summarises — the two used to be
    # a computed count and a flat literal "YES" sitting in different tokens.
    membership = re.search(r"membership (\d+) of (\d+) \(§3\)", residual_ii)
    assert membership, (
        f"{NOTE}'s residual-(ii) states no COUNTED membership figure: {residual_ii!r}. A flat "
        f"'membership YES' is a literal that no measurement can falsify."
    )
    assert (membership.group(1), membership.group(2)) == (found.group(1), found.group(2)), (
        f"{NOTE}'s residual-(ii) membership {membership.group(0)!r} disagrees with "
        f"DECISION-COURONNE-TARGETS ({couronne!r})."
    )

    relations = re.findall(r"-> ([A-Z ]+?)(?=;|$)", residual_ii)
    assert relations, f"{NOTE}'s residual-(ii) states no exhaustion relation: {residual_ii!r}"
    allowed = {"EQUAL", "PROPER SUBSET", "PROPER SUPERSET", "OVERLAPPING", "DISJOINT",
               "EMPTY", "NOT COMPUTABLE"}
    for rel in relations:
        assert rel.strip() in allowed, (
            f"{NOTE}'s residual-(ii) reports the relation {rel.strip()!r}, which is outside "
            f"the computed set-algebra vocabulary {sorted(allowed)}."
        )
    # The unanswerable claim must agree with the marker counts printed beside it.
    marker = re.search(r"NOT ANSWERABLE from this workbook \((\d+) header cells and (\d+) "
                       r"geography labels match", residual_ii)
    if marker:
        assert marker.group(1) == "0" and marker.group(2) == "0", (
            f"{NOTE} claims the RMR-couronne question is NOT ANSWERABLE while reporting "
            f"{marker.group(1)} header cells and {marker.group(2)} labels that DO match a "
            f"metropolitan-area marker: {residual_ii!r}. The conclusion contradicts the count "
            f"it is drawn from."
        )


# ---------------------------------------------------------------------------
# Gate 3 — the floor guards are load-bearing (mutation test, runs OFFLINE).
# ---------------------------------------------------------------------------
def _load_run_p6():
    """Import run_p6.py as a fresh module (probes/ is not an importable package).

    The `sys.path` insert is load-bearing, not tidiness: run_p6.py imports its shared
    machinery FLAT (`from _wds import …`) because probes/ is deliberately not a package and
    script mode resolves it via `sys.path[0]`. `spec_from_file_location` does NOT put the
    file's directory on the path, so without this `exec_module` dies
    `ModuleNotFoundError: No module named '_wds'`.
    """
    import importlib.util
    import sys

    probes_dir = str(NOTE.parent)
    if probes_dir not in sys.path:
        sys.path.insert(0, probes_dir)
    spec = importlib.util.spec_from_file_location("run_p6_under_test", NOTE.parent / "run_p6.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CANDIDATE = ("https://statistique.quebec.ca/fr/fichier/"
             "composantes-demographiques-projetees-mrc-du-quebec.xlsx")

# A sitemap whose sweep DOES resolve the candidate above.
_SITEMAP_HIT = ("<urlset><url><loc>https://statistique.quebec.ca/fr/document/x</loc></url>"
                f"<url><loc>{CANDIDATE}</loc></url></urlset>")
# A NON-EMPTY sitemap whose sweep resolves NOTHING — the population exists, the matches do
# not. This is the fixture that separates an EARNED NOT-FOUND from an UNKNOWN.
_SITEMAP_NO_MATCH = (
    "<urlset>"
    "<url><loc>https://statistique.quebec.ca/fr/fichier/production-laitiere-quebec.xlsx</loc></url>"
    "<url><loc>https://statistique.quebec.ca/fr/fichier/permis-batir-quebec.xlsx</loc></url>"
    "<url><loc>https://statistique.quebec.ca/fr/document/marche-du-travail</loc></url>"
    "</urlset>"
)
_SITEMAP_EMPTY = "<urlset></urlset>"

_XLSX_PROBE = {"status": 200, "ctype": "application/vnd.openxmlformats-officedocument."
                                        "spreadsheetml.sheet",
               "length": "517264", "prefix": b"PK\x03\x04\x14\x00\x06\x00", "error": ""}
# A 200 whose body is an HTML error page — the wrong-body case R7 names. Everything else
# about the response is perfectly well-formed, so nothing raises on its own.
_HTML_PROBE = dict(_XLSX_PROBE, ctype="text/html", length="45288",
                   prefix=b"<!DOCTYPE")

# A structurally COMPLETE grid: caption, header row with an MRC column AND an RA column,
# and data rows carrying two of the declared couronne targets with their real RA codes.
_GOOD_ROWS = [
    ("Composantes démographiques projetées, scénario Référence A2021, MRC du Québec",),
    (None,),
    ("Code", "MRC", "RA1", "Année (t)", "Population"),
    ("62", "Les Moulins", "14", "2024", "1"),
    ("77", "Mirabel", "15", "2024", "2"),
    ("1", "Communauté maritime des Îles-de-la-Madeleine", "11", "2024", "3"),
]
# The same grid with NO MRC-named header cell — a workbook that opened but identifies no
# geography axis.
_NO_HEADER_ROWS = [
    ("Composantes démographiques projetées",),
    (None,),
    ("Code", "Territoire", "RA1", "Année (t)", "Population"),
    ("62", "Les Moulins", "14", "2024", "1"),
]
# An MRC header with ZERO labels below it.
_EMPTY_COLUMN_ROWS = [
    ("Composantes démographiques projetées",),
    (None,),
    ("Code", "MRC", "RA1", "Année (t)", "Population"),
]


def _fake_ckan(*, count: int = 1617, packages: tuple = ("p1",)):
    """A minimal but VALID CKAN seam: a resolvable ISQ org, a non-empty catalogue, and a
    package set that matches nothing. `count=0` / `packages=()` make it vacuous."""
    def _get(url: str) -> dict:
        if "organization_list" in url:
            return {"result": [{"name": "isq",
                                "title": "Institut de la statistique du Québec"}]}
        if "rows=0" in url:
            return {"result": {"count": count, "results": []}}
        return {"result": {"count": len(packages),
                           "results": [{"id": pid, "title": "Production laitière",
                                        "notes": "", "resources": []} for pid in packages]}}
    return _get


def _wire(mod, *, sitemap: str, probe: dict | None = None, rows: list | None = None,
          ckan=None):
    """Patch every network/filesystem seam so a scenario runs fully OFFLINE."""
    mod._ckan_get = ckan if ckan is not None else _fake_ckan()
    mod._sitemap = lambda: sitemap
    mod._probe_url = lambda url, **kw: dict(probe or _XLSX_PROBE)
    mod._download = lambda url: b"PK\x03\x04 not really a workbook"
    mod._workbook_rows = lambda data, **kw: (["Référence A2021"], list(rows or _GOOD_ROWS))


def test_p6_floor_guard_earns_verdict(tmp_path):
    """Gate 3 — every verdict must be EARNED (NS #1 / R7). Four vacuous-or-wrong-body
    scenarios that never RAISE on their own must each route to UNKNOWN-PROBE-FAILED at the
    right boundary; then NEUTERING each safety guard must FLIP a scenario into a FABRICATED
    verdict — proving those guards are what keep the verdicts honest.

    Which guard each scenario proves, graded honestly rather than assumed (P5b's file
    claimed a guard was "ALSO safety-load-bearing" when it was structurally incapable of
    being so, and a wrong self-grade propagates into every risk list that reads it). Each
    grade below was obtained by actually neutering the guard and reading what changed:

      * `_guard_body` is SAFETY-load-bearing for LOCATED **on its shape branches only** —
        neutered on the empty-column scenario, the run publishes LOCATED with a label count
        of zero. Its status/magic-byte branches are a BACKSTOP, not work: `verified` is
        built through `_is_workbook_response`, which screens both, so neutering `_guard_body`
        on the HTML-body scenario changes nothing (measured — it stays UNKNOWN). Mutating a
        scenario a guard cannot see would have graded a live guard as dead.
      * `_guard_not_found` is SAFETY-load-bearing for NOT-FOUND, on BOTH of R7's floors —
        neutered, it fabricates an absence over a zero-package catalogue (2a) and an absence
        over a candidate that answered with the wrong body (2b). Both are mutated, because
        one guard covering two floors means one mutation leaves a floor untested.
      * `_guard_sitemap` is ATTRIBUTION-ONLY. Neutered, the empty-sitemap scenario falls
        through to `_guard_not_found`, which checks `not locs` itself and still raises — so
        the verdict stays UNKNOWN and only `FAILED-AT` moves (isq-sitemap -> isq-file).
        Verified by neutering it; asserted at the end of this test rather than claimed.

    Runs OFFLINE — every boundary is patched; the committed note is untouched.
    """
    scenarios = {
        "empty sitemap (200, zero locs)": (
            dict(sitemap=_SITEMAP_EMPTY), "isq-sitemap"),
        "200-but-wrong-body candidate (HTML error page)": (
            dict(sitemap=_SITEMAP_HIT, probe=_HTML_PROBE), "isq-file"),
        "workbook opens but names no MRC geography column": (
            dict(sitemap=_SITEMAP_HIT, rows=_NO_HEADER_ROWS), "isq-file"),
        "MRC column present but carrying ZERO labels": (
            dict(sitemap=_SITEMAP_HIT, rows=_EMPTY_COLUMN_ROWS), "isq-file"),
        # The R7 floor case: a real, non-empty ISQ population with zero matches is NOT
        # enough on its own — the second searched population must have been swept and be
        # non-empty, or the absence is scoped to nothing.
        "zero matches over an EMPTY CKAN catalogue": (
            dict(sitemap=_SITEMAP_NO_MATCH, ckan=_fake_ckan(count=0, packages=())),
            "isq-file"),
        "zero matches while the CKAN boundary never answered": (
            dict(sitemap=_SITEMAP_NO_MATCH,
                 ckan=lambda url: (_ for _ in ()).throw(TimeoutError("patched outage"))),
            "isq-file"),
    }
    for label, (wiring, boundary) in scenarios.items():
        mod = _load_run_p6()
        mod.OUT = tmp_path / f"note_{abs(hash(label))}.md"
        _wire(mod, **wiring)
        mod.main()
        text = mod.OUT.read_text(encoding="utf-8")
        assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED", (
            f"[{label}] a vacuous / wrong-body response was laundered into a verdict other "
            f"than UNKNOWN — the floor guard did not fire. A verdict must be EARNED (NS #1)."
        )
        assert _recorded_failure_boundary(text) == boundary, (
            f"[{label}] the failure must be attributed to boundary '{boundary}', got "
            f"{_recorded_failure_boundary(text)!r} — the skip gate needs the right host."
        )

    # MUTATION 1: neuter `_guard_body` on the EMPTY-COLUMN scenario. The run must now publish
    # a FABRICATED LOCATED whose geography evidence is an empty list. If this does NOT flip,
    # the guard is not what keeps the LOCATED honest and the loop above proves nothing.
    #
    # Deliberately NOT the HTML-body scenario: `_is_workbook_response` screens that one out
    # before `_guard_body` is ever reached, so neutering `_guard_body` there changes nothing
    # (verified live — it stays UNKNOWN via `_guard_not_found`). Mutating the scenario a
    # guard cannot see would have "proved" the guard dead when it is not. The wrong-body case
    # gets its own mutation below, against the guard that actually holds it.
    mod = _load_run_p6()
    mod.OUT = tmp_path / "note_neutered_body.md"
    _wire(mod, sitemap=_SITEMAP_HIT, rows=_EMPTY_COLUMN_ROWS)
    mod._guard_body = lambda url, probe, sheets, header_row, col, labels: None  # neutered
    mod.main()
    neutered = mod.OUT.read_text(encoding="utf-8")
    assert _token(neutered, "DECISION-VERDICT") == "LOCATED", (
        "neutering `_guard_body` did NOT flip the empty-column scenario into a fabricated "
        "LOCATED — the guard is then not the thing keeping the verdict honest."
    )
    # And the fabrication is exactly what the guard exists to refuse: an MRC-level claim
    # whose own label count is zero, published as if it were measured.
    assert (_token(neutered, "DECISION-MRC-LABEL-COUNT") or "").startswith("0 "), (
        "the neutered run must publish a geography answer over ZERO labels — that is the "
        f"fabricated claim `_guard_body` refuses; got "
        f"{_token(neutered, 'DECISION-MRC-LABEL-COUNT')!r}"
    )

    # MUTATION 2a: neuter `_guard_not_found` on the empty-catalogue scenario. The run must
    # now publish a FABRICATED NOT-FOUND — an absence scoped to a catalogue of zero packages.
    mod = _load_run_p6()
    mod.OUT = tmp_path / "note_neutered_notfound.md"
    _wire(mod, sitemap=_SITEMAP_NO_MATCH, ckan=_fake_ckan(count=0, packages=()))
    mod._guard_not_found = lambda locs, eligible, verified, ckan: None  # neutered
    mod.main()
    neutered2 = mod.OUT.read_text(encoding="utf-8")
    assert _token(neutered2, "DECISION-VERDICT") == "NOT-FOUND", (
        "neutering `_guard_not_found` did NOT flip the empty-catalogue scenario into a "
        "fabricated NOT-FOUND — the guard is then not what keeps the absence claim earned, "
        "and R7's floor ('a zero-result sweep over an EMPTY catalogue => UNKNOWN') rests on "
        "nothing."
    )
    assert "0-package catalogue" in (_token(neutered2, "DECISION-SWEPT-POPULATION") or ""), (
        "the neutered run must publish an absence scoped to a ZERO-package catalogue — that "
        "is the vacuous-absence claim `_guard_not_found` refuses."
    )

    # MUTATION 2b: the SAME guard, on the wrong-body scenario — R7's other floor case
    # ("a 200-but-wrong-body product page => UNKNOWN, never NOT-FOUND"). Neutered, the run
    # publishes an absence while a candidate url sits in its own §2 table: the sweep's
    # failure reported as a finding about ISQ's holdings. Both cases are asserted because
    # one guard now covers two distinct floors, and 2a alone would leave this one untested.
    mod = _load_run_p6()
    mod.OUT = tmp_path / "note_neutered_wrongbody.md"
    _wire(mod, sitemap=_SITEMAP_HIT, probe=_HTML_PROBE)
    mod._guard_not_found = lambda locs, eligible, verified, ckan: None  # neutered
    mod.main()
    neutered2b = mod.OUT.read_text(encoding="utf-8")
    assert _token(neutered2b, "DECISION-VERDICT") == "NOT-FOUND", (
        "neutering `_guard_not_found` did NOT flip the wrong-body scenario into a fabricated "
        "NOT-FOUND — R7's 'a 200-but-wrong-body page never becomes a NOT-FOUND' then rests "
        "on nothing."
    )
    assert "1 eligible" in (_token(neutered2b, "DECISION-SWEPT-POPULATION") or ""), (
        "the neutered run must publish an absence while its own sweep resolved an eligible "
        "candidate — that is the contradiction `_guard_not_found` refuses."
    )

    # The HONEST grade for `_guard_sitemap`, measured rather than asserted: neutering it does
    # NOT change the verdict (the downstream `_guard_not_found` catches the empty population
    # too); it only moves the attribution. Recorded here so the docstring above cannot drift
    # into over-claiming, which is the exact defect P5b's file shipped.
    mod = _load_run_p6()
    mod.OUT = tmp_path / "note_neutered_sitemap.md"
    _wire(mod, sitemap=_SITEMAP_EMPTY)
    mod._guard_sitemap = lambda xml, locs: None  # neutered
    mod.main()
    neutered3 = mod.OUT.read_text(encoding="utf-8")
    assert _token(neutered3, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED", (
        "neutering `_guard_sitemap` changed the VERDICT — it is then safety-load-bearing and "
        "this test's docstring, which grades it attribution-only, is wrong."
    )
    assert _recorded_failure_boundary(neutered3) == "isq-file", (
        "neutering `_guard_sitemap` must move the attribution from 'isq-sitemap' to the "
        "downstream guard's boundary; if it does not move at all, the guard is dead code."
    )


def test_p6_earned_not_found_is_reachable(tmp_path):
    """Gate 5 — NOT-FOUND is a REACHABLE verdict, and it is DISTINCT from UNKNOWN.

    The live run is LOCATED, so nothing in the green path ever reaches the not-found branch
    — which is exactly how a three-valued verdict decays into a two-valued one, and how a
    gate that can only ever say UNKNOWN gets mistaken for a working gate. This drives the
    discriminator R7 names: a NON-EMPTY searched population with ZERO matches must earn
    NOT-FOUND, while the SAME sweep over an empty catalogue must route to UNKNOWN.

    Runs OFFLINE.
    """
    mod = _load_run_p6()
    mod.OUT = tmp_path / "note_notfound.md"
    _wire(mod, sitemap=_SITEMAP_NO_MATCH, ckan=_fake_ckan(count=1617, packages=("a", "b")))
    mod.main()
    text = mod.OUT.read_text(encoding="utf-8")

    assert _token(text, "DECISION-VERDICT") == "NOT-FOUND", (
        f"a non-empty ISQ sweep with zero matches over a non-empty CKAN catalogue must EARN "
        f"NOT-FOUND, not fall to "
        f"{_token(text, 'DECISION-VERDICT')!r}. A verdict that can only take one value is "
        f"not a gate."
    )
    # Fixture guard against a vacuous pass: the population must really be non-empty and the
    # matches must really be zero, or this proves nothing about the discriminator.
    swept = _token(text, "DECISION-SWEPT-POPULATION") or ""
    assert re.search(r"[1-9]\d* ISQ sitemap locs", swept), (
        f"the fixture swept an EMPTY ISQ population, so the NOT-FOUND above is the vacuous "
        f"case rather than the earned one: {swept!r}"
    )
    assert "0-package catalogue" not in swept, (
        f"the fixture swept an EMPTY CKAN catalogue, so this is the UNKNOWN case: {swept!r}"
    )
    assert (_token(text, "DECISION-SPEC-PREMISE") or "").upper().startswith("NOT CONTRADICTED")

    # The same sweep over an EMPTY catalogue must NOT reach NOT-FOUND — the discriminator is
    # the population, and asserting only the positive direction would let a guard that always
    # answers NOT-FOUND pass.
    mod2 = _load_run_p6()
    mod2.OUT = tmp_path / "note_notfound_vacuous.md"
    _wire(mod2, sitemap=_SITEMAP_NO_MATCH, ckan=_fake_ckan(count=0, packages=()))
    mod2.main()
    vacuous = mod2.OUT.read_text(encoding="utf-8")
    assert _token(vacuous, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED", (
        "the SAME zero-match sweep over an EMPTY catalogue reached "
        f"{_token(vacuous, 'DECISION-VERDICT')!r} — NOT-FOUND and UNKNOWN are then the same "
        "value wearing two names, and the searched population is not actually discriminating."
    )


def test_p6_ra_corroboration_is_falsifiable(tmp_path):
    """Gate 6 — the DECLARED RA grouping can actually FAIL (runs OFFLINE).

    `COURONNE_MRC_BY_RA` declares which administrative region each couronne MRC belongs to.
    Declaring it makes the claim honest about its provenance but not yet falsifiable: the
    independent witness is the RA code the LIVE workbook puts beside each MRC, which no
    declaration in run_p6.py controls. Without the negative half below, a check that always
    answers CORROBORATED would pass every positive assertion (P5b shipped exactly that, and
    three of its mutants survived the first attempt for this reason).
    """
    mod = _load_run_p6()
    mod.OUT = tmp_path / "note_ra_ok.md"
    _wire(mod, sitemap=_SITEMAP_HIT)
    mod.main()
    ok = mod.OUT.read_text(encoding="utf-8")

    # Fixture guard: the corroboration must actually have RUN on the two targets the fixture
    # rows carry, or this passes vacuously. The OTHER eight declared targets are legitimately
    # NOT CHECKABLE here (the fixture has no rows for them) — which is itself the right
    # behaviour, and is asserted rather than glossed over.
    assert "RA code observed beside it" in ok, "the fixture produced no corroboration table"
    for target, code in (("Les Moulins", "14"), ("Mirabel", "15")):
        row = re.search(rf"^\|.*\| {re.escape(target)} \|.*$", ok, re.M)
        assert row, f"the fixture's target {target!r} produced no corroboration row"
        assert "CORROBORATED" in row.group(0) and "NOT CORROBORATED" not in row.group(0), (
            f"{target} was not corroborated against its live RA code {code}: {row.group(0)!r}"
        )
    absent = re.search(r"^\|.*\| Thérèse-De Blainville \|.*$", ok, re.M)
    assert absent and "NOT CHECKABLE" in absent.group(0), (
        "a declared target with NO row in the fixture must read NOT CHECKABLE — an unchecked "
        f"declaration must never read as a corroborated one: {absent and absent.group(0)!r}"
    )
    assert "NOT CORROBORATED" not in ok, (
        "the fixture's declared RA numbers disagree with the RA codes in its own rows"
    )
    assert (_token(ok, "DECISION-RA-CORRESPONDENCE") or "").startswith("2 of 2"), (
        f"expected both fixture targets corroborated, got "
        f"{_token(ok, 'DECISION-RA-CORRESPONDENCE')!r}"
    )

    # The FAILURE direction — what proves the check works (NS #1: the live run's failure, not
    # its pass, is the teacher). A DELIBERATELY WRONG declaration must stop corroborating.
    mod2 = _load_run_p6()
    mod2.OUT = tmp_path / "note_ra_wrong.md"
    _wire(mod2, sitemap=_SITEMAP_HIT)
    wrong = {f"RA99 Nowhere-{i}": targets
             for i, targets in enumerate(mod2.COURONNE_MRC_BY_RA.values())}
    # Verify the mutation APPLIED before trusting what it produces: a patch that silently
    # matched nothing would give a clean false-green.
    assert wrong and all(k.startswith("RA99") for k in wrong), "the RA mutation did not apply"
    mod2.COURONNE_MRC_BY_RA = wrong
    mod2.main()
    bad = mod2.OUT.read_text(encoding="utf-8")
    assert "NOT CORROBORATED" in bad, (
        "a DELIBERATELY WRONG declared RA number (99 for MRCs whose live rows carry 14/15) "
        "was still reported as corroborated. The check cannot detect a false declaration, so "
        "the corroboration above proves nothing."
    )
    assert "DISAGREEING" in (_token(bad, "DECISION-RA-CORRESPONDENCE") or ""), (
        "the body marks targets NOT CORROBORATED while the DECISION token stays silent — a "
        "reader of the decision block would never learn the grouping failed."
    )


# The three RA-axis shapes these editions actually publish, as fixtures. The middle one is
# the trap: its geography header NAMES an RA grouping, so a predicate that only asked "is
# there an RA-ish header cell?" would read it as a usable axis and compare labels to
# themselves.
_HEADER_NAMED_ROWS = [
    ("Population projetée des MRC du Québec, scénario Référence (A), 2016-2041",),
    (None,),
    ("Code", "MRC par région administrative", "Population"),
    ("62", "Les Moulins", "1"),
    ("77", "Mirabel", "2"),
]
# A workbook that DOES carry a metropolitan-area marker. Without this shape no fixture ever
# drives §3c's "a marker DOES appear" branch, so the unconditional NOT-ANSWERABLE clause was
# unreachable by any gate — verified: the mutation restoring it passed the whole suite.
_RMR_MARKER_ROWS = [
    ("Population projetée, MRC du Québec",),
    (None,),
    ("Code", "MRC", "RA1", "RMR de rattachement", "Population"),
    ("62", "Les Moulins", "14", "Montréal", "1"),
    ("77", "Mirabel", "15", "Montréal", "2"),
]
_NO_RA_ROWS = [
    ("Population totale, scénarios de 2025, MRC du Québec, 2021-2051",),
    (None,),
    ("Scénario", "Code", "MRC", "2021"),
    ("Référence (A2025)", "62", "Les Moulins", "1"),
    ("Référence (A2025)", "77", "Mirabel", "2"),
]


def test_p6_residuals_are_recorded_observations_not_verdicts(tmp_path):
    """Gate 7 — the two residuals are COMPUTED, and they CANNOT move the verdict (ruling G).

    Two failure modes in one test, because either alone is escapable:

      * a hardcoded residual token would satisfy any presence check — so the SAME probe is
        driven over three genuinely different RA-axis shapes and the tokens must DIFFER;
      * a residual wired into the verdict would silently turn a recorded observation into a
        gate — so DECISION-VERDICT must stay LOCATED across all three.

    The middle shape is the one that matters most: a workbook whose GEOGRAPHY header reads
    "MRC par région administrative" names an RA grouping but publishes no per-MRC code.
    Before `_ra_axis_usable` it was read as a usable axis, which made §3 report NOT
    CORROBORATED and §3c manufacture a DISJOINT relation for a file that simply does not
    carry the axis. Runs OFFLINE.
    """
    seen = {}
    for label, rows in (("separate RA column", _GOOD_ROWS),
                        ("RA named in the geography header only", _HEADER_NAMED_ROWS),
                        ("no RA axis at all", _NO_RA_ROWS),
                        ("a metropolitan-area marker IS present", _RMR_MARKER_ROWS)):
        mod = _load_run_p6()
        mod.OUT = tmp_path / f"note_{abs(hash(label))}.md"
        _wire(mod, sitemap=_SITEMAP_HIT, rows=rows)
        mod.main()
        text = mod.OUT.read_text(encoding="utf-8")
        assert _token(text, "DECISION-VERDICT") == "LOCATED", (
            f"[{label}] the residual shape changed DECISION-VERDICT to "
            f"{_token(text, 'DECISION-VERDICT')!r}. Ruling G: the residuals are RECORDED "
            f"OBSERVATIONS — a find is a find regardless of what they compute."
        )
        # The MEMBERSHIP glosses must follow what §3 actually measured on THIS shape. Two
        # unconditional literals shipped here and this suite stayed green while emitting
        # them: an RA-correspondence gloss asserting "each declared target is present and
        # carries the RA code" beside `NOT CHECKABLE` and `2 of 10`, and a flat
        # `membership YES` beside the same count. These fixtures carry only 2 of the 10
        # declared targets, so they falsify both — which is exactly why they belong here.
        couronne = _token(text, "DECISION-COURONNE-TARGETS") or ""
        hit = re.match(r"^(\d+) of (\d+)", couronne)
        assert hit and hit.group(1) != hit.group(2), (
            f"[{label}] the fixture must NOT find every declared target, or it cannot "
            f"falsify an unconditional membership gloss: {couronne!r}"
        )
        ra_tok = _token(text, "DECISION-RA-CORRESPONDENCE") or ""
        # THE #2 DEFECT, as a cross-token check: a claimed SEPARATE RA column may never sit at
        # the geography column's own index. With the loose `ra_col >= 0` test the token read
        # "corroborated against the opened workbook's own SEPARATE RA column (column 1 …)" on
        # the header-named-only fixture — column 1 IS the geography column, i.e. exactly the
        # machine-readable axis the three-state split exists to deny.
        geo = re.search(r"MRC header cell at row \d+ column (\d+)",
                        _token(text, "DECISION-BODY-SHAPE") or "")
        ra_claim = re.search(r"SEPARATE RA column \(column (\d+)", ra_tok)
        if ra_claim:
            assert geo and ra_claim.group(1) != geo.group(1), (
                f"[{label}] DECISION-RA-CORRESPONDENCE claims a SEPARATE RA column at column "
                f"{ra_claim.group(1)}, which is the GEOGRAPHY column — that is a header that "
                f"names the grouping, not a per-MRC code: {ra_tok!r}"
            )
        assert "all 10 declared targets present" not in ra_tok, (
            f"[{label}] DECISION-RA-CORRESPONDENCE asserts every declared target is present "
            f"while DECISION-COURONNE-TARGETS reports {couronne!r}: {ra_tok!r}"
        )
        # AIMED AT §3's BULLET, not at the token. The membership defect lived in §3's prose
        # ("What this establishes is MEMBERSHIP — each declared target is present…"), one
        # clause away from the token this loop was reading, and so went uncaught. A gate must
        # point at the sentence that can be wrong.
        bullet = re.search(r"What this establishes is MEMBERSHIP[^\n]*", text)
        assert bullet, f"[{label}] §3 emits no MEMBERSHIP bullet to check"
        assert "each declared target is present and sits under" not in bullet.group(0), (
            f"[{label}] §3's MEMBERSHIP bullet asserts every declared target is present and "
            f"placed, while §3 measured {couronne!r}: {bullet.group(0)[:200]!r}"
        )
        assert f"{hit.group(1)} of {hit.group(2)} declared targets are present" in bullet.group(0), (
            f"[{label}] §3's MEMBERSHIP bullet does not state the measured count "
            f"{couronne!r}: {bullet.group(0)[:200]!r}"
        )
        residual_ii = _token(text, "DECISION-RESIDUAL-II-PARTITION") or ""
        # AIMED AT THE PROSE AFTER THE CLOSING BACKTICK — `token()` stops at the backtick, so
        # the clauses that follow it are invisible to every token-based assertion here. Two
        # unconditional claims lived there and no gate could see them.
        after = re.search(r"DECISION-RA-CORRESPONDENCE:[^\n]*", text).group(0).split("`")[-1]
        if "measured there to be unanswerable" in after:
            assert "0 header cells and 0 geography labels" in residual_ii, (
                f"[{label}] the prose after DECISION-RA-CORRESPONDENCE asserts §3c measured "
                f"the composition unanswerable, but §3c reported {residual_ii[:160]!r}"
            )
        # #5 ON A FIXTURE: the NOT-ANSWERABLE conclusion must agree with the counts printed
        # inside its own parenthesis. Gate 2 enforces this on the COMMITTED note, which is
        # always the zero-marker case — so without this copy the RMR shape reached no gate.
        marker = re.search(r"NOT ANSWERABLE from what this run read of this workbook "
                           r"\((\d+) header cells and (\d+) geography labels", residual_ii)
        if marker:
            assert marker.group(1) == "0" and marker.group(2) == "0", (
                f"[{label}] residual-(ii) claims NOT ANSWERABLE while reporting "
                f"{marker.group(1)} header cells and {marker.group(2)} labels that DO match a "
                f"metropolitan-area marker: {residual_ii!r}"
            )
        assert "membership YES" not in residual_ii, (
            f"[{label}] DECISION-RESIDUAL-II-PARTITION states a flat `membership YES` beside "
            f"a measured {couronne!r}: {residual_ii!r}"
        )
        assert f"membership {hit.group(1)} of {hit.group(2)}" in residual_ii, (
            f"[{label}] the residual's membership figure does not match "
            f"DECISION-COURONNE-TARGETS ({couronne!r}): {residual_ii!r}"
        )

        seen[label] = (_token(text, "DECISION-RESIDUAL-I-RA-AXIS"), residual_ii)

    sep = seen["separate RA column"]
    named = seen["RA named in the geography header only"]
    none = seen["no RA axis at all"]
    assert len({s[0] for s in seen.values()}) >= 3, (
        f"residual (i) reported the same axis token for three different RA shapes — it is "
        f"not computed from the workbook: {seen}"
    )
    # The middle shape must NOT be counted as a separate column, and its exhaustion relation
    # must be NOT COMPUTABLE rather than a manufactured set relation.
    assert "1 publish a SEPARATE administrative-region column" in sep[0]
    assert "0 publish a SEPARATE administrative-region column" in named[0], (
        f"a workbook that only NAMES its RA grouping in the geography header was counted as "
        f"publishing a separate RA column: {named[0]!r}"
    )
    assert "1 name the grouping in the geography header ONLY" in named[0]
    assert "NOT COMPUTABLE" in named[1], (
        f"the header-named-only shape produced a computed exhaustion relation ({named[1]!r}) "
        f"— reading that column as RA codes compares every label against itself, so any "
        f"relation it yields is manufactured."
    )
    assert "NOT COMPUTABLE" in none[1], (
        f"a workbook with no RA axis produced a computed exhaustion relation: {none[1]!r}"
    )
    # The separate-RA shape must produce an actual SET RELATION — the specific word depends
    # on the fixture's rows (this one declares more targets than it carries, so PROPER
    # SUPERSET is the correct answer), so the assertion is that a relation was COMPUTED at
    # all, not which one. Pinning the word here would make the gate a fixture snapshot.
    assert "NOT COMPUTABLE" not in sep[1], (
        f"the separate-RA-column shape reported NOT COMPUTABLE ({sep[1]!r}) — the axis IS "
        f"readable there, so the exhaustion relation must actually be computed."
    )
    assert any(w in sep[1] for w in ("EQUAL", "PROPER SUBSET", "PROPER SUPERSET",
                                     "OVERLAPPING", "DISJOINT", "EMPTY")), (
        f"the separate-RA-column shape produced no set relation at all: {sep[1]!r}"
    )


def test_p6_spec_premise_is_read_live_not_typed(tmp_path):
    """Gate 8 — the spec premise is READ, and the DECISION token FOLLOWS what was read.

    The note's premise statement was a typed quote until steering amended §8 and the quote
    went stale — a claim about a locked artifact that the artifact no longer made. Driving
    three synthetic spec texts proves the token is a function of the file rather than of
    this run's outcome, and that an unreadable spec degrades to NOT CHECKED instead of
    asserting either way. Runs OFFLINE.
    """
    cases = {
        "premise still stands": (
            # SYNTHETIC input, not a quote of the real spec: this string exists to drive the
            # premise-stands branch, which the live spec no longer reaches.
            "| couronne-nord precision is DEFERRED (no MRC workbook exists — probed 404) |",
            "PREMISE STANDS", "CONTRADICTED — ESCALATION"),
        "amended": (
            "| couronne-nord precision is DEFERRED to v1. MRC-level ISQ projection workbooks "
            "EXIST — the 404 was a method artifact. |",
            "AMENDED", "ALREADY AMENDED — no live conflict remains"),
        "row rewritten past both markers": (
            "| couronne-nord precision is handled elsewhere now. |",
            "INDETERMINATE", "INDETERMINATE — the spec row did not match either marker"),
    }
    for label, (spec_line, state, token_value) in cases.items():
        mod = _load_run_p6()
        mod.OUT = tmp_path / f"spec_{abs(hash(label))}.md"
        _wire(mod, sitemap=_SITEMAP_HIT)
        mod._spec_text = lambda line=spec_line: f"# spec\n\n{line}\n"
        mod.main()
        text = mod.OUT.read_text(encoding="utf-8")
        assert f"**State: {state}**" in text, (
            f"[{label}] §4 read the spec state as something other than {state!r}"
        )
        assert _token(text, "DECISION-SPEC-PREMISE") == token_value, (
            f"[{label}] the DECISION token is "
            f"{_token(text, 'DECISION-SPEC-PREMISE')!r}, not {token_value!r} — the token does "
            f"not follow the live read, so it is effectively typed."
        )
        assert _token(text, "DECISION-VERDICT") == "LOCATED", (
            f"[{label}] the spec cross-check moved the verdict; it is NON-GATING."
        )

    # An unreadable spec must degrade to NOT CHECKED — never to an assertion either way.
    mod = _load_run_p6()
    mod.OUT = tmp_path / "spec_unreadable.md"
    _wire(mod, sitemap=_SITEMAP_HIT)
    mod._spec_text = lambda: (_ for _ in ()).throw(FileNotFoundError("patched out"))
    mod.main()
    unreadable = mod.OUT.read_text(encoding="utf-8")
    assert _token(unreadable, "DECISION-SPEC-PREMISE") == (
        "NOT CHECKED — the spec file was not read this run"), (
        f"an unreadable spec produced {_token(unreadable, 'DECISION-SPEC-PREMISE')!r} — a "
        f"premise claim on the strength of a read that did not happen."
    )
    assert _token(unreadable, "DECISION-VERDICT") == "LOCATED"


def test_p6_records_v0_framing():
    """Gate 4 — the spec §11.6 invariant. ADDITIVE and explicitly NON-JUDGING.

    Every string asserted here is written UNCONDITIONALLY by run_p6.py on EVERY branch, so
    this gate CANNOT fail on a bad outcome and judges nothing about the run. That is exactly
    why the plan's `assert "v0 PROCEEDS REGARDLESS" in text` was not a gate: it is a spec
    invariant, not an outcome. It is pinned here so a later edit cannot quietly drop the
    framing — and nowhere else, so no gate rests on it. Gates 1-3, 5 and 6 judge the run.
    """
    text = _note_text()
    assert "v0 PROCEEDS REGARDLESS" in text
    assert "ra_proxy" in text
    assert "v1" in text and "Geography" in text
    low = text.lower()
    assert "mrc" in low
    assert ("located" in low) or ("not-found" in low) or ("unknown-probe-failed" in low)
