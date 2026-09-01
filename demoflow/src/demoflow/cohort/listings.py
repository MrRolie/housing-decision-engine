"""Transfer-vs-market split (spec §5): exits carry cause, and `market_listings` is the ONE
entry point that fractions them AND convolves the estate lag — voluntary exits list promptly;
death/estate exits convert to listings with lag L and an eventual-listing fraction (US survey
prior, `borrowed_prior`). Registre foncier mutation counts are the coarse validation check.
This is the supply term `S` that spec §7's excess-demand fraction subtracts.

THE THREE RUN-CONTRACT VALUES BELOW ARE BOUND READ-THROUGH FROM `CENTRAL_ASSUMPTIONS`, and this
module deliberately takes the `demoflow.loaders.constants` import that its `cohort/` siblings
refuse. The siblings' call is right for them and wrong here; the discriminator is WHAT THE VALUE
IS. `decrements.Q_LIVE_BAND` and `gates.RECONCILIATION_BAND` are BAND literals whose anchors live
in `CONSTANTS` — inside `assumptions_hash()`'s payload since the round-3 audit (2026-08-22), which
is why the discriminator is the VALUE's role and not hash coverage: those two modules stay pure
arithmetic (their docstrings record the measured reason: `loaders/validate.py` pulls pandas
transitively) and their literals are pinned test-side against the anchors, same detection, no
coupling — and hashing the ANCHOR now covers the pinned pair transitively. These three are the RUN
CONTRACT ITSELF, read from the dict whose members the run's ED path multiplies directly:
`assumptions_hash()` covers `CENTRAL_ASSUMPTIONS` among its four selections, so a literal here
would move the run's numbers while the hash stayed byte-identical, breaking spec §9's identity.
constants.py states the rule on its own dict — "a second declaration site is a defect".

Test-side pinning CANNOT substitute in this case, which is why the import is taken rather than
avoided: a redeclared literal equal to today's central value passes every equality read.
`tests/test_listings.py` therefore mutates `CENTRAL_ASSUMPTIONS` and RELOADS this module, asserting
the values move — a check only a read-through binding survives. Do not "restore import purity" by
inlining the numbers; that reintroduces the exact defect the reload test exists to kill.

The values and their citations are NOT repeated here — they live in `constants.CENTRAL_ASSUMPTIONS`
and `CENTRAL_PROVENANCE`, with band endpoints in `SWEEP_GRID`. Endpoints enter ONLY the robustness
sweep (rank_stable), never the headline run — and they enter it THROUGH THIS SIGNATURE, which is
what run 33 changed: all three are now parameters, because `phi_voluntary` being the one that was
not is why three declared sweep axes went unevaluated for an entire arc. Band membership is NOT
this function's domain either way, since a hand-worked fixture legitimately passes explicit
off-central params for a pinned example (the plan's boundary fixture does). The guards below are
structural for that reason, never band-tight.

ONE ENTRY POINT, AND THE PER-CAUSE FRACTION ACCESSOR IS DELETED (round-3 elegance audit,
2026-08-22). Spec §7's supply term reads `S = Σ_cause exits(cause)·φ(cause), estate lagged L`,
and `phi_market(cause)` used to serve the φ half alone — with zero non-test callers, reading the
FROZEN module constants above rather than the caller's parameters. That is the run-32 CRITICAL's
own mechanism sitting in a live public function: a Tranche-2 author moving φ through the seam
`balance/excess_demand.py` named would have edited it and moved NOTHING, because the pipeline
passes its φ values as `market_listings` arguments. The lag was the second half of the same trap
— a caller folding a per-cause fraction over causes gets the right decade total and the wrong
year. Both are gone: the φ values are `market_listings` PARAMETERS, defaulting to the
read-through central binding, and the exit-cause VOCABULARY is refused where the causes are
actually mapped (`pipeline._split_exits`, total in both directions).
"""
from demoflow.errors import CalibrationError
from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS

PHI_VOLUNTARY: float = CENTRAL_ASSUMPTIONS["phi_voluntary"]
ESTATE_EVENTUAL_FRACTION: float = CENTRAL_ASSUMPTIONS["estate_eventual_fraction"]
ESTATE_LAG_YEARS: int = CENTRAL_ASSUMPTIONS["estate_lag_years"]


def market_listings(voluntary_by_year: dict[int, float], estate_by_year: dict[int, float],
                    lag: int = ESTATE_LAG_YEARS,
                    eventual_fraction: float = ESTATE_EVENTUAL_FRACTION,
                    phi_voluntary: float = PHI_VOLUNTARY) -> dict[int, float]:
    """listings[t] = voluntary[t]*phi_voluntary + estate[t-lag]*eventual_fraction.

    THE YEAR KEYS ARE THE CALLER'S CONVENTION AND THIS FUNCTION DOES NOT TRANSLATE THEM — it
    convolves the estate lag ON TOP of whatever key it is handed, which is why spec amendment
    #27's end-labelling lands at the producer (`pipeline._exit_landing_year`, applied where the
    roll's exits are keyed) and NOT here. The pipeline hands END LABELS: a flow measured over
    `[y, y+1)` arrives keyed `y+1`, matching the `(t-1, t]` window both demand legs are measured
    over. A second translation inside this body would double-count that offset for every caller,
    including the hand-worked fixture whose whole job is to pin the lag.

    ALL THREE RUN-CONTRACT VALUES ARE PARAMETERS, defaulting to the read-through central
    binding, and `phi_voluntary` became one at run 33 for a measured reason. It was hard-bound
    to the module-level constant INSIDE this body while its two siblings were already
    parameters, so the only way to reach its band endpoints was to mutate `CENTRAL_ASSUMPTIONS`
    and RELOAD this module — which `tests/test_listings.py` does deliberately and a production
    sweep must never do. That asymmetry is why `pipeline._rank_stability` swept ONE of the four
    declared `SWEEP_GRID` axes and shipped `rank_stable: true` as a verdict it had not computed
    (run-32 quant F1 / stress F1, both gates independently). A band endpoint the sweep cannot
    reach through the signature is an axis that silently stops being swept.

    THE DEFAULTS ARE THE BINDING, NEVER A SECOND LITERAL. Each is the module attribute, bound at
    `def` time, so the reload test's mutated dict moves the default path too — the check that a
    redeclared literal here could not survive.

    The three guards are STRUCTURAL and ADDED beyond the plan body (repo precedent:
    `decrements._check_unit`), because every rejected shape is silently wrong rather than loudly
    wrong: a negative lag lands listings BEFORE the deaths that caused them, and a non-integral
    lag lands them on a fractional year key that no annual consumer ever looks up — deleting the
    entire estate leg from the supply term without a trace. NaN falls to the fraction guards by
    the same comparison rule `decrements` relies on (every ordering against NaN is False).
    """
    if not isinstance(lag, int) or lag < 0:
        raise CalibrationError(
            f"estate lag must be a non-negative whole number of years, got {lag!r}")
    if not 0.0 <= eventual_fraction <= 1.0:
        raise CalibrationError(f"eventual_fraction outside [0,1]: {eventual_fraction!r}")
    if not 0.0 <= phi_voluntary <= 1.0:
        raise CalibrationError(f"phi_voluntary outside [0,1]: {phi_voluntary!r}")

    out: dict[int, float] = {}
    for t, v in voluntary_by_year.items():
        out[t] = out.get(t, 0.0) + v * phi_voluntary
    for t, e in estate_by_year.items():
        land = t + lag
        out[land] = out.get(land, 0.0) + e * eventual_fraction
    return out
