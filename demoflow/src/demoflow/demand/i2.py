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
    """Nonnegativity of the P_resident value it is HANDED (codex r7-F3): the identity is
    tautological when P_resident is DERIVED from it, so a negative residual base must fail LOUD,
    never flow into formation.

    IT IS THE TOTAL, NOT THE CELL. This docstring read "Per-cell nonnegativity" and spec §6 says
    the property is "asserted per cell"; codex r12-F1 measured what the code does. The function
    takes a SCALAR and has ONE production call site — `pipeline`'s `resident()`, which hands it
    the (geography, scenario, year) TOTAL, 27 evaluations per geography-scenario against 2,727
    per-age cells, and no call context carries an age. The per-age operand is UNREPRESENTABLE on
    the Tranche-1 path: `_surviving_arrivals` returns a flat list of year flows with no age index,
    so there is no per-age arrivals term to subtract from P_ISQ(a). THE PER-CELL PROPERTY STILL
    HOLDS, by composition rather than by this gate, and this gate is one of its two factors:
    every emitted cell is `P_ISQ(a) × (value / P_ISQ_total)`, so refusing a negative `value`
    here is exactly what keeps that scale nonneg while the loader keeps `P_ISQ(a)` nonneg.
    `demand/formation.py` states the composition at the consumer that depends on it; the binding
    test is `tests/test_pipeline.py`'s per-age operand test. A spec amendment is proposed for
    §6's "per cell" wording — the tree must not carry the claim in the meantime.

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
