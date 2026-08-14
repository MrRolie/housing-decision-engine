"""P8 gates — are the immigrant inputs MEASURED, and is ruling T's territory gate EARNED?

P8's product is a pair of numbers per modeled geography plus a GATE that decides whether two
of those geographies may be flagged `cited` rather than `borrowed_prior`. Both halves are
dangerous in the same way: a value that reads as measured but was typed, and a gate that
reads as passing but could not have failed. Amendment #11 exists because the gate's FIRST
construction fired at the Québec province CONTROL, where territory identity is not in
question — so these gates hold the note to:

  1. every ruled figure is RECOMPUTED and citation-coupled to the digits §6 states (a
     perturbed digit must RED — `test_p8_citation_coupling_reds_on_a_perturbed_digit`);
  2. the territory gate's THRESHOLD is derived from innocent controls measured in the same
     construction, not inherited from the refuted wording — changing the innocent set must
     change the threshold, and the inherited 1% must NOT be it;
  3. every floor guard fires on a mutant applied to the fixture the green path really reads,
     so no guard is unreachable; and
  4. the note regenerates BYTE-IDENTICALLY from that fixture through the real producer, so a
     mutated derivation reds without a network.

  PASS iff the note records EITHER
    (a) `MEASURED` carrying every evidence token, each agreeing with the producer; OR
    (b) `UNKNOWN-PROBE-FAILED` with a recorded exception TYPE and boundary.
  FAIL on an unresolved `[FILL`, a missing or unresolved token under a MEASURED verdict, or a
    note figure the producer does not reproduce.
  SKIP-with-reason ONLY if the recorded exception TYPE is network-class AND www150 is
    independently confirmed unreachable, probed with the SAME HTTP METHOD run_p8.py uses for
    it (POST — `getCubeMetadata` rejects GET, so a GET liveness check reports a healthy
    service as down and launders every recorded failure into a skip).

  The green path is entirely OFFLINE. The WDS/workbook boundaries are replaced by fixtures
  built from the values the 2026-08-14 live run measured, so the producer runs end to end
  with no network; only the failure branch touches www150, and only to decide fail-vs-skip.
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
NOTE = PROBES / "P8-immigrant-inputs.md"
P9_NOTE = PROBES / "P9-catalogue-closure.md"

WDS_LIVENESS = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
LIVENESS_PID = 98100621
REACHABILITY_TIMEOUT = 10

# "NOT-FOUND" and "NONE" are INSIDE this set on purpose: P8 has no legitimate not-found
# outcome. Its only earned verdict is a measurement, and every DECISION token it emits is a
# value, a source, a delta or a level — a token reading NONE would be an unresolved field
# wearing an answer's clothes.
UNRESOLVED = {"", "UNKNOWN-PROBE-FAILED", "UNRESOLVED-PROBE-FAILED", "TBD", "FILL", "[FILL]",
              "N/A", "NONE", "NOT-FOUND", "?"}

MEASURED = "MEASURED"
EVIDENCE_TOKENS = (
    "DECISION-HEADSHIP",
    "DECISION-RATIO",
    "DECISION-SOURCE-MTL_RMR",
    "DECISION-SOURCE-QC_RMR",
    "DECISION-SOURCE-HORS_RMR",
    "DECISION-SOURCE-MTL_ISLAND_RA06",
    "DECISION-SOURCE-LAVAL_RA13",
    "DECISION-TERRITORY-GATE",
    "DECISION-TERRITORY-THRESHOLD",
    "DECISION-TERRITORY-DIAGNOSTIC",
    "DECISION-FLOOR-GATE",
    "DECISION-FLOOR-COVERAGE",
    "DECISION-UNIVERSE-IDENTITY",
    "DECISION-SIBLING-CROSS-CHECK",
    "DECISION-CATALOGUE-CLOSURE",
    "DECISION-SCOPE",
)


def _source_reachable() -> bool:
    """Is the WDS metadata endpoint answering? POST — the method run_p8.py uses for it."""
    return source_reachable(
        WDS_LIVENESS,
        timeout=REACHABILITY_TIMEOUT,
        method="POST",
        data=json.dumps([{"productId": LIVENESS_PID}]).encode(),
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture(scope="module")
def probe():
    return common._load_probe("p8")


@pytest.fixture(scope="module")
def note() -> str:
    assert NOTE.exists(), f"{NOTE} was never written — run probes/run_p8.py"
    return NOTE.read_text(encoding="utf-8")


def _verdict(note: str) -> str:
    value = _token(note, "DECISION-VERDICT")
    assert value, "the note carries no DECISION-VERDICT token at all"
    return value


def _require_measured_or_skip(note: str) -> None:
    verdict = _verdict(note)
    if verdict == MEASURED:
        return
    assert verdict == "UNKNOWN-PROBE-FAILED", f"unknown verdict {verdict!r}"
    failure = _recorded_failure_type(note)
    assert failure, "an UNKNOWN verdict must record the exception TYPE that produced it"
    assert failure in NETWORK_EXCEPTIONS, (
        f"the note records a {failure} — a code/structural fault, not an outage. It must FAIL "
        f"here rather than launder into a skip.")
    assert not _source_reachable(), (
        f"the note records a {failure} but www150 answers POST right now — a recorded failure "
        f"against a healthy service is a real defect, not an outage.")
    pytest.skip(f"P8 recorded {failure} and www150 is confirmed unreachable")


# ===========================================================================
# THE OFFLINE FIXTURE — the values the live boundaries returned on 2026-08-14.
# Hand-entered HERE on purpose: this is the test's input, not the artifact's content.
# The artifact recomputes everything from these, and the byte-equality gate below is what
# ties the two together.
# ===========================================================================
# (persons, maintainers, owner-maintainers) keyed by (productId, geographyMemberId) then by
# Population-characteristics member id.
_P = {
    (98100621, 24): {1: (8308480, 3749035, 2245600), 9: (8308480, 3749035, 2245600),
                     10: (6892110, 3058105, 1921035), 11: (1210600, 599370, 315825),
                     12: (1007855, 527710, 298100), 13: (202740, 71660, 17725),
                     14: (205775, 91565, 8750)},
    (98100621, 30): {1: (98570, 45700, 26810), 9: (98570, 45700, 26810),
                     10: (93735, 43585, 26065), 11: (3700, 1655, 680),
                     12: (2715, 1430, 630), 13: (980, 225, 45), 14: (1130, 455, 60)},
    (98100621, 35): {1: (4206455, 1835705, 998230), 9: (4206455, 1835705, 998230),
                     10: (3021830, 1252635, 724630), 11: (1022940, 511070, 266470),
                     12: (860685, 452595, 252225), 13: (162255, 58475, 14245),
                     14: (161680, 72000, 7135)},
    (98100621, 36): {1: (817105, 387955, 226075), 9: (817105, 387955, 226075),
                     10: (746855, 355550, 213555), 11: (54855, 25400, 12045),
                     12: (40545, 20490, 10965), 13: (14310, 4910, 1085),
                     14: (15395, 7005, 470)},
    (98100621, 40): {1: (157895, 74805, 47920), 9: (157895, 74805, 47920),
                     10: (154185, 73010, 47395), 11: (2065, 980, 490),
                     12: (1645, 785, 450), 13: (425, 190, 45), 14: (1650, 810, 30)},
    (98100621, 48): {1: (220105, 104650, 57350), 9: (220105, 104650, 57350),
                     10: (199565, 95240, 53665), 11: (16725, 7570, 3565),
                     12: (12580, 6220, 3250), 13: (4145, 1350, 310), 14: (3815, 1840, 120)},
    (98100621, 51): {1: (155535, 76635, 43865), 9: (155535, 76635, 43865),
                     10: (146760, 72515, 42495), 11: (6355, 2855, 1335),
                     12: (4900, 2365, 1225), 13: (1455, 485, 115), 14: (2415, 1260, 40)},
    # 98-10-0622-01. The province rows are BIT-IDENTICAL to 98100621's for the ruled triple
    # (popchar 12) and differ by exactly 5 on four other cells — both properties are asserted
    # by `_guard_universe`, so the fixture must carry them exactly as measured.
    (98100622, 884): {1: (8308480, 3749035, 2245600), 9: (8308480, 3749035, 2245600),
                      10: (6892110, 3058100, 1921035), 11: (1210600, 599365, 315820),
                      12: (1007855, 527710, 298100), 13: (202740, 71660, 17725),
                      14: (205770, 91565, 8750)},
    (98100622, 1732): {1: (1959355, 910360, 360120), 9: (1959355, 910360, 360120),
                       10: (1168390, 502530, 211560), 11: (652730, 343815, 143185),
                       12: (538620, 299230, 135510), 13: (114110, 44585, 7680),
                       14: (138240, 64020, 5375)},
    (98100622, 1730): {1: (429555, 169785, 113000), 9: (429555, 169785, 113000),
                       10: (288925, 105975, 69370), 11: (135315, 62065, 43345),
                       12: (119160, 57390, 41745), 13: (16155, 4670, 1605),
                       14: (5310, 1745, 285)},
}
# 43-10-0060-01, PERCENT values: {(geo, immigrant member): {indicator: percent}}
_SIB = {
    (13, 2): {5: 70.4, 8: 16.3}, (13, 3): {5: 56.3, 8: 13.4}, (13, 4): {5: 38.5, 8: 8.9},
    (13, 5): {5: 64.9, 8: 15.6}, (13, 6): {5: 14.0, 8: 16.6},
    (15, 2): {5: 66.1, 8: 15.5}, (15, 3): {5: 55.8, 8: 13.4}, (15, 4): {5: 37.9, 8: 9.2},
    (15, 5): {5: 64.0, 8: 15.4}, (15, 6): {5: 13.6, 8: 16.4},
    (17, 2): {5: 69.5, 8: 18.2}, (17, 3): {5: 51.1, 8: 12.7}, (17, 4): {5: 36.9, 8: 8.6},
    (17, 5): {5: 64.1, 8: 16.4}, (17, 6): {5: 11.8, 8: 17.4},
}
_TOTALPOP = {53: 8501833, 98: 438366, 130: 2004265}

# ISQ July-1 2021 totals (sex code 3) keyed by the workbooks' OWN `Code` column.
_ISQ_RA = {0: 8572020, 1: 199319, 2: 276563, 3: 762707, 4: 274353, 5: 498038, 6: 2015879,
           7: 408052, 8: 147838, 9: 90171, 10: 46128, 11: 91324, 12: 436397, 13: 440489,
           14: 532680, 15: 643216, 16: 1456782, 17: 252084}
_ISQ_RA_NAMES = {0: "Le Québec", 1: "Bas-Saint-Laurent", 2: "Saguenay–Lac-Saint-Jean",
                 3: "Capitale-Nationale", 4: "Mauricie", 5: "Estrie", 6: "Montréal",
                 7: "Outaouais", 8: "Abitibi-Témiscamingue", 9: "Côte-Nord",
                 10: "Nord-du-Québec", 11: "Gaspésie–Îles-de-la-Madeleine",
                 12: "Chaudière-Appalaches", 13: "Laval", 14: "Lanaudière",
                 15: "Laurentides", 16: "Montérégie", 17: "Centre-du-Québec"}
_ISQ_RMR = {0: 8572020, 408: 162376, 421: 844774, 433: 229294, 442: 162531, 447: 102356,
            462: 4330143, 505: 355971, 999: 2384575}
_ISQ_RMR_NAMES = {0: "Le Québec", 408: "RMR de Saguenay ", 421: "RMR de Québec ",
                  433: "RMR de Sherbrooke ", 442: "RMR de Trois-Rivières ",
                  447: "RMR de Drummondville ", 462: "RMR de Montréal ",
                  505: "RMR d'Ottawa-Gatineau2", 999: "Territoire hors des RMR"}
_ISQ_RA_NOTE = ("1. Selon le découpage géographique des régions administratives au "
                "1ᵉʳ juillet 2025.")
_ISQ_RMR_NOTE = "1. Selon le découpage géographique et la dénomination du Recensement de 2021."


def _pad(members: list, total: int, *, nbsp: int = 0, parent: int | None = 99,
         levels: dict | None = None) -> list:
    """Grow a member list to the live dimension's real size with inert filler.

    The live counts (166 / 5,468 / 63 / 307 geography members, 46 population characteristics)
    are printed by the note, and the trailing-NBSP scan is a COUNT over the whole dimension —
    so a fixture carrying only the resolved members would make both figures unreproducible and
    the byte-equality gate meaningless. Filler names cannot collide with a resolved name.
    """
    out = list(members)
    base = max((m["memberId"] for m in out), default=0) + 1
    # `levels` reproduces the live geoLevel HISTOGRAM where the note publishes one. Without
    # it the note's "N of the 63 members are at geoLevel 3" sentence — the measurement that
    # EARNS the floor's not-covered verdict — has no fixture behind it, and the regen gate
    # (correctly) reds. Caught by that gate on the first run after the sentence was added.
    plan = [level for level, count in (levels or {}).items() for _ in range(count)]
    for i in range(total - len(out)):
        suffix = "\xa0\xa0" if i < nbsp else ""
        out.append({"memberId": base + i, "memberNameEn": f"filler-{base + i}{suffix}",
                    "geoLevel": (plan[i] if i < len(plan)
                                 else (None if parent is None else 504)),
                    "parentMemberId": parent, "classificationCode": None})
    assert len(out) == total, (len(out), total)
    return out


def _dim(position: int, name: str, members: list) -> dict:
    return {"dimensionPositionId": position, "dimensionNameEn": name, "member": members}


def _m(member_id: int, name: str, **kw) -> dict:
    return {"memberId": member_id, "memberNameEn": name,
            "geoLevel": kw.get("geo_level"), "parentMemberId": kw.get("parent"),
            "classificationCode": kw.get("code")}


_TENURE_TOTAL = ("Total - Tenure including presence of mortgage payments and subsidized "
                 "housing (totals include farm operators)")
_CENSUS_DIMS = [
    (2, "Tenure including presence of mortgage payments and subsidized housing (totals "
        "include farm operators) (8)", [_m(1, _TENURE_TOTAL), _m(2, "Owner")], 8),
    (3, "Gender (3)", [_m(1, "Total - Gender")], 3),
    (4, "Primary household maintainer (2)",
     [_m(1, "Total - Household maintainer"),
      _m(2, "Person is primary household maintainer")], 2),
    (5, "Statistics (3B)", [_m(1, "Number of people")], 3),
    (6, "Population characteristics (46)",
     [_m(1, "Total - Age"), _m(9, "Total - Immigrant status and period of immigration"),
      _m(10, "Non-immigrants"), _m(11, "Total immigrants"), _m(12, "Before 2016"),
      _m(13, "Recent immigrants: 2016 to 2021"), _m(14, "Non-permanent residents")], 46),
    (7, "Housing suitability and dwelling condition (6)",
     [_m(1, "Total - Housing suitability")], 6),
]

_CMA_MEMBERS = [
    _m(30, "Drummondville (CMA), Que.", geo_level=503, parent=24, code="447"),
    _m(35, "Montréal (CMA), Que.", geo_level=503, parent=24, code="462"),
    _m(36, "Québec (CMA), Que.", geo_level=503, parent=24, code="421"),
    _m(40, "Saguenay (CMA), Que.", geo_level=503, parent=24, code="408"),
    _m(48, "Sherbrooke (CMA), Que.", geo_level=503, parent=24, code="433"),
    _m(51, "Trois-Rivières (CMA), Que.", geo_level=503, parent=24, code="442"),
]


def _fake_meta(pids) -> list:
    """`getCubeMetadata` for the four cubes, shaped like the live responses."""
    cubes = {}
    cubes[98100621] = {
        "productId": "98100621",
        "cubeTitleEn": ("Population groups by housing suitability and condition of dwelling: "
                        "Canada, provinces and territories, census metropolitan areas and "
                        "census agglomerations"),
        "releaseTime": "2023-10-04T08:30",
        "archiveStatusEn": "CURRENT - a cube available to the public and that is current",
        "dimension": [_dim(1, "Geography", _pad(
            [_m(1, "Canada", geo_level=1, parent=None, code="01"),
             _m(24, "Quebec", geo_level=2, parent=1, code="24"), *_CMA_MEMBERS], 166,
            parent=24))]
        + [_dim(p, n, _pad(ms, total, parent=None)) for p, n, ms, total in _CENSUS_DIMS],
    }
    cubes[98100622] = {
        "productId": "98100622",
        "cubeTitleEn": ("Population groups by housing suitability and condition of dwelling: "
                        "Canada, provinces and territories, census divisions and census "
                        "subdivisions"),
        "releaseTime": "2023-10-04T08:30",
        "archiveStatusEn": "CURRENT - a cube available to the public and that is current",
        "dimension": [_dim(1, "Geography", _pad(
            [_m(1, "Canada", geo_level=1, parent=None, code="01"),
             _m(884, "Quebec", geo_level=2, parent=1, code="24"),
             _m(1730, "Laval", geo_level=3, parent=884, code="2465"),
             # The TRAP: the CSD named identically to the CD, one level down.
             _m(1731, "Laval", geo_level=5, parent=1730, code="2465005"),
             _m(1732, "Montréal", geo_level=3, parent=884, code="2466")], 5468, parent=884))]
        + [_dim(p, n, _pad(ms, total, parent=None)) for p, n, ms, total in _CENSUS_DIMS],
    }
    cubes[43100060] = {
        "productId": "43100060",
        "cubeTitleEn": ("Selected housing characteristics, low income indicators and knowledge "
                        "of official languages, by visible minority and other characteristics "
                        "for the population in private households"),
        "releaseTime": "2023-01-23T08:30",
        "archiveStatusEn": "CURRENT - a cube available to the public and that is current",
        "dimension": [
            _dim(1, "Geography", _pad(
                [_m(13, "Quebec", geo_level=2, parent=1, code="24"),
                 _m(15, "Montréal (CMA), Que.\xa0\xa0", geo_level=503, parent=13, code="462"),
                 _m(17, "Québec (CMA), Que.\xa0\xa0", geo_level=503, parent=13, code="421")],
                63, nbsp=32, parent=13,
                # The live histogram, minus the three resolved members (one at level 2, two
                # at 503): 0×1, 1×6, 2×13, 503×41, 505×2 = 63.
                levels={0: 1, 1: 6, 2: 12, 503: 39, 505: 2})),
            _dim(2, "Gender", _pad([_m(1, "Total – Gender")], 3, parent=None)),
            _dim(3, "Age group and first official language spoken",
                 _pad([_m(1, "Total – Age group")], 9, parent=None)),
            _dim(4, "Immigrant and generation status", _pad(
                [_m(1, "Total – Immigrant and generation status"), _m(2, "Non-immigrants"),
                 _m(3, "Immigrants"), _m(4, "Admitted to Canada in the last 10 years"),
                 _m(5, "Admitted to Canada more than 10 years ago"),
                 _m(6, "Non-permanent residents")], 9, parent=None)),
            _dim(5, "Visible minority", _pad([_m(1, "Total – Visible minority")], 15,
                                             parent=None)),
            _dim(6, "Highest certificate, diploma or degree",
                 _pad([_m(6, "Total – Highest certificate, diploma or degree")], 6,
                      parent=None)),
            _dim(7, "Indicators", _pad(
                [_m(5, "Population living in a dwelling owned by some members of the "
                       "household"), _m(8, "Population living alone")], 11, parent=None)),
        ],
    }
    cubes[98100007] = {
        "productId": "98100007",
        "cubeTitleEn": "Population and dwelling counts: Canada and census divisions",
        "releaseTime": "2022-02-09T08:30",
        "archiveStatusEn": "CURRENT - a cube available to the public and that is current",
        "dimension": [
            _dim(1, "Geographic name", _pad(
                [_m(1, "Canada", geo_level=1, parent=None, code="01"),
                 _m(53, "Quebec", geo_level=2, parent=1, code="24"),
                 _m(98, "Laval", geo_level=3, parent=53, code="2465"),
                 _m(130, "Montréal", geo_level=3, parent=53, code="2466")], 307, parent=53)),
            _dim(2, "Population and dwelling counts (13)",
                 _pad([_m(1, "Population, 2021")], 13, parent=None)),
        ],
    }
    # DEEP-COPIED on the way out, and this is load-bearing rather than tidy: the mutation
    # battery edits member dicts IN PLACE (`m["geoLevel"] = 504`). Handing out the shared
    # module-level objects let one mutant's edit persist into every later test in the same
    # process — measured, and it made four mutants fire on the FIRST mutant's contamination
    # instead of their own. A mutant that fires for the wrong reason is an unreachable mutant
    # wearing a green tick.
    return copy.deepcopy([{"status": "SUCCESS", "object": cubes[int(p)]} for p in pids])


def _fake_value(pid: int, coordinate: str):
    ids = [int(x) for x in coordinate.split(".")]
    if pid in (98100621, 98100622):
        geo, tenure, _gender, maintainer, _stat, popchar, _suit = ids[:7]
        cell = _P[(pid, geo)][popchar]
        return {(1, 1): cell[0], (1, 2): cell[1], (2, 2): cell[2]}[(tenure, maintainer)]
    if pid == 43100060:
        geo, _gender, _age, imm, _vm, _edu, indicator = ids[:7]
        return _SIB[(geo, imm)][indicator]
    return _TOTALPOP[ids[0]]


def _fake_data(requests: list) -> list:
    """`getDataFromCubePidCoordAndLatestNPeriods`, returned SORTED BY COORDINATE STRING.

    Not in request order — that is what the live endpoint does (measured 2026-08-07, recorded
    in run_p7.py), and a probe that zipped the two would pair every value with the wrong
    meaning while every count still looked plausible.
    """
    out = [{"status": "SUCCESS",
            "object": {"productId": str(r["productId"]), "coordinate": r["coordinate"],
                       "vectorDataPoint": [
                           {"refPer": "2021-01-01",
                            "value": _fake_value(r["productId"], r["coordinate"])}]}}
           for r in requests]
    out.sort(key=lambda o: (o["object"]["coordinate"], o["object"]["productId"]))
    return out


def _isq_sheet(note: str, totals: dict, names: dict, header_offset: int) -> list[tuple]:
    """The workbook's row grid: notes, the `Scénario` header block, then the data body."""
    rows: list[tuple] = [("Population selon le groupe d'âge et le sexe...",) + (None,) * 6,
                         (note,) + (None,) * 6]
    while len(rows) < header_offset:
        rows.append((None,) * 7)
    rows.append(("Scénario", "Code", "Région1", "Année", "Statut", "Sexe", "TOTAL"))
    rows.append((None,) * 7)
    rows.append((None,) * 7)
    for scenario in ("Référence (A2026)", "Faible (D2026)", "Fort (E2026)"):
        for code, total in totals.items():
            men = total // 2
            for sex, value in ((1, men), (2, total - men), (3, total)):
                rows.append((scenario, code, names[code], 2021, "r", sex, value))
                rows.append((scenario, code, names[code], 2022, "r", sex, value + 1000))
    return rows


