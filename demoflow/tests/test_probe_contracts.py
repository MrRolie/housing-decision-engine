"""Structural contracts every provenance-carrying probe must satisfy — DISCOVERED BY GLOB.

Everything here enumerates `probes/run_p*.py` and `tests/test_probe_p*.py` at collection
time rather than naming p3/p4/p5. That is the whole point: the next probes (P5b, P6) are
being written by copying an existing probe's call block, so a gate that lists today's
probes by name leaves tomorrow's uncovered exactly when the copy-paste trap fires. A probe
that lacks the shared machinery (p1/p2 — no `_wds` import, no provenance registry) is
skipped by discovery, not by an exclusion list.

Two traps these gates exist to catch, both proven live against the previous commit
(adversarial stress audit, the internal WDS-extraction stress record):

  * Replacing `header = provenance_header(facts, ...)` with a hand-typed list literal
    carrying "This run registered 9 provenance-tagged figures." SURVIVED with 38 passed,
    in run_p5.py — whose `main()` three tests execute. House rule #1 ("a generated
    artifact may not state anything not tied to its computed state") had NO call-site
    enforcement in any probe. The behavioural gates cannot catch it: the anti-contamination
    test compares a count LINE across two runs for order-independence, and a constant is
    perfectly order-independent. So this gate is STATIC — which also covers run_p3.py,
    whose `main()` no test executes at all.

  * A probe copying p5's reachability wrapper (`method="GET"`, Range, 200/206) and pointing
    it at a WDS endpoint. Live-verified: POST-parity probe -> True, copied GET probe ->
    False against the same healthy service. Every recorded failure then launders into
    `pytest.skip` — the cardinal cheap all-clear. Caught here by comparing the wrapper's
    declared method against the method its OWN probe uses for that host.
"""

import ast
import importlib
import inspect
import urllib.parse
from pathlib import Path

import pytest

from . import test_probes_common as common
from ._probe_asserts import source_reachable

PROBES = Path(__file__).resolve().parent.parent / "probes"
TESTS = Path(__file__).resolve().parent

# Names that may be bound to `_wds.post` in a probe (p3/p4 alias it to `_post`); resolved
# from the probe's own import statement, with these as the fallback.
_POST_FALLBACK = frozenset({"post", "_post"})


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports_wds(tree: ast.Module) -> bool:
    return any(isinstance(n, ast.ImportFrom) and n.module == "_wds" for n in ast.walk(tree))


def discover_probes() -> list[str]:
    """Stems of every `probes/run_p*.py` that imports the shared `_wds` machinery."""
    return sorted(
        path.stem.removeprefix("run_")
        for path in PROBES.glob("run_p*.py")
        if _imports_wds(_tree(path))
    )


def discover_wrapper_tests(probe_stems: list[str]) -> list[str]:
    """Stems of every `tests/test_probe_p*.py` that defines a `_source_reachable` wrapper
    AND whose sibling probe carries the shared machinery.

    Gated on the PROBE, not on how the wrapper happens to be written: p2 is excluded
    because run_p2.py has no `_wds` import (it is out of scope by standing ruling, and its
    zero-arg GET wrapper is deliberately its own), while a future probe is covered however
    its wrapper is written — including a hand-rolled urllib one, which the delegation
    assertion below then rejects.
    """
    return sorted(
        stem for path in TESTS.glob("test_probe_p*.py")
        if (stem := path.stem.removeprefix("test_probe_")) in probe_stems
        and any(isinstance(n, ast.FunctionDef) and n.name == "_source_reachable"
                for n in _tree(path).body)
    )


PROBE_STEMS = discover_probes()
WRAPPER_STEMS = discover_wrapper_tests(PROBE_STEMS)


def test_discovery_actually_found_the_probes():
    """A glob-driven gate that discovers NOTHING is the cheap all-clear it exists to stop.

    Every gate below is parametrized over these lists, so an empty list would collect zero
    tests and report green. p1/p2 are legitimately absent (no `_wds` import, no wrapper);
    the floor is the three probes that carry the machinery today.
    """
    assert len(PROBE_STEMS) >= 3, f"discovered only {PROBE_STEMS} under {PROBES}/run_p*.py"
    assert len(WRAPPER_STEMS) >= 3, f"discovered only {WRAPPER_STEMS} under {TESTS}"
    assert "p2" not in PROBE_STEMS, "p2 has no provenance registry; discovery must skip it"
    assert "p2" not in WRAPPER_STEMS, "p2's wrapper is deliberately its own; out of scope"


