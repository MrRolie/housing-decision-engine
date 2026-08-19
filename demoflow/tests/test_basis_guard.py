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

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from demoflow.cohort import basis as B
from demoflow.errors import BasisError

# SEAT-COORDINATED SWAP: becomes `actuarial.compat` when actuarial-system's consumer-first branch merges.
from mcp_server.engine import mortality
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


# ------------------------------------------- the basis DIGEST (data-gate finding F1, run 32)
#
# THE BASIS WAS OUTSIDE ARTIFACT IDENTITY. `basis.py` pins the two basis IDENTIFIERS and
# nothing about the TABLE CONTENT; the CSVs live outside this repo behind a uv path dep with
# no digest (`uv.lock`: `source = { directory = "../../actuarial-system" }`), and
# `pipeline._source_hashes` ranges over files under `data_dir` only. So two runs over
# DIFFERENT upstream mortality tables emitted DIFFERENT `rankings.json` bytes under a
# BYTE-IDENTICAL envelope, and `test_golden.py`'s attribution table then routed the operator
# to hunt a code defect that does not exist. These tests pin the digest that closes it.

def test_the_basis_digest_is_a_64_hex_sha256_and_deterministic():
    """Two reads of one basis agree — the digest identifies the surface, never the moment."""
    first = B.basis_digest()
    assert re.fullmatch(r"[0-9a-f]{64}", first), first
    assert B.basis_digest() == first


def test_the_basis_digest_leaves_the_basis_on_the_quebec_pair():
    """It goes through the SAME guarded surface every q lookup does, so it cannot read one
    basis while the model reads another — entering on the US pair (the fixture) it returns
    the QUÉBEC digest and leaves the engine on the Québec basis."""
    assert active_mortality() == US_BASIS          # enter on the WRONG basis on purpose
    B.basis_digest()
    assert active_mortality() == ("CPM2014_combined", "CPM-B")


def test_the_basis_digest_moves_when_the_upstream_table_content_moves(monkeypatch):
    """THE DISCRIMINATION THE ENVELOPE COULD NOT MAKE: re-point `CPM2014_combined` at the
    package's own `cpm2014_public_*` pair — the shape of actuarial-system re-publishing the
    combined tables — and the digest MOVES while both basis IDENTIFIERS stay put.

    The private reach-in is the data gate's own prescription ("prescribe a pytest that swaps
    `_BASE_TABLES` and asserts the emitted identity MOVES") and it is confined to this test:
    spec §2 forbids it in the model path, which is why `basis_digest` computes through the
    public `q_at` surface and not off `mortality._DATA_DIR`. `_base_cache` is swapped for a
    fresh dict in the same breath — without it the already-loaded arrays answer and the test
    passes vacuously; monkeypatch restores both.
    """
    before = B.basis_digest()
    monkeypatch.setattr(mortality, "_base_cache", {})
    monkeypatch.setitem(mortality._BASE_TABLES, "CPM2014_combined",
                        ("cpm2014_public_male.csv", "cpm2014_public_female.csv", 2014))
    after = B.basis_digest()
    assert active_mortality() == ("CPM2014_combined", "CPM-B")   # identifiers UNCHANGED
    assert after != before, (
        "the digest is blind to table CONTENT — the envelope cannot distinguish two runs over "
        "different upstream mortality tables, which is the finding it exists to close")


def test_the_basis_digest_grid_brackets_the_surface_the_model_consumes():
    """A digest over a NARROWER grid than the run reads would miss the change it exists to
    catch, so the AGE axis is bound to the model's own constants rather than to a literal.

    The run's q consumption is TWO call sites: the lumped 75+ bucket rolled at
    `pipeline.ROLL_AGE` over every population-lattice year, and the ruling-O reconciliation
    cohort rolled a decade from `BAND_ENTRY_AGE`. Both bind here without I/O.

    THE POPULATION-LATTICE YEARS DO NOT, and that is why they are not asserted in this file.
    They come from the ISQ frame, not from any constant, so the only thing a unit test can
    write here is the grid's own literal compared against itself — an assertion that fires
    when the GRID narrows and stays green when CONSUMPTION widens past it, which is the
    direction that ships the defect ("under-covering ships a moved table under an unchanged
    envelope"). The year axis is measured instead against the recorded consumption of a real
    run, in `tests/test_pipeline.py`
    (`test_the_basis_digest_grid_covers_the_q_surface_the_run_actually_reads`), which closes
    both directions on all three axes.
    """
    from demoflow.cohort.rollforward import BAND_ENTRY_AGE
    from demoflow.pipeline import RECONCILIATION_COHORT, ROLL_AGE

    _geo, _scen, recon_start, recon_age = RECONCILIATION_COHORT
    ages, years = set(B.BASIS_DIGEST_AGES), set(B.BASIS_DIGEST_YEARS)
    assert set(B.BASIS_DIGEST_GENDERS) == {"M", "F"}          # couples decrement per sex
    assert ROLL_AGE in ages
    assert set(range(BAND_ENTRY_AGE, 101)) <= ages            # the whole modeled band
    assert set(range(recon_age, recon_age + 10)) <= ages      # the decade roll's ages
    assert set(range(recon_start, recon_start + 10)) <= years  # ruling O's decade, a constant


def test_the_basis_digest_reaches_no_private_engine_surface():
    """Spec §2 forbids the private reach-in, and the cheap version of this digest is exactly
    one: hash the CSVs off `mortality._DATA_DIR`. Read on the module's own AST rather than on
    its text — `q_at`'s docstring legitimately NAMES `_load_base` when it explains the engine's
    silent-zero below age 18, and a text grep cannot tell a citation from a reach-in."""
    tree = ast.parse(Path(B.__file__).read_text(encoding="utf-8"))
    imported = [(node.module, alias.name) for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) for alias in node.names]
    reached = [node.attr for node in ast.walk(tree)
               if isinstance(node, ast.Attribute) and node.attr.startswith("_")]
    engine_private = [(mod, name) for mod, name in imported
                      if (mod or "").startswith("mcp_server") and name.startswith("_")]
    assert not engine_private, (
        f"cohort/basis.py imports the engine's private {engine_private} — spec §2 admits the "
        f"public surface only, which is why the digest is taken over the q SURFACE")
    assert not reached, f"cohort/basis.py reaches private attributes {reached}"


# THIRD, TEST-OWNED copy of the basis digest — the same device `tests/test_golden.py` uses for
# the required-indicator names, and here it does one job the golden cannot. A re-published
# upstream table reds the golden, whose remedy line says "re-mint"; re-minting alone would ship
# a FRESH digest under the STALE `pipeline.BASIS_RECORDED_AT`, which is precisely the
# date-describes-a-different-object defect the data gate raised one field over. This literal
# makes the date's staleness a red with an instruction rather than a silent pairing.
_BASIS_DIGEST_AT_DECLARATION = "d15e1f52318413016d1cc3229a5a2c85306fe922010be52e132dc8fbba830cea"


def test_the_declared_recording_date_still_describes_this_basis():
    """Measured 2026-08-19 on actuarial-system's committed CPM2014 + CPM-B tables."""
    from demoflow.pipeline import BASIS_RECORDED_AT

    assert B.basis_digest() == _BASIS_DIGEST_AT_DECLARATION, (
        f"the CPM basis surface MOVED — actuarial-system re-published, or the engine's "
        f"interpolation changed. That is a legitimate re-mint, NOT a refusal: update this pin "
        f"AND `pipeline.BASIS_RECORDED_AT` (declared {BASIS_RECORDED_AT}) in the SAME commit as "
        f"the golden re-mint, so the envelope's date and its digest keep describing one object")
