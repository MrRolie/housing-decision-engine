"""Québec-basis guard (spec §2). The engine DEFAULTS to the US RP2014+MP2021
basis; every demoflow entry point sets the QC basis then CHECKS it echoes,
raising BasisError via an explicit if — NEVER a bare assert (stripped under -O)."""
# SEAT-COORDINATED SWAP: becomes `actuarial.compat` when actuarial-system's consumer-first branch merges.
from mcp_server.engine.mortality import active_mortality, get_qx, set_active_mortality

from demoflow.errors import BasisError

QC_BASIS = ("CPM2014_combined", "CPM-B")


def ensure_qc_basis() -> None:
    set_active_mortality(*QC_BASIS)
    if active_mortality() != QC_BASIS:   # if-check, not assert (codex F7)
        raise BasisError(f"active basis {active_mortality()} is not the Québec basis {QC_BASIS}")


def q_at(age: int, gender: str, year: int) -> float:
    """Guarded q_x: ensures the QC basis, then calls get_qx.

    The `min(age, 120)` mirrors the engine's own clamp (`get_qx` does
    `min(max(age, 0), 120)`) — belt-and-braces, not a distinct cap. 120 is the
    engine's SYNTHESIZED terminal age, not the CPM table max.

    MEASURED domain (cpm2014_male/female.csv publish ages 18–115 plus a 120 row;
    values probed live at year 2035): meaningful from age 18 up. BELOW 18 the engine
    returns a SILENT 0.0 — `_load_base` gap-interpolates only BETWEEN published ages,
    so the array keeps its zero fill under the first one, and no error is raised.
    demoflow never enters that range (spec §5 applies the CPM decrement to 75+ only;
    pre-75 mortality is ISQ-embedded and disjoint), but a caller who strays gets a
    zero hazard rather than a raise. Ages 116–119 interpolate between the two 1.0
    rows and then take improvement, measuring 0.968517; age 120 short-circuits to
    exactly 1.0 before any table lookup.

    POINT hazard lookup only: the spec's 100+ ABSORBING-BUCKET semantics (§8 age
    junction) live in the roll-forward, not here.
    """
    ensure_qc_basis()
    return get_qx(min(age, 120), gender, year)