_FAKE_ISQ = {
    "pop-as-ra-base.xlsx": _isq_sheet(_ISQ_RA_NOTE, _ISQ_RA, _ISQ_RA_NAMES, 5),
    "pop-as-rmr-base.xlsx": _isq_sheet(_ISQ_RMR_NOTE, _ISQ_RMR, _ISQ_RMR_NAMES, 6),
}


def _wire(probe, tmp_path: Path, **overrides):
    """Point the probe's boundary seams at the fixtures and its output at `tmp_path`.

    `new_run()` too: `_sections` registers `Fact`s, and a Fact with no active run raises a
    RuntimeError rather than the ProbeRefusal the guard tests are looking for — which would
    make every mutant below pass for the wrong reason. `main()` opens its own run.
    """
    probe.new_run()
    probe._meta = overrides.get("meta", _fake_meta)
    probe._data = overrides.get("data", _fake_data)
    probe._isq_rows = overrides.get("isq", lambda name: _FAKE_ISQ[name])
    for name in ("spec", "p9", "constants"):
        if name in overrides:
            setattr(probe, {"spec": "_spec_s6", "p9": "_p9_note",
                            "constants": "_constants_source"}[name], overrides[name])
    probe.OUT = tmp_path / "P8-offline.md"
    return probe.OUT


