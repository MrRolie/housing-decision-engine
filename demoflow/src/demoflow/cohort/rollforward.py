"""Owner-household stock-flow roll-forward (spec §5, I1). t->t+1 equation, every
death term exactly once; band-entry-only entrants; NEVER re-anchored to ISQ 75+
stocks. Reconciliation retention = fraction of an initial 75 owner cohort whose
unit is still owned (remain + widow-retained) after a decade of decrements."""
from dataclasses import dataclass
from typing import Callable

from demoflow.cohort.decrements import partition_couple, partition_solo
from demoflow.errors import CalibrationError

QxProvider = Callable[[int, str, int], float]

# Spec §5 band entry. Below this the CPM decrement is NOT ours to apply — pre-75 mortality is
# ISQ-embedded and disjoint, so decrementing there is the I1 double-count in miniature.
BAND_ENTRY_AGE = 75


@dataclass(frozen=True)
class Stock:
    couple: float = 0.0
    solo_m: float = 0.0
    solo_f: float = 0.0

    @property
    def owner_units(self) -> float:
        return self.couple + self.solo_m + self.solo_f


def roll_one_year(stock: Stock, age: int, year: int, q_live: float, qx: QxProvider):
    """Return (next_stock, exits) with exits = {'estate':..., 'living':...}. Every
    death term appears exactly once. Widows (one-dies) are RETAINED into next-year
    Solo of the surviving sex (exit-eligible only from the NEXT year).

    THE AGE GUARD IS LOAD-BEARING, and it guards a SILENCE, not an error (measured
    run 10, re-measured live in tests/test_rollforward.py): the mortality engine
    returns `0.0` for ages 0-17 and clamps negatives into that same range, so an
    out-of-domain age does not raise — it produces a zero-mortality roll-forward whose
    every number stays plausible. `qx` is caller-supplied, so this module cannot
    delegate the domain to the engine even in principle; it owns its own. The bound is
    the SPEC's band entry, not the engine's table floor (18): between 18 and 74 the
    engine answers with a real hazard, and that hazard is precisely the one ISQ has
    already applied — using it is the I1 double-count. Upper end deliberately unbounded
    here: the 100+ absorbing-bucket cap is the multi-year roller's design (spec §8),
    and a point lookup has no basis for presuming it.
    """
    if age < BAND_ENTRY_AGE:
        raise CalibrationError(
            f"roll_one_year age {age} is below spec §5 band entry {BAND_ENTRY_AGE}; "
            "pre-75 mortality is ISQ-embedded (the engine returns a silent 0.0 below 18 "
            "and a double-counted hazard from 18-74)"
        )
    q_m = qx(age, "M", year)
    q_f = qx(age, "F", year)
    pc = partition_couple(q_m, q_f, q_live)
    ps_m = partition_solo(q_m, q_live)
    ps_f = partition_solo(q_f, q_live)

    couple_next = stock.couple * pc["remain"]
    solo_m_next = stock.solo_m * ps_m["remain"] + stock.couple * pc["widow_to_solo_m"]
    solo_f_next = stock.solo_f * ps_f["remain"] + stock.couple * pc["widow_to_solo_f"]

    estate = (stock.couple * pc["both_die"] + stock.solo_m * ps_m["death"] + stock.solo_f * ps_f["death"])
    living = (stock.couple * pc["living_exit"] + stock.solo_m * ps_m["living_exit"] + stock.solo_f * ps_f["living_exit"])
    return Stock(couple_next, solo_m_next, solo_f_next), {"estate": estate, "living": living}


