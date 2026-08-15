"""Import-direction contracts: demoflow ⊥ hde BOTH ways, and the INTERNAL layering.

The spec-mandated half is demoflow ⊥ hde. The second half was missing entirely until Task
25b: nothing bound the model packages (`cohort/`, `demand/`) against the loader package,
even though §6's operand binding is exactly a statement about reach — "native formation's
ONLY population parameter is P_resident by construction (single code path, no access to
P_ISQ)". `test_demand.py` grepped ONE file for ONE loader; this generalises it to both model
trees and every data-acquiring loader, which is what makes it hold for the modules 25b, 26
and 29 add rather than for the one that existed when it was written.

Spec §2 "Placement & dependency topology" → bullet "Import rules (both directions,
test-enforced)"; mandated as a contract test by §10 "Testing" → "Contract tests:
... import-direction tests (demoflow⊥hde both ways)".

The spec's rule is symmetric: `hde` and hde's `mcp_server` never import `demoflow`;
`demoflow` never imports `hde` or hde's `mcp_server`. Coupling is the ScenarioPrior
artifact file only.

`mcp_server` in `sys.modules` is EXPECTED and allowed: in demoflow's env that name resolves
to **actuarial-system's** distribution (uv path dep), never to the HDE repo root's own
`mcp_server/` package — the two never share an environment. So the source-grep contract
forbids `hde` specifically, and the mortality-import test PINS THE PROVENANCE of
`mcp_server` rather than merely asserting the import succeeds: hde's `mcp_server` lacks an
`engine/` subpackage today, so a bare success check would silently start passing against
the wrong package the day someone adds one.
"""

import re
import subprocess
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "demoflow"
REPO_ROOT = Path(__file__).resolve().parents[2]
HDE_SRC = REPO_ROOT / "src" / "hde"
HDE_MCP = REPO_ROOT / "mcp_server"

FORBIDDEN = re.compile(r"^\s*(?:import\s+hde\b|from\s+hde\b)", re.MULTILINE)
FORBIDDEN_DEMOFLOW = re.compile(
    r"^\s*(?:import\s+demoflow\b|from\s+demoflow\b)", re.MULTILINE
)


def _scan(tree: Path, pattern: re.Pattern[str]) -> list[str]:
    """Return files under `tree` matching `pattern`, FAILING LOUD on an unusable tree.

    ADDED beyond the plan's body (absence discipline): a missing or mistyped tree makes
    `rglob` yield nothing and the caller's `assert not offenders` pass vacuously — a check
    that cannot fail is not a check. Both preconditions are asserted before the scan.
    """
    assert tree.is_dir(), f"scan target missing — check would pass vacuously: {tree}"
    files = sorted(tree.rglob("*.py"))
    assert files, f"no .py files under {tree} — check would pass vacuously"
    return [str(p) for p in files if pattern.search(p.read_text())]


def test_public_api_does_not_pull_in_hde():
    # Fresh interpreter: importing demoflow's public API must not import hde.
    code = "import demoflow; import sys; assert 'hde' not in sys.modules, sorted(m for m in sys.modules if m=='hde')"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_source_file_imports_hde():
    offenders = _scan(SRC, FORBIDDEN)
    assert not offenders, f"demoflow source imports hde (forbidden): {offenders}"


def test_hde_source_does_not_import_demoflow():
    """The OTHER direction of the spec's symmetric rule (ADDED beyond the plan's three
    bodies, which only covered demoflow→hde while the task title says "both ways"):
    hde's shipped packages — `src/hde` and the repo-root `mcp_server` — never import
    demoflow. Read-only walk of the HDE tree; nothing outside `demoflow/**` is written."""
    offenders = _scan(HDE_SRC, FORBIDDEN_DEMOFLOW) + _scan(HDE_MCP, FORBIDDEN_DEMOFLOW)
    assert not offenders, f"hde source imports demoflow (forbidden): {offenders}"


# ------------------------------------------------- the INTERNAL layering (added at Task 25b)

# `cohort/` and `demand/` are pure model arithmetic. They may reach the loader package's two
# PURE leaves and nothing else: `validate` (the shared assertion contracts) and `constants`
# (the run contract + anchors, whose single-declaration rule REQUIRES consumers to read it).
# Every other loaders module ACQUIRES data — workbooks, WDS responses, pinned files — and a
# model module reaching one is how §6's operand binding gets broken quietly: an equation that
# can open the population workbook can read P_ISQ where it was ruled to read P_resident.
# `balance/` ADDED at Task 26. The docstring above claims this gate holds "for the modules
# 25b, 26 and 29 add" — true only for modules landing INSIDE the two trees named when it was
# written. Task 26 lands a THIRD model package, so without this entry the newest equations in
# the tree — the ED numerator's denominator and the fraction itself — were the only model code
# free to import a data-acquiring loader. A tree, not a module, is the unit that must be
# enrolled here, and enrolling it is what keeps the docstring's claim true.
MODEL_TREES = (SRC / "cohort", SRC / "demand", SRC / "balance")
LOADERS_ALLOWED_IN_MODEL = frozenset({"constants", "validate"})

