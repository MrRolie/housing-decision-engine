"""The ED→prior mapping (spec §7(a), Tranche 2) — the DANGER-ZONE module, isolated and
version-stamped. This module is the SINGLE derivation path for every drift and tilt value the
ScenarioPrior artifact carries (the emitter tests origin-assert it); nothing else in the tree
may multiply an ED by a beta.

UNITS ARE PINNED HERE AND NOWHERE ELSE (codex r3-F7 — the ambiguity was worth 100x). ED carries
units of yr^-1 (amendment #12; `balance/excess_demand.py` states the composition), beta is
DIMENSIONLESS, and demo_drift comes out in DECIMAL REAL drift per year — so a unit ED maps to
beta-units of decimal/yr per yr^-1 and the worked fixture closes dimensional analysis:
    ED = 0.01 yr^-1, beta = 2.0  ->  demo_drift = 0.02 decimal/yr = 2%/yr real.

V0 FORM IS LINEAR THROUGH THE ORIGIN: `demo_drift = beta x ED`, with beta ~ Uniform[1.0, 4.0].
Zero intercept BY CONSTRUCTION (no demographic tilt at flow balance); any knots/saturation or a
non-uniform beta prior is a future decision made WITH the consumer, never improvised here.

CLOSED-FORM QUANTILES over the uniform beta: the CDF inverse of Uniform[a, b] is
q(p) = a + p (b - a), so
    q10 = 1.0 + 0.1 x 3.0 = 1.3        q90 = 1.0 + 0.9 x 3.0 = 3.7        mean = 2.5
and because the map is LINEAR and MONOTONE INCREASING in beta, the drift quantiles are the
beta quantiles x ED — REVERSED for ED < 0 (multiplying by a negative constant reverses order,
so p10 must stay the SMALL drift): for ed >= 0, p10 = q10 x ed and p90 = q90 x ed; for ed < 0,
p10 = q90 x ed and p90 = q10 x ed; mean is always 2.5 x ed. The band spans include the FULL
beta uncertainty, never just the input scenarios. Worked numbers at ED = 0.01 yr^-1:
    mean = 0.025, p10 = 0.013, p90 = 0.037   (all decimal/yr real)
and at ED = -0.01: mean = -0.025, p10 = -0.037, p90 = -0.013 — band order p10 <= mean <= p90
holds on BOTH sides, which is what §7(a)'s contract test demands of every emitted row.

THE TILT IS NEUTRAL IN V0, AND THAT IS A DECLARED RESIDUAL, NOT AN OVERSIGHT. Spec §13 names
the ED -> drawdown_weight_tilt mapping as a contract debt ("currently unspecified; the beta rule
determines drift only"), and the S4b input-slot sketch that unblocked this build did not resolve
it either. A tilt multiplies S4b's OWN shock hazard with 1.0 = neutral, so the identity element
is the one value that composes into no behavior change — inventing a slope nobody ruled would be
exactly the unvalidated model this module exists to refuse. Consequence, stated where the
contract lives: no emitted row carries `never_relax_stress` today (that flag rides every row
whose tilt < 1.0, and none does), and the flag's enforcement lives at the row validator + RED
fixtures so it arms the day a real tilt rule lands under a version bump.

THE VERSION PIN IS THE ENFORCEMENT, NOT THE CONVENTION. `MAPPING_VERSION` alone would be a
comment; the pin below fingerprints EVERY parameter this module computes from (beta endpoints,
quantile positions, the tilt rule token) and `check_mapping_version` refuses to produce a value
unless the live fingerprint is registered EXACTLY under the declared version. Editing a bound
without bumping the version reds every emitter call; bumping means registering the new
fingerprint under the new version in the same PR-visible diff — which is spec §7(a)'s "changing
the mapping without a version bump fails a test", implemented as a runtime refusal rather than a
test someone has to remember to write.
"""
import hashlib
import json
import math

from demoflow.errors import CalibrationError

# The version STAMPED INTO every artifact row's envelope (spec §7(a)). Bump on any change to
# anything `_mapping_params` returns.
MAPPING_VERSION = "1"

# beta ~ Uniform[BETA_LOW, BETA_HIGH], dimensionless (spec §7(a), codex r6-F5: an interval
# alone leaves quantiles undefined — the UNIFORM distribution is part of the pinned contract).
BETA_LOW = 1.0
BETA_HIGH = 4.0

# Drift-band quantile positions. 0.1/0.9 are §7(a)'s own p10/p90 labels; they are parameters
# here, not literals at the use site, so widening the band is a fingerprinted decision.
P10_POSITION = 0.1
P90_POSITION = 0.9

