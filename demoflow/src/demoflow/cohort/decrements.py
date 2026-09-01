"""Living-exit calibration for the owner-household roll-forward (spec §5, Invariant I3).

`q_live` is the SURVIVOR-CONDITIONAL living-sale hazard — the rate at which owners who did
NOT die that year exit ownership while alive. It is anchored to the CMHC senior-sale figure
(36% over 5 years, 75+, QC) and annualized as `1−(1−0.36)^(1/5) ≈ 0.0854/yr`, band
[0.06, 0.11]/yr, with the age-shape (flat vs rising) as a sensitivity axis.

I3, stated as the trap it guards: the Myers & Simmons retention numbers (~26–31% of 75+
owners still owning after a decade) are ALL-CAUSE — they include death. They are a SANITY
CHECK on the roll-forward's aggregate output and are NEVER a calibration target for this
hazard; fitting q_live to them folds mortality into the living-exit curve and double-counts
it against the CPM decrement the roll-forward already applies.

UNITS ARE LOAD-BEARING (the reason `constants.q_live_five_year` was deleted): 0.36 is a
FIVE-YEAR rate and carries no band; [0.06, 0.11] belongs to the ANNUAL rate. A tripwire
comparing the 5-year figure against the annual band fires crossed permanently.

WHAT THE RUN USES: `assumptions_hash()` (spec §7 identity envelope) covers
`CENTRAL_ASSUMPTIONS["q_live_per_year"]` = 0.085 — the anchor rounded to its documented
precision. This function DERIVES that anchor; it is not a substitute for reading it. Feeding
its raw return (0.0853899) into the pipeline moves the run's numbers while the hash stays
byte-identical. Consumers read the central value from `demoflow.loaders.constants`.

ANCHOR PROVENANCE, deliberately NOT imported: the literals below are pinned against
`CONSTANTS["cmhc_senior_sale_5yr"]` / `CONSTANTS["q_live_annual"].band` /
`SWEEP_GRID["q_live_per_year"]` by `tests/test_q_live.py`, so drift on either side fails
loudly. The import is not taken here because `demoflow.loaders.constants` pulls pandas
transitively (via `loaders/validate.py`, measured) and this module is pure arithmetic.

THE OTHER HALF OF THIS MODULE is the competing-risk partition algebra (`partition_solo`,
`partition_couple`) — spec §5's PINNED branch structure: death resolves FIRST, living exit is
survivor-conditional on the no-death branch, and widowhood RETAINS the unit (a couple losing
one spouse becomes `Solo` of the surviving sex; the new widow is not living-exit-eligible in
the transition year). Calibration and partition sit together because they share the one
quantity — `q_live` is the hazard the partition splits on — and share `CalibrationError` as
the single fail-loud channel for an out-of-domain probability. Note the two guards use
DIFFERENT domains on purpose: `annualize_q_live` is `[0,1)` (a certain 5-year sale is a data
defect), `_check_unit` is `[0,1]` closed (a certain decrement is degenerate but valid).
"""
from demoflow.errors import CalibrationError

# Annual band, spec §5. Band ENDPOINTS enter only the robustness sweep — a headline run
# evaluates q_live at its central value (constants.CENTRAL_ASSUMPTIONS).
Q_LIVE_BAND: tuple[float, float] = (0.06, 0.11)


def annualize_q_live(five_year_rate: float = 0.36) -> float:
    """Annualize a survivor-conditional 5-year sale rate: `1−(1−r)^(1/5)`.

    The default is the CMHC anchor (36%, 75+, QC, 2021 vintage) → 0.08538989614534731.

    The domain guard is LOAD-BEARING, not decoration: Python evaluates a negative base to a
    fractional power as a COMPLEX number and raises nothing, so `r > 1` would silently
    return a complex "hazard" that propagates into the roll-forward. NaN and inf fall to the
    same comparison (every ordering against NaN is False). The upper bound is STRICT: `r`
    exactly 1.0 is arithmetically fine (→ 1.0/yr) but means certain sale within five years —
    a data defect, not a calibration input. Task 20's `_check_unit` uses an INCLUSIVE
    `<= 1.0` on branch probabilities in this same module; the two domains differ on purpose.
    """
    if not 0.0 <= five_year_rate < 1.0:
        raise CalibrationError(f"five_year_rate out of [0,1): {five_year_rate}")
    return 1.0 - (1.0 - five_year_rate) ** (1.0 / 5.0)


def _check_unit(*qs: float) -> None:
    for q in qs:
        if not 0.0 <= q <= 1.0:
            raise CalibrationError(f"probability outside [0,1]: {q}")


def partition_solo(q_s: float, q_live: float) -> dict[str, float]:
    """Solo owner: death (estate) resolves first; survivors split living-exit vs remain."""
    _check_unit(q_s, q_live)
    surv = 1.0 - q_s
    return {"death": q_s, "living_exit": surv * q_live, "remain": surv * (1.0 - q_live)}


def partition_couple(q_m: float, q_f: float, q_live: float) -> dict[str, float]:
    """Couple owner (spec §5, codex F3): both-die -> estate; exactly-one-dies -> widowed
    Solo of the surviving sex, UNIT RETAINED (widow NOT living-exit-eligible in the
    transition year — the widow branch is disjoint from the no-death branch that splits
    q_live); no-death splits q_live -> living exit vs remain. Branches partition to 1."""
    _check_unit(q_m, q_f, q_live)
    both_die = q_m * q_f
    widow_to_solo_f = q_m * (1.0 - q_f)   # male dies -> surviving female Solo_f
    widow_to_solo_m = q_f * (1.0 - q_m)   # female dies -> surviving male Solo_m
    no_death = (1.0 - q_m) * (1.0 - q_f)
    return {
        "both_die": both_die,
        "widow_to_solo_f": widow_to_solo_f,
        "widow_to_solo_m": widow_to_solo_m,
        "living_exit": no_death * q_live,
        "remain": no_death * (1.0 - q_live),
    }
