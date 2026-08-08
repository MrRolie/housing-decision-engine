"""Québec-basis guard contract (spec §2 "Basis contract", §10 "Basis guard tests" codex F7).

The engine holds its active basis in MODULE-LEVEL GLOBALS (`_active_base`/`_active_scale`
in `mcp_server.engine.mortality`, a documented v1 concurrency assumption). Those globals
live in `sys.modules` for the whole pytest process, so basis state LEAKS BETWEEN TESTS.

DIVERGENCE FROM THE PLAN'S TEST BODY (measured, not assumed — plan
docs/plans/2026-07-21-demoflow-tranche1.md Task 17): the plan's guard-path test comments
`# no-op: basis stays US`, but `test_normal_path_sets_qc_basis` runs first in file order
and flips the process global to QC. Stubbing `set_active_mortality` to a no-op then leaves
the basis at QC, `ensure_qc_basis()` sees its echo, and the guard correctly does NOT raise.
Run verbatim, the plan body fails: `Failed: DID NOT RAISE BasisError`.

Spec §10 states the premise the plan body fails to establish — "with `set_active_mortality`
stubbed to a no-op **so `active_mortality()` returns the US basis**". The spec wins: the
`us_basis` autouse fixture FORCES the US pair before every test here via the pinned public
setter (no private reach-in), and restores the prior basis after. This also removes the
vacuity in the normal-path test, which would otherwise pass on inherited QC state even if
`ensure_qc_basis` stopped calling `set_active_mortality` altogether.
"""

import subprocess
import sys

import pytest

from demoflow.cohort import basis as B
from demoflow.errors import BasisError

# SEAT-COORDINATED SWAP: becomes `actuarial.compat` when actuarial-system's consumer-first branch merges.
from mcp_server.engine.mortality import active_mortality, set_active_mortality

US_BASIS = ("RP2014_combined", "MP2021")  # the engine's documented default pair


@pytest.fixture(autouse=True)
def us_basis():
    """Force the engine's US default before each test; restore the prior basis after.

    Setup is the load-bearing half: it makes both the normal path and the guard path
    order-independent and non-vacuous. Teardown keeps this module from leaking QC state
    into the rest of the suite.
    """
    previous = active_mortality()
    set_active_mortality(*US_BASIS)
    assert active_mortality() == US_BASIS, "fixture failed to establish the US basis"
    yield
    set_active_mortality(*previous)


def test_normal_path_sets_qc_basis():
    # US default before set is EXPECTED, not an error; after ensure it echoes QC.
    assert active_mortality() == US_BASIS  # premise, per spec §10(a)
    B.ensure_qc_basis()
    assert active_mortality() == ("CPM2014_combined", "CPM-B")


def test_guard_raises_when_basis_not_qc_and_get_qx_never_called(monkeypatch):
    calls = {"get_qx": 0}
    monkeypatch.setattr(B, "set_active_mortality", lambda *a, **k: None)  # no-op: basis stays US
    monkeypatch.setattr(B, "get_qx", lambda *a, **k: calls.__setitem__("get_qx", calls["get_qx"] + 1))
    assert active_mortality() == US_BASIS  # premise the plan body assumed but never established
    with pytest.raises(BasisError):
        B.q_at(75, "M", 2035)
    assert calls["get_qx"] == 0  # guard raised BEFORE any get_qx


def test_guard_survives_dash_O():
    # -O strips asserts; the if-check must still raise. Run in a subprocess under -O.
    # Hermetic by construction: a fresh interpreter starts at the engine's US default.
    #
    # The get_qx sentinel is ADDED beyond the plan's body: spec §10(b) requires BOTH
    # halves — "BasisError is raised AND get_qx is never called — verified under
    # python -O too" — and the plan's script only checked the raise. The two asserts
    # are kept PAIRED: a lone "not in" check would pass vacuously if the script died
    # early, so the positive BASISERROR_OK assert is what makes it non-vacuous.
    script = (
        "import demoflow.cohort.basis as B;"
        "B.set_active_mortality=lambda *a,**k:None;"  # no-op keeps US basis
        "B.get_qx=lambda *a,**k:print('GET_QX_CALLED');"
        "from demoflow.errors import BasisError\n"
        "try:\n"
        "    B.q_at(75,'M',2035); raise SystemExit('NO RAISE')\n"
        "except BasisError:\n"
        "    print('BASISERROR_OK')\n"
    )
    r = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True, text=True)
    assert "BASISERROR_OK" in r.stdout, (r.stdout, r.stderr)
    assert "GET_QX_CALLED" not in r.stdout, (r.stdout, r.stderr)


def test_q_at_returns_quebec_oracle_values():
    """ADDED beyond the plan's three bodies: the guard tests prove the guard FIRES, but
    nothing proves `q_at` returns QUÉBEC hazards. Charter oracle (quadruple-checked):
    M75 0.0156 / F75 0.0115 / M100 0.3534 — pinned here to calendar year 2035, which this
    task MEASURED live as the year reproducing all three (the charter carry stated the
    values without the year). Tolerance, not equality: the engine returns 0.015604.

    Discriminating: entering with the US basis forced by the fixture, these pass ONLY if
    `q_at` flips the basis itself. On the US pair the same points are M75 0.042830 /
    F75 0.026611 / M100 0.349234 — all outside tolerance, M75 by ~27 basis points.
    """
    assert active_mortality() == US_BASIS  # enter on the WRONG basis on purpose
    assert B.q_at(75, "M", 2035) == pytest.approx(0.0156, abs=5e-5)
    assert B.q_at(75, "F", 2035) == pytest.approx(0.0115, abs=5e-5)
    assert B.q_at(100, "M", 2035) == pytest.approx(0.3534, abs=5e-5)
    assert active_mortality() == ("CPM2014_combined", "CPM-B")  # and it left the basis QC