# ---------------------------------------------------------------------------
# C1 — house rule #1, enforced at the call site, statically.
# ---------------------------------------------------------------------------
def _main_of(stem: str) -> tuple[ast.FunctionDef, ast.Module]:
    tree = _tree(PROBES / f"run_{stem}.py")
    mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert len(mains) == 1, f"run_{stem}.py must define exactly one module-level main()"
    return mains[0], tree


def _note_text_assign(main: ast.FunctionDef) -> ast.Assign | None:
    """The assignment that joins the note's line lists into one string.

    Located by SHAPE (an `<sep>.join(...)` call), not by variable name, so a probe is free
    to name its buffer whatever it likes without silently escaping this gate.
    """
    for node in ast.walk(main):
        if isinstance(node, ast.Assign):
            for sub in ast.walk(node.value):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "join"):
                    return node
    return None


@pytest.mark.parametrize("stem", PROBE_STEMS)
def test_probe_main_routes_its_header_through_provenance_header(stem):
    """The note's provenance header must be COMPUTED, and the computed value must be USED.

    Two halves, because either alone is escapable: calling `provenance_header` and then
    discarding its result for a hand-typed literal would satisfy a call-count check, and a
    reaching check alone would accept any producer.
    """
    main, _ = _main_of(stem)
    calls = [n for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "provenance_header"]
    assert len(calls) == 1, (
        f"run_{stem}.py's main() must build its provenance header with exactly one "
        f"provenance_header(...) call; found {len(calls)}. A hand-typed header literal is a "
        f"claim about this run that nothing computed — house rule #1."
    )
    call = calls[0]

    kwargs = {kw.arg: kw.value for kw in call.keywords}
    written_by = kwargs.get("written_by")
    assert isinstance(written_by, ast.Name) and written_by.id == "_WRITTEN_BY", (
        f"run_{stem}.py passes written_by={ast.dump(written_by) if written_by else None} — it "
        f"must pass the module constant `_WRITTEN_BY`. A filename literal is the field a "
        f"copy-pasted call block carries forward silently, so a probe cloned from another "
        f"would publish its parent's name over its own computed body."
    )

    joined = _note_text_assign(main)
    assert joined is not None, f"run_{stem}.py's main() has no <sep>.join(...) note assembly"
    # The call's value must actually reach the note — either bound to a name that the join
    # references, or inlined into the join itself.
    bound = [t.id for n in ast.walk(main) if isinstance(n, ast.Assign) and n.value is call
             for t in n.targets if isinstance(t, ast.Name)]
    names_in_join = {n.id for n in ast.walk(joined) if isinstance(n, ast.Name)}
    call_inlined = any(sub is call for sub in ast.walk(joined))
    assert call_inlined or (bound and bound[0] in names_in_join), (
        f"run_{stem}.py computes a provenance header but the note text does not use it "
        f"(bound to {bound!r}, join references {sorted(names_in_join)!r}). A computed header "
        f"that is discarded in favour of a literal is the same false claim, one step removed."
    )


@pytest.mark.parametrize("stem", PROBE_STEMS)
def test_probe_declares_its_provenance_prose(stem):
    """Every probe supplies its own header prose, and DERIVES its own filename.

    `_WRITTEN_BY = Path(__file__).name` rather than a literal: the filename is the one
    header field a clone carries forward without a visible error.
    """
    mod = common._load_probe(stem)
    for attr in ("_WRITTEN_BY", "_SCOPE", "_CITED_LABEL"):
        assert isinstance(getattr(mod, attr, None), str), f"run_{stem}.py must define {attr}"
    assert callable(getattr(mod, "_summary", None)), f"run_{stem}.py must define _summary()"
    assert mod._WRITTEN_BY == f"run_{stem}.py", (
        f"run_{stem}.py would attribute its note to {mod._WRITTEN_BY!r}"
    )

    _, tree = _main_of(stem)
    assigns = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "_WRITTEN_BY" for t in n.targets)]
    assert len(assigns) == 1, f"run_{stem}.py must define _WRITTEN_BY exactly once"
    assert not isinstance(assigns[0].value, ast.Constant), (
        f"run_{stem}.py hardcodes _WRITTEN_BY = {ast.literal_eval(assigns[0].value)!r}. Derive "
        f"it (`Path(__file__).name`) so a probe cloned from another cannot inherit its name."
    )