def _run_offline(probe, tmp_path: Path, **overrides) -> str:
    out = _wire(probe, tmp_path, **overrides)
    probe.main()
    return out.read_text(encoding="utf-8")


@pytest.fixture
def offline(probe, tmp_path):
    """A fresh probe module wired to the fixtures — module-scoped state cannot leak."""
    mod = common._load_probe("p8")
    return mod, tmp_path


# ===========================================================================
# 1. The committed note: is the verdict resolved and is every token present?
# ===========================================================================
def test_p8_no_unfilled_placeholder(note):
    assert "[FILL" not in note, "an unresolved placeholder survived into the committed note"


def test_p8_records_a_resolved_verdict(note):
    _require_measured_or_skip(note)
    for name in EVIDENCE_TOKENS:
        value = _token(note, name)
        assert value is not None, f"a MEASURED note must carry `{name}`"
        assert value not in UNRESOLVED, f"`{name}` is unresolved: {value!r}"


def test_p8_note_is_generated_by_the_probe_that_claims_it(note):
    assert "Written by `probes/run_p8.py`" in note
    assert "nothing in this file is hand-edited" in note


def test_p8_the_note_names_both_inputs_not_headship_alone(note):
    """The FILENAME and the note must carry BOTH quantities.

    Ruling S binds a PAIR drawn from one member; a note titled for one of them invites the
    other to be sourced elsewhere, which is the exact transport ruling S eliminated.
    """
    assert NOTE.name == "P8-immigrant-inputs.md"
    head = note[: note.index("\n## ")]
    assert "headship" in head.lower() and "ratio" in head.lower(), head


