"""Reconciliation gate (spec §5 "Reconciliation gate" — the AGGREGATE BACKSTOP half of
Invariant I1). Roll a 75+ owner cohort forward one decade; all-cause retention (survivors
still owning / initial) must land in [0.20, 0.40] — the Myers 0.26-0.31 all-cause envelope
WIDENED. Outside -> CalibrationError.

WHAT THIS GATE IS: a COARSE gross-mortality-double-count backstop, and nothing more. Spec §5
(codex r7-F5) records that a DOUBLED mortality decrement still lands INSIDE this band, and
ruling O corrected the FIGURE upward (spec §5 amendment, 2026-08-08): the blindness is WIDER
than the original ~0.25 reads. Measured on the spec-pinned MTL_RMR cohort, a doubled per-sex
hazard retains 0.3900 / 0.3001 / 0.2293 at q_live 0.06 / 0.085 / 0.11 — in band at EVERY leg
of the q_live axis, with ~0.25 belonging to that axis's HIGH end rather than its low one. The
envelope therefore cannot and does not prove exactly-once. The exactly-once guarantee lives in
the stock-flow equation plus the roll-forward's ORACLE-EXACT mutation test, which asserts the
double-decrement strictly changes the HAND-COMPUTED pinned values. Both together are the
enforcement; neither alone is. Treating a passing band as evidence of exactly-once is the
misreading this paragraph exists to block.

WHAT THIS GATE BINDS — RULING O (spec §5, steering amendment #6, 2026-08-08): the
CENTRAL-ASSUMPTION run ONLY. Sweep legs NEVER re-run `check_reconciliation`. The band's Myers
anchor is a central-case all-cause envelope, so binding every leg makes the spec
self-contradictory: measured at q_live = 0.06 — the sweep grid's OWN low endpoint — the
spec-pinned cohort retains 0.4565 on the CORRECT model (gate RAISES) while a doubled decrement
retains 0.3724 (gate PASSES), inverted at 21/21 start years 2021-2041. Run at sweep scope this
gate would reject the right model and accept the wrong one. The sweep's product is RANK
STABILITY; calibration is the central run's job. (Those two figures are start year 2021, the
spec's unstated one; the same pair at 2035 is 0.4655 / 0.3900 — the row above. The inversion is
21/21 either way.) THE BINDING IS NOT ENFORCEABLE HERE: this module is pure arithmetic with no
notion of which run is calling, so scope is an ORCHESTRATOR obligation — plan Task 29 wires the
call into the central-assumption path only. Recorded at the gate so a later caller cannot
re-derive the wrong scope from a band that looks universal.

COMPOSITION IS A CALLER OBLIGATION THIS GATE CANNOT VERIFY (spec §5, codex r9-F4): retention
is STATE-DEPENDENT, so the band is only well-defined against a PINNED cohort mix — the
household-state + sex mix the INITIALIZATION EQUATIONS produce on the committed vintage for
MTL_RMR, with per-state Solo_m / Solo_f / Couple retention paths additionally pinned in the
oracle fixture. A bare float carries no composition: a caller who rolls a different mix hands
this gate a number the band cannot judge, and the gate has no way to tell. Stated AT the gate
so the obligation stays visible instead of being assumed away by it — it is discharged where
the cohort is built, never here.

SINGLE SOURCE, ENFORCED TEST-SIDE: the band literal is also declared in
`demoflow.loaders.constants` (`CONSTANTS["reconciliation_band"]`, anchored). That module is
deliberately NOT imported here — it pulls pandas transitively via `loaders/validate.py`, and
this module is pure arithmetic (identical call to `decrements.py`). The two sites, and the
band's derivation from the Myers envelope, are bound in tests/test_reconciliation_gate.py, so
a drift in either fails loudly without coupling the cohort layer to the I/O layer.
"""
from demoflow.errors import CalibrationError

RECONCILIATION_BAND = (0.20, 0.40)


def check_reconciliation(retention: float) -> None:
    """Raise CalibrationError unless `retention` lies in the CLOSED band; otherwise return None.

    Signals by RAISING ONLY — never by return value, so no caller can mistake a falsy return
    for a verdict. The chained `lo <= retention <= hi` also refuses NaN (every ordering
    comparison against NaN is False, so the negation fires); the tempting rewrite
    `retention < lo or retention > hi` is False on both disjuncts for NaN and would pass it
    silently. That divergence is pinned by test, not merely noted here.
    """
    lo, hi = RECONCILIATION_BAND
    if not lo <= retention <= hi:
        raise CalibrationError(
            f"decade reconciliation retention {retention:.4f} outside band {RECONCILIATION_BAND}"
        )
