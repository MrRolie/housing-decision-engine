"""Gates on the machinery run_p3/p4/p5.py SHARE (probes/_wds.py, tests/_probe_asserts.py).

These exist because the extraction that created those two modules had one job — change
nothing observable — and three of its failure modes are invisible to the per-probe
suites:

  1. `provenance_header` is now ONE function serving three different notes. If the
     shared skeleton or any probe's relocated prose drifted by a byte, every future
     note carries it. Gated against `fixtures/golden_headers.json`, which was pinned
     from the PRE-extraction `_provenance_header()` of each probe — so this is an
     old-vs-new equivalence check, not a self-consistency one.
  2. The registry moved from three module-global lists to one shared module. A
     module global would now be shared by all three probes AND by every fresh test
     load; `test_cross_probe_runs_do_not_share_a_registry` is what makes that
     impossible-by-construction claim falsifiable.
  3. `NETWORK_EXCEPTIONS` is now one set behind three gates, so widening it once
     widens every probe's excusable-failure set at the same time.
"""

import contextvars
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from . import test_probe_p3 as t3
from . import test_probe_p4 as t4
from . import test_probe_p5 as t5
from ._probe_asserts import NETWORK_EXCEPTIONS, recorded_failure_type, token

PROBES = Path(__file__).resolve().parent.parent / "probes"
GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "golden_headers.json").read_text(
        encoding="utf-8"
    )
)

# The exact mixes the fixture was generated from. Kept verbatim so a golden entry and
# the run that reproduces it cannot drift apart.
MIXES = {
    "empty": [],
    "all_derived": [("1.23", "derived", "how A"), ("4.56", "derived", "how B")],
    "mixed": [("1.23", "derived", "how A"), ("9.9%", "cited", "Source X, 2021"),
              ("7", "derived", "how C"), ("42", "cited", "Source Y")],
    "all_cited": [("9.9%", "cited", "Source X, 2021"), ("42", "cited", "Source Y")],
}


def _wds_module():
    """Import `probes/_wds.py` the FLAT way the probes themselves do.

    The `sys.path` insert is required, not cosmetic: probes/ is deliberately not a
    package (script mode resolves `_wds` via `sys.path[0]`), and neither pytest's
    rootdir handling nor `spec_from_file_location` puts probes/ on the path.
    """
    probes_dir = str(PROBES)
    if probes_dir not in sys.path:
        sys.path.insert(0, probes_dir)
    import _wds

    return _wds