# ===========================================================================
# 2. The producer, offline: regen equality against the committed note
# ===========================================================================
def test_p8_note_regenerates_byte_identically_from_the_fixture(offline, note):
    """REGEN EQUALITY ON THE PRODUCER, not on the artifact.

    A gate that only re-read the committed note would go green under any producer mutation the
    moment the note was regenerated through it. This runs the real derivation over fixtures
    carrying the live values and compares BYTES with what ships.
    """
    mod, tmp_path = offline
    got = _run_offline(mod, tmp_path)
    assert got == note, (
        "the producer no longer reproduces the committed note. If the live source moved, "
        "regenerate the note AND update the fixture in this file together — they are the two "
        "halves of one claim.")
    # Twice from the same fixture: no clock, no ambient state.
    assert _run_offline(mod, tmp_path) == got


def test_p8_reads_no_clock(probe):
    """No date may enter the note from the wall clock.

    Every dated field is a `releaseTime` from a live response or a line the workbook itself
    carries. A `date.today()` would look right on the day the note was built and break regen
    equality on the next — a failure with a one-day fuse that no single run can see.
    """
    tree = ast.parse((PROBES / "run_p8.py").read_text(encoding="utf-8"))
    clocks = {("datetime", "now"), ("date", "today"), ("time", "time"), ("time", "monotonic")}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id, node.func.attr) in clocks):
            raise AssertionError(f"run_p8.py calls {node.func.value.id}.{node.func.attr}() at "
                                 f"line {node.lineno} — the note would stop regenerating")


# ===========================================================================
# 3. The arithmetic, directly
# ===========================================================================
def test_p8_cell_arithmetic_is_the_definition_not_a_gloss(probe):
    cell = probe.Cell(persons=1000, maintainers=500, owner_maintainers=250)
    assert cell.headship == 0.5
    assert cell.owner_propensity == 0.5
    other = probe.Cell(persons=400, maintainers=100, owner_maintainers=40)
    residual = probe.cell_minus(cell, other)
    assert (residual.persons, residual.maintainers, residual.owner_maintainers) == (600, 400, 210)
    assert probe.ownership_ratio(cell, other) == pytest.approx(0.5 / 0.4)


def test_p8_a_zero_denominator_refuses_rather_than_publishing_a_rate(probe):
    """A cell with no persons has no headship. Returning 0.0, nan or inf would put a NUMBER
    where there is no measurement, and every downstream comparison would silently accept it."""
    empty = probe.Cell(persons=0, maintainers=0, owner_maintainers=0)
    with pytest.raises(probe.ProbeRefusal):
        _ = empty.headship
    with pytest.raises(probe.ProbeRefusal):
        _ = empty.owner_propensity


def test_p8_share_residual_cancels_a_uniform_universe_offset(probe):
    """The whole reason amendment #11 replaced the literal comparison.

    Scale the census universe by any constant and the LEVEL comparison moves while the
    province-controlled SHARE residual does not. That property is the construction's claim, so
    it is asserted rather than described.
    """
    for scale in (1.0, 0.97, 0.9, 1.05):
        got = probe.share_residual_pct(part_census=200 * scale, total_census=1000 * scale,
                                       part_isq=190, total_isq=1000)
        assert got == pytest.approx((0.200 / 0.190 - 1) * 100)
    assert probe.share_residual_pct(part_census=1, total_census=10,
                                    part_isq=1, total_isq=10) == pytest.approx(0.0)


# ===========================================================================
# 4. The territory gate — the task's load-bearing check
# ===========================================================================
def test_p8_threshold_is_derived_from_the_innocent_controls(probe):
    """DERIVED, never inherited. The 1% of ruling T's original wording was calibrated against
    the REFUTED construction; a threshold that does not move with its calibration set is a
    hand-typed number one level up."""
    small = {"a": 0.4, "b": -0.6}
    big = {"a": 0.4, "b": -0.6, "c": 2.0}
    t_small = probe.derive_threshold(small)
    t_big = probe.derive_threshold(big)
    assert t_small["max_name"] == "b" and t_small["max_abs"] == pytest.approx(0.6)
    assert t_big["max_name"] == "c" and t_big["max_abs"] == pytest.approx(2.0)
    assert t_big["threshold"] > t_small["threshold"], (
        "the threshold did not move when the innocent controls did — it is not derived")
    assert t_small["threshold"] == pytest.approx(0.6 * (1 + probe.MARGIN_FRACTION))
    assert t_small["margin_pp"] == pytest.approx(0.6 * probe.MARGIN_FRACTION)
    assert t_small["threshold"] != 1.0, "the inherited 1% must not be the derived threshold"


def test_p8_threshold_refuses_an_empty_or_degenerate_control_set(probe):
    """A threshold over zero innocent controls is a number with no calibration behind it."""
    with pytest.raises(probe.ProbeRefusal):
        probe.derive_threshold({})
    with pytest.raises(probe.ProbeRefusal):
        probe.derive_threshold({"a": 0.0, "b": 0.0})


def test_p8_territory_gate_fires_above_the_threshold_in_both_directions(probe):
    """Two-sided on |residual|: a territory mismatch has no preferred sign."""
    threshold = 1.0
    probe._guard_territory({"RA06": 0.9, "RA13": -0.9}, threshold)          # passes
    for bad in ({"RA06": 1.4, "RA13": 0.1}, {"RA06": 0.1, "RA13": -1.4}):
        with pytest.raises(probe.ProbeRefusal) as exc:
            probe._guard_territory(bad, threshold)
        assert "territory" in str(exc.value).lower()


