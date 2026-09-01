"""The committed golden's PIN and its generation path (spec §10, "Golden artifacts (Tranche 1)").

The golden is `demoflow/artifacts/rankings.json` + `demoflow/artifacts/tripwire_baseline.json`:
generated from the committed data vintage, COMMITTED, then re-generated and diffed by
`tests/test_golden.py`. This module is what the generator script and that test SHARE, and it
exists for one reason — the pin below is a CONTRACT between a producer and a checker that run
in different processes, and two copies of a contract drift.

THE GOLDEN IS ONLY REPRODUCIBLE IF ITS INPUTS ARE PINNED, AND `now` IS AN INPUT. The run's
freshness gate takes an injected `(now_year, now_month)` precisely so a verdict is
reproducible, and NO field of either emitted document records the value that was injected —
spec §7 closes the envelope at {schema, schema_version, data_vintage, assumptions_hash} and
`output/artifacts.py` RAISES on an undeclared position, so the document cannot carry its own
`now` without a spec amendment. That makes the pin the artifact's only provenance for it, and
it is why the pin lives in committed source rather than in a shell invocation someone
remembers. `artifacts/README.md` states the same three facts where a reader meets the files.

`GOLDEN_NOW_MONTH` is stated rather than inherited. `run_pipeline` defaults it to 12 — the
FAIL-SAFE end of the freshness axis — and a default is a floor for callers who state nothing,
never a pin: the day that default moves, an inherited golden re-mints itself silently while a
stated one REDS and names the cause. `GOLDEN_DATA_DIR` is stated for the sibling reason
(carry B11): a run with no `data_dir` reads whatever bytes `pins.DATA_DIR` happens to hold,
and a golden whose source is ambient pins nothing a reader can name.

The 2026 year is the plan's own and is not load-bearing in either direction TODAY: all six
tripwire indicators are structurally UNKNOWN on the committed tree, so no freshness comparison
is reached at all. It becomes load-bearing the moment the first real indicator value lands —
which is the same event that re-mints the golden, and `artifacts/README.md` names it as an
expected re-mint rather than a regression.
"""
from pathlib import Path

from demoflow.loaders.pins import DATA_DIR
from demoflow.pipeline import run_pipeline

# demoflow/src/demoflow/golden.py -> demoflow/artifacts. The CLI's `--out` default is the
# relative `artifacts`, which resolves here when `demoflow run` is invoked from `demoflow/`.
GOLDEN_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"

GOLDEN_DATA_DIR = DATA_DIR
GOLDEN_NOW_YEAR = 2026
GOLDEN_NOW_MONTH = 12

# The THREE documents the golden covers (Tranche 2 added `scenario_prior.json`, spec §7(a)),
# named once. `generate_golden`'s caller BINDS this to what the run actually emitted
# (`tests/test_golden.py` asserts the equality), so a fourth document added to `run_pipeline`
# cannot slip past the golden's strict-JSON scan by being absent from a list nobody re-checked.
GOLDEN_ARTIFACTS = ("rankings.json", "tripwire_baseline.json", "scenario_prior.json")


def generate_golden(out_dir=None) -> dict:
    """Run the pipeline over the PINNED inputs, emitting into `out_dir` (default: the golden's
    own committed directory). Returns `run_pipeline`'s record.

    ONE function, called by both the minting script and the golden-diff test, so the committed
    bytes and the bytes the gate re-derives come off the SAME code path — `scripts/gen_headship.py`
    states the same rule for the headship artifact. A test that re-assembled the call itself
    would be a second declaration of the pin, and the first thing it would stop catching is a
    change to the pin.
    """
    return run_pipeline(data_dir=GOLDEN_DATA_DIR,
                        out_dir=Path(out_dir) if out_dir is not None else GOLDEN_DIR,
                        now_year=GOLDEN_NOW_YEAR, now_month=GOLDEN_NOW_MONTH)