# Derived beta quantiles — CLOSED FORM from the uniform (see module docstring). Exposed as
# constants because the worked fixtures and the emitter tests read them directly.
BETA_Q10 = BETA_LOW + P10_POSITION * (BETA_HIGH - BETA_LOW)      # 1.3
BETA_Q90 = BETA_LOW + P90_POSITION * (BETA_HIGH - BETA_LOW)      # 3.7
BETA_MEAN = (BETA_LOW + BETA_HIGH) / 2.0                          # 2.5

# V0 tilt: the multiplicative IDENTITY (see the docstring ruling above). Part of the
# fingerprint, so replacing it is impossible without a version bump.
TILT_RULE_V0_NEUTRAL = "neutral_identity_v0"


def _mapping_params() -> dict:
    """EVERY parameter this module computes from — the fingerprint's whole subject. A new
    parameter belongs here FIRST and in a producer SECOND; the reverse order ships an unpinned
    degree of freedom."""
    return {
        "beta_low": BETA_LOW,
        "beta_high": BETA_HIGH,
        "p10_position": P10_POSITION,
        "p90_position": P90_POSITION,
        "tilt_rule": TILT_RULE_V0_NEUTRAL,
    }


def mapping_fingerprint() -> str:
    """sha256 over the canonical JSON of `_mapping_params()` — the mapping's content identity."""
    return hashlib.sha256(
        json.dumps(_mapping_params(), sort_keys=True).encode("utf-8")).hexdigest()


# MAPPING_VERSION -> the fingerprint that version declares. ONE entry per shipped mapping; a
# bump adds a row and never edits an old one (an old artifact's mapping_version must keep
# resolving to the mapping that produced it).
_VERSION_PINNED_FINGERPRINTS = {
    # v1: the Tranche-2 build itself — linear-through-origin, Uniform[1.0, 4.0] beta,
    # p10/p90 at 0.1/0.9, neutral tilt (see TILT_RULE_V0_NEUTRAL).
    "1": "ddc1e435378dd57af9521b899f08ab837d8a1eb2235319c9bd43845d842efa4f",
}


def check_mapping_version() -> None:
    """Refuse to produce a mapped value unless the LIVE parameter set is exactly what
    `MAPPING_VERSION` declares. Called by every public producer, so there is no code path that
    maps an ED past an unstamped change."""
    pinned = _VERSION_PINNED_FINGERPRINTS.get(MAPPING_VERSION)
    live = mapping_fingerprint()
    if pinned is None:
        raise CalibrationError(
            f"mapping_version {MAPPING_VERSION!r} has NO registered fingerprint — register the "
            f"new mapping's fingerprint under the bumped version in "
            f"_VERSION_PINNED_FINGERPRINTS (live fingerprint {live})")
    if pinned != live:
        raise CalibrationError(
            f"the ED→prior mapping changed (live fingerprint {live}) but mapping_version is "
            f"still {MAPPING_VERSION!r} (pinned {pinned}) — bump MAPPING_VERSION and register "
            f"the new fingerprint; changing the mapping without a version bump fails per "
            f"spec §7(a)")


def _finite_ed(ed: float) -> float:
    if not math.isfinite(ed):
        raise CalibrationError(
            f"ED is {ed!r} — not finite; the mapping refuses it here rather than letting a NaN "
            "band reach the emitter's allow_nan=False gate with no cause left to name")
    return float(ed)


def demo_drift_prior(ed: float) -> tuple[float, float, float]:
    """`(mean, p10, p90)` of demo_drift for one excess-demand rate — LINEAR THROUGH THE ORIGIN
    with closed-form quantiles (module docstring carries the derivation and the worked ED=0.01
    fixture). Sign-reversal for ED < 0 keeps `p10 <= mean <= p90` on BOTH sides, which is the
    shape §7(a) contract-tests on every row."""
    check_mapping_version()
    ed = _finite_ed(ed)
    lo_q, hi_q = BETA_Q10 * ed, BETA_Q90 * ed
    if ed >= 0.0:
        return (BETA_MEAN * ed, lo_q, hi_q)
    return (BETA_MEAN * ed, hi_q, lo_q)


def drawdown_weight_tilt(ed: float) -> float:
    """The drawdown_weight_tilt for one excess-demand rate — V0: identically 1.0 (neutral),
    whatever the ED. See the module-docstring residual ruling: the ED→tilt mapping is an open
    contract debt both the spec and the S4b sketch leave unspecified, and the identity element
    composes into no behavior change. This function exists so the EMITTER has exactly one place
    to read a tilt from (single derivation path) and so the day a real rule lands it lands
    behind the same version pin as the drift."""
    check_mapping_version()
    _finite_ed(ed)
    return 1.0
