"""Import-direction contract: demoflow ⊥ hde, BOTH ways.

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