def test_p8_the_measured_ra_residuals_sit_inside_the_innocent_range(offline):
    """The strongest honest sentence the gate supports, asserted on the real numbers.

    Not "the RAs pass" — that is a function of the margin — but "both RA residuals are smaller
    in absolute value than innocent controls whose territory identity is code-verified".
    """
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    measured = mod.LAST_RUN["territory"]
    innocent = [abs(v) for v in measured["innocent"].values()]
    for name, value in measured["ra"].items():
        assert abs(value) < max(innocent), f"{name} exceeds every innocent control"
        assert abs(value) <= measured["threshold"]


def test_p8_the_signed_residuals_are_published_beside_the_absolute_comparison(offline, note):
    """|residual| is what amendment #11's threshold rules on — but the SIGN is the informative
    direction for a territory difference, and here it does NOT run the same way: four of six
    innocent controls are negative while both geographies under test are positive, and RA13
    sits above every positive control. A note publishing only the |.| comparison would leave
    the adverse half of its own measurement unsaid, and DECISION-TERRITORY-GATE is the token
    plan task 25b consumes. This gate holds the note to BOTH readings.
    """
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    measured = mod.LAST_RUN["territory"]
    innocent, ra, signed = measured["innocent"], measured["ra"], measured["signed"]
    # The measured shape this test exists to keep visible. If the sources move so that the
    # innocent set is one-sided or the RAs stop being the outliers, the note's own sentences
    # change with them — but the note must never publish only the absolute reading.
    assert signed["negative"] and signed["positive"], "the innocent set is no longer two-sided"
    assert len(signed["negative"]) == 4 and len(innocent) == 6, signed
    assert signed["ra_positive"] == list(ra), "a geography under test is no longer positive"
    assert signed["above_every_positive"] == ["LAVAL_RA13"], signed["above_every_positive"]

    body = note[note.index("### 4b."):note.index("### 4c.")]
    assert f"{signed['low']:+.3f}% to {signed['high']:+.3f}%" in body, (
        "the note does not publish the SIGNED span of the innocent controls beside the "
        "absolute-value comparison")
    assert f"{len(signed['negative'])} of the {len(innocent)} of them NEGATIVE" in body, body
    for name in signed["above_every_positive"]:
        assert f"{name} measures ABOVE it" in body, name
    # Every "inside the innocent range" claim, wherever it sits, must say WHICH range — an
    # unqualified one reads as agreement in sign, which this run's own numbers contradict.
    for sentence in re.findall(r"[^.]*inside the innocent[^.]*", note, re.I):
        assert "|residual|" in sentence, f"unqualified innocent-range claim: {sentence.strip()!r}"
    gate = _token(note, "DECISION-TERRITORY-GATE")
    assert "|residual|" in gate and "SIGNED" in gate, gate
    assert f"{signed['low']:+.3f}% to {signed['high']:+.3f}%" in gate, gate


def test_p8_the_gate_never_reaches_for_a_cube_ruling_T_did_not_name(offline):
    """98-10-0007-01 is a DIAGNOSTIC. If it could enter the gate, the gate would be repairable
    by admitting cubes until it passed — which is what amendment #11 refuses."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    gate_pids = mod.LAST_RUN["territory"]["source_pids"]
    assert mod.TOTALPOP_PID not in gate_pids, gate_pids
    assert set(gate_pids) == {mod.CD_PID, mod.CMA_PID, "ISQ"}, gate_pids


# ===========================================================================
# 5. The floor gate — cross-cube, and the member must be the RULED one
# ===========================================================================
def test_p8_floor_gate_reds_when_headship_falls_below_living_alone(probe):
    """Each person living alone maintains exactly one household, so headship BELOW the
    living-alone share is arithmetically impossible — a defect, not a datum."""
    probe._guard_floor({"MTL_RMR": 0.5259}, {"MTL_RMR": 0.154})
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._guard_floor({"MTL_RMR": 0.100}, {"MTL_RMR": 0.154})
    assert "floor" in str(exc.value).lower()
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_floor({"MTL_RMR": 0.154}, {"MTL_RMR": 0.154})  # EXCEED, not equal


def test_p8_floor_gate_refuses_a_geography_it_cannot_check(probe):
    """A floor with no share to compare against must REFUSE, never silently pass."""
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_floor({"MTL_RMR": 0.5259}, {})


def test_p8_the_floor_uses_the_settled_member_not_the_pooled_one(offline):
    """0.154/0.164 (settled) is the ruled and STRICTER bound; 0.134/0.127 is a different
    member. Wiring the looser one would leave the gate green on a value the ruling rejects."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    floor = mod.LAST_RUN["floor"]
    assert floor["member"] == "Admitted to Canada more than 10 years ago"
    assert floor["share"]["MTL_RMR"] == pytest.approx(0.154)
    assert floor["share"]["QC_RMR"] == pytest.approx(0.164)
    assert floor["pooled"]["MTL_RMR"] == pytest.approx(0.134)
    assert floor["pooled"]["QC_RMR"] == pytest.approx(0.127)
    assert all(floor["share"][g] > floor["pooled"][g] for g in ("MTL_RMR", "QC_RMR")), (
        "the settled member is supposed to be the STRICTER bound — that claim just failed")


def test_p8_floor_coverage_absence_is_earned_by_a_live_search(offline, note):
    """A NOT-COVERED verdict must be EARNED. The three uncovered geographies are recorded only
    after searching the sibling cube's own member list for them."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    floor = mod.LAST_RUN["floor"]
    assert floor["searched_members"] == 63, floor["searched_members"]
    assert set(floor["not_covered"]) == {"HORS_RMR", "MTL_ISLAND_RA06", "LAVAL_RA13"}
    assert "63" in _token(note, "DECISION-FLOOR-COVERAGE")


# ===========================================================================
# 6. Citation coupling — on the DIGITS, never on a prose prefix
# ===========================================================================
def test_p8_citation_coupling_reds_on_a_perturbed_digit(offline):
    """The gate that ties this note's PROSE figures to §6.

    Perturbs a figure §6 states OUTSIDE the two ruled tables (the province maintainer count),
    so the table-row gate below cannot fire first and mask this one — two gates covering the
    same text is exactly how one of them becomes unreachable without anybody noticing.
    """
    mod, tmp_path = offline
    real = mod._spec_s6()
    assert "3,749,035" in real
    _wire(mod, tmp_path, spec=lambda: real.replace("3,749,035", "3,749,030"))
    with pytest.raises(mod.ProbeRefusal) as exc:
        mod._sections(["-"])
    assert exc.value.boundary == "citation" and "3,749,035" in str(exc.value)


def test_p8_a_ruled_table_row_whose_value_disagrees_reds(offline):
    """The other half: a recomputed PAIR that is not the pair §6's own row publishes.

    Keyed on the geography token, so the failure names the row rather than a sentence.
    """
    mod, tmp_path = offline
    real = mod._spec_s6()
    assert "| MTL_RMR | **0.5259**" in real
    _wire(mod, tmp_path,
          spec=lambda: real.replace("| MTL_RMR | **0.5259**", "| MTL_RMR | **0.5299**"))
    with pytest.raises(mod.ProbeRefusal) as exc:
        mod._sections(["-"])
    assert exc.value.boundary == "citation"
    assert "MTL_RMR" in str(exc.value) and "0.5259" in str(exc.value)


def test_p8_citation_coupling_refuses_a_section_it_could_not_read(probe):
    """A citation gate over an empty or unparseable §6 passes vacuously — the classic
    can't-fail check. It must refuse instead."""
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_s6_rows("")
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_s6_rows("## 6. Demand side\n\nno tables here at all\n")


