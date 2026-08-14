"""Transfer-vs-market split (spec §5): exits carry cause; `phi_market(cause)` fractions with
estate-lag convolution — voluntary exits list promptly; death/estate exits convert to listings
with lag L and an eventual-listing fraction (US survey prior, `borrowed_prior`). Registre foncier
mutation counts are the coarse validation check. This is the supply term `S` that spec §7's
excess-demand fraction subtracts.

THE THREE RUN-CONTRACT VALUES BELOW ARE BOUND READ-THROUGH FROM `CENTRAL_ASSUMPTIONS`, and this
module deliberately takes the `demoflow.loaders.constants` import that its `cohort/` siblings
refuse. The siblings' call is right for them and wrong here; the discriminator is WHAT THE VALUE
IS. `decrements.Q_LIVE_BAND` and `gates.RECONCILIATION_BAND` are BAND literals whose anchors live
in `CONSTANTS`, outside `assumptions_hash()`'s payload — so those modules stay pure arithmetic
(their docstrings record the measured reason: `loaders/validate.py` pulls pandas transitively) and
are pinned test-side, same detection, no coupling. These three are the RUN CONTRACT ITSELF:
`assumptions_hash()` covers exactly what `CENTRAL_ASSUMPTIONS` holds, so a literal here would move
the run's numbers while the hash stayed byte-identical, breaking spec §9's artifact identity.
constants.py states the rule on its own dict — "a second declaration site is a defect".

Test-side pinning CANNOT substitute in this case, which is why the import is taken rather than
avoided: a redeclared literal equal to today's central value passes every equality read.
`tests/test_listings.py` therefore mutates `CENTRAL_ASSUMPTIONS` and RELOADS this module, asserting
the values move — a check only a read-through binding survives. Do not "restore import purity" by
inlining the numbers; that reintroduces the exact defect the reload test exists to kill.

The values and their citations are NOT repeated here — they live in `constants.CENTRAL_ASSUMPTIONS`
and `CENTRAL_PROVENANCE`, with band endpoints in `SWEEP_GRID`. Endpoints enter ONLY the robustness
sweep (rank_stable), never the headline run; they are NOT this function's domain, since a
hand-worked fixture legitimately passes explicit off-central params for a pinned example (the
plan's boundary fixture does). The guards below are structural for that reason, never band-tight.

LAG IS NOT IN `phi_market` (caller trap, recorded): `phi_market("estate")` returns the eventual
listing fraction alone. Spec §7's supply term reads `S = Σ_cause exits(cause)·φ_market(cause),
estate lagged L` — the lag is a separate rider on the estate leg. A caller folding `phi_market`
over causes WITHOUT the convolution gets the right total and the wrong year. Use `market_listings`,
which applies both.
"""
from demoflow.errors import CalibrationError
from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS

PHI_VOLUNTARY: float = CENTRAL_ASSUMPTIONS["phi_voluntary"]
ESTATE_EVENTUAL_FRACTION: float = CENTRAL_ASSUMPTIONS["estate_eventual_fraction"]
ESTATE_LAG_YEARS: int = CENTRAL_ASSUMPTIONS["estate_lag_years"]


def phi_market(cause: str) -> float:
    """Market-listing fraction for an exit cause. The estate lag is NOT applied here."""
    if cause == "voluntary":
        return PHI_VOLUNTARY
    if cause == "estate":
        return ESTATE_EVENTUAL_FRACTION
    raise ValueError(f"unknown exit cause: {cause!r}")


def market_listings(voluntary_by_year: dict[int, float], estate_by_year: dict[int, float],
                    lag: int = ESTATE_LAG_YEARS,
                    eventual_fraction: float = ESTATE_EVENTUAL_FRACTION) -> dict[int, float]:
    """listings[t] = voluntary[t]*phi_voluntary + estate[t-lag]*eventual_fraction.

    The two guards are STRUCTURAL and ADDED beyond the plan body (repo precedent:
    `decrements._check_unit`), because both rejected shapes are silently wrong rather than loudly
    wrong: a negative lag lands listings BEFORE the deaths that caused them, and a non-integral
    lag lands them on a fractional year key that no annual consumer ever looks up — deleting the
    entire estate leg from the supply term without a trace. NaN falls to the fraction guard by the
    same comparison rule `decrements` relies on (every ordering against NaN is False).
    """
    if not isinstance(lag, int) or lag < 0:
        raise CalibrationError(
            f"estate lag must be a non-negative whole number of years, got {lag!r}")
    if not 0.0 <= eventual_fraction <= 1.0:
        raise CalibrationError(f"eventual_fraction outside [0,1]: {eventual_fraction!r}")

    out: dict[int, float] = {}
    for t, v in voluntary_by_year.items():
        out[t] = out.get(t, 0.0) + v * PHI_VOLUNTARY
    for t, e in estate_by_year.items():
        land = t + lag
        out[land] = out.get(land, 0.0) + e * eventual_fraction
    return out
