"""Québec-basis guard (spec §2). The engine DEFAULTS to the US RP2014+MP2021
basis; every demoflow entry point sets the QC basis then CHECKS it echoes,
raising BasisError via an explicit if — NEVER a bare assert (stripped under -O).

AND THE BASIS'S IDENTITY, which is the other half of the same §2 boundary. The guard pins the
two basis IDENTIFIERS; it says nothing about the TABLE CONTENT behind them, and the tables are
not in this repo — they ride a uv path dependency with no digest (see the
`source.directory` entry in `uv.lock`). Until run 33 that content was outside the
artifact envelope entirely: `pipeline._source_hashes` ranges over files under `data_dir`, so two
runs over DIFFERENT upstream mortality tables emitted DIFFERENT `rankings.json` bytes under a
BYTE-IDENTICAL identity, and the golden's attribution table then routed the reader to hunt a
code defect that does not exist (data-gate finding F1). `basis_digest` closes it.
"""
import hashlib
import json

from actuarial.compat import active_mortality, get_qx, set_active_mortality

from demoflow.errors import BasisError

QC_BASIS = ("CPM2014_combined", "CPM-B")

# THE ENVELOPE KEY, derived from the pair rather than typed beside it — the tree's own
# one-declaration rule, and the key must say WHICH basis it digests. It is not a filename and
# deliberately does not look like one: nothing under `data_dir` holds these bytes.
BASIS_SOURCE_KEY = f"mortality_basis:{QC_BASIS[0]}+{QC_BASIS[1]}"

# THE DIGESTED SURFACE — the q values the model consumes, not the files behind them. Spec §2
# admits the engine's PUBLIC surface only, so hashing `mortality._DATA_DIR`'s CSVs is closed to
# us; hashing what `q_at` ANSWERS is strictly better anyway, because it covers the base table,
# the improvement scale AND the interpolation the engine applies between them.
#
# THE GRID COVERS the two call sites a run has (the lumped 75+ bucket rolled at
# `pipeline.ROLL_AGE` over every population-lattice year, and the ruling-O reconciliation
# cohort's decade from band entry). On the AGE axis it is a deliberate SUPERSET — the whole
# modeled band against the 75-84 a run reads — because over-covering re-mints the golden on a
# table change that moves no number, which is honest and visible in the envelope. On the YEAR
# axis it is an EXACT cover with NO slack: the committed vintage's lattice is 2021-2051 and the
# supply roll reads every one of them. UNDER-covering ships a moved table under an unchanged
# envelope, which is the finding this closes — so the coverage claim is MEASURED rather than
# commented: `tests/test_basis_guard.py` binds the age axis to the model's own constants, and
# `tests/test_pipeline.py` checks a real run's RECORDED q consumption against this grid. That
# second one is the only binding available for the years, which come from DATA and from no
# constant a unit test could compare against.
BASIS_DIGEST_AGES = tuple(range(75, 101))        # the modeled band, through the 100+ bucket
BASIS_DIGEST_GENDERS = ("F", "M")                # couples are decremented per sex
BASIS_DIGEST_YEARS = tuple(range(2021, 2052))    # the ISQ population lattice


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


def basis_digest() -> str:
    """sha256 (full 64-hex, spec §7's width for a `source_hashes` value) over the Québec q
    surface this model consumes — the basis's content identity for the envelope.

    RECORDED, NOT PINNED, and that is the same class the IRCC feed rides in rather than a
    weaker one: actuarial-system may legitimately re-publish its tables, and a pin here would
    make every such refresh a REFUSAL instead of a re-mint. What §9 needs is ATTRIBUTION — two
    runs over different bytes must be distinguishable — and a digest over the surface actually
    read discharges that.

    It goes through `q_at`, so it cannot read one basis while the model reads another: the same
    guard, the same clamp, the same public entry point. Uncached on purpose — ~1,600 lookups is
    milliseconds, and a cache is one more thing that can answer for a basis that has moved.
    """
    surface = [[age, gender, year, q_at(age, gender, year)]
               for age in BASIS_DIGEST_AGES
               for gender in BASIS_DIGEST_GENDERS
               for year in BASIS_DIGEST_YEARS]
    payload = json.dumps({"basis": list(QC_BASIS), "q": surface}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