def test_p8_citation_coupling_keys_rows_on_the_geography_token(offline):
    """Keyed on a STABLE token — the modeled-geography name and the digits — never on a prose
    prefix, which a reworded sentence would silently detach."""
    mod, tmp_path = offline
    real = mod._spec_s6()
    rows = mod._guard_s6_rows(real)
    assert set(rows) == {"MTL_RMR", "QC_RMR", "HORS_RMR", "MTL_ISLAND_RA06", "LAVAL_RA13"}
    assert "0.5259" in rows["MTL_RMR"] and "0.9634" in rows["MTL_RMR"]
    assert "0.5555" in rows["MTL_ISLAND_RA06"] and "1.0757" in rows["MTL_ISLAND_RA06"]
    # A row losing its geography token must not silently drop out of the coupled set.
    with pytest.raises(mod.ProbeRefusal):
        mod._guard_s6_rows(real.replace("| MTL_RMR |", "| MTL_CMA |"))


def test_p8_coupled_tokens_are_all_really_in_the_spec(offline):
    """The coupling list must not contain a token §6 does not carry — a gate asserting the
    presence of something that was never there would red on a correct run."""
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    s6 = mod._spec_s6()
    coupled = mod.LAST_RUN["coupled"]
    assert len(coupled) >= 25, f"only {len(coupled)} figures are citation-coupled"
    for label, tok in coupled:
        assert tok in s6, f"{label}: {tok!r} is not in spec §6"


# ===========================================================================
# 7. The one-universe claim — asserted at exactly its measured strength
# ===========================================================================
def test_p8_identity_is_asserted_on_the_ruled_triple_only(probe):
    """BIT-IDENTITY holds for the ruled Before-2016 triple and NOT cube-wide: independent
    rounding-to-5 gives four cells that differ by exactly 5. A note claiming cube-wide
    identity would assert what its own data contradicts, and a gate pinning that claim would
    pin a falsehood — so the gate binds the triple, tolerates ±5 elsewhere, and refuses more.
    """
    triple = {12: (1007855, 527710, 298100)}
    probe._guard_universe(dict(triple), dict(triple))
    off = {12: (1007855, 527710, 298105)}
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._guard_universe(dict(triple), off)
    assert "12" in str(exc.value)

    cma = {12: (1007855, 527710, 298100), 10: (6892110, 3058105, 1921035)}
    cd_ok = {12: (1007855, 527710, 298100), 10: (6892110, 3058100, 1921035)}
    drifted = probe._guard_universe(cma, cd_ok)
    assert drifted == [(10, 1, 3058105, 3058100)], drifted
    cd_bad = {12: (1007855, 527710, 298100), 10: (6892110, 3058095, 1921035)}
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_universe(cma, cd_bad)


def test_p8_the_note_reports_the_plus_or_minus_five_rows_it_measured(offline, note):
    mod, tmp_path = offline
    _run_offline(mod, tmp_path)
    drifted = mod.LAST_RUN["universe"]["drifted"]
    assert len(drifted) == 4, drifted
    assert {row[0] for row in drifted} == {10, 11, 14}
    for _pc, _field, a, b in drifted:
        assert abs(a - b) == 5
    for value in ("3,058,105", "3,058,100", "599,370", "599,365", "315,825", "315,820",
                  "205,775", "205,770"):
        assert value in note, f"the note does not report the measured cell {value}"
    # Every bit-identity claim in the note must be SCOPED to the ruled triple. An unqualified
    # one would assert what the four rows above contradict.
    for sentence in re.findall(r"[^.]*bit-identical[^.]*\.", note, re.I):
        assert "triple" in sentence.lower(), (
            f"unscoped bit-identity claim: {sentence.strip()!r}")


# ===========================================================================
# 8. Response handling — the WDS traps
# ===========================================================================
def test_p8_responses_are_keyed_by_coordinate_not_request_order(probe):
    requests = [{"productId": 98100621, "coordinate": probe.coord(35, 1, 1, 1, 1, 12, 1),
                 "latestN": 1},
                {"productId": 98100621, "coordinate": probe.coord(24, 1, 1, 1, 1, 12, 1),
                 "latestN": 1}]
    response = list(reversed([
        {"status": "SUCCESS",
         "object": {"productId": "98100621", "coordinate": r["coordinate"],
                    "vectorDataPoint": [{"refPer": "2021-01-01", "value": i}]}}
        for i, r in enumerate(requests)]))
    series = probe._guard_response(requests, response)
    assert series[(98100621, requests[0]["coordinate"])] == 0
    assert series[(98100621, requests[1]["coordinate"])] == 1


def test_p8_a_failed_cell_with_an_empty_point_list_refuses(probe):
    """A `status: FAILED` cell carries an EMPTY `vectorDataPoint`, so a blind `[0]` raises an
    IndexError that reads like a code bug. It is refused explicitly instead."""
    requests = [{"productId": 98100621, "coordinate": probe.coord(24, 1, 1, 1, 1, 12, 1),
                 "latestN": 1}]
    for broken in ({"status": "FAILED", "object": {"productId": "98100621",
                                                   "coordinate": requests[0]["coordinate"],
                                                   "vectorDataPoint": []}},
                   {"status": "SUCCESS", "object": {"productId": "98100621",
                                                    "coordinate": requests[0]["coordinate"],
                                                    "vectorDataPoint": []}}):
        with pytest.raises(probe.ProbeRefusal):
            probe._guard_response(requests, [broken])


def test_p8_a_missing_series_refuses_rather_than_defaulting(probe):
    requests = [{"productId": 98100621, "coordinate": probe.coord(24, 1, 1, 1, 1, 12, 1),
                 "latestN": 1}]
    with pytest.raises(probe.ProbeRefusal):
        probe._guard_response(requests, [])


def test_p8_a_reference_period_that_is_not_the_census_year_refuses(probe):
    requests = [{"productId": 98100621, "coordinate": probe.coord(24, 1, 1, 1, 1, 12, 1),
                 "latestN": 1}]
    response = [{"status": "SUCCESS",
                 "object": {"productId": "98100621", "coordinate": requests[0]["coordinate"],
                            "vectorDataPoint": [{"refPer": "2016-01-01", "value": 1}]}}]
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._guard_response(requests, response)
    assert "2021" in str(exc.value)


def test_p8_member_resolution_is_by_name_and_the_pinned_id_is_asserted(probe):
    metas = {int(r["object"]["productId"]): r["object"]
             for r in _fake_meta([98100621, 98100622, 43100060, 98100007])}
    member = probe._member(metas, 98100622, 1, "Montréal", geo_level=3, parent=884)
    assert member["memberId"] == 1732 and member["classificationCode"] == "2466"
    with pytest.raises(probe.ProbeRefusal):
        probe._member(metas, 98100622, 1, "Nowhere-en-Québec", geo_level=3, parent=884)


def test_p8_the_census_subdivision_trap_is_structurally_avoided(probe):
    """`Laval` names BOTH the census division (1730, geoLevel 3) and a census subdivision
    (1731, geoLevel 5) inside it. Resolving by NAME alone picks whichever comes first."""
    metas = {int(r["object"]["productId"]): r["object"] for r in _fake_meta([98100622])}
    laval = probe._member(metas, 98100622, 1, "Laval", geo_level=3, parent=884)
    assert laval["memberId"] == 1730 and laval["classificationCode"] == "2465"
    names = [m["memberNameEn"] for m in metas[98100622]["dimension"][0]["member"]]
    assert names.count("Laval") == 2, "the fixture no longer carries the trap this test needs"
    # Name ALONE is ambiguous, and ambiguity must refuse rather than take the first hit.
    with pytest.raises(probe.ProbeRefusal):
        probe._member(metas, 98100622, 1, "Laval")