# The `from` form covers BOTH spellings of the same import in one branch — `demoflow.loaders`
# and any relative depth (`..loaders` from a model module, `...loaders` from a model
# subpackage). Two capture groups TOTAL, deliberately: `_loader_imports` reads group(1) or
# group(2), so a third alternation with its own group would silently map its submodule to the
# package-level marker instead. `import ..loaders` needs no branch — Python has no relative
# `import` statement, only relative `from`.
_LOADER_IMPORT = re.compile(
    r"^\s*(?:from\s+(?:demoflow\.|\.+)loaders(?:\.([A-Za-z_]\w*))?\s+import"
    r"|import\s+demoflow\.loaders(?:\.([A-Za-z_]\w*))?)",
    re.MULTILINE,
)


def _loader_imports(text: str) -> set[str]:
    """Loader submodules a source text imports. `""` marks a PACKAGE-level import
    (`from demoflow.loaders import x`), which is never allowed here: it reaches whatever the
    package exposes, so an allowlist keyed on the submodule name cannot rule on it.

    STATED RESIDUAL, because a source grep rules on the spellings it enumerates and honesty
    about the edge is the gate's own doctrine: a DYNAMIC reach —
    `importlib.import_module("demoflow.loaders.isq")` — is invisible here, and no grep closes
    it. It is left named rather than chased. `from demoflow import loaders` is likewise
    unmatched and is left so knowingly: `loaders/__init__.py` is EMPTY, so that form binds no
    submodule on its own — reaching one still needs a spelling this pattern does catch.
    """
    return {(m.group(1) or m.group(2) or "") for m in _LOADER_IMPORT.finditer(text)}


def test_the_layering_gate_can_actually_fail():
    """The mutation proof, on synthetic sources — the tree is CLEAN today, so without this the
    gate below is indistinguishable from a check that cannot fire."""
    assert _loader_imports("from demoflow.loaders.isq import load_population\n") == {"isq"}
    assert _loader_imports("import demoflow.loaders.census\n") == {"census"}
    assert _loader_imports("from demoflow.loaders import compo\n") == {""}
    assert _loader_imports("from demoflow.loaders.validate import assert_fraction\n") == {"validate"}
    assert _loader_imports("from demoflow.errors import LoaderError\n") == set()
    # The RELATIVE spelling is the same import — an absolute-only parser is a gate that reads
    # one of two ordinary forms, and the form it missed is live repo idiom (this file's own
    # suite uses `from ._probe_asserts import token`). Measured 2026-08-14: before this branch
    # existed, `from ..loaders.isq import load_population` in `demand/i2.py` passed the whole
    # 540-test suite. Depth is `\.+`, not two dots: a model SUBpackage would need three.
    assert _loader_imports("from ..loaders.isq import load_population\n") == {"isq"}
    assert _loader_imports("from ..loaders import compo\n") == {""}
    assert _loader_imports("from ...loaders.census import load_ownership\n") == {"census"}
    assert _loader_imports("from ..loaders.validate import assert_fraction\n") == {"validate"}
    assert _loader_imports("from ..errors import LoaderError\n") == set()
    for offending in ("isq", "census", "compo", "ircc", "living_arrangement", "pins", ""):
        assert offending not in LOADERS_ALLOWED_IN_MODEL


def test_model_packages_reach_only_the_pure_loader_leaves():
    for tree in MODEL_TREES:
        assert tree.is_dir(), f"scan target missing — check would pass vacuously: {tree}"
        files = sorted(tree.rglob("*.py"))
        assert files, f"no .py files under {tree} — check would pass vacuously"
        for path in files:
            reached = _loader_imports(path.read_text())
            assert reached <= LOADERS_ALLOWED_IN_MODEL, (
                f"{path} imports demoflow.loaders.{sorted(reached - LOADERS_ALLOWED_IN_MODEL)} — "
                f"model packages may reach only {sorted(LOADERS_ALLOWED_IN_MODEL)}; a data-"
                f"acquiring loader inside the demand equation is how §6's operand binding "
                f"(P_resident, never P_ISQ) breaks without a visible call-site change")


def test_the_public_api_stays_pandas_free():
    """A real property, measured rather than aspired to: `import demoflow` pulls no pandas.

    SCOPED HONESTLY — it binds the PUBLIC API surface, not every submodule. `demoflow.demand
    .formation` DOES pull pandas transitively, because `loaders.validate` (an allowed leaf)
    imports it for its frame-shaped gates. So this pins what the package's own `__init__`
    costs a consumer, and the layering gate above — not this one — is what keeps the model
    trees off the data-acquiring loaders.
    """
    code = "import demoflow, sys; assert 'pandas' not in sys.modules, 'demoflow pulled pandas'"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # the scope statement above, asserted rather than asserted-about: the submodule DOES.
    probe = "import demoflow.demand.formation, sys; print('pandas' in sys.modules)"
    r2 = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert r2.stdout.strip() == "True", (
        "demand.formation no longer pulls pandas — the docstring's scope caveat is now stale, "
        "and the public-API claim above may be strengthenable")


def test_actuarial_mcp_server_import_is_allowed():
    # This resolves to actuarial-system's mcp_server, NOT hde's — must succeed.
    # SEAT-COORDINATED SWAP: becomes `actuarial.compat` when actuarial-system's consumer-first branch merges.
    from mcp_server.engine.mortality import get_qx  # noqa: F401

    # Provenance, not just success: prove WHICH mcp_server answered.
    resolved = Path(sys.modules["mcp_server"].__file__).resolve()
    assert HDE_MCP not in resolved.parents, f"resolved to hde's mcp_server: {resolved}"
    owners = packages_distributions().get("mcp_server")
    assert owners == ["actuarial-system"], (
        f"mcp_server is not unambiguously owned by actuarial-system in this env: {owners}"
    )