def _load_probe(stem: str):
    """Load `probes/run_<stem>.py` as a fresh module object (with `_wds` resolvable)."""
    _wds_module()
    spec = importlib.util.spec_from_file_location(f"{stem}_common_under_test",
                                                  PROBES / f"run_{stem}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("stem", ["p3", "p4", "p5"])
@pytest.mark.parametrize("mix_name", list(MIXES))
def test_provenance_header_matches_pinned_goldens(stem, mix_name):
    """The rewired header must equal, LIST-for-LIST, what the old one produced.

    List equality, not a substring check: a substring assertion passes when a line is
    duplicated, reordered, or when the blank-line structure changes — and the blank
    lines are what separate the summary from the cited block in the rendered note.
    """
    _wds = _wds_module()
    mod = _load_probe(stem)
    log = _wds.new_run()
    for text, kind, source in MIXES[mix_name]:
        _wds.Fact(text, kind, source)

    # `mod._WRITTEN_BY`, NOT a synthesized f"run_{stem}.py": the filename is the one
    # header field that a copy-pasted call block carries forward silently, so the test
    # must read what the probe would actually publish, not reconstruct what it should.
    assert mod._WRITTEN_BY == f"run_{stem}.py", (
        f"{stem} would attribute its note to {mod._WRITTEN_BY!r} — a generated artifact "
        f"must name the file that generated it."
    )
    got = _wds.provenance_header(
        log,
        written_by=mod._WRITTEN_BY,
        scope=mod._SCOPE,
        summary=mod._summary,
        cited_label=mod._CITED_LABEL,
    )
    assert got == GOLDEN[stem][mix_name], (
        f"{stem}/{mix_name}: the extracted provenance_header no longer reproduces the "
        f"header the pre-extraction code produced. Every committed note's provenance "
        f"paragraph is written by this function, so a drift here rewrites them."
    )


def test_fact_outside_a_run_raises():
    """The registry REFUSES a fact it cannot attribute — the gate's FAILURE behaviour.

    Runs inside a fresh `contextvars.Context` on purpose. `_ACTIVE` is deliberately
    not reset when a probe's `main()` returns, so any earlier test in this process
    (every offline `mod.main()` run) leaves it bound; asserting in the ambient context
    would silently test the stale log instead of the unbound case, and would pass or
    fail on collection order. A fresh Context sees the `None` default by construction.
    """
    _wds = _wds_module()

    def _attempt() -> None:
        assert _wds._ACTIVE.get() is None, "fresh Context must start unbound"
        with pytest.raises(RuntimeError, match="no active run"):
            _wds.Fact("x", "derived", "y")

    contextvars.Context().run(_attempt)


def test_new_run_yields_a_fresh_isolated_log():
    _wds = _wds_module()
    first = _wds.new_run()
    assert first.facts == []
    _wds.Fact.derived(1, "how")
    second = _wds.new_run()
    assert second is not first, "each run must get its own log object"
    assert second.facts == [], "a new run must not inherit the previous run's facts"
    assert len(first.facts) == 1, "the previous log must keep exactly what it recorded"


def _registered_line(text: str) -> str:
    """The provenance sentence stating how many figures the run registered."""
    found = re.search(r"^.*[Tt]his run registered .*$", text, re.M)
    assert found, "the note carries no 'this run registered N' provenance sentence"
    return found.group(0)


def test_cross_probe_runs_do_not_share_a_registry(tmp_path):
    """p5's counts must be p5's OWN, whether or not p4 ran first in this process.

    This is the exact hazard the extraction introduces: `_wds` is now ONE
    `sys.modules` entry, so a module-global fact list would be shared by all three
    probes and every fresh probe load — p5's header would report p4's figures plus
    its own. Before the extraction this passed by accident (three separate module
    globals re-created on each load); it must now pass by construction.

    Order-independence is asserted rather than a hardcoded count, so the test cannot
    go stale when a probe adds or drops a `Fact` call. Both probes run fully OFFLINE
    on their existing floor-guard fixtures.
    """
    header_only = "EN_CENSUS_METROPOLITAN_AREA\tEN_PROVINCE_TERRITORY\tTOTAL\n"

    def run_p5(dest: Path) -> str:
        mod = _load_probe("p5")
        mod.OUT = dest
        mod._search = lambda: t5._fake_search()
        mod._fetch_csv = lambda url: header_only
        mod.main()
        return dest.read_text(encoding="utf-8")

    def run_p4(dest: Path) -> str:
        mod = _load_probe("p4")
        mod.OUT = dest
        mod._catalogue = lambda: []
        mod._meta_batch = lambda pids: {}
        mod.main()
        return dest.read_text(encoding="utf-8")

    alone = _registered_line(run_p5(tmp_path / "p5_alone.md"))
    p4_text = run_p4(tmp_path / "p4_between.md")
    after = _registered_line(run_p5(tmp_path / "p5_after_p4.md"))

    # Guard against a vacuous pass: both runs must actually have registered figures,
    # otherwise two zero-count headers would compare equal and prove nothing. Parse the
    # COUNT — a bare "is there a nonzero digit" test matches the 5 in p5's own
    # "the base-5 rounding step" and so can never fire.
    def _count(line: str) -> int:
        found = re.search(r"registered (\d+)", line)
        assert found, f"no parseable registered-count in {line!r}"
        return int(found.group(1))

    assert _count(alone) > 0, f"p5 registered nothing: {alone!r}"
    assert _count(_registered_line(p4_text)) > 0, "p4 registered nothing"

    assert after == alone, (
        "p5's provenance header changed because p4 ran first in the same process — the "
        "fact registry is shared across probes. p5 is reporting figures it never wrote."
    )


def test_shared_network_exceptions_did_not_widen():
    """One set now stands behind three gates, so widening it once widens all three.

    A code fault must never launder into `pytest.skip`: the set is exactly the 18
    members p3/p4/p5 already agreed on, and a non-network type stays outside it.
    """
    # Full-set equality, not a length check plus a denylist: a count pins the SIZE, so
    # any member could be swapped for any other string (e.g. SSLEOFError -> OSError)
    # without a red. This is the one set deciding fail-vs-skip for three probes.
    assert NETWORK_EXCEPTIONS == frozenset({
        "URLError", "HTTPError", "ContentTooShortError", "TimeoutError", "timeout",
        "socket.timeout", "gaierror", "herror", "ConnectionError", "ConnectionResetError",
        "ConnectionRefusedError", "ConnectionAbortedError", "RemoteDisconnected",
        "IncompleteRead", "BadStatusLine", "SSLError", "SSLEOFError", "NoResponse",
    }), sorted(NETWORK_EXCEPTIONS)
    for fault in ("KeyError", "IndexError", "ValueError", "JSONDecodeError", "AssertionError"):
        assert fault not in NETWORK_EXCEPTIONS, f"{fault} would excuse a code fault as an outage"
    assert recorded_failure_type("… LIVE PROBE FAILED: KeyError: 'Men+'") == "KeyError"

    # The per-probe UNRESOLVED sets stay SEPARATE — p3's legitimately excludes
    # NOT-FOUND (a recorded not-found is a valid outcome there, spec §11.3), so
    # merging them would break its legitimate-NOT-FOUND branch.
    assert "NOT-FOUND" not in t3.UNRESOLVED and len(t3.UNRESOLVED) == 7
    assert "NOT-FOUND" in t4.UNRESOLVED and "NOT-FOUND" in t5.UNRESOLVED


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_reachability_wrappers_keep_their_http_shape(monkeypatch):
    """The 'same HTTP method as the real call' rule, as a test rather than a docstring.

    p3/p4 MUST stay POST — `getCubeMetadata` rejects GET, so a GET probe reports a
    healthy service as unreachable and every recorded failure launders into a skip
    (already caught once here: with a GET probe, p3's fail-when-reachable branch was
    dead code). p5 MUST stay GET with its Range header and accept 206 as well as 200,
    or a range-honouring host reads as down. `source_reachable` takes the method as a
    parameter precisely so a later 'simplification' cannot flatten the three.
    """
    from . import _probe_asserts

    seen: dict = {}

    def fake_urlopen(req, timeout=None):
        seen.clear()
        seen.update(
            method=req.get_method(),
            url=req.full_url,
            headers=dict(req.header_items()),
            body=req.data,
            timeout=timeout,
        )
        return _FakeResponse(200)

    # `_probe_asserts.urllib.request` IS the global module; monkeypatch undoes it after.
    # Note this asserts the RULE, not the extraction: a wrapper that bypassed
    # `source_reachable` and called urllib itself would still be held to the same shape.
    monkeypatch.setattr(_probe_asserts.urllib.request, "urlopen", fake_urlopen)

    assert t3._source_reachable() is True
    assert seen["method"] == "POST" and seen["url"] == t3.WDS
    assert json.loads(seen["body"]) == [{"productId": t3.LIVENESS_PID}]
    assert seen["headers"].get("Content-type") == "application/json"
    assert seen["timeout"] == t3.REACHABILITY_TIMEOUT == 10

    assert t4._source_reachable() is True
    assert seen["method"] == "POST" and seen["url"] == t4.WDS
    assert json.loads(seen["body"]) == [{"productId": t4.LIVENESS_PID}]
    assert seen["timeout"] == t4.REACHABILITY_TIMEOUT == 10

    assert t5._source_reachable("csv") is True
    assert seen["method"] == "GET" and seen["url"] == t5.CSV_LIVENESS
    assert seen["body"] is None
    assert seen["headers"].get("Range") == "bytes=0-1024"
    assert seen["timeout"] == t5.REACHABILITY_TIMEOUT == 15
    assert t5._source_reachable("ckan") is True and seen["url"] == t5.CKAN_LIVENESS

    # p5 alone accepts 206; p3/p4 accept only 200.
    monkeypatch.setattr(
        _probe_asserts.urllib.request, "urlopen", lambda req, timeout=None: _FakeResponse(206)
    )
    assert t5._source_reachable("csv") is True, "a Range-honouring 206 host is LIVE, not down"
    assert t3._source_reachable() is False
    assert t4._source_reachable() is False


def test_token_parser_is_shared_and_still_refuses_to_launder(tmp_path):
    """The backtick span wins over the greedy line parse, for every probe's gate."""
    text = "- `DECISION-X: UNRESOLVED-PROBE-FAILED` but see the discussion below\n"
    assert token(text, "DECISION-X") == "UNRESOLVED-PROBE-FAILED"
    assert t3._token(text, "DECISION-X") == "UNRESOLVED-PROBE-FAILED"
    assert t4._token(text, "DECISION-X") == "UNRESOLVED-PROBE-FAILED"
    assert t5._token(text, "DECISION-X") == "UNRESOLVED-PROBE-FAILED"
    assert token("no such token here", "DECISION-X") is None