def test_p8_isq_rows_are_resolved_by_label_and_the_pinned_code_asserted(probe):
    """The ISQ mirror of resolve-by-name / assert-the-pinned-id.

    Before this the ISQ side of the territory gate fetched on a hand-typed code and merely
    PRINTED whatever label sat there, so a re-pinned vintage that renumbered the
    région-administrative axis would have put another région's population through the residual
    with the note still rendering PASS. The census side never accepted that shape.
    """
    labels = {0: "Le Québec", 6: "Montréal", 13: "Laval", 505: "RMR d'Ottawa-Gatineau2",
              462: "RMR de Montréal "}
    assert probe._isq_code("book", labels, "Montréal", 6) == 6
    # The footnote MARKER and the trailing space are not part of a territory's identity: a
    # guard keyed on them would refuse when a footnote is renumbered.
    assert probe._isq_code("book", labels, "RMR d'Ottawa-Gatineau", 505) == 505
    assert probe._isq_code("book", labels, "RMR de Montréal", 462) == 462
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._isq_code("book", labels, "Montréal", 13)          # a renumbered code axis
    assert "pinned" in str(exc.value).lower() and exc.value.boundary == "isq-workbook"
    with pytest.raises(probe.ProbeRefusal):
        probe._isq_code("book", labels, "Nowhere", 6)            # renamed or dropped row
    with pytest.raises(probe.ProbeRefusal):
        probe._isq_code("book", {1: "Laval", 2: "Laval "}, "Laval", 1)   # ambiguous label


def test_p8_every_isq_row_the_run_keys_on_goes_through_the_label_guard(probe):
    """Coverage of the guard, not just its existence: the province row of BOTH workbooks, both
    RA rows, and the two RMR rows §2's Gatineau claim rests on."""
    isq = {probe.ISQ_RA_BOOK: {"labels": dict(_ISQ_RA_NAMES)},
           probe.ISQ_RMR_BOOK: {"labels": dict(_ISQ_RMR_NAMES)}}
    resolved = probe._guard_isq_labels(isq)
    assert resolved == {
        (probe.ISQ_RA_BOOK, "Le Québec"): 0, (probe.ISQ_RA_BOOK, "Montréal"): 6,
        (probe.ISQ_RA_BOOK, "Laval"): 13, (probe.ISQ_RMR_BOOK, "Le Québec"): 0,
        (probe.ISQ_RMR_BOOK, "Territoire hors des RMR"): 999,
        (probe.ISQ_RMR_BOOK, "RMR d'Ottawa-Gatineau"): 505}


def test_p8_pinned_ids_that_move_are_a_finding_not_a_typo(probe):
    """A member resolving to a different id than the one the mandate pinned must RED. The
    pinned id is a claim about the cube; if it stops holding, the claim is what is wrong."""
    metas = {int(r["object"]["productId"]): r["object"] for r in _fake_meta([98100621])}
    quebec = probe._member(metas, 98100621, 1, "Quebec", geo_level=2, parent=1)
    probe._guard_pinned_id(98100621, "Quebec", quebec, 24)
    with pytest.raises(probe.ProbeRefusal) as exc:
        probe._guard_pinned_id(98100621, "Quebec", quebec, 25)
    assert "pinned" in str(exc.value).lower()


# ===========================================================================
# 9. Floor guards over the whole derivation — each mutant applied to the fixture the
#    green path really reads, so no mutant is unreachable.
# ===========================================================================
@pytest.mark.parametrize("mutation", [
    "cma-cd-province-disagree", "isq-parts-do-not-sum", "isq-workbooks-disagree-on-province",
    "census-cubes-disagree-on-province-persons", "empty-vector-data-point",
    "wrong-reference-period", "moved-member-id", "meta-without-dimensions",
    "sibling-loses-the-settled-member", "headship-below-the-floor",
    "ra-residual-above-the-threshold", "code-join-breaks", "cma-children-set-changes",
    "dimension-lists-diverge", "isq-scenario-fans-disagree", "isq-header-note-gone",
    "p9-tokens-gone", "constants-antipattern-gone", "isq-ra-code-axis-renumbered",
    "isq-row-relabelled",
])
def test_p8_floor_guards_are_load_bearing(offline, mutation):
    """Each guard must actually fire. A guard that cannot fail is not a guard — and an
    UNREACHABLE mutant is not a surviving one, so every mutation below is applied to the same
    fixture `test_p8_note_regenerates_byte_identically_from_the_fixture` proves passes clean.
    """
    mod, tmp_path = offline
    meta, data, isq = _fake_meta, _fake_data, (lambda name: _FAKE_ISQ[name])
    extra: dict = {}

    if mutation == "cma-cd-province-disagree":
        broken = {k: dict(v) for k, v in _P.items()}
        broken[(98100622, 884)][12] = (1007855, 527710, 298120)
        data = lambda reqs: _fake_data_with(reqs, broken)                    # noqa: E731
    elif mutation == "isq-parts-do-not-sum":
        totals = dict(_ISQ_RA); totals[6] = totals[6] + 1000
        isq = lambda name: (_isq_sheet(_ISQ_RA_NOTE, totals, _ISQ_RA_NAMES, 5)  # noqa: E731
                            if name == "pop-as-ra-base.xlsx" else _FAKE_ISQ[name])
    elif mutation == "isq-workbooks-disagree-on-province":
        totals = dict(_ISQ_RMR); totals[0] = totals[0] + 5000; totals[999] += 5000
        isq = lambda name: (_isq_sheet(_ISQ_RMR_NOTE, totals, _ISQ_RMR_NAMES, 6)  # noqa: E731
                            if name == "pop-as-rmr-base.xlsx" else _FAKE_ISQ[name])
    elif mutation == "census-cubes-disagree-on-province-persons":
        broken = {k: dict(v) for k, v in _P.items()}
        broken[(98100622, 884)][1] = (8308000, 3749035, 2245600)
        data = lambda reqs: _fake_data_with(reqs, broken)                    # noqa: E731
    elif mutation == "empty-vector-data-point":
        def data(reqs):
            out = _fake_data(reqs)
            out[0]["object"]["vectorDataPoint"] = []
            out[0]["status"] = "FAILED"
            return out
    elif mutation == "wrong-reference-period":
        def data(reqs):
            out = _fake_data(reqs)
            out[0]["object"]["vectorDataPoint"][0]["refPer"] = "2016-01-01"
            return out
    elif mutation == "moved-member-id":
        def meta(pids):
            out = _fake_meta(pids)
            for item in out:
                if int(item["object"]["productId"]) == 98100622:
                    for m in item["object"]["dimension"][0]["member"]:
                        if m["memberId"] == 1732:
                            m["memberId"] = 1799
            return out
    elif mutation == "meta-without-dimensions":
        def meta(pids):
            out = _fake_meta(pids)
            out[0]["object"]["dimension"] = []
            return out
    elif mutation == "sibling-loses-the-settled-member":
        def meta(pids):
            out = _fake_meta(pids)
            for item in out:
                if int(item["object"]["productId"]) == 43100060:
                    dim = item["object"]["dimension"][3]
                    dim["member"] = [m for m in dim["member"] if m["memberId"] != 5]
            return out
    elif mutation == "headship-below-the-floor":
        broken = {k: dict(v) for k, v in _P.items()}
        persons, maint, owner = broken[(98100621, 35)][12]
        broken[(98100621, 35)][12] = (persons, int(persons * 0.10), owner)
        data = lambda reqs: _fake_data_with(reqs, broken)                    # noqa: E731
    elif mutation == "ra-residual-above-the-threshold":
        broken = {k: dict(v) for k, v in _P.items()}
        broken[(98100622, 1732)][1] = (1_500_000, 910360, 360120)
        data = lambda reqs: _fake_data_with(reqs, broken)                    # noqa: E731
    elif mutation == "code-join-breaks":
        # Drummondville's census classification code stops matching any ISQ row. The
        # calibration set's identity is the only reason its spread can set a threshold.
        def meta(pids):
            out = _fake_meta(pids)
            for item in out:
                if int(item["object"]["productId"]) == 98100621:
                    for m in item["object"]["dimension"][0]["member"]:
                        if m["memberId"] == 30:
                            m["classificationCode"] = "446"
            return out
    elif mutation == "cma-children-set-changes":
        # One CMA stops being a geoLevel-503 child, silently redefining HORS_RMR.
        def meta(pids):
            out = _fake_meta(pids)
            for item in out:
                if int(item["object"]["productId"]) == 98100621:
                    for m in item["object"]["dimension"][0]["member"]:
                        if m["memberId"] == 40:
                            m["geoLevel"] = 504
            return out
    elif mutation == "dimension-lists-diverge":
        def meta(pids):
            out = _fake_meta(pids)
            for item in out:
                if int(item["object"]["productId"]) == 98100622:
                    item["object"]["dimension"][2]["dimensionNameEn"] = "Sex (3)"
            return out
    elif mutation == "isq-scenario-fans-disagree":
        rows = [r if not (len(r) == 7 and r[3] == 2021 and r[1] == 6
                          and r[0] == "Fort (E2026)")
                else (r[0], r[1], r[2], r[3], r[4], r[5], r[6] + 7)
                for r in _FAKE_ISQ["pop-as-ra-base.xlsx"]]
        isq = lambda name: (rows if name == "pop-as-ra-base.xlsx"      # noqa: E731
                            else _FAKE_ISQ[name])
    elif mutation == "isq-header-note-gone":
        rows = [r if not (r and r[0] and _ISQ_RA_NOTE in str(r[0])) else (None,) * 7
                for r in _FAKE_ISQ["pop-as-ra-base.xlsx"]]
        isq = lambda name: (rows if name == "pop-as-ra-base.xlsx"      # noqa: E731
                            else _FAKE_ISQ[name])
    elif mutation == "isq-ra-code-axis-renumbered":
        # `Montréal` and `Laval` swap codes — exactly what a re-pinned ISQ vintage that
        # renumbered the région-administrative axis looks like. Before the label guard this
        # produced NO refusal: the gate kept fetching codes 6 and 13, so RA06 silently took
        # Laval's population and the note still rendered PASS. Only §4d's printed labels moved.
        names = dict(_ISQ_RA_NAMES); names[6], names[13] = names[13], names[6]
        isq = lambda name: (_isq_sheet(_ISQ_RA_NOTE, _ISQ_RA, names, 5)   # noqa: E731
                            if name == "pop-as-ra-base.xlsx" else _FAKE_ISQ[name])
    elif mutation == "isq-row-relabelled":
        # The other branch: the row this run keys on is no longer labelled what it was, so it
        # resolves to nothing. An absent territory must refuse, never fall through to a code.
        names = dict(_ISQ_RMR_NAMES); names[505] = "RMR de Gatineau"
        isq = lambda name: (_isq_sheet(_ISQ_RMR_NOTE, _ISQ_RMR, names, 6)  # noqa: E731
                            if name == "pop-as-rmr-base.xlsx" else _FAKE_ISQ[name])
    elif mutation == "p9-tokens-gone":
        extra["p9"] = lambda: "# P9\n\nno decision tokens survive here\n"
    elif mutation == "constants-antipattern-gone":
        extra["constants"] = lambda: '"""a docstring with no anti-pattern block."""\n'

    _wire(mod, tmp_path, meta=meta, data=data, isq=isq, **extra)
    with pytest.raises(mod.ProbeRefusal):
        mod._sections(["-"])