# ---------------------------------------------------------------------------
# C2 — the reachability contract: no inferred method, and the wrapper must match
#      the method its OWN probe uses for that host.
# ---------------------------------------------------------------------------
def test_source_reachable_refuses_to_infer_the_method():
    """`method` must have NO default. A default IS inference.

    The docstring on `source_reachable` records that a GET probe against `getCubeMetadata`
    once made p3's fail-when-reachable branch dead code. Restoring `method: str = "GET"`
    survived the whole suite before this assertion existed, so the rule the docstring states
    was enforced by nothing.
    """
    param = inspect.signature(source_reachable).parameters["method"]
    assert param.default is inspect.Parameter.empty, (
        f"source_reachable(method=...) has default {param.default!r}. A wrapper that omits "
        f"`method=` would silently probe with it, which is the exact failure the docstring "
        f"records as having already happened."
    )
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def _wrapper_call(stem: str) -> ast.Call:
    tree = _tree(TESTS / f"test_probe_{stem}.py")
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_source_reachable")
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "source_reachable"]
    assert len(calls) == 1, (
        f"test_probe_{stem}.py::_source_reachable must delegate to the shared "
        f"source_reachable() exactly once; found {len(calls)}. A hand-rolled urllib call "
        f"escapes every shape rule this contract enforces."
    )
    return calls[0]


def _probe_post_hosts(stem: str) -> set[str]:
    """Hosts the probe reaches by POST, resolved from its own module constants."""
    tree = _tree(PROBES / f"run_{stem}.py")
    post_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "_wds":
            post_names |= {a.asname or a.name for a in node.names if a.name == "post"}
    post_names |= _POST_FALLBACK

    mod = common._load_probe(stem)
    hosts = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in post_names and node.args):
            target = node.args[0]
            if isinstance(target, ast.Name):
                value = getattr(mod, target.id, None)
                if isinstance(value, str):
                    hosts.add(urllib.parse.urlparse(value).netloc)
            elif isinstance(target, ast.Constant) and isinstance(target.value, str):
                hosts.add(urllib.parse.urlparse(target.value).netloc)
    return hosts


@pytest.mark.parametrize("stem", WRAPPER_STEMS)
def test_reachability_wrapper_matches_its_own_probes_method(stem):
    """A liveness probe must use the SAME HTTP method the probe uses for that host.

    This is the copy-paste trap, stated as an invariant rather than a per-probe table: the
    wrapper's declared `method=` is read from its AST, its candidate liveness URLs are
    resolved from the test module, and each URL's host is checked against the set of hosts
    the CORRESPONDING probe reaches by POST. A wrapper cloned from a GET-boundary probe and
    aimed at a POST endpoint reddens here — instead of silently reporting a healthy service
    as unreachable and laundering every recorded failure into a skip.
    """
    call = _wrapper_call(stem)
    kwargs = {kw.arg: kw.value for kw in call.keywords}
    method_node = kwargs.get("method")
    assert isinstance(method_node, ast.Constant) and method_node.value in {"GET", "POST"}, (
        f"test_probe_{stem}.py::_source_reachable must pass an explicit method= literal of "
        f"GET or POST; got {ast.dump(method_node) if method_node else None}."
    )
    method = method_node.value

    test_mod = importlib.import_module(f"{__package__}.test_probe_{stem}")
    url_names = ({n.id for n in ast.walk(call.args[0]) if isinstance(n, ast.Name)}
                 if call.args else set())
    urls = [v for n in url_names if isinstance(v := getattr(test_mod, n, None), str)]
    assert urls, f"test_probe_{stem}.py::_source_reachable resolves no liveness URL constant"

    post_hosts = _probe_post_hosts(stem)
    for url in urls:
        host = urllib.parse.urlparse(url).netloc
        if host in post_hosts:
            assert method == "POST", (
                f"test_probe_{stem}.py probes {host} with {method}, but run_{stem}.py reaches "
                f"that host by POST. A GET liveness check against a POST-only endpoint (e.g. "
                f"getCubeMetadata, which rejects GET) reports a HEALTHY service as unreachable "
                f"— and every recorded failure then launders itself into pytest.skip."
            )