def roll_cohort_decade(start_age: int, start_year: int, q_live: float, qx: QxProvider,
                       years: int = 10, initial: Stock = Stock(couple=1000.0)) -> float:
    """Roll an owner cohort a decade; return retained-ownership fraction
    (remain + widow-retained) / initial. Couples are decremented PER SEX (q_m off the
    male curve, q_f off the female curve, both via `qx`) — not on one blended curve.
    This feeds the reconciliation ENVELOPE (gross-error backstop); the exactly-once
    guarantee is the oracle-exact mutation test above, not this band."""
    stock = initial
    initial_units = stock.owner_units
    for k in range(years):
        stock, _ = roll_one_year(stock, start_age + k, start_year + k, q_live, qx)
    return stock.owner_units / initial_units


def _add(a: Stock, b: Stock) -> Stock:
    return Stock(a.couple + b.couple, a.solo_m + b.solo_m, a.solo_f + b.solo_f)


def roll_cohort_multi_year(base: dict[int, Stock], entrants_per_year: float,
                           start_year: int, n_years: int, q_live: float,
                           qx: QxProvider) -> dict[int, dict[int, Stock]]:
    """Roll an age-indexed set of owner cohorts forward n_years. Each year every cohort
    transitions and ages by one; the 100+ bucket is ABSORBING (spec §8, codex r5-F6) — the
    age-99 age-ins AND the surviving prior 100+ stock BOTH land in age 100 and ACCUMULATE
    (never overwritten or reinitialized), each decremented exactly once. NEW entrants enter
    EXACTLY ONCE at BAND_ENTRY_AGE (spec §5 stock-flow discipline). Returns {year: {age: Stock}}.

    THE ENTRANT ASSIGNMENT IS SAFE ONLY BECAUSE OF `roll_one_year`'S AGE GUARD, and the
    coupling is stated here so a future change to `BAND_ENTRY_AGE` surfaces it: nothing can age
    INTO the band-entry slot, because the lowest age this function may hold is BAND_ENTRY_AGE
    itself (the guard raises below it) and aging sends it to BAND_ENTRY_AGE+1. Entrants are
    therefore the slot's SOLE source, so the assignment destroys nothing. It is an assignment
    and NOT an accumulation ON PURPOSE — entering once is the invariant — so were band entry
    ever lowered while an older cohort remained in `base`, it would silently overwrite real
    age-ins. The guard is what keeps the two compatible.

    ENTRANT COMPOSITION IS A CALLER OBLIGATION THIS FUNCTION DOES NOT MODEL — stated at the
    seam, on gates.py's precedent, rather than left for a caller to infer from the signature.
    A scalar `entrants_per_year` is booked as `Stock(couple=...)`: whole-cohort COUNTS, given
    the household-state mix that makes fixture arithmetic hand-checkable. It is NOT the
    production mix. Spec §5 derives band-entry composition from the INITIALIZATION EQUATIONS
    (three-bucket per-sex Couple / Solo_m / Solo_f on that year's newly-aged-75 ISQ
    population), so a real run's entrants are per-year and per-state, never one number.
    Plan Task 29's pipeline owns that signature; this is the fixture-scale roller the oracle
    pins the mechanism on.

    NO ARGUMENT VALIDATION HERE, deliberately: the age domain is `roll_one_year`'s and it is
    enforced on every cohort every year (raising below band entry), so a second check would
    guard nothing this loop can reach. `n_years` and `entrants_per_year` are left unchecked
    because this layer cannot tell a caller defect from a legitimate figure — fail-loud belongs
    where the domain is actually known, which for entrants is the Task-29 pipeline.
    """
    states: dict[int, dict[int, Stock]] = {start_year: dict(base)}
    for k in range(n_years):
        year = start_year + k
        cur = states[year]
        nxt: dict[int, Stock] = {}
        for age, stock in cur.items():
            rolled, _ = roll_one_year(stock, age, year, q_live, qx)
            dest = min(age + 1, 100)                     # cap into the 100+ absorbing bucket
            nxt[dest] = _add(nxt[dest], rolled) if dest in nxt else rolled
        nxt[BAND_ENTRY_AGE] = Stock(couple=entrants_per_year)   # band-entry: exactly once
        states[year + 1] = nxt
    return states