def _fake_data_with(requests: list, table: dict) -> list:
    """`_fake_data` against a mutated census table."""
    saved = dict(_P)
    try:
        _P.clear(); _P.update(table)
        return _fake_data(requests)
    finally:
        _P.clear(); _P.update(saved)


def test_p8_a_refusal_routes_to_unknown_and_never_to_a_friendlier_verdict(offline):
    """The failure path is a real path, not a comment: a refused run must still write a note,
    and that note must record UNKNOWN with the boundary — never a partial MEASURED."""
    mod, tmp_path = offline

    def boom(pids):
        raise mod.ProbeRefusal("wds-meta", "synthetic outage for the failure-path test")

    text = _run_offline(mod, tmp_path, meta=boom)
    assert _token(text, "DECISION-VERDICT") == "UNKNOWN-PROBE-FAILED"
    assert "LIVE PROBE FAILED: ProbeRefusal:" in text
    assert "LIVE PROBE FAILED-AT: wds-meta" in text
    assert "DECISION-TERRITORY-GATE: PASS" not in text


def test_p8_refusal_is_not_a_network_exception_name(probe):
    assert probe.ProbeRefusal.__name__ not in NETWORK_EXCEPTIONS
    assert issubclass(probe.ProbeRefusal, RuntimeError)
    assert not issubclass(probe.ProbeRefusal, OSError)


# ===========================================================================
# 10. The note's REASONING, held to what the run measured
# ===========================================================================
def test_p8_the_above_one_ratio_is_explained_with_the_propensities_that_establish_it(note):
    """Asserting the composition without printing the propensities that establish it is the
    depth-3 defect this arc grades: a correct number supporting a sentence it does not entail.
    """
    assert "0.4210" in note and "0.4529" in note, (
        "the note claims the island ratio exceeds 1 by composition but does not print the two "
        "owner-maintainer propensities that make that true")
    assert "0.9634" in note
    for marker in ("pooled", "constants.py"):
        assert marker in note, f"the note does not distinguish the {marker} anti-pattern"


def test_p8_the_sibling_check_is_stated_at_its_coarse_strength(note):
    body = note.lower()
    assert "0.9682" in note and "0.9634" in note
    assert "coarse" in body
    for axis in ("member cut", "metric"):
        assert axis in body, f"the sibling comparison does not name its {axis} difference"


def test_p8_the_closure_is_carried_by_reference_from_p9s_own_tokens(note):
    """Carried BY REFERENCE, at the level P9 earned — never restated as an unqualified
    absence. The tokens must be P9's, so a re-run of P9 that narrows its closure narrows this
    sentence too instead of leaving a stale absolute behind."""
    p9 = P9_NOTE.read_text(encoding="utf-8")
    carried = _token(note, "DECISION-CATALOGUE-CLOSURE")
    assert _token(p9, "DECISION-VERDICT") in carried, carried
    assert _token(p9, "DECISION-RESIDUAL") in carried, carried
    assert "does not exist" not in note.lower()


def test_p8_the_scope_token_keeps_this_a_probe(note):
    scope = _token(note, "DECISION-SCOPE")
    assert "immigrant_inputs.py" in scope and "not" in scope.lower(), scope


def test_p8_the_note_states_what_the_gate_cannot_detect(note):
    """The gate's POWER, published beside its verdict. A pass at a resolution of ~1.6% of a
    population share does not establish territory identity — it fails to refute it at that
    resolution, and a reader who cannot see the resolution cannot price the claim."""
    body = note.lower()
    assert "resolution" in body or "cannot detect" in body
    assert "identity" in body


def test_p8_the_two_code_axes_are_registered_facts_not_bare_numerals(offline):
    """§4d's code axes are RECORDED, and recorded means registered.

    The provenance header decomposes the note's untagged numerals into exactly two classes —
    table cells and audit metadata — and presents that as exhaustive. A narrative code printed
    bare belongs to neither, so the header would be describing a document it does not match.
    The ISQ codes are DERIVED (this run resolves them by label in the workbook); the SGC codes
    are CITED (read verbatim off live metadata, computed from nothing).
    """
    mod, tmp_path = offline
    _wire(mod, tmp_path)
    log = mod.new_run()          # supersedes _wire's, so this test reads its OWN registry
    mod._sections(["-"])
    isq_codes = {f.text for f in log.facts
                 if f.kind == "derived" and mod.ISQ_RA_BOOK in f.source}
    assert isq_codes == {"6", "13"}, isq_codes
    sgc_codes = {f.text for f in log.facts
                 if f.kind == "cited" and "classificationCode" in f.source}
    assert sgc_codes == {"2466", "2465"}, sgc_codes


def test_p8_every_narrative_figure_is_a_registered_fact(note):
    """The provenance header's arithmetic must close, and it must be non-trivial."""
    line = re.search(r"This run registered (\d+) provenance-tagged figures: (\d+) DERIVED "
                     r".*?and (\d+) CITED", note, re.S)
    assert line, "the note carries no parseable provenance summary"
    total, derived, cited = (int(g) for g in line.groups())
    assert total == derived + cited and derived > 30 and cited > 0, (total, derived, cited)
