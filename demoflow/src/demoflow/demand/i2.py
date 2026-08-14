"""I2 decomposition + its reconciliation gate (spec §6; codex r5-F3/r7-F3).

`P_resident(t) = P_ISQ(t) − Σ_c SurvivingArrivalCohort_c(t)`. ISQ scenario populations
ALREADY CONTAIN immigrants, so the immigrant channel DECOMPOSES the projected population — it
never adds demand on top — and native formation consumes P_resident ONLY.

TWO CHECKS, and they catch different things (§6 operand binding, codex r6-F1):

  * the DATA-side check is `assert_i2_identity` — the value handed to native formation is the
    one the decomposition produces;
  * the CONSUMER-side check is a PIPELINE mutation (Task 29): with arrivals > 0, feeding
    P_ISQ instead of P_resident changes the emitted demand and fails the integration
    assertion. The identity alone cannot catch a mis-wired consumer, because it holds
    regardless of what native formation reads.

`assert_i2_identity` is DELIBERATELY A DIFFERENT SYMBOL from `cohort.gates.check_reconciliation`
(measured distinct at the run-12 fold): that one is I1's decade all-cause retention band on
the SUPPLY side, binding the central-assumption run only (ruling O); this one is I2's
demand-side double-entry check. Conflating them would put a demand mutation under a gate that
only ever measured mortality.

NON-FINITE IS REFUSED IN BOTH GATES, and that is a correction to the bodies this module was
planned with rather than an extra. Every ordering against NaN is False, so `value < 0.0` and
`abs(native_input − expected) > tol` both evaluate False on a NaN: the plan's two gates would
have CERTIFIED a NaN pipeline, and the NaN then dies quietly downstream inside native
formation's `max(0, ·)`. A gate that greens on the one value it cannot compare is the cheap
all-clear these gates exist to prevent (`demand/formation.py` documents the same class on the
population leg). Spec §4's degenerate policy rules non-finite numeric inputs a raise
everywhere; here the cause is a contradiction between arrival assumptions and the scenario
population, so it raises in this module's own class rather than the loaders'.
"""
import math

from demoflow.errors import CalibrationError

_I2_TOL = 1e-6


def p_resident(p_isq: float, surviving_arrivals: list[float]) -> float:
    """P_ISQ net of the surviving arrival cohorts, per (age, geography, scenario, year).

    Arrival cohorts come from the `compo-*` annual flows and survive forward on the same CPM
    basis — mortality counted once (their post-arrival deaths are ours, their pre-arrival
    dynamics are the flow's).
    """
    return p_isq - sum(surviving_arrivals)


def assert_p_resident_nonneg(value: float, ctx: str) -> float:
    """Per-cell nonnegativity (codex r7-F3): the identity is tautological when P_resident is
    DERIVED from it, so a negative residual base must fail LOUD, never flow into formation.

    Surviving arrivals exceeding P_ISQ in a cell means the arrival-survival assumptions
    CONTRADICT the scenario population — a calibration fault, not a small negative number to
    clamp. Non-finite is refused first, because it cannot be compared at all (see the module
    docstring).
    """
    if not math.isfinite(value):
        raise CalibrationError(
            f"P_resident non-finite at {ctx}: {value} — a NaN/±Inf cell cannot be compared "
            f"against zero (every ordering against NaN is False, so the nonnegativity gate "
            f"would pass it), and it would then vanish inside native formation's max(0, ·)")
    if value < 0.0:
        raise CalibrationError(
            f"P_resident negative at {ctx}: {value} — surviving arrivals exceed P_ISQ "
            f"(assumptions contradict the scenario population)")
    return value


def assert_i2_identity(native_input: float, p_isq: float, surviving_arrivals: list[float]) -> None:
    """native_input must equal P_ISQ − Σ surviving arrivals (feeding total P_ISQ -> fail)."""
    for name, value in (("native_input", native_input), ("p_isq", p_isq),
                        *((f"surviving_arrivals[{i}]", a) for i, a in enumerate(surviving_arrivals))):
        if not math.isfinite(value):
            raise CalibrationError(
                f"I2 double-entry: {name} is non-finite ({value}) — the identity check reads "
                f"as SATISFIED on a NaN (|nan − x| > tol is False), so it is refused instead")
    expected = p_resident(p_isq, surviving_arrivals)
    if abs(native_input - expected) > _I2_TOL + 1e-9 * abs(expected):
        raise CalibrationError(
            f"I2 double-entry: native formation input {native_input} != P_resident {expected} "
            f"(P_ISQ {p_isq} - arrivals {sum(surviving_arrivals)})")
